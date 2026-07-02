"""app/tasks/pms_tasks.py — Night Audit + No-show processing"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.pms_tasks.run_night_audit", bind=True, max_retries=3)
def run_night_audit(self, branch_id: int | None = None, audit_date_str: str | None = None):
    """
    Night Audit — كل يوم 00:01
    يُشغَّل لكل الفروع أو فرع محدد.
    """
    try:
        from app.core.database import SessionLocal          # noqa: PLC0415
        from app.modules.core.models import Branch          # noqa: PLC0415
        from app.modules.pms.services import run_night_audit as _run  # noqa: PLC0415

        audit_date = (
            date.fromisoformat(audit_date_str)
            if audit_date_str
            else date.today() - timedelta(days=1)   # أمس — يُشغَّل بعد منتصف الليل
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
        from app.core.database import SessionLocal              # noqa: PLC0415
        from app.modules.core.models import Branch, Setting     # noqa: PLC0415
        from app.modules.pms.services import _mark_no_shows     # noqa: PLC0415

        today = date.today()

        with SessionLocal() as db:
            if branch_id:
                branches = [db.query(Branch).filter(Branch.id == branch_id).first()]
            else:
                branches = db.query(Branch).filter(Branch.is_active.is_(True)).all()

            for branch in filter(None, branches):
                # no_show_deadline_hour من Settings (default 18:00)
                deadline_setting = (
                    db.query(Setting)
                    .filter(Setting.key == "no_show_deadline_hour",
                            Setting.branch_id == branch.id)
                    .first()
                )
                from datetime import datetime  # noqa: PLC0415
                deadline_hour = int(deadline_setting.value) if deadline_setting else 18
                if datetime.utcnow().hour >= deadline_hour:
                    _mark_no_shows(db, branch.id, today)
                    logger.info("No-show processed: branch=%s date=%s", branch.id, today)

    except Exception as exc:
        logger.error("process_no_shows failed: %s", exc)
