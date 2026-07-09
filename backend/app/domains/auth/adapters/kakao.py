"""카카오 OAuth 어댑터 — Authorization Code (백엔드 주도)."""

from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.domains.auth.adapters.base import NormalizedProfile, OAuthProviderError

AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
PROFILE_URL = "https://kapi.kakao.com/v2/user/me"

_TIMEOUT = httpx.Timeout(10.0)


class KakaoAdapter:
    provider = "kakao"

    def __init__(self, settings: Settings) -> None:
        self._client_id = settings.kakao_client_id
        self._client_secret = settings.kakao_client_secret
        # 콜백은 프론트 rewrites 프록시 경유 — 쿠키가 프론트 오리진에 설정되도록
        self._redirect_uri = f"{settings.frontend_origin}/api/v1/auth/kakao/callback"

    def get_authorize_url(self, state: str) -> str:
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "state": state,
            }
        )
        return f"{AUTHORIZE_URL}?{query}"

    async def exchange_code(self, code: str) -> str:
        data = {
            "grant_type": "authorization_code",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "redirect_uri": self._redirect_uri,
            "code": code,
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                res = await client.post(TOKEN_URL, data=data)
                res.raise_for_status()
                token = res.json().get("access_token")
        except httpx.HTTPError as exc:
            raise OAuthProviderError("kakao token exchange failed") from exc
        if not token:
            raise OAuthProviderError("kakao token response missing access_token")
        return str(token)

    async def fetch_profile(self, access_token: str) -> NormalizedProfile:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                res = await client.get(
                    PROFILE_URL, headers={"Authorization": f"Bearer {access_token}"}
                )
                res.raise_for_status()
                body = res.json()
        except httpx.HTTPError as exc:
            raise OAuthProviderError("kakao profile fetch failed") from exc

        provider_user_id = body.get("id")
        if provider_user_id is None:
            raise OAuthProviderError("kakao profile response missing id")
        account = body.get("kakao_account") or {}
        profile = account.get("profile") or {}
        return NormalizedProfile(
            provider_user_id=str(provider_user_id),
            nickname=profile.get("nickname"),
            email=account.get("email"),  # 동의 거부 시 None 허용
            profile_image_url=profile.get("profile_image_url"),
        )
