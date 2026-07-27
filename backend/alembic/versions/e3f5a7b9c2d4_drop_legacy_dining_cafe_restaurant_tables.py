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


def _table_exists(table_name: str) -> bool:
    """Return whether an exact base/partitioned table exists in this schema."""
    bind = op.get_bind()
    return bool(bind.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                  FROM pg_catalog.pg_class AS relation
                  JOIN pg_catalog.pg_namespace AS schema
                    ON schema.oid = relation.relnamespace
                 WHERE schema.nspname = current_schema()
                   AND relation.relname = :table_name
                   AND relation.relkind IN ('r', 'p')
            )
            """
        ),
        {"table_name": table_name},
    ).scalar_one())


def _column_exists(table_name: str, column_name: str) -> bool:
    """Return whether an exact, non-dropped column exists in this schema."""
    bind = op.get_bind()
    return bool(bind.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                  FROM pg_catalog.pg_attribute AS column_
                  JOIN pg_catalog.pg_class AS relation
                    ON relation.oid = column_.attrelid
                  JOIN pg_catalog.pg_namespace AS schema
                    ON schema.oid = relation.relnamespace
                 WHERE schema.nspname = current_schema()
                   AND relation.relname = :table_name
                   AND relation.relkind IN ('r', 'p')
                   AND column_.attname = :column_name
                   AND column_.attnum > 0
                   AND NOT column_.attisdropped
            )
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).scalar_one())


def _foreign_key_exists(table_name: str, constraint_name: str) -> bool:
    """Return whether an exact FK constraint exists on the exact table."""
    bind = op.get_bind()
    return bool(bind.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                  FROM pg_catalog.pg_constraint AS constraint_
                  JOIN pg_catalog.pg_class AS relation
                    ON relation.oid = constraint_.conrelid
                  JOIN pg_catalog.pg_namespace AS schema
                    ON schema.oid = relation.relnamespace
                 WHERE schema.nspname = current_schema()
                   AND relation.relname = :table_name
                   AND constraint_.conname = :constraint_name
                   AND constraint_.contype = 'f'
            )
            """
        ),
        {
            "table_name": table_name,
            "constraint_name": constraint_name,
        },
    ).scalar_one())


def _index_exists(table_name: str, index_name: str) -> bool:
    """Return whether an exact index belongs to the exact table."""
    bind = op.get_bind()
    return bool(bind.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                  FROM pg_catalog.pg_index AS index_
                  JOIN pg_catalog.pg_class AS index_relation
                    ON index_relation.oid = index_.indexrelid
                  JOIN pg_catalog.pg_class AS table_relation
                    ON table_relation.oid = index_.indrelid
                  JOIN pg_catalog.pg_namespace AS schema
                    ON schema.oid = table_relation.relnamespace
                 WHERE schema.nspname = current_schema()
                   AND table_relation.relname = :table_name
                   AND index_relation.relname = :index_name
            )
            """
        ),
        {"table_name": table_name, "index_name": index_name},
    ).scalar_one())


def upgrade() -> None:
    # ── 1. إزالة FK و column زائد في dining_order_items ────────────────
    # ``split_id`` and its FK existed as drift in the original deployment DB,
    # but no earlier migration creates either object.  Exact catalog guards
    # keep the historical cutover runnable from a clean migration chain while
    # preserving its cleanup on databases that do contain that legacy drift.
    if _foreign_key_exists('dining_order_items', 'fk_dining_order_items_split_id'):
        op.drop_constraint(
            'fk_dining_order_items_split_id',
            'dining_order_items',
            type_='foreignkey',
        )
    if _column_exists('dining_order_items', 'split_id'):
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
    # These two v1 tables were also deployment-only drift: the revision chain
    # never creates them.  Guard the exact tables/indexes, not arbitrary DROP
    # errors, so an unexpected dependency or schema mismatch still fails loud.
    if _table_exists('dining_order_payments'):
        if _index_exists(
            'dining_order_payments',
            'ix_dining_order_payments_order_id',
        ):
            op.drop_index(
                'ix_dining_order_payments_order_id',
                table_name='dining_order_payments',
            )
        if _index_exists(
            'dining_order_payments',
            'ix_dining_order_payments_split_id',
        ):
            op.drop_index(
                'ix_dining_order_payments_split_id',
                table_name='dining_order_payments',
            )
        op.drop_table('dining_order_payments')

    if _table_exists('dining_order_splits'):
        if _index_exists(
            'dining_order_splits',
            'ix_dining_order_splits_order_id',
        ):
            op.drop_index(
                'ix_dining_order_splits_order_id',
                table_name='dining_order_splits',
            )
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
