"""drop_legacy_dining_cafe_restaurant_tables

Revision ID: e3f5a7b9c2d4
Revises: d2e4f6a8b1c3
Create Date: 2026-07-24 21:20:00.000000

يحذف الجداول الـ legacy الموجودة في DB بعد دمج dining:
  - cafe_* (11 جدول) — الكافيه اتندمج في dining
  - menu_* / order_* / orders (9 جداول) — المطعم القديم اتندمج في dining
  - dining_tables, dining_order_payments, dining_order_splits (3 جداول) — v1 قبل إعادة الهيكلة
  - kds_screens, kitchen_tickets (2 جدول) — استُبدلا بـ dining_kds_screens / dining_kitchen_tickets
  - column زائد: dining_order_items.split_id → FK محذوف

ترتيب الحذف: children أولاً ثم parents لتجنّب FK constraint errors.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e3f5a7b9c2d4'
down_revision: Union[str, None] = 'd2e4f6a8b1c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. إزالة FK و column زائد في dining_order_items ────────────────
    op.drop_constraint('fk_dining_order_items_split_id', 'dining_order_items', type_='foreignkey')
    op.drop_column('dining_order_items', 'split_id')

    # ── 2. جداول children أولاً ─────────────────────────────────────────

    # cafe children
    op.drop_table('cafe_order_item_extras')
    op.drop_table('cafe_order_items')
    op.drop_table('cafe_item_variant_recipe_lines')
    op.drop_table('cafe_item_recipe_lines')
    op.drop_table('cafe_menu_item_extras')
    op.drop_table('cafe_menu_item_extra_groups')
    op.drop_table('cafe_item_variants')
    op.drop_table('cafe_orders')
    op.drop_table('cafe_tables')
    op.drop_table('cafe_items')
    op.drop_table('cafe_categories')

    # restaurant / menu children
    op.drop_table('order_item_extras')
    op.drop_table('order_items')
    op.drop_table('menu_item_variant_recipe_lines')
    op.drop_table('menu_item_recipe_lines')
    op.drop_table('menu_item_extras')
    op.drop_table('menu_item_extra_groups')
    op.drop_table('menu_item_variants')
    op.drop_table('orders')
    op.drop_table('menu_items')
    op.drop_table('menu_categories')

    # dining v1 children
    op.drop_index('ix_dining_order_payments_order_id', table_name='dining_order_payments')
    op.drop_index('ix_dining_order_payments_split_id', table_name='dining_order_payments')
    op.drop_table('dining_order_payments')

    op.drop_index('ix_dining_order_splits_order_id', table_name='dining_order_splits')
    op.drop_table('dining_order_splits')

    op.drop_table('dining_tables')

    # standalone legacy
    op.drop_table('kitchen_tickets')
    op.drop_table('kds_screens')


def downgrade() -> None:
    # downgrade غير متاح — الجداول دي legacy وبياناتها موجودة في dining_*
    # لا تُعاد إلا بـ restore من backup
    raise NotImplementedError(
        "downgrade غير مدعوم — الجداول Legacy محذوفة نهائياً. "
        "استخدم backup لاستعادة البيانات لو احتجت."
    )
