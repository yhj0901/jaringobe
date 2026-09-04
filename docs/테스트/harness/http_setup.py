"""HTTP 시나리오용 픽스처: 사용자 A(초안 보유)·B(타인)·C(초안 없음) 생성 후 액세스 토큰 출력."""
import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://jaringobe:jaringobe@localhost:5433/jaringobe_qa")
os.environ["JWT_SECRET"] = "qa-secret"
os.environ["CYCLE_SCHEDULER_ENABLED"] = "false"
os.environ["REMINDER_SCHEDULER_ENABLED"] = "false"
os.environ["NAVER_CLIENT_ID"] = ""
os.environ["NAVER_CLIENT_SECRET"] = ""

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.domains.auth.models import User  # noqa: E402
from app.domains.budget.models import BudgetPlan  # noqa: E402
from app.domains.cycle import service as cycle_service  # noqa: E402
from app.domains.cycle.models import UserCycleSettings  # noqa: E402
from app.domains.household.models import HouseholdMember  # noqa: E402
from app.domains.mealplan.models import Meal, MealIngredient, MealPlan  # noqa: E402
from app.domains.order import service as order_service  # noqa: E402
from app.domains.store.connection_models import StoreConnection  # noqa: E402


async def mk(db, nick, *, with_plan=True, with_draft=False):
    now = datetime.now(UTC)
    user = User(nickname=nick, country="KR", currency="KRW", last_seen_at=now, onboarding_completed_at=now)
    db.add(user)
    await db.flush()
    budget = BudgetPlan(user_id=user.id, household_size=2, amount=Decimal("400000"), currency="KRW",
                        meal_direction="health", source="onboarding", locked=True, cuisines=[])
    db.add(budget)
    db.add(HouseholdMember(user_id=user.id, member_type="adult_m", age=30, position=0))
    db.add(StoreConnection(user_id=user.id, store="kurly", status="connected", connected_at=now))
    settings = UserCycleSettings(user_id=user.id, enabled=True, frequency="weekly", anchor_weekday=0,
                                 timezone="Asia/Seoul", auto_confirm=True, next_run_at=None)
    db.add(settings)
    await db.flush()
    window = cycle_service.cycle_window("weekly", 0, "Asia/Seoul", now)
    if with_plan:
        plan = MealPlan(user_id=user.id, budget_plan_id=budget.id, status="ready", total_cost=Decimal("0"),
                        currency="KRW", region="KR", period_start=window.cycle_start,
                        period_end=window.cycle_start + timedelta(days=7))
        db.add(plan)
        await db.flush()
        for i, (name, qty, unit) in enumerate([("계란", "10", "ea"), ("두부", "2", "ea"), ("쌀", "800", "g")]):
            meal = Meal(meal_plan_id=plan.id, plan_date=window.cycle_start + timedelta(days=i), meal_type="dinner",
                        recipe_name=f"요리{i}")
            db.add(meal)
            await db.flush()
            db.add(MealIngredient(meal_id=meal.id, name=name, quantity=Decimal(qty), unit=unit))
    await db.commit()
    draft_id = None
    if with_draft:
        order = await order_service.create_draft(db, user, cycle_start=window.cycle_start, frequency="weekly",
                                                 auto_confirm=True, grace_hours=24)
        await db.commit()
        draft_id = str(order.id)
    return {"id": str(user.id), "token": create_access_token(user.id), "draft_id": draft_id,
            "cycle_start": window.cycle_start.isoformat()}


async def main():
    async with SessionLocal() as db:
        out = {
            "A": await mk(db, "HTTP-A", with_plan=True, with_draft=True),
            "B": await mk(db, "HTTP-B", with_plan=True, with_draft=False),
            "C": await mk(db, "HTTP-C", with_plan=True, with_draft=False),
            "D": await mk(db, "HTTP-D", with_plan=False, with_draft=False),
            "E": await mk(db, "HTTP-E", with_plan=True, with_draft=True),
        }
    print(json.dumps(out))


asyncio.run(main())
