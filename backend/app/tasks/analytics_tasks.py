"""app/tasks/analytics_tasks.py — DailyStats generation"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.analytics_tasks.generate_daily_stats", bind=True, max_retries=2)
def generate_daily_stats(self, branch_id: int | None = None, stat_date_str: str | None = None):
    """
    يُولِّد لقطة KPI يومية لكل الفروع.
    يُشغَّل كل يوم 01:00 (بعد Night Audit).
    """
    try:
        from app.core.database import SessionLocal          # noqa: PLC0415
        from app.modules.core.models import Branch         # noqa: PLC0415
        from app.core.config import settings                # noqa: PLC0415
        from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

        # "أمس" لازم يتحسب بتوقيت المنتجع (Cairo) مش بتوقيت نظام تشغيل
        # السيرفر — لو السيرفر شغّال UTC (شائع في Docker/VPS)، date.today()
        # كانت بترجع يوم غلط في نافذة الفرق بين التوقيتين (راجع
        # timezone_utils.py وباجات مشابهة اتصلحت في PMS/HR/Timeshare).
        stat_date = (
            date.fromisoformat(stat_date_str)
            if stat_date_str
            else business_today(settings.TIMEZONE) - timedelta(days=1)
        )

        with SessionLocal() as db:
            if branch_id:
                branches = [db.query(Branch).filter(Branch.id == branch_id).first()]
            else:
                branches = db.query(Branch).filter(Branch.is_active.is_(True)).all()

            for branch in filter(None, branches):
                try:
                    _build_stats(db, branch.id, stat_date)
                    logger.info("DailyStats generated: branch=%s date=%s", branch.id, stat_date)
                except Exception as exc:
                    logger.error("DailyStats failed: branch=%s error=%s", branch.id, exc)

    except Exception as exc:
        logger.error("generate_daily_stats task failed: %s", exc)
        raise self.retry(exc=exc, countdown=120)


def _build_stats(db, branch_id: int, stat_date: date) -> None:
    from app.modules.analytics.models import DailyStats  # noqa: PLC0415
    from datetime import datetime as _dt                  # noqa: PLC0415
    from app.core.config import settings                   # noqa: PLC0415
    from app.resort_os.timezone_utils import local_date_to_utc_range  # noqa: PLC0415

    # ⚠️ باج حقيقي (اتصلح هنا): day_start/day_end كانوا بيتبنوا مباشرة من
    # stat_date كأنه يوم UTC (datetime.combine ساذج)، لكن Order.created_at/
    # CafeOrder.created_at متخزّنين UTC فعليًا (Postgres func.now()، DB
    # timezone=UTC) بينما stat_date تاريخ محلي (Africa/Cairo). النتيجة: أي
    # طلب اتعمل بين منتصف ليل القاهرة والساعة 3 فجرًا كان بيتحسب على اليوم
    # الغلط (يوم أمس بدل النهاردة) في كل *DailyStats* اتولّدت من أول ما الكود
    # ده اتكتب — نفس فئة الباج اللي اتصلحت في /analytics/revenue، لكن هنا في
    # الـ Celery job نفسه فضلت من غير ما حد يصلحها.
    day_start, day_end = local_date_to_utc_range(stat_date, settings.TIMEZONE)

    # PMS
    room_revenue    = Decimal("0")
    occupied_rooms  = 0
    total_rooms     = 0
    adr             = Decimal("0")
    revpar          = Decimal("0")
    try:
        from app.modules.pms.models import NightAuditLog, Room  # noqa: PLC0415
        audit = db.query(NightAuditLog).filter(
            NightAuditLog.branch_id == branch_id,
            NightAuditLog.audit_date == stat_date,
            NightAuditLog.status == "completed",
        ).first()
        if audit:
            room_revenue   = audit.room_revenue
            occupied_rooms = audit.occupied_rooms
            total_rooms    = audit.total_rooms
        else:
            total_rooms = db.query(Room).filter(Room.branch_id == branch_id).count()

        if occupied_rooms > 0:
            adr = (room_revenue / occupied_rooms).quantize(Decimal("0.01"))
        if total_rooms > 0:
            revpar = (room_revenue / total_rooms).quantize(Decimal("0.01"))
    except Exception:
        pass

    occupancy_pct = (
        (Decimal(str(occupied_rooms)) / Decimal(str(total_rooms)) * 100).quantize(Decimal("0.01"))
        if total_rooms else Decimal("0")
    )

    # Beach
    # ⚠️ باج حقيقي (اتصلح هنا): كان بيقرأ BeachTransaction.visit_date/
    # t.total_paid — حقلين مش موجودين خالص في الموديل الحقيقي (الأسماء الصح
    # tx_date و total_amount+vat_amount، راجع app/modules/beach/models.py).
    # الاستعلام كان بيرمي AttributeError عند بناء الـ filter نفسه، وده كان
    # بيتبلع بصمت بـ except Exception أدناه — يعني beach_visitors/
    # beach_revenue في DailyStats كانوا صفر ثابت لكل فرع كل يوم من أول ما
    # الكود ده اتكتب، بغض النظر عن أي مبيعات شاطئ حقيقية. اتصلح، ومستبعد منه
    # كمان العمليات الملغاة (voided_at) زي باقي أماكن حساب إيراد الشاطئ.
    beach_visitors = 0
    beach_revenue  = Decimal("0")
    try:
        from app.modules.beach.models import BeachTransaction  # noqa: PLC0415
        txs = db.query(BeachTransaction).filter(
            BeachTransaction.branch_id == branch_id,
            BeachTransaction.tx_date == stat_date,
            BeachTransaction.voided_at.is_(None),
        ).all()
        beach_visitors = len(txs)
        beach_revenue  = sum((t.total_amount + t.vat_amount for t in txs), Decimal("0"))
    except Exception:
        pass

    # Restaurant
    restaurant_covers  = 0
    restaurant_revenue = Decimal("0")
    try:
        from app.modules.restaurant.models import Order  # noqa: PLC0415
        orders = db.query(Order).filter(
            Order.branch_id == branch_id,
            Order.status == "paid",
            Order.created_at >= day_start,
            Order.created_at <= day_end,
        ).all()
        # ⚠️ باج حقيقي كان هنا (اتصلح 2026-07-05): كان بيقرأ Order.covers —
        # حقل مش موجود خالص في الموديل (الاسم الصح guests_count)، فـ
        # hasattr كان بيرجع False دايمًا وrestaurant_covers كان صفر ثابت
        # في كل DailyStats اتولّدت من أول ما الكود ده اتكتب.
        restaurant_covers  = sum(o.guests_count for o in orders if o.guests_count)
        restaurant_revenue = sum((o.total for o in orders), Decimal("0"))
    except Exception:
        pass

    # Cafe
    cafe_revenue = Decimal("0")
    try:
        from app.modules.cafe.models import CafeOrder  # noqa: PLC0415
        cafe_orders = db.query(CafeOrder).filter(
            CafeOrder.branch_id == branch_id,
            CafeOrder.status == "paid",
            CafeOrder.created_at >= day_start,
            CafeOrder.created_at <= day_end,
        ).all()
        cafe_revenue = sum((o.total for o in cafe_orders), Decimal("0"))
    except Exception:
        pass

    total_revenue = room_revenue + beach_revenue + restaurant_revenue + cafe_revenue

    # Upsert
    existing = db.query(DailyStats).filter(
        DailyStats.branch_id == branch_id,
        DailyStats.stat_date == stat_date,
    ).first()

    if existing:
        existing.occupied_rooms     = occupied_rooms
        existing.total_rooms        = total_rooms
        existing.occupancy_pct      = occupancy_pct
        existing.adr                = adr
        existing.revpar             = revpar
        existing.room_revenue       = room_revenue
        existing.beach_visitors     = beach_visitors
        existing.beach_revenue      = beach_revenue
        existing.restaurant_covers  = restaurant_covers
        existing.restaurant_revenue = restaurant_revenue
        existing.cafe_revenue       = cafe_revenue
        existing.total_revenue      = total_revenue
        existing.generated_at       = _dt.utcnow()
    else:
        db.add(DailyStats(
            branch_id=branch_id,
            stat_date=stat_date,
            occupied_rooms=occupied_rooms,
            total_rooms=total_rooms,
            occupancy_pct=occupancy_pct,
            adr=adr,
            revpar=revpar,
            room_revenue=room_revenue,
            beach_visitors=beach_visitors,
            beach_revenue=beach_revenue,
            restaurant_covers=restaurant_covers,
            restaurant_revenue=restaurant_revenue,
            cafe_revenue=cafe_revenue,
            total_revenue=total_revenue,
            generated_at=_dt.utcnow(),
        ))
    db.commit()
