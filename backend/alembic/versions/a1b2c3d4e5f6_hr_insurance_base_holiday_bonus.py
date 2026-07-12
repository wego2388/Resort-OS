"""hr_insurance_base_holiday_bonus

wagdy.md H-04 (insurance_base_salary) + H-05 (holiday_bonus) — حقلان جديدان
على Employee بيدخلوا حساب الراتب فعليًا (راجع app.resort_os.hr_engine):
- insurance_base_salary: وعاء تأمينات منفصل عن basic_salary (NULL = استخدم
  basic_salary، سلوك قديم محفوظ لكل الموظفين الحاليين).
- holiday_bonus: مكافأة عيد ثابتة تُضاف للصافي تلقائيًا (افتراضي 0).
PayrollRun.total_holiday_bonus و PayrollLine.holiday_bonus بيسجّلوا أثر
المكافأة في كشوف الرواتب المحفوظة والقيد المحاسبي المجمّع.

Revision ID: a1b2c3d4e5f6
Revises: 94fb32749f9d
Create Date: 2026-07-12 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '94fb32749f9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'employees',
        sa.Column('insurance_base_salary', sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        'employees',
        sa.Column('holiday_bonus', sa.Numeric(10, 2), nullable=False, server_default='0'),
    )
    op.add_column(
        'payroll_runs',
        sa.Column('total_holiday_bonus', sa.Numeric(12, 2), nullable=False, server_default='0'),
    )
    op.add_column(
        'payroll_lines',
        sa.Column('holiday_bonus', sa.Numeric(10, 2), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('payroll_lines', 'holiday_bonus')
    op.drop_column('payroll_runs', 'total_holiday_bonus')
    op.drop_column('employees', 'holiday_bonus')
    op.drop_column('employees', 'insurance_base_salary')
