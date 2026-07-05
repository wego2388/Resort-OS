"""app/modules/hr/schemas.py — Pydantic v2"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field


class EmployeeCreate(BaseModel):
    branch_id:     int
    employee_code: str = Field(..., max_length=20)
    full_name:     str = Field(..., max_length=200)
    national_id:   Optional[str] = Field(None, max_length=20)
    position:      str = Field(..., max_length=100)
    department:    Optional[str] = Field(None, max_length=100)
    basic_salary:  Decimal = Field(..., gt=0)
    hire_date:     date
    birth_date:    Optional[date] = None
    phone:         Optional[str] = Field(None, max_length=20)
    email:         Optional[str] = Field(None, max_length=100)
    user_id:       Optional[int] = None  # ربط اختياري بحساب دخول عند الإنشاء


class EmployeeUpdate(BaseModel):
    full_name:    Optional[str]     = None
    position:     Optional[str]     = None
    department:   Optional[str]     = None
    basic_salary: Optional[Decimal] = Field(None, gt=0)
    status:       Optional[str]     = Field(None, pattern=r"^(active|on_leave|terminated)$")
    phone:        Optional[str]     = None
    email:        Optional[str]     = None


class EmployeeRead(EmployeeCreate):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    status:     str
    created_at: datetime
    updated_at: datetime


class EmployeeLinkUserRequest(BaseModel):
    """PATCH /hr/employees/{id}/link-user body — ربط موظف بحساب دخول موجود."""
    user_id: int


# ── EmployeeAllowance ─────────────────────────────────────────────────
# كان الموديل (models.EmployeeAllowance) + crud.list_allowances_for_employee
# (للقراءة الداخلية وقت حساب الراتب) موجودين بالكامل، بس مفيش أي طريقة
# لإضافة بدل لموظف (سكن/انتقالات/بدل معيشة...) عن طريق الـ API — نفس فئة
# الباج (Lead/Campaign/TenantCashLog/CallNote/RotaTemplate) لكن هنا الأثر
# أخطر: بدلات الموظف بتدخل مباشرة في حساب الراتب الفعلي (calculate_payroll)،
# فغيابها يعني الطريقة الوحيدة لإضافة بدل كانت INSERT مباشر في الداتابيز.

class EmployeeAllowanceCreate(BaseModel):
    employee_id:    int
    name:           str = Field(..., max_length=100)
    amount:         Decimal = Field(..., gt=0)
    is_taxable:     bool = True
    is_pensionable: bool = False


class EmployeeAllowanceUpdate(BaseModel):
    name:           Optional[str]     = Field(None, max_length=100)
    amount:         Optional[Decimal] = Field(None, gt=0)
    is_taxable:     Optional[bool]    = None
    is_pensionable: Optional[bool]    = None
    is_active:      Optional[bool]    = None


class AllowanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    employee_id:    int
    name:           str
    amount:         Decimal
    is_taxable:     bool
    is_pensionable: bool
    is_active:      bool


class PayrollCalculateRequest(BaseModel):
    employee_id:        int
    period_year:        int = Field(..., ge=2020, le=2099)
    period_month:       int = Field(..., ge=1, le=12)
    penalty_days:       int = Field(0, ge=0)
    unpaid_leave_days:  int = Field(0, ge=0)
    overtime_amount:    Decimal = Field(Decimal("0"), ge=0)


class PayrollResultRead(BaseModel):
    employee_id:              int
    period:                   str
    basic_salary:             Decimal
    taxable_allowances:       Decimal
    non_taxable_allowances:   Decimal
    overtime:                 Decimal
    gross_salary:             Decimal
    insurable_salary:         Decimal
    employee_si:              Decimal
    employer_si:              Decimal
    annual_taxable_base:      Decimal
    annual_tax:               Decimal
    monthly_tax:              Decimal
    penalty_deduction:        Decimal
    unpaid_leave_deduction:   Decimal
    net_salary:               Decimal
    journal_entry:            dict


class PayrollRunCreate(BaseModel):
    branch_id:    int
    period_year:  int = Field(..., ge=2020, le=2099)
    period_month: int = Field(..., ge=1, le=12)


class PayrollLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:                     int
    payroll_run_id:         int
    employee_id:            int
    basic_salary:           Decimal
    gross_salary:           Decimal
    net_salary:             Decimal
    employee_si:            Decimal
    employer_si:            Decimal
    monthly_tax:            Decimal
    penalty_deduction:      Decimal
    unpaid_leave_deduction: Decimal


class PayrollRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    branch_id:    int
    period_year:  int
    period_month: int
    status:       str
    total_gross:  Decimal
    total_net:    Decimal
    total_tax:    Decimal
    total_si:     Decimal
    approved_by:  Optional[int]
    approved_at:  Optional[datetime]
    created_at:   datetime


class AttendanceRecordCreate(BaseModel):
    employee_id: int
    branch_id:   int
    record_date: date
    check_in:    Optional[datetime] = None
    check_out:   Optional[datetime] = None
    status:      str = Field("present", pattern=r"^(present|absent|late|leave|holiday)$")
    notes:       Optional[str] = Field(None, max_length=300)


class AttendanceRecordRead(AttendanceRecordCreate):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def hours_worked(self) -> Optional[float]:
        if not self.check_in or not self.check_out:
            return None
        return round((self.check_out - self.check_in).total_seconds() / 3600, 2)


class LeaveBalanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:              int
    employee_id:     int
    year:            int
    annual_entitled: int
    annual_taken:    int
    sick_taken:      int
    annual_remaining: int = 0

    def model_post_init(self, __context: object) -> None:
        object.__setattr__(self, "annual_remaining",
                           max(0, self.annual_entitled - self.annual_taken))


# ── Department ────────────────────────────────────────────────────────

class DepartmentCreate(BaseModel):
    branch_id:    int
    name:         str = Field(..., max_length=100)
    name_ar:      Optional[str] = Field(None, max_length=100)
    manager_id:   Optional[int] = None
    budget_limit: Decimal = Decimal("0")


class DepartmentRead(DepartmentCreate):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    created_at: datetime
    updated_at: datetime


# ── Shift ─────────────────────────────────────────────────────────────

class ShiftCreate(BaseModel):
    branch_id:      int
    name:           str = Field(..., max_length=100)
    name_ar:        Optional[str] = Field(None, max_length=100)
    start_time:     str = Field(..., max_length=5)   # "08:00"
    end_time:       str = Field(..., max_length=5)   # "16:00"
    duration_hours: Decimal = Field(..., gt=0)


class ShiftRead(ShiftCreate):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    created_at: datetime


# ── LeaveType ─────────────────────────────────────────────────────────

class LeaveTypeCreate(BaseModel):
    branch_id:         int
    name:              str = Field(..., max_length=100)
    name_ar:           Optional[str] = Field(None, max_length=100)
    is_paid:           bool = True
    max_days_per_year: Optional[int] = Field(None, ge=1)
    requires_approval: bool = True


class LeaveTypeRead(LeaveTypeCreate):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    created_at: datetime


# ── LeaveRequest ──────────────────────────────────────────────────────

class LeaveRequestCreate(BaseModel):
    employee_id:   int
    branch_id:     int
    leave_type_id: int
    start_date:    date
    end_date:      date
    reason:        Optional[str] = Field(None, max_length=500)


class LeaveRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:               int
    employee_id:      int
    branch_id:        int
    leave_type_id:    int
    start_date:       date
    end_date:         date
    days_requested:   int
    reason:           Optional[str]
    status:           str
    approved_by:      Optional[int]
    approved_at:      Optional[datetime]
    rejection_reason: Optional[str]
    created_at:       datetime


class LeaveApproveRequest(BaseModel):
    approved_by: int


class LeaveRejectRequest(BaseModel):
    reason: str = Field(..., max_length=300)


class LeaveStatusUpdate(BaseModel):
    """جسم مبسّط لـ PATCH /hr/leaves/{id} — بديل frontend-friendly لـ
    approve/reject endpoints المنفصلة فوق."""
    status: str = Field(..., pattern=r"^(approved|rejected)$")


# ── PenaltyType ───────────────────────────────────────────────────────

class PenaltyTypeCreate(BaseModel):
    branch_id:    int
    name:         str = Field(..., max_length=100)
    name_ar:      Optional[str] = Field(None, max_length=100)
    penalty_days: int = Field(1, ge=1)


class PenaltyTypeRead(PenaltyTypeCreate):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    created_at: datetime


# ── EmployeePenalty ───────────────────────────────────────────────────

class EmployeePenaltyCreate(BaseModel):
    employee_id:     int
    branch_id:       int
    penalty_type_id: Optional[int] = None
    penalty_date:    date
    penalty_days:    int = Field(1, ge=1)
    reason:          str = Field(..., max_length=500)
    applied_by:      int


class EmployeePenaltyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:              int
    employee_id:     int
    branch_id:       int
    penalty_type_id: Optional[int]
    penalty_date:    date
    penalty_days:    int
    reason:          str
    applied_by:      int
    created_at:      datetime


# ── RotaTemplate ──────────────────────────────────────────────────────
# RotaTemplate كان موجود بالكامل في models.py من غير أي schema/crud/router —
# نفس فئة الباج الموثّقة مرارًا (Lead/Campaign/TenantCashLog/CallNote).

class RotaTemplateCreate(BaseModel):
    branch_id:     int
    department_id: int
    name:          str = Field(..., max_length=100)
    week_pattern:  dict = Field(..., description='e.g. {"mon": {"morning": 3}, "tue": {"evening": 2}}')
    is_active:     bool = True


class RotaTemplateUpdate(BaseModel):
    name:          Optional[str]  = Field(None, max_length=100)
    week_pattern:  Optional[dict] = None
    is_active:     Optional[bool] = None


class RotaTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:            int
    branch_id:     int
    department_id: int
    name:          str
    week_pattern:  dict
    is_active:     bool
    created_at:    datetime
    updated_at:    datetime


# ── RotaAssignment ────────────────────────────────────────────────────

class RotaAssignmentCreate(BaseModel):
    branch_id:     int
    employee_id:   int
    shift_id:      int
    assigned_date: date
    notes:         Optional[str] = Field(None, max_length=200)


class RotaAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:            int
    branch_id:     int
    employee_id:   int
    shift_id:      int
    assigned_date: date
    status:        str
    notes:         Optional[str]
    created_at:    datetime


# ── ShiftSwapRequest ──────────────────────────────────────────────────

class ShiftSwapRequestCreate(BaseModel):
    branch_id:          int
    requester_id:       int
    target_employee_id: int
    from_assignment_id: int
    to_assignment_id:   int
    reason:             Optional[str] = Field(None, max_length=300)


class ShiftSwapRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:                 int
    branch_id:          int
    requester_id:       int
    target_employee_id: int
    from_assignment_id: int
    to_assignment_id:   int
    status:             str
    approver_id:        Optional[int]
    reason:             Optional[str]
    created_at:         datetime


# ── Self-Service (/hr/me/*) ───────────────────────────────────────────
# مخصّصة للموظف نفسه، مربوطة بـ Employee.user_id = current_user.id — أضيق
# نطاقاً عمداً من الـ schemas الإدارية فوق (لا تكشف بيانات موظفين آخرين).

class MyLeaveRequestCreate(BaseModel):
    """POST /hr/me/leaves/request body — employee_id/branch_id يُشتقّان من
    الموظف المرتبط بالمستخدم الحالي، مش من الـ client."""
    leave_type_id: int
    start_date:    date
    end_date:      date
    reason:        Optional[str] = Field(None, max_length=500)


class MyProfileRead(BaseModel):
    """GET /hr/me/profile — بيانات الموظف الأساسية لصاحب الحساب نفسه فقط.
    national_id مسموح هنا (بيانات الشخص عن نفسه) — لكن مفيش أي endpoint
    آخر جوه /hr/me/* بيرجّع national_id لموظف تاني."""
    model_config = ConfigDict(from_attributes=True)
    id:            int
    branch_id:     int
    employee_code: str
    full_name:     str
    national_id:   Optional[str] = None
    position:      str
    department:    Optional[str] = None
    hire_date:     date
    birth_date:    Optional[date] = None
    phone:         Optional[str] = None
    email:         Optional[str] = None
    status:        str


class MyPayslipRead(BaseModel):
    """GET /hr/me/payslips — للقراءة فقط، من كشوف رواتب معتمدة/مصروفة فقط
    (مش draft — الأرقام مش نهائية لسه)."""
    id:                     int
    payroll_run_id:         int
    period_year:            int
    period_month:           int
    status:                 str
    basic_salary:           Decimal
    gross_salary:           Decimal
    net_salary:             Decimal
    employee_si:            Decimal
    monthly_tax:            Decimal
    penalty_deduction:      Decimal
    unpaid_leave_deduction: Decimal


class LeaderboardEntry(BaseModel):
    """صف واحد في لوحة أداء الموظفين — مبيعات حقيقية من المطعم/الكافيه/الشاطئ
    مجمّعة بالموظف (عبر user_id، مش employee_id — waiter_id/cashier_id في
    الطلبات كلها User.id فعليًا)، مش أرقام وهمية."""
    user_id:        int
    employee_name:  Optional[str] = None
    employee_code:  Optional[str] = None
    total_sales:    Decimal
    order_count:    int
