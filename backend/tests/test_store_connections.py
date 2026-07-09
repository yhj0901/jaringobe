"""GET/PUT /api/v1/stores/connections — 초기 상태/연동/해제/404/401/upsert 반복 테스트."""

import pytest
from sqlalchemy import select

from app.domains.store.connection_models import StoreConnection
from tests.conftest import login

ALL_STORES = ["kurly", "coupang", "ssg", "naver"]


class TestGetConnections:
    async def test_initial_all_disconnected(self, client, respx_mock):
        """미저장 상태 — KR 4종 전체 disconnected / connectedAt null."""
        await login(client, respx_mock)
        res = await client.get("/api/v1/stores/connections")
        assert res.status_code == 200, res.text
        body = res.json()
        assert [c["store"] for c in body["connections"]] == ALL_STORES
        for conn in body["connections"]:
            assert conn["status"] == "disconnected"
            assert conn["connectedAt"] is None

    async def test_unauthenticated_401(self, client):
        res = await client.get("/api/v1/stores/connections")
        assert res.status_code == 401
        assert res.json()["detail"]["code"] == "AUTH_REQUIRED"


class TestPutConnection:
    async def test_connect_then_get_reflects(self, client, db, respx_mock):
        """PUT connected=true → 200 갱신 상태, GET 에 반영."""
        await login(client, respx_mock)
        res = await client.put("/api/v1/stores/connections/kurly", json={"connected": True})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["store"] == "kurly"
        assert body["status"] == "connected"
        assert body["connectedAt"] is not None
        assert body["connectedAt"].endswith("Z")

        listed = (await client.get("/api/v1/stores/connections")).json()["connections"]
        by_store = {c["store"]: c for c in listed}
        assert by_store["kurly"]["status"] == "connected"
        assert by_store["kurly"]["connectedAt"] == body["connectedAt"]
        for other in ("coupang", "ssg", "naver"):
            assert by_store[other]["status"] == "disconnected"

        rows = (await db.scalars(select(StoreConnection))).all()
        assert len(rows) == 1
        assert (rows[0].store, rows[0].status) == ("kurly", "connected")
        assert rows[0].connected_at is not None

    async def test_disconnect(self, client, db, respx_mock):
        """연동 후 PUT connected=false → disconnected / connectedAt null."""
        await login(client, respx_mock)
        await client.put("/api/v1/stores/connections/naver", json={"connected": True})
        res = await client.put("/api/v1/stores/connections/naver", json={"connected": False})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body == {"store": "naver", "status": "disconnected", "connectedAt": None}

        row = (await db.scalars(select(StoreConnection))).one()
        assert row.status == "disconnected"
        assert row.connected_at is None

    async def test_disconnect_without_prior_row_creates_disconnected(self, client, db, respx_mock):
        """미저장 스토어에 connected=false — disconnected 행 upsert."""
        await login(client, respx_mock)
        res = await client.put("/api/v1/stores/connections/ssg", json={"connected": False})
        assert res.status_code == 200
        assert res.json() == {"store": "ssg", "status": "disconnected", "connectedAt": None}

        row = (await db.scalars(select(StoreConnection))).one()
        assert (row.store, row.status, row.connected_at) == ("ssg", "disconnected", None)

    async def test_repeated_upsert_keeps_single_row(self, client, db, respx_mock):
        """같은 스토어 반복 PUT — 행 1개 유지 (uq user_id+store)."""
        await login(client, respx_mock)
        for connected in (True, False, True, True):
            res = await client.put(
                "/api/v1/stores/connections/coupang", json={"connected": connected}
            )
            assert res.status_code == 200, res.text

        rows = (await db.scalars(select(StoreConnection))).all()
        assert len(rows) == 1
        assert rows[0].status == "connected"
        assert rows[0].connected_at is not None

    @pytest.mark.parametrize("store", ["emart", "walmart", "KURLY", "kurly2", " "])
    async def test_unsupported_store_404(self, client, respx_mock, store):
        await login(client, respx_mock)
        res = await client.put(f"/api/v1/stores/connections/{store}", json={"connected": True})
        assert res.status_code == 404, res.text
        assert res.json()["detail"]["code"] == "STORE_NOT_SUPPORTED"

    async def test_invalid_body_422(self, client, respx_mock):
        await login(client, respx_mock)
        res = await client.put("/api/v1/stores/connections/kurly", json={})
        assert res.status_code == 422
        assert res.json()["detail"]["code"] == "VALIDATION_ERROR"

    async def test_unauthenticated_401(self, client):
        res = await client.put("/api/v1/stores/connections/kurly", json={"connected": True})
        assert res.status_code == 401
        assert res.json()["detail"]["code"] == "AUTH_REQUIRED"

    async def test_user_scoped_isolation(self, client, respx_mock):
        """유저 A 의 연동 상태가 유저 B 조회에 노출되지 않음 (CWE-639)."""
        await login(client, respx_mock, provider_user_id="kakao-A", email="a@example.com")
        await client.put("/api/v1/stores/connections/kurly", json={"connected": True})

        client.cookies.clear()
        await login(client, respx_mock, provider_user_id="kakao-B", email="b@example.com")
        listed = (await client.get("/api/v1/stores/connections")).json()["connections"]
        assert all(c["status"] == "disconnected" for c in listed)
