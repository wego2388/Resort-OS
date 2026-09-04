"""custody, cash receipts, deferred expenses, void support

Revision ID: e58e17b2593d
Revises: 79d4d53e7109
Create Date: 2026-08-19 16:52:42.231150
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e58e17b2593d'
down_revision: Union[str, None] = '79d4d53e7109'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'custodies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=False),
        sa.Column('holder_name', sa.String(length=200), nullable=False),
        sa.Column('holder_employee_id', sa.Integer(), nullable=True),
        sa.Column('purpose', sa.String(length=300), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('disbursed_date', sa.Date(), nullable=False),
        sa.Column('source_account_id', sa.Integer(), nullable=False),
        sa.Column('custody_account_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('disbursement_entry_id', sa.Integer(), nullable=False),
        sa.Column('settlement_entry_id', sa.Integer(), nullable=True),
        sa.Column('returned_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('disbursed_by', sa.Integer(), nullable=False),
        sa.Column('settled_by', sa.Integer(), nullable=True),
        sa.Column('settled_at', sa.DateTime(), nullable=True),
        sa.Column('voided_at', sa.DateTime(), nullable=True),
        sa.Column('voided_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['custody_account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['disbursement_entry_id'], ['journal_entries.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['holder_employee_id'], ['employees.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['settlement_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_custodies_branch_id'), 'custodies', ['branch_id'], unique=False)

    op.create_table(
        'custody_settlement_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('custody_id', sa.Integer(), nullable=False),
        sa.Column('expense_account_id', sa.Integer(), nullable=False),
        sa.Column('cost_center_id', sa.Integer(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('description', sa.String(length=300), nullable=False),
        sa.Column('reference', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['cost_center_id'], ['cost_centers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['custody_id'], ['custodies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['expense_account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_custody_settlement_lines_custody_id'),
        'custody_settlement_lines',
        ['custody_id'],
        unique=False,
    )

    op.create_table(
        'cash_receipts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=False),
        sa.Column('receipt_date', sa.Date(), nullable=False),
        sa.Column('destination_account_id', sa.Integer(), nullable=False),
        sa.Column('source_account_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('description', sa.String(length=300), nullable=False),
        sa.Column('reference', sa.String(length=100), nullable=True),
        sa.Column('cost_center_id', sa.Integer(), nullable=True),
        sa.Column('journal_entry_id', sa.Integer(), nullable=False),
        sa.Column('recorded_by', sa.Integer(), nullable=False),
        sa.Column('voided_at', sa.DateTime(), nullable=True),
        sa.Column('voided_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['cost_center_id'], ['cost_centers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['destination_account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['source_account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_cash_receipts_branch_id'), 'cash_receipts', ['branch_id'], unique=False)

    op.create_table(
        'expense_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=False),
        sa.Column('expense_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('settlement_account_id', sa.Integer(), nullable=False),
        sa.Column('reference', sa.String(length=100), nullable=True),
        sa.Column('notes', sa.String(length=500), nullable=True),
        sa.Column('paid_at', sa.Date(), nullable=False),
        sa.Column('journal_entry_id', sa.Integer(), nullable=False),
        sa.Column('recorded_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['expense_id'], ['expenses.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['settlement_account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_expense_payments_branch_id'), 'expense_payments', ['branch_id'], unique=False)
    op.create_index(op.f('ix_expense_payments_expense_id'), 'expense_payments', ['expense_id'], unique=False)

    op.add_column(
        'expenses',
        sa.Column('payment_status', sa.String(length=20), nullable=False, server_default='paid'),
    )
    op.alter_column('expenses', 'payment_status', server_default=None)
    op.add_column(
        'expenses',
        sa.Column('amount_paid', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'),
    )
    op.alter_column('expenses', 'amount_paid', server_default=None)
    op.add_column('expenses', sa.Column('voided_at', sa.DateTime(), nullable=True))
    op.add_column('expenses', sa.Column('voided_by', sa.Integer(), nullable=True))

    op.add_column('supplier_payments', sa.Column('voided_at', sa.DateTime(), nullable=True))
    op.add_column('supplier_payments', sa.Column('voided_by', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('supplier_payments', 'voided_by')
    op.drop_column('supplier_payments', 'voided_at')

    op.drop_column('expenses', 'voided_by')
    op.drop_column('expenses', 'voided_at')
    op.drop_column('expenses', 'amount_paid')
    op.drop_column('expenses', 'payment_status')

    op.drop_index(op.f('ix_expense_payments_expense_id'), table_name='expense_payments')
    op.drop_index(op.f('ix_expense_payments_branch_id'), table_name='expense_payments')
    op.drop_table('expense_payments')

    op.drop_index(op.f('ix_cash_receipts_branch_id'), table_name='cash_receipts')
    op.drop_table('cash_receipts')

    op.drop_index(op.f('ix_custody_settlement_lines_custody_id'), table_name='custody_settlement_lines')
    op.drop_table('custody_settlement_lines')

    op.drop_index(op.f('ix_custodies_branch_id'), table_name='custodies')
    op.drop_table('custodies')
