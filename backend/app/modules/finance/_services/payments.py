"""
app/modules/finance/_services/payments.py
Extracted from app/modules/finance/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.finance import crud
from app.resort_os.timezone_utils import utc_naive_to_local_date
from app.modules.finance.models import Payment
from app.modules.finance.schemas import (
    PaymentCreate,
)
from app.modules.finance._services.folios import (
    get_folio_or_404,
)
from app.modules.finance._services.shifts import (
    _lock_open_shift_or_conflict,
)
from app.modules.finance._services.posting import (
    post_simple_revenue_journal,
)


def add_payment(db: Session, folio_id: int, data: PaymentCreate, cashier_id: Optional[int] = None) -> Payment:
    """⚠️ باج حقيقي اتصلح هنا (2026-07-07، فجوة معمارية موثّقة في CLAUDE.md
    §18): تحصيل دفعة فوليو (Charge to Room settled at checkout) عمره ما كان
    بيرحّل أي قيد محاسبي خالص — الكاش المحصّل فعليًا من الضيف كان غير مرئي
    تمامًا في دفتر الأستاذ. السبب الأصلي: مطعم/كافيه/شاطئ بيتجاهلوا ترحيل
    الإيراد وقت البيع لو الطلب محمّل على فوليو (عشان الإيراد يتسجّل "لاحقًا
    وقت التسوية" حسب التعليق القديم) — لكن التسوية نفسها (هنا) عمرها ما
    كانت بترحّل حاجة. الحل: Dr Cash(1100)/Cr ذمم الفوليو(1150) هنا — نظير
    Dr ذمم الفوليو(1150)/Cr إيراد الموديول اللي بيترحّل وقت إنشاء الشحنة
    نفسها (راجع restaurant/cafe/beach services._post_*_folio_charge_journal)."""
    folio = get_folio_or_404(db, folio_id)
    # ⚠️ باج حقيقي كان هنا (اتصلح 2026-07-28): folio_id/branch_id بيتحققوا
    # ويتسعّروا هنا من الـ path (folio_id فوق، folio.currency تحت) لكن
    # crud.create_payment كانت بتخزّن وترحّل بـ data.folio_id/data.branch_id
    # الخام من جسم الطلب — لو مختلفين عن الـ path، الدفعة بتتسجّل وتترحّل
    # على فوليو/فرع مختلف تمامًا عن اللي اتحقق منه فعليًا فوق (نفس فئة باج
    # cashier_id تحت اللي كان متصلح من قبل). نوفّق الاتنين على قيمة الـ path
    # الموثوقة دايمًا، بالظبط زي cashier_id.
    data = data.model_copy(update={"folio_id": folio_id, "branch_id": folio.branch_id})
    if cashier_id and not data.cashier_id:
        data = data.model_copy(update={"cashier_id": cashier_id})
    shift_id = None
    if data.cashier_id:
        open_shift = _lock_open_shift_or_conflict(db, data.branch_id, data.cashier_id)
        if open_shift:
            shift_id = open_shift.id
    # عملة الدفعة موروثة من الفوليو دايماً — مش قابلة للتحديد من العميل، عشان
    # نضمن ما يحصلش mismatch بين عملة الفوليو وعملة دفعاته.
    try:
        payment = crud.create_payment(db, data, shift_id=shift_id, currency=folio.currency)
        # strict=True (2026-08-11): تحصيل دفعة فوليو من غير قيد محاسبي مقابل
        # (حساب مش معرَّف للفرع، مثلاً) لازم يفشل كامل، مش يتسجّل بصمت من
        # غير أثر محاسبي — راجع §4.
        post_simple_revenue_journal(
            db, data.branch_id, utc_naive_to_local_date(data.posted_at, settings.TIMEZONE),
            debit_account_code="1100", credit_account_code="1150",
            amount=data.amount,
            reference=f"PAY-{payment.id}",
            description=f"تحصيل دفعة فوليو #{folio_id}",
            source="folio_payment", source_id=payment.id,
            currency=folio.currency,
            strict=True, commit_cost_centers=False,
        )
        db.commit()
        db.refresh(payment)
        return payment
    except Exception:
        db.rollback()
        raise


def void_payment(db: Session, payment_id: int, voided_by: int, reason: str = "voided via API") -> Payment:
    payment = crud.get_payment(db, payment_id)
    if not payment:
        raise ValueError(f"الدفعة {payment_id} غير موجودة")
    # ⚠️ باج حقيقي كان هنا (اتصلح): مفيش أي تحقق من voided_at قبل كده — نفس
    # الدفعة كانت تتلغي مرتين (أو أكتر) من غير أي رفض، كل مرة بتكتب سطر
    # RevenueAuditLog جديد كأنها عملية إلغاء تانية حقيقية (500 → 0 تاني)
    # وبتدهس voided_at/voided_by الأصليين بقيمة/مستخدم جديد — يعني سجل مين
    # ألغى الدفعة فعليًا وإمتى كان بيتمسح بصمت، ومراجع الحسابات كان هيشوف
    # سطرين تدقيق لعملية إلغاء واحدة فعلية.
    if payment.voided_at is not None:
        raise ValueError(f"الدفعة {payment_id} ملغاة بالفعل")
    # ⚠️ باج حقيقي كان هنا (اتصلح 2026-07-28): الدالة دي بتفترض إن كل دفعة
    # لازم يكون ليها folio_id — عكس reversal ثابت Dr 1150/Cr 1100 (نظير
    # add_payment فوق بالظبط). دفعة POS مباشرة (folio_id=None — بيع نقدي
    # فوري من dining/beach عبر crud.create_direct_payment، مش تحصيل فوليو)
    # كان بيدخل هنا يعدّي من غير أي رفض (get_folio(db, None) بترجع None،
    # فحص الفوليو المغلق بيتخطّى بصمت) ويرحّل نفس القيد الغلط — الكاش يترد
    # صح، لكن النظير بيروح لذمم فوليو مش موجودة بدل حساب الإيراد الحقيقي
    # اللي اتسجّل وقت البيع، فيتضخّم رصيد "ذمم فوليو" وهمي والإيراد يفضل
    # متضخّم. إلغاء بيع مباشر لازم يعدّي من مسار الموديول نفسه (زي
    # dining.services.void_order_item) اللي بيعكس المخزون كمان، مش من هنا.
    if payment.folio_id is None:
        raise ValueError(
            f"الدفعة {payment_id} دفعة بيع مباشر (مش تحصيل فوليو) — "
            "استخدم إلغاء الصنف/الطلب من الموديول نفسه (دايننج/شاطئ)"
        )
    folio = crud.get_folio(db, payment.folio_id)
    if folio and folio.status == "closed":
        raise ValueError("لا يمكن إلغاء دفعة من فوليو مغلق")
    try:
        original_amount = payment.amount
        payment = crud.void_payment(db, payment, voided_by)
        # سجل تدقيق إلزامي — أي تغيير فعلي في قيمة دفعة/فاتورة/حجز لازم يترك أثر
        crud.create_revenue_audit_log(
            db, branch_id=payment.branch_id, entity_type="payment", entity_id=payment.id,
            old_value=original_amount, new_value=Decimal("0.00"), reason=reason, changed_by=voided_by,
        )
        # عكس قيد التحصيل اللي add_payment رحّله (Dr Cash/Cr ذمم الفوليو) — الدفعة
        # اتلغت يبقى الكاش ده ما اتحصّلش فعليًا، والذمة ترجع زي ما كانت.
        # strict=True (2026-08-11): فشل قيد العكس لازم يوقف الإلغاء كله — مش
        # يسجّل الدفعة "ملغاة" من غير أي عكس محاسبي حقيقي (راجع §4).
        from app.resort_os.timezone_utils import business_today  # noqa: PLC0415
        post_simple_revenue_journal(
            db, payment.branch_id, business_today(settings.TIMEZONE),
            debit_account_code="1150", credit_account_code="1100",
            amount=original_amount,
            reference=f"PAY-VOID-{payment.id}",
            description=f"إلغاء دفعة فوليو #{payment.folio_id}",
            source="folio_payment_void", source_id=payment.id,
            currency=payment.currency,
            strict=True, commit_cost_centers=False,
        )
        db.commit()
        db.refresh(payment)
        return payment
    except Exception:
        db.rollback()
        raise
