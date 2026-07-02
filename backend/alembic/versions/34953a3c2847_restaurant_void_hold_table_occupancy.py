"""restaurant_void_hold_table_occupancy

Revision ID: 34953a3c2847
Revises: 835390d15436
Create Date: 2026-07-01 06:19:17.559247
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '34953a3c2847'
down_revision: Union[str, None] = '835390d15436'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('order_items', sa.Column('voided_reason', sa.String(length=200), nullable=True))
    op.add_column('order_items', sa.Column('voided_by', sa.Integer(), nullable=True))
    op.add_column('order_items', sa.Column('voided_at', sa.DateTime(), nullable=True))
    op.add_column('dining_tables', sa.Column('occupied_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('dining_tables', 'occupied_at')
    op.drop_column('order_items', 'voided_at')
    op.drop_column('order_items', 'voided_by')
    op.drop_column('order_items', 'voided_reason')
