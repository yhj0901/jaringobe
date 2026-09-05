"""order 도메인 SQLAlchemy 모델 — 0009 + v1.8 cycle 확장 계약.

시뮬레이션 확정 스냅샷. 자격증명 컬럼 없음. meal_plan_id 는 SET NULL(식단 삭제해도 주문 이력 유지).
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Order(Base):
    """유저별 시뮬레이션 확정 주문. P0 status=confirmed, frequency=weekly, simulation=true."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "store IN ('kurly', 'coupang', 'ssg', 'naver', 'walmart', 'instacart')",
            name="ck_orders_store",
        ),
        CheckConstraint(
            "status IN ('draft','awaiting_user','confirmed','cancelled','expired','failed')",
            name="ck_orders_status",
        ),
        CheckConstraint(
            "frequency IN ('weekly','biweekly')", name="ck_orders_frequency"
        ),
        CheckConstraint("currency IN ('KRW', 'USD')", name="ck_orders_currency"),
        CheckConstraint(
            "delivery_state IN ('pending','delivered','unknown')",
            name="ck_orders_delivery_state",
        ),
        Index("ix_orders_user_created", "user_id", text("created_at DESC")),
        Index(
            "uq_orders_confirmed_cycle",
            "user_id",
            "cycle_start",
            unique=True,
            postgresql_where=text("status='confirmed'"),
        ),
        Index(
            "uq_orders_open_cycle",
            "user_id",
            "cycle_start",
            unique=True,
            postgresql_where=text("status IN ('draft','awaiting_user')"),
        ),
        Index(
            "ix_orders_inbound_due",
            "delivery_eta",
            postgresql_where=text(
                "status='confirmed' AND inbound_at IS NULL AND delivery_state <> 'unknown'"
            ),
        ),
        Index(
            "ix_orders_autoconfirm_due",
            "auto_confirm_at",
            postgresql_where=text("status='draft' AND auto_confirm_at IS NOT NULL"),
        ),
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
    )
    meal_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meal_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    store: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False, default="weekly")
    cycle_start: Mapped[date] = mapped_column(Date, nullable=False)
    next_suggested_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    estimated_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    simulation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    delivery_eta: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    inbound_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    auto_confirm_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    auto_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    delivery_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    delivery_confirm_attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    blocked_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reminded_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
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

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    """주문 라인 스냅샷. inbound 대상은 line_type=needed 만 (covered 는 리뷰 재현용)."""

    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity"),
        CheckConstraint("line_type IN ('needed', 'covered')", name="ck_order_items_line_type"),
        Index("ix_order_items_order_id", "order_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    line_type: Mapped[str] = mapped_column(String(20), nullable=False)
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(CHAR(3), nullable=True)
    mall_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    link: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow, server_default=text("now()")
    )

    order: Mapped["Order"] = relationship(back_populates="items")
