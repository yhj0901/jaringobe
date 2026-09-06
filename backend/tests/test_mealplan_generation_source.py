"""실 LLM 없이 실패 진단 로그와 요청별 생성 출처를 검증한다."""

import json
import logging
from types import SimpleNamespace

import pytest

from app.core.logging import JsonFormatter
from app.domains.mealplan import generator
from app.domains.mealplan.llm import LLMClient, _extract_json


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("sk-test-secret PROMPT_PRIVATE"),
        json.JSONDecodeError("Expecting value", "PROMPT_PRIVATE sk-test-secret", 0),
        RuntimeError("PROMPT_PRIVATE sk-test-secret"),
    ],
)
async def test_failure_logs_safe_reason_and_marks_fallback(monkeypatch, caplog, error):
    class FailingLLM:
        enabled = True

        async def complete_json(self, *args):
            raise error

    monkeypatch.setattr(generator, "get_llm", lambda: FailingLLM())
    with caplog.at_level(logging.WARNING):
        result = await generator.generate_meals("KR", 2, "balanced", 7, 3, [], [])
    assert len(result) == 21
    assert result.generation_source == "fallback"
    record = next(r for r in caplog.records if r.message == "mealplan_generation_fallback")
    payload = json.loads(JsonFormatter().format(record))
    assert payload["error_type"] == type(error).__name__
    assert payload["error_message"]
    assert "PROMPT_PRIVATE" not in json.dumps(payload)
    assert "sk-test-secret" not in json.dumps(payload)
    assert record.exc_info is None


def test_http_failure_does_not_log_provider_body(caplog):
    class ProviderError(Exception):
        status_code = 429

    with caplog.at_level(logging.WARNING):
        generator._log_fallback(ProviderError("PRIVATE REQUEST BODY"))
    record = caplog.records[-1]
    assert record.http_status == 429
    assert record.error_message == "LLM API returned HTTP 429"
    assert "PRIVATE" not in JsonFormatter().format(record)


async def test_success_source_and_compact_output_keep_complete_quantities(monkeypatch):
    class SuccessLLM:
        enabled = True

        async def complete_json(self, system, prompt):
            assert "OUTPUT SIZE: Use compact JSON" in prompt
            assert "all required ingredients and full quantities" in prompt
            assert "same dish at most" not in prompt
            return {
                "meals": [
                    {
                        "day": 1,
                        "meal_type": "lunch",
                        "name": "두부구이",
                        "ingredients": [{"name": "두부", "quantity": 300, "unit": "g"}],
                    }
                ]
            }

    monkeypatch.setattr(generator, "get_llm", lambda: SuccessLLM())
    result = await generator.generate_meals("KR", 2, "balanced", 1, 1, [], [])
    assert result.generation_source == "llm"
    assert result[0]["ingredients"][0]["quantity"] == 300


async def test_disabled_llm_marks_fallback(monkeypatch):
    monkeypatch.setattr(generator, "get_llm", lambda: SimpleNamespace(enabled=False))
    result = await generator.generate_meals("US", 2, "balanced", 1, 1, [], [])
    assert result.generation_source == "fallback"


async def test_llm_logs_response_metadata_without_body(caplog):
    client = LLMClient()

    async def create(**kwargs):
        assert kwargs["max_tokens"] == 8000
        return SimpleNamespace(
            stop_reason="end_turn",
            usage=SimpleNamespace(output_tokens=42),
            content=[SimpleNamespace(type="text", text='{"private":"SECRET_BODY"}')],
        )

    client._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    with caplog.at_level(logging.INFO):
        assert await client.complete_json("SYSTEM_PRIVATE", "PROMPT_PRIVATE") == {
            "private": "SECRET_BODY"
        }
    record = next(r for r in caplog.records if r.message == "mealplan_llm_response")
    assert record.output_tokens == 42
    assert record.stop_reason == "end_turn"
    assert "PRIVATE" not in JsonFormatter().format(record)
    assert "SECRET_BODY" not in JsonFormatter().format(record)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('```json\n{"meals": []}\n```', {"meals": []}),
        ("result: [1, 2]", [1, 2]),
    ],
)
def test_extract_provider_json(raw, expected):
    assert _extract_json(raw) == expected


async def test_compact_wire_format_restores_public_draft(monkeypatch):
    class CompactLLM:
        enabled = True

        async def complete_json(self, system, prompt):
            assert "Meal columns:" in prompt
            return {
                "meals": [
                    [1, "lunch", "두부구이", "두부를 굽는다.", 10, "easy", [["두부", 300, "g"]]]
                ]
            }

    monkeypatch.setattr(generator, "get_llm", lambda: CompactLLM())
    result = await generator.generate_meals("KR", 2, "balanced", 1, 1, [], [])
    assert result.generation_source == "llm"
    assert result[0] == {
        "day": 1,
        "meal_type": "lunch",
        "name": "두부구이",
        "steps": "두부를 굽는다.",
        "time_minutes": 10,
        "difficulty": "easy",
        "ingredients": [{"name": "두부", "quantity": 300, "unit": "g"}],
    }


async def test_invalid_compact_shape_preserves_fallback(monkeypatch, caplog):
    class InvalidLLM:
        enabled = True

        async def complete_json(self, *args):
            return {"meals": [[1, "lunch"]]}

    monkeypatch.setattr(generator, "get_llm", lambda: InvalidLLM())
    result = await generator.generate_meals("KR", 2, "balanced", 1, 1, [], [])
    assert result.generation_source == "fallback"
    assert len(result) == 1
    assert caplog.records[-1].error_type == "ValueError"


@pytest.mark.parametrize("model,expected", [("claude-sonnet-5", {"effort": "low"}), ("claude-haiku-4-5", None)])
async def test_effort_only_sent_to_supported_model(model, expected):
    from app.core.config import Settings

    settings = Settings(_env_file=None, anthropic_api_key="", llm_model=model)
    client = LLMClient(settings)

    async def create(**kwargs):
        assert kwargs.get("output_config") == expected
        return SimpleNamespace(
            stop_reason="end_turn", usage=SimpleNamespace(output_tokens=1),
            content=[SimpleNamespace(type="text", text='{}')],
        )

    client._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    assert await client.complete_json("system", "user") == {}
