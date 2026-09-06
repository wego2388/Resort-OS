"""
app/modules/owner/_services/hr_summary.py
Extracted from app/modules/owner/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.modules.owner.schemas import (
    EmployeeAttendanceSummary,
    EmployeePayrollSummary,
    HREmployeeRow,
    HRSummaryResponse,
)
from app.modules.owner._services._helpers import (
    _cairo_today,
)


# Phase 7c — HR Summary
# Decision 0004 §7c: full_name/position/department/hire_date/status +
# آخر payroll (net/gross/penalty/advance) + attendance aggregate.
# لا national_id، لا employee_si، لا monthly_tax، لا phone، لا email.
# ══════════════════════════════════════════════════════════════════════

def get_hr_summary(db: Session, branch_id: int) -> HRSummaryResponse:
    """
    قائمة الموظفين مع آخر PayrollLine لكل منهم + حضور الشهر الحالي.
    branch_id من الـ session فقط.
    """
    import calendar  # noqa: PLC0415
    from app.modules.hr.models import Employee, PayrollLine, PayrollRun, AttendanceRecord  # noqa: PLC0415

    today = _cairo_today()
    month_start = today.replace(day=1)
    _, days_in_month = calendar.monthrange(today.year, today.month)
    month_end = today.replace(day=days_in_month)

    employees = (
        db.query(Employee)
        .filter(Employee.branch_id == branch_id)
        .order_by(Employee.full_name)
        .all()
    )

    # آخر PayrollRun approved/closed للفرع
    latest_run = (
        db.query(PayrollRun)
        .filter(
            PayrollRun.branch_id == branch_id,
            PayrollRun.status.in_(["approved", "closed"]),
        )
        .order_by(PayrollRun.period_year.desc(), PayrollRun.period_month.desc())
        .first()
    )

    # PayrollLines للـ run الأخير — keyed by employee_id
    payroll_map: dict[int, PayrollLine] = {}
    if latest_run:
        lines = (
            db.query(PayrollLine)
            .filter(PayrollLine.payroll_run_id == latest_run.id)
            .all()
        )
        payroll_map = {line.employee_id: line for line in lines}

    # Attendance aggregate الشهر الحالي — keyed by employee_id
    att_records = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.branch_id == branch_id,
            AttendanceRecord.record_date >= month_start,
            AttendanceRecord.record_date <= month_end,
        )
        .all()
    )
    att_map: dict[int, list[AttendanceRecord]] = {}
    for rec in att_records:
        att_map.setdefault(rec.employee_id, []).append(rec)

    result_employees: list[HREmployeeRow] = []
    total_net = Decimal("0")
    active_count = 0
    on_leave_count = 0

    for emp in employees:
        if emp.status == "active":
            active_count += 1
        elif emp.status == "on_leave":
            on_leave_count += 1

        # Payroll summary
        payroll_summary: Optional[EmployeePayrollSummary] = None
        if emp.id in payroll_map and latest_run:
            pl = payroll_map[emp.id]
            total_net += pl.net_salary
            payroll_summary = EmployeePayrollSummary(
                payroll_run_id=pl.payroll_run_id,
                period_year=latest_run.period_year,
                period_month=latest_run.period_month,
                gross_salary=pl.gross_salary,
                net_salary=pl.net_salary,
                penalty_deduction=pl.penalty_deduction + pl.late_penalty_deduction,
                advance_deduction=pl.advance_deduction,
                # لا employee_si، لا monthly_tax — Decision 0004 §7c
            )

        # Attendance aggregate
        att_summary: Optional[EmployeeAttendanceSummary] = None
        emp_records = att_map.get(emp.id, [])
        if emp_records:
            present = sum(1 for r in emp_records if r.status == "present")
            absent  = sum(1 for r in emp_records if r.status == "absent")
            late    = sum(1 for r in emp_records if r.status == "late")
            leave   = sum(1 for r in emp_records if r.status == "leave")
            total_days = len(emp_records)
            att_summary = EmployeeAttendanceSummary(
                present_days=present,
                absent_days=absent,
                late_days=late,
                leave_days=leave,
                total_working_days=total_days,
            )

        result_employees.append(HREmployeeRow(
            employee_id=emp.id,
            full_name=emp.full_name,
            position=emp.position,
            department=emp.department,
            hire_date=emp.hire_date,
            status=emp.status,
            payroll=payroll_summary,
            attendance_this_month=att_summary,
            # لا national_id، لا phone، لا email، لا basic_salary
        ))

    return HRSummaryResponse(
        branch_id=branch_id,
        employees=result_employees,
        active_count=active_count,
        on_leave_count=on_leave_count,
        total_net_payroll=total_net,
        period_year=today.year,
        period_month=today.month,
        computed_at=datetime.utcnow(),
    )


# ══════════════════════════════════════════════════════════════════════
