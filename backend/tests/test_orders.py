"""order 도메인 테스트 — preview / 확정 / latest (api-spec.md §7).

conftest 의 client/login 픽스처 사용. 식단은 mock LLM 대신 DB 시드로 재료를 고정한다.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.security import utcnow
from app.domains.auth.models import User
from app.domains.mealplan.models import Meal, MealIngredient, MealPlan
from app.domains.order import service as order_service
from app.domains.order.models import Order, OrderItem
from tests.conftest import login

KR_BUDGET = {
    "householdSize": 2,
    "budget": {"amount": "500000", "currency": "KRW"},
    "mealDirection": "health",
    "source": "onboarding",
}


@pytest.fixture(autouse=True)
def _reset_order_limiters():
    from app.core.ratelimit import order_confirm_user_limiter, order_preview_user_limiter

    order_preview_user_limiter.reset()
    order_confirm_user_limiter.reset()
    yield
    order_preview_user_limiter.reset()
    order_confirm_user_limiter.reset()


async def _setup(client, respx_mock):
    """로그인 + 예산안. 식단은 테스트가 DB 로 시드한다."""
    await login(client, respx_mock)
    res = await client.post("/api/v1/budget/plans", json=KR_BUDGET)
    assert res.status_code == 201, res.text
    me = (await client.get("/api/v1/users/me")).json()
    return me, res.json()["id"]


async def _seed_plan(
    db,
    user_id,
    budget_id,
    meals,
    region="KR",
    currency="KRW",
    start=None,
) -> MealPlan:
    start = start or utcnow().date()
    plan = MealPlan(
        user_id=UUID(str(user_id)),
        budget_plan_id=UUID(str(budget_id)),
        status="ready",
        total_cost=Decimal("0"),
        currency=currency,
        region=region,
        period_start=start,
        period_end=start + timedelta(days=6),
    )
    db.add(plan)
    await db.flush()
    for i, spec in enumerate(meals):
        meal = Meal(
            meal_plan_id=plan.id,
            plan_date=start,
            meal_type="breakfast",
            recipe_name=spec.get("recipe", f"meal-{i}"),
            completed_at=spec.get("completed_at"),
        )
        db.add(meal)
        await db.flush()
        for ing in spec["ingredients"]:
            db.add(
                MealIngredient(
                    meal_id=meal.id,
                    name=ing["name"],
                    quantity=Decimal(str(ing["quantity"])),
                    unit=ing["unit"],
                )
            )
    await db.commit()
    await db.refresh(plan)
    return plan


async def test_preview_404_without_mealplan(client, respx_mock):
    await login(client, respx_mock)
    res = await client.get("/api/v1/orders/preview")
    assert res.status_code == 404, res.text
    assert res.json()["detail"]["code"] == "MEALPLAN_NOT_FOUND"


async def test_preview_without_saved_draft_is_rate_limited_without_refresh(
    client, respx_mock
):
    await login(client, respx_mock)
    for _ in range(3):
        response = await client.get("/api/v1/orders/preview")
        assert response.status_code == 404
    limited = await client.get("/api/v1/orders/preview")
    assert limited.status_code == 429
    assert limited.json()["detail"]["code"] == "RATE_LIMITED"


async def test_preview_saved_draft_reads_do_not_consume_expensive_rate_limit(
    client, db, respx_mock
):
    me, budget_id = await _setup(client, respx_mock)
    cycle_start = date.fromisoformat((await client.get("/api/v1/cycle")).json()["cycleStart"])
    await _seed_plan(
        db,
        me["id"],
        budget_id,
        [{"ingredients": [{"name": "계란", "quantity": "4", "unit": "ea"}]}],
        start=cycle_start,
    )
    user = await db.get(User, UUID(me["id"]))
    assert user is not None
    draft = await order_service.create_draft(
        db,
        user,
        cycle_start=cycle_start,
        frequency="weekly",
        auto_confirm=True,
        grace_hours=24,
        force_unmatched=True,
    )
    assert draft is not None
    await db.commit()

    for _ in range(6):
        response = await client.get("/api/v1/orders/preview")
        assert response.status_code == 200, response.text
        assert response.json()["orderId"] == str(draft.id)


async def test_preview_splits_needed_covered_trim_case(client, db, respx_mock):
    """이름 strip+lower + 단위 일치로 냉장고 감산. toBuy==0 은 covered."""
    me, budget_id = await _setup(client, respx_mock)
    await _seed_plan(
        db, me["id"], budget_id,
        [{"ingredients": [
            {"name": " Egg ", "quantity": "12", "unit": "ea"},
            {"name": "양파", "quantity": "3", "unit": "ea"},
        ]}],
    )
    add = await client.post("/api/v1/fridge/items", json={"items": [
        {"name": "egg", "quantity": "2", "unit": "ea"},
        {"name": " 양파 ", "quantity": "3", "unit": "ea"},
    ]})
    assert add.status_code == 201, add.text

    res = await client.get("/api/v1/orders/preview")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["country"] == "KR"
    assert body["storeConnected"] is False
    by_needed = {i["name"]: i for i in body["needed"]}
    by_covered = {i["name"]: i for i in body["covered"]}
    assert "Egg" in by_needed
    assert by_needed["Egg"]["needed"] == "12"
    assert by_needed["Egg"]["fromFridge"] == "2"
    assert by_needed["Egg"]["toBuy"] == "10"
    assert "양파" in by_covered
    assert by_covered["양파"]["toBuy"] == "0"
    assert by_covered["양파"]["fromFridge"] == "3"
    assert "Egg" not in by_covered
    assert "양파" not in by_needed
    # 키 없으면 매칭 실패 + 추정가 0
    assert body["estimatedTotal"]["amount"] == "0.00"
    assert body["estimatedTotal"]["currency"] == "KRW"
    assert all(item["matched"] is False for item in body["cart"]["items"])
    assert body["notes"] == ["PRICE_LOOKUP_UNAVAILABLE"]
    assert body["cart"]["notes"] == ["PRICE_LOOKUP_UNAVAILABLE"]
    assert "NAVER_CLIENT" not in str(body)
    assert ".env" not in str(body)


async def test_preview_excludes_completed_meals(client, db, respx_mock):
    me, budget_id = await _setup(client, respx_mock)
    await _seed_plan(
        db, me["id"], budget_id,
        [
            {"recipe": "incomplete", "ingredients": [
                {"name": "당근", "quantity": "5", "unit": "ea"},
            ]},
            {"recipe": "done", "completed_at": utcnow(), "ingredients": [
                {"name": "소고기", "quantity": "1", "unit": "kg"},
            ]},
        ],
    )
    res = await client.get("/api/v1/orders/preview")
    assert res.status_code == 200, res.text
    names = {i["name"] for i in res.json()["needed"]} | {i["name"] for i in res.json()["covered"]}
    assert names == {"당근"}
    assert "소고기" not in names


async def test_post_rejects_extra_items_field(client, respx_mock):
    """클라이언트 라인 목록은 extra='forbid' → 422 VALIDATION_ERROR (CWE-602)."""
    await login(client, respx_mock)
    res = await client.post("/api/v1/orders", json={"store": "kurly", "items": []})
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "VALIDATION_ERROR"


async def test_post_store_not_connected_422(client, db, respx_mock):
    me, budget_id = await _setup(client, respx_mock)
    await _seed_plan(
        db, me["id"], budget_id,
        [{"ingredients": [{"name": "계란", "quantity": "2", "unit": "ea"}]}],
    )
    res = await client.post("/api/v1/orders", json={"store": "kurly"})
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "STORE_NOT_CONNECTED"


async def test_post_store_not_supported_404(client, respx_mock):
    """KR 유저가 US 스토어(walmart) 확정 → 404 STORE_NOT_SUPPORTED."""
    await login(client, respx_mock)
    res = await client.post("/api/v1/orders", json={"store": "walmart"})
    assert res.status_code == 404, res.text
    assert res.json()["detail"]["code"] == "STORE_NOT_SUPPORTED"


async def test_post_defers_inbound_until_delivery_and_is_idempotent(client, db, respx_mock):
    """확정 시 등록하지 않고 배송 확인 뒤 needed 만 delivery 로 1회 등록한다."""
    me, budget_id = await _setup(client, respx_mock)
    await _seed_plan(
        db, me["id"], budget_id,
        [{"ingredients": [
            {"name": "계란", "quantity": "12", "unit": "ea"},
            {"name": "양파", "quantity": "3", "unit": "ea"},
        ]}],
    )
    await client.post("/api/v1/fridge/items", json={"items": [
        {"name": "계란", "quantity": "2", "unit": "ea"},
        {"name": "양파", "quantity": "3", "unit": "ea"},
    ]})
    conn = await client.put("/api/v1/stores/connections/kurly", json={"connected": True})
    assert conn.status_code == 200, conn.text

    res = await client.post("/api/v1/orders", json={"store": "kurly"})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["store"] == "kurly"
    assert body["status"] == "confirmed"
    assert body["frequency"] == "weekly"
    assert body["simulation"] is True
    assert body["confirmedAt"].endswith("Z")
    assert body["deliveryEta"].endswith("Z")
    assert body["inboundAt"] is None
    assert body["deliveryState"] == "pending"
    assert body["nextSuggestedAt"].endswith("Z")
    assert body["estimatedTotal"]["amount"] == "0.00"
    assert body["estimatedTotal"]["currency"] == "KRW"
    by_type = {}
    for item in body["items"]:
        by_type[item["lineType"]] = item
    assert by_type["needed"]["name"] == "계란"
    assert by_type["needed"]["quantity"] == "10"
    assert by_type["covered"]["name"] == "양파"
    assert by_type["covered"]["quantity"] == "3"
    assert by_type["covered"]["matched"] is False
    assert by_type["covered"]["unitPrice"] is None

    rows = (await db.scalars(select(Order))).all()
    assert len(rows) == 1
    assert rows[0].status == "confirmed" and rows[0].simulation is True
    item_rows = (await db.scalars(select(OrderItem))).all()
    assert {r.line_type for r in item_rows} == {"needed", "covered"}

    before_delivery = (await client.get("/api/v1/fridge")).json()
    assert not [i for i in before_delivery if i["source"] == "delivery"]

    delivered = await client.post(
        f"/api/v1/orders/{body['id']}/delivery", json={"received": True}
    )
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["deliveryState"] == "delivered"
    assert delivered.json()["inboundAt"].endswith("Z")
    # 같은 보정 재시도는 compare-and-set no-op 이어야 한다.
    repeated = await client.post(
        f"/api/v1/orders/{body['id']}/delivery", json={"received": True}
    )
    assert repeated.status_code == 200, repeated.text

    fridge = (await client.get("/api/v1/fridge")).json()
    delivery_rows = [i for i in fridge if i["source"] == "delivery"]
    assert len(delivery_rows) == 1
    assert delivery_rows[0]["name"] == "계란"
    assert delivery_rows[0]["quantity"] == "10"
    assert delivery_rows[0]["expiresAt"] is None
    onion_total = sum(Decimal(i["quantity"]) for i in fridge if i["name"] == "양파")
    assert onion_total == Decimal("3")
    egg_total = sum(Decimal(i["quantity"]) for i in fridge if i["name"] == "계란")
    assert egg_total == Decimal("12")  # 기존 2 + delivery inbound 10


async def test_latest_returns_confirmed_order(client, db, respx_mock):
    me, budget_id = await _setup(client, respx_mock)
    await _seed_plan(
        db, me["id"], budget_id,
        [{"ingredients": [{"name": "계란", "quantity": "4", "unit": "ea"}]}],
    )
    await client.put("/api/v1/stores/connections/kurly", json={"connected": True})
    created = await client.post("/api/v1/orders", json={"store": "kurly"})
    assert created.status_code == 201, created.text

    latest = await client.get("/api/v1/orders/latest")
    assert latest.status_code == 200, latest.text
    assert latest.json()["id"] == created.json()["id"]
    assert latest.json()["status"] == "confirmed"


async def test_nothing_to_order_when_fridge_covers_all(client, db, respx_mock):
    me, budget_id = await _setup(client, respx_mock)
    await _seed_plan(
        db, me["id"], budget_id,
        [{"ingredients": [{"name": "계란", "quantity": "4", "unit": "ea"}]}],
    )
    await client.post("/api/v1/fridge/items", json={"items": [
        {"name": "계란", "quantity": "4", "unit": "ea"},
    ]})
    await client.put("/api/v1/stores/connections/kurly", json={"connected": True})

    preview = await client.get("/api/v1/orders/preview")
    assert preview.status_code == 200
    assert preview.json()["needed"] == []
    assert preview.json()["covered"][0]["name"] == "계란"

    res = await client.post("/api/v1/orders", json={"store": "kurly"})
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "NOTHING_TO_ORDER"


async def test_us_user_preview_has_zero_usd(client, db, respx_mock):
    """US 회원 — 네이버 스킵, 가짜 USD 가격 금지, estimatedTotal 0.00 USD."""
    me, budget_id = await _setup(client, respx_mock)
    await _seed_plan(
        db, me["id"], budget_id,
        [{"ingredients": [{"name": "eggs", "quantity": "12", "unit": "ea"}]}],
        region="US",
        currency="USD",
    )
    switched = await client.put("/api/v1/users/me/region", json={"country": "US"})
    assert switched.status_code == 200, switched.text
    assert switched.json()["country"] == "US"
    assert switched.json()["currency"] == "USD"

    res = await client.get("/api/v1/orders/preview")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["country"] == "US"
    assert body["estimatedTotal"] == {"amount": "0.00", "currency": "USD"}
    assert body["cart"]["total"] == {"amount": "0.00", "currency": "USD"}
    assert body["needed"][0]["name"] == "eggs"
    for item in body["cart"]["items"]:
        assert item["matched"] is False
        assert item["price"] is None
        assert item["title"] is None
