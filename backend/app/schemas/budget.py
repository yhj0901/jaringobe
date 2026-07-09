from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.schemas.common import Currency


class BudgetCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    currency: Currency
    period_start: datetime
    period_end: datetime
    locked: bool = True

    @model_validator(mode="after")
    def _check_period(self) -> "BudgetCreate":
        if self.period_end <= self.period_start:
            raise ValueError("period_end must be after period_start")
        return self


class BudgetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    household_id: int
    amount: Decimal
    currency: str
    period_start: datetime
    period_end: datetime
    locked: bool
    created_at: datetime

    @field_serializer("amount")
    def _ser_amount(self, v: Decimal) -> str:
        return str(v)
