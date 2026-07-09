from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Budget(Base):
    """예산 락. 금액은 numeric + 통화코드 (float 금지)."""

    __tablename__ = "budget"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    household_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("household.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_budget_amount_positive"),
        CheckConstraint("currency in ('KRW','USD')", name="ck_budget_currency"),
        CheckConstraint("period_end > period_start", name="ck_budget_period"),
        Index("ix_budget_household_period", "household_id", "period_start"),
    )
