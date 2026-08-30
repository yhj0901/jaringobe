"""cycle 도메인 API 스키마 — api-spec v1.8 §9."""

import uuid
from datetime import date, datetime
from typing import Literal
from zoneinfo import available_timezones

from pydantic import ConfigDict, Field, field_serializer, field_validator
from pydantic.alias_generators import to_camel

from app.core.schema import CamelModel, serialize_utc
from app.domains.budget.schemas import MoneyOut

CycleFrequency = Literal["weekly", "biweekly"]
CycleStage = Literal[
    "idle",
    "generating",
    "generated",
    "generate_failed",
    "drafted",
    "awaiting_user",
    "confirmed",
    "delivered",
    "nothing_to_order",
    "skipped_user",
    "skipped_dormant",
    "deferred_quota",
    "paused",
]


class CycleSettingsUpdateRequest(CamelModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )

    enabled: bool | None = None
    frequency: CycleFrequency | None = None
    anchor_weekday: int | None = Field(default=None, ge=0, le=6)
    timezone: str | None = Field(default=None, max_length=40)
    auto_confirm: bool | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is not None and value not in available_timezones():
            raise ValueError("timezone must be a valid IANA timezone")
        return value


class MealPlanSummary(CamelModel):
    id: uuid.UUID
    status: str


class DraftOrderSummary(CamelModel):
    id: uuid.UUID
    status: str
    estimated_total: MoneyOut
    auto_confirm_at: datetime | None = None
    blocked_reason: str | None = None
    delivery_eta: datetime | None = None

    @field_serializer("auto_confirm_at", "delivery_eta")
    def _serialize_optional_datetime(self, value: datetime | None) -> str | None:
        return serialize_utc(value) if value is not None else None


class CycleState(CamelModel):
    enabled: bool
    frequency: CycleFrequency
    anchor_weekday: int
    timezone: str
    auto_confirm: bool
    cycle_start: date
    cycle_days: int
    stage: CycleStage
    next_run_at: datetime | None = None
    skipped_cycle_start: date | None = None
    weekly_limit: MoneyOut | None = None
    meal_plan: MealPlanSummary | None = None
    draft_order: DraftOrderSummary | None = None
    simulation: bool = True

    @field_serializer("next_run_at")
    def _serialize_next_run_at(self, value: datetime | None) -> str | None:
        return serialize_utc(value) if value is not None else None

