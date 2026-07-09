"""fridge 오케스트레이션 — 재고 CRUD + 장보기 감산(shortfall) + 식사완료 차감(deduct)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, nullslast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.security import utcnow
from app.domains.fridge.models import FridgeItem
from app.domains.fridge.schemas import (
    DeductLine,
    DeductResponse,
    FridgeItemCreate,
    FridgeItemRead,
    NeededItem,
    ShortfallLine,
    ShortfallResponse,
)

_Z = Decimal("0")


def _qstr(d: Decimal) -> str:
    """불필요한 소수 0 제거 (Numeric(10,3) '2.000' → '2'), 지수표기 방지."""
    return format(d.normalize(), "f")


def _read(it: FridgeItem) -> FridgeItemRead:
    return FridgeItemRead(
        id=it.id, name=it.name, quantity=_qstr(it.quantity), unit=it.unit,
        expires_at=it.expires_at, source=it.source, created_at=it.created_at,
    )


def _by_expiry(stmt):
    # 유통기한 임박 순 (NULL은 뒤로), 동률이면 먼저 담긴 것 우선(FIFO)
    return stmt.order_by(nullslast(FridgeItem.expires_at.asc()), FridgeItem.created_at.asc())


async def list_items(db: AsyncSession, user_id: uuid.UUID) -> list[FridgeItemRead]:
    stmt = _by_expiry(select(FridgeItem).where(FridgeItem.user_id == user_id))
    rows = (await db.execute(stmt)).scalars().all()
    return [_read(r) for r in rows]


async def add_items(
    db: AsyncSession, user_id: uuid.UUID, items: list[FridgeItemCreate]
) -> list[FridgeItemRead]:
    created = [
        FridgeItem(user_id=user_id, name=i.name, quantity=i.quantity, unit=i.unit,
                   expires_at=i.expires_at, source=i.source)
        for i in items
    ]
    db.add_all(created)
    await db.commit()
    for c in created:
        await db.refresh(c)
    return [_read(c) for c in created]


async def _owned_item(db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> FridgeItem:
    item = await db.get(FridgeItem, item_id)
    if item is None:
        raise ApiError(404, "NOT_FOUND", "fridge item not found")
    if item.user_id != user_id:
        raise ApiError(403, "FORBIDDEN", "not your resource")
    return item


async def update_quantity(
    db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID, quantity: Decimal
) -> FridgeItemRead:
    item = await _owned_item(db, user_id, item_id)
    item.quantity = quantity
    await db.commit()
    await db.refresh(item)
    return _read(item)


async def delete_item(db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> None:
    item = await _owned_item(db, user_id, item_id)
    await db.delete(item)
    await db.commit()


async def _matches(db: AsyncSession, user_id: uuid.UUID, name: str, unit: str) -> list[FridgeItem]:
    stmt = _by_expiry(
        select(FridgeItem).where(
            FridgeItem.user_id == user_id,
            func.lower(FridgeItem.name) == name.lower(),
            FridgeItem.unit == unit,
        )
    )
    return list((await db.execute(stmt)).scalars().all())


async def compute_shortfall(
    db: AsyncSession, user_id: uuid.UUID, needed: list[NeededItem]
) -> ShortfallResponse:
    """식단 − 재고 = 필요 품목. 재고는 변경하지 않음(계산만)."""
    lines: list[ShortfallLine] = []
    for n in needed:
        available = sum((m.quantity for m in await _matches(db, user_id, n.name, n.unit)), _Z)
        from_fridge = min(available, n.quantity)
        to_buy = n.quantity - from_fridge
        lines.append(ShortfallLine(
            name=n.name, unit=n.unit, needed=_qstr(n.quantity),
            from_fridge=_qstr(from_fridge), to_buy=_qstr(to_buy),
        ))
    return ShortfallResponse(items=lines)


async def deduct(
    db: AsyncSession, user_id: uuid.UUID, consumed: list[NeededItem]
) -> DeductResponse:
    """식사 완료 시 재고 실제 차감 — 유통기한 임박(FIFO)부터 소진, 0되면 삭제."""
    lines: list[DeductLine] = []
    for c in consumed:
        remaining = c.quantity
        deducted = _Z
        for m in await _matches(db, user_id, c.name, c.unit):
            if remaining <= _Z:
                break
            take = min(m.quantity, remaining)
            m.quantity -= take
            remaining -= take
            deducted += take
            if m.quantity <= _Z:
                await db.delete(m)
        lines.append(DeductLine(
            name=c.name, unit=c.unit, requested=_qstr(c.quantity), deducted=_qstr(deducted)
        ))
    await db.commit()
    return DeductResponse(items=lines)


async def expiring(
    db: AsyncSession, user_id: uuid.UUID, days: int
) -> list[FridgeItemRead]:
    threshold = utcnow().date() + timedelta(days=days)
    stmt = _by_expiry(
        select(FridgeItem).where(
            FridgeItem.user_id == user_id,
            FridgeItem.expires_at.is_not(None),
            FridgeItem.expires_at <= threshold,
        )
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_read(r) for r in rows]
