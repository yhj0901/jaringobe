"""auth 도메인 라우터 — /api/v1/auth/* + /api/v1/users/me (api-spec.md §1).

라우터는 요청 파싱/의존성/서비스 호출/응답만 담당한다 (비즈니스 로직 금지).
"""

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.security import (
    REFRESH_COOKIE_NAME,
    InvalidStateError,
    clear_auth_cookies,
    create_state_token,
    decode_state_token,
    sanitize_next_path,
    set_auth_cookies,
)
from app.domains.auth import service
from app.domains.auth.adapters.base import OAuthProviderError
from app.domains.auth.models import User
from app.domains.auth.schemas import UserMeResponse, UserRegionUpdateRequest

router = APIRouter()

_MAX_CODE_LENGTH = 512
_MAX_STATE_LENGTH = 2048


def _login_error_redirect(error_code: str) -> RedirectResponse:
    """콜백 실패 — 프론트 로그인 페이지로 302 (문구는 프론트 i18n 담당)."""
    settings = get_settings()
    return RedirectResponse(
        url=f"{settings.frontend_origin}/login?error={error_code}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/auth/{provider}/authorize")
async def authorize(
    provider: str,
    next_path: str = Query("/", alias="next"),
) -> RedirectResponse:
    """소셜 로그인 시작 — 서명 state 생성 후 provider 인가 페이지로 302."""
    adapter = service.get_adapter(provider)  # 열거값 외/apple → 404 PROVIDER_NOT_SUPPORTED
    safe_next = sanitize_next_path(next_path)  # CWE-601
    state = create_state_token(provider, safe_next)
    return RedirectResponse(url=adapter.get_authorize_url(state), status_code=status.HTTP_302_FOUND)


@router.get("/auth/{provider}/callback")
async def callback(
    request: Request,
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """provider 콜백 — 성공 시 쿠키 세팅 후 {next}?login=success 로 302."""
    adapter = service.get_adapter(provider)
    settings = get_settings()

    if error is not None:  # 사용자가 동의 거부
        return _login_error_redirect("AUTH_PROVIDER_DENIED")

    # code/state 형식·길이 상한 검증 (security-design.md §4)
    if not code or not state or len(code) > _MAX_CODE_LENGTH or len(state) > _MAX_STATE_LENGTH:
        return _login_error_redirect("AUTH_INVALID_STATE")

    try:
        next_path = decode_state_token(state, provider)  # 서명·만료·provider 일치 (CWE-352)
    except InvalidStateError:
        return _login_error_redirect("AUTH_INVALID_STATE")

    try:
        # provider access token 은 프로필 조회 후 즉시 폐기 (저장 금지 — CWE-522)
        provider_token = await adapter.exchange_code(code)
        profile = await adapter.fetch_profile(provider_token)
    except OAuthProviderError:
        return _login_error_redirect("AUTH_PROVIDER_ERROR")

    locale = (
        "en"
        if request.headers.get("accept-language", "").strip().lower().startswith("en")
        else "ko"
    )
    user, notice = await service.get_or_create_user(db, provider, profile, locale=locale)
    access_token, refresh_token = await service.issue_session(db, user.id)

    sep = "&" if "?" in next_path else "?"
    target = f"{settings.frontend_origin}{next_path}{sep}login=success"
    if notice:
        target += f"&notice={notice}"
    redirect = RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)
    set_auth_cookies(redirect, access_token, refresh_token)
    return redirect


@router.post("/auth/refresh")
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Access 재발급 + refresh 회전. 재사용 감지 시 전 세션 폐기 → 401 AUTH_TOKEN_REVOKED."""
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_refresh:
        raise ApiError(401, "AUTH_REQUIRED", "Missing refresh token cookie")
    access_token, new_refresh = await service.rotate_refresh_token(db, raw_refresh)
    set_auth_cookies(response, access_token, new_refresh)
    return {}


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    """refresh 서버측 폐기 + 쿠키 삭제. access 는 잔여 수명 자연 만료 (MVP)."""
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_refresh:
        await service.revoke_refresh_token(db, raw_refresh)
    clear_auth_cookies(response)


@router.get("/users/me", response_model=UserMeResponse)
async def users_me(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserMeResponse:
    """로그인 직후 분기 판정용 단일 콜 (auth 도메인에서 제공)."""
    return await service.build_user_me(db, user)


@router.put("/users/me/region", response_model=UserMeResponse)
async def update_user_region(
    payload: UserRegionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserMeResponse:
    """지역 수동 전환 — country 저장 + currency 서버 매핑 (api-spec.md §1-6, 본인 스코프)."""
    return await service.update_region(db, user, payload.country)
