"""order 도메인 라우터 — /api/v1/orders (preview / 확정 / latest)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.ratelimit import order_confirm_user_limiter, order_preview_user_limiter
from app.domains.auth.models import User
from app.domains.order import service
from app.domains.order.schemas import OrderCreateRequest, OrderPreviewResponse, OrderResponse

router = APIRouter(prefix="/orders")


async def _preview_rate_limit(user: User = Depends(get_current_user)) -> None:
    """유저 기준 3회/분 — 네이버+LLM 비용 방어, 기존 store 한도와 동일 (CWE-770)."""
    if not order_preview_user_limiter.allow(str(user.id)):
        raise ApiError(429, "RATE_LIMITED", "Too many order preview requests")


async def _confirm_rate_limit(user: User = Depends(get_current_user)) -> None:
    """유저 기준 5회/분 (확정 연타 방어, CWE-770)."""
    if not order_confirm_user_limiter.allow(str(user.id)):
        raise ApiError(429, "RATE_LIMITED", "Too many order confirm requests")


@router.get(
    "/preview",
    response_model=OrderPreviewResponse,
    dependencies=[Depends(_preview_rate_limit)],
)
async def preview_order(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OrderPreviewResponse:
    """최신 식단 미완료 재료 − 냉장고 재고. 스토어 연동 없이도 200."""
    return await service.preview_order(db, user)


@router.get("/latest", response_model=OrderResponse)
async def get_latest_order(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OrderResponse:
    """해당 유저 최신 확정 주문 1건. 없으면 404 ORDER_NOT_FOUND."""
    return await service.get_latest_order(db, user)


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_confirm_rate_limit)],
)
async def confirm_order(
    payload: OrderCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OrderResponse:
    """서버가 preview 를 재계산해 시뮬레이션 확정. body 는 store 만 (CWE-602)."""
    return await service.confirm_order(db, user, payload.store)
