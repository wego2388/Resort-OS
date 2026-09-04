"""
tests/test_tasks/test_tasks_package_registers_models.py

باج إنتاج حقيقي (2026-08-24، REL-20 follow-up): `timeshare-mark-overdue`
(أول task في جدول اليوم بيلمس عمود عنده ForeignKey("users.id") حقيقي —
`timeshare_contracts.cancelled_by`) كان بيفشل باستمرار على الإنتاج بـ
`sqlalchemy.exc.NoReferencedTableError`، رغم إن نفس الاستعلام بالظبط بيعدّي
عادي في كل باقي الاختبارات هنا. السبب: باقي الاختبارات كلها بتمرّ عبر
conftest.py اللي بيستورد `app.main` (وبالتبعية كل موديولات التطبيق، بما
فيها `app.core.kernel.models.user.User`) — بينما عملية الـ Celery worker
الحقيقية **لا تستورد `app.main` خالص**، بتستورد `app.tasks` بس (استيرادات
كل ملفات tasks/*.py مُؤجَّلة جوه function bodies عمدًا لتخفيف الـstartup).

الاختبار ده بيحاكي دقيقًا عملية الـ worker الحقيقية: عملية Python منفصلة
تمامًا بتستورد `app.tasks` بس (زي ما `app.celery_app` بيعمل بالظبط)، من
غير أي مرور على `app.main` أو conftest.py fixtures خالص — لو الباج يرجع،
الاختبار ده هيفشل حتى لو باقي كل اختبارات المشروع عدّت عادي.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_importing_tasks_package_alone_registers_users_table():
    """يحاكي بالظبط عملية Celery worker: `import app.tasks` بس (نفس ما
    `app.celery_app` بيعمله)، بدون `app.main` خالص، ثم يتأكد إن
    `sqlalchemy.orm.configure_mappers()` بينجح — لو `users` مش مُسجَّلة،
    ده هيرمي NoReferencedTableError لأي موديول عنده ForeignKey("users.id")
    حقيقي (credit/core/hr/timeshare)."""
    script = """
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_tasks_isolated.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-chars-here-xxxx")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6381/0")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("RESORT_NAME", "Test Resort")
os.environ.setdefault("DEFAULT_CURRENCY", "EGP")
os.environ.setdefault("VAT_PERCENTAGE", "14.0")
os.environ.setdefault("SERVICE_CHARGE_PERCENTAGE", "12.0")
os.environ.setdefault("TIMEZONE", "Africa/Cairo")
os.environ.setdefault("ETA_ENABLED", "false")
os.environ.setdefault("SURVEY_TOKEN_SECRET", "test-survey-secret-minimum-32-chars-xx")
os.environ.setdefault("TIMESHARE_PORTAL_TOKEN_SECRET", "test-timeshare-portal-secret-minimum-32-chars-xxxx")

import app.celery_app  # noqa: F401 — نفس أول import بيعمله worker حقيقي
from sqlalchemy.orm import configure_mappers
configure_mappers()  # هيرمي NoReferencedTableError لو users مش مسجّلة
print("OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"استيراد app.tasks لوحده فشل في تسجيل موديلات users — "
        f"stdout={result.stdout!r} stderr={result.stderr[-2000:]!r}"
    )
    assert "OK" in result.stdout
