"""앱 로그인(원타임 코드 세션 인계) 테스트 — api-spec 1-1(client)·1-6, architecture 3-5.

- authorize?client=app → state 서명에 client 포함
- callback(client=app) → 쿠키 없이 jaringobe://auth?code=...&next=... 딥링크
- GET /auth/app/session → 코드 검증·소진 → Set-Cookie → 302 {next}?login=success
- 실패(위조/만료/재사용) 일괄 AUTH_INVALID_APP_CODE (oracle 차단)
"""

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from sqlalchemy import select

from app.core.security import hash_app_login_code, utcnow
from app.domains.auth.models import AppLoginCode
from tests.conftest import FRONTEND, get_state, mock_kakao_provider

APP_SCHEME = "jaringobe"


@pytest.fixture(autouse=True)
def _reset_auth_limiter():
    from app.core.ratelimit import auth_ip_limiter

    auth_ip_limiter.reset()
    yield
    auth_ip_limiter.reset()


async def _app_callback(client, respx_mock, next_path: str = "/", provider: str = "kakao"):
    """client=app authorize → (mock provider) → callback. 반환: 콜백 302 응답."""
    mock_kakao_provider(respx_mock)
    res = await client.get(
        f"/api/v1/auth/{provider}/authorize",
        params={"next": next_path, "client": "app"},
    )
    assert res.status_code == 302
    state = parse_qs(urlparse(res.headers["location"]).query)["state"][0]
    return await client.get(
        f"/api/v1/auth/{provider}/callback", params={"code": "auth-code", "state": state}
    )


def _deeplink_query(res) -> dict:
    loc = urlparse(res.headers["location"])
    assert loc.scheme == APP_SCHEME
    assert loc.netloc == "auth"
    return parse_qs(loc.query)


class TestAuthorizeClientParam:
    async def test_state_includes_client_app(self, client):
        res = await client.get(
            "/api/v1/auth/kakao/authorize", params={"client": "app", "next": "/mypage"}
        )
        assert res.status_code == 302
        state = parse_qs(urlparse(res.headers["location"]).query)["state"][0]
        claims = jwt.decode(state, "test-jwt-secret", algorithms=["HS256"])
        assert claims["client"] == "app"
        assert claims["next"] == "/mypage"

    async def test_client_defaults_to_web(self, client):
        state = await get_state(client, "kakao")
        claims = jwt.decode(state, "test-jwt-secret", algorithms=["HS256"])
        assert claims["client"] == "web"

    async def test_invalid_client_422(self, client):
        res = await client.get(
            "/api/v1/auth/kakao/authorize", params={"client": "desktop"}
        )
        assert res.status_code == 422


class TestAppCallback:
    async def test_app_callback_issues_code_not_cookies(self, client, db, respx_mock):
        res = await _app_callback(client, respx_mock, next_path="/mypage")
        assert res.status_code == 302
        query = _deeplink_query(res)
        raw_code = query["code"][0]
        assert query["next"] == ["/mypage"]
        # 쿠키 미세팅 (세션은 app/session 에서)
        assert "set-cookie" not in {k.lower() for k in res.headers.keys()}
        # DB 에는 SHA-256 해시만 저장 (원문 저장 금지)
        row = (await db.scalars(select(AppLoginCode))).one()
        assert row.code_hash == hash_app_login_code(raw_code)
        assert raw_code not in row.code_hash
        assert row.used_at is None
        assert row.expires_at <= utcnow() + timedelta(seconds=61)

    async def test_web_callback_unchanged(self, client, respx_mock):
        """client 미지정(web)은 기존 쿠키 흐름 그대로."""
        mock_kakao_provider(respx_mock)
        state = await get_state(client, "kakao")
        res = await client.get(
            "/api/v1/auth/kakao/callback", params={"code": "c", "state": state}
        )
        assert res.headers["location"] == f"{FRONTEND}/?login=success"
        assert res.cookies.get("jaringobe_access")

    async def test_app_callback_provider_denied_redirects_to_app_scheme(self, client):
        res = await client.get("/api/v1/auth/kakao/authorize", params={"client": "app"})
        state = parse_qs(urlparse(res.headers["location"]).query)["state"][0]
        res = await client.get(
            "/api/v1/auth/kakao/callback",
            params={"error": "access_denied", "state": state},
        )
        assert res.status_code == 302
        query = _deeplink_query(res)
        assert query["error"] == ["AUTH_PROVIDER_DENIED"]

    async def test_app_callback_provider_error_redirects_to_app_scheme(
        self, client, respx_mock
    ):
        from tests.conftest import KAKAO_TOKEN_URL

        respx_mock.post(KAKAO_TOKEN_URL).respond(status_code=500)
        res = await client.get("/api/v1/auth/kakao/authorize", params={"client": "app"})
        state = parse_qs(urlparse(res.headers["location"]).query)["state"][0]
        res = await client.get(
            "/api/v1/auth/kakao/callback", params={"code": "c", "state": state}
        )
        query = _deeplink_query(res)
        assert query["error"] == ["AUTH_PROVIDER_ERROR"]

    async def test_tampered_state_falls_back_to_web_redirect(self, client):
        """state 위조 시 client 판별 불가 → 기존 웹 실패 리다이렉트."""
        res = await client.get(
            "/api/v1/auth/kakao/callback", params={"code": "c", "state": "garbage"}
        )
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_INVALID_STATE"


class TestAppSession:
    async def test_exchange_success_sets_cookies(self, client, db, respx_mock):
        res = await _app_callback(client, respx_mock, next_path="/mypage")
        raw_code = _deeplink_query(res)["code"][0]

        res = await client.get(
            "/api/v1/auth/app/session", params={"code": raw_code, "next": "/mypage"}
        )
        assert res.status_code == 302
        assert res.headers["location"] == f"{FRONTEND}/mypage?login=success"
        assert res.cookies.get("jaringobe_access")
        assert res.cookies.get("jaringobe_refresh")
        set_cookie = ";".join(res.headers.get_list("set-cookie")).lower()
        assert "httponly" in set_cookie
        # 단일 사용 마킹
        row = (await db.scalars(select(AppLoginCode))).one()
        assert row.used_at is not None

    async def test_exchange_then_users_me_works(self, client, respx_mock):
        res = await _app_callback(client, respx_mock)
        raw_code = _deeplink_query(res)["code"][0]
        await client.get("/api/v1/auth/app/session", params={"code": raw_code})
        me = await client.get("/api/v1/users/me")
        assert me.status_code == 200
        assert me.json()["nickname"]

    async def test_reuse_rejected_uniformly(self, client, respx_mock, caplog):
        res = await _app_callback(client, respx_mock)
        raw_code = _deeplink_query(res)["code"][0]
        assert (
            await client.get("/api/v1/auth/app/session", params={"code": raw_code})
        ).status_code == 302

        import logging

        with caplog.at_level(logging.WARNING):
            res = await client.get("/api/v1/auth/app/session", params={"code": raw_code})
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_INVALID_APP_CODE"
        # 재사용 시도는 경고 로그 — 코드 원문은 로그에 남기지 않음 (CWE-598)
        assert any("재사용" in r.message for r in caplog.records)
        assert all(raw_code not in r.getMessage() for r in caplog.records)

    async def test_expired_code_rejected(self, client, db, respx_mock):
        res = await _app_callback(client, respx_mock)
        raw_code = _deeplink_query(res)["code"][0]
        row = (await db.scalars(select(AppLoginCode))).one()
        row.expires_at = utcnow() - timedelta(seconds=1)
        await db.commit()

        res = await client.get("/api/v1/auth/app/session", params={"code": raw_code})
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_INVALID_APP_CODE"

    @pytest.mark.parametrize("params", [{}, {"code": "forged-code"}, {"code": "x" * 600}])
    async def test_invalid_or_missing_code_rejected(self, client, params):
        res = await client.get("/api/v1/auth/app/session", params=params)
        assert res.status_code == 302
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_INVALID_APP_CODE"

    async def test_malicious_next_replaced_with_root(self, client, respx_mock):
        res = await _app_callback(client, respx_mock)
        raw_code = _deeplink_query(res)["code"][0]
        res = await client.get(
            "/api/v1/auth/app/session",
            params={"code": raw_code, "next": "https://evil.com"},
        )
        assert res.headers["location"] == f"{FRONTEND}/?login=success"

    async def test_concurrent_consumption_single_winner(self, client, db, respx_mock):
        """동일 코드 동시 소진 race — 정확히 1건만 성공 (BUG-004, CWE-362 원자 소진)."""
        import asyncio

        from app.core.db import SessionLocal
        from app.domains.auth.service import consume_app_login_code

        res = await _app_callback(client, respx_mock)
        raw_code = _deeplink_query(res)["code"][0]

        async def _consume():
            async with SessionLocal() as session:
                return await consume_app_login_code(session, raw_code)

        results = await asyncio.gather(*[_consume() for _ in range(4)])
        assert sum(r is not None for r in results) == 1  # 승자 정확히 1
        row = (await db.scalars(select(AppLoginCode))).one()
        assert row.used_at is not None

    async def test_expired_code_not_consumed_atomically(self, client, db, respx_mock):
        """만료 코드는 원자 UPDATE 조건(expires_at > now)에 걸려 소진되지 않는다 (BUG-004)."""
        from app.domains.auth.service import consume_app_login_code

        res = await _app_callback(client, respx_mock)
        raw_code = _deeplink_query(res)["code"][0]
        row = (await db.scalars(select(AppLoginCode))).one()
        row.expires_at = utcnow() - timedelta(seconds=1)
        await db.commit()

        assert await consume_app_login_code(db, raw_code) is None
        await db.refresh(row)
        assert row.used_at is None  # 만료 코드는 used_at 마킹 자체가 없다

    async def test_rate_limited_by_ip(self, client):
        """/auth/* 공통 IP 10회/분 미들웨어가 app/session 도 커버 (CWE-307)."""
        for _ in range(10):
            res = await client.get("/api/v1/auth/app/session", params={"code": "x"})
            assert res.status_code == 302
        res = await client.get("/api/v1/auth/app/session", params={"code": "x"})
        assert res.status_code == 429
        assert res.json()["detail"]["code"] == "RATE_LIMITED"
