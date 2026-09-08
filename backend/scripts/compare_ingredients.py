"""재료 충분성 전후 비교: 명시 승인, 로컬 전용 DB, 총 10회 상한, 재시도 없음.

동일 입력/프롬프트/low 모델로 baseline 614633d와 현재 생성기를 각각 3회 실행한다.
원본 draft를 보존하므로 규칙 검사 외 직접 조리 가능성 검토도 해야 한다.
"""

import argparse
import asyncio
import json
import os
import subprocess
import time
import types
from decimal import Decimal
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.domains.mealplan import generator
from app.domains.mealplan.llm import LLMClient
from app.domains.mealplan.service import _price

ROOT = Path(__file__).resolve().parents[1]


async def main(args):
    url = make_url(os.environ["DATABASE_URL"])
    if url.database != "jaringobe_ingcheck" or url.host != "localhost" or url.port != 5433:
        raise ValueError("localhost:5433/jaringobe_ingcheck만 허용")
    # 필요한 값만 선택한다. 운영 DATABASE_URL과 다른 외부 API 키는 로드하지 않는다.
    secrets = dotenv_values(args.credentials)
    settings = Settings(
        _env_file=None,
        database_url=str(url),
        anthropic_api_key=secrets.get("ANTHROPIC_API_KEY") or "",
        llm_model=secrets.get("LLM_MODEL") or "claude-sonnet-5",
    )
    if not settings.llm_enabled or not settings.llm_model.startswith("claude-sonnet-5"):
        raise ValueError("실 Sonnet 5 키/모델 필요")
    ledger = ROOT / "reports/ingredient-calls.json"
    calls = json.loads(ledger.read_text()) if ledger.exists() else []
    fixture = json.loads((ROOT / "reports/loopfix-input.json").read_text())
    module = generator
    if args.variant == "before":
        source = subprocess.check_output(
            ["git", "show", "614633d:backend/app/domains/mealplan/generator.py"], text=True
        )
        module = types.ModuleType("baseline_generator")
        exec(compile(source, "baseline_generator.py", "exec"), module.__dict__)
    llm = LLMClient(settings)
    module.get_llm = lambda: llm
    responses = []
    errors = []
    raw_responses = []
    original_log = module._log_fallback

    def log_failure(exc):
        errors.append(
            {"type": type(exc).__name__, "stop_reason": getattr(exc, "stop_reason", None)}
        )
        original_log(exc)

    module._log_fallback = log_failure
    create = llm._client.messages.create

    async def observed(**kwargs):
        assert kwargs.get("output_config") == {"effort": "low"}
        if len(calls) >= 10:
            raise RuntimeError("유료 호출 10회 상한")
        calls.append({"variant": args.variant, "call": len(calls) + 1})
        ledger.write_text(json.dumps(calls, indent=2) + "\n")
        response = await create(**kwargs)
        raw_responses.append([b.text for b in response.content if b.type == "text"])
        responses.append(
            {
                "stop_reason": response.stop_reason,
                "output_tokens": response.usage.output_tokens,
                "input_tokens": response.usage.input_tokens,
            }
        )
        return response

    llm._client.messages.create = observed
    engine = create_async_engine(
        url, connect_args={"server_settings": {"default_transaction_read_only": "on"}}
    )
    output = ROOT / f"reports/ingredients-{args.variant}.json"
    if output.exists():
        raise ValueError("기존 실측 덮어쓰기 금지")
    results = []
    try:
        async with async_sessionmaker(engine)() as db:
            for trial in range(1, 4):
                responses.clear()
                errors.clear()
                raw_responses.clear()
                started = time.monotonic()
                meals = await module.generate_meals(
                    **{
                        k: fixture[k]
                        for k in (
                            "region",
                            "household_size",
                            "meal_direction",
                            "days",
                            "meals_per_day",
                            "allergies",
                            "preferences",
                            "household_desc",
                            "fridge_hint",
                        )
                    },
                    budget_hint=(
                        f"TOTAL PLAN BUDGET: {fixture['limit']} KRW for all 21 meals. "
                        "Keep the full ingredient usage cost within this limit, including "
                        "ingredients already in the fridge; "
                        "the server handles stock subtraction separately."
                    ),
                )
                generation_seconds = time.monotonic() - started
                total = await _price(db, meals, "KR", "KRW")
                names = {i["name"].strip().casefold() for m in meals for i in m["ingredients"]}
                stock = {n.strip().casefold() for n in fixture["stock_names"]}
                used = names & stock
                result = {
                    "errors": list(errors),
                    "raw_responses": list(raw_responses),
                    "trial": trial,
                    "generation_seconds": round(generation_seconds, 3),
                    "total_seconds": round(time.monotonic() - started, 3),
                    "cost_krw": str(total),
                    "over_budget": total > Decimal(fixture["limit"]),
                    "generation_source": meals.generation_source,
                    "llm_responses": list(responses),
                    "stocked_kinds": len(used),
                    "ingredient_kinds": len(names),
                    "stock_usage_ratio": len(used) / len(names),
                    "stock_kinds_consumed_ratio": len(used) / len(stock),
                    "drafts": meals,
                }
                results.append(result)
                output.write_text(
                    json.dumps(
                        {
                            "variant": args.variant,
                            "base": "614633d",
                            "model": settings.llm_model,
                            "runs": results,
                        },
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    )
                    + "\n"
                )
                print(
                    json.dumps(
                        {k: v for k, v in result.items() if k not in {"drafts", "raw_responses"}},
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                if meals.generation_source != "llm":
                    raise RuntimeError("LLM 실패: 유료 호출 중단, 원인 확인 필요")
    finally:
        await llm._client.close()
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("before", "after"), required=True)
    parser.add_argument("--allow-paid-llm", action="store_true", required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
