"""QA 시나리오 하네스 — 주간 사이클 루프를 시간 이동(가상 시계)으로 한 바퀴 돌린다.

실행: cd backend && DATABASE_URL=...jaringobe_qa uv run python <this file>
외부 의존(네이버 시세·LLM·Expo)은 어댑터 경계에서 대역으로 치환한다.
"""
import asyncio
import os
import sys
import traceback
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://jaringobe:jaringobe@localhost:5433/jaringobe_qa"
)
os.environ["JWT_SECRET"] = "qa-secret"
os.environ["CYCLE_SCHEDULER_ENABLED"] = "false"
os.environ["REMINDER_SCHEDULER_ENABLED"] = "false"
os.environ["CYCLE_JITTER_MINUTES"] = "0"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["EXPO_ACCESS_TOKEN"] = ""
# 네이버 키가 "있는" 것처럼 두고 build_cart 를 대역으로 치환한다 (KR 매칭 경로 검증용)
os.environ["NAVER_CLIENT_ID"] = "qa-fake"
os.environ["NAVER_CLIENT_SECRET"] = "qa-fake"

from sqlalchemy import func, select, text  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.core.errors import ApiError  # noqa: E402
from app.domains.auth.models import User  # noqa: E402
from app.domains.budget import service as budget_service  # noqa: E402
from app.domains.budget.models import BudgetPlan  # noqa: E402
from app.domains.budget.schemas import MoneyOut  # noqa: E402
from app.domains.cycle import scheduler as cycle_scheduler  # noqa: E402
from app.domains.cycle import service as cycle_service  # noqa: E402
from app.domains.cycle.models import UserCycleSettings  # noqa: E402
from app.domains.cycle.policy import load_policy  # noqa: E402
from app.domains.fridge import service as fridge_service  # noqa: E402
from app.domains.fridge.models import FridgeItem  # noqa: E402
from app.domains.household.models import HouseholdMember  # noqa: E402
from app.domains.mealplan import fridge_hint as fridge_hint_mod  # noqa: E402
from app.domains.mealplan import generator as generator_mod  # noqa: E402
from app.domains.mealplan import service as mealplan_service  # noqa: E402
from app.domains.mealplan.models import Meal, MealIngredient, MealPlan  # noqa: E402
from app.domains.notification import sender  # noqa: E402
from app.domains.notification.models import NotificationLog  # noqa: E402
from app.domains.order import service as order_service  # noqa: E402
from app.domains.order.models import Order, OrderItem  # noqa: E402
from app.domains.store import service as store_service  # noqa: E402
from app.domains.store.connection_models import StoreConnection  # noqa: E402
from app.domains.store.schemas import CartProduct, StoreCartResponse, krw  # noqa: E402

# ---------------------------------------------------------------- 가상 시계
class Clock:
    now = datetime(2026, 9, 8, 0, 5, tzinfo=UTC)

    @classmethod
    def set(cls, value: datetime) -> datetime:
        cls.now = value
        return value


def _fake_utcnow() -> datetime:
    return Clock.now


for mod in (order_service, cycle_service, cycle_scheduler, mealplan_service, fridge_service,
            fridge_hint_mod, budget_service, sender):
    mod.utcnow = _fake_utcnow  # type: ignore[attr-defined]

# ---------------------------------------------------------------- 시세 대역 (네이버 경계)
PRICES = {"두부": 2500, "된장": 3000, "애호박": 1500, "쌀": 9000, "돼지고기앞다리": 12000,
          "양파": 2000, "고추장": 4000, "계란": 6000, "대파": 1800, "김치": 8000,
          "닭고기": 9000, "감자": 3000, "당근": 1200, "미역": 2500, "소고기": 15000}
CART_CALLS: list[list[str]] = []
CART_MODE = {"mode": "match", "multiplier": Decimal("1"), "unmatched": set()}


async def fake_build_cart(items, mall, max_pages):
    CART_CALLS.append([i.name for i in items])
    if CART_MODE["mode"] == "raise":
        raise RuntimeError("naver down")
    cart, total, matched = [], Decimal("0"), 0
    for it in items:
        if it.name in CART_MODE["unmatched"] or it.name not in PRICES:
            cart.append(CartProduct(ingredient=it.name, matched=False, candidate_count=0))
            continue
        price = Decimal(PRICES[it.name]) * CART_MODE["multiplier"]
        total += price
        matched += 1
        link = "http://insecure.example/x" if it.name == "대파" else "https://kurly.example/p"
        cart.append(CartProduct(ingredient=it.name, matched=True, title=f"<b>{it.name}</b> 상품",
                                price=krw(price), mall_name="마켓컬리", link=link, candidate_count=3))
    return StoreCartResponse(items=cart, total=krw(total), matched_count=matched, notes=[])


order_service.store_service.build_cart = fake_build_cart  # type: ignore[attr-defined]

# generate_meals 호출 캡처 (되먹임 힌트 검증)
GEN_CALLS: list[dict] = []
GEN_MODE = {"mode": "mock"}
_real_generate = generator_mod.generate_meals


async def capturing_generate_meals(*args, **kwargs):
    GEN_CALLS.append({"args": args, "kwargs": kwargs})
    if GEN_MODE["mode"] == "raise":
        raise RuntimeError("llm down")
    return await _real_generate(*args, **kwargs)


mealplan_service.generate_meals = capturing_generate_meals  # type: ignore[attr-defined]

# 푸시 발송 대역 — 실제 Expo 호출 금지, 발송 시도만 기록
PUSH_CALLS: list[tuple[uuid.UUID, str, str]] = []


async def fake_send_to_user(db, user_id, type_, template_key, path, variables=None):
    PUSH_CALLS.append((user_id, template_key, path))
    sender.build_message  # 경로 화이트리스트는 별도 검증
    return 0


from app.domains.notification import service as notification_service  # noqa: E402

notification_service.sender.send_to_user = fake_send_to_user  # type: ignore[attr-defined]

# ---------------------------------------------------------------- 결과 수집
RESULTS: list[tuple[str, str, str]] = []


def record(tid: str, ok: bool, note: str = "") -> None:
    RESULTS.append((tid, "PASS" if ok else "FAIL", note))
    print(f"[{'PASS' if ok else 'FAIL'}] {tid} {note}")


def check(tid: str, cond: bool, note: str = "") -> bool:
    record(tid, bool(cond), note)
    return bool(cond)


def policy():
    return replace(load_policy(), jitter_minutes=0)


# ---------------------------------------------------------------- 픽스처
async def make_user(db, nick, *, country="KR", tz="Asia/Seoul", anchor=0, frequency="weekly",
                    budget=Decimal("400000"), locked=True, store="kurly", connected=True,
                    last_seen=None, prev_completed=True, prev_cycle_start: date | None = None,
                    next_run_at=None, auto_confirm=True):
    currency = "USD" if country == "US" else "KRW"
    user = User(nickname=nick, country=country, currency=currency,
                last_seen_at=last_seen if last_seen is not None else Clock.now,
                onboarding_completed_at=Clock.now)
    db.add(user)
    await db.flush()
    plan = BudgetPlan(user_id=user.id, household_size=2, amount=budget, currency=currency,
                      meal_direction="health", source="onboarding", locked=locked, cuisines=[])
    db.add(plan)
    db.add(HouseholdMember(user_id=user.id, member_type="adult_m", age=30, position=0))
    if store:
        db.add(StoreConnection(user_id=user.id, store=store,
                               status="connected" if connected else "disconnected",
                               connected_at=Clock.now if connected else None))
    await db.flush()
    if prev_completed and prev_cycle_start:
        prior = MealPlan(user_id=user.id, budget_plan_id=plan.id, status="ready",
                         total_cost=Decimal("0"), currency=currency, region=country,
                         period_start=prev_cycle_start,
                         period_end=prev_cycle_start + timedelta(days=7))
        db.add(prior)
        await db.flush()
        db.add(Meal(meal_plan_id=prior.id, plan_date=prev_cycle_start + timedelta(days=1),
                    meal_type="dinner", recipe_name="완료 식사",
                    completed_at=datetime.combine(prev_cycle_start + timedelta(days=2),
                                                  datetime.min.time(), tzinfo=UTC)))
    settings = UserCycleSettings(user_id=user.id, enabled=True, frequency=frequency,
                                 anchor_weekday=anchor, timezone=tz, auto_confirm=auto_confirm,
                                 next_run_at=next_run_at)
    db.add(settings)
    await db.flush()
    if next_run_at is None and prev_cycle_start is not None:
        settings.next_run_at = cycle_service.generation_at(prev_cycle_start + timedelta(days=7), settings, policy())
    await db.commit()
    return user, plan, settings


async def add_fridge(db, user_id, rows):
    for name, qty, unit, exp in rows:
        db.add(FridgeItem(user_id=user_id, name=name, quantity=Decimal(qty), unit=unit,
                          expires_at=exp, source="manual"))
    await db.commit()


async def tick(now: datetime):
    Clock.set(now)
    result = await cycle_scheduler.process_cycle_tick(now)
    # 백그라운드 생성 태스크 수렴 대기
    for _ in range(50):
        pending = [t for t in cycle_scheduler._generation_tasks if not t.done()]
        if not pending:
            break
        await asyncio.sleep(0.1)
    return result


async def get(db, model, **where):
    stmt = select(model)
    for k, v in where.items():
        stmt = stmt.where(getattr(model, k) == v)
    return (await db.execute(stmt)).scalars().all()


async def fridge_qty(db, user_id):
    rows = await get(db, FridgeItem, user_id=user_id)
    out: dict[tuple[str, str], Decimal] = {}
    for r in rows:
        out[(r.name, r.unit)] = out.get((r.name, r.unit), Decimal(0)) + r.quantity
    return out


def plan_need(plan: MealPlan) -> dict[tuple[str, str], Decimal]:
    agg: dict[tuple[str, str], Decimal] = {}
    for m in plan.meals:
        if m.completed_at is not None:
            continue
        for ing in m.ingredients:
            agg[(ing.name, ing.unit)] = agg.get((ing.name, ing.unit), Decimal(0)) + ing.quantity
    return agg


async def load_plan(db, plan_id):
    from sqlalchemy.orm import selectinload
    return (await db.execute(select(MealPlan).where(MealPlan.id == plan_id).options(
        selectinload(MealPlan.meals).selectinload(Meal.ingredients)))).scalar_one()


async def load_order(db, order_id):
    from sqlalchemy.orm import selectinload
    return (await db.execute(select(Order).where(Order.id == order_id).options(
        selectinload(Order.items)))).scalar_one()


async def complete_one(uid, cycle_start, when):
    async with SessionLocal() as db:
        u = (await get(db, User, id=uid))[0]
        p = (await get(db, MealPlan, user_id=uid, period_start=cycle_start))[0]
        p = await load_plan(db, p.id)
        m = sorted(p.meals, key=lambda x: (x.plan_date, x.meal_type))[0]
        Clock.set(when)
        u.last_seen_at = when  # 앱 접속(로그인/refresh) 반영
        await db.commit()
        await mealplan_service.set_meal_completion(db, u, p.id, m.id, True)


def ctx_for(settings, cycle_start):
    p = policy()
    return order_service.OrderCycleContext(
        cycle_start=cycle_start, frequency=settings.frequency, timezone=settings.timezone,
        local_hour=p.stage_local_hour, cancel_window_days=p.cancel_window_days,
        delivery_unknown_attempts=p.delivery_unknown_attempts,
        delivery_lead_days=p.delivery_lead_days,
        delivery_lead_days_default=p.delivery_lead_days_default)


# ====================================================================== S1 전체 루프
async def s1_full_loop():
    """설정 → 생성(D-5) → 초안(D-2) → 자동확정(D-1) → 냉장고 등록(D) → 식사 차감 → 되먹임·감산 → 4주 한도."""
    C1 = date(2026, 9, 13)  # 일요일
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 5, tzinfo=UTC))
        user, budget, settings = await make_user(
            db, "S1-loop", prev_cycle_start=date(2026, 9, 6),
            next_run_at=datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        await add_fridge(db, user.id, [("계란", "4", "ea", date(2026, 9, 9)),
                                       ("쌀", "2000", "g", None),
                                       ("양파", "1", "ea", date(2026, 9, 10))])
        uid = user.id
    ORDERS: list[uuid.UUID] = []

    # --- D-5 생성
    GEN_CALLS.clear()
    r = await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        plans = await get(db, MealPlan, user_id=uid, period_start=C1)
        s = (await get(db, UserCycleSettings, user_id=uid))[0]
        check("S1-01 D-5 자동 식단 생성 접수·완료(mock LLM)",
              len(plans) == 1 and plans[0].status == "ready" and r["generated"] == 1,
              f"plans={len(plans)} status={[p.status for p in plans]} tick={r}")
        check("S1-02 접수 시 멱등키·다음 단계(D-2) 예약",
              s.last_generated_cycle_start == C1 and s.last_stage == "generated"
              and s.next_run_at == datetime(2026, 9, 11, 0, 0, tzinfo=UTC),
              f"stage={s.last_stage} next={s.next_run_at}")
        hint = GEN_CALLS[-1]["args"][-1] if GEN_CALLS else ""
        check("S1-03 냉장고 재고가 LLM 프롬프트 힌트로 전달(임박 우선 섹션 포함)",
              "Fridge inventory" in hint and "Use these FIRST" in hint and "계란 4 ea (expires 2026-09-09)" in hint
              and "쌀 2000 g" in hint and "Do NOT reduce ingredient quantities" in hint,
              hint.replace("\n", " | ")[:300])
        state = await cycle_service.build_cycle_state(db, (await get(db, User, id=uid))[0], s, now=Clock.now)
        check("S1-04 GET /cycle stage=generated, weeklyLimit=월 누적 안분(9/1~9/19 = 19일)",
              state.stage == "generated" and state.weekly_limit.amount == Decimal("253333.33"),
              f"stage={state.stage} limit={state.weekly_limit}")
    # 같은 시각 재실행 → 생성 중복 없음
    r2 = await tick(datetime(2026, 9, 8, 0, 6, tzinfo=UTC))
    async with SessionLocal() as db:
        plans = await get(db, MealPlan, user_id=uid, period_start=C1)
        check("S1-05 D-5 재실행 시 식단 중복 생성 없음(사용자당 주 1회)", len(plans) == 1 and r2["generated"] == 0,
              f"plans={len(plans)} tick={r2}")

    # --- D-2 초안
    CART_CALLS.clear()
    r = await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        orders = await get(db, Order, user_id=uid, cycle_start=C1)
        check("S1-06 D-2 주문 초안 1건 생성(status=draft)", len(orders) == 1 and orders[0].status == "draft",
              f"orders={[(o.status) for o in orders]}")
        o = await load_order(db, orders[0].id)
        ORDERS.append(o.id)
        plan = await load_plan(db, o.meal_plan_id)
        need = plan_need(plan)
        stock = await fridge_qty(db, uid)
        exp_needed = {k: v - min(v, stock.get(k, Decimal(0))) for k, v in need.items()}
        got_needed = {(i.name, i.unit): i.quantity for i in o.items if i.line_type == "needed"}
        got_covered = {(i.name, i.unit): i.quantity for i in o.items if i.line_type == "covered"}
        exp_needed_pos = {k: v for k, v in exp_needed.items() if v > 0}
        check("S1-07 초안 needed = 식단 재료 합 − 냉장고 재고 (동적 감산)",
              got_needed == exp_needed_pos,
              f"diff={ {k: (str(got_needed.get(k)), str(exp_needed_pos.get(k))) for k in set(got_needed)|set(exp_needed_pos) if got_needed.get(k)!=exp_needed_pos.get(k)} }")
        exp_cov = {k: min(v, stock.get(k, Decimal(0))) for k, v in need.items() if stock.get(k, Decimal(0)) >= v}
        check("S1-08a covered 라인 = 냉장고가 전량 충당하는 품목만(toBuy=0)", got_covered == exp_cov,
              f"got={ {k[0]: str(v) for k,v in got_covered.items()} } exp={ {k[0]: str(v) for k,v in exp_cov.items()} }")
        saved = await order_service.preview_order(db, (await get(db, User, id=uid))[0], C1)
        egg = next((l for l in saved.needed if l.name == "계란"), None)
        check("S1-08b [관찰] 저장 초안 preview 의 needed.fromFridge 가 실제 충당분(계란 4)을 보존하는가",
              egg is not None and egg.from_fridge == "4" and egg.needed == str(need[("계란", "ea")].normalize()),
              f"saved needed={egg.needed if egg else None} fromFridge={egg.from_fridge if egg else None} toBuy={egg.to_buy if egg else None} (실제 need={need.get(('계란','ea'))}, stock=4)")
        exp_total = sum(Decimal(PRICES[k[0]]) for k in exp_needed_pos if k[0] in PRICES)
        check("S1-09 추정 합계 = 매칭된 needed 시세 합(서버 계산)", o.estimated_total == exp_total,
              f"got={o.estimated_total} exp={exp_total}")
        check("S1-10 auto_confirm_at = 초안 생성 +24h, 시뮬레이션 고정",
              o.auto_confirm_at == datetime(2026, 9, 12, 0, 5, tzinfo=UTC) and o.simulation is True and o.confirmed_at is None,
              f"aca={o.auto_confirm_at}")
        check("S1-11 초안 생성 시 네이버 시세 조회 1회(needed 만)",
              len(CART_CALLS) == 1 and set(CART_CALLS[0]) == {k[0] for k in exp_needed_pos}, f"calls={len(CART_CALLS)}")
        check("S1-12 order_approval 알림 발송 시도(경로 /orders)",
              any(p[0] == uid and p[1] == "push.orderApproval" and p[2] == "/orders" for p in PUSH_CALLS))
        insecure = [i for i in o.items if i.name == "대파"]
        check("S1-13 비-https 상품 링크는 스냅샷에 null 저장(CWE-79)",
              bool(insecure) and insecure[0].link is None,
              f"link={insecure[0].link if insecure else None} title={insecure[0].title if insecure else None}")
        s = (await get(db, UserCycleSettings, user_id=uid))[0]
        state = await cycle_service.build_cycle_state(db, (await get(db, User, id=uid))[0], s, now=Clock.now)
        check("S1-14 GET /cycle stage=drafted + draftOrder/currentOrder 동기",
              state.stage == "drafted" and state.draft_order and state.draft_order.id == o.id
              and state.current_order and state.current_order.status == "draft")
    r2 = await tick(datetime(2026, 9, 11, 0, 6, tzinfo=UTC))
    async with SessionLocal() as db:
        orders = await get(db, Order, user_id=uid, cycle_start=C1)
        check("S1-15 D-2 재실행 시 초안 중복 없음", len(orders) == 1)

    # --- D-1 자동확정
    r = await tick(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
    async with SessionLocal() as db:
        o = await load_order(db, ORDERS[0])
        check("S1-16 24h 무응답 → 5중 게이트 통과 → 자동확정(auto_confirmed=true)",
              o.status == "confirmed" and o.auto_confirmed is True and o.auto_confirm_at is None
              and o.confirmed_at == datetime(2026, 9, 12, 0, 10, tzinfo=UTC),
              f"status={o.status} auto={o.auto_confirmed}")
        check("S1-17 delivery_eta = 확정 로컬일 + 1일(kurly) 09:00 KST",
              o.delivery_eta == datetime(2026, 9, 13, 0, 0, tzinfo=UTC), f"eta={o.delivery_eta}")
        check("S1-18 확정 시 냉장고 즉시 등록 안 함(inbound_at NULL)", o.inbound_at is None
              and not await get(db, FridgeItem, order_id=o.id))
        s = (await get(db, UserCycleSettings, user_id=uid))[0]
        state = await cycle_service.build_cycle_state(db, (await get(db, User, id=uid))[0], s, now=Clock.now)
        check("S1-19 GET /cycle stage=confirmed, draftOrder=null, currentOrder.deliveryEta 제공(v1.9)",
              state.stage == "confirmed" and state.draft_order is None and state.current_order.delivery_eta == o.delivery_eta)
    r2 = await tick(datetime(2026, 9, 12, 0, 11, tzinfo=UTC))
    async with SessionLocal() as db:
        n = await db.scalar(select(func.count(Order.id)).where(Order.user_id == uid, Order.status == "confirmed"))
        check("S1-20 자동확정 재실행 시 이중 확정 없음", n == 1 and r2["autoConfirmed"] == 0)

    # --- D 냉장고 등록
    before = None
    async with SessionLocal() as db:
        before = await fridge_qty(db, uid)
    PUSH_CALLS.clear()
    r = await tick(datetime(2026, 9, 13, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        o = await load_order(db, ORDERS[0])
        rows = await get(db, FridgeItem, order_id=o.id)
        needed = [i for i in o.items if i.line_type == "needed"]
        check("S1-21 delivery_eta 도달 → needed 라인만 냉장고 등록(source=delivery, order_id FK, expires null)",
              o.inbound_at == datetime(2026, 9, 13, 0, 5, tzinfo=UTC) and o.delivery_state == "delivered"
              and len(rows) == len(needed) and all(r_.source == "delivery" and r_.expires_at is None for r_ in rows)
              and {(r_.name, r_.unit, r_.quantity) for r_ in rows} == {(i.name, i.unit, i.quantity) for i in needed},
              f"rows={len(rows)} needed={len(needed)} inbound={o.inbound_at}")
        check("S1-22 fridge_inbound 알림(경로 /fridge)",
              any(p[0] == uid and p[1] == "push.fridgeInbound" and p[2] == "/fridge" for p in PUSH_CALLS))
        after = await fridge_qty(db, uid)
        s = (await get(db, UserCycleSettings, user_id=uid))[0]
        state = await cycle_service.build_cycle_state(db, (await get(db, User, id=uid))[0], s, now=Clock.now)
        check("S1-23 GET /cycle stage=delivered + mealCount/completedMealCount(v1.9)",
              state.stage == "delivered" and state.meal_plan.meal_count == 21 and state.meal_plan.completed_meal_count == 0,
              f"stage={state.stage} mp={state.meal_plan}")
    r2 = await tick(datetime(2026, 9, 13, 0, 6, tzinfo=UTC))
    async with SessionLocal() as db:
        after2 = await fridge_qty(db, uid)
        check("S1-24 등록 재실행 시 재고 두 배 되지 않음(inbound_at CAS)", after2 == after and r2["inbound"] == 0,
              f"tick={r2}")

    # --- 식사 완료 → 자동 차감
    async with SessionLocal() as db:
        user = (await get(db, User, id=uid))[0]
        o = await load_order(db, ORDERS[0])
        plan = await load_plan(db, o.meal_plan_id)
        day1 = sorted(plan.meals, key=lambda m: (m.plan_date, m.meal_type))[:3]
        stock_before = await fridge_qty(db, uid)
        consumed: dict[tuple[str, str], Decimal] = {}
        for m in day1:
            for ing in m.ingredients:
                consumed[(ing.name, ing.unit)] = consumed.get((ing.name, ing.unit), Decimal(0)) + ing.quantity
        for m in day1:
            Clock.set(datetime(2026, 9, 13, 3, 0, tzinfo=UTC) + timedelta(hours=day1.index(m)))
            await mealplan_service.set_meal_completion(db, user, plan.id, m.id, True)
        stock_after = await fridge_qty(db, uid)
        ok = True
        for k, q in consumed.items():
            exp = max(Decimal(0), stock_before.get(k, Decimal(0)) - q)
            if stock_after.get(k, Decimal(0)) != exp:
                ok = False
        check("S1-25 식사 완료 3끼 → 냉장고 자동 차감(임박 FIFO, 음수 없음)", ok,
              f"before={ {k[0]:str(v) for k,v in stock_before.items()} } after={ {k[0]:str(v) for k,v in stock_after.items()} }")
        plan = await load_plan(db, plan.id)
        snap_ok = all(m.fridge_deducted is not None for m in plan.meals if m.completed_at is not None)
        check("S1-26 완료 끼니에 fridge_deducted 스냅샷 기록", snap_ok)
        s = (await get(db, UserCycleSettings, user_id=uid))[0]
        state = await cycle_service.build_cycle_state(db, user, s, now=Clock.now)
        check("S1-27 completedMealCount=3 반영", state.meal_plan.completed_meal_count == 3)

    # --- C2: 되먹임 + 감산 + 한도 이월
    C2 = date(2026, 9, 20)
    GEN_CALLS.clear()
    r = await tick(datetime(2026, 9, 15, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        plans = await get(db, MealPlan, user_id=uid, period_start=C2)
        check("S1-28 C2 D-5: 지난 사이클 완료 3건+접속 → 활성 → 자동 생성", len(plans) == 1 and plans[0].status == "ready",
              f"tick={r}")
        hint = GEN_CALLS[-1]["args"][-1] if GEN_CALLS else ""
        stock = await fridge_qty(db, uid)
        residual = [k[0] for k, v in stock.items() if v > 0]
        check("S1-29 C2 생성 프롬프트에 배송 잔여 재고가 되먹임(냉장고→식단)",
              bool(residual) and all(name in hint for name in residual), f"residual={residual} hint_len={len(hint)}")
    CART_CALLS.clear()
    r = await tick(datetime(2026, 9, 18, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        orders = await get(db, Order, user_id=uid, cycle_start=C2)
        o2 = await load_order(db, orders[0].id) if orders else None
        if o2:
            ORDERS.append(o2.id)
        cov = [i for i in (o2.items if o2 else []) if i.line_type == "covered"]
        plan2 = await load_plan(db, o2.meal_plan_id)
        need2 = plan_need(plan2)
        full_price = sum(Decimal(PRICES[k[0]]) for k in need2 if k[0] in PRICES)
        check("S1-30 C2 초안: 잔여 재고만큼 covered 발생 + 추정가 감소(잔여분만큼 다음 주문 감산)",
              o2 is not None and len(cov) > 0 and o2.estimated_total < full_price,
              f"covered={[(c.name, str(c.quantity)) for c in cov]} total={o2.estimated_total if o2 else None} full={full_price}")
        prev = await load_order(db, ORDERS[0])
        check("S1-31 C1 주문은 C2 초안에 영향 없이 delivered 유지", prev.status == "confirmed" and prev.inbound_at is not None)
    # C2 자동확정 — 한도: 9/1~9/27 27일 안분 − C1 확정액
    async with SessionLocal() as db:
        user = (await get(db, User, id=uid))[0]
        c1 = await load_order(db, ORDERS[0])
        Clock.set(datetime(2026, 9, 19, 0, 10, tzinfo=UTC))
        limit2 = await budget_service.cycle_limit(db, user, C2, 7, timezone_name="Asia/Seoul")
        exp2 = (Decimal("400000") * 26 / 30).quantize(Decimal("0.01")) - c1.estimated_total
        check("S1-32 2주차 한도 = 26일 누적 안분 − 1주차 확정액 (0 붕괴 없음)", limit2 == exp2 and limit2 > 0,
              f"limit={limit2} exp={exp2} c1={c1.estimated_total}")
    r = await tick(datetime(2026, 9, 19, 0, 10, tzinfo=UTC))
    async with SessionLocal() as db:
        o2 = await load_order(db, ORDERS[1])
        check("S1-33 C2 자동확정 통과", o2.status == "confirmed" and o2.auto_confirmed, f"status={o2.status} reason={o2.blocked_reason}")
    await tick(datetime(2026, 9, 20, 0, 5, tzinfo=UTC))
    await complete_one(uid, C2, datetime(2026, 9, 20, 3, 0, tzinfo=UTC))
    # C3 (9/27): accrual_end=10/1 → 30일 전액 − (C1+C2)
    C3 = date(2026, 9, 27)
    await tick(datetime(2026, 9, 22, 0, 5, tzinfo=UTC))
    await tick(datetime(2026, 9, 25, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        user = (await get(db, User, id=uid))[0]
        c1 = await load_order(db, ORDERS[0]); c2 = await load_order(db, ORDERS[1])
        Clock.set(datetime(2026, 9, 26, 0, 10, tzinfo=UTC))
        limit3 = await budget_service.cycle_limit(db, user, C3, 7, timezone_name="Asia/Seoul")
        exp3 = Decimal("400000") - c1.estimated_total - c2.estimated_total
        check("S1-34 3주차(월 경계) 한도 = 월 전액 − 누적 확정 (다음 달 예산 미차용)", limit3 == max(Decimal(0), exp3),
              f"limit={limit3} exp={exp3}")
        o3 = (await get(db, Order, user_id=uid, cycle_start=C3))
        if o3:
            ORDERS.append(o3[0].id)
    await tick(datetime(2026, 9, 26, 0, 10, tzinfo=UTC))
    async with SessionLocal() as db:
        o3 = await load_order(db, ORDERS[2])
        check("S1-35 C3 자동확정 통과(예산 여유 시)", o3.status == "confirmed", f"status={o3.status} reason={o3.blocked_reason}")
    await tick(datetime(2026, 9, 27, 0, 5, tzinfo=UTC))
    await complete_one(uid, C3, datetime(2026, 9, 27, 3, 0, tzinfo=UTC))
    # C4 (10/4): 10월 1~10일 안분, 10월 확정액 0
    C4 = date(2026, 10, 4)
    await tick(datetime(2026, 9, 29, 0, 5, tzinfo=UTC))
    await tick(datetime(2026, 10, 2, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        user = (await get(db, User, id=uid))[0]
        Clock.set(datetime(2026, 10, 3, 0, 10, tzinfo=UTC))
        limit4 = await budget_service.cycle_limit(db, user, C4, 7, timezone_name="Asia/Seoul")
        check("S1-36 4주차(새 달) 한도 = 10/1~10/10 안분(10일), 9월 확정액 미차감", limit4 == (Decimal("400000") * 10 / 31).quantize(Decimal("0.01")),
              f"limit={limit4}")
        confirmed = await db.scalar(select(func.count(Order.id)).where(Order.user_id == uid, Order.status == "confirmed"))
        check("S1-37 4사이클 연속 확정 누적(1~3주차 confirmed 3건)", confirmed == 3, f"confirmed={confirmed}")
    await tick(datetime(2026, 10, 3, 0, 10, tzinfo=UTC))
    async with SessionLocal() as db:
        o4 = (await get(db, Order, user_id=uid, cycle_start=C4))
        check("S1-38 C4 자동확정 통과 → 4주 연속 한도 붕괴 없음", bool(o4) and o4[0].status == "confirmed",
              f"status={[o.status for o in o4]} reason={[o.blocked_reason for o in o4]}")
    return uid


# ====================================================================== S2 멱등·동시성
async def s2_concurrency():
    C = date(2026, 9, 13)
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 12, 0, 0, tzinfo=UTC))
        user, budget, settings = await make_user(db, "S2-cas", prev_cycle_start=date(2026, 9, 6))
        uid = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC))  # 생성
    await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC))  # 초안
    await tick(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))  # 확정
    async with SessionLocal() as db:
        o = (await get(db, Order, user_id=uid, cycle_start=C))
        check("S2-00 사전조건: 확정 주문 존재", bool(o) and o[0].status == "confirmed", f"{[x.status for x in o]}")
        oid = o[0].id
        needed_n = await db.scalar(select(func.count(OrderItem.id)).where(OrderItem.order_id == oid, OrderItem.line_type == "needed"))

    # 동시 CAS 5개 세션
    Clock.set(datetime(2026, 9, 13, 0, 5, tzinfo=UTC))

    async def cas():
        async with SessionLocal() as db:
            return await order_service.mark_inbound(db, uid, oid, now=Clock.now)

    results = await asyncio.gather(*(cas() for _ in range(5)), return_exceptions=True)
    async with SessionLocal() as db:
        rows = await get(db, FridgeItem, order_id=oid)
        check("S2-01 mark_inbound 5개 동시 실행 → 정확히 1회만 등록 (CAS)",
              sum(1 for r in results if r is True) == 1 and len(rows) == needed_n,
              f"results={results} rows={len(rows)} needed={needed_n}")

    # 사용자 received:true 와 스케줄러 inbound 동시 → 재고 1배
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 12, 0, 20, tzinfo=UTC))
        user, budget, settings = await make_user(db, "S2-race", prev_cycle_start=date(2026, 9, 6))
        uid2 = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 12, 0, 20, tzinfo=UTC))
    async with SessionLocal() as db:
        o = (await get(db, Order, user_id=uid2, cycle_start=C))[0]
        oid2 = o.id
        needed_n2 = await db.scalar(select(func.count(OrderItem.id)).where(OrderItem.order_id == oid2, OrderItem.line_type == "needed"))
        u2 = (await get(db, User, id=uid2))[0]
    Clock.set(datetime(2026, 9, 13, 0, 5, tzinfo=UTC))

    async def user_confirms():
        async with SessionLocal() as db:
            return await order_service.update_delivery(db, u2, oid2, received=True, unknown_attempts=3)

    res = await asyncio.gather(user_confirms(), cycle_scheduler.process_due_inbounds(Clock.now), user_confirms(),
                               return_exceptions=True)
    async with SessionLocal() as db:
        rows = await get(db, FridgeItem, order_id=oid2)
        o = await load_order(db, oid2)
        check("S2-02 사용자 '받았어요' × 스케줄러 등록 동시 → 재고 1배, delivered",
              len(rows) == needed_n2 and o.delivery_state == "delivered" and o.inbound_at is not None,
              f"rows={len(rows)} needed={needed_n2} res={[type(r).__name__ if isinstance(r, Exception) else 'ok' for r in res]}")

    # 동시 approve ×3 (초안) → 1 성공, 나머지 409
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 11, 0, 20, tzinfo=UTC))
        user, budget, settings = await make_user(db, "S2-approve", prev_cycle_start=date(2026, 9, 6))
        uid3 = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 11, 0, 20, tzinfo=UTC))
    async with SessionLocal() as db:
        o = (await get(db, Order, user_id=uid3, cycle_start=C))[0]
        oid3 = o.id
        u3 = (await get(db, User, id=uid3))[0]
    Clock.set(datetime(2026, 9, 11, 1, 0, tzinfo=UTC))

    async def approve():
        async with SessionLocal() as db:
            try:
                return (await order_service.approve_order(db, u3, oid3, exclude_names=None, timezone_name="Asia/Seoul",
                                                          lead_days=1, local_hour=9)).status
            except ApiError as e:
                return e.code

    res = await asyncio.gather(approve(), approve(), approve())
    async with SessionLocal() as db:
        n = await db.scalar(select(func.count(Order.id)).where(Order.user_id == uid3, Order.status == "confirmed"))
        check("S2-03 동시 승인 3회 → 확정 1건, 나머지 409", n == 1 and res.count("confirmed") == 1
              and all(r in ("confirmed", "ORDER_INVALID_STATE", "ORDER_ALREADY_CONFIRMED") for r in res), f"res={res} n={n}")

    # 수동 승인 직후 자동확정 스캔(TOCTOU) → 스킵, 이중 확정 없음
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 11, 0, 30, tzinfo=UTC))
        user, budget, settings = await make_user(db, "S2-toctou", prev_cycle_start=date(2026, 9, 6))
        uid4 = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 11, 0, 30, tzinfo=UTC))
    async with SessionLocal() as db:
        o = (await get(db, Order, user_id=uid4, cycle_start=C))[0]
        oid4 = o.id
        u4 = (await get(db, User, id=uid4))[0]
    Clock.set(datetime(2026, 9, 12, 0, 40, tzinfo=UTC))

    async def approve4():
        async with SessionLocal() as db:
            try:
                return (await order_service.approve_order(db, u4, oid4, exclude_names=None, timezone_name="Asia/Seoul",
                                                          lead_days=1, local_hour=9)).status
            except ApiError as e:
                return e.code

    res = await asyncio.gather(approve4(), cycle_scheduler.process_due_auto_confirms(Clock.now, policy()), approve4())
    async with SessionLocal() as db:
        n = await db.scalar(select(func.count(Order.id)).where(Order.user_id == uid4, Order.status == "confirmed"))
        o = await load_order(db, oid4)
        check("S2-04 수동 승인 × 자동확정 동시 → 확정 1건(부분 유니크 최종 방어선)", n == 1 and o.status == "confirmed",
              f"res={res} n={n} auto={o.auto_confirmed}")


# ====================================================================== S3 예외 흐름: 예산 게이트
async def s3_budget_gates():
    C = date(2026, 9, 13)
    # (a) 락 + 소액 예산 → BUDGET_EXCEEDED
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, budget, settings = await make_user(db, "S3-locked", budget=Decimal("30000"), locked=True,
                                                 prev_cycle_start=date(2026, 9, 6))
        uid = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC))
    PUSH_CALLS.clear()
    await tick(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
    async with SessionLocal() as db:
        o = (await get(db, Order, user_id=uid, cycle_start=C))[0]
        check("S3-01 예산 락 초과 → 자동확정 중단, awaiting_user/BUDGET_EXCEEDED, auto_confirm_at NULL",
              o.status == "awaiting_user" and o.blocked_reason == "BUDGET_EXCEEDED" and o.auto_confirm_at is None
              and o.reminded_at is not None, f"status={o.status} reason={o.blocked_reason}")
        check("S3-02 차단 시 재알림 1회(order_approval)", sum(1 for p in PUSH_CALLS if p[0] == uid and p[1] == "push.orderApproval") == 1)
        oid = o.id
        u = (await get(db, User, id=uid))[0]
        s = (await get(db, UserCycleSettings, user_id=uid))[0]
        state = await cycle_service.build_cycle_state(db, u, s, now=Clock.now)
        check("S3-03 GET /cycle stage=awaiting_user + blockedReason", state.stage == "awaiting_user"
              and state.draft_order.blocked_reason == "BUDGET_EXCEEDED")
    PUSH_CALLS.clear()
    r = await tick(datetime(2026, 9, 12, 1, 0, tzinfo=UTC))
    async with SessionLocal() as db:
        o = await load_order(db, oid)
        check("S3-04 awaiting_user 는 재판정·재알림 반복 없음", o.status == "awaiting_user" and r["autoConfirmed"] == 0
              and not PUSH_CALLS)
        # 사용자가 초과를 알고 승인 → 확정 허용 (락 상태에서도 명시 승인은 사용자 결정)
        u = (await get(db, User, id=uid))[0]
        resp = await order_service.approve_order(db, u, oid, exclude_names=None, timezone_name="Asia/Seoul", lead_days=1, local_hour=9)
        check("S3-05 awaiting_user → 사용자 명시 승인 → confirmed(auto_confirmed=false)", resp.status == "confirmed" and resp.auto_confirmed is False)
    # (b) 락 해제 + 소액 → 통과
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, budget, settings = await make_user(db, "S3-unlocked", budget=Decimal("400000"), locked=False,
                                                 prev_cycle_start=date(2026, 9, 6))
        uid2 = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC))
    CART_MODE["multiplier"] = Decimal("4")  # 초안 322,000 > 한도 253,333
    await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
    CART_MODE["multiplier"] = Decimal("1")
    async with SessionLocal() as db:
        o = (await get(db, Order, user_id=uid2, cycle_start=C))[0]
        check("S3-06 예산 락 해제 사용자는 한도 초과여도 자동확정 허용(경고만)", o.status == "confirmed" and o.auto_confirmed and o.estimated_total > Decimal("253333.33"),
              f"status={o.status} reason={o.blocked_reason} total={o.estimated_total}")
    # (c) 게이트는 초안 금액, 확정은 재계산 금액 — 시세가 사이에 오르면 한도를 넘겨 자동확정되는가?
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, budget, settings = await make_user(db, "S3-drift", budget=Decimal("400000"), locked=True,
                                                 prev_cycle_start=date(2026, 9, 6))
        uid3 = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        o = (await get(db, Order, user_id=uid3, cycle_start=C))[0]
        draft_total = o.estimated_total
        u = (await get(db, User, id=uid3))[0]
        Clock.set(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
        limit = await budget_service.cycle_limit(db, u, C, 7, timezone_name="Asia/Seoul")
    CART_MODE["multiplier"] = Decimal("4")  # 확정 시점 시세 4배 → 322,000 > 253,333
    await tick(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
    CART_MODE["multiplier"] = Decimal("1")
    async with SessionLocal() as db:
        o = (await get(db, Order, user_id=uid3, cycle_start=C))[0]
        check("S3-07 [결함 탐지] 예산 게이트가 초안 금액으로 판정 후 재계산 금액이 한도를 넘어도 자동확정되는가 (넘으면 FAIL)",
              not (o.status == "confirmed" and o.estimated_total > limit),
              f"draft_total={draft_total} limit={limit} confirmed_total={o.estimated_total} status={o.status} reason={o.blocked_reason}")


# ====================================================================== S4 미매칭·US·연동해제·over_budget
async def s4_other_gates():
    C = date(2026, 9, 13)
    # 미매칭 50% (임계 30%)
    CART_MODE["unmatched"] = set(PRICES) - {"쌀", "계란", "두부"}
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, *_ = await make_user(db, "S4-unmatched", prev_cycle_start=date(2026, 9, 6))
        uid = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
    CART_MODE["unmatched"] = set()
    async with SessionLocal() as db:
        o = (await get(db, Order, user_id=uid, cycle_start=C))[0]
        check("S4-01 미매칭 비율 > 30% → awaiting_user/UNMATCHED_RATIO, 미매칭 라인 unit_price null",
              o.status == "awaiting_user" and o.blocked_reason == "UNMATCHED_RATIO", f"status={o.status} reason={o.blocked_reason}")
    # US 사용자 — 시세 호출 금지, 0.00 USD, 항상 승인
    CART_CALLS.clear()
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, *_ = await make_user(db, "S4-us", country="US", tz="America/Los_Angeles", store="walmart",
                                   budget=Decimal("800"), prev_cycle_start=date(2026, 9, 6))
        uid2 = user.id
    # LA 09:00 = 16:00Z
    await tick(datetime(2026, 9, 8, 16, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 11, 16, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 12, 16, 10, tzinfo=UTC))
    async with SessionLocal() as db:
        o = (await get(db, Order, user_id=uid2, cycle_start=C))
        ok = bool(o) and o[0].status == "awaiting_user" and o[0].blocked_reason == "US_NO_PRICE" and o[0].currency == "USD" and o[0].estimated_total == 0
        check("S4-02 US: 가짜 USD 시세 없음(0.00 USD), 네이버 미호출, 항상 사용자 승인(US_NO_PRICE)",
              ok and not CART_CALLS, f"orders={[(x.status, x.blocked_reason, str(x.estimated_total), x.currency) for x in o]} naver_calls={len(CART_CALLS)}")
    # 스토어 연동 해제
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, *_ = await make_user(db, "S4-disc", prev_cycle_start=date(2026, 9, 6))
        uid3 = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        sc = (await get(db, StoreConnection, user_id=uid3))[0]
        sc.status = "disconnected"
        await db.commit()
    await tick(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
    async with SessionLocal() as db:
        o = (await get(db, Order, user_id=uid3, cycle_start=C))[0]
        check("S4-03 스토어 연동 해제 → STORE_DISCONNECTED (초안 생성은 연동 없이도 동작)",
              o.status == "awaiting_user" and o.blocked_reason == "STORE_DISCONNECTED")
        u = (await get(db, User, id=uid3))[0]
        try:
            await order_service.approve_order(db, u, o.id, exclude_names=None, timezone_name="Asia/Seoul", lead_days=1, local_hour=9)
            code = "OK"
        except ApiError as e:
            code = e.code
        check("S4-04 연동 해제 상태 승인 → 422 STORE_NOT_CONNECTED", code == "STORE_NOT_CONNECTED", code)
    # 식단 over_budget
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, *_ = await make_user(db, "S4-overbudget", prev_cycle_start=date(2026, 9, 6))
        uid4 = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        p = (await get(db, MealPlan, user_id=uid4, period_start=C))[0]
        p.status = "over_budget"
        await db.commit()
    await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
    async with SessionLocal() as db:
        o = (await get(db, Order, user_id=uid4, cycle_start=C))
        check("S4-05 식단 over_budget → 초안은 만들되 자동확정 금지(MEALPLAN_OVER_BUDGET)",
              bool(o) and o[0].status == "awaiting_user" and o[0].blocked_reason == "MEALPLAN_OVER_BUDGET",
              f"{[(x.status, x.blocked_reason) for x in o]}")
    # 자동확정 off 토글
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, *_ = await make_user(db, "S4-toggle", prev_cycle_start=date(2026, 9, 6))
        uid5 = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC))
    from app.domains.cycle.schemas import CycleSettingsUpdateRequest
    async with SessionLocal() as db:
        u = (await get(db, User, id=uid5))[0]
        Clock.set(datetime(2026, 9, 11, 1, 0, tzinfo=UTC))
        st = await cycle_service.update_settings(db, u, CycleSettingsUpdateRequest(auto_confirm=False))
        o = (await get(db, Order, user_id=uid5, cycle_start=C))[0]
        check("S4-06 autoConfirm=false → 열린 초안 auto_confirm_at NULL", st.auto_confirm is False and o.auto_confirm_at is None)
    await tick(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
    async with SessionLocal() as db:
        o = (await get(db, Order, user_id=uid5, cycle_start=C))[0]
        check("S4-07 자동확정 off 상태에서 24h 경과에도 draft 유지(항상 사용자 승인)", o.status == "draft")
        u = (await get(db, User, id=uid5))[0]
        Clock.set(datetime(2026, 9, 12, 0, 20, tzinfo=UTC))
        st = await cycle_service.update_settings(db, u, CycleSettingsUpdateRequest(auto_confirm=True))
        o = await load_order(db, o.id)
        check("S4-08 autoConfirm=true 복귀 → 지난 시각이면 now+1h 로 재설정", o.auto_confirm_at == datetime(2026, 9, 12, 1, 20, tzinfo=UTC),
              f"aca={o.auto_confirm_at}")


# ====================================================================== S5 배송 미도착·취소
async def s5_delivery_and_cancel():
    C = date(2026, 9, 13)
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, *_ = await make_user(db, "S5-delivery", prev_cycle_start=date(2026, 9, 6))
        uid = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 12, 0, 10, tzinfo=UTC)); await tick(datetime(2026, 9, 13, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        u = (await get(db, User, id=uid))[0]
        o = (await get(db, Order, user_id=uid, cycle_start=C))[0]
        oid = o.id
        rows0 = len(await get(db, FridgeItem, order_id=oid))
        Clock.set(datetime(2026, 9, 13, 2, 0, tzinfo=UTC))
        r1 = await order_service.update_delivery(db, u, oid, received=False, unknown_attempts=3)
        rows1 = len(await get(db, FridgeItem, order_id=oid))
        check("S5-01 '아직 안 왔어요' → 등록분 롤백, eta = 응답시각+1일, attempts=1, pending",
              rows0 > 0 and rows1 == 0 and r1.delivery_eta == datetime(2026, 9, 14, 2, 0, tzinfo=UTC)
              and r1.delivery_confirm_attempts == 1 and r1.delivery_state == "pending" and r1.inbound_at is None,
              f"rows {rows0}->{rows1} eta={r1.delivery_eta}")
    # 재등록 후 다시 아직 ×2 → unknown
    await tick(datetime(2026, 9, 14, 2, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        u = (await get(db, User, id=uid))[0]
        o = await load_order(db, oid)
        check("S5-02 eta 재도달 → 재등록", o.inbound_at is not None and len(await get(db, FridgeItem, order_id=oid)) > 0)
        Clock.set(datetime(2026, 9, 14, 3, 0, tzinfo=UTC))
        await order_service.update_delivery(db, u, oid, received=False, unknown_attempts=3)
        Clock.set(datetime(2026, 9, 15, 3, 0, tzinfo=UTC))
        r3 = await order_service.update_delivery(db, u, oid, received=False, unknown_attempts=3)
        check("S5-03 3회 '아직' → delivery_state=unknown, 자동 등록 중단", r3.delivery_state == "unknown" and r3.delivery_confirm_attempts == 3)
    r = await tick(datetime(2026, 9, 20, 0, 0, tzinfo=UTC))
    async with SessionLocal() as db:
        o = await load_order(db, oid)
        check("S5-04 unknown 주문은 스캔 ③ 제외(재등록 없음)", o.inbound_at is None and r["inbound"] == 0)
        # 다음 사이클 초안은 이 주문이 냉장고에 없다는 전제(등록 안 됐으므로 재고 0)
        stock = await fridge_qty(db, uid)
        check("S5-05 미도착 주문 재고는 냉장고에 없음 → 다음 초안 과소 발주 방지", all(v == 0 for v in stock.values()) or not stock,
              f"stock={ {k[0]: str(v) for k,v in stock.items()} }")
        u = (await get(db, User, id=uid))[0]
        r5 = await order_service.update_delivery(db, u, oid, received=True, unknown_attempts=3)
        check("S5-06 unknown 에서 '받았어요' → 등록 + delivered 복귀", r5.delivery_state == "delivered" and r5.inbound_at is not None
              and len(await get(db, FridgeItem, order_id=oid)) > 0)
    # 취소: 등록 후 일부 소비 → 남은 행만 삭제
    async with SessionLocal() as db:
        u = (await get(db, User, id=uid))[0]
        o = await load_order(db, oid)
        rows = await get(db, FridgeItem, order_id=oid)
        victim = rows[0]
        # 일부 소비 시뮬레이션: 한 행을 절반 차감, 한 행을 전부 소진(삭제)
        victim.quantity = victim.quantity / 2
        await db.delete(rows[1])
        await db.commit()
        Clock.set(datetime(2026, 9, 20, 1, 0, tzinfo=UTC))  # cycle_start 9/13 + 7일 = 9/20 → 창 내
        r6 = await order_service.cancel_order(db, u, oid, timezone_name="Asia/Seoul", cancel_window_days=7)
        remain = await get(db, FridgeItem, order_id=oid)
        check("S5-07 확정 취소 → 남은 배송분만 삭제(소비분 미복원), status=cancelled, inbound_at 감사 유지",
              r6.status == "cancelled" and not remain and r6.inbound_at is not None)
        try:
            Clock.set(datetime(2026, 9, 21, 1, 0, tzinfo=UTC))
            await order_service.cancel_order(db, u, oid, timezone_name="Asia/Seoul", cancel_window_days=7)
            code = "OK"
        except ApiError as e:
            code = e.code
        check("S5-08 취소된 주문 재취소 → 409 ORDER_INVALID_STATE", code == "ORDER_INVALID_STATE", code)
    # 취소 창 경과
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, *_ = await make_user(db, "S5-window", prev_cycle_start=date(2026, 9, 6))
        uid2 = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
    async with SessionLocal() as db:
        u = (await get(db, User, id=uid2))[0]
        o = (await get(db, Order, user_id=uid2, cycle_start=C))[0]
        Clock.set(datetime(2026, 9, 21, 0, 0, tzinfo=UTC))  # KST 9/21 09:00 > 9/13+7
        try:
            await order_service.cancel_order(db, u, o.id, timezone_name="Asia/Seoul", cancel_window_days=7)
            code = "OK"
        except ApiError as e:
            code = e.code
        check("S5-09 취소 허용 기간(7일) 경과 → 409 ORDER_CANCEL_WINDOW_CLOSED", code == "ORDER_CANCEL_WINDOW_CLOSED", code)


# ====================================================================== S6 실패 흐름
async def s6_failures():
    C = date(2026, 9, 13)
    # 초안 생성 실패(네이버 다운) → 백오프 1/5/15분 → 4회째 시세 없이 초안
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, *_ = await make_user(db, "S6-naverdown", prev_cycle_start=date(2026, 9, 6))
        uid = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC))
    CART_MODE["mode"] = "raise"
    CART_CALLS.clear()
    t = datetime(2026, 9, 11, 0, 5, tzinfo=UTC)
    await tick(t)
    async with SessionLocal() as db:
        s = (await get(db, UserCycleSettings, user_id=uid))[0]
        check("S6-01 [결함 탐지] 초안 실패 1회 → stage_attempts=1, next_run=+1분(백오프)", s.stage_attempts == 1 and s.next_run_at == t + timedelta(minutes=1),
              f"attempts={s.stage_attempts} next={s.next_run_at} (백오프 미동작이면 attempts=0, next 불변)")
    for i in range(1, 6):
        await tick(t + timedelta(minutes=i))
    async with SessionLocal() as db:
        s = (await get(db, UserCycleSettings, user_id=uid))[0]
        check("S6-02 [결함 탐지] 연속 실패 시 재시도가 1/5/15분 백오프를 따르는가 (매 tick 즉시 재시도면 FAIL)",
              len(CART_CALLS) <= 3, f"6 tick 동안 네이버 호출 {len(CART_CALLS)}회, attempts={s.stage_attempts}, next={s.next_run_at}")
        check("S6-03 실패 중 주문 행 생성 없음", not await get(db, Order, user_id=uid))
    for i in range(6, 30):
        await tick(t + timedelta(minutes=i))
    async with SessionLocal() as db:
        o = await get(db, Order, user_id=uid, cycle_start=C)
        s = (await get(db, UserCycleSettings, user_id=uid))[0]
        check("S6-04 [결함 탐지] 3회 초과 실패 시 시세 없이 needed 목록만으로 초안 생성(폴백) — 루프 지속",
              bool(o) and o[0].status == "draft" and o[0].estimated_total == 0 and s.last_stage == "drafted",
              f"orders={[(x.status, str(x.estimated_total)) for x in o]} stage={s.last_stage} attempts={s.stage_attempts} naver_calls_total={len(CART_CALLS)}")
    CART_MODE["mode"] = "match"
    await tick(t + timedelta(minutes=30))
    async with SessionLocal() as db:
        o = await get(db, Order, user_id=uid, cycle_start=C)
        s = (await get(db, UserCycleSettings, user_id=uid))[0]
        check("S6-05 시세 복구 후 다음 tick 에 초안 생성(루프 재개)", bool(o) and o[0].status == "draft" and s.last_stage == "drafted",
              f"orders={[(x.status, str(x.estimated_total)) for x in o]} stage={s.last_stage}")

    # 식단 생성 실패 → 익일 1회 재시도 → 재실패 → 포기(지난 식단 연장 없음, 초안 없음)
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, *_ = await make_user(db, "S6-llmdown", prev_cycle_start=date(2026, 9, 6))
        uid2 = user.id
    GEN_MODE["mode"] = "raise"
    PUSH_CALLS.clear()
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        p = await get(db, MealPlan, user_id=uid2, period_start=C)
        s = (await get(db, UserCycleSettings, user_id=uid2))[0]
        check("S6-06 생성 실패 → plan failed, generate_failed, 익일 09:00 재시도 예약(attempts=1)",
              bool(p) and p[0].status == "failed" and s.last_stage == "generate_failed" and s.stage_attempts == 1
              and s.next_run_at == datetime(2026, 9, 9, 0, 0, tzinfo=UTC), f"plan={[x.status for x in p]} stage={s.last_stage} next={s.next_run_at}")
    await tick(datetime(2026, 9, 9, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        p = await get(db, MealPlan, user_id=uid2, period_start=C)
        s = (await get(db, UserCycleSettings, user_id=uid2))[0]
        check("S6-07 익일 재시도 1회 → 재실패 → 포기, 다음 사이클 D-5 로 예약(중복 플랜 없음)",
              len(p) == 1 and p[0].status == "failed" and s.last_stage == "generate_failed"
              and s.next_run_at == datetime(2026, 9, 15, 0, 0, tzinfo=UTC), f"plans={len(p)} next={s.next_run_at}")
    GEN_MODE["mode"] = "mock"
    r = await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        check("S6-08 식단 없는 D-2: 초안 생성 안 함(지난 주 식단 연장 금지)", not await get(db, Order, user_id=uid2))
        s = (await get(db, UserCycleSettings, user_id=uid2))[0]
        u = (await get(db, User, id=uid2))[0]
        st = await cycle_service.build_cycle_state(db, u, s, now=Clock.now)
        check("S6-09 GET /cycle stage=generate_failed (수동 생성 CTA)", st.stage == "generate_failed", st.stage)
    # 다음 사이클(C2) — 실패 사용자도 정상 복귀? 완료 없음 → 휴면 판정
    await tick(datetime(2026, 9, 15, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        s = (await get(db, UserCycleSettings, user_id=uid2))[0]
        check("S6-10 지난 사이클 완료 0건 → 다음 사이클 skipped_dormant(안전장치)", s.last_stage == "skipped_dormant", s.last_stage)


# ====================================================================== S7 스킵·휴면·상한·만료
async def s7_skip_dormant_quota_expire():
    C = date(2026, 9, 13)
    from app.domains.cycle.schemas import CycleSettingsUpdateRequest
    # 스킵
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, *_ = await make_user(db, "S7-skip", prev_cycle_start=date(2026, 9, 6))
        uid = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        u = (await get(db, User, id=uid))[0]
        Clock.set(datetime(2026, 9, 11, 1, 0, tzinfo=UTC))
        st = await cycle_service.skip_cycle(db, u)
        o = (await get(db, Order, user_id=uid, cycle_start=C))[0]
        check("S7-01 이번 주 건너뛰기 → 초안 cancelled, stage=skipped_user, skippedCycleStart", st.stage == "skipped_user"
              and o.status == "cancelled" and st.skipped_cycle_start == C)
        st2 = await cycle_service.skip_cycle(db, u)
        check("S7-02 스킵 멱등(200 유지)", st2.stage == "skipped_user")
    r = await tick(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
    async with SessionLocal() as db:
        n = await db.scalar(select(func.count(Order.id)).where(Order.user_id == uid, Order.status == "confirmed"))
        check("S7-03 스킵 사이클에 자동확정 없음", n == 0)
    # 다음 사이클 정상 진행 (완료 없음 → 휴면이 되므로 완료 1건 seed)
    async with SessionLocal() as db:
        p = (await get(db, MealPlan, user_id=uid, period_start=C))[0]
        p = await load_plan(db, p.id)
        p.meals[0].completed_at = datetime(2026, 9, 14, 3, 0, tzinfo=UTC)
        await db.commit()
    await tick(datetime(2026, 9, 15, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        s = (await get(db, UserCycleSettings, user_id=uid))[0]
        check("S7-04 스킵 후 다음 사이클은 정상 생성(설정 유지)", s.last_stage == "generated" and s.last_generated_cycle_start == date(2026, 9, 20), s.last_stage)

    # 휴면: 접속 오래됨
    PUSH_CALLS.clear()
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, *_ = await make_user(db, "S7-dormant", prev_cycle_start=date(2026, 9, 6),
                                   last_seen=datetime(2026, 8, 1, tzinfo=UTC))
        uid2 = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        s = (await get(db, UserCycleSettings, user_id=uid2))[0]
        check("S7-05 14일 미접속 → skipped_dormant, 생성 없음, cycle_paused 알림 1회, dormant_since 기록",
              s.last_stage == "skipped_dormant" and not await get(db, MealPlan, user_id=uid2, period_start=C)
              and s.dormant_since is not None and sum(1 for p in PUSH_CALLS if p[0] == uid2 and p[1] == "push.cyclePaused") == 1,
              f"stage={s.last_stage} next={s.next_run_at}")
    PUSH_CALLS.clear()
    await tick(datetime(2026, 9, 15, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        check("S7-06 휴면 2회차: 추가 알림 없음(알림 폭탄 방지)", not [p for p in PUSH_CALLS if p[0] == uid2])
        s = (await get(db, UserCycleSettings, user_id=uid2))[0]
        u = (await get(db, User, id=uid2))[0]
        st = await cycle_service.build_cycle_state(db, u, s, now=Clock.now)
        check("S7-07 GET /cycle stage=skipped_dormant (복귀 카드)", st.stage == "skipped_dormant", st.stage)

    # 일일 상한
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        ua, *_ = await make_user(db, "S7-quota-a", prev_cycle_start=date(2026, 9, 6), next_run_at=datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        ub, *_ = await make_user(db, "S7-quota-b", prev_cycle_start=date(2026, 9, 6), next_run_at=datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        ida, idb = ua.id, ub.id
    async with SessionLocal() as db:
        already = await cycle_service.count_generated_today(db, datetime(2026, 9, 8, 0, 5, tzinfo=UTC))
    Clock.set(datetime(2026, 9, 8, 0, 5, tzinfo=UTC))
    await cycle_scheduler.process_due_settings(Clock.now, replace(policy(), daily_generation_limit=already + 1))
    for _ in range(50):
        if not [t for t in cycle_scheduler._generation_tasks if not t.done()]:
            break
        await asyncio.sleep(0.1)
    async with SessionLocal() as db:
        sa = (await get(db, UserCycleSettings, user_id=ida))[0]
        sb = (await get(db, UserCycleSettings, user_id=idb))[0]
        stages = sorted([sa.last_stage, sb.last_stage])
        deferred = sa if sa.last_stage == "deferred_quota" else sb
        check("S7-08 일일 상한 도달 → 이후 사용자 deferred_quota(실패 아님), 익일 09:00 이월",
              stages == ["deferred_quota", "generated"] and deferred.next_run_at == datetime(2026, 9, 9, 0, 0, tzinfo=UTC),
              f"stages={stages} next={deferred.next_run_at}")

    # 오래된 초안 만료: awaiting_user 초안이 다음 D-5 에 expired
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, *_ = await make_user(db, "S7-expire", budget=Decimal("30000"), locked=True, prev_cycle_start=date(2026, 9, 6))
        uid3 = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
    async with SessionLocal() as db:
        p = (await get(db, MealPlan, user_id=uid3, period_start=C))[0]
        p = await load_plan(db, p.id)
        p.meals[0].completed_at = datetime(2026, 9, 14, 3, 0, tzinfo=UTC)
        await db.commit()
    await tick(datetime(2026, 9, 15, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        o = (await get(db, Order, user_id=uid3, cycle_start=C))[0]
        check("S7-09 승인되지 않은 초안은 다음 사이클 D-5 에 expired 처리", o.status == "expired" and o.auto_confirm_at is None, o.status)


# ====================================================================== S8 상태 머신·엣지
async def s8_state_machine_and_edges():
    C = date(2026, 9, 13)
    # 순수 전이 함수
    o = Order(status="confirmed", inbound_at=None)
    try:
        order_service.transition_order(o, "draft"); c1 = "OK"
    except ApiError as e:
        c1 = e.code
    o2 = Order(status="awaiting_user", inbound_at=datetime(2026, 9, 13, tzinfo=UTC))
    try:
        order_service.transition_order(o2, "confirmed"); c2 = "OK"
    except ApiError as e:
        c2 = e.code
    o3 = Order(status="failed")
    try:
        order_service.transition_order(o3, "draft"); c3 = "OK"
    except ApiError as e:
        c3 = e.code
    check("S8-01 confirmed→draft 역행 / inbound 주문 재확정 / failed→* 전이 모두 409", c1 == c2 == c3 == "ORDER_INVALID_STATE", f"{c1},{c2},{c3}")

    # 엣지 A: D-2 이전 수동 확정(POST /orders) 후 스케줄러 D-2 초안이 또 생기는가
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, budget, settings = await make_user(db, "S8-manual-first", prev_cycle_start=date(2026, 9, 6))
        uid = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        u = (await get(db, User, id=uid))[0]
        Clock.set(datetime(2026, 9, 9, 0, 0, tzinfo=UTC))
        resp = await order_service.confirm_order(db, u, "kurly", cycle_start=C, frequency="weekly", timezone_name="Asia/Seoul", lead_days=1, local_hour=9)
        check("S8-02 사전조건: D-2 이전 수동 확정 성공", resp.status == "confirmed")
    await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        orders = await get(db, Order, user_id=uid, cycle_start=C)
        statuses = sorted(o.status for o in orders)
        s = (await get(db, UserCycleSettings, user_id=uid))[0]
        u = (await get(db, User, id=uid))[0]
        st = await cycle_service.build_cycle_state(db, u, s, now=Clock.now)
        check("S8-03 [결함 탐지] 확정 주문이 있는 사이클에 D-2 스케줄러가 새 초안을 만들지 않는가",
              statuses == ["confirmed"], f"orders={statuses} stage={st.stage}")
        check("S8-04 [결함 탐지] 확정된 사이클의 GET /cycle stage 가 confirmed 인가(drafted 로 덮이지 않는가)", st.stage == "confirmed", st.stage)
        if len(orders) > 1:
            draft = next(o for o in orders if o.status == "draft")
            Clock.set(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
    await tick(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
    async with SessionLocal() as db:
        n = await db.scalar(select(func.count(Order.id)).where(Order.user_id == uid, Order.status == "confirmed"))
        check("S8-05 그 경우에도 이중 확정은 없음(멱등 최종 방어선)", n == 1, f"confirmed={n}")

    # 엣지 B: 월초 사이클(10/1 목요일, anchor=4) — 9/30 확정분이 10월 한도에서 차감되는가
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 26, 0, 0, tzinfo=UTC))
        user, budget, settings = await make_user(db, "S8-monthedge", anchor=4, budget=Decimal("400000"), prev_cycle_start=date(2026, 9, 24))
        uid2 = user.id
    C_oct1 = date(2026, 10, 1)
    await tick(datetime(2026, 9, 26, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 29, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 30, 0, 10, tzinfo=UTC))
    async with SessionLocal() as db:
        o = await get(db, Order, user_id=uid2, cycle_start=C_oct1)
        check("S8-06 사전조건: 10/1 사이클 주문이 9/30 에 확정", bool(o) and o[0].status == "confirmed", f"{[(x.status, x.blocked_reason) for x in o]}")
        total = o[0].estimated_total if o else Decimal(0)
        u = (await get(db, User, id=uid2))[0]
        Clock.set(datetime(2026, 10, 7, 0, 10, tzinfo=UTC))
        limit_oct8 = await budget_service.cycle_limit(db, u, date(2026, 10, 8), 7, timezone_name="Asia/Seoul")
        share = (Decimal("400000") * 14 / 31).quantize(Decimal("0.01"))  # 10/1~10/14
        check("S8-07 [결함 탐지] 10/8 사이클 한도가 10/1 사이클 확정액을 차감하는가 (confirmed_at 이 9월이라 누락되면 FAIL)",
              limit_oct8 == share - total, f"limit={limit_oct8} share={share} oct1_total={total} (미차감 시 limit==share)")

    # 엣지 C: 확정 후 타임존 변경 → 초안 중복?
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, budget, settings = await make_user(db, "S8-tzchange", prev_cycle_start=date(2026, 9, 6))
        uid3 = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
    from app.domains.cycle.schemas import CycleSettingsUpdateRequest
    async with SessionLocal() as db:
        u = (await get(db, User, id=uid3))[0]
        Clock.set(datetime(2026, 9, 12, 2, 0, tzinfo=UTC))
        st = await cycle_service.update_settings(db, u, CycleSettingsUpdateRequest(timezone="Asia/Tokyo"))
        s = (await get(db, UserCycleSettings, user_id=uid3))[0]
        check("S8-08 [결함 탐지] 확정 후 타임존 변경 → next_run_at 이 미래로 재계산되는가(과거 D-2 로 되돌아가면 FAIL)", s.next_run_at is not None and s.next_run_at > Clock.now,
              f"next={s.next_run_at} stage={st.stage}")
    await tick(datetime(2026, 9, 12, 2, 1, tzinfo=UTC)); await tick(datetime(2026, 9, 12, 2, 2, tzinfo=UTC))
    async with SessionLocal() as db:
        orders = await get(db, Order, user_id=uid3, cycle_start=C)
        check("S8-09 [결함 탐지] 타임존 변경 후 같은 사이클에 초안이 추가 생성되지 않는가", sorted(o.status for o in orders) == ["confirmed"],
              f"{sorted(o.status for o in orders)}")

    # 엣지 D: 초안 상태에서 recalculate 는 awaiting_user 상태·차단사유 유지
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, *_ = await make_user(db, "S8-recalc", budget=Decimal("30000"), locked=True, prev_cycle_start=date(2026, 9, 6))
        uid4 = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
    async with SessionLocal() as db:
        u = (await get(db, User, id=uid4))[0]
        o = (await get(db, Order, user_id=uid4, cycle_start=C))[0]
        r = await order_service.recalculate_order(db, u, o.id)
        check("S8-10 awaiting_user 재계산 → 상태·blockedReason·autoConfirmAt(NULL) 유지, 게이트 대체 통과 없음",
              r.status == "awaiting_user" and r.blocked_reason == "BUDGET_EXCEEDED" and r.auto_confirm_at is None)

    # 엣지 E: 냉장고 재고가 전부 충당 → nothing_to_order, 알림 없음
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, *_ = await make_user(db, "S8-fullfridge", prev_cycle_start=date(2026, 9, 6))
        uid5 = user.id
        await add_fridge(db, uid5, [(n, "99999", u_, None) for n, u_ in
                                    [("두부","ea"),("된장","g"),("애호박","ea"),("쌀","g"),("돼지고기앞다리","g"),("양파","ea"),("고추장","g"),("계란","ea"),("대파","ea"),("김치","g"),("닭고기","g"),("감자","ea"),("당근","ea"),("미역","g"),("소고기","g")]])
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC))
    PUSH_CALLS.clear()
    await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC))
    async with SessionLocal() as db:
        s = (await get(db, UserCycleSettings, user_id=uid5))[0]
        u = (await get(db, User, id=uid5))[0]
        st = await cycle_service.build_cycle_state(db, u, s, now=Clock.now)
        check("S8-11 냉장고 전부 충당 → 주문 없음, stage=nothing_to_order, 승인 알림 없음",
              st.stage == "nothing_to_order" and not await get(db, Order, user_id=uid5) and not [p for p in PUSH_CALLS if p[0] == uid5],
              st.stage)

    # 엣지 F: 알림 딥링크 화이트리스트(CWE-601)
    from app.domains.notification.models import DeviceToken
    dev = DeviceToken(user_id=uuid.uuid4(), token="ExponentPushToken[x]", platform="ios", locale="ko")
    bad = []
    for path in ("https://evil.example/orders", "jaringobe://x", "/orders/../admin", "//evil.example", "/settings"):
        try:
            sender.build_message(dev, "push.orderApproval", path)
            bad.append(path)
        except ValueError:
            pass
    check("S8-12 푸시 딥링크 외부 URL·스킴·비허용 경로 차단", not bad, f"allowed_unexpectedly={bad}")
    msg = sender.build_message(dev, "push.orderApproval", "/orders")
    body = str(msg)
    check("S8-13 푸시 본문에 금액·예산·가구 정보 없음(CWE-359)", not any(ch.isdigit() for ch in msg.get("title", "") + msg.get("body", ""))
          and "₩" not in body and "KRW" not in body, body[:200])

    # 엣지 H: 자동확정 중 IntegrityError/ALREADY_CONFIRMED 경합 핸들러 (rollback 후 만료 객체 접근)
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, *_ = await make_user(db, "S8-race-handler", prev_cycle_start=date(2026, 9, 6))
        uid7 = user.id
    await tick(datetime(2026, 9, 8, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 11, 0, 5, tzinfo=UTC))
    real_existing = order_service._existing_confirmed
    calls = {"n": 0}

    async def racy_existing(db, user_id, cycle_start, *, exclude_order_id=None):
        calls["n"] += 1
        if calls["n"] == 2:  # 게이트 ⓪ 통과 후 _confirm_existing 내부 검사에서 경합 발생 시뮬레이션
            return uuid.uuid4()
        return await real_existing(db, user_id, cycle_start, exclude_order_id=exclude_order_id)

    order_service._existing_confirmed = racy_existing
    Clock.set(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
    try:
        await cycle_scheduler.process_due_auto_confirms(Clock.now, policy())
    finally:
        order_service._existing_confirmed = real_existing
    async with SessionLocal() as db:
        o = (await get(db, Order, user_id=uid7, cycle_start=C))[0]
        check("S8-15 [결함 탐지] 자동확정 경합(ALREADY_CONFIRMED) 핸들러가 예외 없이 초안을 expired 로 정리하는가",
              o.status == "expired", f"status={o.status} auto_confirm_at={o.auto_confirm_at} (MissingGreenlet 시 draft 유지)")

    # 엣지 G: biweekly 프로파일 — 3/4일 교대, 그레이스 12h
    async with SessionLocal() as db:
        Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, *_ = await make_user(db, "S8-biweekly", frequency="biweekly", anchor=0, prev_cycle_start=date(2026, 9, 6))
        uid6 = user.id
        w = cycle_service.cycle_window("biweekly", 0, "Asia/Seoul", Clock.now)
        check("S8-14 biweekly 사이클 창: 9/8 기준 다음 배송일 9/9(수), 길이 4일", w.cycle_start == date(2026, 9, 9) and w.cycle_days == 4, f"{w}")


# ====================================================================== 실행
async def main():
    for fn in (s1_full_loop, s2_concurrency, s3_budget_gates, s4_other_gates, s5_delivery_and_cancel,
               s6_failures, s7_skip_dormant_quota_expire, s8_state_machine_and_edges):
        CART_MODE.update({"mode": "match", "multiplier": Decimal("1"), "unmatched": set()})
        GEN_MODE["mode"] = "mock"
        try:
            await fn()
        except Exception:
            record(f"{fn.__name__} EXC", False, traceback.format_exc()[-1500:])
    print("\n==== SUMMARY ====")
    p = sum(1 for r in RESULTS if r[1] == "PASS"); f = len(RESULTS) - p
    print(f"PASS {p} / FAIL {f}")
    for r in RESULTS:
        if r[1] == "FAIL":
            print("  FAIL", r[0], r[2][:400])
    import json
    with open(os.path.join(os.path.dirname(__file__), "qa_loop_results.json"), "w") as fh:
        json.dump(RESULTS, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    asyncio.run(main())
