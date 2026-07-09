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


async def test_latest_mealplan_returns_most_recent(client, respx_mock):
    await login(client, respx_mock)
    await _create_budget(client)
    first_id = (
        await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 2})
    ).json()["id"]
    second_id = (
        await client.post("/api/v1/mealplans", json={"days": 2, "mealsPerDay": 2})
    ).json()["id"]
    assert first_id != second_id

    res = await client.get("/api/v1/mealplans/latest")
    assert res.status_code == 200, res.text  # /latest 가 {plan_id}(uuid) 로 파싱되면 422 → 순서 검증
    assert res.json()["id"] == second_id


async def test_latest_mealplan_empty_dedicated_code(client, respx_mock):
    await login(client, respx_mock)
    await _create_budget(client)
    res = await client.get("/api/v1/mealplans/latest")
    assert res.status_code == 404
    # {id} 조회의 generic NOT_FOUND 와 구분되는 전용 코드 (프론트 빈 상태 분기)
    assert res.json()["detail"]["code"] == "MEALPLAN_NOT_FOUND"


async def test_latest_mealplan_scoped_to_user(client, respx_mock):
    await login(client, respx_mock, provider_user_id="kakao-1", email="a@example.com")
    await _create_budget(client)
    res = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 2})
    assert res.status_code == 201

    # 다른 유저로 재로그인 → 타인 플랜 미노출 (404 전용 코드)
    await login(client, respx_mock, provider_user_id="kakao-2", email="b@example.com")
    await _create_budget(client)
    res = await client.get("/api/v1/mealplans/latest")
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "MEALPLAN_NOT_FOUND"


async def test_latest_mealplan_requires_auth(client):
    res = await client.get("/api/v1/mealplans/latest")
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "AUTH_REQUIRED"


@pytest.mark.parametrize("field", ["allergies", "preferences"])
async def test_mealplan_pref_item_too_long_422(client, respx_mock, field):
    await login(client, respx_mock)
    await _create_budget(client)
    res = await client.post(
        "/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1, field: ["a" * 31]}
    )
    assert res.status_code == 422


@pytest.mark.parametrize("field", ["allergies", "preferences"])
async def test_mealplan_pref_list_too_many_422(client, respx_mock, field):
    await login(client, respx_mock)
    await _create_budget(client)
    res = await client.post(
        "/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1, field: [f"x{i}" for i in range(11)]}
    )
    assert res.status_code == 422


async def test_mealplan_pref_limits_boundary_ok(client, respx_mock):
    await login(client, respx_mock)
    await _create_budget(client)
    res = await client.post(
        "/api/v1/mealplans",
        json={
            "days": 1,
            "mealsPerDay": 1,
            "allergies": ["a" * 30] + [f"x{i}" for i in range(9)],  # 30자 · 10개 경계값
            "preferences": [f"p{i}" for i in range(10)],
        },
    )
    assert res.status_code == 201


async def test_regenerate_pref_limits_422(client, respx_mock):
    await login(client, respx_mock)
    await _create_budget(client)
    plan_id = (
        await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    ).json()["id"]
    res = await client.post(
        f"/api/v1/mealplans/{plan_id}/regenerate",
        json={"scope": "all", "allergies": ["a" * 31]},
    )
    assert res.status_code == 422


async def test_create_meal_plan_llm_failure_falls_back(client, respx_mock, monkeypatch):
    """LLM 예외(타임아웃 등)는 5xx 가 아니라 규칙 기반 폴백으로 201 (api-spec v1.1 §3-2)."""
    from app.domains.mealplan import generator as gen_mod

    class _FailingLLM:
        enabled = True

        async def complete_json(self, *a, **k):
            raise TimeoutError("simulated LLM timeout")

    monkeypatch.setattr(gen_mod, "get_llm", lambda: _FailingLLM())
    await login(client, respx_mock)
    assert (await _create_budget(client)).status_code == 201

    res = await client.post("/api/v1/mealplans", json={"days": 3, "mealsPerDay": 3})
    assert res.status_code == 201, res.text
    assert len(res.json()["meals"]) == 9
