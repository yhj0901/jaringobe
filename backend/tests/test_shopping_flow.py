"""원스톱 흐름 테스트 — 식단 → 냉장고 감산 → 컬리 장바구니.

mock LLM(식단·선택) + respx 네이버. 냉장고 재고가 장보기에서 빠지는지 검증.
"""

import httpx
import pytest

from app.core.config import get_settings
from tests.conftest import login

NAVER_HOST = "openapi.naver.com"
NAVER_PATH = "/v1/search/shop.json"


def _prod(pid, title, price):
    return {"productId": str(pid), "title": title, "lprice": str(price),
            "mallName": "컬리N마트", "category1": "식품", "link": f"http://s/{pid}"}


# 식단(된장찌개+공깃밥) 재료 중 두부 제외한 것들의 네이버 결과
CATALOG = {
    "된장": [_prod(1, "재래식 된장 500g", 5000)],
    "애호박": [_prod(2, "애호박 1개", 1500)],
    "쌀": [_prod(3, "백미 4kg", 20000)],
}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "t")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "t")
    get_settings.cache_clear()
    from app.core.ratelimit import mealplan_user_limiter, store_user_limiter
    store_user_limiter.reset()
    mealplan_user_limiter.reset()
    yield
    get_settings.cache_clear()
    store_user_limiter.reset()


def _naver(request):
    q = request.url.params.get("query", "")
    start = int(request.url.params.get("start", "1"))
    return httpx.Response(200, json={"items": CATALOG.get(q, []) if start == 1 else []})


async def _budget(client):
    return await client.post("/api/v1/budget/plans", json={
        "householdSize": 4, "budget": {"amount": "500000", "currency": "KRW"},
        "mealDirection": "health", "source": "onboarding",
    })


async def test_shopping_flow_subtracts_fridge(client, respx_mock):
    respx_mock.get(host=NAVER_HOST, path=NAVER_PATH).mock(side_effect=_naver)
    await login(client, respx_mock)
    assert (await _budget(client)).status_code == 201

    # 식단 생성 (mock LLM → 된장찌개: 두부1ea, 된장30g, 애호박1ea, 쌀400g)
    mp = await client.post("/api/v1/mealplans", json={"days": 1, "mealsPerDay": 1})
    assert mp.status_code == 201
    plan_id = mp.json()["id"]

    # 냉장고에 두부 2ea → 두부는 장보기에서 빠져야 함
    await client.post("/api/v1/fridge/items", json={
        "items": [{"name": "두부", "quantity": "2", "unit": "ea"}],
    })

    # 원스톱: 식단 → 감산 → 컬리 장바구니
    res = await client.post(f"/api/v1/mealplans/{plan_id}/cart", json={"mall": "kurly", "maxPages": 2})
    assert res.status_code == 200, res.text
    body = res.json()

    needed = {n["name"]: n for n in body["needed"]}
    assert needed["두부"]["fromFridge"] == "1"   # 재고로 충당
    assert needed["두부"]["toBuy"] == "0"

    cart_names = {i["ingredient"] for i in body["cart"]["items"]}
    assert "두부" not in cart_names               # 냉장고에 있어 안 삼
    assert {"된장", "애호박", "쌀"} <= cart_names   # 나머지는 장보기


async def test_shopping_flow_requires_auth(client):
    res = await client.post(
        "/api/v1/mealplans/00000000-0000-0000-0000-000000000000/cart", json={}
    )
    assert res.status_code == 401
