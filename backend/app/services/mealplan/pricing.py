"""④ 재료 가격 — PriceProvider 인터페이스.

v1: DB 기준가 테이블(ingredient_price_ref) 조회. 미존재 재료는 결정적 근사 단가.
후속: store 어댑터(실시간 마트가)로 교체 가능.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price import IngredientPriceRef

_CENT = Decimal("0.01")


def _stable_int(seed: str, lo: int, hi: int) -> int:
    h = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)
    return lo + (h % (hi - lo + 1))


class PriceProvider(ABC):
    @abstractmethod
    async def estimate_cost(
        self, name: str, quantity: Decimal, unit: str, region: str, currency: str
    ) -> Decimal:
        """해당 재료·수량의 추정 비용(currency 기준)."""


class DBPriceProvider(PriceProvider):
    """ingredient_price_ref 조회 + 미존재 시 결정적 근사."""

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
            cost = row.unit_price * (quantity / row.pack_qty)
            return cost.quantize(_CENT, rounding=ROUND_HALF_UP)
        # 미시드 재료: 통화별 결정적 근사 단가 (v1 근사 — 수량 비반영)
        if currency == "KRW":
            base = _stable_int(name, 1500, 12000)
        else:
            base = _stable_int(name, 2, 15)
        return Decimal(base).quantize(_CENT)
