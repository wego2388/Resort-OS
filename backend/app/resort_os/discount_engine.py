"""
app/resort_os/discount_engine.py
═══════════════════════════════════════════════════════════════════════
Pure Domain Engine — بدون FastAPI أو SQLAlchemy imports
يستقبل data objects ويُرجع نتائج — قابل للاختبار بالكامل بدون DB

الـ ORM model (ConditionalDiscount) يعيش في app/modules/finance/models.py
هذا الـ engine يعمل على plain dataclasses فقط.

⚠️ توقيت — كل حقل زمني هنا (order_date, order_time) لازم يوصل من الـ caller
محسوب بتوقيت المنتجع (Africa/Cairo)، مش توقيت UTC الخام. الـ engine نفسه
"ساذج" بالنسبة للتوقيت (بياخد date/time زي ما هي بدون تحويل) — المسؤولية
الكاملة عن التحويل الصحيح على عاتق الـ caller (راجع app.resort_os.timezone_utils
و §13 في CLAUDE.md لفئة الباج دي اللي اتكشفت في 6 موديولات مختلفة).
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

CONDITION_TYPES = (
    "total_amount", "item_count", "day_of_week", "customer_group",
    "time_of_day", "combo_items",
)
DISCOUNT_TYPES = ("percentage", "fixed_amount", "free_item", "combo_fixed_price")
SCOPE_TYPES = ("order", "outlet", "category", "item")
OUTLETS = ("restaurant", "cafe", "beach")


# ─────────────────────── Data Transfer Objects ───────────────────────

@dataclass
class DiscountRule:
    """
    يُمثّل صف ConditionalDiscount من DB — بدون SQLAlchemy dependency.
    النموذج في DB له نفس الحقول + id, branch_id, created_at.

    condition_value — الصيغة حسب condition_type:
        total_amount / item_count → ">=500" | ">= 3" | "500" (بدون operator = تساوي)
        day_of_week               → "friday,saturday"
        customer_group            → "vip,staff"
        time_of_day               → "HH:MM-HH:MM" مثال "14:00-17:00" (بتوقيت
                                     المنتجع المحلي — راجع تحذير التوقيت أعلى
                                     الملف). لو start > end بيُفهم كمدى عابر
                                     لمنتصف الليل (مثال "22:00-02:00").
        combo_items                → "item_id:qty,item_id:qty" مثال "12:1,15:2"
                                     — يعني: لازم يكون في الطلب صنف 12 بكمية
                                     ≥1 وصنف 15 بكمية ≥2 معًا. لازم يترافق مع
                                     scope_type="outlet" (راجع تعليق scope_type
                                     تحت) عشان نعرف نقارن بجدول أصناف مين
                                     (menu_items بتاع المطعم ولا cafe_items).

    scope — نطاق تطبيق الخصم (الافتراضي "order" = زي القديم بالظبط):
        scope_type="order"    → الخصم على إجمالي الطلب كله، أي outlet.
        scope_type="outlet"   → الخصم على إجمالي الطلب، بس لو outlet الطلب
                                 (ctx.outlet) يطابق scope_outlet بالظبط.
                                 (مثال: "10% خصم كافيه بس" — لا يمس مطعم/شاطئ)
        scope_type="category" → الخصم على سطور الطلب المنتمية لـ scope_id
                                 (category id) في outlet=scope_outlet بس —
                                 مش على إجمالي الطلب.
        scope_type="item"     → زي category بس على صنف واحد بعينه (scope_id
                                 = item id).
        condition_type="combo_items" لازم يستخدم scope_type="outlet" (مش
        "item"/"category") — قائمة الأصناف نفسها جاية من condition_value،
        و scope_outlet هنا بس بيحدد أي جدول أصناف (منع تلبيس بين menu_items.id
        و cafe_items.id لو الرقمين اتصادفوا بالغلط).
    """
    id: int
    condition_type: Literal[
        "total_amount", "item_count", "day_of_week", "customer_group",
        "time_of_day", "combo_items",
    ]
    condition_value: str
    discount_type: Literal["percentage", "fixed_amount", "free_item", "combo_fixed_price"]
    discount_value: Decimal
    max_uses: int          # -1 = unlimited
    valid_from: date
    valid_until: date
    priority: int          # الأعلى يُطبَّق أولاً
    uses_count: int = 0    # كم مرة استُخدم حتى الآن
    scope_type: Literal["order", "outlet", "category", "item"] = "order"
    scope_outlet: str | None = None   # "restaurant" | "cafe" | "beach"
    scope_id: int | None = None       # category id أو item id — حسب scope_type
    created_at: date = field(default_factory=date.today)


@dataclass
class OrderLineItem:
    """سطر واحد من الطلب — مطلوب بس لتقييم scope على مستوى صنف/فئة أو combo.
    غير مطلوب لخصومات على مستوى الطلب كله (scope_type="order"/"outlet")."""
    item_id: int
    quantity: int
    unit_price: Decimal
    category_id: int | None = None

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity


@dataclass
class OrderContext:
    """سياق الطلب المطلوب لتقييم الـ discounts."""
    total_amount: Decimal
    item_count: int
    order_date: date
    order_time: time = time(0, 0)   # وقت اليوم بتوقيت المنتجع المحلي (Africa/Cairo) — راجع تحذير التوقيت أعلى الملف
    customer_group: str = "default"   # default|vip|staff|b2b
    outlet: str | None = None         # "restaurant" | "cafe" | "beach" — الـ outlet اللي الطلب ده منه
    line_items: list[OrderLineItem] = field(default_factory=list)


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

    if ctype == "time_of_day":
        return _is_time_in_range(ctx.order_time, cvalue)

    if ctype == "combo_items":
        return _is_combo_met(cvalue, ctx)

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


def _parse_hhmm(value: str) -> time:
    hh, mm = value.strip().split(":")
    return time(int(hh), int(mm))


def _is_time_in_range(order_time: time, condition: str) -> bool:
    """condition بصيغة 'HH:MM-HH:MM' (راجع docstring DiscountRule.condition_value
    لتفاصيل الصيغة). فشل التحليل (صيغة غلط) → False دايمًا (fail-closed، نفس
    فلسفة _compare_numeric)."""
    parts = condition.strip().split("-")
    if len(parts) != 2:
        return False
    try:
        start, end = _parse_hhmm(parts[0]), _parse_hhmm(parts[1])
    except (ValueError, IndexError):
        return False
    if start <= end:
        return start <= order_time <= end
    # مدى عابر لمنتصف الليل (مثال "22:00-02:00")
    return order_time >= start or order_time <= end


def _parse_combo_spec(condition_value: str) -> dict[int, int]:
    """يحلّل صيغة 'item_id:qty,item_id:qty' لـ dict {item_id: min_qty}.
    أي جزء غير صالح (تنسيق غلط، qty<=0) → dict فاضي (fail-closed → الشرط
    مش هيتحقق أبدًا بدل ما يطبّق combo مشوّه)."""
    spec: dict[int, int] = {}
    for part in condition_value.strip().split(","):
        part = part.strip()
        if not part:
            continue
        pieces = part.split(":")
        if len(pieces) != 2:
            return {}
        try:
            item_id, qty = int(pieces[0]), int(pieces[1])
        except ValueError:
            return {}
        if qty <= 0:
            return {}
        spec[item_id] = qty
    return spec


def _is_combo_met(condition_value: str, ctx: OrderContext) -> bool:
    spec = _parse_combo_spec(condition_value)
    if not spec:
        return False
    qty_by_item: dict[int, int] = {}
    for li in ctx.line_items:
        qty_by_item[li.item_id] = qty_by_item.get(li.item_id, 0) + li.quantity
    return all(qty_by_item.get(item_id, 0) >= min_qty for item_id, min_qty in spec.items())


def _is_scope_met(rule: DiscountRule, ctx: OrderContext) -> bool:
    """يتحقق إن كان نطاق الـ rule (outlet/category/item) منطبق على الطلب ده.
    لا علاقة له بـ condition — ده تحقق تاني منفصل تمامًا (rule ممكن تستوفي
    الـ condition لكن تكون خارج نطاقها، أو العكس)."""
    if rule.scope_type == "order":
        return True
    if rule.scope_type == "outlet":
        return ctx.outlet is not None and ctx.outlet == rule.scope_outlet
    if rule.scope_type in ("category", "item"):
        if ctx.outlet is None or ctx.outlet != rule.scope_outlet:
            return False
        if rule.scope_type == "category":
            return any(li.category_id == rule.scope_id for li in ctx.line_items)
        return any(li.item_id == rule.scope_id for li in ctx.line_items)
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
    الدالة الرئيسية — تُطبَّق قاعدة واحدة فقط (الأعلى priority) من بين القواعد
    اللي (1) صالحة تاريخيًا/استخدامًا (2) شرطها متحقق (3) نطاقها منطبق.

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

    eligible = [
        r for r in rules
        if _is_valid(r, ctx.order_date) and _is_condition_met(r, ctx) and _is_scope_met(r, ctx)
    ]

    if not eligible:
        return no_discount

    # ترتيب: priority تنازلي، عند تعادل: id تصاعدي
    eligible.sort(key=_sort_key)
    best = eligible[0]

    amount_saved = _calculate_amount_saved(order_total, best, ctx)
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


def _combo_actual_total(rule: DiscountRule, ctx: OrderContext) -> Decimal:
    """السعر الأصلي (قبل خصم) لعناصر الـ combo بس — الكمية المحدّدة في
    condition_value، مش أي كمية زيادة طلبها العميل فعليًا. بياخد unit_price
    من أول سطر مطابق لكل item_id في الطلب (لو الصنف ظهر في أكتر من سطر
    بأسعار مختلفة نظريًا — مينفعش عمليًا لأن unit_price snapshot ثابت وقت
    الطلب لنفس الصنف)."""
    spec = _parse_combo_spec(rule.condition_value)
    unit_price_by_item: dict[int, Decimal] = {}
    for li in ctx.line_items:
        unit_price_by_item.setdefault(li.item_id, li.unit_price)
    total = Decimal("0")
    for item_id, qty in spec.items():
        total += unit_price_by_item.get(item_id, Decimal("0")) * qty
    return total


def _scope_base_amount(rule: DiscountRule, ctx: OrderContext, order_total: Decimal) -> Decimal:
    """المبلغ اللي الخصم بيُحسب عليه فعليًا — إجمالي الطلب كله لنطاق
    order/outlet، أو مجموع سطور الفئة/الصنف المطابقة بس لنطاق category/item."""
    if rule.scope_type in ("order", "outlet"):
        return order_total
    if rule.scope_type == "category":
        return sum(
            (li.line_total for li in ctx.line_items if li.category_id == rule.scope_id),
            Decimal("0"),
        )
    if rule.scope_type == "item":
        return sum(
            (li.line_total for li in ctx.line_items if li.item_id == rule.scope_id),
            Decimal("0"),
        )
    return Decimal("0")


def _calculate_amount_saved(order_total: Decimal, rule: DiscountRule, ctx: OrderContext) -> Decimal:
    """يحسب مبلغ الخصم — الأساس (base) المحسوب عليه النسبة/المبلغ الثابت
    بيتحدد حسب condition_type (combo_items بيغلب scope) وإلا حسب scope_type."""
    base = _combo_actual_total(rule, ctx) if rule.condition_type == "combo_items" \
        else _scope_base_amount(rule, ctx, order_total)

    if rule.discount_type == "combo_fixed_price":
        # discount_value هنا مش "قيمة تُخصَم" زي باقي الأنواع — هو السعر
        # النهائي الثابت للـ base بالكامل (مثال: ساندوتش+مشروب بـ 65 جنيه
        # بدل سعرهم منفصلين). amount_saved = الفرق (لو موجب).
        return max(Decimal("0"), base - rule.discount_value).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    if rule.discount_type == "percentage":
        pct = min(rule.discount_value, Decimal("100"))  # لا يتجاوز 100%
        return (base * pct / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    if rule.discount_type == "fixed_amount":
        return min(rule.discount_value, base)  # لا يتجاوز الـ base
    if rule.discount_type == "free_item":
        return rule.discount_value  # قيمة الصنف المجاني المُحددة
    return Decimal("0")


def get_applicable_rules_for_order(
    order_total: Decimal,
    item_count: int,
    customer_group: str,
    order_date: date,
    all_rules: list[DiscountRule],
    order_time: time = time(0, 0),
    outlet: str | None = None,
    line_items: list[OrderLineItem] | None = None,
) -> list[DiscountRule]:
    """
    Helper — يُرجع قائمة الـ rules المنطبقة (للعرض في الـ UI مثلاً).
    """
    ctx = OrderContext(
        total_amount=order_total,
        item_count=item_count,
        customer_group=customer_group,
        order_date=order_date,
        order_time=order_time,
        outlet=outlet,
        line_items=line_items or [],
    )
    return [
        r for r in all_rules
        if _is_valid(r, order_date) and _is_condition_met(r, ctx) and _is_scope_met(r, ctx)
    ]
