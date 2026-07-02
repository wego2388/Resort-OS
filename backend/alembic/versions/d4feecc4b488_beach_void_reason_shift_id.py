"""beach_void_reason_shift_id

Revision ID: d4feecc4b488
Revises: 446fef6272eb
Create Date: 2026-07-02 13:20:09.186368
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd4feecc4b488'
down_revision: Union[str, None] = '446fef6272eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('beach_transactions', sa.Column('voided_reason', sa.String(length=200), nullable=True))
    op.add_column('beach_transactions', sa.Column('shift_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_beach_transactions_shift_id'), 'beach_transactions', ['shift_id'], unique=False)
    op.create_foreign_key(
        'fk_beach_transactions_shift_id_cashier_shifts',
        'beach_transactions', 'cashier_shifts', ['shift_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_beach_transactions_shift_id_cashier_shifts', 'beach_transactions', type_='foreignkey')
    op.drop_index(op.f('ix_beach_transactions_shift_id'), table_name='beach_transactions')
    op.drop_column('beach_transactions', 'shift_id')
    op.drop_column('beach_transactions', 'voided_reason')
