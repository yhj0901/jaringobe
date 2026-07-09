from sqlalchemy.ext.asyncio import AsyncSession

from app.models.household import Household
from app.schemas.household import HouseholdCreate


async def create_household(db: AsyncSession, data: HouseholdCreate) -> Household:
    household = Household(
        region=data.region,
        members=[m.model_dump() for m in data.members],
        allergies=data.allergies,
        preferences=data.preferences,
    )
    db.add(household)
    await db.commit()
    await db.refresh(household)
    return household
