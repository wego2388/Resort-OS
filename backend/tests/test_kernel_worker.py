"""
tests/test_kernel_worker.py
wagdy.md T-03 — معظم Celery tasks في app/tasks/ بتلف الجسم كله بـ
try/except Exception وبتبلع الخطأ بـ logger.error() بس، من غير ما ترجّعه
تاني — يعني CoreTask.on_failure (اللي أصلاً بيعمل Sentry capture) عمره ما
كان بيتفعّل ليها. الإصلاح: app.core.kernel.worker.notify_task_failure()
دالة مشتركة (مش مكررة لكل task) بتُستدعى من جوه أي except block بيبتلع
خطأ نهائي — بتعمل Sentry capture. (كانت بتبعت واتساب حقيقي للإدارة كمان —
بعد إلغاء قناة الواتساب للتنبيهات الإدارية العامة، القناة الوحيدة الباقية
هنا هي Sentry.)
"""
from __future__ import annotations

import app.core.kernel.sentry as sentry_module


class TestNotifyTaskFailure:
    def test_sends_sentry_on_failure(self, monkeypatch):
        from app.core.kernel.worker import notify_task_failure

        sentry_calls = []
        monkeypatch.setattr(
            sentry_module, "capture_exception",
            lambda exc, **kw: sentry_calls.append((exc, kw)),
        )

        exc = ValueError("قسط ملكية جزئية فشل الحساب")
        notify_task_failure("app.tasks.timeshare_tasks.mark_overdue", exc)

        assert len(sentry_calls) == 1
        captured_exc, kwargs = sentry_calls[0]
        assert captured_exc is exc
        assert kwargs["tags"] == {"task": "app.tasks.timeshare_tasks.mark_overdue"}

    def test_sentry_failure_does_not_raise(self, monkeypatch):
        """فشل Sentry نفسها (SDK مش متثبّت مثلاً) ميرميش استثناء للـ caller."""
        from app.core.kernel.worker import notify_task_failure

        def _boom(exc, **kw):
            raise RuntimeError("sentry not configured")
        monkeypatch.setattr(sentry_module, "capture_exception", _boom)

        # لازم ميرميش استثناء للـ caller (الـ task نفسها) رغم فشل Sentry
        notify_task_failure("some.task", ValueError("original error"))


class TestCoreTaskOnFailure:
    def test_on_failure_captures_sentry(self, monkeypatch):
        """CoreTask.on_failure — المسار اللي استثناؤه بيوصل فعليًا لـ Celery
        (بما فيه بعد استنفاد self.retry) — لازم يعمل Sentry capture."""
        from app.core.kernel.worker import CoreTask

        sentry_calls = []
        monkeypatch.setattr(
            sentry_module, "capture_exception",
            lambda exc, **kw: sentry_calls.append((exc, kw)) or "evt-id",
        )

        task = CoreTask.__new__(CoreTask)  # instantiate without Celery app binding
        task.name = "app.tasks.finance_tasks.check_due_reminders"
        task.on_failure(RuntimeError("DB down"), "task-id-123", (), {}, None)

        assert len(sentry_calls) == 1
        assert sentry_calls[0][1]["tags"] == {"task": "app.tasks.finance_tasks.check_due_reminders"}


class TestSilentFailureVisibility:
    """مراجعة Codex 2026-08-31 (SEC-13): _try_sentry_capture كانت بتتجاهل
    نتيجة capture_exception تمامًا — لو Sentry مش مُعدّة (None، مش استثناء)،
    الفشل ده كان يختفي بصمت فوق فشل المهمة الأصلي نفسه. دلوقتي لازم يتسجّل
    تحذير واضح في اللوج (monkeypatch على logger.warning نفسها، مش caplog،
    لأن loguru مش بيتوجّه لـstdlib logging افتراضيًا)."""

    def test_sentry_not_configured_logs_warning(self, monkeypatch):
        from app.core.kernel.worker import _try_sentry_capture, logger

        monkeypatch.setattr(sentry_module, "capture_exception", lambda exc, **kw: None)
        warnings = []
        monkeypatch.setattr(logger, "warning", lambda msg: warnings.append(msg))
        _try_sentry_capture(ValueError("boom"), task_name="some.task")
        assert any("Sentry غير مُعدّة" in w for w in warnings)
