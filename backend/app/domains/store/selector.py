"""후보 상품 중 '실제 장볼 원재료' 선택 — LLM(Claude).

후보 전량을 압축(번호)해 LLM에 전달 → 재료별 index 선택.
키 없으면(mock) 최저가 폴백. 라면·과자·즉석·맛변형·가공반찬은 LLM이 제외.
"""

from __future__ import annotations

import re

from app.domains.mealplan.llm import get_llm

_TAG = re.compile(r"<.*?>")

_SYSTEM = (
    "집밥 원재료 고르기. 각 재료별 후보 상품 중 실제 장볼 원재료 번호 1개를 고른다. "
    "라면·과자·즉석식품·음료/차·맛변형(예: 오이맛고추)·가공반찬(예: 계란지단)은 제외, "
    "신선/원물/기본 식재료 우선. 적합한 게 없으면 -1. 오직 JSON만 출력."
)


def _price(it: dict) -> int:
    try:
        return int(it.get("lprice") or 0)
    except (TypeError, ValueError):
        return 0


def _cheapest(cands: list[dict]) -> dict | None:
    return min(cands, key=_price) if cands else None


async def select_products(cand_by_ing: dict[str, list[dict]]) -> dict[str, dict | None]:
    llm = get_llm()
    if not llm.enabled:
        # mock 폴백: 최저가
        return {ing: _cheapest(cs) for ing, cs in cand_by_ing.items()}

    lines = []
    for ing, cs in cand_by_ing.items():
        opts = "; ".join(
            f"{i}){_TAG.sub('', c.get('title', ''))[:24]}/{_price(c)}" for i, c in enumerate(cs)
        )
        lines.append(f"{ing}: {opts or '(후보 없음)'}")
    user = "\n".join(lines) + '\n출력: {"재료명": 번호(없으면 -1)}'

    try:
        data = await llm.complete_json(_SYSTEM, user, max_tokens=800)
    except Exception:
        return {ing: _cheapest(cs) for ing, cs in cand_by_ing.items()}

    result: dict[str, dict | None] = {}
    for ing, cs in cand_by_ing.items():
        idx = data.get(ing, -1) if isinstance(data, dict) else -1
        result[ing] = cs[idx] if isinstance(idx, int) and 0 <= idx < len(cs) else None
    return result
