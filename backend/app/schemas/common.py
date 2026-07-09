from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, field_serializer

Currency = Literal["KRW", "USD"]


class Money(BaseModel):
    """금액 표현. amount는 Decimal, JSON 직렬화 시 문자열(정밀도 보존). float 금지."""

    amount: Decimal
    currency: Currency

    @field_serializer("amount")
    def _ser_amount(self, v: Decimal) -> str:
        return str(v)
