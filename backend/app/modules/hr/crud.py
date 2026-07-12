"""app/modules/hr/crud.py — CRUD خالص"""
from __future__ import annotations

import calendar
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.modules.hr.models import (
    AdvancePayment, AttendancePolicy, AttendanceRecord, Department, Employee, EmployeeAllowance,
    EmployeePenalty, LeaveBalance, LeaveBalanceMonthly, LeaveRequest, LeaveType, PenaltyType,
    PayrollLine, PayrollRun, RotaAssignment, RotaTemplate, SalaryAdvance, ShiftSwapRequest, Shift,
    SocialInsuranceConfig, TaxBracketConfig,
)
from app.modules.hr.schemas import (
    AdvancePaymentCreate,
    AttendancePolicyUpsert, AttendanceRecordCreate, AttendanceRecordUpdate, DepartmentCreate,
    EmployeeCreate, EmployeeUpdate,
    EmployeeAllowanceCreate, EmployeeAllowanceUpdate,
    EmployeePenaltyCreate, LeaveTypeCreate, PenaltyTypeCreate,
    PayrollRunCreate, RotaAssignmentCreate, RotaTemplateCreate, RotaTemplateUpdate,
    SalaryAdvanceCreate,
    ShiftCreate, ShiftSwapRequestCreate,
    SocialInsuranceConfigCreate, TaxBracketConfigCreate,
)


# ── Employee ──────────────────────────────────────────────────────────

def get_employee(db: Session, employee_id: int) -> Optional[Employee]:
    return db.query(Employee).filter(Employee.id == employee_id).first()


def get_employee_by_code(db: Session, code: str) -> Optional[Employee]:
    return db.query(Employee).filter(Employee.employee_code == code).first()


def get_employee_by_name(db: Session, branch_id: int, full_name: str) -> Optional[Employee]:
    """مطابقة بالاسم (case-insensitive، بعد trim) — fallback لاستيراد الحضور
    من Excel (wagdy.md H-07) لو الملف مافيهوش عمود كود الموظف، بس فيه الاسم
    زي ما هو متسجّل بالظبط في النظام. مقيّد بالفرع عشان اسم مكرر في فرع تاني
    ميتلخبطش مع الموظف الصح."""
    from sqlalchemy import func  # noqa: PLC0415
    return (
        db.query(Employee)
        .filter(
            Employee.branch_id == branch_id,
            func.lower(Employee.full_name) == full_name.strip().lower(),
        )
        .first()
    )


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

def get_active_si_config(db: Session, as_of: Optional[date] = None) -> Optional[SocialInsuranceConfig]:
    """⚠️ باج حقيقي كان هنا: من غير `as_of`، الدالة كانت بترجع أحدث صف
    is_active=True بس — يعني لو أضفت نسخة جديدة effective_from مستقبلي (زي
    endpoint POST /hr/config/social-insurance اليوم بالظبط، اللي اتعمل عشان
    "لما القانون يتغيّر")، أي كشف رواتب لأي فترة (حتى فترات ماضية) كان
    هيستخدم النسخة الجديدة فورًا بدل ما يستنى effective_from بتاعها. دلوقتي
    لازم `effective_from <= as_of` (تاريخ أول يوم في فترة الرواتب المطلوبة)."""
    q = db.query(SocialInsuranceConfig).filter(SocialInsuranceConfig.is_active.is_(True))
    if as_of is not None:
        q = q.filter(SocialInsuranceConfig.effective_from <= as_of)
    return q.order_by(SocialInsuranceConfig.effective_from.desc()).first()


def get_active_tax_brackets(db: Session, as_of: Optional[date] = None) -> list[TaxBracketConfig]:
    """⚠️ باج حقيقي أخطر من اللي فوق: كانت الدالة بترجع *كل* الصفوف
    is_active=True مع بعض بغض النظر عن effective_from بتاعها — يعني لو فيه
    نسخة قديمة (2024) ونسخة جديدة (تحديث تشريعي مستقبلي) اتضافت من غير ما
    حد يـ deactivate القديمة يدويًا (مفيش أي تحقق أو تحذير يمنع كده)، شرائح
    النسختين كانت بتتحسب مع بعض في نفس حساب annual_tax — نطاقات متداخلة
    بمعدلات متضاربة، يعني ضريبة كل موظف تتكسر فورًا من لحظة إضافة أي تحديث،
    مش بس الفترات المستقبلية. الحل: اختار "نسخة" واحدة بس (نفس effective_from)
    — أحدث effective_from <= as_of، مش كل الصفوف النشطة من كل النسخ سوا."""
    q = db.query(TaxBracketConfig).filter(TaxBracketConfig.is_active.is_(True))
    if as_of is not None:
        q = q.filter(TaxBracketConfig.effective_from <= as_of)
    latest = q.order_by(TaxBracketConfig.effective_from.desc()).first()
    if not latest:
        return []
    return (
        db.query(TaxBracketConfig)
        .filter(
            TaxBracketConfig.is_active.is_(True),
            TaxBracketConfig.effective_from == latest.effective_from,
        )
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

def get_attendance(db: Session, record_id: int) -> Optional[AttendanceRecord]:
    return db.query(AttendanceRecord).filter(AttendanceRecord.id == record_id).first()


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


def update_attendance(db: Session, record: AttendanceRecord, data: AttendanceRecordUpdate) -> AttendanceRecord:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    db.flush()
    return record


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


def list_attendance_for_payroll_period(
    db: Session, employee_id: int, date_from: date, date_to: date,
) -> list[AttendanceRecord]:
    """كل سجلات حضور موظف خلال مدى تاريخ (شهر رواتب عادةً) — بدون pagination
    عمدًا (استخدام داخلي لحساب الرواتب، مش list endpoint عام؛ مدى شهر واحد
    أقصاه ~31 سجل فمفيش خطر إرجاع آلاف الصفوف بالغلط)."""
    return (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.record_date >= date_from,
            AttendanceRecord.record_date <= date_to,
        )
        .order_by(AttendanceRecord.record_date)
        .all()
    )


def map_rota_shifts_for_period(
    db: Session, employee_id: int, date_from: date, date_to: date,
) -> dict[date, tuple[str, str]]:
    """يرجّع {assigned_date: (shift.start_time, shift.end_time)} لموظف خلال
    مدى تاريخ — استعلام واحد (join) بدل استعلام لكل يوم داخل حلقة (N+1)."""
    rows = (
        db.query(RotaAssignment.assigned_date, Shift.start_time, Shift.end_time)
        .join(Shift, RotaAssignment.shift_id == Shift.id)
        .filter(
            RotaAssignment.employee_id == employee_id,
            RotaAssignment.assigned_date >= date_from,
            RotaAssignment.assigned_date <= date_to,
        )
        .all()
    )
    return {assigned_date: (start, end) for assigned_date, start, end in rows}


# ── AttendancePolicy ──────────────────────────────────────────────────

def get_attendance_policy(db: Session, branch_id: int) -> Optional[AttendancePolicy]:
    return (
        db.query(AttendancePolicy)
        .filter(AttendancePolicy.branch_id == branch_id, AttendancePolicy.is_active.is_(True))
        .first()
    )


def upsert_attendance_policy(
    db: Session, branch_id: int, data: AttendancePolicyUpsert,
) -> AttendancePolicy:
    row = db.query(AttendancePolicy).filter(AttendancePolicy.branch_id == branch_id).first()
    if row:
        for field, value in data.model_dump().items():
            setattr(row, field, value)
    else:
        row = AttendancePolicy(branch_id=branch_id, **data.model_dump())
        db.add(row)
    db.flush()
    return row


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


# ── SalaryAdvance (wagdy.md H-01) ────────────────────────────────────────

def get_salary_advance(db: Session, advance_id: int) -> Optional[SalaryAdvance]:
    return db.query(SalaryAdvance).filter(SalaryAdvance.id == advance_id).first()


def create_salary_advance(db: Session, data: SalaryAdvanceCreate, created_by: int) -> SalaryAdvance:
    advance = SalaryAdvance(
        **data.model_dump(),
        remaining_balance=data.amount,
        created_by=created_by,
    )
    db.add(advance)
    db.flush()
    return advance


def list_salary_advances(
    db: Session, employee_id: Optional[int] = None, branch_id: Optional[int] = None,
    status: Optional[str] = None,
) -> list[SalaryAdvance]:
    q = db.query(SalaryAdvance)
    if employee_id is not None:
        q = q.filter(SalaryAdvance.employee_id == employee_id)
    if branch_id is not None:
        q = q.filter(SalaryAdvance.branch_id == branch_id)
    if status is not None:
        q = q.filter(SalaryAdvance.status == status)
    return q.order_by(SalaryAdvance.disbursed_date.desc()).all()


def list_active_advances_for_employee(db: Session, employee_id: int) -> list[SalaryAdvance]:
    """السلف النشطة (لسه فيها رصيد) لموظف — تُستخدم وقت حساب خصم كشف
    الرواتب (راجع services._compute_advance_deductions)."""
    return (
        db.query(SalaryAdvance)
        .filter(SalaryAdvance.employee_id == employee_id, SalaryAdvance.status == "active")
        .order_by(SalaryAdvance.disbursed_date)
        .all()
    )


# ── AdvancePayment (wagdy.md H-02) ───────────────────────────────────────

def create_advance_payment(db: Session, data: AdvancePaymentCreate, recorded_by: int) -> AdvancePayment:
    payment = AdvancePayment(**data.model_dump(), recorded_by=recorded_by)
    db.add(payment)
    db.flush()
    return payment


def list_advance_payments(
    db: Session, employee_id: Optional[int] = None, branch_id: Optional[int] = None,
    deducted: Optional[bool] = None,
) -> list[AdvancePayment]:
    q = db.query(AdvancePayment)
    if employee_id is not None:
        q = q.filter(AdvancePayment.employee_id == employee_id)
    if branch_id is not None:
        q = q.filter(AdvancePayment.branch_id == branch_id)
    if deducted is not None:
        q = q.filter(AdvancePayment.deducted.is_(deducted))
    return q.order_by(AdvancePayment.payment_date.desc()).all()


def list_undeducted_payments_for_period(
    db: Session, employee_id: int, period_year: int, period_month: int,
) -> list[AdvancePayment]:
    """دفعات الشهر دي لموظف لسه ما اتخصمتش من كشف رواتب — تُستخدم وقت
    حساب خصم كشف الرواتب (راجع services._compute_advance_deductions)."""
    first_day = date(period_year, period_month, 1)
    last_day = date(period_year, period_month, calendar.monthrange(period_year, period_month)[1])
    return (
        db.query(AdvancePayment)
        .filter(
            AdvancePayment.employee_id == employee_id,
            AdvancePayment.deducted.is_(False),
            AdvancePayment.payment_date >= first_day,
            AdvancePayment.payment_date <= last_day,
        )
        .all()
    )


# ── LeaveBalanceMonthly (wagdy.md H-03) ──────────────────────────────────

def get_leave_balance_monthly(
    db: Session, employee_id: int, period_year: int, period_month: int,
) -> Optional[LeaveBalanceMonthly]:
    return (
        db.query(LeaveBalanceMonthly)
        .filter(
            LeaveBalanceMonthly.employee_id == employee_id,
            LeaveBalanceMonthly.period_year == period_year,
            LeaveBalanceMonthly.period_month == period_month,
        )
        .first()
    )


def get_latest_leave_balance_monthly(db: Session, employee_id: int) -> Optional[LeaveBalanceMonthly]:
    return (
        db.query(LeaveBalanceMonthly)
        .filter(LeaveBalanceMonthly.employee_id == employee_id)
        .order_by(LeaveBalanceMonthly.period_year.desc(), LeaveBalanceMonthly.period_month.desc())
        .first()
    )


def list_leave_balance_monthly(
    db: Session, employee_id: int, limit: int = 24,
) -> list[LeaveBalanceMonthly]:
    return (
        db.query(LeaveBalanceMonthly)
        .filter(LeaveBalanceMonthly.employee_id == employee_id)
        .order_by(LeaveBalanceMonthly.period_year.desc(), LeaveBalanceMonthly.period_month.desc())
        .limit(limit)
        .all()
    )


def upsert_leave_balance_monthly(
    db: Session, employee_id: int, branch_id: int, period_year: int, period_month: int,
    opening_balance: Decimal, accrued: Decimal, consumed: Decimal,
) -> LeaveBalanceMonthly:
    row = get_leave_balance_monthly(db, employee_id, period_year, period_month)
    closing_balance = opening_balance + accrued - consumed
    if row:
        row.opening_balance = opening_balance
        row.accrued = accrued
        row.consumed = consumed
        row.closing_balance = closing_balance
    else:
        row = LeaveBalanceMonthly(
            employee_id=employee_id, branch_id=branch_id,
            period_year=period_year, period_month=period_month,
            opening_balance=opening_balance, accrued=accrued, consumed=consumed,
            closing_balance=closing_balance,
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
