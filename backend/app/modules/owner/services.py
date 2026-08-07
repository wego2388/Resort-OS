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
    OccupancyNow,
    OwnerNowResponse,
    OwnerPerformanceResponse,
    OwnerWatchlistCreate,
    PeriodComparison,
    PeriodMeta,
    PeriodSnapshot,
    TimeshareReceivableItem,
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
    day_comparison = _build_period_comparison(snap_today, snap_yesterday)

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
    week_comparison = _build_period_comparison(snap_this_week, snap_prior_week)

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
    month_comparison = _build_period_comparison(snap_this_month, snap_prior_month)

    return OwnerPerformanceResponse(
        today_vs_yesterday=day_comparison,
        week_vs_prior_week=week_comparison,
        month_vs_prior_month=month_comparison,
        computed_at=datetime.utcnow(),
    )
