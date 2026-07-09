"""Claude 호출 래퍼 — 키 없으면 mock 폴백. 타임아웃 + SDK 재시도."""

from __future__ import annotations

import json
import re

from app.core.config import Settings, get_settings

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
# 21끼(7일×3끼) JSON 생성은 수십 초 소요 — 프론트 타임아웃(90초) 안에서 단일 시도에 최대한 할애
LLM_TIMEOUT_SECONDS = 75.0
LLM_MAX_RETRIES = 0


def _extract_json(text: str) -> dict | list:
    text = text.strip()
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1).strip()
    candidates = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if candidates:
        text = text[min(candidates):]
    return json.loads(text)


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = None
        if self.settings.llm_enabled:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(
                api_key=self.settings.anthropic_api_key,
                timeout=LLM_TIMEOUT_SECONDS,
                max_retries=LLM_MAX_RETRIES,
            )

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def complete_json(self, system: str, user: str, max_tokens: int = 8000) -> dict | list:
        assert self._client is not None
        resp = await self._client.messages.create(
            model=self.settings.llm_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = "".join(b.text for b in resp.content if b.type == "text")
        return _extract_json(raw)


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
