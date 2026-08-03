"""add name_ru name_it to dining tables

Revision ID: add_dining_i18n_ru_it
Revises: (paste the current head revision ID here before applying)
Create Date: 2026-08-02

PURPOSE
───────
يضيف حقلي name_ru و name_it إلى:
  - dining_categories
  - dining_items
  - dining_item_extras
  - dining_item_extra_groups
  - dining_item_variants

وكمان description_ar و description_ru و description_it لـ dining_items
(description الإنجليزي موجود بالفعل).

بعد تطبيق الـ migration:
  1. شغّل seed_menu_2026.py عشان تملى الـ name_ar و description_ar
     بالبيانات الجديدة.
  2. ابعت ملف menu_i18n_structure.json للمترجم (أو استخدم AI للترجمة)
     لملى name_ru و name_it.
  3. شغّل apply_translations من seed_menu_2026.py بعد ما الترجمات تتجهز.

HOW TO APPLY
────────────
  cp data/menu/migration_add_i18n_columns.py \\
     backend/alembic/versions/xxxx_add_dining_i18n_ru_it.py

  # عدّل Revises في السطر أعلاه للـ head الحالي:
  cd backend && .venv/bin/alembic heads
  # ثم طبّق:
  .venv/bin/alembic upgrade head

HOW TO ROLLBACK
───────────────
  .venv/bin/alembic downgrade -1
"""
from alembic import op
import sqlalchemy as sa

revision = "add_dining_i18n_ru_it"
down_revision = None   # ← غيّر ده للـ head الحالي قبل التطبيق
branch_labels = None
depends_on = None

_ITEM_TABLES = [
    "dining_categories",
    "dining_items",
    "dining_item_extras",
    "dining_item_extra_groups",
    "dining_item_variants",
]


def upgrade() -> None:
    # ── name_ru / name_it على كل جداول الـ menu ──────────────────────────
    for table in _ITEM_TABLES:
        op.add_column(table, sa.Column("name_ru", sa.String(200), nullable=True))
        op.add_column(table, sa.Column("name_it", sa.String(200), nullable=True))

    # ── description_ar / _ru / _it على dining_items فقط ─────────────────
    # (description الإنجليزي موجود بالفعل كـ Text column)
    for lang_suffix in ("ar", "ru", "it"):
        op.add_column(
            "dining_items",
            sa.Column(f"description_{lang_suffix}", sa.Text, nullable=True),
        )


def downgrade() -> None:
    for lang_suffix in ("it", "ru", "ar"):
        op.drop_column("dining_items", f"description_{lang_suffix}")

    for table in reversed(_ITEM_TABLES):
        op.drop_column(table, "name_it")
        op.drop_column(table, "name_ru")
