"""POS-03 add fx_rate to payments

Revision ID: 52f4544e50d2
Revises: 7b4d81dc08ee
Create Date: 2026-08-05 10:57:38.879051

POS-03: يضيف عمود fx_rate على جدول payments لتسجيل سعر الصرف وقت أي
دفعة كاش بعملة أجنبية. amount يفضل دايمًا EGP-equivalent للاتساق المحاسبي؛
المبلغ الأصلي بالعملة الأجنبية = amount / fx_rate.
server_default='1' يضمن الصفوف الموجودة مش محتاجة تعديل.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '52f4544e50d2'
down_revision: Union[str, None] = '7b4d81dc08ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'payments',
        sa.Column('fx_rate', sa.Numeric(precision=12, scale=6), server_default='1', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('payments', 'fx_rate')
