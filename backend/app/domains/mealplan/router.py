"""mealplan 도메인 라우터 — /api/v1/mealplans (생성/조회/재생성).

v1.5: 생성/재생성은 202 Accepted + BackgroundTasks 비동기 (api-spec §3-2·3-5).
"""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.ratelimit import mealplan_user_limiter, store_user_limiter
from app.domains.auth.models import User
from app.domains.mealplan import service
from app.domains.mealplan.schemas import (
    MealCompletionRequest,
    MealOut,
    MealPlanAcceptedResponse,
    MealPlanCartRequest,
    MealPlanCartResponse,
    MealPlanCreateRequest,
    MealPlanResponse,
    MonthlyPlanRequest,
    MonthlyPlanResponse,
    RegenerateRequest,
)

router = APIRouter()


async def _mealplan_rate_limit(user: User = Depends(get_current_user)) -> None:
    """유저 기준 5회/분 (LLM 비용/DoS 방어, CWE-770)."""
    if not mealplan_user_limiter.allow(str(user.id)):
        raise ApiError(429, "RATE_LIMITED", "Too many meal plan requests")


@router.post(
    "/mealplans",
    response_model=MealPlanAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(_mealplan_rate_limit)],
)
async def create_meal_plan(
    payload: MealPlanCreateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MealPlanAcceptedResponse:
    """202 접수 후 백그라운드 생성 — 클라이언트는 GET /mealplans/{id} 폴링 (v1.5)."""
    plan_id = await service.start_meal_plan_generation(db, user, payload)
    background_tasks.add_task(
        service.run_meal_plan_generation,
        plan_id,
        payload.days,
        payload.meals_per_day,
        payload.allergies,
        payload.preferences,
    )
    return MealPlanAcceptedResponse(id=plan_id)


# 주의: /mealplans/latest 는 /mealplans/{plan_id} 보다 먼저 선언 (uuid 파싱 충돌 방지)
@router.get("/mealplans/latest", response_model=MealPlanResponse)
async def get_latest_meal_plan(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MealPlanResponse:
    return await service.get_latest_meal_plan(db, user)


@router.get("/mealplans/{plan_id}", response_model=MealPlanResponse)
async def get_meal_plan(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MealPlanResponse:
    return await service.get_meal_plan(db, user, plan_id)


# 하위 경로(.../meals/{meal_id}/completion)라 /mealplans/{plan_id} 조회와 충돌 없음
@router.put(
    "/mealplans/{plan_id}/meals/{meal_id}/completion",
    response_model=MealOut,
)
async def set_meal_completion(
    plan_id: uuid.UUID,
    meal_id: uuid.UUID,
    payload: MealCompletionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MealOut:
    """식사 완료 설정/해제 → 갱신된 MealOut."""
    return await service.set_meal_completion(db, user, plan_id, meal_id, payload.completed)


@router.post(
    "/mealplans/{plan_id}/regenerate",
    response_model=MealPlanAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(_mealplan_rate_limit)],
)
async def regenerate_meal_plan(
    plan_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    payload: RegenerateRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MealPlanAcceptedResponse:
    """202 접수 후 백그라운드 재생성 — 폴링·완료 푸시는 생성과 동일 패턴 (v1.5)."""
    req = payload or RegenerateRequest()
    accepted_id, days, meals_per_day = await service.start_meal_plan_regeneration(
        db, user, plan_id, req
    )
    background_tasks.add_task(
        service.run_meal_plan_generation,
        accepted_id,
        days,
        meals_per_day,
        req.allergies,
        req.preferences,
    )
    return MealPlanAcceptedResponse(id=accepted_id)


async def _cart_rate_limit(user: User = Depends(get_current_user)) -> None:
    """마트 조회(네이버+LLM)는 비싸므로 store 리미터(3/분) 재사용."""
    if not store_user_limiter.allow(str(user.id)):
        raise ApiError(429, "RATE_LIMITED", "Too many cart requests")


@router.post(
    "/mealplans/{plan_id}/cart",
    response_model=MealPlanCartResponse,
    dependencies=[Depends(_cart_rate_limit)],
)
async def build_shopping_cart(
    plan_id: uuid.UUID,
    payload: MealPlanCartRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MealPlanCartResponse:
    """식단 → 냉장고 감산 → 컬리 장바구니 (원스톱)."""
    req = payload or MealPlanCartRequest()
    return await service.build_shopping_cart(db, user, plan_id, req.mall, req.max_pages)


@router.post(
    "/mealplans/monthly",
    response_model=MonthlyPlanResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_cart_rate_limit)],
)
async def build_monthly_plan(
    payload: MonthlyPlanRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MonthlyPlanResponse:
    """월 예산 → 그 달(남은 일수, 오늘 포함) 식단 + 첫 주기 주문. 예산은 남은 일자 비율만큼."""
    return await service.build_monthly_plan(db, user, payload or MonthlyPlanRequest())
