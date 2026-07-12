"""app/tasks/pms_tasks.py — Night Audit + No-show processing

⚠️ باج توقيت حقيقي كان هنا (نفس فئة باج KDS "urgent"/dashboard "إيراد اليوم"):
run_night_audit و process_no_shows كانوا بيحسبوا "اليوم" بـ date.today()/
datetime.utcnow() — ده تاريخ/ساعة السيرفر (UTC غالبًا في الإنتاج)، مش توقيت
المنتجع الفعلي (Africa/Cairo، UTC+3). الـ beat schedule نفسه مضبوط صح
(celery_app.conf.timezone = "Africa/Cairo")، فالمهمة كانت فعلاً بتشتغل الساعة
00:01 بتوقيت القاهرة — لكن جوه المهمة، date.today() برضه بيرجع تاريخ UTC مش
تاريخ القاهرة، فكانت بتحسب "أمس" غلط بيوم كامل في نافذة الـ ~3 ساعات حوالين
منتصف ليل القاهرة (Night Audit بيدقق يوم غلط، process_no_shows بيقارن
"وصل الساعة كام" بساعة UTC مش ساعة القاهرة فبيتأخر قرار no-show 3 ساعات
كل يوم). اتصلح باستخدام app.resort_os.timezone_utils (local_today/local_now).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from app.celery_app import celery_app
from app.core.kernel.worker import notify_task_failure

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.pms_tasks.run_night_audit", bind=True, max_retries=3)
def run_night_audit(self, branch_id: int | None = None, audit_date_str: str | None = None):
    """
    Night Audit — كل يوم 00:01
    يُشغَّل لكل الفروع أو فرع محدد.
    """
    try:
        from datetime import date                           # noqa: PLC0415
        from app.core.config import settings                # noqa: PLC0415
        from app.core.database import SessionLocal          # noqa: PLC0415
        from app.modules.core.models import Branch          # noqa: PLC0415
        from app.modules.pms.services import run_night_audit as _run  # noqa: PLC0415
        from app.resort_os.timezone_utils import local_today  # noqa: PLC0415

        audit_date = (
            date.fromisoformat(audit_date_str)
            if audit_date_str
            else local_today(settings.TIMEZONE) - timedelta(days=1)   # أمس بتوقيت المنتجع
        )

        with SessionLocal() as db:
            if branch_id:
                branches = [db.query(Branch).filter(Branch.id == branch_id).first()]
            else:
                branches = db.query(Branch).filter(Branch.is_active.is_(True)).all()

            results = []
            for branch in filter(None, branches):
                try:
                    log = _run(db, branch.id, audit_date)
                    results.append({
                        "branch_id":   branch.id,
                        "audit_date":  str(audit_date),
                        "status":      log.status,
                        "occupancy":   float(log.occupancy_pct),
                        "revenue":     float(log.room_revenue),
                    })
                    logger.info("Night Audit completed: branch=%s date=%s", branch.id, audit_date)
                except Exception as exc:
                    logger.error("Night Audit failed: branch=%s error=%s", branch.id, exc)
                    notify_task_failure(
                        "app.tasks.pms_tasks.run_night_audit", exc,
                        extra={"branch_id": branch.id, "audit_date": str(audit_date)},
                    )

        return results

    except Exception as exc:
        logger.error("run_night_audit task failed: %s", exc)
        raise self.retry(exc=exc, countdown=300)   # retry بعد 5 دقائق


@celery_app.task(name="app.tasks.pms_tasks.process_no_shows", bind=True)
def process_no_shows(self, branch_id: int | None = None):
    """
    يتحقق من الحجوزات التي لم تصل بعد ساعات محددة من check_in.
    يُشغَّل كل ساعة.
    """
    try:
        from app.core.config import settings                    # noqa: PLC0415
        from app.core.database import SessionLocal              # noqa: PLC0415
        from app.modules.core.models import Branch, Setting     # noqa: PLC0415
        from app.modules.pms.services import _mark_no_shows     # noqa: PLC0415
        from app.resort_os.timezone_utils import local_now       # noqa: PLC0415

        now_local = local_now(settings.TIMEZONE)
        today = now_local.date()

        with SessionLocal() as db:
            if branch_id:
                branches = [db.query(Branch).filter(Branch.id == branch_id).first()]
            else:
                branches = db.query(Branch).filter(Branch.is_active.is_(True)).all()

            for branch in filter(None, branches):
                # no_show_deadline_hour من Settings (default 18:00) — ساعة
                # بتوقيت المنتجع (Africa/Cairo)، لازم تتقارن بساعة محلية حقيقية
                # مش UTC، وإلا قرار no-show كان بيتأخر بفرق التوقيت كل يوم.
                deadline_setting = (
                    db.query(Setting)
                    .filter(Setting.key == "no_show_deadline_hour",
                            Setting.branch_id == branch.id)
                    .first()
                )
                deadline_hour = int(deadline_setting.value) if deadline_setting else 18
                if now_local.hour >= deadline_hour:
                    _mark_no_shows(db, branch.id, today)
                    logger.info("No-show processed: branch=%s date=%s", branch.id, today)

    except Exception as exc:
        logger.error("process_no_shows failed: %s", exc)
        notify_task_failure("app.tasks.pms_tasks.process_no_shows", exc)
