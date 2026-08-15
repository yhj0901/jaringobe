"""order 도메인 Pydantic 스키마 — api-spec.md §7 (camelCase).

POST body 는 store 만. items 등 extra 필드는 extra='forbid' 로 422 VALIDATION_ERROR (CWE-602).
status/frequency/lineType/simulation 은 서버가 부여 — 클라이언트가 설정할 수 없다.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field, field_serializer
from pydantic.alias_generators import to_camel

from app.core.schema import CamelModel, serialize_utc
from app.domains.budget.schemas import MoneyOut
from app.domains.store.schemas import StoreCartResponse

StoreName = Literal["kurly", "coupang", "ssg", "naver", "walmart", "instacart"]
LineType = Literal["needed", "covered"]


class OrderCreateRequest(CamelModel):
    """POST /orders — 라인·가격·matched 를 받지 않음 (CWE-602). extra 필드는 거부."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )

    store: StoreName


class ShortfallPreviewLine(CamelModel):
    name: str
    unit: str
    needed: str
    from_fridge: str
    to_buy: str


class OrderPreviewResponse(CamelModel):
    meal_plan_id: uuid.UUID
    store_connected: bool
    country: str
    needed: list[ShortfallPreviewLine]
    covered: list[ShortfallPreviewLine]
    cart: StoreCartResponse
    estimated_total: MoneyOut
    notes: list[str] = Field(default_factory=list)


class OrderItemOut(CamelModel):
    name: str
    quantity: str
    unit: str
    line_type: LineType
    matched: bool
    title: str | None = None
    unit_price: MoneyOut | None = None


class OrderResponse(CamelModel):
    id: uuid.UUID
    store: str
    status: str
    frequency: str
    next_suggested_at: datetime
    estimated_total: MoneyOut
    confirmed_at: datetime
    simulation: bool
    items: list[OrderItemOut]

    @field_serializer("next_suggested_at", "confirmed_at")
    def _ser_dt(self, v: datetime) -> str:
        return serialize_utc(v)
