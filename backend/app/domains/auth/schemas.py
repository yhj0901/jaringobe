"""auth 도메인 Pydantic 스키마 — api-spec.md §1."""

import uuid
from typing import Literal

from app.core.schema import CamelModel


class UserRegionUpdateRequest(CamelModel):
    """PUT /api/v1/users/me/region — 지역 수동 전환 (api-spec.md §1-6).

    country 만 받고 currency 는 서버가 매핑한다(클라이언트 currency 입력 없음).
    열거 위반은 Pydantic 이 422 VALIDATION_ERROR 로 처리.
    """

    country: Literal["KR", "US"]


class UserMeResponse(CamelModel):
    """GET /api/v1/users/me — 로그인 직후 분기 판정용."""

    id: uuid.UUID
    nickname: str
    email: str | None = None  # 카카오 동의 거부 시 null
    profile_image_url: str | None = None
    locale: str
    country: str
    currency: str
    onboarding_completed: bool
    has_budget_plan: bool
