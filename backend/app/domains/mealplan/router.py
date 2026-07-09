"""mealplan 도메인 라우터 — /api/v1/mealplans (생성/조회/재생성)."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.ratelimit import mealplan_user_limiter
from app.domains.auth.models import User
from app.domains.mealplan import service
from app.domains.mealplan.schemas import (
    MealPlanCreateRequest,
    MealPlanResponse,
    RegenerateRequest,
)

router = APIRouter()


async def _mealplan_rate_limit(user: User = Depends(get_current_user)) -> None:
    """유저 기준 5회/분 (LLM 비용/DoS 방어, CWE-770)."""
    if not mealplan_user_limiter.allow(str(user.id)):
        raise ApiError(429, "RATE_LIMITED", "Too many meal plan requests")


@router.post(
    "/mealplans",
    response_model=MealPlanResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_mealplan_rate_limit)],
)
async def create_meal_plan(
    payload: MealPlanCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MealPlanResponse:
    return await service.create_meal_plan(db, user, payload)


@router.get("/mealplans/{plan_id}", response_model=MealPlanResponse)
async def get_meal_plan(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MealPlanResponse:
    return await service.get_meal_plan(db, user, plan_id)


@router.post(
    "/mealplans/{plan_id}/regenerate",
    response_model=MealPlanResponse,
    dependencies=[Depends(_mealplan_rate_limit)],
)
async def regenerate_meal_plan(
    plan_id: uuid.UUID,
    payload: RegenerateRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MealPlanResponse:
    return await service.regenerate_meal_plan(db, user, plan_id, payload or RegenerateRequest())
