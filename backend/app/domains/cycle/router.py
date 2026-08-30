"""cycle 도메인 라우터 — 상태·설정·이번 사이클 건너뛰기."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.ratelimit import cycle_action_user_limiter
from app.domains.auth.models import User
from app.domains.cycle import service
from app.domains.cycle.schemas import CycleSettingsUpdateRequest, CycleState

router = APIRouter(prefix="/cycle")


async def _cycle_action_rate_limit(user: User = Depends(get_current_user)) -> None:
    if not cycle_action_user_limiter.allow(str(user.id)):
        raise ApiError(429, "RATE_LIMITED", "Too many cycle requests")


@router.get("", response_model=CycleState)
async def get_cycle(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CycleState:
    return await service.get_cycle_state(db, user)


@router.put(
    "/settings",
    response_model=CycleState,
    dependencies=[Depends(_cycle_action_rate_limit)],
)
async def update_cycle_settings(
    payload: CycleSettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CycleState:
    return await service.update_settings(db, user, payload)


@router.post(
    "/skip",
    response_model=CycleState,
    dependencies=[Depends(_cycle_action_rate_limit)],
)
async def skip_cycle(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CycleState:
    return await service.skip_cycle(db, user)
