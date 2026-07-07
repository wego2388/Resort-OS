"""beach_locations_live_map

Revision ID: c4a7f0e2b619
Revises: 55029698cdf1
Create Date: 2026-07-07

Adds beach_locations — a live per-spot beach map (individual physical
umbrella/pergola/sunbed, each with a real occupancy status and a link to
whichever guest/transaction currently occupies it). Checking a guest into a
location produces a real BeachTransaction (via services.checkin_location,
which reuses services.sell_ticket's pricing/VAT/journal/CRM/charge-to-room
logic) rather than an untracked side action — see BeachLocation's docstring
in app/modules/beach/models.py for the full design rationale, including why
this is deliberately independent from BeachReservation (a pre-arrival
booking, not a physical spot's live state).

Also adds beach_transactions.location_id (nullable, SET NULL) so a
transaction retains which physical spot it was for even after that spot is
later freed up (checkout clears BeachLocation.current_transaction_id, but
the transaction's own location_id is permanent history).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4a7f0e2b619"
down_revision: Union[str, None] = "55029698cdf1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "beach_locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("location_type", sa.String(length=20), nullable=False),
        sa.Column("number", sa.String(length=10), nullable=False),
        sa.Column("grid_row", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("grid_col", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="available"),
        sa.Column("current_transaction_id", sa.Integer(), nullable=True),
        sa.Column("guest_name", sa.String(length=200), nullable=True),
        sa.Column("guest_phone", sa.String(length=20), nullable=True),
        sa.Column("guests_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("towels_given", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checked_in_at", sa.DateTime(), nullable=True),
        sa.Column("checked_in_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["current_transaction_id"], ["beach_transactions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("branch_id", "location_type", "number",
                             name="uq_beach_location_branch_type_number"),
    )
    op.create_index(op.f("ix_beach_locations_branch_id"), "beach_locations", ["branch_id"], unique=False)
    op.create_index(op.f("ix_beach_locations_status"), "beach_locations", ["status"], unique=False)

    op.add_column("beach_transactions", sa.Column("location_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_beach_transactions_location_id", "beach_transactions", "beach_locations",
        ["location_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(op.f("ix_beach_transactions_location_id"), "beach_transactions", ["location_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_beach_transactions_location_id"), table_name="beach_transactions")
    op.drop_constraint("fk_beach_transactions_location_id", "beach_transactions", type_="foreignkey")
    op.drop_column("beach_transactions", "location_id")

    op.drop_index(op.f("ix_beach_locations_status"), table_name="beach_locations")
    op.drop_index(op.f("ix_beach_locations_branch_id"), table_name="beach_locations")
    op.drop_table("beach_locations")
