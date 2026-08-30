"""cycle 스케줄러 단계·비용 상한·실패 재시도 테스트."""

import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.domains.auth.models import User
from app.domains.budget.models import BudgetPlan
from app.domains.cycle import service as cycle_service
from app.domains.cycle.models import UserCycleSettings
from app.domains.cycle.policy import load_policy
from app.domains.cycle import scheduler as cycle_scheduler
from app.domains.cycle.scheduler import process_due_auto_confirms
from app.domains.mealplan.models import Meal, MealIngredient, MealPlan
from app.domains.order.models import Order, OrderItem
from app.domains.store.connection_models import StoreConnection

NOW = datetime(2026, 8, 25, 0, 0, tzinfo=UTC)
CYCLE_START = date(2026, 8, 30)


async def _active_cycle(db) -> tuple[User, BudgetPlan, UserCycleSettings]:
    user = User(
        nickname="활성 사용자",
        country="KR",
        currency="KRW",
        last_seen_at=NOW,
    )
    db.add(user)
    await db.flush()
    budget = BudgetPlan(
        user_id=user.id,
        household_size=2,
        amount=Decimal("310000"),
        currency="KRW",
        meal_direction="health",
        source="onboarding",
        locked=False,
    )
    db.add(budget)
    await db.flush()
    prior = MealPlan(
        user_id=user.id,
        budget_plan_id=budget.id,
        status="ready",
        total_cost=Decimal("0"),
        currency="KRW",
        region="KR",
        period_start=date(2026, 8, 23),
        period_end=date(2026, 8, 29),
    )
    db.add(prior)
    await db.flush()
    meal = Meal(
        meal_plan_id=prior.id,
        plan_date=date(2026, 8, 24),
        meal_type="dinner",
        recipe_name="완료 식사",
        completed_at=datetime(2026, 8, 24, 12, tzinfo=UTC),
    )
    db.add(meal)
    setting = UserCycleSettings(
        user_id=user.id,
        enabled=True,
        frequency="weekly",
        anchor_weekday=0,
        timezone="UTC",
        auto_confirm=True,
        next_run_at=NOW,
    )
    db.add(setting)
    await db.commit()
    return user, budget, setting


def _policy():
    return replace(load_policy(), jitter_minutes=0, stage_local_hour=0)


async def test_generation_records_weekly_key_at_acceptance_and_finishes(db):
    user, _budget, setting = await _active_cycle(db)
    job = await cycle_service.process_due_setting(
        db,
        user,
        setting,
        policy=_policy(),
        now=NOW,
        generation_allowed=True,
    )
    assert job is not None
    assert job.cycle_start == CYCLE_START
    assert setting.last_generated_cycle_start == CYCLE_START
    assert setting.last_generated_at == NOW
    assert setting.last_stage == "generated"
    assert await cycle_service.count_generated_today(db, NOW) == 1

    plan = await db.get(MealPlan, job.plan_id)
    assert plan.status == "processing"
    assert plan.period_start == CYCLE_START
    plan.status = "ready"
    await db.commit()
    await cycle_service.finish_generation_job(job)
    await db.refresh(setting)
    assert setting.last_stage == "generated"
    assert setting.stage_attempts == 0
    assert setting.next_run_at is not None


async def test_due_settings_scan_locks_and_accepts_generation(db, monkeypatch):
    _user, _budget, _setting = await _active_cycle(db)
    scheduled = []

    async def _capture(job):
        scheduled.append(job)

    monkeypatch.setattr(cycle_scheduler, "_run_generation_job", _capture)
    processed, generated = await cycle_scheduler.process_due_settings(NOW, _policy())
    await asyncio.sleep(0)
    assert (processed, generated) == (1, 1)
    assert len(scheduled) == 1


async def test_generation_failure_retries_same_plan_once_and_obeys_daily_quota(db):
    user, _budget, setting = await _active_cycle(db)
    policy = _policy()
    job = await cycle_service.process_due_setting(
        db,
        user,
        setting,
        policy=policy,
        now=NOW,
        generation_allowed=True,
    )
    assert job is not None
    plan = await db.get(MealPlan, job.plan_id)
    plan.status = "failed"
    await db.commit()
    await cycle_service.finish_generation_job(job)
    await db.refresh(setting)
    assert setting.last_stage == "generate_failed"
    assert setting.stage_attempts == 1

    deferred = await cycle_service.process_due_setting(
        db,
        user,
        setting,
        policy=policy,
        now=NOW + timedelta(days=1),
        generation_allowed=False,
    )
    assert deferred is None
    assert setting.last_stage == "deferred_quota"
    assert plan.status == "failed"

    retry = await cycle_service.process_due_setting(
        db,
        user,
        setting,
        policy=policy,
        now=NOW + timedelta(days=2),
        generation_allowed=True,
    )
    assert retry is not None
    assert retry.plan_id == job.plan_id
    assert setting.stage_attempts == 2
    assert plan.status == "processing"
    assert await db.scalar(select(func.count()).select_from(MealPlan)) == 2

    plan.status = "failed"
    await db.commit()
    await cycle_service.finish_generation_job(retry)
    await db.refresh(setting)
    assert setting.last_stage == "generate_failed"
    assert setting.next_run_at > NOW + timedelta(days=2)


async def test_initial_daily_quota_defers_without_creating_plan(db):
    user, _budget, setting = await _active_cycle(db)
    result = await cycle_service.process_due_setting(
        db,
        user,
        setting,
        policy=_policy(),
        now=NOW,
        generation_allowed=False,
    )
    assert result is None
    assert setting.last_stage == "deferred_quota"
    assert setting.last_generated_cycle_start is None
    assert await db.scalar(select(func.count()).select_from(MealPlan)) == 1


async def test_inactive_user_is_paused_once_without_generation(db):
    user, _budget, setting = await _active_cycle(db)
    user.last_seen_at = NOW - timedelta(days=15)
    await db.commit()
    result = await cycle_service.process_due_setting(
        db,
        user,
        setting,
        policy=_policy(),
        now=NOW,
        generation_allowed=True,
    )
    assert result is None
    assert setting.last_stage == "skipped_dormant"
    assert setting.dormant_since == NOW
    assert await db.scalar(select(func.count()).select_from(MealPlan)) == 1


async def test_generated_plan_becomes_saved_draft(db):
    user, budget, setting = await _active_cycle(db)
    current = MealPlan(
        user_id=user.id,
        budget_plan_id=budget.id,
        status="ready",
        total_cost=Decimal("10000"),
        currency="KRW",
        region="KR",
        period_start=CYCLE_START,
        period_end=CYCLE_START + timedelta(days=6),
    )
    db.add(current)
    await db.flush()
    meal = Meal(
        meal_plan_id=current.id,
        plan_date=CYCLE_START,
        meal_type="breakfast",
        recipe_name="계란요리",
    )
    db.add(meal)
    await db.flush()
    db.add(
        MealIngredient(
            meal_id=meal.id,
            name="계란",
            quantity=Decimal("4"),
            unit="ea",
        )
    )
    setting.last_stage = "generated"
    setting.last_generated_cycle_start = CYCLE_START
    setting.last_generated_at = NOW - timedelta(days=3)
    setting.next_run_at = NOW
    await db.commit()

    result = await cycle_service.process_due_setting(
        db,
        user,
        setting,
        policy=_policy(),
        now=NOW,
        generation_allowed=True,
    )
    assert result is None
    order = (await db.scalars(select(Order))).one()
    assert order.status == "draft"
    assert order.cycle_start == CYCLE_START
    assert order.auto_confirm_at is not None
    assert setting.last_stage == "drafted"


async def test_auto_confirm_due_us_order_moves_to_awaiting_user(db):
    user = User(
        nickname="US user",
        country="US",
        currency="USD",
        last_seen_at=NOW,
    )
    db.add(user)
    await db.flush()
    setting = UserCycleSettings(
        user_id=user.id,
        enabled=True,
        frequency="weekly",
        anchor_weekday=0,
        timezone="UTC",
        auto_confirm=True,
        next_run_at=NOW + timedelta(days=1),
    )
    order = Order(
        user_id=user.id,
        meal_plan_id=None,
        store="walmart",
        status="draft",
        frequency="weekly",
        cycle_start=CYCLE_START,
        next_suggested_at=NOW + timedelta(days=7),
        estimated_total=Decimal("0"),
        currency="USD",
        simulation=True,
        confirmed_at=None,
        auto_confirm_at=NOW - timedelta(minutes=1),
        auto_confirmed=False,
        delivery_state="pending",
    )
    order.items = [
        OrderItem(
            name="eggs",
            quantity=Decimal("12"),
            unit="ea",
            line_type="needed",
            matched=False,
        )
    ]
    db.add_all([setting, order])
    await db.commit()

    assert await process_due_auto_confirms(NOW, _policy()) == 1
    await db.refresh(order)
    assert order.status == "awaiting_user"
    assert order.blocked_reason == "US_NO_PRICE"
    assert order.auto_confirm_at is None
    assert order.reminded_at == NOW


async def test_auto_confirm_due_passes_all_gates(db):
    user, budget, setting = await _active_cycle(db)
    current = MealPlan(
        user_id=user.id,
        budget_plan_id=budget.id,
        status="ready",
        total_cost=Decimal("0"),
        currency="KRW",
        region="KR",
        period_start=CYCLE_START,
        period_end=CYCLE_START + timedelta(days=6),
    )
    db.add(current)
    await db.flush()
    meal = Meal(
        meal_plan_id=current.id,
        plan_date=CYCLE_START,
        meal_type="breakfast",
        recipe_name="계란밥",
    )
    db.add(meal)
    await db.flush()
    db.add(
        MealIngredient(
            meal_id=meal.id,
            name="계란",
            quantity=Decimal("4"),
            unit="ea",
        )
    )
    db.add(
        StoreConnection(
            user_id=user.id,
            store="kurly",
            status="connected",
            connected_at=NOW,
        )
    )
    order = Order(
        user_id=user.id,
        meal_plan_id=current.id,
        store="kurly",
        status="draft",
        frequency="weekly",
        cycle_start=CYCLE_START,
        next_suggested_at=NOW + timedelta(days=7),
        estimated_total=Decimal("0"),
        currency="KRW",
        simulation=True,
        confirmed_at=None,
        auto_confirm_at=NOW - timedelta(minutes=1),
        auto_confirmed=False,
        delivery_state="pending",
    )
    order.items = [
        OrderItem(
            name="계란",
            quantity=Decimal("4"),
            unit="ea",
            line_type="needed",
            matched=False,
        )
    ]
    db.add(order)
    setting.next_run_at = NOW + timedelta(days=1)
    await db.commit()

    permissive = replace(_policy(), unmatched_threshold=Decimal("1"))
    assert await process_due_auto_confirms(NOW, permissive) == 1
    await db.refresh(order)
    assert order.status == "confirmed"
    assert order.auto_confirmed is True
    assert order.auto_confirm_at is None
    assert order.delivery_eta is not None
