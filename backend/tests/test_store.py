"""store 도메인 테스트 — 네이버 검색 respx mock + LLM 미설정(최저가 폴백).

category1='식품' + mallName='컬리' 필터, 최저가 선택 검증.
"""

import httpx
import pytest

from app.core.config import get_settings
from tests.conftest import login

NAVER_HOST = "openapi.naver.com"
NAVER_PATH = "/v1/search/shop.json"


def _prod(pid, title, price, mall="컬리N마트", cat1="식품"):
    return {
        "productId": str(pid), "title": title, "lprice": str(price),
        "mallName": mall, "category1": cat1, "link": f"http://shop/{pid}",
    }


CATALOG = {
    "두부": [
        _prod(1, "연두부 300g", 1200),
        _prod(2, "부침두부 380g", 1500),
        _prod(3, "실리콘 두부틀", 5000, cat1="생활/건강"),   # 비식품 → 제외
        _prod(4, "손두부 두모", 900, mall="쿠팡"),           # 비컬리 → 제외
    ],
    "쌀": [_prod(10, "유기농 쌀 4kg", 18990), _prod(11, "백미 2kg", 8990)],
}


@pytest.fixture(autouse=True)
def _store_env(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "test-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test-secret")
    get_settings.cache_clear()
    from app.core.ratelimit import store_user_limiter
    store_user_limiter.reset()
    yield
    get_settings.cache_clear()
    store_user_limiter.reset()


def _naver_side_effect(request):
    q = request.url.params.get("query", "")
    start = int(request.url.params.get("start", "1"))
    items = CATALOG.get(q, []) if start == 1 else []  # 1페이지만(<100 → 중단)
    return httpx.Response(200, json={"items": items})


async def test_store_cart_filters_and_picks_cheapest(client, respx_mock):
    respx_mock.get(host=NAVER_HOST, path=NAVER_PATH).mock(side_effect=_naver_side_effect)
    await login(client, respx_mock)

    res = await client.post("/api/v1/store/cart", json={
        "items": [{"name": "두부"}, {"name": "쌀"}, {"name": "고사리"}],
        "mall": "kurly", "maxPages": 2,
    })
    assert res.status_code == 200, res.text
    body = res.json()
    by = {i["ingredient"]: i for i in body["items"]}

    # 두부: 식품+컬리 2건만(두부틀·쿠팡 제외), 최저가 연두부 1200
    assert by["두부"]["matched"] is True
    assert by["두부"]["candidateCount"] == 2
    assert by["두부"]["price"]["amount"] == "1200"
    assert by["두부"]["mallName"] == "컬리N마트"
    # 쌀: 최저가 8990
    assert by["쌀"]["price"]["amount"] == "8990"
    # 고사리: 후보 없음
    assert by["고사리"]["matched"] is False
    assert by["고사리"]["candidateCount"] == 0

    assert body["matchedCount"] == 2
    assert body["total"]["currency"] == "KRW"
    assert body["total"]["amount"] == "10190"  # 1200 + 8990


async def test_store_cart_requires_auth(client):
    res = await client.post("/api/v1/store/cart", json={"items": [{"name": "두부"}]})
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "AUTH_REQUIRED"
