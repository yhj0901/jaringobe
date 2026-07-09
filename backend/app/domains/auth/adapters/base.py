"""OAuth 어댑터 공통 인터페이스 — security-design.md §1.

get_authorize_url(state) / exchange_code(code) / fetch_profile(token) → NormalizedProfile
애플(P1) 도입 시에도 동일 인터페이스로 구현한다.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class NormalizedProfile:
    provider_user_id: str
    nickname: str | None = None
    email: str | None = None  # 카카오 동의 거부 시 None
    profile_image_url: str | None = None


class OAuthProviderError(Exception):
    """provider 응답 오류/타임아웃 — 콜백에서 AUTH_PROVIDER_ERROR 로 매핑."""


class OAuthAdapter(Protocol):
    provider: str

    def get_authorize_url(self, state: str) -> str:
        """provider 인가 페이지 URL (state 포함)."""
        ...

    async def exchange_code(self, code: str) -> str:
        """authorization code → provider access token (서버↔서버, 시크릿은 .env 전용)."""
        ...

    async def fetch_profile(self, access_token: str) -> NormalizedProfile:
        """프로필 조회 → 정규화. access token 은 사용 후 저장하지 않는다."""
        ...
