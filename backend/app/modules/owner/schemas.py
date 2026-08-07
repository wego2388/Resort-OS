"""
app/modules/owner/schemas.py
═══════════════════════════════════════════════════════════════════════
Owner Intelligence Cockpit — Pydantic Schemas (Decision 0004, Phase 2+3).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ── OwnerWatchlist ────────────────────────────────────────────────────

class OwnerWatchlistCreate(BaseModel):
    metric_key:     str           = Field(..., min_length=1, max_length=100)
    display_order:  int           = Field(default=0, ge=0)
    label_override: Optional[str] = Field(default=None, max_length=200)
    branch_id:      int


class OwnerWatchlistRead(BaseModel):
    id:             int
    owner_user_id:  int
    metric_key:     str
    display_order:  int
    label_override: Optional[str]
    branch_id:      int
    created_at:     datetime
    updated_at:     datetime

    model_config = {"from_attributes": True}


# ── OwnerAllocationRule ───────────────────────────────────────────────

class AllocationRuleDraftCreate(BaseModel):
    branch_id:    int
    pct_rooms:    Decimal = Field(default=Decimal("0"), ge=0, le=100)
    pct_beach:    Decimal = Field(default=Decimal("0"), ge=0, le=100)
    pct_dining:   Decimal = Field(default=Decimal("0"), ge=0, le=100)
    pct_timeshare: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    notes:        Optional[str] = None

    @field_validator("pct_timeshare")
    @classmethod
    def validate_total(cls, v, info):
        values = info.data
        total = (
            values.get("pct_rooms", Decimal("0"))
            + values.get("pct_beach", Decimal("0"))
            + values.get("pct_dining", Decimal("0"))
            + v
        )
        if total > Decimal("100"):
            raise ValueError("مجموع نسب التخصيص يتجاوز 100%")
        return v


class AllocationRuleDraftUpdate(BaseModel):
    pct_rooms:    Optional[Decimal] = Field(default=None, ge=0, le=100)
    pct_beach:    Optional[Decimal] = Field(default=None, ge=0, le=100)
    pct_dining:   Optional[Decimal] = Field(default=None, ge=0, le=100)
    pct_timeshare: Optional[Decimal] = Field(default=None, ge=0, le=100)
    notes:        Optional[str] = None


class AllocationRuleRead(BaseModel):
    id:              int
    branch_id:       int
    version:         int
    status:          str
    pct_rooms:       Decimal
    pct_beach:       Decimal
    pct_dining:      Decimal
    pct_timeshare:   Decimal
    effective_from:  Optional[date]
    effective_to:    Optional[date]
    published_by:    Optional[int]
    published_at:    Optional[datetime]
    publish_reason:  Optional[str]
    created_by:      int
    notes:           Optional[str]
    created_at:      datetime
    updated_at:      datetime

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════
# Phase 3 — Aggregation API Schemas
# ═══════════════════════════════════════════════════════════════════════

# ── مكوّنات مشتركة ───────────────────────────────────────────────────

class PeriodMeta(BaseModel):
    """ميتاداتا الفترة الزمنية التي يغطيها الرقم — مطلوبة على كل مقياس
    (Decision 0004 §Numbers must equal the source of truth)."""
    date_from:      date
    date_to:        date
    is_provisional: bool   = Field(
        ...,
        description="True = الفترة لم تُقفل بعد (open accounting period). "
                    "لا يُعرض الرقم كأنه نهائي حين تكون True.",
    )
    computed_at:    datetime


class B2BReceivableItem(BaseModel):
    """ذمم عقد B2B واحد — بدون أي بيانات ضيف شخصية (Decision 0004 §Isolation model item 7)."""
    contract_id:      int
    hotel_name:       str
    outstanding:      Decimal  = Field(description="الرصيد غير المسوّى منذ last_settled_at")
    is_overdue:       bool
    credit_limit:     Optional[Decimal]
    last_settled_at:  Optional[date]


class TimeshareReceivableItem(BaseModel):
    """ذمم تايم شير — أقساط مستحقة اليوم أو متأخرة."""
    contract_id:      int
    total_overdue:    Decimal   = Field(description="مجموع أقساط status IN ('unpaid','overdue') due_date <= today")
    installment_count: int


class OccupancyNow(BaseModel):
    """إشغال الغرف الحالي — لحظي (ليس توقعاً)."""
    occupied_rooms:  int
    total_rooms:     int
    occupancy_pct:   Decimal   = Field(description="نسبة مئوية 0-100")
    computed_at:     datetime


class BeachCapacityToday(BaseModel):
    """سعة الشاطئ اليوم — عدّاد تراكمي لا يتراجع (Decision kpi-contracts A-7)."""
    capacity_used:   int
    capacity_max:    int
    utilisation_pct: Decimal   = Field(description="نسبة مئوية 0-100")
    inventory_date:  date
    note:            str = Field(
        default="تذاكر مباعة اليوم — العدّاد تراكمي ولا يتراجع عند الإلغاء",
        description="تنبيه دائم: capacity_used مش إشغال فعلي الآن",
    )


# ── A: شاشة «الآن» ────────────────────────────────────────────────────

class OwnerNowResponse(BaseModel):
    """
    GET /api/v1/owner/now
    ═══════════════════════════════════════════════════════════════════
    المقاييس السبعة للشاشة الرئيسية (A-1 → A-7 من kpi-contracts.md).

    كل رقم مالي يحمل:
    - period:         الفترة التي يغطيها
    - is_provisional: هل الفترة مفتوحة أم مقفولة
    - computed_at:    timestamp الحساب

    لا يُعرض أي رقم provisional كأنه نهائي.
    """
    # A-1: إيراد اليوم الصافي
    revenue_today:          Decimal
    # A-2: كاش الأدراج المتوقع
    cash_in_drawers:        Decimal
    # A-3: مصروفات اليوم
    expense_today:          Decimal
    # A-4: ذمم B2B — قائمة مفصّلة بدون بيانات ضيف
    b2b_receivables:        list[B2BReceivableItem]
    b2b_total_outstanding:  Decimal
    # A-5: ذمم تايم شير
    timeshare_receivables:  list[TimeshareReceivableItem]
    timeshare_total_overdue: Decimal
    # A-6: إشغال الغرف الحالي
    occupancy:              OccupancyNow
    # A-7: سعة الشاطئ اليوم
    beach_capacity:         BeachCapacityToday
    # ميتاداتا الفترة المالية (A-1, A-3 يستعملانها)
    period:                 PeriodMeta
    # عدد الورديات المفتوحة الآن (مرتبط بـ A-2)
    open_shift_count:       int


# ── B: شاشة «الأداء» — مقارنة فترات ─────────────────────────────────

class PeriodSnapshot(BaseModel):
    """لقطة فترة واحدة — الإيراد والمصروف وصافي الدخل."""
    date_from:      date
    date_to:        date
    label:          str     = Field(description="مثال: 'اليوم'، 'أمس'، 'هذا الأسبوع'")
    total_revenue:  Decimal
    total_expense:  Decimal
    net_income:     Decimal
    is_provisional: bool
    computed_at:    datetime


class PeriodComparison(BaseModel):
    """مقارنة فترتين: الحالية vs السابقة — تُحسب في owner services لا في finance."""
    current:         PeriodSnapshot
    prior:           PeriodSnapshot
    revenue_delta:   Decimal  = Field(description="current.total_revenue - prior.total_revenue")
    revenue_pct:     Optional[Decimal] = Field(
        default=None,
        description="نسبة التغيير % — None لو prior كان صفراً",
    )
    expense_delta:   Decimal
    expense_pct:     Optional[Decimal]
    net_income_delta: Decimal
    net_income_pct:  Optional[Decimal]


class OwnerPerformanceResponse(BaseModel):
    """
    GET /api/v1/owner/performance
    ═══════════════════════════════════════════════════════════════════
    مقارنة ثلاث فترات في طلب واحد:
    - today_vs_yesterday:   اليوم vs أمس
    - week_vs_prior_week:   الأسبوع الحالي vs الأسبوع الماضي
    - month_vs_prior_month: الشهر الحالي vs الشهر الماضي

    المقارنة تُحسب في owner.services بـ استدعاءين منفصلين لـ
    get_income_statement لكل فترة، والـ delta يُحسب هنا — لا في
    finance module (Decision 0004 §Numbers must equal the source).
    """
    today_vs_yesterday:    PeriodComparison
    week_vs_prior_week:    PeriodComparison
    month_vs_prior_month:  PeriodComparison
    # timestamp موحّد للاستجابة كاملها
    computed_at:           datetime


# ═══════════════════════════════════════════════════════════════════════
# Phase 6 — Analytics Schemas (C, D, E groups from kpi-contracts.md)
# ═══════════════════════════════════════════════════════════════════════

# ── C: Sales / Product Performance ────────────────────────────────────

class ItemMetricResponse(BaseModel):
    """استجابة صنف واحد مع تصنيف ABC وهامش الربح."""
    item_id:        int
    name:           str
    quantity_sold:  int
    revenue:        Decimal
    recipe_cost:    Optional[Decimal]   = None
    margin_pct:     Optional[Decimal]   = None
    margin_amount:  Optional[Decimal]   = None
    abc_class:      Optional[str]       = None   # 'A' | 'B' | 'C'
    cumulative_pct: Optional[Decimal]   = None


class SalesPerformanceResponse(BaseModel):
    """
    GET /api/v1/owner/sales
    أداء المبيعات: top items مرتّبة بالإيراد + تصنيف ABC + هامش.
    """
    period_from:    date
    period_to:      date
    outlet:         str             = Field(description="'dining' | 'beach' | 'all'")
    items:          list[ItemMetricResponse]
    total_revenue:  Decimal
    is_provisional: bool
    computed_at:    datetime


class BeachTicketTypeRow(BaseModel):
    """أداء نوع تذكرة شاطئ واحد."""
    tx_type:        str
    count:          int
    total_amount:   Decimal
    avg_unit_price: Decimal


class BeachPerformanceResponse(BaseModel):
    """
    GET /api/v1/owner/beach-performance
    أداء الشاطئ مقسّم بنوع التذكرة.
    """
    period_from:  date
    period_to:    date
    ticket_types: list[BeachTicketTypeRow]
    total_revenue: Decimal
    total_count:   int
    computed_at:   datetime


# ── C-4: B2B Channel Analytics ────────────────────────────────────────

class ChannelContractRow(BaseModel):
    """أداء عقد فندق B2B واحد — per hotel/contract, لا per guest (Decision 0004)."""
    contract_id:      int
    hotel_name:       str
    period_checkins:  int
    period_revenue:   Decimal   = Field(description="إيراد الشاطئ للفترة")
    outstanding:      Decimal   = Field(description="الرصيد غير المسوّى الحالي")
    is_overdue:       bool
    credit_limit:     Optional[Decimal]
    fnb_attach:       Decimal   = Field(description="إجمالي F&B للضيوف عبر هذا العقد في الفترة")
    fnb_avg_per_checkin: Decimal = Field(description="متوسط F&B per check-in")


class ChannelAnalyticsResponse(BaseModel):
    """
    GET /api/v1/owner/channel-analytics
    أداء قنوات B2B — per hotel/contract فقط، لا per named guest.
    """
    period_from:    date
    period_to:      date
    contracts:      list[ChannelContractRow]
    total_checkins: int
    total_beach_revenue: Decimal
    total_fnb_attach:    Decimal
    computed_at:    datetime


# ── D: Expense Analytics ───────────────────────────────────────────────

class ExpenseLineResponse(BaseModel):
    """سطر مصروف واحد مع مقارنة الفترتين."""
    account_code:    str
    account_name:    str
    current_amount:  Decimal
    prior_amount:    Decimal
    current_pct:     Optional[Decimal]  = Field(default=None, description="% من الإيراد — الفترة الحالية")
    prior_pct:       Optional[Decimal]  = Field(default=None, description="% من الإيراد — الفترة السابقة")
    variance_flag:   bool               = False
    variance_delta:  Optional[Decimal]  = Field(default=None, description="نقاط مئوية + = ارتفاع")


class PayrollSummary(BaseModel):
    """ملخص رواتب الشهر كنسبة من الإيراد — aggregate فقط، لا per employee."""
    period_year:     int
    period_month:    int
    total_net:       Decimal
    revenue:         Decimal
    payroll_pct:     Optional[Decimal]  = None
    status:          str


class ExpenseAnalyticsResponse(BaseModel):
    """
    GET /api/v1/owner/expense-analytics
    كل فئة مصروف كنسبة % من الإيراد مع variance flags.
    """
    period_from:     date
    period_to:       date
    prior_from:      date
    prior_to:        date
    current_revenue: Decimal
    prior_revenue:   Decimal
    expense_lines:   list[ExpenseLineResponse]
    payroll:         Optional[PayrollSummary]   = None
    is_provisional:  bool
    computed_at:     datetime


# ── E: Procurement Analytics ──────────────────────────────────────────

class SupplierSpendRow(BaseModel):
    """إنفاق مورّد واحد."""
    supplier_id:          int
    supplier_name:        str
    total_spend:          Decimal
    spend_pct:            Decimal
    order_count:          int
    concentration_flag:   bool


class PRPOVarianceRow(BaseModel):
    """مقارنة طلب شراء vs أمر شراء لصنف واحد."""
    product_id:       int
    product_name:     str
    estimated_cost:   Decimal
    actual_cost:      Decimal
    variance_amount:  Decimal
    variance_pct:     Optional[Decimal]


class ProcurementAnalyticsResponse(BaseModel):
    """
    GET /api/v1/owner/procurement-analytics
    تركّز الإنفاق بالموردين + فرق estimate vs actual.
    """
    period_from:    date
    period_to:      date
    total_spend:    Decimal
    suppliers:      list[SupplierSpendRow]
    pr_po_variance: list[PRPOVarianceRow]
    computed_at:    datetime
