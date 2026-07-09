from tests.conftest import make_budget, make_household


async def _setup(client, amount="500000.00"):
    hid = await make_household(client)
    await make_budget(client, hid, amount=amount)
    return hid


async def test_create_and_get_mealplan(client):
    hid = await _setup(client)
    resp = await client.post(
        "/api/v1/mealplans",
        headers={"X-Household-Id": str(hid)},
        json={"days": 2, "meals_per_day": 3},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "ready"
    assert body["budget_summary"]["within_budget"] is True
    assert len(body["meals"]) == 6
    # 금액은 문자열(Decimal) + 통화
    assert body["budget_summary"]["budget"]["currency"] == "KRW"
    assert isinstance(body["budget_summary"]["planned_cost"]["amount"], str)

    pid = body["id"]
    got = await client.get(
        f"/api/v1/mealplans/{pid}", headers={"X-Household-Id": str(hid)}
    )
    assert got.status_code == 200
    assert got.json()["id"] == pid


async def test_mealplan_requires_budget(client):
    hid = await make_household(client)
    resp = await client.post(
        "/api/v1/mealplans",
        headers={"X-Household-Id": str(hid)},
        json={"days": 1, "meals_per_day": 1},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "BUDGET_NOT_SET"


async def test_mealplan_ownership_forbidden(client):
    hid = await _setup(client)
    pid = (
        await client.post(
            "/api/v1/mealplans",
            headers={"X-Household-Id": str(hid)},
            json={"days": 1, "meals_per_day": 2},
        )
    ).json()["id"]

    other = await make_household(client, region="US", allergies=[])
    resp = await client.get(
        f"/api/v1/mealplans/{pid}", headers={"X-Household-Id": str(other)}
    )
    assert resp.status_code == 403


async def test_mealplan_over_budget_transparent(client):
    hid = await _setup(client, amount="1000")  # 빠듯한 예산
    resp = await client.post(
        "/api/v1/mealplans",
        headers={"X-Household-Id": str(hid)},
        json={"days": 3, "meals_per_day": 3},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "over_budget"
    assert body["budget_summary"]["within_budget"] is False
    assert body["notes"]  # 초과 안내 노출 (조용히 자르지 않음)


async def test_mealplan_regenerate_all(client):
    hid = await _setup(client)
    pid = (
        await client.post(
            "/api/v1/mealplans",
            headers={"X-Household-Id": str(hid)},
            json={"days": 2, "meals_per_day": 2},
        )
    ).json()["id"]
    resp = await client.post(
        f"/api/v1/mealplans/{pid}/regenerate",
        headers={"X-Household-Id": str(hid)},
        json={"scope": "all"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == pid


async def test_mealplan_not_found(client):
    hid = await _setup(client)
    resp = await client.get(
        "/api/v1/mealplans/99999", headers={"X-Household-Id": str(hid)}
    )
    assert resp.status_code == 404
