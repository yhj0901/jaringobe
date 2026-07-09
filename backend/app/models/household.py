from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Household(Base):
    """가구 구성 (최소 스텁).

    본래 auth/household 도메인 소유. budget/meal_plan FK 대상을 만들기 위한
    최소 구현이며, 정식 회원/가구 기능은 별도 기획·설계에서 확장한다.
    - members: [{"age_group": "adult|teen|child|infant"}]
    - allergies / preferences: 문자열 리스트
    """

    __tablename__ = "household"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    region: Mapped[str] = mapped_column(String(2), nullable=False, default="KR")
    members: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    allergies: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    preferences: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
