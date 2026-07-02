"""add_cashier_shift_cash_counts

Revision ID: a396515de7a8
Revises: a4a04bc8c4c4
Create Date: 2026-07-02 17:40:26.369089
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a396515de7a8'
down_revision: Union[str, None] = 'a4a04bc8c4c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cashier_shift_cash_counts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shift_id', sa.Integer(), nullable=False),
        sa.Column('denomination', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('subtotal', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['shift_id'], ['cashier_shifts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_cashier_shift_cash_counts_shift_id'),
        'cashier_shift_cash_counts', ['shift_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_cashier_shift_cash_counts_shift_id'), table_name='cashier_shift_cash_counts')
    op.drop_table('cashier_shift_cash_counts')
