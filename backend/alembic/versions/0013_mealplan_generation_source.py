"""식단 생성 출처를 영속 저장한다.

llm | fallback, NULL 은 출처를 알 수 없음을 뜻한다.
기존 행은 추정하지 않고 NULL 로 보존하며 백필·기본값을 두지 않는다.
허용값은 애플리케이션에서 검증한다 (새 생성 경로 추가 시 CHECK 변경 불필요).

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meal_plans", sa.Column("generation_source", sa.String(16), nullable=True)
    )


def downgrade() -> None:
    # 출처 데이터는 컬럼과 함께 소실되며 재적용해도 복원되지 않는다.
    op.drop_column("meal_plans", "generation_source")
