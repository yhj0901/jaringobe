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


async def test_generation_time_budget_stops_retries(client, respx_mock, monkeypatch):
    """시간 예산 소진 시 예산 초과여도 재시도 없이 최선 결과로 201 (over_budget 허용)."""
    from app.domains.mealplan import service as svc

    calls = {"n": 0}
    orig = svc.generate_meals

    async def counting(*a, **k):
        calls["n"] += 1
        return await orig(*a, **k)

    monkeypatch.setattr(svc, "generate_meals", counting)
    monkeypatch.setattr(svc, "GENERATION_TIME_BUDGET_SECONDS", 0.0)
    await login(client, respx_mock)
    # 극소 예산 → 확실한 초과 상황
    assert (await _create_budget(client, amount="50000")).status_code == 201

    res = await client.post("/api/v1/mealplans", json={"days": 7, "mealsPerDay": 3})
    assert res.status_code == 201, res.text
    assert calls["n"] == 1  # 시간 예산 0 → 단일 시도


async def test_generation_includes_household_members(client, respx_mock, monkeypatch):
    """온보딩 구성원(유형·나이)이 생성 프롬프트에 전달된다."""
    from app.domains.mealplan import service as svc

    captured = {}
    orig = svc.generate_meals

    async def spy(*a, **k):
        captured["household_desc"] = a[8] if len(a) > 8 else k.get("household_desc", "")
        return await orig(*a[:8])

    monkeypatch.setattr(svc, "generate_meals", spy)
    await login(client, respx_mock)
    res = await client.put(
        "/api/v1/households/me",
        json={"members": [
            {"memberType": "adult_m", "age": 35},
            {"memberType": "toddler", "age": 4},
        ]},
    )
    assert res.status_code == 200
    assert (await _create_budget(client)).status_code == 201

    res = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 3})
    assert res.status_code == 201, res.text
    assert "adult male (age 35)" in captured["household_desc"]
    assert "toddler (age 4)" in captured["household_desc"]


async def test_generator_dedupes_duplicate_meals(client, respx_mock, monkeypatch):
    """LLM 이 한/영 중복 끼니를 반환해도 (day, meal_type) 당 1끼만 남는다."""
    from app.domains.mealplan import generator as gen_mod

    class _DupLLM:
        enabled = True

        async def complete_json(self, *a, **k):
            return {"meals": [
                {"day": 1, "meal_type": "breakfast", "name": "콩나물국밥",
                 "ingredients": [{"name": "콩나물", "quantity": 200, "unit": "g"}]},
                {"day": 1, "meal_type": "breakfast", "name": "Kongnamul Gukbap",
                 "ingredients": [{"name": "bean sprouts", "quantity": 200, "unit": "g"}]},
                {"day": 1, "meal_type": "lunch", "name": "비빔밥",
                 "ingredients": [{"name": "밥", "quantity": 300, "unit": "g"}]},
            ]}

    monkeypatch.setattr(gen_mod, "get_llm", lambda: _DupLLM())
    drafts = await gen_mod.generate_meals("KR", 2, "health", 1, 3, [], [])
    assert len(drafts) == 2
    assert drafts[0]["name"] == "콩나물국밥"


async def test_mealout_v14_fields_present(client, respx_mock):
    """MealOut 확장 필드(steps/completedAt/timeMinutes/difficulty)가 생성분에 채워진다."""
    await login(client, respx_mock)
    await _create_budget(client)
    body = (
        await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 2})
    ).json()
    meal = body["meals"][0]
    assert meal["completedAt"] is None
    assert isinstance(meal["steps"], list) and len(meal["steps"]) >= 2  # mock 기본 단계
    assert meal["timeMinutes"] == 20  # mock 폴백 기본값
    assert meal["difficulty"] == "easy"


async def test_meal_completion_set_and_unset(client, respx_mock):
    """완료=200 completedAt 세팅 → 해제=None 왕복."""
    await login(client, respx_mock)
    await _create_budget(client)
    body = (
        await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 2})
    ).json()
    plan_id, meal_id = body["id"], body["meals"][0]["id"]

    res = await client.put(
        f"/api/v1/mealplans/{plan_id}/meals/{meal_id}/completion",
        json={"completed": True},
    )
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["id"] == meal_id
    assert out["completedAt"] is not None
    assert out["completedAt"].endswith("Z")  # ISO-8601 UTC

    res = await client.put(
        f"/api/v1/mealplans/{plan_id}/meals/{meal_id}/completion",
        json={"completed": False},
    )
    assert res.status_code == 200
    assert res.json()["completedAt"] is None


async def test_meal_completion_requires_auth(client):
    plan_id = "00000000-0000-0000-0000-000000000000"
    meal_id = "00000000-0000-0000-0000-000000000001"
    res = await client.put(
        f"/api/v1/mealplans/{plan_id}/meals/{meal_id}/completion",
        json={"completed": True},
    )
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "AUTH_REQUIRED"


async def test_meal_completion_plan_not_found(client, respx_mock):
    await login(client, respx_mock)
    await _create_budget(client)
    res = await client.put(
        "/api/v1/mealplans/00000000-0000-0000-0000-000000000000"
        "/meals/00000000-0000-0000-0000-000000000001/completion",
        json={"completed": True},
    )
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "NOT_FOUND"


async def test_meal_completion_meal_not_found(client, respx_mock):
    """플랜은 내 것이지만 존재하지 않는 mealId → 404."""
    await login(client, respx_mock)
    await _create_budget(client)
    plan_id = (
        await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    ).json()["id"]
    res = await client.put(
        f"/api/v1/mealplans/{plan_id}"
        "/meals/00000000-0000-0000-0000-000000000009/completion",
        json={"completed": True},
    )
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "NOT_FOUND"


async def test_meal_completion_forbidden_other_user(client, respx_mock):
    """타 유저 플랜의 끼니 완료 시도 → 403 (CWE-639 소유자 스코프)."""
    await login(client, respx_mock, provider_user_id="kakao-1", email="a@example.com")
    await _create_budget(client)
    body = (
        await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 2})
    ).json()
    plan_id, meal_id = body["id"], body["meals"][0]["id"]

    await login(client, respx_mock, provider_user_id="kakao-2", email="b@example.com")
    res = await client.put(
        f"/api/v1/mealplans/{plan_id}/meals/{meal_id}/completion",
        json={"completed": True},
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "FORBIDDEN"


async def test_meal_completion_requires_body(client, respx_mock):
    """completed 필드 누락 → 422."""
    await login(client, respx_mock)
    await _create_budget(client)
    body = (
        await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    ).json()
    plan_id, meal_id = body["id"], body["meals"][0]["id"]
    res = await client.put(
        f"/api/v1/mealplans/{plan_id}/meals/{meal_id}/completion", json={}
    )
    assert res.status_code == 422


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, []),
        ("", []),
        ("한 줄만", ["한 줄만"]),
        ("1. 손질\n2. 볶기\n3. 담기", ["손질", "볶기", "담기"]),
        ("1) 손질 2) 볶기 3) 담기", ["손질", "볶기", "담기"]),
        ("손질\n\n볶기\n", ["손질", "볶기"]),  # 빈 줄 제거
        ("재료 2개 준비\n30분 조리", ["재료 2개 준비", "30분 조리"]),  # 문장 내 숫자는 미분리
    ],
)
def test_parse_steps(raw, expected):
    from app.domains.mealplan.schemas import parse_steps

    assert parse_steps(raw) == expected


async def test_meal_time_difficulty_round_trip_from_llm(client, respx_mock, monkeypatch):
    """LLM 이 준 time_minutes/difficulty 가 저장→응답까지 왕복한다."""
    from app.domains.mealplan import generator as gen_mod

    class _MetaLLM:
        enabled = True

        async def complete_json(self, *a, **k):
            return {"meals": [
                {"day": 1, "meal_type": "breakfast", "name": "토스트",
                 "steps": "1. 빵을 굽는다\n2. 버터를 바른다",
                 "time_minutes": 15, "difficulty": "normal",
                 "ingredients": [{"name": "빵", "quantity": 2, "unit": "ea"}]},
            ]}

    monkeypatch.setattr(gen_mod, "get_llm", lambda: _MetaLLM())
    await login(client, respx_mock)
    await _create_budget(client)
    body = (
        await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    ).json()
    meal = body["meals"][0]
    assert meal["timeMinutes"] == 15
    assert meal["difficulty"] == "normal"
    assert meal["steps"] == ["빵을 굽는다", "버터를 바른다"]


async def test_meal_llm_invalid_meta_falls_back_to_none(client, respx_mock, monkeypatch):
    """time_minutes 비정상·difficulty 범위 밖이면 None (프론트 기본값)."""
    from app.domains.mealplan import generator as gen_mod

    class _BadMetaLLM:
        enabled = True

        async def complete_json(self, *a, **k):
            return {"meals": [
                {"day": 1, "meal_type": "breakfast", "name": "죽",
                 "time_minutes": "약 20분", "difficulty": "very_hard",
                 "ingredients": [{"name": "쌀", "quantity": 100, "unit": "g"}]},
            ]}

    monkeypatch.setattr(gen_mod, "get_llm", lambda: _BadMetaLLM())
    await login(client, respx_mock)
    await _create_budget(client)
    body = (
        await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    ).json()
    meal = body["meals"][0]
    assert meal["timeMinutes"] is None
    assert meal["difficulty"] is None


def test_pricing_fallback_is_quantity_based():
    """기준가 미등록 재료 폴백이 수량 비례 + 상한(₩8,000)으로 계산된다."""
    import asyncio
    from decimal import Decimal
    from app.domains.mealplan.pricing import DBPriceProvider

    class _NoRowDB:
        async def execute(self, stmt):
            class _R:
                def scalar_one_or_none(self):
                    return None
            return _R()

    p = DBPriceProvider(_NoRowDB())
    cost_g = asyncio.get_event_loop().run_until_complete(
        p.estimate_cost("콩나물", Decimal(200), "g", "KR", "KRW"))
    assert Decimal("100") <= cost_g <= Decimal("8000")
    cost_big = asyncio.get_event_loop().run_until_complete(
        p.estimate_cost("한우", Decimal(5000), "g", "KR", "KRW"))
    assert cost_big == Decimal("8000")
