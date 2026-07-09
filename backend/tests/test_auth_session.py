"""refresh 회전/재사용 감지, logout, users/me 테스트."""

import uuid

from sqlalchemy import select

from app.core.security import create_access_token
from app.domains.auth.models import RefreshToken, User
from tests.conftest import TEST_HOST, login

REFRESH_COOKIE = "jaringobe_refresh"
REFRESH_PATH = "/api/v1/auth"


def set_refresh_cookie(client, value: str) -> None:
    # 동일 (domain, path, name) 키로 서버 세팅 쿠키를 덮어쓴다
    client.cookies.set(REFRESH_COOKIE, value, domain=TEST_HOST, path=REFRESH_PATH)


class TestRefresh:
    async def test_rotation_issues_new_tokens(self, client, db, respx_mock):
        login_res = await login(client, respx_mock)
        old_refresh = login_res.cookies[REFRESH_COOKIE]

        res = await client.post("/api/v1/auth/refresh")
        assert res.status_code == 200
        assert res.json() == {}
        new_refresh = res.cookies.get(REFRESH_COOKIE)
        assert new_refresh and new_refresh != old_refresh
        assert res.cookies.get("jaringobe_access")

        # 회전 체인: 구 토큰 revoked + rotated_from 연결
        tokens = (await db.scalars(select(RefreshToken).order_by(RefreshToken.created_at))).all()
        assert len(tokens) == 2
        assert tokens[0].revoked_at is not None
        assert tokens[1].rotated_from == tokens[0].id

    async def test_reuse_detection_revokes_all_sessions(self, client, db, respx_mock):
        login_res = await login(client, respx_mock)
        old_refresh = login_res.cookies[REFRESH_COOKIE]

        res = await client.post("/api/v1/auth/refresh")
        new_refresh = res.cookies[REFRESH_COOKIE]

        # 폐기된 구 토큰 재사용 → 401 AUTH_TOKEN_REVOKED + 전 세션 폐기
        set_refresh_cookie(client, old_refresh)
        res = await client.post("/api/v1/auth/refresh")
        assert res.status_code == 401
        assert res.json()["detail"]["code"] == "AUTH_TOKEN_REVOKED"

        tokens = (await db.scalars(select(RefreshToken))).all()
        assert all(t.revoked_at is not None for t in tokens)

        # 정상 회전으로 받았던 신 토큰도 이미 폐기 상태
        set_refresh_cookie(client, new_refresh)
        res = await client.post("/api/v1/auth/refresh")
        assert res.status_code == 401
        assert res.json()["detail"]["code"] == "AUTH_TOKEN_REVOKED"

    async def test_refresh_without_cookie(self, client):
        res = await client.post("/api/v1/auth/refresh")
        assert res.status_code == 401
        assert res.json()["detail"]["code"] == "AUTH_REQUIRED"

    async def test_refresh_with_unknown_token(self, client):
        set_refresh_cookie(client, "unknown-token")
        res = await client.post("/api/v1/auth/refresh")
        assert res.status_code == 401
        assert res.json()["detail"]["code"] == "AUTH_REQUIRED"

    async def test_refresh_with_expired_token(self, client, db, respx_mock):
        from datetime import UTC, datetime, timedelta

        login_res = await login(client, respx_mock)
        token = (await db.scalars(select(RefreshToken))).one()
        token.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()

        set_refresh_cookie(client, login_res.cookies[REFRESH_COOKIE])
        res = await client.post("/api/v1/auth/refresh")
        assert res.status_code == 401
        assert res.json()["detail"]["code"] == "AUTH_REQUIRED"


class TestLogout:
    async def test_logout_revokes_and_clears_cookies(self, client, db, respx_mock):
        await login(client, respx_mock)
        res = await client.post("/api/v1/auth/logout")
        assert res.status_code == 204

        token = (await db.scalars(select(RefreshToken))).one()
        assert token.revoked_at is not None

        # 쿠키 삭제됨 → 이후 인증 요청 401
        assert not client.cookies.get("jaringobe_access")
        res = await client.get("/api/v1/users/me")
        assert res.status_code == 401

    async def test_logout_requires_auth(self, client):
        res = await client.post("/api/v1/auth/logout")
        assert res.status_code == 401
        assert res.json()["detail"]["code"] == "AUTH_REQUIRED"


class TestUsersMe:
    async def test_me_after_signup(self, client, respx_mock):
        await login(client, respx_mock, email="me@example.com", nickname="자린이")
        res = await client.get("/api/v1/users/me")
        assert res.status_code == 200
        body = res.json()
        # camelCase 응답 규격 (api-spec.md)
        assert body["nickname"] == "자린이"
        assert body["email"] == "me@example.com"
        assert body["profileImageUrl"] is None
        assert body["locale"] == "ko"
        assert body["country"] == "KR"
        assert body["currency"] == "KRW"
        assert body["onboardingCompleted"] is False
        assert body["hasBudgetPlan"] is False
        uuid.UUID(body["id"])  # UUID 문자열

    async def test_me_null_email(self, client, respx_mock):
        await login(client, respx_mock, email=None)
        res = await client.get("/api/v1/users/me")
        assert res.json()["email"] is None

    async def test_me_without_cookie(self, client):
        res = await client.get("/api/v1/users/me")
        assert res.status_code == 401
        assert res.json()["detail"]["code"] == "AUTH_REQUIRED"

    async def test_me_with_garbage_token(self, client):
        client.cookies.set("jaringobe_access", "not-a-jwt", domain=TEST_HOST, path="/")
        res = await client.get("/api/v1/users/me")
        assert res.status_code == 401
        assert res.json()["detail"]["code"] == "AUTH_REQUIRED"

    async def test_me_with_token_for_missing_user(self, client, db):
        token = create_access_token(uuid.uuid4())  # 존재하지 않는 유저
        client.cookies.set("jaringobe_access", token, domain=TEST_HOST, path="/")
        res = await client.get("/api/v1/users/me")
        assert res.status_code == 401
        assert res.json()["detail"]["code"] == "AUTH_REQUIRED"

    async def test_me_after_login_flow_keeps_single_user(self, client, db, respx_mock):
        await login(client, respx_mock, provider_user_id="k-9")
        await client.post("/api/v1/auth/refresh")
        res = await client.get("/api/v1/users/me")
        assert res.status_code == 200
        assert len((await db.scalars(select(User))).all()) == 1
