"""store 연동 상태 라우터 — /api/v1/stores/connections (api-spec.md §6)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.domains.auth.models import User
from app.domains.store import connection_service
from app.domains.store.connection_schemas import (
    StoreConnectionOut,
    StoreConnectionsResponse,
    StoreConnectionUpdateRequest,
)

router = APIRouter()


@router.get("/stores/connections", response_model=StoreConnectionsResponse)
async def list_store_connections(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StoreConnectionsResponse:
    """KR 4종 전체 연동 상태 조회 — 미저장 스토어는 disconnected."""
    return await connection_service.list_connections(db, user)


@router.put("/stores/connections/{store}", response_model=StoreConnectionOut)
async def update_store_connection(
    store: str,
    payload: StoreConnectionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StoreConnectionOut:
    """연동 상태 upsert — 지원 외 스토어 404 STORE_NOT_SUPPORTED."""
    return await connection_service.update_connection(db, user, store, payload.connected)
