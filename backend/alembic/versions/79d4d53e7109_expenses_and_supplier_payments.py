"""Organized expense vouchers + supplier payable settlement

Revision ID: 79d4d53e7109
Revises: a7b3f2c8e9d1
Create Date: 2026-08-16

Additive, forward-only. Two independent, real accounting features Mohamed
requested explicitly (real vouchers for the accountant role), bundled in one
migration since they land in the same release:

  * ``expenses`` — an organized "expense voucher" (سند مصروفات): the
    accountant records a real GL expense (rent/utilities/maintenance/...)
    against a debit expense account (5xxx) and a credit settlement account
    (cash/bank), posting a real balanced journal entry
    (``services.record_expense``). Replaces the only prior option, which was
    either a raw manual journal entry (no category/traceability) or nothing.
  * ``purchase_orders.amount_paid`` / ``payment_status`` + new
    ``supplier_payments`` table — closes the accounts-payable loop.
    ``receive_purchase_order`` already posts Dr. Inventory (1200) /
    Cr. Suppliers-Payable (2200) on receipt, but there was no way to record
    that the resort later actually paid the supplier, so 2200's balance
    only ever grew. ``services.pay_purchase_order`` posts Dr. 2200 /
    Cr. settlement account per payment, and ``supplier_payments`` is the
    durable ledger of those settlements (one row per payment, not a
    denormalized running total only).

No backfill needed for either table — both are purely new, forward-only
activity; no existing rows can retroactively have an expense/payment record
invented for them.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "79d4d53e7109"
down_revision = "a7b3f2c8e9d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("expense_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("settlement_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("cost_center_id", sa.Integer(), sa.ForeignKey("cost_centers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("recorded_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_expenses_branch_date", "expenses", ["branch_id", "expense_date"])

    op.add_column(
        "purchase_orders",
        sa.Column("amount_paid", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "purchase_orders",
        sa.Column("payment_status", sa.String(20), nullable=False, server_default="unpaid"),
    )

    op.create_table(
        "supplier_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("settlement_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("paid_at", sa.Date(), nullable=False),
        sa.Column("journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("recorded_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_supplier_payments_supplier", "supplier_payments", ["supplier_id"])


def downgrade() -> None:
    op.drop_index("ix_supplier_payments_supplier", table_name="supplier_payments")
    op.drop_table("supplier_payments")
    op.drop_column("purchase_orders", "payment_status")
    op.drop_column("purchase_orders", "amount_paid")
    op.drop_index("ix_expenses_branch_date", table_name="expenses")
    op.drop_table("expenses")
