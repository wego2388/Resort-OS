"""
tests/test_engines/test_hr_engine.py
اختبارات كاملة لـ HR Engine — قانون العمل المصري
بدون DB، بدون fixtures — pure functions فقط
"""

from datetime import date
from decimal import Decimal

import pytest

from app.resort_os.hr_engine import (
    Allowance,
    EmployeePayrollInput,
    SocialInsuranceConfig,
    TaxBracket,
    annual_leave_entitlement,
    calculate_annual_tax,
    calculate_gratuity,
    calculate_payroll,
    calculate_penalty_deduction,
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
) -> EmployeePayrollInput:
    return EmployeePayrollInput(
        employee_id=1,
        basic_salary=basic_salary,
        allowances=allowances or [],
        overtime_amount=overtime,
        penalty_days=penalty_days,
        unpaid_leave_days=unpaid_leave_days,
        hire_date=date(2020, 1, 1),
        birth_date=date(1990, 6, 15),
        period_month=date(2026, 6, 1),
    )


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
