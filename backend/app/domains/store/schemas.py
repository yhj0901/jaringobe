"""store 도메인 Pydantic 스키마 (camelCase).

마트 장바구니 = 재료 목록 → 네이버 쇼핑 검색 → category1='식품' + 몰 필터 → LLM 선택.
"""

from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.core.schema import CamelModel
from app.domains.budget.schemas import MoneyOut


class NeededItem(CamelModel):
    name: str
    quantity: float | None = None
    unit: str | None = None


class StoreCartRequest(CamelModel):
    items: list[NeededItem] = Field(min_length=1, max_length=40)
    mall: Literal["kurly", "all"] = "kurly"
    # 네이버 순차 페이지네이션 페이지 수(1=100개 … 10=1000개). 깊을수록 커버리지↑ 속도↓
    max_pages: int = Field(default=5, ge=1, le=10)


class CartProduct(CamelModel):
    ingredient: str
    matched: bool = True
    title: str | None = None
    price: MoneyOut | None = None
    mall_name: str | None = None
    link: str | None = None
    candidate_count: int = 0


class StoreCartResponse(CamelModel):
    items: list[CartProduct]
    total: MoneyOut
    matched_count: int
    notes: list[str] = Field(default_factory=list)


def krw(amount: Decimal) -> MoneyOut:
    return MoneyOut(amount=amount, currency="KRW")
