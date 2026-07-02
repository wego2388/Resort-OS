"""Finance: add currency column to folios and payments (multi-currency support)

Revision ID: f1a2b3c4d5e6
Revises: a97674556485
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d5e6"
down_revision = "a97674556485"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "folios",
        sa.Column("currency", sa.String(3), nullable=False, server_default="EGP"),
    )
    op.add_column(
        "payments",
        sa.Column("currency", sa.String(3), nullable=False, server_default="EGP"),
    )


def downgrade() -> None:
    op.drop_column("payments", "currency")
    op.drop_column("folios", "currency")
