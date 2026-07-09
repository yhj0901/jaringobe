"""mealplan 도메인 Pydantic 스키마 (camelCase, CamelModel).

금액은 budget 도메인의 MoneyOut 재사용(amount 문자열, float 금지).
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from app.core.schema import CamelModel
from app.domains.budget.schemas import MoneyOut

# 알레르기/선호 입력 제한 — 항목당 30자, 리스트 최대 10개 (api-spec v1.1 §3-2, security-design 5-1)
PrefItem = Annotated[str, Field(max_length=30)]
PrefList = Annotated[list[PrefItem], Field(max_length=10)]


class MealPlanCreateRequest(CamelModel):
    days: int = Field(default=7, ge=1, le=31)
    meals_per_day: int = Field(default=3, ge=1, le=5)
    # v0: 알레르기/선호는 저장소가 없어 요청으로 받음(LLM 전달 + 코드 재검증). 안전상 알레르기 우선.
    allergies: PrefList = Field(default_factory=list)
    preferences: PrefList = Field(default_factory=list)


class RegenerateRequest(CamelModel):
    scope: Literal["all", "meal"] = "all"
    meal_id: uuid.UUID | None = None
    allergies: PrefList = Field(default_factory=list)
    preferences: PrefList = Field(default_factory=list)


class MealIngredientOut(CamelModel):
    id: uuid.UUID
    name: str
    quantity: str
    unit: str
    est_cost: MoneyOut | None = None


class MealOut(CamelModel):
    id: uuid.UUID
    plan_date: date
    meal_type: str
    recipe_name: str
    ingredients: list[MealIngredientOut]


class BudgetSummary(CamelModel):
    budget: MoneyOut
    planned_cost: MoneyOut
    remaining: MoneyOut
    within_budget: bool


class MealPlanResponse(CamelModel):
    id: uuid.UUID
    status: str
    region: str
    currency: str
    period_start: date
    period_end: date
    budget_summary: BudgetSummary
    meals: list[MealOut]
    notes: list[str] = Field(default_factory=list)


# 내부 전달용(직렬화 아님)
def money(amount: Decimal, currency: str) -> MoneyOut:
    return MoneyOut(amount=amount, currency=currency)
