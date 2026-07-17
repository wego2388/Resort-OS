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
    # وعاء التأمينات الاجتماعية — None يعني "استخدم basic_salary" (راجع
    # hr_engine.calculate_payroll). موجود لأن بعض الموظفين وعاءهم التأميني
    # المسجّل رسميًا أقل من راتبهم الأساسي الفعلي.
    insurance_base_salary: Optional[Decimal] = Field(None, gt=0)
    # مكافأة الأعياد الرسمية — بند ثابت يدخل حساب الراتب تلقائيًا كل مرة
    # يُشغَّل فيها كشف رواتب لهذا الموظف (راجع hr_engine.calculate_payroll).
    holiday_bonus: Decimal = Field(Decimal("0"), ge=0)
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
    insurance_base_salary: Optional[Decimal] = Field(None, gt=0)
    holiday_bonus: Optional[Decimal] = Field(None, ge=0)
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


# ── SocialInsuranceConfig / TaxBracketConfig (admin) ───────────────────
# الموديلان (models.SocialInsuranceConfig/TaxBracketConfig) موجودين بالكامل
# ومقروئين فعليًا داخل حساب الراتب (hr_engine عبر crud.get_active_si_config/
# get_active_tax_brackets)، بس مفيش أي schema/router خالص لإضافة نسخة جديدة
# لما القانون يتغيّر (زي تحديث شرائح الضريبة أو نسب التأمينات سنويًا) — كانت
# الطريقة الوحيدة INSERT مباشر في الداتابيز (زي seed.py). دلوقتي فيه endpoint
# admin-only لإضافة نسخة جديدة (effective_from) من غير أي DB access مباشر.

class SocialInsuranceConfigCreate(BaseModel):
    max_insurable_salary:      Decimal = Field(..., gt=0)
    employee_rate:             Decimal = Field(..., gt=0, le=1)
    employer_rate:             Decimal = Field(..., gt=0, le=1)
    personal_exemption_annual: Decimal = Field(..., ge=0)
    max_penalty_days_monthly:  int     = Field(5, ge=0, le=31)
    effective_from:            date
    is_active:                 bool    = True


class SocialInsuranceConfigRead(SocialInsuranceConfigCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class TaxBracketConfigCreate(BaseModel):
    lower_bound:    Decimal = Field(..., ge=0)
    upper_bound:    Optional[Decimal] = Field(None, gt=0)
    rate:           Decimal = Field(..., ge=0, le=1)
    effective_from: date
    is_active:      bool = True


class TaxBracketConfigRead(TaxBracketConfigCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


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
    late_penalty_deduction:   Decimal
    unpaid_leave_deduction:   Decimal
    advance_deduction:        Decimal
    holiday_bonus:            Decimal
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
    late_penalty_deduction: Decimal
    unpaid_leave_deduction: Decimal
    advance_deduction:      Decimal
    holiday_bonus:          Decimal
    non_taxable_allowances: Decimal


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
    total_holiday_bonus: Decimal
    total_advance_deduction: Decimal
    total_non_taxable_allowances: Decimal
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


class AttendanceRecordUpdate(BaseModel):
    """تصحيح إداري لسجل حضور موجود (موظف نسي يبصم انصراف، وقت خطأ...) — مدير+
    فقط (راجع الراوتر). notes بيتحدّث كمان عشان المدير يوثّق سبب التصحيح؛
    مفيش عمود "سبب" منفصل، notes هو نفسه ده."""
    check_in:  Optional[datetime] = None
    check_out: Optional[datetime] = None
    status:    Optional[str] = Field(None, pattern=r"^(present|absent|late|leave|holiday)$")
    notes:     Optional[str] = Field(None, max_length=300)


class AttendanceImportResult(BaseModel):
    """POST /hr/attendance/import-excel — نتيجة استيراد ملف حضور Excel
    (wagdy.md H-07). imported = عدد خلايا (موظف × يوم) اتحوّلت لسجل حضور
    حقيقي بنجاح (إنشاء أو تحديث — upsert، مش رفض التكرار). errors محدودة
    بـ 20 سطر (نفس نمط استيراد عقود التايم شير) عشان الرد ميضخمش على ملف
    فيه مشاكل كتير. unmatched_employees = القيم في عمود تعريف الموظف (كود
    أو اسم) اللي مالقتلهاش أي Employee مطابق في الفرع — أكتر سبب واقعي
    للفشل الجزئي، فبتترجع صريحة بدل ما تتخبّى جوه errors العامة."""
    imported:            int
    errors:              list[str]
    unmatched_employees: list[str]


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


# ── SalaryAdvance (wagdy.md H-01) ────────────────────────────────────────

class SalaryAdvanceCreate(BaseModel):
    employee_id:              int
    branch_id:                int
    amount:                   Decimal = Field(..., gt=0)
    disbursed_date:           date
    monthly_deduction_amount: Decimal = Field(..., gt=0)
    notes:                    Optional[str] = Field(None, max_length=500)


class SalaryAdvanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:                        int
    employee_id:               int
    branch_id:                 int
    amount:                    Decimal
    disbursed_date:            date
    monthly_deduction_amount:  Decimal
    remaining_balance:         Decimal
    status:                    str
    notes:                     Optional[str]
    created_by:                int
    created_at:                datetime


class SalaryAdvanceCancel(BaseModel):
    """PATCH /hr/salary-advances/{id}/cancel — يلغي سلفة نشطة (لسه ماتخصمش
    ولا قسط منها) قبل ما تدخل حساب الراتب. سلفة اتخصم منها أي قسط بالفعل
    ماينفعش تتلغى (راجع services.cancel_salary_advance)."""
    reason: Optional[str] = Field(None, max_length=300)


# ── AdvancePayment (wagdy.md H-02) ───────────────────────────────────────

class AdvancePaymentCreate(BaseModel):
    employee_id:  int
    branch_id:    int
    amount:       Decimal = Field(..., gt=0)
    payment_date: date
    notes:        Optional[str] = Field(None, max_length=300)


class AdvancePaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:               int
    employee_id:      int
    branch_id:        int
    amount:           Decimal
    payment_date:     date
    notes:            Optional[str]
    recorded_by:      int
    deducted:          bool
    payroll_line_id:  Optional[int]
    created_at:       datetime


# ── LeaveBalanceMonthly (wagdy.md H-03) ──────────────────────────────────

class LeaveBalanceMonthlyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:               int
    employee_id:      int
    branch_id:        int
    period_year:      int
    period_month:      int
    opening_balance:  Decimal
    accrued:          Decimal
    consumed:         Decimal
    closing_balance:  Decimal


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


# ── AttendancePolicy ──────────────────────────────────────────────────
# سياسة الحضور/الانصراف لكل فرع — تغذّي app.resort_os.hr_engine.compute_
# attendance_minutes لتحويل بصمات AttendanceRecord الخام لدقايق تأخير/
# أوفرتايم/انصراف مبكر تلقائيًا قبل تشغيل الرواتب (راجع services.
# run_payroll_for_branch).

class AttendancePolicyUpsert(BaseModel):
    late_grace_minutes:           int = Field(10, ge=0, le=120)
    early_leave_grace_minutes:    int = Field(10, ge=0, le=120)
    standard_shift_start:         str = Field("09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    standard_shift_end:           str = Field("17:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    overtime_rate_multiplier:     Decimal = Field(Decimal("1.50"), ge=0)
    late_penalty_rate_multiplier: Decimal = Field(Decimal("1.00"), ge=0)
    is_active:                    bool = True


class AttendancePolicyRead(AttendancePolicyUpsert):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    branch_id:  int
    created_at: datetime
    updated_at: datetime


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
    late_penalty_deduction: Decimal
    unpaid_leave_deduction: Decimal
    holiday_bonus:          Decimal = Decimal("0")
    advance_deduction:      Decimal = Decimal("0")


class LeaderboardEntry(BaseModel):
    """صف واحد في لوحة أداء الموظفين — مبيعات حقيقية من المطعم/الكافيه/الشاطئ
    مجمّعة بالموظف (عبر user_id، مش employee_id — waiter_id/cashier_id في
    الطلبات كلها User.id فعليًا)، مش أرقام وهمية."""
    user_id:        int
    employee_name:  Optional[str] = None
    employee_code:  Optional[str] = None
    total_sales:    Decimal
    order_count:    int
