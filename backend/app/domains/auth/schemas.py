"""auth 도메인 Pydantic 스키마 — api-spec.md §1."""

import uuid

from app.core.schema import CamelModel


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
