"""app/resort_os/clock.py — Clock قابل للحقن لسيناريوهات البيانات التاريخية.

HIST-01 (OPS-DATA-02 §9.2): توليد بيانات يوليو 2026 في أغسطس (أو أي وقت
لاحق) يحتاج كل مسارات local_today/local_now/business_today تفكر إنها فعليًا
بتشتغل وقت الحدث التاريخي، مش وقت التشغيل الحقيقي — وإلا قيود يوليو هتترحّل
بتاريخ أغسطس (entry_date/created_at/paid_at...) رغم إن البيانات المصدرية
(check_in/due_date/إلخ) بتاريخ يوليو الصحيح.

الحل هنا: ContextVar override بديل عن نداء الوقت الحقيقي، مش:
- monkeypatch مؤقت لـ datetime.now — بيفضل أثره لو استثناء وقع وسط العملية
  ومنسيش يترجع (خطر حقيقي على أي كود تاني شغال بالتوازي في نفس الـ process).
- تعديل SQL بعد الإنشاء (UPDATE شامل على created_at) — بيكسر أي منطق بيعتمد
  على الوقت وقت الحدث نفسه (GL posting، قفل فترة محاسبية، إلخ)، ومينفعش
  يترحّل بأثر رجعي على قيود اتترحّلت فعلًا بمنطق مختلف.

ContextVar (مش متغيّر global عادي) عشان thread/async-safe فعليًا — مهم لأن
FastAPI/Celery ممكن يشغّلوا طلبات/tasks تانية بالتوازي في نفس الـ process،
ومحتاجين الـ override يفضل معزول تمامًا لكل سياق تنفيذ (context) لوحده.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Iterator, Optional

_scenario_now: ContextVar[Optional[datetime]] = ContextVar("_scenario_now", default=None)


@contextmanager
def scenario_clock(fixed_now: datetime) -> Iterator[None]:
    """يحقن وقت ثابت (لازم يكون timezone-aware) لكل نداءات
    timezone_utils.local_now/local_today/business_today جوه الـ block ده —
    بغض النظر عن عمق الاستدعاء (أي دالة service/crud بتنادي الدوال دي
    بتورّث الوقت المحقون تلقائيًا). الوقت الحقيقي بيرجع تلقائيًا عند الخروج
    من الـ block حتى لو استثناء وقع (finally). Nesting مدعوم — أقرب context
    بيفوز، والقديم بيرجع عند الخروج من الداخلي.

    ⚠️ CLI الاستيراد التاريخي هو المستخدم الوحيد المقصود لده — استخدامه في
    أي مسار HTTP عادي معناه سماح مستخدم عادي بتزوير توقيت عملياته، وده
    بالظبط اللي §9.2 بيمنعه صراحةً ("event_at داخلي وليس query عامًا يسمح
    للمستخدم العادي بالـbackdate")."""
    if fixed_now.tzinfo is None:
        raise ValueError("scenario_clock يحتاج datetime مع tzinfo صريح (timezone-aware)")
    token = _scenario_now.set(fixed_now)
    try:
        yield
    finally:
        _scenario_now.reset(token)


def get_scenario_now() -> Optional[datetime]:
    """الوقت المحقون حاليًا لو موجود جوه scenario_clock، وإلا None (يعني
    استخدم الوقت الحقيقي — هو الافتراضي دايمًا برّه أداة الاستيراد)."""
    return _scenario_now.get()
