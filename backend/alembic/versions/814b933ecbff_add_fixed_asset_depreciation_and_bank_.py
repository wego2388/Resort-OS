"""add fixed-asset depreciation and bank reconciliation

Revision ID: 814b933ecbff
Revises: fix_ts_pms_analytics
Create Date: 2026-07-04 03:22:05.935019

NOTE: hand-pruned after --autogenerate. The raw autogenerate diff also
picked up a bunch of pre-existing drift unrelated to this change (index
naming-convention differences and FK ondelete differences on audit_logs/
notifications/settings/attendance_records/beach_inventory/etc. tables) —
that drift predates this migration and touching it here would risk
silently changing ON DELETE behavior on unrelated tables. Only the actual
new depreciation + bank-reconciliation objects are kept below.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '814b933ecbff'
down_revision: Union[str, None] = 'fix_ts_pms_analytics'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'asset_depreciation_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('accumulated_after', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('journal_entry_id', sa.Integer(), nullable=True),
        sa.Column('posted_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_id', 'year', 'month', name='uq_depreciation_asset_period'),
    )
    op.create_index(
        op.f('ix_asset_depreciation_entries_asset_id'),
        'asset_depreciation_entries', ['asset_id'], unique=False,
    )

    op.create_table(
        'bank_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=False),
        sa.Column('bank_name', sa.String(length=150), nullable=False),
        sa.Column('account_name', sa.String(length=200), nullable=False),
        sa.Column('account_number', sa.String(length=50), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('gl_account_id', sa.Integer(), nullable=True),
        sa.Column('opening_balance', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['gl_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('branch_id', 'account_number', name='uq_bank_account_branch_number'),
    )

    op.create_table(
        'bank_statement_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=False),
        sa.Column('line_date', sa.Date(), nullable=False),
        sa.Column('description', sa.String(length=300), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('external_reference', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('matched_payment_id', sa.Integer(), nullable=True),
        sa.Column('matched_at', sa.DateTime(), nullable=True),
        sa.Column('matched_by', sa.Integer(), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['matched_payment_id'], ['payments.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_bank_statement_lines_bank_account_id'),
        'bank_statement_lines', ['bank_account_id'], unique=False,
    )
    op.create_index(
        op.f('ix_bank_statement_lines_line_date'),
        'bank_statement_lines', ['line_date'], unique=False,
    )
    op.create_index(
        op.f('ix_bank_statement_lines_status'),
        'bank_statement_lines', ['status'], unique=False,
    )

    op.add_column('assets', sa.Column('purchase_cost', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('assets', sa.Column('salvage_value', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'))
    op.add_column('assets', sa.Column('useful_life_years', sa.Integer(), nullable=True))
    op.add_column('assets', sa.Column('depreciation_method', sa.String(length=20), nullable=False, server_default='straight_line'))
    op.add_column('assets', sa.Column('depreciation_start_date', sa.Date(), nullable=True))
    op.add_column('assets', sa.Column('accumulated_depreciation', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('assets', 'accumulated_depreciation')
    op.drop_column('assets', 'depreciation_start_date')
    op.drop_column('assets', 'depreciation_method')
    op.drop_column('assets', 'useful_life_years')
    op.drop_column('assets', 'salvage_value')
    op.drop_column('assets', 'purchase_cost')

    op.drop_index(op.f('ix_bank_statement_lines_status'), table_name='bank_statement_lines')
    op.drop_index(op.f('ix_bank_statement_lines_line_date'), table_name='bank_statement_lines')
    op.drop_index(op.f('ix_bank_statement_lines_bank_account_id'), table_name='bank_statement_lines')
    op.drop_table('bank_statement_lines')

    op.drop_table('bank_accounts')

    op.drop_index(op.f('ix_asset_depreciation_entries_asset_id'), table_name='asset_depreciation_entries')
    op.drop_table('asset_depreciation_entries')
