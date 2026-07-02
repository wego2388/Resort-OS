"""add_work_order_schedule_id

Revision ID: 3fe20f98d77c
Revises: a396515de7a8
Create Date: 2026-07-02 18:38:01.691347
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3fe20f98d77c'
down_revision: Union[str, None] = 'a396515de7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'work_orders',
        sa.Column('schedule_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_work_orders_schedule_id', 'work_orders', 'preventive_schedules',
        ['schedule_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_work_orders_schedule_id', 'work_orders', type_='foreignkey')
    op.drop_column('work_orders', 'schedule_id')
