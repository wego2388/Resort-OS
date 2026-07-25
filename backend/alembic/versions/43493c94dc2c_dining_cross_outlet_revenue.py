"""pms_accrual_and_cross_outlet_revenue

Revision ID: a1b2c3d4e5f6
Revises: f4a6b8c0d2e5
Create Date: 2026-07-25 22:30:00.000000

تغييران محاسبيان مترابطان:

1. PMS — تصحيح دورة قيود الغرف:
   الوضع القديم: checkout_booking كان يُسجّل Dr.1100/Cr.4100 (يخلط
   تحصيل الكاش مع الاعتراف بالإيراد في لحظة واحدة).
   الوضع الجديد:
     - checkin_booking  → Dr.1150 / Cr.4100 (اعتراف بالإيراد عند الدخول)
     - Night Audit      → Dr.1150 / Cr.4100 (تكرار يومي للمراقبة — لا تغيير)
     - checkout_booking → Dr.1100 or 1110 / Cr.1150 (تسوية الذمة عند الخروج)
   لا migration مطلوب لهذا — هو تغيير سلوك في services.py فقط.

2. Dining — cross-outlet revenue allocation:
   إضافة outlet_id على dining_order_items لتتبع منفذ كل صنف.
   يُمكّن settle_order من توزيع الإيراد per-outlet بدل per-order.
   NULLable للتوافق مع الأصناف القديمة.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '43493c94dc2c'
down_revision: Union[str, None] = 'f4a6b8c0d2e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── dining_order_items: إضافة outlet_id ────────────────────────────
    op.add_column(
        'dining_order_items',
        sa.Column('outlet_id', sa.Integer(), sa.ForeignKey('dining_outlets.id', ondelete='SET NULL'), nullable=True),
    )
    op.create_index(
        'ix_dining_order_items_outlet_id',
        'dining_order_items',
        ['outlet_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_dining_order_items_outlet_id', table_name='dining_order_items')
    op.drop_column('dining_order_items', 'outlet_id')
