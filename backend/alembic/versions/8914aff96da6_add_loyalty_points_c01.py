"""add_loyalty_points_c01

C-01 — برنامج نقاط الولاء للعملاء:
  - loyalty_programs   : إعدادات البرنامج (earn_rate, redeem_rate, ...)
  - loyalty_accounts   : رصيد كل عميل
  - loyalty_transactions: سجل كل عملية كسب/استرداد/تعديل

Revision ID: 8914aff96da6
Revises: 0921acaccd1f
Create Date: 2026-07-15 00:16:56.762361
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '8914aff96da6'
down_revision: Union[str, None] = '0921acaccd1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'loyalty_programs',
        sa.Column('id',             sa.Integer(),                             nullable=False),
        sa.Column('branch_id',      sa.Integer(),                             nullable=False),
        sa.Column('earn_rate',      sa.Numeric(precision=8, scale=2),         nullable=False, server_default='10'),
        sa.Column('redeem_rate',    sa.Numeric(precision=8, scale=4),         nullable=False, server_default='0.5'),
        sa.Column('min_redeem',     sa.Integer(),                             nullable=False, server_default='50'),
        sa.Column('max_redeem_pct', sa.Numeric(precision=5, scale=2),         nullable=False, server_default='50'),
        sa.Column('is_active',      sa.Boolean(),                             nullable=False, server_default=sa.text('true')),
        sa.Column('name',           sa.String(length=100),                    nullable=False, server_default='برنامج النقاط'),
        sa.Column('description',    sa.String(length=300),                    nullable=True),
        sa.Column('created_at',     sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at',     sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('branch_id', name='uq_loyalty_program_branch'),
    )
    op.create_index('ix_loyalty_programs_branch_id', 'loyalty_programs', ['branch_id'], unique=False)

    op.create_table(
        'loyalty_accounts',
        sa.Column('id',              sa.Integer(), nullable=False),
        sa.Column('program_id',      sa.Integer(), nullable=False),
        sa.Column('customer_id',     sa.Integer(), nullable=False),
        sa.Column('branch_id',       sa.Integer(), nullable=False),
        sa.Column('points',          sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_earned',    sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_redeemed',  sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tier',            sa.String(length=20), nullable=False, server_default='bronze'),
        sa.Column('is_frozen',       sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at',      sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at',      sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['branch_id'],   ['branches.id'],       ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_id'], ['crm_customers.id'],  ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['program_id'],  ['loyalty_programs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('program_id', 'customer_id', name='uq_loyalty_account_program_customer'),
    )
    op.create_index('ix_loyalty_accounts_branch_id',   'loyalty_accounts', ['branch_id'],   unique=False)
    op.create_index('ix_loyalty_accounts_customer_id', 'loyalty_accounts', ['customer_id'], unique=False)
    op.create_index('ix_loyalty_accounts_program_id',  'loyalty_accounts', ['program_id'],  unique=False)

    op.create_table(
        'loyalty_transactions',
        sa.Column('id',            sa.Integer(),          nullable=False),
        sa.Column('account_id',    sa.Integer(),          nullable=False),
        sa.Column('branch_id',     sa.Integer(),          nullable=False),
        sa.Column('txn_type',      sa.String(length=20),  nullable=False),
        sa.Column('points',        sa.Integer(),          nullable=False),
        sa.Column('balance_after', sa.Integer(),          nullable=False),
        sa.Column('source',        sa.String(length=30),  nullable=False, server_default='manual'),
        sa.Column('source_id',     sa.Integer(),          nullable=True),
        sa.Column('reference',     sa.String(length=100), nullable=True),
        sa.Column('notes',         sa.String(length=300), nullable=True),
        sa.Column('created_by',    sa.Integer(),          nullable=True),
        sa.Column('created_at',    sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at',    sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['loyalty_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['branch_id'],  ['branches.id'],         ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_loyalty_transactions_account_id', 'loyalty_transactions', ['account_id'], unique=False)
    op.create_index('ix_loyalty_transactions_branch_id',  'loyalty_transactions', ['branch_id'],  unique=False)


def downgrade() -> None:
    op.drop_index('ix_loyalty_transactions_branch_id',  table_name='loyalty_transactions')
    op.drop_index('ix_loyalty_transactions_account_id', table_name='loyalty_transactions')
    op.drop_table('loyalty_transactions')
    op.drop_index('ix_loyalty_accounts_program_id',  table_name='loyalty_accounts')
    op.drop_index('ix_loyalty_accounts_customer_id', table_name='loyalty_accounts')
    op.drop_index('ix_loyalty_accounts_branch_id',   table_name='loyalty_accounts')
    op.drop_table('loyalty_accounts')
    op.drop_index('ix_loyalty_programs_branch_id', table_name='loyalty_programs')
    op.drop_table('loyalty_programs')
