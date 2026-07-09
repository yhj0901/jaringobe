from tests.conftest import make_budget, make_household


async def test_household_and_budget_flow(client):
    hid = await make_household(client)
    resp = await make_budget(client, hid)
    assert resp.status_code == 201
    assert resp.json()["amount"] == "500000.00"
    assert resp.json()["currency"] == "KRW"

    current = await client.get(
        "/api/v1/budgets/current", headers={"X-Household-Id": str(hid)}
    )
    assert current.status_code == 200
    assert current.json()["household_id"] == hid


async def test_budget_requires_auth(client):
    resp = await client.get("/api/v1/budgets/current")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHORIZED"


async def test_budget_not_set(client):
    hid = await make_household(client)
    resp = await client.get(
        "/api/v1/budgets/current", headers={"X-Household-Id": str(hid)}
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "BUDGET_NOT_SET"


async def test_budget_negative_amount_rejected(client):
    hid = await make_household(client)
    resp = await client.post(
        "/api/v1/budgets",
        headers={"X-Household-Id": str(hid)},
        json={
            "amount": "-1",
            "currency": "KRW",
            "period_start": "2026-07-01T00:00:00Z",
            "period_end": "2026-07-31T23:59:59Z",
        },
    )
    assert resp.status_code == 422


async def test_budget_bad_period_rejected(client):
    hid = await make_household(client)
    resp = await client.post(
        "/api/v1/budgets",
        headers={"X-Household-Id": str(hid)},
        json={
            "amount": "1000",
            "currency": "KRW",
            "period_start": "2026-07-31T00:00:00Z",
            "period_end": "2026-07-01T00:00:00Z",
        },
    )
    assert resp.status_code == 422


async def test_household_not_found(client):
    resp = await client.get(
        "/api/v1/budgets/current", headers={"X-Household-Id": "99999"}
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "HOUSEHOLD_REQUIRED"
