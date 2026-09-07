"""
app/modules/finance/_services/_exceptions.py
Extracted from app/modules/finance/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations



class FinancialConfigurationError(Exception):
    """Gate 1B (Financial Atomicity): حساب GL أو مركز تكلفة مطلوب غير معرَّف
    للفرع، حتى بعد محاولة التجهيز التلقائي (ensure_default_cost_centers) —
    503، مش خطأ عميل (400) ولا database error عشوائي (500): إعداد ناقص
    محتاج محاسب/مدير يظبطه، مش غلطة في الطلب نفسه. تُرفع فقط من مسارات
    strict=True الصريحة (post_simple_revenue_journal، inventory._post_cogs_
    journal) — كل الاستدعاءات الحالية التانية (strict=False الافتراضي)
    تحافظ على سلوكها القديم تمامًا (ابتلاع صامت، ترجع None)."""


# ── Folio ─────────────────────────────────────────────────────────────

class FolioClosedError(ValueError):
    """محاولة إضافة شحنة لفوليو مقفول/ملغي — بتترفض تحت قفل الفوليو نفسه
    عشان تمنع سباق حقيقي بين إضافة شحنة وتسوية/إقفال نفس الفوليو في نفس
    اللحظة (راجع خطة Gate 1B، بند قفل الفوليو). يرث من ValueError (مراجعة
    Codex الثانية) عشان أي router قديم بيعمل ``except ValueError`` عام
    يفضل يمسكها ويترجمها 400 بدل ما تتسرب كـ 500 غير متوقع."""
