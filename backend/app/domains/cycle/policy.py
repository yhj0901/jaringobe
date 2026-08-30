"""주간 사이클 운영 정책 — pydantic Settings 환경변수를 안전하게 해석한다."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_DEFAULT_WEEKLY = {"generateLeadDays": 5, "draftLeadDays": 2, "graceHours": 24}
_DEFAULT_BIWEEKLY = {"generateLeadDays": 2, "draftLeadDays": 1, "graceHours": 12}
_DEFAULT_DELIVERY_LEADS = {
    "kurly": 1,
    "coupang": 1,
    "ssg": 1,
    "naver": 2,
    "walmart": 2,
    "instacart": 1,
}
_DEFAULT_EXPIRING_DAYS = {"KR": 3, "US": 5}


@dataclass(frozen=True)
class CycleProfile:
    generate_lead_days: int
    draft_lead_days: int
    grace_hours: int


@dataclass(frozen=True)
class CyclePolicy:
    scheduler_enabled: bool
    scheduler_interval_seconds: float
    weekly: CycleProfile
    biweekly: CycleProfile
    stage_local_hour: int
    jitter_minutes: int
    active_completion_min: int
    active_seen_days: int
    daily_generation_limit: int
    unmatched_threshold: Decimal
    delivery_lead_days: dict[str, int]
    delivery_lead_days_default: int
    expiring_days: dict[str, int]
    fridge_prompt_max_expiring_lines: int
    fridge_prompt_max_lines: int
    draft_retry_delays_minutes: tuple[int, ...]
    cancel_window_days: int
    delivery_unknown_attempts: int

    def profile(self, frequency: str) -> CycleProfile:
        return self.biweekly if frequency == "biweekly" else self.weekly

    def delivery_days(self, store: str) -> int:
        return self.delivery_lead_days.get(store, self.delivery_lead_days_default)

    def expiring_window(self, country: str) -> int:
        return self.expiring_days.get(country, self.expiring_days.get("KR", 3))


def _warn(key: str) -> None:
    logger.warning("사이클 정책 파싱 실패 — 기본값 사용 key=%s", key)


def _json_dict(raw: str, default: dict, key: str) -> dict:
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (TypeError, ValueError, json.JSONDecodeError):
        _warn(key)
        return dict(default)


def _positive_int(value: object, default: int, key: str, *, allow_zero: bool = False) -> int:
    try:
        parsed = int(str(value))
        if (allow_zero and parsed < 0) or (not allow_zero and parsed <= 0):
            raise ValueError
        return parsed
    except (TypeError, ValueError):
        _warn(key)
        return default


def _profile(raw: str, default: dict[str, int], key: str) -> CycleProfile:
    value = _json_dict(raw, default, key)
    return CycleProfile(
        generate_lead_days=_positive_int(
            value.get("generateLeadDays"), default["generateLeadDays"], key
        ),
        draft_lead_days=_positive_int(
            value.get("draftLeadDays"), default["draftLeadDays"], key
        ),
        grace_hours=_positive_int(value.get("graceHours"), default["graceHours"], key),
    )


def _int_map(raw: str, default: dict[str, int], key: str) -> dict[str, int]:
    value = _json_dict(raw, default, key)
    parsed: dict[str, int] = {}
    try:
        for name, amount in value.items():
            number = int(amount)
            if number < 0:
                raise ValueError
            parsed[str(name)] = number
    except (TypeError, ValueError):
        _warn(key)
        return dict(default)
    return parsed or dict(default)


def _retry_delays(raw: str) -> tuple[int, ...]:
    try:
        values = tuple(int(v.strip()) for v in raw.split(",") if v.strip())
        if not values or any(v <= 0 for v in values):
            raise ValueError
        return values
    except (AttributeError, ValueError):
        _warn("CYCLE_DRAFT_RETRY_DELAYS_MINUTES")
        return (1, 5, 15)


def load_policy() -> CyclePolicy:
    """현재 환경변수 스냅샷을 정책 객체로 변환한다."""
    settings = get_settings()
    try:
        unmatched = Decimal(str(settings.cycle_unmatched_threshold))
        if unmatched < 0 or unmatched > 1:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        _warn("CYCLE_UNMATCHED_THRESHOLD")
        unmatched = Decimal("0.30")

    hour = _positive_int(
        settings.cycle_stage_local_hour,
        9,
        "CYCLE_STAGE_LOCAL_HOUR",
        allow_zero=True,
    )
    if hour > 23:
        _warn("CYCLE_STAGE_LOCAL_HOUR")
        hour = 9

    return CyclePolicy(
        scheduler_enabled=settings.cycle_scheduler_enabled,
        scheduler_interval_seconds=max(1.0, settings.cycle_scheduler_interval_seconds),
        weekly=_profile(
            settings.cycle_profile_weekly, _DEFAULT_WEEKLY, "CYCLE_PROFILE_WEEKLY"
        ),
        biweekly=_profile(
            settings.cycle_profile_biweekly, _DEFAULT_BIWEEKLY, "CYCLE_PROFILE_BIWEEKLY"
        ),
        stage_local_hour=hour,
        jitter_minutes=_positive_int(
            settings.cycle_jitter_minutes,
            30,
            "CYCLE_JITTER_MINUTES",
            allow_zero=True,
        ),
        active_completion_min=_positive_int(
            settings.cycle_active_completion_min,
            1,
            "CYCLE_ACTIVE_COMPLETION_MIN",
        ),
        active_seen_days=_positive_int(
            settings.cycle_active_seen_days, 14, "CYCLE_ACTIVE_SEEN_DAYS"
        ),
        daily_generation_limit=_positive_int(
            settings.cycle_daily_generation_limit,
            200,
            "CYCLE_DAILY_GENERATION_LIMIT",
        ),
        unmatched_threshold=unmatched,
        delivery_lead_days=_int_map(
            settings.cycle_delivery_lead_days,
            _DEFAULT_DELIVERY_LEADS,
            "CYCLE_DELIVERY_LEAD_DAYS",
        ),
        delivery_lead_days_default=_positive_int(
            settings.cycle_delivery_lead_days_default,
            1,
            "CYCLE_DELIVERY_LEAD_DAYS_DEFAULT",
            allow_zero=True,
        ),
        expiring_days=_int_map(
            settings.cycle_expiring_days,
            _DEFAULT_EXPIRING_DAYS,
            "CYCLE_EXPIRING_DAYS",
        ),
        fridge_prompt_max_expiring_lines=_positive_int(
            settings.cycle_fridge_prompt_max_expiring_lines,
            15,
            "CYCLE_FRIDGE_PROMPT_MAX_EXPIRING_LINES",
            allow_zero=True,
        ),
        fridge_prompt_max_lines=_positive_int(
            settings.cycle_fridge_prompt_max_lines,
            25,
            "CYCLE_FRIDGE_PROMPT_MAX_LINES",
            allow_zero=True,
        ),
        draft_retry_delays_minutes=_retry_delays(settings.cycle_draft_retry_delays_minutes),
        cancel_window_days=_positive_int(
            settings.cycle_cancel_window_days, 7, "CYCLE_CANCEL_WINDOW_DAYS"
        ),
        delivery_unknown_attempts=_positive_int(
            settings.cycle_delivery_unknown_attempts,
            3,
            "CYCLE_DELIVERY_UNKNOWN_ATTEMPTS",
        ),
    )
