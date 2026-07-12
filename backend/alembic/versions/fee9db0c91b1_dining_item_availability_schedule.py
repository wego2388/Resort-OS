"""dining_item_availability_schedule

Revision ID: fee9db0c91b1
Revises: f4a7c9b2d105
Create Date: 2026-07-13 00:00:00.000000

DINING_CUTOVER_PLAN.md Batch 1/2 — dining.DiningItem كان مفهوش
available_from_time/available_until_time خالص (wagdy.md P-03، اتضافوا
لـ menu_items/cafe_items يوم 2026-07-12 بعد ما موديول dining اتبنى). فجوة
تكافؤ حقيقية (نفس فئة KDS bump/table transfer) — لو اتسابت من غير حل، أي
صنف عنده نافذة تقديم محدودة (إفطار/غداء/عشاء) كان هيفقد القيد ده تمامًا
بعد حذف restaurant/cafe.

بتضيف الأعمدة + تنسخ (backfill، مش نقل) أي قيمة موجودة فعليًا في
menu_items/cafe_items لنظيرتها في dining_items عبر legacy_module/legacy_id
— نفس نمط النسخ في 0bd6f63e5446 بالظبط، idempotent (UPDATE بس، مفيش INSERT
هنا فمفيش داعي WHERE NOT EXISTS).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'fee9db0c91b1'
down_revision: Union[str, None] = 'f4a7c9b2d105'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('dining_items', sa.Column('available_from_time', sa.Time(), nullable=True))
    op.add_column('dining_items', sa.Column('available_until_time', sa.Time(), nullable=True))

    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE dining_items di
        SET available_from_time = mi.available_from_time,
            available_until_time = mi.available_until_time
        FROM menu_items mi
        WHERE di.legacy_module = 'restaurant' AND di.legacy_id = mi.id
          AND (mi.available_from_time IS NOT NULL OR mi.available_until_time IS NOT NULL)
    """))
    bind.execute(sa.text("""
        UPDATE dining_items di
        SET available_from_time = ci.available_from_time,
            available_until_time = ci.available_until_time
        FROM cafe_items ci
        WHERE di.legacy_module = 'cafe' AND di.legacy_id = ci.id
          AND (ci.available_from_time IS NOT NULL OR ci.available_until_time IS NOT NULL)
    """))


def downgrade() -> None:
    op.drop_column('dining_items', 'available_until_time')
    op.drop_column('dining_items', 'available_from_time')
