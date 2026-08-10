"""app/tasks/leasing_tasks.py — Leasing overdue + penalties"""
from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.core.kernel.worker import notify_task_failure

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.leasing_tasks.mark_overdue", bind=True, max_retries=3)
def mark_overdue(self):
    """
    كل يوم 2:30 صباحاً — يُحدّث دفعات الإيجار المتأخرة ويُحسب الغرامة.

    ⚠️ باج توقيت حقيقي (نفس الفئة الموثّقة في resort_os/timezone_utils.py):
    `date.today()` بترجع تاريخ السيرفر (UTC غالبًا في الإنتاج) مش تاريخ
    المنتجع (Africa/Cairo) — تحديدًا هنا بيأثّر على شريحة الغرامة (8/30 يوم).

    ⚠️ باج حقيقي كان هنا (اتصلح 2026-07-29): الفلتر كان ``status == "pending"``
    بس — دفعة اتسدّدت جزئيًا (``status="partial"``، فيها ``paid_amount>0``)
    كانت بتتخطى فحص التأخر للأبد، فمفيهاش غرامة اتحسبت خالص ولو فضل جزء كبير
    من المبلغ مش متحصّل من شهور. وبمجرد ما دفعة توصف "overdue" مرة، كانت
    بتتخطى برضو في الأيام الجاية — يعني شريحة الغرامة (5% لـ8-30 يوم، 10%
    لأكتر من 30) كانت بتتجمّد على أول قيمة اتحسبت بدل ما تتصاعد مع الوقت.
    اتصلح بتوسيع الفلتر لـ(pending/partial/overdue) واستخدام
    ``leasing.services.calculate_penalty`` (نفس المصدر الوحيد اللي
    ``apply_penalties`` بيستخدمه) بدل تكرار حساب الشريحة هنا — عشان مفيش
    نسختين من نفس القاعدة تتفرقوا زي الباج الموثّق في ``calculate_penalty``
    نفسها.
    """
    try:
        from app.core.config import settings                       # noqa: PLC0415
        from app.core.database import SessionLocal                  # noqa: PLC0415
        from app.resort_os.timezone_utils import local_today         # noqa: PLC0415
        today = local_today(settings.TIMEZONE)

        with SessionLocal() as db:
            try:
                from app.modules.leasing.models import LeasePayment  # noqa: PLC0415
                from app.modules.leasing.services import calculate_penalty  # noqa: PLC0415

                overdue_payments = (
                    db.query(LeasePayment)
                    .filter(
                        LeasePayment.due_date < today,
                        LeasePayment.status.in_(("pending", "partial", "overdue")),
                    )
                    .all()
                )
                updated = 0
                for p in overdue_payments:
                    penalty = calculate_penalty(p, today)
                    if penalty == p.penalty and p.status == "overdue":
                        continue
                    p.penalty = penalty
                    if penalty > 0:
                        p.status = "overdue"
                    updated += 1
                    logger.info(
                        "Lease payment overdue: id=%s amount=%s penalty=%s",
                        p.id, p.amount, penalty,
                    )

                db.commit()
                logger.info("Leasing overdue processed: checked=%s updated=%s", len(overdue_payments), updated)

            except ImportError:
                logger.debug("Leasing module not yet built — skipped")

    except Exception as exc:
        logger.error("leasing mark_overdue failed: %s", exc)
        raise self.retry(exc=exc, countdown=600)


@celery_app.task(name="app.tasks.leasing_tasks.accrue_due_rents", bind=True, max_retries=3)
def accrue_due_rents(self):
    """
    كل يوم 2:00 صباحاً (قبل mark_overdue) — يثبت إيراد كل دفعات الإيجار اللي
    وصل تاريخ استحقاقها اليوم أو قبل كده ولسه ما اتحقّقتش محاسبيًا (Dr ذمم
    مستأجرين / Cr إيراد إيجارات — راجع OPS-DATA-02 §10.5). عبر كل الفروع،
    idempotent (LeasePayment.accrued يمنع الترحيل مرتين).
    """
    try:
        from app.core.config import settings                       # noqa: PLC0415
        from app.core.database import SessionLocal                  # noqa: PLC0415
        from app.resort_os.timezone_utils import local_today         # noqa: PLC0415
        today = local_today(settings.TIMEZONE)

        with SessionLocal() as db:
            try:
                from app.modules.core.models import Branch  # noqa: PLC0415
                from app.modules.leasing.services import accrue_due_rents as _accrue  # noqa: PLC0415

                total = 0
                for branch in db.query(Branch).all():
                    accrued = _accrue(db, branch.id, today)
                    total += len(accrued)
                logger.info("Leasing rent accrual processed: accrued=%s", total)

            except ImportError:
                logger.debug("Leasing module not yet built — skipped")

    except Exception as exc:
        logger.error("leasing accrue_due_rents failed: %s", exc)
        raise self.retry(exc=exc, countdown=600)


@celery_app.task(name="app.tasks.leasing_tasks.send_due_reminders", bind=True)
def send_due_reminders(self):
    """
    كل يوم 9 صباحاً — تذكير دفعات الإيجار المستحقة خلال 7 أيام.
    """
    try:
        from app.core.config import settings                # noqa: PLC0415
        from app.core.database import SessionLocal            # noqa: PLC0415
        from app.resort_os.timezone_utils import local_today   # noqa: PLC0415
        from datetime import timedelta                          # noqa: PLC0415
        remind_date = local_today(settings.TIMEZONE) + timedelta(days=7)

        with SessionLocal() as db:
            try:
                from app.modules.leasing.models import LeaseContract, LeasePayment  # noqa: PLC0415
                from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415

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
                    contract = db.query(LeaseContract).filter(LeaseContract.id == p.contract_id).first()
                    if contract and contract.tenant_phone:
                        send_whatsapp_message(
                            contract.tenant_phone,
                            f"تذكير مبكر: دفعة إيجار بقيمة {p.amount:,.2f} ج.م مستحقة بعد أسبوع ({p.due_date:%Y-%m-%d}).",
                        )

            except ImportError:
                pass

    except Exception as exc:
        logger.error("leasing send_due_reminders failed: %s", exc)
        notify_task_failure("app.tasks.leasing_tasks.send_due_reminders", exc)
