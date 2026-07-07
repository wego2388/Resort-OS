"""
tests/test_engines/test_discount_engine.py
اختبارات كاملة للـ Discount Engine — بدون DB، < 1 ثانية
"""

from datetime import date, time
from decimal import Decimal

import pytest

from app.resort_os.discount_engine import (
    DiscountRule,
    DiscountResult,
    OrderContext,
    OrderLineItem,
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
    scope_type: str = "order",
    scope_outlet: str | None = None,
    scope_id: int | None = None,
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
        scope_type=scope_type,
        scope_outlet=scope_outlet,
        scope_id=scope_id,
    )


def _ctx(
    total: Decimal = Decimal("500"),
    items: int = 3,
    group: str = "default",
    order_date: date | None = None,
    order_time: time | None = None,
    outlet: str | None = None,
    line_items: list[OrderLineItem] | None = None,
) -> OrderContext:
    return OrderContext(
        total_amount=total,
        item_count=items,
        customer_group=group,
        order_date=order_date or date.today(),
        order_time=order_time or time(0, 0),
        outlet=outlet,
        line_items=line_items or [],
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


class TestTimeOfDayCondition:
    """خصم Happy Hour — condition_value بصيغة 'HH:MM-HH:MM'. الـ engine نفسه
    'ساذج' بالنسبة للتوقيت: order_time لازم يوصله جاهز بتوقيت المنتجع
    المحلي من الـ caller (راجع test_restaurant_http.py::TestHappyHourTimezone
    للتحقق من التحويل الصح من UTC فعليًا على مستوى service الحقيقي)."""

    def test_inside_window_applies(self):
        rules = [_rule(1, priority=1, condition_type="time_of_day", condition_value="14:00-17:00")]
        result = calculate_discount(Decimal("100"), rules, _ctx(order_time=time(15, 30)))
        assert result.applied

    def test_at_exact_boundaries_applies(self):
        rules = [_rule(1, priority=1, condition_type="time_of_day", condition_value="14:00-17:00")]
        assert calculate_discount(Decimal("100"), rules, _ctx(order_time=time(14, 0))).applied
        assert calculate_discount(Decimal("100"), rules, _ctx(order_time=time(17, 0))).applied

    def test_outside_window_does_not_apply(self):
        rules = [_rule(1, priority=1, condition_type="time_of_day", condition_value="14:00-17:00")]
        assert not calculate_discount(Decimal("100"), rules, _ctx(order_time=time(13, 59))).applied
        assert not calculate_discount(Decimal("100"), rules, _ctx(order_time=time(17, 1))).applied

    def test_wraps_past_midnight(self):
        """مدى عابر لمنتصف الليل — مثال خصم عشاء متأخر 22:00-02:00."""
        rules = [_rule(1, priority=1, condition_type="time_of_day", condition_value="22:00-02:00")]
        assert calculate_discount(Decimal("100"), rules, _ctx(order_time=time(23, 0))).applied
        assert calculate_discount(Decimal("100"), rules, _ctx(order_time=time(1, 0))).applied
        assert not calculate_discount(Decimal("100"), rules, _ctx(order_time=time(10, 0))).applied

    def test_malformed_condition_value_fails_closed(self):
        rules = [_rule(1, priority=1, condition_type="time_of_day", condition_value="not-a-time-range")]
        assert not calculate_discount(Decimal("100"), rules, _ctx(order_time=time(15, 0))).applied


class TestScope:
    """scope_type="order" (افتراضي) لسه بيشتغل بالظبط زي القديم (كل التستات
    فوق دي بتستخدمه بدون ما تحدده صراحة). دول تستات النطاقات الجديدة."""

    def test_order_scope_ignores_outlet(self):
        """scope_type='order' الافتراضي بيتطبق على أي outlet — نفس السلوك
        القديم قبل ما scope يتضاف خالص."""
        rules = [_rule(1, priority=1, discount_value=Decimal("10"))]
        assert calculate_discount(Decimal("500"), rules, _ctx(outlet="cafe")).applied
        assert calculate_discount(Decimal("500"), rules, _ctx(outlet=None)).applied

    def test_outlet_scope_matches_only_that_outlet(self):
        rules = [_rule(1, priority=1, scope_type="outlet", scope_outlet="cafe")]
        assert calculate_discount(Decimal("500"), rules, _ctx(outlet="cafe")).applied
        assert not calculate_discount(Decimal("500"), rules, _ctx(outlet="restaurant")).applied
        assert not calculate_discount(Decimal("500"), rules, _ctx(outlet=None)).applied

    def test_category_scope_discounts_only_matching_lines(self):
        """خصم 20% على فئة الحلويات (category_id=5) بس — مش على إجمالي
        الطلب كله. الطلب فيه صنف حلويات بـ 100 وصنف تاني (فئة تانية) بـ 400."""
        rules = [_rule(
            1, priority=1, discount_type="percentage", discount_value=Decimal("20"),
            scope_type="category", scope_outlet="restaurant", scope_id=5,
        )]
        line_items = [
            OrderLineItem(item_id=1, quantity=1, unit_price=Decimal("100"), category_id=5),
            OrderLineItem(item_id=2, quantity=1, unit_price=Decimal("400"), category_id=9),
        ]
        result = calculate_discount(
            Decimal("500"), rules,
            _ctx(total=Decimal("500"), outlet="restaurant", line_items=line_items),
        )
        assert result.applied
        assert result.amount_saved == Decimal("20.00")   # 20% من الـ 100 بس، مش من الـ 500
        assert result.final_amount == Decimal("480.00")

    def test_category_scope_no_matching_line_does_not_apply(self):
        rules = [_rule(
            1, priority=1, scope_type="category", scope_outlet="restaurant", scope_id=5,
        )]
        line_items = [OrderLineItem(item_id=2, quantity=1, unit_price=Decimal("400"), category_id=9)]
        result = calculate_discount(
            Decimal("400"), rules,
            _ctx(total=Decimal("400"), outlet="restaurant", line_items=line_items),
        )
        assert not result.applied

    def test_item_scope_discounts_only_that_item(self):
        rules = [_rule(
            1, priority=1, discount_type="fixed_amount", discount_value=Decimal("15"),
            scope_type="item", scope_outlet="cafe", scope_id=42,
        )]
        line_items = [
            OrderLineItem(item_id=42, quantity=2, unit_price=Decimal("30"), category_id=1),  # 60
            OrderLineItem(item_id=7,  quantity=1, unit_price=Decimal("100"), category_id=2),
        ]
        result = calculate_discount(
            Decimal("160"), rules,
            _ctx(total=Decimal("160"), outlet="cafe", line_items=line_items),
        )
        assert result.applied
        assert result.amount_saved == Decimal("15")
        assert result.final_amount == Decimal("145")

    def test_scope_and_outlet_must_both_match(self):
        """رقم item_id ممكن يتصادف بين menu_items (مطعم) وcafe_items (كافيه)
        — scope_outlet لازم يطابق ctx.outlet برضه، مش بس scope_id."""
        rules = [_rule(
            1, priority=1, scope_type="item", scope_outlet="restaurant", scope_id=42,
        )]
        line_items = [OrderLineItem(item_id=42, quantity=1, unit_price=Decimal("100"))]
        result = calculate_discount(
            Decimal("100"), rules,
            _ctx(total=Decimal("100"), outlet="cafe", line_items=line_items),  # outlet مختلف
        )
        assert not result.applied

    def test_fixed_amount_scope_capped_to_scoped_base_not_whole_order(self):
        """fixed_amount أكبر من قيمة السطر المستهدف لازم يتقص على قيمة السطر
        بس، مش على إجمالي الطلب كله."""
        rules = [_rule(
            1, priority=1, discount_type="fixed_amount", discount_value=Decimal("1000"),
            scope_type="item", scope_outlet="cafe", scope_id=1,
        )]
        line_items = [
            OrderLineItem(item_id=1, quantity=1, unit_price=Decimal("50")),
            OrderLineItem(item_id=2, quantity=1, unit_price=Decimal("450")),
        ]
        result = calculate_discount(
            Decimal("500"), rules,
            _ctx(total=Decimal("500"), outlet="cafe", line_items=line_items),
        )
        assert result.amount_saved == Decimal("50")   # مش 500 ولا 1000
        assert result.final_amount == Decimal("450")


class TestComboItems:
    """condition_type='combo_items' — 'item_id:qty,item_id:qty'، لازم يترافق
    مع scope_type='outlet' (validated في الـ Pydantic schema، مش الـ engine
    نفسه — الـ engine بيثق في القيم اللي وصلته)."""

    def test_combo_not_met_when_item_missing(self):
        rules = [_rule(
            1, priority=1, condition_type="combo_items", condition_value="1:1,2:1",
            scope_type="outlet", scope_outlet="cafe",
        )]
        line_items = [OrderLineItem(item_id=1, quantity=1, unit_price=Decimal("30"))]
        result = calculate_discount(
            Decimal("30"), rules, _ctx(total=Decimal("30"), outlet="cafe", line_items=line_items),
        )
        assert not result.applied

    def test_combo_not_met_when_quantity_insufficient(self):
        rules = [_rule(
            1, priority=1, condition_type="combo_items", condition_value="1:2",
            scope_type="outlet", scope_outlet="cafe",
        )]
        line_items = [OrderLineItem(item_id=1, quantity=1, unit_price=Decimal("30"))]
        result = calculate_discount(
            Decimal("30"), rules, _ctx(total=Decimal("30"), outlet="cafe", line_items=line_items),
        )
        assert not result.applied

    def test_combo_fixed_price_charges_flat_price_for_the_bundle(self):
        """ساندوتش (30) + مشروب (25) = 55 عادةً، لكن الـ combo بـ 40 ثابت."""
        rules = [_rule(
            1, priority=1, condition_type="combo_items", condition_value="1:1,2:1",
            discount_type="combo_fixed_price", discount_value=Decimal("40"),
            scope_type="outlet", scope_outlet="cafe",
        )]
        line_items = [
            OrderLineItem(item_id=1, quantity=1, unit_price=Decimal("30")),
            OrderLineItem(item_id=2, quantity=1, unit_price=Decimal("25")),
        ]
        result = calculate_discount(
            Decimal("55"), rules, _ctx(total=Decimal("55"), outlet="cafe", line_items=line_items),
        )
        assert result.applied
        assert result.amount_saved == Decimal("15.00")   # 55 - 40
        assert result.final_amount == Decimal("40.00")

    def test_combo_ignores_extra_quantity_beyond_spec(self):
        """العميل طلب 3 من الصنف 1 بس الـ combo محتاج واحد بس — الفائض مش
        جزء من الـ combo، مبيتحسبش في الـ base بتاع الخصم."""
        rules = [_rule(
            1, priority=1, condition_type="combo_items", condition_value="1:1,2:1",
            discount_type="combo_fixed_price", discount_value=Decimal("40"),
            scope_type="outlet", scope_outlet="cafe",
        )]
        line_items = [
            OrderLineItem(item_id=1, quantity=3, unit_price=Decimal("30")),  # 90 فعليًا
            OrderLineItem(item_id=2, quantity=1, unit_price=Decimal("25")),
        ]
        result = calculate_discount(
            Decimal("115"), rules, _ctx(total=Decimal("115"), outlet="cafe", line_items=line_items),
        )
        assert result.applied
        # base الـ combo = (30×1) + (25×1) = 55 — مش 90+25
        assert result.amount_saved == Decimal("15.00")

    def test_combo_fixed_price_never_negative_when_bundle_already_cheaper(self):
        rules = [_rule(
            1, priority=1, condition_type="combo_items", condition_value="1:1",
            discount_type="combo_fixed_price", discount_value=Decimal("100"),
            scope_type="outlet", scope_outlet="cafe",
        )]
        line_items = [OrderLineItem(item_id=1, quantity=1, unit_price=Decimal("30"))]
        result = calculate_discount(
            Decimal("30"), rules, _ctx(total=Decimal("30"), outlet="cafe", line_items=line_items),
        )
        assert result.applied
        assert result.amount_saved == Decimal("0.00")
        assert result.final_amount == Decimal("30.00")

    def test_combo_wrong_outlet_does_not_apply(self):
        rules = [_rule(
            1, priority=1, condition_type="combo_items", condition_value="1:1,2:1",
            discount_type="combo_fixed_price", discount_value=Decimal("40"),
            scope_type="outlet", scope_outlet="cafe",
        )]
        line_items = [
            OrderLineItem(item_id=1, quantity=1, unit_price=Decimal("30")),
            OrderLineItem(item_id=2, quantity=1, unit_price=Decimal("25")),
        ]
        result = calculate_discount(
            Decimal("55"), rules,
            _ctx(total=Decimal("55"), outlet="restaurant", line_items=line_items),  # outlet مختلف
        )
        assert not result.applied
