"""구글 OAuth 어댑터 — Authorization Code (백엔드 주도)."""

from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.domains.auth.adapters.base import NormalizedProfile, OAuthProviderError

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
PROFILE_URL = "https://openidconnect.googleapis.com/v1/userinfo"

_TIMEOUT = httpx.Timeout(10.0)


class GoogleAdapter:
    provider = "google"

    def __init__(self, settings: Settings) -> None:
        self._client_id = settings.google_client_id
        self._client_secret = settings.google_client_secret
        self._redirect_uri = f"{settings.frontend_origin}/api/v1/auth/google/callback"

    def get_authorize_url(self, state: str) -> str:
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
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
            raise OAuthProviderError("google token exchange failed") from exc
        if not token:
            raise OAuthProviderError("google token response missing access_token")
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
            raise OAuthProviderError("google profile fetch failed") from exc

        provider_user_id = body.get("sub")
        if not provider_user_id:
            raise OAuthProviderError("google profile response missing sub")
        return NormalizedProfile(
            provider_user_id=str(provider_user_id),
            nickname=body.get("name"),
            email=body.get("email"),
            profile_image_url=body.get("picture"),
        )
