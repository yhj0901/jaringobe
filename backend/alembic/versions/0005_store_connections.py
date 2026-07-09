"""store_connections 신규 — 자동 주문 연동 스토어 상태 (docs/설계/db-schema.md 2-7)

자격증명 컬럼 없음 — 실계정 연동 도입 시 store 본설계에서 암호화 참조로 확장 (평문 저장 금지).

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "store_connections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("store", sa.String(10), nullable=False),
        sa.Column("status", sa.String(15), nullable=False),
        sa.Column("connected_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("store IN ('kurly', 'coupang', 'ssg', 'naver')", name="ck_store_connections_store"),
        sa.CheckConstraint("status IN ('connected', 'disconnected')", name="ck_store_connections_status"),
        sa.UniqueConstraint("user_id", "store", name="uq_store_connections_user_store"),
    )
    op.create_index("ix_store_connections_user_id", "store_connections", ["user_id"])


def downgrade() -> None:
    op.drop_table("store_connections")
