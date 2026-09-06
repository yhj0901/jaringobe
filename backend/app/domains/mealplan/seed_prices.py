"""기존 ingredient_price_refs에 초기 추정치를 추가하는 명시적·멱등 데이터 시드."""

import argparse
import asyncio
import os

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domains.mealplan.models import IngredientPriceRef
from app.domains.mealplan.price_catalog import kr_price_rows


async def seed_price_refs(db: AsyncSession) -> int:
    """기존/수동 기준가는 보존한다. 호출자가 트랜잭션 commit/rollback을 소유한다."""
    statement = (
        insert(IngredientPriceRef)
        .values(kr_price_rows())
        .on_conflict_do_nothing(constraint="uq_price_name_region_unit")
        .returning(IngredientPriceRef.id)
    )
    return len((await db.execute(statement)).scalars().all())


async def seed_database(database_url: str, expected_database: str) -> int:
    """대상 DB 이름을 명시적으로 대조하고 기존 테이블에 데이터만 추가한다."""
    url = make_url(database_url)
    if url.drivername != "postgresql+asyncpg" or url.database != expected_database:
        raise ValueError("Explicit asyncpg DATABASE_URL and --database must match")
    engine = create_async_engine(url)
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions.begin() as db:
            return await seed_price_refs(db)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="KR 초기 추정 기준가 추가 (기존 가격 보존)")
    parser.add_argument("--database", required=True, help="DATABASE_URL 대상 DB 이름 재확인")
    args = parser.parse_args()
    # .env의 암묵적 기본 DB로 쓰지 않도록 셸에서 명시한 환경변수만 받는다.
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL must be explicitly set in the environment")
    inserted = asyncio.run(seed_database(database_url, args.database))
    print(f"ingredient_price_refs: inserted={inserted}, catalog={len(kr_price_rows())}")


if __name__ == "__main__":
    main()
