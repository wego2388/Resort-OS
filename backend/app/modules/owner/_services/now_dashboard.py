"""
app/modules/owner/_services/now_dashboard.py
Extracted from app/modules/owner/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from app.modules.owner.schemas import (
    DaySnapshot,
    NowHistoryResponse,
    OwnerNowResponse,
    OwnerPerformanceResponse,
    PeriodMeta,
)
from app.modules.owner._services._helpers import (
    _cairo_today,
    _is_period_provisional,
    _build_period_snapshot,
    _build_period_comparison,
    _build_outlet_breakdown,
    _fetch_b2b_receivables,
    _fetch_timeshare_receivables,
    _fetch_occupancy_now,
    _fetch_beach_capacity_today,
)


# Phase 3 — Public API: get_owner_now
# ══════════════════════════════════════════════════════════════════════

def get_owner_now(db: Session, branch_id: int) -> OwnerNowResponse:
    """
    يجمع المقاييس السبعة للشاشة الرئيسية (A-1 → A-7).

    كل مقياس مالي أساسي يُقرأ من مصدر الحقيقة المعتمد مباشرةً:
    - A-1, A-3: finance.services.get_income_statement
    - A-2:      finance.services.build_active_shifts_response
    - A-4:      beach.models.B2BContract + B2BContractDay
    - A-5:      timeshare.models.TimeshareInstallment
    - A-6:      pms.models.Room
    - A-7:      beach.models.BeachInventory

    branch_id يصل من الـ session server-side فقط — لا يُقبل من الـ client.
    """
    from app.modules.finance.services import (  # noqa: PLC0415
        build_active_shifts_response,
        get_income_statement,
    )

    today = _cairo_today()
    computed_at = datetime.utcnow()

    # A-1 + A-3: نداء واحد يعطينا الإيراد والمصروف معاً
    income_stmt = get_income_statement(db, branch_id, today, today)
    is_prov = _is_period_provisional(db, branch_id, today)

    # A-2: كاش الأدراج — مجموع expected_cash على كل الورديات المفتوحة
    shifts_resp = build_active_shifts_response(db, branch_id)
    cash_in_drawers = sum(
        (s.expected_cash for s in shifts_resp.shifts),
        Decimal("0"),
    )

    # A-4: ذمم B2B
    b2b_items, b2b_total = _fetch_b2b_receivables(db, branch_id)

    # A-5: ذمم ملكية جزئية
    ts_items, ts_total = _fetch_timeshare_receivables(db, branch_id, today)

    # A-6: إشغال الغرف
    occupancy = _fetch_occupancy_now(db, branch_id)

    # A-7: سعة الشاطئ
    beach_cap = _fetch_beach_capacity_today(db, branch_id, today)

    # A-8: ذمم آجلة شخصية (Decision 0005)
    from app.modules.credit.services import get_branch_outstanding  # noqa: PLC0415
    from app.modules.credit import crud as credit_crud  # noqa: PLC0415
    credit_outstanding = get_branch_outstanding(db, branch_id)
    # Suspended accounts remain collectible receivables and must not disappear
    # from the owner's exposure total/count.
    credit_count = len(credit_crud.get_accounts_with_balance(db, branch_id))

    return OwnerNowResponse(
        revenue_today=income_stmt.total_revenue,
        cash_in_drawers=cash_in_drawers,
        expense_today=income_stmt.total_expense,
        b2b_receivables=b2b_items,
        b2b_total_outstanding=b2b_total,
        timeshare_receivables=ts_items,
        timeshare_total_overdue=ts_total,
        occupancy=occupancy,
        beach_capacity=beach_cap,
        period=PeriodMeta(
            date_from=today,
            date_to=today,
            is_provisional=is_prov,
            computed_at=computed_at,
        ),
        open_shift_count=shifts_resp.shift_count,
        credit_account_outstanding=credit_outstanding,
        credit_account_count=credit_count,
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 3 — Public API: get_owner_performance
# ══════════════════════════════════════════════════════════════════════

def get_owner_performance(db: Session, branch_id: int) -> OwnerPerformanceResponse:
    """
    يبني مقارنة ثلاث فترات في طلب واحد:
    - اليوم vs أمس
    - الأسبوع الحالي (الاثنين → اليوم) vs الأسبوع الماضي (نفس المدة)
    - الشهر الحالي (1 الشهر → اليوم) vs الشهر الماضي (نفس اليوم من الشهر)

    كل فترة: نداءان منفصلان لـ get_income_statement — الـ delta يُحسب هنا
    بـ Decimal arithmetic — لا منطق مالي جديد في هذا الملف.
    """
    today = _cairo_today()
    yesterday = today - timedelta(days=1)

    # ── اليوم vs أمس ──────────────────────────────────────────────────
    snap_today = _build_period_snapshot(db, branch_id, today, today, "اليوم")
    snap_yesterday = _build_period_snapshot(db, branch_id, yesterday, yesterday, "أمس")
    # كان مقصور على مقارنة الشهر بس — مد نفس تفصيل المنفذ لليوم والأسبوع
    # كمان (أول سؤال منطقي للمالك لما يشوف فرق: "أي قسم سبب ده؟").
    day_breakdown = _build_outlet_breakdown(db, branch_id, today, today)
    day_comparison = _build_period_comparison(snap_today, snap_yesterday, day_breakdown)

    # ── الأسبوع الحالي vs الأسبوع الماضي ──────────────────────────────
    # الأسبوع الحالي: من الاثنين الأخير حتى اليوم
    days_since_monday = today.weekday()          # 0=الاثنين، 6=الأحد
    week_start = today - timedelta(days=days_since_monday)
    week_days = days_since_monday + 1            # عدد أيام الأسبوع الحالي حتى اليوم
    prior_week_end = week_start - timedelta(days=1)
    prior_week_start = prior_week_end - timedelta(days=week_days - 1)

    snap_this_week = _build_period_snapshot(
        db, branch_id, week_start, today, "هذا الأسبوع"
    )
    snap_prior_week = _build_period_snapshot(
        db, branch_id, prior_week_start, prior_week_end, "الأسبوع الماضي"
    )
    week_breakdown = _build_outlet_breakdown(db, branch_id, week_start, today)
    week_comparison = _build_period_comparison(snap_this_week, snap_prior_week, week_breakdown)

    # ── الشهر الحالي vs الشهر الماضي ──────────────────────────────────
    # الشهر الحالي: 1 الشهر → اليوم
    month_start = today.replace(day=1)
    day_of_month = today.day          # مثال: إذا اليوم 7 → نقارن 1-7 من الشهرين

    # الشهر الماضي: نفس الفترة بالضبط (1 الشهر الماضي → اليوم من الشهر الماضي)
    if month_start.month == 1:
        prior_month_start = month_start.replace(year=month_start.year - 1, month=12)
    else:
        prior_month_start = month_start.replace(month=month_start.month - 1)

    import calendar  # noqa: PLC0415
    days_in_prior_month = calendar.monthrange(prior_month_start.year, prior_month_start.month)[1]
    # نأخذ نفس اليوم من الشهر أو آخر يوم في الشهر الماضي (لو الشهر الماضي أقصر)
    prior_month_day = min(day_of_month, days_in_prior_month)
    prior_month_end = prior_month_start.replace(day=prior_month_day)

    snap_this_month = _build_period_snapshot(
        db, branch_id, month_start, today, "هذا الشهر"
    )
    snap_prior_month = _build_period_snapshot(
        db, branch_id, prior_month_start, prior_month_end, "الشهر الماضي"
    )
    # Phase 7e: breakdown للشهر الحالي فقط (الأكثر فائدة)
    month_breakdown = _build_outlet_breakdown(db, branch_id, month_start, today)
    month_comparison = _build_period_comparison(snap_this_month, snap_prior_month, month_breakdown)

    return OwnerPerformanceResponse(
        today_vs_yesterday=day_comparison,
        week_vs_prior_week=week_comparison,
        month_vs_prior_month=month_comparison,
        computed_at=datetime.utcnow(),
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 7a — Public API: get_now_history (Sparklines)
# ══════════════════════════════════════════════════════════════════════

def get_now_history(db: Session, branch_id: int, days: int = 7) -> NowHistoryResponse:
    """
    يرجع آخر N أيام من مقاييس شاشة "الآن" للـ sparklines.

    كل يوم: revenue, expense, cash_in_drawers, occupancy_pct, beach_utilisation_pct
    مصادر: نفس مصادر get_owner_now — لا حسابات جديدة.
    الأيام مرتّبة تصاعدياً (الأقدم أولاً).
    """
    from app.modules.finance.services import (  # noqa: PLC0415
        build_active_shifts_response,
        get_income_statement,
    )

    today = _cairo_today()
    days = max(1, min(days, 30))  # 1-30 يوم فقط
    snapshots: list[DaySnapshot] = []

    for i in range(days - 1, -1, -1):  # من الأقدم للأحدث
        day = today - timedelta(days=i)
        try:
            income = get_income_statement(db, branch_id, day, day)
            revenue = income.total_revenue
            expense = income.total_expense
        except Exception:
            revenue = Decimal("0")
            expense = Decimal("0")

        # كاش الأدراج: فقط لليوم الحالي (الورديات المفتوحة)
        # للأيام الماضية نرجع صفر (لا يوجد "وردية مفتوحة أمس")
        cash = Decimal("0")
        if i == 0:
            try:
                shifts_resp = build_active_shifts_response(db, branch_id)
                cash = sum((s.expected_cash for s in shifts_resp.shifts), Decimal("0"))
            except Exception:
                cash = Decimal("0")

        try:
            occ = _fetch_occupancy_now(db, branch_id)
            occupancy_pct = occ.occupancy_pct
        except Exception:
            occupancy_pct = Decimal("0")

        try:
            beach = _fetch_beach_capacity_today(db, branch_id, day)
            beach_pct = beach.utilisation_pct
        except Exception:
            beach_pct = Decimal("0")

        is_prov = _is_period_provisional(db, branch_id, day)

        snapshots.append(DaySnapshot(
            day=day,
            revenue=revenue,
            expense=expense,
            cash_in_drawers=cash,
            occupancy_pct=occupancy_pct,
            beach_utilisation_pct=beach_pct,
            is_provisional=is_prov,
        ))

    return NowHistoryResponse(days=snapshots, computed_at=datetime.utcnow())
