"""add dining i18n columns and item sort_order

Revision ID: a7c3f0e9d5b2
Revises: 88d1c505a9dc
Create Date: 2026-08-03

منيو 2026 (راجع data/menu/) محتاج عمودين ماكانوش موجودين خالص على
DiningItem: sort_order (ترتيب العرض داخل الفئة — الأصناف كانت بترجع
بترتيب الـID بس) وname_ru/name_it/description_ar/description_ru/
description_it (ترجمات — dining_items عنده name_ar بس قبل كده).
dining_categories محتاج name_ru/name_it بالمثل. كل الأعمدة nullable —
صفر تغيير سلوك على البيانات الموجودة، صفر تأثير على أي endpoint حالي
(name_ru/name_it لسه مش مقروءين في أي schema عام، راجع docstring
DiningItem.name_ru في models.py).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "a7c3f0e9d5b2"
down_revision: str | None = "88d1c505a9dc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dining_items", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("dining_items", sa.Column("name_ru", sa.String(200), nullable=True))
    op.add_column("dining_items", sa.Column("name_it", sa.String(200), nullable=True))
    op.add_column("dining_items", sa.Column("description_ar", sa.Text(), nullable=True))
    op.add_column("dining_items", sa.Column("description_ru", sa.Text(), nullable=True))
    op.add_column("dining_items", sa.Column("description_it", sa.Text(), nullable=True))
    op.alter_column("dining_items", "sort_order", server_default=None)

    op.add_column("dining_categories", sa.Column("name_ru", sa.String(100), nullable=True))
    op.add_column("dining_categories", sa.Column("name_it", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("dining_categories", "name_it")
    op.drop_column("dining_categories", "name_ru")

    op.drop_column("dining_items", "description_it")
    op.drop_column("dining_items", "description_ru")
    op.drop_column("dining_items", "description_ar")
    op.drop_column("dining_items", "name_it")
    op.drop_column("dining_items", "name_ru")
    op.drop_column("dining_items", "sort_order")
