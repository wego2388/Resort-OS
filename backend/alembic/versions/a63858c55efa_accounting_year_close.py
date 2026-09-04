"""accounting year close

Revision ID: a63858c55efa
Revises: e58e17b2593d
Create Date: 2026-08-19 22:45:31.856086
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a63858c55efa'
down_revision: Union[str, None] = 'e58e17b2593d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'accounting_year_closes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('journal_entry_id', sa.Integer(), nullable=False),
        sa.Column('net_income', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('closed_by', sa.Integer(), nullable=False),
        sa.Column('closed_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('branch_id', 'year', name='uq_year_close_branch_year'),
    )
    op.create_index(
        op.f('ix_accounting_year_closes_branch_id'), 'accounting_year_closes', ['branch_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_accounting_year_closes_branch_id'), table_name='accounting_year_closes')
    op.drop_table('accounting_year_closes')
