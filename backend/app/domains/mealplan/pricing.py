"""식단 사용량의 추정 원가 — DB 기준가(ingredient_price_refs) + 미등록 재료 근사.

현재 store 검색/장바구니 가격은 이 provider에 연결되지 않는다. 네이버 키가 있어도
식단 원가와 생성 시 예산 판정에는 반영되지 않으며, 키가 없으면 store 검색도 불가하다.
기준가는 실제 포장 구매액/배송비가 아닌 사용량 비용이다. 운영 및 근거: reports/pricing-review.md.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.mealplan.models import IngredientPriceRef

_CENT = Decimal("0.01")


def _stable_int(seed: str, lo: int, hi: int) -> int:
    h = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)
    return lo + (h % (hi - lo + 1))


class PriceProvider(ABC):
    @abstractmethod
    async def estimate_cost(
        self, name: str, quantity: Decimal, unit: str, region: str, currency: str
    ) -> Decimal: ...


class DBPriceProvider(PriceProvider):
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def estimate_cost(
        self, name: str, quantity: Decimal, unit: str, region: str, currency: str
    ) -> Decimal:
        stmt = select(IngredientPriceRef).where(
            IngredientPriceRef.name == name,
            IngredientPriceRef.region == region,
            IngredientPriceRef.unit == unit,
        )
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if row is not None and row.pack_qty and row.pack_qty > 0:
            return (row.unit_price * (quantity / row.pack_qty)).quantize(
                _CENT, rounding=ROUND_HALF_UP
            )
        # 기준가 미등록 재료: 수량 기반 근사 (재료당 고정 난수는 한 끼를 수만원으로 과대 계산)
        krw = currency == "KRW"
        unit_l = unit.lower()
        if unit_l in ("g", "ml"):
            per100 = _stable_int(name, 300, 1200) if krw else _stable_int(name, 30, 120)
            cost = Decimal(per100) * quantity / Decimal(100)
            if not krw:
                cost = cost / Decimal(100)  # cents → dollars
        elif unit_l in ("ea", "개", "pc", "pcs"):
            per = _stable_int(name, 500, 3000) if krw else _stable_int(name, 1, 4)
            cost = Decimal(per) * quantity
        else:
            cost = Decimal(_stable_int(name, 800, 3000)) if krw else Decimal(_stable_int(name, 1, 4))
        cap = Decimal(8000) if krw else Decimal(9)
        floor = Decimal(100) if krw else Decimal("0.2")
        return min(max(cost, floor), cap).quantize(_CENT, rounding=ROUND_HALF_UP)
