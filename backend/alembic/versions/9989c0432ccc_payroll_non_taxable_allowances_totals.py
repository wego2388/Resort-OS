"""payroll_non_taxable_allowances_totals

Real accounting bug fix (found live via seeded payroll data on a real
Postgres check, 2026-07-17): hr_engine.calculate_employee_payroll computes
net_salary inclusive of non_taxable_allowances (transport/housing-type
allowances not subject to tax/social-insurance), so the "net salaries
payable" credit line in the aggregated payroll journal
(hr.services._post_payroll_journal) already includes them — but the debit
side (run.total_gross + run.total_holiday_bonus) never did, because
non_taxable_allowances was never aggregated onto PayrollRun/PayrollLine at
all (only gross_salary, which explicitly excludes it, was tracked). Every
approved payroll run with any employee holding a non-taxable allowance
posted a genuinely unbalanced journal entry (credit > debit by exactly the
allowance total) — confirmed live: a 500.00 EGP imbalance appeared in a
real balance-sheet check against seeded data before this fix.

Adds total_non_taxable_allowances (PayrollRun) and non_taxable_allowances
(PayrollLine), same pattern as the existing total_holiday_bonus/
holiday_bonus pair. hr.services._post_payroll_journal now includes the new
run-level total in its debit calculation.

Revision ID: 9989c0432ccc
Revises: 504f42d2c755
Create Date: 2026-07-17 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9989c0432ccc'
down_revision: Union[str, None] = '504f42d2c755'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'payroll_runs',
        sa.Column('total_non_taxable_allowances', sa.Numeric(12, 2), nullable=False, server_default='0'),
    )
    op.add_column(
        'payroll_lines',
        sa.Column('non_taxable_allowances', sa.Numeric(10, 2), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('payroll_lines', 'non_taxable_allowances')
    op.drop_column('payroll_runs', 'total_non_taxable_allowances')
