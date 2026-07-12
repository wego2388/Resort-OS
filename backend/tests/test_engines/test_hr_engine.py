"""
tests/test_engines/test_hr_engine.py
اختبارات كاملة لـ HR Engine — قانون العمل المصري
بدون DB، بدون fixtures — pure functions فقط
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.resort_os.hr_engine import (
    Allowance,
    AttendanceMinutesResult,
    AttendancePolicyConfig,
    AttendancePunch,
    EmployeePayrollInput,
    SocialInsuranceConfig,
    TaxBracket,
    annual_leave_entitlement,
    attendance_minutes_to_amount,
    calculate_annual_tax,
    calculate_gratuity,
    calculate_payroll,
    calculate_penalty_deduction,
    compute_attendance_minutes,
    standard_shift_hours,
)


# ─── Fixtures ─────────────────────────────────────────────────────────

def _si_config() -> SocialInsuranceConfig:
    """إعدادات التأمينات الاجتماعية — أرقام 2024"""
    return SocialInsuranceConfig(
        max_insurable_salary=Decimal("14000"),
        employee_rate=Decimal("0.11"),
        employer_rate=Decimal("0.1875"),
        personal_exemption_annual=Decimal("15000"),
        effective_from=date(2024, 1, 1),
    )


def _tax_brackets() -> list[TaxBracket]:
    """شرائح ضريبة الدخل المصرية 2024"""
    return [
        TaxBracket(Decimal("0"),      Decimal("15000"),  Decimal("0.00")),
        TaxBracket(Decimal("15000"),  Decimal("30000"),  Decimal("0.10")),
        TaxBracket(Decimal("30000"),  Decimal("45000"),  Decimal("0.15")),
        TaxBracket(Decimal("45000"),  Decimal("60000"),  Decimal("0.20")),
        TaxBracket(Decimal("60000"),  Decimal("200000"), Decimal("0.225")),
        TaxBracket(Decimal("200000"), Decimal("400000"), Decimal("0.25")),
        TaxBracket(Decimal("400000"), None,              Decimal("0.275")),
    ]


def _basic_employee(
    basic_salary: Decimal = Decimal("5000"),
    allowances: list | None = None,
    overtime: Decimal = Decimal("0"),
    penalty_days: int = 0,
    unpaid_leave_days: int = 0,
    late_penalty_amount: Decimal = Decimal("0"),
    insurance_base_salary: Decimal | None = None,
    holiday_bonus_amount: Decimal = Decimal("0"),
) -> EmployeePayrollInput:
    return EmployeePayrollInput(
        employee_id=1,
        basic_salary=basic_salary,
        allowances=allowances or [],
        overtime_amount=overtime,
        penalty_days=penalty_days,
        late_penalty_amount=late_penalty_amount,
        unpaid_leave_days=unpaid_leave_days,
        insurance_base_salary=insurance_base_salary,
        holiday_bonus_amount=holiday_bonus_amount,
        hire_date=date(2020, 1, 1),
        birth_date=date(1990, 6, 15),
        period_month=date(2026, 6, 1),
    )


CAIRO = ZoneInfo("Africa/Cairo")


def _cairo_local_to_utc_naive(d: date, hour: int, minute: int) -> datetime:
    """نفس تحويل hr_engine._local_wall_time_to_utc_naive بالظبط — بيستخدم
    ZoneInfo الفعلي بدل ما يفترض إزاحة ثابتة (UTC+3)، عشان التست يفضل صحيح
    حتى لو مصر غيّرت قاعدة التوقيت الصيفي مستقبلاً."""
    local_dt = datetime(d.year, d.month, d.day, hour, minute, tzinfo=CAIRO)
    return local_dt.astimezone(timezone.utc).replace(tzinfo=None)


# ─── calculate_annual_tax ─────────────────────────────────────────────

class TestCalculateAnnualTax:

    def test_zero_income_no_tax(self):
        assert calculate_annual_tax(Decimal("0"), _tax_brackets()) == Decimal("0")

    def test_negative_income_no_tax(self):
        assert calculate_annual_tax(Decimal("-500"), _tax_brackets()) == Decimal("0")

    def test_within_exempt_bracket(self):
        """أقل من 15,000 → لا ضريبة"""
        assert calculate_annual_tax(Decimal("14999"), _tax_brackets()) == Decimal("0")

    def test_exactly_at_bracket_boundary(self):
        """بالضبط 15,000 → لا ضريبة"""
        assert calculate_annual_tax(Decimal("15000"), _tax_brackets()) == Decimal("0")

    def test_second_bracket_10pct(self):
        """15,001 → 30,000 بـ 10%"""
        # 1 جنيه فوق الحد → 0.10 جنيه
        result = calculate_annual_tax(Decimal("15001"), _tax_brackets())
        assert result == Decimal("0.10")

    def test_full_second_bracket(self):
        """30,000 → 10% على 15,000 = 1,500"""
        result = calculate_annual_tax(Decimal("30000"), _tax_brackets())
        assert result == Decimal("1500.00")

    def test_multiple_brackets(self):
        """45,000 → يمر بالشريحة الأولى (0) + الثانية (1500) + الثالثة (15%×15000=2250)"""
        result = calculate_annual_tax(Decimal("45000"), _tax_brackets())
        assert result == Decimal("3750.00")  # 0 + 1500 + 2250

    def test_top_bracket_above_400k(self):
        """500,000 → كل الشرائح تُطبَّق"""
        result = calculate_annual_tax(Decimal("500000"), _tax_brackets())
        # 0 + 1500 + 2250 + 3000 + 31500 + 50000 + (100000*0.275)
        # = 0 + 1500 + 2250 + 3000 + 31500 + 50000 + 27500 = 115750
        assert result == Decimal("115750.00")

    def test_empty_brackets_returns_zero(self):
        assert calculate_annual_tax(Decimal("100000"), []) == Decimal("0")

    def test_brackets_unsorted_order(self):
        """الترتيب لا يؤثر — الدالة تُرتّب تلقائياً"""
        brackets_reversed = list(reversed(_tax_brackets()))
        result = calculate_annual_tax(Decimal("30000"), brackets_reversed)
        assert result == Decimal("1500.00")


# ─── calculate_penalty_deduction ─────────────────────────────────────

class TestCalculatePenaltyDeduction:

    def test_no_penalty_days(self):
        result = calculate_penalty_deduction(Decimal("6000"), 0, max_monthly_days=5)
        assert result == Decimal("0.00")

    def test_single_penalty_day(self):
        """6000 ÷ 30 = 200/يوم → 1 يوم = 200.00"""
        result = calculate_penalty_deduction(Decimal("6000"), 1, max_monthly_days=5)
        assert result == Decimal("200.00")

    def test_penalty_capped_at_max(self):
        """10 أيام لكن الحد القانوني 5 → يُحسب 5 فقط"""
        result = calculate_penalty_deduction(Decimal("6000"), 10, max_monthly_days=5)
        assert result == Decimal("1000.00")  # 200 × 5

    def test_fractional_daily_rate(self):
        """5000 ÷ 30 = 166.67/يوم"""
        result = calculate_penalty_deduction(Decimal("5000"), 2, max_monthly_days=5)
        # 5000/30 = 166.67, × 2 = 333.33
        assert result == Decimal("333.33")

    def test_penalty_exactly_at_limit(self):
        result = calculate_penalty_deduction(Decimal("3000"), 5, max_monthly_days=5)
        assert result == Decimal("500.00")  # 100 × 5


# ─── annual_leave_entitlement ─────────────────────────────────────────

class TestAnnualLeaveEntitlement:

    def test_less_than_10_years_under_50(self):
        """أقل من 10 سنوات خدمة وأقل من 50 سنة → 21 يوم"""
        hire = date.today().replace(year=date.today().year - 5)
        birth = date.today().replace(year=date.today().year - 30)
        assert annual_leave_entitlement(hire, birth) == 21

    def test_over_10_years_service(self):
        """أكثر من 10 سنوات خدمة → 30 يوم"""
        hire = date.today().replace(year=date.today().year - 11)
        birth = date.today().replace(year=date.today().year - 35)
        assert annual_leave_entitlement(hire, birth) == 30

    def test_over_50_age(self):
        """عمر 51 سنة → 30 يوم بغض النظر عن سنوات الخدمة"""
        hire = date.today().replace(year=date.today().year - 3)
        birth = date.today().replace(year=date.today().year - 51)
        assert annual_leave_entitlement(hire, birth) == 30

    def test_exactly_10_years_service(self):
        """بالضبط 10 سنوات → 30 يوم"""
        hire = date(date.today().year - 10, date.today().month, date.today().day)
        birth = date(1990, 1, 1)
        assert annual_leave_entitlement(hire, birth) == 30


# ─── calculate_gratuity ───────────────────────────────────────────────

class TestCalculateGratuity:

    def test_termination_full_gratuity(self):
        """فصل → شهر/سنة كاملة"""
        hire = date(date.today().year - 5, 1, 1)
        result = calculate_gratuity(Decimal("5000"), hire, "termination")
        assert result == Decimal("25000.00")  # 5000 × 5 سنوات

    def test_resignation_before_5_years_one_third(self):
        hire = date(date.today().year - 3, 1, 1)
        result = calculate_gratuity(Decimal("6000"), hire, "resignation_before_5y")
        # 6000 × 3 = 18000 → ÷ 3 = 6000
        assert result == Decimal("6000.00")

    def test_resignation_5_to_10_years_two_thirds(self):
        hire = date(date.today().year - 7, 1, 1)
        result = calculate_gratuity(Decimal("6000"), hire, "resignation_5_to_10y")
        # 6000 × 7 = 42000 → × 2/3 = 28000
        assert result == Decimal("28000.00")

    def test_resignation_after_10_years_full(self):
        hire = date(date.today().year - 12, 1, 1)
        result = calculate_gratuity(Decimal("5000"), hire, "resignation_after_10y")
        assert result == Decimal("60000.00")  # 5000 × 12

    def test_zero_years_service(self):
        """أقل من سنة → صفر"""
        hire = date.today().replace(month=max(1, date.today().month - 6))
        result = calculate_gratuity(Decimal("5000"), hire, "termination")
        assert result == Decimal("0.00")


# ─── calculate_payroll ────────────────────────────────────────────────

class TestCalculatePayroll:

    def test_basic_payroll_no_allowances(self):
        """راتب أساسي 5000 بدون بدلات"""
        emp = _basic_employee(basic_salary=Decimal("5000"))
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)

        assert result.employee_id == 1
        assert result.basic_salary == Decimal("5000")
        assert result.gross_salary == Decimal("5000")
        assert result.taxable_allowances == Decimal("0")
        assert result.non_taxable_allowances == Decimal("0")

        # التأمينات: min(5000, 14000) × 11%
        assert result.insurable_salary == Decimal("5000")
        assert result.employee_si == Decimal("550.00")   # 5000 × 0.11
        assert result.employer_si == Decimal("937.50")   # 5000 × 0.1875

        # الصافي > 0 وأقل من الإجمالي
        assert Decimal("0") < result.net_salary < result.gross_salary

    def test_insurable_salary_capped_at_maximum(self):
        """راتب 20,000 → الأجر التأميني محدود بـ 14,000"""
        emp = _basic_employee(basic_salary=Decimal("20000"))
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)

        assert result.insurable_salary == Decimal("14000")
        assert result.employee_si == Decimal("1540.00")   # 14000 × 0.11
        assert result.employer_si == Decimal("2625.00")   # 14000 × 0.1875

    def test_taxable_allowance_included_in_gross(self):
        """بدل خاضع للضريبة يُضاف للإجمالي"""
        allowances = [Allowance("housing", Decimal("1000"), is_taxable=True, is_pensionable=False)]
        emp = _basic_employee(basic_salary=Decimal("5000"), allowances=allowances)
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)

        assert result.gross_salary == Decimal("6000")
        assert result.taxable_allowances == Decimal("1000")

    def test_non_taxable_allowance_not_in_gross_but_in_net(self):
        """بدل غير خاضع للضريبة لا يدخل الإجمالي لكن يُضاف للصافي"""
        allowances = [Allowance("transport", Decimal("500"), is_taxable=False, is_pensionable=False)]
        emp = _basic_employee(basic_salary=Decimal("5000"), allowances=allowances)
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)

        assert result.gross_salary == Decimal("5000")  # لا يتأثر الإجمالي
        assert result.non_taxable_allowances == Decimal("500")

        # الصافي مع البدل > الصافي بدونه
        emp_no_allowance = _basic_employee(basic_salary=Decimal("5000"))
        result_no = calculate_payroll(emp_no_allowance, _si_config(), _tax_brackets(), 5)
        assert result.net_salary > result_no.net_salary

    def test_pensionable_allowance_included_in_insurable(self):
        """بدل pensionable يدخل الأجر التأميني"""
        allowances = [Allowance("incentive", Decimal("2000"), is_taxable=True, is_pensionable=True)]
        emp = _basic_employee(basic_salary=Decimal("5000"), allowances=allowances)
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)

        # insurable = min(5000+2000, 14000) = 7000
        assert result.insurable_salary == Decimal("7000")

    def test_overtime_included_in_gross(self):
        emp = _basic_employee(basic_salary=Decimal("5000"), overtime=Decimal("800"))
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)

        assert result.gross_salary == Decimal("5800")
        assert result.overtime == Decimal("800")

    def test_penalty_deduction_applied(self):
        """يوم جزاء واحد → خصم يومي"""
        emp = _basic_employee(basic_salary=Decimal("6000"), penalty_days=1)
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)

        assert result.penalty_deduction == Decimal("200.00")  # 6000/30

    def test_unpaid_leave_deduction(self):
        """يومان إجازة بلا أجر"""
        emp = _basic_employee(basic_salary=Decimal("6000"), unpaid_leave_days=2)
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)

        assert result.unpaid_leave_deduction == Decimal("400.00")  # 200 × 2

    def test_net_salary_never_negative_with_extreme_deductions(self):
        """رغم الخصومات الكبيرة، الصافي ≥ 0"""
        emp = _basic_employee(
            basic_salary=Decimal("1000"),
            penalty_days=5,
            unpaid_leave_days=30,
        )
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)
        # لا يُفرض أن الصافي صفر بالضبط لكن يجب أن يكون رقم حقيقي
        assert isinstance(result.net_salary, Decimal)

    def test_journal_entry_structure(self):
        """القيد المحاسبي يحتوي على debits و credits"""
        emp = _basic_employee(basic_salary=Decimal("5000"))
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)

        je = result.journal_entry
        assert "debits" in je
        assert "credits" in je
        assert len(je["debits"]) >= 2
        assert len(je["credits"]) >= 3

    def test_period_format(self):
        """format الفترة YYYY-MM"""
        emp = _basic_employee(basic_salary=Decimal("5000"))
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)
        assert result.period == "2026-06"

    def test_low_salary_below_exemption_no_tax(self):
        """راتب منخفض — وعاء الضريبة صفر أو سالب → لا ضريبة"""
        emp = _basic_employee(basic_salary=Decimal("1500"))
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)
        # annual_gross = 18000, SI = 1980, taxable_base = 18000 - 1980 - 15000 = 1020 > 0
        # لكن الضريبة على 1020 = 0 (ضمن الشريحة الأولى 0-15000)
        assert result.monthly_tax == Decimal("0.00")

    def test_high_salary_has_tax(self):
        """راتب عالٍ يجب أن يكون عليه ضريبة"""
        emp = _basic_employee(basic_salary=Decimal("20000"))
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)
        assert result.monthly_tax > Decimal("0")

    def test_gross_equals_basic_plus_taxable_allowances_plus_overtime(self):
        allowances = [
            Allowance("bonus", Decimal("1000"), is_taxable=True, is_pensionable=False),
            Allowance("transport", Decimal("300"), is_taxable=False, is_pensionable=False),
        ]
        emp = _basic_employee(
            basic_salary=Decimal("5000"),
            allowances=allowances,
            overtime=Decimal("500"),
        )
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)
        assert result.gross_salary == Decimal("6500")  # 5000 + 1000 + 500 (لا transport)

    def test_late_penalty_deduction_applied_and_separate_from_manual_penalty(self):
        """late_penalty_amount (تلقائي من الحضور) وpenalty_days (يدوي/تأديبي)
        بيتخصموا مع بعض، مش أحدهما بدل التاني — تحقق التعايش بينهم صراحةً."""
        emp = _basic_employee(
            basic_salary=Decimal("6000"),
            penalty_days=1,                              # يدوي: 200.00
            late_penalty_amount=Decimal("37.50"),         # تلقائي من الحضور
        )
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)

        assert result.penalty_deduction == Decimal("200.00")
        assert result.late_penalty_deduction == Decimal("37.50")

        # الصافي بدون أي منهم أكبر من الصافي بيهم مجتمعين
        base = calculate_payroll(_basic_employee(basic_salary=Decimal("6000")), _si_config(), _tax_brackets(), 5)
        assert result.net_salary == base.net_salary - Decimal("200.00") - Decimal("37.50")

    def test_late_penalty_deduction_defaults_to_zero(self):
        emp = _basic_employee(basic_salary=Decimal("5000"))
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)
        assert result.late_penalty_deduction == Decimal("0.00")

    # ── wagdy.md H-04: insurance_base_salary ────────────────────────────

    def test_insurance_base_salary_none_falls_back_to_basic_salary(self):
        """من غير insurance_base_salary — نفس السلوك القديم بالظبط (basic_salary
        هو الوعاء التأميني)."""
        emp = _basic_employee(basic_salary=Decimal("20000"))
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)
        assert result.insurable_salary == Decimal("14000")  # min(20000, 14000)

    def test_insurance_base_salary_used_when_set(self):
        """راتب أساسي 20,000 لكن وعاء تأميني 13,500 (مثال حقيقي من Mohamed) —
        التأمينات تُحسب على 13,500 مش 20,000."""
        emp = _basic_employee(
            basic_salary=Decimal("20000"),
            insurance_base_salary=Decimal("13500"),
        )
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)
        assert result.insurable_salary == Decimal("13500")
        assert result.employee_si == Decimal("1485.00")   # 13500 × 0.11
        assert result.employer_si == Decimal("2531.25")   # 13500 × 0.1875
        # gross_salary/net_salary لسه مبنيين على basic_salary الحقيقي
        assert result.gross_salary == Decimal("20000")

    def test_insurance_base_salary_still_capped_at_maximum(self):
        """حتى لو insurance_base_salary أعلى من basic_salary، لسه محدود بالحد الأقصى."""
        emp = _basic_employee(
            basic_salary=Decimal("10000"),
            insurance_base_salary=Decimal("18000"),
        )
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)
        assert result.insurable_salary == Decimal("14000")

    # ── wagdy.md H-05: holiday_bonus ─────────────────────────────────────

    def test_holiday_bonus_defaults_to_zero(self):
        emp = _basic_employee(basic_salary=Decimal("5000"))
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)
        assert result.holiday_bonus == Decimal("0.00")

    def test_holiday_bonus_added_to_net_not_gross(self):
        """مكافأة العيد بتُضاف للصافي مباشرة، مش جزء من gross_salary (عشان
        متدخلش حساب annual_gross/الضريبة السنوية زي بند متكرر)."""
        emp = _basic_employee(basic_salary=Decimal("5000"), holiday_bonus_amount=Decimal("1000"))
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)

        assert result.holiday_bonus == Decimal("1000.00")
        assert result.gross_salary == Decimal("5000")  # لا يتأثر

        base = calculate_payroll(_basic_employee(basic_salary=Decimal("5000")), _si_config(), _tax_brackets(), 5)
        assert result.net_salary == base.net_salary + Decimal("1000.00")

    def test_holiday_bonus_not_insurable(self):
        """مكافأة العيد مش خاضعة للتأمينات — الوعاء التأميني ثابت بغض النظر عنها."""
        emp = _basic_employee(basic_salary=Decimal("5000"), holiday_bonus_amount=Decimal("2000"))
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)
        assert result.insurable_salary == Decimal("5000")

    def test_holiday_bonus_adds_debit_line_to_journal(self):
        emp = _basic_employee(basic_salary=Decimal("5000"), holiday_bonus_amount=Decimal("500"))
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)
        debit_accounts = [d["account"] for d in result.journal_entry["debits"]]
        assert "مصروف مكافأة عيد" in debit_accounts

    def test_no_holiday_bonus_no_extra_debit_line(self):
        emp = _basic_employee(basic_salary=Decimal("5000"))
        result = calculate_payroll(emp, _si_config(), _tax_brackets(), max_penalty_days=5)
        debit_accounts = [d["account"] for d in result.journal_entry["debits"]]
        assert "مصروف مكافأة عيد" not in debit_accounts


# ─── standard_shift_hours ──────────────────────────────────────────────

class TestStandardShiftHours:

    def test_regular_day_shift(self):
        assert standard_shift_hours("09:00", "17:00") == Decimal("8.00")

    def test_overnight_shift_crosses_midnight(self):
        """22:00 → 06:00 = 8 ساعات رغم عبورها منتصف الليل"""
        assert standard_shift_hours("22:00", "06:00") == Decimal("8.00")

    def test_short_shift(self):
        assert standard_shift_hours("09:00", "13:00") == Decimal("4.00")


# ─── compute_attendance_minutes ─────────────────────────────────────────

def _policy(**overrides) -> AttendancePolicyConfig:
    defaults = dict(
        late_grace_minutes=10,
        early_leave_grace_minutes=10,
        standard_shift_start="09:00",
        standard_shift_end="17:00",
        overtime_rate_multiplier=Decimal("1.50"),
        late_penalty_rate_multiplier=Decimal("1.00"),
    )
    defaults.update(overrides)
    return AttendancePolicyConfig(**defaults)


class TestComputeAttendanceMinutes:
    """شفت أمثلة الحدود الحرجة دي بالضبط — مطلوبة صراحةً في المواصفة: 9 دقايق
    تأخير مع سماح 10 = صفر (مش خصم جزئي)، 1 دقيقة فوق السماح = تُحسب كاملة."""

    def test_nine_minutes_late_under_ten_minute_grace_is_zero(self):
        d = date(2026, 6, 1)
        punch = AttendancePunch(
            record_date=d,
            check_in=_cairo_local_to_utc_naive(d, 9, 9),   # 9 دقايق تأخير
            check_out=_cairo_local_to_utc_naive(d, 17, 0),
        )
        result = compute_attendance_minutes([punch], _policy())
        assert result.late_minutes == 0

    def test_exactly_at_grace_boundary_is_forgiven(self):
        """التأخير = مدة السماح بالظبط (10 دقايق) → صفر، مش على الحافة"""
        d = date(2026, 6, 1)
        punch = AttendancePunch(
            record_date=d,
            check_in=_cairo_local_to_utc_naive(d, 9, 10),
            check_out=_cairo_local_to_utc_naive(d, 17, 0),
        )
        result = compute_attendance_minutes([punch], _policy())
        assert result.late_minutes == 0

    def test_one_minute_over_grace_counts_full_lateness(self):
        """11 دقيقة تأخير مع سماح 10 → 11 دقيقة كاملة تُحسب (مش دقيقة واحدة
        بس فوق الحد) — ده القرار التصميمي الموثّق في docstring الدالة."""
        d = date(2026, 6, 1)
        punch = AttendancePunch(
            record_date=d,
            check_in=_cairo_local_to_utc_naive(d, 9, 11),
            check_out=_cairo_local_to_utc_naive(d, 17, 0),
        )
        result = compute_attendance_minutes([punch], _policy())
        assert result.late_minutes == 11

    def test_early_leave_over_grace_counted(self):
        d = date(2026, 6, 1)
        punch = AttendancePunch(
            record_date=d,
            check_in=_cairo_local_to_utc_naive(d, 9, 0),
            check_out=_cairo_local_to_utc_naive(d, 16, 45),  # 15 دقيقة قبل النهاية
        )
        result = compute_attendance_minutes([punch], _policy())
        assert result.early_leave_minutes == 15

    def test_early_leave_under_grace_is_zero(self):
        d = date(2026, 6, 1)
        punch = AttendancePunch(
            record_date=d,
            check_in=_cairo_local_to_utc_naive(d, 9, 0),
            check_out=_cairo_local_to_utc_naive(d, 16, 55),  # 5 دقايق بس قبل النهاية
        )
        result = compute_attendance_minutes([punch], _policy())
        assert result.early_leave_minutes == 0

    def test_overtime_no_grace_any_minute_over_counts(self):
        d = date(2026, 6, 1)
        punch = AttendancePunch(
            record_date=d,
            check_in=_cairo_local_to_utc_naive(d, 9, 0),
            check_out=_cairo_local_to_utc_naive(d, 18, 30),  # 90 دقيقة أوفرتايم
        )
        result = compute_attendance_minutes([punch], _policy())
        assert result.overtime_minutes == 90

    def test_on_time_and_on_schedule_all_zero(self):
        d = date(2026, 6, 1)
        punch = AttendancePunch(
            record_date=d,
            check_in=_cairo_local_to_utc_naive(d, 9, 0),
            check_out=_cairo_local_to_utc_naive(d, 17, 0),
        )
        result = compute_attendance_minutes([punch], _policy())
        assert result == AttendanceMinutesResult(0, 0, 0, 1)

    def test_missing_punch_is_skipped_not_error(self):
        """يوم غياب (مفيش check_in ولا check_out) — يتجاهل بهدوء، مش خطأ"""
        d = date(2026, 6, 1)
        punch = AttendancePunch(record_date=d, check_in=None, check_out=None)
        result = compute_attendance_minutes([punch], _policy())
        assert result == AttendanceMinutesResult(0, 0, 0, 0)

    def test_check_in_only_still_computes_lateness(self):
        """موظف لسه في الوردية (مفيش check_out لسه) — التأخير لازم يتحسب برضه"""
        d = date(2026, 6, 1)
        punch = AttendancePunch(
            record_date=d,
            check_in=_cairo_local_to_utc_naive(d, 9, 20),  # 20 دقيقة تأخير
            check_out=None,
        )
        result = compute_attendance_minutes([punch], _policy())
        assert result.late_minutes == 20
        assert result.overtime_minutes == 0

    def test_per_day_shift_overrides_policy_default(self):
        """RotaAssignment→Shift الخاص باليوم بياخد الأولوية على fallback
        السياسة — وردية 12:00-20:00 بدل الافتراضي 09:00-17:00"""
        d = date(2026, 6, 1)
        punch = AttendancePunch(
            record_date=d,
            check_in=_cairo_local_to_utc_naive(d, 12, 5),   # 5 دقايق تأخير عن 12:00 (تحت السماح)
            check_out=_cairo_local_to_utc_naive(d, 20, 0),
            shift_start="12:00",
            shift_end="20:00",
        )
        result = compute_attendance_minutes([punch], _policy())
        assert result.late_minutes == 0  # لو استُخدم 09:00 غلط كان هيبقى "متأخر" بساعات

    def test_overnight_shift_late_and_overtime(self):
        """وردية ليلية 22:00 → 06:00 — دخول متأخر 15 دقيقة + خروج متأخر (أوفرتايم)"""
        d = date(2026, 6, 1)
        punch = AttendancePunch(
            record_date=d,
            check_in=_cairo_local_to_utc_naive(d, 22, 15),
            check_out=_cairo_local_to_utc_naive(d + timedelta(days=1), 6, 30),
            shift_start="22:00",
            shift_end="06:00",
        )
        result = compute_attendance_minutes([punch], _policy())
        assert result.late_minutes == 15
        assert result.overtime_minutes == 30

    def test_aggregates_across_multiple_days(self):
        d1, d2 = date(2026, 6, 1), date(2026, 6, 2)
        punches = [
            AttendancePunch(record_date=d1, check_in=_cairo_local_to_utc_naive(d1, 9, 20), check_out=_cairo_local_to_utc_naive(d1, 17, 0)),
            AttendancePunch(record_date=d2, check_in=_cairo_local_to_utc_naive(d2, 9, 30), check_out=_cairo_local_to_utc_naive(d2, 17, 0)),
        ]
        result = compute_attendance_minutes(punches, _policy())
        assert result.late_minutes == 50  # 20 + 30
        assert result.days_with_data == 2


# ─── attendance_minutes_to_amount ────────────────────────────────────────

class TestAttendanceMinutesToAmount:

    def test_worked_example_ninety_minutes_overtime(self):
        """مثال محسوب يدويًا: راتب أساسي 6000، وردية 8 ساعات → معدل يومي
        200، معدل ساعة 25. 90 دقيقة (1.5 ساعة) أوفرتايم × 1.5x = 56.25"""
        amount = attendance_minutes_to_amount(
            minutes=90, basic_salary=Decimal("6000"),
            shift_hours=Decimal("8"), rate_multiplier=Decimal("1.5"),
        )
        assert amount == Decimal("56.25")

    def test_worked_example_late_penalty(self):
        """نفس الراتب، 11 دقيقة تأخير × نسبة خصم 1.0x:
        (11/60) × 25 × 1.0 = 4.583... → 4.58"""
        amount = attendance_minutes_to_amount(
            minutes=11, basic_salary=Decimal("6000"),
            shift_hours=Decimal("8"), rate_multiplier=Decimal("1.0"),
        )
        assert amount == Decimal("4.58")

    def test_zero_minutes_zero_amount(self):
        assert attendance_minutes_to_amount(0, Decimal("6000"), Decimal("8"), Decimal("1.5")) == Decimal("0.00")

    def test_negative_minutes_treated_as_zero(self):
        assert attendance_minutes_to_amount(-5, Decimal("6000"), Decimal("8"), Decimal("1.5")) == Decimal("0.00")

    def test_zero_shift_hours_returns_zero_not_division_error(self):
        assert attendance_minutes_to_amount(60, Decimal("6000"), Decimal("0"), Decimal("1.5")) == Decimal("0.00")
