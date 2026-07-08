"""restaurant/cafe: add true variants (menu_item_variants, cafe_item_variants +
their own recipe/BOM lines) and order_items/cafe_order_items.variant_id

Revision ID: 7b209880c396
Revises: c4a7f0e2b619
Create Date: 2026-07-07 22:00:00.000000

باج تصميمي حقيقي اتكشف بمقارنة نظام "extras" (menu_item_extra_groups/
menu_item_extras) مع احتياج حقيقي: كافيه بيبيع نفس الصنف بأحجام مختلفة
(كابتشينو صغير/كبير) لها سعر *و* استهلاك مخزون مختلفين تمامًا، مش رسم
إضافي ثابت فوق وصفة واحدة. الفحص أثبت إن extras (MenuItemExtra.price_addition
بس، مفيش أي ربط recipe/BOM خالص) والوصفة نفسها (MenuItemRecipeLine مربوطة
بـ menu_item_id فقط) — الاتنين مالهمش أي طريقة يعبّروا عن سعر ووصفة مختلفين
حسب الاختيار. هذا الجدولين الجدد (+ نظيرهم في cafe) بيسدّوا الفجوة دي.

جدول وصفة منفصل لكل متغيّر (menu_item_variant_recipe_lines) عمدًا — مش عمود
variant_id nullable على menu_item_recipe_lines نفسه — عشان menu_item.recipe_lines
(المستخدمة في compute_menu_item_cost/_deduct_inventory_for_order/
get_food_cost_report، بُنيت واتأكد منها قبل المتغيّرات بيوم واحد بالظبط)
تفضل تعني بالضبط نفس الحاجة اللي كانت تعنيها من قبل، من غير أي فلترة إضافية
لازم تتضاف بأثر رجعي في كل نقطة استخدام موجودة.

order_items.variant_id / cafe_order_items.variant_id: ON DELETE SET NULL —
لو المتغيّر اتحذف بعدين، السجل التاريخي (name/unit_price بتاعت OrderItem،
snapshot أصلاً) بيفضل صحيح، بس المرجع الهيكلي بيتصفّر (زي نفس فلسفة
extra_id على order_item_extras).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '7b209880c396'
down_revision: Union[str, None] = 'd3f6a8c1b4e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── restaurant ───────────────────────────────────────────────────
    op.create_table('menu_item_variants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('menu_item_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('is_available', sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['menu_item_id'], ['menu_items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('menu_item_id', 'name', name='uq_menu_item_variant_name'),
    )
    op.create_index(op.f('ix_menu_item_variants_menu_item_id'), 'menu_item_variants', ['menu_item_id'])

    op.create_table('menu_item_variant_recipe_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('variant_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('quantity_per_unit', sa.Numeric(precision=12, scale=3), nullable=False),
    sa.Column('notes', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['variant_id'], ['menu_item_variants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('variant_id', 'product_id', name='uq_menu_item_variant_recipe_product'),
    )
    op.create_index(op.f('ix_menu_item_variant_recipe_lines_variant_id'), 'menu_item_variant_recipe_lines', ['variant_id'])
    op.create_index(op.f('ix_menu_item_variant_recipe_lines_product_id'), 'menu_item_variant_recipe_lines', ['product_id'])

    op.add_column('order_items', sa.Column('variant_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_order_items_variant_id', 'order_items', 'menu_item_variants',
                          ['variant_id'], ['id'], ondelete='SET NULL')
    op.create_index(op.f('ix_order_items_variant_id'), 'order_items', ['variant_id'])

    # ── cafe ─────────────────────────────────────────────────────────
    op.create_table('cafe_item_variants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cafe_item_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('is_available', sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['cafe_item_id'], ['cafe_items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cafe_item_id', 'name', name='uq_cafe_item_variant_name'),
    )
    op.create_index(op.f('ix_cafe_item_variants_cafe_item_id'), 'cafe_item_variants', ['cafe_item_id'])

    op.create_table('cafe_item_variant_recipe_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('variant_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('quantity_per_unit', sa.Numeric(precision=12, scale=3), nullable=False),
    sa.Column('notes', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['variant_id'], ['cafe_item_variants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('variant_id', 'product_id', name='uq_cafe_item_variant_recipe_product'),
    )
    op.create_index(op.f('ix_cafe_item_variant_recipe_lines_variant_id'), 'cafe_item_variant_recipe_lines', ['variant_id'])
    op.create_index(op.f('ix_cafe_item_variant_recipe_lines_product_id'), 'cafe_item_variant_recipe_lines', ['product_id'])

    op.add_column('cafe_order_items', sa.Column('variant_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_cafe_order_items_variant_id', 'cafe_order_items', 'cafe_item_variants',
                          ['variant_id'], ['id'], ondelete='SET NULL')
    op.create_index(op.f('ix_cafe_order_items_variant_id'), 'cafe_order_items', ['variant_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_cafe_order_items_variant_id'), table_name='cafe_order_items')
    op.drop_constraint('fk_cafe_order_items_variant_id', 'cafe_order_items', type_='foreignkey')
    op.drop_column('cafe_order_items', 'variant_id')

    op.drop_index(op.f('ix_cafe_item_variant_recipe_lines_product_id'), table_name='cafe_item_variant_recipe_lines')
    op.drop_index(op.f('ix_cafe_item_variant_recipe_lines_variant_id'), table_name='cafe_item_variant_recipe_lines')
    op.drop_table('cafe_item_variant_recipe_lines')

    op.drop_index(op.f('ix_cafe_item_variants_cafe_item_id'), table_name='cafe_item_variants')
    op.drop_table('cafe_item_variants')

    op.drop_index(op.f('ix_order_items_variant_id'), table_name='order_items')
    op.drop_constraint('fk_order_items_variant_id', 'order_items', type_='foreignkey')
    op.drop_column('order_items', 'variant_id')

    op.drop_index(op.f('ix_menu_item_variant_recipe_lines_product_id'), table_name='menu_item_variant_recipe_lines')
    op.drop_index(op.f('ix_menu_item_variant_recipe_lines_variant_id'), table_name='menu_item_variant_recipe_lines')
    op.drop_table('menu_item_variant_recipe_lines')

    op.drop_index(op.f('ix_menu_item_variants_menu_item_id'), table_name='menu_item_variants')
    op.drop_table('menu_item_variants')
