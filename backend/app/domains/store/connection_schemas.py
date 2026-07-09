"""store 연동 상태 Pydantic 스키마 — api-spec.md §6 (camelCase)."""

from datetime import datetime

from pydantic import field_serializer

from app.core.schema import CamelModel, serialize_utc

SUPPORTED_STORES: tuple[str, ...] = ("kurly", "coupang", "ssg", "naver")


class StoreConnectionUpdateRequest(CamelModel):
    connected: bool


class StoreConnectionOut(CamelModel):
    store: str
    status: str
    connected_at: datetime | None = None

    @field_serializer("connected_at")
    def _ser_connected_at(self, v: datetime | None) -> str | None:
        return serialize_utc(v) if v is not None else None


class StoreConnectionsResponse(CamelModel):
    connections: list[StoreConnectionOut]
