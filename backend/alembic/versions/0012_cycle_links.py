"""주간 사이클과 fridge/auth/notification 연결.

fridge_items 에 주문 FK 를 연결하고 기존 source='order' 값을 delivery 로 통합한다.
users 최근 접속 시각과 사이클 트랜잭션 알림 3종도 함께 반영한다.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SETTING_TYPES_V1 = (
    "'meal_reminder_breakfast', 'meal_reminder_lunch', 'meal_reminder_dinner', "
    "'mealplan_done', 'weekly_nudge'"
)
_SETTING_TYPES_V2 = (
    f"{_SETTING_TYPES_V1}, 'order_approval', 'fridge_inbound', 'cycle_paused'"
)


def upgrade() -> None:
    op.add_column(
        "fridge_items", sa.Column("order_id", UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_fridge_items_order_id_orders",
        "fridge_items",
        "orders",
        ["order_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_fridge_items_order_id",
        "fridge_items",
        ["order_id"],
        postgresql_where=sa.text("order_id IS NOT NULL"),
    )
    # fridge_items.source 에 DB CHECK 는 없으므로 제약 재정의 없이 값만 통합한다.
    op.execute(sa.text("UPDATE fridge_items SET source = 'delivery' WHERE source = 'order'"))

    op.add_column(
        "users", sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    op.execute(sa.text("UPDATE users SET last_seen_at = updated_at"))

    # 0010 의 기존 CHECK 를 확장하지 않으면 신규 알림 INSERT 가 거부된다.
    op.drop_constraint(
        "ck_notification_settings_type", "notification_settings", type_="check"
    )
    op.create_check_constraint(
        "ck_notification_settings_type",
        "notification_settings",
        f"type IN ({_SETTING_TYPES_V2})",
    )


def downgrade() -> None:
    # 0010 CHECK 로 복구하기 전에 신규 타입 행을 제거해야 제약 생성이 성공한다.
    op.execute(
        sa.text(
            """
            DELETE FROM notification_settings
             WHERE type IN ('order_approval', 'fridge_inbound', 'cycle_paused')
            """
        )
    )
    op.drop_constraint(
        "ck_notification_settings_type", "notification_settings", type_="check"
    )
    op.create_check_constraint(
        "ck_notification_settings_type",
        "notification_settings",
        f"type IN ({_SETTING_TYPES_V1})",
    )

    op.drop_column("users", "last_seen_at")

    # upgrade 의 값 통합을 역방향으로 되돌린다. 0011 이전에는 order 가 정본이었다.
    op.execute(sa.text("UPDATE fridge_items SET source = 'order' WHERE source = 'delivery'"))
    op.drop_index("ix_fridge_items_order_id", table_name="fridge_items")
    op.drop_constraint(
        "fk_fridge_items_order_id_orders", "fridge_items", type_="foreignkey"
    )
    op.drop_column("fridge_items", "order_id")
