"""app/tasks/timeshare_tasks.py — Timeshare overdue + visit reminders

⚠️ كل الـ 3 tasks هنا كانت بتستخدم date.today() (توقيت السيرفر المحلي) بدل
توقيت المنتجع (Africa/Cairo) — نفس فئة باج توقيت تذاكر المطبخ (KDS). لو
السيرفر شغّال بتوقيت مختلف (مثلاً UTC)، فيه نافذة كل يوم (~2-3 ساعات) كان
ممكن يعتبر فيها قسط مستحق "النهاردة" لسه مش متأخر، أو يبعت تذكير زيارة بيوم
غلط. بقى بيستخدم business_today(settings.TIMEZONE)."""
from __future__ import annotations

import logging
from datetime import date

from app.celery_app import celery_app
from app.core.config import settings
from app.resort_os.timezone_utils import business_today

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.timeshare_tasks.mark_overdue", bind=True, max_retries=3)
def mark_overdue(self):
    """
    كل يوم 2 صباحاً — يُحدّث الأقساط المتأخرة ويُجمّد حقوق الحجز.
    """
    try:
        from app.core.database import SessionLocal  # noqa: PLC0415
        today = business_today(settings.TIMEZONE)

        with SessionLocal() as db:
            try:
                overdue_count = _mark_overdue(db, today)
                db.commit()
                logger.info("Timeshare overdue processed: count=%s", overdue_count)
            except ImportError:
                logger.debug("Timeshare module not yet built — skipped")

    except Exception as exc:
        logger.error("timeshare mark_overdue failed: %s", exc)
        raise self.retry(exc=exc, countdown=600)


def _mark_overdue(db, today: date) -> int:
    """
    الجزء القابل للاختبار: يُحدِّث حالة الأقساط المتأخرة إلى overdue ثم يُجمِّد
    حق الحجز (booking_frozen) لأي عقد نشط لديه أقساط متأخرة.

    ⚠️ لا تستخدم `contract.installments` هنا — ده عمود عدد الأقساط (int)،
    العلاقة الصحيحة هي `contract.installments_list`.
    """
    from app.modules.timeshare.models import (  # noqa: PLC0415
        TimeshareInstallment, TimeshareContract,
    )
    from app.resort_os.timeshare_engine import should_freeze_booking  # noqa: PLC0415
    from decimal import Decimal  # noqa: PLC0415

    # تحديث الأقساط المتأخرة — بما فيها اللي سُدِّدت جزئياً (partial) ولسه متأخرة،
    # وإلا القسط ده مش هيتحسب أبداً في overdue_total تحت (اللي بيفلتر status=="overdue"
    # بس)، فعقد فيه قسط مدفوع جزئياً ومتأخر ميتجمّدش حقه في الحجز رغم إنه متأخر فعلاً.
    overdue_insts = (
        db.query(TimeshareInstallment)
        .filter(
            TimeshareInstallment.due_date < today,
            TimeshareInstallment.status.in_(["pending", "partial"]),
        )
        .all()
    )
    for inst in overdue_insts:
        inst.status = "overdue"

    # حساب المبالغ المتأخرة لكل عقد وتجميد الحجز
    contracts = db.query(TimeshareContract).filter(
        TimeshareContract.status == "active"
    ).all()
    for contract in contracts:
        overdue_total = sum(
            i.amount for i in contract.installments_list
            if i.status == "overdue"
        ) or Decimal("0")
        if should_freeze_booking(overdue_total):
            contract.booking_frozen = True

    return len(overdue_insts)


@celery_app.task(name="app.tasks.timeshare_tasks.send_visit_reminders", bind=True)
def send_visit_reminders(self):
    """
    كل يوم 9 صباحاً — يُرسل تذكير للزيارات القادمة خلال 3 أيام.
    """
    try:
        from app.core.database import SessionLocal  # noqa: PLC0415
        today = business_today(settings.TIMEZONE)

        with SessionLocal() as db:
            try:
                from app.modules.timeshare.models import TimeshareContract  # noqa: PLC0415
                from app.resort_os.timeshare_engine import (  # noqa: PLC0415
                    find_next_visit, should_send_visit_reminder,
                )

                contracts = db.query(TimeshareContract).filter(
                    TimeshareContract.status == "active",
                    TimeshareContract.week_number.isnot(None),
                ).all()

                from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415

                reminders_sent = 0
                for c in contracts:
                    visit = find_next_visit(c.week_number, c.nights_per_year, today)
                    if visit and should_send_visit_reminder(visit):
                        logger.info(
                            "Visit reminder: contract=%s guest=%s visit_start=%s",
                            c.id, c.customer_name, visit.visit_start,
                        )
                        if c.customer_phone:
                            send_whatsapp_message(
                                c.customer_phone,
                                f"تذكير: زيارتك القادمة في الخيمة بيتش تبدأ يوم {visit.visit_start:%Y-%m-%d} — نتشرف باستقبالك.",
                            )
                        reminders_sent += 1

                logger.info("Visit reminders sent: %s", reminders_sent)

            except ImportError:
                logger.debug("Timeshare module not yet built — skipped")

    except Exception as exc:
        logger.error("send_visit_reminders failed: %s", exc)


@celery_app.task(name="app.tasks.timeshare_tasks.send_installment_reminders", bind=True)
def send_installment_reminders(self):
    """
    كل يوم 9 صباحاً — تذكير الأقساط المستحقة خلال 7 أيام.
    """
    try:
        from app.core.database import SessionLocal  # noqa: PLC0415
        from datetime import timedelta              # noqa: PLC0415
        today = business_today(settings.TIMEZONE)
        remind_date = today + timedelta(days=7)

        with SessionLocal() as db:
            try:
                from app.modules.timeshare.models import TimeshareInstallment  # noqa: PLC0415

                from app.modules.timeshare.models import TimeshareContract  # noqa: PLC0415
                from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415

                due_soon = (
                    db.query(TimeshareInstallment)
                    .filter(
                        TimeshareInstallment.due_date == remind_date,
                        TimeshareInstallment.status == "pending",
                    )
                    .all()
                )
                for inst in due_soon:
                    logger.info(
                        "Installment reminder: id=%s amount=%s due=%s",
                        inst.id, inst.amount, inst.due_date,
                    )
                    contract = db.query(TimeshareContract).filter(
                        TimeshareContract.id == inst.contract_id
                    ).first()
                    if contract and contract.customer_phone:
                        send_whatsapp_message(
                            contract.customer_phone,
                            f"تذكير: قسط بقيمة {inst.amount:,.2f} ج.م مستحق يوم {inst.due_date:%Y-%m-%d} — عقد رقم {contract.contract_number}.",
                        )

            except ImportError:
                pass

    except Exception as exc:
        logger.error("send_installment_reminders failed: %s", exc)
