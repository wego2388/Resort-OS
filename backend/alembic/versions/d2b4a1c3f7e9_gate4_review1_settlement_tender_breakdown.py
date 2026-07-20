"""Gate 4 review round 1 (M2) — dining_settlements.tender_breakdown snapshot

Revision ID: d2b4a1c3f7e9
Revises: c9f1a4d7e2b8
Create Date: 2026-07-20

Additive, forward-only. Adds a single nullable JSON column
``dining_settlements.tender_breakdown`` — a per-settlement snapshot of the
tender allocation ([{"method","amount","account"?,"folio_id"?}]) captured at
settlement time (Gate 4 Codex review round 1, finding M2).

Why: the settlement's exact tender split used to live only as live
``finance.Payment`` rows (direct tenders) plus a ``FolioCharge`` (room tender).
That made the shift-end report blind to room tenders (no Payment row exists
for them) and left historical receipts / OrderRead dependent on current
Payment state (which a later reversal mutates). The snapshot is the
independent historical source: the shift report sums the room share from it,
and a receipt can reconstruct the split without today's menu prices.

Rollback honesty: downgrade drops the column. After the app starts writing
snapshots, a downgrade loses the historical breakdown for any settlement made
under this revision — maintenance-only, not a safe production revert once real
settlements carry snapshots. No data predating this migration is destroyed by
the upgrade (the column is nullable; existing rows get NULL).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "d2b4a1c3f7e9"
down_revision = "c9f1a4d7e2b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dining_settlements",
        sa.Column("tender_breakdown", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dining_settlements", "tender_breakdown")
