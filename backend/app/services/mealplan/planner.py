"""⑤ 식단 오케스트레이션.

생성(LLM) → 알레르기 코드 재검증 → 기준가 비용 산출 → 예산 검산·재시도
→ 초과 시 status=over_budget(투명 노출) → 저장. 재생성/직렬화 포함.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.budget import Budget
from app.models.household import Household
from app.models.mealplan import Meal, MealIngredient, MealPlan
from app.schemas.common import Money
from app.schemas.mealplan import (
    BudgetSummary,
    MealIngredientRead,
    MealPlanCreate,
    MealPlanRead,
    MealRead,
    RegenerateRequest,
)
from app.services.llm import get_llm
from app.services.mealplan.generator import generate_meals
from app.services.mealplan.pricing import DBPriceProvider

_CENT = Decimal("0.01")
MAX_BUDGET_RETRIES = 3


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


async def _price_drafts(
    price: DBPriceProvider, drafts: list[dict], region: str, currency: str
) -> Decimal:
    total = Decimal("0")
    for meal in drafts:
        for ing in meal["ingredients"]:
            cost = await price.estimate_cost(
                ing["name"], ing["quantity"], ing["unit"], region, currency
            )
            ing["est_cost"] = cost
            total += cost
    return total.quantize(_CENT, rounding=ROUND_HALF_UP)


async def _generate_within_budget(
    db: AsyncSession, household: Household, budget: Budget, req: MealPlanCreate
) -> tuple[list[dict], str, Decimal, list[str]]:
    region = household.region
    currency = budget.currency
    price = DBPriceProvider(db)
    notes: list[str] = []
    budget_hint = ""
    allergy_hint = ""
    llm_enabled = get_llm().enabled

    best: tuple[list[dict], Decimal] | None = None
    status = "failed"

    for attempt in range(MAX_BUDGET_RETRIES + 1):
        hint = " ".join(x for x in (budget_hint, allergy_hint) if x)
        drafts = await generate_meals(
            household, req.days, req.meals_per_day, req.diet_direction, region, hint
        )

        violations = _check_allergies(drafts, household.allergies)
        if violations and attempt < MAX_BUDGET_RETRIES and llm_enabled:
            allergy_hint = f"NEVER include these allergens: {violations}."
            continue
        if violations:
            notes.append(f"⚠️ 알레르기 재검증 미해결 가능: {violations} — 확인 필요")

        total = await _price_drafts(price, drafts, region, currency)
        best = (drafts, total)
        if total <= budget.amount:
            status = "ready"
            break
        status = "over_budget"
        over = total - budget.amount
        budget_hint = (
            f"PREVIOUS PLAN COST {total} {currency}, OVER budget {budget.amount} "
            f"by {over}. Make it cheaper (smaller quantities / cheaper ingredients)."
        )
        if not llm_enabled:
            break  # mock은 재생성해도 동일 → 재시도 무의미

    assert best is not None
    drafts, total = best
    if status == "over_budget":
        notes.append(
            f"⚠️ 예산 초과: {total} {currency} > {budget.amount} {currency} "
            f"({MAX_BUDGET_RETRIES}회 재시도 후, 임의로 자르지 않음)"
        )
    return drafts, status, total, notes


def _apply_drafts(
    plan: MealPlan, drafts: list[dict], budget: Budget, days: int, currency: str
) -> None:
    for m in drafts:
        day = max(1, min(int(m["day"]), days))
        plan_date = (budget.period_start + timedelta(days=day - 1)).date()
        meal = Meal(
            plan_date=plan_date,
            meal_type=m["meal_type"][:16],
            recipe_name=m["name"][:200] or "meal",
            recipe_steps=m.get("steps"),
        )
        for ing in m["ingredients"]:
            meal.ingredients.append(MealIngredient(
                name=ing["name"][:200],
                quantity=ing["quantity"],
                unit=ing["unit"][:16],
                est_cost=ing.get("est_cost"),
                currency=currency,
            ))
        plan.meals.append(meal)


async def _reload(db: AsyncSession, plan_id: int) -> MealPlan:
    stmt = (
        select(MealPlan)
        .where(MealPlan.id == plan_id)
        .options(selectinload(MealPlan.meals).selectinload(Meal.ingredients))
    )
    return (await db.execute(stmt)).scalar_one()


async def generate_meal_plan(
    db: AsyncSession, household: Household, budget: Budget, req: MealPlanCreate
) -> tuple[MealPlan, list[str]]:
    drafts, status, total, notes = await _generate_within_budget(db, household, budget, req)

    plan = MealPlan(
        household_id=household.id,
        budget_id=budget.id,
        period_start=budget.period_start,
        period_end=budget.period_start + timedelta(days=req.days),
        status=status,
        total_cost=total,
        currency=budget.currency,
        region=household.region,
    )
    _apply_drafts(plan, drafts, budget, req.days, budget.currency)
    db.add(plan)
    await db.commit()
    return await _reload(db, plan.id), notes


async def regenerate_meal_plan(
    db: AsyncSession, household: Household, plan: MealPlan,
    budget: Budget, req: RegenerateRequest,
) -> tuple[MealPlan, list[str]]:
    days = max(1, (plan.period_end.date() - plan.period_start.date()).days)

    if req.scope == "meal":
        # 단일 끼니 재생성
        target = next((m for m in plan.meals if m.id == req.meal_id), None)
        if target is None:
            raise ValueError("meal_not_found")
        one = MealPlanCreate(days=1, meals_per_day=1, diet_direction="balanced")
        drafts = await generate_meals(
            household, 1, 1, "balanced", household.region
        )
        price = DBPriceProvider(db)
        await _price_drafts(price, drafts[:1], household.region, budget.currency)
        d = drafts[0]
        target.recipe_name = d["name"][:200] or "meal"
        target.recipe_steps = d.get("steps")
        # 재료 교체
        for old in list(target.ingredients):
            await db.delete(old)
        target.ingredients = [
            MealIngredient(name=i["name"][:200], quantity=i["quantity"],
                           unit=i["unit"][:16], est_cost=i.get("est_cost"),
                           currency=budget.currency)
            for i in d["ingredients"]
        ]
        await db.flush()
        # 총비용 재계산
        refreshed = await _reload(db, plan.id)
        total = sum((i.est_cost or Decimal("0"))
                    for m in refreshed.meals for i in m.ingredients).quantize(_CENT)
        refreshed.status = "ready" if total <= budget.amount else "over_budget"
        refreshed.total_cost = total
        await db.commit()
        _ = one  # (days/meals 재사용 여지)
        return await _reload(db, plan.id), []

    # scope == "all": 전체 재생성
    req_all = MealPlanCreate(
        days=days, meals_per_day=max(1, round(len(plan.meals) / days)),
        diet_direction="balanced",
    )
    for m in list(plan.meals):
        await db.delete(m)
    await db.flush()
    drafts, status, total, notes = await _generate_within_budget(
        db, household, budget, req_all
    )
    plan.status = status
    plan.total_cost = total
    _apply_drafts(plan, drafts, budget, days, budget.currency)
    await db.commit()
    return await _reload(db, plan.id), notes


def to_mealplan_read(
    plan: MealPlan, budget: Budget, notes: list[str] | None = None
) -> MealPlanRead:
    cur = plan.currency
    planned = plan.total_cost
    remaining = (budget.amount - planned)
    summary = BudgetSummary(
        budget=Money(amount=budget.amount, currency=cur),
        planned_cost=Money(amount=planned, currency=cur),
        remaining=Money(amount=remaining, currency=cur),
        within_budget=plan.status == "ready",
    )
    meals = []
    for m in sorted(plan.meals, key=lambda x: (x.plan_date, x.id)):
        ings = [
            MealIngredientRead(
                id=i.id, name=i.name, quantity=str(i.quantity), unit=i.unit,
                est_cost=(Money(amount=i.est_cost, currency=i.currency)
                          if i.est_cost is not None and i.currency else None),
            )
            for i in sorted(m.ingredients, key=lambda x: x.id)
        ]
        meals.append(MealRead(
            id=m.id, plan_date=m.plan_date, meal_type=m.meal_type,
            recipe_name=m.recipe_name, ingredients=ings,
        ))
    return MealPlanRead(
        id=plan.id, status=plan.status, region=plan.region, currency=cur,
        period_start=plan.period_start, period_end=plan.period_end,
        budget_summary=summary, meals=meals, notes=notes or [],
    )
