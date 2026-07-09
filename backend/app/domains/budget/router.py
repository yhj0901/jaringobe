"""budget 도메인 라우터 — /api/v1/budget/plans (api-spec.md §2)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.ratelimit import budget_user_limiter
from app.domains.auth.models import User
from app.domains.budget import service
from app.domains.budget.schemas import BudgetPlanCreateRequest, BudgetPlanResponse

router = APIRouter()


async def _budget_rate_limit(user: User = Depends(get_current_user)) -> None:
    """유저 기준 5회/분 (CWE-307). 인증 이후에만 카운트."""
    if not budget_user_limiter.allow(str(user.id)):
        raise ApiError(429, "RATE_LIMITED", "Too many budget plan requests")


@router.post(
    "/budget/plans",
    response_model=BudgetPlanResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_budget_rate_limit)],
)
async def create_budget_plan(
    payload: BudgetPlanCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BudgetPlanResponse:
    """예산안 생성 — 게스트 예산안 이전(FR-108)과 온보딩 생성 공용."""
    return await service.create_budget_plan(db, user, payload)
