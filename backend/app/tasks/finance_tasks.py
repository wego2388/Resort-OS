"""app/tasks/finance_tasks.py — Due date reminders"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from app.celery_app import celery_app
from app.core.config import settings
from app.resort_os.timezone_utils import local_today

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.finance_tasks.check_due_reminders", bind=True)
def check_due_reminders(self):
    """
    يُرسل تذكيرات للفواتير المستحقة خلال 3 أيام.
    يُشغَّل كل يوم 9 صباحاً.
    """
    try:
        from app.core.database import SessionLocal              # noqa: PLC0415
        from app.modules.core.models import Branch # noqa: PLC0415

        today  = local_today(settings.TIMEZONE)
        remind = today + timedelta(days=3)

        with SessionLocal() as db:
            branches = db.query(Branch).filter(Branch.is_active.is_(True)).all()
            for branch in branches:
                try:
                    _check_timeshare_dues(db, branch.id, remind)
                    _check_leasing_dues(db, branch.id, remind)
                except Exception as exc:
                    logger.warning("Finance reminder failed: branch=%s error=%s", branch.id, exc)

    except Exception as exc:
        logger.error("check_due_reminders failed: %s", exc)


def _check_timeshare_dues(db, branch_id: int, remind_date: date) -> None:
    """تذكيرات أقساط التايم شير (نداء مبكر 3 أيام قبل الاستحقاق — النداء التاني
    عند 7 أيام موجود في timeshare_tasks.send_installment_reminders)."""
    try:
        from app.modules.timeshare.models import TimeshareContract, TimeshareInstallment  # noqa: PLC0415
        from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415
        dues = (
            db.query(TimeshareInstallment)
            .filter(
                TimeshareInstallment.due_date == remind_date,
                TimeshareInstallment.status == "pending",
            )
            .all()
        )
        for inst in dues:
            logger.info("Timeshare installment due reminder: id=%s due=%s", inst.id, inst.due_date)
            contract = db.query(TimeshareContract).filter(
                TimeshareContract.id == inst.contract_id
            ).first()
            if contract and contract.customer_phone:
                send_whatsapp_message(
                    contract.customer_phone,
                    f"تذكير أخير: قسط بقيمة {inst.amount:,.2f} ج.م مستحق بعد 3 أيام ({inst.due_date:%Y-%m-%d}).",
                )
    except ImportError:
        pass


def _check_leasing_dues(db, branch_id: int, remind_date: date) -> None:
    """تذكيرات دفعات الإيجار."""
    try:
        from app.modules.leasing.models import LeaseContract, LeasePayment  # noqa: PLC0415
        from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415
        dues = (
            db.query(LeasePayment)
            .filter(
                LeasePayment.due_date == remind_date,
                LeasePayment.status == "pending",
            )
            .all()
        )
        for p in dues:
            logger.info("Lease payment due reminder: id=%s due=%s", p.id, p.due_date)
            contract = db.query(LeaseContract).filter(LeaseContract.id == p.contract_id).first()
            if contract and contract.tenant_phone:
                send_whatsapp_message(
                    contract.tenant_phone,
                    f"تذكير: دفعة إيجار بقيمة {p.amount:,.2f} ج.م مستحقة يوم {p.due_date:%Y-%m-%d}.",
                )
    except ImportError:
        pass
