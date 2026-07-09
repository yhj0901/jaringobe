from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentHousehold, DbSession
from app.schemas.budget import BudgetCreate, BudgetRead
from app.services.budget import create_budget, get_current_budget

router = APIRouter(prefix="/api/v1/budgets", tags=["budget"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BudgetRead)
async def create(
    data: BudgetCreate, household: CurrentHousehold, db: DbSession
) -> BudgetRead:
    budget = await create_budget(db, household.id, data)
    return BudgetRead.model_validate(budget)


@router.get("/current", response_model=BudgetRead)
async def current(household: CurrentHousehold, db: DbSession) -> BudgetRead:
    budget = await get_current_budget(db, household.id)
    if budget is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "BUDGET_NOT_SET", "message": "no budget set for household"},
        )
    return BudgetRead.model_validate(budget)
