"""시드 누락에도 유지할 기본 재료 추정 정책. 가격 근거는 reports/pricing-review.md.

물은 수도요금 제외 정책, 양념은 포장 가격을 사용량에 안분한다. 후추/참기름은
중량당 저가가 아니므로 단가를 임의로 낮추지 않고 최소 비용 바닥값만 제거한다.
US 값은 환율 변환이 아닌 독립적인 초기 추정치이며 실시간 시세가 아니다.
"""

from dataclasses import dataclass
from decimal import Decimal

FREE_WATER_NAMES = frozenset(
    {
        "물",
        "수돗물",
        "데침물",
        "삶는물",
        "삶는 물",
        "조리용 물",
        "water",
        "tap water",
        "cooking water",
        "blanching water",
    }
)


def normalize_name(name: str) -> str:
    return " ".join(name.casefold().split())


@dataclass(frozen=True)
class PantryPrice:
    names: tuple[str, ...]
    unit: str
    pack_qty: Decimal
    krw: Decimal
    usd: Decimal
    serving_qty: Decimal


# 소금 1kg, 후추 50g, 설탕 1kg, 콩기름 1.5L, 참기름 320ml.
# 동일 상수를 미등록 폴백과 명시적 DB 시드에서 공유하여 가격 이중 관리를 방지한다.
PANTRY_PRICES = (
    PantryPrice(
        ("소금", "salt", "table salt", "천일염", "꽃소금"),
        "g",
        Decimal("1000"),
        Decimal("2200"),
        Decimal("2"),
        Decimal("1"),
    ),
    PantryPrice(
        ("후추", "흑후추", "후춧가루", "후추가루", "pepper", "black pepper", "ground black pepper"),
        "g",
        Decimal("50"),
        Decimal("5400"),
        Decimal("2"),
        Decimal("0.1"),
    ),
    PantryPrice(
        ("설탕", "sugar", "white sugar", "granulated sugar"),
        "g",
        Decimal("1000"),
        Decimal("2400"),
        Decimal("2"),
        Decimal("4"),
    ),
    PantryPrice(
        (
            "식용유",
            "콩기름",
            "카놀라유",
            "vegetable oil",
            "cooking oil",
            "soybean oil",
            "canola oil",
        ),
        "ml",
        Decimal("1500"),
        Decimal("6800"),
        Decimal("5"),
        Decimal("5"),
    ),
    PantryPrice(
        ("참기름", "sesame oil"), "ml", Decimal("320"), Decimal("8500"), Decimal("7"), Decimal("3")
    ),
    # E: 일반 올리브유 500ml 포장 8000원/US $7 자체 추정(콩기름과 분리).
    PantryPrice(
        ("올리브유", "olive oil"),
        "ml",
        Decimal("500"),
        Decimal("8000"),
        Decimal("7"),
        Decimal("5"),
    ),
    # E: 2026-09-08 자체 초기 추정, 실시간 조회/특정 상품 가격 아님.
    # 카레분 100g 4인분 소매 포장 2500원/US $3, 국간장 1L 10000원/US $8.
    # 국간장은 진간장과 용도·염도가 달라 별도 이름/기준가로 유지한다.
    PantryPrice(
        ("카레가루", "카레 가루", "카레분말", "카레분", "고형카레", "curry powder", "curry roux"),
        "g",
        Decimal("100"),
        Decimal("2500"),
        Decimal("3"),
        Decimal("25"),
    ),
    PantryPrice(
        ("국간장", "국 간장", "조선간장", "soup soy sauce"),
        "ml",
        Decimal("1000"),
        Decimal("10000"),
        Decimal("8"),
        Decimal("5"),
    ),
    # E: 양조식초 900ml 2000원/US $2, 볶은 참깨 100g 3000원/US $3 포장 가정.
    PantryPrice(
        ("식초", "양조식초", "vinegar", "rice vinegar"),
        "ml",
        Decimal("900"),
        Decimal("2000"),
        Decimal("2"),
        Decimal("5"),
    ),
    PantryPrice(
        ("깨", "참깨", "통깨", "깨소금", "sesame seeds"),
        "g",
        Decimal("100"),
        Decimal("3000"),
        Decimal("3"),
        Decimal("1"),
    ),
)


def pantry_cost(
    name: str, quantity: Decimal, unit: str, region: str, currency: str
) -> Decimal | None:
    """알려진 기본 재료만 처리; 생수/육수/부분문자열은 무료로 분류하지 않는다."""
    normalized = normalize_name(name)
    if normalized in FREE_WATER_NAMES:
        return Decimal("0")
    if (region, currency) not in {("KR", "KRW"), ("US", "USD")}:
        return None
    for price in PANTRY_PRICES:
        if normalized not in price.names:
            continue
        # LLM 기본 단위 g/ml/ea 외 계량도 수용. 부피↔중량은 밀도 1의 초기 근사이며,
        # 모호한 단위(ea/약간 등)는 한 번의 소량 사용량으로 추정한다 (난수 미사용).
        factor = {
            "g": "1",
            "ml": "1",
            "kg": "1000",
            "l": "1000",
            "tsp": "5",
            "tbsp": "15",
            "pinch": "0.3",
        }.get(unit.strip().lower())
        used = quantity * (Decimal(factor) if factor else price.serving_qty)
        amount = price.krw if currency == "KRW" else price.usd
        return amount * used / price.pack_qty
    return None
