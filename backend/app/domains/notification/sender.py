"""Expo Push 발송 — ko/en 템플릿 렌더 + 발송 이력 기록 + 무효 토큰 정리.

- 인증: EXPO_ACCESS_TOKEN (.env, core/config 경유 — CWE-522)
- 본문: 메뉴명·완료 여부까지만 (CWE-359, 잠금화면 노출 전제)
- 이력: notification_logs 에 본문 원문 저장 금지 — template_key 만
- DeviceNotRegistered 응답 → 해당 토큰 즉시 삭제
- 디바이스 토큰은 로그에 원문 출력 금지 (마스킹)
"""

import logging
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import utcnow
from app.domains.notification.models import DeviceToken, NotificationLog

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
SEND_TIMEOUT_SECONDS = 10.0

# 푸시 템플릿 카탈로그 (i18n — ko/en 동시 관리, api-spec 6-A-5)
# 변수: push.mealReminder → meal_type(로캘 라벨 치환), recipe_name
TEMPLATES: dict[str, dict[str, tuple[str, str]]] = {
    "push.mealplanDone": {
        "ko": ("🍽 이번 주 식단이 완성됐어요", "지금 확인하고 장보기를 시작해 보세요."),
        "en": ("🍽 Your meal plan is ready", "Check it out and start shopping."),
    },
    "push.mealplanFailed": {
        "ko": ("식단 생성에 실패했어요", "잠시 후 다시 시도해 주세요."),
        "en": ("Meal plan generation failed", "Please try again in a moment."),
    },
    "push.mealReminder": {
        "ko": ("오늘 {meal_type}: {recipe_name}", "지금 만들어 볼까요?"),
        "en": ("Today's {meal_type}: {recipe_name}", "Time to cook it up!"),
    },
    "push.weeklyNudge": {
        "ko": ("이번 주 식단이 아직 없어요", "예산에 맞는 식단을 만들어 볼까요?"),
        "en": ("No meal plan for this week yet", "Shall we create one within your budget?"),
    },
}

# meal_type 로캘 라벨 (리마인더 본문용)
MEAL_TYPE_LABELS: dict[str, dict[str, str]] = {
    "ko": {"breakfast": "아침", "lunch": "점심", "dinner": "저녁", "snack": "간식", "supper": "야식"},
    "en": {"breakfast": "breakfast", "lunch": "lunch", "dinner": "dinner", "snack": "snack", "supper": "supper"},
}


def mask_token(token: str) -> str:
    """디바이스 토큰 로그 마스킹 (CWE-522)."""
    return token[:18] + "…" if len(token) > 18 else "…"


def render_template(
    template_key: str, locale: str, variables: dict[str, str] | None = None
) -> tuple[str, str]:
    """템플릿 키 + 로캘 → (title, body). 미지원 로캘은 ko 폴백."""
    catalog = TEMPLATES[template_key]
    title_fmt, body_fmt = catalog.get(locale, catalog["ko"])
    vars_ = dict(variables or {})
    if "meal_type" in vars_:
        labels = MEAL_TYPE_LABELS.get(locale, MEAL_TYPE_LABELS["ko"])
        vars_["meal_type"] = labels.get(vars_["meal_type"], vars_["meal_type"])
    return title_fmt.format(**vars_), body_fmt.format(**vars_)


def build_message(
    device: DeviceToken, template_key: str, path: str, variables: dict[str, str] | None = None
) -> dict:
    """Expo 발송 페이로드 — data.path 는 내부 상대경로만 (CWE-601, api-spec 6-A-5)."""
    title, body = render_template(template_key, device.locale, variables)
    return {
        "to": device.token,
        "title": title,
        "body": body,
        "data": {"v": 1, "path": path},
    }


async def _post_expo(messages: list[dict]) -> list[dict]:
    """Expo Push API 호출 — 타임아웃 필수, 실패 시 예외 전파 (호출부에서 이력 기록)."""
    settings = get_settings()
    headers = {"Content-Type": "application/json"}
    if settings.expo_access_token:
        headers["Authorization"] = f"Bearer {settings.expo_access_token}"
    async with httpx.AsyncClient(timeout=SEND_TIMEOUT_SECONDS) as client:
        res = await client.post(EXPO_PUSH_URL, json=messages, headers=headers)
        res.raise_for_status()
        data = res.json().get("data", [])
    if not isinstance(data, list):
        data = []
    return data


async def send_to_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    type_: str,
    template_key: str,
    path: str,
    variables: dict[str, str] | None = None,
) -> int:
    """유저의 전체 디바이스에 발송. 반환: 성공(sent) 건수.

    발송 결과는 notification_logs 에 기록(template_key 만),
    DeviceNotRegistered 응답 토큰은 즉시 삭제한다 (FR-011).
    """
    devices = (
        (await db.execute(select(DeviceToken).where(DeviceToken.user_id == user_id)))
        .scalars()
        .all()
    )
    if not devices:
        return 0

    messages = [build_message(d, template_key, path, variables) for d in devices]
    try:
        tickets = await _post_expo(messages)
    except Exception:  # noqa: BLE001 - 외부 연동 실패는 전 건 failed 기록 (폴백: 화면 폴링)
        logger.exception("Expo Push API 호출 실패 user_id=%s template=%s", user_id, template_key)
        tickets = [{"status": "error", "details": {"error": "REQUEST_ERROR"}}] * len(devices)

    sent = 0
    now = utcnow()
    for device, ticket in zip(devices, tickets, strict=False):
        ok = isinstance(ticket, dict) and ticket.get("status") == "ok"
        error_code = None
        if not ok:
            details = ticket.get("details") if isinstance(ticket, dict) else None
            error_code = (details or {}).get("error") or "UNKNOWN"
        db.add(
            NotificationLog(
                user_id=user_id,
                device_token_id=device.id,
                type=type_,
                template_key=template_key,
                status="sent" if ok else "failed",
                error_code=error_code,
                sent_at=now,
            )
        )
        if ok:
            sent += 1
        elif error_code == "DeviceNotRegistered":
            # 만료/무효 토큰 즉시 삭제 (FR-011, 세션 보안 요구)
            logger.info("무효 디바이스 토큰 삭제 token=%s", mask_token(device.token))
            await db.delete(device)
    await db.commit()
    return sent
