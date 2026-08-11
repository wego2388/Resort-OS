"""app/modules/leasing/services.py"""
from __future__ import annotations

import json
import logging

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.leasing import crud

logger = logging.getLogger(__name__)
from app.modules.leasing.models import LeaseContract, LeasePayment, TenantCashLog
from app.modules.leasing.schemas import (
    LeaseContractCreate, LeaseContractUpdate, PayLeaseRequest, TenantCashLogCreate,
)
from app.resort_os.timeshare_engine import calculate_lease_penalty, generate_lease_monthly_schedule
from app.resort_os.timezone_utils import local_today
# ⚠️ باج توقيت من نفس الفئة الموثّقة في timezone_utils.py (KDS/PMS/HR): كل
# استخدامات date.today()/_date.today() هنا كانت بترجع تاريخ السيرفر (UTC غالبًا
# في الإنتاج) مش تاريخ المنتجع الفعلي (Africa/Cairo) — قرب منتصف ليل القاهرة
# (UTC+3) كان ممكن يحسب "أيام التأخير" بتاريخ غلط بيوم كامل، وهو بالظبط
# الحساب اللي بيحدد شريحة الغرامة (5%/10%) عند حدود الـ8/30 يوم. اتصلح
# بالاعتماد على local_today(settings.TIMEZONE) زي باقي الموديولات
# (pms/timeshare/hr) بدل تكرار نفس الباج تاني هنا.

# عقوبة تأخر الإيجار (resort-os-docs/12-TIMESHARE-COMPLETE.md § "عقوبة تأخر
# الإيجار"): 5% للتأخير 8-30 يوم، 10% لأكثر من 30 يوم. القيم القديمة هنا
# (3/15 يوم) كانت غير مطابقة للسبيك — اتصححت 2026-07-01 بعد مراجعة Task B.


def days_until_expiry(contract: LeaseContract, today: date | None = None) -> int:
    """أيام متبقية حتى نهاية عقد الإيجار (سالب لو العقد منتهي بالفعل بتاريخه).
    نفس فكرة `VisitWindow.days_until` في `timeshare_engine.py` — لازم `today`
    يتحسب بتوقيت المنتجع (Africa/Cairo)، مش تاريخ السيرفر."""
    today = today or local_today(settings.TIMEZONE)
    return (contract.end_date - today).days


def get_tenant_aging(db: Session, branch_id: int) -> list[dict]:
    return crud.get_tenant_aging(db, branch_id, local_today(settings.TIMEZONE))


def list_expiring_soon(db: Session, branch_id: int, within_days: int = 30) -> list[LeaseContract]:
    """عقود إيجار نشطة هتنتهي خلال `within_days` يوم القادمة — wagdy.md بند #28:
    عقود قربت تنتهي كانت من غير أي تنبيه، مدير الإيجارات بيكتشفها بالصدفة بس.
    اتستخدمت من `GET /leasing/contracts?expiring_within_days=` لإظهار تنبيه
    فوري (real-time، مش مخزّن/stale) في LeasingView.vue."""
    today = local_today(settings.TIMEZONE)
    return crud.list_contracts_expiring_soon(db, branch_id, today, within_days)


def get_contract_or_404(db: Session, contract_id: int) -> LeaseContract:
    c = crud.get_contract(db, contract_id)
    if not c:
        raise ValueError(f"عقد الإيجار {contract_id} غير موجود")
    return c


def create_contract(db: Session, data: LeaseContractCreate, signed_by: int) -> LeaseContract:
    if data.end_date <= data.start_date:
        raise ValueError("تاريخ الانتهاء يجب أن يكون بعد تاريخ البداية")

    contract = crud.create_contract(db, data, signed_by)

    # توليد جدول الدفعات من الـ engine
    schedule = generate_lease_monthly_schedule(
        base_rent=data.base_rent,
        increase_rate=float(data.increase_rate),
        start_date=data.start_date,
        end_date=data.end_date,
        grace_months=data.grace_months,
        billing_day=data.billing_day,
    )
    crud.create_payments(db, contract.id, schedule)

    # ⚠️ التأمين عمره ما بيترحّل هنا (راجع OPS-DATA-02 §10.5: "لا تسجل
    # security deposit كـCash بمجرد توقيع العقد؛ سجله عند receipt حقيقي") —
    # كان القيد بيترحّل هنا تلقائيًا بمجرد التوقيع حتى لو التأمين لسه ما
    # استُلمش فعليًا (Dr Cash وهمي). التسجيل الحقيقي بقى صراحةً عبر
    # confirm_deposit_received تحت، لما الكاشير/المدير يأكد الاستلام الفعلي.

    db.commit()
    db.refresh(contract)
    return contract


# طريقة الدفع → الحساب المدين الصحيح عند استلام نقدية فعلية — راجع
# OPS-DATA-02 §10.5: "لا تستخدم 1100 لكل طرق الدفع". "other" بترحّل لـ1100
# افتراضيًا (نفس منطق cash) لأنها الأكثر تحفظًا محاسبيًا لطريقة غير محددة،
# مش لأنها فعليًا نقدية.
_PAYMENT_METHOD_DEBIT_ACCOUNT = {
    "cash": "1100", "bank_transfer": "1110", "card": "1120", "other": "1100",
}


def _audit_leasing_action(
    db: Session,
    *,
    user_id: int,
    branch_id: int,
    action: str,
    entity_type: str,
    entity_id: int,
    old_data: dict | None = None,
    new_data: dict | None = None,
) -> None:
    """Append an operator-attributed audit row inside the caller transaction."""
    from app.modules.core.crud import create_audit_log  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415

    create_audit_log(db, AuditLogCreate(
        user_id=user_id, branch_id=branch_id, action=action,
        entity_type=entity_type, entity_id=entity_id,
        old_data=json.dumps(old_data, ensure_ascii=False, default=str) if old_data is not None else None,
        new_data=json.dumps(new_data, ensure_ascii=False, default=str) if new_data is not None else None,
    ))

def confirm_deposit_received(
    db: Session, contract_id: int, payment_method: str, received_by: int,
    *, enforce_cash_shift: bool = True,
) -> LeaseContract:
    """يرحّل قيد التأمين فقط عند التأكيد الفعلي لاستلامه — Dr Cash/Bank/Card
    (حسب طريقة الدفع الفعلية) / Cr تأمينات مستأجرين (2150). idempotent
    (contract.deposit_received يمنع الترحيل مرتين).

    ⚠️ 2026-08-11: strict=True + rollback على أي استثناء — قبل كده
    post_simple_revenue_journal كانت بتترحّل بـstrict=False الافتراضي
    (تبتلع فشل الحساب/العملة وترجع None بصمت)، وdeposit_received=True
    كان بيتسجّل بغض النظر — يعني ممكن يتسجّل "التأمين استُلم" فعليًا
    من غير أي قيد محاسبي حقيقي يثبته."""
    try:
        contract = get_contract_or_404(db, contract_id)
        if contract.deposit_received:
            raise ValueError(f"تأمين العقد {contract.contract_number} مُسجَّل استلامه بالفعل")
        if (contract.security_deposit or Decimal("0")) <= 0:
            raise ValueError(f"العقد {contract.contract_number} بلا تأمين مطلوب")

        from app.modules.finance.services import (  # noqa: PLC0415
            post_simple_revenue_journal, record_external_payment,
        )

        collection = record_external_payment(
            db,
            branch_id=contract.branch_id,
            amount=contract.security_deposit,
            payment_method=payment_method,
            collector_id=received_by,
            reference=f"LC-DEP-{contract.contract_number}",
            source="leasing_deposit",
            source_id=contract.id,
            require_cash_shift=enforce_cash_shift,
        )

        debit_code = _PAYMENT_METHOD_DEBIT_ACCOUNT.get(payment_method, "1100")
        post_simple_revenue_journal(
            db, contract.branch_id, local_today(settings.TIMEZONE),
            debit_account_code=debit_code, credit_account_code="2150",
            amount=contract.security_deposit,
            reference=f"LC-DEP-{contract.contract_number}",
            description=f"استلام تأمين عقد إيجار — {contract.contract_number} ({contract.tenant_name})",
            source="leasing", source_id=collection.id,
            created_by=received_by, cost_center_code="LEASE",
            strict=True, commit_cost_centers=False,
        )
        contract.deposit_received = True
        contract.deposit_received_at = datetime.now(timezone.utc)
        contract.deposit_payment_method = payment_method
        contract.deposit_received_by = received_by
        _audit_leasing_action(
            db, user_id=received_by, branch_id=contract.branch_id,
            action="confirm_deposit_receipt", entity_type="lease_contract",
            entity_id=contract.id, old_data={"deposit_received": False},
            new_data={
                "deposit_received": True, "amount": contract.security_deposit,
                "payment_method": payment_method, "payment_id": collection.id,
            },
        )
        db.commit()
        db.refresh(contract)
        return contract
    except Exception:
        db.rollback()
        raise


def _accrue_single_payment(
    db: "Session",
    payment: "LeasePayment",
    contract: "LeaseContract",
    *,
    created_by: int | None = None,
) -> None:
    """Dr ذمم مستأجرين (1260) / Cr إيرادات إيجارات تجارية (4500) — يثبت
    الإيراد عند الاستحقاق بغض النظر عن التحصيل الفعلي (OPS-DATA-02 §10.5).
    idempotent عبر payment.accrued — استدعاء تاني على نفس الدفعة no-op.

    ⚠️ 2026-08-11: strict=True — قبل كده entry كان ممكن يرجع None (فشل
    ترحيل صامت) وpayment.accrued يتسجّل True بردو، يعني استحقاق إيراد
    حقيقي بيتسجّل من غير أي قيد يثبته، وبما إن accrued=True كان بيمنع
    أي إعادة محاولة لاحقة (idempotency guard فوق)، الفجوة كانت دايمة —
    مفيش فرصة تانية تترحّل. دلوقتي: فشل الترحيل بيرفع استثناء يوقف
    accrued=True نفسه، والمحاولة القادمة (يوم تاني، أو retry يدوي) لسه
    شايفة الدفعة كـunaccrued وهتحاول تاني."""
    if payment.accrued:
        return
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    entry = post_simple_revenue_journal(
        db, contract.branch_id, payment.due_date,
        debit_account_code="1260", credit_account_code="4500",
        amount=payment.amount,
        reference=f"LSE-ACR-{payment.id:06d}",
        description=f"استحقاق إيجار — {contract.contract_number} ({contract.tenant_name})",
        source="leasing", source_id=payment.id,
        created_by=created_by if created_by is not None else (contract.signed_by or 0),
        cost_center_code="LEASE",
        strict=True, commit_cost_centers=False,
    )
    payment.accrued = True
    payment.accrual_journal_entry_id = entry.id
    db.flush()


def accrue_due_rents(
    db: Session,
    branch_id: int,
    as_of: date | None = None,
    *,
    created_by: int | None = None,
    raise_on_error: bool = False,
    commit: bool = True,
) -> list[LeasePayment]:
    """يرحّل استحقاق كل دفعات الإيجار اللي وصل تاريخ استحقاقها ولسه ما
    اتحقّقتش محاسبيًا (accrued=False) — بتُستدعى يوميًا من
    app.tasks.leasing_tasks.accrue_due_rents، ومن pay_payment/record_cash_log
    inline لو التحصيل حصل قبل ما المهمة اليومية تشتغل.

    ⚠️ 2026-08-11: كل دفعة بتترحّل جوه SAVEPOINT مستقل (db.begin_nested)
    — لو دفعة واحدة فشلت (حساب مش معرّف، مثلاً)، الدفعات التانية الناجحة
    في نفس الدفعة اليومية (batch) لازم تفضل متسجّلة، مش كل الـbatch يترفض
    بسبب عقد واحد بمشكلة إعداد. الفشل بيتسجّل بوضوح ويكمل للدفعة الجاية،
    مش يبتلع بصمت (نفس مبدأ الـstrict فوق، بس على مستوى العنصر الواحد
    داخل معالجة دفعية مش طلب HTTP فردي)."""
    today = as_of or local_today(settings.TIMEZONE)
    due = crud.list_unaccrued_due_payments(db, branch_id, today)
    accrued_payments: list[LeasePayment] = []
    for payment in due:
        contract = crud.get_contract(db, payment.contract_id)
        if not contract:
            continue
        try:
            with db.begin_nested():
                _accrue_single_payment(
                    db, payment, contract, created_by=created_by,
                )
            accrued_payments.append(payment)
        except Exception:
            logger.error(
                "accrue_due_rents: فشل استحقاق دفعة %s (عقد %s) — تحتاج مراجعة يدوية",
                payment.id, contract.contract_number, exc_info=True,
            )
            if raise_on_error:
                raise
    if accrued_payments and commit:
        db.commit()
    return accrued_payments


def _post_rent_receipt_journal(
    db: "Session",
    source_obj,
    contract: "LeaseContract",
    collected_amount: Decimal,
    payment_method: str,
    *,
    collection_payment_id: int,
    collected_by: int,
) -> None:
    """Dr Cash/Bank/Card (حسب طريقة الدفع الفعلية) / Cr ذمم مستأجرين (1260)
    — تحصيل فعلي بس، بعد ما الإيراد يكون اتحقّق (accrued) بالفعل. `source_obj`
    أي صف عنده `.id` (LeasePayment أو TenantCashLog) — بيُستخدم كمرجع بس.

    ⚠️ 2026-08-11: كان فيه try/except محلي هنا بيبتلع أي استثناء (حتى لو
    strict=True كان هيتضاف بعدين) ويسجّله بس كـlog.error — يعني تحصيل
    نقدي حقيقي (paid_amount اتسجّل بالفعل في pay_payment قبل النداء ده)
    كان بيفضل مسجّل حتى لو القيد المحاسبي المقابل فشل تمامًا، من غير أي
    أثر على استجابة الطلب. اتشال الـtry/except — الاستثناء دلوقتي بيطلع
    لصاحب المعاملة الأكبر (pay_payment) اللي بيعمل rollback للعملية كلها."""
    if collected_amount <= 0:
        return
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    debit_code = _PAYMENT_METHOD_DEBIT_ACCOUNT.get(payment_method or "cash", "1100")
    post_simple_revenue_journal(
        db, contract.branch_id, local_today(settings.TIMEZONE),
        debit_account_code=debit_code, credit_account_code="1260",
        amount=collected_amount,
        reference=f"LSE-RCV-{source_obj.id:06d}",
        description=f"تحصيل إيجار — {contract.contract_number} ({contract.tenant_name})",
        source="leasing", source_id=collection_payment_id,
        created_by=collected_by, cost_center_code="LEASE",
        strict=True, commit_cost_centers=False,
    )


def _post_direct_rent_journal(
    db: "Session",
    source_obj,
    contract: "LeaseContract",
    amount: Decimal,
    payment_method: str,
    *,
    collection_payment_id: int,
    collected_by: int,
) -> None:
    """قيد واحد مباشر Dr Cash/Bank/Card / Cr إيراد — لتسويات كاش فورية
    (TenantCashLog) بدون جدول استحقاق مسبق (مركز غوص/واتر سبورت بيدفعوا
    حصة إيراد متغيّرة، مش قسط شهري ثابت له تاريخ استحقاق مسبق) — عمدًا
    من غير أي عبور على 1260 لأن مفيش ذمة سبق إثباتها هنا أصلًا.

    ⚠️ 2026-08-11: نفس إصلاح _post_rent_receipt_journal — شال try/except
    المحلي اللي كان بيبتلع الفشل، strict=True دلوقتي."""
    if amount <= 0:
        return
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    debit_code = _PAYMENT_METHOD_DEBIT_ACCOUNT.get(payment_method or "cash", "1100")
    post_simple_revenue_journal(
        db, contract.branch_id, local_today(settings.TIMEZONE),
        debit_account_code=debit_code, credit_account_code="4500",
        amount=amount,
        reference=f"LSE-CL-{source_obj.id:06d}",
        description=f"تسوية كاش مستأجر — {contract.contract_number} ({contract.tenant_name})",
        source="leasing", source_id=collection_payment_id,
        created_by=collected_by, cost_center_code="LEASE",
        strict=True, commit_cost_centers=False,
    )


def update_contract(
    db: Session, contract_id: int, data: LeaseContractUpdate, *, updated_by: int | None = None,
) -> LeaseContract:
    contract = get_contract_or_404(db, contract_id)
    changes = data.model_dump(exclude_unset=True)
    old_status = contract.status
    obj = crud.update_contract(db, contract, data)
    if updated_by is not None and changes:
        _audit_leasing_action(
            db, user_id=updated_by, branch_id=contract.branch_id,
            action="update_contract", entity_type="lease_contract", entity_id=contract.id,
            old_data={"status": old_status},
            new_data={"status": contract.status, "changed_fields": sorted(changes)},
        )
    db.commit()
    db.refresh(obj)
    return obj


def calculate_penalty(payment: LeasePayment, as_of: date | None = None) -> Decimal:
    """يحسب الغرامة بناءً على أيام التأخير: 5% للتأخير 8-30 يوم، 10% لأكثر
    من 30 يوم (مطابق لـ resort-os-docs/12-TIMESHARE-COMPLETE.md).

    ⚠️ باج تكرار منطق حقيقي كان هنا: نسخة محلية من نفس الحساب كانت بتستخدم
    حدود >= (>=8 و>=30) بدل > (>7 و>30) المستخدمة في resort_os.timeshare_engine
    .calculate_lease_penalty — يعني دفعة متأخرة 30 يوم بالظبط كانت بتاخد غرامة
    10% غلط بدل 5% (التأخير المفروض "8-30 يوم" شامل يوم الـ30 نفسه حسب توثيق
    السبيك، والـ 10% مفروض تبدأ من يوم 31). اتصلح بالاعتماد على نسخة الـ engine
    الوحيدة (نفس اللي بينادي عليها app.tasks.leasing_tasks.mark_overdue أصلاً)
    بدل تكرار نفس القاعدة مرتين بقيم مختلفة.

    ⚠️ باج توقيت حقيقي تاني كان هنا (نفس الفئة الموثّقة في
    resort_os/timezone_utils.py — KDS/PMS/HR): `date.today()` بترجع تاريخ
    السيرفر، مش تاريخ المنتجع (Africa/Cairo). اتصلح بـ local_today() —
    مهم هنا تحديدًا لأن ده بالظبط الحساب اللي بيحدد حدود شريحة الغرامة
    (8/30 يوم)."""
    today = as_of or local_today(settings.TIMEZONE)
    if payment.status == "paid" or payment.due_date >= today:
        return Decimal("0")
    return calculate_lease_penalty(payment.amount, payment.due_date, today)


def apply_penalties(db: Session, contract_id: int) -> list[LeasePayment]:
    """يحدّث غرامات التأخير لجميع الدفعات المتأخرة."""
    get_contract_or_404(db, contract_id)  # يتحقق من وجود العقد (يرمي 404)
    payments = crud.list_payments(db, contract_id)
    updated = []
    for p in payments:
        if p.status in ("pending", "partial", "overdue"):
            penalty = calculate_penalty(p)
            if penalty != p.penalty:
                p.penalty = penalty
                if penalty > 0:
                    p.status = "overdue"
                updated.append(p)
    if updated:
        db.flush()
        db.commit()
    return updated


class PaymentConflictError(Exception):
    """دفعة إيجار مقفولة بعملية تحصيل تانية شغالة عليها دلوقتي — 409، مش 400."""


def _lock_payment_or_raise(db: Session, payment_id: int) -> LeasePayment:
    """⚠️ باج حقيقي اتصلح (2026-07-28، مرآة timeshare.services._lock_installment_or_raise):
    pay_payment كانت بتقرا/تعدّل paid_amount من غير أي قفل صف — تحصيلين
    متزامنين على نفس الدفعة كانوا يمسحوا بعض بصمت (فلوس محصّلة فعليًا
    بتختفي من غير أي خطأ)."""
    try:
        locked = crud.lock_payment_for_update(db, payment_id)
    except OperationalError as exc:
        db.rollback()
        raise PaymentConflictError(
            "الدفعة مقفولة الآن بعملية تحصيل أخرى — حاول تاني خلال لحظات"
        ) from exc
    if not locked:
        raise ValueError(f"الدفعة {payment_id} غير موجودة")
    return locked


def pay_payment(
    db: Session, payment_id: int, req: PayLeaseRequest, *, collected_by: int,
    enforce_cash_shift: bool = True,
) -> LeasePayment:
    """⚠️ نفس فئة الباجين اللي اتصلحوا قبل كده في `timeshare.services.pay_installment`
    (الموديول الشقيق)، اتكشفوا هنا كمان أثناء اختبار حي كمدير إيجارات — الكود كان
    منسوخ جزئيًا من غير الإصلاحين:
    1. مفيش أي تحقق من حالة العقد — كان ممكن تسجّل تحصيل إيجار على عقد **مفسوخ**
       أو **منتهي** فعليًا.
    2. مفيش أي حد أقصى على المبلغ — إدخال 50,000 على دفعة قيمتها 5,000 كان
       بيتقبل بصمت (paid_amount بيبقى أكبر من amount+penalty، والحالة بتبقى
       "paid" من غير أي تنبيه أو تسجيل فرق) — باج مالي حقيقي، مش نظري.
    """
    payment = _lock_payment_or_raise(db, payment_id)
    try:
        if payment.status == "paid":
            raise ValueError("الدفعة مسددة بالكامل مسبقاً")
        contract = get_contract_or_404(db, payment.contract_id)
        if contract.status == "terminated":
            raise ValueError(f"العقد {contract.contract_number} مفسوخ — لا يمكن تحصيل دفعات عليه")
        if contract.status == "expired":
            raise ValueError(f"العقد {contract.contract_number} منتهي — لا يمكن تحصيل دفعات عليه")

        remaining = payment.amount + payment.penalty - payment.paid_amount
        if req.paid_amount > remaining:
            raise ValueError(
                f"المبلغ المُدخَل ({req.paid_amount:,.2f} ج) أكبر من المتبقي على هذه "
                f"الدفعة ({remaining:,.2f} ج) — تحقّق من المبلغ قبل التسجيل"
            )

        previous_status = payment.status
        previous_paid_amount = payment.paid_amount
        from app.modules.finance.services import record_external_payment  # noqa: PLC0415
        collection = record_external_payment(
            db,
            branch_id=contract.branch_id,
            amount=req.paid_amount,
            payment_method=req.payment_method,
            collector_id=collected_by,
            reference=f"LSE-RCV-{payment.id:06d}",
            source="leasing_rent",
            source_id=payment.id,
            require_cash_shift=enforce_cash_shift,
        )
        # الإيراد لازم يكون اتحقّق (accrued) قبل أي تحصيل — لو التحصيل حصل في
        # نفس يوم/قبل ما مهمة accrue_due_rents اليومية تشتغل، بنحقّقه هنا
        # inline (idempotent، مفيش خطر ترحيل مزدوج).
        _accrue_single_payment(db, payment, contract)
        obj = crud.pay_payment(db, payment, req)
        _post_rent_receipt_journal(
            db, obj, contract, req.paid_amount, req.payment_method,
            collection_payment_id=collection.id, collected_by=collected_by,
        )
        _audit_leasing_action(
            db, user_id=collected_by, branch_id=contract.branch_id,
            action="collect_lease_payment", entity_type="lease_payment",
            entity_id=payment.id,
            old_data={"status": previous_status, "paid_amount": previous_paid_amount},
            new_data={
                "status": obj.status, "paid_amount": obj.paid_amount,
                "collected_amount": req.paid_amount, "payment_method": req.payment_method,
                "receipt_number": req.receipt_number, "payment_id": collection.id,
            },
        )
        db.commit()
        db.refresh(obj)
        return obj
    except Exception:
        db.rollback()
        raise


def record_cash_log(db: Session, data: TenantCashLogCreate, recorded_by: int) -> TenantCashLog:
    """تسجيل تسوية كاش يومية مع مستأجر (مركز غوص/واتر سبورت) — خارج دورة
    الاستحقاق الشهرية العادية. لو النوع rent_payment أو revenue_share، بيرحّل
    قيد مباشر واحد (Dr Cash/Bank/Card / Cr 4500) — عمدًا من غير عبور على
    1260 لأن مفيش جدول استحقاق مسبق لتحصيلات النوع ده (راجع
    _post_direct_rent_journal).

    ⚠️ باج حقيقي اتصلح (2026-08-02): pay_payment (تحصيل الدفعة الشهرية
    العادية) بيرفض العقد terminated/expired، لكن المسار المواز ده — اللي
    بيرحّل بالظبط نفس قيد إثبات الإيراد لـrent_payment/revenue_share —
    مكانش عنده نفس الفحص خالص. يعني عقد مفسوخ فعليًا كان لسه ممكن يتسجّل
    عليه "تحصيل إيجار" حقيقي يرحّل إيراد في الدفاتر. الأنواع التانية
    (deposit/refund/penalty/maintenance/other) مسموحة عمدًا حتى بعد
    الفسخ/الانتهاء — رد تأمين أو غرامة تسوية نهائية سيناريو تشغيلي طبيعي
    بعد إقفال العقد، عكس تحصيل إيراد إيجار جديد."""
    try:
        contract = get_contract_or_404(db, data.contract_id)
        if data.activity_type in ("rent_payment", "revenue_share"):
            if contract.status == "terminated":
                raise ValueError(f"العقد {contract.contract_number} مفسوخ — لا يمكن تحصيل إيجار عليه")
            if contract.status == "expired":
                raise ValueError(f"العقد {contract.contract_number} منتهي — لا يمكن تحصيل إيجار عليه")
        log = crud.create_cash_log(db, data, recorded_by)

        from app.modules.finance.services import record_external_payment  # noqa: PLC0415
        ledger_amount = -data.amount if data.activity_type == "refund" else data.amount
        collection = record_external_payment(
            db,
            branch_id=contract.branch_id,
            amount=ledger_amount,
            payment_method=data.payment_method,
            collector_id=recorded_by,
            reference=data.reference or f"LSE-CL-{log.id:06d}",
            source="leasing_cash_log",
            source_id=log.id,
        )

        if data.activity_type in ("rent_payment", "revenue_share"):
            _post_direct_rent_journal(
                db, log, contract, data.amount, data.payment_method,
                collection_payment_id=collection.id, collected_by=recorded_by,
            )
        _audit_leasing_action(
            db, user_id=recorded_by, branch_id=contract.branch_id,
            action="record_tenant_cash_log", entity_type="tenant_cash_log",
            entity_id=log.id,
            new_data={
                "contract_id": contract.id, "activity_type": data.activity_type,
                "amount": data.amount, "payment_method": data.payment_method,
                "reference": data.reference, "payment_id": collection.id,
            },
        )

    except Exception:
        db.rollback()
        raise

    db.commit()
    db.refresh(log)
    return log


def list_cash_logs(db: Session, contract_id: int) -> list[TenantCashLog]:
    get_contract_or_404(db, contract_id)
    return crud.list_cash_logs(db, contract_id)


def generate_rent_receipt_pdf(db: Session, payment_id: int) -> bytes:
    """PDF إيصال إيجار."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    payment = crud.get_payment(db, payment_id)
    if not payment:
        raise ValueError(f"الدفعة {payment_id} غير موجودة")
    contract = crud.get_contract(db, payment.contract_id)
    if not contract:
        raise ValueError("العقد غير موجود")

    # نحسب الغرامة لحظيًا وقت إصدار الإيصال بدل ما نعتمد على payment.penalty المخزّن،
    # اللي بيفضل قديم إلى ما حد يستدعي apply_penalties() — القيمة المحسوبة هنا هي
    # الحقيقة الحالية، وبنعرضها من غير ما نعدّل سجل الدفعة نفسه (إصدار إيصال مفروض
    # يكون read-only، والتحديث الفعلي مسؤولية apply_penalties()).
    penalty = calculate_penalty(payment)
    total = float(payment.paid_amount or payment.amount) + float(penalty)

    fields = [
        ("المستأجر",       contract.tenant_name),
        ("الوحدة",         contract.unit_description),
        ("رقم العقد",      contract.contract_number),
        ("تاريخ الاستحقاق", str(payment.due_date)),
        ("مبلغ الإيجار",   f"{payment.amount:,.2f} EGP"),
    ]
    if penalty > 0:
        fields.append(("غرامة التأخير", f"{penalty:,.2f} EGP"))
    if payment.payment_method:
        fields.append(("طريقة الدفع", payment.payment_method))

    return builder.receipt_pdf(
        reference=payment.receipt_number or f"LP-{payment.id:06d}",
        title="إيصال إيجار",
        fields=fields,
        total=total,
        currency="EGP",
        note=f"عقد الإيجار {contract.contract_number}",
    )
