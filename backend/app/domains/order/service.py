"""order 상태 머신 — 초안·확정·배송 등록과 서버 재계산 스냅샷."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import utcnow
from app.domains.auth.models import User
from app.domains.budget import service as budget_service
from app.domains.budget.models import BudgetPlan
from app.domains.budget.schemas import MoneyOut
from app.domains.fridge import service as fridge_service
from app.domains.fridge.schemas import FridgeItemCreate, NeededItem as FridgeNeed
from app.domains.mealplan.models import Meal, MealPlan
from app.domains.order.models import Order, OrderItem
from app.domains.order.schemas import (
    OrderItemOut,
    OrderPreviewResponse,
    OrderResponse,
    ShortfallPreviewLine,
)
from app.domains.store import connection_service, service as store_service
from app.domains.store.connection_models import StoreConnection
from app.domains.store.connection_schemas import stores_for_country
from app.domains.store.schemas import CartProduct, NeededItem as StoreNeed, StoreCartResponse

_Z = Decimal("0")
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"awaiting_user", "confirmed", "cancelled", "expired", "failed"},
    "awaiting_user": {"confirmed", "cancelled", "expired", "failed"},
    "confirmed": {"cancelled", "failed"},
    "cancelled": {"failed"},
    "expired": {"failed"},
    "failed": set(),
}


@dataclass(frozen=True)
class OrderCycleContext:
    """API 합성 계층이 cycle에서 주입하는 주문용 최소 정책 스냅샷."""

    cycle_start: date
    frequency: str
    timezone: str
    local_hour: int
    cancel_window_days: int
    delivery_unknown_attempts: int
    delivery_lead_days: dict[str, int]
    delivery_lead_days_default: int

    def delivery_days(self, store: str) -> int:
        return self.delivery_lead_days.get(store, self.delivery_lead_days_default)


def _qstr(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _money(amount: Decimal, currency: str) -> MoneyOut:
    return MoneyOut(amount=amount, currency=currency)


def _https_link(link: str | None) -> str | None:
    if link and link.startswith("https://"):
        return link
    return None


def _clip(value: str | None, max_len: int) -> str | None:
    return value[:max_len] if value is not None else None


def transition_order(order: Order, new_status: str) -> None:
    """명시 상태 머신 강제. confirmed→draft 및 inbound 주문 재확정을 차단한다."""
    if new_status == "confirmed" and order.inbound_at is not None:
        raise ApiError(409, "ORDER_INVALID_STATE", "inbound order cannot be reconfirmed")
    if order.status == new_status:
        return
    if new_status not in _ALLOWED_TRANSITIONS.get(order.status, set()):
        raise ApiError(409, "ORDER_INVALID_STATE", "invalid order state transition")
    order.status = new_status


async def _latest_plan(
    db: AsyncSession,
    user: User,
    *,
    period_start: date | None = None,
) -> MealPlan:
    stmt = (
        select(MealPlan)
        .where(MealPlan.user_id == user.id)
        .order_by(MealPlan.created_at.desc())
        .limit(1)
        .options(selectinload(MealPlan.meals).selectinload(Meal.ingredients))
    )
    if period_start is not None:
        stmt = stmt.where(MealPlan.period_start == period_start)
    plan = (await db.execute(stmt)).scalar_one_or_none()
    if plan is None:
        raise ApiError(404, "MEALPLAN_NOT_FOUND", "no meal plan yet")
    return plan


def _aggregate_incomplete(plan: MealPlan) -> list[FridgeNeed]:
    agg: dict[tuple[str, str], list] = {}
    for meal in plan.meals:
        if meal.completed_at is not None:
            continue
        for ingredient in meal.ingredients:
            if ingredient.quantity <= _Z:
                continue
            key = (ingredient.name.strip().lower(), ingredient.unit)
            if key not in agg:
                agg[key] = [ingredient.name.strip() or ingredient.name, Decimal("0")]
            agg[key][1] += ingredient.quantity
    return [
        FridgeNeed(name=name, quantity=quantity, unit=unit)
        for (_normalized, unit), (name, quantity) in agg.items()
    ]


def _split_shortfall(shortfall) -> tuple[list[ShortfallPreviewLine], list[ShortfallPreviewLine]]:
    needed: list[ShortfallPreviewLine] = []
    covered: list[ShortfallPreviewLine] = []
    for line in shortfall.items:
        preview = ShortfallPreviewLine(
            name=line.name,
            unit=line.unit,
            needed=line.needed,
            from_fridge=line.from_fridge,
            to_buy=line.to_buy,
        )
        (needed if Decimal(line.to_buy) > _Z else covered).append(preview)
    return needed, covered


def _unmatched_cart(
    needed: list[ShortfallPreviewLine], currency: str, notes: list[str]
) -> StoreCartResponse:
    return StoreCartResponse(
        items=[
            CartProduct(ingredient=line.name, matched=False, candidate_count=0)
            for line in needed
        ],
        total=_money(_Z, currency),
        matched_count=0,
        notes=list(notes),
    )


def _sanitize_cart(cart: StoreCartResponse) -> StoreCartResponse:
    for item in cart.items:
        item.link = _https_link(item.link)
    return cart


async def _store_connected(db: AsyncSession, user: User, store: str | None = None) -> bool:
    listed = await connection_service.list_connections(db, user)
    return any(
        connection.status == "connected"
        and (store is None or connection.store == store)
        for connection in listed.connections
    )


async def _draft_store(db: AsyncSession, user: User) -> str:
    supported = stores_for_country(user.country)
    connected = await db.scalar(
        select(StoreConnection.store)
        .where(
            StoreConnection.user_id == user.id,
            StoreConnection.store.in_(supported),
            StoreConnection.status == "connected",
        )
        .order_by(StoreConnection.created_at.asc())
        .limit(1)
    )
    return connected or supported[0]


async def _build_preview(
    db: AsyncSession,
    user: User,
    cycle_start: date,
    *,
    force_unmatched: bool = False,
    plan_period_start: date | None = None,
) -> OrderPreviewResponse:
    plan = await _latest_plan(db, user, period_start=plan_period_start)
    shortfall = await fridge_service.compute_shortfall(
        db, user.id, _aggregate_incomplete(plan)
    )
    needed, covered = _split_shortfall(shortfall)
    store_connected = await _store_connected(db, user)
    currency = user.currency
    notes: list[str] = []
    settings = get_settings()
    has_naver = bool(settings.naver_client_id and settings.naver_client_secret)

    if user.country == "US":
        note = "US price adapter is P2 — no estimated USD prices"
        notes.append(note)
        cart = _unmatched_cart(needed, "USD", [note])
    elif user.country == "KR" and has_naver and not force_unmatched:
        if needed:
            store_items = [
                StoreNeed(
                    name=line.name,
                    quantity=float(Decimal(line.to_buy)),
                    unit=line.unit,
                )
                for line in needed
            ]
            cart = _sanitize_cart(await store_service.build_cart(store_items, "kurly", 5))
        else:
            cart = _unmatched_cart(needed, "KRW", [])
        notes.extend(cart.notes)
    else:
        note = (
            "시세 조회 실패 — 가격 없는 needed 목록으로 생성"
            if force_unmatched
            else "네이버 API 키 미설정 — 검색 결과 없음(.env NAVER_CLIENT_ID/SECRET 필요)"
        )
        notes.append(note)
        cart = _unmatched_cart(needed, currency, [note])

    return OrderPreviewResponse(
        meal_plan_id=plan.id,
        store_connected=store_connected,
        country=user.country,
        needed=needed,
        covered=covered,
        cart=cart,
        estimated_total=cart.total,
        notes=notes,
        cycle_start=cycle_start,
    )


def _cart_by_ingredient(cart: StoreCartResponse) -> dict[str, CartProduct]:
    return {item.ingredient: item for item in cart.items}


def _snapshot_lines(
    preview: OrderPreviewResponse,
    exclude_names: list[str] | None = None,
) -> list[OrderItem]:
    excluded = {name.strip().lower() for name in (exclude_names or [])}
    cart_map = _cart_by_ingredient(preview.cart)
    lines: list[OrderItem] = []
    for line in preview.needed:
        if line.name.strip().lower() in excluded:
            continue
        quantity = Decimal(line.to_buy)
        matched = cart_map.get(line.name)
        price = matched.price if matched and matched.matched else None
        lines.append(
            OrderItem(
                name=line.name,
                quantity=quantity,
                unit=line.unit,
                line_type="needed",
                matched=bool(matched and matched.matched),
                title=_clip(matched.title if matched else None, 500),
                unit_price=price.amount if price else None,
                currency=price.currency if price else None,
                mall_name=_clip(matched.mall_name if matched else None, 100),
                link=_https_link(matched.link if matched else None),
            )
        )
    for line in preview.covered:
        quantity = Decimal(line.from_fridge)
        if quantity <= _Z:
            continue
        lines.append(
            OrderItem(
                name=line.name,
                quantity=quantity,
                unit=line.unit,
                line_type="covered",
                matched=False,
            )
        )
    return lines


def _item_out(row: OrderItem) -> OrderItemOut:
    unit_price = (
        _money(row.unit_price, row.currency)
        if row.unit_price is not None and row.currency
        else None
    )
    return OrderItemOut(
        name=row.name,
        quantity=_qstr(row.quantity),
        unit=row.unit,
        line_type=row.line_type,  # type: ignore[arg-type]
        matched=row.matched,
        title=row.title,
        unit_price=unit_price,
    )


def order_response(order: Order) -> OrderResponse:
    items = sorted(
        order.items, key=lambda row: (0 if row.line_type == "needed" else 1, str(row.id))
    )
    return OrderResponse(
        id=order.id,
        store=order.store,
        status=order.status,
        frequency=order.frequency,
        next_suggested_at=order.next_suggested_at,
        estimated_total=_money(order.estimated_total, order.currency),
        confirmed_at=order.confirmed_at,
        simulation=order.simulation,
        items=[_item_out(row) for row in items],
        cycle_start=order.cycle_start,
        delivery_eta=order.delivery_eta,
        inbound_at=order.inbound_at,
        delivery_state=order.delivery_state,  # type: ignore[arg-type]
        delivery_confirm_attempts=order.delivery_confirm_attempts,
        auto_confirmed=order.auto_confirmed,
        auto_confirm_at=order.auto_confirm_at,
        blocked_reason=order.blocked_reason,
    )


def _preview_from_order(order: Order, user: User, store_connected: bool) -> OrderPreviewResponse:
    if order.meal_plan_id is None:
        raise ApiError(409, "ORDER_INVALID_STATE", "draft order has no meal plan")
    needed: list[ShortfallPreviewLine] = []
    covered: list[ShortfallPreviewLine] = []
    cart_items: list[CartProduct] = []
    matched_count = 0
    for item in order.items:
        quantity = _qstr(item.quantity)
        if item.line_type == "needed":
            needed.append(
                ShortfallPreviewLine(
                    name=item.name,
                    unit=item.unit,
                    needed=quantity,
                    from_fridge="0",
                    to_buy=quantity,
                )
            )
            price = (
                _money(item.unit_price, item.currency)
                if item.unit_price is not None and item.currency
                else None
            )
            cart_items.append(
                CartProduct(
                    ingredient=item.name,
                    matched=item.matched,
                    title=item.title,
                    price=price,
                    mall_name=item.mall_name,
                    link=item.link,
                    candidate_count=1 if item.matched else 0,
                )
            )
            matched_count += int(item.matched)
        else:
            covered.append(
                ShortfallPreviewLine(
                    name=item.name,
                    unit=item.unit,
                    needed=quantity,
                    from_fridge=quantity,
                    to_buy="0",
                )
            )
    return OrderPreviewResponse(
        meal_plan_id=order.meal_plan_id,
        store_connected=store_connected,
        country=user.country,
        needed=needed,
        covered=covered,
        cart=StoreCartResponse(
            items=cart_items,
            total=_money(order.estimated_total, order.currency),
            matched_count=matched_count,
            notes=[],
        ),
        estimated_total=_money(order.estimated_total, order.currency),
        notes=[],
        order_id=order.id,
        status=order.status,  # type: ignore[arg-type]
        auto_confirm_at=order.auto_confirm_at,
        blocked_reason=order.blocked_reason,
        cycle_start=order.cycle_start,
    )


async def _open_order(
    db: AsyncSession, user_id: uuid.UUID, cycle_start: date
) -> Order | None:
    return (
        await db.execute(
            select(Order)
            .where(
                Order.user_id == user_id,
                Order.cycle_start == cycle_start,
                Order.status.in_(("draft", "awaiting_user")),
            )
            .options(selectinload(Order.items))
            .limit(1)
        )
    ).scalar_one_or_none()


async def has_saved_preview(
    db: AsyncSession, user_id: uuid.UUID, cycle_start: date
) -> bool:
    """현재 사이클의 저장 초안이 있어 외부 조회 없이 preview를 반환할 수 있는지 확인한다."""
    order_id = await db.scalar(
        select(Order.id)
        .where(
            Order.user_id == user_id,
            Order.cycle_start == cycle_start,
            Order.status.in_(("draft", "awaiting_user")),
        )
        .limit(1)
    )
    return order_id is not None


async def preview_order(
    db: AsyncSession,
    user: User,
    cycle_start: date,
    *,
    refresh: bool = False,
) -> OrderPreviewResponse:
    existing = await _open_order(db, user.id, cycle_start)
    if existing is not None and not refresh:
        return _preview_from_order(
            existing, user, await _store_connected(db, user, existing.store)
        )
    preview = await _build_preview(
        db,
        user,
        cycle_start,
        plan_period_start=cycle_start if existing is not None else None,
    )
    if existing is not None:
        existing.meal_plan_id = preview.meal_plan_id
        existing.estimated_total = preview.estimated_total.amount
        existing.currency = preview.estimated_total.currency
        existing.items = _snapshot_lines(preview)
        if existing.status == "draft":
            existing.blocked_reason = None
        await db.commit()
        return _preview_from_order(
            existing, user, await _store_connected(db, user, existing.store)
        )
    return preview


async def create_draft(
    db: AsyncSession,
    user: User,
    *,
    cycle_start: date,
    frequency: str,
    auto_confirm: bool,
    grace_hours: int,
    force_unmatched: bool = False,
) -> Order | None:
    existing = await _open_order(db, user.id, cycle_start)
    if existing is not None:
        return existing
    preview = await _build_preview(
        db,
        user,
        cycle_start,
        force_unmatched=force_unmatched,
        plan_period_start=cycle_start,
    )
    if not preview.needed:
        return None
    now = utcnow()
    order = Order(
        user_id=user.id,
        meal_plan_id=preview.meal_plan_id,
        store=await _draft_store(db, user),
        status="draft",
        frequency=frequency,
        cycle_start=cycle_start,
        next_suggested_at=now + timedelta(days=7 if frequency == "weekly" else 3),
        estimated_total=preview.estimated_total.amount,
        currency=preview.estimated_total.currency,
        simulation=True,
        confirmed_at=None,
        auto_confirm_at=(now + timedelta(hours=grace_hours) if auto_confirm else None),
        auto_confirmed=False,
        delivery_state="pending",
    )
    order.items = _snapshot_lines(preview)
    db.add(order)
    await db.flush()
    return order


def compute_delivery_eta(
    confirmed_at: datetime,
    *,
    timezone_name: str,
    lead_days: int,
    local_hour: int,
) -> datetime:
    tz = ZoneInfo(timezone_name)
    local_confirmed = confirmed_at.astimezone(tz)
    candidate = datetime.combine(
        local_confirmed.date() + timedelta(days=lead_days),
        time(local_hour),
        tzinfo=tz,
    ).astimezone(UTC)
    return max(candidate, confirmed_at.astimezone(UTC) + timedelta(hours=1))


async def _existing_confirmed(
    db: AsyncSession,
    user_id: uuid.UUID,
    cycle_start: date,
    *,
    exclude_order_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    stmt = select(Order.id).where(
        Order.user_id == user_id,
        Order.cycle_start == cycle_start,
        Order.status == "confirmed",
    )
    if exclude_order_id is not None:
        stmt = stmt.where(Order.id != exclude_order_id)
    return await db.scalar(stmt.limit(1))


async def _require_connected(db: AsyncSession, user: User, store: str) -> None:
    if store not in stores_for_country(user.country):
        raise ApiError(404, "STORE_NOT_SUPPORTED", f"Unsupported store: {store}")
    if not await _store_connected(db, user, store):
        raise ApiError(422, "STORE_NOT_CONNECTED", f"Store not connected: {store}")


async def _confirm_existing(
    db: AsyncSession,
    user: User,
    order: Order,
    *,
    auto_confirmed: bool,
    timezone_name: str,
    lead_days: int,
    local_hour: int,
    exclude_names: list[str] | None = None,
) -> OrderResponse:
    if order.status not in ("draft", "awaiting_user") or order.inbound_at is not None:
        raise ApiError(409, "ORDER_INVALID_STATE", "order cannot be confirmed")
    if await _existing_confirmed(
        db, user.id, order.cycle_start, exclude_order_id=order.id
    ):
        raise ApiError(
            409, "ORDER_ALREADY_CONFIRMED", "cycle already has a confirmed order"
        )
    await _require_connected(db, user, order.store)
    preview = await _build_preview(
        db,
        user,
        order.cycle_start,
        plan_period_start=order.cycle_start,
    )
    lines = _snapshot_lines(preview, exclude_names)
    if not any(line.line_type == "needed" for line in lines):
        raise ApiError(422, "NOTHING_TO_ORDER", "No items to buy after fridge shortfall")
    now = utcnow()
    transition_order(order, "confirmed")
    order.meal_plan_id = preview.meal_plan_id
    order.estimated_total = preview.estimated_total.amount
    order.currency = preview.estimated_total.currency
    order.items = lines
    order.confirmed_at = now
    order.delivery_eta = compute_delivery_eta(
        now,
        timezone_name=timezone_name,
        lead_days=lead_days,
        local_hour=local_hour,
    )
    order.auto_confirm_at = None
    order.auto_confirmed = auto_confirmed
    order.blocked_reason = None
    order.delivery_state = "pending"
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ApiError(
            409, "ORDER_ALREADY_CONFIRMED", "cycle already has a confirmed order"
        ) from exc
    return order_response(await _reload_order(db, order.id))


async def confirm_order(
    db: AsyncSession,
    user: User,
    store: str,
    *,
    cycle_start: date,
    frequency: str,
    timezone_name: str,
    lead_days: int,
    local_hour: int,
) -> OrderResponse:
    await _require_connected(db, user, store)
    if await _existing_confirmed(db, user.id, cycle_start):
        raise ApiError(
            409, "ORDER_ALREADY_CONFIRMED", "cycle already has a confirmed order"
        )
    open_order = await _open_order(db, user.id, cycle_start)
    if open_order is not None:
        transition_order(open_order, "cancelled")
        open_order.auto_confirm_at = None
    preview = await _build_preview(db, user, cycle_start)
    lines = _snapshot_lines(preview)
    if not any(line.line_type == "needed" for line in lines):
        raise ApiError(422, "NOTHING_TO_ORDER", "No items to buy after fridge shortfall")
    now = utcnow()
    order = Order(
        user_id=user.id,
        meal_plan_id=preview.meal_plan_id,
        store=store,
        status="confirmed",
        frequency=frequency,
        cycle_start=cycle_start,
        next_suggested_at=now + timedelta(days=7 if frequency == "weekly" else 3),
        estimated_total=preview.estimated_total.amount,
        currency=preview.estimated_total.currency,
        simulation=True,
        confirmed_at=now,
        delivery_eta=compute_delivery_eta(
            now,
            timezone_name=timezone_name,
            lead_days=lead_days,
            local_hour=local_hour,
        ),
        auto_confirmed=False,
        delivery_state="pending",
    )
    order.items = lines
    db.add(order)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ApiError(
            409, "ORDER_ALREADY_CONFIRMED", "cycle already has a confirmed order"
        ) from exc
    return order_response(await _reload_order(db, order.id))


async def _owned_order(
    db: AsyncSession,
    user: User,
    order_id: uuid.UUID,
    *,
    lock: bool = False,
) -> Order:
    owner_id = await db.scalar(select(Order.user_id).where(Order.id == order_id))
    if owner_id is None:
        raise ApiError(404, "ORDER_NOT_FOUND", "order not found")
    if owner_id != user.id:
        raise ApiError(403, "FORBIDDEN", "not your order")
    stmt = (
        select(Order)
        .where(Order.id == order_id, Order.user_id == user.id)
        .options(selectinload(Order.items))
    )
    if lock:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one()


async def approve_order(
    db: AsyncSession,
    user: User,
    order_id: uuid.UUID,
    *,
    exclude_names: list[str] | None,
    timezone_name: str,
    lead_days: int,
    local_hour: int,
) -> OrderResponse:
    order = await _owned_order(db, user, order_id, lock=True)
    return await _confirm_existing(
        db,
        user,
        order,
        auto_confirmed=False,
        timezone_name=timezone_name,
        lead_days=lead_days,
        local_hour=local_hour,
        exclude_names=exclude_names,
    )


async def auto_confirm_order(
    db: AsyncSession,
    user: User,
    order: Order,
    *,
    auto_confirm: bool,
    timezone_name: str,
    cycle_days: int,
    unmatched_threshold: Decimal,
    lead_days: int,
    local_hour: int,
) -> OrderResponse | None:
    """그레이스 자동확정 게이트. IntegrityError는 정상 idempotent skip."""
    if order.status != "draft" or order.auto_confirm_at is None:
        return None
    if await _existing_confirmed(
        db, user.id, order.cycle_start, exclude_order_id=order.id
    ):
        transition_order(order, "expired")
        order.auto_confirm_at = None
        await db.commit()
        return None

    blocked_reason: str | None = None
    if not auto_confirm:
        blocked_reason = "AUTO_CONFIRM_OFF"
    elif user.country == "US":
        blocked_reason = "US_NO_PRICE"
    elif not await _store_connected(db, user, order.store):
        blocked_reason = "STORE_DISCONNECTED"
    else:
        needed = [line for line in order.items if line.line_type == "needed"]
        unmatched = sum(1 for line in needed if not line.matched)
        ratio = Decimal(unmatched) / Decimal(len(needed)) if needed else Decimal("1")
        if ratio > unmatched_threshold:
            blocked_reason = "UNMATCHED_RATIO"

    budget = await db.scalar(select(BudgetPlan).where(BudgetPlan.user_id == user.id))
    if blocked_reason is None and budget is not None:
        limit = await budget_service.cycle_limit(
            db,
            user,
            order.cycle_start,
            cycle_days,
            timezone_name=timezone_name,
        )
        if budget.locked and order.estimated_total > limit:
            blocked_reason = "BUDGET_EXCEEDED"
    if blocked_reason is None:
        plan = await db.get(MealPlan, order.meal_plan_id) if order.meal_plan_id else None
        if plan is not None and plan.status == "over_budget":
            blocked_reason = "MEALPLAN_OVER_BUDGET"

    if blocked_reason is not None:
        transition_order(order, "awaiting_user")
        order.blocked_reason = blocked_reason
        order.auto_confirm_at = None
        await db.commit()
        return order_response(await _reload_order(db, order.id))

    try:
        return await _confirm_existing(
            db,
            user,
            order,
            auto_confirmed=True,
            timezone_name=timezone_name,
            lead_days=lead_days,
            local_hour=local_hour,
        )
    except ApiError as exc:
        if exc.code == "ORDER_ALREADY_CONFIRMED":
            await db.rollback()
            duplicate = await db.get(Order, order.id)
            if duplicate is not None and duplicate.status == "draft":
                transition_order(duplicate, "expired")
                duplicate.auto_confirm_at = None
                await db.commit()
            return None
        raise


async def cancel_order(
    db: AsyncSession,
    user: User,
    order_id: uuid.UUID,
    *,
    timezone_name: str,
    cancel_window_days: int,
) -> OrderResponse:
    order = await _owned_order(db, user, order_id, lock=True)
    if order.status != "confirmed":
        raise ApiError(409, "ORDER_INVALID_STATE", "only confirmed order can be cancelled")
    local_today = utcnow().astimezone(ZoneInfo(timezone_name)).date()
    if local_today > order.cycle_start + timedelta(days=cancel_window_days):
        raise ApiError(
            409, "ORDER_CANCEL_WINDOW_CLOSED", "order cancellation window is closed"
        )
    if order.inbound_at is not None:
        await fridge_service.delete_delivery_items(db, user.id, order.id)
    transition_order(order, "cancelled")
    order.auto_confirm_at = None
    await db.commit()
    return order_response(await _reload_order(db, order.id))


async def mark_inbound(
    db: AsyncSession,
    user_id: uuid.UUID,
    order_id: uuid.UUID,
    *,
    now: datetime | None = None,
    commit: bool = True,
) -> bool:
    """inbound_at compare-and-set 후 같은 트랜잭션에서 needed 라인만 등록."""
    now = now or utcnow()
    claimed = await db.scalar(
        update(Order)
        .where(
            Order.id == order_id,
            Order.user_id == user_id,
            Order.status == "confirmed",
            Order.inbound_at.is_(None),
        )
        .values(inbound_at=now, delivery_state="delivered")
        .returning(Order.id)
        .execution_options(synchronize_session=False)
    )
    if claimed is None:
        return False
    rows = (
        await db.execute(
            select(OrderItem).where(
                OrderItem.order_id == order_id, OrderItem.line_type == "needed"
            )
        )
    ).scalars().all()
    items = [
        FridgeItemCreate(
            name=row.name,
            quantity=row.quantity,
            unit=row.unit,
            expires_at=None,
            source="delivery",
        )
        for row in rows
    ]
    if items:
        await fridge_service.add_items(
            db,
            user_id,
            items,
            order_id=order_id,
            commit=False,
        )
    if commit:
        await db.commit()
    return True


async def update_delivery(
    db: AsyncSession,
    user: User,
    order_id: uuid.UUID,
    *,
    received: bool,
    unknown_attempts: int,
) -> OrderResponse:
    order = await _owned_order(db, user, order_id, lock=True)
    if order.status != "confirmed":
        raise ApiError(409, "ORDER_INVALID_STATE", "delivery requires confirmed order")
    if received:
        changed = await mark_inbound(db, user.id, order.id, commit=False)
        if not changed:
            order.delivery_state = "delivered"
        await db.commit()
        await db.refresh(order)
    else:
        if order.inbound_at is not None:
            await fridge_service.delete_delivery_items(db, user.id, order.id)
        order.inbound_at = None
        order.delivery_eta = (order.delivery_eta or utcnow()) + timedelta(days=1)
        order.delivery_confirm_attempts += 1
        order.delivery_state = (
            "unknown"
            if order.delivery_confirm_attempts >= unknown_attempts
            else "pending"
        )
        await db.commit()
    return order_response(await _reload_order(db, order.id))


async def _reload_order(db: AsyncSession, order_id: uuid.UUID) -> Order:
    return (
        await db.execute(
            select(Order).where(Order.id == order_id).options(selectinload(Order.items))
        )
    ).scalar_one()


async def get_latest_order(db: AsyncSession, user: User) -> OrderResponse:
    order = (
        await db.execute(
            select(Order)
            .where(Order.user_id == user.id)
            .order_by(Order.created_at.desc())
            .limit(1)
            .options(selectinload(Order.items))
        )
    ).scalar_one_or_none()
    if order is None:
        raise ApiError(404, "ORDER_NOT_FOUND", "no order yet")
    return order_response(order)


async def clear_open_auto_confirm(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(Order)
        .where(
            Order.user_id == user_id,
            Order.status.in_(("draft", "awaiting_user")),
        )
        .values(auto_confirm_at=None)
    )


async def restore_open_auto_confirm(
    db: AsyncSession, user_id: uuid.UUID, grace_hours: int, now: datetime
) -> None:
    orders = (
        await db.execute(
            select(Order).where(
                Order.user_id == user_id,
                Order.status == "draft",
                Order.auto_confirm_at.is_(None),
            )
        )
    ).scalars().all()
    for order in orders:
        proposed = order.created_at + timedelta(hours=grace_hours)
        order.auto_confirm_at = max(proposed, now + timedelta(hours=1))


async def cancel_open_order_for_cycle(
    db: AsyncSession, user_id: uuid.UUID, cycle_start: date
) -> None:
    order = await _open_order(db, user_id, cycle_start)
    if order is not None:
        transition_order(order, "cancelled")
        order.auto_confirm_at = None


async def expire_open_orders_before(
    db: AsyncSession, user_id: uuid.UUID, cycle_start: date
) -> None:
    orders = (
        await db.execute(
            select(Order).where(
                Order.user_id == user_id,
                Order.cycle_start < cycle_start,
                Order.status.in_(("draft", "awaiting_user")),
            )
        )
    ).scalars().all()
    for order in orders:
        transition_order(order, "expired")
        order.auto_confirm_at = None
