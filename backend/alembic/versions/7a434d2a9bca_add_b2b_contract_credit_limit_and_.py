"""add b2b contract credit limit and overdue dunning fields

عقود B2B (فنادق شريكة) هي علاقة ائتمانية متكررة حقيقية — الفندق بيبعت
ضيوفه للشاطئ وبيتحاسب دوريًا، مش كاش فوري. الأعمدة دي بتضيف ضبط ائتماني
حقيقي: حد أقصى اختياري للرصيد المستحق (credit_limit، nullable — مش كل
فندق شريك محتاج حد) + تتبّع تأخر السداد (payment_terms_days/last_settled_at/
is_overdue/notified_overdue). راجع app/modules/beach/models.py::B2BContract
للتفاصيل الكاملة.

⚠️ ملحوظة: autogenerate اكتشف كمان فرق pre-existing بين النماذج وتاريخ
الهجرات في فهرسة/أسماء foreign keys لجداول تانية (attendance_records،
audit_logs، beach_inventory/reservations/transactions، bookings،
conditional_discounts، folio_charges، folios، housekeeping_tasks،
notifications، orders، rooms، settings) — دي مش من هذا التعديل، اتشالت من
هنا عمدًا (نطاق منفصل تمامًا عن عقود B2B، ومحتاجة مراجعة منفصلة).

Revision ID: 7a434d2a9bca
Revises: b2d7f931a4e1
Create Date: 2026-07-06 22:30:34.076100
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7a434d2a9bca'
down_revision: Union[str, None] = 'b2d7f931a4e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('b2b_contracts', sa.Column('credit_limit', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('b2b_contracts', sa.Column(
        'payment_terms_days', sa.Integer(), nullable=False, server_default='30',
    ))
    op.add_column('b2b_contracts', sa.Column('last_settled_at', sa.Date(), nullable=True))
    op.add_column('b2b_contracts', sa.Column(
        'is_overdue', sa.Boolean(), nullable=False, server_default=sa.text('false'),
    ))
    op.add_column('b2b_contracts', sa.Column(
        'notified_overdue', sa.Boolean(), nullable=False, server_default=sa.text('false'),
    ))
    # الـ server_default كان بس عشان الأعمدة الموجودة تتملى وقت الـ ALTER —
    # الكود بيبعت القيمة صراحةً دايمًا (B2BContractCreate.payment_terms_days
    # ليها default=30 في Pydantic)، فمش محتاجينه بعد كده كـ default دائم.
    op.alter_column('b2b_contracts', 'payment_terms_days', server_default=None)
    op.alter_column('b2b_contracts', 'is_overdue', server_default=None)
    op.alter_column('b2b_contracts', 'notified_overdue', server_default=None)


def downgrade() -> None:
    op.drop_column('b2b_contracts', 'notified_overdue')
    op.drop_column('b2b_contracts', 'is_overdue')
    op.drop_column('b2b_contracts', 'last_settled_at')
    op.drop_column('b2b_contracts', 'payment_terms_days')
    op.drop_column('b2b_contracts', 'credit_limit')
