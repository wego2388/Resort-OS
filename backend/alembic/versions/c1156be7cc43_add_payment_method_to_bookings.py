"""add_payment_method_to_bookings

Revision ID: c1156be7cc43
Revises: 8c12d9e4f6a1
Create Date: 2026-07-24 21:15:54.469327

يضيف عمود payment_method لجدول bookings لتسجيل طريقة الدفع المتوقعة
عند الـ check-in (cash | card | bank_transfer).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1156be7cc43'
down_revision: Union[str, None] = '8c12d9e4f6a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'bookings',
        sa.Column('payment_method', sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('bookings', 'payment_method')
