"""mealplan 오케스트레이션 — 생성(LLM)→알레르기 재검증→기준가 비용→예산 검산·재시도→저장.

예산 기준: 유저의 budget_plans.amount (유저당 1개). 초과 시 status=over_budget 투명 노출.
v1.5: 생성/재생성은 202 비동기 — 요청 시 processing 행 생성, BackgroundTasks 로 실제 생성.
"""

from __future__ import annotations

import calendar
import logging
import uuid
from collections import Counter
from datetime import timedelta
from time import monotonic
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.security import utcnow
from app.domains.auth.models import User
from app.domains.budget.models import BudgetPlan
from app.domains.budget.schemas import MoneyOut
from app.domains.mealplan.generator import generate_meals
from app.domains.mealplan.models import Meal, MealIngredient, MealPlan
from app.domains.mealplan.pricing import DBPriceProvider
from app.domains.fridge import service as fridge_service
from app.domains.fridge.schemas import NeededItem as FridgeNeed
from app.domains.mealplan.schemas import (
    BudgetSummary,
    MealIngredientOut,
    MealOut,
    FirstCycleOrder,
    parse_steps,
    MealPlanCartResponse,
    MealPlanCreateRequest,
    MealPlanResponse,
    MonthlyPlanRequest,
    MonthlyPlanResponse,
    RegenerateRequest,
)
from app.domains.notification import service as notification_service
from app.domains.store import service as store_service
from app.domains.store.schemas import NeededItem as StoreNeed

logger = logging.getLogger(__name__)

_CENT = Decimal("0.01")
MAX_BUDGET_RETRIES = 3
# 플랜 status 열거 (v1.5 — CHECK 제약 없음, 서비스 레벨 검증만. db-schema.md 2-8 정정)
PLAN_STATUSES = ("processing", "ready", "over_budget", "failed")
# 응답에서 meals/budgetSummary/period 를 숨기는 상태 (api-spec §3-2 v1.5)
_STUB_STATUSES = ("processing", "failed")
# 재시도 진입 허용 시한(초). 재시도는 이 시점 이전에만 시작되므로
# 최악 응답 = 25 + LLM_TIMEOUT(60) = 85초 < 프론트 타임아웃 90초 (api-spec §3-2 over_budget 201 허용)
GENERATION_TIME_BUDGET_SECONDS = 25.0
MEAL_DIRECTION_HINT = {"health": "balanced", "diet": "diet", "hearty": "hearty", "kids": "kids"}


async def _get_budget(db: AsyncSession, user: User) -> BudgetPlan:
    budget = await db.scalar(select(BudgetPlan).where(BudgetPlan.user_id == user.id))
    if budget is None:
        raise ApiError(409, "BUDGET_PLAN_REQUIRED", "Create a budget plan first")
    return budget


def _check_allergies(drafts: list[dict], allergies: list[str]) -> list[str]:
    allergs = [a.lower().strip() for a in (allergies or []) if a.strip()]
    found: set[str] = set()
    for meal in drafts:
        for ing in meal["ingredients"]:
            nl = ing["name"].lower()
            for a in allergs:
                if a in nl:
                    found.add(ing["name"])
    return sorted(found)


async def _price(db, drafts, region, currency) -> Decimal:
    provider = DBPriceProvider(db)
    total = Decimal("0")
    for meal in drafts:
        for ing in meal["ingredients"]:
            cost = await provider.estimate_cost(
                ing["name"], ing["quantity"], ing["unit"], region, currency
            )
            ing["est_cost"] = cost
            total += cost
    return total.quantize(_CENT, rounding=ROUND_HALF_UP)


_MEMBER_TYPE_EN = {
    "adult_m": "adult male", "adult_f": "adult female",
    "teen": "teenager", "child": "child", "toddler": "toddler",
}


async def _household_desc(db: AsyncSession, user_id) -> str:
    """온보딩 구성원(유형·나이)을 LLM 프롬프트용 요약으로 (없으면 빈 문자열)."""
    from app.domains.household.models import HouseholdMember

    rows = (
        await db.execute(
            select(HouseholdMember)
            .where(HouseholdMember.user_id == user_id)
            .order_by(HouseholdMember.position)
        )
    ).scalars().all()
    return ", ".join(f"{_MEMBER_TYPE_EN.get(m.member_type, m.member_type)} (age {m.age})" for m in rows)


async def _generate_within_budget(
    db: AsyncSession, budget: BudgetPlan, region: str,
    days: int, meals_per_day: int, allergies: list[str], preferences: list[str],
    limit_amount: Decimal | None = None,
) -> tuple[list[dict], str, Decimal, list[str]]:
    from app.domains.mealplan.llm import get_llm

    household_desc = await _household_desc(db, budget.user_id)

    currency = budget.currency
    direction = MEAL_DIRECTION_HINT.get(budget.meal_direction, "balanced")
    # 프로레이트 예산이 주어지면 그 한도로 검산(월예산 전액 아님)
    limit = limit_amount if limit_amount is not None else budget.amount
    notes: list[str] = []
    budget_hint = ""
    allergy_hint = ""
    llm_enabled = get_llm().enabled
    best: tuple[list[dict], Decimal] | None = None
    status = "failed"
    started = monotonic()

    def _time_left() -> bool:
        return monotonic() - started < GENERATION_TIME_BUDGET_SECONDS

    for attempt in range(MAX_BUDGET_RETRIES + 1):
        hint = " ".join(x for x in (budget_hint, allergy_hint) if x)
        drafts = await generate_meals(
            region, budget.household_size, direction, days, meals_per_day,
            allergies, preferences, hint, household_desc,
        )
        violations = _check_allergies(drafts, allergies)
        if violations and attempt < MAX_BUDGET_RETRIES and llm_enabled and _time_left():
            allergy_hint = f"NEVER include these allergens: {violations}."
            continue
        if violations:
            notes.append(f"⚠️ 알레르기 재검증 미해결 가능: {violations} — 확인 필요")

        total = await _price(db, drafts, region, currency)
        best = (drafts, total)
        if total <= limit:
            status = "ready"
            break
        status = "over_budget"
        over = total - limit
        budget_hint = (
            f"PREVIOUS PLAN COST {total} {currency}, OVER budget {limit} by {over}. "
            "Make it cheaper."
        )
        if not llm_enabled or not _time_left():
            break

    assert best is not None
    drafts, total = best
    if status == "over_budget":
        notes.append(
            f"⚠️ 예산 초과: {total} {currency} > {limit} {currency} "
            f"({MAX_BUDGET_RETRIES}회 재시도 후, 임의로 자르지 않음)"
        )
    return drafts, status, total, notes


def _apply_drafts(plan: MealPlan, drafts: list[dict], start, days: int, currency: str) -> None:
    for m in drafts:
        day = max(1, min(int(m["day"]), days))
        difficulty = m.get("difficulty")
        if difficulty not in ("easy", "normal", "hard"):
            difficulty = None
        time_minutes = m.get("time_minutes")
        meal = Meal(
            plan_date=start + timedelta(days=day - 1),
            meal_type=m["meal_type"][:16],
            recipe_name=(m["name"] or "meal")[:200],
            recipe_steps=m.get("steps"),
            time_minutes=int(time_minutes) if time_minutes is not None else None,
            difficulty=difficulty,
        )
        for ing in m["ingredients"]:
            meal.ingredients.append(MealIngredient(
                name=ing["name"][:200], quantity=ing["quantity"], unit=ing["unit"][:16],
                est_cost=ing.get("est_cost"), currency=currency,
            ))
        plan.meals.append(meal)


async def _reload(db: AsyncSession, plan_id) -> MealPlan:
    stmt = (
        select(MealPlan).where(MealPlan.id == plan_id)
        .options(selectinload(MealPlan.meals).selectinload(Meal.ingredients))
    )
    return (await db.execute(stmt)).scalar_one()


def _serialize(plan: MealPlan, budget: BudgetPlan | None, notes: list[str]) -> MealPlanResponse:
    # v1.5: processing/failed 는 meals []·budgetSummary null·period null (api-spec §3-2)
    if plan.status in _STUB_STATUSES:
        return MealPlanResponse(
            id=plan.id, status=plan.status, region=plan.region, currency=plan.currency,
            period_start=None, period_end=None, budget_summary=None, meals=[],
            notes=["GENERATION_FAILED"] if plan.status == "failed" else [],
        )
    assert budget is not None
    planned = plan.total_cost
    summary = BudgetSummary(
        budget=MoneyOut(amount=budget.amount, currency=plan.currency),
        planned_cost=MoneyOut(amount=planned, currency=plan.currency),
        remaining=MoneyOut(amount=budget.amount - planned, currency=plan.currency),
        within_budget=plan.status == "ready",
    )
    if plan.status == "over_budget" and not notes:
        # 생성이 202 비동기로 바뀌어 초과 사유는 GET 폴링 응답으로도 노출 (FR-206)
        notes = [
            f"⚠️ 예산 초과: {planned} {plan.currency} > {budget.amount} {plan.currency}"
        ]
    meals = [
        _meal_out(m)
        for m in sorted(plan.meals, key=lambda x: (x.plan_date, str(x.id)))
    ]
    return MealPlanResponse(
        id=plan.id, status=plan.status, region=plan.region, currency=plan.currency,
        period_start=plan.period_start, period_end=plan.period_end,
        budget_summary=summary, meals=meals, notes=notes,
    )


def _is_stale_processing(plan: MealPlan, now=None) -> bool:
    """processing 이 생성 시작(created_at, 재생성 시 갱신) 후 타임아웃을 넘겼는지 (BUG-001).

    서버 재시작 등으로 BackgroundTasks(인프로세스)가 유실되면 processing 이 영구 잔류하므로
    타임아웃 초과 processing 은 failed 로 취급한다 (단일 인스턴스 전제 — 별도 reaper 없음).
    """
    if plan.status != "processing":
        return False
    timeout = timedelta(minutes=get_settings().mealplan_generation_timeout_minutes)
    return (now or utcnow()) - plan.created_at >= timeout


async def _resolve_stale_processing(db: AsyncSession, plan: MealPlan) -> MealPlan:
    """조회 경로 지연 정리 (BUG-001) — stale processing 을 failed 로 마킹 후 반환.

    _mark_generation_failed 가 실패해 processing 이 남아도 이 경로로 결국 failed 로 수렴한다.
    """
    if _is_stale_processing(plan):
        plan.status = "failed"
        plan.total_cost = Decimal("0")
        await db.commit()
    return plan


async def _ensure_not_generating(db: AsyncSession, user_id: uuid.UUID) -> None:
    """이미 processing 플랜이 있으면 409 MEALPLAN_GENERATING (중복 생성 방지).

    단, stale processing(좀비 — BUG-001)은 failed 로 마킹하고 통과시킨다.
    """
    result = await db.execute(
        select(MealPlan).where(MealPlan.user_id == user_id, MealPlan.status == "processing")
    )
    rows = result.scalars().all()
    now = utcnow()
    generating = False
    marked = False
    for plan in rows:
        if _is_stale_processing(plan, now):
            plan.status = "failed"
            plan.total_cost = Decimal("0")
            marked = True
        else:
            generating = True
    if marked:
        await db.commit()
    if generating:
        raise ApiError(409, "MEALPLAN_GENERATING", "meal plan generation already in progress")


async def start_meal_plan_generation(
    db: AsyncSession, user: User, req: MealPlanCreateRequest
) -> uuid.UUID:
    """202 접수 — processing 플랜 행만 생성. 실제 생성은 run_meal_plan_generation(백그라운드)."""
    budget = await _get_budget(db, user)
    await _ensure_not_generating(db, user.id)
    start = utcnow().date()
    plan = MealPlan(
        user_id=user.id, budget_plan_id=budget.id, status="processing",
        total_cost=Decimal("0"), currency=budget.currency, region=user.country,
        period_start=start, period_end=start + timedelta(days=req.days),
    )
    db.add(plan)
    await db.commit()
    return plan.id


async def run_meal_plan_generation(
    plan_id: uuid.UUID,
    days: int,
    meals_per_day: int,
    allergies: list[str],
    preferences: list[str],
) -> None:
    """BackgroundTasks 엔트리 — 자체 세션으로 생성 실행, 완료/실패 시 푸시 발송.

    폴백까지 전부 실패(예외)하면 status=failed (사유는 GET notes 의 GENERATION_FAILED).
    """
    user_id: uuid.UUID | None = None
    succeeded = False
    try:
        async with SessionLocal() as db:
            plan = await _reload_or_none(db, plan_id)
            if plan is None:  # 접수 직후 삭제된 경우 — 조용히 종료
                return
            user_id = plan.user_id
            budget = await db.get(BudgetPlan, plan.budget_plan_id)
            if budget is None:
                raise RuntimeError("budget plan missing for meal plan generation")
            drafts, status, total, _notes = await _generate_within_budget(
                db, budget, plan.region, days, meals_per_day, allergies, preferences
            )
            # 재생성 경로 대비 — 기존 끼니 제거 후 새 결과 반영
            for m in list(plan.meals):
                await db.delete(m)
            await db.flush()
            plan.status = status
            plan.total_cost = total
            _apply_drafts(plan, drafts, plan.period_start, days, budget.currency)
            await db.commit()
            succeeded = True
    except Exception:  # noqa: BLE001 - 백그라운드 실패는 failed 마킹으로 흡수 (5xx 전파 금지)
        logger.exception("식단 생성 백그라운드 작업 실패 plan_id=%s", plan_id)
        failed_user_id = await _mark_generation_failed(plan_id)
        user_id = user_id or failed_user_id
    if user_id is not None:
        # 완료/실패 푸시 — 설정(mealplan_done) enabled 확인은 notification 서비스가 수행
        await notification_service.notify_mealplan_result(user_id, plan_id, succeeded)


async def _mark_generation_failed(plan_id: uuid.UUID) -> uuid.UUID | None:
    """생성 실패 마킹 — 별도 세션 (실패한 세션 상태와 격리)."""
    try:
        async with SessionLocal() as db:
            plan = await db.get(MealPlan, plan_id)
            if plan is None:
                return None
            plan.status = "failed"
            plan.total_cost = Decimal("0")
            await db.commit()
            return plan.user_id
    except Exception:  # noqa: BLE001 - 마킹조차 실패하면 로그만 (폴링이 processing 유지 노출)
        logger.exception("식단 생성 실패 마킹 실패 plan_id=%s", plan_id)
        return None


async def get_latest_meal_plan(db: AsyncSession, user: User) -> MealPlanResponse:
    """인증 유저의 최신 플랜 1건 — status 무관 반환 (v1.5 §3-6, 프론트가 상태 분기)."""
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
    plan = await _resolve_stale_processing(db, plan)  # 좀비 processing → failed (BUG-001)
    if plan.status in _STUB_STATUSES:
        return _serialize(plan, None, [])
    budget = await _get_budget(db, user)
    return _serialize(plan, budget, [])


async def get_meal_plan(db: AsyncSession, user: User, plan_id) -> MealPlanResponse:
    """상세 조회 겸 생성 상태 폴링 (v1.5 §3-3 — rate limit 미적용)."""
    plan = await _reload_or_none(db, plan_id)
    if plan is None:
        raise ApiError(404, "NOT_FOUND", "meal plan not found")
    if plan.user_id != user.id:
        raise ApiError(403, "FORBIDDEN", "not your resource")
    plan = await _resolve_stale_processing(db, plan)  # 좀비 processing → failed (BUG-001)
    if plan.status in _STUB_STATUSES:
        return _serialize(plan, None, [])
    budget = await _get_budget(db, user)
    return _serialize(plan, budget, [])


def _meal_out(m: Meal) -> MealOut:
    return MealOut(
        id=m.id, plan_date=m.plan_date, meal_type=m.meal_type, recipe_name=m.recipe_name,
        steps=parse_steps(m.recipe_steps),
        completed_at=m.completed_at,
        time_minutes=m.time_minutes,
        difficulty=m.difficulty,  # type: ignore[arg-type]
        ingredients=[
            MealIngredientOut(
                id=i.id, name=i.name, quantity=str(i.quantity), unit=i.unit,
                est_cost=(MoneyOut(amount=i.est_cost, currency=i.currency)
                          if i.est_cost is not None and i.currency else None),
            )
            for i in sorted(m.ingredients, key=lambda x: str(x.id))
        ],
    )


async def set_meal_completion(
    db: AsyncSession, user: User, plan_id, meal_id, completed: bool
) -> MealOut:
    """식사 완료 설정/해제 → 갱신된 MealOut. 소유자 스코프 검증(CWE-639).

    plan·meal 존재하지 않으면 404, 타인 소유면 403.
    완료=completed_at=utcnow(), 해제=None.
    """
    plan = await _reload_or_none(db, plan_id)
    if plan is None:
        raise ApiError(404, "NOT_FOUND", "meal plan not found")
    if plan.user_id != user.id:
        raise ApiError(403, "FORBIDDEN", "not your resource")
    meal = next((m for m in plan.meals if m.id == meal_id), None)
    if meal is None:
        raise ApiError(404, "NOT_FOUND", "meal not found")
    meal.completed_at = utcnow() if completed else None
    await db.commit()
    # commit 후 관계 만료 → 이글 로딩으로 재조회(async lazy-load 회피)
    plan = await _reload(db, plan_id)
    meal = next(m for m in plan.meals if m.id == meal_id)
    return _meal_out(meal)


async def _reload_or_none(db: AsyncSession, plan_id) -> MealPlan | None:
    stmt = (
        select(MealPlan).where(MealPlan.id == plan_id)
        .options(selectinload(MealPlan.meals).selectinload(Meal.ingredients))
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def start_meal_plan_regeneration(
    db: AsyncSession, user: User, plan_id, req: RegenerateRequest
) -> tuple[uuid.UUID, int, int]:
    """202 접수 — 플랜을 processing 으로 전환. 실제 재생성은 run_meal_plan_generation.

    반환: (plan_id, days, meals_per_day) — 백그라운드 작업 파라미터.
    끼니가 없는 플랜(생성 실패분)은 409 MEALPLAN_REGENERATE_EMPTY (BUG-002 — 신규 POST 유도).
    """
    plan = await _reload_or_none(db, plan_id)
    if plan is None:
        raise ApiError(404, "NOT_FOUND", "meal plan not found")
    if plan.user_id != user.id:
        raise ApiError(403, "FORBIDDEN", "not your resource")
    await _get_budget(db, user)  # 예산 없으면 409 BUDGET_PLAN_REQUIRED
    await _ensure_not_generating(db, user.id)

    if not plan.meals:
        # BUG-002: 끼니가 없는(생성 실패) 플랜은 원 요청 파라미터(mealsPerDay 등)를
        # 복원할 수 없다 — 하루 1끼로 조용히 붕괴시키는 대신 신규 POST 를 유도한다.
        raise ApiError(
            409,
            "MEALPLAN_REGENERATE_EMPTY",
            "plan has no meals to derive original parameters; create a new plan",
        )
    days = max(1, (plan.period_end - plan.period_start).days)
    # BUG-002: 일자별 최다 끼니 수로 원 요청 mealsPerDay 를 복원
    # (평균 round 방식은 중복 제거 등으로 끼니가 빠졌을 때 아래로 왜곡될 수 있음)
    meals_per_day = max(Counter(m.plan_date for m in plan.meals).values())
    plan.status = "processing"
    plan.created_at = utcnow()  # stale 판정 기준 = 이번 생성 시작 시점 (BUG-001)
    await db.commit()
    return plan.id, days, meals_per_day


async def build_shopping_cart(
    db: AsyncSession, user: User, plan_id, mall: str, max_pages: int
) -> MealPlanCartResponse:
    """원스톱: 식단 재료 집계 → 냉장고 감산(shortfall) → 필요 품목만 마트(컬리) 장바구니.

    냉장고 재고는 차감하지 않음(shortfall = 비파괴 계산). 실제 소진은 식사 완료 deduct.
    """
    plan = await _reload_or_none(db, plan_id)
    if plan is None:
        raise ApiError(404, "NOT_FOUND", "meal plan not found")
    if plan.user_id != user.id:
        raise ApiError(403, "FORBIDDEN", "not your resource")

    # 식단 재료 집계 (name+unit 기준 합산)
    agg: dict[tuple[str, str], list] = {}
    for meal in plan.meals:
        for ing in meal.ingredients:
            key = (ing.name.lower(), ing.unit)
            if key not in agg:
                agg[key] = [ing.name, Decimal("0")]
            agg[key][1] += ing.quantity
    needed = [FridgeNeed(name=name, quantity=qty, unit=unit)
              for (_nl, unit), (name, qty) in agg.items()]

    # 식단 − 냉장고 재고 = 필요 품목 (재고 불변)
    shortfall = await fridge_service.compute_shortfall(db, user.id, needed)
    to_buy = [
        StoreNeed(name=line.name, quantity=Decimal(line.to_buy), unit=line.unit)
        for line in shortfall.items if Decimal(line.to_buy) > 0
    ]

    # 필요 품목만 마트(컬리) 장바구니
    cart = await store_service.build_cart(to_buy, mall, max_pages)
    return MealPlanCartResponse(meal_plan_id=plan.id, needed=shortfall.items, cart=cart)


def _prorate(as_of, monthly: Decimal) -> tuple[int, int, Decimal, str]:
    """월예산을 '오늘 포함 남은 일수' 비율로 안분. (예: 7/10 → 22/31)."""
    dim = calendar.monthrange(as_of.year, as_of.month)[1]
    remaining = dim - as_of.day + 1
    prorated = (monthly * Decimal(remaining) / Decimal(dim)).quantize(_CENT, rounding=ROUND_HALF_UP)
    return remaining, dim, prorated, f"{remaining}/{dim}"


async def build_monthly_plan(
    db: AsyncSession, user: User, req: MonthlyPlanRequest
) -> MonthlyPlanResponse:
    """월 예산 → 그 달(남은 일수) 식단 + 첫 주기 주문(컬리). 예산은 남은 일자 비율만큼."""
    budget = await _get_budget(db, user)
    as_of = req.as_of or utcnow().date()
    remaining, _dim, prorated, ratio = _prorate(as_of, budget.amount)
    region = user.country
    cur = budget.currency

    # 한 달치(남은 일수) 식단 — 프로레이트 예산 기준 검산
    drafts, status, total, _notes = await _generate_within_budget(
        db, budget, region, remaining, req.meals_per_day, [], [], limit_amount=prorated
    )
    plan = MealPlan(
        user_id=user.id, budget_plan_id=budget.id, status=status, total_cost=total,
        currency=cur, region=region,
        period_start=as_of, period_end=as_of + timedelta(days=remaining - 1),
    )
    _apply_drafts(plan, drafts, as_of, remaining, cur)
    db.add(plan)
    await db.commit()
    plan = await _reload(db, plan.id)

    # 첫 주기(주문): weekly=7 / biweekly=14
    cycle_days = 7 if req.cycle == "weekly" else 14
    first_days = min(cycle_days, remaining)
    first_end_excl = as_of + timedelta(days=first_days)
    agg: dict[tuple[str, str], list] = {}
    for meal in plan.meals:
        if meal.plan_date >= first_end_excl:
            continue
        for ing in meal.ingredients:
            key = (ing.name.lower(), ing.unit)
            if key not in agg:
                agg[key] = [ing.name, Decimal("0")]
            agg[key][1] += ing.quantity
    needed = [FridgeNeed(name=n, quantity=q, unit=u) for (_nl, u), (n, q) in agg.items()]
    shortfall = await fridge_service.compute_shortfall(db, user.id, needed)
    to_buy = [
        StoreNeed(name=line.name, quantity=Decimal(line.to_buy), unit=line.unit)
        for line in shortfall.items if Decimal(line.to_buy) > 0
    ]
    cart = await store_service.build_cart(to_buy, req.mall, req.max_pages)

    first_order = FirstCycleOrder(
        period_start=as_of, period_end=as_of + timedelta(days=first_days - 1),
        days=first_days, needed=shortfall.items, cart=cart,
    )
    return MonthlyPlanResponse(
        meal_plan_id=plan.id, status=status,
        period_start=as_of, period_end=as_of + timedelta(days=remaining - 1), days=remaining,
        monthly_budget=MoneyOut(amount=budget.amount, currency=cur),
        prorated_budget=MoneyOut(amount=prorated, currency=cur),
        prorate_ratio=ratio,
        planned_cost=MoneyOut(amount=total, currency=cur),
        within_budget=(status == "ready"),
        first_order=first_order,
    )
