"""Daily idempotent expiry scan for the private document vault."""
from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.core.kernel.worker import notify_task_failure


logger = logging.getLogger(__name__)
_TASK_NAME = "app.tasks.document_tasks.scan_expiry_notifications"


@celery_app.task(name=_TASK_NAME, bind=True, max_retries=3)
def scan_expiry_notifications(self):
    try:
        from app.core.database import SessionLocal  # noqa: PLC0415
        from app.modules.documents.services import scan_expiry_notifications as scan  # noqa: PLC0415

        with SessionLocal() as db:
            created = scan(db)
        logger.info("Document expiry scan complete: new_markers=%s", created)
        return created
    except Exception as exc:
        logger.exception("Document expiry scan failed")
        notify_task_failure(_TASK_NAME, exc)
        raise self.retry(exc=exc, countdown=600)
