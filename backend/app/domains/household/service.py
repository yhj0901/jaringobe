"""household 도메인 비즈니스 로직 — 가구 구성 replace-all 저장/조회 (api-spec.md §4)."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.security import utcnow
from app.domains.auth.models import User
from app.domains.budget.models import BudgetPlan
from app.domains.household.models import HouseholdMember
from app.domains.household.schemas import (
    HouseholdMemberOut,
    HouseholdResponse,
    HouseholdUpdateRequest,
)


async def replace_household(
    db: AsyncSession, user: User, payload: HouseholdUpdateRequest
) -> HouseholdResponse:
    """구성원 전체 교체(replace-all) — 트랜잭션 내 삭제 후 삽입.

    저장 성공 시 유저에게 budget_plan 이 존재하면 온보딩 완료로 파생
    (users.onboarding_completed_at 세팅, 이미 세팅돼 있으면 유지).
    """
    await db.execute(delete(HouseholdMember).where(HouseholdMember.user_id == user.id))
    members = [
        HouseholdMember(user_id=user.id, member_type=m.member_type, age=m.age, position=i)
        for i, m in enumerate(payload.members)
    ]
    db.add_all(members)

    if user.onboarding_completed_at is None:
        has_plan = await db.scalar(select(BudgetPlan.id).where(BudgetPlan.user_id == user.id))
        if has_plan is not None:
            user.onboarding_completed_at = utcnow()

    await db.commit()

    return HouseholdResponse(
        members=[HouseholdMemberOut(member_type=m.member_type, age=m.age) for m in members],
        size=len(members),
    )


async def get_household(db: AsyncSession, user: User) -> HouseholdResponse:
    """가구 구성 조회 — 미설정 시 404 HOUSEHOLD_NOT_FOUND."""
    rows = (
        await db.scalars(
            select(HouseholdMember)
            .where(HouseholdMember.user_id == user.id)
            .order_by(HouseholdMember.position)
        )
    ).all()
    if not rows:
        raise ApiError(404, "HOUSEHOLD_NOT_FOUND", "Household is not configured")

    return HouseholdResponse(
        members=[HouseholdMemberOut(member_type=m.member_type, age=m.age) for m in rows],
        size=len(rows),
    )
