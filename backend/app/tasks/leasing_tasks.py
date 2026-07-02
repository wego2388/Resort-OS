"""app/tasks/leasing_tasks.py — Leasing overdue + penalties"""
from __future__ import annotations

import logging
from datetime import date

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.leasing_tasks.mark_overdue", bind=True, max_retries=3)
def mark_overdue(self):
    """
    كل يوم 2:30 صباحاً — يُحدّث دفعات الإيجار المتأخرة ويُحسب الغرامة.
    """
    try:
        from app.core.database import SessionLocal  # noqa: PLC0415
        today = date.today()

        with SessionLocal() as db:
            try:
                from app.modules.leasing.models import LeasePayment  # noqa: PLC0415
                from app.resort_os.timeshare_engine import calculate_lease_penalty  # noqa: PLC0415

                overdue_payments = (
                    db.query(LeasePayment)
                    .filter(
                        LeasePayment.due_date < today,
                        LeasePayment.status == "pending",
                    )
                    .all()
                )
                for p in overdue_payments:
                    penalty = calculate_lease_penalty(p.amount, p.due_date, today)
                    p.status  = "overdue"
                    p.penalty = penalty
                    logger.info(
                        "Lease payment overdue: id=%s amount=%s penalty=%s",
                        p.id, p.amount, penalty,
                    )

                db.commit()
                logger.info("Leasing overdue processed: count=%s", len(overdue_payments))

            except ImportError:
                logger.debug("Leasing module not yet built — skipped")

    except Exception as exc:
        logger.error("leasing mark_overdue failed: %s", exc)
        raise self.retry(exc=exc, countdown=600)


@celery_app.task(name="app.tasks.leasing_tasks.send_due_reminders", bind=True)
def send_due_reminders(self):
    """
    كل يوم 9 صباحاً — تذكير دفعات الإيجار المستحقة خلال 7 أيام.
    """
    try:
        from app.core.database import SessionLocal  # noqa: PLC0415
        from datetime import timedelta              # noqa: PLC0415
        remind_date = date.today() + timedelta(days=7)

        with SessionLocal() as db:
            try:
                from app.modules.leasing.models import LeasePayment  # noqa: PLC0415

                due_soon = (
                    db.query(LeasePayment)
                    .filter(
                        LeasePayment.due_date == remind_date,
                        LeasePayment.status == "pending",
                    )
                    .all()
                )
                for p in due_soon:
                    logger.info(
                        "Lease due reminder: id=%s amount=%s due=%s",
                        p.id, p.amount, p.due_date,
                    )
                    # TODO: إشعار WhatsApp للمستأجر

            except ImportError:
                pass

    except Exception as exc:
        logger.error("leasing send_due_reminders failed: %s", exc)
