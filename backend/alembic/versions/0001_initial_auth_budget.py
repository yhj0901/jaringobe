"""auth 3테이블 + budget_plans v0 최초 생성 (docs/설계/db-schema.md)

Revision ID: 0001
Revises:
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # gen_random_uuid() 사용을 위한 확장 (있으면 무시)
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("nickname", sa.String(50), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),  # 카카오 동의 거부 시 null
        sa.Column("profile_image_url", sa.Text(), nullable=True),
        sa.Column("locale", sa.String(10), nullable=False, server_default="ko"),
        sa.Column("country", sa.CHAR(2), nullable=False, server_default="KR"),
        sa.Column("currency", sa.CHAR(3), nullable=False, server_default="KRW"),
        sa.Column("onboarding_completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    # 동일 이메일 타 provider 안내(FR-004) 조회용 — 정책상 중복 허용이므로 비유니크
    op.create_index("ix_users_email", "users", [sa.text("lower(email)")])

    op.create_table(
        "auth_identities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("email_at_signup", sa.String(255), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_auth_identities_provider_uid"),
        sa.CheckConstraint("provider IN ('kakao', 'google', 'apple')", name="ck_auth_identities_provider"),
    )
    op.create_index("ix_auth_identities_user_id", "auth_identities", ["user_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.CHAR(64), nullable=False, unique=True),  # SHA-256 hex — 원문 저장 금지
        sa.Column(
            "rotated_from",
            UUID(as_uuid=True),
            sa.ForeignKey("refresh_tokens.id", ondelete="SET NULL"),  # 만료분 배치 삭제 시 체인 FK 위반 방지
            nullable=True,
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])

    op.create_table(
        "budget_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,  # v0: 유저당 활성 예산안 1개
        ),
        sa.Column("household_size", sa.SmallInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),  # float 금지 원칙
        sa.Column("currency", sa.CHAR(3), nullable=False),
        sa.Column("meal_direction", sa.String(20), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("household_size BETWEEN 1 AND 10", name="ck_budget_plans_household_size"),
        sa.CheckConstraint("amount > 0", name="ck_budget_plans_amount_positive"),
        sa.CheckConstraint("currency IN ('KRW', 'USD')", name="ck_budget_plans_currency"),
        sa.CheckConstraint(
            "meal_direction IN ('health', 'diet', 'hearty', 'kids')", name="ck_budget_plans_meal_direction"
        ),
        sa.CheckConstraint("source IN ('guest', 'onboarding')", name="ck_budget_plans_source"),
    )


def downgrade() -> None:
    # 생성 역순 drop — 최초 리비전이므로 완전 롤백 가능 (pgcrypto 확장은 공용이라 유지)
    op.drop_table("budget_plans")
    op.drop_table("refresh_tokens")
    op.drop_table("auth_identities")
    op.drop_table("users")
