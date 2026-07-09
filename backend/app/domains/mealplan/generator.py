"""식단 생성 — LLM(Claude) + mock 폴백.

반환 draft: {"day","meal_type","name","steps","ingredients":[{"name","quantity":Decimal,"unit"}]}
"""

from __future__ import annotations

from decimal import Decimal

from app.domains.mealplan.llm import get_llm

MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack", "supper"]

_RECIPES: dict[str, list[dict]] = {
    "KR": [
        {"name": "된장찌개+공깃밥", "ingredients": [
            {"name": "두부", "quantity": "1", "unit": "ea"},
            {"name": "된장", "quantity": "30", "unit": "g"},
            {"name": "애호박", "quantity": "1", "unit": "ea"},
            {"name": "쌀", "quantity": "400", "unit": "g"}]},
        {"name": "제육볶음", "ingredients": [
            {"name": "돼지고기앞다리", "quantity": "500", "unit": "g"},
            {"name": "양파", "quantity": "1", "unit": "ea"},
            {"name": "고추장", "quantity": "40", "unit": "g"},
            {"name": "쌀", "quantity": "400", "unit": "g"}]},
        {"name": "계란볶음밥", "ingredients": [
            {"name": "계란", "quantity": "4", "unit": "ea"},
            {"name": "쌀", "quantity": "400", "unit": "g"},
            {"name": "대파", "quantity": "1", "unit": "ea"}]},
        {"name": "김치찌개", "ingredients": [
            {"name": "김치", "quantity": "300", "unit": "g"},
            {"name": "돼지고기앞다리", "quantity": "300", "unit": "g"},
            {"name": "두부", "quantity": "1", "unit": "ea"}]},
        {"name": "닭볶음탕", "ingredients": [
            {"name": "닭고기", "quantity": "800", "unit": "g"},
            {"name": "감자", "quantity": "2", "unit": "ea"},
            {"name": "당근", "quantity": "1", "unit": "ea"}]},
        {"name": "미역국+밥", "ingredients": [
            {"name": "미역", "quantity": "20", "unit": "g"},
            {"name": "소고기", "quantity": "200", "unit": "g"},
            {"name": "쌀", "quantity": "400", "unit": "g"}]},
    ],
    "US": [
        {"name": "Chicken & Rice Bowl", "ingredients": [
            {"name": "chicken breast", "quantity": "500", "unit": "g"},
            {"name": "rice", "quantity": "400", "unit": "g"},
            {"name": "broccoli", "quantity": "1", "unit": "ea"}]},
        {"name": "Spaghetti Bolognese", "ingredients": [
            {"name": "ground beef", "quantity": "500", "unit": "g"},
            {"name": "spaghetti", "quantity": "400", "unit": "g"},
            {"name": "tomato sauce", "quantity": "1", "unit": "ea"}]},
        {"name": "Scrambled Eggs & Toast", "ingredients": [
            {"name": "eggs", "quantity": "6", "unit": "ea"},
            {"name": "bread", "quantity": "1", "unit": "ea"},
            {"name": "butter", "quantity": "30", "unit": "g"}]},
        {"name": "Bean Chili", "ingredients": [
            {"name": "canned beans", "quantity": "2", "unit": "ea"},
            {"name": "ground beef", "quantity": "400", "unit": "g"},
            {"name": "onion", "quantity": "1", "unit": "ea"}]},
        {"name": "Veggie Stir Fry", "ingredients": [
            {"name": "tofu", "quantity": "400", "unit": "g"},
            {"name": "mixed vegetables", "quantity": "500", "unit": "g"},
            {"name": "rice", "quantity": "400", "unit": "g"}]},
        {"name": "Oatmeal & Banana", "ingredients": [
            {"name": "oats", "quantity": "300", "unit": "g"},
            {"name": "banana", "quantity": "4", "unit": "ea"},
            {"name": "milk", "quantity": "1000", "unit": "ml"}]},
    ],
}

_SYSTEM = (
    "You are a meal-planning assistant for JARINGOBE, a budget grocery app. "
    "HARD CONSTRAINTS: never include any ingredient the user is allergic to; "
    "keep meals realistic, healthy, culturally appropriate for the region; "
    "prefer affordable ingredients to fit the budget. Return ONLY valid JSON."
)


def _mock(region: str, days: int, meals_per_day: int) -> list[dict]:
    bank = _RECIPES.get(region.upper(), _RECIPES["KR"])
    out: list[dict] = []
    idx = 0
    for day in range(1, days + 1):
        for m in range(meals_per_day):
            r = bank[idx % len(bank)]
            idx += 1
            out.append({
                "day": day,
                "meal_type": MEAL_TYPES[m % len(MEAL_TYPES)],
                "name": r["name"],
                "steps": None,
                "ingredients": [
                    {"name": i["name"], "quantity": Decimal(i["quantity"]), "unit": i["unit"]}
                    for i in r["ingredients"]
                ],
            })
    return out


def _prompt(
    region: str, household_size: int, meal_direction: str, days: int, meals_per_day: int,
    allergies: list[str], preferences: list[str], budget_hint: str,
) -> str:
    lines = [
        f"Region: {region}",
        f"Household size: {household_size}",
        f"Meal direction: {meal_direction}",
        f"Allergies (AVOID strictly): {allergies}",
        f"Preferences: {preferences}",
        f"Plan: {days} days x {meals_per_day} meals/day",
    ]
    if budget_hint:
        lines.append(budget_hint)
    lines.append(
        'Return JSON: {"meals":[{"day":1,"meal_type":"breakfast","name":"...",'
        '"steps":"...","ingredients":[{"name":"...","quantity":1,"unit":"g|ml|ea"}]}]}'
    )
    return "\n".join(lines)


async def generate_meals(
    region: str, household_size: int, meal_direction: str, days: int, meals_per_day: int,
    allergies: list[str], preferences: list[str], budget_hint: str = "",
) -> list[dict]:
    llm = get_llm()
    if not llm.enabled:
        return _mock(region, days, meals_per_day)

    try:
        data = await llm.complete_json(
            _SYSTEM,
            _prompt(region, household_size, meal_direction, days, meals_per_day,
                    allergies, preferences, budget_hint),
        )
    except Exception:
        # api-spec v1.1 §3-2: LLM 실패(타임아웃 포함)는 5xx 가 아니라 규칙 기반 폴백 생성
        return _mock(region, days, meals_per_day)
    meals_raw = data.get("meals", []) if isinstance(data, dict) else data
    drafts: list[dict] = []
    for m in meals_raw:
        ings = []
        for i in m.get("ingredients", []):
            try:
                qty = Decimal(str(i.get("quantity", "1")))
            except Exception:
                qty = Decimal("1")
            ings.append({"name": str(i.get("name", "")).strip(),
                         "quantity": qty, "unit": str(i.get("unit", "ea")).strip()})
        drafts.append({
            "day": int(m.get("day", 1)),
            "meal_type": str(m.get("meal_type", "meal")),
            "name": str(m.get("name", "")).strip(),
            "steps": m.get("steps"),
            "ingredients": ings,
        })
    return drafts
