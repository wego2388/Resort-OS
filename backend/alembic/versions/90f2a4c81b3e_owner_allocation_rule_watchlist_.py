"""owner_allocation_rule_watchlist_unique_constraints

Security review finding (2026-08-11), Decision 0004 §Isolation model:

  1. owner_allocation_rules had no DB-level constraint on (branch_id,
     version) — crud.create_allocation_rule_draft computed
     MAX(version) + 1 with no locking, a real race between two concurrent
     draft-creation requests for the same branch. FOR UPDATE locking was
     added to the create path (defense #1); this unique constraint is
     defense #2 for the case where no existing row exists yet to lock.

  2. owner_watchlist's uniqueness (owner_user_id, metric_key) did not
     include branch_id — would incorrectly block pinning the same metric
     in two different branches for the same owner account.

Revision ID: 90f2a4c81b3e
Revises: b7c8d9e0f1a2
Create Date: 2026-08-11
"""
from __future__ import annotations

from alembic import op

# revision identifiers
revision = "90f2a4c81b3e"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_owner_watchlist_user_metric", "owner_watchlist", type_="unique")
    op.create_unique_constraint(
        "uq_owner_watchlist_user_branch_metric",
        "owner_watchlist",
        ["owner_user_id", "branch_id", "metric_key"],
    )
    op.create_unique_constraint(
        "uq_owner_allocation_rule_branch_version",
        "owner_allocation_rules",
        ["branch_id", "version"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_owner_allocation_rule_branch_version", "owner_allocation_rules", type_="unique")
    op.drop_constraint("uq_owner_watchlist_user_branch_metric", "owner_watchlist", type_="unique")
    op.create_unique_constraint(
        "uq_owner_watchlist_user_metric",
        "owner_watchlist",
        ["owner_user_id", "metric_key"],
    )
