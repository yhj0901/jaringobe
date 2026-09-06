"""Claude 호출 래퍼 — 키 없으면 mock 폴백. 타임아웃 + SDK 재시도."""

from __future__ import annotations

import json
import logging
import re
from time import monotonic

from app.core.config import Settings, get_settings

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
# 21끼(7일×3끼) JSON 생성은 수십 초 소요. 재시도 예산(service.GENERATION_TIME_BUDGET_SECONDS=25)과
# 합산해 최악 응답을 85초(<프론트 90초)로 보장: 재시도 진입(≤25s 시점) + 호출 상한 60s
LLM_TIMEOUT_SECONDS = 60.0
LLM_MAX_RETRIES = 0
logger = logging.getLogger(__name__)


class LLMOutputLimitError(RuntimeError):
    """응답 본문을 담지 않는 출력 상한 오류."""

    stop_reason = "max_tokens"


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
        started = monotonic()
        # Sonnet 5는 adaptive thinking/high가 기본이며 추론도 8000 토큰에 포함된다.
        # 60초 식단 생성 경로에서는 low로 토큰 지출을 제한한다. 미지원 모델에는 보내지 않는다.
        # medium 실측 53.1초는 서비스 재시도 진입 예산 25초를 넘겨 알레르기 재시도가
        # 불가능해 채택하지 않았다. 상세 근거/남은 품질 위험: reports/loopfix-review.md.
        # 근거: https://platform.claude.com/docs/en/models/sonnet-5/migration-guide
        request_options: dict = {}
        if self.settings.llm_model.startswith("claude-sonnet-5"):
            request_options["output_config"] = {"effort": "low"}
        resp = await self._client.messages.create(
            model=self.settings.llm_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            **request_options,
        )
        logger.info("mealplan_llm_response", extra={
            "event": "mealplan_llm_response", "stop_reason": resp.stop_reason,
            "output_tokens": resp.usage.output_tokens, "max_tokens": max_tokens,
            "elapsed_seconds": round(monotonic() - started, 3),
        })
        if resp.stop_reason == "max_tokens":
            # 우연히 파싱 가능한 부분 응답도 완성된 AI 식단으로 저장하지 않는다.
            raise LLMOutputLimitError("LLM output reached max_tokens before completion")
        raw = "".join(b.text for b in resp.content if b.type == "text")
        return _extract_json(raw)


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
