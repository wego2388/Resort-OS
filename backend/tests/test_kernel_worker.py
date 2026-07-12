"""
tests/test_kernel_worker.py
wagdy.md T-03 — معظم Celery tasks في app/tasks/ بتلف الجسم كله بـ
try/except Exception وبتبلع الخطأ بـ logger.error() بس، من غير ما ترجّعه
تاني — يعني CoreTask.on_failure (اللي أصلاً بيعمل Sentry capture) عمره ما
كان بيتفعّل ليها. الإصلاح: app.core.kernel.worker.notify_task_failure()
دالة مشتركة (مش مكررة لكل task) بتُستدعى من جوه أي except block بيبتلع
خطأ نهائي — بتعمل Sentry capture + تنبيه واتساب حقيقي للإدارة. CoreTask.
on_failure نفسه اتحدّث كمان يبعت واتساب (مش Sentry بس زي قبل كده) عشان أي
فشل حقيقي يوصل لـ Celery (بما فيه بعد استنفاد self.retry) يوصل بردو.
"""
from __future__ import annotations

import app.core.kernel.whatsapp as wa_module
import app.core.kernel.sentry as sentry_module


class TestNotifyTaskFailure:
    def test_sends_whatsapp_and_sentry_on_failure(self, monkeypatch):
        from app.core.kernel.worker import notify_task_failure

        whatsapp_calls = []
        monkeypatch.setattr(wa_module, "notify_admin", lambda msg: whatsapp_calls.append(msg))

        sentry_calls = []
        monkeypatch.setattr(
            sentry_module, "capture_exception",
            lambda exc, **kw: sentry_calls.append((exc, kw)),
        )

        exc = ValueError("قسط تايم شير فشل الحساب")
        notify_task_failure("app.tasks.timeshare_tasks.mark_overdue", exc)

        assert len(whatsapp_calls) == 1
        assert "mark_overdue" in whatsapp_calls[0]
        assert "قسط تايم شير" in whatsapp_calls[0]

        assert len(sentry_calls) == 1
        captured_exc, kwargs = sentry_calls[0]
        assert captured_exc is exc
        assert kwargs["tags"] == {"task": "app.tasks.timeshare_tasks.mark_overdue"}

    def test_whatsapp_failure_does_not_raise(self, monkeypatch):
        """notify_admin نفسها ممكن تفشل (مثلاً ADMIN_PHONE مش متضبط، أو
        Twilio مش شغال) — لازم ميوقفش تسجيل الفشل الأصلي في Sentry."""
        from app.core.kernel.worker import notify_task_failure

        def _boom(msg):
            raise RuntimeError("WhatsApp API down")
        monkeypatch.setattr(wa_module, "notify_admin", _boom)

        sentry_calls = []
        monkeypatch.setattr(
            sentry_module, "capture_exception",
            lambda exc, **kw: sentry_calls.append(exc),
        )

        # لازم ميرميش استثناء للـ caller (الـ task نفسها) رغم فشل الواتساب
        notify_task_failure("some.task", ValueError("original error"))
        assert len(sentry_calls) == 1

    def test_sentry_failure_does_not_raise(self, monkeypatch):
        """نفس المنطق بالعكس — فشل Sentry (SDK مش متثبّت مثلاً) ميمنعش
        محاولة إرسال تنبيه الواتساب."""
        from app.core.kernel.worker import notify_task_failure

        def _boom(exc, **kw):
            raise RuntimeError("sentry not configured")
        monkeypatch.setattr(sentry_module, "capture_exception", _boom)

        whatsapp_calls = []
        monkeypatch.setattr(wa_module, "notify_admin", lambda msg: whatsapp_calls.append(msg))

        notify_task_failure("some.task", ValueError("boom"))
        assert len(whatsapp_calls) == 1


class TestCoreTaskOnFailure:
    def test_on_failure_sends_whatsapp(self, monkeypatch):
        """CoreTask.on_failure — المسار اللي استثناؤه بيوصل فعليًا لـ Celery
        (بما فيه بعد استنفاد self.retry) — لازم يبعت واتساب زي notify_task_
        failure بالظبط، مش Sentry بس زي قبل التعديل."""
        from app.core.kernel.worker import CoreTask

        whatsapp_calls = []
        monkeypatch.setattr(wa_module, "notify_admin", lambda msg: whatsapp_calls.append(msg))
        monkeypatch.setattr(sentry_module, "capture_exception", lambda exc, **kw: "evt-id")

        task = CoreTask.__new__(CoreTask)  # instantiate without Celery app binding
        task.name = "app.tasks.finance_tasks.check_due_reminders"
        task.on_failure(RuntimeError("DB down"), "task-id-123", (), {}, None)

        assert len(whatsapp_calls) == 1
        assert "check_due_reminders" in whatsapp_calls[0]
