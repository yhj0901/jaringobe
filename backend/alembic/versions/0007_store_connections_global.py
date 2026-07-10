"""store_connections CHECK 제약에 walmart·instacart 편입 (docs/설계/db-schema.md 2-7, 글로벌-지역전환 FR-604)

국가별 스토어 세트 확장 — KR(kurly/coupang/ssg/naver) 외 US(walmart/instacart) 허용.
컬럼 타입 변경 없음(varchar(10) 이 instacart 9자 수용). 허용 집합 확대만이라 기존 행 영향 없음.
국가↔스토어 매핑 제약은 두지 않음(지역 전환 시 타 국가 연동 행 보존·복원 — 노출 세트는 애플리케이션 계층이 user.country 로 결정).

주의(downgrade): walmart/instacart 연동 행이 존재하면 KR 4종으로 CHECK 원복 시 위반 발생 →
운영 롤백 전 해당 행 정리 필요.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONSTRAINT = "ck_store_connections_store"
_TABLE = "store_connections"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "store IN ('kurly', 'coupang', 'ssg', 'naver', 'walmart', 'instacart')",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "store IN ('kurly', 'coupang', 'ssg', 'naver')",
    )
