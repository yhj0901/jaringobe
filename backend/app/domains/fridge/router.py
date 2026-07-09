"""fridge 도메인 라우터 — /api/v1/fridge (가상 냉장고)."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.domains.auth.models import User
from app.domains.fridge import service
from app.domains.fridge.schemas import (
    DeductResponse,
    FridgeItemRead,
    FridgeItemsCreate,
    FridgeItemUpdate,
    NeedsRequest,
    ShortfallResponse,
)

router = APIRouter(prefix="/fridge")


@router.get("", response_model=list[FridgeItemRead])
async def list_fridge(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[FridgeItemRead]:
    return await service.list_items(db, user.id)


@router.post("/items", status_code=status.HTTP_201_CREATED, response_model=list[FridgeItemRead])
async def add_items(
    payload: FridgeItemsCreate,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> list[FridgeItemRead]:
    return await service.add_items(db, user.id, payload.items)


@router.patch("/items/{item_id}", response_model=FridgeItemRead)
async def update_item(
    item_id: uuid.UUID, payload: FridgeItemUpdate,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> FridgeItemRead:
    return await service.update_quantity(db, user.id, item_id, payload.quantity)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> None:
    await service.delete_item(db, user.id, item_id)


@router.post("/shortfall", response_model=ShortfallResponse)
async def shortfall(
    payload: NeedsRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> ShortfallResponse:
    """식단 재료 − 냉장고 재고 = 필요 품목 (재고 불변). store/cart 입력용."""
    return await service.compute_shortfall(db, user.id, payload.items)


@router.post("/deduct", response_model=DeductResponse)
async def deduct(
    payload: NeedsRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> DeductResponse:
    """식사 완료 시 재고 실제 차감 (유통기한 임박 FIFO)."""
    return await service.deduct(db, user.id, payload.items)


@router.get("/expiring", response_model=list[FridgeItemRead])
async def expiring(
    days: int = Query(default=3, ge=1, le=30),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> list[FridgeItemRead]:
    return await service.expiring(db, user.id, days)
