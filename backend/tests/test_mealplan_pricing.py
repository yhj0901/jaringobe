"""식단 원가 회귀 — 운영 DB/외부 API 없이 전용 DB에서 검증."""

from decimal import Decimal

import pytest

from app.domains.mealplan.models import IngredientPriceRef
from app.domains.mealplan.pricing import DBPriceProvider


@pytest.mark.parametrize("region,currency", [("KR", "KRW"), ("US", "USD")])
@pytest.mark.parametrize("name", ["물", "수돗물", "water", " Tap Water "])
async def test_cooking_water_is_free_without_seed(db, name, region, currency):
    assert await DBPriceProvider(db).estimate_cost(
        name, Decimal("500"), "ml", region, currency
    ) == Decimal("0.00")


@pytest.mark.parametrize("name", ["생수", "탄산수", "멸치육수", "bottled water", "watermelon"])
async def test_paid_water_and_substring_names_are_not_free(db, name):
    assert await DBPriceProvider(db).estimate_cost(name, Decimal("500"), "ml", "KR", "KRW") > 0


@pytest.mark.parametrize("name", ["소금", "salt", "후추", "black pepper", "설탕", "sugar"])
async def test_small_condiment_has_no_hundred_won_floor(db, name):
    cost = await DBPriceProvider(db).estimate_cost(name, Decimal("0.1"), "g", "KR", "KRW")
    assert Decimal("0") < cost < Decimal("20")


@pytest.mark.parametrize("name", ["salt", "후추", "sugar", "식용유", "sesame oil"])
async def test_us_condiment_has_no_twenty_cent_floor(db, name):
    unit = "ml" if name in {"식용유", "sesame oil"} else "g"
    assert await DBPriceProvider(db).estimate_cost(name, Decimal("1"), unit, "US", "USD") < Decimal(
        "0.20"
    )


@pytest.mark.parametrize("name", ["두부", "소금", "water"])
async def test_valid_db_reference_precedes_estimates(db, name):
    db.add(
        IngredientPriceRef(
            name=name,
            region="KR",
            unit="g",
            pack_qty=Decimal("300"),
            unit_price=Decimal("2100"),
            currency="KRW",
        )
    )
    await db.flush()
    assert await DBPriceProvider(db).estimate_cost(
        name, Decimal("150"), "g", "KR", "KRW"
    ) == Decimal("1050.00")


async def test_reference_currency_cannot_be_mislabelled_as_usd(db):
    db.add(
        IngredientPriceRef(
            name="salt",
            region="US",
            unit="g",
            pack_qty=Decimal("100"),
            unit_price=Decimal("1000"),
            currency="KRW",
        )
    )
    await db.flush()
    assert await DBPriceProvider(db).estimate_cost(
        "salt", Decimal("1"), "g", "US", "USD"
    ) < Decimal("0.20")


@pytest.mark.parametrize("pack_qty", ["0", "-1"])
async def test_invalid_reference_quantity_uses_pantry_estimate(db, pack_qty):
    db.add(
        IngredientPriceRef(
            name="소금",
            region="KR",
            unit="g",
            pack_qty=Decimal(pack_qty),
            unit_price=Decimal("1000"),
            currency="KRW",
        )
    )
    await db.flush()
    assert await DBPriceProvider(db).estimate_cost(
        "소금", Decimal("1"), "g", "KR", "KRW"
    ) < Decimal("10")


@pytest.mark.parametrize("region,currency", [("KR", "KRW"), ("US", "USD")])
@pytest.mark.parametrize("name", ["salt", "pepper", "sugar", "cooking oil", "sesame oil"])
async def test_pantry_never_uses_random_hash(db, monkeypatch, name, region, currency):
    from app.domains.mealplan import pricing

    def fail_hash(*args):
        pytest.fail("기본 양념이 난수 가격 경로로 들어갔습니다")

    monkeypatch.setattr(pricing, "_stable_int", fail_hash)
    for unit in ("g", "ml", "kg", "l", "tsp", "tbsp", "pinch", "ea", "약간"):
        await DBPriceProvider(db).estimate_cost(name, Decimal("1"), unit, region, currency)


async def test_zero_pantry_quantity_stays_zero(db):
    assert await DBPriceProvider(db).estimate_cost(
        "소금", Decimal("0"), "g", "KR", "KRW"
    ) == Decimal("0.00")
