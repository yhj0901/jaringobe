"""auth 도메인 라우터 — /api/v1/auth/* + /api/v1/users/me (api-spec.md §1).

라우터는 요청 파싱/의존성/서비스 호출/응답만 담당한다 (비즈니스 로직 금지).
"""

from typing import Literal
from urllib.parse import quote

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
from app.domains.auth.schemas import UserMeResponse

router = APIRouter()

_MAX_CODE_LENGTH = 512
_MAX_STATE_LENGTH = 2048


def _login_error_redirect(error_code: str, client: str = "web") -> RedirectResponse:
    """콜백 실패 — web 은 프론트 로그인 페이지, app 은 앱 스킴으로 302 (문구는 프론트 i18n)."""
    settings = get_settings()
    if client == "app":
        url = f"{settings.app_scheme}://auth?error={error_code}"
    else:
        url = f"{settings.frontend_origin}/login?error={error_code}"
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/auth/{provider}/authorize")
async def authorize(
    provider: str,
    next_path: str = Query("/", alias="next"),
    client: Literal["web", "app"] = Query("web"),
) -> RedirectResponse:
    """소셜 로그인 시작 — 서명 state(client 포함) 생성 후 provider 인가 페이지로 302."""
    adapter = service.get_adapter(provider)  # 열거값 외/apple → 404 PROVIDER_NOT_SUPPORTED
    safe_next = sanitize_next_path(next_path)  # CWE-601
    state = create_state_token(provider, safe_next, client)
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
    """provider 콜백 — web 은 쿠키 세팅 후 {next}?login=success 302, app 은 원타임 코드 딥링크."""
    adapter = service.get_adapter(provider)
    settings = get_settings()

    # state 를 먼저 해석해 client(web|app) 분기를 결정 — 서명에 포함돼 위조 불가 (CWE-352)
    client = "web"
    next_path = "/"
    state_valid = False
    if state and len(state) <= _MAX_STATE_LENGTH:
        try:
            next_path, client = decode_state_token(state, provider)  # 서명·만료·provider 일치
            state_valid = True
        except InvalidStateError:
            state_valid = False

    if error is not None:  # 사용자가 동의 거부
        return _login_error_redirect("AUTH_PROVIDER_DENIED", client)

    # code/state 형식·길이 상한 검증 (security-design.md §4)
    if not state_valid or not code or len(code) > _MAX_CODE_LENGTH:
        return _login_error_redirect("AUTH_INVALID_STATE", client)

    try:
        # provider access token 은 프로필 조회 후 즉시 폐기 (저장 금지 — CWE-522)
        provider_token = await adapter.exchange_code(code)
        profile = await adapter.fetch_profile(provider_token)
    except OAuthProviderError:
        return _login_error_redirect("AUTH_PROVIDER_ERROR", client)

    locale = (
        "en"
        if request.headers.get("accept-language", "").strip().lower().startswith("en")
        else "ko"
    )
    user, notice = await service.get_or_create_user(db, provider, profile, locale=locale)

    if client == "app":
        # 쿠키 대신 원타임 코드 발급 → 앱 딥링크 (세션은 /auth/app/session 에서 웹뷰에 세팅)
        raw_code = await service.issue_app_login_code(db, user.id)
        target = f"{settings.app_scheme}://auth?code={raw_code}&next={quote(next_path, safe='')}"
        return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)

    access_token, refresh_token = await service.issue_session(db, user.id)

    sep = "&" if "?" in next_path else "?"
    target = f"{settings.frontend_origin}{next_path}{sep}login=success"
    if notice:
        target += f"&notice={notice}"
    redirect = RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)
    set_auth_cookies(redirect, access_token, refresh_token)
    return redirect


@router.get("/auth/app/session")
async def app_session(
    code: str | None = Query(None),
    next_path: str = Query("/", alias="next"),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """원타임 앱 로그인 코드 → 웹뷰 쿠키 교환 (api-spec 1-6, v1.5).

    실패는 사유 구분 없이 일괄 302 /login?error=AUTH_INVALID_APP_CODE (oracle 차단).
    rate limit 은 /api/v1/auth/* 공통 IP 10회/분 미들웨어가 커버 (CWE-307).
    """
    settings = get_settings()
    safe_next = sanitize_next_path(next_path)  # CWE-601 — 기존 화이트리스트 규칙 재사용

    user_id = None
    if code and len(code) <= _MAX_CODE_LENGTH:
        user_id = await service.consume_app_login_code(db, code)
    if user_id is None:
        return RedirectResponse(
            url=f"{settings.frontend_origin}/login?error=AUTH_INVALID_APP_CODE",
            status_code=status.HTTP_302_FOUND,
        )

    access_token, refresh_token = await service.issue_session(db, user_id)
    sep = "&" if "?" in safe_next else "?"
    redirect = RedirectResponse(
        url=f"{settings.frontend_origin}{safe_next}{sep}login=success",
        status_code=status.HTTP_302_FOUND,
    )
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
