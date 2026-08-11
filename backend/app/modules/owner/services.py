"""
app/modules/owner/services.py
═══════════════════════════════════════════════════════════════════════
Owner Intelligence Cockpit — Services (Decision 0004, Phase 2+3).

Phase 2: OwnerWatchlist + OwnerAllocationRule draft logic.
Phase 3: Aggregation services — /owner/now + /owner/performance.

قواعد ثابتة:
• كل مقياس مالي أساسي (revenue/expense/cash) يُقرأ من مصدر الحقيقة الموجود
  مباشرةً — لا يُعاد حسابه هنا (Decision 0004 §Numbers must equal the source).
• branch_id يُشتق من الـ session server-side فقط — لا يُقبل من الـ client.
• كل رقم يحمل period + is_provisional + computed_at.
• لا رقم provisional يُقدَّم كأنه نهائي.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.owner import crud
from app.modules.owner.models import OwnerAllocationRule, OwnerWatchlist
from app.modules.owner.schemas import (
    AllocationRuleDraftCreate,
    AllocationRuleDraftUpdate,
    B2BReceivableItem,
    BeachCapacityToday,
    BeachPerformanceResponse,
    BeachTicketTypeRow,
    BeachTypeDetailResponse,
    BeachTypeTransaction,
    ChannelAnalyticsResponse,
    ChannelContractRow,
    CashMovementItem,
    CustomerGroupDiscountRow,
    CustomerGroupMember,
    DaySnapshot,
    DiningItemDetailResponse,
    DiningItemTransaction,
    DiscountAnalyticsResponse,
    DiscountTypeRow,
    EmployeeAttendanceSummary,
    EmployeePayrollSummary,
    ExceptionsResponse,
    ExpenseAnalyticsResponse,
    ExpenseDetailResponse,
    ExpenseJournalLine,
    ExpenseLineResponse,
    HREmployeeRow,
    HRSummaryResponse,
    ItemMetricResponse,
    ManualDiscountPerCashier,
    NowHistoryResponse,
    OccupancyNow,
    OwnerExceptionItem,
    OwnerNowResponse,
    OwnerPerformanceResponse,
    OwnerWatchlistCreate,
    OwnerSearchResponse,
    PayrollSummary,
    ProductDetailResponse,
    ProductMovement,
    PerformanceBreakdown,
    PeriodComparison,
    PeriodMeta,
    PeriodSnapshot,
    PRPOVarianceRow,
    ProcurementAnalyticsResponse,
    SalesPerformanceResponse,
    SearchResultItem,
    ShiftHistoryItem,
    ShiftHistoryResponse,
    ShiftMonitorItem,
    ShiftMonitorResponse,
    SupplierDetailResponse,
    SupplierPurchaseOrder,
    SupplierSpendRow,
    TimeshareReceivableItem,
)
from app.resort_os.owner_analytics_engine import (
    ItemMetric,
    ExpenseLine,
    OwnerException,
    ShiftVarianceResult,
    SupplierSpend,
    PRPOVarianceLine,
    classify_abc,
    enrich_items_with_margin,
    detect_variance,
    score_supplier_concentration,
    compute_pr_po_variance,
    score_shift_variance,
    rank_exceptions,
    build_fraud_exceptions,
    build_shift_variance_exceptions,
)
from app.resort_os.timezone_utils import business_today


# ══════════════════════════════════════════════════════════════════════
# Phase 2 — OwnerWatchlist
# ══════════════════════════════════════════════════════════════════════

def get_watchlist(db: Session, owner_user_id: int, branch_id: int) -> list[OwnerWatchlist]:
    return crud.list_watchlist(db, owner_user_id, branch_id)


def add_watchlist_item(
    db: Session, data: OwnerWatchlistCreate, owner_user_id: int,
) -> OwnerWatchlist:
    """يضيف metric للـ watchlist — يرفض التكرار."""
    existing = (
        db.query(OwnerWatchlist)
        .filter(
            OwnerWatchlist.owner_user_id == owner_user_id,
            OwnerWatchlist.metric_key == data.metric_key,
            OwnerWatchlist.branch_id == data.branch_id,
        )
        .first()
    )
    if existing:
        raise ValueError(f"المقياس '{data.metric_key}' موجود بالفعل في قائمة المراقبة")

    item = crud.create_watchlist_item(db, data, owner_user_id)
    db.commit()
    db.refresh(item)
    return item


def remove_watchlist_item(db: Session, item_id: int, owner_user_id: int) -> None:
    item = crud.get_watchlist_item(db, item_id, owner_user_id)
    if not item:
        raise ValueError(f"العنصر {item_id} غير موجود أو لا تملك صلاحية حذفه")
    crud.delete_watchlist_item(db, item)
    db.commit()


# ══════════════════════════════════════════════════════════════════════
# Phase 2 — OwnerAllocationRule
# ══════════════════════════════════════════════════════════════════════

def list_allocation_rules(db: Session, branch_id: int) -> list[OwnerAllocationRule]:
    return crud.list_allocation_rules(db, branch_id)


def create_draft(
    db: Session, data: AllocationRuleDraftCreate, owner_user_id: int,
) -> OwnerAllocationRule:
    rule = crud.create_allocation_rule_draft(db, data, created_by=owner_user_id)
    db.commit()
    db.refresh(rule)
    return rule


def update_draft(
    db: Session, rule_id: int, data: AllocationRuleDraftUpdate, owner_user_id: int,
) -> OwnerAllocationRule:
    rule = crud.get_allocation_rule(db, rule_id)
    if not rule:
        raise ValueError(f"قاعدة التخصيص {rule_id} غير موجودة")
    if rule.status != "draft":
        raise ValueError("لا يمكن تعديل قاعدة منشورة — أنشئ مسودة جديدة")
    rule = crud.update_allocation_rule_draft(db, rule, data)
    db.commit()
    db.refresh(rule)
    return rule


def delete_draft(db: Session, rule_id: int, owner_user_id: int) -> None:
    rule = crud.get_allocation_rule(db, rule_id)
    if not rule:
        raise ValueError(f"قاعدة التخصيص {rule_id} غير موجودة")
    if rule.status != "draft":
        raise ValueError("لا يمكن حذف قاعدة منشورة")
    crud.delete_allocation_rule_draft(db, rule)
    db.commit()


# ══════════════════════════════════════════════════════════════════════
# Phase 3 — داخلي: helpers
# ══════════════════════════════════════════════════════════════════════

def _cairo_today() -> date:
    """تاريخ اليوم بتوقيت القاهرة — المصدر الوحيد لـ 'اليوم' في كل owner services."""
    return business_today(get_settings().TIMEZONE)


def _is_period_provisional(db: Session, branch_id: int, for_date: date) -> bool:
    """يتحقق هل الفترة المحاسبية للشهر المطلوب مقفولة أم لا.

    المنطق: لو في AccountingPeriod مقفولة (closed=True أو status='closed')
    للشهر ده → الأرقام نهائية. لو مفيش record أصلاً أو مفتوحة → provisional.

    اليوم الحالي دايماً provisional (مش ممكن تقفل الشهر وهو لسه جاري).
    """
    from app.modules.finance.crud import get_period_status  # noqa: PLC0415

    period = get_period_status(db, branch_id, for_date.year, for_date.month)
    if period is None:
        return True  # لا يوجد record → provisional
    # status field على AccountingPeriod: 'open' | 'closed'
    return getattr(period, "status", "open") != "closed"


def _safe_pct(numerator: Decimal, denominator: Decimal) -> Optional[Decimal]:
    """نسبة التغيير % — None لو المقام صفر (تجنّب ZeroDivisionError)."""
    if denominator == Decimal("0"):
        return None
    return ((numerator - denominator) / denominator * Decimal("100")).quantize(Decimal("0.01"))


def _build_period_snapshot(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
    label: str,
) -> PeriodSnapshot:
    """يبني PeriodSnapshot لفترة معيّنة بـ استدعاء واحد لـ get_income_statement.

    is_provisional يتحدد بالشهر اللي فيه date_to (الشهر الأخير في المدى) —
    لو أي جزء من الفترة في شهر مفتوح → provisional.
    """
    from app.modules.finance.services import get_income_statement  # noqa: PLC0415

    report = get_income_statement(db, branch_id, date_from, date_to)
    is_prov = _is_period_provisional(db, branch_id, date_to)

    return PeriodSnapshot(
        date_from=date_from,
        date_to=date_to,
        label=label,
        total_revenue=report.total_revenue,
        total_expense=report.total_expense,
        net_income=report.net_income,
        is_provisional=is_prov,
        computed_at=datetime.utcnow(),
    )


def _build_period_comparison(
    current: PeriodSnapshot,
    prior: PeriodSnapshot,
    breakdown: "Optional[PerformanceBreakdown]" = None,
) -> PeriodComparison:
    """يحسب الـ delta والنسب — خارج finance module تماماً."""
    return PeriodComparison(
        current=current,
        prior=prior,
        revenue_delta=current.total_revenue - prior.total_revenue,
        revenue_pct=_safe_pct(current.total_revenue, prior.total_revenue),
        expense_delta=current.total_expense - prior.total_expense,
        expense_pct=_safe_pct(current.total_expense, prior.total_expense),
        net_income_delta=current.net_income - prior.net_income,
        net_income_pct=_safe_pct(current.net_income, prior.net_income),
        breakdown=breakdown,
    )


def _build_outlet_breakdown(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
) -> "PerformanceBreakdown":
    """
    Phase 7e: يحسب breakdown الإيراد per outlet للفترة.
    مصدر: نفس مصادر Phase 6 — لا جداول جديدة.
    None لو البيانات مش متاحة (provisional أو لا معاملات).
    """
    from app.modules.owner.schemas import PerformanceBreakdown  # noqa: PLC0415

    # dining revenue من income statement
    dining_rev: Optional[Decimal] = None
    beach_rev: Optional[Decimal] = None
    rooms_rev: Optional[Decimal] = None
    other_rev: Optional[Decimal] = None

    try:
        from app.modules.finance.services import get_income_statement  # noqa: PLC0415
        income = get_income_statement(db, branch_id, date_from, date_to)
        # dining: cost centers أو revenue accounts تحتوي "dining"/"restaurant"/"cafe"
        # نستخدم التقسيم المتاح في income statement
        for line in getattr(income, 'revenue_lines', []):
            code = getattr(line, 'account_code', '') or ''
            name = getattr(line, 'account_name', '') or ''
            amt  = getattr(line, 'amount', Decimal('0'))
            low  = (code + name).lower()
            if any(kw in low for kw in ('dining', 'restaurant', 'food', 'cafe', 'مطعم', 'كافيه')):
                dining_rev = (dining_rev or Decimal('0')) + amt
            elif any(kw in low for kw in ('beach', 'شاطئ')):
                beach_rev = (beach_rev or Decimal('0')) + amt
            elif any(kw in low for kw in ('room', 'hotel', 'pms', 'غرف', 'فندق')):
                rooms_rev = (rooms_rev or Decimal('0')) + amt
            else:
                other_rev = (other_rev or Decimal('0')) + amt
    except Exception:
        pass  # لو income statement فشل، كل القيم تبقى None

    return PerformanceBreakdown(
        dining_revenue=dining_rev,
        beach_revenue=beach_rev,
        rooms_revenue=rooms_rev,
        other_revenue=other_rev,
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 3 — داخلي: data fetchers لكل مقياس
# ══════════════════════════════════════════════════════════════════════

def _fetch_b2b_receivables(db: Session, branch_id: int) -> tuple[list[B2BReceivableItem], Decimal]:
    """A-4: ذمم B2B — كل عقد نشط مع رصيده غير المسوّى منذ last_settled_at.

    الرصيد = مجموع B2BContractDay.total_amount بعد last_settled_at.
    لا يحتوي الـ response على اسم ضيف أو هاتف (Decision 0004 §Isolation
    model item 7 — B2B per hotel/contract only, never per named guest).
    """
    from app.modules.beach.models import B2BContract, B2BContractDay  # noqa: PLC0415

    contracts = (
        db.query(B2BContract)
        .filter(
            B2BContract.branch_id == branch_id,
            B2BContract.is_active.is_(True),
        )
        .all()
    )

    items: list[B2BReceivableItem] = []
    total = Decimal("0")

    for contract in contracts:
        # نحسب الرصيد غير المسوّى منذ last_settled_at
        q = db.query(B2BContractDay).filter(
            B2BContractDay.contract_id == contract.id,
        )
        if contract.last_settled_at is not None:
            q = q.filter(B2BContractDay.day > contract.last_settled_at)

        days = q.all()
        outstanding = sum((d.total_amount for d in days), Decimal("0"))
        total += outstanding

        items.append(B2BReceivableItem(
            contract_id=contract.id,
            hotel_name=contract.hotel_name,
            outstanding=outstanding,
            is_overdue=contract.is_overdue,
            credit_limit=contract.credit_limit,
            last_settled_at=contract.last_settled_at,
        ))

    # ترتيب: المتأخرون أولاً ثم الأكبر رصيداً
    items.sort(key=lambda x: (not x.is_overdue, -x.outstanding))
    return items, total


def _fetch_timeshare_receivables(
    db: Session, branch_id: int, today: date,
) -> tuple[list[TimeshareReceivableItem], Decimal]:
    """A-5: ذمم تايم شير — أقساط unpaid/overdue بـ due_date <= اليوم.

    نجمّع بالعقد (contract_id) — لا نكشف اسم ضيف (Decision 0004 §Isolation
    model item 7). نحتاج join مع TimeshareContract للـ branch_id.
    """
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.timeshare.models import (  # noqa: PLC0415
        TimeshareContract,
        TimeshareInstallment,
    )

    rows = (
        db.query(
            TimeshareInstallment.contract_id,
            sa_func.sum(TimeshareInstallment.amount).label("total_overdue"),
            sa_func.count(TimeshareInstallment.id).label("installment_count"),
        )
        .join(TimeshareContract, TimeshareContract.id == TimeshareInstallment.contract_id)
        .filter(
            TimeshareContract.branch_id == branch_id,
            TimeshareInstallment.status.in_(["unpaid", "overdue"]),
            TimeshareInstallment.due_date <= today,
        )
        .group_by(TimeshareInstallment.contract_id)
        .all()
    )

    items: list[TimeshareReceivableItem] = []
    total = Decimal("0")
    for row in rows:
        overdue_amount = row.total_overdue or Decimal("0")
        total += overdue_amount
        items.append(TimeshareReceivableItem(
            contract_id=row.contract_id,
            total_overdue=overdue_amount,
            installment_count=row.installment_count,
        ))

    items.sort(key=lambda x: -x.total_overdue)
    return items, total


def _fetch_occupancy_now(db: Session, branch_id: int) -> OccupancyNow:
    """A-6: إشغال الغرف الحالي — نسبة الغرف occupied من إجمالي الغرف.

    ليس توقعاً — حالة فعلية لحظية من Room.status.
    الغرف في حالة maintenance/out_of_order تُستثنى من المقام.
    """
    from app.modules.pms.models import Room  # noqa: PLC0415
    from sqlalchemy import func as sa_func  # noqa: PLC0415

    # المقام: كل الغرف النشطة (ليست maintenance / out_of_order)
    total_rooms: int = (
        db.query(sa_func.count(Room.id))
        .filter(
            Room.branch_id == branch_id,
            Room.status.notin_(["maintenance", "out_of_order"]),
        )
        .scalar() or 0
    )

    # البسط: الغرف المشغولة فعلياً
    occupied_rooms: int = (
        db.query(sa_func.count(Room.id))
        .filter(
            Room.branch_id == branch_id,
            Room.status == "occupied",
        )
        .scalar() or 0
    )

    if total_rooms > 0:
        pct = (Decimal(occupied_rooms) / Decimal(total_rooms) * Decimal("100")).quantize(
            Decimal("0.1")
        )
    else:
        pct = Decimal("0")

    return OccupancyNow(
        occupied_rooms=occupied_rooms,
        total_rooms=total_rooms,
        occupancy_pct=pct,
        computed_at=datetime.utcnow(),
    )


def _fetch_beach_capacity_today(db: Session, branch_id: int, today: date) -> BeachCapacityToday:
    """A-7: سعة الشاطئ اليوم — من BeachInventory لليوم الحالي.

    capacity_used عدّاد تراكمي (لا يتراجع عند الإلغاء) — يُعرض كـ
    'تذاكر مباعة اليوم' لا 'إشغال فعلي الآن' (kpi-contracts A-7).
    لو لا يوجد record لليوم → يُعاد صفر/صفر.
    """
    from app.modules.beach.models import BeachInventory  # noqa: PLC0415

    inv = (
        db.query(BeachInventory)
        .filter(
            BeachInventory.branch_id == branch_id,
            BeachInventory.inventory_date == today,
        )
        .first()
    )

    if inv is None:
        return BeachCapacityToday(
            capacity_used=0,
            capacity_max=0,
            utilisation_pct=Decimal("0"),
            inventory_date=today,
        )

    if inv.capacity_max > 0:
        pct = (Decimal(inv.capacity_used) / Decimal(inv.capacity_max) * Decimal("100")).quantize(
            Decimal("0.1")
        )
    else:
        pct = Decimal("0")

    return BeachCapacityToday(
        capacity_used=inv.capacity_used,
        capacity_max=inv.capacity_max,
        utilisation_pct=pct,
        inventory_date=inv.inventory_date,
    )


# ══════════════════════════════════════════════════════════════════════
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

    # A-5: ذمم تايم شير
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


# ══════════════════════════════════════════════════════════════════════
# Phase 6 — Sales Performance (C-1, C-2)
# ══════════════════════════════════════════════════════════════════════

def get_sales_performance(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
    outlet: str = "dining",
    limit: int = 50,
) -> SalesPerformanceResponse:
    """
    أداء المبيعات: top items مرتّبة بالإيراد + ABC Pareto + هامش ربح.

    outlet: 'dining' | 'beach' | 'all' (dining + beach مدمجَين)
    مصدر dining: DiningOrderItem (paid orders فقط)
    مصدر beach: BeachTransaction (non-voided فقط)
    هامش الربح: من MenuItemRecipeLine + Product.cost_price (لو موجود)
    لا float — Decimal طول الوقت.
    """
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.dining.models import DiningOrder, DiningOrderItem  # noqa: PLC0415
    from app.modules.beach.models import BeachTransaction  # noqa: PLC0415

    items: list[ItemMetric] = []

    # ── Dining items ──────────────────────────────────────────────────
    if outlet in ("dining", "all"):
        rows = (
            db.query(
                DiningOrderItem.item_id.label("item_id"),
                DiningOrderItem.name.label("name"),
                sa_func.sum(DiningOrderItem.quantity).label("qty"),
                sa_func.sum(
                    DiningOrderItem.unit_price * DiningOrderItem.quantity
                ).label("revenue"),
            )
            .join(DiningOrder, DiningOrder.id == DiningOrderItem.order_id)
            .filter(
                DiningOrder.branch_id == branch_id,
                DiningOrder.status == "paid",
                DiningOrder.created_at >= datetime.combine(date_from, datetime.min.time()),
                DiningOrder.created_at <= datetime.combine(date_to, datetime.max.time()),
                DiningOrderItem.status != "cancelled",
            )
            .group_by(DiningOrderItem.item_id, DiningOrderItem.name)
            .order_by(sa_func.sum(
                DiningOrderItem.unit_price * DiningOrderItem.quantity
            ).desc())
            .limit(limit)
            .all()
        )

        # نجلب recipe costs بـ batch query لتجنّب N+1
        item_ids = [r.item_id for r in rows if r.item_id is not None]
        recipe_costs: dict[int, Decimal] = {}
        if item_ids:
            recipe_costs = _fetch_recipe_costs(db, item_ids)

        for r in rows:
            items.append(ItemMetric(
                item_id=r.item_id or 0,
                name=r.name,
                quantity_sold=int(r.qty or 0),
                revenue=Decimal(str(r.revenue or 0)),
                recipe_cost=recipe_costs.get(r.item_id) if r.item_id else None,
            ))

    # ── Beach ticket types (كـ items) ────────────────────────────────
    if outlet in ("beach", "all"):
        beach_rows = (
            db.query(
                BeachTransaction.tx_type.label("tx_type"),
                sa_func.count(BeachTransaction.id).label("cnt"),
                sa_func.sum(BeachTransaction.total_amount).label("revenue"),
            )
            .filter(
                BeachTransaction.branch_id == branch_id,
                BeachTransaction.voided_at.is_(None),
                BeachTransaction.tx_date >= date_from,
                BeachTransaction.tx_date <= date_to,
            )
            .group_by(BeachTransaction.tx_type)
            .all()
        )
        for br in beach_rows:
            items.append(ItemMetric(
                item_id=0,
                name=f"شاطئ — {br.tx_type}",
                quantity_sold=int(br.cnt or 0),
                revenue=Decimal(str(br.revenue or 0)),
                recipe_cost=None,
            ))

    # ── ABC + Margin ───────────────────────────────────────────────────
    items = classify_abc(items)
    items = enrich_items_with_margin(items)

    total_revenue = sum(i.revenue for i in items)
    is_prov = _is_period_provisional(db, branch_id, date_to)

    return SalesPerformanceResponse(
        period_from=date_from,
        period_to=date_to,
        outlet=outlet,
        items=[
            ItemMetricResponse(
                item_id=i.item_id,
                name=i.name,
                quantity_sold=i.quantity_sold,
                revenue=i.revenue,
                recipe_cost=i.recipe_cost,
                margin_pct=i.margin_pct,
                margin_amount=i.margin_amount,
                abc_class=i.abc_class,
                cumulative_pct=i.cumulative_pct,
            )
            for i in items
        ],
        total_revenue=total_revenue,
        is_provisional=is_prov,
        computed_at=datetime.utcnow(),
    )


def _fetch_recipe_costs(db: Session, menu_item_ids: list[int]) -> dict[int, Decimal]:
    """Batch: يجلب تكلفة وصفة الوحدة لقائمة dining item_ids.

    التكلفة = SUM(Product.cost_price × DiningItemRecipeLine.quantity_per_unit)
    per item_id.
    """
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.dining.models import DiningItemRecipeLine  # noqa: PLC0415
    from app.modules.inventory.models import Product  # noqa: PLC0415

    if not menu_item_ids:
        return {}

    rows = (
        db.query(
            DiningItemRecipeLine.item_id,
            sa_func.sum(Product.cost_price * DiningItemRecipeLine.quantity_per_unit).label("unit_cost"),
        )
        .join(Product, Product.id == DiningItemRecipeLine.product_id)
        .filter(DiningItemRecipeLine.item_id.in_(menu_item_ids))
        .group_by(DiningItemRecipeLine.item_id)
        .all()
    )

    return {r.item_id: Decimal(str(r.unit_cost or 0)) for r in rows}


# ══════════════════════════════════════════════════════════════════════
# Phase 6 — Beach Performance by Ticket Type (C-3)
# ══════════════════════════════════════════════════════════════════════

def get_beach_performance(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
) -> BeachPerformanceResponse:
    """
    C-3: أداء الشاطئ مقسّم بنوع التذكرة.
    مصدر: BeachTransaction (non-voided, tx_date في المدى).
    """
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.beach.models import BeachTransaction  # noqa: PLC0415

    rows = (
        db.query(
            BeachTransaction.tx_type,
            sa_func.count(BeachTransaction.id).label("cnt"),
            sa_func.sum(BeachTransaction.total_amount).label("total"),
            sa_func.avg(BeachTransaction.unit_price).label("avg_price"),
        )
        .filter(
            BeachTransaction.branch_id == branch_id,
            BeachTransaction.voided_at.is_(None),
            BeachTransaction.tx_date >= date_from,
            BeachTransaction.tx_date <= date_to,
        )
        .group_by(BeachTransaction.tx_type)
        .order_by(sa_func.sum(BeachTransaction.total_amount).desc())
        .all()
    )

    ticket_types = [
        BeachTicketTypeRow(
            tx_type=r.tx_type,
            count=int(r.cnt or 0),
            total_amount=Decimal(str(r.total or 0)),
            avg_unit_price=Decimal(str(r.avg_price or 0)).quantize(Decimal("0.01")),
        )
        for r in rows
    ]

    total_revenue = sum(t.total_amount for t in ticket_types)
    total_count   = sum(t.count for t in ticket_types)

    return BeachPerformanceResponse(
        period_from=date_from,
        period_to=date_to,
        ticket_types=ticket_types,
        total_revenue=total_revenue,
        total_count=total_count,
        computed_at=datetime.utcnow(),
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 6 — Channel Analytics / B2B (C-4)
# ══════════════════════════════════════════════════════════════════════

def get_channel_analytics(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
) -> ChannelAnalyticsResponse:
    """
    C-4: أداء قنوات B2B — per hotel/contract.
    لا بيانات ضيف فردية (Decision 0004 §Isolation model item 7).

    البيانات:
    - B2BContractDay: check-ins وإيراد الشاطئ في الفترة
    - DiningOrder.b2b_contract_id: F&B attach (REL-10)
    - B2BContract: outstanding وoverdue (من _fetch_b2b_receivables)
    """
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.beach.models import B2BContract, B2BContractDay  # noqa: PLC0415
    from app.modules.dining.models import DiningOrder  # noqa: PLC0415

    contracts = (
        db.query(B2BContract)
        .filter(B2BContract.branch_id == branch_id, B2BContract.is_active.is_(True))
        .all()
    )

    if not contracts:
        return ChannelAnalyticsResponse(
            period_from=date_from,
            period_to=date_to,
            contracts=[],
            total_checkins=0,
            total_beach_revenue=Decimal("0"),
            total_fnb_attach=Decimal("0"),
            computed_at=datetime.utcnow(),
        )

    contract_ids = [c.id for c in contracts]

    # Beach revenue + checkins في الفترة
    beach_rows = (
        db.query(
            B2BContractDay.contract_id,
            sa_func.sum(B2BContractDay.checked_in_count).label("checkins"),
            sa_func.sum(B2BContractDay.total_amount).label("beach_rev"),
        )
        .filter(
            B2BContractDay.contract_id.in_(contract_ids),
            B2BContractDay.day >= date_from,
            B2BContractDay.day <= date_to,
        )
        .group_by(B2BContractDay.contract_id)
        .all()
    )
    beach_by_contract = {r.contract_id: r for r in beach_rows}

    # F&B attach: مجموع dining orders بـ b2b_contract_id في الفترة
    fnb_rows = (
        db.query(
            DiningOrder.b2b_contract_id,
            sa_func.sum(DiningOrder.total).label("fnb_total"),
        )
        .filter(
            DiningOrder.b2b_contract_id.in_(contract_ids),
            DiningOrder.status == "paid",
            DiningOrder.created_at >= datetime.combine(date_from, datetime.min.time()),
            DiningOrder.created_at <= datetime.combine(date_to, datetime.max.time()),
        )
        .group_by(DiningOrder.b2b_contract_id)
        .all()
    )
    fnb_by_contract = {r.b2b_contract_id: Decimal(str(r.fnb_total or 0)) for r in fnb_rows}

    # Outstanding per contract (نفس منطق _fetch_b2b_receivables)
    _, _ = _fetch_b2b_receivables(db, branch_id)   # نعيد الحساب مؤقتاً
    b2b_items_map, _ = _fetch_b2b_receivables(db, branch_id)
    outstanding_map = {item.contract_id: item.outstanding for item in b2b_items_map}
    overdue_map     = {item.contract_id: item.is_overdue  for item in b2b_items_map}
    credit_map      = {item.contract_id: item.credit_limit for item in b2b_items_map}

    contract_rows = []
    for c in contracts:
        bd = beach_by_contract.get(c.id)
        checkins    = int(bd.checkins or 0) if bd else 0
        beach_rev   = Decimal(str(bd.beach_rev or 0)) if bd else Decimal("0")
        fnb_attach  = fnb_by_contract.get(c.id, Decimal("0"))
        fnb_avg     = (fnb_attach / checkins).quantize(Decimal("0.01")) if checkins > 0 else Decimal("0")

        contract_rows.append(ChannelContractRow(
            contract_id=c.id,
            hotel_name=c.hotel_name,
            period_checkins=checkins,
            period_revenue=beach_rev,
            outstanding=outstanding_map.get(c.id, Decimal("0")),
            is_overdue=overdue_map.get(c.id, False),
            credit_limit=credit_map.get(c.id),
            fnb_attach=fnb_attach,
            fnb_avg_per_checkin=fnb_avg,
        ))

    # ترتيب: الأعلى إيراداً أولاً
    contract_rows.sort(key=lambda x: -x.period_revenue)

    return ChannelAnalyticsResponse(
        period_from=date_from,
        period_to=date_to,
        contracts=contract_rows,
        total_checkins=sum(r.period_checkins for r in contract_rows),
        total_beach_revenue=sum(r.period_revenue for r in contract_rows),
        total_fnb_attach=sum(r.fnb_attach for r in contract_rows),
        computed_at=datetime.utcnow(),
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 6 — Expense Analytics (D-1, D-2)
# ══════════════════════════════════════════════════════════════════════

def get_expense_analytics(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
) -> ExpenseAnalyticsResponse:
    """
    D-1 + D-2: كل فئة مصروف كنسبة % من الإيراد مع variance flags.

    الفترة المقارنة = نفس المدة الزمنية بالضبط في الشهر السابق.
    مصدر: finance.services.get_income_statement (نفس كل مقياس مالي آخر).
    رواتب: PayrollRun.total_net aggregate — لا per employee.
    """
    from app.modules.finance.services import get_income_statement  # noqa: PLC0415
    from app.modules.hr.models import PayrollRun  # noqa: PLC0415

    # فترة المقارنة: نفس المدة في الشهر الماضي
    delta = date_to - date_from
    prior_to   = date_from - timedelta(days=1)
    prior_from = prior_to - delta

    current_stmt = get_income_statement(db, branch_id, date_from, date_to)
    prior_stmt   = get_income_statement(db, branch_id, prior_from, prior_to)
    is_prov = _is_period_provisional(db, branch_id, date_to)

    # بناء expense lines من account breakdown
    current_by_code = {
        line.account_code: line
        for line in getattr(current_stmt, "expense_lines", [])
    }
    prior_by_code = {
        line.account_code: line
        for line in getattr(prior_stmt, "expense_lines", [])
    }

    all_codes = set(current_by_code) | set(prior_by_code)
    expense_lines_raw: list[ExpenseLine] = []
    for code in sorted(all_codes):
        cur  = current_by_code.get(code)
        prev = prior_by_code.get(code)
        expense_lines_raw.append(ExpenseLine(
            account_code=code,
            account_name=getattr(cur or prev, "account_name", code),
            current_amount=Decimal(str(getattr(cur,  "amount", 0) or 0)),
            prior_amount  =Decimal(str(getattr(prev, "amount", 0) or 0)),
            current_revenue=current_stmt.total_revenue,
            prior_revenue  =prior_stmt.total_revenue,
        ))

    enriched = detect_variance(expense_lines_raw)

    # رواتب الشهر الحالي (aggregate فقط)
    payroll_summary: Optional[PayrollSummary] = None
    payroll_run = (
        db.query(PayrollRun)
        .filter(
            PayrollRun.branch_id == branch_id,
            PayrollRun.period_year  == date_from.year,
            PayrollRun.period_month == date_from.month,
        )
        .first()
    )
    if payroll_run:
        payroll_pct = _safe_pct(payroll_run.total_net, current_stmt.total_revenue) \
                      if current_stmt.total_revenue > Decimal("0") else None
        payroll_summary = PayrollSummary(
            period_year=payroll_run.period_year,
            period_month=payroll_run.period_month,
            total_net=payroll_run.total_net,
            revenue=current_stmt.total_revenue,
            payroll_pct=payroll_pct,
            status=payroll_run.status,
        )

    return ExpenseAnalyticsResponse(
        period_from=date_from,
        period_to=date_to,
        prior_from=prior_from,
        prior_to=prior_to,
        current_revenue=current_stmt.total_revenue,
        prior_revenue=prior_stmt.total_revenue,
        expense_lines=[
            ExpenseLineResponse(
                account_code=el.account_code,
                account_name=el.account_name,
                current_amount=el.current_amount,
                prior_amount=el.prior_amount,
                current_pct=el.current_pct,
                prior_pct=el.prior_pct,
                variance_flag=el.variance_flag,
                variance_delta=el.variance_delta,
            )
            for el in enriched
        ],
        payroll=payroll_summary,
        is_provisional=is_prov,
        computed_at=datetime.utcnow(),
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 6 — Procurement Analytics (E-1, E-2)
# ══════════════════════════════════════════════════════════════════════

def get_procurement_analytics(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
) -> ProcurementAnalyticsResponse:
    """
    E-1: تركّز الإنفاق بالموردين.
    E-2: فرق PR estimate vs PO actual (عبر source_request_id — Phase 2 fix).

    PurchaseOrder.status IN ('received','partial') — أوامر مستلمة فعلاً.
    لا float — Decimal طول الوقت.
    """
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.inventory.models import (  # noqa: PLC0415
        PurchaseOrder, PurchaseOrderItem,
        PurchaseRequest, PurchaseRequestItem,
        Supplier, Product,
    )

    # E-1: إنفاق بالمورد
    supplier_rows = (
        db.query(
            PurchaseOrder.supplier_id,
            sa_func.coalesce(Supplier.name, PurchaseOrder.supplier_name, "غير محدد").label("supplier_name"),
            sa_func.sum(PurchaseOrder.total_amount).label("total_spend"),
            sa_func.count(PurchaseOrder.id).label("order_count"),
        )
        .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .filter(
            PurchaseOrder.branch_id == branch_id,
            PurchaseOrder.status.in_(["received", "partial"]),
            PurchaseOrder.ordered_at >= date_from,
            PurchaseOrder.ordered_at <= date_to,
        )
        .group_by(PurchaseOrder.supplier_id, Supplier.name, PurchaseOrder.supplier_name)
        .all()
    )

    supplier_spends = [
        SupplierSpend(
            supplier_id=r.supplier_id or 0,
            supplier_name=r.supplier_name or "غير محدد",
            total_spend=Decimal(str(r.total_spend or 0)),
        )
        for r in supplier_rows
    ]
    supplier_spends = score_supplier_concentration(supplier_spends)
    order_counts = {r.supplier_id: int(r.order_count) for r in supplier_rows}
    total_spend = sum(s.total_spend for s in supplier_spends)

    # E-2: PR→PO variance عبر source_request_id
    variance_rows = (
        db.query(
            PurchaseOrderItem.product_id,
            Product.name.label("product_name"),
            sa_func.sum(PurchaseRequestItem.estimated_unit_cost).label("est_cost"),
            sa_func.sum(PurchaseOrderItem.unit_cost).label("act_cost"),
        )
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
        .join(PurchaseRequest, PurchaseRequest.id == PurchaseOrder.source_request_id)
        .join(
            PurchaseRequestItem,
            (PurchaseRequestItem.request_id == PurchaseRequest.id) &
            (PurchaseRequestItem.product_id == PurchaseOrderItem.product_id),
        )
        .join(Product, Product.id == PurchaseOrderItem.product_id)
        .filter(
            PurchaseOrder.branch_id == branch_id,
            PurchaseOrder.status.in_(["received", "partial"]),
            PurchaseOrder.ordered_at >= date_from,
            PurchaseOrder.ordered_at <= date_to,
            PurchaseOrder.source_request_id.isnot(None),
        )
        .group_by(PurchaseOrderItem.product_id, Product.name)
        .all()
    )

    variance_lines = [
        PRPOVarianceLine(
            product_id=r.product_id,
            product_name=r.product_name,
            estimated_cost=Decimal(str(r.est_cost or 0)),
            actual_cost=Decimal(str(r.act_cost or 0)),
            variance_amount=Decimal("0"),
            variance_pct=None,
        )
        for r in variance_rows
    ]
    variance_lines = compute_pr_po_variance(variance_lines)

    return ProcurementAnalyticsResponse(
        period_from=date_from,
        period_to=date_to,
        total_spend=total_spend,
        suppliers=[
            SupplierSpendRow(
                supplier_id=s.supplier_id,
                supplier_name=s.supplier_name,
                total_spend=s.total_spend,
                spend_pct=s.spend_pct,
                order_count=order_counts.get(s.supplier_id, 0),
                concentration_flag=s.concentration_flag,
            )
            for s in supplier_spends
        ],
        pr_po_variance=[
            PRPOVarianceRow(
                product_id=v.product_id,
                product_name=v.product_name,
                estimated_cost=v.estimated_cost,
                actual_cost=v.actual_cost,
                variance_amount=v.variance_amount,
                variance_pct=v.variance_pct,
            )
            for v in variance_lines
        ],
        computed_at=datetime.utcnow(),
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 7 — Shift Monitoring
# ══════════════════════════════════════════════════════════════════════

def get_shift_monitor(db: Session, branch_id: int) -> ShiftMonitorResponse:
    """
    F-1 + F-2 + F-3: مراقبة الورديات — من يعمل الآن + cash movements.

    المالك يقرأ فقط — لا approve/close/dispute من هذه الواجهة.
    مصدر: finance.services.build_active_shifts_response + list_cash_movements.
    اسم الكاشير موجود فقط في سياق مراقبة الوردية (Decision 0004 §Isolation item 7).
    """
    from app.modules.finance.services import (  # noqa: PLC0415
        build_active_shifts_response,
        list_cash_movements,
    )
    from app.modules.finance.models import CashierShift  # noqa: PLC0415
    from app.core.kernel.models.user import User  # noqa: PLC0415

    active_resp = build_active_shifts_response(db, branch_id)

    # نجلب أسماء performed_by لحركات الكاش — batch
    shift_items: list[ShiftMonitorItem] = []

    for s in active_resp.shifts:
        # حركات الكاش لهذه الوردية
        try:
            movements_raw = list_cash_movements(db, s.shift_id)
        except ValueError:
            movements_raw = []

        # نجلب أسماء performed_by بـ batch
        performer_ids = list({m.performed_by for m in movements_raw})
        performer_names: dict[int, str] = {}
        if performer_ids:
            users = db.query(User).filter(User.id.in_(performer_ids)).all()
            performer_names = {u.id: (u.full_name or f"#{u.id}") for u in users}

        cash_movements = [
            CashMovementItem(
                id=m.id,
                movement_type=m.movement_type,
                amount=m.amount,
                direction=getattr(m, "direction", None),
                reason=m.reason or "",
                performed_by_name=performer_names.get(m.performed_by, f"#{m.performed_by}"),
                created_at=m.created_at,
            )
            for m in movements_raw
        ]

        # تقييم الوردية — مفتوحة → variance=None → tier=normal
        variance_result = score_shift_variance(
            shift_id=s.shift_id,
            cashier_id=s.cashier_id,
            cashier_name=s.cashier_name,
            variance=None,   # open shift — no counted_cash yet
            is_closed=False,
        )

        shift_items.append(ShiftMonitorItem(
            shift_id=s.shift_id,
            cashier_id=s.cashier_id,
            cashier_name=s.cashier_name,
            opened_at=s.opened_at,
            opening_float=s.opening_float,
            total_sales=s.total_sales,
            total_cash=s.total_cash,
            expected_cash=s.expected_cash,
            invoice_count=s.invoice_count,
            variance=None,
            is_closed=False,
            cash_movements=cash_movements,
            variance_tier=variance_result.tier,
        ))

    return ShiftMonitorResponse(
        branch_id=branch_id,
        open_count=len(shift_items),
        shifts=shift_items,
        computed_at=datetime.utcnow(),
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 7 — Exceptions Engine
# ══════════════════════════════════════════════════════════════════════

def get_exceptions(db: Session, branch_id: int) -> ExceptionsResponse:
    """
    G-1 + G-2: قائمة استثناءات مرتّبة بالخطورة.

    مصادر:
    1. fraud_tasks.find_fraud_signals → critical tier
    2. shift variance (مغلقة) → critical/attention
    3. expense variance flags (من get_expense_analytics) → attention
    4. B2B overdue → attention
    5. Supplier concentration → watch
    6. Long open shifts (>12h) → watch

    الاستثناءات الفعلية (realized) تأتي من بيانات حقيقية.
    لا تكرار لمنطق fraud_tasks — نستدعيه مباشرة.
    """
    from app.tasks.fraud_tasks import find_fraud_signals  # noqa: PLC0415
    from app.modules.finance.models import CashierShift   # noqa: PLC0415
    from app.modules.beach.models import B2BContract      # noqa: PLC0415
    from app.core.config import get_settings              # noqa: PLC0415
    from app.core.kernel.models.user import User          # noqa: PLC0415

    cfg = get_settings()
    exceptions: list[OwnerException] = []

    # ── 1. Fraud signals ────────────────────────────────────────────────
    try:
        fraud_signals = find_fraud_signals(
            db,
            now=datetime.utcnow(),
            refund_threshold=cfg.FRAUD_REFUND_COUNT_THRESHOLD,
            refund_window_minutes=cfg.FRAUD_REFUND_WINDOW_MINUTES,
            void_threshold=cfg.FRAUD_VOID_COUNT_THRESHOLD,
            void_window_minutes=cfg.FRAUD_VOID_WINDOW_MINUTES,
            discount_threshold=cfg.FRAUD_DISCOUNT_COUNT_THRESHOLD,
            discount_window_minutes=cfg.FRAUD_DISCOUNT_WINDOW_MINUTES,
            drawer_open_threshold=cfg.FRAUD_DRAWER_OPEN_COUNT_THRESHOLD,
            drawer_open_window_minutes=cfg.FRAUD_DRAWER_OPEN_WINDOW_MINUTES,
        )
        exceptions.extend(build_fraud_exceptions(fraud_signals))
    except Exception:
        pass  # لو فشل fetch الـ fraud signals — لا نوقف كل القائمة

    # ── 2. Shift variance (closed shifts — آخر 24 ساعة) ────────────────
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    since_24h = datetime.utcnow() - timedelta(hours=24)
    closed_shifts = (
        db.query(CashierShift)
        .filter(
            CashierShift.branch_id == branch_id,
            CashierShift.status == "closed",
            CashierShift.closed_at >= since_24h,
            CashierShift.variance.isnot(None),
        )
        .all()
    )

    cashier_ids = [s.cashier_id for s in closed_shifts]
    cashier_names_map: dict[int, str] = {}
    if cashier_ids:
        users = db.query(User).filter(User.id.in_(cashier_ids)).all()
        cashier_names_map = {u.id: (u.full_name or f"#{u.id}") for u in users}

    variance_results = [
        score_shift_variance(
            shift_id=s.id,
            cashier_id=s.cashier_id,
            cashier_name=cashier_names_map.get(s.cashier_id, f"#{s.cashier_id}"),
            variance=s.variance,
            is_closed=True,
        )
        for s in closed_shifts
    ]
    exceptions.extend(build_shift_variance_exceptions(variance_results))

    # ── 3. B2B overdue contracts → attention ──────────────────────────
    overdue_contracts = (
        db.query(B2BContract)
        .filter(
            B2BContract.branch_id == branch_id,
            B2BContract.is_active.is_(True),
            B2BContract.is_overdue.is_(True),
        )
        .all()
    )
    for c in overdue_contracts:
        exceptions.append(OwnerException(
            exception_id=f"b2b_overdue:{c.id}",
            tier="attention",
            category="b2b_overdue",
            title=f"ذمة متأخرة — {c.hotel_name}",
            detail=f"عقد B2B متأخر السداد منذ {c.last_settled_at or 'غير محدد'}",
            entity_id=c.id,
            entity_name=c.hotel_name,
            impact=Decimal("0"),
            confidence=Decimal("1.0"),
            status="realized",
            source="b2b_contracts",
        ))

    # ── 4. Long open shifts (> 12 ساعة) → watch ────────────────────────
    cutoff_12h = datetime.utcnow() - timedelta(hours=12)
    long_shifts = (
        db.query(CashierShift)
        .filter(
            CashierShift.branch_id == branch_id,
            CashierShift.status == "open",
            CashierShift.opened_at <= cutoff_12h,
        )
        .all()
    )
    for s in long_shifts:
        name = cashier_names_map.get(s.cashier_id)
        if not name:
            user = db.query(User).filter(User.id == s.cashier_id).first()
            name = (user.full_name if user else None) or f"#{s.cashier_id}"
        hours_open = int((datetime.utcnow() - s.opened_at).total_seconds() // 3600)
        exceptions.append(OwnerException(
            exception_id=f"long_shift:{s.id}",
            tier="watch",
            category="long_open_shift",
            title=f"وردية مفتوحة {hours_open} ساعة — {name}",
            detail=f"الوردية مفتوحة منذ {s.opened_at.strftime('%H:%M')} — لم تُغلق بعد",
            entity_id=s.cashier_id,
            entity_name=name,
            impact=Decimal("0"),
            confidence=Decimal("1.0"),
            status="realized",
            source="cashier_shifts",
        ))

    ranked = rank_exceptions(exceptions)

    return ExceptionsResponse(
        critical_count=sum(1 for e in ranked if e.tier == "critical"),
        attention_count=sum(1 for e in ranked if e.tier == "attention"),
        watch_count=sum(1 for e in ranked if e.tier == "watch"),
        exceptions=[
            OwnerExceptionItem(
                exception_id=e.exception_id,
                tier=e.tier,
                category=e.category,
                title=e.title,
                detail=e.detail,
                entity_id=e.entity_id,
                entity_name=e.entity_name,
                impact=e.impact,
                confidence=e.confidence,
                status=e.status,
                source=e.source,
                score=e.score,
            )
            for e in ranked
        ],
        computed_at=datetime.utcnow(),
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 7b — Shift History
# ══════════════════════════════════════════════════════════════════════

def get_shift_history(db: Session, branch_id: int, days: int = 7) -> ShiftHistoryResponse:
    """
    الورديات المغلقة خلال آخر N أيام — للمراجعة التاريخية.
    مصدر: CashierShift (status='closed') + CashMovement.
    المالك يقرأ فقط — لا actions.
    """
    from app.modules.finance.models import CashierShift, CashMovement  # noqa: PLC0415
    from app.core.kernel.models.user import User  # noqa: PLC0415

    cutoff = datetime.utcnow() - timedelta(days=max(1, min(days, 30)))

    raw_shifts = (
        db.query(CashierShift)
        .filter(
            CashierShift.branch_id == branch_id,
            CashierShift.status == "closed",
            CashierShift.closed_at >= cutoff,
        )
        .order_by(CashierShift.closed_at.desc())
        .all()
    )

    # جلب أسماء الكاشيرين دفعة واحدة
    cashier_ids = list({s.cashier_id for s in raw_shifts})
    cashier_names: dict[int, str] = {}
    if cashier_ids:
        rows = db.query(User.id, User.full_name).filter(User.id.in_(cashier_ids)).all()
        cashier_names = {r.id: r.full_name for r in rows}

    shift_ids = [s.id for s in raw_shifts]
    movements_map: dict[int, list[CashMovement]] = {sid: [] for sid in shift_ids}
    if shift_ids:
        mvs = (
            db.query(CashMovement)
            .filter(CashMovement.shift_id.in_(shift_ids))
            .order_by(CashMovement.created_at)
            .all()
        )
        # أسماء المنفذين
        performer_ids = list({m.performed_by for m in mvs})
        performer_names: dict[int, str] = {}
        if performer_ids:
            rows2 = db.query(User.id, User.full_name).filter(User.id.in_(performer_ids)).all()
            performer_names = {r.id: r.full_name for r in rows2}
        for mv in mvs:
            movements_map[mv.shift_id].append(mv)
    else:
        performer_names = {}

    result_shifts: list[ShiftHistoryItem] = []
    for shift in raw_shifts:
        mvs_list = movements_map.get(shift.id, [])
        variance = shift.variance
        if variance is not None:
            from app.resort_os.owner_analytics_engine import score_shift_variance  # noqa: PLC0415
            # باج حقيقي حي اتكشف (2026-08-11، فحص جودة نهائي): الدالة بتاخد
            # 5 args إجباري (shift_id/cashier_id/cashier_name/variance/
            # is_closed)، مش variance بس — /owner/shifts/history كان بيرمي
            # 500 مضمون في أي وردية مغلقة عندها variance (يعني أي بيانات
            # تاريخية حقيقية). كل ورديات الاستعلام هنا closed بالتعريف
            # (فلتر status=='closed' فوق) → is_closed=True دايمًا هنا.
            svr = score_shift_variance(
                shift_id=shift.id,
                cashier_id=shift.cashier_id,
                cashier_name=cashier_names.get(shift.cashier_id, f"كاشير {shift.cashier_id}"),
                variance=variance,
                is_closed=True,
            )
            variance_tier = svr.tier
        else:
            variance_tier = "normal"

        result_shifts.append(ShiftHistoryItem(
            shift_id=shift.id,
            cashier_id=shift.cashier_id,
            cashier_name=cashier_names.get(shift.cashier_id, f"كاشير {shift.cashier_id}"),
            opened_at=shift.opened_at,
            closed_at=shift.closed_at,
            opening_float=shift.opening_float or Decimal("0"),
            total_sales=shift.expected_cash or Decimal("0"),  # expected = total_sales في الورديات المغلقة
            total_cash=shift.counted_cash or Decimal("0"),
            expected_cash=shift.expected_cash or Decimal("0"),
            invoice_count=0,  # لا يُحسب هنا — بيانات تاريخية
            variance=variance,
            variance_tier=variance_tier,
            cash_movements=[
                CashMovementItem(
                    id=mv.id,
                    movement_type=mv.movement_type,
                    amount=mv.amount,
                    direction=mv.direction,
                    reason=mv.reason,
                    performed_by_name=performer_names.get(mv.performed_by, f"مستخدم {mv.performed_by}"),
                    created_at=mv.created_at,
                )
                for mv in mvs_list
            ],
        ))

    return ShiftHistoryResponse(
        branch_id=branch_id,
        days=days,
        shifts=result_shifts,
        computed_at=datetime.utcnow(),
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 7c — HR Summary
# Decision 0004 §7c: full_name/position/department/hire_date/status +
# آخر payroll (net/gross/penalty/advance) + attendance aggregate.
# لا national_id، لا employee_si، لا monthly_tax، لا phone، لا email.
# ══════════════════════════════════════════════════════════════════════

def get_hr_summary(db: Session, branch_id: int) -> HRSummaryResponse:
    """
    قائمة الموظفين مع آخر PayrollLine لكل منهم + حضور الشهر الحالي.
    branch_id من الـ session فقط.
    """
    import calendar  # noqa: PLC0415
    from app.modules.hr.models import Employee, PayrollLine, PayrollRun, AttendanceRecord  # noqa: PLC0415

    today = date.today()
    month_start = today.replace(day=1)
    _, days_in_month = calendar.monthrange(today.year, today.month)
    month_end = today.replace(day=days_in_month)

    employees = (
        db.query(Employee)
        .filter(Employee.branch_id == branch_id)
        .order_by(Employee.full_name)
        .all()
    )

    # آخر PayrollRun approved/closed للفرع
    latest_run = (
        db.query(PayrollRun)
        .filter(
            PayrollRun.branch_id == branch_id,
            PayrollRun.status.in_(["approved", "closed"]),
        )
        .order_by(PayrollRun.period_year.desc(), PayrollRun.period_month.desc())
        .first()
    )

    # PayrollLines للـ run الأخير — keyed by employee_id
    payroll_map: dict[int, PayrollLine] = {}
    if latest_run:
        lines = (
            db.query(PayrollLine)
            .filter(PayrollLine.payroll_run_id == latest_run.id)
            .all()
        )
        payroll_map = {line.employee_id: line for line in lines}

    # Attendance aggregate الشهر الحالي — keyed by employee_id
    att_records = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.branch_id == branch_id,
            AttendanceRecord.record_date >= month_start,
            AttendanceRecord.record_date <= month_end,
        )
        .all()
    )
    att_map: dict[int, list[AttendanceRecord]] = {}
    for rec in att_records:
        att_map.setdefault(rec.employee_id, []).append(rec)

    result_employees: list[HREmployeeRow] = []
    total_net = Decimal("0")
    active_count = 0
    on_leave_count = 0

    for emp in employees:
        if emp.status == "active":
            active_count += 1
        elif emp.status == "on_leave":
            on_leave_count += 1

        # Payroll summary
        payroll_summary: Optional[EmployeePayrollSummary] = None
        if emp.id in payroll_map and latest_run:
            pl = payroll_map[emp.id]
            total_net += pl.net_salary
            payroll_summary = EmployeePayrollSummary(
                payroll_run_id=pl.payroll_run_id,
                period_year=latest_run.period_year,
                period_month=latest_run.period_month,
                gross_salary=pl.gross_salary,
                net_salary=pl.net_salary,
                penalty_deduction=pl.penalty_deduction + pl.late_penalty_deduction,
                advance_deduction=pl.advance_deduction,
                # لا employee_si، لا monthly_tax — Decision 0004 §7c
            )

        # Attendance aggregate
        att_summary: Optional[EmployeeAttendanceSummary] = None
        emp_records = att_map.get(emp.id, [])
        if emp_records:
            present = sum(1 for r in emp_records if r.status == "present")
            absent  = sum(1 for r in emp_records if r.status == "absent")
            late    = sum(1 for r in emp_records if r.status == "late")
            leave   = sum(1 for r in emp_records if r.status == "leave")
            total_days = len(emp_records)
            att_summary = EmployeeAttendanceSummary(
                present_days=present,
                absent_days=absent,
                late_days=late,
                leave_days=leave,
                total_working_days=total_days,
            )

        result_employees.append(HREmployeeRow(
            employee_id=emp.id,
            full_name=emp.full_name,
            position=emp.position,
            department=emp.department,
            hire_date=emp.hire_date,
            status=emp.status,
            payroll=payroll_summary,
            attendance_this_month=att_summary,
            # لا national_id، لا phone، لا email، لا basic_salary
        ))

    return HRSummaryResponse(
        branch_id=branch_id,
        employees=result_employees,
        active_count=active_count,
        on_leave_count=on_leave_count,
        total_net_payroll=total_net,
        period_year=today.year,
        period_month=today.month,
        computed_at=datetime.utcnow(),
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 7d — Discount Analytics
# Decision 0004 §7d: أنواع خصم + يدوي per cashier + مجموعات بالاسم.
# لا هاتف/email/national_id. لا عملاء بدون مجموعة.
# ══════════════════════════════════════════════════════════════════════

def get_discount_analytics(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
) -> DiscountAnalyticsResponse:
    """
    تحليل الخصومات: أنواع + يدوي per cashier + مجموعات بالاسم.
    مصدر: DiningOrder + CustomerGroup + Customer (الاسم فقط).
    """
    from sqlalchemy import func, and_  # noqa: PLC0415
    from app.modules.dining.models import DiningOrder  # noqa: PLC0415
    from app.modules.crm.models import CustomerGroup, Customer  # noqa: PLC0415
    from app.core.kernel.models.user import User  # noqa: PLC0415

    # الطلبات المدفوعة في الفترة
    paid_orders = (
        db.query(DiningOrder)
        .filter(
            DiningOrder.branch_id == branch_id,
            DiningOrder.status == "paid",
            func.date(DiningOrder.created_at) >= date_from,
            func.date(DiningOrder.created_at) <= date_to,
        )
        .all()
    )

    total_revenue = sum(o.subtotal + o.vat_amount + o.service_charge - o.discount_amount
                        for o in paid_orders
                        if hasattr(o, 'subtotal'))
    if not total_revenue:
        # fallback: مجموع الطلبات المدفوعة بدون subtotal
        total_revenue = sum(getattr(o, 'total_amount', Decimal("0")) for o in paid_orders)

    total_discount = sum(o.discount_amount for o in paid_orders)

    # ── أنواع الخصم ──────────────────────────────────────────────────
    # نوع 1: conditional (applied_discount_rule_id != None وليس customer_group)
    # نوع 2: customer_group (discount من CustomerGroup)
    # نوع 3: manual (discount_amount > 0 بدون rule أو group)
    discount_types_data: dict[str, dict] = {
        "conditional":    {"label": "خصم شرطي",       "count": 0, "amount": Decimal("0")},
        "customer_group": {"label": "خصم مجموعة",     "count": 0, "amount": Decimal("0")},
        "manual":         {"label": "خصم يدوي",        "count": 0, "amount": Decimal("0")},
    }

    manual_per_cashier_map: dict[int, dict] = {}

    for order in paid_orders:
        disc = getattr(order, 'discount_amount', Decimal("0"))
        if disc <= 0:
            continue
        rule_id  = getattr(order, 'applied_discount_rule_id', None)
        cust_id  = getattr(order, 'customer_id', None)
        cashier_id = getattr(order, 'cashier_id', None)

        # تحديد نوع الخصم
        if rule_id:
            dtype = "conditional"
        elif cust_id:
            # نتحقق لو العميل ده في مجموعة
            cust = db.query(Customer.customer_group_id).filter(Customer.id == cust_id).first()
            dtype = "customer_group" if (cust and cust.customer_group_id) else "manual"
        else:
            dtype = "manual"

        discount_types_data[dtype]["count"] += 1
        discount_types_data[dtype]["amount"] += disc

        # manual per cashier
        if dtype == "manual" and cashier_id:
            if cashier_id not in manual_per_cashier_map:
                manual_per_cashier_map[cashier_id] = {"count": 0, "amount": Decimal("0")}
            manual_per_cashier_map[cashier_id]["count"] += 1
            manual_per_cashier_map[cashier_id]["amount"] += disc

    discount_pct = (total_discount / total_revenue * 100) if total_revenue > 0 else None

    discount_type_rows = [
        DiscountTypeRow(
            type=k,
            type_label=v["label"],
            order_count=v["count"],
            total_amount=v["amount"],
            pct_of_revenue=(v["amount"] / total_revenue * 100) if total_revenue > 0 else None,
        )
        for k, v in discount_types_data.items()
        if v["count"] > 0
    ]

    # cashier names
    cashier_ids = list(manual_per_cashier_map.keys())
    cashier_names: dict[int, str] = {}
    if cashier_ids:
        rows = db.query(User.id, User.full_name).filter(User.id.in_(cashier_ids)).all()
        cashier_names = {r.id: r.full_name for r in rows}

    manual_cashier_rows = sorted(
        [
            ManualDiscountPerCashier(
                cashier_id=cid,
                cashier_name=cashier_names.get(cid, f"كاشير {cid}"),
                order_count=v["count"],
                total_manual_discount=v["amount"],
            )
            for cid, v in manual_per_cashier_map.items()
        ],
        key=lambda x: x.total_manual_discount,
        reverse=True,
    )[:10]  # top 10 فقط

    # ── مجموعات العملاء بالاسم ───────────────────────────────────────
    # Decision 0004 §7d: الاسم فقط — لا هاتف/email/national_id
    # لا عملاء بدون مجموعة
    groups = (
        db.query(CustomerGroup)
        .filter(
            CustomerGroup.branch_id == branch_id,
            CustomerGroup.is_active == True,
        )
        .all()
    )

    # العملاء الذين لهم طلبات في الفترة
    customer_ids_with_orders = {
        getattr(o, 'customer_id', None)
        for o in paid_orders
        if getattr(o, 'customer_id', None)
    }

    group_rows: list[CustomerGroupDiscountRow] = []
    for group in groups:
        # أعضاء المجموعة
        members = (
            db.query(Customer.id, Customer.full_name)
            .filter(
                Customer.customer_group_id == group.id,
                Customer.is_active == True,
            )
            .all()
        )
        member_ids = {m.id for m in members}
        active_member_ids = member_ids & customer_ids_with_orders

        if not active_member_ids:
            continue  # مجموعة بدون أي نشاط في الفترة — لا تُعرض

        # تجميع مبيعات كل عضو
        member_sales: dict[int, dict] = {}
        for order in paid_orders:
            cid = getattr(order, 'customer_id', None)
            if cid not in active_member_ids:
                continue
            if cid not in member_sales:
                member_sales[cid] = {"invoices": 0, "sales": Decimal("0")}
            member_sales[cid]["invoices"] += 1
            member_sales[cid]["sales"] += getattr(order, 'total_amount',
                order.subtotal + order.vat_amount + order.service_charge - order.discount_amount
                if hasattr(order, 'subtotal') else Decimal("0"))

        member_name_map = {m.id: m.full_name for m in members}
        member_rows = [
            CustomerGroupMember(
                customer_id=cid,
                full_name=member_name_map.get(cid, f"عميل {cid}"),
                invoice_count=data["invoices"],
                total_sales=data["sales"],
            )
            for cid, data in sorted(member_sales.items(), key=lambda x: x[1]["sales"], reverse=True)
        ]

        group_rows.append(CustomerGroupDiscountRow(
            group_id=group.id,
            group_name=group.name_ar or group.name,
            discount_pct=group.discount_percentage,
            member_count=len(members),
            total_invoices=sum(d["invoices"] for d in member_sales.values()),
            total_sales_after_discount=sum(d["sales"] for d in member_sales.values()),
            members=member_rows,
        ))

    return DiscountAnalyticsResponse(
        period_from=date_from.isoformat(),
        period_to=date_to.isoformat(),
        total_revenue=total_revenue,
        total_discount=total_discount,
        discount_pct_of_revenue=discount_pct,
        discount_types=discount_type_rows,
        manual_per_cashier=manual_cashier_rows,
        customer_groups=sorted(group_rows, key=lambda x: x.total_sales_after_discount, reverse=True),
        computed_at=datetime.utcnow(),
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 8 — تفاصيل التفاصيل (Universal Drill-Down)
# ══════════════════════════════════════════════════════════════════════
# نفس مصدر البيانات المستخدم في التجميع أعلاه بالظبط، بس السجلات الخام
# بدل الإجمالي. صفر منطق مالي جديد.

def get_dining_item_detail(
    db: Session, branch_id: int, item_id: int, date_from: date, date_to: date,
) -> DiningItemDetailResponse:
    """كل الطلبات اللي فيها صنف مطعم/كافيه معيّن — نفس فلتر get_sales_
    performance بالظبط (paid orders، غير ملغاة) بس على مستوى الطلب لا التجميع."""
    from app.modules.dining.models import DiningOrder, DiningOrderItem, Outlet  # noqa: PLC0415

    rows = (
        db.query(DiningOrderItem, DiningOrder, Outlet.name.label("outlet_name"))
        .join(DiningOrder, DiningOrder.id == DiningOrderItem.order_id)
        .join(Outlet, Outlet.id == DiningOrder.outlet_id)
        .filter(
            DiningOrder.branch_id == branch_id,
            DiningOrder.status == "paid",
            DiningOrderItem.item_id == item_id,
            DiningOrderItem.status != "cancelled",
            DiningOrder.created_at >= datetime.combine(date_from, datetime.min.time()),
            DiningOrder.created_at <= datetime.combine(date_to, datetime.max.time()),
        )
        .order_by(DiningOrder.created_at.desc())
        .all()
    )

    item_name = rows[0][0].name if rows else ""
    transactions = [
        DiningItemTransaction(
            order_id=item.order_id,
            order_number=order.order_number,
            outlet_name=outlet_name,
            order_type=order.order_type,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.unit_price * item.quantity,
            status=order.status,
            ordered_at=order.created_at,
        )
        for item, order, outlet_name in rows
    ]

    return DiningItemDetailResponse(
        item_id=item_id,
        item_name=item_name,
        period_from=date_from,
        period_to=date_to,
        transactions=transactions,
        total_quantity=sum(t.quantity for t in transactions),
        total_revenue=sum(t.line_total for t in transactions),
        computed_at=datetime.utcnow(),
    )


def get_beach_type_detail(
    db: Session, branch_id: int, tx_type: str, date_from: date, date_to: date,
) -> BeachTypeDetailResponse:
    """كل معاملات نوع تذكرة شاطئ معيّن — نفس فلتر get_beach_performance."""
    from app.modules.beach.models import BeachTransaction  # noqa: PLC0415
    from app.core.kernel.models.user import User  # noqa: PLC0415

    rows = (
        db.query(BeachTransaction)
        .filter(
            BeachTransaction.branch_id == branch_id,
            BeachTransaction.voided_at.is_(None),
            BeachTransaction.tx_type == tx_type,
            BeachTransaction.tx_date >= date_from,
            BeachTransaction.tx_date <= date_to,
        )
        .order_by(BeachTransaction.tx_date.desc(), BeachTransaction.id.desc())
        .all()
    )

    cashier_ids = {r.cashier_id for r in rows if r.cashier_id}
    cashier_names: dict[int, str] = {}
    if cashier_ids:
        users = db.query(User).filter(User.id.in_(cashier_ids)).all()
        cashier_names = {u.id: (u.full_name or f"#{u.id}") for u in users}

    transactions = [
        BeachTypeTransaction(
            transaction_id=r.id,
            tx_date=r.tx_date,
            guest_name=None,  # لا بيانات ضيف شخصية في شاشة الأونر — نفس قاعدة HR
            unit_price=r.unit_price,
            total_amount=r.total_amount,
            cashier_name=cashier_names.get(r.cashier_id) if r.cashier_id else None,
        )
        for r in rows
    ]

    return BeachTypeDetailResponse(
        tx_type=tx_type,
        period_from=date_from,
        period_to=date_to,
        transactions=transactions,
        total_count=len(transactions),
        total_revenue=sum(t.total_amount for t in transactions),
        computed_at=datetime.utcnow(),
    )


def get_expense_detail(
    db: Session, branch_id: int, account_code: str, date_from: date, date_to: date,
) -> ExpenseDetailResponse:
    """كل قيود اليومية (سطور المدين) داخل حساب مصروف معيّن — نفس فترة
    get_expense_analytics بس سطور خام بدل إجمالي الحساب."""
    from app.modules.finance.models import Account, JournalEntry, JournalLine  # noqa: PLC0415

    account = db.query(Account).filter(
        Account.branch_id == branch_id, Account.code == account_code,
    ).first()
    if not account:
        return ExpenseDetailResponse(
            account_code=account_code, account_name=account_code,
            period_from=date_from, period_to=date_to, lines=[],
            total_amount=Decimal("0"), computed_at=datetime.utcnow(),
        )

    rows = (
        db.query(JournalLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(
            JournalLine.account_id == account.id,
            JournalEntry.branch_id == branch_id,
            JournalEntry.entry_date >= date_from,
            JournalEntry.entry_date <= date_to,
            JournalLine.debit > 0,
        )
        .order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
        .all()
    )

    lines = [
        ExpenseJournalLine(
            entry_id=entry.id,
            entry_date=entry.entry_date,
            reference=entry.reference,
            description=line.description or entry.description,
            amount=line.debit,
            source=entry.source,
            cost_center=None,
        )
        for line, entry in rows
    ]

    return ExpenseDetailResponse(
        account_code=account_code,
        account_name=account.name,
        period_from=date_from,
        period_to=date_to,
        lines=lines,
        total_amount=sum(l.amount for l in lines),
        computed_at=datetime.utcnow(),
    )


def get_supplier_detail(
    db: Session, branch_id: int, supplier_id: int, date_from: date, date_to: date,
) -> SupplierDetailResponse:
    """كل أوامر الشراء المستلمة لمورد معيّن — نفس فلتر get_procurement_analytics."""
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.inventory.models import PurchaseOrder, PurchaseOrderItem, Supplier  # noqa: PLC0415

    supplier = db.query(Supplier).filter(
        Supplier.id == supplier_id, Supplier.branch_id == branch_id,
    ).first()

    rows = (
        db.query(
            PurchaseOrder,
            sa_func.count(PurchaseOrderItem.id).label("item_count"),
        )
        .outerjoin(PurchaseOrderItem, PurchaseOrderItem.purchase_order_id == PurchaseOrder.id)
        .filter(
            PurchaseOrder.branch_id == branch_id,
            PurchaseOrder.supplier_id == supplier_id,
            PurchaseOrder.status.in_(["received", "partial"]),
            PurchaseOrder.ordered_at >= date_from,
            PurchaseOrder.ordered_at <= date_to,
        )
        .group_by(PurchaseOrder.id)
        .order_by(PurchaseOrder.ordered_at.desc())
        .all()
    )

    orders = [
        SupplierPurchaseOrder(
            po_id=po.id,
            po_number=po.order_number,
            status=po.status,
            ordered_at=po.ordered_at,
            received_at=po.received_at,
            item_count=int(item_count or 0),
            total_amount=po.total_amount,
        )
        for po, item_count in rows
    ]

    return SupplierDetailResponse(
        supplier_id=supplier_id,
        supplier_name=(supplier.name if supplier else "غير محدد"),
        period_from=date_from,
        period_to=date_to,
        orders=orders,
        total_amount=sum(o.total_amount for o in orders),
        computed_at=datetime.utcnow(),
    )


def get_product_detail(
    db: Session, branch_id: int, product_id: int, date_from: date, date_to: date,
) -> ProductDetailResponse:
    """حركات مخزون منتج معيّن (شراء/استهلاك/تعديل/تحويل) + الرصيد الحالي."""
    from app.modules.inventory.models import Product, StockMovement, Warehouse  # noqa: PLC0415

    product = db.query(Product).filter(
        Product.id == product_id, Product.branch_id == branch_id,
    ).first()
    if not product:
        return ProductDetailResponse(
            product_id=product_id, product_name="غير موجود", unit="",
            current_stock=Decimal("0"), cost_price=Decimal("0"),
            period_from=date_from, period_to=date_to, movements=[],
            total_in=Decimal("0"), total_out=Decimal("0"), computed_at=datetime.utcnow(),
        )

    rows = (
        db.query(StockMovement, Warehouse.name.label("warehouse_name"))
        .join(Warehouse, Warehouse.id == StockMovement.warehouse_id)
        .filter(
            StockMovement.branch_id == branch_id,
            StockMovement.product_id == product_id,
            StockMovement.moved_at >= datetime.combine(date_from, datetime.min.time()),
            StockMovement.moved_at <= datetime.combine(date_to, datetime.max.time()),
        )
        .order_by(StockMovement.moved_at.desc())
        .all()
    )

    movements = [
        ProductMovement(
            movement_id=m.id,
            movement_type=m.movement_type,
            quantity=m.quantity,
            unit_cost=m.unit_cost,
            warehouse_name=wh_name,
            moved_at=m.moved_at,
            notes=m.notes,
        )
        for m, wh_name in rows
    ]

    return ProductDetailResponse(
        product_id=product_id,
        product_name=product.name,
        unit=product.unit,
        current_stock=product.current_stock,
        cost_price=product.cost_price,
        period_from=date_from,
        period_to=date_to,
        movements=movements,
        total_in=sum((m.quantity for m in movements if m.quantity > 0), Decimal("0")),
        total_out=sum((-m.quantity for m in movements if m.quantity < 0), Decimal("0")),
        computed_at=datetime.utcnow(),
    )


def search_everything(db: Session, branch_id: int, query: str, limit: int = 15) -> OwnerSearchResponse:
    """بحث عام بالاسم عبر المنتجات/الموردين/حسابات المصروف/الموظفين —
    كل نوع بيرجع أعلى النتائج تطابقًا بالاسم بس (بدون بيانات مالية إضافية،
    الفرونت إند بيفتح الـdetail المناسب لما المستخدم يدوس على نتيجة)."""
    from app.modules.inventory.models import Product, Supplier  # noqa: PLC0415
    from app.modules.finance.models import Account  # noqa: PLC0415
    from app.modules.hr.models import Employee  # noqa: PLC0415
    from app.modules.dining.models import DiningItem  # noqa: PLC0415

    q = f"%{query.strip()}%"
    results: list[SearchResultItem] = []
    if not query.strip():
        return OwnerSearchResponse(query=query, results=[], computed_at=datetime.utcnow())

    dining_items = (
        db.query(DiningItem)
        .filter(DiningItem.branch_id == branch_id, DiningItem.name.ilike(q))
        .limit(limit)
        .all()
    )
    results += [
        SearchResultItem(
            entity_type="dining_item", entity_id=i.id, title=i.name,
            subtitle="صنف مطعم/كافيه",
        )
        for i in dining_items
    ]

    products = (
        db.query(Product)
        .filter(Product.branch_id == branch_id, Product.name.ilike(q))
        .limit(limit)
        .all()
    )
    results += [
        SearchResultItem(
            entity_type="product", entity_id=p.id, title=p.name,
            subtitle=f"مخزون — {p.sku}",
        )
        for p in products
    ]

    suppliers = (
        db.query(Supplier)
        .filter(Supplier.branch_id == branch_id, Supplier.name.ilike(q))
        .limit(limit)
        .all()
    )
    results += [
        SearchResultItem(
            entity_type="supplier", entity_id=s.id, title=s.name,
            subtitle="مورد",
        )
        for s in suppliers
    ]

    accounts = (
        db.query(Account)
        .filter(
            Account.branch_id == branch_id,
            Account.account_type == "expense",
            Account.name.ilike(q),
        )
        .limit(limit)
        .all()
    )
    results += [
        SearchResultItem(
            entity_type="expense_account", entity_id=a.id, title=a.name,
            subtitle=f"حساب مصروف — {a.code}", value_label=a.code,
        )
        for a in accounts
    ]

    employees = (
        db.query(Employee)
        .filter(Employee.branch_id == branch_id, Employee.full_name.ilike(q))
        .limit(limit)
        .all()
    )
    results += [
        SearchResultItem(
            entity_type="employee", entity_id=e.id, title=e.full_name,
            subtitle=e.position,
        )
        for e in employees
    ]

    return OwnerSearchResponse(query=query, results=results, computed_at=datetime.utcnow())
