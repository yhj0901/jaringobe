"""저장된 익명 실측의 무과금 재생: 규칙 누락/0수량/수량 하한/가격 효과를 분리한다.

자동 누락 수치는 알려진 규칙에만 해당한다. 사람의 독립적인 조리 검토를 대체하지 않는다.
"""

import asyncio
import json
import os
import time
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domains.mealplan.ingredient_requirements import (
    BROTHS,
    INGREDIENTS,
    PASTA,
    RAW_RICE,
    repair_meal_ingredients,
)
from app.domains.mealplan.service import _price

ROOT = Path(__file__).resolve().parents[1]


def normalize(name):
    return "".join(name.casefold().split())


def analyze(drafts):
    repaired = deepcopy(drafts)
    findings = []
    for index, (original, changed) in enumerate(zip(drafts, repaired, strict=True), 1):
        changes = repair_meal_ingredients(changed, "KR", 2)
        for change in changes:
            spec = next(s for s in INGREDIENTS.values() if change["name"] in s.names)
            names = {normalize(n) for n in spec.names}
            originals = [i for i in original["ingredients"] if normalize(i["name"]) in names]
            kind = "missing"
            if originals:
                kind = (
                    "quantity_topup"
                    if any(Decimal(i["quantity"]) > 0 for i in originals)
                    else "zero_quantity_repair"
                )
            elif spec.ko == "물":
                # 국 500ml→600ml는 물의 누락이 아니라 우리가 택한 수량 하한의 차이이다.
                # 데침/삶기/취사는 국물과 별도의 공정이므로 데침물 부재는 누락으로 센다.
                step_text = str(original.get("steps"))
                boiling = any(word in step_text for word in ("데치", "데쳐", "데친"))
                if any(word in normalize(step_text) for word in ("육수에데", "국물에데")):
                    boiling = False
                side_context = (original["name"] + step_text).replace("콩나물", "콩")
                boiling |= any(
                    word in side_context for word in ("나물", "시금치무침", "콩무침", "비빔밥")
                )
                boiling |= "장조림" in original["name"] or "콩나물밥" in original["name"]
                boiling |= any(
                    normalize(i["name"]) in {normalize(n) for n in (*PASTA, *RAW_RICE)}
                    for i in original["ingredients"]
                )
                if not boiling and any(
                    normalize(i["name"]) in {normalize(n) for n in BROTHS}
                    and Decimal(i["quantity"]) > 0
                    for i in original["ingredients"]
                ):
                    kind = "quantity_topup"
            findings.append({"meal": index, "dish": original["name"], "kind": kind, **change})
    return repaired, findings


async def main():
    url = make_url(os.environ["DATABASE_URL"])
    if url.database != "jaringobe_ingcheck" or url.host != "localhost" or url.port != 5433:
        raise ValueError("로컬 전용 DB만 허용")
    engine = create_async_engine(
        url, connect_args={"server_settings": {"default_transaction_read_only": "on"}}
    )
    results = []
    try:
        async with async_sessionmaker(engine)() as db:
            for variant in ("before", "after"):
                data = json.loads((ROOT / f"reports/ingredients-{variant}.json").read_text())
                for run in data["runs"]:
                    for draft in run["drafts"]:
                        for ingredient in draft["ingredients"]:
                            ingredient["quantity"] = Decimal(str(ingredient["quantity"]))
                    started = time.monotonic()
                    repaired, findings = analyze(run["drafts"])
                    milliseconds = (time.monotonic() - started) * 1000
                    current_prices_only = await _price(db, deepcopy(run["drafts"]), "KR", "KRW")
                    repaired_cost = await _price(db, repaired, "KR", "KRW")
                    zero = [
                        {"meal": idx, "dish": m["name"], **i}
                        for idx, m in enumerate(run["drafts"], 1)
                        for i in m["ingredients"]
                        if Decimal(i["quantity"]) <= 0
                    ]
                    row = {
                        "variant": variant,
                        "trial": run["trial"],
                        "missing_count": sum(f["kind"] == "missing" for f in findings),
                        "nonpositive_count": len(zero),
                        "topup_count": sum(f["kind"] == "quantity_topup" for f in findings),
                        "measured_cost": run["cost_krw"],
                        "price_only_cost": str(current_prices_only),
                        "paired_repaired_cost": str(repaired_cost),
                        "repair_cost_increase": str(repaired_cost - current_prices_only),
                        "paired_over_budget": repaired_cost > Decimal("102666.67"),
                        "rule_ms": round(milliseconds, 3),
                        "nonpositive_ingredients": zero,
                        "findings": findings,
                    }
                    results.append(row)
                    print(
                        json.dumps(
                            {
                                k: v
                                for k, v in row.items()
                                if k not in {"findings", "nonpositive_ingredients"}
                            },
                            ensure_ascii=False,
                        )
                    )
        (ROOT / "reports/ingredient-audit.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2, default=str) + "\n"
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
