"""Support final customer-facing dining prices.

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
"""

import sqlalchemy as sa

from alembic import op

revision = "d1e2f3a4b5c6"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dining_items",
        sa.Column(
            "price_includes_vat_service",
            sa.Boolean(),
            nullable=False,
            # Mohamed's 2026-08-12 commercial rule: every displayed dining
            # price is final and already includes VAT + service.
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "dining_order_items",
        sa.Column("listed_unit_price", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "dining_order_item_extras",
        sa.Column("listed_price_addition", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dining_order_item_extras", "listed_price_addition")
    op.drop_column("dining_order_items", "listed_unit_price")
    op.drop_column("dining_items", "price_includes_vat_service")
