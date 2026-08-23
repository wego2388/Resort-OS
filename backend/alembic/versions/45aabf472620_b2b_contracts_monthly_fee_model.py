"""b2b contracts monthly fee model

Revision ID: 45aabf472620
Revises: a63858c55efa
Create Date: 2026-08-22 21:58:46.590005

2026-08-20، طلب Mohamed صراحةً — استبدال نموذج تسعير عقود B2B الشاطئ بالكامل:
كان "سعر لكل ضيف × حصة يومية" (daily_quota/entry_price/towel_price)، بقى "مبلغ
شهري ثابت + حد أقصى استرشادي للدخول الشهري" (monthly_fee/monthly_guest_cap).
راجع app/modules/beach/models.py's B2BContract/B2BContractMonth docstrings
للتفاصيل الكاملة.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '45aabf472620'
down_revision: Union[str, None] = 'a63858c55efa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'b2b_contract_months',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('period_month', sa.Date(), nullable=False),
        sa.Column('guests_count', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('journal_entry_id', sa.Integer(), nullable=False),
        sa.Column('billed_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['contract_id'], ['b2b_contracts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('contract_id', 'period_month', name='uq_b2b_contract_month'),
    )

    # ── b2b_contracts: نموذج التسعير الجديد ────────────────────────────
    # nullable=True مؤقتًا للسماح بالـ backfill قبل ما نضيف NOT NULL —
    # الـ backfill بيحسب أفضل تقدير من القيم القديمة (سعر × حصة × 30 يوم)
    # كنقطة بداية معقولة للعقود الموجودة (اسمية/Demo فعليًا)، مش قيمة نهائية.
    op.add_column('b2b_contracts', sa.Column('monthly_fee', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('b2b_contracts', sa.Column('monthly_guest_cap', sa.Integer(), nullable=True))
    op.add_column('b2b_contracts', sa.Column('notified_quota_warning_period', sa.Date(), nullable=True))

    op.execute(
        """
        UPDATE b2b_contracts
        SET monthly_fee = COALESCE(entry_price, 0) * COALESCE(daily_quota, 0) * 30,
            monthly_guest_cap = COALESCE(daily_quota, 0) * 30
        """
    )

    op.alter_column('b2b_contracts', 'monthly_fee', nullable=False)
    op.alter_column('b2b_contracts', 'monthly_guest_cap', nullable=False)

    op.drop_column('b2b_contracts', 'towel_price')
    op.drop_column('b2b_contracts', 'daily_quota')
    op.drop_column('b2b_contracts', 'entry_price')

    # ── b2b_contract_days: بقى عدّاد يومي بحت، مفيش قيمة مالية لكل يوم ──
    op.drop_column('b2b_contract_days', 'total_amount')
    op.drop_column('b2b_contract_days', 'notified_quota_warning')


def downgrade() -> None:
    op.add_column('b2b_contract_days', sa.Column('notified_quota_warning', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('b2b_contract_days', sa.Column('total_amount', sa.Numeric(precision=10, scale=2), server_default=sa.text("'0'::numeric"), nullable=False))

    op.add_column('b2b_contracts', sa.Column('entry_price', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('b2b_contracts', sa.Column('daily_quota', sa.Integer(), server_default=sa.text('50'), nullable=False))
    op.add_column('b2b_contracts', sa.Column('towel_price', sa.Numeric(precision=10, scale=2), server_default=sa.text("'0'::numeric"), nullable=False))

    op.execute(
        """
        UPDATE b2b_contracts
        SET entry_price = CASE WHEN daily_quota > 0 THEN monthly_fee / (daily_quota * 30) ELSE monthly_fee END
        """
    )
    op.alter_column('b2b_contracts', 'entry_price', nullable=False)

    op.drop_column('b2b_contracts', 'notified_quota_warning_period')
    op.drop_column('b2b_contracts', 'monthly_guest_cap')
    op.drop_column('b2b_contracts', 'monthly_fee')

    op.drop_table('b2b_contract_months')
