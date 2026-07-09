"""store 연동 상태 SQLAlchemy 모델 — 마이그레이션 0005(docs/설계/db-schema.md 2-7)와 1:1 일치.

자격증명 컬럼 없음 — 실계정 연동 도입 시 store 본설계에서 암호화 참조로 확장 (평문 저장 금지).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class StoreConnection(Base):
    """유저별 마트 연동 상태 — (user_id, store) 유니크, 상태 관리만 (1단계)."""

    __tablename__ = "store_connections"
    __table_args__ = (
        CheckConstraint(
            "store IN ('kurly', 'coupang', 'ssg', 'naver')",
            name="ck_store_connections_store",
        ),
        CheckConstraint(
            "status IN ('connected', 'disconnected')",
            name="ck_store_connections_status",
        ),
        UniqueConstraint("user_id", "store", name="uq_store_connections_user_store"),
        Index("ix_store_connections_user_id", "user_id"),
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
    store: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    connected_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
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
