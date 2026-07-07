"""restaurant/cafe: add recipe/BOM lines (menu_item_recipe_lines, cafe_item_recipe_lines)

Revision ID: c1f4a8e02b7d
Revises: 7a434d2a9bca
Create Date: 2026-07-06 10:00:00.000000

⚠️ down_revision اتحدّث من b2d7f931a4e1 لـ 7a434d2a9bca أثناء دمج الفروع
(2026-07-07) — الهجرتين اتعملوا بالتوازي في worktrees منفصلة على نفس الأب
(b2d7f931a4e1)، فلما اتدمجوا مع بعض ظهر alembic heads اتنين. أُعيد ترتيبهم
تسلسليًا هنا (B2B credit-limit اتعمل قبل، فبيسبق هجرة الوصفة/BOM) — نفس
الأسلوب المتّبع فعلاً قبل كده في هذا المشروع لتعارض مشابه بين PMS/Finance.

باج حقيقي اتكشف بمقارنة مع نظام POS مطعم/كافيه حقيقي قديم: MenuItem/CafeItem
كان معاهم بس cost يدوي + ربط اختياري 1:1 بصنف مخزني واحد (linked_product_id)
— مفيش أي طريقة تعبّر إن "برجر" بيستهلك 150 جم لحم مفروم + رغيف + 30 جم جبنة
من المخزون. الجدولين دول بيمثّلوا وصفة/BOM حقيقية: كل سطر = كمية من
inventory.Product بتتستهلك لكل وحدة مباعة من الصنف. الكمية بوحدة الصنف
المخزني نفسها (Product.unit) — مفيش تحويل وحدات.

جدولين منفصلين (مش جدول مشترك) — نفس نمط الازدواجية الموجود فعلاً بين
menu_item_extra_groups/cafe_menu_item_extra_groups، مش تصميم جديد.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c1f4a8e02b7d'
down_revision: Union[str, None] = '7a434d2a9bca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('menu_item_recipe_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('menu_item_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('quantity_per_unit', sa.Numeric(precision=12, scale=3), nullable=False),
    sa.Column('notes', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['menu_item_id'], ['menu_items.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('menu_item_id', 'product_id', name='uq_menu_item_recipe_product'),
    )
    op.create_index(op.f('ix_menu_item_recipe_lines_menu_item_id'), 'menu_item_recipe_lines', ['menu_item_id'])
    op.create_index(op.f('ix_menu_item_recipe_lines_product_id'), 'menu_item_recipe_lines', ['product_id'])

    op.create_table('cafe_item_recipe_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cafe_item_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('quantity_per_unit', sa.Numeric(precision=12, scale=3), nullable=False),
    sa.Column('notes', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['cafe_item_id'], ['cafe_items.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cafe_item_id', 'product_id', name='uq_cafe_item_recipe_product'),
    )
    op.create_index(op.f('ix_cafe_item_recipe_lines_cafe_item_id'), 'cafe_item_recipe_lines', ['cafe_item_id'])
    op.create_index(op.f('ix_cafe_item_recipe_lines_product_id'), 'cafe_item_recipe_lines', ['product_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_cafe_item_recipe_lines_product_id'), table_name='cafe_item_recipe_lines')
    op.drop_index(op.f('ix_cafe_item_recipe_lines_cafe_item_id'), table_name='cafe_item_recipe_lines')
    op.drop_table('cafe_item_recipe_lines')

    op.drop_index(op.f('ix_menu_item_recipe_lines_product_id'), table_name='menu_item_recipe_lines')
    op.drop_index(op.f('ix_menu_item_recipe_lines_menu_item_id'), table_name='menu_item_recipe_lines')
    op.drop_table('menu_item_recipe_lines')
