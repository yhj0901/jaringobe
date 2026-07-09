"""가구 라우터 — ⚠️ 개발용 스텁 (auth/household 도메인 정식 구현 시 대체)."""

from fastapi import APIRouter, status

from app.core.deps import CurrentHousehold, DbSession
from app.schemas.household import HouseholdCreate, HouseholdRead
from app.services.household import create_household

router = APIRouter(prefix="/api/v1/households", tags=["household(stub)"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=HouseholdRead)
async def create(data: HouseholdCreate, db: DbSession) -> HouseholdRead:
    household = await create_household(db, data)
    return HouseholdRead.model_validate(household)


@router.get("/me", response_model=HouseholdRead)
async def me(household: CurrentHousehold) -> HouseholdRead:
    return HouseholdRead.model_validate(household)
