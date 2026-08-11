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
from datetime import datetime, timezone
from typing import Iterator, Optional

from sqlalchemy import event
from sqlalchemy.orm import Session

_scenario_now: ContextVar[Optional[datetime]] = ContextVar("_scenario_now", default=None)


def _stamp_scenario_timestamps(session: Session, _flush_context, _instances) -> None:
    """SQLAlchemy `before_flush` — بيدمغ created_at/updated_at بوقت
    السيناريو النشط (لو موجود) بدل ما يسيبهم لـserver_default=func.now()
    (وقت تنفيذ الأداة الحقيقي، مش تاريخ الحدث التاريخي). راجع OPS-DATA-02
    §9.2: "DB created_at/updated_at للأطفال والسجلات التابعة لا تبقى
    بتاريخ التطبيق". مسجَّل globally على Session لكنه no-op تمامًا برّه
    أي scenario_clock نشط (get_scenario_now() فاضية) — صفر تأثير على أي
    استخدام عادي للتطبيق."""
    now = get_scenario_now()
    if now is None:
        return
    naive_now = now.astimezone(timezone.utc).replace(tzinfo=None)
    for obj in session.new:
        if hasattr(obj, "created_at"):
            obj.created_at = naive_now
        if hasattr(obj, "updated_at"):
            obj.updated_at = naive_now
    for obj in session.dirty:
        if hasattr(obj, "updated_at"):
            obj.updated_at = naive_now


event.listen(Session, "before_flush", _stamp_scenario_timestamps)


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


def scenario_utcnow() -> datetime:
    """بديل مباشر لـ`datetime.utcnow()` (naive UTC، نفس الـcontract بالظبط)
    بس بيحترم scenario_clock لو نشط. باج حقيقي حي اتكشف (2026-08-10):
    `leasing.crud`/`timeshare.crud`'s `payment.paid_at = datetime.utcnow()`
    كان بيسجّل وقت تشغيل أداة الاستيراد الحقيقي (النهاردة) مش تاريخ يوليو
    التاريخي اللي جوه scenario_clock — `_stamp_scenario_timestamps`'s
    before_flush hook بيدمغ بس created_at/updated_at أوتوماتيكيًا، مش أي
    عمود business-meaning تاني زي paid_at بيتحط يدويًا في كود التطبيق.
    النتيجة: `/analytics/revenue`'s فلترة `paid_at` بمدى يوليو كانت بترجع
    صفر رغم إن الدفعات موجودة فعليًا — كل عمود مماثل (paid_at، confirmed_at،
    إلخ) لازم يستخدم الدالة دي بدل `datetime.utcnow()` المباشرة."""
    now = get_scenario_now()
    if now is not None:
        return now.astimezone(timezone.utc).replace(tzinfo=None)
    return datetime.now(timezone.utc).replace(tzinfo=None)
