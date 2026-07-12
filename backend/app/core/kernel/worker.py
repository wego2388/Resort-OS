"""
app/core/kernel/worker.py
Celery factory for resort-os — make_celery() + CoreTask base class
(structured logging, auto-retry on transient errors, Sentry capture).
"""

import os
from typing import Any, Optional

from loguru import logger

try:
    from celery import Task as _CeleryTask
except ImportError:
    _CeleryTask = object  # type: ignore[assignment,misc]


def make_celery(settings=None, *, app_name: Optional[str] = None):
    """
    Create and configure a Celery app wired to the project's Redis broker.
    """
    try:
        from celery import Celery
    except ImportError:
        raise RuntimeError("celery is not installed")

    redis_url = (
        getattr(settings, "REDIS_URL", None)
        or os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    # Honor dedicated Celery broker/result URLs when configured (documented in
    # .env.example + DEPLOYMENT.md as separate Redis logical DBs), else fall
    # back to REDIS_URL so nothing breaks when they're unset.
    broker_url = (
        getattr(settings, "CELERY_BROKER_URL", None)
        or os.getenv("CELERY_BROKER_URL")
        or redis_url
    )
    result_backend = (
        getattr(settings, "CELERY_RESULT_BACKEND", None)
        or os.getenv("CELERY_RESULT_BACKEND")
        or redis_url
    )
    name = app_name or getattr(settings, "APP_NAME", None) or "resort_os"

    app = Celery(name, broker=broker_url, backend=result_backend)

    app.config_from_object({
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],

        "task_acks_late": True,
        "task_reject_on_worker_lost": True,
        "task_track_started": True,

        "result_expires": 86_400,

        "timezone": "Africa/Cairo",
        "enable_utc": True,

        "task_default_retry_delay": 60,
        "task_max_retries": 3,

        "worker_prefetch_multiplier": 1,
        "worker_max_tasks_per_child": 500,

        "beat_scheduler": "celery.beat:PersistentScheduler",
    })

    app.Task = CoreTask
    return app


class CoreTask(_CeleryTask):
    """
    Base Celery task with structured logging and auto-retry on common
    transient errors.
    """

    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        # wagdy.md T-03 — بيتفعّل لما استثناء يوصل فعليًا لـ Celery (يعني مش
        # مبتلَع جوه try/except الـ task نفسها) — بما فيه بعد استنفاد كل
        # محاولات self.retry(). Sentry + واتساب هنا سوا في مكان واحد مشترك
        # (مش مكرر لكل task) عشان أي فشل نهائي فعلي يوصل للإدارة، مش بس اللوج.
        logger.error(f"[Task:{self.name}] FAILED id={task_id} exc={exc!r}")
        _try_sentry_capture(exc, task_name=self.name)
        _try_whatsapp_notify(self.name, exc)
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning(f"[Task:{self.name}] RETRY id={task_id} exc={exc!r}")
        super().on_retry(exc, task_id, args, kwargs, einfo)

    def on_success(self, retval, task_id, args, kwargs):
        logger.debug(f"[Task:{self.name}] OK id={task_id}")
        super().on_success(retval, task_id, args, kwargs)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        with logger.contextualize(task_id=self.request.id, task_name=self.name):
            try:
                return super().__call__(*args, **kwargs)
            except (ConnectionError, TimeoutError, OSError) as exc:
                raise self.retry(exc=exc, countdown=60)


def _try_sentry_capture(exc: Exception, *, task_name: Optional[str] = None, extra: Optional[dict] = None) -> None:
    try:
        from app.core.kernel.sentry import capture_exception
        capture_exception(exc, tags={"task": task_name} if task_name else None, extra=extra)
    except Exception:
        pass


def _try_whatsapp_notify(task_name: str, exc: Exception) -> None:
    try:
        from app.core.kernel.whatsapp import notify_admin
        notify_admin(f"⚠️ فشلت مهمة مجدولة: {task_name}\nالخطأ: {exc}")
    except Exception:
        pass


def notify_task_failure(task_name: str, exc: Exception, *, extra: Optional[dict] = None) -> None:
    """wagdy.md T-03 — معظم tasks في app/tasks/ بتلف الجسم كله بـ
    `try/except Exception` وبتبلع الخطأ بـ logger.error() بس، من غير ما
    ترجّعه تاني — يعني CoreTask.on_failure فوق عمره ما بيتفعّل ليها، لأن
    Celery من منظورها الـ task خلصت "بنجاح" (مفيش استثناء طلع منها خالص).
    استدعِ الدالة دي من جوه أي except block بيبتلع خطأ نهائي بدل ما تكتفي
    بـ logger.error() لوحدها — بتعمل نفس اللي on_failure بيعمله (Sentry +
    واتساب حقيقي للإدارة عبر ADMIN_PHONE)، فمفيش فرق في المستوى ده بين task
    بترجّع استثناء لـ Celery أو task بتبتلعه داخليًا."""
    logger.error(f"[Task:{task_name}] FAILED (swallowed) exc={exc!r}")
    _try_sentry_capture(exc, task_name=task_name, extra=extra)
    _try_whatsapp_notify(task_name, exc)
