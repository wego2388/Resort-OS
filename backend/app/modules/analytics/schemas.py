"""
app/modules/analytics/schemas.py — Pydantic v2

⚠️ First schemas.py this module has ever had. Every other endpoint in
api/router.py returns ad-hoc dicts (no response_model) — an intentional style
for a read-only aggregation module. These 2 schemas exist only because
UtilityReading is a genuine write path (Task B audit finding: the model +
migration existed, but there was no way anywhere in the system to ever create
a reading) and FastAPI request-body validation needs a real Pydantic model.

Update: response_model schemas added for all JSON-returning endpoints so
OpenAPI docs are complete and FastAPI can validate response shapes.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class UtilityReadingCreate(BaseModel):
    branch_id:     int
    reading_date:  date
    utility_type:  str = Field(..., pattern=r"^(electricity|water|gas|diesel)$")
    reading_value: Decimal = Field(..., gt=0)
    unit:          str = Field("kWh", max_length=10)
    unit_cost:     Decimal = Field(Decimal(0), ge=0)
    notes:         str | None = Field(None, max_length=300)


class UtilityReadingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:            int
    branch_id:     int
    reading_date:  date
    utility_type:  str
    reading_value: Decimal
    unit:          str
    unit_cost:     Decimal
    total_cost:    Decimal
    notes:         str | None
    recorded_by:   int | None
    created_at:    datetime


# ── Guest review submission (public, token-gated — راجع submit_guest_review) ──
# ⚠️ باج حقيقي اتصلح (2026-08-02): الـ endpoint ده كان بياخد `data: dict = Body(...)`
# خام من غير أي تحقق — أي طلب فاسد (categories عنصر ناقص "rating"، overall_rating
# برّه المدى 1-5، guest_name أطول من العمود String(200)) كان بيوصل لـDB error خام
# (500) أو بيتخزّن قيمة غير منطقية تماماً (زي overall_rating=999) بتلوّث كل
# إحصائيات GSS ومتوسط التقييمات — والـendpoint ده عام بالكامل (بدون auth، بس
# token JWT)، فأي حد ماسك لينك الاستبيان (أو حتى بيجرّب توكن عشوائي) كان يقدر
# يبعت مدخلات عدائية بحرية تامة.
class GuestReviewCategoryInput(BaseModel):
    category: str = Field(..., min_length=1, max_length=30)
    rating:   int = Field(..., ge=1, le=5)


class GuestReviewSubmitRequest(BaseModel):
    guest_name:     str = Field("ضيف", max_length=200)
    overall_rating: int = Field(3, ge=1, le=5)
    comment:        str | None = Field(None, max_length=2000)
    categories:     list[GuestReviewCategoryInput] = Field(default_factory=list)


# ── Simple fixed-shape response schemas ──────────────────────────────────────
class ReviewSubmitResponse(BaseModel):
    id:             int
    overall_rating: float

class SurveyTokenResponse(BaseModel):
    token:          str
    expires_in_days: int

class SurveySendResponse(BaseModel):
    queued: bool


# ── Revenue Dashboard ─────────────────────────────────────────────────────────

class RevenueBucket(BaseModel):
    """إيراد موديول واحد (مطعم/كافيه/فندق/شاطئ/إيجار/ملكية جزئية)."""
    orders: int | None = None        # dining buckets
    bookings: int | None = None      # pms
    visits: int | None = None        # beach
    payments: int | None = None      # leasing / timeshare
    total: Decimal = Decimal(0)

class RevenuePeriod(BaseModel):
    from_: str = Field(alias="from")
    to: str

    model_config = ConfigDict(populate_by_name=True)

class RevenueSummary(BaseModel):
    """GET /analytics/revenue"""
    period:     RevenuePeriod
    branch_id:  int
    restaurant: RevenueBucket | None = None
    cafe:       RevenueBucket | None = None
    pms:        RevenueBucket | None = None
    beach:      RevenueBucket | None = None
    leasing:    RevenueBucket | None = None
    timeshare:  RevenueBucket | None = None
    total:      Decimal = Decimal(0)


# ── Occupancy ─────────────────────────────────────────────────────────────────

class PMSOccupancy(BaseModel):
    nights_audited:       int
    avg_occupancy_pct:    float
    total_room_revenue:   Decimal

class OccupancySummary(BaseModel):
    """GET /analytics/occupancy"""
    month:  int
    year:   int
    pms:    PMSOccupancy | None = None
    beach:  None = None   # حاليًا لا يُحسب


# ── HR Summary ────────────────────────────────────────────────────────────────

class LastPayrollSummary(BaseModel):
    period:     str           # "YYYY-MM"
    status:     str
    total_net:  Decimal

class HRSummary(BaseModel):
    """GET /analytics/hr"""
    active_employees: int = 0
    last_payroll:     LastPayrollSummary | None = None


# ── Maintenance KPIs ──────────────────────────────────────────────────────────

class MaintenanceSummary(BaseModel):
    """GET /analytics/maintenance"""
    open_work_orders:     int = 0
    critical_work_orders: int = 0


# ── CRM Pipeline ─────────────────────────────────────────────────────────────

class PipelineStage(BaseModel):
    stage: str
    count: int
    value: Decimal | None = None

class CRMSummary(BaseModel):
    """GET /analytics/crm"""
    total_customers: int = 0
    pipeline:        list[PipelineStage] = Field(default_factory=list)


# ── Inventory Alerts ──────────────────────────────────────────────────────────

class InventoryAlerts(BaseModel):
    """GET /analytics/inventory"""
    low_stock_count:   int = 0
    out_of_stock_count: int = 0


# ── DailyStats ────────────────────────────────────────────────────────────────

class DailyStatsRead(BaseModel):
    """GET /analytics/daily-stats"""
    stat_date:          str
    occupancy_pct:      float = 0
    adr:                float = 0
    revpar:             float = 0
    room_revenue:       Decimal = Decimal(0)
    beach_visitors:     int   = 0
    beach_revenue:      Decimal = Decimal(0)
    restaurant_covers:  int   = 0
    restaurant_revenue: Decimal = Decimal(0)
    # متوسط الفاتورة للفرد (Average Check per Cover) — مؤشر ضيافة أساسي،
    # الداتا (revenue وcovers) كانت متجمّعة أصلاً بس متقسمتش على بعض قبل
    # كده (2026-08-11، طلب Mohamed أثناء نقاش POS الكاشير). restaurant فقط
    # (مش cafe) لأن restaurant_covers نفسها بتتبع guests_count المطعم بس —
    # الكافيه counter-service من غير مفهوم "غطاء" حقيقي. null لو صفر غطاء
    # بدل 0 مضلّل (يبان وكأنه متوسط فعلي صفر مش "مفيش بيانات كافية").
    avg_check_per_cover: float | None = None
    cafe_revenue:       Decimal = Decimal(0)
    total_revenue:      Decimal = Decimal(0)
    # حالة "لا توجد بيانات" — نرجع message بدل الأرقام
    message:            str | None = None


# ── Energy KPIs ───────────────────────────────────────────────────────────────

class EnergyKPIs(BaseModel):
    """GET /analytics/energy — يطابق شكل get_energy_kpis() في services.py"""
    period:                            str
    by_type:                           dict[str, Decimal] = Field(default_factory=dict)
    total_cost:                        Decimal = Decimal(0)
    guest_nights:                      int   = 0
    electricity_cost_per_guest_night:  Decimal | None = None


# ── Energy Trend ──────────────────────────────────────────────────────────────
# get_energy_trend() ترجع list[dict] (كل عنصر بنفس شكل EnergyKPIs)
# نستخدم list[EnergyKPIs] مباشرة كـ response_model

EnergyTrendResponse = list[EnergyKPIs]


# ── Guest Reviews ─────────────────────────────────────────────────────────────

class GuestReviewItem(BaseModel):
    id:             int
    guest_name:     str | None = None
    overall_rating: float
    comment:        str | None = None
    source:         str | None = None
    reviewed_at:    str

class GuestReviewListResponse(BaseModel):
    """GET /analytics/reviews"""
    total:      int
    avg_rating: float = 0
    items:      list[GuestReviewItem] = Field(default_factory=list)


# ── Review Category Insights ──────────────────────────────────────────────────

class CategoryInsightItem(BaseModel):
    category:   str
    avg_rating: float
    count:      int

class ReviewCategoryInsights(BaseModel):
    """GET /analytics/reviews/insights — يطابق get_review_category_insights()"""
    overall_avg:        float | None = None
    gss_score:          float | None = None
    review_count:       int = 0
    category_breakdown: list[CategoryInsightItem] = Field(default_factory=list)


# ── Full Dashboard ─────────────────────────────────────────────────────────────

class DashboardRevenue(BaseModel):
    restaurant: Decimal = Decimal(0)
    cafe:       Decimal = Decimal(0)
    pms:        Decimal = Decimal(0)
    beach:      Decimal = Decimal(0)
    leasing:    Decimal = Decimal(0)
    timeshare:  Decimal = Decimal(0)
    total:      Decimal = Decimal(0)

class DashboardHR(BaseModel):
    active_employees:   int   = 0
    last_payroll_period: str | None = None

class DashboardMaintenance(BaseModel):
    open_work_orders: int = 0

class DashboardCRM(BaseModel):
    total_customers: int = 0

class DashboardInventory(BaseModel):
    low_stock_count: int = 0

class DashboardReviews(BaseModel):
    count:      int   = 0
    avg_rating: float | None = None

class FullDashboard(BaseModel):
    """GET /analytics/dashboard"""
    branch_id:   int
    as_of:       str
    revenue_30d: DashboardRevenue | None    = None
    hr:          DashboardHR | None         = None
    maintenance: DashboardMaintenance | None = None
    crm:         DashboardCRM | None        = None
    inventory:   DashboardInventory | None  = None
    reviews:     DashboardReviews | None    = None
