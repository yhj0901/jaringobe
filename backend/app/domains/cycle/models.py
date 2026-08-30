"""cycle 도메인 SQLAlchemy 모델 — user_cycle_settings 소유."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UserCycleSettings(Base):
    """사용자별 주간 사이클 정책과 다음 due 스캔 상태."""

    __tablename__ = "user_cycle_settings"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_cycle_settings_user"),
        CheckConstraint("frequency IN ('weekly', 'biweekly')", name="ck_cycle_frequency"),
        CheckConstraint("anchor_weekday BETWEEN 0 AND 6", name="ck_cycle_anchor_weekday"),
        CheckConstraint(
            "last_stage IS NULL OR last_stage IN ("
            "'generated','generate_failed','drafted','skipped_dormant',"
            "'skipped_user','deferred_quota')",
            name="ck_cycle_last_stage",
        ),
        Index(
            "ix_cycle_settings_due",
            "next_run_at",
            postgresql_where=text("enabled AND next_run_at IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    frequency: Mapped[str] = mapped_column(
        String(20), nullable=False, default="weekly", server_default="weekly"
    )
    anchor_weekday: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    timezone: Mapped[str] = mapped_column(
        String(40), nullable=False, default="Asia/Seoul", server_default="Asia/Seoul"
    )
    auto_confirm: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    skip_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    stage_attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    last_generated_cycle_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_generated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    dormant_since: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
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
