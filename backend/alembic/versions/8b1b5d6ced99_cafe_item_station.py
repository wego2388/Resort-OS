"""cafe_item_station

Revision ID: 8b1b5d6ced99
Revises: 7b209880c396
Create Date: 2026-07-08 04:58:43.713163

باج حقيقي اتصلح: cafe_items ماكانش عنده أي عمود "station" (عكس menu_items
اللي عنده station من زمان لتوجيه الـ KDS تلقائيًا). النتيجة كانت إن كل تذكرة
كافيه بتتوجّه لمحطة "bar" ثابتة في كود cafe.services.update_order_status —
يعني أي صنف كافيه محتاج مطبخ حقيقي (مش مجرد مشروب) عمره ما كان بيوصل لشاشة
kds/kitchen خالص، وشاشة kds/bar كانت بتزدحم بأصناف مش بارية أصلاً.

server_default='bar' عشان الأعمدة الموجودة فعليًا (لو الجدول متزروع بالفعل)
تاخد قيمة افتراضية معقولة فورًا — أغلب أصناف الكافيه الحقيقية (مشروبات) فعلاً
"bar"، فده مش تخمين عشوائي.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8b1b5d6ced99'
down_revision: Union[str, None] = '7b209880c396'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'cafe_items',
        sa.Column('station', sa.String(length=50), nullable=False, server_default='bar'),
    )


def downgrade() -> None:
    op.drop_column('cafe_items', 'station')
