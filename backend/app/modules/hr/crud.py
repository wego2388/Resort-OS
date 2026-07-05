"""app/modules/hr/crud.py — CRUD خالص"""
from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.modules.hr.models import (
    AttendanceRecord, Department, Employee, EmployeeAllowance,
    EmployeePenalty, LeaveBalance, LeaveRequest, LeaveType, PenaltyType,
    PayrollLine, PayrollRun, RotaAssignment, RotaTemplate, ShiftSwapRequest, Shift,
    SocialInsuranceConfig, TaxBracketConfig,
)
from app.modules.hr.schemas import (
    AttendanceRecordCreate, DepartmentCreate, EmployeeCreate, EmployeeUpdate,
    EmployeeAllowanceCreate, EmployeeAllowanceUpdate,
    EmployeePenaltyCreate, LeaveTypeCreate, PenaltyTypeCreate,
    PayrollRunCreate, RotaAssignmentCreate, RotaTemplateCreate, RotaTemplateUpdate,
    ShiftCreate, ShiftSwapRequestCreate,
    SocialInsuranceConfigCreate, TaxBracketConfigCreate,
)


# ── Employee ──────────────────────────────────────────────────────────

def get_employee(db: Session, employee_id: int) -> Optional[Employee]:
    return db.query(Employee).filter(Employee.id == employee_id).first()


def get_employee_by_code(db: Session, code: str) -> Optional[Employee]:
    return db.query(Employee).filter(Employee.employee_code == code).first()


def get_employee_by_user_id(db: Session, user_id: int) -> Optional[Employee]:
    return db.query(Employee).filter(Employee.user_id == user_id).first()


def list_employees(
    db: Session,
    branch_id: int,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Employee], int]:
    q = db.query(Employee).filter(Employee.branch_id == branch_id)
    if status:
        q = q.filter(Employee.status == status)
    total = q.count()
    items = q.order_by(Employee.full_name).offset(skip).limit(limit).all()
    return items, total


def create_employee(db: Session, data: EmployeeCreate) -> Employee:
    emp = Employee(**data.model_dump())
    db.add(emp)
    db.flush()
    return emp


def update_employee(db: Session, emp: Employee, data: EmployeeUpdate) -> Employee:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(emp, field, value)
    db.flush()
    return emp


# ── Config ────────────────────────────────────────────────────────────

def get_active_si_config(db: Session) -> Optional[SocialInsuranceConfig]:
    return (
        db.query(SocialInsuranceConfig)
        .filter(SocialInsuranceConfig.is_active.is_(True))
        .order_by(SocialInsuranceConfig.effective_from.desc())
        .first()
    )


def get_active_tax_brackets(db: Session) -> list[TaxBracketConfig]:
    return (
        db.query(TaxBracketConfig)
        .filter(TaxBracketConfig.is_active.is_(True))
        .order_by(TaxBracketConfig.lower_bound)
        .all()
    )


def create_si_config(db: Session, data: SocialInsuranceConfigCreate) -> SocialInsuranceConfig:
    obj = SocialInsuranceConfig(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def list_si_configs(db: Session) -> list[SocialInsuranceConfig]:
    return db.query(SocialInsuranceConfig).order_by(SocialInsuranceConfig.effective_from.desc()).all()


def create_tax_bracket(db: Session, data: TaxBracketConfigCreate) -> TaxBracketConfig:
    obj = TaxBracketConfig(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def list_tax_brackets(db: Session) -> list[TaxBracketConfig]:
    return db.query(TaxBracketConfig).order_by(TaxBracketConfig.effective_from.desc(), TaxBracketConfig.lower_bound).all()


def list_allowances_for_employee(
    db: Session, employee_id: int, active_only: bool = True
) -> list[EmployeeAllowance]:
    q = db.query(EmployeeAllowance).filter(EmployeeAllowance.employee_id == employee_id)
    if active_only:
        q = q.filter(EmployeeAllowance.is_active.is_(True))
    return q.all()


def create_allowance(db: Session, data: EmployeeAllowanceCreate) -> EmployeeAllowance:
    allowance = EmployeeAllowance(**data.model_dump())
    db.add(allowance)
    db.flush()
    return allowance


def get_allowance(db: Session, allowance_id: int) -> Optional[EmployeeAllowance]:
    return db.query(EmployeeAllowance).filter(EmployeeAllowance.id == allowance_id).first()


def update_allowance(
    db: Session, allowance: EmployeeAllowance, data: EmployeeAllowanceUpdate
) -> EmployeeAllowance:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(allowance, field, value)
    db.flush()
    return allowance


# ── PenaltyType ───────────────────────────────────────────────────────

def create_penalty_type(db: Session, data: PenaltyTypeCreate) -> PenaltyType:
    penalty_type = PenaltyType(**data.model_dump())
    db.add(penalty_type)
    db.flush()
    return penalty_type


def list_penalty_types(db: Session, branch_id: int) -> list[PenaltyType]:
    return (
        db.query(PenaltyType)
        .filter(PenaltyType.branch_id == branch_id)
        .order_by(PenaltyType.name)
        .all()
    )


# ── PayrollRun ────────────────────────────────────────────────────────

def get_payroll_run(db: Session, run_id: int) -> Optional[PayrollRun]:
    return db.query(PayrollRun).filter(PayrollRun.id == run_id).first()


def get_payroll_run_by_period(
    db: Session, branch_id: int, year: int, month: int
) -> Optional[PayrollRun]:
    return (
        db.query(PayrollRun)
        .filter(
            PayrollRun.branch_id == branch_id,
            PayrollRun.period_year == year,
            PayrollRun.period_month == month,
        )
        .first()
    )


def list_payroll_runs(
    db: Session, branch_id: int, skip: int = 0, limit: int = 24
) -> tuple[list[PayrollRun], int]:
    q = db.query(PayrollRun).filter(PayrollRun.branch_id == branch_id)
    total = q.count()
    items = q.order_by(PayrollRun.period_year.desc(), PayrollRun.period_month.desc()).offset(skip).limit(limit).all()
    return items, total


def create_payroll_run(db: Session, data: PayrollRunCreate) -> PayrollRun:
    run = PayrollRun(**data.model_dump(), status="draft")
    db.add(run)
    db.flush()
    return run


def create_payroll_line(db: Session, run_id: int, data: dict) -> PayrollLine:
    line = PayrollLine(payroll_run_id=run_id, **data)
    db.add(line)
    db.flush()
    return line


def list_lines_for_run(db: Session, run_id: int) -> list[PayrollLine]:
    return db.query(PayrollLine).filter(PayrollLine.payroll_run_id == run_id).all()


def list_payslips_for_employee(
    db: Session, employee_id: int, skip: int = 0, limit: int = 24,
) -> tuple[list[PayrollLine], int]:
    """قسائم راتب موظف معين — كشوف رواتب approved/paid فقط (مش draft، الأرقام
    مش نهائية لسه). run محمّل مسبقاً (joinedload) لتفادي N+1."""
    q = (
        db.query(PayrollLine)
        .join(PayrollRun, PayrollLine.payroll_run_id == PayrollRun.id)
        .options(joinedload(PayrollLine.run))
        .filter(PayrollLine.employee_id == employee_id, PayrollRun.status != "draft")
    )
    total = q.count()
    items = (
        q.order_by(PayrollRun.period_year.desc(), PayrollRun.period_month.desc())
        .offset(skip).limit(limit).all()
    )
    return items, total


# ── Attendance ────────────────────────────────────────────────────────

def get_attendance_for_date(db: Session, employee_id: int, record_date: date) -> Optional[AttendanceRecord]:
    return (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.record_date == record_date,
        )
        .first()
    )


def upsert_attendance(db: Session, data: AttendanceRecordCreate) -> AttendanceRecord:
    row = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == data.employee_id,
            AttendanceRecord.record_date == data.record_date,
        )
        .first()
    )
    if row:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
    else:
        row = AttendanceRecord(**data.model_dump())
        db.add(row)
    db.flush()
    return row


def list_attendance(
    db: Session,
    employee_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[AttendanceRecord], int]:
    q = db.query(AttendanceRecord)
    if employee_id:
        q = q.filter(AttendanceRecord.employee_id == employee_id)
    if branch_id:
        q = q.filter(AttendanceRecord.branch_id == branch_id)
    if date_from:
        q = q.filter(AttendanceRecord.record_date >= date_from)
    if date_to:
        q = q.filter(AttendanceRecord.record_date <= date_to)
    total = q.count()
    items = q.order_by(AttendanceRecord.record_date.desc()).offset(skip).limit(limit).all()
    return items, total


# ── LeaveBalance ──────────────────────────────────────────────────────

def get_leave_balance(db: Session, employee_id: int, year: int) -> Optional[LeaveBalance]:
    return (
        db.query(LeaveBalance)
        .filter(LeaveBalance.employee_id == employee_id, LeaveBalance.year == year)
        .first()
    )


def upsert_leave_balance(
    db: Session, employee_id: int, year: int, annual_entitled: int
) -> LeaveBalance:
    row = get_leave_balance(db, employee_id, year)
    if row:
        row.annual_entitled = annual_entitled
    else:
        row = LeaveBalance(
            employee_id=employee_id,
            year=year,
            annual_entitled=annual_entitled,
        )
        db.add(row)
    db.flush()
    return row


# ── Department ────────────────────────────────────────────────────────

def create_department(db: Session, data: DepartmentCreate) -> Department:
    dept = Department(**data.model_dump())
    db.add(dept)
    db.flush()
    return dept


def list_departments(db: Session, branch_id: int) -> list[Department]:
    return (
        db.query(Department)
        .filter(Department.branch_id == branch_id)
        .order_by(Department.name)
        .all()
    )


# ── Shift ─────────────────────────────────────────────────────────────

def create_shift(db: Session, data: ShiftCreate) -> Shift:
    shift = Shift(**data.model_dump())
    db.add(shift)
    db.flush()
    return shift


def get_shift(db: Session, shift_id: int) -> Optional[Shift]:
    return db.query(Shift).filter(Shift.id == shift_id).first()


def list_shifts(db: Session, branch_id: int) -> list[Shift]:
    return (
        db.query(Shift)
        .filter(Shift.branch_id == branch_id)
        .order_by(Shift.start_time)
        .all()
    )


# ── LeaveType ─────────────────────────────────────────────────────────

def create_leave_type(db: Session, data: LeaveTypeCreate) -> LeaveType:
    lt = LeaveType(**data.model_dump())
    db.add(lt)
    db.flush()
    return lt


def list_leave_types(db: Session, branch_id: int) -> list[LeaveType]:
    return (
        db.query(LeaveType)
        .filter(LeaveType.branch_id == branch_id)
        .order_by(LeaveType.name)
        .all()
    )


# ── LeaveRequest ──────────────────────────────────────────────────────

def create_leave_request(
    db: Session,
    employee_id: int,
    branch_id: int,
    leave_type_id: int,
    start_date: date,
    end_date: date,
    days_requested: int,
    reason: Optional[str] = None,
) -> LeaveRequest:
    req = LeaveRequest(
        employee_id=employee_id,
        branch_id=branch_id,
        leave_type_id=leave_type_id,
        start_date=start_date,
        end_date=end_date,
        days_requested=days_requested,
        reason=reason,
        status="pending",
    )
    db.add(req)
    db.flush()
    return req


def get_leave_request(db: Session, request_id: int) -> Optional[LeaveRequest]:
    return db.query(LeaveRequest).filter(LeaveRequest.id == request_id).first()


def get_overlapping_leave(
    db: Session, employee_id: int, start_date: date, end_date: date,
) -> Optional[LeaveRequest]:
    """يدوّر على أي طلب إجازة (معلّق أو معتمد — مش مرفوض) لنفس الموظف بيتقاطع
    مع المدى المطلوب. تقاطع مدَيين: existing.start <= new.end AND existing.end
    >= new.start (المعادلة القياسية لتقاطع فترتين)."""
    return (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status.in_(("pending", "approved")),
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date,
        )
        .first()
    )


def list_leave_requests(
    db: Session,
    branch_id: int,
    employee_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[LeaveRequest], int]:
    q = db.query(LeaveRequest).filter(LeaveRequest.branch_id == branch_id)
    if employee_id:
        q = q.filter(LeaveRequest.employee_id == employee_id)
    if status:
        q = q.filter(LeaveRequest.status == status)
    total = q.count()
    items = q.order_by(LeaveRequest.start_date.desc()).offset(skip).limit(limit).all()
    return items, total


def approve_leave_request(
    db: Session, request: LeaveRequest, approved_by: int
) -> LeaveRequest:
    request.status      = "approved"
    request.approved_by = approved_by
    request.approved_at = datetime.utcnow()
    db.flush()
    return request


def reject_leave_request(
    db: Session, request: LeaveRequest, reason: str
) -> LeaveRequest:
    request.status           = "rejected"
    request.rejection_reason = reason
    db.flush()
    return request


# ── EmployeePenalty ───────────────────────────────────────────────────

def create_penalty(db: Session, data: EmployeePenaltyCreate) -> EmployeePenalty:
    penalty = EmployeePenalty(**data.model_dump())
    db.add(penalty)
    db.flush()
    return penalty


def list_penalties(
    db: Session,
    branch_id: int,
    employee_id: Optional[int] = None,
    month: Optional[str] = None,  # "YYYY-MM"
) -> list[EmployeePenalty]:
    q = db.query(EmployeePenalty).filter(EmployeePenalty.branch_id == branch_id)
    if employee_id:
        q = q.filter(EmployeePenalty.employee_id == employee_id)
    if month:
        year, mon = map(int, month.split("-"))
        first_day = date(year, mon, 1)
        last_day  = date(year, mon, calendar.monthrange(year, mon)[1])
        q = q.filter(
            EmployeePenalty.penalty_date >= first_day,
            EmployeePenalty.penalty_date <= last_day,
        )
    return q.order_by(EmployeePenalty.penalty_date.desc()).all()


# ── RotaTemplate ──────────────────────────────────────────────────────

def create_rota_template(db: Session, data: RotaTemplateCreate) -> RotaTemplate:
    template = RotaTemplate(**data.model_dump())
    db.add(template)
    db.flush()
    return template


def get_rota_template(db: Session, template_id: int) -> Optional[RotaTemplate]:
    return db.query(RotaTemplate).filter(RotaTemplate.id == template_id).first()


def list_rota_templates(
    db: Session,
    branch_id: int,
    department_id: Optional[int] = None,
    is_active: Optional[bool] = None,
) -> list[RotaTemplate]:
    q = db.query(RotaTemplate).filter(RotaTemplate.branch_id == branch_id)
    if department_id:
        q = q.filter(RotaTemplate.department_id == department_id)
    if is_active is not None:
        q = q.filter(RotaTemplate.is_active.is_(is_active))
    return q.order_by(RotaTemplate.name).all()


def update_rota_template(db: Session, template: RotaTemplate, data: RotaTemplateUpdate) -> RotaTemplate:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    db.flush()
    return template


# ── RotaAssignment ────────────────────────────────────────────────────

def create_rota_assignment(db: Session, data: RotaAssignmentCreate) -> RotaAssignment:
    assignment = RotaAssignment(**data.model_dump())
    db.add(assignment)
    db.flush()
    return assignment


def get_rota_assignment(db: Session, assignment_id: int) -> Optional[RotaAssignment]:
    return db.query(RotaAssignment).filter(RotaAssignment.id == assignment_id).first()


def list_rota_assignments(
    db: Session,
    branch_id: int,
    week_start: date,
    week_end: date,
    employee_id: Optional[int] = None,
) -> list[RotaAssignment]:
    q = (
        db.query(RotaAssignment)
        .filter(
            RotaAssignment.branch_id == branch_id,
            RotaAssignment.assigned_date >= week_start,
            RotaAssignment.assigned_date <= week_end,
        )
    )
    if employee_id:
        q = q.filter(RotaAssignment.employee_id == employee_id)
    return q.order_by(RotaAssignment.assigned_date, RotaAssignment.employee_id).all()


# ── ShiftSwapRequest ──────────────────────────────────────────────────

def create_swap_request(db: Session, data: ShiftSwapRequestCreate) -> ShiftSwapRequest:
    swap = ShiftSwapRequest(**data.model_dump())
    db.add(swap)
    db.flush()
    return swap


def get_swap_request(db: Session, swap_id: int) -> Optional[ShiftSwapRequest]:
    return db.query(ShiftSwapRequest).filter(ShiftSwapRequest.id == swap_id).first()


def approve_swap(
    db: Session, swap_request: ShiftSwapRequest, approver_id: int
) -> ShiftSwapRequest:
    from_assignment = get_rota_assignment(db, swap_request.from_assignment_id)
    to_assignment   = get_rota_assignment(db, swap_request.to_assignment_id)

    if from_assignment and to_assignment:
        # Swap employee_ids between the two assignments
        from_assignment.employee_id, to_assignment.employee_id = (
            to_assignment.employee_id, from_assignment.employee_id
        )
        from_assignment.status = "swapped"
        to_assignment.status   = "swapped"

    swap_request.status      = "approved"
    swap_request.approver_id = approver_id
    db.flush()
    return swap_request
