"""
tests/test_engines/test_discount_engine.py
اختبارات كاملة للـ Discount Engine — بدون DB، < 1 ثانية
"""

from datetime import date
from decimal import Decimal

import pytest

from app.resort_os.discount_engine import (
    DiscountRule,
    DiscountResult,
    OrderContext,
    calculate_discount,
    get_applicable_rules_for_order,
)


# ─── Helpers ─────────────────────────────────────────────────────────

def _rule(
    id: int,
    priority: int,
    discount_value: Decimal = Decimal("10"),
    discount_type: str = "percentage",
    condition_type: str = "total_amount",
    condition_value: str = ">=100",
    max_uses: int = -1,
    uses_count: int = 0,
) -> DiscountRule:
    return DiscountRule(
        id=id,
        condition_type=condition_type,
        condition_value=condition_value,
        discount_type=discount_type,
        discount_value=discount_value,
        max_uses=max_uses,
        valid_from=date(2020, 1, 1),
        valid_until=date(2099, 12, 31),
        priority=priority,
        uses_count=uses_count,
    )


def _ctx(
    total: Decimal = Decimal("500"),
    items: int = 3,
    group: str = "default",
    order_date: date | None = None,
) -> OrderContext:
    return OrderContext(
        total_amount=total,
        item_count=items,
        customer_group=group,
        order_date=order_date or date.today(),
    )


# ─── Tests ───────────────────────────────────────────────────────────

class TestNoDiscount:

    def test_empty_rules(self):
        result = calculate_discount(Decimal("500"), [], _ctx())
        assert not result.applied
        assert result.final_amount == Decimal("500")
        assert result.amount_saved == Decimal("0")

    def test_condition_not_met_amount(self):
        rules = [_rule(1, priority=1, condition_value=">=1000")]
        result = calculate_discount(Decimal("500"), rules, _ctx(total=Decimal("500")))
        assert not result.applied

    def test_expired_rule(self):
        rule = DiscountRule(
            id=1, condition_type="total_amount", condition_value=">=100",
            discount_type="percentage", discount_value=Decimal("10"),
            max_uses=-1, uses_count=0,
            valid_from=date(2020, 1, 1),
            valid_until=date(2020, 12, 31),  # منتهي
            priority=1,
        )
        result = calculate_discount(Decimal("500"), [rule], _ctx())
        assert not result.applied

    def test_max_uses_exhausted(self):
        rule = _rule(1, priority=1, max_uses=5, uses_count=5)
        result = calculate_discount(Decimal("500"), [rule], _ctx())
        assert not result.applied

    def test_future_rule_not_started(self):
        rule = DiscountRule(
            id=1, condition_type="total_amount", condition_value=">=100",
            discount_type="percentage", discount_value=Decimal("10"),
            max_uses=-1, uses_count=0,
            valid_from=date(2099, 1, 1),    # لم يبدأ بعد
            valid_until=date(2099, 12, 31),
            priority=1,
        )
        result = calculate_discount(Decimal("500"), [rule], _ctx())
        assert not result.applied


class TestPercentageDiscount:

    def test_basic_percentage(self):
        rules = [_rule(1, priority=1, discount_value=Decimal("10"))]
        result = calculate_discount(Decimal("500"), rules, _ctx())
        assert result.applied
        assert result.amount_saved == Decimal("50.00")
        assert result.final_amount == Decimal("450.00")

    def test_percentage_cannot_exceed_100(self):
        rules = [_rule(1, priority=1, discount_value=Decimal("150"))]
        result = calculate_discount(Decimal("500"), rules, _ctx())
        assert result.amount_saved == Decimal("500.00")   # max = total
        assert result.final_amount == Decimal("0.00")

    def test_fractional_percentage(self):
        rules = [_rule(1, priority=1, discount_value=Decimal("12.5"))]
        result = calculate_discount(Decimal("800"), rules, _ctx())
        assert result.amount_saved == Decimal("100.00")
        assert result.final_amount == Decimal("700.00")


class TestFixedAmountDiscount:

    def test_basic_fixed_amount(self):
        rules = [_rule(1, priority=1, discount_type="fixed_amount", discount_value=Decimal("50"))]
        result = calculate_discount(Decimal("200"), rules, _ctx())
        assert result.amount_saved == Decimal("50")
        assert result.final_amount == Decimal("150")

    def test_fixed_amount_cannot_exceed_total(self):
        rules = [_rule(1, priority=1, discount_type="fixed_amount", discount_value=Decimal("1000"))]
        result = calculate_discount(Decimal("200"), rules, _ctx())
        assert result.amount_saved == Decimal("200")
        assert result.final_amount == Decimal("0")


class TestPriorityAndTieBreaker:

    def test_highest_priority_wins(self):
        rules = [
            _rule(1, priority=1, discount_value=Decimal("10")),
            _rule(2, priority=5, discount_value=Decimal("20")),
            _rule(3, priority=3, discount_value=Decimal("15")),
        ]
        result = calculate_discount(Decimal("500"), rules, _ctx())
        assert result.rule_id == 2   # أعلى priority
        assert result.amount_saved == Decimal("100.00")

    def test_tie_broken_by_id_ascending(self):
        """عند تعادل priority: أصغر id يفوز — deterministic دائماً."""
        rules = [
            _rule(id=10, priority=5, discount_value=Decimal("20")),
            _rule(id=3,  priority=5, discount_value=Decimal("10")),  # id أصغر → يفوز
            _rule(id=7,  priority=5, discount_value=Decimal("15")),
        ]
        result = calculate_discount(Decimal("500"), rules, _ctx())
        assert result.rule_id == 3

    def test_tie_same_id_not_possible(self):
        """لو كان في rule واحد بنفس المواصفات — يُطبَّق مرة واحدة."""
        rule = _rule(1, priority=5)
        result = calculate_discount(Decimal("500"), [rule, rule], _ctx())
        assert result.rule_id == 1
        assert result.amount_saved == Decimal("50.00")  # ليس 100


class TestConditionTypes:

    def test_total_amount_gte(self):
        rules = [_rule(1, priority=1, condition_value=">=500")]
        assert calculate_discount(Decimal("500"), rules, _ctx(total=Decimal("500"))).applied
        assert not calculate_discount(Decimal("499"), rules, _ctx(total=Decimal("499"))).applied

    def test_total_amount_gt(self):
        rules = [_rule(1, priority=1, condition_value=">500")]
        assert calculate_discount(Decimal("501"), rules, _ctx(total=Decimal("501"))).applied
        assert not calculate_discount(Decimal("500"), rules, _ctx(total=Decimal("500"))).applied

    def test_item_count_condition(self):
        rules = [_rule(1, priority=1, condition_type="item_count", condition_value=">=3")]
        assert calculate_discount(Decimal("500"), rules, _ctx(items=3)).applied
        assert not calculate_discount(Decimal("500"), rules, _ctx(items=2)).applied

    def test_day_of_week_friday(self):
        friday = date(2026, 7, 3)   # جمعة
        saturday = date(2026, 7, 4)  # سبت
        monday = date(2026, 7, 6)   # اثنين
        rules = [_rule(1, priority=1, condition_type="day_of_week",
                       condition_value="friday,saturday")]
        assert calculate_discount(Decimal("100"), rules, _ctx(order_date=friday)).applied
        assert calculate_discount(Decimal("100"), rules, _ctx(order_date=saturday)).applied
        assert not calculate_discount(Decimal("100"), rules, _ctx(order_date=monday)).applied

    def test_customer_group_vip(self):
        rules = [_rule(1, priority=1, condition_type="customer_group",
                       condition_value="vip,staff")]
        assert calculate_discount(Decimal("100"), rules, _ctx(group="vip")).applied
        assert calculate_discount(Decimal("100"), rules, _ctx(group="staff")).applied
        assert not calculate_discount(Decimal("100"), rules, _ctx(group="default")).applied

    def test_condition_value_with_spaces(self):
        """تنسيقات مختلفة للـ condition_value."""
        rules = [_rule(1, priority=1, condition_value=">=  500")]
        assert calculate_discount(Decimal("500"), rules, _ctx(total=Decimal("500"))).applied


class TestGetApplicableRules:

    def test_returns_all_matching_rules(self):
        rules = [
            _rule(1, priority=1, condition_value=">=100"),
            _rule(2, priority=5, condition_value=">=200"),
            _rule(3, priority=3, condition_value=">=1000"),  # لا ينطبق
        ]
        matching = get_applicable_rules_for_order(
            order_total=Decimal("500"), item_count=3,
            customer_group="default", order_date=date.today(),
            all_rules=rules,
        )
        assert len(matching) == 2
        assert 3 not in [r.id for r in matching]
