"""auth 도메인 비즈니스 로직 — 소셜 로그인/세션 관리 (security-design.md §1~2)."""

import secrets
import uuid
from datetime import timedelta

from sqlalchemy import exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    utcnow,
)
from app.domains.auth.adapters.base import NormalizedProfile, OAuthAdapter
from app.domains.auth.adapters.google import GoogleAdapter
from app.domains.auth.adapters.kakao import KakaoAdapter
from app.domains.auth.models import AuthIdentity, RefreshToken, User
from app.domains.auth.schemas import UserMeResponse
from app.domains.budget.models import BudgetPlan

EMAIL_CONFLICT_NOTICE = "AUTH_EMAIL_CONFLICT_NOTICE"


def get_adapter(provider: str) -> OAuthAdapter:
    """provider 어댑터 조회. apple(P1)·열거값 외는 404 PROVIDER_NOT_SUPPORTED."""
    settings = get_settings()
    if provider == "kakao":
        return KakaoAdapter(settings)
    if provider == "google":
        return GoogleAdapter(settings)
    raise ApiError(404, "PROVIDER_NOT_SUPPORTED", f"Provider '{provider}' is not supported")


def _default_nickname() -> str:
    """provider 가 닉네임을 주지 않은 경우 서비스 기본값 생성 (db-schema.md users.nickname)."""
    return f"자린이-{secrets.token_hex(3)}"


async def get_or_create_user(
    db: AsyncSession,
    provider: str,
    profile: NormalizedProfile,
    locale: str = "ko",
) -> tuple[User, str | None]:
    """auth_identities 조회 → 없으면 users 생성. 반환: (user, notice code | None).

    동일 이메일 타 provider 계정이 있으면 자동 통합하지 않고(CWE-287)
    AUTH_EMAIL_CONFLICT_NOTICE 만 반환한다 (FR-004).
    """
    identity = await db.scalar(
        select(AuthIdentity).where(
            AuthIdentity.provider == provider,
            AuthIdentity.provider_user_id == profile.provider_user_id,
        )
    )
    if identity is not None:
        user = await db.get(User, identity.user_id)
        if user is None:  # FK CASCADE 상 도달 불가 — 방어적 처리
            raise ApiError(401, "AUTH_REQUIRED", "User for identity not found")
        return user, None

    notice: str | None = None
    if profile.email:
        email_taken = await db.scalar(
            select(exists().where(func.lower(User.email) == profile.email.lower()))
        )
        if email_taken:
            notice = EMAIL_CONFLICT_NOTICE

    user = User(
        nickname=(profile.nickname or _default_nickname())[:50],
        email=profile.email,
        profile_image_url=profile.profile_image_url,
        locale=locale,
    )
    db.add(user)
    await db.flush()
    db.add(
        AuthIdentity(
            user_id=user.id,
            provider=provider,
            provider_user_id=profile.provider_user_id,
            email_at_signup=profile.email,
        )
    )
    await db.commit()
    return user, notice


async def issue_session(db: AsyncSession, user_id: uuid.UUID) -> tuple[str, str]:
    """신규 토큰 세트 발급 (세션 고정 없음 — CWE-384). 반환: (access JWT, refresh 원문)."""
    settings = get_settings()
    raw_refresh = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=utcnow() + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await db.commit()
    return create_access_token(user_id), raw_refresh


async def rotate_refresh_token(db: AsyncSession, raw_refresh: str) -> tuple[str, str]:
    """refresh 회전 — 기존 revoke + 신규 발급 (rotated_from 체인).

    revoked 토큰 재사용 감지 시 해당 유저 전 세션 즉시 폐기 + 401 AUTH_TOKEN_REVOKED (CWE-613).
    """
    token = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_refresh))
    )
    if token is None:
        raise ApiError(401, "AUTH_REQUIRED", "Unknown refresh token")

    now = utcnow()
    if token.revoked_at is not None:
        await revoke_all_sessions(db, token.user_id)
        raise ApiError(
            401, "AUTH_TOKEN_REVOKED", "Refresh token reuse detected; all sessions revoked"
        )
    if token.expires_at <= now:
        raise ApiError(401, "AUTH_REQUIRED", "Refresh token expired")

    settings = get_settings()
    token.revoked_at = now
    new_raw = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=token.user_id,
            token_hash=hash_refresh_token(new_raw),
            rotated_from=token.id,
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await db.commit()
    return create_access_token(token.user_id), new_raw


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    """유저의 미폐기 refresh 전부 폐기 (재사용 감지 대응)."""
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await db.commit()


async def revoke_refresh_token(db: AsyncSession, raw_refresh: str) -> None:
    """로그아웃 — 해당 refresh 서버측 폐기 (없으면 무시)."""
    await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_refresh_token(raw_refresh),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow())
    )
    await db.commit()


async def build_user_me(db: AsyncSession, user: User) -> UserMeResponse:
    """GET /users/me 응답 — onboardingCompleted / hasBudgetPlan 분기 필드 포함."""
    has_plan = bool(await db.scalar(select(exists().where(BudgetPlan.user_id == user.id))))
    return UserMeResponse(
        id=user.id,
        nickname=user.nickname,
        email=user.email,
        profile_image_url=user.profile_image_url,
        locale=user.locale,
        country=user.country,
        currency=user.currency,
        onboarding_completed=user.onboarding_completed_at is not None,
        has_budget_plan=has_plan,
    )
