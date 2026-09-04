"""주간 사이클 계산·상태 조회·사용자 단계 오케스트레이션."""

from __future__ import annotations

import logging
import uuid
import zlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.security import utcnow
from app.domains.auth.models import User
from app.domains.budget import service as budget_service
from app.domains.budget.models import BudgetPlan
from app.domains.budget.schemas import MoneyOut
from app.domains.cycle.models import UserCycleSettings
from app.domains.cycle.policy import CyclePolicy, load_policy
from app.domains.cycle.schemas import (
    CycleSettingsUpdateRequest,
    CycleState,
    DraftOrderSummary,
    MealPlanSummary,
)
from app.domains.mealplan import service as mealplan_service
from app.domains.mealplan.models import Meal, MealPlan
from app.domains.mealplan.schemas import MealPlanCreateRequest
from app.domains.notification import service as notification_service
from app.domains.order import service as order_service
from app.domains.order.models import Order

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CycleWindow:
    cycle_start: date
    cycle_days: int


@dataclass(frozen=True)
class GenerationJob:
    setting_id: uuid.UUID
    plan_id: uuid.UUID
    cycle_start: date
    days: int
    meals_per_day: int
    allergies: list[str]
    preferences: list[str]


def _delivery_weekdays(frequency: str, anchor_weekday: int) -> tuple[int, ...]:
    if frequency == "biweekly":
        return tuple(sorted((anchor_weekday, (anchor_weekday + 3) % 7)))
    return (anchor_weekday,)


def _js_weekday(value: date) -> int:
    """Python Monday=0 → JS Sunday=0."""
    return (value.weekday() + 1) % 7


def cycle_window(
    frequency: str,
    anchor_weekday: int,
    timezone_name: str,
    now: datetime | None = None,
) -> CycleWindow:
    """사용자 로컬 기준 다음(오늘 포함) 배송일과 그 사이클 길이."""
    current = (now or utcnow()).astimezone(ZoneInfo(timezone_name)).date()
    weekdays = _delivery_weekdays(frequency, anchor_weekday)
    delta = min((weekday - _js_weekday(current)) % 7 for weekday in weekdays)
    start = current + timedelta(days=delta)
    next_start = next_cycle_start(start, frequency, anchor_weekday)
    return CycleWindow(cycle_start=start, cycle_days=(next_start - start).days)


def next_cycle_start(value: date, frequency: str, anchor_weekday: int) -> date:
    weekdays = _delivery_weekdays(frequency, anchor_weekday)
    for days in range(1, 8):
        candidate = value + timedelta(days=days)
        if _js_weekday(candidate) in weekdays:
            return candidate
    raise AssertionError("cycle weekday must repeat within seven days")


def previous_cycle_start(value: date, frequency: str, anchor_weekday: int) -> date:
    weekdays = _delivery_weekdays(frequency, anchor_weekday)
    for days in range(1, 8):
        candidate = value - timedelta(days=days)
        if _js_weekday(candidate) in weekdays:
            return candidate
    raise AssertionError("cycle weekday must repeat within seven days")


def deterministic_jitter(user_id: uuid.UUID, max_minutes: int) -> int:
    if max_minutes <= 0:
        return 0
    return zlib.crc32(user_id.bytes) % max_minutes


def _stage_at(
    cycle_start: date,
    lead_days: int,
    timezone_name: str,
    user_id: uuid.UUID,
    policy: CyclePolicy,
) -> datetime:
    local = datetime.combine(
        cycle_start - timedelta(days=lead_days),
        time(policy.stage_local_hour),
        tzinfo=ZoneInfo(timezone_name),
    )
    local += timedelta(minutes=deterministic_jitter(user_id, policy.jitter_minutes))
    return local.astimezone(UTC)


def generation_at(
    cycle_start: date,
    settings: UserCycleSettings,
    policy: CyclePolicy,
) -> datetime:
    return _stage_at(
        cycle_start,
        policy.profile(settings.frequency).generate_lead_days,
        settings.timezone,
        settings.user_id,
        policy,
    )


def draft_at(
    cycle_start: date,
    settings: UserCycleSettings,
    policy: CyclePolicy,
) -> datetime:
    return _stage_at(
        cycle_start,
        policy.profile(settings.frequency).draft_lead_days,
        settings.timezone,
        settings.user_id,
        policy,
    )


def _next_generation_at(
    cycle_start: date,
    settings: UserCycleSettings,
    policy: CyclePolicy,
) -> datetime:
    return generation_at(
        next_cycle_start(cycle_start, settings.frequency, settings.anchor_weekday),
        settings,
        policy,
    )


def _initial_next_run(
    user_id: uuid.UUID,
    frequency: str,
    anchor_weekday: int,
    timezone_name: str,
    policy: CyclePolicy,
    now: datetime,
) -> datetime:
    window = cycle_window(frequency, anchor_weekday, timezone_name, now)
    cycle_start = window.cycle_start
    while True:
        local = datetime.combine(
            cycle_start - timedelta(
                days=policy.profile(frequency).generate_lead_days
            ),
            time(policy.stage_local_hour),
            tzinfo=ZoneInfo(timezone_name),
        )
        local += timedelta(
            minutes=deterministic_jitter(user_id, policy.jitter_minutes)
        )
        candidate = local.astimezone(UTC)
        if candidate > now:
            return candidate
        cycle_start = next_cycle_start(cycle_start, frequency, anchor_weekday)


async def get_or_create_settings(
    db: AsyncSession,
    user: User,
    *,
    policy: CyclePolicy | None = None,
    now: datetime | None = None,
) -> UserCycleSettings:
    """사용자당 1행 lazy 생성. PostgreSQL ON CONFLICT 로 동시 최초 호출도 멱등."""
    existing = await db.scalar(
        select(UserCycleSettings).where(UserCycleSettings.user_id == user.id)
    )
    if existing is not None:
        return existing

    policy = policy or load_policy()
    now = now or utcnow()
    next_run_at = _initial_next_run(
        user.id, "weekly", 0, "Asia/Seoul", policy, now
    )
    stmt = (
        pg_insert(UserCycleSettings)
        .values(
            user_id=user.id,
            enabled=True,
            frequency="weekly",
            anchor_weekday=0,
            timezone="Asia/Seoul",
            auto_confirm=True,
            next_run_at=next_run_at,
        )
        .on_conflict_do_nothing(index_elements=[UserCycleSettings.user_id])
    )
    await db.execute(stmt)
    return (
        await db.execute(
            select(UserCycleSettings).where(UserCycleSettings.user_id == user.id)
        )
    ).scalar_one()


async def ensure_settings_for_onboarding(db: AsyncSession, user: User) -> None:
    """온보딩 완료 쓰기 경로에서 호출하는 idempotent 보조 진입점."""
    if user.id is None:  # 커밋 전 객체/단위 테스트 대역에서는 PK 생성 뒤 다음 호출에 생성
        return
    await get_or_create_settings(db, user)


async def _current_order(
    db: AsyncSession, user_id: uuid.UUID, cycle_start: date
) -> Order | None:
    return await db.scalar(
        select(Order)
        .where(Order.user_id == user_id, Order.cycle_start == cycle_start)
        .order_by(Order.created_at.desc())
        .limit(1)
    )


async def _current_plan(
    db: AsyncSession, user_id: uuid.UUID, cycle_start: date
) -> MealPlan | None:
    return await db.scalar(
        select(MealPlan)
        .where(MealPlan.user_id == user_id, MealPlan.period_start == cycle_start)
        .order_by(MealPlan.created_at.desc())
        .limit(1)
    )


def _derive_stage(
    settings: UserCycleSettings,
    cycle_start: date,
    plan: MealPlan | None,
    order: Order | None,
) -> str:
    if not settings.enabled:
        return "paused"
    if order is not None and order.status == "confirmed":
        return "delivered" if order.inbound_at is not None else "confirmed"
    if order is not None and order.status == "draft":
        return "drafted"
    if order is not None and order.status == "awaiting_user":
        return "awaiting_user"
    if settings.skip_until == cycle_start:
        return "skipped_user"
    if plan is not None and plan.status == "processing":
        return "generating"
    if settings.last_stage == "drafted" and order is None:
        return "nothing_to_order"
    if settings.last_stage in (
        "generated",
        "generate_failed",
        "skipped_dormant",
        "deferred_quota",
    ):
        return settings.last_stage
    if plan is not None and plan.status in ("ready", "over_budget"):
        return "generated"
    return "idle"


async def build_cycle_state(
    db: AsyncSession,
    user: User,
    settings: UserCycleSettings,
    *,
    now: datetime | None = None,
) -> CycleState:
    now = now or utcnow()
    window = cycle_window(
        settings.frequency, settings.anchor_weekday, settings.timezone, now
    )
    plan = await _current_plan(db, user.id, window.cycle_start)
    order = await _current_order(db, user.id, window.cycle_start)
    budget = await db.scalar(select(BudgetPlan).where(BudgetPlan.user_id == user.id))
    weekly_limit: MoneyOut | None = None
    if budget is not None:
        limit = await budget_service.cycle_limit(
            db,
            user,
            window.cycle_start,
            window.cycle_days,
            timezone_name=settings.timezone,
        )
        weekly_limit = MoneyOut(amount=limit, currency=budget.currency)

    draft_order = None
    if order is not None and order.status in ("draft", "awaiting_user"):
        draft_order = DraftOrderSummary(
            id=order.id,
            status=order.status,
            estimated_total=MoneyOut(
                amount=order.estimated_total, currency=order.currency
            ),
            auto_confirm_at=order.auto_confirm_at,
            blocked_reason=order.blocked_reason,
            delivery_eta=order.delivery_eta,
        )

    return CycleState(
        enabled=settings.enabled,
        frequency=settings.frequency,  # type: ignore[arg-type]
        anchor_weekday=settings.anchor_weekday,
        timezone=settings.timezone,
        auto_confirm=settings.auto_confirm,
        cycle_start=window.cycle_start,
        cycle_days=window.cycle_days,
        stage=_derive_stage(settings, window.cycle_start, plan, order),  # type: ignore[arg-type]
        next_run_at=settings.next_run_at,
        skipped_cycle_start=settings.skip_until,
        weekly_limit=weekly_limit,
        meal_plan=(MealPlanSummary(id=plan.id, status=plan.status) if plan is not None else None),
        draft_order=draft_order,
        simulation=True,
    )


async def get_cycle_state(db: AsyncSession, user: User) -> CycleState:
    settings = await get_or_create_settings(db, user)
    await db.commit()
    return await build_cycle_state(db, user, settings)


async def get_order_cycle_context(
    db: AsyncSession, user: User
) -> order_service.OrderCycleContext:
    """order 라우터에 의존성 주입할 최소 사이클 정책을 제공한다."""
    policy = load_policy()
    settings = await get_or_create_settings(db, user, policy=policy)
    await db.commit()
    window = cycle_window(
        settings.frequency, settings.anchor_weekday, settings.timezone
    )
    return order_service.OrderCycleContext(
        cycle_start=window.cycle_start,
        frequency=settings.frequency,
        timezone=settings.timezone,
        local_hour=policy.stage_local_hour,
        cancel_window_days=policy.cancel_window_days,
        delivery_unknown_attempts=policy.delivery_unknown_attempts,
        delivery_lead_days=policy.delivery_lead_days,
        delivery_lead_days_default=policy.delivery_lead_days_default,
    )


async def update_settings(
    db: AsyncSession,
    user: User,
    payload: CycleSettingsUpdateRequest,
) -> CycleState:
    policy = load_policy()
    now = utcnow()
    settings = await get_or_create_settings(db, user, policy=policy, now=now)
    schedule_fields = {"frequency", "anchor_weekday", "timezone"}
    should_recompute = bool(payload.model_fields_set & schedule_fields)
    for field in payload.model_fields_set:
        value = getattr(payload, field)
        if value is not None:
            setattr(settings, field, value)

    window = cycle_window(
        settings.frequency, settings.anchor_weekday, settings.timezone, now
    )
    if should_recompute:
        settings.next_run_at = (
            draft_at(window.cycle_start, settings, policy)
            if settings.last_generated_cycle_start == window.cycle_start
            else _initial_next_run(
                settings.user_id,
                settings.frequency,
                settings.anchor_weekday,
                settings.timezone,
                policy,
                now,
            )
        )
    if payload.auto_confirm is False or payload.enabled is False:
        await order_service.clear_open_auto_confirm(db, user.id)
    elif payload.auto_confirm is True or (
        payload.enabled is True and settings.auto_confirm
    ):
        await order_service.restore_open_auto_confirm(
            db,
            user.id,
            policy.profile(settings.frequency).grace_hours,
            now,
        )
    await db.commit()
    return await build_cycle_state(db, user, settings, now=now)


async def skip_cycle(db: AsyncSession, user: User) -> CycleState:
    policy = load_policy()
    now = utcnow()
    settings = await get_or_create_settings(db, user, policy=policy, now=now)
    window = cycle_window(
        settings.frequency, settings.anchor_weekday, settings.timezone, now
    )
    confirmed = await db.scalar(
        select(Order.id).where(
            Order.user_id == user.id,
            Order.cycle_start == window.cycle_start,
            Order.status == "confirmed",
        )
    )
    if confirmed is not None:
        raise ApiError(
            409,
            "CYCLE_ALREADY_CONFIRMED",
            "confirmed cycle cannot be skipped",
        )
    if settings.skip_until != window.cycle_start:
        settings.skip_until = window.cycle_start
        settings.last_stage = "skipped_user"
        settings.stage_attempts = 0
        settings.next_run_at = _next_generation_at(window.cycle_start, settings, policy)
        await order_service.cancel_open_order_for_cycle(
            db, user.id, window.cycle_start
        )
        _log_transition(user.id, "skipped_user", "skipped_user", window.cycle_start)
        await db.commit()
    return await build_cycle_state(db, user, settings, now=now)


def _log_transition(
    user_id: uuid.UUID, stage: str, reason: str, cycle_start: date
) -> None:
    logger.info(
        "사이클 단계 전이",
        extra={
            "user_id": str(user_id),
            "stage": stage,
            "reason": reason,
            "cycle_start": cycle_start.isoformat(),
        },
    )


async def is_active_user(
    db: AsyncSession,
    user: User,
    settings: UserCycleSettings,
    cycle_start: date,
    policy: CyclePolicy,
    now: datetime,
) -> bool:
    if user.last_seen_at is None or user.last_seen_at < now - timedelta(
        days=policy.active_seen_days
    ):
        return False
    previous = previous_cycle_start(
        cycle_start, settings.frequency, settings.anchor_weekday
    )
    tz = ZoneInfo(settings.timezone)
    start_utc = datetime.combine(previous, time.min, tzinfo=tz).astimezone(UTC)
    end_utc = datetime.combine(cycle_start, time.min, tzinfo=tz).astimezone(UTC)
    completions = await db.scalar(
        select(func.count(Meal.id))
        .join(MealPlan, Meal.meal_plan_id == MealPlan.id)
        .where(
            MealPlan.user_id == user.id,
            Meal.completed_at.is_not(None),
            Meal.completed_at >= start_utc,
            Meal.completed_at < end_utc,
        )
    )
    return int(completions or 0) >= policy.active_completion_min


def _deferred_until(
    settings: UserCycleSettings, policy: CyclePolicy, now: datetime
) -> datetime:
    tz = ZoneInfo(settings.timezone)
    local_now = now.astimezone(tz)
    local = datetime.combine(
        local_now.date() + timedelta(days=1),
        time(policy.stage_local_hour),
        tzinfo=tz,
    )
    local += timedelta(
        minutes=deterministic_jitter(settings.user_id, policy.jitter_minutes)
    )
    return local.astimezone(UTC)


async def _process_generation_stage(
    db: AsyncSession,
    user: User,
    settings: UserCycleSettings,
    window: CycleWindow,
    policy: CyclePolicy,
    now: datetime,
    generation_allowed: bool,
) -> GenerationJob | None:
    await order_service.expire_open_orders_before(db, user.id, window.cycle_start)
    if settings.skip_until == window.cycle_start:
        settings.last_stage = "skipped_user"
        settings.next_run_at = _next_generation_at(window.cycle_start, settings, policy)
        _log_transition(user.id, "skipped_user", "skipped_user", window.cycle_start)
        await db.commit()
        return None
    if settings.last_generated_cycle_start == window.cycle_start:
        plan = await _current_plan(db, user.id, window.cycle_start)
        if (
            plan is not None
            and plan.status == "failed"
            and settings.stage_attempts == 1
        ):
            if not generation_allowed:
                settings.last_stage = "deferred_quota"
                settings.next_run_at = _deferred_until(settings, policy, now)
                _log_transition(
                    user.id, "deferred_quota", "deferred_quota", window.cycle_start
                )
                await db.commit()
                return None
            plan.status = "processing"
            plan.total_cost = Decimal("0")
            settings.last_stage = "generated"
            settings.stage_attempts = 2
            settings.last_generated_at = now
            settings.next_run_at = draft_at(window.cycle_start, settings, policy)
            await db.commit()
            _log_transition(
                user.id, "generated", "generation_retry", window.cycle_start
            )
            return GenerationJob(
                setting_id=settings.id,
                plan_id=plan.id,
                cycle_start=window.cycle_start,
                days=window.cycle_days,
                meals_per_day=3,
                allergies=[],
                preferences=[],
            )
        settings.last_stage = "generate_failed" if plan and plan.status == "failed" else "generated"
        if settings.last_stage == "generate_failed":
            settings.next_run_at = _next_generation_at(
                window.cycle_start, settings, policy
            )
        else:
            settings.next_run_at = draft_at(window.cycle_start, settings, policy)
        _log_transition(user.id, settings.last_stage, "idempotent_skip", window.cycle_start)
        await db.commit()
        return None
    if not await is_active_user(db, user, settings, window.cycle_start, policy, now):
        settings.last_stage = "skipped_dormant"
        settings.next_run_at = _next_generation_at(window.cycle_start, settings, policy)
        first_pause = settings.dormant_since is None
        if first_pause:
            settings.dormant_since = now
        _log_transition(
            user.id, "skipped_dormant", "skipped_dormant", window.cycle_start
        )
        await db.commit()
        if first_pause:
            await notification_service.notify_cycle_event(
                user.id,
                "cycle_paused",
                "push.cyclePaused",
                "/orders",
            )
        return None
    if not generation_allowed:
        settings.last_stage = "deferred_quota"
        settings.next_run_at = _deferred_until(settings, policy, now)
        _log_transition(user.id, "deferred_quota", "deferred_quota", window.cycle_start)
        await db.commit()
        return None

    request = MealPlanCreateRequest(
        days=window.cycle_days,
        meals_per_day=3,
        allergies=[],
        preferences=[],
    )
    settings.last_generated_cycle_start = window.cycle_start
    settings.last_generated_at = now
    settings.last_stage = "generated"
    settings.stage_attempts = 0
    settings.next_run_at = draft_at(window.cycle_start, settings, policy)
    plan_id = await mealplan_service.start_meal_plan_generation(
        db,
        user,
        request,
        period_start=window.cycle_start,
    )
    _log_transition(user.id, "generated", "generated", window.cycle_start)
    return GenerationJob(
        setting_id=settings.id,
        plan_id=plan_id,
        cycle_start=window.cycle_start,
        days=window.cycle_days,
        meals_per_day=3,
        allergies=[],
        preferences=[],
    )


async def _process_draft_stage(
    db: AsyncSession,
    user: User,
    settings: UserCycleSettings,
    window: CycleWindow,
    policy: CyclePolicy,
    now: datetime,
) -> None:
    try:
        order = await order_service.create_draft(
            db,
            user,
            cycle_start=window.cycle_start,
            frequency=settings.frequency,
            auto_confirm=settings.auto_confirm,
            grace_hours=policy.profile(settings.frequency).grace_hours,
            force_unmatched=settings.stage_attempts >= len(policy.draft_retry_delays_minutes),
        )
    except Exception:
        await db.rollback()
        settings = (
            await db.execute(
                select(UserCycleSettings)
                .where(UserCycleSettings.id == settings.id)
                .with_for_update()
            )
        ).scalar_one()
        settings.stage_attempts += 1
        if settings.stage_attempts <= len(policy.draft_retry_delays_minutes):
            delay = policy.draft_retry_delays_minutes[settings.stage_attempts - 1]
            settings.next_run_at = now + timedelta(minutes=delay)
            await db.commit()
            return
        settings.last_stage = "generate_failed"
        settings.next_run_at = _next_generation_at(window.cycle_start, settings, policy)
        _log_transition(
            user.id, "generate_failed", "draft_fallback_failed", window.cycle_start
        )
        await db.commit()
        return
    settings.last_stage = "drafted"
    settings.stage_attempts = 0
    settings.next_run_at = _next_generation_at(window.cycle_start, settings, policy)
    _log_transition(user.id, "drafted", "drafted", window.cycle_start)
    await db.commit()
    if order is not None:
        await notification_service.notify_cycle_event(
            user.id,
            "order_approval",
            "push.orderApproval",
            "/orders",
        )


async def process_due_setting(
    db: AsyncSession,
    user: User,
    settings: UserCycleSettings,
    *,
    policy: CyclePolicy,
    now: datetime,
    generation_allowed: bool,
) -> GenerationJob | None:
    """due 사용자 단계 1건 처리. 주문 확정·inbound 스캔과 상태를 섞지 않는다."""
    window = cycle_window(
        settings.frequency, settings.anchor_weekday, settings.timezone, now
    )
    if (
        settings.last_stage == "generated"
        and settings.last_generated_cycle_start == window.cycle_start
    ):
        await _process_draft_stage(db, user, settings, window, policy, now)
        return None
    return await _process_generation_stage(
        db,
        user,
        settings,
        window,
        policy,
        now,
        generation_allowed,
    )


async def count_generated_today(db: AsyncSession, now: datetime) -> int:
    start = datetime.combine(now.astimezone(UTC).date(), time.min, tzinfo=UTC)
    count = await db.scalar(
        select(func.count(UserCycleSettings.id)).where(
            UserCycleSettings.last_generated_at >= start
        )
    )
    return int(count or 0)


async def finish_generation_job(job: GenerationJob) -> None:
    """비동기 생성 결과를 사용자 단계에 수렴시키고 실패는 한 번만 재시도 예약한다."""
    now = utcnow()
    policy = load_policy()
    async with SessionLocal() as db:
        plan = await db.get(MealPlan, job.plan_id)
        settings = (
            await db.execute(
                select(UserCycleSettings)
                .where(UserCycleSettings.id == job.setting_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if plan is None or settings is None:
            return
        if settings.last_generated_cycle_start != job.cycle_start:
            return
        if plan.status == "failed":
            settings.last_stage = "generate_failed"
            if settings.stage_attempts == 0:
                settings.stage_attempts = 1
                settings.next_run_at = _deferred_until(settings, policy, now)
            else:
                settings.next_run_at = _next_generation_at(
                    job.cycle_start, settings, policy
                )
            _log_transition(
                settings.user_id,
                "generate_failed",
                "generate_failed",
                job.cycle_start,
            )
        else:
            settings.last_stage = "generated"
            settings.stage_attempts = 0
            settings.dormant_since = None
            settings.next_run_at = max(
                draft_at(job.cycle_start, settings, policy), now
            )
        await db.commit()
