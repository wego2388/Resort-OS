"""owner_module_phase2_and_pr_po_linkage

Decision 0004 — Phase 2:
  1. owner_watchlist        — OwnerWatchlist (pinned metrics / preferences)
  2. owner_allocation_rules — OwnerAllocationRule (cost-allocation drafts + published)
  3. purchase_orders.source_request_id — E-2 gap fix: link back to originating PR

Revision ID: f8aa1f0fabba
Revises: a3f9c1d2e4b5
Create Date: 2026-08-07
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "f8aa1f0fabba"
down_revision = "a3f9c1d2e4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. owner_watchlist ───────────────────────────────────────────────
    op.create_table(
        "owner_watchlist",
        sa.Column("id",             sa.Integer(), primary_key=True),
        sa.Column("owner_user_id",  sa.Integer(), nullable=False),
        sa.Column("metric_key",     sa.String(100), nullable=False),
        sa.Column("display_order",  sa.Integer(), nullable=False, server_default="0"),
        sa.Column("label_override", sa.String(200), nullable=True),
        sa.Column("branch_id",      sa.Integer(), nullable=False),
        sa.Column("created_at",     sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",     sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("owner_user_id", "metric_key", name="uq_owner_watchlist_user_metric"),
    )
    op.create_index("ix_owner_watchlist_owner_user_id", "owner_watchlist", ["owner_user_id"])
    op.create_index("ix_owner_watchlist_branch_id",     "owner_watchlist", ["branch_id"])

    # ── 2. owner_allocation_rules ────────────────────────────────────────
    op.create_table(
        "owner_allocation_rules",
        sa.Column("id",                   sa.Integer(), primary_key=True),
        sa.Column("branch_id",            sa.Integer(), nullable=False),
        sa.Column("version",              sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status",               sa.String(20), nullable=False, server_default="draft"),
        sa.Column("pct_rooms",            sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("pct_beach",            sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("pct_dining",           sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("pct_timeshare",        sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("effective_from",       sa.Date(), nullable=True),
        sa.Column("effective_to",         sa.Date(), nullable=True),
        sa.Column("published_by",         sa.Integer(), nullable=True),
        sa.Column("published_at",         sa.DateTime(), nullable=True),
        sa.Column("publish_step_up_ref",  sa.String(100), nullable=True),
        sa.Column("publish_reason",       sa.Text(), nullable=True),
        sa.Column("created_by",           sa.Integer(), nullable=False),
        sa.Column("notes",                sa.Text(), nullable=True),
        sa.Column("created_at",           sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",           sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_owner_allocation_rules_branch_id", "owner_allocation_rules", ["branch_id"])
    op.create_index("ix_owner_allocation_rules_status",    "owner_allocation_rules", ["status"])

    # ── 3. purchase_orders.source_request_id (E-2 gap fix) ──────────────
    # convert_to_purchase_order لم يكن يخزّن id طلب الشراء الأصلي على أمر
    # الشراء الناتج — يمنع حساب variance بين التقديري والفعلي لاحقاً.
    # nullable=True: لا backfill لأوامر الشراء القديمة (قرار موثّق في
    # kpi-contracts.md §E-2).
    op.add_column(
        "purchase_orders",
        sa.Column(
            "source_request_id",
            sa.Integer(),
            sa.ForeignKey("purchase_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_purchase_orders_source_request_id",
        "purchase_orders",
        ["source_request_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_purchase_orders_source_request_id", "purchase_orders")
    op.drop_column("purchase_orders", "source_request_id")

    op.drop_index("ix_owner_allocation_rules_status",    "owner_allocation_rules")
    op.drop_index("ix_owner_allocation_rules_branch_id", "owner_allocation_rules")
    op.drop_table("owner_allocation_rules")

    op.drop_index("ix_owner_watchlist_branch_id",     "owner_watchlist")
    op.drop_index("ix_owner_watchlist_owner_user_id", "owner_watchlist")
    op.drop_table("owner_watchlist")
