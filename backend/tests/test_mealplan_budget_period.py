"""식단 원가·한도·요약이 동일한 날짜 범위를 사용하는지 검증한다."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.core.ratelimit import mealplan_user_limiter, store_user_limiter
from app.domains.mealplan import service
from app.domains.mealplan.models import MealPlan
from tests.conftest import login


@pytest.fixture(autouse=True)
def _reset_limiters():
    mealplan_user_limiter.reset()
    store_user_limiter.reset()


@pytest.mark.parametrize(
    "start,days,cost,expected_limit",
    [
        ("2026-09-01", 7, "155876.00", "42000.00"),
        ("2026-09-01", 7, "42000.00", "42000.00"),
        ("2026-09-01", 7, "42000.01", "42000.00"),
        ("2026-08-29", 7, "41419.36", "41419.35"),
        ("2028-02-27", 3, "18620.69", "18620.69"),
        ("2026-09-01", 1, "6000.01", "6000.00"),
    ],
)
async def test_generation_and_regeneration_use_plan_period_budget(
    client,
    respx_mock,
    monkeypatch,
    start,
    days,
    cost,
    expected_limit,
):
    """실측 초과액·동일액·센트 경계·월 경계·윤년·하루 및 재생성까지 고정."""
    now = datetime.fromisoformat(start).replace(tzinfo=UTC)
    monkeypatch.setattr(service, "utcnow", lambda: now)
    monkeypatch.setattr(service, "_price", AsyncMock(return_value=Decimal(cost)))
    await login(client, respx_mock)
    budget = await client.put(
        "/api/v1/budget/plans",
        json={
            "householdSize": 2,
            "budget": {"amount": "180000", "currency": "KRW"},
            "mealDirection": "health",
            "locked": True,
            "cuisines": [],
        },
    )
    assert budget.status_code == 201
    accepted = await client.post(
        "/api/v1/mealplans",
        json={"days": days, "mealsPerDay": 1},
    )
    assert accepted.status_code == 202
    plan_id = accepted.json()["id"]
    within = Decimal(cost) <= Decimal(expected_limit)

    async def assert_summary():
        for endpoint in (f"/api/v1/mealplans/{plan_id}", "/api/v1/mealplans/latest"):
            response = await client.get(endpoint)
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == ("ready" if within else "over_budget")
            assert body["periodStart"] == start
            assert len(body["meals"]) == days
            assert body["budgetSummary"] == {
                "budget": {"amount": expected_limit, "currency": "KRW"},
                "plannedCost": {"amount": cost, "currency": "KRW"},
                "remaining": {
                    "amount": str(Decimal(expected_limit) - Decimal(cost)),
                    "currency": "KRW",
                },
                "withinBudget": within,
            }
            if not within:
                assert body["notes"] == [f"⚠️ 예산 초과: {cost} KRW > {expected_limit} KRW"]
            else:
                assert body["notes"] == []

    await assert_summary()
    # 재생성 실행일이 바뀌어도 원래 식단 날짜(월별 분모)를 사용해야 한다.
    monkeypatch.setattr(service, "utcnow", lambda: datetime(2028, 4, 1, tzinfo=UTC))
    regenerated = await client.post(
        f"/api/v1/mealplans/{plan_id}/regenerate",
        json={"scope": "all"},
    )
    assert regenerated.status_code == 202
    await assert_summary()


async def test_summary_rechecks_legacy_status_and_current_budget(
    client,
    respx_mock,
    monkeypatch,
    db,
):
    """기존 월 기준 ready 행·예산 변경 후에도 금액과 withinBudget이 모순되지 않는다."""
    monkeypatch.setattr(service, "utcnow", lambda: datetime(2026, 9, 1, tzinfo=UTC))
    monkeypatch.setattr(service, "_price", AsyncMock(return_value=Decimal("155876.00")))
    await login(client, respx_mock)
    payload = {
        "householdSize": 2,
        "budget": {"amount": "180000", "currency": "KRW"},
        "mealDirection": "health",
        "locked": True,
        "cuisines": [],
    }
    await client.put("/api/v1/budget/plans", json=payload)
    accepted = await client.post("/api/v1/mealplans", json={"days": 7, "mealsPerDay": 1})
    plan_id = accepted.json()["id"]
    plan = await db.get(MealPlan, UUID(plan_id))
    assert plan is not None
    plan.status = "ready"  # 수정 전 서비스가 남긴 잘못된 판정 재현
    await db.commit()
    got = (await client.get(f"/api/v1/mealplans/{plan_id}")).json()
    assert got["status"] == "over_budget"
    assert got["budgetSummary"]["withinBudget"] is False
    assert got["budgetSummary"]["remaining"]["amount"] == "-113876.00"
    assert got["notes"] == ["⚠️ 예산 초과: 155876.00 KRW > 42000.00 KRW"]

    plan.status = "over_budget"
    await db.commit()
    payload["budget"]["amount"] = "900000"
    updated = await client.put("/api/v1/budget/plans", json=payload)
    assert updated.status_code == 200
    got = (await client.get(f"/api/v1/mealplans/{plan_id}")).json()
    assert got["status"] == "ready"
    assert got["budgetSummary"]["budget"]["amount"] == "210000.00"
    assert got["budgetSummary"]["remaining"]["amount"] == "54124.00"
    assert got["budgetSummary"]["withinBudget"] is True
    assert got["notes"] == []
