"""dining_tables_grid_pos

Revision ID: c8f2d4b1e703
Revises: a2e9b3c5f017
Create Date: 2026-07-08 23:30:00.000000

يضيف إحداثيات الشبكة (grid_col, grid_row) على dining_tables — مطلوبة
لخريطة الطاولات الحية (TablesMapView.vue). القيم الافتراضية NULL عمداً:
الطاولات الموجودة مش هتظهر على الخريطة حتى يحدّد المدير مكانها من
صفحة الإعدادات (RestaurantSettingsView), بالضبط نفس نمط beach_locations.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c8f2d4b1e703'
down_revision: Union[str, None] = 'a2e9b3c5f017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('dining_tables', sa.Column('grid_row', sa.Integer(), nullable=True))
    op.add_column('dining_tables', sa.Column('grid_col', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('dining_tables', 'grid_col')
    op.drop_column('dining_tables', 'grid_row')
