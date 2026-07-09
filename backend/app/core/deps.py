"""공통 의존성 — 인증 검증 등."""

import uuid

import jwt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import ApiError
from app.core.security import ACCESS_COOKIE_NAME, decode_access_token
from app.domains.auth.models import User


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """jaringobe_access 쿠키의 JWT 를 검증하고 유저를 로드한다. 실패 시 401 AUTH_REQUIRED."""
    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not token:
        raise ApiError(401, "AUTH_REQUIRED", "Missing access token cookie")
    try:
        claims = decode_access_token(token)
        user_id = uuid.UUID(str(claims["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise ApiError(401, "AUTH_REQUIRED", "Invalid or expired access token") from exc

    user = await db.get(User, user_id)
    if user is None:
        raise ApiError(401, "AUTH_REQUIRED", "User not found")
    return user
