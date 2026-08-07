"""
resort_os/owner_analytics_engine.py
═══════════════════════════════════════════════════════════════════════
Owner Intelligence Cockpit — Analytics Engine (Decision 0004, Phase 6).

Pure computation engine — no FastAPI, no SQLAlchemy, no external calls.
نفس نمط food_cost_engine.py / discount_engine.py:
  • Decimal arithmetic طول الوقت — لا float.
  • stdlib فقط (statistics, decimal) — لا pandas، لا numpy.
  • كل دالة deterministic وقابلة للاختبار بدون DB.
  • لا AI، لا LLM، لا external service call.

الدوال:
  classify_abc          — ABC/Pareto classification لقائمة items
  compute_item_margin   — هامش ربح صنف واحد
  detect_variance       — flag تغيير غير طبيعي في نسبة مصروف/إيراد
  score_supplier_concentration — تركّز الإنفاق بالموردين
  compute_pr_po_variance — فرق estimate vs actual في طلبات الشراء
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

TWO   = Decimal("0.01")
ONE   = Decimal("0.1")
ZERO  = Decimal("0")

# ── ABC/Pareto thresholds ──────────────────────────────────────────────
ABC_A_THRESHOLD = Decimal("70")   # أعلى 70% من الإيراد → Class A
ABC_B_THRESHOLD = Decimal("90")   # الـ 70-90% → Class B
# ما تبقّى (90-100%) → Class C

# ── Exception tiers ───────────────────────────────────────────────────
EXCEPTION_TIERS = ("critical", "attention", "watch")
# الترتيب داخل كل tier: impact × confidence (تنازلي)

# عتبة فرق الكاش الافتراضية لـ critical exception (بالجنيه)
SHIFT_VARIANCE_CRITICAL_EGP = Decimal("200")
SHIFT_VARIANCE_ATTENTION_EGP = Decimal("50")


# ══════════════════════════════════════════════════════════════════════
# Data structures
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ItemMetric:
    """مقياس صنف واحد — input لـ classify_abc وcompute_item_margin."""
    item_id:       int
    name:          str
    quantity_sold: int
    revenue:       Decimal
    recipe_cost:   Optional[Decimal] = None   # تكلفة وصفة الوحدة — None لو مفيش وصفة
    # يُعبأ بواسطة classify_abc
    abc_class:     Optional[str]     = None   # 'A' | 'B' | 'C'
    cumulative_pct: Optional[Decimal] = None
    # يُعبأ بواسطة compute_item_margin
    margin_pct:    Optional[Decimal] = None
    margin_amount: Optional[Decimal] = None


@dataclass
class ExpenseLine:
    """سطر مصروف واحد مع تفاصيل الفترتين للمقارنة."""
    account_code:   str
    account_name:   str
    current_amount: Decimal
    prior_amount:   Decimal
    current_revenue: Decimal
    prior_revenue:  Decimal
    # يُعبأ بواسطة detect_variance
    current_pct:    Optional[Decimal] = None
    prior_pct:      Optional[Decimal] = None
    variance_flag:  bool = False
    variance_delta: Optional[Decimal] = None   # النقاط المئوية + تعني ارتفاع


@dataclass
class SupplierSpend:
    """إنفاق مورّد واحد مع نسبته من الإجمالي."""
    supplier_id:   int
    supplier_name: str
    total_spend:   Decimal
    spend_pct:     Decimal = ZERO
    concentration_flag: bool = False   # True لو > CONCENTRATION_THRESHOLD


@dataclass
class PRPOVarianceLine:
    """مقارنة طلب شراء vs أمر شراء لصنف واحد."""
    product_id:      int
    product_name:    str
    estimated_cost:  Decimal
    actual_cost:     Decimal
    variance_amount: Decimal   # actual - estimated
    variance_pct:    Optional[Decimal]   # None لو estimated=0


# ══════════════════════════════════════════════════════════════════════
# ABC / Pareto Classification
# ══════════════════════════════════════════════════════════════════════

def classify_abc(items: list[ItemMetric]) -> list[ItemMetric]:
    """
    يصنّف قائمة items بـ ABC/Pareto بناءً على الإيراد.

    القاعدة:
      A = أعلى items تغطي 0–70% من إجمالي الإيراد
      B = items التالية تغطي 70–90%
      C = الباقي (90–100%)

    Determinism:
      • ترتيب تنازلي بالإيراد.
      • Tie-break بالاسم أبجدياً (ضروري للـ tests — نفس القائمة دايماً نفس النتيجة).
      • قائمة فارغة → قائمة فارغة.
      • صنف واحد → class A (هو 100% من الإيراد — threshold 70% متحقق).
      • كل الأصناف نفس الإيراد → يكملون أبجدياً حتى يتجاوزوا 70% ثم B ثم C.
    """
    if not items:
        return []

    # ترتيب تنازلي بالإيراد ثم أبجدي كـ tie-break
    sorted_items = sorted(items, key=lambda x: (-x.revenue, x.name))

    total_revenue = sum(i.revenue for i in sorted_items)
    if total_revenue == ZERO:
        # لا يوجد إيراد — كل شيء Class C
        for item in sorted_items:
            item.abc_class = "C"
            item.cumulative_pct = Decimal("100")
        return sorted_items

    cumulative = ZERO
    for item in sorted_items:
        cumulative += item.revenue
        pct = (cumulative / total_revenue * Decimal("100")).quantize(TWO, ROUND_HALF_UP)
        item.cumulative_pct = pct

        # نحدد الـ class بناءً على النسبة التراكمية قبل إضافة هذا الصنف
        # (السؤال: هل الإيراد الإجمالي قبل هذا الصنف كان أقل من الحد؟)
        prior_cumulative = cumulative - item.revenue
        prior_pct = (prior_cumulative / total_revenue * Decimal("100")).quantize(TWO, ROUND_HALF_UP)

        if prior_pct < ABC_A_THRESHOLD:
            item.abc_class = "A"
        elif prior_pct < ABC_B_THRESHOLD:
            item.abc_class = "B"
        else:
            item.abc_class = "C"

    return sorted_items


# ══════════════════════════════════════════════════════════════════════
# Per-item Margin
# ══════════════════════════════════════════════════════════════════════

def compute_item_margin(item: ItemMetric) -> ItemMetric:
    """
    يحسب هامش الربح للصنف:
      margin_amount = revenue - (recipe_cost × quantity_sold)
      margin_pct    = margin_amount / revenue × 100

    لو recipe_cost = None → margin_pct/amount تبقى None (مفيش وصفة مسجّلة).
    لو revenue = 0 → margin_pct = None (قسمة على صفر).
    """
    if item.recipe_cost is None:
        item.margin_pct    = None
        item.margin_amount = None
        return item

    total_cost = (item.recipe_cost * item.quantity_sold).quantize(TWO, ROUND_HALF_UP)
    item.margin_amount = (item.revenue - total_cost).quantize(TWO, ROUND_HALF_UP)

    if item.revenue == ZERO:
        item.margin_pct = None
    else:
        item.margin_pct = (item.margin_amount / item.revenue * Decimal("100")).quantize(TWO, ROUND_HALF_UP)

    return item


def enrich_items_with_margin(items: list[ItemMetric]) -> list[ItemMetric]:
    """يطبّق compute_item_margin على كل القائمة."""
    return [compute_item_margin(item) for item in items]


# ══════════════════════════════════════════════════════════════════════
# Expense Variance Detection
# ══════════════════════════════════════════════════════════════════════

# الحد الافتراضي: 20% relative change في نسبة المصروف/الإيراد بين الفترتين
VARIANCE_THRESHOLD_PCT = Decimal("20")


def detect_variance(
    lines: list[ExpenseLine],
    threshold_pct: Decimal = VARIANCE_THRESHOLD_PCT,
) -> list[ExpenseLine]:
    """
    يضع variance_flag=True على كل سطر مصروف تغيّرت نسبته بشكل غير طبيعي.

    المنطق:
      current_pct = current_amount / current_revenue × 100
      prior_pct   = prior_amount   / prior_revenue   × 100
      variance_delta = current_pct - prior_pct  (بالنقاط المئوية)

      flag = True لو |variance_delta| / prior_pct > threshold_pct/100
             أو لو prior_pct = 0 وcurrent_pct > 0 (ظهر مصروف جديد)

    Division-safe: None لو المقام صفر.
    """
    for line in lines:
        # احسب النسب
        if line.current_revenue > ZERO:
            line.current_pct = (line.current_amount / line.current_revenue * Decimal("100")).quantize(TWO, ROUND_HALF_UP)
        else:
            line.current_pct = None

        if line.prior_revenue > ZERO:
            line.prior_pct = (line.prior_amount / line.prior_revenue * Decimal("100")).quantize(TWO, ROUND_HALF_UP)
        else:
            line.prior_pct = None

        # احسب delta
        if line.current_pct is not None and line.prior_pct is not None:
            line.variance_delta = (line.current_pct - line.prior_pct).quantize(TWO, ROUND_HALF_UP)

            if line.prior_pct == ZERO:
                # مصروف جديد
                line.variance_flag = line.current_pct > ZERO
            else:
                relative_change = abs(line.variance_delta) / line.prior_pct * Decimal("100")
                line.variance_flag = relative_change > threshold_pct

        elif line.current_pct is not None and line.prior_pct is None:
            # لم يكن موجوداً من قبل
            line.variance_delta = line.current_pct
            line.variance_flag  = line.current_pct > ZERO

        else:
            line.variance_delta = None
            line.variance_flag  = False

    return lines


# ══════════════════════════════════════════════════════════════════════
# Supplier Concentration
# ══════════════════════════════════════════════════════════════════════

CONCENTRATION_THRESHOLD = Decimal("50")   # > 50% → تركّز عالٍ


def score_supplier_concentration(
    suppliers: list[SupplierSpend],
    concentration_threshold: Decimal = CONCENTRATION_THRESHOLD,
) -> list[SupplierSpend]:
    """
    يحسب نسبة كل مورد من إجمالي الإنفاق ويضع concentration_flag لو تجاوز
    الحد.

    ترتيب تنازلي بالإنفاق.
    """
    if not suppliers:
        return []

    total = sum(s.total_spend for s in suppliers)
    if total == ZERO:
        return sorted(suppliers, key=lambda x: -x.total_spend)

    for s in suppliers:
        s.spend_pct = (s.total_spend / total * Decimal("100")).quantize(TWO, ROUND_HALF_UP)
        s.concentration_flag = s.spend_pct > concentration_threshold

    return sorted(suppliers, key=lambda x: -x.total_spend)


# ══════════════════════════════════════════════════════════════════════
# PR→PO Variance
# ══════════════════════════════════════════════════════════════════════

def compute_pr_po_variance(lines: list[PRPOVarianceLine]) -> list[PRPOVarianceLine]:
    """
    يحسب variance_amount وvariance_pct لكل سطر مقارنة PR→PO.

    variance_amount = actual_cost - estimated_cost
    variance_pct    = variance_amount / estimated_cost × 100
                      None لو estimated_cost = 0

    ترتيب تنازلي بـ abs(variance_amount).
    """
    for line in lines:
        line.variance_amount = (line.actual_cost - line.estimated_cost).quantize(TWO, ROUND_HALF_UP)

        if line.estimated_cost == ZERO:
            line.variance_pct = None
        else:
            line.variance_pct = (
                line.variance_amount / line.estimated_cost * Decimal("100")
            ).quantize(TWO, ROUND_HALF_UP)

    return sorted(lines, key=lambda x: -abs(x.variance_amount))


# ══════════════════════════════════════════════════════════════════════
# Phase 7 — Shift Variance Scoring
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ShiftVarianceResult:
    """نتيجة تقييم فرق كاش وردية واحدة."""
    shift_id:       int
    cashier_id:     int
    cashier_name:   str
    variance:       Decimal          # counted - expected (لو مغلقة) أو None→0
    abs_variance:   Decimal
    tier:           str              # 'critical' | 'attention' | 'normal'
    is_closed:      bool


def score_shift_variance(
    shift_id: int,
    cashier_id: int,
    cashier_name: str,
    variance: Optional[Decimal],
    is_closed: bool,
    critical_threshold: Decimal = SHIFT_VARIANCE_CRITICAL_EGP,
    attention_threshold: Decimal = SHIFT_VARIANCE_ATTENTION_EGP,
) -> ShiftVarianceResult:
    """
    يُصنّف فرق كاش وردية:
      |variance| > critical_threshold (200 ج افتراضياً) → critical
      |variance| > attention_threshold (50 ج) → attention
      غير ذلك → normal

    وردية مفتوحة (is_closed=False): لا variance → لا flag.
    """
    v = variance or ZERO
    abs_v = abs(v)

    if not is_closed or variance is None:
        tier = "normal"
    elif abs_v > critical_threshold:
        tier = "critical"
    elif abs_v > attention_threshold:
        tier = "attention"
    else:
        tier = "normal"

    return ShiftVarianceResult(
        shift_id=shift_id,
        cashier_id=cashier_id,
        cashier_name=cashier_name,
        variance=v,
        abs_variance=abs_v,
        tier=tier,
        is_closed=is_closed,
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 7 — Exception Ranking
# ══════════════════════════════════════════════════════════════════════

@dataclass
class OwnerException:
    """استثناء واحد في قائمة المالك."""
    exception_id:   str              # unique key: rule:entity_id
    tier:           str              # 'critical' | 'attention' | 'watch'
    category:       str              # 'fraud' | 'shift_variance' | 'expense_variance' | 'b2b_overdue' | 'supplier_concentration' | 'pr_po_variance'
    title:          str              # عنوان قصير
    detail:         str              # تفاصيل
    entity_id:      Optional[int]    # cashier_id / contract_id / supplier_id
    entity_name:    Optional[str]    # اسم الكيان (كاشير/فندق/مورّد)
    impact:         Decimal          # قيمة مالية تقديرية (0 لو مجهولة)
    confidence:     Decimal          # 0-1 (1 = متأكد)
    status:         str              # 'realized' | 'projected' | 'potential'
    source:         str              # مصدر البيانات
    score:          Decimal = field(default=ZERO)   # impact × confidence


_TIER_ORDER = {"critical": 0, "attention": 1, "watch": 2}


def rank_exceptions(exceptions: list[OwnerException]) -> list[OwnerException]:
    """
    يرتّب الاستثناءات:
    1. Tier أولاً (critical → attention → watch)
    2. داخل كل tier: score = impact × confidence (تنازلي)

    يحسب score لكل استثناء قبل الترتيب.
    """
    for exc in exceptions:
        exc.score = (exc.impact * exc.confidence).quantize(TWO, ROUND_HALF_UP)

    return sorted(
        exceptions,
        key=lambda x: (_TIER_ORDER.get(x.tier, 99), -x.score),
    )


def build_fraud_exceptions(fraud_signals: list) -> list[OwnerException]:
    """
    يحوّل FraudSignal objects (من fraud_tasks.find_fraud_signals) إلى
    OwnerException objects بـ tier=critical دائماً.

    يستقبل list[FraudSignal] من fraud_tasks — لا يستورد fraud_tasks هنا
    (pure engine — لا imports خارجية).
    """
    exceptions = []
    for sig in fraud_signals:
        exceptions.append(OwnerException(
            exception_id=f"fraud:{sig.user_id}:{sig.rule}",
            tier="critical",
            category="fraud",
            title=f"نشاط مشبوه — {sig.rule}",
            detail=sig.message,
            entity_id=sig.user_id,
            entity_name=sig.user_name,
            impact=ZERO,   # لا قيمة مالية محددة لإشارة احتيال
            confidence=Decimal("0.8"),
            status="potential",
            source="fraud_tasks",
        ))
    return exceptions


def build_shift_variance_exceptions(
    results: list[ShiftVarianceResult],
) -> list[OwnerException]:
    """يحوّل ShiftVarianceResult objects إلى OwnerException — tier=critical/attention."""
    exceptions = []
    for r in results:
        if r.tier == "normal":
            continue
        exceptions.append(OwnerException(
            exception_id=f"shift_variance:{r.shift_id}",
            tier=r.tier,
            category="shift_variance",
            title=f"فرق كاش في وردية {r.cashier_name}",
            detail=f"الفرق: {r.variance:+.2f} ج — الوردية {'مغلقة' if r.is_closed else 'مفتوحة'}",
            entity_id=r.cashier_id,
            entity_name=r.cashier_name,
            impact=r.abs_variance,
            confidence=Decimal("1.0"),   # فرق كاش فعلي → confidence كاملة
            status="realized",
            source="cashier_shifts",
        ))
    return exceptions
