"""add order refunded_amount for post-payment refund flow

Revision ID: ef29bb120188
Revises: 814b933ecbff
Create Date: 2026-07-04 03:47:20.354761

NOTE: hand-pruned after --autogenerate — see 814b933ecbff for the same
pre-existing drift (unrelated index/FK naming differences) that autogenerate
also picks up here. Only the two new refunded_amount columns are kept.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ef29bb120188'
down_revision: Union[str, None] = '814b933ecbff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('refunded_amount', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0'))
    op.add_column('cafe_orders', sa.Column('refunded_amount', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('cafe_orders', 'refunded_amount')
    op.drop_column('orders', 'refunded_amount')
