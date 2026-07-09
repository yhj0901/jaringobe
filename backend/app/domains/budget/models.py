"""budget 도메인 SQLAlchemy 모델 — 마이그레이션 0001(docs/설계/db-schema.md)과 1:1 일치."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class BudgetPlan(Base):
    """v0 최소 스키마 — 유저당 활성 예산안 1개 (UNIQUE(user_id))."""

    __tablename__ = "budget_plans"
    __table_args__ = (
        CheckConstraint("household_size BETWEEN 1 AND 10", name="ck_budget_plans_household_size"),
        CheckConstraint("amount > 0", name="ck_budget_plans_amount_positive"),
        CheckConstraint("currency IN ('KRW', 'USD')", name="ck_budget_plans_currency"),
        CheckConstraint(
            "meal_direction IN ('health', 'diet', 'hearty', 'kids')",
            name="ck_budget_plans_meal_direction",
        ),
        CheckConstraint("source IN ('guest', 'onboarding')", name="ck_budget_plans_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # v0: 유저당 활성 예산안 1개
    )
    household_size: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)  # float 금지 원칙
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    meal_direction: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    # 0004 확장 — 예산 락 여부 + 선호 음식(enum 배열, 서비스 검증)
    locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    cuisines: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
        server_default=text("now()"),
    )
