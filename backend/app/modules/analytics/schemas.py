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
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UtilityReadingCreate(BaseModel):
    branch_id:     int
    reading_date:  date
    utility_type:  str = Field(..., pattern=r"^(electricity|water|gas|diesel)$")
    reading_value: Decimal = Field(..., gt=0)
    unit:          str = Field("kWh", max_length=10)
    unit_cost:     Decimal = Field(Decimal("0"), ge=0)
    notes:         Optional[str] = Field(None, max_length=300)


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
    notes:         Optional[str]
    recorded_by:   Optional[int]
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
    comment:        Optional[str] = Field(None, max_length=2000)
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
    orders: Optional[int] = None        # dining buckets
    bookings: Optional[int] = None      # pms
    visits: Optional[int] = None        # beach
    payments: Optional[int] = None      # leasing / timeshare
    total: float = 0.0

class RevenuePeriod(BaseModel):
    from_: str = Field(alias="from")
    to: str

    model_config = ConfigDict(populate_by_name=True)

class RevenueSummary(BaseModel):
    """GET /analytics/revenue"""
    period:     RevenuePeriod
    branch_id:  int
    restaurant: Optional[RevenueBucket] = None
    cafe:       Optional[RevenueBucket] = None
    pms:        Optional[RevenueBucket] = None
    beach:      Optional[RevenueBucket] = None
    leasing:    Optional[RevenueBucket] = None
    timeshare:  Optional[RevenueBucket] = None
    total:      float = 0.0


# ── Occupancy ─────────────────────────────────────────────────────────────────

class PMSOccupancy(BaseModel):
    nights_audited:       int
    avg_occupancy_pct:    float
    total_room_revenue:   Decimal

class OccupancySummary(BaseModel):
    """GET /analytics/occupancy"""
    month:  int
    year:   int
    pms:    Optional[PMSOccupancy] = None
    beach:  None = None   # حاليًا لا يُحسب


# ── HR Summary ────────────────────────────────────────────────────────────────

class LastPayrollSummary(BaseModel):
    period:     str           # "YYYY-MM"
    status:     str
    total_net:  Decimal

class HRSummary(BaseModel):
    """GET /analytics/hr"""
    active_employees: int = 0
    last_payroll:     Optional[LastPayrollSummary] = None


# ── Maintenance KPIs ──────────────────────────────────────────────────────────

class MaintenanceSummary(BaseModel):
    """GET /analytics/maintenance"""
    open_work_orders:     int = 0
    critical_work_orders: int = 0


# ── CRM Pipeline ─────────────────────────────────────────────────────────────

class PipelineStage(BaseModel):
    stage: str
    count: int
    value: Optional[Decimal] = None

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
    room_revenue:       float = 0
    beach_visitors:     int   = 0
    beach_revenue:      float = 0
    restaurant_covers:  int   = 0
    restaurant_revenue: float = 0
    # متوسط الفاتورة للفرد (Average Check per Cover) — مؤشر ضيافة أساسي،
    # الداتا (revenue وcovers) كانت متجمّعة أصلاً بس متقسمتش على بعض قبل
    # كده (2026-08-11، طلب Mohamed أثناء نقاش POS الكاشير). restaurant فقط
    # (مش cafe) لأن restaurant_covers نفسها بتتبع guests_count المطعم بس —
    # الكافيه counter-service من غير مفهوم "غطاء" حقيقي. null لو صفر غطاء
    # بدل 0 مضلّل (يبان وكأنه متوسط فعلي صفر مش "مفيش بيانات كافية").
    avg_check_per_cover: Optional[float] = None
    cafe_revenue:       float = 0
    total_revenue:      float = 0
    # حالة "لا توجد بيانات" — نرجع message بدل الأرقام
    message:            Optional[str] = None


# ── Energy KPIs ───────────────────────────────────────────────────────────────

class EnergyKPIs(BaseModel):
    """GET /analytics/energy — يطابق شكل get_energy_kpis() في services.py"""
    period:                            str
    by_type:                           dict[str, float] = Field(default_factory=dict)
    total_cost:                        float = 0.0
    guest_nights:                      int   = 0
    electricity_cost_per_guest_night:  Optional[float] = None


# ── Energy Trend ──────────────────────────────────────────────────────────────
# get_energy_trend() ترجع list[dict] (كل عنصر بنفس شكل EnergyKPIs)
# نستخدم list[EnergyKPIs] مباشرة كـ response_model

EnergyTrendResponse = list[EnergyKPIs]


# ── Guest Reviews ─────────────────────────────────────────────────────────────

class GuestReviewItem(BaseModel):
    id:             int
    guest_name:     Optional[str] = None
    overall_rating: float
    comment:        Optional[str] = None
    source:         Optional[str] = None
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
    overall_avg:        Optional[float] = None
    gss_score:          Optional[float] = None
    review_count:       int = 0
    category_breakdown: list[CategoryInsightItem] = Field(default_factory=list)


# ── Full Dashboard ─────────────────────────────────────────────────────────────

class DashboardRevenue(BaseModel):
    restaurant: float = 0
    cafe:       float = 0
    pms:        float = 0
    beach:      float = 0
    leasing:    float = 0
    timeshare:  float = 0
    total:      float = 0

class DashboardHR(BaseModel):
    active_employees:   int   = 0
    last_payroll_period: Optional[str] = None

class DashboardMaintenance(BaseModel):
    open_work_orders: int = 0

class DashboardCRM(BaseModel):
    total_customers: int = 0

class DashboardInventory(BaseModel):
    low_stock_count: int = 0

class DashboardReviews(BaseModel):
    count:      int   = 0
    avg_rating: Optional[float] = None

class FullDashboard(BaseModel):
    """GET /analytics/dashboard"""
    branch_id:   int
    as_of:       str
    revenue_30d: Optional[DashboardRevenue]    = None
    hr:          Optional[DashboardHR]         = None
    maintenance: Optional[DashboardMaintenance] = None
    crm:         Optional[DashboardCRM]        = None
    inventory:   Optional[DashboardInventory]  = None
    reviews:     Optional[DashboardReviews]    = None
