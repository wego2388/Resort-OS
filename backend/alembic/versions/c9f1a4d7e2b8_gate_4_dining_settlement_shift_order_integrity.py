"""Gate 4 — dining settlement ledger, exactly-once payment, shift & order integrity

Revision ID: c9f1a4d7e2b8
Revises: b8f4d2a19c07
Create Date: 2026-07-19

Additive, forward-only. Adds:

  * ``dining_settlements`` — one exactly-once settlement row per paid dining
    order (Gate 4A). UNIQUE(order_id) enforces "one settlement per order";
    a partial UNIQUE(branch_id, idempotency_key) WHERE idempotency_key IS NOT
    NULL is the DB-level idempotency guard for pay/split retries.
  * ``payments.source`` / ``payments.original_payment_id`` — a generic source
    label and a reversal→original linkage (Gate 4A/4C), so the shift report
    and reconciliation can distinguish direct tenders from reversals without
    fragile reference-string parsing.
  * ``dining_orders.created_by`` / ``dining_order_items.added_by`` — real
    creator / item-actor attribution (Gate 4C), distinct from the mutable
    assigned-waiter and from voided_by.
  * ``uq_active_order_per_table`` — partial unique index: at most one active
    (held|open|in_kitchen|served) order per table (Gate 4C).
  * ``uq_open_shift_per_branch_cashier`` — partial unique index: at most one
    OPEN shift per (branch_id, cashier_id) (Gate 4B).

The two partial unique indexes are PostgreSQL-specific (``postgresql_where``);
SQLite silently gets a plain index (harmless — SQLite is only used by the
in-process unit suite, never for the real concurrency proofs). Both indexes
are created only after a read-only preflight confirmed the live data has no
duplicate active orders per table and no duplicate open shifts, so the
CREATE UNIQUE INDEX cannot fail on existing rows.

Rollback honesty: downgrade drops the settlement table, the two columns on
payments, the two actor columns, and both partial unique indexes. Once the
application has started recording settlements/idempotency keys, a downgrade
loses the exactly-once ledger and the actor attribution, and re-opens the
double-open-shift / double-active-order races — it is a maintenance-only
rollback, not a safe production revert after real settlements exist. No data
that predates this migration is destroyed by the upgrade.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "c9f1a4d7e2b8"
down_revision = "b8f4d2a19c07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) dining_settlements
    op.create_table(
        "dining_settlements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("dining_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=80), nullable=True),
        sa.Column("intent_hash", sa.String(length=64), nullable=False),
        sa.Column("total", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("cashier_id", sa.Integer(), nullable=True),
        sa.Column("shift_id", sa.Integer(), sa.ForeignKey("cashier_shifts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("order_id", name="uq_dining_settlement_order"),
    )
    op.create_index("ix_dining_settlements_cashier_id", "dining_settlements", ["cashier_id"])
    op.create_index("ix_dining_settlements_shift_id", "dining_settlements", ["shift_id"])
    op.create_index(
        "uq_dining_settlement_idem_key", "dining_settlements",
        ["branch_id", "idempotency_key"], unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # 2) payments.source / payments.original_payment_id
    op.add_column("payments", sa.Column("source", sa.String(length=30), nullable=True))
    op.add_column("payments", sa.Column("original_payment_id", sa.Integer(), nullable=True))
    op.create_index("ix_payments_source", "payments", ["source"])
    op.create_index("ix_payments_original_payment_id", "payments", ["original_payment_id"])

    # 3) dining_orders.created_by / dining_order_items.added_by
    op.add_column("dining_orders", sa.Column("created_by", sa.Integer(), nullable=True))
    op.add_column("dining_order_items", sa.Column("added_by", sa.Integer(), nullable=True))

    # 3b) cash_movements.direction (Gate 4B — explicit direction for corrections)
    op.add_column("cash_movements", sa.Column("direction", sa.String(length=10), nullable=True))

    # 4) partial unique indexes (one active order per table / one open shift).
    # Both PostgreSQL and SQLite support partial indexes; the WHERE clause is
    # essential — a non-partial unique index would forbid a table/cashier from
    # ever having a second (paid/closed, i.e. historical) row.
    _active_where = (
        "table_id IS NOT NULL AND status IN "
        "('held','open','in_kitchen','served')"
    )
    op.create_index(
        "uq_active_order_per_table", "dining_orders", ["table_id"], unique=True,
        postgresql_where=sa.text(_active_where), sqlite_where=sa.text(_active_where),
    )
    op.create_index(
        "uq_open_shift_per_branch_cashier", "cashier_shifts",
        ["branch_id", "cashier_id"], unique=True,
        postgresql_where=sa.text("status = 'open'"), sqlite_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_index("uq_open_shift_per_branch_cashier", table_name="cashier_shifts")
    op.drop_index("uq_active_order_per_table", table_name="dining_orders")

    op.drop_column("cash_movements", "direction")
    op.drop_column("dining_order_items", "added_by")
    op.drop_column("dining_orders", "created_by")

    op.drop_index("ix_payments_original_payment_id", table_name="payments")
    op.drop_index("ix_payments_source", table_name="payments")
    op.drop_column("payments", "original_payment_id")
    op.drop_column("payments", "source")

    op.drop_index("uq_dining_settlement_idem_key", table_name="dining_settlements")
    op.drop_index("ix_dining_settlements_shift_id", table_name="dining_settlements")
    op.drop_index("ix_dining_settlements_cashier_id", table_name="dining_settlements")
    op.drop_table("dining_settlements")
