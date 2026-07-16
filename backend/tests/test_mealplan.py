"""mealplan 도메인 통합 테스트 — 로그인(mock provider) + mock LLM.

conftest 의 login/ client 픽스처 사용. LLM 은 ANTHROPIC_API_KEY 미설정 → mock.
"""

import uuid

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


async def _create_plan(client, json_body: dict) -> dict:
    """v1.5 비동기 계약: 202 접수 → (백그라운드 완료 후) GET 상세 반환."""
    res = await client.post("/api/v1/mealplans", json=json_body)
    assert res.status_code == 202, res.text
    accepted = res.json()
    assert accepted["status"] == "processing"
    got = await client.get(f"/api/v1/mealplans/{accepted['id']}")
    assert got.status_code == 200, got.text
    return got.json()


async def test_create_returns_202_accepted(client, respx_mock):
    """POST /mealplans → 202 {id, status:"processing"} (api-spec §3-2 v1.5)."""
    await login(client, respx_mock)
    assert (await _create_budget(client)).status_code == 201

    res = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    assert res.status_code == 202, res.text
    body = res.json()
    assert set(body.keys()) == {"id", "status"}
    assert body["status"] == "processing"


async def test_create_and_get_mealplan(client, respx_mock):
    await login(client, respx_mock)
    assert (await _create_budget(client)).status_code == 201

    body = await _create_plan(
        client, {"days": 2, "mealsPerDay": 3, "allergies": ["peanut"]}
    )
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
    body = await _create_plan(client, {"days": 7, "mealsPerDay": 3})
    assert body["status"] == "over_budget"
    assert body["budgetSummary"]["withinBudget"] is False
    assert body["notes"]  # 초과 안내 노출 (자르지 않음 — 폴링 GET 에서도 노출)


async def test_mealplan_ownership_forbidden(client, respx_mock):
    await login(client, respx_mock, provider_user_id="kakao-1", email="a@example.com")
    await _create_budget(client)
    plan_id = (await _create_plan(client, {"days": 1, "mealsPerDay": 2}))["id"]

    # 다른 유저로 재로그인 → 타인 식단 접근 시 403
    await login(client, respx_mock, provider_user_id="kakao-2", email="b@example.com")
    res = await client.get(f"/api/v1/mealplans/{plan_id}")
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "FORBIDDEN"


async def test_mealplan_regenerate_all(client, respx_mock):
    await login(client, respx_mock)
    await _create_budget(client)
    plan_id = (await _create_plan(client, {"days": 2, "mealsPerDay": 2}))["id"]
    res = await client.post(
        f"/api/v1/mealplans/{plan_id}/regenerate", json={"scope": "all"}
    )
    assert res.status_code == 202, res.text
    assert res.json() == {"id": plan_id, "status": "processing"}
    # 백그라운드 완료 후 폴링 → 재생성 결과 반영
    got = await client.get(f"/api/v1/mealplans/{plan_id}")
    assert got.status_code == 200
    assert got.json()["status"] in ("ready", "over_budget")
    assert got.json()["meals"]


async def test_mealplan_duplicate_generation_409(client, respx_mock, monkeypatch):
    """이미 processing 플랜이 있으면 409 MEALPLAN_GENERATING (api-spec §3-2)."""
    from app.domains.mealplan import service as svc

    async def _noop(*a, **k):
        return None

    # 백그라운드 생성을 무력화 → 첫 플랜이 processing 으로 남는다
    monkeypatch.setattr(svc, "run_meal_plan_generation", _noop)
    await login(client, respx_mock)
    await _create_budget(client)

    first = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    assert first.status_code == 202
    plan_id = first.json()["id"]

    res = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "MEALPLAN_GENERATING"

    # 재생성도 동일 차단
    res = await client.post(f"/api/v1/mealplans/{plan_id}/regenerate", json={"scope": "all"})
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "MEALPLAN_GENERATING"


async def test_mealplan_processing_polling_shape(client, respx_mock, monkeypatch):
    """processing 상태 GET: meals []·budgetSummary null·period null (api-spec §3-2 v1.5)."""
    from app.domains.mealplan import service as svc

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(svc, "run_meal_plan_generation", _noop)
    await login(client, respx_mock)
    await _create_budget(client)
    plan_id = (
        await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    ).json()["id"]

    got = await client.get(f"/api/v1/mealplans/{plan_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["status"] == "processing"
    assert body["meals"] == []
    assert body["budgetSummary"] is None
    assert body["periodStart"] is None and body["periodEnd"] is None
    assert body["notes"] == []

    # latest 도 status 무관 최신 1건 반환 (v1.5 §3-6)
    latest = await client.get("/api/v1/mealplans/latest")
    assert latest.status_code == 200
    assert latest.json()["id"] == plan_id
    assert latest.json()["status"] == "processing"


async def test_mealplan_generation_failure_marks_failed(client, respx_mock, monkeypatch):
    """생성이 폴백까지 전부 실패하면 status=failed + notes GENERATION_FAILED."""
    from app.domains.mealplan import service as svc

    async def _boom(*a, **k):
        raise RuntimeError("simulated total generation failure")

    monkeypatch.setattr(svc, "_generate_within_budget", _boom)
    await login(client, respx_mock)
    await _create_budget(client)

    res = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    assert res.status_code == 202

    got = await client.get(f"/api/v1/mealplans/{res.json()['id']}")
    assert got.status_code == 200
    body = got.json()
    assert body["status"] == "failed"
    assert body["notes"] == ["GENERATION_FAILED"]
    assert body["meals"] == []
    assert body["budgetSummary"] is None


async def test_mealplan_not_found(client, respx_mock):
    await login(client, respx_mock)
    await _create_budget(client)
    res = await client.get("/api/v1/mealplans/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404


async def test_latest_mealplan_returns_most_recent(client, respx_mock):
    await login(client, respx_mock)
    await _create_budget(client)
    first_id = (await _create_plan(client, {"days": 1, "mealsPerDay": 2}))["id"]
    second_id = (await _create_plan(client, {"days": 2, "mealsPerDay": 2}))["id"]
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
    assert res.status_code == 202

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
    assert res.status_code == 202


async def test_regenerate_pref_limits_422(client, respx_mock):
    await login(client, respx_mock)
    await _create_budget(client)
    plan_id = (await _create_plan(client, {"days": 1, "mealsPerDay": 1}))["id"]
    res = await client.post(
        f"/api/v1/mealplans/{plan_id}/regenerate",
        json={"scope": "all", "allergies": ["a" * 31]},
    )
    assert res.status_code == 422


async def test_create_meal_plan_llm_failure_falls_back(client, respx_mock, monkeypatch):
    """LLM 예외(타임아웃 등)는 failed 가 아니라 규칙 기반 폴백 생성 (api-spec §3-2)."""
    from app.domains.mealplan import generator as gen_mod

    class _FailingLLM:
        enabled = True

        async def complete_json(self, *a, **k):
            raise TimeoutError("simulated LLM timeout")

    monkeypatch.setattr(gen_mod, "get_llm", lambda: _FailingLLM())
    await login(client, respx_mock)
    assert (await _create_budget(client)).status_code == 201

    body = await _create_plan(client, {"days": 3, "mealsPerDay": 3})
    assert body["status"] in ("ready", "over_budget")
    assert len(body["meals"]) == 9


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

    body = await _create_plan(client, {"days": 7, "mealsPerDay": 3})
    assert body["status"] == "over_budget"
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
    assert res.status_code == 202, res.text
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
    body = await _create_plan(client, {"days": 1, "mealsPerDay": 2})
    meal = body["meals"][0]
    assert meal["completedAt"] is None
    assert isinstance(meal["steps"], list) and len(meal["steps"]) >= 2  # mock 기본 단계
    assert meal["timeMinutes"] == 20  # mock 폴백 기본값
    assert meal["difficulty"] == "easy"


async def test_meal_completion_set_and_unset(client, respx_mock):
    """완료=200 completedAt 세팅 → 해제=None 왕복."""
    await login(client, respx_mock)
    await _create_budget(client)
    body = await _create_plan(client, {"days": 1, "mealsPerDay": 2})
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
    plan_id = (await _create_plan(client, {"days": 1, "mealsPerDay": 1}))["id"]
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
    body = await _create_plan(client, {"days": 1, "mealsPerDay": 2})
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
    body = await _create_plan(client, {"days": 1, "mealsPerDay": 1})
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
    body = await _create_plan(client, {"days": 1, "mealsPerDay": 1})
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
    body = await _create_plan(client, {"days": 1, "mealsPerDay": 1})
    meal = body["meals"][0]
    assert meal["timeMinutes"] is None
    assert meal["difficulty"] is None


# ---------- BUG-001: 좀비 processing 플랜 stale 수렴 ----------


def _stall_generation(monkeypatch):
    """백그라운드 생성 무력화 — 서버 재시작으로 BackgroundTasks 가 유실된 상황 시뮬레이션."""
    from app.domains.mealplan import service as svc

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(svc, "run_meal_plan_generation", _noop)


async def _age_plan(db, plan_id, minutes: int = 11) -> None:
    """플랜 created_at 을 과거로 밀어 stale(기본 타임아웃 10분) 상태로 만든다."""
    from datetime import timedelta

    from sqlalchemy import update

    from app.core.security import utcnow
    from app.domains.mealplan.models import MealPlan

    await db.execute(
        update(MealPlan)
        .where(MealPlan.id == plan_id)
        .values(created_at=utcnow() - timedelta(minutes=minutes))
    )
    await db.commit()


async def test_stale_processing_allows_new_generation(client, db, respx_mock, monkeypatch):
    """타임아웃 지난 좀비 processing 은 failed 마킹 후 신규 생성 통과 (BUG-001)."""
    _stall_generation(monkeypatch)
    await login(client, respx_mock)
    await _create_budget(client)

    first = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    assert first.status_code == 202
    zombie_id = first.json()["id"]

    # 아직 stale 아님 → 기존대로 409
    res = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "MEALPLAN_GENERATING"

    await _age_plan(db, zombie_id)
    res = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    assert res.status_code == 202, res.text  # 영구 409 잠금 해제

    # 좀비는 failed 로 수렴
    got = await client.get(f"/api/v1/mealplans/{zombie_id}")
    assert got.status_code == 200
    assert got.json()["status"] == "failed"
    assert got.json()["notes"] == ["GENERATION_FAILED"]


async def test_stale_processing_regenerate_not_blocked_forever(
    client, db, respx_mock, monkeypatch
):
    """좀비 processing 이 있어도 (다른 ready 플랜) 재생성이 영구 409 되지 않는다 (BUG-001)."""
    await login(client, respx_mock)
    await _create_budget(client)
    ready_id = (await _create_plan(client, {"days": 1, "mealsPerDay": 2}))["id"]

    _stall_generation(monkeypatch)
    zombie = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    assert zombie.status_code == 202
    await _age_plan(db, zombie.json()["id"])

    res = await client.post(f"/api/v1/mealplans/{ready_id}/regenerate", json={"scope": "all"})
    assert res.status_code == 202, res.text


async def test_stale_processing_get_by_id_converges_to_failed(
    client, db, respx_mock, monkeypatch
):
    """조회 경로(GET {id}) 지연 정리 — stale processing 을 failed 로 응답 + DB 반영 (BUG-001)."""
    from sqlalchemy import select

    from app.domains.mealplan.models import MealPlan

    _stall_generation(monkeypatch)
    await login(client, respx_mock)
    await _create_budget(client)
    plan_id = (
        await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    ).json()["id"]
    await _age_plan(db, plan_id)

    got = await client.get(f"/api/v1/mealplans/{plan_id}")
    assert got.status_code == 200
    assert got.json()["status"] == "failed"
    assert got.json()["notes"] == ["GENERATION_FAILED"]

    row = await db.scalar(select(MealPlan).where(MealPlan.id == uuid.UUID(plan_id)))
    await db.refresh(row)
    assert row.status == "failed"  # 응답용 간주가 아니라 실제 failed 마킹 (지연 정리)


async def test_stale_processing_latest_converges_to_failed(client, db, respx_mock, monkeypatch):
    """조회 경로(GET latest) 지연 정리 — stale processing 을 failed 로 응답 (BUG-001)."""
    _stall_generation(monkeypatch)
    await login(client, respx_mock)
    await _create_budget(client)
    plan_id = (
        await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    ).json()["id"]
    await _age_plan(db, plan_id)

    latest = await client.get("/api/v1/mealplans/latest")
    assert latest.status_code == 200
    assert latest.json()["id"] == plan_id
    assert latest.json()["status"] == "failed"


async def test_fresh_processing_not_marked_stale(client, respx_mock, monkeypatch):
    """타임아웃 전 processing 은 그대로 processing (오탐 없음)."""
    _stall_generation(monkeypatch)
    await login(client, respx_mock)
    await _create_budget(client)
    plan_id = (
        await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    ).json()["id"]

    got = await client.get(f"/api/v1/mealplans/{plan_id}")
    assert got.json()["status"] == "processing"


async def test_mark_failed_failure_converges_via_stale(client, db, respx_mock, monkeypatch):
    """생성 실패 + failed 마킹까지 실패해도 stale 경로로 결국 failed 수렴 (BUG-001)."""
    from app.domains.mealplan import service as svc

    async def _boom(*a, **k):
        raise RuntimeError("simulated total generation failure")

    async def _mark_fails(*a, **k):
        return None  # DB 장애 등으로 failed 마킹 자체가 실패 — processing 잔류

    monkeypatch.setattr(svc, "_generate_within_budget", _boom)
    monkeypatch.setattr(svc, "_mark_generation_failed", _mark_fails)
    await login(client, respx_mock)
    await _create_budget(client)

    res = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    assert res.status_code == 202
    plan_id = res.json()["id"]

    got = await client.get(f"/api/v1/mealplans/{plan_id}")
    assert got.json()["status"] == "processing"  # 마킹 실패로 잔류

    await _age_plan(db, plan_id)
    got = await client.get(f"/api/v1/mealplans/{plan_id}")
    assert got.json()["status"] == "failed"
    assert got.json()["notes"] == ["GENERATION_FAILED"]

    # 신규 생성도 다시 가능 (영구 잠금 없음)
    monkeypatch.setattr(svc, "run_meal_plan_generation", _mark_fails)  # 접수만 검증
    res = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    assert res.status_code == 202


async def test_regenerate_resets_stale_clock(client, db, respx_mock, monkeypatch):
    """재생성 접수 시 created_at 갱신 — 오래된 플랜이 즉시 stale 로 오판되지 않는다 (BUG-001)."""
    await login(client, respx_mock)
    await _create_budget(client)
    plan_id = (await _create_plan(client, {"days": 1, "mealsPerDay": 2}))["id"]
    await _age_plan(db, plan_id)  # 플랜 자체는 오래됨 (생성 후 11분 경과)

    _stall_generation(monkeypatch)  # 재생성 백그라운드는 아직 미완료 상태 유지
    res = await client.post(f"/api/v1/mealplans/{plan_id}/regenerate", json={"scope": "all"})
    assert res.status_code == 202

    got = await client.get(f"/api/v1/mealplans/{plan_id}")
    assert got.json()["status"] == "processing"  # 방금 시작 — stale 아님


# ---------- BUG-002: failed 재생성 시 mealsPerDay 붕괴 제거 ----------


async def test_regenerate_failed_empty_plan_409_dedicated_code(client, respx_mock, monkeypatch):
    """meals 0 failed 플랜 재생성 → 409 MEALPLAN_REGENERATE_EMPTY (BUG-002 — 1끼 붕괴 제거).

    원 요청 파라미터 스냅샷이 없어(스키마 변경 불가) 복원 불가 — 신규 POST 유도 전용 코드.
    """
    from app.domains.mealplan import service as svc

    async def _boom(*a, **k):
        raise RuntimeError("simulated total generation failure")

    monkeypatch.setattr(svc, "_generate_within_budget", _boom)
    await login(client, respx_mock)
    await _create_budget(client)

    res = await client.post("/api/v1/mealplans", json={"days": 3, "mealsPerDay": 3})
    assert res.status_code == 202
    plan_id = res.json()["id"]
    got = await client.get(f"/api/v1/mealplans/{plan_id}")
    assert got.json()["status"] == "failed"

    res = await client.post(f"/api/v1/mealplans/{plan_id}/regenerate", json={"scope": "all"})
    assert res.status_code == 409, res.text
    assert res.json()["detail"]["code"] == "MEALPLAN_REGENERATE_EMPTY"

    # 하루 1끼 플랜으로 조용히 붕괴하지 않는다 — failed 그대로
    got = await client.get(f"/api/v1/mealplans/{plan_id}")
    assert got.json()["status"] == "failed"
    assert got.json()["meals"] == []


async def test_regenerate_preserves_meals_per_day(client, respx_mock):
    """days=2·mealsPerDay=3 플랜 재생성 → 하루 3끼(총 6끼) 유지 (BUG-002)."""
    await login(client, respx_mock)
    await _create_budget(client)
    body = await _create_plan(client, {"days": 2, "mealsPerDay": 3})
    assert len(body["meals"]) == 6
    plan_id = body["id"]

    res = await client.post(f"/api/v1/mealplans/{plan_id}/regenerate", json={"scope": "all"})
    assert res.status_code == 202
    got = await client.get(f"/api/v1/mealplans/{plan_id}")
    assert got.status_code == 200
    assert got.json()["status"] in ("ready", "over_budget")
    assert len(got.json()["meals"]) == 6  # round(len/days) 왜곡 없이 하루 3끼 유지


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
