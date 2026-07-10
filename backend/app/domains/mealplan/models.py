"""mealplan 도메인 SQLAlchemy 모델 — 마이그레이션 0002와 1:1 일치.

user_id(users) + budget_plan_id(budget_plans) 기준. UUID PK, timestamptz(UTC).
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    TIMESTAMP,
    Date,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MealPlan(Base):
    __tablename__ = "meal_plans"
    __table_args__ = (Index("ix_meal_plans_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    budget_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budget_plans.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ready")
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    region: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow, server_default=text("now()")
    )

    meals: Mapped[list["Meal"]] = relationship(
        back_populates="meal_plan", cascade="all, delete-orphan"
    )


class Meal(Base):
    __tablename__ = "meals"
    __table_args__ = (Index("ix_meals_plan_date", "meal_plan_id", "plan_date"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    meal_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False
    )
    plan_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_type: Mapped[str] = mapped_column(String(16), nullable=False)
    recipe_name: Mapped[str] = mapped_column(String(200), nullable=False)
    recipe_steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 식사 완료·레시피 메타 (마이그레이션 0006 과 1:1). 전부 NULL 허용
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    time_minutes: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(10), nullable=True)

    meal_plan: Mapped["MealPlan"] = relationship(back_populates="meals")
    ingredients: Mapped[list["MealIngredient"]] = relationship(
        back_populates="meal", cascade="all, delete-orphan"
    )


class MealIngredient(Base):
    __tablename__ = "meal_ingredients"
    __table_args__ = (Index("ix_meal_ingredients_meal", "meal_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    meal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meals.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    est_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(CHAR(3), nullable=True)

    meal: Mapped["Meal"] = relationship(back_populates="ingredients")


class IngredientPriceRef(Base):
    """지역별 재료 기준가 (v1 가격 소스). 후속 store 어댑터로 교체 가능."""

    __tablename__ = "ingredient_price_refs"
    __table_args__ = (
        UniqueConstraint("name", "region", "unit", name="uq_price_name_region_unit"),
        Index("ix_price_region_name", "region", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    region: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    pack_qty: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
