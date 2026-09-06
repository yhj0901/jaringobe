"""배송 추정 유통기한 → 임박 재료 되먹임 회귀 검증."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select

from app.domains.fridge.models import FridgeItem
from app.domains.fridge.shelf_life import estimate_expires_at
from app.domains.mealplan.fridge_hint import build_fridge_hint
from app.domains.order import service as order_service
from app.domains.order.models import Order
from tests.test_orders import _seed_plan, _setup


@pytest.mark.parametrize(
    "name,days",
    [
        ("닭고기", 2),
        ("시금치", 3),
        ("두부", 3),
        ("우유", 5),
        ("양파", 14),
        ("계란", 21),
        ("간장", 180),
        ("소금", 365),
        ("  MILK  ", 5),
        ("  ground   beef ", 2),
        ("미등록 재료", 3),
        ("소금빵", 3),
    ],
)
def test_estimated_shelf_life_by_exact_name(name, days):
    received = date(2026, 12, 31)
    assert estimate_expires_at(name, received) == received + timedelta(days=days)


@pytest.mark.parametrize("via_scheduler", [False, True])
async def test_confirm_delivery_dates_feed_expiring_hint(
    client, db, respx_mock, monkeypatch, via_scheduler
):
    from app.core.ratelimit import order_confirm_user_limiter, order_preview_user_limiter
    from app.domains.cycle.scheduler import process_due_inbounds

    order_confirm_user_limiter.reset()
    order_preview_user_limiter.reset()
    me, budget_id = await _setup(client, respx_mock)
    await _seed_plan(
        db,
        me["id"],
        budget_id,
        [
            {
                "ingredients": [
                    {"name": name, "quantity": "100", "unit": "g"}
                    for name in ("두부", "시금치", "닭고기", "소금", "미등록 재료")
                ]
            }
        ],
    )
    await client.put("/api/v1/stores/connections/kurly", json={"connected": True})
    confirmed = await client.post("/api/v1/orders", json={"store": "kurly"})
    assert confirmed.status_code == 201, confirmed.text
    order_id = UUID(confirmed.json()["id"])
    assert not (await db.scalars(select(FridgeItem))).all()
    now = datetime(2026, 9, 6, 23, 30, tzinfo=UTC)
    monkeypatch.setattr(order_service, "utcnow", lambda: now)
    if via_scheduler:
        order = await db.get(Order, order_id)
        order.delivery_eta = now - timedelta(minutes=1)
        await db.commit()
        assert await process_due_inbounds(now) == 1
        assert await process_due_inbounds(now + timedelta(days=1)) == 0
    else:
        for _ in range(2):
            delivered = await client.post(
                f"/api/v1/orders/{order_id}/delivery", json={"received": True}
            )
            assert delivered.status_code == 200, delivered.text
    rows = (await db.scalars(select(FridgeItem))).all()
    assert len(rows) == 5
    dates = {row.name: row.expires_at for row in rows}
    assert dates == {
        "두부": date(2026, 9, 9),
        "시금치": date(2026, 9, 9),
        "닭고기": date(2026, 9, 8),
        "소금": date(2027, 9, 6),
        "미등록 재료": date(2026, 9, 9),
    }
    assert all(row.source == "delivery" and row.order_id == order_id for row in rows)
    hint = await build_fridge_hint(db, UUID(me["id"]), "KR", today=now.date())
    expiring = hint.split("Use these FIRST (expiring soon):")[1].split("RULES:")[0]
    assert "두부 100 g (expires 2026-09-09)" in expiring
    assert "닭고기 100 g (expires 2026-09-08)" in expiring
    assert "소금" not in expiring
