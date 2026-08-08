"""add personal credit accounts (Decision 0005)

Revision ID: c9d4e5f6a7b8
Revises: f8aa1f0fabba
Create Date: 2026-08-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "c9d4e5f6a7b8"
down_revision = "f8aa1f0fabba"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "beach_transactions",
        sa.Column("payment_method", sa.String(30), nullable=True),
    )
    op.create_table(
        "credit_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("holder_type", sa.String(10), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("employee_id", sa.Integer(), nullable=True),
        sa.Column("credit_limit", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("current_balance", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("opened_by", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["crm_customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["opened_by"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "(customer_id IS NOT NULL AND employee_id IS NULL) OR "
            "(customer_id IS NULL AND employee_id IS NOT NULL)",
            name="ck_credit_account_holder_xor",
        ),
        sa.CheckConstraint(
            "(holder_type = 'customer' AND customer_id IS NOT NULL) OR "
            "(holder_type = 'employee' AND employee_id IS NOT NULL)",
            name="ck_credit_account_holder_type_match",
        ),
        sa.CheckConstraint("credit_limit >= 0", name="ck_credit_account_limit_nonnegative"),
        sa.CheckConstraint("current_balance >= 0", name="ck_credit_account_balance_nonnegative"),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'closed')",
            name="ck_credit_account_status_valid",
        ),
        sa.UniqueConstraint("branch_id", "customer_id", name="uq_credit_account_branch_customer"),
        sa.UniqueConstraint("branch_id", "employee_id", name="uq_credit_account_branch_employee"),
    )
    op.create_index("ix_credit_accounts_branch_id", "credit_accounts", ["branch_id"])
    op.create_index("ix_credit_accounts_customer_id", "credit_accounts", ["customer_id"])
    op.create_index("ix_credit_accounts_employee_id", "credit_accounts", ["employee_id"])
    op.create_index("ix_credit_accounts_branch_status", "credit_accounts", ["branch_id", "status"])

    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("credit_account_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("txn_type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_delta", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_method", sa.String(10), nullable=True),
        sa.Column("ref_order_id", sa.Integer(), nullable=True),
        sa.Column("ref_beach_tx_id", sa.Integer(), nullable=True),
        sa.Column("reversed_txn_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.Integer(), nullable=False),
        sa.Column("journal_entry_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["credit_account_id"], ["credit_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ref_order_id"], ["dining_orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ref_beach_tx_id"], ["beach_transactions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reversed_txn_id"], ["credit_transactions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("amount > 0", name="ck_credit_txn_amount_positive"),
        sa.CheckConstraint("balance_delta <> 0", name="ck_credit_txn_delta_nonzero"),
        sa.CheckConstraint(
            "txn_type IN ('charge', 'payment', 'refund', 'reversal')",
            name="ck_credit_txn_type_valid",
        ),
        sa.CheckConstraint(
            "(txn_type = 'charge' AND balance_delta = amount) OR "
            "(txn_type = 'payment' AND balance_delta = -amount) OR "
            "(txn_type = 'refund' AND balance_delta = -amount) OR txn_type = 'reversal'",
            name="ck_credit_txn_delta_direction",
        ),
        sa.CheckConstraint(
            "(txn_type = 'charge' AND "
            " ((ref_order_id IS NOT NULL AND ref_beach_tx_id IS NULL) OR "
            "  (ref_order_id IS NULL AND ref_beach_tx_id IS NOT NULL)) AND "
            " reversed_txn_id IS NULL AND payment_method IS NULL) OR "
            "(txn_type = 'payment' AND ref_order_id IS NULL AND ref_beach_tx_id IS NULL "
            " AND reversed_txn_id IS NULL AND payment_method IN ('cash', 'bank')) OR "
            "(txn_type = 'refund' AND ref_order_id IS NULL AND ref_beach_tx_id IS NULL "
            " AND reversed_txn_id IS NOT NULL AND payment_method IS NULL) OR "
            "(txn_type = 'reversal' AND ref_order_id IS NULL AND ref_beach_tx_id IS NULL "
            " AND reversed_txn_id IS NOT NULL AND payment_method IS NULL)",
            name="ck_credit_txn_shape",
        ),
        sa.UniqueConstraint("ref_order_id", name="uq_credit_txn_order_charge"),
        sa.UniqueConstraint("ref_beach_tx_id", name="uq_credit_txn_beach_charge"),
        sa.UniqueConstraint("branch_id", "idempotency_key", name="uq_credit_txn_branch_idempotency"),
    )
    op.create_index("ix_credit_transactions_credit_account_id", "credit_transactions", ["credit_account_id"])
    op.create_index(
        "uq_credit_txn_reversal_once",
        "credit_transactions",
        ["reversed_txn_id"],
        unique=True,
        postgresql_where=sa.text("txn_type = 'reversal'"),
    )
    op.create_index("ix_credit_transactions_account_type", "credit_transactions", ["credit_account_id", "txn_type"])
    op.create_index("ix_credit_transactions_branch_created", "credit_transactions", ["branch_id", "created_at"])

    # 1200 is inventory in the existing chart. 1160 is deliberately dedicated
    # to personal receivables and attached to the 1000 Assets header.
    op.execute(sa.text("""
        INSERT INTO accounts
            (branch_id, code, name, name_ar, account_type, parent_id, is_active, created_at, updated_at)
        SELECT b.id, '1160', 'Personal credit receivables',
               'ذمم مدينة — حسابات آجلة شخصية', 'asset', parent.id, true, NOW(), NOW()
        FROM branches b
        LEFT JOIN accounts parent
          ON parent.branch_id = b.id AND parent.code = '1000'
        WHERE NOT EXISTS (
            SELECT 1 FROM accounts a WHERE a.branch_id = b.id AND a.code = '1160'
        )
    """))


def downgrade() -> None:
    op.drop_table("credit_transactions")
    op.drop_table("credit_accounts")
    op.drop_column("beach_transactions", "payment_method")
    # Keep GL 1160: a chart account may be referenced by posted journal history.
