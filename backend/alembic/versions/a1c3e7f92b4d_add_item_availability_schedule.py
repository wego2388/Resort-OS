"""add_item_availability_schedule

Revision ID: a1c3e7f92b4d
Revises: 94fb32749f9d
Create Date: 2026-07-12 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c3e7f92b4d'
down_revision: Union[str, None] = 'b3c7d9e1f2a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # wagdy.md P-03 — نافذة تقديم الصنف (إفطار/غداء/عشاء). NULL في أي عمود
    # يعني بدون قيد وقتي من هذه الجهة — نفس اتفاقية الحقول الاختيارية في
    # باقي المشروع. مطعم وكافيه معًا (نفس نمط CafeItem.station السابق).
    op.add_column('menu_items', sa.Column('available_from_time', sa.Time(), nullable=True))
    op.add_column('menu_items', sa.Column('available_until_time', sa.Time(), nullable=True))
    op.add_column('cafe_items', sa.Column('available_from_time', sa.Time(), nullable=True))
    op.add_column('cafe_items', sa.Column('available_until_time', sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column('cafe_items', 'available_until_time')
    op.drop_column('cafe_items', 'available_from_time')
    op.drop_column('menu_items', 'available_until_time')
    op.drop_column('menu_items', 'available_from_time')
