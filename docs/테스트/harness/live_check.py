"""실제 lifespan 스케줄러 루프(uvicorn :8012, 5초 주기)가 due 사용자를 실시간으로 처리하는지 확인."""
import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://jaringobe:jaringobe@localhost:5433/jaringobe_qa")
os.environ["JWT_SECRET"] = "qa-secret"
os.environ["CYCLE_SCHEDULER_ENABLED"] = "false"
os.environ["REMINDER_SCHEDULER_ENABLED"] = "false"

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.domains.auth.models import User  # noqa: E402
from app.domains.budget.models import BudgetPlan  # noqa: E402
from app.domains.cycle import service as cycle_service  # noqa: E402
from app.domains.cycle.models import UserCycleSettings  # noqa: E402
from app.domains.household.models import HouseholdMember  # noqa: E402
from app.domains.mealplan.models import Meal, MealPlan  # noqa: E402
from app.domains.order.models import Order  # noqa: E402
from app.domains.store.connection_models import StoreConnection  # noqa: E402


async def main():
    now = datetime.now(UTC)
    window = cycle_service.cycle_window("weekly", 0, "Asia/Seoul", now)
    prev = cycle_service.previous_cycle_start(window.cycle_start, "weekly", 0)
    async with SessionLocal() as db:
        user = User(nickname="LIVE-sched", country="KR", currency="KRW", last_seen_at=now, onboarding_completed_at=now)
        db.add(user)
        await db.flush()
        budget = BudgetPlan(user_id=user.id, household_size=2, amount=Decimal("400000"), currency="KRW",
                            meal_direction="health", source="onboarding", locked=True, cuisines=[])
        db.add(budget)
        db.add(HouseholdMember(user_id=user.id, member_type="adult_m", age=30, position=0))
        db.add(StoreConnection(user_id=user.id, store="kurly", status="connected", connected_at=now))
        await db.flush()
        prior = MealPlan(user_id=user.id, budget_plan_id=budget.id, status="ready", total_cost=Decimal("0"),
                         currency="KRW", region="KR", period_start=prev, period_end=window.cycle_start)
        db.add(prior)
        await db.flush()
        db.add(Meal(meal_plan_id=prior.id, plan_date=prev + timedelta(days=1), meal_type="dinner", recipe_name="완료",
                    completed_at=datetime.combine(prev + timedelta(days=1), datetime.min.time(), tzinfo=UTC) + timedelta(hours=12)))
        settings = UserCycleSettings(user_id=user.id, enabled=True, frequency="weekly", anchor_weekday=0,
                                     timezone="Asia/Seoul", auto_confirm=True, next_run_at=now - timedelta(seconds=1))
        db.add(settings)
        await db.commit()
        uid = user.id
    print(f"seeded user={uid} cycle_start={window.cycle_start} prev={prev} next_run_at=now-1s; waiting for live scheduler...")
    for i in range(12):
        await asyncio.sleep(5)
        async with SessionLocal() as db:
            s = (await db.execute(select(UserCycleSettings).where(UserCycleSettings.user_id == uid))).scalar_one()
            plans = (await db.execute(select(MealPlan).where(MealPlan.user_id == uid, MealPlan.period_start == window.cycle_start))).scalars().all()
            orders = (await db.execute(select(Order).where(Order.user_id == uid))).scalars().all()
            print(f"t+{(i+1)*5}s stage={s.last_stage} attempts={s.stage_attempts} next_run_at={s.next_run_at} plans={[p.status for p in plans]} orders={[(o.status, o.auto_confirm_at is not None) for o in orders]}")
            if orders and s.last_stage == "drafted":
                break
    ok = bool(orders) and orders[0].status == "draft" and plans and plans[0].status == "ready" and s.last_stage == "drafted"
    print("LIVE_RESULT", "PASS" if ok else "FAIL")


asyncio.run(main())
