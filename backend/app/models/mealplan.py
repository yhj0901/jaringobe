from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class MealPlan(Base):
    """생성된 식단(기간 단위). status: generating/ready/over_budget/failed."""

    __tablename__ = "meal_plan"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    household_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("household.id", ondelete="CASCADE"), nullable=False
    )
    budget_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("budget.id"), nullable=False
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="generating")
    total_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    region: Mapped[str] = mapped_column(String(2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    meals: Mapped[list["Meal"]] = relationship(
        back_populates="meal_plan", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_mealplan_household_period", "household_id", "period_start"),
    )


class Meal(Base):
    """식단의 한 끼."""

    __tablename__ = "meal"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    meal_plan_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("meal_plan.id", ondelete="CASCADE"), nullable=False
    )
    plan_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_type: Mapped[str] = mapped_column(String(16), nullable=False)
    recipe_name: Mapped[str] = mapped_column(String(200), nullable=False)
    recipe_steps: Mapped[str | None] = mapped_column(Text, nullable=True)

    meal_plan: Mapped["MealPlan"] = relationship(back_populates="meals")
    ingredients: Mapped[list["MealIngredient"]] = relationship(
        back_populates="meal", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_meal_plan_date", "meal_plan_id", "plan_date"),
    )


class MealIngredient(Base):
    """끼니별 재료. est_cost는 기준가 기반 산출값."""

    __tablename__ = "meal_ingredient"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    meal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("meal.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    est_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    meal: Mapped["Meal"] = relationship(back_populates="ingredients")

    __table_args__ = (
        Index("ix_ingredient_meal", "meal_id"),
    )
