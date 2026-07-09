"""budget 도메인 Pydantic 스키마 — api-spec.md §2 + §5(v1.2 확장).

서버측 전량 재검증 (CWE-20/602 — 클라이언트 값 불신):
- householdSize 1~10 정수
- currency KRW|USD, 금액 KRW 50,000~5,000,000 / USD 50~5,000 (Decimal, 소수 2자리 이내)
- mealDirection / source 열거값
- locked boolean, cuisines 열거값 0~6개·중복 금지 (v1.2)
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_serializer, field_validator, model_validator

from app.core.schema import CamelModel, serialize_utc

AMOUNT_RANGE: dict[str, tuple[Decimal, Decimal]] = {
    "KRW": (Decimal("50000"), Decimal("5000000")),
    "USD": (Decimal("50"), Decimal("5000")),
}


class MoneyIn(CamelModel):
    amount: Decimal
    currency: Literal["KRW", "USD"]

    @field_validator("amount")
    @classmethod
    def validate_decimal_places(cls, v: Decimal) -> Decimal:
        exponent = v.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("amount must have at most 2 decimal places")
        return v

    @model_validator(mode="after")
    def validate_amount_range(self) -> "MoneyIn":
        low, high = AMOUNT_RANGE[self.currency]
        if not (low <= self.amount <= high):
            raise ValueError(f"amount out of range for {self.currency} ({low}~{high})")
        return self


class MoneyOut(CamelModel):
    amount: Decimal
    currency: str

    @field_serializer("amount")
    def serialize_amount(self, v: Decimal) -> str:
        """금액은 문자열(Decimal 직렬화, 소수 2자리) — float 금지."""
        return str(v.quantize(Decimal("0.01")))


class BudgetPlanCreateRequest(CamelModel):
    household_size: int = Field(ge=1, le=10)
    budget: MoneyIn
    meal_direction: Literal["health", "diet", "hearty", "kids"]
    source: Literal["guest", "onboarding"]


Cuisine = Literal["korean", "western", "japanese", "chinese", "comfort", "salad"]


class BudgetPlanUpsertRequest(CamelModel):
    """PUT /budget/plans (v1.2) — 온보딩·수정용 upsert. POST 검증 + locked/cuisines 확장."""

    household_size: int = Field(ge=1, le=10)
    budget: MoneyIn
    meal_direction: Literal["health", "diet", "hearty", "kids"]
    locked: bool = True
    cuisines: list[Cuisine] = Field(default_factory=list, max_length=6)

    @field_validator("cuisines")
    @classmethod
    def validate_no_duplicates(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("cuisines must not contain duplicates")
        return v


class BudgetPlanResponse(CamelModel):
    id: uuid.UUID
    household_size: int
    budget: MoneyOut
    meal_direction: str
    source: str
    locked: bool
    cuisines: list[str]
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return serialize_utc(v)
