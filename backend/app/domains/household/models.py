"""household 도메인 SQLAlchemy 모델 — 마이그레이션 0004(docs/설계/db-schema.md 2-6)와 1:1 일치."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class HouseholdMember(Base):
    """가구 구성원 — 유저별 replace-all 저장, position 으로 표시 순서 유지."""

    __tablename__ = "household_members"
    __table_args__ = (
        CheckConstraint(
            "member_type IN ('adult_m', 'adult_f', 'teen', 'child', 'toddler')",
            name="ck_household_members_type",
        ),
        CheckConstraint("age BETWEEN 0 AND 99", name="ck_household_members_age"),
        Index("ix_household_members_user_id", "user_id"),
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
    member_type: Mapped[str] = mapped_column(String(10), nullable=False)
    age: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow, server_default=text("now()")
    )
