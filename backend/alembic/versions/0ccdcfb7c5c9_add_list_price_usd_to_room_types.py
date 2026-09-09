"""add list_price_usd to room_types

Revision ID: 0ccdcfb7c5c9
Revises: d86579367d94
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0ccdcfb7c5c9"
down_revision = "d86579367d94"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "room_types",
        sa.Column("list_price_usd", sa.Numeric(precision=10, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("room_types", "list_price_usd")
