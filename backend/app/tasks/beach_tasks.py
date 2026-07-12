"""app/tasks/beach_tasks.py — Beach reservation no-show processing + B2B dunning

⚠️ باج توقيت حقيقي كان هنا (نفس فئة الباج الموثّقة في resort_os/timezone_utils.py
واللي اتكشفت في KDS/PMS/تايم-شير/موارد بشرية/إيجارات/شاطئ يوم 2026-07-06):
`process_reservation_no_shows` كانت بتستخدم `date.today()` (توقيت السيرفر، UTC
غالبًا في الإنتاج) بدل توقيت المنتجع (Africa/Cairo) — بقى بيستخدم business_today.

كان فيه كمان تعريف مكرر ومعطوب لمهمة `timeshare_mark_overdue` هنا (نسخة أبسط
وأقدم من `app.tasks.timeshare_tasks.mark_overdue` الحقيقية) — مش مسجّلة في
`celery_app.beat_schedule` خالص (كود ميت فعليًا)، ومفيهاش تجميد الحجز
(`booking_frozen`) ولا معالجة الأقساط partial زي النسخة الحقيقية. اتشالت.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from app.celery_app import celery_app
from app.core.config import settings
from app.core.kernel.worker import notify_task_failure
from app.resort_os.timezone_utils import business_today

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

        today = business_today(settings.TIMEZONE)
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
        notify_task_failure("app.tasks.beach_tasks.process_reservation_no_shows", exc)


@celery_app.task(name="app.tasks.beach_tasks.mark_b2b_overdue", bind=True, max_retries=3)
def mark_b2b_overdue(self):
    """
    كل يوم 2:15 صباحاً — يُحدّث حالة تأخر السداد (is_overdue) لكل عقود B2B
    النشطة حسب مهلة السداد (payment_terms_days)، وبيبعت تنبيه واتساب مرة
    واحدة لكل دخول في حالة التأخر. نفس نمط timeshare_tasks.mark_overdue
    بالظبط: الجزء القابل للاختبار (services.mark_b2b_contracts_overdue)
    منفصل عن الـ task نفسه (SessionLocal + retry) عشان يتعمله unit test
    من غير Celery/Redis حقيقيين.
    """
    try:
        from app.core.database import SessionLocal  # noqa: PLC0415
        today: Optional[date] = business_today(settings.TIMEZONE)

        with SessionLocal() as db:
            from app.modules.beach.services import mark_b2b_contracts_overdue  # noqa: PLC0415

            changed = mark_b2b_contracts_overdue(db, today)
            db.commit()
            logger.info("B2B overdue processed: changed=%s", changed)

    except Exception as exc:
        logger.error("beach mark_b2b_overdue failed: %s", exc)
        raise self.retry(exc=exc, countdown=600)
