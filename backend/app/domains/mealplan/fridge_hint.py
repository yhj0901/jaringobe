"""냉장고 재고를 LLM 식단 프롬프트용 제한된 문자열로 조립한다."""

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import utcnow
from app.domains.fridge.models import FridgeItem

_DEFAULT_EXPIRING_DAYS = {"KR": 3, "US": 5}


@dataclass
class _Aggregate:
    name: str
    quantity: Decimal
    unit: str
    expires_at: date | None
    created_at: datetime


def _qstr(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _safe_name(value: str) -> str:
    return " ".join(value.split())


def _aggregate(rows: list[FridgeItem]) -> list[_Aggregate]:
    by_key: dict[tuple[str, str], _Aggregate] = {}
    for row in rows:
        key = (row.name.strip().lower(), row.unit)
        current = by_key.get(key)
        if current is None:
            by_key[key] = _Aggregate(
                name=_safe_name(row.name) or row.name,
                quantity=row.quantity,
                unit=row.unit,
                expires_at=row.expires_at,
                created_at=row.created_at,
            )
            continue
        current.quantity += row.quantity
        if row.expires_at is not None and (
            current.expires_at is None or row.expires_at < current.expires_at
        ):
            current.expires_at = row.expires_at
        if row.created_at < current.created_at:
            current.created_at = row.created_at
    return list(by_key.values())


def _sort_key(item: _Aggregate) -> tuple[date, datetime, str, str]:
    return (
        item.expires_at or date.max,
        item.created_at,
        item.name.lower(),
        item.unit,
    )


def _lines(items: list[_Aggregate], maximum: int, *, expiring: bool) -> list[str]:
    if maximum <= 0:
        return []
    shown = items if len(items) <= maximum else items[: maximum - 1]
    lines = [
        f"- {item.name} {_qstr(item.quantity)} {item.unit}"
        + (
            f" (expires {item.expires_at.isoformat()})"
            if expiring and item.expires_at is not None
            else ""
        )
        for item in shown
    ]
    omitted = len(items) - len(shown)
    if omitted > 0:
        lines.append(f"- ...and {omitted} more items")
    return lines


async def build_fridge_hint(
    db: AsyncSession,
    user_id: uuid.UUID,
    country: str,
    *,
    today: date | None = None,
) -> str:
    """최대 15 임박 + 25 일반 줄로 재고를 합산·절삭한다."""
    settings = get_settings()
    try:
        parsed = json.loads(settings.cycle_expiring_days)
        if not isinstance(parsed, dict):
            raise ValueError
        expiring_days = {str(key): int(value) for key, value in parsed.items()}
        if any(value < 0 for value in expiring_days.values()):
            raise ValueError
    except (TypeError, ValueError, json.JSONDecodeError):
        expiring_days = _DEFAULT_EXPIRING_DAYS
    expiring_window = expiring_days.get(country, expiring_days.get("KR", 3))
    max_expiring = max(0, settings.cycle_fridge_prompt_max_expiring_lines)
    max_regular = max(0, settings.cycle_fridge_prompt_max_lines)
    today = today or utcnow().date()
    rows = list(
        (
            await db.execute(
                select(FridgeItem).where(FridgeItem.user_id == user_id)
            )
        ).scalars().all()
    )
    aggregated = sorted(_aggregate(rows), key=_sort_key)
    threshold = today + timedelta(days=expiring_window)
    expiring = [
        item
        for item in aggregated
        if item.expires_at is not None and item.expires_at <= threshold
    ]
    regular = [item for item in aggregated if item not in expiring]
    if not expiring and not regular:
        return ""

    sections: list[str] = []
    regular_lines = _lines(regular, max_regular, expiring=False)
    if regular_lines:
        sections.append(
            "\n".join(
                [
                    "Fridge inventory (already owned — prefer recipes that consume these):",
                    *regular_lines,
                ]
            )
        )
    expiring_lines = _lines(expiring, max_expiring, expiring=True)
    if expiring_lines:
        sections.append(
            "\n".join(
                [
                    "Use these FIRST (expiring soon):",
                    *expiring_lines,
                ]
            )
        )
    if not sections:
        return ""
    sections.append(
        "\n".join(
            [
                "RULES:",
                "- Do NOT reduce ingredient quantities because an item is in the fridge.",
                "  Always list the FULL amount the recipe needs; the server subtracts stock separately.",
                "- Allergy constraints override the fridge. Never use a fridge item that is an allergen.",
            ]
        )
    )
    return "\n".join(sections)
