"""KR 기준가 시드의 멱등성·기존값 보존·실측 40종 적용 검증."""

from decimal import Decimal

import pytest

from app.domains.mealplan.models import IngredientPriceRef
from app.domains.mealplan.pricing import DBPriceProvider


async def test_seeding_is_idempotent_and_preserves_existing_reference(db):
    from sqlalchemy import func, select

    from app.domains.mealplan.price_catalog import kr_price_rows
    from app.domains.mealplan.seed_prices import seed_price_refs

    db.add(
        IngredientPriceRef(
            name="두부",
            region="KR",
            unit="g",
            pack_qty=Decimal("300"),
            unit_price=Decimal("2300"),
            currency="KRW",
        )
    )
    await db.flush()
    assert await seed_price_refs(db) == len(kr_price_rows()) - 1
    assert await seed_price_refs(db) == 0
    assert await db.scalar(select(func.count()).select_from(IngredientPriceRef)) == len(
        kr_price_rows()
    )
    assert await DBPriceProvider(db).estimate_cost(
        "두부", Decimal("150"), "g", "KR", "KRW"
    ) == Decimal("1150.00")


async def test_seed_covers_every_observed_ingredient_and_does_not_call_fallback(db, monkeypatch):
    import json
    from pathlib import Path

    from app.domains.mealplan import pricing
    from app.domains.mealplan.seed_prices import seed_price_refs

    await seed_price_refs(db)
    snapshot = json.loads((Path(__file__).parents[1] / "reports/pricing_snapshot.json").read_text())
    assert len({(row["name"], row["unit"]) for row in snapshot}) == 40

    def no_fallback(*args):
        pytest.fail("시드된 실측 40종 재료가 폴백 경로에 들어갔습니다")

    monkeypatch.setattr(pricing, "pantry_cost", no_fallback)
    monkeypatch.setattr(pricing, "_stable_int", no_fallback)
    total = Decimal("0")
    for row in snapshot:
        total += await DBPriceProvider(db).estimate_cost(
            row["name"], Decimal(row["quantity"]), row["unit"], "KR", "KRW"
        )
    assert Decimal("0") < total < Decimal("132882.60")


async def test_seed_database_rejects_wrong_target_before_connecting():
    from app.domains.mealplan.seed_prices import seed_database

    with pytest.raises(ValueError, match="must match"):
        await seed_database("postgresql+asyncpg://localhost/jaringobe", "jaringobe_pricing")


async def test_us_and_kr_pantry_are_separate_estimates(db):
    from app.domains.mealplan.seed_prices import seed_price_refs

    await seed_price_refs(db)
    provider = DBPriceProvider(db)
    assert await provider.estimate_cost("salt", Decimal("1000"), "g", "KR", "KRW") == 2200
    assert await provider.estimate_cost("salt", Decimal("1000"), "g", "US", "USD") == 2


async def test_seed_database_commits_rows_and_is_repeatable(db):
    import os

    from sqlalchemy.engine import make_url

    from app.domains.mealplan.price_catalog import kr_price_rows
    from app.domains.mealplan.seed_prices import seed_database

    url = os.environ["DATABASE_URL"]
    database = make_url(url).database
    assert database is not None
    assert await seed_database(url, database) == len(kr_price_rows())
    assert await seed_database(url, database) == 0
    assert await DBPriceProvider(db).estimate_cost(
        "두부", Decimal("150"), "g", "KR", "KRW"
    ) == Decimal("800.00")


def test_seed_cli_refuses_implicit_dotenv_database(monkeypatch):
    from app.domains.mealplan.seed_prices import main

    monkeypatch.delenv("DATABASE_URL")
    monkeypatch.setattr("sys.argv", ["seed_prices", "--database", "jaringobe_pricing"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
