"""app/tasks/maintenance_tasks.py — Preventive maintenance scheduler"""
from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.core.config import settings
from app.resort_os.timezone_utils import local_today

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.maintenance_tasks.generate_preventive_tasks",
    bind=True,
    max_retries=3,
)
def generate_preventive_tasks(self):
    """
    كل يوم 6 صباحاً — ينشئ أوامر صيانة وقائية لكل الجداول المستحقة.
    """
    try:
        from app.core.database import SessionLocal      # noqa: PLC0415
        from app.modules.core.models import Branch      # noqa: PLC0415

        total_created = 0

        with SessionLocal() as db:
            try:
                from app.modules.maintenance.services import (  # noqa: PLC0415
                    generate_preventive_work_orders,
                )

                branches = db.query(Branch).filter(Branch.is_active.is_(True)).all()
                for branch in branches:
                    created = generate_preventive_work_orders(db, branch.id)
                    if created:
                        logger.info(
                            "Preventive WOs created: branch=%s count=%s",
                            branch.id, created,
                        )
                    total_created += created

            except ImportError:
                logger.debug("Maintenance module not yet built — skipped")

        logger.info("Preventive maintenance task done: total_created=%s", total_created)

    except Exception as exc:
        logger.error("generate_preventive_tasks failed: %s", exc)
        raise self.retry(exc=exc, countdown=600)


@celery_app.task(
    name="app.tasks.maintenance_tasks.notify_overdue_work_orders",
    bind=True,
)
def notify_overdue_work_orders(self):
    """
    كل يوم 8 صباحاً — تنبيه لأوامر الصيانة المفتوحة المتأخرة عن موعدها.
    """
    try:
        from app.core.database import SessionLocal          # noqa: PLC0415

        today = local_today(settings.TIMEZONE)

        with SessionLocal() as db:
            try:
                from app.modules.maintenance.models import WorkOrder  # noqa: PLC0415
                from app.modules.hr.models import Employee  # noqa: PLC0415
                from app.core.kernel.whatsapp import notify_admin, send_whatsapp_message  # noqa: PLC0415

                overdue = (
                    db.query(WorkOrder)
                    .filter(
                        WorkOrder.scheduled_date < today,
                        WorkOrder.status.in_(["open", "in_progress"]),
                    )
                    .all()
                )

                for wo in overdue:
                    logger.info(
                        "Overdue WO: id=%s title=%s branch=%s priority=%s scheduled=%s",
                        wo.id, wo.title, wo.branch_id, wo.priority, wo.scheduled_date,
                    )
                    sent = False
                    if wo.assigned_to:
                        emp = db.query(Employee).filter(Employee.id == wo.assigned_to).first()
                        if emp and emp.phone:
                            send_whatsapp_message(
                                emp.phone,
                                f"أمر صيانة متأخر: {wo.title} — كان مجدول {wo.scheduled_date:%Y-%m-%d}.",
                            )
                            sent = True
                    if not sent:
                        notify_admin(f"أمر صيانة متأخر بلا موظف مسؤول: {wo.title} (WO #{wo.id}).")

                logger.info("Overdue work orders found: %s", len(overdue))

            except ImportError:
                logger.debug("Maintenance module not yet built — skipped")

    except Exception as exc:
        logger.error("notify_overdue_work_orders failed: %s", exc)
