"""notification 도메인 통합 테스트 — devices/settings API (api-spec 6-A)."""

from datetime import UTC, datetime, time

import pytest
from sqlalchemy import func, select

from app.domains.notification.models import DeviceToken, NotificationSetting
from tests.conftest import login

TOKEN_A = "ExponentPushToken[aaaaaaaaaaaaaaaaaaaaaa]"
TOKEN_B = "ExponentPushToken[bbbbbbbbbbbbbbbbbbbbbb]"


@pytest.fixture(autouse=True)
def _reset_notification_limiter():
    from app.core.ratelimit import notification_user_limiter

    notification_user_limiter.reset()
    yield
    notification_user_limiter.reset()


def _device_body(token: str = TOKEN_A, **overrides) -> dict:
    body = {
        "token": token,
        "platform": "ios",
        "locale": "ko",
        "timezone": "Asia/Seoul",
        "appVersion": "1.0.0",
    }
    body.update(overrides)
    return body


# ---------- PUT /notifications/devices ----------


class TestRegisterDevice:
    async def test_requires_auth(self, client):
        res = await client.put("/api/v1/notifications/devices", json=_device_body())
        assert res.status_code == 401
        assert res.json()["detail"]["code"] == "AUTH_REQUIRED"

    async def test_register_creates_row(self, client, db, respx_mock):
        await login(client, respx_mock)
        res = await client.put("/api/v1/notifications/devices", json=_device_body())
        assert res.status_code == 200, res.text
        assert res.json()["id"]
        row = (await db.scalars(select(DeviceToken))).one()
        assert row.token == TOKEN_A
        assert row.platform == "ios"
        assert row.locale == "ko"
        assert row.timezone == "Asia/Seoul"
        assert row.app_version == "1.0.0"

    async def test_register_is_idempotent_upsert(self, client, db, respx_mock):
        await login(client, respx_mock)
        first = await client.put("/api/v1/notifications/devices", json=_device_body())
        # 같은 token 재등록 — locale/timezone 최신화 + 행 1개 유지
        second = await client.put(
            "/api/v1/notifications/devices",
            json=_device_body(locale="en", timezone="America/New_York"),
        )
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert await db.scalar(select(func.count()).select_from(DeviceToken)) == 1
        row = (await db.scalars(select(DeviceToken))).one()
        assert row.locale == "en"
        assert row.timezone == "America/New_York"

    async def test_register_transfers_token_from_other_user(self, client, db, respx_mock):
        """타 유저 소유 token 은 현 유저로 이전 — 이전 소유자 오발송 차단 (CWE-639)."""
        await login(client, respx_mock, provider_user_id="kakao-1", email="a@example.com")
        assert (
            await client.put("/api/v1/notifications/devices", json=_device_body())
        ).status_code == 200

        await login(client, respx_mock, provider_user_id="kakao-2", email="b@example.com")
        res = await client.put("/api/v1/notifications/devices", json=_device_body())
        assert res.status_code == 200
        rows = (await db.scalars(select(DeviceToken))).all()
        assert len(rows) == 1
        me = await client.get("/api/v1/users/me")
        assert str(rows[0].user_id) == me.json()["id"]

    @pytest.mark.parametrize(
        "overrides",
        [
            {"token": "not-an-expo-token"},
            {"token": "ExponentPushToken[" + "x" * 4100 + "]"},  # 길이 상한
            {"platform": "web"},
            {"locale": "fr"},
            {"timezone": "Not/AZone"},
            {"appVersion": "x" * 21},
        ],
    )
    async def test_register_validation_422(self, client, respx_mock, overrides):
        await login(client, respx_mock)
        res = await client.put(
            "/api/v1/notifications/devices", json=_device_body(**overrides)
        )
        assert res.status_code == 422
        assert res.json()["detail"]["code"] == "VALIDATION_ERROR"

    async def test_register_rate_limited(self, client, respx_mock):
        await login(client, respx_mock)
        for _ in range(10):
            assert (
                await client.put("/api/v1/notifications/devices", json=_device_body())
            ).status_code == 200
        res = await client.put("/api/v1/notifications/devices", json=_device_body())
        assert res.status_code == 429
        assert res.json()["detail"]["code"] == "RATE_LIMITED"


# ---------- DELETE /notifications/devices/{token} ----------


class TestDeleteDevice:
    async def test_requires_auth(self, client):
        res = await client.delete(f"/api/v1/notifications/devices/{TOKEN_A}")
        assert res.status_code == 401

    async def test_delete_own_token(self, client, db, respx_mock):
        await login(client, respx_mock)
        await client.put("/api/v1/notifications/devices", json=_device_body())
        res = await client.delete(f"/api/v1/notifications/devices/{TOKEN_A}")
        assert res.status_code == 204
        assert await db.scalar(select(func.count()).select_from(DeviceToken)) == 0

    async def test_delete_unknown_token_is_idempotent_204(self, client, respx_mock):
        await login(client, respx_mock)
        res = await client.delete(f"/api/v1/notifications/devices/{TOKEN_B}")
        assert res.status_code == 204

    async def test_delete_other_users_token_does_not_remove(self, client, db, respx_mock):
        """타 유저 토큰 삭제 시도 — 204 이지만 실제 삭제 안 됨 (CWE-639)."""
        await login(client, respx_mock, provider_user_id="kakao-1", email="a@example.com")
        await client.put("/api/v1/notifications/devices", json=_device_body())

        await login(client, respx_mock, provider_user_id="kakao-2", email="b@example.com")
        res = await client.delete(f"/api/v1/notifications/devices/{TOKEN_A}")
        assert res.status_code == 204
        assert await db.scalar(select(func.count()).select_from(DeviceToken)) == 1


# ---------- GET /notifications/settings ----------


class TestGetSettings:
    async def test_requires_auth(self, client):
        res = await client.get("/api/v1/notifications/settings")
        assert res.status_code == 401

    async def test_lazy_creates_defaults(self, client, db, respx_mock):
        """최초 호출 시 5행 lazy 생성 — 기본 08:00/12:00/18:30, weekly_nudge 만 off."""
        await login(client, respx_mock)
        res = await client.get("/api/v1/notifications/settings")
        assert res.status_code == 200, res.text
        by_type = {s["type"]: s for s in res.json()["settings"]}
        assert set(by_type) == {
            "meal_reminder_breakfast",
            "meal_reminder_lunch",
            "meal_reminder_dinner",
            "mealplan_done",
            "weekly_nudge",
        }
        assert by_type["meal_reminder_breakfast"]["localTime"] == "08:00"
        assert by_type["meal_reminder_lunch"]["localTime"] == "12:00"
        assert by_type["meal_reminder_dinner"]["localTime"] == "18:30"
        assert by_type["mealplan_done"] == {
            "type": "mealplan_done", "enabled": True, "localTime": None, "timezone": None,
        }
        assert by_type["weekly_nudge"]["enabled"] is False
        # 리마인더는 next_send_at(UTC) 세팅 (스케줄러 스캔 키)
        rows = (await db.scalars(select(NotificationSetting))).all()
        for row in rows:
            if row.type.startswith("meal_reminder_"):
                assert row.next_send_at is not None
                assert row.next_send_at > datetime.now(UTC)
            else:
                assert row.next_send_at is None

    async def test_timezone_defaults_to_latest_device(self, client, respx_mock):
        await login(client, respx_mock)
        await client.put(
            "/api/v1/notifications/devices",
            json=_device_body(timezone="America/New_York", locale="en"),
        )
        res = await client.get("/api/v1/notifications/settings")
        by_type = {s["type"]: s for s in res.json()["settings"]}
        assert by_type["meal_reminder_breakfast"]["timezone"] == "America/New_York"

    async def test_second_call_does_not_duplicate(self, client, db, respx_mock):
        await login(client, respx_mock)
        await client.get("/api/v1/notifications/settings")
        await client.get("/api/v1/notifications/settings")
        assert await db.scalar(select(func.count()).select_from(NotificationSetting)) == 5


# ---------- PUT /notifications/settings ----------


class TestUpdateSettings:
    async def test_requires_auth(self, client):
        res = await client.put(
            "/api/v1/notifications/settings",
            json={"settings": [{"type": "mealplan_done", "enabled": False}]},
        )
        assert res.status_code == 401

    async def test_partial_update_only_sent_types(self, client, respx_mock):
        await login(client, respx_mock)
        res = await client.put(
            "/api/v1/notifications/settings",
            json={"settings": [
                {"type": "meal_reminder_dinner", "enabled": True, "localTime": "19:00"},
            ]},
        )
        assert res.status_code == 200, res.text
        by_type = {s["type"]: s for s in res.json()["settings"]}
        assert by_type["meal_reminder_dinner"]["localTime"] == "19:00"
        # 다른 type 은 기본값 유지 + 전체 5행 재반환
        assert by_type["meal_reminder_breakfast"]["localTime"] == "08:00"
        assert len(by_type) == 5

    async def test_update_recomputes_next_send_at(self, client, db, respx_mock):
        await login(client, respx_mock)
        await client.get("/api/v1/notifications/settings")  # lazy 생성
        before = await db.scalar(
            select(NotificationSetting.next_send_at).where(
                NotificationSetting.type == "meal_reminder_dinner"
            )
        )
        res = await client.put(
            "/api/v1/notifications/settings",
            json={"settings": [
                {"type": "meal_reminder_dinner", "localTime": "23:59", "timezone": "UTC"},
            ]},
        )
        assert res.status_code == 200
        row = await db.scalar(
            select(NotificationSetting).where(
                NotificationSetting.type == "meal_reminder_dinner"
            )
        )
        assert row.local_time == time(23, 59)
        assert row.timezone == "UTC"
        assert row.next_send_at != before
        # UTC 23:59 다음 발송 시각 — UTC 기준 23:59 정각
        assert row.next_send_at.astimezone(UTC).strftime("%H:%M") == "23:59"

    async def test_disable_clears_next_send_at(self, client, db, respx_mock):
        await login(client, respx_mock)
        res = await client.put(
            "/api/v1/notifications/settings",
            json={"settings": [{"type": "meal_reminder_breakfast", "enabled": False}]},
        )
        assert res.status_code == 200
        row = await db.scalar(
            select(NotificationSetting).where(
                NotificationSetting.type == "meal_reminder_breakfast"
            )
        )
        assert row.enabled is False
        assert row.next_send_at is None

    @pytest.mark.parametrize(
        "item",
        [
            {"type": "mealplan_done", "localTime": "12:00"},  # 리마인더 외 localTime 금지
            {"type": "weekly_nudge", "localTime": "09:00"},
            {"type": "meal_reminder_lunch", "localTime": "25:00"},  # HH:MM 위반
            {"type": "meal_reminder_lunch", "localTime": "9시"},
            {"type": "unknown_type", "enabled": True},  # type 열거 위반
            {"type": "meal_reminder_lunch", "timezone": "Mars/Olympus"},  # IANA 위반
        ],
    )
    async def test_update_validation_422(self, client, respx_mock, item):
        await login(client, respx_mock)
        res = await client.put(
            "/api/v1/notifications/settings", json={"settings": [item]}
        )
        assert res.status_code == 422
        assert res.json()["detail"]["code"] == "VALIDATION_ERROR"

    async def test_empty_settings_list_422(self, client, respx_mock):
        await login(client, respx_mock)
        res = await client.put("/api/v1/notifications/settings", json={"settings": []})
        assert res.status_code == 422

    async def test_update_rate_limited(self, client, respx_mock):
        await login(client, respx_mock)
        body = {"settings": [{"type": "mealplan_done", "enabled": True}]}
        for _ in range(10):
            assert (
                await client.put("/api/v1/notifications/settings", json=body)
            ).status_code == 200
        res = await client.put("/api/v1/notifications/settings", json=body)
        assert res.status_code == 429
