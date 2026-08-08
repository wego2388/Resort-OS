"""add real room inventory fields and explicit unpriced state

Revision ID: d0e1f2a3b4c5
Revises: c9d4e5f6a7b8
Create Date: 2026-08-08

Real El Kheima units are identified independently by physical type and view.
Their commercial prices/capacities have not been approved, so NULL deliberately
means "not configured"; it must not be represented as a zero financial value.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "d0e1f2a3b4c5"
down_revision = "c9d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "room_types",
        "base_rate",
        existing_type=sa.Numeric(10, 2),
        nullable=True,
    )
    op.alter_column(
        "room_types",
        "max_occupancy",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.add_column(
        "rooms",
        sa.Column(
            "view_type",
            sa.String(20),
            nullable=False,
            server_default="none",
        ),
    )
    op.create_check_constraint(
        "ck_rooms_view_type_valid",
        "rooms",
        "view_type IN ('none', 'side_sea', 'sea')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    missing_configuration = bind.execute(
        sa.text(
            "SELECT count(*) FROM room_types "
            "WHERE base_rate IS NULL OR max_occupancy IS NULL"
        )
    ).scalar_one()
    if missing_configuration:
        raise RuntimeError(
            "Downgrade blocked: room types still have unapproved NULL pricing "
            "or capacity. Restore the pre-deploy backup or configure them first."
        )

    op.drop_constraint("ck_rooms_view_type_valid", "rooms", type_="check")
    op.drop_column("rooms", "view_type")
    op.alter_column(
        "room_types",
        "max_occupancy",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "room_types",
        "base_rate",
        existing_type=sa.Numeric(10, 2),
        nullable=False,
    )
