"""app/tasks/beach_tasks.py — Beach reservation no-show processing"""
from __future__ import annotations

import logging
from datetime import date

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.beach_tasks.process_reservation_no_shows", bind=True)
def process_reservation_no_shows(self):
    """
    بعد 11 صباحاً — يُحوّل الحجوزات غير المُسجَّلة إلى no_show.
    """
    try:
        from app.core.database import SessionLocal          # noqa: PLC0415
        from app.modules.core.models import Branch          # noqa: PLC0415
        from app.modules.beach.crud import (               # noqa: PLC0415
            list_reservations, update_reservation_status,
        )

        today = date.today()
        with SessionLocal() as db:
            branches = db.query(Branch).filter(Branch.is_active.is_(True)).all()
            total_no_shows = 0
            for branch in branches:
                items, _ = list_reservations(
                    db, branch.id,
                    res_date=today,
                    status="confirmed",
                    limit=500,
                )
                for res in items:
                    update_reservation_status(db, res, "no_show")
                    total_no_shows += 1
            db.commit()
            logger.info("Beach no-shows processed: date=%s count=%s", today, total_no_shows)

    except Exception as exc:
        logger.error("process_reservation_no_shows failed: %s", exc)


@celery_app.task(name="app.tasks.beach_tasks.timeshare_mark_overdue", bind=True)
def timeshare_mark_overdue(self):
    """
    كل يوم 2 صباحاً — يُحدّث الأقساط المتأخرة.
    """
    try:
        from app.core.database import SessionLocal          # noqa: PLC0415

        today = date.today()
        with SessionLocal() as db:
            try:
                from app.modules.timeshare.models import TimeshareInstallment  # noqa: PLC0415
                overdue = (
                    db.query(TimeshareInstallment)
                    .filter(
                        TimeshareInstallment.due_date < today,
                        TimeshareInstallment.status == "pending",
                    )
                    .all()
                )
                for inst in overdue:
                    inst.status = "overdue"
                db.commit()
                logger.info("Timeshare overdue marked: count=%s", len(overdue))
            except ImportError:
                pass

    except Exception as exc:
        logger.error("timeshare_mark_overdue failed: %s", exc)
