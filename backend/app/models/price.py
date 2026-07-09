from decimal import Decimal

from sqlalchemy import BigInteger, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class IngredientPriceRef(Base):
    """지역별 재료 기준가 (v1 가격 소스).

    PriceProvider 가 이 테이블을 조회한다. 후속 store 어댑터로 교체 가능.
    """

    __tablename__ = "ingredient_price_ref"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    region: Mapped[str] = mapped_column(String(2), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    pack_qty: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    __table_args__ = (
        UniqueConstraint("name", "region", "unit", name="uq_price_name_region_unit"),
        Index("ix_price_region_name", "region", "name"),
    )
