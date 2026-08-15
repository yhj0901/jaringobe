"""meals.fridge_deducted — 식사 완료 시 실제 냉장고 차감 스냅샷 (Zero-UX 복원)

완료 해제 시 레시피 전량이 아니라 이 스냅샷 수량만 되돌린다.
JSONB NULL. 기존 행 영향 없음.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meals",
        sa.Column("fridge_deducted", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("meals", "fridge_deducted")
