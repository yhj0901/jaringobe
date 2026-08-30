"""notification 도메인 Pydantic 스키마 — api-spec.md 6-A (camelCase, CamelModel)."""

import re
import uuid
from datetime import time
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator

from app.core.schema import CamelModel

SettingType = Literal[
    "meal_reminder_breakfast",
    "meal_reminder_lunch",
    "meal_reminder_dinner",
    "mealplan_done",
    "weekly_nudge",
]

REMINDER_TYPES = ("meal_reminder_breakfast", "meal_reminder_lunch", "meal_reminder_dinner")

# Expo Push Token 형식 — ExponentPushToken[...] / ExpoPushToken[...]
_EXPO_TOKEN_RE = re.compile(r"^Expo(nent)?PushToken\[[^\[\]]+\]$")
_LOCAL_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def validate_iana_timezone(value: str) -> str:
    """IANA 타임존 유효성 검증 (예: Asia/Seoul, America/New_York)."""
    try:
        ZoneInfo(value)
    except Exception as exc:
        raise ValueError(f"invalid IANA timezone: {value}") from exc
    return value


class DeviceRegisterRequest(CamelModel):
    """PUT /notifications/devices — token 기준 idempotent upsert (api-spec 6-A-1)."""

    token: str = Field(max_length=4096)
    platform: Literal["ios", "android"]
    locale: Literal["ko", "en"]
    timezone: str = Field(max_length=40)
    app_version: str | None = Field(default=None, max_length=20)

    @field_validator("token")
    @classmethod
    def validate_expo_token(cls, v: str) -> str:
        if not _EXPO_TOKEN_RE.match(v):
            raise ValueError("token must be an Expo push token")
        return v

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        return validate_iana_timezone(v)


class DeviceRegisterResponse(CamelModel):
    id: uuid.UUID


class NotificationSettingOut(CamelModel):
    type: str
    enabled: bool
    local_time: str | None = None  # "HH:MM" (리마인더 3종만)
    timezone: str | None = None


class NotificationSettingsResponse(CamelModel):
    settings: list[NotificationSettingOut]


class NotificationSettingUpdateItem(CamelModel):
    """PUT /notifications/settings 항목 — 보낸 필드만 반영 (부분 갱신)."""

    type: SettingType
    enabled: bool | None = None
    local_time: str | None = None
    timezone: str | None = None

    @field_validator("local_time")
    @classmethod
    def validate_local_time_format(cls, v: str | None) -> str | None:
        if v is not None and not _LOCAL_TIME_RE.match(v):
            raise ValueError("localTime must be HH:MM (24h)")
        return v

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is not None:
            return validate_iana_timezone(v)
        return v

    @model_validator(mode="after")
    def validate_local_time_only_for_reminders(self) -> "NotificationSettingUpdateItem":
        # localTime 은 리마인더 3종만 허용 — 그 외 type 에 오면 422 (api-spec 6-A-4)
        if self.local_time is not None and self.type not in REMINDER_TYPES:
            raise ValueError(f"localTime is not allowed for type '{self.type}'")
        return self

    def parsed_local_time(self) -> time | None:
        if self.local_time is None:
            return None
        hh, mm = self.local_time.split(":")
        return time(int(hh), int(mm))


class NotificationSettingsUpdateRequest(CamelModel):
    settings: list[NotificationSettingUpdateItem] = Field(min_length=1, max_length=5)
