"""
app/resort_os/discount_engine.py
═══════════════════════════════════════════════════════════════════════
Pure Domain Engine — بدون FastAPI أو SQLAlchemy imports
يستقبل data objects ويُرجع نتائج — قابل للاختبار بالكامل بدون DB

الـ ORM model (ConditionalDiscount) يعيش في app/modules/finance/models.py
هذا الـ engine يعمل على plain dataclasses فقط.
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal


# ─────────────────────── Data Transfer Objects ───────────────────────

@dataclass
class DiscountRule:
    """
    يُمثّل صف ConditionalDiscount من DB — بدون SQLAlchemy dependency.
    النموذج في DB له نفس الحقول + id, branch_id, created_at.
    """
    id: int
    condition_type: Literal["total_amount", "item_count", "day_of_week", "customer_group"]
    condition_value: str   # ">= 500" | ">= 3" | "friday,saturday" | "vip"
    discount_type: Literal["percentage", "fixed_amount", "free_item"]
    discount_value: Decimal
    max_uses: int          # -1 = unlimited
    valid_from: date
    valid_until: date
    priority: int          # الأعلى يُطبَّق أولاً
    uses_count: int = 0    # كم مرة استُخدم حتى الآن
    created_at: date = field(default_factory=date.today)


@dataclass
class OrderContext:
    """سياق الطلب المطلوب لتقييم الـ discounts."""
    total_amount: Decimal
    item_count: int
    order_date: date
    customer_group: str = "default"   # default|vip|staff|b2b
    applicable_rule_id: int | None = None


@dataclass
class DiscountResult:
    """نتيجة تطبيق الـ discount."""
    applied: bool
    rule_id: int | None
    discount_type: str | None
    discount_value: Decimal
    amount_saved: Decimal
    final_amount: Decimal
    reason: str


# ──────────────────────── Engine Functions ───────────────────────────

def _is_condition_met(rule: DiscountRule, ctx: OrderContext) -> bool:
    """يتحقق إن كان الـ condition مُستوفى."""
    ctype = rule.condition_type
    cvalue = rule.condition_value.strip()

    if ctype == "total_amount":
        # تنسيق: ">=500" أو ">= 500" أو ">=500.00"
        return _compare_numeric(ctx.total_amount, cvalue)

    if ctype == "item_count":
        return _compare_numeric(Decimal(ctx.item_count), cvalue)

    if ctype == "day_of_week":
        day_names = {
            0: "monday", 1: "tuesday", 2: "wednesday", 3: "thursday",
            4: "friday", 5: "saturday", 6: "sunday",
        }
        today_name = day_names.get(ctx.order_date.weekday(), "")
        allowed_days = [d.strip().lower() for d in cvalue.split(",")]
        return today_name in allowed_days

    if ctype == "customer_group":
        allowed_groups = [g.strip().lower() for g in cvalue.split(",")]
        return ctx.customer_group.lower() in allowed_groups

    return False


def _compare_numeric(value: Decimal, condition: str) -> bool:
    """يُحلّل ويقيّم شرط رقمي مثل '>=500' أو '<100'."""
    condition = condition.replace(" ", "")
    for op, func in [
        (">=", lambda v, t: v >= t),
        ("<=", lambda v, t: v <= t),
        (">",  lambda v, t: v > t),
        ("<",  lambda v, t: v < t),
        ("==", lambda v, t: v == t),
        ("=",  lambda v, t: v == t),
    ]:
        if condition.startswith(op):
            try:
                threshold = Decimal(condition[len(op):])
                return func(value, threshold)
            except Exception:
                return False
    # رقم بدون operator → تساوي
    try:
        return value == Decimal(condition)
    except Exception:
        return False


def _is_valid(rule: DiscountRule, check_date: date) -> bool:
    """يتحقق من صلاحية الـ discount."""
    if not (rule.valid_from <= check_date <= rule.valid_until):
        return False
    if rule.max_uses != -1 and rule.uses_count >= rule.max_uses:
        return False
    return True


def _sort_key(rule: DiscountRule) -> tuple:
    """
    Tie-breaker محدد:
    1. priority تنازلي (الأعلى أولاً)
    2. عند تعادل الـ priority: id تصاعدي (الأقدم يفوز — deterministic)

    هذا يضمن نتيجة واحدة دائماً بغض النظر عن ترتيب الـ query.
    """
    return (-rule.priority, rule.id)


def calculate_discount(
    order_total: Decimal,
    rules: list[DiscountRule],
    ctx: OrderContext,
) -> DiscountResult:
    """
    الدالة الرئيسية — تُطبَّق قاعدة واحدة فقط (الأعلى priority).

    عند تعادل الـ priority: الـ rule ذات أصغر id تفوز (الأولى في الإنشاء).

    Args:
        order_total: إجمالي الطلب قبل الخصم
        rules: قائمة كل الـ discount rules النشطة
        ctx: سياق الطلب

    Returns:
        DiscountResult مع التفاصيل
    """
    no_discount = DiscountResult(
        applied=False,
        rule_id=None,
        discount_type=None,
        discount_value=Decimal("0"),
        amount_saved=Decimal("0"),
        final_amount=order_total,
        reason="لا يوجد خصم منطبق",
    )

    if not rules:
        return no_discount

    # فلتر: valid + condition met
    eligible = [
        r for r in rules
        if _is_valid(r, ctx.order_date) and _is_condition_met(r, ctx)
    ]

    if not eligible:
        return no_discount

    # ترتيب: priority تنازلي، عند تعادل: id تصاعدي
    eligible.sort(key=_sort_key)
    best = eligible[0]

    amount_saved = _calculate_amount_saved(order_total, best)
    final = (order_total - amount_saved).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return DiscountResult(
        applied=True,
        rule_id=best.id,
        discount_type=best.discount_type,
        discount_value=best.discount_value,
        amount_saved=amount_saved,
        final_amount=max(final, Decimal("0")),
        reason=f"خصم #{best.id} — priority={best.priority}",
    )


def _calculate_amount_saved(total: Decimal, rule: DiscountRule) -> Decimal:
    """يحسب مبلغ الخصم."""
    if rule.discount_type == "percentage":
        pct = min(rule.discount_value, Decimal("100"))  # لا يتجاوز 100%
        return (total * pct / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    if rule.discount_type == "fixed_amount":
        return min(rule.discount_value, total)  # لا يتجاوز الإجمالي
    if rule.discount_type == "free_item":
        return rule.discount_value  # قيمة الصنف المجاني المُحددة
    return Decimal("0")


def get_applicable_rules_for_order(
    order_total: Decimal,
    item_count: int,
    customer_group: str,
    order_date: date,
    all_rules: list[DiscountRule],
) -> list[DiscountRule]:
    """
    Helper — يُرجع قائمة الـ rules المنطبقة (للعرض في الـ UI مثلاً).
    """
    ctx = OrderContext(
        total_amount=order_total,
        item_count=item_count,
        customer_group=customer_group,
        order_date=order_date,
    )
    return [r for r in all_rules if _is_valid(r, order_date) and _is_condition_met(r, ctx)]
