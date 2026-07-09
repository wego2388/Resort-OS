"""app/modules/hr/services.py — Business logic"""
from __future__ import annotations

import logging

import calendar
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.modules.hr import crud
from app.modules.hr.models import AttendancePolicy, AttendanceRecord, Employee, LeaveRequest, PayrollRun
from app.modules.hr.schemas import (
    AttendanceRecordCreate, EmployeeCreate, EmployeeUpdate,
    PayrollResultRead, PayrollRunCreate,
)
from app.resort_os.hr_engine import (
    Allowance as AllowanceDC,
    AttendancePolicyConfig,
    AttendancePunch,
    EmployeePayrollInput,
    SocialInsuranceConfig as SIConfig,
    TaxBracket,
    attendance_minutes_to_amount,
    calculate_payroll,
    compute_attendance_minutes,
    standard_shift_hours,
)
from app.resort_os.timezone_utils import local_today


def get_employee_or_404(db: Session, employee_id: int) -> Employee:
    emp = crud.get_employee(db, employee_id)
    if not emp:
        raise ValueError(f"الموظف {employee_id} غير موجود")
    return emp


def create_employee(db: Session, data: EmployeeCreate) -> Employee:
    if crud.get_employee_by_code(db, data.employee_code):
        raise ValueError(f"كود الموظف '{data.employee_code}' مستخدم مسبقاً")
    emp = crud.create_employee(db, data)
    db.commit()
    db.refresh(emp)
    return emp


def update_employee(db: Session, employee_id: int, data: EmployeeUpdate, updated_by: Optional[int] = None) -> Employee:
    emp = get_employee_or_404(db, employee_id)
    changes = data.model_dump(exclude_unset=True)

    # الراتب الأساسي تغيير حساس — لازم أثر واضح لمين غيّره وإمتى ومن كام لكام
    if "basic_salary" in changes and changes["basic_salary"] != emp.basic_salary:
        from app.modules.core.crud import create_audit_log  # noqa: PLC0415
        from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415
        create_audit_log(db, AuditLogCreate(
            user_id=updated_by, branch_id=emp.branch_id, action="update_salary",
            entity_type="employee", entity_id=emp.id,
            old_data=f'{{"basic_salary": "{emp.basic_salary}"}}',
            new_data=f'{{"basic_salary": "{changes["basic_salary"]}"}}',
        ))

    emp = crud.update_employee(db, emp, data)
    db.commit()
    db.refresh(emp)
    return emp


def link_employee_to_user(db: Session, emp: Employee, user_id: int) -> Employee:
    """يربط Employee موجود بحساب User موجود — يسمح للموظف بالدخول على
    /hr/me/* الخاصة به. emp لازم يكون موجود فعلاً (يتحقق منه الـ router قبل
    النداء هنا، نفس نمط باقي الـ endpoints)."""
    from app.core.kernel.models.user import User  # noqa: PLC0415

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"المستخدم {user_id} غير موجود")

    existing = crud.get_employee_by_user_id(db, user_id)
    if existing and existing.id != emp.id:
        raise ValueError(f"المستخدم مرتبط بالفعل بموظف آخر (id={existing.id})")

    emp.user_id = user_id
    db.commit()
    db.refresh(emp)
    return emp


def get_my_employee_or_404(db: Session, user_id: int) -> Employee:
    """يجيب سجل Employee المرتبط بالمستخدم الحالي — لأي endpoint من /hr/me/*.
    ValueError هنا يترجم لـ 404 في الراوتر (مش 500 ولا قائمة فاضية بصمت) —
    الحالة الواقعية دي بتحصل مع أي حساب مش موظف فعلياً (زي super_admin
    تجريبي)."""
    emp = crud.get_employee_by_user_id(db, user_id)
    if not emp:
        raise ValueError("لا يوجد ملف موظف مرتبط بحسابك — تواصل مع الموارد البشرية")
    return emp


def punch_in(db: Session, user_id: int) -> AttendanceRecord:
    emp = get_my_employee_or_404(db, user_id)
    # local_today (مش date.today()) — راجع تعليق timezone_utils.local_today:
    # date.today() بيثق في توقيت نظام تشغيل السيرفر، اللي غالبًا UTC على أي
    # VPS/سحابة حقيقية، مش Africa/Cairo. موظف يسجّل حضور بعد نص الليل بتوقيت
    # القاهرة كان ممكن يتسجّل على تاريخ اليوم اللي فات.
    today = local_today(settings.TIMEZONE)
    existing = crud.get_attendance_for_date(db, emp.id, today)
    if existing and existing.check_in:
        raise ValueError("تم تسجيل الحضور بالفعل النهاردة")
    record = crud.upsert_attendance(db, AttendanceRecordCreate(
        employee_id=emp.id, branch_id=emp.branch_id,
        record_date=today, check_in=datetime.utcnow(), status="present",
    ))
    db.commit()
    db.refresh(record)
    return record


def punch_out(db: Session, user_id: int) -> AttendanceRecord:
    emp = get_my_employee_or_404(db, user_id)
    today = local_today(settings.TIMEZONE)
    existing = crud.get_attendance_for_date(db, emp.id, today)
    if not existing or not existing.check_in:
        raise ValueError("لازم تسجّل الحضور الأول قبل تسجيل الانصراف")
    if existing.check_out:
        raise ValueError("تم تسجيل الانصراف بالفعل النهاردة")
    existing.check_out = datetime.utcnow()
    db.commit()
    db.refresh(existing)
    return existing


def calculate_employee_payroll(
    db: Session,
    employee_id: int,
    period_year: int,
    period_month: int,
    penalty_days: int = 0,
    unpaid_leave_days: int = 0,
    overtime_amount: Decimal = Decimal("0"),
    late_penalty_amount: Decimal = Decimal("0"),
) -> PayrollResultRead:
    emp = get_employee_or_404(db, employee_id)

    # ⚠️ لازم as_of = أول يوم في فترة الرواتب المطلوبة، مش "دلوقتي" — راجع
    # تعليق crud.get_active_si_config/get_active_tax_brackets: من غيره أي
    # تحديث تشريعي (SocialInsuranceConfig/TaxBracketConfig جديد) كان بيكسر
    # حساب كل الفترات (الماضية والحاضرة) فورًا، مش بس الفترات المستقبلية.
    period_start = date(period_year, period_month, 1)

    si_orm = crud.get_active_si_config(db, as_of=period_start)
    if not si_orm:
        raise ValueError("لا يوجد إعداد تأمينات اجتماعية نشط لهذه الفترة — أضف SocialInsuranceConfig في DB")

    brackets_orm = crud.get_active_tax_brackets(db, as_of=period_start)
    if not brackets_orm:
        raise ValueError("لا توجد شرائح ضريبية نشطة لهذه الفترة — أضف TaxBracketConfig في DB")

    si_config = SIConfig(
        max_insurable_salary=si_orm.max_insurable_salary,
        employee_rate=si_orm.employee_rate,
        employer_rate=si_orm.employer_rate,
        personal_exemption_annual=si_orm.personal_exemption_annual,
        effective_from=si_orm.effective_from,
    )
    tax_brackets = [
        TaxBracket(lower=b.lower_bound, upper=b.upper_bound, rate=b.rate)
        for b in brackets_orm
    ]

    allowances_orm = crud.list_allowances_for_employee(db, employee_id)
    allowances = [
        AllowanceDC(
            name=a.name,
            amount=a.amount,
            is_taxable=a.is_taxable,
            is_pensionable=a.is_pensionable,
        )
        for a in allowances_orm
    ]

    emp_input = EmployeePayrollInput(
        employee_id=emp.id,
        basic_salary=emp.basic_salary,
        allowances=allowances,
        overtime_amount=overtime_amount,
        penalty_days=penalty_days,
        late_penalty_amount=late_penalty_amount,
        unpaid_leave_days=unpaid_leave_days,
        hire_date=emp.hire_date,
        birth_date=emp.birth_date or emp.hire_date,
        period_month=date(period_year, period_month, 1),
    )

    result = calculate_payroll(emp_input, si_config, tax_brackets, si_orm.max_penalty_days_monthly)
    return PayrollResultRead(**result.__dict__)


def _compute_auto_attendance_adjustments(
    db: Session, emp: Employee, period_year: int, period_month: int,
    policy_orm: Optional[AttendancePolicy],
) -> tuple[Decimal, Decimal]:
    """يرجّع (overtime_amount, late_penalty_amount) محسوبة تلقائيًا من بصمات
    AttendanceRecord الفعلية للموظف خلال الفترة + سياسة حضور الفرع (policy_orm
    — تُجلب مرة واحدة في run_payroll_for_branch قبل الحلقة، مش لكل موظف، عشان
    مفيش داعي لاستعلام مطابق N مرة لنفس الفرع). دي "إضافة" فوق الحساب اليدوي/
    التأديبي الموجود أصلاً (EmployeePenalty)، مش شرط لتشغيل الرواتب — مفيش
    سياسة نشطة أو مفيش بصمات فعلية = (0, 0) بالظبط، ويفضل الراتب يتحسب عادي."""
    if not policy_orm:
        return Decimal("0"), Decimal("0")

    first_day = date(period_year, period_month, 1)
    last_day = date(period_year, period_month, calendar.monthrange(period_year, period_month)[1])

    records = crud.list_attendance_for_payroll_period(db, emp.id, first_day, last_day)
    if not records:
        return Decimal("0"), Decimal("0")

    shift_by_date = crud.map_rota_shifts_for_period(db, emp.id, first_day, last_day)

    punches = [
        AttendancePunch(
            record_date=r.record_date,
            check_in=r.check_in,
            check_out=r.check_out,
            shift_start=shift_by_date.get(r.record_date, (None, None))[0],
            shift_end=shift_by_date.get(r.record_date, (None, None))[1],
        )
        for r in records
    ]

    policy = AttendancePolicyConfig(
        late_grace_minutes=policy_orm.late_grace_minutes,
        early_leave_grace_minutes=policy_orm.early_leave_grace_minutes,
        standard_shift_start=policy_orm.standard_shift_start,
        standard_shift_end=policy_orm.standard_shift_end,
        overtime_rate_multiplier=policy_orm.overtime_rate_multiplier,
        late_penalty_rate_multiplier=policy_orm.late_penalty_rate_multiplier,
    )
    minutes_result = compute_attendance_minutes(punches, policy, tz_name=settings.TIMEZONE)
    shift_hours = standard_shift_hours(policy.standard_shift_start, policy.standard_shift_end)

    overtime_amount = attendance_minutes_to_amount(
        minutes_result.overtime_minutes, emp.basic_salary, shift_hours, policy.overtime_rate_multiplier,
    )
    late_penalty_amount = attendance_minutes_to_amount(
        minutes_result.late_minutes, emp.basic_salary, shift_hours, policy.late_penalty_rate_multiplier,
    )
    return overtime_amount, late_penalty_amount


def run_payroll_for_branch(
    db: Session,
    branch_id: int,
    period_year: int,
    period_month: int,
    requested_by: Optional[int] = None,
) -> PayrollRun:
    existing = crud.get_payroll_run_by_period(db, branch_id, period_year, period_month)
    if existing:
        raise ValueError(f"كشف رواتب {period_year}/{period_month} موجود مسبقاً (id={existing.id})")

    run = crud.create_payroll_run(
        db, PayrollRunCreate(branch_id=branch_id, period_year=period_year, period_month=period_month)
    )

    employees, _ = crud.list_employees(db, branch_id, status="active", limit=1000)
    policy_orm = crud.get_attendance_policy(db, branch_id)  # مرة واحدة للفرع، مش لكل موظف

    total_gross = Decimal("0")
    total_net   = Decimal("0")
    total_tax   = Decimal("0")
    total_si    = Decimal("0")

    period_str = f"{period_year}-{period_month:02d}"

    for emp in employees:
        # ⚠️ باج حقيقي: EmployeePenalty (POST /hr/penalties) كان بيتسجّل في
        # الداتابيز فعلاً، لكن run_payroll_for_branch كان بينادي
        # calculate_employee_payroll من غير ما يبعتله penalty_days خالص —
        # يعني قيمتها الافتراضية صفر دايمًا، فأي جزاء مسجّل لموظف كان بيُتجاهَل
        # تمامًا وقت تشغيل كشف الرواتب الفعلي (كان بيشتغل بس لو الأدمن كتب
        # الرقم يدويًا في GET /hr/employees/{id}/payslip?penalty_days=). دلوقتي
        # بنجمع جزاءات الشهر الفعلية المسجّلة للموظف ونبعتها فعليًا للحساب.
        penalties = crud.list_penalties(db, branch_id, employee_id=emp.id, month=period_str)
        penalty_days = sum(p.penalty_days for p in penalties)

        # حساب تلقائي جديد: overtime_amount/late_penalty_amount من بصمات
        # الحضور الفعلية + سياسة الفرع (لو موجودة) — يتخصم/يتضاف فوق الجزاءات
        # اليدوية فوق، مش بدلاً منها (راجع _compute_auto_attendance_adjustments).
        overtime_amount, late_penalty_amount = _compute_auto_attendance_adjustments(
            db, emp, period_year, period_month, policy_orm,
        )

        try:
            result = calculate_employee_payroll(
                db, emp.id, period_year, period_month,
                penalty_days=penalty_days,
                overtime_amount=overtime_amount,
                late_penalty_amount=late_penalty_amount,
            )
        except ValueError:
            continue  # تجاهل الموظفين الذين لا تتوفر لهم بيانات

        crud.create_payroll_line(db, run.id, {
            "employee_id":            emp.id,
            "basic_salary":           result.basic_salary,
            "gross_salary":           result.gross_salary,
            "net_salary":             result.net_salary,
            "employee_si":            result.employee_si,
            "employer_si":            result.employer_si,
            "monthly_tax":            result.monthly_tax,
            "penalty_deduction":      result.penalty_deduction,
            "late_penalty_deduction": result.late_penalty_deduction,
            "unpaid_leave_deduction": result.unpaid_leave_deduction,
            "journal_entry":          json.dumps(result.journal_entry, ensure_ascii=False),
        })

        total_gross += result.gross_salary
        total_net   += result.net_salary
        total_tax   += result.monthly_tax
        total_si    += result.employee_si

    run.total_gross = total_gross
    run.total_net   = total_net
    run.total_tax   = total_tax
    run.total_si    = total_si

    db.commit()
    db.refresh(run)
    return run


def approve_payroll_run(
    db: Session, run_id: int, approved_by: int
) -> PayrollRun:
    run = crud.get_payroll_run(db, run_id)
    if not run:
        raise ValueError(f"كشف الرواتب {run_id} غير موجود")
    if run.status != "draft":
        raise ValueError(f"لا يمكن اعتماد كشف بحالة '{run.status}'")
    run.status      = "approved"
    run.approved_by = approved_by
    run.approved_at = datetime.utcnow()
    db.flush()

    # ── قيد محاسبي مجمّع للرواتب ────────────────────────────────────
    _post_payroll_journal(db, run, approved_by)

    db.commit()
    db.refresh(run)
    return run


def _post_payroll_journal(db: Session, run: "PayrollRun", user_id: int) -> None:
    """يُنشئ قيد مزدوج مجمّع لكشف الرواتب المعتمد."""
    try:
        from app.modules.finance.crud import get_account_by_code, create_journal_entry  # noqa: PLC0415
        from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate  # noqa: PLC0415
    except ImportError:
        return  # Finance module not available

    # جلب الحسابات — نتجاهل القيد إذا لم تُوجد الحسابات
    accs: dict[str, int] = {}
    for code in ("5100", "5110", "2100", "2110", "2120"):
        acc = get_account_by_code(db, run.branch_id, code)
        if acc:
            accs[code] = acc.id

    if not accs:
        return  # لا حسابات مُعرَّفة — تجاوز القيد

    period_str = f"{run.period_year}-{run.period_month:02d}"
    lines: list[JournalLineCreate] = []

    # ⚠️ حساب "5110" (مصروف تأمينات صاحب عمل) متعمّد الاستبعاد هنا: PayrollRun
    # بيجمّع total_si من employee_si بس (راجع run_payroll_for_branch) — مفيش
    # عمود total_employer_si على الـ run لتخزين نصيب الشركة الفعلي (بمعدّل
    # employer_rate المختلف عن employee_rate). كان هنا كود قديم بيدبّت
    # run.total_si (SI الموظف) تحت مسمى "مصروف صاحب العمل" بدون أي قيد دائن
    # مقابل — ده كان بيكسر توازن القيد (مدين ≠ دائن) في أي مرة الحساب يكون
    # موجود فعلاً. اتشال لحد ما يُضاف عمود total_employer_si حقيقي (migration).
    if "5100" in accs and run.total_gross:
        lines.append(JournalLineCreate(
            account_id=accs["5100"],
            debit=run.total_gross,
            credit=Decimal("0"),
            description=f"مصروف رواتب {period_str}",
        ))
    if "2100" in accs and run.total_tax:
        lines.append(JournalLineCreate(
            account_id=accs["2100"],
            debit=Decimal("0"),
            credit=run.total_tax,
            description=f"ضريبة دخل مستحقة {period_str}",
        ))
    if "2110" in accs and run.total_si:
        lines.append(JournalLineCreate(
            account_id=accs["2110"],
            debit=Decimal("0"),
            credit=run.total_si,
            description=f"تأمينات اجتماعية مستحقة {period_str}",
        ))
    net_salaries = (run.total_net or Decimal("0"))
    if "2120" in accs and net_salaries:
        lines.append(JournalLineCreate(
            account_id=accs["2120"],
            debit=Decimal("0"),
            credit=net_salaries,
            description=f"صافي رواتب مستحقة {period_str}",
        ))

    if not lines:
        return

    entry_data = JournalEntryCreate(
        branch_id=run.branch_id,
        entry_date=date(run.period_year, run.period_month, 1),
        reference=f"PR-{run.period_year}-{run.period_month:02d}",
        description=f"رواتب {period_str}",
        source="payroll",
        source_id=run.id,
        lines=lines,
    )
    try:
        create_journal_entry(db, entry_data, user_id)
    except Exception:
        pass  # لا نوقف الاعتماد إذا فشل القيد


# ── Leave Management ──────────────────────────────────────────────────

def request_leave(
    db: Session,
    employee_id: int,
    branch_id: int,
    leave_type_id: int,
    start_date: "date",
    end_date: "date",
    reason: Optional[str] = None,
) -> LeaveRequest:
    days = (end_date - start_date).days + 1
    if days <= 0:
        raise ValueError("تاريخ نهاية الإجازة يجب أن يكون بعد تاريخ البداية")

    # تحقق من سلامة الموظف
    get_employee_or_404(db, employee_id)

    # تحقق اختياري من سلد الفعلية (إذا كان السجل موجوداً)
    balance = crud.get_leave_balance(db, employee_id, start_date.year)
    if balance and (balance.annual_taken + days) > balance.annual_entitled:
        raise ValueError(
            f"سلد الإجازات غير كافٍ — المتاح: {balance.annual_entitled - balance.annual_taken} يوم"
        )

    # تحقق من عدم تداخل المدى مع طلب إجازة تاني (معلّق أو معتمد) لنفس الموظف —
    # من غيره ممكن يبقى عند الموظف إجازتين معتمدتين لنفس اليوم في نفس الوقت.
    overlap = crud.get_overlapping_leave(db, employee_id, start_date, end_date)
    if overlap:
        raise ValueError(
            f"يوجد طلب إجازة آخر ({overlap.start_date} → {overlap.end_date}, "
            f"حالة: {overlap.status}) يتداخل مع المدى المطلوب"
        )

    req = crud.create_leave_request(
        db, employee_id, branch_id, leave_type_id, start_date, end_date, days, reason
    )
    db.commit()
    db.refresh(req)
    return req


def request_my_leave(
    db: Session,
    user_id: int,
    leave_type_id: int,
    start_date: "date",
    end_date: "date",
    reason: Optional[str] = None,
) -> LeaveRequest:
    """نسخة self-service من request_leave — بتشتق employee_id/branch_id من
    الموظف المرتبط بالمستخدم الحالي بدل ما تثق في جسم الطلب."""
    emp = get_my_employee_or_404(db, user_id)
    return request_leave(db, emp.id, emp.branch_id, leave_type_id, start_date, end_date, reason)


def approve_leave(
    db: Session, request_id: int, approved_by: int
) -> LeaveRequest:
    req = crud.get_leave_request(db, request_id)
    if not req:
        raise ValueError("طلب الإجازة غير موجود")
    if req.status != "pending":
        raise ValueError(f"الطلب في حالة '{req.status}' — لا يمكن اعتماده")

    # ⚠️ لا سماح بالاعتماد الذاتي: لو الموظف صاحب الطلب مرتبط بنفس حساب
    # الدخول اللي بيحاول يعتمد (approved_by = Employee.user_id)، ارفض. كان
    # مفيش أي تحقق هنا خالص — مدير مرتبط بموظف نفسه كان يقدر يعتمد إجازته
    # الخاصة عن طريق /hr/leaves/{id} أو /hr/leave-requests/{id}/approve.
    emp = get_employee_or_404(db, req.employee_id)
    if emp.user_id is not None and emp.user_id == approved_by:
        raise ValueError("لا يمكن للموظف اعتماد طلب إجازته الخاص — يلزم اعتماد مدير آخر")

    approved = crud.approve_leave_request(db, req, approved_by)

    # تحديث سلد الإجازات إذا كان الميزان موجوداً
    balance = crud.get_leave_balance(db, req.employee_id, req.start_date.year)
    if balance:
        balance.annual_taken += req.days_requested

    db.commit()
    db.refresh(approved)
    return approved


def generate_payslip_pdf(db: Session, run_id: int, employee_id: int) -> bytes:
    """PDF قسيمة راتب لموظف في كشف رواتب معين."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    run = crud.get_payroll_run(db, run_id)
    if not run:
        raise ValueError(f"كشف الرواتب {run_id} غير موجود")

    lines = crud.list_lines_for_run(db, run_id)
    line = next((l for l in lines if l.employee_id == employee_id), None)
    if not line:
        raise ValueError(f"الموظف {employee_id} غير موجود في هذا الكشف")

    emp = crud.get_employee(db, employee_id)
    emp_name = emp.full_name if emp else f"موظف #{employee_id}"

    period_str = f"{run.period_year}-{run.period_month:02d}"
    fields = [
        ("الموظف",              emp_name),
        ("الفترة",              period_str),
        ("المرتب الأساسي",      f"{line.basic_salary:,.2f} EGP"),
        ("الإجمالي",            f"{line.gross_salary:,.2f} EGP"),
        ("تأمينات الموظف",      f"{line.employee_si:,.2f} EGP"),
        ("ضريبة الدخل",         f"{line.monthly_tax:,.2f} EGP"),
    ]
    if line.penalty_deduction and line.penalty_deduction > 0:
        fields.append(("جزاءات", f"{line.penalty_deduction:,.2f} EGP"))
    if line.late_penalty_deduction and line.late_penalty_deduction > 0:
        fields.append(("خصم تأخير", f"{line.late_penalty_deduction:,.2f} EGP"))
    if line.unpaid_leave_deduction and line.unpaid_leave_deduction > 0:
        fields.append(("إجازة بدون أجر", f"{line.unpaid_leave_deduction:,.2f} EGP"))

    return builder.receipt_pdf(
        reference=f"PAY-{period_str}-{employee_id}",
        title="قسيمة راتب",
        fields=fields,
        total=float(line.net_salary),
        currency="EGP",
        note="الصافي للصرف — الخيمة بيتش ريزورت",
    )


def generate_payroll_excel(db: Session, run_id: int) -> bytes:
    """Excel كشف رواتب كامل."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    run = crud.get_payroll_run(db, run_id)
    if not run:
        raise ValueError(f"كشف الرواتب {run_id} غير موجود")

    lines = crud.list_lines_for_run(db, run_id)
    employees = {e.id: e for e in crud.list_employees(db, run.branch_id, limit=10000)[0]}

    def _employee_label(employee_id: int) -> str:
        emp = employees.get(employee_id)
        return emp.full_name if emp else f"#{employee_id}"

    period_str = f"{run.period_year}-{run.period_month:02d}"
    rows = [
        [
            _employee_label(l.employee_id),
            float(l.basic_salary),
            float(l.gross_salary),
            float(l.employee_si),
            float(l.monthly_tax),
            float(l.penalty_deduction or 0),
            float(l.late_penalty_deduction or 0),
            float(l.net_salary),
        ]
        for l in lines
    ]

    return builder.excel(
        sheets=[{
            "name": f"رواتب {period_str}",
            "headers": ["الموظف", "الأساسي", "الإجمالي", "تأمينات", "ضريبة", "جزاءات", "خصم تأخير", "الصافي"],
            "rows": rows,
            "col_types": ["text", "currency", "currency", "currency", "currency", "currency", "currency", "currency"],
            "summary": {
                "إجمالي الصافي": float(run.total_net or 0),
                "إجمالي الضريبة": float(run.total_tax or 0),
            },
        }],
        title=f"كشف رواتب {period_str}",
    )


def reject_leave(
    db: Session, request_id: int, reason: str
) -> LeaveRequest:
    req = crud.get_leave_request(db, request_id)
    if not req:
        raise ValueError("طلب الإجازة غير موجود")
    if req.status != "pending":
        raise ValueError(f"الطلب في حالة '{req.status}' — لا يمكن رفضه")

    rejected = crud.reject_leave_request(db, req, reason)
    db.commit()
    db.refresh(rejected)
    return rejected


def get_sales_leaderboard(
    db: Session, branch_id: int, date_from: date, date_to: date,
) -> list["LeaderboardEntry"]:
    """لوحة أداء الموظفين — إجمالي المبيعات الحقيقية لكل موظف عبر المطعم
    والكافيه والشاطئ خلال المدى المطلوب، مرتّبة من الأعلى مبيعًا. waiter_id/
    cashier_id في الطلبات هي User.id فعليًا (مش Employee.id) — بنربطها بجدول
    الموظفين عبر Employee.user_id عشان نعرض الاسم، ولو مفيش موظف مرتبط
    (حساب تجريبي مثلاً) بيتعرض برقم الحساب بس."""
    from app.modules.hr.schemas import LeaderboardEntry  # noqa: PLC0415
    from datetime import datetime as _dt  # noqa: PLC0415

    dt_from = _dt.combine(date_from, _dt.min.time())
    dt_to = _dt.combine(date_to, _dt.max.time())

    totals: dict[int, Decimal] = {}
    counts: dict[int, int] = {}

    def _accumulate(user_id: Optional[int], amount: Decimal):
        if not user_id:
            return
        totals[user_id] = totals.get(user_id, Decimal("0")) + amount
        counts[user_id] = counts.get(user_id, 0) + 1

    try:
        from app.modules.restaurant.models import Order  # noqa: PLC0415
        orders = db.query(Order).filter(
            Order.branch_id == branch_id, Order.status == "paid",
            Order.created_at >= dt_from, Order.created_at <= dt_to,
        ).all()
        for o in orders:
            _accumulate(o.waiter_id, o.total)
    except Exception:
        logger.warning("get_sales_performance: فشل جلب طلبات المطعم — branch=%s", branch_id, exc_info=True)

    try:
        from app.modules.cafe.models import CafeOrder  # noqa: PLC0415
        orders = db.query(CafeOrder).filter(
            CafeOrder.branch_id == branch_id, CafeOrder.status == "paid",
            CafeOrder.created_at >= dt_from, CafeOrder.created_at <= dt_to,
        ).all()
        for o in orders:
            _accumulate(o.waiter_id, o.total)
    except Exception:
        logger.warning("get_sales_performance: فشل جلب طلبات الكافيه — branch=%s", branch_id, exc_info=True)

    try:
        from app.modules.beach.models import BeachTransaction  # noqa: PLC0415
        txs = db.query(BeachTransaction).filter(
            BeachTransaction.branch_id == branch_id,
            BeachTransaction.tx_date >= date_from, BeachTransaction.tx_date <= date_to,
            BeachTransaction.voided_at.is_(None),
        ).all()
        for tx in txs:
            _accumulate(tx.cashier_id, tx.total_amount + tx.vat_amount)
    except Exception:
        logger.warning("get_sales_performance: فشل جلب معاملات الشاطئ — branch=%s", branch_id, exc_info=True)

    employees = {
        e.user_id: e for e in db.query(Employee).filter(Employee.user_id.in_(totals.keys())).all()
    } if totals else {}

    entries = [
        LeaderboardEntry(
            user_id=uid,
            employee_name=employees[uid].full_name if uid in employees else None,
            employee_code=employees[uid].employee_code if uid in employees else None,
            total_sales=amount,
            order_count=counts[uid],
        )
        for uid, amount in totals.items()
    ]
    entries.sort(key=lambda e: e.total_sales, reverse=True)
    return entries
