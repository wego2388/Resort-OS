"""add name_ar snapshot to dining order items and extras

Revision ID: f1e6c8b4a3d7
Revises: a7c3f0e9d5b2
Create Date: 2026-08-03

الضيف ممكن يطلب بأي لغة من الأربعة (ar/en/ru/it، راجع migration
a7c3f0e9d5b2)، لكن نظام الموظفين (KDS/POS) عربي/إنجليزي بس عمدًا.
dining_order_items.name كان بيسجّل الإنجليزي بس وقت إنشاء البند — لو
الموظف حوّل شاشته عربي، اسم الصنف على أي طلب مُقدَّم فعلاً كان يفضل
إنجليزي (عكس باقي الشاشة). نفس المشكلة بالظبط على dining_order_item_
extras.extra_name. الأعمدة دي nullable — بنود قديمة قبل الـmigration
تفضل من غير نسخة عربية (تتظهر بالإنجليزي fallback، صفر كسر).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "f1e6c8b4a3d7"
down_revision: str | None = "a7c3f0e9d5b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dining_order_items", sa.Column("name_ar", sa.String(200), nullable=True))
    op.add_column("dining_order_item_extras", sa.Column("extra_name_ar", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("dining_order_item_extras", "extra_name_ar")
    op.drop_column("dining_order_items", "name_ar")
