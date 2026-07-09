"""store 오케스트레이션 — 재료목록 → 네이버 순차조회 → 식품/몰 필터 → LLM 선택 → 장바구니."""

from __future__ import annotations

import re
from decimal import Decimal

from app.core.config import get_settings
from app.domains.store.naver import search_candidates
from app.domains.store.schemas import (
    CartProduct,
    NeededItem,
    StoreCartResponse,
    krw,
)
from app.domains.store.selector import select_products

_TAG = re.compile(r"<.*?>")


async def build_cart(
    items: list[NeededItem], mall: str, max_pages: int
) -> StoreCartResponse:
    notes: list[str] = []
    settings = get_settings()
    if not (settings.naver_client_id and settings.naver_client_secret):
        notes.append("네이버 API 키 미설정 — 검색 결과 없음(.env NAVER_CLIENT_ID/SECRET 필요)")
    if not settings.llm_enabled:
        notes.append("LLM 미설정 — 최저가 폴백으로 선택")

    # 재료별 후보 수집 (재료마다 순차 페이지네이션 — 병렬 금지)
    cand_by_ing: dict[str, list[dict]] = {}
    for it in items:
        cand_by_ing[it.name] = await search_candidates(it.name, max_pages, mall)

    selected = await select_products(cand_by_ing)

    cart: list[CartProduct] = []
    total = Decimal("0")
    matched = 0
    for it in items:
        cands = cand_by_ing.get(it.name, [])
        chosen = selected.get(it.name)
        if not chosen:
            cart.append(CartProduct(ingredient=it.name, matched=False, candidate_count=len(cands)))
            continue
        try:
            price = Decimal(str(chosen.get("lprice") or 0))
        except Exception:
            price = Decimal("0")
        total += price
        matched += 1
        cart.append(CartProduct(
            ingredient=it.name,
            matched=True,
            title=_TAG.sub("", chosen.get("title", "")),
            price=krw(price),
            mall_name=chosen.get("mallName"),
            link=chosen.get("link"),
            candidate_count=len(cands),
        ))

    return StoreCartResponse(items=cart, total=krw(total), matched_count=matched, notes=notes)
