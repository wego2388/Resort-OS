"""restaurant_extras_modifiers

Revision ID: 4288553c3a51
Revises: 67a5a4cf1db5
Create Date: 2026-07-01 05:05:34.197222
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '4288553c3a51'
down_revision: Union[str, None] = '67a5a4cf1db5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('menu_item_extra_groups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('menu_item_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('min_select', sa.Integer(), nullable=False),
    sa.Column('max_select', sa.Integer(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['menu_item_id'], ['menu_items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('menu_item_extras',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('group_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('price_addition', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('is_available', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['group_id'], ['menu_item_extra_groups.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('order_item_extras',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_item_id', sa.Integer(), nullable=False),
    sa.Column('extra_id', sa.Integer(), nullable=True),
    sa.Column('extra_name', sa.String(length=100), nullable=False),
    sa.Column('price_addition', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['extra_id'], ['menu_item_extras.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['order_item_id'], ['order_items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.add_column('menu_items', sa.Column('station', sa.String(length=50), nullable=False, server_default='hot'))


def downgrade() -> None:
    op.drop_column('menu_items', 'station')
    op.drop_table('order_item_extras')
    op.drop_table('menu_item_extras')
    op.drop_table('menu_item_extra_groups')
