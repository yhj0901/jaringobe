"""mealplan 오케스트레이션 — 생성(LLM)→알레르기 재검증→기준가 비용→예산 검산·재시도→저장.

예산 기준: 유저의 budget_plans.amount (유저당 1개). 초과 시 status=over_budget 투명 노출.
"""

from __future__ import annotations

import calendar
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    MealPlanCartResponse,
    MealPlanCreateRequest,
    MealPlanResponse,
    MonthlyPlanRequest,
    MonthlyPlanResponse,
    RegenerateRequest,
)
from app.domains.store import service as store_service
from app.domains.store.schemas import NeededItem as StoreNeed

_CENT = Decimal("0.01")
MAX_BUDGET_RETRIES = 3
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


async def _generate_within_budget(
    db: AsyncSession, budget: BudgetPlan, region: str,
    days: int, meals_per_day: int, allergies: list[str], preferences: list[str],
    limit_amount: Decimal | None = None,
) -> tuple[list[dict], str, Decimal, list[str]]:
    from app.domains.mealplan.llm import get_llm

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

    for attempt in range(MAX_BUDGET_RETRIES + 1):
        hint = " ".join(x for x in (budget_hint, allergy_hint) if x)
        drafts = await generate_meals(
            region, budget.household_size, direction, days, meals_per_day,
            allergies, preferences, hint,
        )
        violations = _check_allergies(drafts, allergies)
        if violations and attempt < MAX_BUDGET_RETRIES and llm_enabled:
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
        if not llm_enabled:
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
        meal = Meal(
            plan_date=start + timedelta(days=day - 1),
            meal_type=m["meal_type"][:16],
            recipe_name=(m["name"] or "meal")[:200],
            recipe_steps=m.get("steps"),
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


def _serialize(plan: MealPlan, budget: BudgetPlan, notes: list[str]) -> MealPlanResponse:
    planned = plan.total_cost
    summary = BudgetSummary(
        budget=MoneyOut(amount=budget.amount, currency=plan.currency),
        planned_cost=MoneyOut(amount=planned, currency=plan.currency),
        remaining=MoneyOut(amount=budget.amount - planned, currency=plan.currency),
        within_budget=plan.status == "ready",
    )
    meals = [
        MealOut(
            id=m.id, plan_date=m.plan_date, meal_type=m.meal_type, recipe_name=m.recipe_name,
            ingredients=[
                MealIngredientOut(
                    id=i.id, name=i.name, quantity=str(i.quantity), unit=i.unit,
                    est_cost=(MoneyOut(amount=i.est_cost, currency=i.currency)
                              if i.est_cost is not None and i.currency else None),
                )
                for i in sorted(m.ingredients, key=lambda x: str(x.id))
            ],
        )
        for m in sorted(plan.meals, key=lambda x: (x.plan_date, str(x.id)))
    ]
    return MealPlanResponse(
        id=plan.id, status=plan.status, region=plan.region, currency=plan.currency,
        period_start=plan.period_start, period_end=plan.period_end,
        budget_summary=summary, meals=meals, notes=notes,
    )


async def create_meal_plan(
    db: AsyncSession, user: User, req: MealPlanCreateRequest
) -> MealPlanResponse:
    budget = await _get_budget(db, user)
    region = user.country
    drafts, status, total, notes = await _generate_within_budget(
        db, budget, region, req.days, req.meals_per_day, req.allergies, req.preferences
    )
    start = utcnow().date()
    plan = MealPlan(
        user_id=user.id, budget_plan_id=budget.id, status=status,
        total_cost=total, currency=budget.currency, region=region,
        period_start=start, period_end=start + timedelta(days=req.days),
    )
    _apply_drafts(plan, drafts, start, req.days, budget.currency)
    db.add(plan)
    await db.commit()
    return _serialize(await _reload(db, plan.id), budget, notes)


async def get_meal_plan(db: AsyncSession, user: User, plan_id) -> MealPlanResponse:
    plan = await _reload_or_none(db, plan_id)
    if plan is None:
        raise ApiError(404, "NOT_FOUND", "meal plan not found")
    if plan.user_id != user.id:
        raise ApiError(403, "FORBIDDEN", "not your resource")
    budget = await _get_budget(db, user)
    return _serialize(plan, budget, [])


async def _reload_or_none(db: AsyncSession, plan_id) -> MealPlan | None:
    stmt = (
        select(MealPlan).where(MealPlan.id == plan_id)
        .options(selectinload(MealPlan.meals).selectinload(Meal.ingredients))
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def regenerate_meal_plan(
    db: AsyncSession, user: User, plan_id, req: RegenerateRequest
) -> MealPlanResponse:
    plan = await _reload_or_none(db, plan_id)
    if plan is None:
        raise ApiError(404, "NOT_FOUND", "meal plan not found")
    if plan.user_id != user.id:
        raise ApiError(403, "FORBIDDEN", "not your resource")
    budget = await _get_budget(db, user)
    region = user.country
    days = max(1, (plan.period_end - plan.period_start).days)
    meals_per_day = max(1, round(len(plan.meals) / days))

    for m in list(plan.meals):
        await db.delete(m)
    await db.flush()

    drafts, status, total, notes = await _generate_within_budget(
        db, budget, region, days, meals_per_day, req.allergies, req.preferences
    )
    plan.status = status
    plan.total_cost = total
    _apply_drafts(plan, drafts, plan.period_start, days, budget.currency)
    await db.commit()
    return _serialize(await _reload(db, plan.id), budget, notes)


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
