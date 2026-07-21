"""dining_tables_shared_across_outlets

Revision ID: 9b4e1a2c7f30
Revises: d2b4a1c3f7e9
Create Date: 2026-07-21 00:00:00.000000

Mohamed (real user report, 2026-07-21): switching the outlet dropdown
(restaurant/cafe) on the unified POS screen shows a **completely different
table grid** — cafe shows tables 1-8, restaurant shows a separate 1-13 set.
Real-world layout has exactly one physical set of tables shared by every
outlet; only the *menu* should change when the cashier switches outlet, not
the tables themselves.

Root cause: `dining_venue_tables.outlet_id` was a required FK (VenueTable
was scoped to one outlet), so `_seed_dining_tables` had always created two
duplicate physical sets per branch — 12 "restaurant" tables + 8 "cafe"
tables, both numbered from 1. This migration consolidates them into one
branch-scoped set and drops the outlet ownership entirely — see
`VenueTable`'s updated docstring (`app/modules/dining/models.py`).

Data reconciliation (idempotent, per branch):
  - If a branch's tables are already scoped to a single outlet_id (or has
    none), nothing to reconcile.
  - Otherwise, keep the outlet with the most table rows (tie-break: lowest
    outlet_id) as the canonical numbering, and delete the other outlet(s)'
    table rows for that branch. `dining_orders.table_id` has
    `ondelete=SET NULL`, so any *closed/historical* order referencing a
    deleted table is safely detached automatically — expected and harmless.
  - Safety guard: if any row about to be deleted is referenced by a
    currently ACTIVE order (held/open/in_kitchen/served), the migration
    aborts with a clear error instead of silently orphaning a live table —
    this needs a human decision (transfer the order first), not an
    automatic one. Not expected to trigger on any pre-launch database, but
    written defensively rather than assumed safe.

Schema: drops `dining_venue_tables.outlet_id` (column + FK + its index),
adds `UniqueConstraint(branch_id, table_number)` — table numbers must now be
unique per branch, not per outlet.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9b4e1a2c7f30'
down_revision: Union[str, None] = 'd2b4a1c3f7e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE_STATUSES = ("held", "open", "in_kitchen", "served")


def upgrade() -> None:
    bind = op.get_bind()

    branches_with_multiple_outlets = bind.execute(sa.text("""
        SELECT branch_id FROM dining_venue_tables
        GROUP BY branch_id
        HAVING COUNT(DISTINCT outlet_id) > 1
    """)).scalars().all()

    for branch_id in branches_with_multiple_outlets:
        counts = bind.execute(sa.text("""
            SELECT outlet_id, COUNT(*) AS n FROM dining_venue_tables
            WHERE branch_id = :branch_id
            GROUP BY outlet_id
            ORDER BY n DESC, outlet_id ASC
        """), {"branch_id": branch_id}).mappings().all()
        keeper_outlet_id = counts[0]["outlet_id"]
        losing_outlet_ids = [row["outlet_id"] for row in counts[1:]]

        for outlet_id in losing_outlet_ids:
            active_conflict = bind.execute(sa.text("""
                SELECT t.id, t.table_number, o.order_number
                FROM dining_venue_tables t
                JOIN dining_orders o ON o.table_id = t.id
                WHERE t.branch_id = :branch_id AND t.outlet_id = :outlet_id
                  AND o.status = ANY(:active_statuses)
            """), {
                "branch_id": branch_id, "outlet_id": outlet_id,
                "active_statuses": list(_ACTIVE_STATUSES),
            }).mappings().all()
            if active_conflict:
                details = ", ".join(
                    f"table {row['table_number']} (order {row['order_number']})"
                    for row in active_conflict
                )
                raise RuntimeError(
                    f"dining_tables_shared_across_outlets: branch {branch_id} has an "
                    f"ACTIVE order pinned to a table that would be deleted by "
                    f"consolidating onto outlet {keeper_outlet_id}: {details}. "
                    "Resolve manually (transfer the order to a kept table, or close it) "
                    "before re-running this migration."
                )
            bind.execute(sa.text("""
                DELETE FROM dining_venue_tables WHERE branch_id = :branch_id AND outlet_id = :outlet_id
            """), {"branch_id": branch_id, "outlet_id": outlet_id})

    op.drop_index('ix_dining_venue_tables_outlet_id', table_name='dining_venue_tables')
    op.drop_constraint('dining_venue_tables_outlet_id_fkey', 'dining_venue_tables', type_='foreignkey')
    op.drop_column('dining_venue_tables', 'outlet_id')
    op.create_unique_constraint(
        'uq_dining_table_branch_number', 'dining_venue_tables', ['branch_id', 'table_number'],
    )


def downgrade() -> None:
    # Best-effort structural reversal only — the consolidation above deletes
    # real rows (duplicate per-outlet tables), which is not reconstructable.
    # Re-adds outlet_id as nullable (no data to backfill it with) so the
    # column/FK/index shape matches pre-migration, without pretending the
    # deleted duplicate rows can come back.
    op.drop_constraint('uq_dining_table_branch_number', 'dining_venue_tables', type_='unique')
    op.add_column('dining_venue_tables', sa.Column('outlet_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'dining_venue_tables_outlet_id_fkey', 'dining_venue_tables', 'dining_outlets',
        ['outlet_id'], ['id'], ondelete='CASCADE',
    )
    op.create_index('ix_dining_venue_tables_outlet_id', 'dining_venue_tables', ['outlet_id'], unique=False)
