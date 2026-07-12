"""dining_extra_group_text_type

Revision ID: f4a7c9b2d105
Revises: 0bd6f63e5446
Create Date: 2026-07-12 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f4a7c9b2d105'
down_revision: Union[str, None] = '0bd6f63e5446'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # فجوة حقيقية اتكشفت بمقارنة نظام "Click" القديم اللي المنتجع ده كان
    # شغال بيه فعليًا — free-text extra-group type (مثال حقيقي: "كام سمكة؟"
    # كـ prompt نصي على الصنف) مش pick-list بس. راجع docstring
    # dining.models.DiningItemExtraGroup/DiningOrderItemExtra للتفاصيل
    # الكاملة. النطاق محصور بالكامل داخل dining/ الموديول الإضافي الجديد —
    # مفيش أي عمود مماثل مطلوب في restaurant/cafe (مش مصدر الحقيقة، مش
    # هيتلمسوا).
    op.add_column(
        'dining_item_extra_groups',
        sa.Column('group_type', sa.String(length=20), nullable=False, server_default='pick_list'),
    )
    op.add_column(
        'dining_order_item_extras',
        sa.Column('text_value', sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('dining_order_item_extras', 'text_value')
    op.drop_column('dining_item_extra_groups', 'group_type')
