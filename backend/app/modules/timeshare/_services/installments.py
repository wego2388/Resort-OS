"""app/modules/timeshare/_services/installments.py — installment row
locking, collection, and its journal/audit trail."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.modules.timeshare import crud
from app.modules.timeshare.models import TimeshareContract, TimeshareInstallment
from app.modules.timeshare.schemas import PayInstallmentRequest

from ._exceptions import PaymentConflictError


def _lock_installment_or_raise(db: Session, inst_id: int) -> TimeshareInstallment:
    """⚠️ باج حقيقي كان هنا (اتصلح 2026-07-28، اتأكد بريبرو حي على حالتين
    منفصلتين تدويًا قبل الإصلاح): pay_installment كانت بتقرا/تعدّل paid_amount
    من غير أي قفل صف خالص — تحصيلين متزامنين (كاشيرين مختلفين بيسجّلوا دفعة
    على نفس القسط في نفس اللحظة) كانوا يقروا نفس paid_amount القديم، وآخر
    commit يمسح أثر التحصيل التاني بصمت من غير أي خطأ — فلوس محصّلة فعليًا
    كانت بتختفي من الدفاتر. راجع beach._lock_inventory_or_raise لنفس النمط."""
    try:
        locked = crud.lock_installment_for_update(db, inst_id)
    except OperationalError as exc:
        db.rollback()
        raise PaymentConflictError(
            "القسط مقفول الآن بعملية تحصيل أخرى — حاول تاني خلال لحظات"
        ) from exc
    if not locked:
        raise ValueError(f"القسط {inst_id} غير موجود")
    return locked


def pay_installment(
    db: Session,
    inst_id: int,
    req: PayInstallmentRequest,
    *,
    collected_by: int,
    enforce_cash_shift: bool = True,
) -> TimeshareInstallment:
    """⚠️ 3 باجات حقيقية اتصلحوا هنا (اتكشفوا أثناء اختبار حي كمدير خدمة عملاء
    ملكية جزئية):
    1. مفيش أي تحقق من حالة العقد — كان ممكن تسجّل تحصيل قسط على عقد **ملغي**
       أو **منتهي** فعليًا (العقد اتلغى بس القسط المرتبط بيه فضل قابل للتحصيل).
    2. مفيش أي حد أقصى على المبلغ — إدخال 50,000 على قسط قيمته 10,000 كان
       بيتقبل بصمت (paid_amount بيبقى أكبر من amount، والحالة بتبقى "paid" من
       غير أي تنبيه أو تسجيل فرق) — باج مالي حقيقي، مش نظري.
    3. **الأهم**: تحصيل قسط عمره ما كان بيرحّل أي قيد يومية خالص — بعكس الدفعة
       الأولى (_post_deferred_revenue_journal بتترحّل عند إنشاء العقد فقط).
       يعني كل تحصيلات الأقساط (اللي هي معظم إيراد الملكية الجزئية على مدار سنين
       العقد) كانت غايبة تمامًا عن الدفاتر المحاسبية — مخالفة مباشرة لـ
       "Finance First" (§5.2 في CLAUDE.md بيذكر أقساط الملكية الجزئية بالاسم صراحةً).

    4. ⚠️ مراجعة Codex 2026-08-30 (H-05): ترتيب الأقفال كان معكوس مقارنة
       بـcancel_contract (بتقفل العقد الأول). هنا كان بيتقفل القسط الأول
       والعقد بيتقرا من غير قفل — ترتيب أقفال غير ثابت بين المسارين ده
       بالظبط اللي بيسمح بحالة سباق: دفع وإلغاء متزامنين ممكن الاتنين
       يعدّوا من غير ما أي واحد يشوف تأثير التاني، فيتلزّموا مع بعض
       (دفعة على عقد اتلغى، أو رد مبلغ محسوب من غير آخر تحصيل). دلوقتي
       العقد بيتقفل الأول دايمًا (نفس ترتيب cancel_contract بالظبط)."""
    inst_lookup = crud.get_installment(db, inst_id)
    if not inst_lookup:
        raise ValueError(f"القسط {inst_id} غير موجود")
    contract = crud.lock_contract_for_update(db, inst_lookup.contract_id)
    if not contract:
        raise ValueError(f"العقد المرتبط بالقسط {inst_id} غير موجود")
    inst = _lock_installment_or_raise(db, inst_id)
    try:
        if inst.status == "paid":
            raise ValueError("القسط مدفوع بالكامل مسبقاً")

        if contract.status == "cancelled":
            raise ValueError(f"العقد {contract.contract_number} ملغي — لا يمكن تحصيل أقساط عليه")
        if contract.status == "expired":
            raise ValueError(f"العقد {contract.contract_number} منتهي — لا يمكن تحصيل أقساط عليه")

        remaining = inst.amount - inst.paid_amount
        if req.paid_amount > remaining:
            raise ValueError(
                f"المبلغ المُدخَل ({req.paid_amount:,.2f} ج) أكبر من المتبقي على هذا "
                f"القسط ({remaining:,.2f} ج) — تحقّق من المبلغ قبل التسجيل"
            )

        from app.modules.finance.services import record_external_payment  # noqa: PLC0415
        collection = record_external_payment(
            db,
            branch_id=contract.branch_id,
            amount=req.paid_amount,
            payment_method=req.payment_method,
            collector_id=collected_by,
            reference=f"TS-INST-{contract.contract_number}-{inst.installment_no}",
            source="timeshare_installment",
            source_id=inst.id,
            require_cash_shift=enforce_cash_shift,
        )
        obj = crud.pay_installment(db, inst, req)
        # strict=True (2026-08-11): تحصيل قسط من غير قيد محاسبي مقابل يفشل
        # كامل، مش يتسجّل بصمت من غير أثر محاسبي — راجع _post_installment_
        # payment_journal.
        _post_installment_payment_journal(
            db,
            contract,
            req.paid_amount,
            inst,
            req.payment_method,
            collection_payment_id=collection.id,
            collected_by=collected_by,
        )

        # سجل تدقيق — تاريخ التحصيل قابل للمراجعة والتصحيح لاحقاً
        _audit_installment_payment(db, contract, inst, req, collected_by)

        # إلغاء تجميد الحجز إن كان مفيش أي رصيد متأخر تاني (أقساط أو صيانة)
        if contract.booking_frozen and not _has_any_overdue_balance(contract):
            contract.booking_frozen = False

        db.commit()
        db.refresh(obj)
        return obj
    except Exception:
        db.rollback()
        raise


def _has_any_overdue_balance(contract: TimeshareContract) -> bool:
    """هل عند العقد أي رصيد متأخر — أقساط أو صيانة — لسه غير مسدَّد؟ مصدر
    الحقيقة الوحيد لقرار إلغاء تجميد الحجز، يستخدمه pay_installment و
    pay_maintenance_due الاتنين بدل منطق منفصل لكل واحد.

    ⚠️ باج كامن حقيقي كان في pay_installment قبل التوحيد ده: الفحص القديم
    كان بيستبعد صراحة القسط اللي اتدفع لسه (`i.id != inst_id`) — يعني لو
    دفعة جزئية سابت القسط "partial" (لسه مش مسدَّد بالكامل) وكان هو القسط
    الوحيد المتأخر، العقد كان بيتفك تجميده غلط رغم إنه لسه مديون بيه. هنا
    بنفحص الحالة الفعلية الحالية لكل الأقساط/المستحقات من غير أي استبعاد —
    وده صح لأن crud.pay_installment/pay_maintenance_due بيحدّثوا status في
    نفس الـ object (identity map) قبل ما الفحص ده يتنادى، فالحالة المعروضة
    هنا هي الحالة الصحيحة بعد الدفعة مباشرة."""
    has_overdue_installment = any(
        i.status in ("overdue", "partial") for i in contract.installments_list
    )
    has_overdue_maintenance = any(
        d.status in ("overdue", "partial") for d in contract.maintenance_dues_list
    )
    return has_overdue_installment or has_overdue_maintenance


# ⚠️ باج حقيقي كان هنا (اتصلح، نفس فئة الباج اللي اتصلح في leasing.services
# في نفس الجلسة — راجع OPS-DATA-02 §10.5 "لا تستخدم 1100 لكل طرق الدفع"):
# كل تحصيل قسط/صيانة كان بيترحّل Dr.1100 (كاش) دايمًا، حتى لو الكاشير سجّل
# payment_method="bank_transfer" أو "card" فعليًا على الصف نفسه — يعني رصيد
# حساب الكاش الفعلي كان بيتضخّم بمبالغ حوّلتها البنك، ورصيد البنك/الكارت
# مايتحرّكش خالص رغم إن التحصيل الحقيقي مكانش نقدية.
#
# مشترك مع maintenance.py (نفس منطق تحديد حساب الدفع بالضبط لتحصيل الصيانة) —
# _services.maintenance بيستورده من هنا بدل ما يكرره.
_PAYMENT_METHOD_DEBIT_ACCOUNT = {
    "cash": "1100", "bank_transfer": "1110", "card": "1120", "other": "1100",
}


def _post_installment_payment_journal(
    db: "Session",
    contract: "TimeshareContract",
    paid_amount,
    inst: "TimeshareInstallment",
    payment_method: str,
    *,
    collection_payment_id: int,
    collected_by: int,
) -> None:
    """Dr. Cash/Bank/Card (حسب طريقة الدفع الفعلية) / Cr. إيرادات عقود
    الملكية الجزئية (4600) عند تحصيل أي قسط — نفس منطق _post_deferred_revenue_
    journal بالظبط بس لكل تحصيل قسط، مش الدفعة الأولى بس (راجع تعليق تلك
    الدالة في contracts.py لتفاصيل باج حساب 2300)."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    debit_code = _PAYMENT_METHOD_DEBIT_ACCOUNT.get(payment_method or "cash", "1100")
    post_simple_revenue_journal(
        db, contract.branch_id, business_today(settings.TIMEZONE),
        debit_account_code=debit_code, credit_account_code="4600",
        amount=paid_amount,
        reference=f"TS-INST-{contract.contract_number}-{inst.installment_no}",
        description=f"تحصيل قسط رقم {inst.installment_no} — {contract.contract_number}",
        source="timeshare", source_id=collection_payment_id,
        created_by=collected_by,
        cost_center_code="TS",
        strict=True, commit_cost_centers=False,
    )


def _audit_installment_payment(
    db: "Session",
    contract: "TimeshareContract",
    inst: "TimeshareInstallment",
    req: "PayInstallmentRequest",
    collected_by: int,
) -> None:
    """يسجّل AuditLog لكل تحصيل قسط — يتيح مراجعة تاريخ التحصيل الكامل
    وتصحيح أي خطأ لاحقاً (تاريخ، طريقة دفع، مبلغ). `transfer_unit` عنده
    نفس السجل — الأقساط كانت الاستثناء الوحيد."""
    import json as _json  # noqa: PLC0415
    from app.modules.core.crud import create_audit_log  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415

    old_data = _json.dumps({
        "status": "pending" if inst.status == "partial" else inst.status,
        "paid_amount": float(inst.paid_amount - req.paid_amount),
    }, ensure_ascii=False)
    new_data = _json.dumps({
        "status": inst.status,
        "paid_amount": float(inst.paid_amount),
        "payment_method": req.payment_method,
        "receipt_number": req.receipt_number,
        "amount_paid_now": float(req.paid_amount),
    }, ensure_ascii=False)

    create_audit_log(db, AuditLogCreate(
        user_id=collected_by,
        branch_id=contract.branch_id,
        action="pay_installment",
        entity_type="timeshare_installment",
        entity_id=inst.id,
        old_data=old_data,
        new_data=new_data,
    ))


def list_installments(
    db: Session, branch_id: int,
    status: Optional[str] = None, contract_id: Optional[int] = None,
    month: Optional[str] = None, search: Optional[str] = None, limit: int = 200,
) -> dict:
    items = crud.list_all_installments(db, branch_id, status, contract_id, month, search, limit)
    return {
        "installments": items,
        "total": len(items),
        "summary": crud.installments_summary(db, branch_id),
    }
