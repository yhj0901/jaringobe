"""store 연동 상태 Pydantic 스키마 — api-spec.md §6 (camelCase). v1.5 국가별 세트."""

from datetime import datetime

from pydantic import field_serializer

from app.core.schema import CamelModel, serialize_utc

# 국가별 지원 스토어 세트 (api-spec.md §6, FR-603). DB CHECK(리비전 0007)는 전체 합집합을 허용하고,
# 노출/검증 세트는 user.country 로 결정한다 (지역 전환 시 타 국가 연동 행 보존).
STORES_BY_COUNTRY: dict[str, tuple[str, ...]] = {
    "KR": ("kurly", "coupang", "ssg", "naver"),
    "US": ("walmart", "instacart"),
}


def stores_for_country(country: str) -> tuple[str, ...]:
    """user.country 의 스토어 세트 반환 — 미정의 국가는 KR 로 폴백."""
    return STORES_BY_COUNTRY.get(country, STORES_BY_COUNTRY["KR"])


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
