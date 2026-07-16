"""Expo 발송 서비스 테스트 — 템플릿 렌더/발송 이력/무효 토큰 정리 (Expo API 는 mock)."""

import pytest
from sqlalchemy import func, select

from app.domains.notification import sender
from app.domains.notification.models import DeviceToken, NotificationLog
from tests.conftest import login

EXPO_URL = "https://exp.host/--/api/v2/push/send"

TOKEN_A = "ExponentPushToken[aaaaaaaaaaaaaaaaaaaaaa]"
TOKEN_B = "ExponentPushToken[bbbbbbbbbbbbbbbbbbbbbb]"


@pytest.fixture(autouse=True)
def _reset_notification_limiter():
    from app.core.ratelimit import notification_user_limiter

    notification_user_limiter.reset()
    yield
    notification_user_limiter.reset()


async def _register(client, token: str, locale: str = "ko") -> None:
    res = await client.put(
        "/api/v1/notifications/devices",
        json={
            "token": token,
            "platform": "android",
            "locale": locale,
            "timezone": "Asia/Seoul",
        },
    )
    assert res.status_code == 200, res.text


async def _me_id(client):
    import uuid

    return uuid.UUID((await client.get("/api/v1/users/me")).json()["id"])


# ---------- 템플릿 카탈로그 ----------


class TestTemplates:
    @pytest.mark.parametrize(
        "key", ["push.mealplanDone", "push.mealplanFailed", "push.weeklyNudge"]
    )
    @pytest.mark.parametrize("locale", ["ko", "en"])
    def test_catalog_has_ko_en(self, key, locale):
        title, body = sender.render_template(key, locale)
        assert title and body

    def test_meal_reminder_renders_variables_ko(self):
        title, body = sender.render_template(
            "push.mealReminder", "ko", {"meal_type": "lunch", "recipe_name": "김치찌개"}
        )
        assert title == "오늘 점심: 김치찌개"
        assert body == "지금 만들어 볼까요?"

    def test_meal_reminder_renders_variables_en(self):
        title, _ = sender.render_template(
            "push.mealReminder", "en", {"meal_type": "dinner", "recipe_name": "Bean Chili"}
        )
        assert title == "Today's dinner: Bean Chili"

    def test_unknown_locale_falls_back_to_ko(self):
        title_fr, _ = sender.render_template("push.mealplanDone", "fr")
        title_ko, _ = sender.render_template("push.mealplanDone", "ko")
        assert title_fr == title_ko

    def test_mask_token(self):
        assert sender.mask_token(TOKEN_A).endswith("…")
        assert TOKEN_A[20:] not in sender.mask_token(TOKEN_A)


# ---------- 발송 + 이력 ----------


class TestSendToUser:
    async def test_sends_to_all_devices_and_logs(self, client, db, respx_mock):
        await login(client, respx_mock)
        await _register(client, TOKEN_A, locale="ko")
        await _register(client, TOKEN_B, locale="en")
        user_id = await _me_id(client)

        route = respx_mock.post(EXPO_URL).respond(
            json={"data": [{"status": "ok"}, {"status": "ok"}]}
        )
        sent = await sender.send_to_user(
            db, user_id, type_="mealplan_done",
            template_key="push.mealplanDone", path="/mealplan/x",
        )
        assert sent == 2
        # 페이로드: 디바이스 로캘별 렌더 + data.path (api-spec 6-A-5)
        import json

        messages = json.loads(route.calls[0].request.content)
        assert {m["to"] for m in messages} == {TOKEN_A, TOKEN_B}
        titles = {m["to"]: m["title"] for m in messages}
        assert titles[TOKEN_A] != titles[TOKEN_B]  # ko/en 개별 렌더
        assert all(m["data"] == {"v": 1, "path": "/mealplan/x"} for m in messages)
        # 이력: 본문 원문 대신 template_key 만 (CWE-359)
        logs = (await db.scalars(select(NotificationLog))).all()
        assert len(logs) == 2
        assert all(log.status == "sent" for log in logs)
        assert all(log.template_key == "push.mealplanDone" for log in logs)

    async def test_device_not_registered_deletes_token(self, client, db, respx_mock):
        await login(client, respx_mock)
        await _register(client, TOKEN_A)
        user_id = await _me_id(client)

        respx_mock.post(EXPO_URL).respond(
            json={"data": [{
                "status": "error",
                "message": "device not registered",
                "details": {"error": "DeviceNotRegistered"},
            }]}
        )
        sent = await sender.send_to_user(
            db, user_id, type_="mealplan_done",
            template_key="push.mealplanDone", path="/mealplan/x",
        )
        assert sent == 0
        # 무효 토큰 즉시 삭제 (FR-011) + failed 이력
        assert await db.scalar(select(func.count()).select_from(DeviceToken)) == 0
        log = (await db.scalars(select(NotificationLog))).one()
        assert log.status == "failed"
        assert log.error_code == "DeviceNotRegistered"
        assert log.device_token_id is None  # FK ON DELETE SET NULL — 이력은 보존

    async def test_expo_http_failure_logs_failed(self, client, db, respx_mock):
        await login(client, respx_mock)
        await _register(client, TOKEN_A)
        user_id = await _me_id(client)

        respx_mock.post(EXPO_URL).respond(status_code=500)
        sent = await sender.send_to_user(
            db, user_id, type_="mealplan_done",
            template_key="push.mealplanDone", path="/mealplan/x",
        )
        assert sent == 0
        log = (await db.scalars(select(NotificationLog))).one()
        assert log.status == "failed"
        assert log.error_code == "REQUEST_ERROR"

    async def test_no_devices_no_call(self, client, db, respx_mock):
        await login(client, respx_mock)
        user_id = await _me_id(client)
        # Expo route 미등록 — 호출되면 respx 가 실패시킴
        sent = await sender.send_to_user(
            db, user_id, type_="mealplan_done",
            template_key="push.mealplanDone", path="/mealplan/x",
        )
        assert sent == 0
        assert await db.scalar(select(func.count()).select_from(NotificationLog)) == 0

    async def test_access_token_header_attached(self, client, db, respx_mock, monkeypatch):
        from app.core.config import get_settings

        monkeypatch.setattr(get_settings(), "expo_access_token", "expo-secret")
        await login(client, respx_mock)
        await _register(client, TOKEN_A)
        user_id = await _me_id(client)

        route = respx_mock.post(EXPO_URL).respond(json={"data": [{"status": "ok"}]})
        await sender.send_to_user(
            db, user_id, type_="mealplan_done",
            template_key="push.mealplanDone", path="/mealplan/x",
        )
        assert route.calls[0].request.headers["authorization"] == "Bearer expo-secret"


# ---------- 식단 생성 완료/실패 푸시 연동 (FR-005) ----------


class TestMealplanDonePush:
    async def _budget(self, client):
        return await client.post(
            "/api/v1/budget/plans",
            json={
                "householdSize": 2,
                "budget": {"amount": "500000", "currency": "KRW"},
                "mealDirection": "health",
                "source": "onboarding",
            },
        )

    async def test_generation_done_sends_push(self, client, db, respx_mock):
        from app.core.ratelimit import mealplan_user_limiter

        mealplan_user_limiter.reset()
        await login(client, respx_mock)
        assert (await self._budget(client)).status_code == 201
        await _register(client, TOKEN_A)

        route = respx_mock.post(EXPO_URL).respond(json={"data": [{"status": "ok"}]})
        res = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
        assert res.status_code == 202
        plan_id = res.json()["id"]

        assert route.called  # 백그라운드 완료 → mealplan_done 푸시
        import json

        message = json.loads(route.calls[0].request.content)[0]
        assert message["data"]["path"] == f"/mealplan/{plan_id}"
        log = (await db.scalars(select(NotificationLog))).one()
        assert log.type == "mealplan_done"
        assert log.template_key == "push.mealplanDone"

    async def test_generation_done_respects_disabled_setting(self, client, db, respx_mock):
        from app.core.ratelimit import mealplan_user_limiter

        mealplan_user_limiter.reset()
        await login(client, respx_mock)
        assert (await self._budget(client)).status_code == 201
        await _register(client, TOKEN_A)
        res = await client.put(
            "/api/v1/notifications/settings",
            json={"settings": [{"type": "mealplan_done", "enabled": False}]},
        )
        assert res.status_code == 200

        # Expo route 미등록 — 발송 시도가 있으면 실패한다
        res = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
        assert res.status_code == 202
        assert await db.scalar(select(func.count()).select_from(NotificationLog)) == 0

    async def test_generation_failed_sends_failed_template(
        self, client, db, respx_mock, monkeypatch
    ):
        from app.core.ratelimit import mealplan_user_limiter
        from app.domains.mealplan import service as svc

        async def _boom(*a, **k):
            raise RuntimeError("simulated total generation failure")

        monkeypatch.setattr(svc, "_generate_within_budget", _boom)
        mealplan_user_limiter.reset()
        await login(client, respx_mock)
        assert (await self._budget(client)).status_code == 201
        await _register(client, TOKEN_A)

        route = respx_mock.post(EXPO_URL).respond(json={"data": [{"status": "ok"}]})
        res = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
        assert res.status_code == 202
        assert route.called
        log = (await db.scalars(select(NotificationLog))).one()
        assert log.template_key == "push.mealplanFailed"
