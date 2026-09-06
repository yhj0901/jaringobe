"""KR 초기 기준가 추정 카탈로그 — 실시간 가격이 아님 (2026-09-06 작성).

출처·환산 근거: reports/pricing-review.md. A=농식품부 2026-03-30 자료 규모 참고,
B=참가격 조회 화면 참고, E=포장/조리 상태를 명시한 자체 추정. 모두 반올림한
초기값이며 특정 브랜드/원산지 가격을 모든 재료에 동일하다고 보증하지 않는다.
운영 SELECT의 40종 전부와 한·영 별칭, KR 규칙 생성기의 일부 ea 단위를 포함한다.
"""

from decimal import Decimal

from app.domains.mealplan.pantry_prices import FREE_WATER_NAMES, PANTRY_PRICES

# (정확히 일치하는 별칭들, 단위, 포장 수량, 포장 가격 KRW, 근거)
KR_PRICE_ESTIMATES = (
    (("김", "gim", "nori"), "ea", "10", "2000", "E: 전장 김 10장"),
    (("무", "radish", "daikon"), "g", "1500", "2000", "A: 무 1개 약 1.5kg"),
    (("밥", "cooked rice"), "g", "1000", "1500", "E: 쌀 400g → 밥 1kg, 조리비 여유"),
    (("쌀", "rice", "uncooked rice"), "g", "20000", "63000", "A: 쌀 20kg"),
    (("간장", "soy sauce"), "ml", "860", "7800", "B: 진간장 860ml"),
    (("감자", "potato", "potatoes"), "g", "1000", "5500", "A: 감자 100g 560원 규모"),
    (("계란", "달걀", "egg", "eggs"), "ea", "30", "6900", "A: 일반 계란 30개"),
    (("당근", "carrot"), "g", "1000", "3400", "A: 당근 1kg"),
    (("당면", "glass noodles"), "g", "300", "3500", "B: 자른 당면 300g"),
    (("대파", "green onion", "scallion"), "g", "1000", "3100", "A: 대파 1kg"),
    (("된장", "doenjang", "soybean paste"), "g", "1000", "9000", "B: 재래식 된장 1kg"),
    (("두부", "tofu"), "g", "300", "1600", "B: 일반 찌개두부 300g"),
    (("마늘", "garlic"), "g", "1000", "12500", "A: 깐마늘 1kg"),
    (("버터", "butter"), "g", "450", "9000", "E: 버터 450g 포장"),
    (("삼치", "spanish mackerel"), "ea", "1", "4500", "E: 손질 생선 1토막 약 200g"),
    (("식빵", "bread", "sliced bread"), "ea", "12", "3600", "E: 한 봉지 12조각"),
    (("양파", "onion"), "g", "1000", "2000", "A: 양파 1kg"),
    (("우유", "milk"), "ml", "1000", "3000", "E: 일반 우유 1L"),
    (("고등어", "mackerel"), "ea", "1", "3000", "E: 손질 생선 1토막 약 150g"),
    (("고추장", "gochujang"), "g", "1000", "17000", "B: 고추장 1kg"),
    (("단무지", "pickled radish"), "g", "400", "2500", "E: 단무지 400g 포장"),
    (("닭고기", "chicken"), "g", "1000", "7000", "A: 일반 닭 1kg 규모, 부위 미지정"),
    (("소고기", "beef"), "g", "100", "3500", "E: 수입/일반 국거리 추정, 한우 등심 아님"),
    (("순두부", "soft tofu", "silken tofu"), "g", "350", "1500", "E: 순두부 350g 포장"),
    (("시금치", "spinach"), "g", "100", "800", "A: 시금치 100g"),
    (("시리얼", "cereal"), "g", "600", "8000", "B: 콘 시리얼 600g"),
    (("애호박", "zucchini"), "g", "300", "1800", "A: 애호박 1개 약 300g"),
    (("오징어", "squid"), "g", "300", "4500", "E: 손질 오징어 300g"),
    (("콩나물", "soybean sprouts", "bean sprouts"), "g", "380", "1800", "B: 콩나물 380g"),
    (
        ("고춧가루", "고추가루", "gochugaru", "red pepper flakes"),
        "g",
        "1000",
        "57000",
        "B: 국산 고춧가루 1kg, 수입/벌크는 더 낮을 수 있음",
    ),
    (("다진마늘", "다진 마늘", "minced garlic"), "g", "1000", "12500", "A/E: 깐마늘과 동가 근사"),
    (("돼지고기", "pork"), "g", "100", "1800", "E: 일반 찌개용, 삼겹살보다 낮게 추정"),
    (
        ("멸치육수", "anchovy stock", "anchovy broth"),
        "ml",
        "1000",
        "500",
        "E: 직접 낸 희석 육수 1L, 농축액 아님",
    ),
    (("배추김치", "김치", "kimchi"), "g", "1000", "8000", "E: 일반 배추김치 1kg"),
    (("칼국수면", "kalguksu noodles"), "g", "600", "3000", "E: 생 칼국수면 600g"),
    (
        ("돼지고기 앞다리살", "돼지고기앞다리", "pork shoulder"),
        "g",
        "100",
        "1400",
        "E: 앞다리살 100g, 구이용 삼겹살과 구분",
    ),
    (("두부", "tofu"), "ea", "1", "1600", "E: 두부 1모 300g"),
    (("애호박", "zucchini"), "ea", "1", "1800", "E: 애호박 1개 300g"),
    (("양파", "onion"), "ea", "1", "400", "E: 양파 1개 200g"),
    (("대파", "green onion", "scallion"), "ea", "1", "310", "E: 대파 1대 100g"),
    (("감자", "potato", "potatoes"), "ea", "1", "1100", "E: 감자 1개 200g"),
    (("당근", "carrot"), "ea", "1", "680", "E: 당근 1개 200g"),
)


def kr_price_rows() -> list[dict]:
    rows: list[dict] = [
        {
            "name": name,
            "region": "KR",
            "unit": unit,
            "pack_qty": Decimal(qty),
            "unit_price": Decimal(amount),
            "currency": "KRW",
        }
        for names, unit, qty, amount, _source in KR_PRICE_ESTIMATES
        for name in names
    ]
    rows.extend(
        {
            "name": name,
            "region": "KR",
            "unit": price.unit,
            "pack_qty": price.pack_qty,
            "unit_price": price.krw,
            "currency": "KRW",
        }
        for price in PANTRY_PRICES
        for name in price.names
    )
    rows.extend(
        {
            "name": name,
            "region": "KR",
            "unit": "ml",
            "pack_qty": Decimal("1000"),
            "unit_price": Decimal("0"),
            "currency": "KRW",
        }
        for name in sorted(FREE_WATER_NAMES)
    )
    return rows
