"""order v1.8 상태 전이·배송 보정·inbound 멱등성 테스트."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.core.errors import ApiError
from app.core.security import utcnow
from app.domains.fridge import service as fridge_service
from app.domains.fridge.models import FridgeItem
from app.domains.order import service as order_service
from app.domains.order.models import Order, OrderItem
from app.domains.order.schemas import OrderPreviewResponse, ShortfallPreviewLine
from app.domains.budget.schemas import MoneyOut
from app.domains.store.schemas import CartProduct, StoreCartResponse
from tests.test_orders import _seed_plan, _setup


@pytest.fixture(autouse=True)
def _reset_action_limiter():
    from app.core.ratelimit import cycle_action_user_limiter, order_confirm_user_limiter

    cycle_action_user_limiter.reset()
    order_confirm_user_limiter.reset()
    yield
    cycle_action_user_limiter.reset()
    order_confirm_user_limiter.reset()


async def _confirmed_order(client, db, respx_mock) -> tuple[dict, dict]:
    me, budget_id = await _setup(client, respx_mock)
    await _seed_plan(
        db,
        me["id"],
        budget_id,
        [
            {
                "ingredients": [
                    {"name": "계란", "quantity": "10", "unit": "ea"},
                    {"name": "양파", "quantity": "2", "unit": "ea"},
                ]
            }
        ],
    )
    await client.put("/api/v1/stores/connections/kurly", json={"connected": True})
    response = await client.post("/api/v1/orders", json={"store": "kurly"})
    assert response.status_code == 201, response.text
    return me, response.json()


def test_state_machine_rejects_regression_and_inbound_reconfirm():
    confirmed = Order(status="confirmed", inbound_at=None)
    with pytest.raises(ApiError) as regression:
        order_service.transition_order(confirmed, "draft")
    assert regression.value.code == "ORDER_INVALID_STATE"

    inbound = Order(status="confirmed", inbound_at=utcnow())
    with pytest.raises(ApiError) as reconfirm:
        order_service.transition_order(inbound, "confirmed")
    assert reconfirm.value.code == "ORDER_INVALID_STATE"


async def test_delivery_false_rolls_back_and_unknown_then_true_recovers(
    client, db, respx_mock
):
    _me, created = await _confirmed_order(client, db, respx_mock)
    order_id = created["id"]

    arrived = await client.post(
        f"/api/v1/orders/{order_id}/delivery", json={"received": True}
    )
    assert arrived.status_code == 200
    first_eta = arrived.json()["deliveryEta"]
    assert await db.scalar(select(func.count()).select_from(FridgeItem)) == 2

    not_arrived = await client.post(
        f"/api/v1/orders/{order_id}/delivery", json={"received": False}
    )
    assert not_arrived.status_code == 200, not_arrived.text
    body = not_arrived.json()
    assert body["inboundAt"] is None
    assert body["deliveryState"] == "pending"
    assert body["deliveryConfirmAttempts"] == 1
    assert body["deliveryEta"] > first_eta
    assert await db.scalar(select(func.count()).select_from(FridgeItem)) == 0

    for expected in (2, 3):
        response = await client.post(
            f"/api/v1/orders/{order_id}/delivery", json={"received": False}
        )
        assert response.status_code == 200
        assert response.json()["deliveryConfirmAttempts"] == expected
    assert response.json()["deliveryState"] == "unknown"

    recovered = await client.post(
        f"/api/v1/orders/{order_id}/delivery", json={"received": True}
    )
    assert recovered.status_code == 200
    assert recovered.json()["deliveryState"] == "delivered"
    assert recovered.json()["inboundAt"].endswith("Z")
    assert await db.scalar(select(func.count()).select_from(FridgeItem)) == 2


async def test_delivery_false_reschedules_from_response_time(
    client, db, respx_mock, monkeypatch
):
    _me, created = await _confirmed_order(client, db, respx_mock)
    order = await db.get(Order, UUID(created["id"]))
    order.delivery_eta = datetime(2026, 8, 1, tzinfo=UTC)
    await db.commit()
    answered_at = datetime(2026, 9, 1, 12, tzinfo=UTC)
    monkeypatch.setattr(order_service, "utcnow", lambda: answered_at)

    response = await client.post(
        f"/api/v1/orders/{order.id}/delivery", json={"received": False}
    )

    assert response.status_code == 200, response.text
    assert response.json()["deliveryEta"] == "2026-09-02T12:00:00Z"


async def test_cancel_removes_remaining_delivery_rows_but_keeps_audit_time(
    client, db, respx_mock
):
    _me, created = await _confirmed_order(client, db, respx_mock)
    order_id = created["id"]
    await client.post(
        f"/api/v1/orders/{order_id}/delivery", json={"received": True}
    )
    assert await db.scalar(select(func.count()).select_from(FridgeItem)) == 2

    cancelled = await client.post(f"/api/v1/orders/{order_id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["inboundAt"].endswith("Z")
    assert await db.scalar(select(func.count()).select_from(FridgeItem)) == 0

    repeated = await client.post(f"/api/v1/orders/{order_id}/cancel")
    assert repeated.status_code == 409
    assert repeated.json()["detail"]["code"] == "ORDER_INVALID_STATE"


async def test_inbound_compare_and_set_rolls_back_atomically_on_fridge_failure(
    client, db, respx_mock, monkeypatch
):
    me, created = await _confirmed_order(client, db, respx_mock)
    order_id = UUID(created["id"])
    original = fridge_service.add_items

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated fridge insert failure")

    monkeypatch.setattr(fridge_service, "add_items", _boom)
    with pytest.raises(RuntimeError):
        await order_service.mark_inbound(db, UUID(me["id"]), order_id)
    await db.rollback()
    order = await db.get(Order, order_id)
    await db.refresh(order)
    assert order.inbound_at is None
    assert await db.scalar(select(func.count()).select_from(FridgeItem)) == 0

    monkeypatch.setattr(fridge_service, "add_items", original)
    assert await order_service.mark_inbound(db, UUID(me["id"]), order_id) is True
    assert await order_service.mark_inbound(db, UUID(me["id"]), order_id) is False
    assert await db.scalar(select(func.count()).select_from(FridgeItem)) == 2


async def test_due_inbound_scheduler_retries_without_inventory_inflation(
    client, db, respx_mock
):
    from app.domains.cycle.scheduler import process_due_inbounds

    _me, created = await _confirmed_order(client, db, respx_mock)
    order = await db.get(Order, UUID(created["id"]))
    order.delivery_eta = utcnow() - timedelta(minutes=1)
    await db.commit()

    assert await process_due_inbounds(utcnow()) == 1
    assert await process_due_inbounds(utcnow()) == 0
    assert await db.scalar(select(func.count()).select_from(FridgeItem)) == 2


async def test_approve_recalculates_server_lines_and_defers_inbound(
    client, db, respx_mock
):
    me, budget_id = await _setup(client, respx_mock)
    cycle = (await client.get("/api/v1/cycle")).json()
    cycle_start = date.fromisoformat(cycle["cycleStart"])
    plan = await _seed_plan(
        db,
        me["id"],
        budget_id,
        [{"ingredients": [{"name": "계란", "quantity": "4", "unit": "ea"}]}],
        start=cycle_start,
    )
    await client.put("/api/v1/stores/connections/kurly", json={"connected": True})
    now = utcnow()
    draft = Order(
        user_id=UUID(me["id"]),
        meal_plan_id=plan.id,
        store="kurly",
        status="draft",
        frequency="weekly",
        cycle_start=cycle_start,
        next_suggested_at=now + timedelta(days=7),
        estimated_total=Decimal("999999"),
        currency="KRW",
        simulation=True,
        confirmed_at=None,
        auto_confirm_at=now + timedelta(hours=24),
        auto_confirmed=False,
        delivery_state="pending",
    )
    draft.items = [
        OrderItem(
            name="클라이언트 위조품",
            quantity=Decimal("999"),
            unit="ea",
            line_type="needed",
            matched=True,
        )
    ]
    db.add(draft)
    await db.commit()

    cached = await client.get("/api/v1/orders/preview")
    assert cached.status_code == 200, cached.text
    assert cached.json()["orderId"] == str(draft.id)
    assert cached.json()["status"] == "draft"
    assert cached.json()["needed"][0]["name"] == "클라이언트 위조품"

    refreshed = await client.get("/api/v1/orders/preview?refresh=true")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["orderId"] == str(draft.id)
    assert refreshed.json()["needed"][0]["name"] == "계란"

    approved = await client.post(
        f"/api/v1/orders/{draft.id}/approve", json={"excludeNames": []}
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "confirmed"
    assert body["autoConfirmed"] is False
    assert body["inboundAt"] is None
    assert [line["name"] for line in body["items"]] == ["계란"]
    assert await db.scalar(select(func.count()).select_from(FridgeItem)) == 0

    invalid = await client.post(
        f"/api/v1/orders/{draft.id}/approve", json={"items": []}
    )
    assert invalid.status_code == 422


async def test_approve_excluded_items_recalculates_estimated_total(
    client, db, respx_mock, monkeypatch
):
    me, budget_id = await _setup(client, respx_mock)
    cycle_start = date.fromisoformat((await client.get("/api/v1/cycle")).json()["cycleStart"])
    plan = await _seed_plan(
        db,
        me["id"],
        budget_id,
        [{"ingredients": [{"name": "계란", "quantity": "1", "unit": "ea"}]}],
        start=cycle_start,
    )
    await client.put("/api/v1/stores/connections/kurly", json={"connected": True})
    now = utcnow()
    draft = Order(
        user_id=UUID(me["id"]),
        meal_plan_id=plan.id,
        store="kurly",
        status="draft",
        frequency="weekly",
        cycle_start=cycle_start,
        next_suggested_at=now + timedelta(days=7),
        estimated_total=Decimal("300"),
        currency="KRW",
        simulation=True,
        confirmed_at=None,
        auto_confirm_at=now + timedelta(hours=24),
        auto_confirmed=False,
        delivery_state="pending",
    )
    draft.items = [
        OrderItem(
            name="기존 초안",
            quantity=Decimal("1"),
            unit="ea",
            line_type="needed",
            matched=False,
        )
    ]
    db.add(draft)
    await db.commit()

    preview = OrderPreviewResponse(
        meal_plan_id=plan.id,
        store_connected=True,
        country="KR",
        needed=[
            ShortfallPreviewLine(
                name="계란", unit="ea", needed="1", from_fridge="0", to_buy="1"
            ),
            ShortfallPreviewLine(
                name="양파", unit="ea", needed="1", from_fridge="0", to_buy="1"
            ),
        ],
        covered=[],
        cart=StoreCartResponse(
            items=[
                CartProduct(
                    ingredient="계란",
                    matched=True,
                    price=MoneyOut(amount=Decimal("100"), currency="KRW"),
                ),
                CartProduct(
                    ingredient="양파",
                    matched=True,
                    price=MoneyOut(amount=Decimal("200"), currency="KRW"),
                ),
            ],
            total=MoneyOut(amount=Decimal("300"), currency="KRW"),
            matched_count=2,
        ),
        estimated_total=MoneyOut(amount=Decimal("300"), currency="KRW"),
        cycle_start=cycle_start,
    )

    async def fixed_preview(*_args, **_kwargs):
        return preview

    monkeypatch.setattr(order_service, "_build_preview", fixed_preview)
    approved = await client.post(
        f"/api/v1/orders/{draft.id}/approve", json={"excludeNames": ["양파"]}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["estimatedTotal"]["amount"] == "100.00"
    assert [item["name"] for item in approved.json()["items"]] == ["계란"]


async def test_second_manual_confirmation_in_same_cycle_is_rejected(
    client, db, respx_mock
):
    _me, first = await _confirmed_order(client, db, respx_mock)
    second = await client.post("/api/v1/orders", json={"store": "kurly"})
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "ORDER_ALREADY_CONFIRMED"
    assert await db.scalar(
        select(func.count()).select_from(Order).where(Order.status == "confirmed")
    ) == 1


async def test_cancel_window_and_cross_user_ownership_are_enforced(
    client, db, respx_mock
):
    from tests.conftest import login

    _me, created = await _confirmed_order(client, db, respx_mock)
    order = await db.get(Order, UUID(created["id"]))
    order.cycle_start = utcnow().date() - timedelta(days=8)
    await db.commit()
    closed = await client.post(f"/api/v1/orders/{order.id}/cancel")
    assert closed.status_code == 409
    assert closed.json()["detail"]["code"] == "ORDER_CANCEL_WINDOW_CLOSED"

    await login(
        client,
        respx_mock,
        provider_user_id="another-user",
        email="another@example.com",
    )
    forbidden = await client.post(
        f"/api/v1/orders/{order.id}/delivery", json={"received": True}
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"]["code"] == "FORBIDDEN"
