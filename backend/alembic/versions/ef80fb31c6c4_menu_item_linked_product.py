"""menu_item_linked_product

Revision ID: ef80fb31c6c4
Revises: analytics_util_cost
Create Date: 2026-07-02 02:47:17.626813

ربط اختياري MenuItem → inventory.Product (linked_product_id) — يسمح لدفع
طلب المطعم بخصم المخزون تلقائياً لو الصنف مربوط بمنتج مخزني (اختياري،
معظم الأصناف بدون ربط وده متوقع).

ملاحظة: alembic autogenerate التقط drift ضخم غير متعلق من موديولات تانية
(indexes/foreign keys/NOT NULL على جداول زي audit_logs, notifications,
settings, module_states, ...) — اتشال يدوياً وسيبنا بس التغيير المقصود.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'ef80fb31c6c4'
down_revision: Union[str, None] = 'analytics_util_cost'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('menu_items', sa.Column('linked_product_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'menu_items_linked_product_id_fkey', 'menu_items', 'products',
        ['linked_product_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('menu_items_linked_product_id_fkey', 'menu_items', type_='foreignkey')
    op.drop_column('menu_items', 'linked_product_id')
