"""식단 생성 — LLM(Claude) + mock 폴백.

반환 draft: {"day","meal_type","name","steps","ingredients":[{"name","quantity":Decimal,"unit"}]}
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal

from app.domains.mealplan.generation_source import GenerationSource
from app.domains.mealplan.llm import get_llm

MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack", "supper"]
logger = logging.getLogger(__name__)


class MealDrafts(list[dict]):
    """리스트 호환 생성 결과에 출처를 실어 재시도/동시 요청 간 혼동을 방지한다."""

    def __init__(self, meals: list[dict], source: GenerationSource) -> None:
        super().__init__(meals)
        self.generation_source = GenerationSource(source)


def _log_fallback(error: Exception) -> None:
    # SDK 예외의 str/body/traceback에는 요청/응답 본문이 섞일 수 있다.
    # JSON 파서의 표준 오류 문구만 허용하고 그 외는 타입/상태별 안전한 요약을 쓴다.
    status = getattr(error, "status_code", None)
    stop_reason = getattr(error, "stop_reason", None)
    if stop_reason == "max_tokens":
        message = "LLM output reached max_tokens before completion"
    elif isinstance(error, json.JSONDecodeError):
        message = f"{error.msg} (line {error.lineno}, column {error.colno})"
    elif isinstance(status, int):
        message = f"LLM API returned HTTP {status}"
    elif isinstance(error, TimeoutError) or type(error).__name__ == "APITimeoutError":
        message = "LLM request timed out"
    else:
        message = "LLM generation failed; exception body omitted"
    logger.warning("mealplan_generation_fallback", extra={
        "event": "mealplan_generation_fallback", "generation_source": GenerationSource.FALLBACK,
        "error_type": type(error).__name__, "error_message": message,
        "http_status": status if isinstance(status, int) else None,
        "stop_reason": "max_tokens" if stop_reason == "max_tokens" else None,
    })

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


# 폴백 레시피 시트가 비지 않도록 지역별 기본 조리 단계 (parse_steps 가 줄바꿈 기준 분리)
_MOCK_STEPS = {
    "KR": "1. 재료를 손질해요.\n2. 팬이나 냄비에 재료를 넣고 익혀요.\n3. 간을 맞추고 그릇에 담아 완성해요.",
    "US": "1. Prep the ingredients.\n2. Cook them in a pan or pot.\n3. Season to taste and serve.",
}


def _mock(region: str, days: int, meals_per_day: int) -> list[dict]:
    bank = _RECIPES.get(region.upper(), _RECIPES["KR"])
    steps = _MOCK_STEPS.get(region.upper(), _MOCK_STEPS["KR"])
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
                "steps": steps,
                "time_minutes": 20,
                "difficulty": "easy",
                "ingredients": [
                    {"name": i["name"], "quantity": Decimal(i["quantity"]), "unit": i["unit"]}
                    for i in r["ingredients"]
                ],
            })
    return out


def _prompt(
    region: str, household_size: int, meal_direction: str, days: int, meals_per_day: int,
    allergies: list[str], preferences: list[str], budget_hint: str,
    household_desc: str = "",
    fridge_hint: str = "",
) -> str:
    lines = [
        f"Region: {region}",
        f"Household size: {household_size}",
        f"Meal direction: {meal_direction}",
        f"Allergies (AVOID strictly): {allergies}",
        f"Preferences: {preferences}",
        f"Plan: {days} days x {meals_per_day} meals/day",
        f"Return EXACTLY {days * meals_per_day} meals — one per meal_type per day, no duplicates.",
        "Dish and ingredient names in Korean only." if region == "KR" else "Dish and ingredient names in English only.",
    ]
    if household_desc:
        # 구성원 유형·나이 반영 (영양·식사량 개인화 힌트)
        lines.insert(2, f"Household members: {household_desc}")
    if budget_hint:
        lines.append(budget_hint)
    if fridge_hint:
        lines.append(fridge_hint)
    lines.append(
        "MEAL COMPLETENESS: Each entry must be a full meal with a staple and main, "
        "never a side dish alone. Quantities are TOTAL for the entire household above, "
        "not per person; do not shrink portions to fit fridge stock. "
        "EVERY ingredient required by the dish or used in steps, including water and "
        "seasonings, MUST appear in ingredients with its full quantity. "
        "The ingredients list is the shopping order: unlisted ingredients will not be delivered. "
        "Cross-check steps against that list; add missing quantities or rewrite the step. "
        "Use ONLY listed ingredients in steps; include broth/water for boiling and oil for frying. "
        "Keep ingredient names identical to fridge names when reusing stock."
    )
    # 21끼 상세 JSON이 60초 호출 상한을 넘지 않도록 불필요한 출력량을 줄인다.
    # 식단 다양성/재고 우선순위/필수 재료 수량은 바꾸지 않는다.
    lines.append(
        "OUTPUT SIZE: Use compact JSON without indentation or commentary. "
        "Keep each steps value to 3 short cooking instructions, at most 80 characters total. "
        "Use concise dish names. Include all required ingredients and full quantities, "
        "but omit optional garnishes and explanations."
    )
    lines.append(
        'Return JSON using positional arrays to avoid repeated keys: '
        '{"meals":[[1,"breakfast","dish name","steps",20,"easy",[["ingredient",1,"g"]]]]}. '
        'Meal columns: [day,meal_type,name,steps,time_minutes,difficulty,ingredients]. '
        'Ingredient columns: [name,quantity,unit]. '
        'difficulty: easy|normal|hard; unit: g|ml|ea. '
        'Return all requested meals, with no omitted days.'
    )
    return "\n".join(lines)


async def generate_meals(
    region: str, household_size: int, meal_direction: str, days: int, meals_per_day: int,
    allergies: list[str], preferences: list[str], budget_hint: str = "",
    household_desc: str = "",
    fridge_hint: str = "",
) -> list[dict]:
    llm = get_llm()
    if not llm.enabled:
        logger.info("mealplan_generation_fallback", extra={
            "event": "mealplan_generation_fallback", "generation_source": GenerationSource.FALLBACK,
            "error_type": "LLMDisabled", "error_message": "LLM is not configured",
        })
        return MealDrafts(_mock(region, days, meals_per_day), GenerationSource.FALLBACK)

    try:
        data = await llm.complete_json(
            _SYSTEM,
            _prompt(region, household_size, meal_direction, days, meals_per_day,
                    allergies, preferences, budget_hint, household_desc, fridge_hint),
        )
        return _parse_meals(data, days, meals_per_day)
    except Exception as exc:
        # api-spec v1.1 §3-2: LLM 실패(타임아웃 포함)는 5xx 가 아니라 규칙 기반 폴백 생성
        _log_fallback(exc)
        return MealDrafts(_mock(region, days, meals_per_day), GenerationSource.FALLBACK)


def _parse_meals(data: dict | list, days: int, meals_per_day: int) -> MealDrafts:
    meals_raw = data.get("meals", []) if isinstance(data, dict) else data
    drafts: list[dict] = []
    for m in meals_raw:
        # 전송만 압축한다. 기존 객체 형식도 받아 외부 draft/API 계약을 유지한다.
        if isinstance(m, list):
            m = dict(zip(
                ("day", "meal_type", "name", "steps", "time_minutes", "difficulty", "ingredients"),
                m, strict=True,
            ))
        ings = []
        for i in m.get("ingredients", []):
            if isinstance(i, list):
                i = dict(zip(("name", "quantity", "unit"), i, strict=True))
            try:
                qty = Decimal(str(i.get("quantity", "1")))
            except Exception:
                qty = Decimal("1")
            ings.append({"name": str(i.get("name", "")).strip(),
                         "quantity": qty, "unit": str(i.get("unit", "ea")).strip()})
        # time_minutes: 양의 정수만 채택, 그 외 None (프론트 기본값)
        tm: int | None
        try:
            parsed = int(m.get("time_minutes"))
            tm = parsed if parsed > 0 else None
        except (TypeError, ValueError):
            tm = None
        diff = m.get("difficulty")
        difficulty = diff if diff in ("easy", "normal", "hard") else None
        drafts.append({
            "day": int(m.get("day", 1)),
            "meal_type": str(m.get("meal_type", "meal")),
            "name": str(m.get("name", "")).strip(),
            "steps": m.get("steps"),
            "time_minutes": tm,
            "difficulty": difficulty,
            "ingredients": ings,
        })
    # LLM 이 한/영 중복 등으로 초과 반환하는 경우 방어: (day, meal_type) 당 1끼 + 총량 상한
    seen: set[tuple[int, str]] = set()
    unique: list[dict] = []
    for d in drafts:
        key = (d["day"], d["meal_type"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(d)
    return MealDrafts(unique[: days * meals_per_day], GenerationSource.LLM)
