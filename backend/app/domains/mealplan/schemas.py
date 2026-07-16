"""mealplan 도메인 Pydantic 스키마 (camelCase, CamelModel).

금액은 budget 도메인의 MoneyOut 재사용(amount 문자열, float 금지).
"""

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, field_serializer

from app.core.schema import CamelModel, serialize_utc
from app.domains.budget.schemas import MoneyOut
from app.domains.fridge.schemas import ShortfallLine
from app.domains.store.schemas import StoreCartResponse

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


Difficulty = Literal["easy", "normal", "hard"]

# 번호 접두("1." "2)" 등) 또는 줄바꿈 기준 단계 분리
_STEP_SPLIT = re.compile(r"(?:\r?\n)+|(?<!\d)\d+[.)]\s*")


def parse_steps(recipe_steps: str | None) -> list[str]:
    """recipe_steps(Text) → 조리 단계 배열.

    줄바꿈 또는 "1." "2)" 형태의 번호를 기준으로 분리하고 빈 항목은 제거한다.
    """
    if not recipe_steps:
        return []
    parts = _STEP_SPLIT.split(recipe_steps)
    return [s.strip() for s in parts if s and s.strip()]


class MealCompletionRequest(CamelModel):
    completed: bool


class MealOut(CamelModel):
    id: uuid.UUID
    plan_date: date
    meal_type: str
    recipe_name: str
    ingredients: list[MealIngredientOut]
    # v1.4 확장 (하위 호환 옵셔널)
    steps: list[str] = Field(default_factory=list)
    completed_at: datetime | None = None
    time_minutes: int | None = None
    difficulty: Difficulty | None = None

    @field_serializer("completed_at")
    def _ser_completed_at(self, v: datetime | None) -> str | None:
        return serialize_utc(v) if v is not None else None


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
    # v1.5: processing/failed 상태에서는 period/budgetSummary null + meals [] (api-spec §3-2)
    period_start: date | None = None
    period_end: date | None = None
    budget_summary: BudgetSummary | None = None
    meals: list[MealOut] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class MealPlanAcceptedResponse(CamelModel):
    """202 Accepted — 생성/재생성 비동기 접수 (api-spec §3-2 v1.5)."""

    id: uuid.UUID
    status: Literal["processing"] = "processing"


# 내부 전달용(직렬화 아님)
def money(amount: Decimal, currency: str) -> MoneyOut:
    return MoneyOut(amount=amount, currency=currency)


# ---------- 원스톱: 식단 → 냉장고 감산 → 컬리 장바구니 ----------
class MealPlanCartRequest(CamelModel):
    mall: Literal["kurly", "all"] = "kurly"
    max_pages: int = Field(default=5, ge=1, le=10)


class MealPlanCartResponse(CamelModel):
    meal_plan_id: uuid.UUID
    needed: list[ShortfallLine]   # 식단 재료 − 냉장고 재고 = 필요 품목
    cart: StoreCartResponse       # 필요 품목의 마트(컬리) 장바구니


# ---------- 월 예산 → 한 달 식단 + 첫 주기 주문 ----------
class MonthlyPlanRequest(CamelModel):
    cycle: Literal["weekly", "biweekly"] = "weekly"
    meals_per_day: int = Field(default=3, ge=1, le=5)
    as_of: date | None = None   # 기본: 서버 오늘 (예산 입력일)
    mall: Literal["kurly", "all"] = "kurly"
    max_pages: int = Field(default=5, ge=1, le=10)


class FirstCycleOrder(CamelModel):
    period_start: date
    period_end: date
    days: int
    needed: list[ShortfallLine]   # 첫 주기 식단 − 냉장고 = 주문할 목록
    cart: StoreCartResponse       # 첫 주기 컬리 장바구니(주문)


class MonthlyPlanResponse(CamelModel):
    meal_plan_id: uuid.UUID
    status: str
    period_start: date
    period_end: date
    days: int
    monthly_budget: MoneyOut      # 입력한 월 예산
    prorated_budget: MoneyOut     # 남은 일자 비율만큼(오늘 포함)
    prorate_ratio: str            # 예: "22/31"
    planned_cost: MoneyOut        # 한 달 식단 예상 비용(기준가)
    within_budget: bool
    first_order: FirstCycleOrder
