"""공용 의존성.

⚠️ 인증은 현재 **개발용 스텁**: `X-Household-Id` 헤더로 현재 가구를 식별한다.
정식 소셜 로그인 + JWT 는 auth 도메인 구현 시 이 의존성을 대체한다.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.household import Household


async def get_current_household(
    x_household_id: Annotated[int | None, Header(alias="X-Household-Id")] = None,
    db: AsyncSession = Depends(get_db),
) -> Household:
    if x_household_id is None:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "UNAUTHORIZED",
                "message": "X-Household-Id header required (dev auth stub)",
            },
        )
    household = await db.get(Household, x_household_id)
    if household is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "HOUSEHOLD_REQUIRED", "message": "household not found"},
        )
    return household


CurrentHousehold = Annotated[Household, Depends(get_current_household)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
