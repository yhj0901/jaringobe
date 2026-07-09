"""Pydantic 공통 베이스 — api-spec.md 공통 규격.

- 요청/응답 JSON 모두 camelCase (alias_generator=to_camel, populate_by_name=True)
- 시각은 ISO-8601 UTC ('Z' 표기) 직렬화
"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


def serialize_utc(dt: datetime) -> str:
    """timestamptz(UTC) → '2026-07-09T04:00:00Z' 형식."""
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
