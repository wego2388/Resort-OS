"""salary_advances_and_leave_balance_monthly

wagdy.md H-01 (salary_advances) + H-02 (advance_payments) + H-03
(leave_balance_monthly) — three new tables covering the employee
loan/advance/leave-accrual cluster that today only exists in Mohamed's
Excel sheets (كشف يناير: 60,066 ج سلف شهرية = 26% من المستحق). Also adds
advance_deduction to payroll_lines/payroll_runs so the deduction actually
flows through the payroll calculation (app.resort_os.hr_engine).

Revision ID: b3c7d9e1f2a4
Revises: a1b2c3d4e5f6
Create Date: 2026-07-12 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3c7d9e1f2a4'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'salary_advances',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id', ondelete='CASCADE'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('disbursed_date', sa.Date(), nullable=False),
        sa.Column('monthly_deduction_amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('remaining_balance', sa.Numeric(10, 2), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('notes', sa.String(length=500), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_salary_advances_employee_id', 'salary_advances', ['employee_id'])

    op.create_table(
        'advance_payments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id', ondelete='CASCADE'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('payment_date', sa.Date(), nullable=False),
        sa.Column('notes', sa.String(length=300), nullable=True),
        sa.Column('recorded_by', sa.Integer(), nullable=False),
        sa.Column('deducted', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('payroll_line_id', sa.Integer(), sa.ForeignKey('payroll_lines.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_advance_payments_employee_id', 'advance_payments', ['employee_id'])
    op.create_index('ix_advance_payments_payment_date', 'advance_payments', ['payment_date'])

    op.create_table(
        'leave_balance_monthly',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id', ondelete='CASCADE'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('period_year', sa.Integer(), nullable=False),
        sa.Column('period_month', sa.Integer(), nullable=False),
        sa.Column('opening_balance', sa.Numeric(6, 2), nullable=False, server_default='0'),
        sa.Column('accrued', sa.Numeric(6, 2), nullable=False, server_default='7.5'),
        sa.Column('consumed', sa.Numeric(6, 2), nullable=False, server_default='0'),
        sa.Column('closing_balance', sa.Numeric(6, 2), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('employee_id', 'period_year', 'period_month', name='uq_leave_monthly_employee_period'),
    )

    op.add_column(
        'payroll_lines',
        sa.Column('advance_deduction', sa.Numeric(10, 2), nullable=False, server_default='0'),
    )
    op.add_column(
        'payroll_runs',
        sa.Column('total_advance_deduction', sa.Numeric(12, 2), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('payroll_runs', 'total_advance_deduction')
    op.drop_column('payroll_lines', 'advance_deduction')
    op.drop_table('leave_balance_monthly')
    op.drop_index('ix_advance_payments_payment_date', table_name='advance_payments')
    op.drop_index('ix_advance_payments_employee_id', table_name='advance_payments')
    op.drop_table('advance_payments')
    op.drop_index('ix_salary_advances_employee_id', table_name='salary_advances')
    op.drop_table('salary_advances')
