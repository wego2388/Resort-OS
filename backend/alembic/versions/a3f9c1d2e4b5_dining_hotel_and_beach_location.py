"""dining: b2b_contract_id + beach_location_id on dining_orders

Revision ID: a3f9c1d2e4b5
Revises: 52f4544e50d2
Create Date: 2026-08-07 03:57:00

فيتشرين:
١. b2b_contract_id على dining_orders — يربط طلب الدايننج بالفندق المتعاقد
   (b2b_contracts)، nullable لأن معظم الطلبات عادية بدون فندق.
٢. beach_location_id على dining_orders — يربط طلب الدايننج بموقع شاطئ
   (شمسية/برجولة)، nullable لأن معظم الطلبات من طاولات عادية.
كلا العمودين SET NULL عند حذف الفندق/الموقع — الطلبات التاريخية لا تتأثر.

Partial unique index لمنع طلبين نشطين على نفس الشمسية — نفس منطق
uq_active_order_per_table الموجود على table_id.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a3f9c1d2e4b5'
down_revision: Union[str, None] = '52f4544e50d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ١. ربط الطلب بالفندق المتعاقد
    op.add_column(
        'dining_orders',
        sa.Column(
            'b2b_contract_id',
            sa.Integer(),
            sa.ForeignKey('b2b_contracts.id', ondelete='SET NULL', name='fk_dining_orders_b2b_contract_id'),
            nullable=True,
        ),
    )
    op.create_index('ix_dining_orders_b2b_contract_id', 'dining_orders', ['b2b_contract_id'])

    # ٢. ربط الطلب بموقع شاطئ (شمسية/برجولة)
    op.add_column(
        'dining_orders',
        sa.Column(
            'beach_location_id',
            sa.Integer(),
            sa.ForeignKey('beach_locations.id', ondelete='SET NULL', name='fk_dining_orders_beach_location_id'),
            nullable=True,
        ),
    )
    op.create_index('ix_dining_orders_beach_location_id', 'dining_orders', ['beach_location_id'])

    # ٣. Partial unique index — طلب واحد نشط لكل موقع شاطئ
    #    نفس منطق uq_active_order_per_table على table_id بالظبط:
    #    الحالات النشطة فقط (held|open|in_kitchen|served)، NULL مستبعد.
    op.create_index(
        'uq_active_order_per_beach_location',
        'dining_orders',
        ['beach_location_id'],
        unique=True,
        postgresql_where=sa.text(
            "beach_location_id IS NOT NULL AND status IN "
            "('held','open','in_kitchen','served')"
        ),
        sqlite_where=sa.text(
            "beach_location_id IS NOT NULL AND status IN "
            "('held','open','in_kitchen','served')"
        ),
    )


def downgrade() -> None:
    op.drop_index('uq_active_order_per_beach_location', table_name='dining_orders')
    op.drop_index('ix_dining_orders_beach_location_id', table_name='dining_orders')
    op.drop_column('dining_orders', 'beach_location_id')
    op.drop_index('ix_dining_orders_b2b_contract_id', table_name='dining_orders')
    op.drop_column('dining_orders', 'b2b_contract_id')
