"""meals 에 completed_at·time_minutes·difficulty 추가 (docs/설계/db-schema.md, 식사완료-레시피)

전부 NULL 허용 — 기존 행 영향 없음. 완료=시각 저장, 해제=NULL.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("meals", sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("meals", sa.Column("time_minutes", sa.SmallInteger(), nullable=True))
    op.add_column("meals", sa.Column("difficulty", sa.String(10), nullable=True))
    op.create_check_constraint(
        "ck_meals_difficulty",
        "meals",
        "difficulty IS NULL OR difficulty IN ('easy', 'normal', 'hard')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_meals_difficulty", "meals", type_="check")
    op.drop_column("meals", "difficulty")
    op.drop_column("meals", "time_minutes")
    op.drop_column("meals", "completed_at")
