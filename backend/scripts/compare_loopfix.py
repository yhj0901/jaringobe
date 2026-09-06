"""명시적으로만 실행하는 유료 LLM 비교 (최대 3회, 실패 시 중단, 자동 재시도 없음).

전용 DB의 복제 기준가와 익명화한 동일 재고 힌트를 사용한다. pytest에서 호출하지 않는다.
backend에서 DATABASE_URL=.../jaringobe_loopfix uv run python scripts/compare_loopfix.py
--variant before|after --allow-paid-llm --credentials /승인된/.env 로 실행한다.
before는 지정 베이스의 생성기와 LLM 래퍼를 함께 읽는다.
"""

import argparse
import asyncio
import json
import os
import subprocess
import time
import types
from collections import Counter
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.domains.mealplan import generator
from app.domains.mealplan.llm import LLMClient
from app.domains.mealplan.service import _price


async def main(
    variant: str, trials: int, credentials: Path, output: Path | None, effort: str | None
) -> None:
    # 운영 DATABASE_URL 등 다른 설정은 절대 로드하지 않는다.
    secrets = dotenv_values(credentials)
    for key in ("ANTHROPIC_API_KEY", "LLM_MODEL"):
        if secrets.get(key):
            os.environ[key] = secrets[key]
    get_settings.cache_clear()
    settings = get_settings()
    url = make_url(settings.database_url)
    if url.database != "jaringobe_loopfix":
        raise ValueError("jaringobe_loopfix 전용 DB만 허용")
    fixture = json.loads(Path("reports/loopfix-input.json").read_text())
    module = generator
    client_class = LLMClient
    if variant == "before":
        source = subprocess.check_output(
            ["git", "show", "5e9b159:backend/app/domains/mealplan/generator.py"], text=True
        )
        module = types.ModuleType("baseline_generator")
        exec(compile(source, "baseline_generator.py", "exec"), module.__dict__)
        llm_source = subprocess.check_output(
            ["git", "show", "5e9b159:backend/app/domains/mealplan/llm.py"], text=True
        )
        llm_module = types.ModuleType("baseline_llm")
        exec(compile(llm_source, "baseline_llm.py", "exec"), llm_module.__dict__)
        client_class = llm_module.LLMClient
    llm = client_class(settings)
    if not llm.enabled:
        raise ValueError("실 LLM 키가 필요함")
    original = llm.complete_json
    failures: list[str] = []
    responses: list[dict] = []
    create_message = llm._client.messages.create

    async def observed_message(**kwargs):
        if effort is not None:
            kwargs["output_config"] = {"effort": effort}
        response = await create_message(**kwargs)
        responses.append(
            {
                "stop_reason": response.stop_reason,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
        )
        return response

    llm._client.messages.create = observed_message

    async def observed(*args, **kwargs):
        try:
            return await original(*args, **kwargs)
        except Exception as exc:
            # 키/본문/개인정보가 포함될 수 있는 예외 문자열은 기록하지 않는다.
            failures.append(type(exc).__name__)
            raise

    llm.complete_json = observed
    module.get_llm = lambda: llm
    engine = create_async_engine(
        url, connect_args={"server_settings": {"default_transaction_read_only": "on"}}
    )
    results = []
    try:
        async with async_sessionmaker(engine)() as db:
            for trial in range(1, trials + 1):
                failures.clear()
                responses.clear()
                started = time.monotonic()
                meals = await module.generate_meals(
                    budget_hint=(
                        f"TOTAL PLAN BUDGET: {fixture['limit']} KRW for all 21 meals. "
                        "Keep the full ingredient usage cost within this limit, including ingredients "
                        "already in the fridge; the server handles stock subtraction separately."
                    )
                    if variant == "after"
                    else "",
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
                )
                total = await _price(db, meals, "KR", "KRW")
                names = {i["name"].strip().casefold() for m in meals for i in m["ingredients"]}
                stocked = names & {n.strip().casefold() for n in fixture["stock_names"]}
                result = {
                    "effort_override": effort,
                    "trial": trial,
                    "seconds": round(time.monotonic() - started, 2),
                    "meals": len(meals),
                    "unique_menus": len({m["name"] for m in meals}),
                    "cost_krw": str(total),
                    "stocked_kinds": len(stocked),
                    "ingredient_kinds": len(names),
                    "stock_usage_ratio": len(stocked) / len(names),
                    "llm_errors": list(failures),
                    "generation_source": getattr(meals, "generation_source", None),
                    "llm_responses": list(responses),
                    "menu_counts": dict(Counter(m["name"] for m in meals)),
                    "drafts": meals,
                }
                results.append(result)
                (output or Path(f"reports/loopfix-{variant}.json")).write_text(
                    json.dumps(
                        {"variant": variant, "model": settings.llm_model, "runs": results},
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    )
                    + "\n"
                )
                print(
                    json.dumps(
                        {k: v for k, v in result.items() if k != "drafts"}, ensure_ascii=False
                    ),
                    flush=True,
                )
                if failures:
                    break  # 실패 시 원인부터 확인; 유료 폴백 표본을 반복하지 않는다.
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("before", "after"), required=True)
    parser.add_argument("--allow-paid-llm", action="store_true", required=True)
    parser.add_argument("--trials", type=int, choices=range(1, 4), default=3)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--effort", choices=("low", "medium"))
    args = parser.parse_args()
    asyncio.run(main(args.variant, args.trials, args.credentials, args.output, args.effort))
