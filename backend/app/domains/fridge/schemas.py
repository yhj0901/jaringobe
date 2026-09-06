"""fridge 도메인 Pydantic 스키마 (camelCase)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_serializer

from app.core.schema import CamelModel, serialize_utc
from datetime import datetime


class FridgeItemCreate(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: Decimal = Field(gt=0)
    unit: str = Field(default="ea", max_length=16)
    expires_at: date | None = None
    source: Literal["manual", "delivery", "mealplan"] = "manual"


class FridgeItemsCreate(CamelModel):
    """단건/복수 추가 (배송 자동등록 포함)."""
    items: list[FridgeItemCreate] = Field(min_length=1, max_length=100)


class FridgeItemUpdate(CamelModel):
    quantity: Decimal = Field(gt=0)


class FridgeItemRead(CamelModel):
    id: uuid.UUID
    name: str
    quantity: str
    unit: str
    expires_at: date | None = None
    source: str
    created_at: datetime

    @field_serializer("created_at")
    def _ser_created(self, v: datetime) -> str:
        return serialize_utc(v)


# ---------- 감산/차감 ----------
class NeededItem(CamelModel):
    name: str
    quantity: Decimal = Field(gt=0)
    unit: str = "ea"


class NeedsRequest(CamelModel):
    items: list[NeededItem] = Field(min_length=1, max_length=100)


class ShortfallLine(CamelModel):
    name: str
    unit: str
    needed: str        # 식단 필요량
    from_fridge: str   # 냉장고에서 충당
    to_buy: str        # 실제 장볼 양 (= needed - from_fridge)


class ShortfallResponse(CamelModel):
    """식단 − 재고 = 필요 품목 (재고 불변, 계산만)."""
    items: list[ShortfallLine]


class DeductLine(CamelModel):
    name: str
    unit: str
    requested: str
    deducted: str      # 실제 차감된 양 (재고 부족 시 requested보다 적을 수 있음)


class DeductResponse(CamelModel):
    """식사 완료 시 재고 실제 차감 결과."""
    items: list[DeductLine]
