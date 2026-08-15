"""order 오케스트레이션 — 미완료 끼니 감산 preview + 시뮬레이션 확정 + fridge inbound.

POST 는 클라이언트 라인을 받지 않고 서버가 preview 를 재계산한다 (CWE-602).
확정 시 needed 수량만 fridge.add_items(source=order). covered inbound 금지.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import utcnow
from app.domains.auth.models import User
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


def _qstr(d: Decimal) -> str:
    """불필요한 소수 0 제거 (Numeric(10,3) '2.000' → '2'), 지수표기 방지."""
    return format(d.normalize(), "f")


def _money(amount: Decimal, currency: str) -> MoneyOut:
    return MoneyOut(amount=amount, currency=currency)


def _https_link(link: str | None) -> str | None:
    """상품 링크는 https 만 허용 — 그 외 null (CWE-79)."""
    if link and link.startswith("https://"):
        return link
    return None


def _clip(value: str | None, max_len: int) -> str | None:
    if value is None:
        return None
    return value[:max_len]


async def _latest_plan(db: AsyncSession, user: User) -> MealPlan:
    """최신 식단 1건 + 끼니·재료 eager load. 없으면 404 MEALPLAN_NOT_FOUND."""
    stmt = (
        select(MealPlan)
        .where(MealPlan.user_id == user.id)
        .order_by(MealPlan.created_at.desc())
        .limit(1)
        .options(selectinload(MealPlan.meals).selectinload(Meal.ingredients))
    )
    plan = (await db.execute(stmt)).scalar_one_or_none()
    if plan is None:
        raise ApiError(404, "MEALPLAN_NOT_FOUND", "no meal plan yet")
    return plan


def _aggregate_incomplete(plan: MealPlan) -> list[FridgeNeed]:
    """미완료 끼니 재료를 (name.strip().lower(), unit) 키로 합산. 표시명은 첫 등장(trim) 유지."""
    agg: dict[tuple[str, str], list] = {}
    for meal in plan.meals:
        if meal.completed_at is not None:
            continue
        for ing in meal.ingredients:
            if ing.quantity <= _Z:
                continue
            key = (ing.name.strip().lower(), ing.unit)
            if key not in agg:
                display = ing.name.strip() or ing.name
                agg[key] = [display, Decimal("0")]
            agg[key][1] += ing.quantity
    return [FridgeNeed(name=name, quantity=qty, unit=unit) for (_nl, unit), (name, qty) in agg.items()]


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
        if Decimal(line.to_buy) > _Z:
            needed.append(preview)
        else:
            covered.append(preview)
    return needed, covered


def _unmatched_cart(needed: list[ShortfallPreviewLine], currency: str, notes: list[str]) -> StoreCartResponse:
    items = [
        CartProduct(ingredient=line.name, matched=False, candidate_count=0)
        for line in needed
    ]
    return StoreCartResponse(
        items=items,
        total=_money(_Z, currency),
        matched_count=0,
        notes=list(notes),
    )


def _sanitize_cart(cart: StoreCartResponse) -> StoreCartResponse:
    """네이버 링크는 https 만 남긴다 (그 외 null)."""
    for item in cart.items:
        item.link = _https_link(item.link)
    return cart


async def _store_connected(db: AsyncSession, user: User) -> bool:
    listed = await connection_service.list_connections(db, user)
    return any(c.status == "connected" for c in listed.connections)


async def _build_preview(db: AsyncSession, user: User) -> OrderPreviewResponse:
    """최신 식단 미완료 재료 − 냉장고 = needed/covered. KR·키 있으면 build_cart(mall=kurly)."""
    plan = await _latest_plan(db, user)
    fridge_needed = _aggregate_incomplete(plan)
    shortfall = await fridge_service.compute_shortfall(db, user.id, fridge_needed)
    needed, covered = _split_shortfall(shortfall)
    store_connected = await _store_connected(db, user)
    country = user.country
    currency = user.currency
    notes: list[str] = []
    settings = get_settings()
    has_naver = bool(settings.naver_client_id and settings.naver_client_secret)

    if country == "US":
        # 네이버 호출 금지 · 가짜 USD 가격 금지 (US 시세 어댑터는 P2)
        note = "US price adapter is P2 — no estimated USD prices"
        notes.append(note)
        cart = _unmatched_cart(needed, "USD", [note])
        estimated = _money(_Z, "USD")
    elif country == "KR" and has_naver:
        if needed:
            # store.NeededItem.quantity 는 float|null — Decimal 은 호출 경계에서만 변환
            store_items = [
                StoreNeed(name=line.name, quantity=float(Decimal(line.to_buy)), unit=line.unit)
                for line in needed
            ]
            cart = _sanitize_cart(await store_service.build_cart(store_items, "kurly", 5))
            estimated = cart.total
            notes.extend(cart.notes)
        else:
            cart = _unmatched_cart(needed, "KRW", [])
            estimated = cart.total
    else:
        note = "네이버 API 키 미설정 — 검색 결과 없음(.env NAVER_CLIENT_ID/SECRET 필요)"
        notes.append(note)
        cart = _unmatched_cart(needed, currency, [note])
        estimated = cart.total

    return OrderPreviewResponse(
        meal_plan_id=plan.id,
        store_connected=store_connected,
        country=country,
        needed=needed,
        covered=covered,
        cart=cart,
        estimated_total=estimated,
        notes=notes,
    )


def _cart_by_ingredient(cart: StoreCartResponse) -> dict[str, CartProduct]:
    return {item.ingredient: item for item in cart.items}


def _item_out(row: OrderItem) -> OrderItemOut:
    unit_price = (
        _money(row.unit_price, row.currency) if row.unit_price is not None and row.currency else None
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


def _order_response(order: Order) -> OrderResponse:
    items = sorted(order.items, key=lambda r: (0 if r.line_type == "needed" else 1, str(r.id)))
    return OrderResponse(
        id=order.id,
        store=order.store,
        status=order.status,
        frequency=order.frequency,
        next_suggested_at=order.next_suggested_at,
        estimated_total=_money(order.estimated_total, order.currency),
        confirmed_at=order.confirmed_at,
        simulation=order.simulation,
        items=[_item_out(r) for r in items],
    )


async def preview_order(db: AsyncSession, user: User) -> OrderPreviewResponse:
    """GET /orders/preview — 스토어 연동 여부와 무관하게 200. 식단 없으면 404."""
    return await _build_preview(db, user)


async def confirm_order(db: AsyncSession, user: User, store: str) -> OrderResponse:
    """POST /orders — 서버 재계산 후 confirmed 스냅샷 + needed fridge inbound.

    한 트랜잭션: 주문·라인 저장 후 inbound. inbound 실패 시 주문 롤백.
    """
    if store not in stores_for_country(user.country):
        raise ApiError(404, "STORE_NOT_SUPPORTED", f"Unsupported store: {store}")

    row = await db.scalar(
        select(StoreConnection).where(
            StoreConnection.user_id == user.id, StoreConnection.store == store
        )
    )
    if row is None or row.status != "connected":
        raise ApiError(422, "STORE_NOT_CONNECTED", f"Store not connected: {store}")

    preview = await _build_preview(db, user)
    if not preview.needed:
        raise ApiError(422, "NOTHING_TO_ORDER", "No items to buy after fridge shortfall")

    now = utcnow()
    cart_map = _cart_by_ingredient(preview.cart)
    order = Order(
        user_id=user.id,
        meal_plan_id=preview.meal_plan_id,
        store=store,
        status="confirmed",
        frequency="weekly",
        next_suggested_at=now + timedelta(days=7),
        estimated_total=preview.estimated_total.amount,
        currency=preview.estimated_total.currency,
        simulation=True,
        confirmed_at=now,
    )

    lines: list[OrderItem] = []
    inbound: list[FridgeItemCreate] = []
    for line in preview.needed:
        qty = Decimal(line.to_buy)
        matched = cart_map.get(line.name)
        price = matched.price if matched and matched.matched else None
        lines.append(
            OrderItem(
                name=line.name,
                quantity=qty,
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
        inbound.append(
            FridgeItemCreate(
                name=line.name,
                quantity=qty,
                unit=line.unit,
                expires_at=None,
                source="order",
            )
        )
    for line in preview.covered:
        qty = Decimal(line.from_fridge)
        if qty <= _Z:
            continue
        lines.append(
            OrderItem(
                name=line.name,
                quantity=qty,
                unit=line.unit,
                line_type="covered",
                matched=False,
                title=None,
                unit_price=None,
                currency=None,
                mall_name=None,
                link=None,
            )
        )

    order.items = lines
    db.add(order)
    # add_items 가 session.commit 하므로 expire 되면 async lazy-load 가 실패한다 (#37 과 동일)
    db.expire_on_commit = False
    try:
        await fridge_service.add_items(db, user.id, inbound)
    except Exception:
        await db.rollback()
        raise

    return _order_response(order)


async def get_latest_order(db: AsyncSession, user: User) -> OrderResponse:
    """GET /orders/latest — created_at DESC LIMIT 1, 본인 스코프. 없으면 404 ORDER_NOT_FOUND."""
    stmt = (
        select(Order)
        .where(Order.user_id == user.id)
        .order_by(Order.created_at.desc())
        .limit(1)
        .options(selectinload(Order.items))
    )
    order = (await db.execute(stmt)).scalar_one_or_none()
    if order is None:
        raise ApiError(404, "ORDER_NOT_FOUND", "no order yet")
    return _order_response(order)
