"""배송 재료의 소진 우선순위를 위한 보관 기간 추정 카탈로그.

제조사 소비기한이나 섭취 안전 보증이 아니다. 신선식품은 냉장, 건조 재료·양념은
통상 보관을 가정한 자체 추정치이며 실제 포장 표시/보관 상태가 우선한다.
입고 UTC 날짜에 일수를 더한다(기존 fridge_hint의 UTC 날짜 판정과 동일).
포장/개봉/냉동 여부 데이터가 없으므로 미등록 재료는 보수적으로 3일 후 소진을 권한다.
수동 등록의 사용자 지정 날짜에는 적용하지 않는다. 별도 DDL/가격 시드 의존성 없음.
"""

from datetime import date, timedelta

DEFAULT_SHELF_LIFE_DAYS = 3

# 정확한 별칭 일치만 허용: 소금빵을 소금의 365일로 오분류하지 않는다.
_ESTIMATES = (
    (
        2,
        (
            "닭고기",
            "닭가슴살",
            "chicken",
            "chicken breast",
            "ground beef",
            "돼지고기 다짐육",
            "다진 돼지고기",
            "ground pork",
            "minced pork",
            "삼치",
            "spanish mackerel",
            "고등어",
            "mackerel",
            "갈치",
            "hairtail",
            "오징어",
            "squid",
            "생선",
            "fish",
            "salmon",
            "연어",
        ),
    ),
    (
        3,
        (
            "돼지고기",
            "돼지고기앞다리",
            "돼지고기 앞다리살",
            "pork",
            "pork shoulder",
            "소고기",
            "소고기 불고기용",
            "beef",
            "두부",
            "tofu",
            "순두부",
            "soft tofu",
            "silken tofu",
            "시금치",
            "spinach",
            "콩나물",
            "bean sprouts",
            "soybean sprouts",
            "밥",
            "cooked rice",
            "멸치육수",
            "anchovy stock",
            "anchovy broth",
        ),
    ),
    (
        5,
        (
            "우유",
            "milk",
            "식빵",
            "bread",
            "sliced bread",
            "칼국수면",
            "kalguksu noodles",
            "떡국떡",
            "rice cakes",
            "바나나",
            "banana",
            "버섯",
            "mushrooms",
        ),
    ),
    (
        7,
        (
            "애호박",
            "zucchini",
            "대파",
            "green onion",
            "scallion",
            "broccoli",
            "브로콜리",
            "mixed vegetables",
            "다진마늘",
            "다진 마늘",
            "minced garlic",
            "배",
            "pear",
        ),
    ),
    (
        14,
        (
            "감자",
            "potato",
            "potatoes",
            "당근",
            "carrot",
            "무",
            "radish",
            "daikon",
            "양파",
            "onion",
            "마늘",
            "garlic",
        ),
    ),
    (21, ("계란", "달걀", "egg", "eggs")),
    (30, ("김치", "배추김치", "kimchi", "단무지", "pickled radish")),
    (60, ("버터", "butter")),
    (90, ("김", "gim", "nori", "시리얼", "cereal", "누룽지", "scorched rice")),
    (
        180,
        (
            "쌀",
            "rice",
            "uncooked rice",
            "당면",
            "glass noodles",
            "미역",
            "dried seaweed",
            "간장",
            "soy sauce",
            "된장",
            "doenjang",
            "soybean paste",
            "고추장",
            "gochujang",
            "고춧가루",
            "고추가루",
            "gochugaru",
            "red pepper flakes",
            "식용유",
            "콩기름",
            "vegetable oil",
            "cooking oil",
            "soybean oil",
            "참기름",
            "sesame oil",
            "spaghetti",
            "oats",
            "canned beans",
            "tomato sauce",
        ),
    ),
    (
        365,
        (
            "소금",
            "salt",
            "table salt",
            "천일염",
            "꽃소금",
            "설탕",
            "sugar",
            "white sugar",
            "granulated sugar",
            "후추",
            "흑후추",
            "후춧가루",
            "후추가루",
            "pepper",
            "black pepper",
            "ground black pepper",
        ),
    ),
)


def _normalize(name: str) -> str:
    return " ".join(name.casefold().split())


SHELF_LIFE_DAYS = {name: days for days, names in _ESTIMATES for name in names}


def estimate_expires_at(name: str, received_on: date) -> date:
    """미등록 재료도 날짜를 채워 다음 식단의 소진 우선순위에 포함한다."""
    days = SHELF_LIFE_DAYS.get(_normalize(name), DEFAULT_SHELF_LIFE_DAYS)
    return received_on + timedelta(days=days)
