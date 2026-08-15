"""store 연동 상태 비즈니스 로직 — api-spec.md §6.

- 조회/갱신 모두 인증 유저 본인 스코프로만 접근 (CWE-639)
- 1단계: 연동 상태 관리만 (자격증명 미수집)
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.security import utcnow
from app.domains.auth.models import User
from app.domains.store.connection_models import StoreConnection
from app.domains.store.connection_schemas import (
    StoreConnectionOut,
    StoreConnectionsResponse,
    stores_for_country,
)


async def list_connections(db: AsyncSession, user: User) -> StoreConnectionsResponse:
    """user.country 의 스토어 세트 상태 반환 — 미저장 스토어는 disconnected(connectedAt null).

    타 국가 연동 행은 삭제하지 않고 응답에서 제외만 한다(지역 재전환 시 복원).
    """
    stores = stores_for_country(user.country)
    rows = (
        await db.scalars(select(StoreConnection).where(StoreConnection.user_id == user.id))
    ).all()
    by_store = {row.store: row for row in rows}
    return StoreConnectionsResponse(
        connections=[
            StoreConnectionOut(
                store=store,
                status=by_store[store].status if store in by_store else "disconnected",
                connected_at=by_store[store].connected_at if store in by_store else None,
            )
            for store in stores
        ]
    )


async def update_connection(
    db: AsyncSession, user: User, store: str, connected: bool
) -> StoreConnectionOut:
    """연동 상태 upsert — user.country 허용 세트 외 스토어는 404 STORE_NOT_SUPPORTED."""
    if store not in stores_for_country(user.country):
        raise ApiError(404, "STORE_NOT_SUPPORTED", f"Unsupported store: {store}")

    row = await db.scalar(
        select(StoreConnection).where(
            StoreConnection.user_id == user.id, StoreConnection.store == store
        )
    )
    if row is None:
        row = StoreConnection(user_id=user.id, store=store, status="disconnected")
        db.add(row)

    if connected:
        row.status = "connected"
        row.connected_at = utcnow()
    else:
        row.status = "disconnected"
        row.connected_at = None

    await db.commit()
    return StoreConnectionOut(store=row.store, status=row.status, connected_at=row.connected_at)
