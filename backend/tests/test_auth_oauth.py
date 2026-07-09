"""소셜 로그인 authorize/callback 시나리오 테스트."""

from urllib.parse import parse_qs, urlparse

import jwt
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import create_state_token
from app.domains.auth.models import AuthIdentity, User
from tests.conftest import (
    FRONTEND,
    GOOGLE_PROFILE_URL,
    GOOGLE_TOKEN_URL,
    KAKAO_PROFILE_URL,
    KAKAO_TOKEN_URL,
    do_callback,
    get_state,
    login,
    mock_kakao_provider,
)


class TestAuthorize:
    async def test_kakao_redirects_to_provider_with_state(self, client):
        res = await client.get("/api/v1/auth/kakao/authorize", params={"next": "/mypage"})
        assert res.status_code == 302
        loc = urlparse(res.headers["location"])
        assert loc.netloc == "kauth.kakao.com"
        query = parse_qs(loc.query)
        assert query["response_type"] == ["code"]
        assert query["redirect_uri"] == [f"{FRONTEND}/api/v1/auth/kakao/callback"]
        # state 는 서명 JWT — next 가 들어있다
        claims = jwt.decode(query["state"][0], "test-jwt-secret", algorithms=["HS256"])
        assert claims["next"] == "/mypage"
        assert claims["provider"] == "kakao"

    async def test_google_redirects_to_provider(self, client):
        res = await client.get("/api/v1/auth/google/authorize")
        assert res.status_code == 302
        assert urlparse(res.headers["location"]).netloc == "accounts.google.com"

    async def test_malicious_next_is_replaced_with_root(self, client):
        for bad in ["https://evil.com", "//evil.com", "/a\\b", "javascript://x"]:
            res = await client.get("/api/v1/auth/kakao/authorize", params={"next": bad})
            state = parse_qs(urlparse(res.headers["location"]).query)["state"][0]
            claims = jwt.decode(state, "test-jwt-secret", algorithms=["HS256"])
            assert claims["next"] == "/", bad

    async def test_apple_not_supported_404(self, client):
        res = await client.get("/api/v1/auth/apple/authorize")
        assert res.status_code == 404
        assert res.json()["detail"]["code"] == "PROVIDER_NOT_SUPPORTED"

    async def test_unknown_provider_404(self, client):
        res = await client.get("/api/v1/auth/naver/authorize")
        assert res.status_code == 404
        assert res.json()["detail"]["code"] == "PROVIDER_NOT_SUPPORTED"


class TestCallbackSignupAndLogin:
    async def test_new_user_signup_kakao(self, client, db, respx_mock):
        res = await login(client, respx_mock, provider="kakao", provider_user_id="k-100")
        assert res.headers["location"] == f"{FRONTEND}/?login=success"
        # 쿠키 세팅
        assert res.cookies.get("jaringobe_access")
        assert res.cookies.get("jaringobe_refresh")
        set_cookie = ";".join(res.headers.get_list("set-cookie")).lower()
        assert "httponly" in set_cookie
        assert "samesite=lax" in set_cookie
        assert "path=/api/v1/auth" in set_cookie  # refresh 쿠키 Path 제한
        # DB 에 유저 + identity 생성
        user = (await db.scalars(select(User))).one()
        assert user.email == "user@example.com"
        identity = (await db.scalars(select(AuthIdentity))).one()
        assert identity.provider == "kakao"
        assert identity.provider_user_id == "k-100"
        assert identity.email_at_signup == "user@example.com"

    async def test_new_user_signup_google(self, client, db, respx_mock):
        res = await login(client, respx_mock, provider="google", provider_user_id="g-100")
        assert res.headers["location"] == f"{FRONTEND}/?login=success"
        identity = (await db.scalars(select(AuthIdentity))).one()
        assert identity.provider == "google"

    async def test_existing_user_login_no_duplicate(self, client, db, respx_mock):
        await login(client, respx_mock, provider_user_id="k-1")
        res = await login(client, respx_mock, provider_user_id="k-1")
        assert "notice" not in res.headers["location"]
        assert await db.scalar(select(func.count()).select_from(User)) == 1

    async def test_email_conflict_notice_on_other_provider_signup(self, client, db, respx_mock):
        await login(
            client, respx_mock, provider="google", provider_user_id="g-1", email="same@example.com"
        )
        res = await login(
            client, respx_mock, provider="kakao", provider_user_id="k-1", email="SAME@example.com"
        )  # 대소문자 무시 매칭
        # 로그인은 정상 진행 + notice 쿼리만 추가 (FR-004 — 자동 통합 금지)
        assert res.headers["location"] == (
            f"{FRONTEND}/?login=success&notice=AUTH_EMAIL_CONFLICT_NOTICE"
        )
        assert await db.scalar(select(func.count()).select_from(User)) == 2

    async def test_kakao_null_email_allowed(self, client, db, respx_mock):
        await login(client, respx_mock, provider_user_id="k-2", email=None)
        user = (await db.scalars(select(User))).one()
        assert user.email is None

    async def test_default_nickname_when_missing(self, client, db, respx_mock):
        await login(client, respx_mock, provider_user_id="k-3", nickname=None)
        user = (await db.scalars(select(User))).one()
        assert user.nickname.startswith("자린이-")

    async def test_next_path_preserved(self, client, respx_mock):
        mock_kakao_provider(respx_mock)
        res = await do_callback(client, "kakao", next_path="/mypage")
        assert res.headers["location"] == f"{FRONTEND}/mypage?login=success"

    async def test_locale_from_accept_language(self, client, db, respx_mock):
        mock_kakao_provider(respx_mock)
        state = await get_state(client, "kakao")
        res = await client.get(
            "/api/v1/auth/kakao/callback",
            params={"code": "c", "state": state},
            headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        assert res.status_code == 302
        user = (await db.scalars(select(User))).one()
        assert user.locale == "en"


class TestCallbackFailures:
    async def test_provider_denied(self, client):
        res = await client.get("/api/v1/auth/kakao/callback", params={"error": "access_denied"})
        assert res.status_code == 302
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_PROVIDER_DENIED"

    async def test_missing_code_or_state(self, client):
        res = await client.get("/api/v1/auth/kakao/callback", params={"state": "s"})
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_INVALID_STATE"
        res = await client.get("/api/v1/auth/kakao/callback", params={"code": "c"})
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_INVALID_STATE"

    async def test_oversized_code_rejected(self, client):
        state = await get_state(client, "kakao")
        res = await client.get(
            "/api/v1/auth/kakao/callback", params={"code": "a" * 513, "state": state}
        )
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_INVALID_STATE"

    async def test_tampered_state(self, client):
        res = await client.get(
            "/api/v1/auth/kakao/callback", params={"code": "c", "state": "garbage"}
        )
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_INVALID_STATE"

    async def test_state_provider_mismatch(self, client):
        state = await get_state(client, "google")  # google 용 state 를 kakao 콜백에 사용
        res = await client.get("/api/v1/auth/kakao/callback", params={"code": "c", "state": state})
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_INVALID_STATE"

    async def test_expired_state(self, client, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "oauth_state_expire_minutes", -1)
        state = create_state_token("kakao", "/")
        monkeypatch.undo()
        res = await client.get("/api/v1/auth/kakao/callback", params={"code": "c", "state": state})
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_INVALID_STATE"

    async def test_provider_token_endpoint_error(self, client, respx_mock):
        respx_mock.post(KAKAO_TOKEN_URL).respond(status_code=500)
        res = await do_callback(client, "kakao")
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_PROVIDER_ERROR"

    async def test_provider_token_missing_access_token(self, client, respx_mock):
        respx_mock.post(KAKAO_TOKEN_URL).respond(json={})
        res = await do_callback(client, "kakao")
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_PROVIDER_ERROR"

    async def test_provider_profile_endpoint_error(self, client, respx_mock):
        respx_mock.post(KAKAO_TOKEN_URL).respond(json={"access_token": "t"})
        respx_mock.get(KAKAO_PROFILE_URL).respond(status_code=500)
        res = await do_callback(client, "kakao")
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_PROVIDER_ERROR"

    async def test_provider_profile_missing_id(self, client, respx_mock):
        respx_mock.post(KAKAO_TOKEN_URL).respond(json={"access_token": "t"})
        respx_mock.get(KAKAO_PROFILE_URL).respond(json={"kakao_account": {}})
        res = await do_callback(client, "kakao")
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_PROVIDER_ERROR"

    async def test_google_token_error(self, client, respx_mock):
        respx_mock.post(GOOGLE_TOKEN_URL).respond(status_code=502)
        res = await do_callback(client, "google")
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_PROVIDER_ERROR"

    async def test_google_token_missing_access_token(self, client, respx_mock):
        respx_mock.post(GOOGLE_TOKEN_URL).respond(json={"token_type": "Bearer"})
        res = await do_callback(client, "google")
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_PROVIDER_ERROR"

    async def test_google_profile_error(self, client, respx_mock):
        respx_mock.post(GOOGLE_TOKEN_URL).respond(json={"access_token": "t"})
        respx_mock.get(GOOGLE_PROFILE_URL).respond(status_code=500)
        res = await do_callback(client, "google")
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_PROVIDER_ERROR"

    async def test_google_profile_missing_sub(self, client, respx_mock):
        respx_mock.post(GOOGLE_TOKEN_URL).respond(json={"access_token": "t"})
        respx_mock.get(GOOGLE_PROFILE_URL).respond(json={"email": "x@y.com"})
        res = await do_callback(client, "google")
        assert res.headers["location"] == f"{FRONTEND}/login?error=AUTH_PROVIDER_ERROR"
