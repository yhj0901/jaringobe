"""식사 리마인더 스케줄러 — FastAPI lifespan asyncio 태스크 (architecture.md 3-7).

30초 주기로 notification_settings 의 due 행(enabled AND next_send_at <= now)을
partial index(ix_notification_settings_due) 스캔으로 조회하고,
발송 직전 3중 재확인(최신 활성 플랜에 당일 로컬 날짜 해당 끼니 존재 / 미완료 / enabled)
후 발송한다 (판정은 최신 플랜 1개 안에서만 — 구플랜 폴백 금지, BUG-005).
발송 여부와 무관하게 next_send_at 은 익일 동일 로컬시각(UTC 환산)으로 재계산한다.

테스트 용이성을 위해 주기 루프(run_scheduler_loop)와 판정/처리(process_due_reminders,
resolve_reminder_meal)를 분리한다. 단일 인스턴스 전제 (멀티 인스턴스 시 락/분리 — 후속 확장점).
"""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.security import utcnow
from app.domains.mealplan.models import Meal, MealPlan
from app.domains.notification import sender
from app.domains.notification.models import NotificationSetting
from app.domains.notification.service import DEFAULT_TIMEZONE, compute_next_send_at

logger = logging.getLogger(__name__)

# 리마인더 type → meal_type 매핑
REMINDER_MEAL_TYPE = {
    "meal_reminder_breakfast": "breakfast",
    "meal_reminder_lunch": "lunch",
    "meal_reminder_dinner": "dinner",
}

# 리마인더 대상 플랜 status — 생성 중/실패 플랜은 발송 대상 아님
_ACTIVE_PLAN_STATUSES = ("ready", "over_budget")


async def find_due_settings(db: AsyncSession, now: datetime) -> list[NotificationSetting]:
    """due 행 스캔 — partial index(enabled AND next_send_at IS NOT NULL) 커버."""
    stmt = select(NotificationSetting).where(
        NotificationSetting.enabled.is_(True),
        NotificationSetting.next_send_at.is_not(None),
        NotificationSetting.next_send_at <= now,
    )
    return list((await db.execute(stmt)).scalars().all())


async def resolve_reminder_meal(
    db: AsyncSession, setting: NotificationSetting, now: datetime
) -> Meal | None:
    """발송 직전 재확인 ①②: 당일(설정 타임존 로컬 날짜) 해당 끼니 meal 존재 + 미완료.

    최신 활성(ready/over_budget) 플랜 1개를 먼저 선택하고, 그 플랜 안에서만 판정한다
    (BUG-005 — 최신 플랜에 해당 끼니가 없거나 완료됐으면 구플랜 폴백 없이 발송 스킵).
    조건 미충족 시 None (발송 스킵 — 로그 없음).
    """
    meal_type = REMINDER_MEAL_TYPE.get(setting.type)
    if meal_type is None or setting.local_time is None:
        return None
    tz = ZoneInfo(setting.timezone or DEFAULT_TIMEZONE)
    local_date = now.astimezone(tz).date()
    latest_plan_id = await db.scalar(
        select(MealPlan.id)
        .where(
            MealPlan.user_id == setting.user_id,
            MealPlan.status.in_(_ACTIVE_PLAN_STATUSES),
        )
        .order_by(MealPlan.created_at.desc())
        .limit(1)
    )
    if latest_plan_id is None:
        return None
    stmt = (
        select(Meal)
        .where(
            Meal.meal_plan_id == latest_plan_id,
            Meal.plan_date == local_date,
            Meal.meal_type == meal_type,
            Meal.completed_at.is_(None),
        )
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def process_due_reminders(now: datetime | None = None) -> int:
    """due 리마인더 1회 처리. 반환: 발송 성공 건수. (주기 루프와 분리 — 테스트 진입점)"""
    now = now or utcnow()
    sent_total = 0
    async with SessionLocal() as db:
        for setting in await find_due_settings(db, now):
            # 재확인 ③(enabled) 은 find_due_settings 조회 시점에 함께 보장된다
            meal = await resolve_reminder_meal(db, setting, now)
            if meal is not None:
                sent_total += await sender.send_to_user(
                    db,
                    setting.user_id,
                    type_=setting.type,
                    template_key="push.mealReminder",
                    path=f"/mealplan/{meal.meal_plan_id}",
                    variables={"meal_type": meal.meal_type, "recipe_name": meal.recipe_name},
                )
            # 공통: 발송/스킵 무관 next_send_at = 익일 동일 로컬시각 (UTC 환산)
            if setting.local_time is not None:
                setting.next_send_at = compute_next_send_at(
                    setting.local_time, setting.timezone or DEFAULT_TIMEZONE, now
                )
            else:
                setting.next_send_at = None
        await db.commit()
    return sent_total


async def run_scheduler_loop(interval_seconds: float = 30.0) -> None:
    """주기 루프 — 예외를 삼키고 계속 돈다 (스케줄러 정지 방지). lifespan 에서 기동."""
    logger.info("식사 리마인더 스케줄러 시작 (주기 %.0f초)", interval_seconds)
    while True:
        try:
            await process_due_reminders()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - 개별 사이클 실패가 루프를 멈추면 안 됨
            logger.exception("리마인더 사이클 처리 실패")
        await asyncio.sleep(interval_seconds)
