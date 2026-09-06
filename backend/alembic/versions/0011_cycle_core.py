"""주간 사이클 핵심 스키마 + 기존 확정 주문 안전 백필.

user_cycle_settings 를 만들고 orders 를 주간 사이클 상태 머신에 맞게 확장한다.
기존 confirmed 주문은 auto-order-p0 에서 이미 냉장고에 등록됐으므로
inbound_at=confirmed_at 으로 반드시 백필해 재등록을 막는다.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 사용자별 설정은 lazy 생성이 정본이다. 기존 users 전체 백필은 하지 않는다.
    op.create_table(
        "user_cycle_settings",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "frequency", sa.String(20), nullable=False, server_default="weekly"
        ),
        sa.Column(
            "anchor_weekday", sa.SmallInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "timezone", sa.String(40), nullable=False, server_default="Asia/Seoul"
        ),
        sa.Column(
            "auto_confirm", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("skip_until", sa.Date(), nullable=True),
        sa.Column("next_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_stage", sa.String(20), nullable=True),
        sa.Column(
            "stage_attempts", sa.SmallInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("last_generated_cycle_start", sa.Date(), nullable=True),
        sa.Column("last_generated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("dormant_since", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "frequency IN ('weekly', 'biweekly')", name="ck_cycle_frequency"
        ),
        sa.CheckConstraint(
            "anchor_weekday BETWEEN 0 AND 6", name="ck_cycle_anchor_weekday"
        ),
        sa.CheckConstraint(
            "last_stage IS NULL OR last_stage IN ("
            "'generated','generate_failed','drafted','skipped_dormant',"
            "'skipped_user','deferred_quota')",
            name="ck_cycle_last_stage",
        ),
        sa.UniqueConstraint("user_id", name="uq_cycle_settings_user"),
    )
    op.create_index(
        "ix_cycle_settings_due",
        "user_cycle_settings",
        ["next_run_at"],
        postgresql_where=sa.text("enabled AND next_run_at IS NOT NULL"),
    )

    # 1) 신규 컬럼은 NULL 허용 또는 안전한 DEFAULT 상태로 먼저 추가한다.
    op.add_column("orders", sa.Column("cycle_start", sa.Date(), nullable=True))
    op.add_column(
        "orders", sa.Column("delivery_eta", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("inbound_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("auto_confirm_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    op.add_column(
        "orders",
        sa.Column(
            "auto_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "delivery_state", sa.String(20), nullable=False, server_default="pending"
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "delivery_confirm_attempts",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column("orders", sa.Column("blocked_reason", sa.String(30), nullable=True))
    op.add_column(
        "orders", sa.Column("reminded_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )

    # 초안은 확정 시각이 없다는 API/모델 계약을 실제 DB에도 반영한다.
    op.alter_column(
        "orders",
        "confirmed_at",
        existing_type=sa.TIMESTAMP(timezone=True),
        nullable=True,
    )

    # 중복 confirmed 행을 cancelled 로 강등할 수 있도록 상태 CHECK 를 먼저 확장한다.
    op.drop_constraint("ck_orders_status", "orders", type_="check")
    op.create_check_constraint(
        "ck_orders_status",
        "orders",
        "status IN ('draft','awaiting_user','confirmed','cancelled','expired','failed')",
    )
    op.drop_constraint("ck_orders_frequency", "orders", type_="check")
    op.create_check_constraint(
        "ck_orders_frequency", "orders", "frequency IN ('weekly','biweekly')"
    )
    op.create_check_constraint(
        "ck_orders_delivery_state",
        "orders",
        "delivery_state IN ('pending','delivered','unknown')",
    )

    # 2) 기존 confirmed 주문은 이미 냉장고에 들어간 주문이다.
    # ★ inbound_at 백필이 없으면 새 due 스캔이 같은 배송분을 다시 등록한다.
    op.execute(
        sa.text(
            """
            UPDATE orders
               SET cycle_start = (confirmed_at AT TIME ZONE 'Asia/Seoul')::date,
                   delivery_eta = confirmed_at,
                   inbound_at = confirmed_at,
                   delivery_state = 'delivered',
                   auto_confirmed = false
             WHERE status = 'confirmed'
            """
        )
    )

    # 3) 기존 행 백필이 끝난 뒤에만 NOT NULL 로 승격한다.
    op.alter_column("orders", "cycle_start", existing_type=sa.Date(), nullable=False)

    # 4) 같은 사용자/사이클의 기존 confirmed 중 최신 1건만 유지한다.
    # 삭제하지 않고 나머지를 cancelled 로 강등하는 것이 확정 설계다.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY user_id, cycle_start
                           ORDER BY created_at DESC, id DESC
                       ) AS row_number
                  FROM orders
                 WHERE status = 'confirmed'
            )
            UPDATE orders AS target
               SET status = 'cancelled', updated_at = now()
              FROM ranked
             WHERE target.id = ranked.id
               AND ranked.row_number > 1
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                      FROM orders
                     WHERE status = 'confirmed'
                     GROUP BY user_id, cycle_start
                    HAVING count(*) > 1
                ) THEN
                    RAISE EXCEPTION 'duplicate confirmed orders remain after cycle backfill';
                END IF;
            END
            $$
            """
        )
    )

    # 5) 백필과 중복 정리가 완료된 뒤 부분 인덱스를 만든다.
    op.create_index(
        "uq_orders_confirmed_cycle",
        "orders",
        ["user_id", "cycle_start"],
        unique=True,
        postgresql_where=sa.text("status='confirmed'"),
    )
    op.create_index(
        "uq_orders_open_cycle",
        "orders",
        ["user_id", "cycle_start"],
        unique=True,
        postgresql_where=sa.text("status IN ('draft','awaiting_user')"),
    )
    op.create_index(
        "ix_orders_inbound_due",
        "orders",
        ["delivery_eta"],
        postgresql_where=sa.text(
            "status='confirmed' AND inbound_at IS NULL AND delivery_state <> 'unknown'"
        ),
    )
    op.create_index(
        "ix_orders_autoconfirm_due",
        "orders",
        ["auto_confirm_at"],
        postgresql_where=sa.text("status='draft' AND auto_confirm_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_orders_autoconfirm_due", table_name="orders")
    op.drop_index("ix_orders_inbound_due", table_name="orders")
    op.drop_index("uq_orders_open_cycle", table_name="orders")
    op.drop_index("uq_orders_confirmed_cycle", table_name="orders")

    # 파괴적 롤백: 0009 는 confirmed 단일 상태 + confirmed_at NOT NULL 만 허용한다.
    # 따라서 0011 이후 생긴 초안/대기/취소/만료/실패 주문과 그 order_items 는
    # 0009 계약 복구 전에 삭제한다(order_items FK CASCADE). confirmed 이력은 보존한다.
    op.execute(
        sa.text(
            "DELETE FROM orders WHERE status <> 'confirmed' OR confirmed_at IS NULL"
        )
    )

    op.drop_constraint("ck_orders_delivery_state", "orders", type_="check")
    op.drop_constraint("ck_orders_frequency", "orders", type_="check")
    op.drop_constraint("ck_orders_status", "orders", type_="check")
    op.create_check_constraint(
        "ck_orders_status", "orders", "status IN ('confirmed')"
    )
    op.create_check_constraint(
        "ck_orders_frequency", "orders", "frequency IN ('weekly')"
    )
    op.alter_column(
        "orders",
        "confirmed_at",
        existing_type=sa.TIMESTAMP(timezone=True),
        nullable=False,
    )

    op.drop_column("orders", "reminded_at")
    op.drop_column("orders", "blocked_reason")
    op.drop_column("orders", "delivery_confirm_attempts")
    op.drop_column("orders", "delivery_state")
    op.drop_column("orders", "auto_confirmed")
    op.drop_column("orders", "auto_confirm_at")
    op.drop_column("orders", "inbound_at")
    op.drop_column("orders", "delivery_eta")
    op.drop_column("orders", "cycle_start")

    op.drop_index("ix_cycle_settings_due", table_name="user_cycle_settings")
    op.drop_table("user_cycle_settings")
