"""add_beach_transaction_client_local_id

Revision ID: 94fb32749f9d
Revises: 5df68c547b10
Create Date: 2026-07-11 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '94fb32749f9d'
down_revision: Union[str, None] = '5df68c547b10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'beach_transactions',
        sa.Column('client_local_id', sa.String(length=60), nullable=True),
    )
    op.create_unique_constraint(
        'uq_beach_transactions_client_local_id', 'beach_transactions', ['client_local_id'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_beach_transactions_client_local_id', 'beach_transactions', type_='unique')
    op.drop_column('beach_transactions', 'client_local_id')
