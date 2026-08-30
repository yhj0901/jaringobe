"""FR-805~806 냉장고 재고 프롬프트 되먹임 테스트."""

from datetime import date, timedelta
from decimal import Decimal

from app.core.config import get_settings
from app.domains.auth.models import User
from app.domains.budget.models import BudgetPlan
from app.domains.fridge.models import FridgeItem
from app.domains.mealplan import service as mealplan_service
from app.domains.mealplan.fridge_hint import build_fridge_hint
from app.domains.mealplan.generator import _prompt


async def _user_budget(db) -> tuple[User, BudgetPlan]:
    user = User(nickname="프롬프트 사용자", country="KR", currency="KRW")
    db.add(user)
    await db.flush()
    budget = BudgetPlan(
        user_id=user.id,
        household_size=2,
        amount=Decimal("300000"),
        currency="KRW",
        meal_direction="health",
        source="onboarding",
        locked=False,
    )
    db.add(budget)
    await db.commit()
    return user, budget


async def test_hint_aggregates_sorts_and_truncates_with_full_quantities(
    db, monkeypatch
):
    user, _budget = await _user_budget(db)
    settings = get_settings()
    monkeypatch.setattr(settings, "cycle_fridge_prompt_max_lines", 2)
    monkeypatch.setattr(settings, "cycle_fridge_prompt_max_expiring_lines", 2)
    today = date(2026, 8, 30)
    db.add_all(
        [
            FridgeItem(
                user_id=user.id,
                name=" 계란 ",
                quantity=Decimal("2"),
                unit="ea",
                expires_at=None,
                source="manual",
            ),
            FridgeItem(
                user_id=user.id,
                name="계란",
                quantity=Decimal("3"),
                unit="ea",
                expires_at=None,
                source="manual",
            ),
            FridgeItem(
                user_id=user.id,
                name="우유",
                quantity=Decimal("1000"),
                unit="ml",
                expires_at=None,
                source="manual",
            ),
            FridgeItem(
                user_id=user.id,
                name="쌀",
                quantity=Decimal("500"),
                unit="g",
                expires_at=None,
                source="manual",
            ),
            FridgeItem(
                user_id=user.id,
                name="두부",
                quantity=Decimal("2"),
                unit="ea",
                expires_at=today + timedelta(days=1),
                source="manual",
            ),
            FridgeItem(
                user_id=user.id,
                name="애호박",
                quantity=Decimal("1"),
                unit="ea",
                expires_at=today + timedelta(days=2),
                source="manual",
            ),
        ]
    )
    await db.commit()

    hint = await build_fridge_hint(db, user.id, "KR", today=today)
    assert "Fridge inventory" in hint
    assert "- 계란 5 ea" in hint
    assert "- ...and 2 more items" in hint
    assert "Use these FIRST" in hint
    assert f"- 두부 2 ea (expires {(today + timedelta(days=1)).isoformat()})" in hint
    assert "Allergy constraints override the fridge" in hint
    assert "Always list the FULL amount" in hint


async def test_empty_fridge_omits_section(db):
    user, _budget = await _user_budget(db)
    assert await build_fridge_hint(db, user.id, "KR") == ""
    prompt = _prompt("KR", 2, "health", 1, 1, [], [], "", "", "")
    assert "Fridge inventory" not in prompt
    assert "Use these FIRST" not in prompt


async def test_generate_within_budget_injects_hint_on_all_paths(db, monkeypatch):
    user, budget = await _user_budget(db)
    db.add(
        FridgeItem(
            user_id=user.id,
            name="계란",
            quantity=Decimal("6"),
            unit="ea",
            expires_at=None,
            source="manual",
        )
    )
    await db.commit()
    captured: dict[str, str] = {}

    async def _generate(*args):
        captured["fridge_hint"] = args[-1]
        return [
            {
                "day": 1,
                "meal_type": "breakfast",
                "name": "계란밥",
                "ingredients": [
                    {"name": "계란", "quantity": Decimal("2"), "unit": "ea"}
                ],
            }
        ]

    async def _price(*_args):
        return Decimal("0")

    monkeypatch.setattr(mealplan_service, "generate_meals", _generate)
    monkeypatch.setattr(mealplan_service, "_price", _price)
    drafts, status, total, _notes = await mealplan_service._generate_within_budget(
        db,
        budget,
        "KR",
        1,
        1,
        [],
        [],
        limit_amount=Decimal("10000"),
    )
    assert status == "ready"
    assert total == Decimal("0")
    assert drafts[0]["name"] == "계란밥"
    assert "- 계란 6 ea" in captured["fridge_hint"]

    prompt = _prompt(
        "KR",
        2,
        "health",
        1,
        1,
        ["egg"],
        [],
        "",
        "",
        captured["fridge_hint"],
    )
    assert prompt.index("Fridge inventory") < prompt.index("Return JSON")
    assert "Allergies (AVOID strictly): ['egg']" in prompt
