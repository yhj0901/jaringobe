"""재료 가격 — PriceProvider. v1: DB 기준가(ingredient_price_refs) + 근사. 후속 store 교체."""

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
        base = _stable_int(name, 1500, 12000) if currency == "KRW" else _stable_int(name, 2, 15)
        return Decimal(base).quantize(_CENT)
