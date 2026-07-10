"""PUT /api/v1/users/me/region — 지역 전환 + 통화 서버 매핑 (api-spec.md §1-6, security §5-4)."""

import pytest
from sqlalchemy import select

from app.domains.auth.models import User
from tests.conftest import login


class TestUpdateRegion:
    async def test_default_region_is_kr(self, client, respx_mock):
        """가입 직후 기본 지역 KR / 통화 KRW."""
        await login(client, respx_mock)
        me = (await client.get("/api/v1/users/me")).json()
        assert me["country"] == "KR"
        assert me["currency"] == "KRW"

    async def test_switch_to_us_maps_currency(self, client, db, respx_mock):
        """country=US → currency 서버 매핑 USD, 200 UserMe 반영 + DB 영속."""
        await login(client, respx_mock)
        res = await client.put("/api/v1/users/me/region", json={"country": "US"})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["country"] == "US"
        assert body["currency"] == "USD"

        row = (await db.scalars(select(User))).one()
        assert (row.country, row.currency) == ("US", "USD")

    async def test_switch_back_to_kr(self, client, respx_mock):
        """US → KR 재전환 시 currency 도 KRW 로 원복."""
        await login(client, respx_mock)
        await client.put("/api/v1/users/me/region", json={"country": "US"})
        res = await client.put("/api/v1/users/me/region", json={"country": "KR"})
        assert res.status_code == 200, res.text
        assert res.json()["currency"] == "KRW"

    async def test_client_currency_is_ignored(self, client, respx_mock):
        """클라이언트가 currency 를 보내도 무시 — country 로만 매핑 (CWE-20 정합)."""
        await login(client, respx_mock)
        res = await client.put(
            "/api/v1/users/me/region", json={"country": "US", "currency": "KRW"}
        )
        assert res.status_code == 200, res.text
        assert res.json()["currency"] == "USD"

    @pytest.mark.parametrize("country", ["JP", "kr", "us", "", "KOR", 1])
    async def test_invalid_country_422(self, client, respx_mock, country):
        await login(client, respx_mock)
        res = await client.put("/api/v1/users/me/region", json={"country": country})
        assert res.status_code == 422, res.text
        assert res.json()["detail"]["code"] == "VALIDATION_ERROR"

    async def test_missing_body_422(self, client, respx_mock):
        await login(client, respx_mock)
        res = await client.put("/api/v1/users/me/region", json={})
        assert res.status_code == 422
        assert res.json()["detail"]["code"] == "VALIDATION_ERROR"

    async def test_unauthenticated_401(self, client):
        res = await client.put("/api/v1/users/me/region", json={"country": "US"})
        assert res.status_code == 401
        assert res.json()["detail"]["code"] == "AUTH_REQUIRED"

    async def test_no_retroactive_conversion_isolation(self, client, respx_mock):
        """지역 전환은 본인 스코프 — 타 유저 지역에 영향 없음 (CWE-639)."""
        await login(client, respx_mock, provider_user_id="kakao-A", email="a@example.com")
        await client.put("/api/v1/users/me/region", json={"country": "US"})

        client.cookies.clear()
        await login(client, respx_mock, provider_user_id="kakao-B", email="b@example.com")
        me_b = (await client.get("/api/v1/users/me")).json()
        assert me_b["country"] == "KR"
        assert me_b["currency"] == "KRW"
