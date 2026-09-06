"""
app/modules/owner/_services/_helpers.py
Extracted from app/modules/owner/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.modules.owner.schemas import (
    B2BReceivableItem,
    BeachCapacityToday,
    OccupancyNow,
    PerformanceBreakdown,
    PeriodComparison,
    PeriodSnapshot,
    TimeshareReceivableItem,
)
from app.resort_os.timezone_utils import business_today, local_date_to_utc_range


# Phase 3 — داخلي: helpers
# ══════════════════════════════════════════════════════════════════════

def _cairo_today() -> date:
    """تاريخ اليوم بتوقيت القاهرة — المصدر الوحيد لـ 'اليوم' في كل owner services."""
    return business_today(get_settings().TIMEZONE)


def _utc_date_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """Cairo-local inclusive date range converted to stored UTC-naive bounds."""
    timezone_name = get_settings().TIMEZONE
    range_start, _ = local_date_to_utc_range(date_from, timezone_name)
    _, range_end = local_date_to_utc_range(date_to, timezone_name)
    return range_start, range_end

def _pagination_meta(page: int, size: int, total_items: int) -> dict[str, int]:
    """Return stable pagination metadata without losing full-result totals."""
    return {
        "page": page, "size": size, "total_items": total_items,
        "total_pages": (total_items + size - 1) // size if total_items else 0,
    }



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

    2026-08-20: الرصيد بقى مجموع B2BContractMonth.amount (الرسم الشهري
    الثابت المُرحَّل) بعد last_settled_at، بدل B2BContractDay.total_amount
    القديمة — راجع beach.crud.get_b2b_outstanding_balance (نفس الدالة اللي
    beach.services بتستخدمها، مش تكرار منطق منفصل هنا). لا يحتوي الـ
    response على اسم ضيف أو هاتف (Decision 0004 §Isolation model item 7 —
    B2B per hotel/contract only, never per named guest).
    """
    from app.modules.beach import crud as beach_crud  # noqa: PLC0415
    from app.modules.beach.models import B2BContract  # noqa: PLC0415

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
        outstanding = beach_crud.get_b2b_outstanding_balance(db, contract.id, contract.last_settled_at)
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
    """A-5: ذمم ملكية جزئية — أقساط unpaid/overdue بـ due_date <= اليوم.

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
