"""budget 도메인 비즈니스 로직 — 예산안 생성(게스트 이전 FR-108) + upsert(v1.2 온보딩·수정)."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.security import utcnow
from app.domains.auth.models import User
from app.domains.budget.models import BudgetPlan
from app.domains.budget.schemas import (
    BudgetPlanCreateRequest,
    BudgetPlanResponse,
    BudgetPlanUpsertRequest,
    MoneyOut,
)
from app.domains.household.models import HouseholdMember


def _to_response(plan: BudgetPlan) -> BudgetPlanResponse:
    return BudgetPlanResponse(
        id=plan.id,
        household_size=plan.household_size,
        budget=MoneyOut(amount=plan.amount, currency=plan.currency),
        meal_direction=plan.meal_direction,
        source=plan.source,
        locked=plan.locked,
        cuisines=list(plan.cuisines),
        created_at=plan.created_at,
    )


async def create_budget_plan(
    db: AsyncSession, user: User, payload: BudgetPlanCreateRequest
) -> BudgetPlanResponse:
    """예산안 생성. 기존 활성 예산안 보유 시 409 BUDGET_PLAN_EXISTS.

    성공 시 users.onboarding_completed_at 세팅 (게스트 이전 성공 = 온보딩 완료).
    """
    existing = await db.scalar(select(BudgetPlan.id).where(BudgetPlan.user_id == user.id))
    if existing is not None:
        raise ApiError(409, "BUDGET_PLAN_EXISTS", "User already has an active budget plan")

    plan = BudgetPlan(
        user_id=user.id,
        household_size=payload.household_size,
        amount=payload.budget.amount,
        currency=payload.budget.currency,
        meal_direction=payload.meal_direction,
        source=payload.source,
    )
    db.add(plan)
    if user.onboarding_completed_at is None:
        user.onboarding_completed_at = utcnow()
    try:
        await db.commit()
    except IntegrityError as exc:  # 동시 요청 경합 — UNIQUE(user_id) 위반
        await db.rollback()
        raise ApiError(409, "BUDGET_PLAN_EXISTS", "User already has an active budget plan") from exc
    await db.refresh(plan)

    return _to_response(plan)


async def upsert_budget_plan(
    db: AsyncSession, user: User, payload: BudgetPlanUpsertRequest
) -> tuple[BudgetPlanResponse, bool]:
    """예산안 upsert (v1.2) — 없으면 생성(created=True), 있으면 갱신.

    성공 시 household 가 존재하면 users.onboarding_completed_at 세팅
    (이미 세팅돼 있으면 유지). 반환: (응답, 생성 여부).
    """
    plan = await db.scalar(select(BudgetPlan).where(BudgetPlan.user_id == user.id))
    created = plan is None
    if plan is None:
        plan = BudgetPlan(
            user_id=user.id,
            household_size=payload.household_size,
            amount=payload.budget.amount,
            currency=payload.budget.currency,
            meal_direction=payload.meal_direction,
            source="onboarding",
            locked=payload.locked,
            cuisines=list(payload.cuisines),
        )
        db.add(plan)
    else:
        plan.household_size = payload.household_size
        plan.amount = payload.budget.amount
        plan.currency = payload.budget.currency
        plan.meal_direction = payload.meal_direction
        plan.locked = payload.locked
        plan.cuisines = list(payload.cuisines)

    if user.onboarding_completed_at is None:
        has_household = await db.scalar(
            select(HouseholdMember.id).where(HouseholdMember.user_id == user.id).limit(1)
        )
        if has_household is not None:
            user.onboarding_completed_at = utcnow()

    try:
        await db.commit()
    except IntegrityError as exc:  # 동시 생성 경합 — UNIQUE(user_id) 위반
        await db.rollback()
        raise ApiError(409, "BUDGET_PLAN_EXISTS", "Concurrent budget plan creation") from exc
    await db.refresh(plan)

    return _to_response(plan), created
