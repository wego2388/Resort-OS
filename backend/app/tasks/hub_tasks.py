"""app/tasks/hub_tasks.py — Digital Hub: sitemap refresh + offer expiry"""
from __future__ import annotations

import logging
from datetime import date

from app.celery_app import celery_app
from app.core.config import settings
from app.resort_os.timezone_utils import local_today

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.hub_tasks.refresh_sitemap",
    bind=True,
    max_retries=3,
)
def refresh_sitemap(self):
    """
    كل يوم 3 صباحاً — يُحدّث سجل الـ sitemap لكل الفروع.
    """
    try:
        from app.core.database import SessionLocal      # noqa: PLC0415
        from app.modules.core.models import Branch      # noqa: PLC0415

        with SessionLocal() as db:
            try:
                from app.modules.hub.services import refresh_sitemap as do_refresh  # noqa: PLC0415

                branches = db.query(Branch).filter(Branch.is_active.is_(True)).all()
                total_pages = 0

                for branch in branches:
                    pages_count = do_refresh(db, branch.id)
                    logger.info(
                        "Sitemap refreshed: branch=%s pages=%s",
                        branch.id, pages_count,
                    )
                    total_pages += pages_count

                logger.info("Sitemap refresh done: total_pages=%s", total_pages)

            except ImportError:
                logger.debug("Hub module not yet built — skipped")

    except Exception as exc:
        logger.error("hub refresh_sitemap failed: %s", exc)
        raise self.retry(exc=exc, countdown=600)


@celery_app.task(
    name="app.tasks.hub_tasks.expire_old_offers",
    bind=True,
)
def expire_old_offers(self):
    """
    كل يوم منتصف الليل — يُعطّل العروض المنتهية الصلاحية.
    """
    try:
        from app.core.database import SessionLocal      # noqa: PLC0415

        today = local_today(settings.TIMEZONE)

        with SessionLocal() as db:
            try:
                from app.modules.hub.models import HubOffer  # noqa: PLC0415

                expired = (
                    db.query(HubOffer)
                    .filter(
                        HubOffer.is_active.is_(True),
                        HubOffer.valid_until < today,
                    )
                    .all()
                )

                for offer in expired:
                    offer.is_active = False
                    logger.info(
                        "Offer expired: id=%s title=%s valid_until=%s",
                        offer.id, offer.title, offer.valid_until,
                    )

                db.commit()
                logger.info("Expired offers deactivated: %s", len(expired))

            except ImportError:
                logger.debug("Hub module not yet built — skipped")

    except Exception as exc:
        logger.error("hub expire_old_offers failed: %s", exc)


@celery_app.task(
    name="app.tasks.hub_tasks.process_pending_bookings_reminder",
    bind=True,
)
def process_pending_bookings_reminder(self):
    """
    كل يوم 10 صباحاً — تذكير للحجوزات الإلكترونية التي لم تُؤكَّد منذ 24 ساعة.
    """
    try:
        from app.core.database import SessionLocal          # noqa: PLC0415
        from datetime import datetime, timedelta            # noqa: PLC0415

        cutoff = datetime.utcnow() - timedelta(hours=24)

        with SessionLocal() as db:
            try:
                from app.modules.hub.models import HubOnlineBooking  # noqa: PLC0415

                pending = (
                    db.query(HubOnlineBooking)
                    .filter(
                        HubOnlineBooking.status == "pending",
                        HubOnlineBooking.created_at <= cutoff,
                    )
                    .all()
                )

                for booking in pending:
                    logger.info(
                        "Unconfirmed booking: id=%s guest=%s phone=%s date=%s source=%s",
                        booking.id, booking.guest_name,
                        booking.guest_phone, booking.requested_date,
                        booking.source,
                    )

                if pending:
                    from app.core.kernel.whatsapp import notify_admin  # noqa: PLC0415
                    names = "، ".join(b.guest_name for b in pending[:5])
                    more = f" و{len(pending) - 5} حجز آخر" if len(pending) > 5 else ""
                    notify_admin(f"تنبيه ريسبشن: {len(pending)} حجز أونلاين لسه مش متابَع من أكتر من 24 ساعة — {names}{more}.")

                logger.info("Pending online bookings found: %s", len(pending))

            except ImportError:
                logger.debug("Hub module not yet built — skipped")

    except Exception as exc:
        logger.error("hub process_pending_bookings_reminder failed: %s", exc)
