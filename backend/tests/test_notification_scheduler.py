"""식사 리마인더 스케줄러 테스트 — 판정 로직(process_due_reminders) 직접 호출 검증.

주기 루프(run_scheduler_loop)와 분리된 판정/처리 함수를 검증한다 (architecture.md 3-7).
"""

from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.core.security import utcnow
from app.domains.notification.models import NotificationLog, NotificationSetting
from app.domains.notification.scheduler import process_due_reminders
from app.domains.notification.service import compute_next_send_at
from tests.conftest import login

EXPO_URL = "https://exp.host/--/api/v2/push/send"
TOKEN = "ExponentPushToken[scheduler-test-token]"


@pytest.fixture(autouse=True)
def _reset_limiters():
    from app.core.ratelimit import mealplan_user_limiter, notification_user_limiter

    mealplan_user_limiter.reset()
    notification_user_limiter.reset()
    yield
    mealplan_user_limiter.reset()
    notification_user_limiter.reset()


# ---------- next_send_at 계산 (로컬시각 + IANA 존 → UTC) ----------


class TestComputeNextSendAt:
    def test_today_when_local_time_not_passed(self):
        now = datetime(2026, 7, 14, 0, 0, tzinfo=UTC)  # KST 09:00
        nxt = compute_next_send_at(time(12, 0), "Asia/Seoul", now)
        assert nxt == datetime(2026, 7, 14, 3, 0, tzinfo=UTC)  # KST 12:00

    def test_tomorrow_when_local_time_passed(self):
        now = datetime(2026, 7, 14, 5, 0, tzinfo=UTC)  # KST 14:00 — 12:00 지남
        nxt = compute_next_send_at(time(12, 0), "Asia/Seoul", now)
        assert nxt == datetime(2026, 7, 15, 3, 0, tzinfo=UTC)

    def test_dst_transition_keeps_wall_clock(self):
        """미국 DST 종료(2026-11-01) 경계 — 로컬 08:00 벽시계가 유지된다."""
        # ET 2026-10-31 20:00 (EDT, UTC-4) → 다음 08:00 은 11-01 (EST, UTC-5)
        now = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)  # ET 10-31 20:00
        nxt = compute_next_send_at(time(8, 0), "America/New_York", now)
        assert nxt == datetime(2026, 11, 1, 13, 0, tzinfo=UTC)  # EST 08:00 = UTC 13:00


# ---------- 발송 판정 통합 ----------


async def _setup_user_with_plan(client, db, respx_mock) -> dict:
    """로그인 + 예산 + 오늘(UTC) 1일 3끼 플랜 생성 → GET 상세 반환."""
    await login(client, respx_mock)
    res = await client.post(
        "/api/v1/budget/plans",
        json={
            "householdSize": 2,
            "budget": {"amount": "500000", "currency": "KRW"},
            "mealDirection": "health",
            "source": "onboarding",
        },
    )
    assert res.status_code == 201
    res = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 3})
    assert res.status_code == 202
    got = await client.get(f"/api/v1/mealplans/{res.json()['id']}")
    assert got.status_code == 200
    return got.json()


async def _register_device(client) -> None:
    res = await client.put(
        "/api/v1/notifications/devices",
        json={"token": TOKEN, "platform": "ios", "locale": "ko", "timezone": "UTC"},
    )
    assert res.status_code == 200


async def _make_due_setting(
    db, client, type_: str = "meal_reminder_lunch", enabled: bool = True
) -> None:
    """설정 lazy 생성 후 대상 type 을 UTC 존 + 과거 next_send_at 으로 due 상태로 만든다."""
    assert (await client.get("/api/v1/notifications/settings")).status_code == 200
    setting = await db.scalar(
        select(NotificationSetting).where(NotificationSetting.type == type_)
    )
    setting.enabled = enabled
    setting.timezone = "UTC"
    setting.local_time = time(12, 0)
    setting.next_send_at = utcnow() - timedelta(minutes=1) if enabled else None
    await db.commit()


async def test_due_reminder_sends_push_and_reschedules(client, db, respx_mock):
    plan = await _setup_user_with_plan(client, db, respx_mock)
    await _register_device(client)
    await _make_due_setting(db, client, "meal_reminder_lunch")

    route = respx_mock.post(EXPO_URL).respond(json={"data": [{"status": "ok"}]})
    now = utcnow()
    sent = await process_due_reminders(now=now)
    assert sent == 1

    # 본문: 메뉴명 포함 + 딥링크 path (CWE-359 — 메뉴명까지만)
    import json

    message = json.loads(route.calls[0].request.content)[0]
    lunch = next(m for m in plan["meals"] if m["mealType"] == "lunch")
    assert lunch["recipeName"] in message["title"]
    assert message["data"]["path"] == f"/mealplan/{plan['id']}"

    log = (await db.scalars(select(NotificationLog))).one()
    assert log.type == "meal_reminder_lunch"
    assert log.template_key == "push.mealReminder"

    # 발송 후 next_send_at 익일 재계산 (미래)
    setting = await db.scalar(
        select(NotificationSetting).where(NotificationSetting.type == "meal_reminder_lunch")
    )
    await db.refresh(setting)
    assert setting.next_send_at is not None
    assert setting.next_send_at > now


async def test_completed_meal_skips_send_but_reschedules(client, db, respx_mock):
    plan = await _setup_user_with_plan(client, db, respx_mock)
    await _register_device(client)
    lunch = next(m for m in plan["meals"] if m["mealType"] == "lunch")
    res = await client.put(
        f"/api/v1/mealplans/{plan['id']}/meals/{lunch['id']}/completion",
        json={"completed": True},
    )
    assert res.status_code == 200
    await _make_due_setting(db, client, "meal_reminder_lunch")

    # Expo route 미등록 — 발송 시도가 있으면 실패
    now = utcnow()
    sent = await process_due_reminders(now=now)
    assert sent == 0
    logs = (await db.scalars(select(NotificationLog))).all()
    assert logs == []  # 스킵은 로그 없음

    setting = await db.scalar(
        select(NotificationSetting).where(NotificationSetting.type == "meal_reminder_lunch")
    )
    await db.refresh(setting)
    assert setting.next_send_at > now  # 스킵해도 익일 재계산


async def test_no_meal_today_skips_send(client, db, respx_mock):
    """당일 해당 끼니 식단이 없으면 발송하지 않는다 (FR-006)."""
    await login(client, respx_mock)
    await _register_device(client)
    await _make_due_setting(db, client, "meal_reminder_dinner")

    sent = await process_due_reminders(now=utcnow())
    assert sent == 0
    assert (await db.scalars(select(NotificationLog))).all() == []


async def test_disabled_setting_not_selected(client, db, respx_mock):
    await _setup_user_with_plan(client, db, respx_mock)
    await _register_device(client)
    await _make_due_setting(db, client, "meal_reminder_lunch", enabled=False)

    sent = await process_due_reminders(now=utcnow())
    assert sent == 0
    assert (await db.scalars(select(NotificationLog))).all() == []


# ---------- BUG-005: 다중 플랜 공존 시 구플랜 폴백 금지 ----------


async def _create_second_plan(client, meals_per_day: int = 3) -> dict:
    """기간 중첩 신규 플랜 생성 (구플랜 ready 잔존) → GET 상세 반환."""
    res = await client.post(
        "/api/v1/mealplans", json={"days": 1, "mealsPerDay": meals_per_day}
    )
    assert res.status_code == 202
    got = await client.get(f"/api/v1/mealplans/{res.json()['id']}")
    assert got.status_code == 200
    assert got.json()["status"] in ("ready", "over_budget")
    return got.json()


async def test_multi_plan_completed_latest_meal_skips_old_plan(client, db, respx_mock):
    """최신 플랜 점심 완료 시 구플랜 미완료 점심으로 폴백 발송하지 않는다 (BUG-005, FR-006)."""
    await _setup_user_with_plan(client, db, respx_mock)  # 구플랜 (ready 잔존, 점심 미완료)
    plan2 = await _create_second_plan(client)
    lunch2 = next(m for m in plan2["meals"] if m["mealType"] == "lunch")
    res = await client.put(
        f"/api/v1/mealplans/{plan2['id']}/meals/{lunch2['id']}/completion",
        json={"completed": True},
    )
    assert res.status_code == 200

    await _register_device(client)
    await _make_due_setting(db, client, "meal_reminder_lunch")

    # Expo route 미등록 — 발송 시도가 있으면 실패
    now = utcnow()
    sent = await process_due_reminders(now=now)
    assert sent == 0  # 구플랜 점심이 미완료여도 발송 스킵
    assert (await db.scalars(select(NotificationLog))).all() == []

    setting = await db.scalar(
        select(NotificationSetting).where(NotificationSetting.type == "meal_reminder_lunch")
    )
    await db.refresh(setting)
    assert setting.next_send_at > now  # 스킵해도 익일 재계산


async def test_multi_plan_latest_without_meal_type_skips(client, db, respx_mock):
    """최신 플랜에 해당 끼니 자체가 없으면 구플랜에 있어도 발송 스킵 (BUG-005)."""
    await _setup_user_with_plan(client, db, respx_mock)  # 구플랜 3끼 (점심 있음)
    await _create_second_plan(client, meals_per_day=1)  # 최신 플랜 = 아침만

    await _register_device(client)
    await _make_due_setting(db, client, "meal_reminder_lunch")

    sent = await process_due_reminders(now=utcnow())
    assert sent == 0
    assert (await db.scalars(select(NotificationLog))).all() == []


async def test_multi_plan_sends_from_latest_plan(client, db, respx_mock):
    """다중 플랜 공존 + 최신 플랜 점심 미완료 → 최신 플랜 기준으로 발송 (딥링크 포함)."""
    import json

    await _setup_user_with_plan(client, db, respx_mock)  # 구플랜
    plan2 = await _create_second_plan(client)  # 최신 플랜 (점심 미완료)

    await _register_device(client)
    await _make_due_setting(db, client, "meal_reminder_lunch")

    route = respx_mock.post(EXPO_URL).respond(json={"data": [{"status": "ok"}]})
    sent = await process_due_reminders(now=utcnow())
    assert sent == 1

    message = json.loads(route.calls[0].request.content)[0]
    assert message["data"]["path"] == f"/mealplan/{plan2['id']}"  # 구플랜 아닌 최신 플랜


# ---------- 주기 루프 / lifespan ----------


async def test_run_scheduler_loop_survives_errors(monkeypatch):
    """개별 사이클 예외가 루프를 멈추지 않는다."""
    import asyncio

    from app.domains.notification import scheduler as sched

    calls = {"n": 0}

    async def flaky(now=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated cycle failure")
        return 0

    monkeypatch.setattr(sched, "process_due_reminders", flaky)
    task = asyncio.create_task(sched.run_scheduler_loop(interval_seconds=0.01))
    await asyncio.sleep(0.08)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls["n"] >= 2  # 첫 사이클 실패 후에도 계속 실행


async def test_lifespan_starts_and_cancels_scheduler(monkeypatch):
    """lifespan 이 설정에 따라 스케줄러 태스크를 기동/정지한다."""
    import asyncio

    from app.core.config import get_settings
    from app.main import app, lifespan

    started = {"n": 0}

    async def fake_loop(interval_seconds):
        started["n"] += 1
        while True:
            await asyncio.sleep(60)

    import app.main as main_mod

    monkeypatch.setattr(main_mod, "run_scheduler_loop", fake_loop)
    monkeypatch.setattr(get_settings(), "reminder_scheduler_enabled", True)
    async with lifespan(app):
        await asyncio.sleep(0)
    assert started["n"] == 1


async def test_lifespan_disabled_no_scheduler(monkeypatch):
    import asyncio

    import app.main as main_mod
    from app.core.config import get_settings
    from app.main import app, lifespan

    started = {"n": 0}

    async def fake_loop(interval_seconds):
        started["n"] += 1

    monkeypatch.setattr(main_mod, "run_scheduler_loop", fake_loop)
    monkeypatch.setattr(get_settings(), "reminder_scheduler_enabled", False)
    async with lifespan(app):
        await asyncio.sleep(0)
    assert started["n"] == 0


async def test_processing_or_failed_plan_not_reminded(client, db, respx_mock, monkeypatch):
    """processing/failed 플랜의 끼니는 리마인더 대상이 아니다."""
    from app.domains.mealplan import service as svc

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(svc, "run_meal_plan_generation", _noop)
    await login(client, respx_mock)
    res = await client.post(
        "/api/v1/budget/plans",
        json={
            "householdSize": 2,
            "budget": {"amount": "500000", "currency": "KRW"},
            "mealDirection": "health",
            "source": "onboarding",
        },
    )
    assert res.status_code == 201
    res = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 3})
    assert res.status_code == 202  # 백그라운드 무력화 → processing 유지 (meals 없음)
    await _register_device(client)
    await _make_due_setting(db, client, "meal_reminder_lunch")

    sent = await process_due_reminders(now=utcnow())
    assert sent == 0
    assert (await db.scalars(select(NotificationLog))).all() == []
