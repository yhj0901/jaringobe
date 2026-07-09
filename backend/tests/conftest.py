"""공용 테스트 픽스처 — 테스트 DB(jaringobe_test) + ASGI httpx 클라이언트.

환경변수는 app 모듈 임포트 전에 세팅해야 한다 (get_settings lru_cache).
"""

import os

os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://jaringobe:jaringobe@localhost:5432/jaringobe_test"
)
os.environ["JWT_SECRET"] = "test-jwt-secret"
os.environ["FRONTEND_ORIGIN"] = "http://localhost:3000"
os.environ["COOKIE_SECURE"] = "false"
os.environ["KAKAO_CLIENT_ID"] = "kakao-client-id"
os.environ["KAKAO_CLIENT_SECRET"] = "kakao-client-secret"
os.environ["GOOGLE_CLIENT_ID"] = "google-client-id"
os.environ["GOOGLE_CLIENT_SECRET"] = "google-client-secret"

from urllib.parse import parse_qs, urlparse  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

import app.domains.auth.models  # noqa: E402, F401 - 메타데이터 등록
import app.domains.budget.models  # noqa: E402, F401
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core.ratelimit import auth_ip_limiter, budget_user_limiter  # noqa: E402
from app.main import app  # noqa: E402

FRONTEND = "http://localhost:3000"

# 테스트 클라이언트 호스트 — http.cookiejar 가 점(.) 없는 호스트에 '.local' 을 붙여
# 수동 쿠키 세팅이 불가능해지는 문제를 피하기 위해 점 있는 호스트 사용
TEST_HOST = "frontend.test"

KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_PROFILE_URL = "https://kapi.kakao.com/v2/user/me"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_PROFILE_URL = "https://openidconnect.googleapis.com/v1/userinfo"


@pytest.fixture(autouse=True)
async def _db_schema():
    """테스트마다 스키마 재생성 + rate limiter 초기화 + 엔진 dispose(이벤트 루프 격리)."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    auth_ip_limiter.reset()
    budget_user_limiter.reset()
    yield
    await engine.dispose()


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=f"http://{TEST_HOST}") as c:
        yield c


@pytest.fixture
async def db():
    async with SessionLocal() as session:
        yield session


# ---------- provider mock + 로그인 헬퍼 ----------


def mock_kakao_provider(
    respx_mock,
    provider_user_id: str = "kakao-1",
    email: str | None = "user@example.com",
    nickname: str | None = "자린이",
    profile_image_url: str | None = None,
):
    respx_mock.post(KAKAO_TOKEN_URL).respond(json={"access_token": "kakao-access-token"})
    respx_mock.get(KAKAO_PROFILE_URL).respond(
        json={
            "id": provider_user_id,
            "kakao_account": {
                "email": email,
                "profile": {"nickname": nickname, "profile_image_url": profile_image_url},
            },
        }
    )


def mock_google_provider(
    respx_mock,
    provider_user_id: str = "google-1",
    email: str | None = "user@example.com",
    nickname: str | None = "Jarin Lee",
    profile_image_url: str | None = None,
):
    respx_mock.post(GOOGLE_TOKEN_URL).respond(json={"access_token": "google-access-token"})
    respx_mock.get(GOOGLE_PROFILE_URL).respond(
        json={
            "sub": provider_user_id,
            "name": nickname,
            "email": email,
            "picture": profile_image_url,
        }
    )


async def get_state(client: httpx.AsyncClient, provider: str, next_path: str = "/") -> str:
    """authorize 302 의 Location 에서 state 추출."""
    res = await client.get(f"/api/v1/auth/{provider}/authorize", params={"next": next_path})
    assert res.status_code == 302
    query = parse_qs(urlparse(res.headers["location"]).query)
    return query["state"][0]


async def do_callback(
    client: httpx.AsyncClient, provider: str, next_path: str = "/", code: str = "auth-code"
) -> httpx.Response:
    state = await get_state(client, provider, next_path)
    return await client.get(
        f"/api/v1/auth/{provider}/callback", params={"code": code, "state": state}
    )


async def login(
    client: httpx.AsyncClient,
    respx_mock,
    provider: str = "kakao",
    provider_user_id: str = "kakao-1",
    email: str | None = "user@example.com",
    nickname: str | None = "자린이",
) -> httpx.Response:
    """authorize → (mock) provider → callback 전체 플로우로 로그인 쿠키 확보."""
    if provider == "kakao":
        mock_kakao_provider(
            respx_mock, provider_user_id=provider_user_id, email=email, nickname=nickname
        )
    else:
        mock_google_provider(
            respx_mock, provider_user_id=provider_user_id, email=email, nickname=nickname
        )
    res = await do_callback(client, provider)
    assert res.status_code == 302, res.text
    return res
