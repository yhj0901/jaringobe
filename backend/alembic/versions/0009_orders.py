"""orders + order_items 신규 — 자동주문 P0 시뮬레이션 확정 스냅샷 (docs/설계/db-schema.md 2-8)

PK uuid + timestamptz UTC. 금액 numeric(float 금지). 자격증명 컬럼 없음
(평문/암호문 모두 금지 — 실연동 시 store 본설계의 암호화 참조를 쓰지, orders 에 복사하지 않음).
보관: 확정 후 24개월 후 배치 삭제(P0 는 잡 미구현 — 기간만 명시). 게스트 주문 행 없음.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "meal_plan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("meal_plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("store", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False, server_default="weekly"),
        sa.Column("next_suggested_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("estimated_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False),
        sa.Column("simulation", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "store IN ('kurly', 'coupang', 'ssg', 'naver', 'walmart', 'instacart')",
            name="ck_orders_store",
        ),
        sa.CheckConstraint("status IN ('confirmed')", name="ck_orders_status"),
        sa.CheckConstraint("frequency IN ('weekly')", name="ck_orders_frequency"),
        sa.CheckConstraint("currency IN ('KRW', 'USD')", name="ck_orders_currency"),
    )
    # latest 커버: (user_id, created_at DESC) — btree 정렬이 조회와 일치
    op.execute(sa.text("CREATE INDEX ix_orders_user_created ON orders (user_id, created_at DESC)"))

    op.create_table(
        "order_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "order_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("line_type", sa.String(20), nullable=False),
        sa.Column("matched", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.CHAR(3), nullable=True),
        sa.Column("mall_name", sa.String(100), nullable=True),
        sa.Column("link", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("quantity > 0", name="ck_order_items_quantity"),
        sa.CheckConstraint("line_type IN ('needed', 'covered')", name="ck_order_items_line_type"),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_orders_user_created", table_name="orders")
    op.drop_table("orders")
