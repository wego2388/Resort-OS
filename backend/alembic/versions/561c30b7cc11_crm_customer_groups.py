"""crm_customer_groups

Revision ID: 561c30b7cc11
Revises: 8a78528e9403
Create Date: 2026-07-13 00:00:00.000000

Batch 2 من طلب Mohamed: مجموعات عملاء بخصم دائم ثابت (standing discount) —
مختلفة تمامًا عن finance.conditional_discounts (شروط/حالات مؤقتة زي Happy
Hour). يضيف:

1. crm_customer_groups (branch_id, name, name_ar, discount_percentage,
   is_active).
2. crm_customers.customer_group_id (FK nullable — عميل من غير مجموعة
   افتراضيًا).
3. beach_transactions.discount_amount (Numeric، افتراضي صفر) — عمود جديد
   لتسجيل قيمة خصم مجموعة العميل على معاملة الشاطئ (راجع
   beach.services.sell_ticket)، منفصل عن total_amount اللي بقى صافي بعد
   الخصم من دلوقتي (كان يساوي unit_price × quantity قبل كده دايمًا).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '561c30b7cc11'
down_revision: Union[str, None] = '8a78528e9403'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'crm_customer_groups',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('name_ar', sa.String(100), nullable=True),
        sa.Column('discount_percentage', sa.Numeric(5, 2), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_crm_customer_groups_branch_id', 'crm_customer_groups', ['branch_id'])

    op.add_column(
        'crm_customers',
        sa.Column('customer_group_id', sa.Integer(),
                  sa.ForeignKey('crm_customer_groups.id', ondelete='SET NULL'), nullable=True),
    )
    op.create_index('ix_crm_customers_customer_group_id', 'crm_customers', ['customer_group_id'])

    op.add_column(
        'beach_transactions',
        sa.Column('discount_amount', sa.Numeric(10, 2), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('beach_transactions', 'discount_amount')
    op.drop_index('ix_crm_customers_customer_group_id', table_name='crm_customers')
    op.drop_column('crm_customers', 'customer_group_id')
    op.drop_index('ix_crm_customer_groups_branch_id', table_name='crm_customer_groups')
    op.drop_table('crm_customer_groups')
