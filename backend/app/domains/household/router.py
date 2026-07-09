"""household 도메인 라우터 — /api/v1/households/me (api-spec.md §4)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.domains.auth.models import User
from app.domains.household import service
from app.domains.household.schemas import HouseholdResponse, HouseholdUpdateRequest

router = APIRouter()


@router.put("/households/me", response_model=HouseholdResponse)
async def replace_household(
    payload: HouseholdUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HouseholdResponse:
    """가구 구성원 전체 교체 저장 (replace-all)."""
    return await service.replace_household(db, user, payload)


@router.get("/households/me", response_model=HouseholdResponse)
async def get_household(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HouseholdResponse:
    """가구 구성 조회 — 미설정 시 404 HOUSEHOLD_NOT_FOUND."""
    return await service.get_household(db, user)
