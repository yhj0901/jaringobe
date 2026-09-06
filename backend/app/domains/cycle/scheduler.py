"""주간 사이클 스케줄러 — lifespan asyncio + partial-index due 스캔."""

import asyncio
import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.db import SessionLocal
from app.core.security import utcnow
from app.domains.auth.models import User
from app.domains.cycle import service
from app.domains.cycle.models import UserCycleSettings
from app.domains.cycle.policy import CyclePolicy, load_policy
from app.domains.mealplan import service as mealplan_service
from app.domains.order import service as order_service
from app.domains.order.models import Order
from app.domains.notification import service as notification_service

logger = logging.getLogger(__name__)
_generation_tasks: set[asyncio.Task[None]] = set()


async def _due_setting_ids(now: datetime) -> list[uuid.UUID]:
    async with SessionLocal() as db:
        rows = await db.scalars(
            select(UserCycleSettings.id)
            .where(
                UserCycleSettings.enabled.is_(True),
                UserCycleSettings.next_run_at.is_not(None),
                UserCycleSettings.next_run_at <= now,
            )
            .order_by(UserCycleSettings.next_run_at.asc())
        )
        return list(rows.all())


async def _due_order_ids(now: datetime, *, inbound: bool) -> list[uuid.UUID]:
    async with SessionLocal() as db:
        stmt = select(Order.id)
        if inbound:
            stmt = stmt.where(
                Order.status == "confirmed",
                Order.inbound_at.is_(None),
                Order.delivery_state != "unknown",
                Order.delivery_eta.is_not(None),
                Order.delivery_eta <= now,
            ).order_by(Order.delivery_eta.asc())
        else:
            stmt = stmt.where(
                Order.status == "draft",
                Order.auto_confirm_at.is_not(None),
                Order.auto_confirm_at <= now,
            ).order_by(Order.auto_confirm_at.asc())
        return list((await db.scalars(stmt)).all())


async def _run_generation_job(job: service.GenerationJob) -> None:
    try:
        await mealplan_service.run_meal_plan_generation(
            job.plan_id,
            job.days,
            job.meals_per_day,
            job.allergies,
            job.preferences,
        )
        await service.finish_generation_job(job)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - 백그라운드 예외 미회수 방지
        logger.exception(
            "사이클 식단 생성 결과 수렴 실패 setting_id=%s plan_id=%s",
            job.setting_id,
            job.plan_id,
        )


async def process_due_settings(
    now: datetime,
    policy: CyclePolicy,
) -> tuple[int, int]:
    """사용자 단계 스캔. 반환 (처리 수, 새 자동 생성 접수 수)."""
    async with SessionLocal() as db:
        generated_today = await service.count_generated_today(db, now)
    processed = 0
    generated = 0
    for setting_id in await _due_setting_ids(now):
        async with SessionLocal() as db:
            try:
                setting = (
                    await db.execute(
                        select(UserCycleSettings)
                        .where(
                            UserCycleSettings.id == setting_id,
                            UserCycleSettings.enabled.is_(True),
                            UserCycleSettings.next_run_at.is_not(None),
                            UserCycleSettings.next_run_at <= now,
                        )
                        .with_for_update(skip_locked=True)
                    )
                ).scalar_one_or_none()
                if setting is None:
                    continue
                user = await db.scalar(
                    select(User).where(User.id == setting.user_id)
                )
                if user is None:
                    continue
                job = await service.process_due_setting(
                    db,
                    user,
                    setting,
                    policy=policy,
                    now=now,
                    generation_allowed=(
                        generated_today + generated < policy.daily_generation_limit
                    ),
                )
                processed += 1
                if job is not None:
                    generated += 1
                    task = asyncio.create_task(_run_generation_job(job))
                    _generation_tasks.add(task)
                    task.add_done_callback(_generation_tasks.discard)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - 한 사용자 실패로 전체 루프 정지 금지
                await db.rollback()
                logger.exception("사이클 사용자 단계 처리 실패 user_cycle_setting_id=%s", setting_id)
    return processed, generated


async def process_due_auto_confirms(now: datetime, policy: CyclePolicy) -> int:
    processed = 0
    for order_id in await _due_order_ids(now, inbound=False):
        async with SessionLocal() as db:
            try:
                order = (
                    await db.execute(
                        select(Order)
                        .where(
                            Order.id == order_id,
                            Order.status == "draft",
                            Order.auto_confirm_at.is_not(None),
                            Order.auto_confirm_at <= now,
                        )
                        .options(selectinload(Order.items))
                        .with_for_update(skip_locked=True)
                    )
                ).scalar_one_or_none()
                if order is None:
                    continue
                user = await db.scalar(
                    select(User).where(User.id == order.user_id)
                )
                settings = await db.scalar(
                    select(UserCycleSettings).where(
                        UserCycleSettings.user_id == order.user_id
                    )
                )
                if user is None or settings is None:
                    continue
                next_start = service.next_cycle_start(
                    order.cycle_start, order.frequency, settings.anchor_weekday
                )
                result = await order_service.auto_confirm_order(
                    db,
                    user,
                    order,
                    auto_confirm=settings.auto_confirm and settings.enabled,
                    timezone_name=settings.timezone,
                    cycle_days=(next_start - order.cycle_start).days,
                    unmatched_threshold=policy.unmatched_threshold,
                    lead_days=policy.delivery_days(order.store),
                    local_hour=policy.stage_local_hour,
                )
                if (
                    result is not None
                    and result.status == "awaiting_user"
                    and order.reminded_at is None
                ):
                    order.reminded_at = now
                    await db.commit()
                    await notification_service.notify_cycle_event(
                        order.user_id,
                        "order_approval",
                        "push.orderApproval",
                        "/orders",
                    )
                processed += 1
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                await db.rollback()
                logger.exception("사이클 자동확정 처리 실패 order_id=%s", order_id)
    return processed


async def process_due_inbounds(now: datetime) -> int:
    processed = 0
    for order_id in await _due_order_ids(now, inbound=True):
        async with SessionLocal() as db:
            try:
                order = (
                    await db.execute(
                        select(Order)
                        .where(
                            Order.id == order_id,
                            Order.status == "confirmed",
                            Order.inbound_at.is_(None),
                            Order.delivery_state != "unknown",
                            Order.delivery_eta.is_not(None),
                            Order.delivery_eta <= now,
                        )
                        .with_for_update(skip_locked=True)
                    )
                ).scalar_one_or_none()
                if order is None:
                    continue
                # due 행의 user_id 로 다시 스코프한 CAS만 허용한다 (CWE-639/FR-816).
                if await order_service.mark_inbound(
                    db, order.user_id, order.id, now=now
                ):
                    processed += 1
                    await notification_service.notify_cycle_event(
                        order.user_id,
                        "fridge_inbound",
                        "push.fridgeInbound",
                        "/fridge",
                    )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                await db.rollback()
                logger.exception("사이클 냉장고 등록 처리 실패 order_id=%s", order_id)
    return processed


async def process_cycle_tick(now: datetime | None = None) -> dict[str, int]:
    """독립 3스캔을 한 번 실행하는 테스트 진입점."""
    now = now or utcnow()
    policy = load_policy()
    settings_count, generated_count = await process_due_settings(now, policy)
    auto_confirm_count = await process_due_auto_confirms(now, policy)
    inbound_count = await process_due_inbounds(now)
    return {
        "settings": settings_count,
        "generated": generated_count,
        "autoConfirmed": auto_confirm_count,
        "inbound": inbound_count,
    }


async def run_cycle_loop(interval_seconds: float | None = None) -> None:
    policy = load_policy()
    interval = interval_seconds or policy.scheduler_interval_seconds
    logger.info("주간 사이클 스케줄러 시작 (주기 %.0f초)", interval)
    try:
        while True:
            try:
                await process_cycle_tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - tick 실패 후 다음 tick 계속
                logger.exception("주간 사이클 tick 처리 실패")
            await asyncio.sleep(interval)
    finally:
        pending = list(_generation_tasks)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
