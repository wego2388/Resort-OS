"""HIST-01 — مولّد بيانات الموارد البشرية التاريخية ليوليو 2026 (OPS-DATA-02
§10.1). بيستخدم services/crud الحقيقية بس (create_employee/upsert_attendance/
upsert_attendance_policy/create_leave_type/request_leave/approve_leave/
create_penalty/run_payroll_for_branch/approve_payroll_run) — صفر SQL مباشر.

⚠️ قرارات نطاق موثّقة صراحةً:
- SocialInsuranceConfig/TaxBracketConfig **جداول عالمية** (بلا branch_id
  خالص — راجع models.py) مش خاصة بفرع HIST-01 بس؛ المولّد بيتأكد إنها
  موجودة (idempotent check-then-create بنفس القيم الحقيقية 2024 اللي
  app.seed._seed_social_insurance/_seed_tax_brackets بتستخدمها) بدل ما
  يزرعها من غير شرط، عشان ميكسرش/يكرّرش إعداد فرع تاني حقيقي موجود بالفعل.
  §9.1 نفسها بتحذّر من مقارنته بحساب قانوني حقيقي — synthetic_non_filing.
- "غياب مبرر" من §10.1 اتفسّرت هنا كإجازة غير مدفوعة معتمدة (بالظبط
  السيناريو اللي كشف باج unpaid_leave_deduction الحقيقي اللي اتصلح في نفس
  الجلسة) — التفسير الأكتر واقعية لـ"غياب اتوافق عليه" (مش مجرد no-show).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.resort_os.clock import scenario_clock

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.operational_history_seed import ScenarioContext

# (رمز، الاسم، المنصب، القسم، الراتب الأساسي) — §10.1 بالظبط، 14 موظف،
# إجمالي أساسي 181,000.
_EMPLOYEES: tuple[tuple[str, str, str, str, Decimal], ...] = (
    ("MGR-01", "مدير المنتجع HIST", "Resort Manager", "Management", Decimal("28000")),
    ("ACC-01", "محاسب HIST", "Accountant", "Finance", Decimal("18000")),
    ("HR-01", "أخصائي موارد بشرية HIST", "HR", "HR", Decimal("15000")),
    ("REC-01", "موظف استقبال 1 HIST", "Reception", "Front Office", Decimal("13000")),
    ("REC-02", "موظف استقبال 2 HIST", "Reception", "Front Office", Decimal("13000")),
    ("CSH-01", "كاشير 1 HIST", "Cashier", "Finance", Decimal("11000")),
    ("CSH-02", "كاشير 2 HIST", "Cashier", "Finance", Decimal("11000")),
    ("KIT-01", "مطبخ/كافيه 1 HIST", "Kitchen/Cafe", "Dining", Decimal("12000")),
    ("KIT-02", "مطبخ/كافيه 2 HIST", "Kitchen/Cafe", "Dining", Decimal("12000")),
    ("SRV-01", "خدمة 1 HIST", "Service", "Service", Decimal("9000")),
    ("SRV-02", "خدمة 2 HIST", "Service", "Service", Decimal("9000")),
    ("HSK-01", "تدبير منزلي 1 HIST", "Housekeeping", "Housekeeping", Decimal("8500")),
    ("HSK-02", "تدبير منزلي 2 HIST", "Housekeeping", "Housekeeping", Decimal("8500")),
    ("MNT-01", "صيانة HIST", "Maintenance", "Maintenance", Decimal("13000")),
)

_HIRE_DATE = date(2024, 1, 1)


def _cairo_to_utc_naive(d: date, hour: int, minute: int, tz: ZoneInfo) -> datetime:
    local_dt = datetime(d.year, d.month, d.day, hour, minute, tzinfo=tz)
    return local_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _ensure_global_payroll_config(db: "Session") -> None:
    """SocialInsuranceConfig/TaxBracketConfig عالميين — نفس القيم الحقيقية
    (2024) اللي app.seed بيستخدمها، بس idempotent check-then-create بدل
    زرع بلا شرط (راجع docstring الملف)."""
    from app.modules.hr.models import SocialInsuranceConfig, TaxBracketConfig

    if not db.query(SocialInsuranceConfig).filter(SocialInsuranceConfig.is_active.is_(True)).first():
        db.add(SocialInsuranceConfig(
            max_insurable_salary=Decimal("14000"), employee_rate=Decimal("0.11"),
            employer_rate=Decimal("0.1875"), personal_exemption_annual=Decimal("15000"),
            max_penalty_days_monthly=5, effective_from=date(2024, 1, 1), is_active=True,
        ))
    if not db.query(TaxBracketConfig).filter(TaxBracketConfig.is_active.is_(True)).first():
        brackets = [
            (Decimal("0"), Decimal("15000"), Decimal("0.000")),
            (Decimal("15001"), Decimal("30000"), Decimal("0.100")),
            (Decimal("30001"), Decimal("45000"), Decimal("0.150")),
            (Decimal("45001"), Decimal("60000"), Decimal("0.200")),
            (Decimal("60001"), Decimal("200000"), Decimal("0.225")),
            (Decimal("200001"), Decimal("400000"), Decimal("0.250")),
            (Decimal("400001"), None, Decimal("0.275")),
        ]
        for lower, upper, rate in brackets:
            db.add(TaxBracketConfig(
                lower_bound=lower, upper_bound=upper, rate=rate,
                effective_from=date(2024, 1, 1), is_active=True,
            ))
    db.flush()


def generate(db: "Session", ctx: "ScenarioContext") -> dict:
    from app.modules.hr import crud as hr_crud, services as hr_services
    from app.modules.hr.schemas import (
        AttendancePolicyUpsert, AttendanceRecordCreate, EmployeeCreate,
        EmployeePenaltyCreate, LeaveTypeCreate,
    )

    branch_id = ctx.branch_id
    tz = ZoneInfo(ctx.tz_name)
    year, month = ctx.period_year, ctx.period_month
    month_start = date(year, month, 1)
    days_in_month = 31 if month == 7 else (date(year, month % 12 + 1, 1) - timedelta(days=1)).day
    if ctx.period_end_day is not None:
        days_in_month = min(days_in_month, ctx.period_end_day)

    with scenario_clock(datetime(year, month, 1, 6, 0, tzinfo=tz)):
        _ensure_global_payroll_config(db)
        hr_crud.upsert_attendance_policy(db, branch_id, AttendancePolicyUpsert(
            late_grace_minutes=10, early_leave_grace_minutes=10,
            standard_shift_start="09:00", standard_shift_end="17:00",
            overtime_rate_multiplier=Decimal("1.50"), late_penalty_rate_multiplier=Decimal("1.00"),
            is_active=True,
        ))

        employees = []
        for code, name, position, department, salary in _EMPLOYEES:
            emp = hr_services.create_employee(db, EmployeeCreate(
                branch_id=branch_id, employee_code=code, full_name=name,
                position=position, department=department, basic_salary=salary,
                hire_date=_HIRE_DATE,
            ))
            employees.append(emp)
        db.flush()

        paid_leave_type = hr_crud.create_leave_type(db, LeaveTypeCreate(
            branch_id=branch_id, name="Annual Leave", name_ar="إجازة سنوية", is_paid=True,
        ))
        unpaid_leave_type = hr_crud.create_leave_type(db, LeaveTypeCreate(
            branch_id=branch_id, name="Unpaid Leave", name_ar="إجازة بدون أجر (غياب مبرر)",
            is_paid=False,
        ))
        db.flush()

        # ── حضور يوليو الأساسي: كل موظف present 9:00-17:00 كل يوم ────────
        for emp in employees:
            for offset in range(days_in_month):
                day = month_start + timedelta(days=offset)
                hr_crud.upsert_attendance(db, AttendanceRecordCreate(
                    employee_id=emp.id, branch_id=branch_id, record_date=day,
                    check_in=_cairo_to_utc_naive(day, 9, 0, tz),
                    check_out=_cairo_to_utc_naive(day, 17, 0, tz),
                    status="present",
                ))
        db.flush()

        # ── استثناءات حقيقية (تأخير/أوفرتايم/إجازة مدفوعة/إجازة غير
        # مدفوعة معتمدة/جزاء يدوي) — راجع §10.1. ────────────────────────
        reception1 = employees[3]  # REC-01
        for offset in (4, 11, 18):  # 3 أيام تأخير 20 دقيقة
            day = month_start + timedelta(days=offset)
            hr_crud.upsert_attendance(db, AttendanceRecordCreate(
                employee_id=reception1.id, branch_id=branch_id, record_date=day,
                check_in=_cairo_to_utc_naive(day, 9, 20, tz),
                check_out=_cairo_to_utc_naive(day, 17, 0, tz),
                status="late",
            ))

        housekeeping1 = employees[11]  # HSK-01
        for offset in (7, 14):  # يومين أوفرتايم 90 دقيقة
            day = month_start + timedelta(days=offset)
            hr_crud.upsert_attendance(db, AttendanceRecordCreate(
                employee_id=housekeeping1.id, branch_id=branch_id, record_date=day,
                check_in=_cairo_to_utc_naive(day, 9, 0, tz),
                check_out=_cairo_to_utc_naive(day, 18, 30, tz),
                status="present",
            ))
        db.flush()

        cashier2 = employees[6]  # CSH-02 — إجازة مدفوعة معتمدة (يوم واحد)
        paid_leave = hr_services.request_leave(
            db, cashier2.id, branch_id, paid_leave_type.id,
            date(year, month, 20), date(year, month, 20), reason="إجازة سنوية",
        )
        hr_services.approve_leave(db, paid_leave.id, approved_by=0)

        cashier1 = employees[5]  # CSH-01 — غياب مبرر = إجازة غير مدفوعة معتمدة (يومين)
        unpaid_leave = hr_services.request_leave(
            db, cashier1.id, branch_id, unpaid_leave_type.id,
            date(year, month, 15), date(year, month, 16), reason="ظرف عائلي",
        )
        hr_services.approve_leave(db, unpaid_leave.id, approved_by=0)

        housekeeping2 = employees[12]  # HSK-02 — جزاء تأديبي يدوي (يوم واحد)
        hr_crud.create_penalty(db, EmployeePenaltyCreate(
            employee_id=housekeeping2.id, branch_id=branch_id,
            penalty_date=date(year, month, 12), penalty_days=1,
            reason="مخالفة لائحة داخلية", applied_by=0,
        ))
        db.commit()

        # ── تشغيل واعتماد كشف رواتب يوليو حقيقي ──────────────────────────
        run = hr_services.run_payroll_for_branch(db, branch_id, year, month)
        approved_run = hr_services.approve_payroll_run(db, run.id, approved_by=0)

    return {
        "counts": {
            "employees_created": len(employees),
            "attendance_records": len(employees) * days_in_month,
            "leave_requests_approved": 2,
            "manual_penalties": 1,
            "payroll_lines": len(hr_crud.list_lines_for_run(db, approved_run.id)),
        },
        "totals": {
            "total_basic_salary": str(sum(row[4] for row in _EMPLOYEES)),
            "payroll_total_gross": str(approved_run.total_gross),
            "payroll_total_net": str(approved_run.total_net),
            "payroll_total_tax": str(approved_run.total_tax),
            "payroll_total_si": str(approved_run.total_si),
        },
    }
