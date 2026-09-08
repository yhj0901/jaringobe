"""요리명/조리 공정에서 유도한 재료 하한을 생성 draft에 보완한다.

완전한 레시피 검증기가 아니다. 알려진 요리/공정만 다루며 미등록 요리는 통과한다.
가격 별칭에 의존하지 않는다. steps 사전은 명시 누락을 보조할 뿐, 짧은 steps에
없는 데침물/팬 기름/취사 물은 요리명과 원재료에서 별도로 유도한다.
수량은 성인 1인 기준 조리용 추정 하한(가구 인원 배수)이며 예산/재고로 줄이지 않는다.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal


logger = logging.getLogger(__name__)


class IngredientRepairs(list[dict]):
    """보완 내역과 추가하지 못한 필수 재료를 호출부로 함께 전달한다."""

    def __init__(self) -> None:
        super().__init__()
        self.allergy_conflicts: set[str] = set()


@dataclass(frozen=True)
class Ingredient:
    ko: str
    en: str
    unit: str
    per_person: str
    aliases: tuple[str, ...] = ()

    @property
    def names(self) -> tuple[str, ...]:
        return (self.ko, self.en, *self.aliases)


# 가격 카탈로그와 분리된 조리 사전. 계량은 누락 시 적용하는 조리 가정이며 시세가 아니다.
INGREDIENTS = {
    "curry": Ingredient(
        "카레가루",
        "curry powder",
        "g",
        "25",
        ("카레 가루", "카레분말", "카레분", "고형카레", "curry roux"),
    ),
    "soup_soy": Ingredient("국간장", "soup soy sauce", "ml", "5", ("조선간장", "국 간장")),
    "soy": Ingredient("간장", "soy sauce", "ml", "5", ("진간장", "양조간장")),
    "scallion": Ingredient("대파", "green onion", "g", "10", ("scallion", "scallions")),
    "oil": Ingredient(
        "식용유",
        "cooking oil",
        "ml",
        "5",
        (
            "콩기름",
            "vegetable oil",
            "soybean oil",
            "카놀라유",
            "canola oil",
            "올리브유",
            "olive oil",
        ),
    ),
    "sesame_oil": Ingredient("참기름", "sesame oil", "ml", "3"),
    "butter": Ingredient("버터", "butter", "g", "5"),
    "water": Ingredient(
        "물",
        "water",
        "ml",
        "300",
        (
            "수돗물",
            "데침물",
            "삶는물",
            "삶는 물",
            "조리용 물",
            "tap water",
            "cooking water",
            "blanching water",
        ),
    ),
    "salt": Ingredient("소금", "salt", "g", "1", ("천일염", "꽃소금", "table salt")),
    "pepper": Ingredient("후추", "black pepper", "g", "0.1", ("후춧가루", "후추가루", "흑후추")),
    "garlic": Ingredient("다진마늘", "minced garlic", "g", "3", ("다진 마늘", "마늘", "garlic")),
    "sugar": Ingredient("설탕", "sugar", "g", "3"),
    "vinegar": Ingredient("식초", "vinegar", "ml", "5", ("양조식초", "rice vinegar")),
    "sesame": Ingredient("깨", "sesame seeds", "g", "1", ("참깨", "통깨", "깨소금")),
    "gochujang": Ingredient("고추장", "gochujang", "g", "10"),
    "doenjang": Ingredient("된장", "doenjang", "g", "15", ("soybean paste",)),
    "chili": Ingredient("고춧가루", "gochugaru", "g", "3", ("고추가루", "red pepper flakes")),
    "kimchi": Ingredient("김치", "kimchi", "g", "100", ("배추김치",)),
    "tofu": Ingredient("두부", "tofu", "g", "150"),
    "soft_tofu": Ingredient("순두부", "soft tofu", "g", "150", ("silken tofu",)),
    "spinach": Ingredient("시금치", "spinach", "g", "70"),
    "sprouts": Ingredient("콩나물", "bean sprouts", "g", "100", ("soybean sprouts",)),
    "radish": Ingredient("무", "radish", "g", "100", ("daikon",)),
    "egg": Ingredient("계란", "eggs", "ea", "1", ("달걀", "egg")),
    "chicken": Ingredient(
        "닭고기", "chicken", "g", "150", ("닭가슴살", "닭다리살", "chicken breast")
    ),
    "pork": Ingredient(
        "돼지고기",
        "pork",
        "g",
        "150",
        (
            "돼지고기 앞다리살",
            "돼지고기앞다리",
            "돼지고기 다짐육",
            "돼지고기다짐육",
            "pork shoulder",
            "ground pork",
        ),
    ),
    "beef": Ingredient("소고기", "beef", "g", "100", ("소고기 불고기용", "ground beef")),
    "onion": Ingredient("양파", "onion", "g", "50"),
    "carrot": Ingredient("당근", "carrot", "g", "30"),
    "potato": Ingredient("감자", "potato", "g", "100", ("potatoes",)),
    "zucchini": Ingredient("애호박", "zucchini", "g", "70"),
    "seaweed": Ingredient("미역", "seaweed", "g", "5"),
    "rice": Ingredient("밥", "cooked rice", "g", "200", ("공깃밥", "공기밥")),
}


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", value.casefold())


def _has(text: str, markers: tuple[str, ...]) -> bool:
    return any(_norm(marker) in text for marker in markers)


def _mentioned(text: str) -> set[str]:
    # 긴 이름 우선으로 소비한다: 국간장→간장, 참기름→기름, 순두부→두부 중복 방지.
    found = set()
    remaining = text.casefold()
    entries = sorted(
        ((alias, key) for key, spec in INGREDIENTS.items() for alias in spec.names),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    for alias, key in entries:
        # 한국어 조사/합성 요리명은 허용하되 '무침'의 무, '국물'의 물은 재료로 세지 않는다.
        if alias in {"무", "물", "깨", "밥"}:
            pattern = rf"(?<![가-힣]){alias}(?=$|[을를은는이가와과에로 ,.+])"
        elif alias.isascii():
            pattern = rf"(?<![a-z]){re.escape(alias)}(?![a-z])"
        else:
            pattern = re.escape(alias)
        remaining, count = re.subn(pattern, " ", remaining)
        if count:
            found.add(key)
    return found


def _quantity(ing: dict) -> Decimal:
    value = Decimal(str(ing["quantity"]))
    return value if value.is_finite() and value > 0 else Decimal("0")


def _amount(ingredients: list[dict], names: tuple[str, ...], unit: str) -> Decimal:
    normalized = {_norm(name) for name in names}
    total = Decimal("0")
    for ing in ingredients:
        if _norm(ing["name"]) not in normalized:
            continue
        factor = {unit: 1, "kg" if unit == "g" else "l": 1000}.get(ing["unit"].lower())
        if factor:
            total += _quantity(ing) * factor
    return total


BROTHS = (
    "멸치육수",
    "육수",
    "채수",
    "다시마육수",
    "닭육수",
    "anchovy stock",
    "anchovy broth",
    "vegetable broth",
    "chicken broth",
    "stock",
    "broth",
)
CURRY_SAUCES = (
    "카레소스",
    "카레 소스",
    "즉석카레",
    "레토르트카레",
    "curry sauce",
    "ready-made curry",
)
RAW_RICE = ("쌀", "백미", "현미", "rice", "uncooked rice", "brown rice")
PASTA = (
    "소면",
    "칼국수면",
    "당면",
    "스파게티",
    "파스타면",
    "국수면",
    "spaghetti",
    "pasta",
    "noodles",
    "glass noodles",
)


# 브랜드별 배합을 확인할 수 없는 가공 양념/혼합유는 알레르기 입력이 있으면 추가하지 않는다.
_UNVERIFIED_COMPOSITES = {"curry", "soup_soy", "soy", "doenjang", "gochujang", "oil"}
# 원재료 알레르기 이름도 함께 대조한다. 특정 제품의 무알레르기 보증으로 쓰지 않는다.
_ALLERGEN_NAMES = {
    "tofu": ("콩", "대두", "soy", "soybean"),
    "soft_tofu": ("콩", "대두", "soy", "soybean"),
    "sprouts": ("콩", "대두", "soy", "soybean"),
    "butter": ("우유", "유제품", "milk", "dairy"),
    "sesame_oil": ("깨", "참깨", "sesame"),
    "sesame": ("깨", "참깨", "sesame"),
}


def repair_meal_ingredients(
    meal: dict,
    region: str,
    household_size: int,
    allergies: list[str] | None = None,
) -> IngredientRepairs:
    """제자리 보완 + 변경 내역 반환. 기존 이름/양/steps 보존, 반복 적용해도 불변."""
    ingredients = meal["ingredients"]
    name = _norm(meal["name"])
    steps = str(meal.get("steps") or "")
    text = name + " " + _norm(steps)
    people = Decimal(household_size)
    changes = IngredientRepairs()
    allergs = [_norm(a) for a in (allergies or []) if a.strip()]

    def present(key: str) -> bool:
        aliases = {_norm(n) for n in INGREDIENTS[key].names}
        return any(_norm(i["name"]) in aliases and _quantity(i) > 0 for i in ingredients)

    def add(key: str, reason: str, quantity: Decimal | None = None) -> None:
        spec = INGREDIENTS[key]
        if key == "rice" and _amount(ingredients, RAW_RICE, "g") > 0:
            return
        if quantity is None and present(key):
            return
        qty = quantity if quantity is not None else Decimal(spec.per_person) * people
        if qty <= 0:
            return
        allergy_names = (*spec.names, *_ALLERGEN_NAMES.get(key, ()))
        if allergs and (
            key in _UNVERIFIED_COMPOSITES
            or any(a in _norm(alias) for a in allergs for alias in allergy_names)
        ):
            changes.allergy_conflicts.add(spec.ko if region.upper() == "KR" else spec.en)
            # 건강 입력/재료명/프롬프트 본문은 로그에 남기지 않는다.
            logger.warning(
                "mealplan_ingredient_repair_skipped",
                extra={
                    "event": "mealplan_ingredient_repair_skipped",
                    "reason": "unverified_composition"
                    if key in _UNVERIFIED_COMPOSITES
                    else "allergy_constraint",
                    "skipped_requirement_count": 1,
                },
            )
            return
        # 같은 이름·단위 행이 있으면 증량. 줄이거나 재고량으로 대체하지 않는다.
        aliases = {_norm(n) for n in spec.names}
        existing = next(
            (i for i in ingredients if _norm(i["name"]) in aliases and i["unit"] == spec.unit), None
        )
        if existing is not None:
            existing["quantity"] = _quantity(existing) + qty
            added_name = existing["name"]
        else:
            added_name = spec.ko if region.upper() == "KR" else spec.en
            ingredients.append({"name": added_name, "quantity": qty, "unit": spec.unit})
        changes.append({"name": added_name, "quantity": qty, "unit": spec.unit, "reason": reason})

    # 목록의 0/음수도 실물이 배송되지 않는 누락이다. 알려진 품목의 1인량으로만 복원한다.
    for ingredient in list(ingredients):
        if _quantity(ingredient) == 0:
            for key, spec in INGREDIENTS.items():
                if _norm(ingredient["name"]) in {_norm(n) for n in spec.names}:
                    add(key, "nonpositive_quantity")
                    break

    # 직접 명시된 재료는 조리 사전의 범위 내에서 보완. 선택/부정 표현은 추정하지 않는다.
    explicit = set()
    for clause in re.split(r"[.。\n]", steps):
        if not _has(_norm(clause), ("선택", "생략", "없이", "않", "optional", "without", "omit")):
            explicit |= _mentioned(clause)
    for key in sorted(explicit - {"water", "oil", "butter", "sesame_oil"}):
        add(key, "explicit_step")

    # 요리의 정체성을 이루는 명시 재료. '무침' 같은 접미사는 위의 사전과 별개로 다룬다.
    for key in (
        "kimchi",
        "doenjang",
        "soft_tofu",
        "spinach",
        "sprouts",
        "scallion",
        "chicken",
        "pork",
        "beef",
        "onion",
        "carrot",
        "potato",
        "zucchini",
        "seaweed",
    ):
        if _has(name, INGREDIENTS[key].names):
            add(key, "dish_identity")
    if _has(name, ("닭볶음탕", "찜닭")):
        add("chicken", "dish_identity")
    if _has(name, ("두부", "tofu")) and not _has(name, ("순두부", "soft tofu", "silken tofu")):
        add("tofu", "dish_identity")
    if _has(name, ("무국", "무두부국", "뭇국", "무조림", "radish soup")):
        add("radish", "dish_identity")
    if "egg" in _mentioned(meal["name"]) or re.search(r"\bomelet(?:te)?\b", meal["name"], re.I):
        add("egg", "dish_identity")
    if (
        _has(name, ("밥", "rice bowl", "fried rice"))
        and not present("rice")
        and not any(_norm(i["name"]) in {_norm(n) for n in RAW_RICE} for i in ingredients)
    ):
        add("rice", "dish_staple")

    curry = _has(name, ("카레", "커리", "curry")) and not any(
        _norm(i["name"]) in {_norm(n) for n in CURRY_SAUCES} for i in ingredients
    )
    if curry:
        add("curry", "curry_base")

    # 국수/국물볶음의 '국' 오탐 방지. 밥과 국이 한 끼에 있으면 공정별 물을 합산한다.
    soup = bool(re.search(r"(?:국|탕|찌개)(?:$|[+와과&]|정식|과밥)", name)) or _has(
        name, ("soup", "stew", "국밥")
    )
    braise = _has(name, ("조림", "찜닭", "김치찜", "braised")) or _has(
        _norm(steps), ("조린", "졸인", "조리다")
    )
    steam_egg = _has(name, ("계란찜", "달걀찜", "steamed egg"))
    porridge = _has(name, ("죽", "porridge", "congee"))
    cooking_water = Decimal("0")
    if curry:
        # 카레분 25g당 물 175ml: 100g/4인분 + 700ml의 조리 배합을 초기 가정으로 사용.
        cooking_water = max(25 * people, _amount(ingredients, INGREDIENTS["curry"].names, "g")) * 7
    elif soup or porridge:
        cooking_water = (400 if porridge else 300) * people
    elif braise or steam_egg:
        cooking_water = 100 * people
    cooking_water = max(Decimal("0"), cooking_water - _amount(ingredients, BROTHS, "ml"))

    # '콩나물'은 재료명: 콩나물국/콩나물밥을 나물 반찬으로 오분류하지 않는다.
    # 제목이 정식이어도 steps가 특정 나물 반찬을 명시하면 해당 공정이 필요하다.
    namul_context = name.replace("콩나물", "콩") + " " + _norm(steps).replace("콩나물", "콩")
    named_blanch = _has(namul_context, ("나물", "시금치무침", "콩무침", "비빔밥"))
    named_blanch = named_blanch and (present("spinach") or present("sprouts"))
    step_blanch = _has(_norm(steps), ("데치", "데친", "데쳐", "blanch"))
    broth_blanch = _has(_norm(steps), ("육수에데", "국물에데", "blanchinbroth"))
    blanch = named_blanch or (step_blanch and not broth_blanch)
    boiling_water = max(Decimal("1000"), 500 * people) if blanch else Decimal("0")
    # 완성 밥과 생 콩나물을 찌는 조리에는 취사 물과 별도로 소량의 찜 물을 잡는다.
    if "콩나물밥" in name and _amount(ingredients, RAW_RICE, "g") == 0:
        boiling_water += 100 * people
    if _has(name, ("계란장조림", "달걀장조림", "삶은계란", "삶은달걀", "boiled egg")):
        boiling_water += max(Decimal("1000"), 500 * people)
    if any(_norm(i["name"]) in {_norm(n) for n in PASTA} for i in ingredients):
        boiling_water += 1000 * people
    # 생쌀의 취사 물은 완성 밥과 구분. 죽은 위의 액체 하한에 이미 반영된다.
    rice_water = Decimal("0") if porridge else _amount(ingredients, RAW_RICE, "g") * Decimal("1.5")
    required_water = cooking_water + boiling_water + rice_water
    if "water" in explicit and required_water == 0:
        required_water = 300 * people
    add(
        "water",
        "cooking_liquid",
        required_water - _amount(ingredients, INGREDIENTS["water"].names, "ml"),
    )

    # 볶음탕은 국물 공정: 볶음 접미사와 구분하고 실제 볶기 steps가 있을 때 팬으로 판정.
    pan = bool(re.search(r"볶음(?!탕)", name)) or _has(
        name,
        (
            "볶은",
            "프라이",
            "후라이",
            "계란말이",
            "달걀말이",
            "두부구이",
            "부침",
            "팬케이크",
            "stir fry",
            "stir-fry",
            "fried",
            "scrambled",
            "omelet",
            "pancake",
        ),
    )
    pan = (
        pan
        or curry
        or _has(
            _norm(steps), ("볶", "부치", "부쳐", "프라이", "후라이", "팬에굽", "pan-fry", "saute")
        )
    )
    # 비빔밥/나물밥에 원란이 있으면 계란 고명을 익힐 팬 기름도 필요하다.
    pan = pan or (
        present("egg") and _has(name.replace("콩나물", "콩"), ("비빔밥", "나물밥", "bibimbap"))
    )
    no_pan_oil = _has(text, ("기름없이", "에어프라이", "air fryer", "oil-free", "without oil"))
    fats = ("oil", "sesame_oil", "butter")
    for key in sorted(explicit & set(fats)):
        add(key, "explicit_step")
    if pan and not no_pan_oil and not any(present(k) for k in ("oil", "butter")):
        # 마무리용 참기름은 계란 프라이/팬 볶음의 기름을 충당했다고 간주하지 않는다.
        add("oil", "pan_fat")
    # 무염/맹물 국이 되지 않도록 간이 되는 재료가 하나도 없을 때만 소금을 보완한다.
    if (soup or steam_egg) and not any(
        present(k) for k in ("salt", "soy", "soup_soy", "doenjang", "gochujang", "kimchi")
    ):
        add("salt", "soup_seasoning")
    return changes
