"""app/modules/timeshare/_services/contracts.py — contract lifecycle:
create, update, cancel (with refund), unit transfer."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.modules.timeshare import crud
from app.modules.timeshare.models import TimeshareContract
from app.modules.timeshare.schemas import (
    TimeshareContractCreate, TimeshareContractUpdate, TimeshareUnitTransferRequest,
)
from app.resort_os.timeshare_engine import generate_installment_schedule

# نفس الحسابات المستخدمة في installments._PAYMENT_METHOD_DEBIT_ACCOUNT بالظبط
# (دفعة أولى بترحّل بنفس منطق تحصيل القسط) — مستوردة بدل ما تتكرر هنا.
from .installments import _PAYMENT_METHOD_DEBIT_ACCOUNT


def get_contract_or_404(db: Session, contract_id: int) -> TimeshareContract:
    c = crud.get_contract(db, contract_id)
    if not c:
        raise ValueError(f"العقد {contract_id} غير موجود")
    return c


def create_contract(
    db: Session,
    data: TimeshareContractCreate,
    signed_by: int,
    *,
    collection_actor_id: Optional[int] = None,
) -> TimeshareContract:
    if data.down_payment > data.total_value:
        raise ValueError("الدفعة الأولى لا يمكن أن تتجاوز إجمالي قيمة العقد")
    if data.end_date and data.end_date <= data.start_date:
        raise ValueError("تاريخ الانتهاء يجب أن يكون بعد تاريخ البداية")

    try:
        contract = crud.create_contract(db, data, signed_by)

        # توليد جدول الأقساط من الـ engine
        schedule = generate_installment_schedule(
            total_value=data.total_value,
            down_payment=data.down_payment,
            installments=data.installments,
            installment_period=data.installment_period,
            first_installment_date=data.first_installment_date,
        )
        crud.create_installments(db, contract.id, [
            {"installment_no": s.installment_no, "due_date": s.due_date, "amount": s.amount}
            for s in schedule
        ])

        # قيد إيرادات مؤجَّلة (deferred revenue) — strict=True (2026-08-11):
        # عقد جديد بدفعة أولى حقيقية كان ممكن يتسجّل بالكامل حتى لو فشل
        # ترحيل قيد الإيراد المقابل (حساب مش معرَّف للفرع، مثلاً). دفعة أولى
        # صفرية مش فشل محاسبي — مفيش مبلغ حقيقي يترحّل خالص، فمينفعش نستدعي
        # الترحيل الصارم أصلاً (post_simple_revenue_journal(strict=True) بيرفض
        # مبلغ صفري كخطأ تجهيز، مش no-op شرعي).
        if contract.down_payment and contract.down_payment > 0:
            collection_payment_id = None
            if collection_actor_id is not None:
                from app.modules.finance.services import record_external_payment  # noqa: PLC0415

                collection = record_external_payment(
                    db,
                    branch_id=contract.branch_id,
                    amount=contract.down_payment,
                    payment_method=contract.down_payment_method or "cash",
                    collector_id=collection_actor_id,
                    reference=f"TS-DP-{contract.contract_number}",
                    source="timeshare_down_payment",
                    source_id=contract.id,
                )
                collection_payment_id = collection.id
            _post_deferred_revenue_journal(
                db,
                contract,
                collection_payment_id=collection_payment_id,
                collected_by=collection_actor_id or signed_by,
            )

        # مستحق الصيانة الأول للعقد — لو التوليد الجماعي السنوي (1 يناير) كان
        # اشتغل بالفعل قبل ما العقد ده يتوقّع، كان هيفضل من غير مستحق صيانة
        # للسنة الحالية خالص. راجع _generate_maintenance_due_for_new_contract.
        _generate_maintenance_due_for_new_contract(db, contract)

        db.commit()
        db.refresh(contract)
        return contract
    except Exception:
        db.rollback()
        raise


def _generate_maintenance_due_for_new_contract(db: "Session", contract: "TimeshareContract") -> None:
    """يولّد مستحق صيانة لسنة التوقيع نفسها فور إنشاء العقد — بالمبلغ الكامل
    (بدون تناسب زمني، قرار Mohamed) وموعد استحقاق = تاريخ التوقيع نفسه، **مش**
    1 يناير الثابت اللي التوليد الجماعي السنوي بيستخدمه — عشان عقد اتوقّع نص
    السنة (مثلاً يونيو) ميبقاش "متأخر" فورًا من لحظة إنشائه لو استخدمنا تاريخ
    فات بالفعل. idempotent: مبيعملش حاجة لو مستحق نفس السنة موجود بالفعل
    (مهم لو التوليد الجماعي اشتغل بعد إنشاء العقد في نفس السنة بالغلط)."""
    from decimal import Decimal as _D  # noqa: PLC0415

    if not contract.maintenance_fee or contract.maintenance_fee <= _D("0"):
        return
    signing_date = contract.contract_date or contract.start_date
    fee_year = signing_date.year
    if crud.get_maintenance_due_for_year(db, contract.id, fee_year):
        return
    crud.create_maintenance_due(
        db, contract.id, fee_year, due_date=signing_date, amount=contract.maintenance_fee,
    )


def _post_deferred_revenue_journal(
    db: "Session",
    contract: "TimeshareContract",
    *,
    collection_payment_id: Optional[int],
    collected_by: int,
) -> None:
    """Dr. tender account / Cr. timeshare revenue for the down payment.

    ⚠️ باج محاسبي حقيقي كان هنا (اتصلح 2026-07-07، قرار Mohamed): كان بيرحّل
    لحساب 2300 ("إيرادات مؤجَّلة") وهو حساب liability مش revenue — يعني كل
    دفعة أولى ولا قسط ملكية جزئية من أول ما اتعمل الموديول كان بيتراكم في حساب
    التزامات للأبد، بدون أي خطوة "تحرير" لاحقة تنقله لإيراد فعلي، فمكانش
    بيظهر في قائمة الدخل خالص. القرار: تسجيل إيراد فوري وقت كل دفعة (نفس
    فلسفة حجز الغرف)، لحساب Revenue مخصص منفصل عن إيراد حجوزات الغرف
    (4100) — الحساب 2300 القديم فضل موجود في الشجرة للسجلات التاريخية بس،
    مش بيتستخدم في أي قيد جديد بعد كده."""
    from decimal import Decimal as _D  # noqa: PLC0415
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    post_simple_revenue_journal(
        db, contract.branch_id, business_today(settings.TIMEZONE),
        debit_account_code=_PAYMENT_METHOD_DEBIT_ACCOUNT.get(
            contract.down_payment_method or "cash", "1100",
        ),
        credit_account_code="4600",
        amount=contract.down_payment or _D("0"),
        reference=f"TS-DP-{contract.contract_number}",
        description=f"دفعة أولى ملكية جزئية — {contract.contract_number}",
        source="timeshare",
        source_id=collection_payment_id or contract.id,
        created_by=collected_by,
        cost_center_code="TS",
        strict=True, commit_cost_centers=False,
    )


def update_contract(
    db: Session, contract_id: int, data: TimeshareContractUpdate,
    *, updated_by: int | None = None,
) -> TimeshareContract:
    import json as _json  # noqa: PLC0415
    from app.modules.core.crud import create_audit_log  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415

    contract = get_contract_or_404(db, contract_id)
    changes = data.model_dump(exclude_unset=True)
    if data.status == "cancelled" and contract.status != "cancelled":
        raise ValueError("استخدم إجراء إلغاء العقد المخصص لتسجيل الرد والقيد وسجل التدقيق")
    if data.unit_capacity is not None:
        effective_room_type = contract.room_type
        if effective_room_type == "Studio" and data.unit_capacity != 2:
            raise ValueError("Studio دايمًا سعة 2 أفراد")
        if effective_room_type == "Chalet" and data.unit_capacity not in (4, 6):
            raise ValueError("Chalet سعة 4 أو 6 أفراد (6 = باقة Family Compound)")
    old_values = {field: getattr(contract, field) for field in changes}
    try:
        obj = crud.update_contract(db, contract, data)
        if changes:
            create_audit_log(db, AuditLogCreate(
                user_id=updated_by, branch_id=contract.branch_id,
                action="update_contract", entity_type="timeshare_contract",
                entity_id=contract.id,
                old_data=_json.dumps(old_values, ensure_ascii=False, default=str),
                new_data=_json.dumps(changes, ensure_ascii=False, default=str),
            ))
        db.commit()
        db.refresh(obj)
        return obj
    except Exception:
        db.rollback()
        raise


_REFUND_METHOD_CREDIT_ACCOUNT = {
    "cash": "1100",
    "bank_transfer": "1110",
    "card": "1120",
}


def _contract_refundable_amount(contract: TimeshareContract) -> Decimal:
    """Contract principal collected, net of any refund already recorded."""
    collected = Decimal(contract.down_payment or 0) + sum(
        (Decimal(inst.paid_amount or 0) for inst in contract.installments_list),
        Decimal("0"),
    )
    already_refunded = Decimal(contract.cancel_amount or 0)
    return max(Decimal("0"), collected - already_refunded)


def cancel_contract(
    db: Session,
    contract_id: int,
    cancel_amount,
    *,
    refund_method: str = "cash",
    cancelled_by: int,
    enforce_cash_shift: bool = True,
) -> TimeshareContract:
    refund_amount = Decimal(str(cancel_amount))
    if refund_amount < 0:
        raise ValueError("مبلغ الرد لا يمكن أن يكون سالبًا")
    if refund_method not in _REFUND_METHOD_CREDIT_ACCOUNT:
        raise ValueError("طريقة الرد يجب أن تكون cash أو card أو bank_transfer")
    if cancelled_by <= 0:
        raise ValueError("المستخدم المنفذ لإلغاء العقد مطلوب")

    try:
        contract = crud.lock_contract_for_update(db, contract_id)
        if not contract:
            raise ValueError(f"العقد {contract_id} غير موجود")
        if contract.status == "cancelled":
            raise ValueError("العقد ملغي بالفعل")

        refundable = _contract_refundable_amount(contract)
        if refund_amount > refundable:
            raise ValueError(
                f"مبلغ الرد ({refund_amount:,.2f} ج) أكبر من صافي المحصل القابل "
                f"للرد ({refundable:,.2f} ج)"
            )

        effective_method = refund_method if refund_amount > 0 else None
        refund_payment_id = None
        if refund_amount > 0:
            from app.modules.finance.services import record_external_payment  # noqa: PLC0415

            refund_payment = record_external_payment(
                db,
                branch_id=contract.branch_id,
                amount=-refund_amount,
                payment_method=refund_method,
                collector_id=cancelled_by,
                reference=f"TS-CANCEL-{contract.contract_number}",
                source="timeshare_refund",
                source_id=contract.id,
                require_cash_shift=enforce_cash_shift,
            )
            refund_payment_id = refund_payment.id
        obj = crud.cancel_contract(
            db,
            contract,
            refund_amount,
            effective_method,
            cancelled_by,
        )
        # ⚠️ باج محاسبي حقيقي كان هنا: إلغاء العقد بمبلغ استرداد (cancel_amount)
        # كان بيسجّل الرقم على العقد نفسه بس من غير أي قيد يومية — يعني كاش
        # حقيقي بيتدفع للعميل (استرداد) كان بيخرج من الخزينة من غير ما يترحّل
        # محاسبيًا خالص، والإيراد اللي اتسجّل وقت الدفعة الأولى/الأقساط
        # (_post_deferred_revenue_journal/installments._post_installment_payment_
        # journal) كان يفضل مبالغ فيه للأبد رغم إن جزء منه اترد فعليًا للعميل.
        # strict=True (2026-08-11): فشل ترحيل قيد الاسترداد لازم يوقف الإلغاء
        # كله، مش يسجّل العقد "ملغي" من غير أي أثر محاسبي للاسترداد.
        if refund_amount > 0:
            _post_contract_cancellation_refund_journal(
                db,
                obj,
                refund_amount,
                refund_method,
                cancelled_by,
                collection_payment_id=refund_payment_id,
            )
        _audit_contract_cancellation(
            db, obj, refund_amount, effective_method, cancelled_by,
        )
        db.commit()
        db.refresh(obj)
        return obj
    except Exception:
        db.rollback()
        raise


def _post_contract_cancellation_refund_journal(
    db: "Session",
    contract: "TimeshareContract",
    refund_amount,
    refund_method: str,
    cancelled_by: int,
    *,
    collection_payment_id: int,
) -> None:
    """Reverse revenue against the actual cash/bank/card refund account."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    post_simple_revenue_journal(
        db, contract.branch_id, business_today(settings.TIMEZONE),
        debit_account_code="4600",
        credit_account_code=_REFUND_METHOD_CREDIT_ACCOUNT[refund_method],
        amount=refund_amount,
        reference=f"TS-CANCEL-{contract.contract_number}",
        description=f"استرداد إلغاء عقد ملكية جزئية — {contract.contract_number}",
        source="timeshare", source_id=collection_payment_id,
        created_by=cancelled_by,
        cost_center_code="TS",
        strict=True, commit_cost_centers=False,
    )


def _audit_contract_cancellation(
    db: Session,
    contract: TimeshareContract,
    refund_amount: Decimal,
    refund_method: Optional[str],
    cancelled_by: int,
) -> None:
    import json as _json  # noqa: PLC0415
    from app.modules.core.crud import create_audit_log  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415

    create_audit_log(db, AuditLogCreate(
        user_id=cancelled_by,
        branch_id=contract.branch_id,
        action="cancel_contract",
        entity_type="timeshare_contract",
        entity_id=contract.id,
        old_data=_json.dumps({"status": "active"}, ensure_ascii=False),
        new_data=_json.dumps({
            "status": "cancelled",
            "refund_amount": float(refund_amount),
            "refund_method": refund_method,
        }, ensure_ascii=False),
    ))


def transfer_unit(
    db: Session, contract_id: int, data: TimeshareUnitTransferRequest,
    transferred_by: Optional[int] = None,
) -> TimeshareContract:
    """wagdy.md #10: نقل عقد من الوحدة الثابتة المخصَّصة له لوحدة تانية —
    التعديل المباشر عبر update_contract (TimeshareContractUpdate.unit_id)
    كان موجود من غير أي تحقق خالص. عمدًا مقصور على نفس room_type — تحويل
    لنوع وحدة مختلف ("ترقية") معناه غالبًا تغيير في قيمة العقد، وده قرار
    تسعير منفصل مش جزء من "نقل الوحدة الفعلي"، فبنرفضه بوضوح بدل ما نخمّن.

    مفيش قفل صف على الوحدة الهدف (على عكس visits.create_visit) — عمدًا: على
    عكس حجز زيارة فعلي، أكتر من عقد ممكن يشير لنفس unit_id بالفعل في التصميم
    الحالي (عقود عائمة/مؤجَّرة سنويًا بأسابيع مختلفة على نفس الوحدة الفعلية)،
    فمفيش مورد حصري بنحميه هنا — الحماية الحقيقية اللازمة هي التحقق من عدم
    وجود زيارة قادمة لسه شايلة الوحدة القديمة (تحت)."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.core.crud import create_audit_log  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    contract = get_contract_or_404(db, contract_id)
    if contract.status in ("cancelled", "expired"):
        raise ValueError(f"العقد {contract.contract_number} {contract.status} — لا يمكن نقل وحدته")
    if contract.unit_id is None:
        raise ValueError("العقد عائم (بدون وحدة ثابتة مخصَّصة) — لا يوجد شيء يُنقَل منه")
    if data.new_unit_id == contract.unit_id:
        raise ValueError("الوحدة الجديدة هي نفس الوحدة الحالية")

    new_unit = crud.get_unit(db, data.new_unit_id)
    if not new_unit:
        raise ValueError(f"الوحدة {data.new_unit_id} غير موجودة")
    if new_unit.branch_id != contract.branch_id:
        raise ValueError("الوحدة الجديدة في فرع مختلف")
    if new_unit.unit_type != contract.room_type:
        raise ValueError(
            f"الوحدة {new_unit.unit_number} من نوع {new_unit.unit_type} — العقد من نوع "
            f"{contract.room_type}. نقل لنوع مختلف (ترقية) قرار تسعير منفصل، راجع المدير أولاً."
        )
    if new_unit.status == "maintenance":
        raise ValueError(f"الوحدة {new_unit.unit_number} تحت الصيانة حاليًا")

    today = business_today(settings.TIMEZONE)
    if crud.has_upcoming_visit(db, contract.id, today):
        raise ValueError(
            "فيه زيارة مجدولة/جارية لسه على الوحدة الحالية — ألغِ أو أعِد جدولة الزيارة أولاً"
        )

    old_unit_id = contract.unit_id
    create_audit_log(db, AuditLogCreate(
        user_id=transferred_by, branch_id=contract.branch_id, action="transfer_unit",
        entity_type="timeshare_contract", entity_id=contract.id,
        old_data=f'{{"unit_id": {old_unit_id}}}',
        new_data=f'{{"unit_id": {data.new_unit_id}, "reason": "{data.reason}"}}',
    ))
    contract.unit_id = data.new_unit_id
    db.commit()
    db.refresh(contract)
    return contract
