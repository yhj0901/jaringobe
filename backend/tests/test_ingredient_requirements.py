"""산문에서 빠진 조리 전제·실 누락·멱등성·원가/재고 연결 회귀."""

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domains.mealplan.ingredient_requirements import repair_meal_ingredients


@pytest.fixture
def final_samples():
    path = Path(__file__).resolve().parents[1] / "reports/ingredients-after.json"
    return json.loads(path.read_text())["runs"]


@pytest.fixture
def final_sample_meals(final_samples):
    """최종 실측의 보완 전 원문을 파싱한다. 유료 호출/이미 보완된 draft 역산 없음."""
    from app.domains.mealplan.generator import _parse_meals

    return [_parse_meals(json.loads(run["raw_responses"][0][0]), 7, 3) for run in final_samples]


def meal(name, ingredients=(), steps="재료를 익혀 낸다."):
    return {
        "name": name,
        "steps": steps,
        "day": 1,
        "meal_type": "lunch",
        "ingredients": [
            {"name": n, "quantity": Decimal(str(q)), "unit": u} for n, q, u in ingredients
        ],
    }


def quantities(draft):
    return {i["name"]: i["quantity"] for i in draft["ingredients"]}


def test_observed_braise_explicit_water_counts_existing_broth(final_sample_meals):
    draft = final_sample_meals[1][10]
    assert draft["name"] == "돼지고기김치찜"
    assert quantities(draft)["멸치육수"] == 300
    assert "물" not in quantities(draft)
    steps = draft["steps"]
    repair_meal_ingredients(draft, "KR", 2)
    assert quantities(draft)["물"] == 300
    assert quantities(draft)["물"] + quantities(draft)["멸치육수"] == 600
    assert draft["steps"] == steps
    assert repair_meal_ingredients(draft, "KR", 2) == []


def test_observed_set_meal_soup_only_in_steps_gets_liquid(final_sample_meals):
    draft = final_sample_meals[0][2]
    assert draft["name"] == "고등어구이정식"
    assert "무국을 준비한다" in draft["steps"]
    steps = draft["steps"]
    assert repair_meal_ingredients(draft, "KR", 2) == [
        {"name": "물", "quantity": Decimal(600), "unit": "ml", "reason": "cooking_liquid"}
    ]
    assert quantities(draft)["물"] == 600
    assert draft["steps"] == steps
    assert repair_meal_ingredients(draft, "KR", 2) == []


@pytest.mark.parametrize("trial", [1, 2, 3])
def test_final_samples_replay_changes_only_two_observed_meals(
    final_samples, final_sample_meals, trial
):
    drafts = final_sample_meals[trial - 1]
    expected = deepcopy(final_samples[trial - 1]["drafts"])
    assert len(drafts) == len(expected) == 21
    if trial == 1:
        expected[2]["ingredients"].append({"name": "물", "quantity": "600", "unit": "ml"})
    elif trial == 2:
        next(i for i in expected[10]["ingredients"] if i["name"] == "물")["quantity"] = "300"
    for draft, prior in zip(drafts, expected, strict=True):
        repair_meal_ingredients(draft, "KR", 2)
        for ingredient in prior["ingredients"]:
            ingredient.pop("est_cost", None)
            ingredient["quantity"] = Decimal(ingredient["quantity"])
        assert draft == prior
        assert repair_meal_ingredients(draft, "KR", 2) == []


@pytest.mark.parametrize(
    "steps",
    [
        "무국을 준비한다",
        "갈비탕을 끓인다",
        "두부찌개를 만든다",
        "국을 끓인다",
        "무국 준비한다",
        "국수는 생략한다;무국을 준비한다",
    ],
)
def test_step_soup_requires_cooking_context(steps):
    draft = meal("정식", [("소금", 2, "g")], steps)
    repair_meal_ingredients(draft, "KR", 2)
    assert quantities(draft)["물"] == 600


@pytest.mark.parametrize(
    "steps",
    [
        "국수를 준비한다",
        "비빔국수를 만든다",
        "국물볶음을 준비한다",
        "국물볶음용 양념을 끓인다",
        "국간장을 넣어 볶는다",
        "설탕을 끓인다",
        "흑설탕을 끓인다",
        "사탕을 만든다",
        "무국은 선택으로 준비한다",
        "무국을 준비하지 않는다",
        "무국을 끓이는 과정은 생략한다",
        "무국을 곁들인다",
        "즉석 무국을 데운다",
    ],
)
def test_step_soup_boundaries_do_not_add_cooking_liquid(steps):
    draft = meal("정식", [("소금", 2, "g")], steps)
    repair_meal_ingredients(draft, "KR", 2)
    assert "물" not in quantities(draft)


@pytest.mark.parametrize("name", ["비빔국수", "국물볶음"])
def test_soup_name_boundaries_still_exclude_noodles_and_brothy_stir_fry(name):
    draft = meal(name, [("소금", 2, "g")], "재료를 준비한다")
    repair_meal_ingredients(draft, "KR", 2)
    assert "물" not in quantities(draft)


@pytest.mark.parametrize("broth", [0, 300, 600, 800])
def test_explicit_water_fallback_subtracts_broth_and_existing_water(broth):
    ingredients = [("물", 100, "ml")]
    if broth:
        ingredients.append(("멸치육수", broth, "ml"))
    draft = meal(
        "정식",
        ingredients,
        "물을 넣는다",
    )
    repair_meal_ingredients(draft, "KR", 2)
    assert quantities(draft)["물"] == max(100, 600 - broth)
    assert repair_meal_ingredients(draft, "KR", 2) == []


def test_step_soup_does_not_replace_separate_noodle_boiling_water():
    draft = meal("정식", [("소면", 200, "g"), ("멸치육수", 300, "ml")], "무국을 준비한다")
    repair_meal_ingredients(draft, "KR", 2)
    assert quantities(draft)["물"] == 2300


@pytest.mark.parametrize(
    "name,ingredients,required",
    [
        ("닭고기카레", [("닭고기", 300, "g")], {"카레가루": 50, "물": 350, "식용유": 10}),
        ("무두부국", [("무", 200, "g"), ("두부", 300, "g")], {"물": 600, "소금": 2}),
        ("계란볶음밥", [("밥", 400, "g"), ("계란", 2, "ea")], {"식용유": 10}),
        ("시금치나물비빔밥", [("시금치", 100, "g"), ("밥", 400, "g")], {"물": 1000}),
        ("콩나물무침", [("콩나물", 200, "g")], {"물": 1000}),
        ("두부구이", [("두부", 300, "g")], {"식용유": 10}),
        (
            "계란후라이밥",
            [("계란", 2, "ea"), ("밥", 400, "g"), ("참기름", 5, "ml")],
            {"식용유": 10},
        ),
        ("고등어조림", [("고등어", 2, "ea")], {"물": 200}),
        ("계란찜", [("계란", 2, "ea")], {"물": 200}),
        ("닭고기죽", [("닭고기", 200, "g"), ("밥", 300, "g")], {"물": 800}),
        ("쌀밥과 된장국", [("쌀", 200, "g"), ("된장", 30, "g")], {"물": 900}),
        ("비빔국수", [("소면", 200, "g")], {"물": 2000}),
        ("대파계란볶음밥", [("밥", 400, "g")], {"대파": 20, "계란": 2, "식용유": 10}),
        ("순두부계란찜", [("순두부", 0, "g"), ("계란", 2, "ea")], {"순두부": 300, "물": 200}),
    ],
)
def test_dish_implies_missing_requirements_without_steps(name, ingredients, required):
    draft = meal(name, ingredients)
    before = deepcopy(draft)
    assert repair_meal_ingredients(draft, "KR", 2)
    for ingredient, quantity in required.items():
        assert quantities(draft)[ingredient] == quantity
    assert draft["steps"] == before["steps"]
    for original in before["ingredients"]:
        assert quantities(draft)[original["name"]] >= original["quantity"]
    repaired = deepcopy(draft)
    assert repair_meal_ingredients(draft, "KR", 2) == []
    assert draft == repaired


def test_explicit_soup_soy_is_distinct_from_regular_soy_and_no_partial_duplicates():
    draft = meal(
        "무두부국",
        [("무", 200, "g"), ("두부", 300, "g"), ("간장", 10, "ml"), ("멸치육수", 600, "ml")],
        "국간장과 대파를 넣어 끓인다.",
    )
    repair_meal_ingredients(draft, "KR", 2)
    assert quantities(draft)["국간장"] == 10
    assert quantities(draft)["대파"] == 20
    assert "물" not in quantities(draft)
    assert "소금" not in quantities(draft)
    assert quantities(draft)["간장"] == 10


@pytest.mark.parametrize(
    "name,ingredients,steps",
    [
        ("오이무침", [("오이", 200, "g")], "오이를 썰어 무친다."),
        ("시금치샐러드", [("시금치", 100, "g")], "씻어 담는다."),
        ("에어프라이 감자", [("감자", 200, "g")], "기름 없이 에어프라이어로 굽는다."),
        ("즉석카레", [("카레소스", 200, "g")], "전자레인지에 데운다."),
        ("두부구이", [("두부", 300, "g"), ("버터", 10, "g")], "버터에 두부를 굽는다."),
        ("Stir Fry", [("cooking oil", 10, "ml")], "Stir fry and serve."),
        ("샐러드", [("오이", 100, "g")], "참깨와 참기름은 선택으로 생략한다."),
    ],
)
def test_exceptions_do_not_invent_water_oil_or_garnishes(name, ingredients, steps):
    draft = meal(name, ingredients, steps)
    assert repair_meal_ingredients(draft, "KR", 2) == []


def test_broth_cannot_pay_for_separate_blanching_and_rice_water():
    draft = meal(
        "시금치나물과 된장국",
        [("시금치", 100, "g"), ("된장", 30, "g"), ("쌀", 200, "g"), ("멸치육수", 600, "ml")],
    )
    repair_meal_ingredients(draft, "KR", 2)
    assert quantities(draft)["물"] == 1300
    assert "밥" not in quantities(draft)


def test_existing_liquid_is_only_increased_and_units_converted():
    draft = meal(
        "닭고기카레",
        [("닭고기", 300, "g"), ("카레가루", 100, "g"), ("물", 0.2, "l"), ("식용유", 10, "ml")],
    )
    repair_meal_ingredients(draft, "KR", 2)
    waters = [i for i in draft["ingredients"] if i["name"] == "물"]
    assert waters == [
        {"name": "물", "quantity": Decimal("0.2"), "unit": "l"},
        {"name": "물", "quantity": Decimal("500"), "unit": "ml"},
    ]
    assert repair_meal_ingredients(draft, "KR", 2) == []


def test_household_scaling_and_english_names():
    draft = meal("chicken curry", [("chicken", 600, "g")])
    repair_meal_ingredients(draft, "US", 4)
    assert quantities(draft)["curry powder"] == 100
    assert quantities(draft)["water"] == 700
    assert quantities(draft)["cooking oil"] == 20


def test_free_water_alias_and_existing_pantry_alias_preserved():
    draft = meal(
        "시금치나물",
        [("시금치", 100, "g"), ("데침물", 1000, "ml"), ("조선간장", 10, "ml")],
        "시금치를 데쳐 국간장으로 무친다.",
    )
    assert repair_meal_ingredients(draft, "KR", 2) == []
    assert "국간장" not in quantities(draft)


async def test_real_generator_repairs_before_allergy_and_pricing(monkeypatch, db):
    from app.domains.mealplan import generator, service

    calls = []

    async def complete_json(*args):
        calls.append(1)
        return {
            "meals": [[1, "lunch", "닭고기카레", "끓여 낸다.", 20, "easy", [["닭고기", 300, "g"]]]]
        }

    monkeypatch.setattr(
        generator, "get_llm", lambda: SimpleNamespace(enabled=True, complete_json=complete_json)
    )
    drafts = await generator.generate_meals("KR", 2, "balanced", 1, 1, [], [])
    assert len(calls) == 1
    assert drafts.generation_source == "llm"
    assert service._check_allergies(drafts, ["카레가루"]) == ["카레가루"]
    total = await service._price(db, drafts, "KR", "KRW")
    curry = next(i for i in drafts[0]["ingredients"] if i["name"] == "카레가루")
    assert curry["est_cost"] == Decimal("1250.00")
    assert total > curry["est_cost"]


async def test_missing_ingredients_enter_needed_stock_and_consumption(db):
    from app.domains.auth.models import User
    from app.domains.fridge import service
    from app.domains.fridge.schemas import FridgeItemCreate, NeededItem

    user = User(nickname="재료검증", country="KR", currency="KRW")
    db.add(user)
    await db.flush()
    user_id = user.id
    draft = meal("닭고기카레", [("닭고기", 300, "g")])
    repair_meal_ingredients(draft, "KR", 2)
    needed = [NeededItem(**i) for i in draft["ingredients"]]
    before = await service.compute_shortfall(db, user_id, needed)
    assert next(i for i in before.items if i.name == "카레가루").to_buy == "50"
    await service.add_items(
        db, user_id, [FridgeItemCreate(**i, source="manual") for i in draft["ingredients"]]
    )
    stocked = await service.compute_shortfall(db, user_id, needed)
    assert all(i.to_buy == "0" for i in stocked.items)
    consumed = await service.deduct(db, user_id, needed)
    assert all(i.requested == i.deducted for i in consumed.items)
    assert await service.list_items(db, user_id) == []


@pytest.mark.parametrize(
    "name,qty,unit,amount",
    [
        ("카레가루", "50", "g", "1250"),
        ("국간장", "10", "ml", "100"),
        ("식초", "9", "ml", "20"),
        ("참깨", "2", "g", "60"),
        ("데침물", "2000", "ml", "0"),
    ],
)
async def test_added_price_references_work_without_seed(db, name, qty, unit, amount):
    from app.domains.mealplan.pricing import DBPriceProvider

    assert await DBPriceProvider(db).estimate_cost(
        name, Decimal(qty), unit, "KR", "KRW"
    ) == Decimal(amount)


@pytest.mark.parametrize(
    "name,allergies,blocked",
    [
        ("계란볶음밥", ["계란"], "계란"),
        ("두부구이", ["대두"], "두부"),
        ("닭고기카레", ["밀"], "카레가루"),
        ("무두부국", ["소금"], "소금"),
    ],
)
def test_allergy_is_checked_before_adding_and_skip_is_logged(caplog, name, allergies, blocked):
    draft = meal(name)
    changes = repair_meal_ingredients(draft, "KR", 2, allergies)
    assert blocked in changes.allergy_conflicts
    assert blocked not in quantities(draft)
    assert any(r.message == "mealplan_ingredient_repair_skipped" for r in caplog.records)
    assert all(r.reason in {"allergy_constraint", "unverified_composition"} for r in caplog.records)
    assert not any(a in caplog.text for a in allergies)


async def test_repaired_cost_drives_over_budget_without_reducing_quantities(monkeypatch, db):
    from app.domains.auth.models import User
    from app.domains.budget.models import BudgetPlan
    from app.domains.mealplan import generator, llm, service

    user = User(nickname="예산검증", country="KR", currency="KRW")
    db.add(user)
    await db.flush()
    budget = BudgetPlan(
        user_id=user.id,
        household_size=2,
        amount=Decimal("100000"),
        currency="KRW",
        meal_direction="health",
        source="onboarding",
    )

    async def complete_json(*args):
        return {
            "meals": [[1, "lunch", "닭고기카레", "끓여 낸다.", 20, "easy", [["닭고기", 300, "g"]]]]
        }

    monkeypatch.setattr(
        generator, "get_llm", lambda: SimpleNamespace(enabled=True, complete_json=complete_json)
    )
    # 이 테스트에서는 예산 재호출을 끄고 실제 생성→수리→가격→상태 경로를 검증한다.
    monkeypatch.setattr(llm, "get_llm", lambda: SimpleNamespace(enabled=False))
    drafts, status, total, notes = await service._generate_within_budget(
        db, budget, "KR", 1, 1, [], [], limit_amount=Decimal("1000")
    )
    assert status == "over_budget"
    assert total > 1000
    assert quantities(drafts[0])["카레가루"] == 50
    assert notes


def test_veggie_is_not_egg_and_vegan_dish_does_not_gain_eggs():
    draft = meal("Veggie Stir Fry", [("tofu", 300, "g"), ("cooking oil", 10, "ml")])
    repair_meal_ingredients(draft, "US", 2)
    assert "eggs" not in quantities(draft)


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN"])
def test_nonpositive_named_ingredient_is_repaired_even_if_not_in_short_steps(quantity):
    draft = meal("집밥", [("돼지고기 앞다리살", quantity, "g"), ("밥", 400, "g")])
    repair_meal_ingredients(draft, "KR", 2)
    assert quantities(draft)["돼지고기 앞다리살"] == 300
    assert repair_meal_ingredients(draft, "KR", 2) == []


def test_sprout_soup_is_not_a_separate_blanch_or_fried_egg_side():
    draft = meal(
        "콩나물국밥",
        [
            ("콩나물", 200, "g"),
            ("계란", 2, "ea"),
            ("밥", 400, "g"),
            ("멸치육수", 600, "ml"),
            ("소금", 2, "g"),
        ],
        "콩나물을 육수에 데친다.계란을 풀고 밥을 말아 낸다.",
    )
    assert repair_meal_ingredients(draft, "KR", 2) == []


def test_named_side_dish_in_steps_implies_blanching_even_without_blanch_verb():
    draft = meal(
        "고등어구이 정식",
        [("고등어", 2, "ea"), ("시금치", 110, "g"), ("밥", 400, "g")],
        "고등어를 굽고 시금치나물을 곁들인다.",
    )
    repair_meal_ingredients(draft, "KR", 2)
    assert quantities(draft)["물"] == 1000


def test_sprout_rice_and_egg_soup_do_not_imply_fried_egg_garnish():
    draft = meal(
        "콩나물밥과 계란국",
        [
            ("콩나물", 150, "g"),
            ("계란", 2, "ea"),
            ("밥", 400, "g"),
            ("멸치육수", 600, "ml"),
            ("소금", 2, "g"),
        ],
    )
    repair_meal_ingredients(draft, "KR", 2)
    assert quantities(draft)["물"] == 200
    assert "식용유" not in quantities(draft)


@pytest.mark.parametrize("time_expired", [False, True])
async def test_skipped_requirement_joins_existing_allergy_retry_policy(
    monkeypatch, db, time_expired
):
    from app.domains.auth.models import User
    from app.domains.budget.models import BudgetPlan
    from app.domains.mealplan import generator, llm, service

    user = User(nickname="알레르기검증", country="KR", currency="KRW")
    db.add(user)
    await db.flush()
    budget = BudgetPlan(
        user_id=user.id,
        household_size=2,
        amount=Decimal("1000000"),
        currency="KRW",
        meal_direction="health",
        source="onboarding",
    )
    calls = []

    async def complete_json(system, prompt):
        calls.append(prompt)
        if len(calls) == 1:
            return {
                "meals": [
                    [1, "lunch", "닭고기카레", "끓여 낸다.", 20, "easy", [["닭고기", 300, "g"]]]
                ]
            }
        assert "NEVER include these allergens" in prompt
        assert "카레가루" in prompt
        return {
            "meals": [
                [
                    1,
                    "lunch",
                    "무국",
                    "끓여 낸다.",
                    20,
                    "easy",
                    [["무", 200, "g"], ["물", 600, "ml"], ["소금", 2, "g"]],
                ]
            ]
        }

    fake = SimpleNamespace(enabled=True, complete_json=complete_json)
    monkeypatch.setattr(generator, "get_llm", lambda: fake)
    monkeypatch.setattr(llm, "get_llm", lambda: fake)
    if time_expired:
        ticks = iter((0.0, 26.0))
        monkeypatch.setattr(service, "monotonic", lambda: next(ticks))
    drafts, status, total, notes = await service._generate_within_budget(
        db, budget, "KR", 1, 1, ["밀"], [], limit_amount=Decimal("100000")
    )
    assert status == "ready"  # 시한 소진 뒤 warning + ready라는 기존 정책을 보존한다.
    assert "카레가루" not in quantities(drafts[0])
    if time_expired:
        assert len(calls) == 1
        assert "카레가루" in service._check_allergies(drafts, ["밀"])
        assert any("알레르기" in note for note in notes)
    else:
        assert len(calls) == 2
        assert drafts[0]["name"] == "무국"
        assert service._check_allergies(drafts, ["밀"]) == []
