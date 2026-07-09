"""테스트 공용 픽스처.

- 별도 test DB(jaringobe_test) 사용 (개발 DB 오염 방지)
- ANTHROPIC_API_KEY 를 비워 LLM을 mock 으로 강제 (실 Claude 호출/비용 없음)
- 각 테스트마다 스키마 재생성
※ 반드시 app import 전에 환경변수를 세팅한다.
"""

import os

os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://jaringobe:jaringobe@db:5432/jaringobe_test"
)
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["LLM_MODEL"] = "claude-sonnet-5"

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

import app.models  # noqa: E402,F401  (모델 metadata 등록)
from app.core.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await engine.dispose()


async def make_household(client, region="KR", allergies=None):
    resp = await client.post(
        "/api/v1/households",
        json={
            "region": region,
            "members": [{"age_group": "adult"}, {"age_group": "child"}],
            "allergies": allergies or ["peanut"],
            "preferences": [],
        },
    )
    return resp.json()["id"]


async def make_budget(client, household_id, amount="500000.00"):
    return await client.post(
        "/api/v1/budgets",
        headers={"X-Household-Id": str(household_id)},
        json={
            "amount": amount,
            "currency": "KRW",
            "period_start": "2026-07-01T00:00:00Z",
            "period_end": "2026-07-31T23:59:59Z",
            "locked": True,
        },
    )
