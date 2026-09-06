"""notification 도메인 라우터 — /api/v1/notifications/* (api-spec.md 6-A).

라우터는 요청 파싱/의존성/서비스 호출/응답만 담당한다 (비즈니스 로직 금지).
전 엔드포인트 JWT 인증 필수 + 본인 스코프 (CWE-287/639).
"""

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.ratelimit import notification_user_limiter
from app.domains.auth.models import User
from app.domains.notification import service
from app.domains.notification.schemas import (
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    NotificationSettingsResponse,
    NotificationSettingsUpdateRequest,
)

router = APIRouter()


def _notification_rate_limit(scope: str):
    """유저 기준 10회/분 — 엔드포인트별 개별 한도 (api-spec 6-A-1·6-A-4, CWE-307)."""

    async def dependency(user: User = Depends(get_current_user)) -> None:
        if not notification_user_limiter.allow(f"{scope}:{user.id}"):
            raise ApiError(429, "RATE_LIMITED", "Too many notification requests")

    return dependency


@router.put(
    "/notifications/devices",
    response_model=DeviceRegisterResponse,
    dependencies=[Depends(_notification_rate_limit("devices"))],
)
async def register_device(
    payload: DeviceRegisterRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeviceRegisterResponse:
    """디바이스 토큰 등록/갱신 — token 기준 idempotent upsert (앱 실행 시마다 호출)."""
    device_id = await service.upsert_device(db, user, payload)
    return DeviceRegisterResponse(id=device_id)


@router.delete("/notifications/devices/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    token: str = Path(max_length=4096),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """로그아웃/알림 전체 해제 시 토큰 삭제. 본인 소유만, 없는 토큰도 204 (idempotent)."""
    await service.delete_device(db, user, token)


@router.get("/notifications/settings", response_model=NotificationSettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationSettingsResponse:
    """알림 설정 조회 — 행이 없으면 기본값으로 lazy 생성 후 반환."""
    settings = await service.get_or_create_settings(db, user)
    return NotificationSettingsResponse(settings=service.serialize_settings(settings))


@router.put(
    "/notifications/settings",
    response_model=NotificationSettingsResponse,
    dependencies=[Depends(_notification_rate_limit("settings"))],
)
async def update_settings(
    payload: NotificationSettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationSettingsResponse:
    """부분 갱신 — 보낸 type 만 반영, next_send_at(UTC) 재계산, 전체 설정 재반환."""
    settings = await service.update_settings(db, user, payload.settings)
    return NotificationSettingsResponse(settings=service.serialize_settings(settings))
