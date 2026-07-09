"""fridge 도메인 테스트 — 재고 CRUD + 장보기 감산(shortfall) + 식사완료 차감(deduct)."""

from datetime import date, timedelta

from tests.conftest import login


async def test_add_and_list(client, respx_mock):
    await login(client, respx_mock)
    res = await client.post("/api/v1/fridge/items", json={"items": [
        {"name": "두부", "quantity": "2", "unit": "ea", "expiresAt": "2026-07-20"},
        {"name": "쌀", "quantity": "1000", "unit": "g"},
    ]})
    assert res.status_code == 201
    assert len(res.json()) == 2

    lst = await client.get("/api/v1/fridge")
    assert lst.status_code == 200
    assert {i["name"] for i in lst.json()} == {"두부", "쌀"}


async def test_shortfall_subtracts_stock(client, respx_mock):
    await login(client, respx_mock)
    await client.post("/api/v1/fridge/items", json={"items": [
        {"name": "두부", "quantity": "2", "unit": "ea"},
    ]})
    res = await client.post("/api/v1/fridge/shortfall", json={"items": [
        {"name": "두부", "quantity": "3", "unit": "ea"},   # 재고 2 → 1만 사면 됨
        {"name": "쌀", "quantity": "500", "unit": "g"},     # 재고 없음 → 500 전량
    ]})
    assert res.status_code == 200
    by = {i["name"]: i for i in res.json()["items"]}
    assert by["두부"]["fromFridge"] == "2" and by["두부"]["toBuy"] == "1"
    assert by["쌀"]["fromFridge"] == "0" and by["쌀"]["toBuy"] == "500"


async def test_deduct_fifo_by_expiry(client, respx_mock):
    await login(client, respx_mock)
    await client.post("/api/v1/fridge/items", json={"items": [
        {"name": "두부", "quantity": "2", "unit": "ea", "expiresAt": "2026-07-10"},  # 임박
        {"name": "두부", "quantity": "3", "unit": "ea", "expiresAt": "2026-07-30"},
    ]})
    res = await client.post("/api/v1/fridge/deduct", json={"items": [
        {"name": "두부", "quantity": "3", "unit": "ea"},
    ]})
    assert res.status_code == 200
    assert res.json()["items"][0]["deducted"] == "3"
    # 임박 2 소진 + 나중 3에서 1 → 총 2 남음
    items = (await client.get("/api/v1/fridge")).json()
    total = sum(float(i["quantity"]) for i in items if i["name"] == "두부")
    assert total == 2.0


async def test_deduct_insufficient_removes_item(client, respx_mock):
    await login(client, respx_mock)
    await client.post("/api/v1/fridge/items", json={"items": [
        {"name": "계란", "quantity": "1", "unit": "ea"},
    ]})
    res = await client.post("/api/v1/fridge/deduct", json={"items": [
        {"name": "계란", "quantity": "5", "unit": "ea"},
    ]})
    assert res.json()["items"][0]["deducted"] == "1"  # 있는 만큼만
    items = (await client.get("/api/v1/fridge")).json()
    assert not [i for i in items if i["name"] == "계란"]  # 0 → 삭제


async def test_expiring(client, respx_mock):
    await login(client, respx_mock)
    soon = (date.today() + timedelta(days=1)).isoformat()
    far = (date.today() + timedelta(days=30)).isoformat()
    await client.post("/api/v1/fridge/items", json={"items": [
        {"name": "우유", "quantity": "1", "unit": "ea", "expiresAt": soon},
        {"name": "쌀", "quantity": "1", "unit": "kg", "expiresAt": far},
    ]})
    res = await client.get("/api/v1/fridge/expiring", params={"days": 3})
    names = [i["name"] for i in res.json()]
    assert "우유" in names and "쌀" not in names


async def test_requires_auth(client):
    res = await client.get("/api/v1/fridge")
    assert res.status_code == 401


async def test_update_and_delete(client, respx_mock):
    await login(client, respx_mock)
    created = (await client.post("/api/v1/fridge/items", json={"items": [
        {"name": "양파", "quantity": "3", "unit": "ea"},
    ]})).json()
    item_id = created[0]["id"]

    upd = await client.patch(f"/api/v1/fridge/items/{item_id}", json={"quantity": "1"})
    assert upd.status_code == 200 and upd.json()["quantity"] == "1"

    dele = await client.delete(f"/api/v1/fridge/items/{item_id}")
    assert dele.status_code == 204
    assert (await client.get("/api/v1/fridge")).json() == []


async def test_item_not_found(client, respx_mock):
    await login(client, respx_mock)
    res = await client.delete("/api/v1/fridge/items/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404
