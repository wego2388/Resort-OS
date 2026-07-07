"""
tests/test_engines/test_food_cost_engine.py
اختبارات كاملة لـ Food Cost Engine — بدون DB، بدون fixtures، pure functions فقط.
"""
from decimal import Decimal

from app.resort_os.food_cost_engine import (
    DEFAULT_FOOD_COST_THRESHOLD_PCT,
    calculate_theoretical_total_cost,
    calculate_theoretical_unit_cost,
    compute_food_cost_result,
    exceeds_threshold,
    food_cost_pct,
    gross_margin,
    gross_margin_pct,
)


class TestTheoreticalUnitCost:
    def test_single_ingredient(self):
        # لحمة مفرومة: 40 جنيه/كيلو × 0.150 كيلو للتقديمة = 6.00
        lines = [(Decimal("40.00"), Decimal("0.150"))]
        assert calculate_theoretical_unit_cost(lines) == Decimal("6.00")

    def test_multiple_ingredients_summed(self):
        # برجر: لحمة 6.00 + رغيف 2.50 + جبنة (0.030 كيلو × 80) = 2.40 → 10.90
        lines = [
            (Decimal("40.00"), Decimal("0.150")),
            (Decimal("2.50"), Decimal("1")),
            (Decimal("80.00"), Decimal("0.030")),
        ]
        assert calculate_theoretical_unit_cost(lines) == Decimal("10.90")

    def test_empty_recipe_is_zero(self):
        assert calculate_theoretical_unit_cost([]) == Decimal("0.00")

    def test_rounds_half_up_to_two_places(self):
        lines = [(Decimal("3.333"), Decimal("1"))]
        assert calculate_theoretical_unit_cost(lines) == Decimal("3.33")


class TestTheoreticalTotalCost:
    def test_multiplies_by_quantity_sold(self):
        assert calculate_theoretical_total_cost(Decimal("10.90"), 50) == Decimal("545.00")

    def test_zero_quantity_sold_is_zero(self):
        assert calculate_theoretical_total_cost(Decimal("10.90"), 0) == Decimal("0.00")


class TestFoodCostPct:
    def test_known_scenario(self):
        # تكلفة 10.90 على سعر بيع 80.00 → نسبة تكلفة الطعام 13.625% → 13.63
        assert food_cost_pct(Decimal("10.90"), Decimal("80.00")) == Decimal("13.63")

    def test_exact_threshold_boundary_not_exceeding(self):
        # تكلفة = بالظبط 30% من الإيراد
        pct = food_cost_pct(Decimal("30.00"), Decimal("100.00"))
        assert pct == Decimal("30.00")
        assert exceeds_threshold(pct, Decimal("30")) is False  # يساوي الحد، مش أكبر منه

    def test_just_above_threshold_exceeds(self):
        pct = food_cost_pct(Decimal("30.01"), Decimal("100.00"))
        assert exceeds_threshold(pct, Decimal("30")) is True

    def test_zero_revenue_returns_none(self):
        assert food_cost_pct(Decimal("10.00"), Decimal("0")) is None

    def test_negative_revenue_returns_none(self):
        assert food_cost_pct(Decimal("10.00"), Decimal("-5")) is None


class TestExceedsThreshold:
    def test_none_pct_never_exceeds(self):
        assert exceeds_threshold(None) is False

    def test_uses_default_threshold_when_unspecified(self):
        assert exceeds_threshold(Decimal("35")) is True
        assert exceeds_threshold(Decimal("25")) is False
        assert DEFAULT_FOOD_COST_THRESHOLD_PCT == Decimal("30")


class TestGrossMargin:
    def test_known_scenario(self):
        assert gross_margin(Decimal("80.00"), Decimal("10.90")) == Decimal("69.10")

    def test_margin_can_be_negative(self):
        # الصنف بيتباع بأقل من تكلفته — سيناريو حقيقي محتمل (خطأ تسعير)
        assert gross_margin(Decimal("10.00"), Decimal("15.00")) == Decimal("-5.00")

    def test_pct_known_scenario(self):
        assert gross_margin_pct(Decimal("80.00"), Decimal("10.90")) == Decimal("86.38")

    def test_pct_zero_revenue_returns_none(self):
        assert gross_margin_pct(Decimal("0"), Decimal("10.00")) is None


class TestComputeFoodCostResult:
    def test_full_known_scenario(self):
        lines = [(Decimal("40.00"), Decimal("0.150")), (Decimal("2.50"), Decimal("1"))]
        # unit_cost = 6.00 + 2.50 = 8.50 ؛ 20 وحدة مباعة بسعر إجمالي 1600.00
        result = compute_food_cost_result(lines, quantity_sold=20, revenue=Decimal("1600.00"))
        assert result.theoretical_unit_cost == Decimal("8.50")
        assert result.theoretical_total_cost == Decimal("170.00")
        assert result.quantity_sold == 20
        assert result.revenue == Decimal("1600.00")
        assert result.food_cost_pct == Decimal("10.63")
        assert result.gross_margin_amount == Decimal("1430.00")
        assert result.gross_margin_pct == Decimal("89.38")

    def test_zero_revenue_edge_case(self):
        lines = [(Decimal("40.00"), Decimal("0.150"))]
        result = compute_food_cost_result(lines, quantity_sold=0, revenue=Decimal("0"))
        assert result.theoretical_unit_cost == Decimal("6.00")
        assert result.theoretical_total_cost == Decimal("0.00")
        assert result.food_cost_pct is None
        assert result.gross_margin_pct is None
        # المبلغ (لا النسبة) يفضل قابل للحساب حتى بدون إيراد — التكلفة معروفة بغض النظر عن المبيعات
        assert result.gross_margin_amount == Decimal("0.00")
