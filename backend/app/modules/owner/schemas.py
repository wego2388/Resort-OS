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
    """ذمم ملكية جزئية — أقساط مستحقة اليوم أو متأخرة."""
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
    # A-5: ذمم ملكية جزئية
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
    # A-8: ذمم شخصية آجلة (Decision 0005) — إجمالي الرصيد المستحق
    credit_account_outstanding: Decimal = Decimal("0")
    credit_account_count:       int     = 0


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
    # Phase 7e: breakdown اختياري per outlet — None لو البيانات مش متاحة
    breakdown: Optional["PerformanceBreakdown"] = None


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


# ── تفصيل الإيراد بالحساب (2026-08-17) ─────────────────────────────────
# طلب Mohamed الصريح بعد تجربة تطبيق المالك: الضغط على كارت "إيراد اليوم"/
# "مصروفات اليوم" لازم يوريه تفاصيل أكتر من الحسابات نفسها. جانب المصروف
# جاهز أصلاً (ExpenseAnalyticsResponse.expense_lines فوق). دول نظيرهم على
# جانب الإيراد — نفس مصدر الحقيقة (get_income_statement) بالظبط.

class RevenueLineResponse(BaseModel):
    """سطر إيراد واحد لفترة معيّنة — بدون مقارنة فترة سابقة (عرض سريع للحظة
    الحالية فقط، عكس ExpenseLineResponse اللي مبني لمقارنة D-1/D-2)."""
    account_code: str
    account_name: str
    amount:       Decimal


class RevenueBreakdownResponse(BaseModel):
    """
    GET /api/v1/owner/revenue-breakdown
    تفصيل الإيراد بالحساب لأي فترة — من نفس get_income_statement المستخدم
    لكل رقم مالي أساسي تاني (Decision 0004 §Numbers must equal source).
    """
    period_from:    date
    period_to:      date
    total_revenue:  Decimal
    revenue_lines:  list[RevenueLineResponse]
    is_provisional: bool
    computed_at:    datetime


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


# ═══════════════════════════════════════════════════════════════════════
# Phase 7 — Shifts & Exceptions Schemas
# ═══════════════════════════════════════════════════════════════════════

class CashMovementItem(BaseModel):
    """حركة كاش يدوية في وردية — read-only للمالك."""
    id:            int
    movement_type: str
    amount:        Decimal
    direction:     Optional[str]   = None
    reason:        str
    performed_by_name: str
    created_at:    datetime


class ShiftMonitorItem(BaseModel):
    """وردية واحدة مع حركات الكاش — للمراقبة فقط، لا actions."""
    shift_id:       int
    cashier_id:     int
    cashier_name:   str
    opened_at:      datetime
    opening_float:  Decimal
    total_sales:    Decimal
    total_cash:     Decimal
    expected_cash:  Decimal
    invoice_count:  int
    variance:       Optional[Decimal]  = None   # None لو مفتوحة
    is_closed:      bool
    cash_movements: list[CashMovementItem]
    variance_tier:  str                = "normal"   # 'critical'|'attention'|'normal'


class ShiftMonitorResponse(BaseModel):
    """
    GET /api/v1/owner/shifts
    كل الورديات المفتوحة الآن مع حركات الكاش.
    المالك يقرأ فقط — لا approve/close/dispute.
    """
    branch_id:    int
    open_count:   int
    shifts:       list[ShiftMonitorItem]
    computed_at:  datetime


class OwnerExceptionItem(BaseModel):
    """استثناء واحد في قائمة المالك."""
    exception_id:  str
    tier:          str        # 'critical' | 'attention' | 'watch'
    category:      str
    title:         str
    detail:        str
    entity_id:     Optional[int]   = None
    entity_name:   Optional[str]   = None
    impact:        Decimal
    confidence:    Decimal
    status:        str        # 'realized' | 'projected' | 'potential'
    source:        str
    score:         Decimal


class ExceptionsResponse(BaseModel):
    """
    GET /api/v1/owner/exceptions
    قائمة مرتّبة بالخطورة: critical → attention → watch.
    داخل كل tier: impact × confidence تنازلي.
    """
    critical_count:   int
    attention_count:  int
    watch_count:      int
    exceptions:       list[OwnerExceptionItem]
    computed_at:      datetime


# ═══════════════════════════════════════════════════════════════════════
# Phase 7a — Now History (Sparklines)
# ═══════════════════════════════════════════════════════════════════════

class DaySnapshot(BaseModel):
    """لقطة يوم واحد للـ sparklines — 5 متغيّرات فقط."""
    day:                 date
    revenue:             Decimal
    expense:             Decimal
    cash_in_drawers:     Decimal
    occupancy_pct:       Decimal   = Field(description="0-100")
    beach_utilisation_pct: Decimal = Field(description="0-100")
    is_provisional:      bool


class NowHistoryResponse(BaseModel):
    """
    GET /api/v1/owner/now/history?days=N
    آخر N أيام من مقاييس الشاشة الرئيسية — للـ sparklines.
    الأيام مرتّبة تصاعدياً (الأقدم أولاً).
    """
    days:        list[DaySnapshot]
    computed_at: datetime


# ═══════════════════════════════════════════════════════════════════════
# Phase 7b — Shift History
# ═══════════════════════════════════════════════════════════════════════

class ShiftHistoryItem(BaseModel):
    """وردية مغلقة — تاريخية للمالك. قراءة فقط."""
    shift_id:       int
    cashier_id:     int
    cashier_name:   str
    opened_at:      datetime
    closed_at:      datetime
    opening_float:  Decimal
    total_sales:    Decimal
    total_cash:     Decimal
    expected_cash:  Decimal
    invoice_count:  int
    variance:       Optional[Decimal] = None
    cash_movements: list[CashMovementItem]
    variance_tier:  str = "normal"


class ShiftHistoryResponse(BaseModel):
    """
    GET /api/v1/owner/shifts/history?days=N
    الورديات المغلقة خلال آخر N أيام — للمراجعة التاريخية.
    """
    branch_id:   int
    days:        int
    shifts:      list[ShiftHistoryItem]
    computed_at: datetime


# ═══════════════════════════════════════════════════════════════════════
# Phase 7c — HR Summary
# Decision 0004 §7c: الاسم + وظيفة + راتب صافي/إجمالي + جزاءات + سلف + حضور aggregate
# لا national_id، لا employee_si، لا monthly_tax، لا phone، لا email
# ═══════════════════════════════════════════════════════════════════════

class EmployeePayrollSummary(BaseModel):
    """آخر كشف رواتب للموظف — حقول المالك فقط."""
    payroll_run_id:    int
    period_year:       int
    period_month:      int
    gross_salary:      Decimal
    net_salary:        Decimal
    penalty_deduction: Decimal
    advance_deduction: Decimal
    # لا employee_si، لا monthly_tax — Decision 0004 §7c


class EmployeeAttendanceSummary(BaseModel):
    """aggregate حضور الشهر الحالي — لا raw timestamps."""
    present_days:     int
    absent_days:      int
    late_days:        int
    leave_days:       int
    total_working_days: int


class HREmployeeRow(BaseModel):
    """موظف واحد للعرض على شاشة HR للمالك."""
    employee_id:           int
    full_name:             str
    position:              str
    department:            Optional[str] = None
    hire_date:             date
    status:                str
    payroll:               Optional[EmployeePayrollSummary]      = None
    attendance_this_month: Optional[EmployeeAttendanceSummary]   = None
    # لا national_id، لا phone، لا email، لا basic_salary — Decision 0004 §7c


class HRSummaryResponse(BaseModel):
    """
    GET /api/v1/owner/hr-summary
    قائمة الموظفين + آخر payroll + حضور الشهر الحالي.
    """
    branch_id:       int
    employees:       list[HREmployeeRow]
    active_count:    int
    on_leave_count:  int
    total_net_payroll: Decimal
    period_year:     int
    period_month:    int
    computed_at:     datetime


# ═══════════════════════════════════════════════════════════════════════
# Phase 7d — Discount Analytics
# Decision 0004 §7d: خصومات + مجموعات بالاسم. لا هاتف/email/national_id.
# ═══════════════════════════════════════════════════════════════════════

class DiscountTypeRow(BaseModel):
    """نوع خصم واحد — aggregate."""
    type:           str
    type_label:     str
    order_count:    int
    total_amount:   Decimal
    pct_of_revenue: Optional[Decimal] = None


class ManualDiscountPerCashier(BaseModel):
    """خصومات يدوية per cashier — aggregate للشهر."""
    cashier_id:            int
    cashier_name:          str
    order_count:           int
    total_manual_discount: Decimal


class CustomerGroupMember(BaseModel):
    """عميل في مجموعة — الاسم فقط. لا هاتف/email/national_id."""
    customer_id:  int
    full_name:    str
    invoice_count: int
    total_sales:  Decimal


class CustomerGroupDiscountRow(BaseModel):
    """مجموعة عملاء مع أعضائها بالاسم فقط."""
    group_id:                   int
    group_name:                 str
    discount_pct:               Decimal
    member_count:               int
    total_invoices:             int
    total_sales_after_discount: Decimal
    members:                    list[CustomerGroupMember]


class DiscountAnalyticsResponse(BaseModel):
    """
    GET /api/v1/owner/discount-analytics
    تحليل الخصومات: أنواع + يدوي per cashier + مجموعات بالاسم.
    لا بيانات عميل غير مجموعة (زوار عشوائيين).
    """
    period_from:             str
    period_to:               str
    total_revenue:           Decimal
    total_discount:          Decimal
    discount_pct_of_revenue: Optional[Decimal] = None
    discount_types:          list[DiscountTypeRow]
    manual_per_cashier:      list[ManualDiscountPerCashier]
    customer_groups:         list[CustomerGroupDiscountRow]
    computed_at:             datetime


# ═══════════════════════════════════════════════════════════════════════
# Phase 7e — Performance Breakdown
# ═══════════════════════════════════════════════════════════════════════

class PerformanceBreakdown(BaseModel):
    """تفصيل الإيراد per outlet — None لو البيانات مش متاحة."""
    dining_revenue: Optional[Decimal] = None
    beach_revenue:  Optional[Decimal] = None
    rooms_revenue:  Optional[Decimal] = None
    other_revenue:  Optional[Decimal] = None


# ═══════════════════════════════════════════════════════════════════════
# Phase 8 — تفاصيل التفاصيل (Universal Drill-Down)
# ═══════════════════════════════════════════════════════════════════════
# كل شاشات الأونر لحد دلوقتي بتعرض إجماليات بس (فئة مصروف، مورد، صنف...).
# الـendpoints دي بترجع السجلات الخام اللي كوّنت الإجمالي — نفس الفلتر
# (فترة + معرّف العنصر)، مصدر بيانات واحد بس (نفس الجداول المستخدمة في
# التجميع)، صفر منطق مالي جديد.

class PaginationMeta(BaseModel):
    """Bounded drill-down pagination metadata; totals always cover all rows."""
    page:        int = 1
    size:        int = 50
    total_items: int = 0
    total_pages: int = 0


class DiningItemTransaction(BaseModel):
    order_id:      int
    order_number:  str
    outlet_name:   str
    order_type:    str
    quantity:      int
    unit_price:    Decimal
    line_total:    Decimal
    status:        str
    ordered_at:    datetime


class DiningItemDetailResponse(PaginationMeta):
    """GET /api/v1/owner/sales/item-detail — كل الطلبات اللي فيها صنف معيّن."""
    item_id:       int
    item_name:     str
    period_from:   date
    period_to:     date
    transactions:  list[DiningItemTransaction]
    total_quantity: int
    total_revenue:  Decimal
    computed_at:    datetime


class BeachTypeTransaction(BaseModel):
    transaction_id: int
    tx_date:        date
    guest_name:     Optional[str] = None
    unit_price:     Decimal
    total_amount:   Decimal
    cashier_name:   Optional[str] = None


class BeachTypeDetailResponse(PaginationMeta):
    """GET /api/v1/owner/beach/type-detail — كل معاملات نوع تذكرة معيّن."""
    tx_type:        str
    period_from:    date
    period_to:      date
    transactions:   list[BeachTypeTransaction]
    total_count:    int
    total_revenue:  Decimal
    computed_at:    datetime


class ExpenseJournalLine(BaseModel):
    entry_id:     int
    entry_date:   date
    reference:    str
    description:  str
    amount:       Decimal
    source:       Optional[str] = None
    cost_center:  Optional[str] = None


class ExpenseDetailResponse(PaginationMeta):
    """GET /api/v1/owner/expense-detail — كل قيود اليومية داخل فئة مصروف معيّنة."""
    account_code:  str
    account_name:  str
    period_from:   date
    period_to:     date
    lines:         list[ExpenseJournalLine]
    total_amount:  Decimal
    computed_at:   datetime


class RevenueJournalLine(BaseModel):
    entry_id:    int
    entry_date:  date
    reference:   str
    description: str
    amount:      Decimal
    source:      Optional[str] = None


class RevenueDetailResponse(PaginationMeta):
    """GET /api/v1/owner/revenue-detail — كل قيود اليومية داخل حساب إيراد
    معيّن. نظير ExpenseDetailResponse بالظبط على جانب الدائن (الإيراد يزيد
    بالدائن، عكس المصروف اللي يزيد بالمدين)."""
    account_code: str
    account_name: str
    period_from:  date
    period_to:    date
    lines:        list[RevenueJournalLine]
    total_amount: Decimal
    computed_at:  datetime


class SupplierPurchaseOrder(BaseModel):
    po_id:        int
    po_number:    str
    status:       str
    ordered_at:   date
    received_at:  Optional[date] = None
    item_count:   int
    total_amount: Decimal


class SupplierDetailResponse(PaginationMeta):
    """GET /api/v1/owner/procurement-detail — كل أوامر الشراء لمورد معيّن."""
    supplier_id:   int
    supplier_name: str
    period_from:   date
    period_to:     date
    orders:        list[SupplierPurchaseOrder]
    total_amount:  Decimal
    computed_at:   datetime


class ProductMovement(BaseModel):
    movement_id:    int
    movement_type:  str
    quantity:       Decimal
    unit_cost:      Decimal
    warehouse_name: str
    moved_at:       datetime
    notes:          Optional[str] = None


class ProductDetailResponse(PaginationMeta):
    """GET /api/v1/owner/product-detail — حركات مخزون منتج معيّن + الرصيد الحالي."""
    product_id:      int
    product_name:    str
    unit:            str
    current_stock:   Decimal
    cost_price:      Decimal
    period_from:      date
    period_to:        date
    movements:        list[ProductMovement]
    total_in:         Decimal
    total_out:        Decimal
    computed_at:      datetime


class SearchResultItem(BaseModel):
    """صف نتيجة بحث واحد — نوع مختلف الشكل حسب entity_type، الفرونت إند
    بيقرر إزاي يعرضه وإيه الـdetail endpoint المناسب لو اتدوس عليه."""
    entity_type:  str   # product | supplier | expense_account | employee | b2b_contract | timeshare_contract
    entity_id:    int
    title:        str
    subtitle:     Optional[str] = None
    value:        Optional[Decimal] = None
    value_label:  Optional[str] = None


class OwnerSearchResponse(BaseModel):
    """GET /api/v1/owner/search"""
    query:    str
    results:  list[SearchResultItem]
    computed_at: datetime


# resolve forward reference
PeriodComparison.model_rebuild()
