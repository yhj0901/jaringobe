"""order 도메인 Pydantic 스키마 — api-spec.md §7 (camelCase).

POST body 는 store 만. items 등 extra 필드는 extra='forbid' 로 422 VALIDATION_ERROR (CWE-602).
status/frequency/lineType/simulation 은 서버가 부여 — 클라이언트가 설정할 수 없다.
"""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import ConfigDict, Field, StrictBool, field_serializer, field_validator
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
    order_id: uuid.UUID | None = None
    status: Literal["draft", "awaiting_user"] | None = None
    auto_confirm_at: datetime | None = None
    blocked_reason: str | None = None
    cycle_start: date

    @field_serializer("auto_confirm_at")
    def _ser_auto_confirm_at(self, value: datetime | None) -> str | None:
        return serialize_utc(value) if value is not None else None


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
    confirmed_at: datetime | None
    simulation: bool
    items: list[OrderItemOut]
    cycle_start: date
    delivery_eta: datetime | None = None
    inbound_at: datetime | None = None
    delivery_state: Literal["pending", "delivered", "unknown"]
    delivery_confirm_attempts: int
    auto_confirmed: bool
    auto_confirm_at: datetime | None = None
    blocked_reason: str | None = None

    @field_serializer(
        "next_suggested_at", "confirmed_at", "delivery_eta", "inbound_at", "auto_confirm_at"
    )
    def _ser_dt(self, value: datetime | None) -> str | None:
        return serialize_utc(value) if value is not None else None


class OrderApproveRequest(CamelModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )

    exclude_names: list[str] | None = Field(default=None, max_length=40)

    @field_validator("exclude_names")
    @classmethod
    def validate_exclude_names(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        for name in value:
            if not 1 <= len(name) <= 200:
                raise ValueError("excludeNames entries must be 1..200 characters")
        return value


class DeliveryUpdateRequest(CamelModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )

    received: StrictBool
