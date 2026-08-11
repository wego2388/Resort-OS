"""app/modules/hr/services.py — Business logic"""
from __future__ import annotations

import calendar
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.hr import crud
from app.modules.hr.models import (
    AttendancePolicy, AttendanceRecord, Employee, LeaveRequest,
    PayrollRun, SocialInsuranceConfig, TaxBracketConfig,
)
from app.modules.hr.schemas import (
    AdvancePaymentCreate,
    AttendanceRecordCreate, EmployeeCreate, EmployeeUpdate,
    PayrollResultRead, PayrollRunCreate,
    SalaryAdvanceCreate,
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

if TYPE_CHECKING:
    from app.modules.hr.schemas import LeaderboardEntry

logger = logging.getLogger(__name__)


def get_employee_or_404(db: Session, employee_id: int) -> Employee:
    emp = crud.get_employee(db, employee_id)
    if not emp:
        raise ValueError(f"الموظف {employee_id} غير موجود")
    return emp


def create_employee(
    db: Session,
    data: EmployeeCreate,
    created_by: Optional[int] = None,
) -> Employee:
    if crud.get_employee_by_code(db, data.employee_code):
        raise ValueError(f"كود الموظف '{data.employee_code}' مستخدم مسبقاً")
    emp = crud.create_employee(db, data)
    db.flush()

    # Employee creation is the first half of the staff-onboarding workflow.
    # Keep an attributable event before the super-admin later provisions the
    # login identity and branch membership.
    from app.modules.core.crud import create_audit_log  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415
    create_audit_log(db, AuditLogCreate(
        user_id=created_by,
        branch_id=emp.branch_id,
        action="employee_record_created",
        entity_type="employee",
        entity_id=emp.id,
        new_data=json.dumps({
            "employee_code": emp.employee_code,
            "full_name": emp.full_name,
            "position": emp.position,
            "department": emp.department,
            "account_status": "pending",
        }, ensure_ascii=False, sort_keys=True),
    ))
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

    # ⚠️ باج حقيقي كان هنا (2026-08-03): تسجيل موظف "منتهي الخدمة" مالوش
    # أي أثر على حساب دخوله المرتبط (Employee.user_id) — الحساب كان بيفضل
    # نشط وقادر يسجّل دخول عادي بعد إنهاء الخدمة فعليًا. راجع CLAUDE.md §13
    # بند ❻: أي تغيير فعلي في is_active لازم revoke_user_tokens(). هنا
    # الإلغاء نطاقه أضيق عمدًا من core.services.update_user_role (اللي
    # مقفول على super_admin بحماية Gate 2A كاملة) — hr_manager مسموح له
    # يلغي حساب موظف مربوط بيه بس، ومش بيلمس role/is_active لأي حساب
    # super_admin خالص (دفاع إضافي ضد إنهاء خدمة "موظف" اتربط غلط بحساب
    # صلاحيات أعلى).
    just_terminated = (
        changes.get("status") == "terminated" and emp.status != "terminated" and emp.user_id
    )

    emp = crud.update_employee(db, emp, data)

    deactivated_user_id: Optional[int] = None
    if just_terminated:
        from app.core.kernel.models.user import User  # noqa: PLC0415
        from app.modules.core.crud import create_audit_log  # noqa: PLC0415
        from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415

        linked_user = db.query(User).filter(User.id == emp.user_id).first()
        if linked_user and linked_user.role != "super_admin" and linked_user.is_active:
            linked_user.is_active = False
            deactivated_user_id = linked_user.id
            create_audit_log(db, AuditLogCreate(
                user_id=updated_by, branch_id=emp.branch_id, action="deactivate_login_on_termination",
                entity_type="user", entity_id=linked_user.id,
                old_data='{"is_active": true}', new_data='{"is_active": false}',
            ))

    db.commit()
    db.refresh(emp)

    if deactivated_user_id is not None:
        from app.core.deps import revoke_user_tokens  # noqa: PLC0415
        revoke_user_tokens(deactivated_user_id)

    return emp


def link_employee_to_user(
    db: Session,
    emp: Employee,
    user_id: int,
    linked_by: Optional[int] = None,
) -> Employee:
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
    if linked_by is not None:
        from app.modules.core.crud import create_audit_log  # noqa: PLC0415
        from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415
        create_audit_log(db, AuditLogCreate(
            user_id=linked_by,
            branch_id=emp.branch_id,
            action="employee_account_linked",
            entity_type="employee",
            entity_id=emp.id,
            new_data=json.dumps({
                "user_id": user_id,
                "employee_code": emp.employee_code,
            }, ensure_ascii=False, sort_keys=True),
        ))
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


# ── Excel Attendance Import (wagdy.md H-07) ─────────────────────────────
# الحضور لسه بيتسجّل يدويًا في Excel (كشف "يوم بيوم" — عمود موظف + عمود لكل
# يوم في الشهر، وقيمة الخلية كود حالة p/v/u...) مش في النظام خالص. نفس نمط
# استيراد عقود الملكية الجزئية (timeshare.services.import_contracts_excel):
# openpyxl، لا dry-run، commit واحد في الآخر، أخطاء لكل صف/خلية بتتجمّع
# بدل ما توقف الاستيراد كله (errors[:20])، بس هنا upsert حقيقي (مش skip-on-
# duplicate) لأن AttendanceRecord عنده مفتاح طبيعي حقيقي (employee_id +
# record_date، UniqueConstraint فعلي) — إعادة رفع نفس الملف بعد تصحيح خانة
# لازم يحدّث السجل الموجود، مش يتجاهله.
_STATUS_CODE_MAP: dict[str, str] = {
    "p": "present", "present": "present", "حاضر": "present", "ح": "present",
    "u": "absent", "absent": "absent", "غياب": "absent", "غ": "absent", "a": "absent",
    "v": "leave", "leave": "leave", "اجازة": "leave", "إجازة": "leave",
    "late": "late", "متاخر": "late", "متأخر": "late",
    "h": "holiday", "holiday": "holiday", "عطلة": "holiday",
}


def _resolve_import_column_day(header: object) -> Optional[tuple[int, int, int] | int]:
    """يحلّل عنوان عمود يوم في ملف الحضور — إما رقم يوم خام (يُستخدم مع
    period_year/period_month اللي المدير اختارهم وقت الرفع) أو تاريخ كامل
    (openpyxl بيرجّعه date/datetime حقيقي لو الخلية متنسّقة كتاريخ في
    الإكسل) بيغلب period_year/period_month لنفس العمود ده تحديدًا. أي حاجة
    تانية (عمود اسم/ملاحظات) بترجع None وتتجاهل بصمت."""
    if isinstance(header, bool):
        return None
    if isinstance(header, (int, float)):
        return int(header)
    if isinstance(header, (date, datetime)):
        d = header.date() if isinstance(header, datetime) else header
        return (d.year, d.month, d.day)
    if isinstance(header, str) and header.strip().isdigit():
        return int(header.strip())
    return None


def import_attendance_excel(
    db: Session, branch_id: int, period_year: int, period_month: int, file_content: bytes,
):
    """wagdy.md H-07 — يحوّل ملف Excel (عمود موظف أول + عمود لكل يوم) لسجلات
    AttendanceRecord حقيقية. العمود الأول بيتقارن بـ employee_code أولاً
    (تطابق حرفي)، وإلا بالاسم الكامل (case-insensitive) داخل نفس الفرع."""
    import openpyxl  # noqa: PLC0415
    import io as _io  # noqa: PLC0415
    import calendar as _calendar  # noqa: PLC0415

    from app.modules.hr.schemas import AttendanceImportResult, AttendanceRecordCreate  # noqa: PLC0415

    wb = openpyxl.load_workbook(_io.BytesIO(file_content), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows or len(rows) < 2:
        raise ValueError("الملف فاضي")

    headers = rows[0]
    day_columns: list[tuple[int, object]] = []  # (col_index, resolved_day_info)
    for col_idx, header in enumerate(headers[1:], start=1):
        resolved = _resolve_import_column_day(header)
        if resolved is not None:
            day_columns.append((col_idx, resolved))

    if not day_columns:
        raise ValueError("لم يتم العثور على أي عمود يوم صالح (رقم يوم أو تاريخ) في الصف الأول")

    days_in_month = _calendar.monthrange(period_year, period_month)[1]

    imported = 0
    errors: list[str] = []
    unmatched: set[str] = set()

    for row_idx, row in enumerate(rows[1:], start=2):
        identifier = row[0] if row else None
        if identifier is None or str(identifier).strip() == "":
            continue  # صف فاضي/فاصل — يتجاهل بصمت

        identifier_str = str(identifier).strip()
        emp = crud.get_employee_by_code(db, identifier_str)
        if not emp or emp.branch_id != branch_id:
            emp = crud.get_employee_by_name(db, branch_id, identifier_str)
        if not emp:
            unmatched.add(identifier_str)
            continue

        for col_idx, day_info in day_columns:
            cell = row[col_idx] if col_idx < len(row) else None
            if cell is None or str(cell).strip() == "":
                continue  # مفيش بيانات لليوم ده — يوم مستقبلي غالبًا، يتجاهل

            try:
                if isinstance(day_info, tuple):
                    y, m, d = day_info
                else:
                    y, m, d = period_year, period_month, day_info
                    if d < 1 or d > days_in_month:
                        raise ValueError(f"رقم يوم غير صالح: {d}")

                status = _STATUS_CODE_MAP.get(str(cell).strip().lower())
                if not status:
                    raise ValueError(f"قيمة حالة غير معروفة: '{cell}'")

                crud.upsert_attendance(db, AttendanceRecordCreate(
                    employee_id=emp.id, branch_id=branch_id,
                    record_date=date(y, m, d), status=status,
                ))
                imported += 1
            except Exception as exc:
                if len(errors) < 20:
                    errors.append(f"صف {row_idx} ({identifier_str}), يوم {day_info}: {str(exc)[:120]}")

    db.commit()
    return AttendanceImportResult(
        imported=imported, errors=errors, unmatched_employees=sorted(unmatched),
    )


def calculate_employee_payroll(
    db: Session,
    employee_id: int,
    period_year: int,
    period_month: int,
    penalty_days: int = 0,
    unpaid_leave_days: int = 0,
    overtime_amount: Decimal = Decimal("0"),
    late_penalty_amount: Decimal = Decimal("0"),
    advance_deduction_amount: Decimal = Decimal("0"),
    si_config_orm: Optional[SocialInsuranceConfig] = None,
    tax_brackets_orm: Optional[list[TaxBracketConfig]] = None,
) -> PayrollResultRead:
    """si_config_orm/tax_brackets_orm — تحميل مسبق اختياري (N+1 fix): نفس
    التأمينات/الشرائح صحيحة لكل موظفي الفرع في نفس الفترة، فـ
    run_payroll_for_branch بيجيبهم مرة واحدة قبل حلقة الموظفين ويبعتهم هنا
    بدل ما كل موظف يعمل نفس الاستعلامين من جديد (كان ٢×عدد الموظفين استعلام
    زيادة على فرع فيه، مثلاً، 60 موظف). الاستدعاء المباشر (زي GET
    /hr/employees/{id}/payslip لموظف واحد) لسه بيجيب بنفسه زي الأول لو
    الباراميترين مش متمررين."""
    emp = get_employee_or_404(db, employee_id)

    # ⚠️ لازم as_of = أول يوم في فترة الرواتب المطلوبة، مش "دلوقتي" — راجع
    # تعليق crud.get_active_si_config/get_active_tax_brackets: من غيره أي
    # تحديث تشريعي (SocialInsuranceConfig/TaxBracketConfig جديد) كان بيكسر
    # حساب كل الفترات (الماضية والحاضرة) فورًا، مش بس الفترات المستقبلية.
    period_start = date(period_year, period_month, 1)

    si_orm = si_config_orm if si_config_orm is not None else crud.get_active_si_config(db, as_of=period_start)
    if not si_orm:
        raise ValueError("لا يوجد إعداد تأمينات اجتماعية نشط لهذه الفترة — أضف SocialInsuranceConfig في DB")

    brackets_orm = tax_brackets_orm if tax_brackets_orm is not None else crud.get_active_tax_brackets(db, as_of=period_start)
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
        insurance_base_salary=emp.insurance_base_salary,
        holiday_bonus_amount=emp.holiday_bonus,
        advance_deduction_amount=advance_deduction_amount,
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


def _compute_advance_deductions(
    db: Session, emp: Employee, period_year: int, period_month: int,
) -> tuple[Decimal, list, list]:
    """wagdy.md H-01/H-02 — يجمع (إجمالي الخصم, أقساط السلف النشطة اللي
    هتتخصم, دفعات الشهر اللي لسه ما اتخصمتش) لموظف/فترة. الإجمالي فقط هو
    اللي بيدخل حساب الراتب (hr_engine)؛ القوائم بترجع عشان run_payroll_for_
    branch يقدر يطبّق التغيير الفعلي (remaining_balance/deducted) بعد ما
    يتأكد إن سطر كشف الرواتب اتسجّل بنجاح — مش قبل كده."""
    advances = crud.list_active_advances_for_employee(db, emp.id)
    payments = crud.list_undeducted_payments_for_period(db, emp.id, period_year, period_month)

    total = Decimal("0")
    for adv in advances:
        deduct = min(adv.monthly_deduction_amount, adv.remaining_balance)
        total += deduct
    for payment in payments:
        total += payment.amount

    return total.quantize(Decimal("0.01")), advances, payments


def _cap_advance_deductions(
    requested_total: Decimal, cap: Decimal, advances: list, payments: list,
) -> tuple[Decimal, list[tuple], list]:
    """كل سلفة لوحدها كانت محدودة بـ remaining_balance بتاعها، لكن إجمالي عدة
    سلف/دفعات مع بعض مكانش له أي سقف — كان ممكن يدفع net_salary تحت الصفر
    (باج حقيقي اتكشف 2026-07-28). لو الإجمالي المطلوب أكبر من الصافي المتاح
    (cap = الصافي قبل خصم أي سلفة)، نوزّع المتاح بالأولوية: السلف أولاً
    (تخصيص جزئي مسموح، الباقي يفضل في remaining_balance لشهر جاي — بالظبط زي
    سلفة واحدة أكبر من رصيدها)، بعدين الدفعات (كل دفعة كاملة أو تفضل غير
    مخصومة لشهر جاي، مالهاش مفهوم تخصيص جزئي)."""
    remaining = max(cap, Decimal("0"))
    allocated_advances: list[tuple] = []
    for adv in advances:
        requested = min(adv.monthly_deduction_amount, adv.remaining_balance)
        take = min(requested, remaining)
        if take > Decimal("0"):
            allocated_advances.append((adv, take))
        remaining -= take

    allocated_payments = []
    for payment in payments:
        if payment.amount <= remaining:
            allocated_payments.append(payment)
            remaining -= payment.amount

    applied_total = (max(cap, Decimal("0")) - remaining).quantize(Decimal("0.01"))
    return applied_total, allocated_advances, allocated_payments


def _apply_advance_deductions(db: Session, advances: list[tuple], payments: list, payroll_line_id: int) -> None:
    """يطبّق فعليًا أثر الخصم المحسوب في _compute_advance_deductions/
    _cap_advance_deductions — بيتنادى بعد ما سطر كشف الرواتب يتسجّل بنجاح
    فقط (نفس الـ transaction، commit واحد في الآخر مع باقي
    run_payroll_for_branch). `advances` دايمًا (SalaryAdvance, deduct_amount)
    tuples — المبلغ الفعلي المطبَّق، ممكن يكون أقل من monthly_deduction_amount
    لو اتقصّ عن طريق _cap_advance_deductions."""
    for adv, deduct in advances:
        adv.remaining_balance -= deduct
        if adv.remaining_balance <= Decimal("0"):
            adv.remaining_balance = Decimal("0")
            adv.status = "settled"
    for payment in payments:
        payment.deducted = True
        payment.payroll_line_id = payroll_line_id


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

    # ⚡ N+1 fix (2026-07-29): التأمينات/الشرائح الضريبية ثابتة لكل موظفي
    # الفرع في نفس الفترة (مش بيانات خاصة بموظف)، وكانت بتتقرا من جديد جوه
    # calculate_employee_payroll لكل موظف (لحد مرتين لو عنده سلفة نشطة — راجع
    # _cap_advance_deductions تحت) بدل مرة واحدة للفرع كله، زي
    # policy_orm فوق بالظبط. لو مش موجودة، سيبها None وخلّي calculate_
    # employee_payroll يرفع نفس الـ ValueError القديم بنفسه لكل موظف (نفس
    # سلوك "تجاهل كل الموظفين" الأصلي، مش تغيير سلوك).
    period_start = date(period_year, period_month, 1)
    si_config_orm = crud.get_active_si_config(db, as_of=period_start)
    tax_brackets_orm = crud.get_active_tax_brackets(db, as_of=period_start) or None

    total_gross = Decimal("0")
    total_net   = Decimal("0")
    total_tax   = Decimal("0")
    total_si    = Decimal("0")
    total_holiday_bonus = Decimal("0")
    total_advance_deduction = Decimal("0")
    total_non_taxable_allowances = Decimal("0")

    period_str = f"{period_year}-{period_month:02d}"

    # ⚡ نفس فكرة الـN+1 fix فوق: جزاءات الشهر لكل موظفي الفرع بيتقروا باستعلام
    # واحد بدل استعلام لكل موظف داخل الحلقة، وبيتجمّعوا هنا حسب employee_id.
    penalties_by_employee: dict[int, int] = {}
    for penalty in crud.list_penalties(db, branch_id, month=period_str):
        penalties_by_employee[penalty.employee_id] = (
            penalties_by_employee.get(penalty.employee_id, 0) + penalty.penalty_days
        )

    # ⚠️ باج حقيقي كان هنا (اتصلح — نفس فئة باج penalty_days الموثّق فوق
    # بالظبط): LeaveRequest معتمدة (approve_leave) على LeaveType غير
    # مدفوعة (is_paid=False) عمرها ما كانت بتوصل لـ calculate_employee_
    # payroll خالص — unpaid_leave_days كانت بتفضل صفر دايمًا بغض النظر عن
    # أي إجازة غير مدفوعة معتمدة فعليًا، يعني unpaid_leave_deduction عمره
    # ما اتحسب في أي كشف رواتب حقيقي من أول ما الميزة دي اتعملت في
    # hr_engine. بنحسب هنا تقاطع كل طلب مع فترة الرواتب (الطلب ممكن يعبر
    # شهرين) ونجمعه لكل موظف، مرة واحدة للفرع كله قبل الحلقة.
    period_end = date(period_year, period_month, calendar.monthrange(period_year, period_month)[1])
    unpaid_leave_days_by_employee: dict[int, int] = {}
    for leave in crud.list_approved_unpaid_leave_requests(db, branch_id):
        overlap_start = max(leave.start_date, period_start)
        overlap_end = min(leave.end_date, period_end)
        if overlap_start <= overlap_end:
            days = (overlap_end - overlap_start).days + 1
            unpaid_leave_days_by_employee[leave.employee_id] = (
                unpaid_leave_days_by_employee.get(leave.employee_id, 0) + days
            )

    for emp in employees:
        # ⚠️ باج حقيقي: EmployeePenalty (POST /hr/penalties) كان بيتسجّل في
        # الداتابيز فعلاً، لكن run_payroll_for_branch كان بينادي
        # calculate_employee_payroll من غير ما يبعتله penalty_days خالص —
        # يعني قيمتها الافتراضية صفر دايمًا، فأي جزاء مسجّل لموظف كان بيُتجاهَل
        # تمامًا وقت تشغيل كشف الرواتب الفعلي (كان بيشتغل بس لو الأدمن كتب
        # الرقم يدويًا في GET /hr/employees/{id}/payslip?penalty_days=). دلوقتي
        # بنجمع جزاءات الشهر الفعلية المسجّلة للموظف ونبعتها فعليًا للحساب.
        penalty_days = penalties_by_employee.get(emp.id, 0)
        unpaid_leave_days = unpaid_leave_days_by_employee.get(emp.id, 0)

        # حساب تلقائي جديد: overtime_amount/late_penalty_amount من بصمات
        # الحضور الفعلية + سياسة الفرع (لو موجودة) — يتخصم/يتضاف فوق الجزاءات
        # اليدوية فوق، مش بدلاً منها (راجع _compute_auto_attendance_adjustments).
        overtime_amount, late_penalty_amount = _compute_auto_attendance_adjustments(
            db, emp, period_year, period_month, policy_orm,
        )

        # wagdy.md H-01/H-02 — أقساط سلف نشطة + دفعات الشهر غير المخصومة بعد.
        advance_deduction_amount, active_advances, undeducted_payments = _compute_advance_deductions(
            db, emp, period_year, period_month,
        )

        try:
            if advance_deduction_amount > Decimal("0"):
                # نحسب الصافي *قبل* خصم أي سلفة أولاً، عشان نعرف نقص إجمالي
                # السلف/الدفعات لو هيدفع الصافي تحت الصفر (راجع تعليق
                # _cap_advance_deductions فوق).
                net_before_advances = calculate_employee_payroll(
                    db, emp.id, period_year, period_month,
                    penalty_days=penalty_days,
                    unpaid_leave_days=unpaid_leave_days,
                    overtime_amount=overtime_amount,
                    late_penalty_amount=late_penalty_amount,
                    advance_deduction_amount=Decimal("0"),
                    si_config_orm=si_config_orm, tax_brackets_orm=tax_brackets_orm,
                ).net_salary
                if advance_deduction_amount > net_before_advances:
                    advance_deduction_amount, active_advances, undeducted_payments = _cap_advance_deductions(
                        advance_deduction_amount, net_before_advances, active_advances, undeducted_payments,
                    )
                else:
                    active_advances = [
                        (adv, min(adv.monthly_deduction_amount, adv.remaining_balance))
                        for adv in active_advances
                    ]
            else:
                active_advances = []

            result = calculate_employee_payroll(
                db, emp.id, period_year, period_month,
                penalty_days=penalty_days,
                unpaid_leave_days=unpaid_leave_days,
                overtime_amount=overtime_amount,
                late_penalty_amount=late_penalty_amount,
                advance_deduction_amount=advance_deduction_amount,
                si_config_orm=si_config_orm, tax_brackets_orm=tax_brackets_orm,
            )
        except ValueError:
            continue  # تجاهل الموظفين الذين لا تتوفر لهم بيانات

        line = crud.create_payroll_line(db, run.id, {
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
            "holiday_bonus":          result.holiday_bonus,
            "advance_deduction":      result.advance_deduction,
            "non_taxable_allowances": result.non_taxable_allowances,
            "journal_entry":          json.dumps(result.journal_entry, ensure_ascii=False),
        })
        # الرصيد الفعلي (SalaryAdvance.remaining_balance/AdvancePayment.deducted)
        # يتحدّث بس دلوقتي — بعد ما السطر يتسجّل بنجاح، مش قبله.
        _apply_advance_deductions(db, active_advances, undeducted_payments, line.id)

        total_gross += result.gross_salary
        total_net   += result.net_salary
        total_tax   += result.monthly_tax
        total_si    += result.employee_si
        total_holiday_bonus += result.holiday_bonus
        total_advance_deduction += result.advance_deduction
        total_non_taxable_allowances += result.non_taxable_allowances

    run.total_gross = total_gross
    run.total_net   = total_net
    run.total_tax   = total_tax
    run.total_si    = total_si
    run.total_holiday_bonus = total_holiday_bonus
    run.total_advance_deduction = total_advance_deduction
    run.total_non_taxable_allowances = total_non_taxable_allowances

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
    """يُنشئ قيد مزدوج مجمّع لكشف الرواتب المعتمد.

    ⚠️ باج محاسبي حقيقي كان هنا (اتصلح، OPS-DATA-02 §12 Phase 6): القيد كان
    فعليًا **غير متوازن** (مدين ≠ دائن) في أي كشف فيه أي خصم من
    penalty_deduction/late_penalty_deduction/unpaid_leave_deduction/
    advance_deduction — كل الخصومات دي بتقلل total_net (وبالتالي سطر الدائن
    "صافي رواتب مستحقة") من غير أي سطر مدين مقابل يوازنها. اتصلح بتفريق
    نوعين:
    1. penalty/late_penalty/unpaid_leave — تقليل حقيقي في مصروف الرواتب
       (الموظف كسب أقل فعليًا)، فبيقلّلوا سطر المدين "مصروف رواتب" نفسه.
    2. advance_deduction — سداد سلفة سابقة (ذمة مستحقة على الموظف، مش تقليل
       فيما كسبه)، فبيترحّل كسطر دائن منفصل لحساب أصول "سلف موظفين مستحقة"
       (1180) بدل ما يفضل جزء ضايع من المعادلة — راجع create_salary_advance/
       create_advance_payment تحت اللي بيرحّلوا الطرف التاني (Dr 1180 وقت
       الصرف الفعلي)."""
    try:
        from app.modules.finance.crud import get_account_by_code, create_journal_entry  # noqa: PLC0415
        from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate  # noqa: PLC0415
    except ImportError:
        return  # Finance module not available

    # جلب الحسابات — نتجاهل القيد إذا لم تُوجد الحسابات
    accs: dict[str, int] = {}
    for code in ("5100", "5110", "2100", "2110", "2120", "1180"):
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
    # مكافآت الأعياد (total_holiday_bonus) وnon_taxable_allowances (بدلات
    # مواصلات/سكن) مضافين هنا لنفس حساب "مصروف رواتب" — الاتنين مستبعدين من
    # total_gross نفسه (راجع hr_engine.calculate_payroll: gross_salary =
    # basic + taxable_allowances + overtime بس)، لكن لازم يدخلوا المدين هنا
    # عشان يفضلوا متوازنين مع "صافي رواتب مستحقة" تحت (اللي total_net
    # بتاعه بيشملهم الاتنين فعليًا — راجع صيغة `net` في hr_engine.calculate_
    # employee_payroll). ⚠️ باج محاسبي حقيقي كان هنا اتصلح: non_taxable_
    # allowances مكانش بيتضاف هنا خالص (وعمود total_non_taxable_allowances
    # نفسه مكانش موجود على PayrollRun) — يعني أي كشف فيه موظف عنده بدل غير
    # خاضع (مواصلات/سكن) كان بيرحّل قيد غير متوازن فعليًا (دائن > مدين
    # بالظبط بقيمة إجمالي البدلات)، اتأكد حي على Postgres حقيقي بفرق 500
    # جنيه في seed data واقعية. hr_engine.calculate_employee_payroll نفسه
    # كان بالفعل بيبني journal_entry مرجعي صح (Dr "مصروف رواتب" = gross +
    # non_taxable_allowances، مخزّن في PayrollLine.journal_entry) — بس
    # _post_payroll_journal هنا (القيد المجمّع الفعلي اللي بيترحّل للدفتر)
    # كان بيعيد حساب المدين من عمودين run-level بس (total_gross/total_
    # holiday_bonus) من غير ما يشوف الـ non_taxable_allowances خالص.
    #
    # خصومات penalty/late_penalty/unpaid_leave مفيهاش عمود إجمالي على مستوى
    # الـ run (بعكس total_advance_deduction) — بتتجمّع من سطور الكشف مباشرة.
    forfeited_earnings = sum(
        (l.penalty_deduction or Decimal("0"))
        + (l.late_penalty_deduction or Decimal("0"))
        + (l.unpaid_leave_deduction or Decimal("0"))
        for l in run.lines
    )
    gross_debit = (
        (run.total_gross or Decimal("0"))
        + (run.total_holiday_bonus or Decimal("0"))
        + (run.total_non_taxable_allowances or Decimal("0"))
        - forfeited_earnings
    )
    if "5100" in accs and gross_debit:
        lines.append(JournalLineCreate(
            account_id=accs["5100"],
            debit=gross_debit,
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
    advance_total = run.total_advance_deduction or Decimal("0")
    if "1180" in accs and advance_total:
        lines.append(JournalLineCreate(
            account_id=accs["1180"],
            debit=Decimal("0"),
            credit=advance_total,
            description=f"سداد سلف موظفين عبر الراتب {period_str}",
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
    # ⚠️ Finance-first (CLAUDE.md §5.2): فشل القيد يرفع — approve_payroll_run
    # يلفّ الاستدعاء كله في transaction واحد مع db.flush() قبل هنا، فأي
    # استثناء هنا سيُفقد التغييرات (run.status = "approved") تلقائيًا.
    # لو الحسابات غير مهيّأة للفرع: FinancialConfigurationError → ValueError
    # في approve_payroll_run → 400 للواجهة (لا commit، لا approved run).
    create_journal_entry(db, entry_data, user_id)


# ── SalaryAdvance (wagdy.md H-01) ────────────────────────────────────────

def create_salary_advance(db: Session, data: SalaryAdvanceCreate, created_by: int):
    get_employee_or_404(db, data.employee_id)
    if data.monthly_deduction_amount > data.amount:
        raise ValueError("القسط الشهري لا يمكن أن يكون أكبر من مبلغ السلفة نفسه")
    try:
        advance = crud.create_salary_advance(db, data, created_by)
        # strict=True (2026-08-11): صرف سلفة من غير قيد محاسبي مقابل (حساب
        # مش معرَّف للفرع، مثلاً) لازم يفشل كامل — راجع §4.
        _post_advance_disbursement_journal(db, data.branch_id, advance.id, "salary_advance", data.amount, created_by)
        db.commit()
        db.refresh(advance)
        return advance
    except Exception:
        db.rollback()
        raise


def _post_advance_disbursement_journal(
    db: Session, branch_id: int, source_id: int, source_kind: str,
    amount: Decimal, created_by: int,
) -> None:
    """Dr سلف موظفين مستحقة (1180) / Cr الصندوق (1100) — عند الصرف الفعلي
    (نقدية بتخرج فعليًا للموظف). الطرف المقابل بيترحّل لاحقًا كسطر دائن
    منفصل جوه _post_payroll_journal وقت خصم القسط من الراتب (سداد الذمة، مش
    تقليل مصروف الرواتب — راجع docstring _post_payroll_journal)."""
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import local_today  # noqa: PLC0415
    from app.core.config import settings  # noqa: PLC0415

    post_simple_revenue_journal(
        db, branch_id, local_today(settings.TIMEZONE),
        debit_account_code="1180", credit_account_code="1100",
        amount=amount,
        reference=f"HR-ADV-{source_kind}-{source_id:06d}",
        description="صرف سلفة موظف",
        source="payroll_advance", source_id=source_id,
        created_by=created_by,
        strict=True, commit_cost_centers=False,
    )


def _post_advance_cancellation_journal(
    db: Session,
    advance_id: int,
    branch_id: int,
    amount: Decimal,
    cancelled_by: int,
) -> None:
    """Reverse the untouched advance: Dr cash 1100 / Cr receivable 1180."""
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db,
        branch_id,
        local_today(settings.TIMEZONE),
        debit_account_code="1100",
        credit_account_code="1180",
        amount=amount,
        reference=f"HR-ADV-CANCEL-{advance_id:06d}",
        description="إلغاء وصرف عكسي لسلفة موظف",
        source="payroll_advance_cancel",
        source_id=advance_id,
        created_by=cancelled_by,
        strict=True,
        commit_cost_centers=False,
    )


def cancel_salary_advance(
    db: Session,
    advance_id: int,
    reason: Optional[str] = None,
    *,
    cancelled_by: int,
):
    """Cancel an untouched advance and reverse its disbursement atomically."""
    if cancelled_by <= 0:
        raise ValueError("المستخدم المنفذ لإلغاء السلفة مطلوب")
    try:
        advance = crud.lock_salary_advance_for_update(db, advance_id)
        if not advance:
            raise ValueError(f"السلفة {advance_id} غير موجودة")
        if advance.status != "active":
            raise ValueError(f"السلفة في حالة '{advance.status}' ولا يمكن إلغاؤها")
        if advance.remaining_balance != advance.amount:
            raise ValueError("لا يمكن إلغاء سلفة تم خصم أقساط منها بالفعل")

        advance.status = "cancelled"
        advance.cancelled_by = cancelled_by
        advance.cancelled_at = datetime.utcnow()
        if reason:
            advance.notes = f"{advance.notes or ''}\n[إلغاء] {reason}".strip()

        _post_advance_cancellation_journal(
            db,
            advance.id,
            advance.branch_id,
            advance.amount,
            cancelled_by,
        )
        db.commit()
        db.refresh(advance)
        return advance
    except Exception:
        db.rollback()
        raise


# ── AdvancePayment (wagdy.md H-02) ───────────────────────────────────────

def create_advance_payment(db: Session, data: AdvancePaymentCreate, recorded_by: int):
    get_employee_or_404(db, data.employee_id)
    try:
        payment = crud.create_advance_payment(db, data, recorded_by)
        _post_advance_disbursement_journal(db, data.branch_id, payment.id, "advance_payment", data.amount, recorded_by)
        db.commit()
        db.refresh(payment)
        return payment
    except Exception:
        db.rollback()
        raise


# ── LeaveBalanceMonthly (wagdy.md H-03) ──────────────────────────────────

def accrue_monthly_leave_balance(
    db: Session, employee_id: int, branch_id: int, period_year: int, period_month: int,
    monthly_rate: Decimal = Decimal("7.5"),
):
    """يستحق 7.5 يوم إجازة للموظف للشهر ده، بيخصم منها أيام الإجازة
    المعتمدة اللي بدايتها وقعت في نفس الشهر، ويرحّل الرصيد الختامي للشهر
    اللي فات كرصيد افتتاحي (راجع LeaveBalanceMonthly.__doc__ للفرق عن
    LeaveBalance.annual_entitled القانوني). يُستدعى شهريًا من
    app.tasks.hr_tasks.accrue_monthly_leave_ledger لكل موظف نشط."""
    previous = crud.get_latest_leave_balance_monthly(db, employee_id)
    opening_balance = previous.closing_balance if previous else Decimal("0")

    first_day = date(period_year, period_month, 1)
    last_day = date(period_year, period_month, calendar.monthrange(period_year, period_month)[1])
    approved_leaves = crud.list_leave_requests(
        db, branch_id, employee_id=employee_id, status="approved",
        limit=200,
    )[0]
    consumed = sum(
        (Decimal(str(lr.days_requested)) for lr in approved_leaves
         if first_day <= lr.start_date <= last_day),
        Decimal("0"),
    )

    row = crud.upsert_leave_balance_monthly(
        db, employee_id, branch_id, period_year, period_month,
        opening_balance=opening_balance, accrued=monthly_rate, consumed=consumed,
    )
    db.commit()
    db.refresh(row)
    return row


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
    line = next((ln for ln in lines if ln.employee_id == employee_id), None)
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


def generate_bulk_payroll_pdf(db: Session, run_id: int) -> bytes:
    """PDF كشف مرتبات جماعي — جدول بكل الموظفين في صفحة واحدة أو أكثر.
    H-06 من wagdy.md — للمحاسب لطباعة الكشف الرسمي بدل Excel."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    run = crud.get_payroll_run(db, run_id)
    if not run:
        raise ValueError(f"كشف الرواتب {run_id} غير موجود")

    lines = crud.list_lines_for_run(db, run_id)
    employees = {e.id: e for e in crud.list_employees(db, run.branch_id, limit=10000)[0]}

    period_str = f"{run.period_year}-{run.period_month:02d}"
    rows = []
    for ln in lines:
        emp = employees.get(ln.employee_id)
        rows.append([
            emp.full_name if emp else f"#{ln.employee_id}",
            f"{ln.basic_salary:,.0f}",
            f"{ln.gross_salary:,.0f}",
            f"{ln.employee_si:,.0f}",
            f"{ln.monthly_tax:,.0f}",
            f"{(ln.penalty_deduction or 0) + (ln.late_penalty_deduction or 0):,.0f}",
            f"{ln.advance_deduction or 0:,.0f}",
            f"{ln.net_salary:,.2f}",
        ])

    headers = ["الموظف", "الأساسي", "الإجمالي", "تأمينات", "ضريبة", "جزاءات", "سلف", "الصافي"]

    return builder.table_pdf(
        title=f"كشف مرتبات — {period_str}",
        subtitle=f"إجمالي صافي: {float(run.total_net or 0):,.2f} EGP  |  عدد الموظفين: {len(rows)}",
        headers=headers,
        rows=rows,
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
            _employee_label(ln.employee_id),
            float(ln.basic_salary),
            float(ln.gross_salary),
            float(ln.employee_si),
            float(ln.monthly_tax),
            float(ln.penalty_deduction or 0),
            float(ln.late_penalty_deduction or 0),
            float(ln.net_salary),
        ]
        for ln in lines
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
        # dining.DiningOrder بدل restaurant.Order/cafe.CafeOrder المنفصلين
        # (DINING_CUTOVER_PLAN.md D-05) — نفس استعلام واحد يغطي المطعم
        # والكافيه معًا (مفيش فرق فعلي هنا، اللوحة بتجمّع الاتنين على أي حال).
        from app.modules.dining.models import DiningOrder  # noqa: PLC0415
        orders = db.query(DiningOrder).filter(
            DiningOrder.branch_id == branch_id, DiningOrder.status == "paid",
            DiningOrder.created_at >= dt_from, DiningOrder.created_at <= dt_to,
        ).all()
        for o in orders:
            _accumulate(o.waiter_id, o.total)
    except Exception:
        logger.warning("get_sales_performance: فشل جلب طلبات الدايننج — branch=%s", branch_id, exc_info=True)

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
