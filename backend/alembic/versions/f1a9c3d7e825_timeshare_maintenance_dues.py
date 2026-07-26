"""timeshare_maintenance_dues

Revision ID: f1a9c3d7e825
Revises: 43493c94dc2c
Create Date: 2026-07-26 00:00:00.000000

نظام رسم الصيانة السنوية لعقود التايم شير — TimeshareContract كان عنده
بالفعل حقلَين خاملَين من استيراد بيانات قديم (maintenance_fee،
maintenance_increase) بدون أي استحقاق/تحصيل/إيراد فعلي مرتبط بيهم (نفس نمط
"الموديل موجود، الـ API صفر" المتكرر في المشروع). الجدول ده هو سجل الاستحقاق
السنوي الفعلي — مستحق واحد لكل (عقد، سنة)، بمبلغ لقطة (snapshot) من
maintenance_fee وقت التوليد.

قرار Mohamed: دورة سداد موحّدة (سنة تقويمية) لكل العقود، بلا أي backfill
لبيانات تاريخية (2022-2025) — الجدول بيبدأ فاضي، والتتبع يبدأ من 2026 وتلافي.

مكتوبة يدويًا (مش --autogenerate) — راجع CLAUDE.md §13 بخصوص الضوضاء غير
المتعلقة اللي autogenerate بيطلعها في المشروع ده، ونفس نمط 5fed6e302861/
23e4eca09fe0/8a78528e9403.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f1a9c3d7e825'
down_revision: Union[str, None] = '43493c94dc2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'timeshare_maintenance_dues',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('timeshare_contracts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('fee_year', sa.Integer(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('amount', sa.Numeric(14, 2), nullable=False),
        sa.Column('paid_amount', sa.Numeric(14, 2), nullable=False, server_default='0'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('payment_method', sa.String(30), nullable=True),
        sa.Column('receipt_number', sa.String(50), nullable=True),
        sa.Column('notes', sa.String(300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('contract_id', 'fee_year', name='uq_maintenance_due_contract_year'),
    )
    op.create_index('ix_timeshare_maintenance_dues_contract_id', 'timeshare_maintenance_dues', ['contract_id'])
    op.create_index('ix_timeshare_maintenance_dues_fee_year', 'timeshare_maintenance_dues', ['fee_year'])
    op.create_index('ix_timeshare_maintenance_dues_due_date', 'timeshare_maintenance_dues', ['due_date'])


def downgrade() -> None:
    op.drop_index('ix_timeshare_maintenance_dues_due_date', table_name='timeshare_maintenance_dues')
    op.drop_index('ix_timeshare_maintenance_dues_fee_year', table_name='timeshare_maintenance_dues')
    op.drop_index('ix_timeshare_maintenance_dues_contract_id', table_name='timeshare_maintenance_dues')
    op.drop_table('timeshare_maintenance_dues')
