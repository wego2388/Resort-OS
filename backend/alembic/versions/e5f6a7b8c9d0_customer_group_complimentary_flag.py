"""crm_customer_groups.is_complimentary — distinguish welfare/comp discounts
(staff, VIP comps) from ordinary commercial discounts (loyalty, negotiated
corporate rates) so settlement can post the forgone amount as a real
expense instead of letting it vanish.

Revision ID: e5f6a7b8c9d0
Revises: d1e2f3a4b5c6
"""

import sqlalchemy as sa

from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crm_customer_groups",
        sa.Column(
            "is_complimentary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("crm_customer_groups", "is_complimentary")
