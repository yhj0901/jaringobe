"""household_members 신규 + budget_plans locked/cuisines 확장 (docs/설계/db-schema.md 2-6)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "household_members",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_type", sa.String(10), nullable=False),
        sa.Column("age", sa.SmallInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "member_type IN ('adult_m', 'adult_f', 'teen', 'child', 'toddler')",
            name="ck_household_members_type",
        ),
        sa.CheckConstraint("age BETWEEN 0 AND 99", name="ck_household_members_age"),
    )
    op.create_index("ix_household_members_user_id", "household_members", ["user_id"])

    # 기존 행: 락 기본 활성(기획 의도), 선호 음식 빈 배열
    op.add_column("budget_plans", sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("budget_plans", sa.Column("cuisines", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))


def downgrade() -> None:
    op.drop_column("budget_plans", "cuisines")
    op.drop_column("budget_plans", "locked")
    op.drop_table("household_members")
