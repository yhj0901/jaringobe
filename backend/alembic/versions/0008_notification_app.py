"""notification 도메인 + 앱 로그인 — 신규 4테이블 (docs/설계/db-schema.md 2-8)

앱 웹뷰 + 푸시 알림 (docs/기획/앱-웹뷰-푸시알림.md):
- device_tokens          : Expo 푸시 토큰 (token 은 발송 주소 — 비밀 아님, 로그 마스킹만)
- notification_settings  : 유형별 on/off + 리마인더 로컬시각/타임존, next_send_at(UTC) 스케줄 키
- notification_logs      : 발송 이력 — 본문 원문 저장 금지(template_key 만), 90일 배치 삭제
- app_login_codes        : 원타임 앱 로그인 코드 — SHA-256 해시만 저장, 60초 만료·단일 사용

meal_plans.status 의 processing/failed 확장은 DDL 불필요 (CHECK 제약 없음 — 서비스 레벨 검증만).
선행 조건: down_revision=0007(feature/global-region) — 해당 브랜치 main 머지 후 운영 적용.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SETTING_TYPES = (
    "'meal_reminder_breakfast', 'meal_reminder_lunch', 'meal_reminder_dinner', "
    "'mealplan_done', 'weekly_nudge'"
)


def upgrade() -> None:
    op.create_table(
        "device_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(10), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("locale", sa.String(10), nullable=False, server_default="ko"),
        sa.Column("timezone", sa.String(40), nullable=False, server_default="Asia/Seoul"),
        sa.Column("app_version", sa.String(20), nullable=True),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("platform IN ('ios', 'android')", name="ck_device_tokens_platform"),
        sa.UniqueConstraint("token", name="uq_device_tokens_token"),
    )
    op.create_index("ix_device_tokens_user_id", "device_tokens", ["user_id"])

    op.create_table(
        "notification_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("local_time", sa.Time(), nullable=True),
        sa.Column("timezone", sa.String(40), nullable=True),
        sa.Column("next_send_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(f"type IN ({_SETTING_TYPES})", name="ck_notification_settings_type"),
        sa.UniqueConstraint("user_id", "type", name="uq_notification_settings_user_type"),
    )
    # 스케줄러 due 스캔 전용 partial index — enabled 이면서 발송 예정이 있는 행만 (타임존별 전체 스캔 금지)
    op.create_index(
        "ix_notification_settings_due",
        "notification_settings",
        ["next_send_at"],
        postgresql_where=sa.text("enabled AND next_send_at IS NOT NULL"),
    )

    op.create_table(
        "notification_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "device_token_id",
            UUID(as_uuid=True),
            sa.ForeignKey("device_tokens.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("template_key", sa.String(50), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('sent', 'failed')", name="ck_notification_logs_status"),
    )
    # 누적성 테이블 — weekly_nudge 주 1회 한도 판정 + 유저별 이력 조회 커버, 90일 경과분 배치 삭제
    op.create_index("ix_notification_logs_user_sent", "notification_logs", ["user_id", "sent_at"])

    op.create_table(
        "app_login_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_hash", sa.CHAR(64), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("code_hash", name="uq_app_login_codes_code_hash"),
    )


def downgrade() -> None:
    # 신규 테이블만 — 역순 drop (notification_logs 가 device_tokens 를 FK 참조하므로 먼저)
    op.drop_table("app_login_codes")
    op.drop_table("notification_logs")
    op.drop_table("notification_settings")
    op.drop_table("device_tokens")
