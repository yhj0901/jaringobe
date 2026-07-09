"""PUT/GET /api/v1/households/me — replace-all/검증/404/온보딩 완료 파생 테스트."""

import pytest
from sqlalchemy import select

from app.domains.auth.models import User
from app.domains.household.models import HouseholdMember
from tests.conftest import login

VALID_PAYLOAD = {
    "members": [
        {"memberType": "adult_m", "age": 35},
        {"memberType": "adult_f", "age": 33},
        {"memberType": "toddler", "age": 4},
    ]
}

BUDGET_PUT_PAYLOAD = {
    "householdSize": 3,
    "budget": {"amount": "450000", "currency": "KRW"},
    "mealDirection": "health",
    "locked": True,
    "cuisines": ["korean", "japanese"],
}


class TestPutHousehold:
    async def test_put_success(self, client, db, respx_mock):
        await login(client, respx_mock)
        res = await client.put("/api/v1/households/me", json=VALID_PAYLOAD)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["size"] == 3
        assert body["members"] == [
            {"memberType": "adult_m", "age": 35},
            {"memberType": "adult_f", "age": 33},
            {"memberType": "toddler", "age": 4},
        ]

        rows = (await db.scalars(select(HouseholdMember).order_by(HouseholdMember.position))).all()
        assert [(m.member_type, m.age, m.position) for m in rows] == [
            ("adult_m", 35, 0),
            ("adult_f", 33, 1),
            ("toddler", 4, 2),
        ]

    async def test_put_replace_all(self, client, db, respx_mock):
        """두 번째 PUT 은 기존 구성원을 전부 교체한다 (누적 금지)."""
        await login(client, respx_mock)
        assert (await client.put("/api/v1/households/me", json=VALID_PAYLOAD)).status_code == 200
        res = await client.put(
            "/api/v1/households/me",
            json={"members": [{"memberType": "teen", "age": 15}]},
        )
        assert res.status_code == 200
        assert res.json() == {"members": [{"memberType": "teen", "age": 15}], "size": 1}

        rows = (await db.scalars(select(HouseholdMember))).all()
        assert len(rows) == 1
        assert rows[0].member_type == "teen"
        assert rows[0].position == 0

    async def test_unauthenticated_401(self, client):
        res = await client.put("/api/v1/households/me", json=VALID_PAYLOAD)
        assert res.status_code == 401
        assert res.json()["detail"]["code"] == "AUTH_REQUIRED"


class TestPutHouseholdValidation:
    @pytest.mark.parametrize(
        "members",
        [
            [],  # 0명
            [{"memberType": "adult_m", "age": 35}] * 11,  # 11명 초과
            [{"memberType": "wizard", "age": 35}],  # 유형 열거 위반
            [{"memberType": "adult_m", "age": 19}],  # 성인 하한 미만
            [{"memberType": "adult_f", "age": 100}],  # 성인 상한 초과
            [{"memberType": "teen", "age": 12}],  # 청소년 하한 미만
            [{"memberType": "teen", "age": 20}],  # 청소년 상한 초과
            [{"memberType": "child", "age": 6}],  # 어린이 하한 미만
            [{"memberType": "child", "age": 13}],  # 어린이 상한 초과
            [{"memberType": "toddler", "age": -1}],  # 유아 하한 미만
            [{"memberType": "toddler", "age": 7}],  # 유아 상한 초과
            [{"memberType": "adult_m", "age": "abc"}],  # 정수 아님
            [{"memberType": "adult_m"}],  # age 누락
        ],
    )
    async def test_422_validation_error(self, client, respx_mock, members):
        await login(client, respx_mock)
        res = await client.put("/api/v1/households/me", json={"members": members})
        assert res.status_code == 422, res.text
        detail = res.json()["detail"]
        assert detail["code"] == "VALIDATION_ERROR"
        assert detail["errors"]

    async def test_422_does_not_touch_existing(self, client, db, respx_mock):
        """검증 실패 시 기존 구성원 보존 (replace-all 미실행)."""
        await login(client, respx_mock)
        await client.put("/api/v1/households/me", json=VALID_PAYLOAD)
        res = await client.put(
            "/api/v1/households/me",
            json={"members": [{"memberType": "teen", "age": 99}]},
        )
        assert res.status_code == 422
        rows = (await db.scalars(select(HouseholdMember))).all()
        assert len(rows) == 3


class TestGetHousehold:
    async def test_get_404_when_not_configured(self, client, respx_mock):
        await login(client, respx_mock)
        res = await client.get("/api/v1/households/me")
        assert res.status_code == 404
        assert res.json()["detail"]["code"] == "HOUSEHOLD_NOT_FOUND"

    async def test_get_200_after_put(self, client, respx_mock):
        await login(client, respx_mock)
        await client.put("/api/v1/households/me", json=VALID_PAYLOAD)
        res = await client.get("/api/v1/households/me")
        assert res.status_code == 200
        body = res.json()
        assert body["size"] == 3
        assert body["members"][0] == {"memberType": "adult_m", "age": 35}

    async def test_unauthenticated_401(self, client):
        res = await client.get("/api/v1/households/me")
        assert res.status_code == 401


class TestOnboardingDerivation:
    async def test_household_only_does_not_complete(self, client, db, respx_mock):
        """household 만 저장 — budget_plan 없으면 온보딩 미완료."""
        await login(client, respx_mock)
        await client.put("/api/v1/households/me", json=VALID_PAYLOAD)
        user = (await db.scalars(select(User))).one()
        assert user.onboarding_completed_at is None

    async def test_household_after_budget_completes(self, client, db, respx_mock):
        """budget(PUT) → household 순서 — household 저장 시 온보딩 완료."""
        await login(client, respx_mock)
        assert (
            await client.put("/api/v1/budget/plans", json=BUDGET_PUT_PAYLOAD)
        ).status_code == 201
        user = (await db.scalars(select(User))).one()
        await db.refresh(user)
        assert user.onboarding_completed_at is None  # household 아직 없음

        await client.put("/api/v1/households/me", json=VALID_PAYLOAD)
        await db.refresh(user)
        assert user.onboarding_completed_at is not None

        me = (await client.get("/api/v1/users/me")).json()
        assert me["onboardingCompleted"] is True

    async def test_budget_after_household_completes(self, client, db, respx_mock):
        """household → budget(PUT) 순서 — budget 저장 시 온보딩 완료 (양방향)."""
        await login(client, respx_mock)
        await client.put("/api/v1/households/me", json=VALID_PAYLOAD)
        user = (await db.scalars(select(User))).one()
        await db.refresh(user)
        assert user.onboarding_completed_at is None

        res = await client.put("/api/v1/budget/plans", json=BUDGET_PUT_PAYLOAD)
        assert res.status_code == 201
        await db.refresh(user)
        assert user.onboarding_completed_at is not None

    async def test_completed_at_is_preserved(self, client, db, respx_mock):
        """이미 완료된 onboarding_completed_at 은 재저장에도 유지."""
        await login(client, respx_mock)
        await client.put("/api/v1/households/me", json=VALID_PAYLOAD)
        await client.put("/api/v1/budget/plans", json=BUDGET_PUT_PAYLOAD)
        user = (await db.scalars(select(User))).one()
        await db.refresh(user)
        first = user.onboarding_completed_at
        assert first is not None

        await client.put("/api/v1/households/me", json=VALID_PAYLOAD)
        await db.refresh(user)
        assert user.onboarding_completed_at == first
