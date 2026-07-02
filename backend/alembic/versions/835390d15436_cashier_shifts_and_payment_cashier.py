"""cashier_shifts_and_payment_cashier

Revision ID: 835390d15436
Revises: 4288553c3a51
Create Date: 2026-07-01 05:12:05.550129
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '835390d15436'
down_revision: Union[str, None] = '4288553c3a51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('cashier_shifts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=False),
        sa.Column('cashier_id', sa.Integer(), nullable=False),
        sa.Column('opened_at', sa.DateTime(), nullable=False),
        sa.Column('opened_by', sa.Integer(), nullable=False),
        sa.Column('opening_float', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('closed_by', sa.Integer(), nullable=True),
        sa.Column('expected_cash', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('counted_cash', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('variance', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('notes', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_cashier_shifts_cashier_id'), 'cashier_shifts', ['cashier_id'], unique=False)
    op.create_index(op.f('ix_cashier_shifts_status'), 'cashier_shifts', ['status'], unique=False)

    op.add_column('payments', sa.Column('cashier_id', sa.Integer(), nullable=True))
    op.add_column('payments', sa.Column('shift_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_payments_cashier_id'), 'payments', ['cashier_id'], unique=False)
    op.create_index(op.f('ix_payments_shift_id'), 'payments', ['shift_id'], unique=False)
    op.create_foreign_key(
        'payments_shift_id_fkey', 'payments', 'cashier_shifts', ['shift_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('payments_shift_id_fkey', 'payments', type_='foreignkey')
    op.drop_index(op.f('ix_payments_shift_id'), table_name='payments')
    op.drop_index(op.f('ix_payments_cashier_id'), table_name='payments')
    op.drop_column('payments', 'shift_id')
    op.drop_column('payments', 'cashier_id')

    op.drop_index(op.f('ix_cashier_shifts_status'), table_name='cashier_shifts')
    op.drop_index(op.f('ix_cashier_shifts_cashier_id'), table_name='cashier_shifts')
    op.drop_table('cashier_shifts')
