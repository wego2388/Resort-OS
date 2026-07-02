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
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple


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
    penalty_days: int = 0           # أيام الجزاءات
    unpaid_leave_days: int = 0      # أيام الإجازة بدون أجر
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
    unpaid_leave_deduction: Decimal

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
    # الأجر التأميني = min(أساسي + بدلات خاضعة للتأمين، الحد الأقصى)
    pensionable_gross = emp.basic_salary + pensionable_allowances
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

    # ─── إجازة بدون أجر ───────────────────────────────────────────────
    daily_rate = emp.basic_salary / Decimal("30")
    unpaid_leave_deduction = (daily_rate * Decimal(emp.unpaid_leave_days)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # ─── الصافي ───────────────────────────────────────────────────────
    net = (
        gross
        + non_taxable_allowances
        - employee_si
        - monthly_tax
        - penalty_deduction
        - unpaid_leave_deduction
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    period_str = emp.period_month.strftime("%Y-%m")

    # ─── القيد المحاسبي ───────────────────────────────────────────────
    journal_entry = {
        "description": f"رواتب شهر {period_str} — موظف {emp.employee_id}",
        "debits": [
            {"account": "مصروف رواتب",                   "amount": float(gross + non_taxable_allowances)},
            {"account": "مصروف تأمينات اجتماعية (صاحب عمل)", "amount": float(employer_si)},
        ],
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
        unpaid_leave_deduction=unpaid_leave_deduction,
        net_salary=net,
        journal_entry=journal_entry,
    )
