"""notification 도메인 비즈니스 로직 — 디바이스 토큰/설정/next_send_at 재계산.

- 토큰 upsert: token 기준 idempotent. 타 유저 소유 토큰은 현 유저로 이전 (기기 재사용 — CWE-639)
- 설정: GET 최초 호출 시 기본값 lazy 생성 (08:00/12:00/18:30, weekly_nudge 만 off)
- next_send_at: "로컬시각 + IANA 존" 쌍 → UTC 환산 다음 발송 시각 (DST 대응)
"""

import logging
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.security import utcnow
from app.domains.auth.models import User
from app.domains.notification import sender
from app.domains.notification.models import SETTING_TYPES, DeviceToken, NotificationSetting
from app.domains.notification.schemas import (
    REMINDER_TYPES,
    DeviceRegisterRequest,
    NotificationSettingOut,
    NotificationSettingUpdateItem,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "Asia/Seoul"

# 리마인더 기본 시각 — 기획 FR-006 (아침 08:00 / 점심 12:00 / 저녁 18:30)
DEFAULT_REMINDER_TIMES: dict[str, time] = {
    "meal_reminder_breakfast": time(8, 0),
    "meal_reminder_lunch": time(12, 0),
    "meal_reminder_dinner": time(18, 30),
}

# 기본 enabled — weekly_nudge(P2) 만 off (api-spec 6-A-3)
DEFAULT_ENABLED: dict[str, bool] = {t: (t != "weekly_nudge") for t in SETTING_TYPES}


def compute_next_send_at(local_time: time, tz_name: str, now: datetime) -> datetime:
    """로컬시각+IANA 존 → 다음 발송 시각(UTC). now 이후의 가장 가까운 해당 로컬시각."""
    tz = ZoneInfo(tz_name)
    local_now = now.astimezone(tz)
    candidate = datetime.combine(local_now.date(), local_time, tzinfo=tz)
    if candidate <= local_now:
        # 오늘 시각이 지났으면 익일 동일 로컬시각 (날짜 재조합 — DST 경계 대응)
        candidate = datetime.combine(local_now.date() + timedelta(days=1), local_time, tzinfo=tz)
    return candidate.astimezone(UTC)


def _recompute_setting_schedule(setting: NotificationSetting, now: datetime) -> None:
    """리마인더 + enabled 일 때만 next_send_at 유지, 그 외 None."""
    if (
        setting.type in REMINDER_TYPES
        and setting.enabled
        and setting.local_time is not None
    ):
        setting.next_send_at = compute_next_send_at(
            setting.local_time, setting.timezone or DEFAULT_TIMEZONE, now
        )
    else:
        setting.next_send_at = None


# ---------- 디바이스 토큰 ----------


async def upsert_device(db: AsyncSession, user: User, req: DeviceRegisterRequest) -> uuid.UUID:
    """token 기준 idempotent upsert. 타 유저 소유 token 은 현 유저로 이전 (오발송 차단)."""
    now = utcnow()
    device = await db.scalar(select(DeviceToken).where(DeviceToken.token == req.token))
    if device is None:
        device = DeviceToken(
            user_id=user.id,
            platform=req.platform,
            token=req.token,
            locale=req.locale,
            timezone=req.timezone,
            app_version=req.app_version,
            last_seen_at=now,
        )
        db.add(device)
    else:
        if device.user_id != user.id:
            # 기기 양도/계정 전환 — 이전 소유자에게 오발송 차단 (security-design.md 5-4)
            device.user_id = user.id
        device.platform = req.platform
        device.locale = req.locale
        device.timezone = req.timezone
        device.app_version = req.app_version
        device.last_seen_at = now
    await db.commit()
    return device.id


async def delete_device(db: AsyncSession, user: User, token: str) -> None:
    """본인 소유 토큰만 삭제 (CWE-639). 없는/타인 토큰도 조용히 204 (idempotent)."""
    await db.execute(
        delete(DeviceToken).where(DeviceToken.token == token, DeviceToken.user_id == user.id)
    )
    await db.commit()


# ---------- 알림 설정 ----------


async def _latest_device_timezone(db: AsyncSession, user_id: uuid.UUID) -> str:
    tz = await db.scalar(
        select(DeviceToken.timezone)
        .where(DeviceToken.user_id == user_id)
        .order_by(DeviceToken.last_seen_at.desc())
        .limit(1)
    )
    return tz or DEFAULT_TIMEZONE


async def get_or_create_settings(
    db: AsyncSession, user: User
) -> list[NotificationSetting]:
    """설정 5행 조회 — 없는 type 은 기본값으로 lazy 생성 (api-spec 6-A-3)."""
    rows = (
        (await db.execute(select(NotificationSetting).where(NotificationSetting.user_id == user.id)))
        .scalars()
        .all()
    )
    by_type = {r.type: r for r in rows}
    missing = [t for t in SETTING_TYPES if t not in by_type]
    if missing:
        now = utcnow()
        default_tz = await _latest_device_timezone(db, user.id)
        for t in missing:
            setting = NotificationSetting(
                user_id=user.id,
                type=t,
                enabled=DEFAULT_ENABLED[t],
                local_time=DEFAULT_REMINDER_TIMES.get(t),
                timezone=default_tz if t in REMINDER_TYPES else None,
            )
            _recompute_setting_schedule(setting, now)
            db.add(setting)
            by_type[t] = setting
        await db.commit()
    return [by_type[t] for t in SETTING_TYPES]


async def update_settings(
    db: AsyncSession, user: User, items: list[NotificationSettingUpdateItem]
) -> list[NotificationSetting]:
    """부분 갱신 — 보낸 type 만 반영 후 next_send_at(UTC) 재계산, 전체 설정 반환."""
    settings = await get_or_create_settings(db, user)
    by_type = {s.type: s for s in settings}
    now = utcnow()
    for item in items:
        setting = by_type[item.type]
        if item.enabled is not None:
            setting.enabled = item.enabled
        if item.local_time is not None:
            setting.local_time = item.parsed_local_time()
        if item.timezone is not None:
            setting.timezone = item.timezone
        _recompute_setting_schedule(setting, now)
    await db.commit()
    return [by_type[t] for t in SETTING_TYPES]


def serialize_settings(settings: list[NotificationSetting]) -> list[NotificationSettingOut]:
    return [
        NotificationSettingOut(
            type=s.type,
            enabled=s.enabled,
            local_time=s.local_time.strftime("%H:%M") if s.local_time is not None else None,
            timezone=s.timezone,
        )
        for s in settings
    ]


async def is_type_enabled(db: AsyncSession, user_id: uuid.UUID, type_: str) -> bool:
    """설정 행이 없으면 기본값 (weekly_nudge 만 off) 으로 판정."""
    enabled = await db.scalar(
        select(NotificationSetting.enabled).where(
            NotificationSetting.user_id == user_id, NotificationSetting.type == type_
        )
    )
    if enabled is None:
        return DEFAULT_ENABLED.get(type_, False)
    return bool(enabled)


# ---------- 식단 생성 완료/실패 푸시 (mealplan 도메인에서 호출) ----------


async def notify_mealplan_result(
    user_id: uuid.UUID, plan_id: uuid.UUID, succeeded: bool
) -> None:
    """생성 완료/실패 푸시 — 자체 세션 사용, 실패해도 예외를 올리지 않는다 (보조 채널)."""
    try:
        async with SessionLocal() as db:
            if not await is_type_enabled(db, user_id, "mealplan_done"):
                return
            template_key = "push.mealplanDone" if succeeded else "push.mealplanFailed"
            await sender.send_to_user(
                db,
                user_id,
                type_="mealplan_done",
                template_key=template_key,
                path=f"/mealplan/{plan_id}",
            )
    except Exception:  # noqa: BLE001 - 푸시는 보조 채널, 생성 결과에 영향 금지
        logger.exception("식단 생성 결과 푸시 발송 실패 user_id=%s plan_id=%s", user_id, plan_id)
