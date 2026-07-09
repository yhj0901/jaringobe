import time

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentHousehold, DbSession
from app.models.budget import Budget
from app.models.mealplan import Meal, MealPlan
from app.schemas.mealplan import MealPlanCreate, MealPlanRead, RegenerateRequest
from app.services.budget import get_current_budget
from app.services.mealplan.planner import (
    generate_meal_plan,
    regenerate_meal_plan,
    to_mealplan_read,
)

router = APIRouter(prefix="/api/v1/mealplans", tags=["mealplan"])

# 간단 in-memory rate limit (재생성) — v1 단일 인스턴스 전제. 멀티 인스턴스는 Redis 필요.
_RL: dict[int, list[float]] = {}
_RL_WINDOW = 60.0
_RL_LIMIT = 5


def _rate_ok(household_id: int) -> bool:
    now = time.monotonic()
    recent = [t for t in _RL.get(household_id, []) if now - t < _RL_WINDOW]
    if len(recent) >= _RL_LIMIT:
        _RL[household_id] = recent
        return False
    recent.append(now)
    _RL[household_id] = recent
    return True


async def _load_plan(db: DbSession, plan_id: int) -> MealPlan | None:
    stmt = (
        select(MealPlan)
        .where(MealPlan.id == plan_id)
        .options(selectinload(MealPlan.meals).selectinload(Meal.ingredients))
    )
    return (await db.execute(stmt)).scalar_one_or_none()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=MealPlanRead)
async def create(
    data: MealPlanCreate, household: CurrentHousehold, db: DbSession
) -> MealPlanRead:
    budget = await get_current_budget(db, household.id)
    if budget is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "BUDGET_NOT_SET", "message": "set a budget first"},
        )
    plan, notes = await generate_meal_plan(db, household, budget, data)
    return to_mealplan_read(plan, budget, notes)


@router.get("/{plan_id}", response_model=MealPlanRead)
async def get(plan_id: int, household: CurrentHousehold, db: DbSession) -> MealPlanRead:
    plan = await _load_plan(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "meal plan not found"})
    if plan.household_id != household.id:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "not your resource"})
    budget = await db.get(Budget, plan.budget_id)
    return to_mealplan_read(plan, budget)


@router.post("/{plan_id}/regenerate", response_model=MealPlanRead)
async def regenerate(
    plan_id: int, household: CurrentHousehold, db: DbSession,
    body: RegenerateRequest | None = None,
) -> MealPlanRead:
    req = body or RegenerateRequest()
    if not _rate_ok(household.id):
        raise HTTPException(status_code=429, detail={"code": "RATE_LIMITED", "message": "too many regenerations"})
    plan = await _load_plan(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "meal plan not found"})
    if plan.household_id != household.id:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "not your resource"})
    budget = await db.get(Budget, plan.budget_id)
    try:
        plan, notes = await regenerate_meal_plan(db, household, plan, budget, req)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "meal not found"})
    return to_mealplan_read(plan, budget, notes)
