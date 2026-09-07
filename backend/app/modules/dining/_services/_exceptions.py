"""
app/modules/dining/_services/_exceptions.py
Extracted from app/modules/dining/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations



class OrderPaymentConcurrencyError(Exception):
    """صف الطلب مشغول بعملية دفع أخرى (SELECT FOR UPDATE NOWAIT فشل) — 409
    ORDER_PAYMENT_IN_PROGRESS (راجع خطة Gate 1B)."""


class OrderAlreadyPaidError(Exception):
    """الطلب اتدفع بالفعل — اتكشف تحت قفل صف الطلب نفسه، مش من قراءة سابقة
    غير مقفولة — 409 ORDER_ALREADY_PAID (راجع خطة Gate 1B)."""


class InvalidOrderTotalError(Exception):
    """إجمالي الطلب صفر أو سالب وقت محاولة تحويله لـ "مدفوع" — 400
    INVALID_ORDER_TOTAL (راجع خطة Gate 1B)."""


class InvalidPaymentMethodError(Exception):
    """تناقض بين payment_method وحالة الفوليو (Gate 1B، مراجعة Codex
    الثانية) — 400 INVALID_PAYMENT_METHOD. القاعدة: order.folio_id
    (تحويل فعلي على فوليو ضيف) وpayment_method="room" لازم يتطابقوا
    دايمًا، مينفعش نرحّل قيد فوليو بينما payment_method بيدّعي كاش/بطاقة/
    محفظة، ولا العكس (طلب "room" من غير فوليو حقيقي أصلاً)."""


class IdempotencyConflictError(Exception):
    """نفس Idempotency-Key اتبعت لطلب/بنية دفع مختلفة عن أول استخدام لها
    (Gate 4A) — 409 IDEMPOTENCY_KEY_CONFLICT. المفتاح بيتولّد مرة لكل محاولة
    منطقية ويُعاد استخدامه عند retry بنفس النية فقط؛ إعادة استخدامه لنية
    مختلفة غلط عميل واضح لازم يترفض بدل ما يرجّع نتيجة أول محاولة بالغلط."""


class NoOpenShiftError(Exception):
    """محاولة تحصيل tender مباشر (كاش/بطاقة/محفظة) من غير وردية مفتوحة لنفس
    الكاشير والفرع (Gate 4A) — 409 NO_OPEN_SHIFT. الدفع المباشر لازم يُنسب
    لوردية مفتوحة عشان يظهر في تقرير الوردية ومطابقة الكاش؛ من غيرها الكاش
    المحصّل هيبقى غير منسوب (orphaned) — نفس القاعدة اللي كانت مفقودة تمامًا
    قبل Gate 4."""


class PaymentAllocationError(Exception):
    """مجموع الـ tenders لا يساوي إجمالي الطلب بدقة Decimal، أو tender بمبلغ
    غير صالح (Gate 4A) — 400 PAYMENT_ALLOCATION_MISMATCH."""
