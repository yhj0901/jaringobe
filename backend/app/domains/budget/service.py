"""budget 도메인 비즈니스 로직 — 예산안 생성 (게스트 이전 FR-108 + 온보딩 공용)."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.security import utcnow
from app.domains.auth.models import User
from app.domains.budget.models import BudgetPlan
from app.domains.budget.schemas import BudgetPlanCreateRequest, BudgetPlanResponse, MoneyOut


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

    return BudgetPlanResponse(
        id=plan.id,
        household_size=plan.household_size,
        budget=MoneyOut(amount=plan.amount, currency=plan.currency),
        meal_direction=plan.meal_direction,
        source=plan.source,
        created_at=plan.created_at,
    )
