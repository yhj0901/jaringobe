"""네이버 쇼핑 검색 API 어댑터.

- API는 일반 검색만 제공(몰 지정 파라미터 없음) → client-side 필터
- 페이지네이션: display=100, start 1→901 (최대 1000). **순차만** (동시요청=429)
- category1=='식품' 으로 비식품(두부틀·용기·요리책) 제거
- 몰 필터: mallName 에 '컬리/kurly' 포함 여부
"""

from __future__ import annotations

import asyncio

import httpx

from app.core.config import get_settings

NAVER_SHOP_URL = "https://openapi.naver.com/v1/search/shop.json"


def is_food(item: dict) -> bool:
    return item.get("category1") == "식품"


def is_kurly(item: dict) -> bool:
    m = item.get("mallName") or ""
    return "컬리" in m or "kurly" in m.lower()


async def search_candidates(query: str, max_pages: int, mall: str) -> list[dict]:
    """순차 페이지네이션으로 후보 수집 후 식품/몰 필터. 키 없거나 오류면 빈 리스트."""
    settings = get_settings()
    if not (settings.naver_client_id and settings.naver_client_secret):
        return []
    headers = {
        "X-Naver-Client-Id": settings.naver_client_id,
        "X-Naver-Client-Secret": settings.naver_client_secret,
    }
    seen: set[str] = set()
    out: list[dict] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for page in range(max_pages):  # 순차 (병렬 금지)
            params = {"query": query, "display": 100, "start": 1 + page * 100, "sort": "sim"}
            try:
                resp = await client.get(NAVER_SHOP_URL, params=params, headers=headers)
            except httpx.HTTPError:
                break
            if resp.status_code == 429:
                await asyncio.sleep(1.0)
                continue
            if resp.status_code != 200:
                break
            items = resp.json().get("items", [])
            for it in items:
                if not is_food(it):
                    continue
                if mall == "kurly" and not is_kurly(it):
                    continue
                pid = str(it.get("productId") or it.get("link"))
                if pid in seen:
                    continue
                seen.add(pid)
                out.append(it)
            if len(items) < 100:  # 결과 끝
                break
    return out
