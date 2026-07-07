"""
food_cost_engine.py — Pure food-cost / COGS domain logic.
No database, no HTTP framework, no external services.

يحسب نسبة تكلفة الطعام (Food Cost %)، هامش الربح الإجمالي (Gross Margin)،
والتكلفة النظرية (Theoretical Cost) بمقارنة الوصفة (recipe/BOM) بحجم المبيعات
الفعلي — نفس التقرير القياسي في صناعة المطاعم (theoretical vs actual food
cost variance). مُستخدم من restaurant.services وcafe.services معًا (نفس
الحساب بالظبط لصنف مطعم أو كافيه)، عشان النسبة/الحدّ ما يتكررش في الموديولين.

مبني بعد مقارنة مع نظام شقيق حقيقي منشور لنفس المنتجع
(elkheima-beach-resort/backend/app/modules/erp/services/kitchen_service.py) —
ده بيستخدم float للأموال هناك (عيب معماري معروف في الكود ده). هنا Decimal
دايمًا، زي باقي resort_os/*_engine.py، بدون أي استثناء.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

TWO_PLACES = Decimal("0.01")

# نسبة تكلفة الطعام الافتراضية اللي فوقها الصنف يُعتبر "منذر" (alert) —
# قابلة للتعديل لكل استدعاء (بعض المطاعم بتقبل نسب أعلى لأصناف مميزة).
DEFAULT_FOOD_COST_THRESHOLD_PCT = Decimal("30")


def calculate_theoretical_unit_cost(recipe_lines: list[tuple[Decimal, Decimal]]) -> Decimal:
    """تكلفة تقديم واحد من الصنف = مجموع (تكلفة وحدة المكوّن × الكمية
    المطلوبة لكل تقديم) لكل سطر وصفة. ``recipe_lines`` هي قائمة
    ``(ingredient_cost, qty_per_serving)`` — مطابقة تمامًا لـ
    ``(Product.cost_price, MenuItemRecipeLine.quantity_per_unit)``.
    قائمة فاضية (صنف بدون وصفة) ترجع صفر — الـ caller هو المسؤول عن التفرقة
    بين "وصفة تكلفتها صفر" و"مفيش وصفة أصلاً" (راجع has_recipe في الطبقة
    اللي بتنادي الدالة دي)."""
    total = sum((cost * qty for cost, qty in recipe_lines), Decimal("0"))
    return total.quantize(TWO_PLACES, ROUND_HALF_UP)


def calculate_theoretical_total_cost(unit_cost: Decimal, quantity_sold: int) -> Decimal:
    """التكلفة النظرية الإجمالية = تكلفة التقديم الواحد × عدد الوحدات
    المباعة فعليًا في المدى الزمني — دي التكلفة اللي "المفروض" تكون اتصرفت
    على المخزون لو الوصفة بتتنفذ بالظبط زي ما هي مكتوبة، بتتقارن بالمصروف
    الفعلي على المشتريات لمعرفة الفرق (variance)."""
    return (unit_cost * quantity_sold).quantize(TWO_PLACES, ROUND_HALF_UP)


def food_cost_pct(cost: Decimal, revenue: Decimal) -> Optional[Decimal]:
    """نسبة تكلفة الطعام = (التكلفة / الإيراد) × 100. ``None`` لو الإيراد
    صفر أو أقل (مفيش مبيعات فعلية في المدى — نسبة "0%" هنا هتبقى مضلّلة
    زي ما لو الصنف مفيهوش وصفة أصلاً، مش نفس معنى "تكلفة صفر حقيقية")."""
    if revenue <= 0:
        return None
    return ((cost / revenue) * 100).quantize(TWO_PLACES, ROUND_HALF_UP)


def gross_margin(revenue: Decimal, cost: Decimal) -> Decimal:
    """هامش الربح الإجمالي بالقيمة = الإيراد − التكلفة النظرية."""
    return (revenue - cost).quantize(TWO_PLACES, ROUND_HALF_UP)


def gross_margin_pct(revenue: Decimal, cost: Decimal) -> Optional[Decimal]:
    """هامش الربح الإجمالي كنسبة من الإيراد. ``None`` لو الإيراد صفر أو أقل
    (نفس منطق food_cost_pct — مفيش نسبة ذات معنى بدون إيراد فعلي)."""
    if revenue <= 0:
        return None
    return (((revenue - cost) / revenue) * 100).quantize(TWO_PLACES, ROUND_HALF_UP)


def exceeds_threshold(pct: Optional[Decimal], threshold: Decimal = DEFAULT_FOOD_COST_THRESHOLD_PCT) -> bool:
    """True لو نسبة تكلفة الطعام تخطّت الحد المسموح. ``pct=None`` (مفيش
    وصفة أو مفيش مبيعات) دايمًا False — مينفعش نُنذر على حاجة مش قابلة
    للحساب أصلاً."""
    if pct is None:
        return False
    return pct > threshold


@dataclass
class FoodCostResult:
    """نتيجة حساب كاملة لصنف واحد في مدى زمني معيّن — تُبنى من الطبقة اللي
    بتجيب بيانات الوصفة/المبيعات من DB (services.py)، مفيش I/O هنا."""
    theoretical_unit_cost: Decimal
    theoretical_total_cost: Decimal
    quantity_sold: int
    revenue: Decimal
    food_cost_pct: Optional[Decimal]
    gross_margin_amount: Decimal
    gross_margin_pct: Optional[Decimal]


def compute_food_cost_result(
    recipe_lines: list[tuple[Decimal, Decimal]],
    quantity_sold: int,
    revenue: Decimal,
) -> FoodCostResult:
    """نقطة الدخول الوحيدة المستخدمة من services.py — تجمّع كل الحسابات فوق
    في نتيجة واحدة متسقة، عشان الفورمولا متتكررش بين restaurant وcafe."""
    unit_cost = calculate_theoretical_unit_cost(recipe_lines)
    total_cost = calculate_theoretical_total_cost(unit_cost, quantity_sold)
    return FoodCostResult(
        theoretical_unit_cost=unit_cost,
        theoretical_total_cost=total_cost,
        quantity_sold=quantity_sold,
        revenue=revenue,
        food_cost_pct=food_cost_pct(total_cost, revenue),
        gross_margin_amount=gross_margin(revenue, total_cost),
        gross_margin_pct=gross_margin_pct(revenue, total_cost),
    )
