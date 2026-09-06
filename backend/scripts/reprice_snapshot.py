"""SELECT 추출 스냅샷의 전후 원가를 재계산한다. 대상 DB/저장 식단은 수정하지 않는다.

backend에서 실행: DATABASE_URL=... uv run python scripts/reprice_snapshot.py
--database jaringobe_pricing --snapshot reports/pricing_snapshot.json
"""

import argparse
import asyncio
import json
import os
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domains.mealplan.pricing import DBPriceProvider

BASIC = {"물", "수돗물", "소금", "후추", "설탕", "식용유", "참기름"}


async def main(database: str, snapshot: Path) -> None:
    url = make_url(os.environ["DATABASE_URL"])
    if url.drivername != "postgresql+asyncpg" or url.database != database:
        raise ValueError("Explicit asyncpg DATABASE_URL and --database must match")
    rows = json.loads(snapshot.read_text())
    engine = create_async_engine(
        url, connect_args={"server_settings": {"default_transaction_read_only": "on"}}
    )
    amounts: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
    try:
        async with async_sessionmaker(engine)() as db:
            provider = DBPriceProvider(db)
            for row in rows:
                amounts[row["name"]][0] += Decimal(row["est_cost"])
                amounts[row["name"]][1] += await provider.estimate_cost(
                    row["name"], Decimal(row["quantity"]), row["unit"], "KR", "KRW"
                )
    finally:
        await engine.dispose()
    totals = [sum(values[i] for values in amounts.values()) for i in (0, 1)]
    basic = [sum(values[i] for name, values in amounts.items() if name in BASIC) for i in (0, 1)]
    print(
        json.dumps(
            {
                "ingredient_kinds": len(amounts),
                "ingredient_lines": len(rows),
                "before_total_krw": str(totals[0]),
                "after_total_krw": str(totals[1]),
                "before_basic_krw": str(basic[0]),
                "after_basic_krw": str(basic[1]),
                "before_basic_percent": str(basic[0] / totals[0] * 100),
                "after_basic_percent": str(basic[1] / totals[1] * 100),
                "ingredients": {
                    name: {"before": str(values[0]), "after": str(values[1])}
                    for name, values in sorted(amounts.items())
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="식단 재료 스냅샷 원가 비교 (DB 읽기 전용)")
    parser.add_argument("--database", required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.database, args.snapshot))
