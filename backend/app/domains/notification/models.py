"""notification 도메인 SQLAlchemy 모델 — 마이그레이션 0008(docs/설계/db-schema.md 2-8)과 1:1 일치.

- device_tokens          : Expo 푸시 토큰 (발송 주소 — 비밀 아님, 로그엔 마스킹)
- notification_settings  : 유형별 on/off + 리마인더 로컬시각/타임존, next_send_at(UTC) 스케줄 키
- notification_logs      : 발송 이력 — 본문 원문 저장 금지(template_key 만), 90일 배치 삭제
(app_login_codes 는 auth 도메인 models 에 위치 — 세션 인계 개념)
"""

import uuid
from datetime import UTC, datetime, time

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


# settings.type 열거 — 마이그레이션 0008 CHECK 와 동일
SETTING_TYPES = (
    "meal_reminder_breakfast",
    "meal_reminder_lunch",
    "meal_reminder_dinner",
    "mealplan_done",
    "weekly_nudge",
)


class DeviceToken(Base):
    __tablename__ = "device_tokens"
    __table_args__ = (
        CheckConstraint("platform IN ('ios', 'android')", name="ck_device_tokens_platform"),
        UniqueConstraint("token", name="uq_device_tokens_token"),
        Index("ix_device_tokens_user_id", "user_id"),
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
    platform: Mapped[str] = mapped_column(String(10), nullable=False)
    token: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(
        String(10), nullable=False, default="ko", server_default="ko"
    )
    timezone: Mapped[str] = mapped_column(
        String(40), nullable=False, default="Asia/Seoul", server_default="Asia/Seoul"
    )
    app_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow, server_default=text("now()")
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


class NotificationSetting(Base):
    __tablename__ = "notification_settings"
    __table_args__ = (
        CheckConstraint(
            "type IN ('meal_reminder_breakfast', 'meal_reminder_lunch', "
            "'meal_reminder_dinner', 'mealplan_done', 'weekly_nudge')",
            name="ck_notification_settings_type",
        ),
        UniqueConstraint("user_id", "type", name="uq_notification_settings_user_type"),
        # 스케줄러 due 스캔 전용 partial index (타임존별 전체 스캔 금지)
        Index(
            "ix_notification_settings_due",
            "next_send_at",
            postgresql_where=text("enabled AND next_send_at IS NOT NULL"),
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
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    local_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    next_send_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
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


class NotificationLog(Base):
    __tablename__ = "notification_logs"
    __table_args__ = (
        CheckConstraint("status IN ('sent', 'failed')", name="ck_notification_logs_status"),
        Index("ix_notification_logs_user_sent", "user_id", "sent_at"),
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
    device_token_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("device_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    # 본문 원문 저장 금지 — template_key 만 (CWE-359)
    template_key: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow, server_default=text("now()")
    )
