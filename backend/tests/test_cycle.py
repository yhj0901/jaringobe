"""cycle 상태·설정·스킵 API와 일정/예산 순수 계산 테스트."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.core.security import utcnow
from app.domains.auth.models import User
from app.domains.budget import service as budget_service
from app.domains.budget.models import BudgetPlan
from app.domains.cycle.models import UserCycleSettings
from app.domains.cycle.policy import load_policy
from app.domains.cycle.service import _initial_next_run, cycle_window
from app.domains.mealplan.models import Meal, MealPlan
from app.domains.order.models import Order
from tests.conftest import login

KR_BUDGET = {
    "householdSize": 2,
    "budget": {"amount": "310000", "currency": "KRW"},
    "mealDirection": "health",
    "source": "onboarding",
}


@pytest.fixture(autouse=True)
def _reset_cycle_limiter():
    from app.core.ratelimit import cycle_action_user_limiter

    cycle_action_user_limiter.reset()
    yield
    cycle_action_user_limiter.reset()


async def _login_budget(client, respx_mock) -> tuple[dict, dict]:
    await login(client, respx_mock)
    created = await client.post("/api/v1/budget/plans", json=KR_BUDGET)
    assert created.status_code == 201, created.text
    me = (await client.get("/api/v1/users/me")).json()
    return me, created.json()


async def _draft(db, user_id, cycle_start: date) -> Order:
    now = utcnow()
    order = Order(
        user_id=UUID(str(user_id)),
        meal_plan_id=None,
        store="kurly",
        status="draft",
        frequency="weekly",
        cycle_start=cycle_start,
        next_suggested_at=now + timedelta(days=7),
        estimated_total=Decimal("12000"),
        currency="KRW",
        simulation=True,
        confirmed_at=None,
        auto_confirm_at=now + timedelta(hours=24),
        auto_confirmed=False,
        delivery_state="pending",
    )
    db.add(order)
    await db.commit()
    return order


async def test_get_cycle_lazy_defaults_without_budget(client, db, respx_mock):
    await login(client, respx_mock)
    response = await client.get("/api/v1/cycle")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enabled"] is True
    assert body["frequency"] == "weekly"
    assert body["anchorWeekday"] == 0
    assert body["timezone"] == "Asia/Seoul"
    assert body["autoConfirm"] is True
    assert body["weeklyLimit"] is None
    assert body["simulation"] is True
    assert body["stage"] == "idle"
    assert body["mealPlan"] is None
    assert body["currentOrder"] is None
    assert await db.scalar(select(func.count()).select_from(UserCycleSettings)) == 1


async def test_cycle_state_includes_current_order_and_meal_progress(
    client, db, respx_mock
):
    me, budget = await _login_budget(client, respx_mock)
    initial = (await client.get("/api/v1/cycle")).json()
    cycle_start = date.fromisoformat(initial["cycleStart"])
    plan = MealPlan(
        user_id=UUID(me["id"]),
        budget_plan_id=UUID(budget["id"]),
        status="ready",
        total_cost=Decimal("0"),
        currency="KRW",
        region="KR",
        period_start=cycle_start,
        period_end=cycle_start + timedelta(days=6),
    )
    db.add(plan)
    await db.flush()
    completed_at = utcnow()
    db.add_all(
        [
            Meal(
                meal_plan_id=plan.id,
                plan_date=cycle_start + timedelta(days=index),
                meal_type="breakfast",
                recipe_name=f"meal-{index}",
                completed_at=completed_at if index < 2 else None,
            )
            for index in range(3)
        ]
    )
    order = await _draft(db, me["id"], cycle_start)
    order.meal_plan_id = plan.id
    order.status = "confirmed"
    order.confirmed_at = completed_at
    order.auto_confirm_at = None
    order.auto_confirmed = True
    order.delivery_eta = completed_at + timedelta(days=1)
    order.inbound_at = completed_at
    order.delivery_state = "delivered"
    await db.commit()

    response = await client.get("/api/v1/cycle")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stage"] == "delivered"
    assert body["mealPlan"] == {
        "id": str(plan.id),
        "status": "ready",
        "mealCount": 3,
        "completedMealCount": 2,
    }
    assert body["draftOrder"] is None
    assert body["currentOrder"] == {
        "id": str(order.id),
        "status": "confirmed",
        "deliveryState": "delivered",
        "deliveryEta": (completed_at + timedelta(days=1))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "inboundAt": completed_at.replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "autoConfirmed": True,
    }


async def test_onboarding_completion_creates_settings_and_last_seen(client, db, respx_mock):
    await login(client, respx_mock)
    user = (await db.scalars(select(User))).one()
    assert user.last_seen_at is not None
    created = await client.post("/api/v1/budget/plans", json=KR_BUDGET)
    assert created.status_code == 201, created.text
    setting = (await db.scalars(select(UserCycleSettings))).one()
    assert setting.user_id == user.id
    assert setting.next_run_at is not None


async def test_settings_partial_update_validation_and_rate_limit(client, respx_mock):
    await _login_budget(client, respx_mock)
    updated = await client.put(
        "/api/v1/cycle/settings",
        json={
            "frequency": "biweekly",
            "anchorWeekday": 3,
            "timezone": "UTC",
            "autoConfirm": False,
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["frequency"] == "biweekly"
    assert body["anchorWeekday"] == 3
    assert body["timezone"] == "UTC"
    assert body["autoConfirm"] is False

    invalid = await client.put(
        "/api/v1/cycle/settings", json={"timezone": "Mars/Olympus"}
    )
    assert invalid.status_code == 422
    extra = await client.put(
        "/api/v1/cycle/settings", json={"unexpected": True}
    )
    assert extra.status_code == 422

    # 위 상태 변경 1회와 검증 실패는 리미터 hit에 포함되므로 새로 초기화한다.
    from app.core.ratelimit import cycle_action_user_limiter

    cycle_action_user_limiter.reset()
    for _ in range(5):
        assert (
            await client.put("/api/v1/cycle/settings", json={"enabled": True})
        ).status_code == 200
    limited = await client.put(
        "/api/v1/cycle/settings", json={"enabled": True}
    )
    assert limited.status_code == 429
    assert limited.json()["detail"]["code"] == "RATE_LIMITED"


async def test_auto_confirm_toggle_updates_open_draft(client, db, respx_mock):
    me, _budget = await _login_budget(client, respx_mock)
    state = (await client.get("/api/v1/cycle")).json()
    order = await _draft(db, me["id"], date.fromisoformat(state["cycleStart"]))

    off = await client.put(
        "/api/v1/cycle/settings", json={"autoConfirm": False}
    )
    assert off.status_code == 200, off.text
    await db.refresh(order)
    assert order.auto_confirm_at is None

    on = await client.put(
        "/api/v1/cycle/settings", json={"autoConfirm": True}
    )
    assert on.status_code == 200, on.text
    await db.refresh(order)
    assert order.auto_confirm_at is not None

    paused = await client.put(
        "/api/v1/cycle/settings", json={"enabled": False}
    )
    assert paused.json()["stage"] == "paused"
    await db.refresh(order)
    assert order.auto_confirm_at is None

    resumed = await client.put(
        "/api/v1/cycle/settings", json={"enabled": True}
    )
    assert resumed.status_code == 200
    await db.refresh(order)
    assert order.auto_confirm_at is not None


async def test_skip_is_idempotent_and_cancels_open_draft(client, db, respx_mock):
    me, _budget = await _login_budget(client, respx_mock)
    state = (await client.get("/api/v1/cycle")).json()
    cycle_start = date.fromisoformat(state["cycleStart"])
    order = await _draft(db, me["id"], cycle_start)

    first = await client.post("/api/v1/cycle/skip")
    assert first.status_code == 200, first.text
    assert first.json()["stage"] == "skipped_user"
    assert first.json()["skippedCycleStart"] == cycle_start.isoformat()
    await db.refresh(order)
    assert order.status == "cancelled"
    assert order.auto_confirm_at is None

    second = await client.post("/api/v1/cycle/skip")
    assert second.status_code == 200
    assert second.json()["skippedCycleStart"] == cycle_start.isoformat()


async def test_skip_rejects_confirmed_cycle(client, db, respx_mock):
    me, _budget = await _login_budget(client, respx_mock)
    state = (await client.get("/api/v1/cycle")).json()
    order = await _draft(db, me["id"], date.fromisoformat(state["cycleStart"]))
    order.status = "confirmed"
    order.confirmed_at = utcnow()
    order.auto_confirm_at = None
    await db.commit()

    response = await client.post("/api/v1/cycle/skip")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CYCLE_ALREADY_CONFIRMED"


async def test_timezone_change_after_confirmation_schedules_next_cycle(
    client, db, respx_mock
):
    me, _budget = await _login_budget(client, respx_mock)
    state = (await client.get("/api/v1/cycle")).json()
    order = await _draft(db, me["id"], date.fromisoformat(state["cycleStart"]))
    order.status = "confirmed"
    order.confirmed_at = utcnow()
    order.auto_confirm_at = None
    settings = (await db.scalars(select(UserCycleSettings))).one()
    settings.last_stage = "generated"
    settings.last_generated_cycle_start = order.cycle_start
    await db.commit()

    response = await client.put(
        "/api/v1/cycle/settings", json={"timezone": "Asia/Tokyo"}
    )

    assert response.status_code == 200, response.text
    await db.refresh(settings)
    assert settings.next_run_at is not None
    assert settings.next_run_at > utcnow()
    assert response.json()["stage"] == "confirmed"
    assert await db.scalar(select(func.count()).select_from(Order)) == 1


def test_biweekly_window_uses_three_and_four_day_intervals():
    sunday = datetime(2026, 8, 30, 0, tzinfo=UTC)
    first = cycle_window("biweekly", 0, "UTC", sunday)
    assert first.cycle_start == date(2026, 8, 30)
    assert first.cycle_days == 3
    thursday = cycle_window(
        "biweekly", 0, "UTC", datetime(2026, 9, 3, 0, tzinfo=UTC)
    )
    assert thursday.cycle_start == date(2026, 9, 6)
    assert thursday.cycle_days == 3
    wednesday = cycle_window(
        "biweekly", 0, "UTC", datetime(2026, 9, 2, 0, tzinfo=UTC)
    )
    assert wednesday.cycle_start == date(2026, 9, 2)
    assert wednesday.cycle_days == 4


def test_initial_schedule_skips_a_generation_time_that_already_passed():
    import uuid
    from dataclasses import replace

    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    policy = replace(load_policy(), jitter_minutes=0, stage_local_hour=9)
    next_run = _initial_next_run(
        uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "weekly",
        0,
        "UTC",
        policy,
        now,
    )
    assert next_run == datetime(2026, 9, 1, 9, tzinfo=UTC)


def test_remaining_month_proration_is_decimal_and_unchanged():
    assert budget_service.prorate_remaining_month(
        date(2026, 2, 20), Decimal("310000")
    ) == Decimal("99642.86")


async def test_cycle_limit_accumulates_month_share_across_three_cycles(db):
    """같은 달의 2·3번째 사이클도 앞선 확정액 때문에 한도가 0으로 붕괴하지 않는다."""
    user = User(nickname="예산 누적 사용자", country="KR", currency="KRW")
    db.add(user)
    await db.flush()
    db.add(
        BudgetPlan(
            user_id=user.id,
            household_size=2,
            amount=Decimal("310000"),
            currency="KRW",
            meal_direction="health",
            source="onboarding",
            locked=True,
        )
    )
    await db.flush()

    async def add_confirmed(cycle_start: date, confirmed_at: datetime) -> None:
        db.add(
            Order(
                user_id=user.id,
                meal_plan_id=None,
                store="kurly",
                status="confirmed",
                frequency="weekly",
                cycle_start=cycle_start,
                next_suggested_at=confirmed_at + timedelta(days=7),
                estimated_total=Decimal("70000"),
                currency="KRW",
                simulation=True,
                confirmed_at=confirmed_at,
                auto_confirmed=True,
                delivery_state="pending",
            )
        )
        await db.flush()

    first = date(2026, 8, 1)
    assert await budget_service.cycle_limit(db, user, first, 7, timezone_name="UTC") == Decimal(
        "70000.00"
    )
    await add_confirmed(first, datetime(2026, 8, 5, tzinfo=UTC))

    second = date(2026, 8, 8)
    assert await budget_service.cycle_limit(db, user, second, 7, timezone_name="UTC") == Decimal(
        "70000.00"
    )
    await add_confirmed(second, datetime(2026, 8, 12, tzinfo=UTC))

    third = date(2026, 8, 15)
    assert await budget_service.cycle_limit(db, user, third, 7, timezone_name="UTC") == Decimal(
        "70000.00"
    )


def test_policy_parse_failures_fall_back_without_stopping(monkeypatch, caplog):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "cycle_profile_weekly", "not-json")
    monkeypatch.setattr(settings, "cycle_delivery_lead_days", "[]")
    monkeypatch.setattr(settings, "cycle_expiring_days", '{"US":-1}')
    monkeypatch.setattr(settings, "cycle_unmatched_threshold", "2")
    monkeypatch.setattr(settings, "cycle_stage_local_hour", 99)
    monkeypatch.setattr(settings, "cycle_draft_retry_delays_minutes", "0,bad")
    policy = load_policy()
    assert policy.weekly.generate_lead_days == 5
    assert policy.delivery_days("unknown") == 1
    assert policy.expiring_window("US") == 5
    assert policy.unmatched_threshold == Decimal("0.30")
    assert policy.stage_local_hour == 9
    assert policy.draft_retry_delays_minutes == (1, 5, 15)
    assert "기본값 사용" in caplog.text
