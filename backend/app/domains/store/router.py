"""store 도메인 라우터 — /api/v1/store/cart (마트 장바구니 구성)."""

from fastapi import APIRouter, Depends, status

from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.ratelimit import store_user_limiter
from app.domains.auth.models import User
from app.domains.store import service
from app.domains.store.schemas import StoreCartRequest, StoreCartResponse

router = APIRouter()


async def _store_rate_limit(user: User = Depends(get_current_user)) -> None:
    """유저 기준 3회/분 (네이버 순차조회+LLM 비용 방어, CWE-770)."""
    if not store_user_limiter.allow(str(user.id)):
        raise ApiError(429, "RATE_LIMITED", "Too many store cart requests")


@router.post(
    "/store/cart",
    response_model=StoreCartResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(_store_rate_limit)],
)
async def build_store_cart(
    payload: StoreCartRequest,
    user: User = Depends(get_current_user),
) -> StoreCartResponse:
    """재료 목록 → 네이버 쇼핑(식품/몰 필터) → LLM 선택 → 마트 장바구니."""
    return await service.build_cart(payload.items, payload.mall, payload.max_pages)
