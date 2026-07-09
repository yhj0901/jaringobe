"""mealplan 도메인 테이블 (meal_plans/meals/meal_ingredients/ingredient_price_refs)

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meal_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("budget_plan_id", UUID(as_uuid=True), sa.ForeignKey("budget_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ready"),
        sa.Column("total_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.CHAR(3), nullable=False),
        sa.Column("region", sa.CHAR(2), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_meal_plans_user_created", "meal_plans", ["user_id", "created_at"])

    op.create_table(
        "meals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("meal_plan_id", UUID(as_uuid=True), sa.ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("meal_type", sa.String(16), nullable=False),
        sa.Column("recipe_name", sa.String(200), nullable=False),
        sa.Column("recipe_steps", sa.Text(), nullable=True),
    )
    op.create_index("ix_meals_plan_date", "meals", ["meal_plan_id", "plan_date"])

    op.create_table(
        "meal_ingredients",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("meal_id", UUID(as_uuid=True), sa.ForeignKey("meals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("est_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.CHAR(3), nullable=True),
    )
    op.create_index("ix_meal_ingredients_meal", "meal_ingredients", ["meal_id"])

    op.create_table(
        "ingredient_price_refs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("region", sa.CHAR(2), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("pack_qty", sa.Numeric(10, 3), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False),
        sa.UniqueConstraint("name", "region", "unit", name="uq_price_name_region_unit"),
    )
    op.create_index("ix_price_region_name", "ingredient_price_refs", ["region", "name"])


def downgrade() -> None:
    op.drop_index("ix_price_region_name", table_name="ingredient_price_refs")
    op.drop_table("ingredient_price_refs")
    op.drop_index("ix_meal_ingredients_meal", table_name="meal_ingredients")
    op.drop_table("meal_ingredients")
    op.drop_index("ix_meals_plan_date", table_name="meals")
    op.drop_table("meals")
    op.drop_index("ix_meal_plans_user_created", table_name="meal_plans")
    op.drop_table("meal_plans")
