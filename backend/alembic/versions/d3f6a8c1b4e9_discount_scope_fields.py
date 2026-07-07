"""discount_scope_fields

Revision ID: d3f6a8c1b4e9
Revises: c4a7f0e2b619
Create Date: 2026-07-07

Adds scope_type/scope_outlet/scope_id to conditional_discounts — lets a
discount rule target a specific outlet (e.g. "10% off cafe only"),
category, or menu/cafe item instead of only the whole order total (the
only option before this migration). scope_type defaults to "order" so
every existing row keeps its exact previous behaviour unchanged.

Also widens condition_type/discount_type semantics at the application
layer only (no column-width change needed — both are already
String(40)/String(30)) to add "time_of_day"/"combo_items" condition
types and a "combo_fixed_price" discount type. See
app.resort_os.discount_engine.DiscountRule docstring for the full
condition_value format for each new type.

Also adds cafe_orders.applied_discount_rule_id — the cafe module never had
this column (only restaurant.orders did), so a ConditionalDiscount could
never actually be applied to a cafe order before this migration; the
discount engine's new "outlet" scope (e.g. "10% off cafe only") would
otherwise be untestable in production for the cafe side. Nullable, no
backfill needed (every existing row simply has no discount applied yet).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d3f6a8c1b4e9"
down_revision: Union[str, None] = "c4a7f0e2b619"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conditional_discounts",
        sa.Column("scope_type", sa.String(length=20), nullable=False, server_default="order"),
    )
    op.add_column(
        "conditional_discounts",
        sa.Column("scope_outlet", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "conditional_discounts",
        sa.Column("scope_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "cafe_orders",
        sa.Column("applied_discount_rule_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cafe_orders", "applied_discount_rule_id")
    op.drop_column("conditional_discounts", "scope_id")
    op.drop_column("conditional_discounts", "scope_outlet")
    op.drop_column("conditional_discounts", "scope_type")
