"""mealplan 도메인 통합 테스트 — 로그인(mock provider) + mock LLM.

conftest 의 login/ client 픽스처 사용. LLM 은 ANTHROPIC_API_KEY 미설정 → mock.
"""

import pytest

from tests.conftest import login


@pytest.fixture(autouse=True)
def _reset_mealplan_limiter():
    from app.core.ratelimit import mealplan_user_limiter

    mealplan_user_limiter.reset()
    yield
    mealplan_user_limiter.reset()


async def _create_budget(client, amount: str = "500000"):
    return await client.post(
        "/api/v1/budget/plans",
        json={
            "householdSize": 4,
            "budget": {"amount": amount, "currency": "KRW"},
            "mealDirection": "health",
            "source": "onboarding",
        },
    )


async def test_create_and_get_mealplan(client, respx_mock):
    await login(client, respx_mock)
    assert (await _create_budget(client)).status_code == 201

    res = await client.post(
        "/api/v1/mealplans", json={"days": 2, "mealsPerDay": 3, "allergies": ["peanut"]}
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "ready"
    assert body["budgetSummary"]["withinBudget"] is True
    assert len(body["meals"]) == 6
    # camelCase + 금액 문자열
    assert body["budgetSummary"]["budget"]["currency"] == "KRW"
    assert isinstance(body["budgetSummary"]["plannedCost"]["amount"], str)

    plan_id = body["id"]
    got = await client.get(f"/api/v1/mealplans/{plan_id}")
    assert got.status_code == 200
    assert got.json()["id"] == plan_id


async def test_mealplan_requires_auth(client):
    res = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "AUTH_REQUIRED"


async def test_mealplan_requires_budget(client, respx_mock):
    await login(client, respx_mock)
    res = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "BUDGET_PLAN_REQUIRED"


async def test_mealplan_over_budget_transparent(client, respx_mock):
    await login(client, respx_mock)
    await _create_budget(client, amount="50000")  # 최소 예산 → 초과 유도
    res = await client.post("/api/v1/mealplans", json={"days": 7, "mealsPerDay": 3})
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "over_budget"
    assert body["budgetSummary"]["withinBudget"] is False
    assert body["notes"]  # 초과 안내 노출 (자르지 않음)


async def test_mealplan_ownership_forbidden(client, respx_mock):
    await login(client, respx_mock, provider_user_id="kakao-1", email="a@example.com")
    await _create_budget(client)
    plan_id = (
        await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 2})
    ).json()["id"]

    # 다른 유저로 재로그인 → 타인 식단 접근 시 403
    await login(client, respx_mock, provider_user_id="kakao-2", email="b@example.com")
    res = await client.get(f"/api/v1/mealplans/{plan_id}")
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "FORBIDDEN"


async def test_mealplan_regenerate_all(client, respx_mock):
    await login(client, respx_mock)
    await _create_budget(client)
    plan_id = (
        await client.post("/api/v1/mealplans", json={"days": 2, "mealsPerDay": 2})
    ).json()["id"]
    res = await client.post(
        f"/api/v1/mealplans/{plan_id}/regenerate", json={"scope": "all"}
    )
    assert res.status_code == 200
    assert res.json()["id"] == plan_id


async def test_mealplan_not_found(client, respx_mock):
    await login(client, respx_mock)
    await _create_budget(client)
    res = await client.get("/api/v1/mealplans/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404
