"""
app/modules/hr/models.py
HR Module — always_on
Tables: employees, social_insurance_config, tax_bracket_configs,
        employee_allowances, payroll_runs, payroll_lines,
        attendance_records, leave_balances
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, JSON,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.kernel.models.mixins import TimestampMixin
from app.core.database import Base
from app.core.encryption import EncryptedString


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"

    id:            Mapped[int]         = mapped_column(primary_key=True)
    branch_id:     Mapped[int]         = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    employee_code: Mapped[str]         = mapped_column(String(20), unique=True)  # EMP-001
    full_name:     Mapped[str]         = mapped_column(String(200))
    national_id:   Mapped[str | None]  = mapped_column(EncryptedString(255), nullable=True)
    position:      Mapped[str]         = mapped_column(String(100))
    department:    Mapped[str | None]  = mapped_column(String(100), nullable=True)
    basic_salary:  Mapped[Decimal]     = mapped_column(Numeric(10, 2))
    # وعاء التأمينات الاجتماعية — منفصل عمدًا عن basic_salary (وعده وقانوني
    # المتري: راتب 20,000 لكن وعاء تأميني 13,500 لبعض الموظفين، تُفرَّغ عمدًا).
    # NULL = يُستخدم basic_salary كوعاء تأميني (السلوك القديم قبل الحقل ده،
    # محفوظ لكل الموظفين الحاليين تلقائيًا) — راجع hr_engine.calculate_payroll.
    insurance_base_salary: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    # مكافأة الأعياد الرسمية — مبلغ ثابت لكل موظف بيدخل حساب الراتب تلقائيًا
    # كل مرة يتشغّل فيها كشف رواتب له (راجع hr_engine.calculate_payroll: بند
    # منفصل عن الأساسي/البدلات، مش خاضع لضريبة ولا تأمينات، بيُضاف للصافي
    # مباشرة). الإدارة تصفّره بعد شهر العيد لو مش عايزاه يتكرر كل شهر.
    holiday_bonus: Mapped[Decimal]     = mapped_column(Numeric(10, 2), default=Decimal("0"))
    hire_date:     Mapped[date]        = mapped_column(Date)
    birth_date:    Mapped[date | None] = mapped_column(Date, nullable=True)
    status:        Mapped[str]         = mapped_column(String(20), default="active")  # active|on_leave|terminated
    phone:         Mapped[str | None]  = mapped_column(String(20), nullable=True)
    email:         Mapped[str | None]  = mapped_column(String(100), nullable=True)
    # ربط اختياري بحساب تسجيل دخول (app.core.kernel.models.user.User) — يسمح للموظف
    # نفسه بمشاهدة حضوره/إجازاته/راتبه عبر /hr/me/*. NULL لموظفين موسميين/بدون
    # حساب دخول. unique — كل User مربوط بموظف واحد كحد أقصى.
    user_id:       Mapped[int | None]  = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, unique=True,
    )

    allowances: Mapped[list["EmployeeAllowance"]] = relationship("EmployeeAllowance", back_populates="employee", lazy="select")


class SocialInsuranceConfig(Base, TimestampMixin):
    __tablename__ = "social_insurance_configs"

    id:                        Mapped[int]     = mapped_column(primary_key=True)
    max_insurable_salary:      Mapped[Decimal] = mapped_column(Numeric(10, 2))
    employee_rate:             Mapped[Decimal] = mapped_column(Numeric(5, 4))
    employer_rate:             Mapped[Decimal] = mapped_column(Numeric(5, 4))
    personal_exemption_annual: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    max_penalty_days_monthly:  Mapped[int]     = mapped_column(Integer, default=5)
    effective_from:            Mapped[date]    = mapped_column(Date)
    is_active:                 Mapped[bool]    = mapped_column(Boolean, default=True)


class TaxBracketConfig(Base, TimestampMixin):
    __tablename__ = "tax_bracket_configs"

    id:             Mapped[int]         = mapped_column(primary_key=True)
    lower_bound:    Mapped[Decimal]     = mapped_column(Numeric(12, 2))
    upper_bound:    Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    rate:           Mapped[Decimal]     = mapped_column(Numeric(5, 4))
    effective_from: Mapped[date]        = mapped_column(Date)
    is_active:      Mapped[bool]        = mapped_column(Boolean, default=True)


class EmployeeAllowance(Base, TimestampMixin):
    __tablename__ = "employee_allowances"

    id:             Mapped[int]     = mapped_column(primary_key=True)
    employee_id:    Mapped[int]     = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    name:           Mapped[str]     = mapped_column(String(100))
    amount:         Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_taxable:     Mapped[bool]    = mapped_column(Boolean, default=True)
    is_pensionable: Mapped[bool]    = mapped_column(Boolean, default=False)
    is_active:      Mapped[bool]    = mapped_column(Boolean, default=True)

    employee: Mapped["Employee"] = relationship("Employee", back_populates="allowances")


class PayrollRun(Base, TimestampMixin):
    __tablename__ = "payroll_runs"
    __table_args__ = (
        UniqueConstraint("branch_id", "period_year", "period_month", name="uq_payroll_period"),
    )

    id:           Mapped[int]            = mapped_column(primary_key=True)
    branch_id:    Mapped[int]            = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    period_year:  Mapped[int]            = mapped_column(Integer)
    period_month: Mapped[int]            = mapped_column(Integer)
    status:       Mapped[str]            = mapped_column(String(20), default="draft")  # draft|approved|paid
    total_gross:  Mapped[Decimal]        = mapped_column(Numeric(12, 2), default=Decimal("0"))
    total_net:    Mapped[Decimal]        = mapped_column(Numeric(12, 2), default=Decimal("0"))
    total_tax:    Mapped[Decimal]        = mapped_column(Numeric(12, 2), default=Decimal("0"))
    total_si:     Mapped[Decimal]        = mapped_column(Numeric(12, 2), default=Decimal("0"))
    # إجمالي مكافآت الأعياد المُصروفة ضمن الكشف ده — منفصل عن total_gross
    # (مكافأة العيد مش خاضعة لضريبة/تأمينات، فمش جزء من gross_salary القياسي)
    # لكن لازم يُحتسب في القيد المحاسبي المجمّع (_post_payroll_journal) عشان
    # المدين يفضل متوازن مع صافي الرواتب المستحقة اللي بيشمل المكافأة.
    total_holiday_bonus: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    # إجمالي خصومات السلف/الدفعات (H-01+H-02) المطبَّقة في الكشف ده — جزء من
    # total_net (مخصوم منه فعلاً في hr_engine.calculate_payroll) فمش محتاج
    # سطر قيد محاسبي منفصل في _post_payroll_journal (خصومات الصافي الأخرى
    # زي penalty_deduction ماعندهاش سطر منفصل برضه، نفس النمط الموجود).
    total_advance_deduction: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    approved_by:  Mapped[int | None]     = mapped_column(Integer, nullable=True)
    approved_at:  Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    lines: Mapped[list["PayrollLine"]] = relationship("PayrollLine", back_populates="run", lazy="select")


class PayrollLine(Base, TimestampMixin):
    __tablename__ = "payroll_lines"

    id:                    Mapped[int]     = mapped_column(primary_key=True)
    payroll_run_id:        Mapped[int]     = mapped_column(ForeignKey("payroll_runs.id", ondelete="CASCADE"))
    employee_id:           Mapped[int]     = mapped_column(ForeignKey("employees.id", ondelete="RESTRICT"))
    basic_salary:          Mapped[Decimal] = mapped_column(Numeric(10, 2))
    gross_salary:          Mapped[Decimal] = mapped_column(Numeric(10, 2))
    net_salary:            Mapped[Decimal] = mapped_column(Numeric(10, 2))
    employee_si:           Mapped[Decimal] = mapped_column(Numeric(10, 2))
    employer_si:           Mapped[Decimal] = mapped_column(Numeric(10, 2))
    monthly_tax:           Mapped[Decimal] = mapped_column(Numeric(10, 2))
    penalty_deduction:     Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    late_penalty_deduction:Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))  # خصم تأخير محسوب تلقائيًا من الحضور — منفصل عن penalty_deduction (جزاءات تأديبية يدوية بالأيام)
    unpaid_leave_deduction:Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    holiday_bonus:          Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))  # مكافأة العيد المُطبَّقة على هذا الموظف لهذا الكشف — راجع Employee.holiday_bonus
    advance_deduction:      Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))  # إجمالي أقساط سلف (H-01) + دفعات (H-02) المخصومة لهذا الموظف لهذا الكشف
    journal_entry:         Mapped[str | None] = mapped_column(Text, nullable=True)   # JSON

    run: Mapped["PayrollRun"] = relationship("PayrollRun", back_populates="lines")


class AttendanceRecord(Base, TimestampMixin):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("employee_id", "record_date", name="uq_attendance_employee_date"),
    )

    id:          Mapped[int]            = mapped_column(primary_key=True)
    employee_id: Mapped[int]            = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    branch_id:   Mapped[int]            = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    record_date: Mapped[date]           = mapped_column(Date, index=True)
    check_in:    Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    check_out:   Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status:      Mapped[str]            = mapped_column(String(20), default="present")  # present|absent|late|leave|holiday
    notes:       Mapped[str | None]     = mapped_column(String(300), nullable=True)


class AttendancePolicy(Base, TimestampMixin):
    """سياسة الحضور/الانصراف لكل فرع — تتحكم في تحويل بصمات الحضور الخام
    (AttendanceRecord.check_in/check_out) لدقايق تأخير/أوفرتايم/انصراف مبكر
    تلقائيًا قبل ما تتحول لمبالغ مالية تدخل حساب الراتب (راجع
    app.resort_os.hr_engine.compute_attendance_minutes). فرع واحد = سياسة واحدة
    (unique على branch_id) — مفيش سياسة نشطة = مفيش حساب تلقائي، الراتب لسه
    بيشتغل عادي بالمدخلات اليدوية زي ما كان قبل كده (إضافة، مش استبدال)."""
    __tablename__ = "attendance_policies"

    id:        Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), unique=True)

    late_grace_minutes:        Mapped[int] = mapped_column(Integer, default=10)
    early_leave_grace_minutes: Mapped[int] = mapped_column(Integer, default=10)

    # الوردية الافتراضية (fallback) لموظف بدون RotaAssignment صريح لليوم —
    # لو فيه RotaAssignment→Shift مضبوط لليوم ده، بياخد الأولوية دايمًا على القيم دي.
    standard_shift_start: Mapped[str] = mapped_column(String(5), default="09:00")   # "HH:MM"
    standard_shift_end:   Mapped[str] = mapped_column(String(5), default="17:00")   # "HH:MM"

    overtime_rate_multiplier:     Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("1.50"))
    late_penalty_rate_multiplier: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("1.00"))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LeaveBalance(Base, TimestampMixin):
    __tablename__ = "leave_balances"
    __table_args__ = (
        UniqueConstraint("employee_id", "year", name="uq_leave_employee_year"),
    )

    id:               Mapped[int] = mapped_column(primary_key=True)
    employee_id:      Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    year:             Mapped[int] = mapped_column(Integer)
    annual_entitled:  Mapped[int] = mapped_column(Integer)
    annual_taken:     Mapped[int] = mapped_column(Integer, default=0)
    sick_taken:       Mapped[int] = mapped_column(Integer, default=0)


class SalaryAdvance(Base, TimestampMixin):
    """سلفة راتب — قرض بيُخصم على أقساط شهرية ثابتة من الراتب لحد ما يتسدد
    بالكامل (wagdy.md H-01). دي "السلف" اللي ظهرت في كشف يناير الحقيقي
    (60,066 ج شهريًا، 26% من المستحق) — منفصلة عمدًا عن AdvancePayment تحت
    (H-02، دفعات يومية بسيطة بتتخصم بالكامل في نفس شهرها، مش قرض بأقساط)."""
    __tablename__ = "salary_advances"

    id:                        Mapped[int]        = mapped_column(primary_key=True)
    employee_id:               Mapped[int]        = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    branch_id:                 Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    amount:                    Mapped[Decimal]    = mapped_column(Numeric(10, 2))
    disbursed_date:            Mapped[date]       = mapped_column(Date)
    monthly_deduction_amount:  Mapped[Decimal]    = mapped_column(Numeric(10, 2))
    # يبدأ = amount، وينقص كل مرة كشف رواتب يتشغّل ويخصم قسط (راجع
    # services._compute_advance_deductions) لحد ما يوصل صفر → status="settled".
    remaining_balance:         Mapped[Decimal]    = mapped_column(Numeric(10, 2))
    status:                    Mapped[str]        = mapped_column(String(20), default="active")  # active|settled|cancelled
    notes:                     Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by:                Mapped[int]        = mapped_column(Integer)

    employee: Mapped["Employee"] = relationship("Employee", lazy="select")


class AdvancePayment(Base, TimestampMixin):
    """دفعة جزئية يومية للموظف خلال الشهر (wagdy.md H-02) — الملف الحقيقي
    "دفعات المرتبات.xlsx" منفصل تمامًا عن ملف السلف. بتُخصم بالكامل من صافي
    راتب نفس الشهر (مش أقساط زي SalaryAdvance فوق). deducted/payroll_line_id
    بيتسجّلوا لما run_payroll_for_branch يخصمها فعليًا — audit trail واضح
    لمين اتخصم فين، مش شرط لصحة الحساب نفسه (تشغيل كشف رواتب لنفس الفترة
    مرتين ممنوع أصلاً عبر UniqueConstraint على payroll_runs)."""
    __tablename__ = "advance_payments"

    id:               Mapped[int]        = mapped_column(primary_key=True)
    employee_id:      Mapped[int]        = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    branch_id:        Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    amount:           Mapped[Decimal]    = mapped_column(Numeric(10, 2))
    payment_date:     Mapped[date]       = mapped_column(Date, index=True)
    notes:            Mapped[str | None] = mapped_column(String(300), nullable=True)
    recorded_by:      Mapped[int]        = mapped_column(Integer)
    deducted:         Mapped[bool]       = mapped_column(Boolean, default=False)
    payroll_line_id:  Mapped[int | None] = mapped_column(
        ForeignKey("payroll_lines.id", ondelete="SET NULL"), nullable=True,
    )

    employee: Mapped["Employee"] = relationship("Employee", lazy="select")


class LeaveBalanceMonthly(Base, TimestampMixin):
    """رصيد إجازات شهري متحرّك (wagdy.md H-03) — لقطة واحدة لكل موظف لكل
    شهر: 7.5 يوم يُستحق (accrued)، أيام الإجازات المعتمدة المستهلكة في نفس
    الشهر تُخصم (consumed)، والرصيد الجاري (closing_balance) يترحّل لأول
    الشهر التالي كـ opening_balance — بالظبط زي الطريقة اللي بتتابَع بيها
    الإجازات فعليًا في Excel اليوم (كشف حضور منفصل لكل موظف).

    منفصل عمدًا عن LeaveBalance.annual_entitled (الاستحقاق القانوني السنوي
    حسب مادة 47 قانون العمل — 21/30 يوم حسب الأقدمية/السن، محسوب في
    hr_engine.annual_leave_entitlement وبيُحدَّث مرة واحدة يناير) — ده تتبّع
    تشغيلي شهري إضافي حسب سياسة المنتجع الفعلية، مش بديل للحساب القانوني."""
    __tablename__ = "leave_balance_monthly"
    __table_args__ = (
        UniqueConstraint("employee_id", "period_year", "period_month", name="uq_leave_monthly_employee_period"),
    )

    id:               Mapped[int]     = mapped_column(primary_key=True)
    employee_id:      Mapped[int]     = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    branch_id:        Mapped[int]     = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    period_year:      Mapped[int]     = mapped_column(Integer)
    period_month:     Mapped[int]     = mapped_column(Integer)
    opening_balance:  Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    accrued:          Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("7.5"))
    consumed:         Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    closing_balance:  Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))

    employee: Mapped["Employee"] = relationship("Employee", lazy="select")


class Department(Base, TimestampMixin):
    __tablename__ = "departments"

    id:           Mapped[int]          = mapped_column(primary_key=True)
    branch_id:    Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    name:         Mapped[str]          = mapped_column(String(100))
    name_ar:      Mapped[str | None]   = mapped_column(String(100), nullable=True)
    manager_id:   Mapped[int | None]   = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    budget_limit: Mapped[Decimal]      = mapped_column(Numeric(12, 2), default=Decimal("0"))


class Shift(Base, TimestampMixin):
    __tablename__ = "shifts"

    id:             Mapped[int]        = mapped_column(primary_key=True)
    branch_id:      Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    name:           Mapped[str]        = mapped_column(String(100))
    name_ar:        Mapped[str | None] = mapped_column(String(100), nullable=True)
    start_time:     Mapped[str]        = mapped_column(String(5))   # "08:00"
    end_time:       Mapped[str]        = mapped_column(String(5))   # "16:00"
    duration_hours: Mapped[Decimal]    = mapped_column(Numeric(4, 2))


class LeaveType(Base, TimestampMixin):
    __tablename__ = "leave_types"

    id:                 Mapped[int]        = mapped_column(primary_key=True)
    branch_id:          Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    name:               Mapped[str]        = mapped_column(String(100))
    name_ar:            Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_paid:            Mapped[bool]       = mapped_column(Boolean, default=True)
    max_days_per_year:  Mapped[int | None] = mapped_column(Integer, nullable=True)
    requires_approval:  Mapped[bool]       = mapped_column(Boolean, default=True)


class LeaveRequest(Base, TimestampMixin):
    __tablename__ = "leave_requests"

    id:               Mapped[int]             = mapped_column(primary_key=True)
    employee_id:      Mapped[int]             = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    branch_id:        Mapped[int]             = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    leave_type_id:    Mapped[int]             = mapped_column(ForeignKey("leave_types.id", ondelete="RESTRICT"))
    start_date:       Mapped[date]            = mapped_column(Date)
    end_date:         Mapped[date]            = mapped_column(Date)
    days_requested:   Mapped[int]             = mapped_column(Integer)
    reason:           Mapped[str | None]      = mapped_column(String(500), nullable=True)
    status:           Mapped[str]             = mapped_column(String(20), default="pending")  # pending|approved|rejected
    approved_by:      Mapped[int | None]      = mapped_column(Integer, nullable=True)
    approved_at:      Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str | None]      = mapped_column(String(300), nullable=True)

    employee:   Mapped["Employee"]  = relationship("Employee", lazy="select", foreign_keys=[employee_id])
    leave_type: Mapped["LeaveType"] = relationship("LeaveType", lazy="select")


class PenaltyType(Base, TimestampMixin):
    __tablename__ = "penalty_types"

    id:           Mapped[int]        = mapped_column(primary_key=True)
    branch_id:    Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    name:         Mapped[str]        = mapped_column(String(100))
    name_ar:      Mapped[str | None] = mapped_column(String(100), nullable=True)
    penalty_days: Mapped[int]        = mapped_column(Integer, default=1)


class EmployeePenalty(Base, TimestampMixin):
    __tablename__ = "employee_penalties"

    id:              Mapped[int]        = mapped_column(primary_key=True)
    employee_id:     Mapped[int]        = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    branch_id:       Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    penalty_type_id: Mapped[int | None] = mapped_column(ForeignKey("penalty_types.id", ondelete="SET NULL"), nullable=True)
    penalty_date:    Mapped[date]       = mapped_column(Date)
    penalty_days:    Mapped[int]        = mapped_column(Integer, default=1)
    reason:          Mapped[str]        = mapped_column(String(500))
    applied_by:      Mapped[int]        = mapped_column(Integer)

    employee: Mapped["Employee"] = relationship("Employee", lazy="select")


class RotaTemplate(Base, TimestampMixin):
    """قالب جدول أسبوعي لقسم معيّن."""
    __tablename__ = "rota_templates"

    id:            Mapped[int]  = mapped_column(primary_key=True)
    branch_id:     Mapped[int]  = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    department_id: Mapped[int]  = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"))
    name:          Mapped[str]  = mapped_column(String(100))
    week_pattern:  Mapped[dict] = mapped_column(JSON)  # {"mon": {"morning": 3}, ...}
    is_active:     Mapped[bool] = mapped_column(Boolean, default=True)


class RotaAssignment(Base, TimestampMixin):
    """تعيين وردية لموظف معيّن."""
    __tablename__ = "rota_assignments"

    id:            Mapped[int]        = mapped_column(primary_key=True)
    branch_id:     Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    employee_id:   Mapped[int]        = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    shift_id:      Mapped[int]        = mapped_column(ForeignKey("shifts.id", ondelete="RESTRICT"))
    assigned_date: Mapped[date]       = mapped_column(Date, index=True)
    status:        Mapped[str]        = mapped_column(String(20), default="scheduled")  # scheduled|confirmed|swapped|absent
    notes:         Mapped[str | None] = mapped_column(String(200), nullable=True)

    employee: Mapped["Employee"] = relationship("Employee", lazy="select")
    shift:    Mapped["Shift"]    = relationship("Shift", lazy="select")


class ShiftSwapRequest(Base, TimestampMixin):
    """طلب تبديل وردية بين موظفين."""
    __tablename__ = "shift_swap_requests"

    id:                 Mapped[int]        = mapped_column(primary_key=True)
    branch_id:          Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    requester_id:       Mapped[int]        = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    target_employee_id: Mapped[int]        = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    from_assignment_id: Mapped[int]        = mapped_column(ForeignKey("rota_assignments.id", ondelete="CASCADE"))
    to_assignment_id:   Mapped[int]        = mapped_column(ForeignKey("rota_assignments.id", ondelete="CASCADE"))
    status:             Mapped[str]        = mapped_column(String(20), default="pending")  # pending|approved|rejected
    approver_id:        Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason:             Mapped[str | None] = mapped_column(String(300), nullable=True)
