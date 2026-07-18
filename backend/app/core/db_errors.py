"""app/core/db_errors.py — تصنيف دقيق لأخطاء قاعدة البيانات المتعلقة بالأقفال.

راجع Gate 1B (مراجعة Codex الثانية): كان الكود بيحوّل أي OperationalError
لخطأ تزامن (409) عند SELECT ... FOR UPDATE NOWAIT — يعني أي مشكلة قاعدة
بيانات حقيقية تانية (فقدان الاتصال، deadlock، مشكلة سيرفر) كانت بتتغطى
بصمت بخطأ "الصف مشغول" مضلّل بدل ما توصل كخطأ حقيقي لـ secure 500 handler.
الدالة هنا بتتحقق من SQLSTATE الفعلي (55P03 = lock_not_available، الكود
اللي PostgreSQL بيرجّعه حصريًا لـ NOWAIT/timeout lock contention) قبل ما
تسمح بتحويل الخطأ لدومين exception — أي SQLSTATE تاني (أو مفيش sqlstate
خالص، زي أي OperationalError عادي على SQLite) لازم يفضل يتصعّد زي ما هو.
"""
from sqlalchemy.exc import OperationalError

LOCK_NOT_AVAILABLE_SQLSTATE = "55P03"


def is_lock_not_available(exc: OperationalError) -> bool:
    """True فقط لو الخطأ فعليًا PostgreSQL SQLSTATE 55P03 (lock_not_available
    — نتيجة SELECT ... FOR UPDATE NOWAIT على صف مقفول بالفعل). بيتحقق من
    ``exc.orig.sqlstate`` (psycopg يعيّنها تلقائيًا) بدل افتراض إن أي
    OperationalError معناها قفل مشغول."""
    return getattr(getattr(exc, "orig", None), "sqlstate", None) == LOCK_NOT_AVAILABLE_SQLSTATE
