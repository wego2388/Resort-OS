"""app/modules/analytics/api/router.py
Analytics Module — لوحة التحليلات الشاملة (Read-Only، لا جداول خاصة)
يقرأ من كل الـ modules ويُجمّع الأرقام.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import asyncio
import json

from fastapi import APIRouter, Body, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import DbDep, get_current_active_user, get_manager_user, get_websocket_user
from app.core.database import SessionLocal
from app.modules.analytics import services
from app.modules.analytics.schemas import UtilityReadingCreate, UtilityReadingRead
from app.resort_os.timezone_utils import business_today, local_date_to_utc_range

router = APIRouter(tags=["analytics"])


def _today() -> date:
    """"النهاردة" بتوقيت المنتجع (settings.TIMEZONE)، مش توقيت نظام تشغيل
    السيرفر — راجع app/resort_os/timezone_utils.py. أي endpoint هنا محتاج
    قيمة افتراضية لـ "اليوم" (تقرير، لقطة، WebSocket) لازم يستخدم الدالة دي
    مش date.today() مباشرة."""
    return business_today(settings.TIMEZONE)


def _safe_query(func, *args, **kwargs):
    """يُشغّل query ويُرجع None إذا فشل الـ import (module لم يُبنَ)."""
    try:
        return func(*args, **kwargs)
    except (ImportError, Exception):
        return None


# ── Revenue Dashboard ─────────────────────────────────────────────────

@router.get("/analytics/revenue")
def revenue_summary(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
    date_from: date = Query(default_factory=lambda: _today() - timedelta(days=30)),
    date_to: date = Query(default_factory=_today),
):
    # created_at (restaurant/cafe) مخزّن UTC — لازم نحوّل مدى التاريخ المحلي
    # (settings.TIMEZONE) لـ UTC، وإلا الفلترة بتفشل لمدة ~3 ساعات كل يوم.
    range_start, _ = local_date_to_utc_range(date_from, settings.TIMEZONE)
    _, range_end = local_date_to_utc_range(date_to, settings.TIMEZONE)
    result: dict = {
        "period": {"from": str(date_from), "to": str(date_to)},
        "branch_id": branch_id,
        "restaurant": None,
        "cafe":       None,
        "pms":        None,
        "beach":      None,
        "leasing":    None,
        "timeshare":  None,
        "total":      Decimal("0"),
    }

    # Restaurant revenue
    def _restaurant(db: Session):
        from app.modules.restaurant.models import Order  # noqa: PLC0415
        rows = db.query(Order).filter(
            Order.branch_id == branch_id,
            Order.status == "paid",
            Order.created_at >= range_start,
            Order.created_at <= range_end,
        ).all()
        return {"orders": len(rows), "total": sum(o.total for o in rows)}

    def _cafe(db: Session):
        from app.modules.cafe.models import CafeOrder  # noqa: PLC0415
        rows = db.query(CafeOrder).filter(
            CafeOrder.branch_id == branch_id,
            CafeOrder.status == "paid",
            CafeOrder.created_at >= range_start,
            CafeOrder.created_at <= range_end,
        ).all()
        return {"orders": len(rows), "total": sum(o.total for o in rows)}

    def _pms(db: Session):
        from app.modules.pms.models import Booking  # noqa: PLC0415
        rows = db.query(Booking).filter(
            Booking.branch_id == branch_id,
            Booking.status == "checked_out",
            Booking.check_out >= date_from,
            Booking.check_out <= date_to,
        ).all()
        return {"bookings": len(rows), "total": sum(b.total_rate for b in rows)}

    def _beach(db: Session):
        from app.modules.beach.models import BeachTransaction  # noqa: PLC0415
        rows = db.query(BeachTransaction).filter(
            BeachTransaction.branch_id == branch_id,
            BeachTransaction.voided_at.is_(None),
            BeachTransaction.tx_date >= date_from,
            BeachTransaction.tx_date <= date_to,
        ).all()
        return {"visits": len(rows), "total": sum(r.total_amount + r.vat_amount for r in rows)}

    def _leasing(db: Session):
        from app.modules.leasing.models import LeasePayment  # noqa: PLC0415
        rows = db.query(LeasePayment).filter(
            LeasePayment.paid_at.isnot(None),
            LeasePayment.status == "paid",
            LeasePayment.paid_at >= range_start,
            LeasePayment.paid_at <= range_end,
        ).all()
        return {"payments": len(rows), "total": sum(p.amount for p in rows)}

    def _timeshare(db: Session):
        from app.modules.timeshare.models import TimeshareInstallment  # noqa: PLC0415
        rows = db.query(TimeshareInstallment).filter(
            TimeshareInstallment.paid_at.isnot(None),
            TimeshareInstallment.status == "paid",
            TimeshareInstallment.paid_at >= range_start,
            TimeshareInstallment.paid_at <= range_end,
        ).all()
        return {"payments": len(rows), "total": sum(p.amount for p in rows)}

    result["restaurant"] = _safe_query(_restaurant, db)
    result["cafe"]       = _safe_query(_cafe, db)
    result["pms"]        = _safe_query(_pms, db)
    result["beach"]      = _safe_query(_beach, db)
    result["leasing"]    = _safe_query(_leasing, db)
    result["timeshare"]  = _safe_query(_timeshare, db)

    total = Decimal("0")
    for key in ("restaurant", "cafe", "pms", "beach", "leasing", "timeshare"):
        val = result[key]
        if val and "total" in val:
            total += Decimal(str(val["total"]))
    result["total"] = total

    return result


# ── Occupancy ─────────────────────────────────────────────────────────

@router.get("/analytics/occupancy")
def occupancy_summary(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
    month: Optional[int] = Query(None),
    year:  Optional[int] = Query(None),
):
    today = _today()
    target_month = month or today.month
    target_year  = year or today.year

    result: dict = {"month": target_month, "year": target_year, "pms": None, "beach": None}

    def _pms_occupancy(db: Session):
        from app.modules.pms.models import NightAuditLog  # noqa: PLC0415
        rows = db.query(NightAuditLog).filter(
            NightAuditLog.branch_id == branch_id,
            NightAuditLog.status == "completed",
        ).all()
        month_rows = [r for r in rows if r.audit_date.month == target_month and r.audit_date.year == target_year]
        if not month_rows:
            return None
        avg_occ = sum(r.occupancy_pct for r in month_rows) / len(month_rows)
        return {
            "nights_audited": len(month_rows),
            "avg_occupancy_pct": float(avg_occ),
            "total_room_revenue": sum(r.room_revenue for r in month_rows),
        }

    result["pms"] = _safe_query(_pms_occupancy, db)
    return result


# ── HR Summary ────────────────────────────────────────────────────────

@router.get("/analytics/hr")
def hr_summary(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
):
    def _hr(db: Session):
        from app.modules.hr.models import Employee, PayrollRun  # noqa: PLC0415
        active_employees = db.query(Employee).filter(
            Employee.branch_id == branch_id,
            Employee.status == "active",
        ).count()
        last_payroll = db.query(PayrollRun).filter(
            PayrollRun.branch_id == branch_id,
        ).order_by(PayrollRun.created_at.desc()).first()
        return {
            "active_employees": active_employees,
            "last_payroll": {
                "period": f"{last_payroll.period_year}-{last_payroll.period_month:02d}",
                "status": last_payroll.status,
                "total_net": last_payroll.total_net,
            } if last_payroll else None,
        }

    return _safe_query(_hr, db) or {}


# ── Maintenance KPIs ──────────────────────────────────────────────────

@router.get("/analytics/maintenance")
def maintenance_summary(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
):
    def _maint(db: Session):
        from app.modules.maintenance.models import WorkOrder  # noqa: PLC0415
        open_wos = db.query(WorkOrder).filter(
            WorkOrder.branch_id == branch_id,
            WorkOrder.status.in_(["open", "in_progress"]),
        ).count()
        critical_wos = db.query(WorkOrder).filter(
            WorkOrder.branch_id == branch_id,
            WorkOrder.priority == "critical",
            WorkOrder.status.in_(["open", "in_progress"]),
        ).count()
        return {"open_work_orders": open_wos, "critical_work_orders": critical_wos}

    return _safe_query(_maint, db) or {}


# ── CRM Pipeline ─────────────────────────────────────────────────────

@router.get("/analytics/crm")
def crm_summary(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
):
    def _crm(db: Session):
        from app.modules.crm.models import Opportunity, Customer  # noqa: PLC0415
        from sqlalchemy import func  # noqa: PLC0415

        total_customers = db.query(Customer).filter(
            Customer.branch_id == branch_id, Customer.is_active.is_(True)
        ).count()

        pipeline = db.query(
            Opportunity.stage,
            func.count(Opportunity.id).label("count"),
            func.sum(Opportunity.expected_value).label("value"),
        ).filter(
            Opportunity.branch_id == branch_id,
            Opportunity.stage.notin_(["won", "lost"]),
        ).group_by(Opportunity.stage).all()

        return {
            "total_customers": total_customers,
            "pipeline": [
                {"stage": r.stage, "count": r.count, "value": r.value}
                for r in pipeline
            ],
        }

    return _safe_query(_crm, db) or {}


# ── Inventory Alerts ──────────────────────────────────────────────────

@router.get("/analytics/inventory")
def inventory_alerts(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
):
    def _inv(db: Session):
        from app.modules.inventory.models import Product  # noqa: PLC0415
        low_stock = db.query(Product).filter(
            Product.branch_id == branch_id,
            Product.is_active.is_(True),
            Product.current_stock <= Product.reorder_point,
        ).count()
        out_of_stock = db.query(Product).filter(
            Product.branch_id == branch_id,
            Product.is_active.is_(True),
            Product.current_stock <= 0,
        ).count()
        return {"low_stock_count": low_stock, "out_of_stock_count": out_of_stock}

    return _safe_query(_inv, db) or {}


# ── DailyStats ────────────────────────────────────────────────────────

@router.get("/analytics/daily-stats")
def get_daily_stats(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
    stat_date: date = Query(default_factory=_today),
):
    from app.modules.analytics.models import DailyStats  # noqa: PLC0415
    row = db.query(DailyStats).filter(
        DailyStats.branch_id == branch_id,
        DailyStats.stat_date == stat_date,
    ).first()
    if not row:
        return {"stat_date": str(stat_date), "message": "لا توجد بيانات لهذا اليوم"}
    return {
        "stat_date":          str(row.stat_date),
        "occupancy_pct":      float(row.occupancy_pct),
        "adr":                float(row.adr),
        "revpar":             float(row.revpar),
        "room_revenue":       float(row.room_revenue),
        "beach_visitors":     row.beach_visitors,
        "beach_revenue":      float(row.beach_revenue),
        "restaurant_covers":  row.restaurant_covers,
        "restaurant_revenue": float(row.restaurant_revenue),
        "cafe_revenue":       float(row.cafe_revenue),
        "total_revenue":      float(row.total_revenue),
    }


# ── UtilityReading / Energy KPI ────────────────────────────────────────
# Task B audit: الموديل + الـ migration كانوا موجودين من زمان، بس مفيش أي
# طريقة تسجيل قراءة مرفق في كل النظام — نفس فئة الباج الموثّقة في
# CLAUDE.md § 11.6 (GET /restaurant/menu/categories) و TenantCashLog في leasing.

@router.post("/analytics/utilities", response_model=UtilityReadingRead,
             status_code=status.HTTP_201_CREATED)
def create_utility_reading(data: UtilityReadingCreate, db: DbDep, user=Depends(get_manager_user)):
    return services.record_utility_reading(db, data, recorded_by=user.id)


@router.get("/analytics/utilities", response_model=list[UtilityReadingRead])
def list_utility_readings(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
    utility_type: Optional[str] = Query(None),
    period: Optional[str] = Query(None, description="YYYY-MM"),
):
    return services.list_utility_readings(db, branch_id, utility_type, period)


@router.get("/analytics/energy")
def energy_kpis(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
    period: str = Query(..., description="YYYY-MM"),
):
    """مؤشر الطاقة (تكلفة كيلوواط/نزيل) — من قايمة KPIs الأساسية في السبيك
    اللي مكنش ليها أي endpoint خالص."""
    return services.get_energy_kpis(db, branch_id, period)


@router.get("/analytics/energy/trend")
def energy_trend(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
    end_period: str = Query(default_factory=lambda: business_today(settings.TIMEZONE).strftime("%Y-%m"), description="YYYY-MM"),
    months: int = Query(24, ge=1, le=60),
):
    """اتجاه تكلفة المرافق الشهري + مقارنة سنة بسنة (wagdy.md #18) — 24 شهر
    افتراضيًا (سنة حالية + سابقة) عشان الفرونت إند يقارن من نفس الرد."""
    return services.get_energy_trend(db, branch_id, end_period, months)


@router.get("/analytics/energy/trend/export")
def download_energy_trend_excel(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
    end_period: str = Query(default_factory=lambda: business_today(settings.TIMEZONE).strftime("%Y-%m"), description="YYYY-MM"),
    months: int = Query(24, ge=1, le=60),
):
    """تصدير Excel لاتجاه تكلفة المرافق (wagdy.md #18)."""
    xlsx = services.generate_energy_trend_excel(db, branch_id, end_period, months)
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=energy-trend.xlsx"},
    )


def _compute_live_kpis(branch_id: int) -> dict:
    """يحسب KPIs آنية — تُستدعى من WebSocket loop."""
    with SessionLocal() as db:
        today = _today()
        result: dict = {"branch_id": branch_id, "as_of": str(today)}

        try:
            from app.modules.pms.models import Room  # noqa: PLC0415
            total_rooms = db.query(Room).filter(Room.branch_id == branch_id).count()
            occupied    = db.query(Room).filter(
                Room.branch_id == branch_id,
                Room.status == "occupied",
            ).count()
            result["pms"] = {
                "total_rooms": total_rooms,
                "occupied":    occupied,
                "occupancy_pct": round(100 * occupied / total_rooms, 1) if total_rooms else 0,
            }
        except Exception:
            result["pms"] = None

        try:
            from app.modules.beach.models import BeachInventory  # noqa: PLC0415
            # ⚠️ باج حقيقي (اتصلح هنا): كان بيقرأ BeachInventory.inv_date —
            # عمود مش موجود خالص في الموديل الحقيقي (الاسم الصح
            # inventory_date). كان بيرمي AttributeError عند بناء الـ filter،
            # وده كان بيتبلع بصمت بـ except Exception تحت — يعني قسم الشاطئ
            # في WebSocket الـ KPIs الحية كان بيرجع null دايمًا لكل فرع، بغض
            # النظر عن أي نشاط شاطئ حقيقي (تذاكر مباعة، فوط مستخدمة...).
            inv = db.query(BeachInventory).filter(
                BeachInventory.branch_id == branch_id,
                BeachInventory.inventory_date == today,
            ).first()
            result["beach"] = {
                "capacity_used":  int(inv.capacity_used)    if inv else 0,
                "capacity_max":   int(inv.capacity_max)     if inv else 0,
                "towels_used":    int(inv.towels_used)      if inv else 0,
            }
        except Exception:
            result["beach"] = None

        try:
            from app.modules.maintenance.models import WorkOrder  # noqa: PLC0415
            open_wos = db.query(WorkOrder).filter(
                WorkOrder.branch_id == branch_id,
                WorkOrder.status.in_(["open", "in_progress"]),
            ).count()
            result["maintenance"] = {"open_work_orders": open_wos}
        except Exception:
            result["maintenance"] = None

        return result


@router.websocket("/ws/analytics/kpis/{branch_id}")
async def kpi_websocket(websocket: WebSocket, branch_id: int, db: DbDep):
    """WebSocket يُرسل KPIs كل 10 ثوانٍ للـ frontend. بيانات مالية حسّاسة —
    محتاج ?token= JWT صالح بمستوى مدير+ (نفس مستوى /analytics/reviews
    وباقي endpoints الموديول)."""
    if not await get_websocket_user(websocket, db, min_level=60):
        return
    await websocket.accept()
    try:
        while True:
            data = await asyncio.get_event_loop().run_in_executor(
                None, _compute_live_kpis, branch_id
            )
            await websocket.send_text(json.dumps(data, default=str))
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        pass
    except Exception:
        await websocket.close()


# ── Guest Reviews ─────────────────────────────────────────────────────

@router.get("/analytics/reviews")
def list_reviews(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
    source: Optional[str] = Query(None),
    booking_id: Optional[int] = Query(None),
    timeshare_visit_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    from app.modules.analytics.models import GuestReview  # noqa: PLC0415
    q = db.query(GuestReview).filter(GuestReview.branch_id == branch_id)
    if booking_id or timeshare_visit_id:
        # عرض تقييمات مرجع محدد (بروفايل عميل تايم شير مثلاً) — يشمل الغير
        # منشورة كمان (الفريق الداخلي محتاج يشوف الصورة كاملة، مش بس المنشور
        # للعامة). القائمة العامة (من غير فلتر) لسه بتفلتر is_published فقط.
        if booking_id:
            q = q.filter(GuestReview.booking_id == booking_id)
        if timeshare_visit_id:
            q = q.filter(GuestReview.timeshare_visit_id == timeshare_visit_id)
    else:
        q = q.filter(GuestReview.is_published.is_(True))
    if source:
        q = q.filter(GuestReview.source == source)
    total = q.count()
    items = q.order_by(GuestReview.reviewed_at.desc()).offset((page - 1) * size).limit(size).all()
    avg   = sum(r.overall_rating for r in items) / len(items) if items else 0
    return {
        "total": total,
        "avg_rating": round(avg, 2),
        "items": [
            {
                "id":             r.id,
                "guest_name":     r.guest_name,
                "overall_rating": r.overall_rating,
                "comment":        r.comment,
                "source":         r.source,
                "reviewed_at":    str(r.reviewed_at),
            }
            for r in items
        ],
    }


@router.get("/analytics/reviews/insights")
def review_category_insights(db: DbDep, _=Depends(get_manager_user), branch_id: int = Query(...)):
    """Task B audit: ReviewCategory كان بيتسجّل فعلاً مع كل تقييم (submit_review)
    بس مفيش أي مكان بيقراه أو يجمّعه — السبيك بيطلب 'GSS score + per-category
    insights' صراحة."""
    return services.get_review_category_insights(db, branch_id)


# ── Full Dashboard ────────────────────────────────────────────────────

@router.get("/analytics/dashboard")
def full_dashboard(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
):
    """لوحة القيادة الشاملة — كل المؤشرات في طلب واحد."""
    today = _today()
    date_from_30 = today - timedelta(days=30)

    def _rev():
        return _safe_query(lambda d: _build_revenue(d, branch_id, date_from_30, today), db)

    def _build_revenue(d, bid, dfrom, dto):
        from app.modules.restaurant.models import Order  # noqa: PLC0415
        from app.modules.cafe.models import CafeOrder    # noqa: PLC0415
        from app.modules.pms.models import Booking       # noqa: PLC0415
        from app.modules.beach.models import BeachTransaction  # noqa: PLC0415
        # ⚠️ باج حقيقي (اتصلح هنا): كان بيقارن created_at (UTC فعليًا) بحدود
        # يوم مبنية بـ datetime.combine ساذج من تاريخ محلي (Africa/Cairo) —
        # نفس الباج اللي اتصلح في /analytics/revenue جنبه بالظبط، لكن هنا في
        # لوحة القيادة الرئيسية (اللي AnalyticsView.vue بيعرضها كـ"إجمالي
        # الإيرادات 30 يوم") فضل من غير ما يتصلح. النتيجة: إيرادات المطعم/
        # الكافيه في نافذة ~3 ساعات كل يوم (منتصف ليل القاهرة → 3 فجرًا) كانت
        # بتتحسب على اليوم الغلط.
        range_start, _ = local_date_to_utc_range(dfrom, settings.TIMEZONE)
        _, range_end = local_date_to_utc_range(dto, settings.TIMEZONE)
        rest = sum(o.total for o in d.query(Order).filter(
            Order.branch_id == bid, Order.status == "paid",
            Order.created_at >= range_start,
            Order.created_at <= range_end,
        ).all())
        cafe = sum(o.total for o in d.query(CafeOrder).filter(
            CafeOrder.branch_id == bid, CafeOrder.status == "paid",
            CafeOrder.created_at >= range_start,
            CafeOrder.created_at <= range_end,
        ).all())
        pms_rev = sum(b.total_rate for b in d.query(Booking).filter(
            Booking.branch_id == bid, Booking.status == "checked_out",
            Booking.check_out >= dfrom, Booking.check_out <= dto,
        ).all())
        beach_rev = sum(r.total_amount + r.vat_amount for r in d.query(BeachTransaction).filter(
            BeachTransaction.branch_id == bid, BeachTransaction.voided_at.is_(None),
            BeachTransaction.tx_date >= dfrom, BeachTransaction.tx_date <= dto,
        ).all())
        # إيرادات الإيجار والتايم شير — paid_at مخزّن UTC، نفس نطاق range_start/end
        try:
            from app.modules.leasing.models import LeasePayment  # noqa: PLC0415
            lease_rev = sum(p.amount for p in d.query(LeasePayment).filter(
                LeasePayment.paid_at.isnot(None), LeasePayment.status == "paid",
                LeasePayment.paid_at >= range_start, LeasePayment.paid_at <= range_end,
            ).all())
        except Exception:
            lease_rev = Decimal("0")
        try:
            from app.modules.timeshare.models import TimeshareInstallment  # noqa: PLC0415
            ts_rev = sum(p.amount for p in d.query(TimeshareInstallment).filter(
                TimeshareInstallment.paid_at.isnot(None), TimeshareInstallment.status == "paid",
                TimeshareInstallment.paid_at >= range_start, TimeshareInstallment.paid_at <= range_end,
            ).all())
        except Exception:
            ts_rev = Decimal("0")
        total = rest + cafe + pms_rev + beach_rev + lease_rev + ts_rev
        return {
            "restaurant": float(rest), "cafe": float(cafe),
            "pms": float(pms_rev), "beach": float(beach_rev),
            "leasing": float(lease_rev), "timeshare": float(ts_rev),
            "total": float(total),
        }

    return {
        "branch_id":   branch_id,
        "as_of":       str(today),
        "revenue_30d": _rev(),
        "hr":          _safe_query(lambda d: _hr_data(d, branch_id), db),
        "maintenance": _safe_query(lambda d: _maint_data(d, branch_id), db),
        "crm":         _safe_query(lambda d: _crm_data(d, branch_id), db),
        "inventory":   _safe_query(lambda d: _inv_data(d, branch_id), db),
        "reviews":     _safe_query(lambda d: _review_avg(d, branch_id), db),
    }


def _hr_data(db, branch_id):
    from app.modules.hr.models import Employee, PayrollRun  # noqa: PLC0415
    emp_count = db.query(Employee).filter(Employee.branch_id == branch_id, Employee.status == "active").count()
    last = db.query(PayrollRun).filter(PayrollRun.branch_id == branch_id).order_by(PayrollRun.created_at.desc()).first()
    return {"active_employees": emp_count, "last_payroll_period": f"{last.period_year}-{last.period_month:02d}" if last else None}


def _maint_data(db, branch_id):
    from app.modules.maintenance.models import WorkOrder  # noqa: PLC0415
    open_wo = db.query(WorkOrder).filter(WorkOrder.branch_id == branch_id, WorkOrder.status.in_(["open", "in_progress"])).count()
    return {"open_work_orders": open_wo}


def _crm_data(db, branch_id):
    from app.modules.crm.models import Customer  # noqa: PLC0415
    return {"total_customers": db.query(Customer).filter(Customer.branch_id == branch_id, Customer.is_active.is_(True)).count()}


def _inv_data(db, branch_id):
    from app.modules.inventory.models import Product  # noqa: PLC0415
    low = db.query(Product).filter(Product.branch_id == branch_id, Product.is_active.is_(True), Product.current_stock <= Product.reorder_point).count()
    return {"low_stock_count": low}


def _review_avg(db, branch_id):
    from app.modules.analytics.models import GuestReview  # noqa: PLC0415
    reviews = db.query(GuestReview).filter(GuestReview.branch_id == branch_id, GuestReview.is_published.is_(True)).all()
    if not reviews:
        return {"count": 0, "avg_rating": None}
    return {"count": len(reviews), "avg_rating": round(sum(r.overall_rating for r in reviews) / len(reviews), 2)}


# ── Survey Token + Review Submission ─────────────────────────────────

@router.post("/analytics/reviews/submit")
async def submit_guest_review(
    db: DbDep,
    token: str = Query(..., description="survey JWT from checkout"),
    data: dict = Body(...),
):
    """يستقبل تقييم الضيف بعد checkout (حجز فندقي) أو بعد زيارة تايم شير —
    يتحقق من JWT أولاً، ويحدِّد نوع المرجع (ref_type) من التوكن نفسه."""
    from app.modules.analytics.services import verify_survey_token, submit_review  # noqa: PLC0415
    payload = verify_survey_token(token)
    ref_id = int(payload["sub"])
    branch_id = payload["branch_id"]
    ref_type = payload.get("ref_type", "booking")  # توكنات قديمة بدون ref_type = حجز فندقي دايمًا

    if ref_type == "timeshare_visit":
        review = submit_review(db, branch_id, booking_id=None, data=data, timeshare_visit_id=ref_id)
    else:
        review = submit_review(db, branch_id, booking_id=ref_id, data=data)
    return {"id": review.id, "overall_rating": review.overall_rating}


@router.get("/analytics/reviews/survey-token/{booking_id}")
async def get_survey_token(
    booking_id: int,
    db: DbDep,
    branch_id: int = Query(...),
    current_user=Depends(get_current_active_user),
):
    """يُولِّد survey token لحجز فندقي — يُستدعى من checkout screen."""
    from app.modules.analytics.services import create_survey_token  # noqa: PLC0415
    token = create_survey_token(branch_id=branch_id, booking_id=booking_id)
    return {"token": token, "expires_in_days": 7}


@router.get("/analytics/reviews/survey-token/timeshare/{visit_id}")
async def get_timeshare_survey_token(
    visit_id: int,
    db: DbDep,
    branch_id: int = Query(...),
    current_user=Depends(get_current_active_user),
):
    """يُولِّد survey token لزيارة تايم شير — نفس شكل استجابة الحجز الفندقي
    بالظبط، endpoint موازٍ مش تعديل على القديم (الحجز الفندقي والتايم شير
    مصدرين مختلفين تمامًا، مش نفس الجدول)."""
    from app.modules.analytics.services import create_survey_token  # noqa: PLC0415
    token = create_survey_token(branch_id=branch_id, timeshare_visit_id=visit_id)
    return {"token": token, "expires_in_days": 7}


@router.post(
    "/analytics/reviews/survey-token/timeshare/{visit_id}/send",
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_timeshare_survey(
    visit_id: int,
    db: DbDep,
    branch_id: int = Query(...),
    current_user=Depends(get_current_active_user),
):
    """يبعت لينك الاستبيان لصاحب زيارة تايم شير فعليًا عبر واتساب (Celery،
    مش synchronous — نفس نمط باقي إشعارات واتساب في المشروع).

    قبل الـ endpoint ده، get_timeshare_survey_token فوق كان بيولّد الـ token
    بس من غير أي طريقة حقيقية توصّله للضيف — يعني الاستبيان (رغم إن الباك
    إند والفرونت إند شغالين بالكامل) كان عمليًا غير قابل للاستخدام."""
    from app.modules.timeshare.models import TimeshareVisit  # noqa: PLC0415
    visit = db.query(TimeshareVisit).filter(
        TimeshareVisit.id == visit_id, TimeshareVisit.branch_id == branch_id,
    ).first()
    if not visit:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الزيارة غير موجودة")

    from app.tasks.timeshare_tasks import send_visit_survey  # noqa: PLC0415
    send_visit_survey.delay(visit_id, branch_id)
    return {"queued": True}
