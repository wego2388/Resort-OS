"""
app/resort_os/hr_engine.py
═══════════════════════════════════════════════════════════════════════
Pure Domain Engine — حساب الراتب المصري
قانون العمل 12/2003 + ضريبة الدخل 91/2005 وتعديلاته

⚠️ لا أرقام hardcoded في هذا الـ engine.
   كل الحدود والنسب تأتي من SocialInsuranceConfig في DB.
   إذا أردت تغيير نسبة التأمين → عدّل في DB، لا في الكود.

Pure Domain: لا FastAPI، لا SQLAlchemy، لا app imports.
يعمل على plain dataclasses — قابل للاختبار بالكامل بدون DB.
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo


# ─────────────────── Config DTOs (من DB) ─────────────────────────────

@dataclass
class SocialInsuranceConfig:
    """
    يُمثّل جدول social_insurance_config في DB.
    يحتوي على الأرقام القانونية التي قد تتغير بتعديلات تشريعية.
    لا تعدّل هذا الـ dataclass — عدّل في DB وأعد تحميل البيانات.
    """
    max_insurable_salary: Decimal    # الحد الأقصى للأجر التأميني (كان 12,000 ورُفع لـ 14,000 عام 2024)
    employee_rate: Decimal           # نسبة تأمين الموظف (11%)
    employer_rate: Decimal           # نسبة تأمين صاحب العمل (18.75%)
    personal_exemption_annual: Decimal  # الإعفاء الشخصي السنوي (15,000)
    effective_from: date             # تاريخ سريان هذه الأرقام


@dataclass
class TaxBracket:
    """شريحة ضريبية واحدة."""
    lower: Decimal           # الحد الأدنى للشريحة
    upper: Decimal | None    # الحد الأقصى (None = غير محدد)
    rate: Decimal            # نسبة الضريبة (0.10 = 10%)


@dataclass
class Allowance:
    """بدل راتب."""
    name: str
    amount: Decimal
    is_taxable: bool      # خاضع لضريبة الدخل؟
    is_pensionable: bool  # خاضع للتأمينات الاجتماعية؟


@dataclass
class EmployeePayrollInput:
    """مدخلات حساب الراتب لموظف واحد."""
    employee_id: int
    basic_salary: Decimal
    allowances: list[Allowance] = field(default_factory=list)
    overtime_amount: Decimal = Decimal("0")
    penalty_days: int = 0           # أيام الجزاءات التأديبية اليدوية (مادة 69 — EmployeePenalty)
    late_penalty_amount: Decimal = Decimal("0")   # خصم تأخير محسوب تلقائيًا من الحضور — منفصل عن penalty_days
    unpaid_leave_days: int = 0      # أيام الإجازة بدون أجر
    # وعاء التأمينات الاجتماعية — لو None يُستخدم basic_salary (سلوك قديم
    # محفوظ). موجود لأن بعض الموظفين وعاءهم التأميني المسجّل أقل من راتبهم
    # الأساسي الفعلي (Employee.insurance_base_salary).
    insurance_base_salary: Decimal | None = None
    # مكافأة عيد ثابتة — غير خاضعة لضريبة الدخل ولا للتأمينات الاجتماعية،
    # بتُضاف مباشرة للصافي (Employee.holiday_bonus).
    holiday_bonus_amount: Decimal = Decimal("0")
    hire_date: date = field(default_factory=date.today)
    birth_date: date = field(default_factory=date.today)
    period_month: date = field(default_factory=date.today)


@dataclass
class PayrollResult:
    """نتيجة حساب الراتب."""
    employee_id: int
    period: str                         # YYYY-MM

    # المكونات
    basic_salary: Decimal
    taxable_allowances: Decimal
    non_taxable_allowances: Decimal
    overtime: Decimal
    gross_salary: Decimal               # = basic + taxable_allowances + overtime

    # التأمينات
    insurable_salary: Decimal           # = min(gross, max_insurable_salary)
    employee_si: Decimal                # = insurable × employee_rate
    employer_si: Decimal                # = insurable × employer_rate

    # الضريبة
    annual_taxable_base: Decimal        # = (gross × 12) − (employee_si × 12) − exemption
    annual_tax: Decimal
    monthly_tax: Decimal

    # الخصومات
    penalty_deduction: Decimal
    late_penalty_deduction: Decimal     # خصم تأخير تلقائي من الحضور (منفصل عن penalty_deduction اليدوي)
    unpaid_leave_deduction: Decimal

    # مكافأة العيد — غير خاضعة لضريبة/تأمينات، بند مستقل يُضاف للصافي مباشرة
    holiday_bonus: Decimal

    # الصافي
    net_salary: Decimal

    # للقيود المحاسبية
    journal_entry: dict = field(default_factory=dict)


# ─────────────────── Calculation Functions ───────────────────────────

def calculate_annual_tax(
    annual_taxable_base: Decimal,
    brackets: list[TaxBracket],
) -> Decimal:
    """
    يحسب ضريبة الدخل السنوية بالشرائح التصاعدية.

    مثال للشرائح (الأرقام تأتي من DB):
      0       → 15,000   : 0%
      15,001  → 30,000   : 10%
      30,001  → 45,000   : 15%
      45,001  → 60,000   : 20%
      60,001  → 200,000  : 22.5%
      200,001 → 400,000  : 25%
      400,001 → ∞        : 27.5%
    """
    if annual_taxable_base <= Decimal("0"):
        return Decimal("0")

    total_tax = Decimal("0")
    remaining = annual_taxable_base

    sorted_brackets = sorted(brackets, key=lambda b: b.lower)

    for bracket in sorted_brackets:
        if remaining <= Decimal("0"):
            break

        bracket_start = bracket.lower
        bracket_end = bracket.upper

        if annual_taxable_base <= bracket_start:
            break

        # الجزء الخاضع لهذه الشريحة
        if bracket_end is None:
            taxable_in_bracket = remaining
        else:
            bracket_size = bracket_end - bracket_start
            taxable_in_bracket = min(remaining, bracket_size)

        total_tax += taxable_in_bracket * bracket.rate
        remaining -= taxable_in_bracket

    return total_tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_penalty_deduction(
    basic_salary: Decimal,
    penalty_days: int,
    max_monthly_days: int,
) -> Decimal:
    """
    يحسب خصم الجزاءات.
    max_monthly_days: الحد القانوني (مادة 69 قانون العمل) — يأتي من DB
    """
    daily_rate = basic_salary / Decimal("30")
    actual_days = min(penalty_days, max_monthly_days)
    return (daily_rate * Decimal(actual_days)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def annual_leave_entitlement(hire_date: date, birth_date: date) -> int:
    """
    أيام الإجازة السنوية حسب قانون العمل مادة 47.
    30 يوم لـ: خدمة ≥ 10 سنوات أو عمر ≥ 50 سنة.
    21 يوم لغير ذلك.
    """
    today = date.today()
    years_of_service = (today - hire_date).days // 365
    age = (today - birth_date).days // 365
    return 30 if (years_of_service >= 10 or age >= 50) else 21


def calculate_gratuity(
    basic_salary: Decimal,
    hire_date: date,
    separation_type: str = "termination",
) -> Decimal:
    """
    مكافأة نهاية الخدمة — مادة 80 قانون العمل.

    separation_type:
      termination → شهر/سنة (100%)
      resignation_before_5y → ثلث المكافأة
      resignation_5_to_10y  → ثلثا المكافأة
      resignation_after_10y → شهر/سنة (100%)
    """
    years = (date.today() - hire_date).days // 365
    full_gratuity = basic_salary * Decimal(years)

    if separation_type == "termination":
        return full_gratuity
    if separation_type == "resignation_before_5y":
        return (full_gratuity / Decimal("3")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    if separation_type == "resignation_5_to_10y":
        return ((full_gratuity * Decimal("2")) / Decimal("3")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    # resignation_after_10y أو أي حالة أخرى
    return full_gratuity


# ─────────────────── Attendance → Payroll Conversion ──────────────────
#
# يحوّل بصمات حضور خام (check_in/check_out فعليين) لدقايق تأخير/أوفرتايم/
# انصراف مبكر، ثم لمبلغ مالي يغذّي calculate_payroll فوق. النظام قبل كده
# كان محتاج موظف بشري يحسب overtime_amount/penalty_days يدويًا لكل موظف
# لكل شهر — الكود ده هو الـ pipeline الناقص اللي بيربط AttendanceRecord
# (بصمات خام) بمحرك الرواتب تلقائيًا.

@dataclass
class AttendancePolicyConfig:
    """يمثّل جدول attendance_policies في DB — سياسة حضور فرع واحد."""
    late_grace_minutes: int              # دقايق سماح قبل ما التأخير "يُحسب"
    early_leave_grace_minutes: int        # دقايق سماح قبل ما الانصراف المبكر "يُحسب"
    standard_shift_start: str             # "HH:MM" — fallback لو مفيش RotaAssignment لليوم
    standard_shift_end: str               # "HH:MM"
    overtime_rate_multiplier: Decimal     # نسبة أجر الساعة الإضافية (مثلاً 1.5×)
    late_penalty_rate_multiplier: Decimal # نسبة خصم دقيقة التأخير (مثلاً 1.0×)


@dataclass
class AttendancePunch:
    """بصمة حضور يوم واحد لموظف — check_in/check_out فعليين (UTC naive، نفس
    تمثيل عمود AttendanceRecord بالداتابيز) + الوردية المتوقعة لليوم ده لو
    فيه RotaAssignment→Shift مضبوط (وإلا None فيستخدم fallback السياسة)."""
    record_date: date
    check_in: datetime | None = None
    check_out: datetime | None = None
    shift_start: str | None = None   # "HH:MM" من Shift.start_time الخاص باليوم ده لو موجود
    shift_end: str | None = None     # "HH:MM"


@dataclass
class AttendanceMinutesResult:
    """إجمالي دقايق التأخير/الأوفرتايم/الانصراف المبكر لموظف خلال فترة (شهر
    الرواتب عادةً) — بعد تطبيق سماحية السياسة. days_with_data للتشخيص فقط
    (كام يوم كان فيه بصمة فعلية اتحسبت، مش مستخدم في أي حساب مالي)."""
    late_minutes: int = 0
    early_leave_minutes: int = 0
    overtime_minutes: int = 0
    days_with_data: int = 0


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _local_wall_time_to_utc_naive(local_date: date, local_time: time, tz_name: str) -> datetime:
    """يحوّل تاريخ+وقت محلي (توقيت الفرع، مثلاً بداية وردية "08:00" بتوقيت
    القاهرة) لـ UTC naive — نفس تمثيل check_in/check_out المخزّنين بالداتابيز.

    ملحوظة: نفس أسلوب app.resort_os.timezone_utils.local_date_to_utc_range
    بالظبط (نقطة زمنية واحدة بدل مدى يوم كامل) — مش استيراد منه مباشرةً عشان
    الملف ده (hr_engine) متعمّد يفضل بدون أي import من app.* غير stdlib (راجع
    تعليق أعلى الملف)، فالتحويل بسيط بما يكفي إنه يتكرر هنا بأمان.
    """
    tz = ZoneInfo(tz_name)
    local_dt = datetime.combine(local_date, local_time, tzinfo=tz)
    return local_dt.astimezone(timezone.utc).replace(tzinfo=None)


def standard_shift_hours(shift_start: str, shift_end: str) -> Decimal:
    """يحسب طول الوردية بالساعات من "HH:MM"→"HH:MM"، مع التعامل مع الورديات
    الليلية العابرة لمنتصف الليل (مثلاً 22:00 → 06:00 = 8 ساعات)."""
    start = _parse_hhmm(shift_start)
    end = _parse_hhmm(shift_end)
    start_minutes = start.hour * 60 + start.minute
    end_minutes = end.hour * 60 + end.minute
    if end_minutes <= start_minutes:
        end_minutes += 24 * 60
    return (Decimal(end_minutes - start_minutes) / Decimal("60")).quantize(Decimal("0.01"))


def compute_attendance_minutes(
    punches: list[AttendancePunch],
    policy: AttendancePolicyConfig,
    tz_name: str = "Africa/Cairo",
) -> AttendanceMinutesResult:
    """يحسب إجمالي دقايق التأخير/الأوفرتايم/الانصراف المبكر لموظف عبر مجموعة
    بصمات (عادةً كل أيام شهر رواتب واحد)، بتطبيق سماحية السياسة (grace).

    قاعدة السماحية (grace) — **حد فاصل، مش خصم جزئي**: لو التأخير الفعلي ≤
    مدة السماح، صفر دقايق محسوبة تمامًا (مفيش "خصم جزئي" حتى لو قريب من
    الحد). لو تجاوز التأخير مدة السماح ولو بدقيقة واحدة، **كل** دقايق التأخير
    الفعلية تُحسب (مش بس الزيادة عن حد السماح) — ده نفس منطق أنظمة الحضور
    الشائعة في السوق المصري (نافذة تسامح، وبعدها التأخير كله بيتحاسب عليه).
    مثال: سماح 10 دقايق → تأخير 9 دقايق = صفر، تأخير 11 دقيقة = 11 دقيقة كاملة
    محسوبة (مش دقيقة واحدة بس).

    الأوفرتايم مفيهوش سماحية — أي دقيقة بعد نهاية الوردية المتوقعة تُحسب.
    """
    result = AttendanceMinutesResult()

    for punch in punches:
        if punch.check_in is None and punch.check_out is None:
            continue  # مفيش بصمة فعلية (غياب/إجازة/عطلة) — لا يوجد ما يُحسب

        start_str = punch.shift_start or policy.standard_shift_start
        end_str = punch.shift_end or policy.standard_shift_end

        expected_start = _local_wall_time_to_utc_naive(punch.record_date, _parse_hhmm(start_str), tz_name)
        expected_end = _local_wall_time_to_utc_naive(punch.record_date, _parse_hhmm(end_str), tz_name)
        if expected_end <= expected_start:
            expected_end += timedelta(days=1)  # وردية ليلية عابرة لمنتصف الليل

        result.days_with_data += 1

        if punch.check_in is not None:
            late_minutes = int((punch.check_in - expected_start).total_seconds() // 60)
            if late_minutes > policy.late_grace_minutes:
                result.late_minutes += late_minutes

        if punch.check_out is not None:
            early_minutes = int((expected_end - punch.check_out).total_seconds() // 60)
            if early_minutes > policy.early_leave_grace_minutes:
                result.early_leave_minutes += early_minutes

            overtime_minutes = int((punch.check_out - expected_end).total_seconds() // 60)
            if overtime_minutes > 0:
                result.overtime_minutes += overtime_minutes

    return result


def attendance_minutes_to_amount(
    minutes: int,
    basic_salary: Decimal,
    shift_hours: Decimal,
    rate_multiplier: Decimal,
) -> Decimal:
    """يحوّل عدد دقايق (تأخير أو أوفرتايم) لمبلغ مالي.

    hourly_rate = (basic_salary ÷ 30) ÷ shift_hours   — نفس اصطلاح daily_rate
    (basic_salary/30) المستخدم فعلاً في باقي الملف ده (calculate_penalty_deduction
    وخصم الإجازة بدون أجر)، مقسوم على طول الوردية القياسية للفرع.

    amount = (minutes ÷ 60) × hourly_rate × rate_multiplier
    """
    if minutes <= 0 or shift_hours <= 0:
        return Decimal("0.00")
    daily_rate = basic_salary / Decimal("30")
    hourly_rate = daily_rate / shift_hours
    amount = (Decimal(minutes) / Decimal("60")) * hourly_rate * rate_multiplier
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_payroll(
    emp: EmployeePayrollInput,
    si_config: SocialInsuranceConfig,
    tax_brackets: list[TaxBracket],
    max_penalty_days: int,
) -> PayrollResult:
    """
    الدالة الرئيسية — تحسب كل مكونات الراتب.

    Args:
        emp: مدخلات الموظف
        si_config: إعدادات التأمينات الاجتماعية (من DB)
        tax_brackets: شرائح ضريبة الدخل (من DB)
        max_penalty_days: الحد القانوني للجزاءات/شهر (من DB)
    """
    # ─── تصنيف البدلات ────────────────────────────────────────────────
    taxable_allowances = sum(
        (a.amount for a in emp.allowances if a.is_taxable), Decimal("0")
    )
    non_taxable_allowances = sum(
        (a.amount for a in emp.allowances if not a.is_taxable), Decimal("0")
    )
    pensionable_allowances = sum(
        (a.amount for a in emp.allowances if a.is_pensionable), Decimal("0")
    )

    # ─── الإجمالي ─────────────────────────────────────────────────────
    gross = emp.basic_salary + taxable_allowances + emp.overtime_amount

    # ─── التأمينات الاجتماعية ─────────────────────────────────────────
    # الأجر التأميني = min(وعاء التأمين + بدلات خاضعة للتأمين، الحد الأقصى).
    # وعاء التأمين = insurance_base_salary لو محدَّد (بعض الموظفين وعاءهم
    # التأميني المسجّل رسميًا أقل من راتبهم الأساسي الفعلي)، وإلا basic_salary
    # (السلوك القديم — كل الموظفين الحاليين من غير الحقل ده يتأثروش خالص).
    insurance_base = emp.insurance_base_salary if emp.insurance_base_salary is not None else emp.basic_salary
    pensionable_gross = insurance_base + pensionable_allowances
    insurable = min(pensionable_gross, si_config.max_insurable_salary)

    employee_si = (insurable * si_config.employee_rate).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    employer_si = (insurable * si_config.employer_rate).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # ─── وعاء الضريبة ─────────────────────────────────────────────────
    annual_gross = gross * Decimal("12")
    annual_si_deduction = employee_si * Decimal("12")
    annual_taxable_base = max(
        annual_gross - annual_si_deduction - si_config.personal_exemption_annual,
        Decimal("0"),
    )

    # ─── ضريبة الدخل ──────────────────────────────────────────────────
    annual_tax = calculate_annual_tax(annual_taxable_base, tax_brackets)
    monthly_tax = (annual_tax / Decimal("12")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # ─── الجزاءات ─────────────────────────────────────────────────────
    penalty_deduction = calculate_penalty_deduction(
        emp.basic_salary, emp.penalty_days, max_penalty_days
    )

    # ─── خصم التأخير التلقائي ─────────────────────────────────────────
    # محسوب مسبقًا (من دقايق التأخير الفعلية × نسبة الخصم — راجع
    # attendance_minutes_to_amount) — منفصل تمامًا عن penalty_deduction فوق
    # (جزاءات تأديبية يدوية بالأيام، مادة 69 قانون العمل). الاتنين بيتحسموا
    # مع بعض، مش أحدهما بدل الآخر.
    late_penalty_deduction = emp.late_penalty_amount.quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # ─── إجازة بدون أجر ───────────────────────────────────────────────
    daily_rate = emp.basic_salary / Decimal("30")
    unpaid_leave_deduction = (daily_rate * Decimal(emp.unpaid_leave_days)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # ─── مكافأة العيد ─────────────────────────────────────────────────
    # بند ثابت غير خاضع لضريبة/تأمينات (مش جزء من gross فوق عمدًا — لو
    # دخل annual_gross هيتفرض عليه ضريبة سنوية متكررة رغم إنه مبلغ موسمي
    # لمرة واحدة)، بيُضاف مباشرة للصافي زي non_taxable_allowances بالظبط.
    holiday_bonus = emp.holiday_bonus_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # ─── الصافي ───────────────────────────────────────────────────────
    net = (
        gross
        + non_taxable_allowances
        + holiday_bonus
        - employee_si
        - monthly_tax
        - penalty_deduction
        - late_penalty_deduction
        - unpaid_leave_deduction
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    period_str = emp.period_month.strftime("%Y-%m")

    # ─── القيد المحاسبي ───────────────────────────────────────────────
    debits = [
        {"account": "مصروف رواتب",                   "amount": float(gross + non_taxable_allowances)},
        {"account": "مصروف تأمينات اجتماعية (صاحب عمل)", "amount": float(employer_si)},
    ]
    if holiday_bonus > Decimal("0"):
        # سطر مدين مستقل — مضاف عشان المدين يفضل متوازن مع "صافي رواتب
        # مستحقة" تحت (اللي بيشمل holiday_bonus فعليًا عبر net فوق).
        debits.append({"account": "مصروف مكافأة عيد", "amount": float(holiday_bonus)})
    journal_entry = {
        "description": f"رواتب شهر {period_str} — موظف {emp.employee_id}",
        "debits": debits,
        "credits": [
            {"account": "ضريبة دخل مستحقة",               "amount": float(monthly_tax)},
            {"account": "تأمينات اجتماعية مستحقة",          "amount": float(employee_si + employer_si)},
            {"account": "صافي رواتب مستحقة",               "amount": float(net)},
        ],
    }

    return PayrollResult(
        employee_id=emp.employee_id,
        period=period_str,
        basic_salary=emp.basic_salary,
        taxable_allowances=taxable_allowances,
        non_taxable_allowances=non_taxable_allowances,
        overtime=emp.overtime_amount,
        gross_salary=gross,
        insurable_salary=insurable,
        employee_si=employee_si,
        employer_si=employer_si,
        annual_taxable_base=annual_taxable_base,
        annual_tax=annual_tax,
        monthly_tax=monthly_tax,
        penalty_deduction=penalty_deduction,
        late_penalty_deduction=late_penalty_deduction,
        unpaid_leave_deduction=unpaid_leave_deduction,
        holiday_bonus=holiday_bonus,
        net_salary=net,
        journal_entry=journal_entry,
    )
