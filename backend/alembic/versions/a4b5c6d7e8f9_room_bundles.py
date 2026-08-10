"""room_bundles table + bookings.room_bundle_id

Revision ID: a4b5c6d7e8f9
Revises: f2a3b4c5d6e7
Create Date: 2026-08-10

OPS-DATA-02 §7.1/§3: "Family Compound 6P" is not a third RoomType — it is
an atomic booking of a Chalet + Family Studio sharing the same unit number.
room_bundles records which specific Room pairs are the Mohamed-approved
combos and the bundle's own net nightly price; the underlying booking still
uses two ordinary BookingRoom rows (see pms.services.create_bundle_booking).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "a4b5c6d7e8f9"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "room_bundles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("name_ar", sa.String(100), nullable=True),
        sa.Column("chalet_room_id", sa.Integer(), sa.ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("studio_room_id", sa.Integer(), sa.ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("max_occupancy", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("chalet_room_id", name="uq_room_bundle_chalet_room"),
        sa.UniqueConstraint("studio_room_id", name="uq_room_bundle_studio_room"),
    )

    op.add_column(
        "bookings",
        sa.Column(
            "room_bundle_id", sa.Integer(),
            sa.ForeignKey("room_bundles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("bookings", "room_bundle_id")
    op.drop_table("room_bundles")
