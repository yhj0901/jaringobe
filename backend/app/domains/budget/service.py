"""budget 도메인 비즈니스 로직 — 예산안 CRUD + 월/사이클 안분."""

import calendar
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
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

_CENT = Decimal("0.01")


def prorate(monthly: Decimal, days: Iterable[date]) -> Decimal:
    """각 날짜가 속한 달의 일수로 월 예산을 안분해 합산한다."""
    total = sum(
        (
            monthly / Decimal(calendar.monthrange(day.year, day.month)[1])
            for day in days
        ),
        Decimal("0"),
    )
    return total.quantize(_CENT, rounding=ROUND_HALF_UP)


def prorate_remaining_month(as_of: date, monthly: Decimal) -> Decimal:
    """오늘 포함 월말까지의 기존 월간 안분 결과와 동일한 공개 함수."""
    dim = calendar.monthrange(as_of.year, as_of.month)[1]
    remaining = dim - as_of.day + 1
    return prorate(
        monthly,
        (as_of + timedelta(days=offset) for offset in range(remaining)),
    )


async def cycle_limit(
    db: AsyncSession,
    user: User,
    cycle_start: date,
    cycle_days: int,
    *,
    timezone_name: str = "Asia/Seoul",
) -> Decimal:
    """월초부터 이번 사이클 끝까지의 누적 안분액에서 같은 기간 확정액을 차감한다."""
    plan = await db.scalar(select(BudgetPlan).where(BudgetPlan.user_id == user.id))
    if plan is None:
        raise ApiError(409, "BUDGET_PLAN_REQUIRED", "Create a budget plan first")

    month_start = date(cycle_start.year, cycle_start.month, 1)
    if cycle_start.month == 12:
        next_month = date(cycle_start.year + 1, 1, 1)
    else:
        next_month = date(cycle_start.year, cycle_start.month + 1, 1)
    accrual_end = min(cycle_start + timedelta(days=cycle_days), next_month)
    share = prorate(
        plan.amount,
        (
            month_start + timedelta(days=offset)
            for offset in range((accrual_end - month_start).days)
        ),
    )
    tz = ZoneInfo(timezone_name)
    start_utc = datetime.combine(month_start, time.min, tzinfo=tz).astimezone(UTC)
    end_utc = datetime.combine(accrual_end, time.min, tzinfo=tz).astimezone(UTC)

    # 순환 import를 막기 위해 주문 모델은 함수 실행 시점에만 로드한다.
    from app.domains.order.models import Order

    committed = await db.scalar(
        select(func.coalesce(func.sum(Order.estimated_total), Decimal("0"))).where(
            Order.user_id == user.id,
            Order.status == "confirmed",
            Order.confirmed_at >= start_utc,
            Order.confirmed_at < end_utc,
        )
    )
    return max(Decimal("0"), share - Decimal(committed or 0)).quantize(
        _CENT, rounding=ROUND_HALF_UP
    )


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
        from app.domains.cycle.service import ensure_settings_for_onboarding

        await ensure_settings_for_onboarding(db, user)
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
            from app.domains.cycle.service import ensure_settings_for_onboarding

            await ensure_settings_for_onboarding(db, user)

    try:
        await db.commit()
    except IntegrityError as exc:  # 동시 생성 경합 — UNIQUE(user_id) 위반
        await db.rollback()
        raise ApiError(409, "BUDGET_PLAN_EXISTS", "Concurrent budget plan creation") from exc
    await db.refresh(plan)

    return _to_response(plan), created


async def get_budget_plan(db: AsyncSession, user: User) -> BudgetPlanResponse:
    """내 예산안 조회 — 없으면 404 (설정 페이지 요약·부분 수정 병합용, api-spec v1.3.1)."""
    plan = (
        await db.execute(select(BudgetPlan).where(BudgetPlan.user_id == user.id))
    ).scalar_one_or_none()
    if plan is None:
        raise ApiError(404, "BUDGET_PLAN_NOT_FOUND", "No budget plan for user")
    return _to_response(plan)
