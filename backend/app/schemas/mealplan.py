from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Money

DietDirection = Literal["balanced", "diet", "hearty", "kids"]


# ---------- 요청 ----------
class MealPlanCreate(BaseModel):
    days: int = Field(7, ge=1, le=31)
    meals_per_day: int = Field(3, ge=1, le=5)
    diet_direction: DietDirection = "balanced"


class RegenerateRequest(BaseModel):
    scope: Literal["all", "meal"] = "all"
    meal_id: int | None = None


# ---------- 응답 ----------
class MealIngredientRead(BaseModel):
    id: int
    name: str
    quantity: str
    unit: str
    est_cost: Money | None = None


class MealRead(BaseModel):
    id: int
    plan_date: date
    meal_type: str
    recipe_name: str
    ingredients: list[MealIngredientRead]


class BudgetSummary(BaseModel):
    budget: Money
    planned_cost: Money
    remaining: Money
    within_budget: bool


class MealPlanRead(BaseModel):
    id: int
    status: str
    region: str
    currency: str
    period_start: datetime
    period_end: datetime
    budget_summary: BudgetSummary
    meals: list[MealRead]
    notes: list[str] = Field(default_factory=list)
