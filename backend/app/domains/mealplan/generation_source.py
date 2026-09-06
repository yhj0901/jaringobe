"""식단 생성 출처의 허용값. 기존 데이터의 미상 출처는 NULL로 유지한다."""

from enum import StrEnum


class GenerationSource(StrEnum):
    LLM = "llm"
    FALLBACK = "fallback"
