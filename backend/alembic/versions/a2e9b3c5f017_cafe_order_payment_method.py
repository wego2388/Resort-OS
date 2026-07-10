"""cafe_order_payment_method

Revision ID: a2e9b3c5f017
Revises: 8b1b5d6ced99
Create Date: 2026-07-08 23:00:00.000000

يضيف عمود payment_method (cash|card|wallet, nullable) على جدول cafe_orders.
كان فيه باج حقيقي: اختيار طريقة الدفع في CafePOSView.vue (كاش/كارت/محفظة)
كان UI-only بالكامل — مش بيتبعت للـ backend خالص، يعني إغلاق الوردية وتقارير
الإيرادات مكانوش بيفرقوا بين كاش وكارت في الكافيه. النتيجة الفعلية: الكاشير
مش قادر يتحقق من رصيد صندوقه بدقة لأن مفيش بيانات طريقة الدفع أصلاً.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a2e9b3c5f017'
down_revision: Union[str, None] = '8b1b5d6ced99'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'cafe_orders',
        sa.Column('payment_method', sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('cafe_orders', 'payment_method')
