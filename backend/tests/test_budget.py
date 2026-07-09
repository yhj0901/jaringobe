"""POST /api/v1/budget/plans — 성공/409/422/401 테스트."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.domains.auth.models import User
from app.domains.budget.models import BudgetPlan
from tests.conftest import login

VALID_PAYLOAD = {
    "householdSize": 4,
    "budget": {"amount": "700000", "currency": "KRW"},
    "mealDirection": "kids",
    "source": "guest",
}


class TestCreateBudgetPlan:
    async def test_create_success(self, client, db, respx_mock):
        await login(client, respx_mock)
        res = await client.post("/api/v1/budget/plans", json=VALID_PAYLOAD)
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["householdSize"] == 4
        assert body["budget"] == {"amount": "700000.00", "currency": "KRW"}  # 문자열 직렬화
        assert body["mealDirection"] == "kids"
        assert body["source"] == "guest"
        assert body["createdAt"].endswith("Z")  # ISO-8601 UTC

        plan = (await db.scalars(select(BudgetPlan))).one()
        assert plan.amount == Decimal("700000.00")
        # 성공 시 온보딩 완료 처리
        user = (await db.scalars(select(User))).one()
        assert user.onboarding_completed_at is not None

    async def test_me_reflects_budget_plan(self, client, respx_mock):
        await login(client, respx_mock)
        await client.post("/api/v1/budget/plans", json=VALID_PAYLOAD)
        me = (await client.get("/api/v1/users/me")).json()
        assert me["hasBudgetPlan"] is True
        assert me["onboardingCompleted"] is True

    async def test_usd_plan_with_decimals(self, client, respx_mock):
        await login(client, respx_mock)
        payload = {
            **VALID_PAYLOAD,
            "budget": {"amount": "125.50", "currency": "USD"},
            "source": "onboarding",
        }
        res = await client.post("/api/v1/budget/plans", json=payload)
        assert res.status_code == 201
        assert res.json()["budget"] == {"amount": "125.50", "currency": "USD"}

    async def test_duplicate_plan_409(self, client, respx_mock):
        await login(client, respx_mock)
        assert (await client.post("/api/v1/budget/plans", json=VALID_PAYLOAD)).status_code == 201
        res = await client.post("/api/v1/budget/plans", json=VALID_PAYLOAD)
        assert res.status_code == 409
        assert res.json()["detail"]["code"] == "BUDGET_PLAN_EXISTS"

    async def test_unauthenticated_401(self, client):
        res = await client.post("/api/v1/budget/plans", json=VALID_PAYLOAD)
        assert res.status_code == 401
        assert res.json()["detail"]["code"] == "AUTH_REQUIRED"


class TestValidation:
    @pytest.mark.parametrize(
        "mutation",
        [
            {"householdSize": 0},  # 하한 미만
            {"householdSize": 11},  # 상한 초과
            {"householdSize": "abc"},  # 정수 아님
            {"budget": {"amount": "49999.99", "currency": "KRW"}},  # KRW 하한 미만
            {"budget": {"amount": "5000000.01", "currency": "KRW"}},  # KRW 상한 초과
            {"budget": {"amount": "49.99", "currency": "USD"}},  # USD 하한 미만
            {"budget": {"amount": "5001", "currency": "USD"}},  # USD 상한 초과
            {"budget": {"amount": "700000", "currency": "EUR"}},  # 통화 열거 위반
            {"budget": {"amount": "700000.123", "currency": "KRW"}},  # 소수 3자리
            {"budget": {"amount": "not-a-number", "currency": "KRW"}},
            {"mealDirection": "spicy"},  # 열거 위반
            {"source": "hacked"},  # 열거 위반
        ],
    )
    async def test_422_validation_error(self, client, respx_mock, mutation):
        await login(client, respx_mock)
        payload = {**VALID_PAYLOAD, **mutation}
        res = await client.post("/api/v1/budget/plans", json=payload)
        assert res.status_code == 422, res.text
        detail = res.json()["detail"]
        assert detail["code"] == "VALIDATION_ERROR"
        assert detail["errors"]  # FastAPI 기본 오류 배열 래핑

    async def test_race_integrity_error_maps_to_409(self):
        """동시 요청 경합 — 사전 조회는 통과했지만 commit 에서 UNIQUE 위반."""
        from sqlalchemy.exc import IntegrityError

        from app.core.errors import ApiError
        from app.domains.budget import service
        from app.domains.budget.schemas import BudgetPlanCreateRequest

        class FakeDB:
            async def scalar(self, *_args, **_kwargs):
                return None  # 사전 조회에서는 기존 플랜 없음

            def add(self, _obj):
                pass

            async def commit(self):
                raise IntegrityError("stmt", {}, Exception("duplicate key"))

            async def rollback(self):
                self.rolled_back = True

        user = User(nickname="자린이")
        payload = BudgetPlanCreateRequest.model_validate(VALID_PAYLOAD)
        fake_db = FakeDB()
        with pytest.raises(ApiError) as exc_info:
            await service.create_budget_plan(fake_db, user, payload)
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "BUDGET_PLAN_EXISTS"
        assert fake_db.rolled_back is True

    async def test_422_does_not_create_plan(self, client, db, respx_mock):
        await login(client, respx_mock)
        await client.post(
            "/api/v1/budget/plans",
            json={**VALID_PAYLOAD, "budget": {"amount": "1", "currency": "KRW"}},
        )
        assert (await db.scalars(select(BudgetPlan))).all() == []
        user = (await db.scalars(select(User))).one()
        assert user.onboarding_completed_at is None


# ---------- v1.2 — PUT /api/v1/budget/plans (upsert) ----------

UPSERT_PAYLOAD = {
    "householdSize": 5,
    "budget": {"amount": "450000", "currency": "KRW"},
    "mealDirection": "health",
    "locked": True,
    "cuisines": ["korean", "japanese"],
}


class TestUpsertBudgetPlan:
    async def test_put_creates_201(self, client, db, respx_mock):
        await login(client, respx_mock)
        res = await client.put("/api/v1/budget/plans", json=UPSERT_PAYLOAD)
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["householdSize"] == 5
        assert body["budget"] == {"amount": "450000.00", "currency": "KRW"}
        assert body["mealDirection"] == "health"
        assert body["source"] == "onboarding"
        assert body["locked"] is True
        assert body["cuisines"] == ["korean", "japanese"]

        plan = (await db.scalars(select(BudgetPlan))).one()
        assert plan.locked is True
        assert plan.cuisines == ["korean", "japanese"]

    async def test_put_updates_200(self, client, db, respx_mock):
        await login(client, respx_mock)
        assert (await client.put("/api/v1/budget/plans", json=UPSERT_PAYLOAD)).status_code == 201
        res = await client.put(
            "/api/v1/budget/plans",
            json={
                "householdSize": 2,
                "budget": {"amount": "300000", "currency": "KRW"},
                "mealDirection": "diet",
                "locked": False,
                "cuisines": ["salad"],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["householdSize"] == 2
        assert body["locked"] is False
        assert body["cuisines"] == ["salad"]

        plans = (await db.scalars(select(BudgetPlan))).all()
        assert len(plans) == 1  # upsert — 중복 생성 금지
        assert plans[0].meal_direction == "diet"
        assert plans[0].locked is False

    async def test_put_updates_existing_post_plan_and_keeps_source(self, client, respx_mock):
        """기존 POST(게스트 이전)로 만든 플랜을 PUT 이 갱신 — source 유지."""
        await login(client, respx_mock)
        assert (await client.post("/api/v1/budget/plans", json=VALID_PAYLOAD)).status_code == 201
        res = await client.put("/api/v1/budget/plans", json=UPSERT_PAYLOAD)
        assert res.status_code == 200
        assert res.json()["source"] == "guest"

    async def test_put_defaults_locked_true_cuisines_empty(self, client, respx_mock):
        """locked/cuisines 미전송 시 기본값 (locked true, cuisines [])."""
        await login(client, respx_mock)
        payload = {k: v for k, v in UPSERT_PAYLOAD.items() if k not in ("locked", "cuisines")}
        res = await client.put("/api/v1/budget/plans", json=payload)
        assert res.status_code == 201
        assert res.json()["locked"] is True
        assert res.json()["cuisines"] == []

    async def test_unauthenticated_401(self, client):
        res = await client.put("/api/v1/budget/plans", json=UPSERT_PAYLOAD)
        assert res.status_code == 401

    @pytest.mark.parametrize(
        "mutation",
        [
            {"householdSize": 0},  # POST 와 동일 검증 유지
            {"budget": {"amount": "49999.99", "currency": "KRW"}},
            {"mealDirection": "spicy"},
            {"locked": "yes-please"},  # boolean 아님
            {"cuisines": ["korean", "pizza"]},  # 열거 위반
            {"cuisines": ["korean", "korean"]},  # 중복
            {
                "cuisines": [
                    "korean",
                    "western",
                    "japanese",
                    "chinese",
                    "comfort",
                    "salad",
                    "korean",
                ]
            },  # 7개 초과
            {"cuisines": "korean"},  # 배열 아님
        ],
    )
    async def test_put_422_validation_error(self, client, respx_mock, mutation):
        await login(client, respx_mock)
        res = await client.put("/api/v1/budget/plans", json={**UPSERT_PAYLOAD, **mutation})
        assert res.status_code == 422, res.text
        assert res.json()["detail"]["code"] == "VALIDATION_ERROR"

    async def test_put_race_integrity_error_maps_to_409(self):
        """동시 생성 경합 — 사전 조회는 없음이었지만 commit 에서 UNIQUE 위반."""
        from sqlalchemy.exc import IntegrityError

        from app.core.errors import ApiError
        from app.domains.budget import service
        from app.domains.budget.schemas import BudgetPlanUpsertRequest

        class FakeDB:
            async def scalar(self, *_args, **_kwargs):
                return None

            def add(self, _obj):
                pass

            async def commit(self):
                raise IntegrityError("stmt", {}, Exception("duplicate key"))

            async def rollback(self):
                self.rolled_back = True

        user = User(nickname="자린이")
        payload = BudgetPlanUpsertRequest.model_validate(UPSERT_PAYLOAD)
        fake_db = FakeDB()
        with pytest.raises(ApiError) as exc_info:
            await service.upsert_budget_plan(fake_db, user, payload)
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "BUDGET_PLAN_EXISTS"
        assert fake_db.rolled_back is True

    async def test_post_regression_defaults(self, client, db, respx_mock):
        """기존 POST 동작 불변 — locked 기본 true, cuisines 기본 [] + 응답에 확장 필드."""
        await login(client, respx_mock)
        res = await client.post("/api/v1/budget/plans", json=VALID_PAYLOAD)
        assert res.status_code == 201
        body = res.json()
        assert body["locked"] is True
        assert body["cuisines"] == []
        assert body["source"] == "guest"

        plan = (await db.scalars(select(BudgetPlan))).one()
        assert plan.locked is True
        assert plan.cuisines == []


async def test_get_budget_plan(client, respx_mock):
    """GET /budget/plans — 미설정 404 전용 코드, 설정 후 현재값 반환 (v1.3.1)."""
    await login(client, respx_mock)
    res = await client.get("/api/v1/budget/plans")
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "BUDGET_PLAN_NOT_FOUND"

    put = await client.put(
        "/api/v1/budget/plans",
        json={
            "householdSize": 3,
            "budget": {"amount": "500000", "currency": "KRW"},
            "mealDirection": "kids",
            "locked": True,
            "cuisines": ["korean", "japanese"],
        },
    )
    assert put.status_code in (200, 201)

    res = await client.get("/api/v1/budget/plans")
    assert res.status_code == 200
    body = res.json()
    assert body["mealDirection"] == "kids"
    assert body["cuisines"] == ["korean", "japanese"]
    assert body["locked"] is True
