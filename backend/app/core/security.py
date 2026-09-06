"""JWT 발급/검증 + OAuth state 서명 토큰 + refresh 토큰 유틸 + 쿠키 정책.

security-design.md 기준:
- Access: JWT HS256, 30분, claims sub/exp/iat/jti — 쿠키 jaringobe_access
- Refresh: 불투명 랜덤 256bit — DB 에는 SHA-256 해시만 저장, 14일, Path=/api/v1/auth
- state: 서명 JWT (nonce + next + provider, 10분 만료) — CWE-352
- next: '/' 로 시작하는 상대 경로만 허용 — CWE-601
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Response

from app.core.config import get_settings

ACCESS_COOKIE_NAME = "jaringobe_access"
REFRESH_COOKIE_NAME = "jaringobe_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"  # refresh/logout 외 전송 차단 (노출면 최소화)

_STATE_PURPOSE = "oauth_state"


class InvalidStateError(Exception):
    """OAuth state 서명/만료/provider 불일치."""


def utcnow() -> datetime:
    return datetime.now(UTC)


# ---------- Access JWT ----------


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = utcnow()
    claims = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_alg)


def decode_access_token(token: str) -> dict:
    """유효하지 않으면 jwt.PyJWTError 를 그대로 올린다 (호출부에서 401 매핑)."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])


# ---------- OAuth state ----------


def create_state_token(provider: str, next_path: str, client: str = "web") -> str:
    """client(web|app) 를 state 서명에 포함 — 콜백 분기 위조 차단 (CWE-352, v1.5)."""
    settings = get_settings()
    now = utcnow()
    claims = {
        "purpose": _STATE_PURPOSE,
        "nonce": secrets.token_urlsafe(16),
        "next": next_path,
        "provider": provider,
        "client": client,
        "iat": now,
        "exp": now + timedelta(minutes=settings.oauth_state_expire_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_alg)


def decode_state_token(token: str, provider: str) -> tuple[str, str]:
    """state 검증 후 (next 상대경로, client) 반환. 실패 시 InvalidStateError."""
    settings = get_settings()
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
    except jwt.PyJWTError as exc:
        raise InvalidStateError("state signature/expiry validation failed") from exc
    if claims.get("purpose") != _STATE_PURPOSE or claims.get("provider") != provider:
        raise InvalidStateError("state purpose/provider mismatch")
    client = claims.get("client", "web")
    if client not in ("web", "app"):
        client = "web"
    return sanitize_next_path(str(claims.get("next", "/"))), client


def sanitize_next_path(next_path: str) -> str:
    """CWE-601 — '/' 로 시작하는 상대 경로만 허용. '//'·백슬래시·스킴 포함 시 '/'."""
    if (
        not next_path.startswith("/")
        or next_path.startswith("//")
        or "\\" in next_path
        or "://" in next_path
        or any(ord(ch) < 0x20 for ch in next_path)
    ):
        return "/"
    return next_path


# ---------- Refresh 토큰 ----------


def generate_refresh_token() -> str:
    """불투명 랜덤 256bit. 원문은 쿠키로만 전달, DB 저장 금지."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(raw: str) -> str:
    """SHA-256 hex(64자) — DB 에는 해시만 저장."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------- 앱 로그인 원타임 코드 (v1.5, security-design.md 5-4) ----------


def generate_app_login_code() -> str:
    """256bit 랜덤 원타임 코드. 원문은 딥링크로만 전달, DB 저장 금지 (CWE-598)."""
    return secrets.token_urlsafe(32)


def hash_app_login_code(raw: str) -> str:
    """SHA-256 hex(64자) — DB 에는 해시만 저장 (refresh_tokens 와 동일 원칙)."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------- 쿠키 정책 ----------


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        access_token,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 3600,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        ACCESS_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
