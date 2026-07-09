from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import Budget
from app.schemas.budget import BudgetCreate


async def create_budget(
    db: AsyncSession, household_id: int, data: BudgetCreate
) -> Budget:
    budget = Budget(
        household_id=household_id,
        amount=data.amount,
        currency=data.currency,
        period_start=data.period_start,
        period_end=data.period_end,
        locked=data.locked,
    )
    db.add(budget)
    await db.commit()
    await db.refresh(budget)
    return budget


async def get_current_budget(db: AsyncSession, household_id: int) -> Budget | None:
    """현재(가장 최근 기간) 예산. period_start 내림차순 최신 1건."""
    stmt = (
        select(Budget)
        .where(Budget.household_id == household_id)
        .order_by(Budget.period_start.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
