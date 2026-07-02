"""cafe_full_parity

Revision ID: a97674556485
Revises: ef80fb31c6c4
Create Date: 2026-07-02 04:30:57.597309

Cafe module — full parity with restaurant: extras/modifiers
(cafe_menu_item_extra_groups → cafe_menu_item_extras → cafe_order_item_extras,
snapshot-on-order pattern), void-with-reason on cafe_order_items, inventory
linkage on cafe_items, and table occupancy tracking on cafe_tables.

⚠️ Hand-trimmed: `alembic revision --autogenerate` on this project always picks
up unrelated drift from concurrent work by other agents (index renames on
attendance/beach/notifications/audit_logs, NOT NULL tightening on unrelated
timestamp columns, FK re-ordering on module_states/settings). None of that
belongs to this migration — only the cafe_* changes below are intentional.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a97674556485'
down_revision: Union[str, None] = 'ef80fb31c6c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('cafe_menu_item_extra_groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cafe_item_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('name_ar', sa.String(length=100), nullable=True),
        sa.Column('min_select', sa.Integer(), nullable=False),
        sa.Column('max_select', sa.Integer(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['cafe_item_id'], ['cafe_items.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('cafe_menu_item_extras',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('name_ar', sa.String(length=100), nullable=True),
        sa.Column('price_addition', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('is_available', sa.Boolean(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['cafe_menu_item_extra_groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('cafe_order_item_extras',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_item_id', sa.Integer(), nullable=False),
        sa.Column('extra_id', sa.Integer(), nullable=True),
        sa.Column('extra_name', sa.String(length=100), nullable=False),
        sa.Column('price_addition', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['extra_id'], ['cafe_menu_item_extras.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['order_item_id'], ['cafe_order_items.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.add_column('cafe_items', sa.Column('linked_product_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'cafe_items', 'products', ['linked_product_id'], ['id'], ondelete='SET NULL')
    op.add_column('cafe_order_items', sa.Column('voided_reason', sa.String(length=200), nullable=True))
    op.add_column('cafe_order_items', sa.Column('voided_by', sa.Integer(), nullable=True))
    op.add_column('cafe_order_items', sa.Column('voided_at', sa.DateTime(), nullable=True))
    op.add_column('cafe_tables', sa.Column('occupied_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('cafe_tables', 'occupied_at')
    op.drop_column('cafe_order_items', 'voided_at')
    op.drop_column('cafe_order_items', 'voided_by')
    op.drop_column('cafe_order_items', 'voided_reason')
    op.drop_constraint(None, 'cafe_items', type_='foreignkey')
    op.drop_column('cafe_items', 'linked_product_id')
    op.drop_table('cafe_order_item_extras')
    op.drop_table('cafe_menu_item_extras')
    op.drop_table('cafe_menu_item_extra_groups')
