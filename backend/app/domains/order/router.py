"""order 도메인 라우터 — 사이클 컨텍스트는 composition root에서 주입한다."""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.ratelimit import (
    cycle_action_user_limiter,
    order_confirm_user_limiter,
    order_preview_user_limiter,
)
from app.domains.auth.models import User
from app.domains.order import service
from app.domains.order.models import Order
from app.domains.order.schemas import (
    DeliveryUpdateRequest,
    OrderApproveRequest,
    OrderCreateRequest,
    OrderPreviewResponse,
    OrderResponse,
)
from app.domains.store.connection_schemas import stores_for_country

CycleContextProvider = Callable[
    [AsyncSession, User], Awaitable[service.OrderCycleContext]
]


def create_router(cycle_context_provider: CycleContextProvider) -> APIRouter:
    """cycle→order 단방향 의존을 지키며 `/orders/*`를 order가 소유한다."""
    router = APIRouter(prefix="/orders")

    async def confirm_rate_limit(user: User = Depends(get_current_user)) -> None:
        if not order_confirm_user_limiter.allow(str(user.id)):
            raise ApiError(429, "RATE_LIMITED", "Too many order confirm requests")

    async def action_rate_limit(user: User = Depends(get_current_user)) -> None:
        if not cycle_action_user_limiter.allow(str(user.id)):
            raise ApiError(429, "RATE_LIMITED", "Too many order action requests")

    @router.get(
        "/preview",
        response_model=OrderPreviewResponse,
    )
    async def preview_order(
        refresh: bool = Query(False),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> OrderPreviewResponse:
        context = await cycle_context_provider(db, user)
        if (
            refresh
            or not await service.has_saved_preview(db, user.id, context.cycle_start)
        ) and not order_preview_user_limiter.allow(str(user.id)):
            raise ApiError(429, "RATE_LIMITED", "Too many order preview requests")
        return await service.preview_order(
            db, user, context.cycle_start, refresh=refresh
        )

    @router.get("/latest", response_model=OrderResponse)
    async def get_latest_order(
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> OrderResponse:
        return await service.get_latest_order(db, user)

    @router.post(
        "",
        response_model=OrderResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(confirm_rate_limit)],
    )
    async def confirm_order(
        payload: OrderCreateRequest,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> OrderResponse:
        context = await cycle_context_provider(db, user)
        return await service.confirm_order(
            db,
            user,
            payload.store,
            cycle_start=context.cycle_start,
            frequency=context.frequency,
            timezone_name=context.timezone,
            lead_days=context.delivery_days(payload.store),
            local_hour=context.local_hour,
        )

    @router.post(
        "/{order_id}/approve",
        response_model=OrderResponse,
        dependencies=[Depends(action_rate_limit)],
    )
    async def approve_order(
        order_id: uuid.UUID,
        payload: OrderApproveRequest | None = None,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> OrderResponse:
        context = await cycle_context_provider(db, user)
        store = await db.scalar(
            select(Order.store).where(Order.id == order_id, Order.user_id == user.id)
        )
        lead_days = context.delivery_days(
            store or stores_for_country(user.country)[0]
        )
        return await service.approve_order(
            db,
            user,
            order_id,
            exclude_names=payload.exclude_names if payload else None,
            timezone_name=context.timezone,
            lead_days=lead_days,
            local_hour=context.local_hour,
        )

    @router.post(
        "/{order_id}/cancel",
        response_model=OrderResponse,
        dependencies=[Depends(action_rate_limit)],
    )
    async def cancel_order(
        order_id: uuid.UUID,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> OrderResponse:
        context = await cycle_context_provider(db, user)
        return await service.cancel_order(
            db,
            user,
            order_id,
            timezone_name=context.timezone,
            cancel_window_days=context.cancel_window_days,
        )

    @router.post(
        "/{order_id}/delivery",
        response_model=OrderResponse,
        dependencies=[Depends(action_rate_limit)],
    )
    async def update_delivery(
        order_id: uuid.UUID,
        payload: DeliveryUpdateRequest,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> OrderResponse:
        context = await cycle_context_provider(db, user)
        return await service.update_delivery(
            db,
            user,
            order_id,
            received=payload.received,
            unknown_attempts=context.delivery_unknown_attempts,
        )

    return router
