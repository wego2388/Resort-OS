"""app/modules/timeshare/services.py"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.modules.timeshare import crud
from app.modules.timeshare.models import (
    TimeshareContract, TimeshareInstallment, TimeshareMaintenanceDue,
    TimeshareSupportTicket, TimeshareUnit, TimeshareVisit, TimeshareVisitRequest,
)
from app.modules.timeshare.schemas import (
    TimeshareContractCreate, TimeshareContractUpdate, TimeshareUnitTransferRequest,
    PayInstallmentRequest, PayMaintenanceDueRequest,
    TimeshareSupportTicketCreate, TimeshareUnitCreate, TimeshareUnitUpdate,
    TimeshareVisitCreate, TimeshareVisitRequestCreate,
    TimeshareVisitUpdate, WaitlistCreate,
)
from app.resort_os.timeshare_engine import (
    generate_installment_schedule,
)


class VisitConflictError(Exception):
    """وحدة تايم شير مقفولة فعلاً أو ماسكاها transaction تانية الآن — 409، مش 400."""


class PaymentConflictError(Exception):
    """قسط/مستحق صيانة مقفول بعملية تحصيل تانية شغالة عليه دلوقتي — 409، مش 400."""


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


def _lock_maintenance_due_or_raise(db: Session, due_id: int) -> TimeshareMaintenanceDue:
    """مرآة _lock_installment_or_raise — pay_maintenance_due نفس فئة الباج بالظبط."""
    try:
        locked = crud.lock_maintenance_due_for_update(db, due_id)
    except OperationalError as exc:
        db.rollback()
        raise PaymentConflictError(
            "مستحق الصيانة مقفول الآن بعملية تحصيل أخرى — حاول تاني خلال لحظات"
        ) from exc
    if not locked:
        raise ValueError(f"مستحق الصيانة {due_id} غير موجود")
    return locked


def get_contract_or_404(db: Session, contract_id: int) -> TimeshareContract:
    c = crud.get_contract(db, contract_id)
    if not c:
        raise ValueError(f"العقد {contract_id} غير موجود")
    return c


def create_contract(db: Session, data: TimeshareContractCreate, signed_by: int) -> TimeshareContract:
    if data.down_payment > data.total_value:
        raise ValueError("الدفعة الأولى لا يمكن أن تتجاوز إجمالي قيمة العقد")
    if data.end_date and data.end_date <= data.start_date:
        raise ValueError("تاريخ الانتهاء يجب أن يكون بعد تاريخ البداية")

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

    # قيد إيرادات مؤجَّلة (deferred revenue)
    _post_deferred_revenue_journal(db, contract)

    # مستحق الصيانة الأول للعقد — لو التوليد الجماعي السنوي (1 يناير) كان
    # اشتغل بالفعل قبل ما العقد ده يتوقّع، كان هيفضل من غير مستحق صيانة
    # للسنة الحالية خالص. راجع _generate_maintenance_due_for_new_contract.
    _generate_maintenance_due_for_new_contract(db, contract)

    db.commit()
    db.refresh(contract)
    return contract


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


def _post_deferred_revenue_journal(db: "Session", contract: "TimeshareContract") -> None:
    """Dr. Cash (1100) / Cr. إيرادات عقود التايم شير (4600) عند إنشاء العقد.

    ⚠️ باج محاسبي حقيقي كان هنا (اتصلح 2026-07-07، قرار Mohamed): كان بيرحّل
    لحساب 2300 ("إيرادات مؤجَّلة") وهو حساب liability مش revenue — يعني كل
    دفعة أولى ولا قسط تايم شير من أول ما اتعمل الموديول كان بيتراكم في حساب
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
        debit_account_code="1100", credit_account_code="4600",
        amount=contract.down_payment or _D("0"),
        reference=f"TS-DP-{contract.contract_number}",
        description=f"دفعة أولى تايم شير — {contract.contract_number}",
        source="timeshare", source_id=contract.id,
        created_by=contract.signed_by or 0,
        cost_center_code="TS",
    )


def update_contract(db: Session, contract_id: int, data: TimeshareContractUpdate) -> TimeshareContract:
    contract = get_contract_or_404(db, contract_id)
    obj = crud.update_contract(db, contract, data)
    db.commit()
    db.refresh(obj)
    return obj


def pay_installment(db: Session, inst_id: int, req: PayInstallmentRequest) -> TimeshareInstallment:
    """⚠️ 3 باجات حقيقية اتصلحوا هنا (اتكشفوا أثناء اختبار حي كمدير خدمة عملاء
    تايم شير):
    1. مفيش أي تحقق من حالة العقد — كان ممكن تسجّل تحصيل قسط على عقد **ملغي**
       أو **منتهي** فعليًا (العقد اتلغى بس القسط المرتبط بيه فضل قابل للتحصيل).
    2. مفيش أي حد أقصى على المبلغ — إدخال 50,000 على قسط قيمته 10,000 كان
       بيتقبل بصمت (paid_amount بيبقى أكبر من amount، والحالة بتبقى "paid" من
       غير أي تنبيه أو تسجيل فرق) — باج مالي حقيقي، مش نظري.
    3. **الأهم**: تحصيل قسط عمره ما كان بيرحّل أي قيد يومية خالص — بعكس الدفعة
       الأولى (_post_deferred_revenue_journal بتترحّل عند إنشاء العقد فقط).
       يعني كل تحصيلات الأقساط (اللي هي معظم إيراد التايم شير على مدار سنين
       العقد) كانت غايبة تمامًا عن الدفاتر المحاسبية — مخالفة مباشرة لـ
       "Finance First" (§5.2 في CLAUDE.md بيذكر أقساط التايم شير بالاسم صراحةً).
    """
    inst = _lock_installment_or_raise(db, inst_id)
    if inst.status == "paid":
        raise ValueError("القسط مدفوع بالكامل مسبقاً")

    contract = crud.get_contract(db, inst.contract_id)
    if not contract:
        raise ValueError(f"العقد المرتبط بالقسط {inst_id} غير موجود")
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

    obj = crud.pay_installment(db, inst, req)
    _post_installment_payment_journal(db, contract, req.paid_amount, inst)

    # سجل تدقيق — تاريخ التحصيل قابل للمراجعة والتصحيح لاحقاً
    _audit_installment_payment(db, contract, inst, req)

    # إلغاء تجميد الحجز إن كان مفيش أي رصيد متأخر تاني (أقساط أو صيانة)
    if contract.booking_frozen and not _has_any_overdue_balance(contract):
        contract.booking_frozen = False

    db.commit()
    db.refresh(obj)
    return obj


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


def _post_installment_payment_journal(
    db: "Session", contract: "TimeshareContract", paid_amount, inst: "TimeshareInstallment",
) -> None:
    """Dr. Cash (1100) / Cr. إيرادات عقود التايم شير (4600) عند تحصيل أي
    قسط — نفس منطق _post_deferred_revenue_journal بالظبط بس لكل تحصيل قسط،
    مش الدفعة الأولى بس (راجع تعليق تلك الدالة لتفاصيل باج حساب 2300)."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    post_simple_revenue_journal(
        db, contract.branch_id, business_today(settings.TIMEZONE),
        debit_account_code="1100", credit_account_code="4600",
        amount=paid_amount,
        reference=f"TS-INST-{contract.contract_number}-{inst.installment_no}",
        description=f"تحصيل قسط رقم {inst.installment_no} — {contract.contract_number}",
        source="timeshare", source_id=contract.id,
        created_by=0,
        cost_center_code="TS",
    )


def _audit_installment_payment(
    db: "Session",
    contract: "TimeshareContract",
    inst: "TimeshareInstallment",
    req: "PayInstallmentRequest",
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

    try:
        create_audit_log(db, AuditLogCreate(
            branch_id=contract.branch_id,
            action="pay_installment",
            entity_type="timeshare_installment",
            entity_id=inst.id,
            old_data=old_data,
            new_data=new_data,
        ))
    except ValueError:
        # لو AuditLog فشل (branch مش موجود مثلاً في test env) — لا يوقف العملية
        pass


def pay_maintenance_due(db: Session, due_id: int, req: PayMaintenanceDueRequest) -> TimeshareMaintenanceDue:
    """تحصيل مستحق صيانة سنوي — مرآة كاملة لـ pay_installment (نفس تسلسل
    التحقق بالضبط: موجود؟ مدفوع بالفعل؟ العقد ملغي/منتهي؟ المبلغ زيادة عن
    المتبقي؟) بس على TimeshareMaintenanceDue بدل TimeshareInstallment."""
    due = _lock_maintenance_due_or_raise(db, due_id)
    if due.status == "paid":
        raise ValueError("مستحق الصيانة مدفوع بالكامل مسبقاً")

    contract = crud.get_contract(db, due.contract_id)
    if not contract:
        raise ValueError(f"العقد المرتبط بمستحق الصيانة {due_id} غير موجود")
    if contract.status == "cancelled":
        raise ValueError(f"العقد {contract.contract_number} ملغي — لا يمكن تحصيل صيانة عليه")
    if contract.status == "expired":
        raise ValueError(f"العقد {contract.contract_number} منتهي — لا يمكن تحصيل صيانة عليه")

    remaining = due.amount - due.paid_amount
    if req.paid_amount > remaining:
        raise ValueError(
            f"المبلغ المُدخَل ({req.paid_amount:,.2f} ج) أكبر من المتبقي على "
            f"مستحق صيانة سنة {due.fee_year} ({remaining:,.2f} ج) — تحقّق من المبلغ قبل التسجيل"
        )

    obj = crud.pay_maintenance_due(db, due, req)
    _post_maintenance_payment_journal(db, contract, req.paid_amount, due)
    _audit_maintenance_payment(db, contract, due, req)

    if contract.booking_frozen and not _has_any_overdue_balance(contract):
        contract.booking_frozen = False

    db.commit()
    db.refresh(obj)
    return obj


def _post_maintenance_payment_journal(
    db: "Session", contract: "TimeshareContract", paid_amount, due: "TimeshareMaintenanceDue",
) -> None:
    """Dr. Cash (1100) / Cr. إيرادات صيانة عقود التايم شير (4650) — حساب
    منفصل عمدًا عن 4600 (إيراد سعر الشراء): إيراد الصيانة رسم خدمة سنوي
    مرتبط بسنة محدَّدة (fee_year)، مختلف في طبيعته المحاسبية عن إيراد بيع
    العقد لمرة واحدة."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    post_simple_revenue_journal(
        db, contract.branch_id, business_today(settings.TIMEZONE),
        debit_account_code="1100", credit_account_code="4650",
        amount=paid_amount,
        reference=f"TS-MAINT-{contract.contract_number}-{due.fee_year}",
        description=f"تحصيل صيانة سنة {due.fee_year} — {contract.contract_number}",
        source="timeshare", source_id=contract.id,
        created_by=0,
        cost_center_code="TS",
    )


def _audit_maintenance_payment(
    db: "Session",
    contract: "TimeshareContract",
    due: "TimeshareMaintenanceDue",
    req: "PayMaintenanceDueRequest",
) -> None:
    """يسجّل AuditLog لكل تحصيل صيانة — مرآة _audit_installment_payment."""
    import json as _json  # noqa: PLC0415
    from app.modules.core.crud import create_audit_log  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415

    old_data = _json.dumps({
        "status": "pending" if due.status == "partial" else due.status,
        "paid_amount": float(due.paid_amount - req.paid_amount),
    }, ensure_ascii=False)
    new_data = _json.dumps({
        "status": due.status,
        "paid_amount": float(due.paid_amount),
        "payment_method": req.payment_method,
        "receipt_number": req.receipt_number,
        "amount_paid_now": float(req.paid_amount),
    }, ensure_ascii=False)

    try:
        create_audit_log(db, AuditLogCreate(
            branch_id=contract.branch_id,
            action="pay_maintenance_due",
            entity_type="timeshare_maintenance_due",
            entity_id=due.id,
            old_data=old_data,
            new_data=new_data,
        ))
    except ValueError:
        pass


def list_maintenance_dues_for_branch(
    db: Session, branch_id: int,
    status: Optional[str] = None, contract_id: Optional[int] = None,
    fee_year: Optional[int] = None, search: Optional[str] = None, limit: int = 200,
) -> dict:
    """مرآة list_installments — قايمة مستحقات صيانة عبر الفرع كله (لشاشة
    تاب "الصيانة" الإدارية)، بعكس crud.list_maintenance_dues اللي بتاعة
    عقد واحد بس (مستخدمة في بروفايل العميل)."""
    items = crud.list_all_maintenance_dues(db, branch_id, status, contract_id, fee_year, search, limit)
    return {
        "maintenance_dues": items,
        "total": len(items),
        "summary": crud.maintenance_dues_summary(db, branch_id),
    }


def generate_annual_maintenance_dues(db: Session, branch_id: int, fee_year: int) -> int:
    """نقطة الدخول الوحيدة اللي الـ router بيكلّمها — بتفوّض للمنطق الفعلي
    في app.tasks.timeshare_tasks (نفس مكان _mark_overdue بالظبط، الاتفاقية
    القائمة في الموديول ده) عشان يبقى فيه تنفيذ واحد بس يستخدمه الـ Celery
    task والـ endpoint اليدوي، زي run_night_audit في pms."""
    from app.tasks.timeshare_tasks import _generate_annual_maintenance_dues  # noqa: PLC0415

    created = _generate_annual_maintenance_dues(db, branch_id, fee_year)
    db.commit()
    return created


def add_to_waitlist(db: Session, data: WaitlistCreate) -> object:
    get_contract_or_404(db, data.contract_id)
    if data.requested_end <= data.requested_start:
        raise ValueError("تاريخ النهاية يجب أن يكون بعد تاريخ البداية")
    obj = crud.create_waitlist_entry(db, data)
    db.commit()
    db.refresh(obj)
    return obj


def update_waitlist_status(db: Session, waitlist_id: int, new_status: str) -> object:
    """تحكم يدوي من الموظف — confirmed (اتحجزله فعليًا خارج هذا المسار عبر
    create_visit العادية) أو cancelled (العميل ملوش نية تاني). راجع
    app.tasks.timeshare_tasks.process_waitlist للانتقالات النظامية
    (waiting→notified، notified→expired)."""
    entry = crud.get_waitlist_entry(db, waitlist_id)
    if not entry:
        raise ValueError(f"عنصر قائمة الانتظار {waitlist_id} غير موجود")
    if entry.status not in ("waiting", "notified"):
        raise ValueError(f"عنصر قائمة الانتظار ده حالته '{entry.status}' بالفعل — مينفعش يتغيّر")
    entry.status = new_status
    db.commit()
    db.refresh(entry)
    return entry


def generate_monthly_collection_report(
    db: Session, branch_id: int, month: str,
) -> bytes:
    """تقرير التحصيل الشهري — Excel مُنسَّق للإدارة.

    `month` بصيغة "YYYY-MM".

    الشيت الأول: تفاصيل الأقساط (مدفوعة + متأخرة + معلقة) للشهر.
    الشيت الثاني: ملخص تنفيذي (المطلوب / المحصَّل / المتأخر / نسبة التحصيل).

    يستخدم `crud.list_all_installments` الموجود مع فلتر month — نفس البيانات
    التي يعرضها تاب الأقساط في الـ UI، لكن في تقرير Excel مُنسَّق بشكل أفضل
    للاجتماعات الشهرية وبريد الإدارة."""
    from decimal import Decimal as _D  # noqa: PLC0415
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    installments = crud.list_all_installments(
        db, branch_id, month=month, limit=10000,
    )

    # ── حساب ملخص التحصيل ──────────────────────────────────────────
    total_due = _D("0")
    total_collected = _D("0")
    total_overdue = _D("0")
    total_pending = _D("0")

    detail_rows = []
    for i in installments:
        c = i.contract
        customer_name = c.customer_name if c else "—"
        customer_phone = c.customer_phone if c else "—"
        room_type = c.room_type if c else "—"
        contract_number = c.contract_number if c else "—"

        total_due += i.amount
        if i.status == "paid":
            total_collected += i.paid_amount
        elif i.status == "overdue":
            total_overdue += i.amount - i.paid_amount
        elif i.status in ("pending", "partial"):
            total_pending += i.amount - i.paid_amount

        status_label = {
            "paid": "مدفوع", "pending": "معلق",
            "overdue": "متأخر", "partial": "جزئي",
        }.get(i.status, i.status)

        detail_rows.append([
            customer_name,
            customer_phone or "—",
            contract_number,
            room_type,
            i.installment_no,
            str(i.due_date),
            float(i.amount),
            float(i.paid_amount),
            float(i.amount - i.paid_amount),
            status_label,
            i.payment_method or "—",
            i.receipt_number or "—",
        ])

    # ترتيب: متأخر أولاً ثم معلق ثم مدفوع
    status_order = {"متأخر": 0, "جزئي": 1, "معلق": 2, "مدفوع": 3}
    detail_rows.sort(key=lambda r: status_order.get(r[9], 9))

    collection_rate = (
        round(float(total_collected) / float(total_due) * 100, 1)
        if total_due > 0 else 0.0
    )

    summary_rows = [
        ["إجمالي المطلوب للشهر",  float(total_due)],
        ["إجمالي المحصَّل",        float(total_collected)],
        ["إجمالي المتأخر",         float(total_overdue)],
        ["إجمالي المعلق",          float(total_pending)],
        ["نسبة التحصيل %",         collection_rate],
        ["عدد الأقساط",            len(installments)],
    ]

    year, month_num = month.split("-")
    month_label = f"{month_num}-{year}"  # بدون / لأن openpyxl لا يقبله في اسم الشيت

    return builder.excel(
        title=f"تقرير التحصيل الشهري — {month_label}",
        sheets=[
            {
                "name": f"تفاصيل {month_label}",
                "headers": [
                    "العميل", "الهاتف", "رقم العقد", "نوع الوحدة",
                    "القسط #", "تاريخ الاستحقاق",
                    "المبلغ", "المدفوع", "المتبقي",
                    "الحالة", "طريقة الدفع", "رقم الإيصال",
                ],
                "rows": detail_rows,
                "col_types": [
                    "text", "text", "text", "text",
                    "number", "text",
                    "currency", "currency", "currency",
                    "text", "text", "text",
                ],
                "summary": {
                    "إجمالي المطلوب": float(total_due),
                    "المحصَّل": float(total_collected),
                    "المتأخر": float(total_overdue),
                },
            },
            {
                "name": "ملخص تنفيذي",
                "headers": ["البيان", "القيمة"],
                "rows": summary_rows,
                "col_types": ["text", "currency"],
                "summary": {"نسبة التحصيل %": collection_rate},
            },
        ],
    )


def generate_contract_pdf(db: Session, contract_id: int) -> bytes:
    """PDF ملخص عقد التايم شير."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    contract = get_contract_or_404(db, contract_id)
    week_label = f"أسبوع {contract.week_number}" if contract.week_number else "عائم"
    fields = [
        ("العميل",             contract.customer_name),
        ("رقم العقد",          contract.contract_number),
        ("نوع الغرفة",         contract.room_type),
        ("الأسبوع",            week_label),
        ("الليالي/سنة",        str(contract.nights_per_year)),
        ("إجمالي العقد",       f"{contract.total_value:,.2f} EGP"),
        ("الدفعة الأولى",      f"{contract.down_payment:,.2f} EGP"),
        ("عدد الأقساط",        str(contract.installments)),
        ("تاريخ البداية",      str(contract.start_date)),
        ("الحالة",             contract.status),
    ]
    return builder.receipt_pdf(
        reference=contract.contract_number,
        title="عقد تايم شير",
        fields=fields,
        total=float(contract.total_value),
        currency="EGP",
        note="الخيمة بيتش ريزورت — وثيقة العقد",
    )


# ── CS Dashboard ─────────────────────────────────────────────────────

def get_cs_summary(db: Session, branch_id: int) -> dict:
    """ملخص شامل لخدمة عملاء التايم شير — زيارات قادمة + متأخرات + نسبة تحصيل.

    ⚠️ "اليوم" هنا بيتحسب بتوقيت المنتجع (business_today) مش توقيت السيرفر
    المحلي — نفس فئة باج تذاكر المطبخ (KDS)، هنا بيأثّر على "الأيام المتبقية
    لزيارة قادمة" و"متأخرات" المعروضة لموظف خدمة العملاء."""
    from app.core.config import settings  # noqa: PLC0415
    from app.resort_os.timeshare_engine import ContractSummary, build_cs_summary, find_next_visit  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    today = business_today(settings.TIMEZONE)
    rows = crud.list_active_contracts_with_aggregates(db, branch_id)

    summaries: list[ContractSummary] = []
    upcoming_visits = []
    for contract, collected, overdue_amount, pending_count, next_due in rows:
        summaries.append(ContractSummary(
            contract_id=contract.id,
            customer_name=contract.customer_name,
            customer_phone=contract.customer_phone,
            room_type=contract.room_type,
            week_number=contract.week_number,
            total_value=contract.total_value,
            collected=collected,
            overdue_amount=overdue_amount,
            pending_count=pending_count,
            next_due=next_due,
        ))
        if contract.week_number:
            visit = find_next_visit(contract.week_number, contract.nights_per_year, today)
            if visit and 0 <= visit.days_until <= 30:
                upcoming_visits.append({
                    "id": contract.id, "contract_number": contract.contract_number,
                    "customer_name": contract.customer_name, "customer_phone": contract.customer_phone,
                    "room_type": contract.room_type, "week_number": contract.week_number,
                    "visit_start": visit.visit_start.isoformat(), "visit_end": visit.visit_end.isoformat(),
                    "days_until": visit.days_until, "overdue_amount": float(overdue_amount),
                })

    this_month_due = crud.get_this_month_due(db, branch_id, today)
    summary = build_cs_summary(summaries, this_month_due)
    summary["upcoming_visits"] = sorted(upcoming_visits, key=lambda x: x["days_until"])

    # مؤشر إشغال مخزون الوحدات (2026-08-03) — نسبة الوحدات المشغولة فعليًا
    # النهاردة من إجمالي المخزون القابل للحجز، مؤشر تشغيلي مفيش له مكان
    # تاني في اللوحة رغم إن كل البيانات اللازمة له موجودة أصلاً.
    occupied_units, total_units = crud.unit_occupancy_today(db, branch_id, today)
    summary["occupied_units"] = occupied_units
    summary["total_units"] = total_units
    summary["occupancy_rate_pct"] = (
        round(occupied_units / total_units * 100, 1) if total_units > 0 else 0.0
    )
    # 2026-08-04: تابا "طلبات الزيارة" و"تذاكر الدعم" مالهومش أي مؤشر في
    # اللوحة قبل كده — الموظف لازم يفتحهم يدويًا كل مرة يتأكد مفيش حاجة
    # جديدة، نفس فئة مؤشر الإشغال فوق ده بالظبط.
    summary["pending_visit_requests"] = crud.count_pending_visit_requests(db, branch_id)
    summary["open_support_tickets"] = crud.count_open_support_tickets(db, branch_id)
    summary["overdue_clients"] = [
        {
            "id": c.contract_id, "customer_name": c.customer_name, "customer_phone": c.customer_phone,
            "room_type": c.room_type, "overdue_amount": float(c.overdue_amount),
            "pending_count": c.pending_count,
            "next_due": c.next_due.isoformat() if c.next_due else None,
        }
        for c in summary["overdue_clients"]
    ]
    return summary


def get_sales_dashboard(db: Session, branch_id: int) -> dict:
    """لوحة مبيعات لفريق المبيعات (مختلفة عن cs-summary الإداري) — pipeline
    (draft→active→...)، متأخرات بأرقام تليفون جاهزة للاتصال، أقساط الشهر الحالي."""
    cs = get_cs_summary(db, branch_id)
    pipeline = crud.count_contracts_by_status(db, branch_id)
    for key in ("draft", "active", "suspended", "cancelled", "expired"):
        pipeline.setdefault(key, 0)

    return {
        "pipeline": pipeline,
        "active_contracts": cs["active_contracts"],
        "overdue_contracts_count": cs["overdue_contracts_count"],
        "expired_contracts_count": pipeline.get("expired", 0),
        "this_month_due": cs["this_month_due"],
        "collection_rate_pct": cs["collection_rate_pct"],
        "total_value": cs["total_value"],
        "total_collected": cs["total_collected"],
        "total_overdue": cs["total_overdue"],
        "overdue_clients": cs["overdue_clients"],  # كل واحد فيه customer_phone جاهز للاتصال
        "upcoming_visits": cs["upcoming_visits"],
    }


def generate_sales_dashboard_excel(db: Session, branch_id: int) -> bytes:
    """تصدير Excel للوحة مبيعات التايم شير — قائمة اتصال يومية (متأخرات السداد)
    وزيارات قادمة، لمدير المبيعات (طباعة/مشاركة، راجع wagdy.md #12).
    نفس بيانات SalesDashboardView.vue بالظبط، بدون أي منطق عمل إضافي هنا —
    الشيت مجرد عرض مختلف لنفس get_sales_dashboard."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    dash = get_sales_dashboard(db, branch_id)

    overdue_rows = [
        [c["customer_name"], c["customer_phone"] or "—", c["room_type"],
         c["pending_count"], c["overdue_amount"], c["next_due"] or "—"]
        for c in dash["overdue_clients"]
    ]
    total_overdue = sum(c["overdue_amount"] for c in dash["overdue_clients"])

    visit_rows = [
        [v["customer_name"], v["customer_phone"] or "—", v["contract_number"],
         v["room_type"], v["week_number"], v["visit_start"], v["days_until"]]
        for v in dash["upcoming_visits"]
    ]

    return builder.excel(
        sheets=[
            {
                "name": "متأخرات السداد",
                "headers": ["اسم العميل", "رقم الهاتف", "نوع الوحدة",
                            "أقساط معلقة", "المبلغ المتأخر", "أقرب استحقاق"],
                "rows": overdue_rows,
                "col_types": ["text", "text", "text", "number", "currency", "text"],
                "summary": {"عدد العملاء": len(overdue_rows), "إجمالي المتأخر": total_overdue},
            },
            {
                "name": "زيارات قادمة",
                "headers": ["اسم العميل", "رقم الهاتف", "رقم العقد",
                            "نوع الوحدة", "رقم الأسبوع", "تاريخ الزيارة", "الأيام المتبقية"],
                "rows": visit_rows,
                "col_types": ["text", "text", "text", "text", "number", "text", "number"],
                "summary": {"عدد الزيارات": len(visit_rows)},
            },
        ],
        title=f"لوحة مبيعات التايم شير — فرع {branch_id}",
    )


def get_calendar(db: Session, branch_id: int, year: Optional[int] = None) -> dict:
    """تقويم 52 أسبوع ISO — كل أسبوع وعقوده وزياراته الفعلية.

    المصادر التي تُبنى منها بيانات كل أسبوع:
    ① عقود ثابتة (week_number محدد) — النافذة محسوبة رياضياً من timeshare_engine.
    ② زيارات فعلية من جدول timeshare_visits (سواء لعقود ثابتة أو عائمة) —
       check_in.isocalendar()[1] يحدّد الأسبوع الفعلي.

    يتم التمييز في الـ response بـ `source: "contract" | "visit"`:
    - `source=contract` → نافذة محسوبة (عقد ثابت لم يُجدَّل بعد بزيارة فعلية)
    - `source=visit`    → زيارة مسجّلة فعلاً في قاعدة البيانات
    """
    from datetime import date as _date, timedelta as _timedelta  # noqa: PLC0415

    from app.core.config import settings  # noqa: PLC0415
    from app.resort_os.timeshare_engine import calculate_visit_window  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    today = business_today(settings.TIMEZONE)
    year = year or today.year

    MONTH_AR = ["يناير", "فبراير", "مارس", "إبريل", "مايو", "يونيو",
                "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    cur_week = today.isocalendar()[1] if today.year == year else -1

    week_map: dict[int, list[dict]] = {}

    # ① عقود ثابتة — النافذة المحسوبة رياضياً
    for c in crud.list_contracts_with_week(db, branch_id):
        window = calculate_visit_window(c.week_number, c.nights_per_year, year, today)
        if not window:
            continue
        week_map.setdefault(c.week_number, []).append({
            "id": c.id, "contract_number": c.contract_number,
            "customer_name": c.customer_name, "customer_phone": c.customer_phone,
            "room_type": c.room_type, "season": c.season,
            "rci_included": c.rci_included, "nights_per_year": c.nights_per_year,
            "visit_start": window.visit_start.isoformat(), "visit_end": window.visit_end.isoformat(),
            "booking_frozen": c.booking_frozen,
            "source": "contract",
            "visit_id": None,
            "visit_status": None,
        })

    # ② زيارات فعلية — تُضاف بجانب/بدل النافذة المحسوبة (المستخدم يرى كلاهما)
    for v in crud.list_visits_for_calendar(db, branch_id, year):
        week_num = v.check_in.isocalendar()[1]
        contract = v.contract  # lazy="select" — محمّل عند الوصول (OK: حجم صغير)
        if contract is None:
            continue
        week_map.setdefault(week_num, []).append({
            "id": contract.id, "contract_number": contract.contract_number,
            "customer_name": contract.customer_name, "customer_phone": contract.customer_phone,
            "room_type": contract.room_type, "season": contract.season,
            "rci_included": contract.rci_included, "nights_per_year": contract.nights_per_year,
            "visit_start": v.check_in.isoformat(), "visit_end": v.check_out.isoformat(),
            "booking_frozen": contract.booking_frozen,
            "source": "visit",
            "visit_id": v.id,
            "visit_status": v.status,
        })

    months: dict[int, list[dict]] = {}
    for w in range(1, 53):
        try:
            ws = _date.fromisocalendar(year, w, 1)
        except ValueError:
            continue
        we = ws + _timedelta(days=6)
        months.setdefault(ws.month, []).append({
            "week": w, "start_date": ws.isoformat(), "end_date": we.isoformat(),
            "is_current": w == cur_week, "is_past": we < today,
            "contracts": week_map.get(w, []),
        })

    return {
        "year": year,
        "total_booked_weeks": len(week_map),
        "calendar": [
            {"month": m, "month_name": MONTH_AR[m - 1], "weeks": months[m]}
            for m in sorted(months)
        ],
    }


def get_available_weeks(
    db: Session, branch_id: int, year: int, room_type: Optional[str] = None,
) -> dict:
    """الأسابيع المتاحة للبيع في سنة بعينها — لفريق المبيعات.

    المنطق: (52 أسبوع ISO) - (أسابيع محجوزة بعقود ثابتة) - (أسابيع محجوزة
    بزيارات فعلية من عقود عائمة).
    يدعم فلتر room_type اختياري (Studio/Chalet)."""
    from datetime import date as _date, timedelta as _timedelta  # noqa: PLC0415

    booked = crud.get_booked_week_numbers(db, branch_id, year, room_type)

    available_weeks: list[dict] = []
    for w in range(1, 53):
        try:
            ws = _date.fromisocalendar(year, w, 1)
        except ValueError:
            continue
        if w not in booked:
            available_weeks.append({
                "week": w,
                "start_date": ws.isoformat(),
                "end_date": (ws + _timedelta(days=6)).isoformat(),
            })

    return {
        "year": year,
        "room_type": room_type,
        "total_available": len(available_weeks),
        "total_booked": 52 - len(available_weeks),
        "available_weeks": available_weeks,
    }


def get_upcoming_visits(db: Session, branch_id: int, days: int = 30) -> list[dict]:
    from app.core.config import settings  # noqa: PLC0415
    from app.resort_os.timeshare_engine import find_next_visit  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    today = business_today(settings.TIMEZONE)
    contracts = crud.list_contracts_with_week(db, branch_id)
    result = []
    for c in contracts:
        if c.status != "active":
            continue
        visit = find_next_visit(c.week_number, c.nights_per_year, today)
        # مفيش حد أدنى صفر على days_until — زيارة جارية دلوقتي (بدأت قبل
        # النهاردة، لسه ما خلصتش) لازم تفضل ظاهرة برضه، راجع تعليق
        # timeshare_engine.find_next_visit/get_upcoming_visits.
        if visit and visit.days_until <= days:
            result.append({
                "id": c.id, "contract_number": c.contract_number,
                "customer_name": c.customer_name, "customer_phone": c.customer_phone,
                "customer_email": c.customer_email,
                "room_type": c.room_type, "week_number": c.week_number,
                "nights_per_year": c.nights_per_year, "season": c.season,
                "rci_included": c.rci_included,
                "visit_start": visit.visit_start.isoformat(), "visit_end": visit.visit_end.isoformat(),
                "days_until": visit.days_until,
                "total_value": float(c.total_value),
            })
    return sorted(result, key=lambda x: x["days_until"])


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


def get_stats(db: Session, branch_id: int) -> dict:
    by_partner = crud.stats_by_partner(db, branch_id)
    by_room_type = crud.stats_by_room_type(db, branch_id)
    by_batch = crud.stats_by_batch(db, branch_id)
    cancelled = crud.cancellation_summary(db, branch_id)
    collection = crud.overall_collection(db, branch_id)

    collected, pending = collection["collected"], collection["pending"]
    rate = round(float(collected) / float(collected + pending) * 100, 1) if (collected + pending) > 0 else 0

    return {
        "by_partner": [
            {"partner_company": r.partner_company, "contracts": r.contracts,
             "total_value": float(r.total_value), "total_down": float(r.total_down),
             "resort_share": float(r.resort_share)}
            for r in by_partner
        ],
        "by_room_type": [
            {"room_type": r.room_type, "contracts": r.contracts,
             "total_value": float(r.total_value), "avg_value": float(r.avg_value)}
            for r in by_room_type
        ],
        "by_batch": [
            {"batch_number": r.batch_number, "contracts": r.contracts,
             "total_value": float(r.total_value), "total_down": float(r.total_down),
             "batch_date": r.batch_date.date().isoformat() if r.batch_date else None}
            for r in by_batch
        ],
        "cancelled": {"count": cancelled["count"], "refunded": float(cancelled["refunded"])},
        "collection": {
            "collected": float(collection["collected"]),
            "pending": float(collection["pending"]),
            "overdue": float(collection["overdue"]),
            "rate": rate,
        },
    }


def cancel_contract(
    db: Session, contract_id: int, cancel_amount, cancelled_by: Optional[int] = None,
) -> TimeshareContract:
    contract = get_contract_or_404(db, contract_id)
    if contract.status == "cancelled":
        raise ValueError("العقد ملغي بالفعل")
    obj = crud.cancel_contract(db, contract, cancel_amount)
    # ⚠️ باج محاسبي حقيقي كان هنا: إلغاء العقد بمبلغ استرداد (cancel_amount)
    # كان بيسجّل الرقم على العقد نفسه بس من غير أي قيد يومية — يعني كاش
    # حقيقي بيتدفع للعميل (استرداد) كان بيخرج من الخزينة من غير ما يترحّل
    # محاسبيًا خالص، والإيراد اللي اتسجّل وقت الدفعة الأولى/الأقساط
    # (_post_deferred_revenue_journal/_post_installment_payment_journal) كان
    # يفضل مبالغ فيه للأبد رغم إن جزء منه اترد فعليًا للعميل.
    if cancel_amount and cancel_amount > 0:
        _post_contract_cancellation_refund_journal(db, obj, cancel_amount, cancelled_by or 0)
    db.commit()
    db.refresh(obj)
    return obj


def _post_contract_cancellation_refund_journal(
    db: "Session", contract: "TimeshareContract", refund_amount, cancelled_by: int,
) -> None:
    """Dr. إيرادات عقود التايم شير (4600) / Cr. نقدية (1100) — عكس الإيراد
    المسجَّل سابقًا بمقدار المبلغ المسترد فعليًا للعميل عند إلغاء العقد
    (نفس فلسفة عكس القيد وقت إلغاء عملية شاطئ، راجع
    beach.services._post_beach_revenue_reversal_journal)."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    post_simple_revenue_journal(
        db, contract.branch_id, business_today(settings.TIMEZONE),
        debit_account_code="4600", credit_account_code="1100",
        amount=refund_amount,
        reference=f"TS-CANCEL-{contract.contract_number}",
        description=f"استرداد إلغاء عقد تايم شير — {contract.contract_number}",
        source="timeshare", source_id=contract.id,
        created_by=cancelled_by,
        cost_center_code="TS",
    )


def transfer_unit(
    db: Session, contract_id: int, data: TimeshareUnitTransferRequest,
    transferred_by: Optional[int] = None,
) -> TimeshareContract:
    """wagdy.md #10: نقل عقد من الوحدة الثابتة المخصَّصة له لوحدة تانية —
    التعديل المباشر عبر update_contract (TimeshareContractUpdate.unit_id)
    كان موجود من غير أي تحقق خالص. عمدًا مقصور على نفس room_type — تحويل
    لنوع وحدة مختلف ("ترقية") معناه غالبًا تغيير في قيمة العقد، وده قرار
    تسعير منفصل مش جزء من "نقل الوحدة الفعلي"، فبنرفضه بوضوح بدل ما نخمّن.

    مفيش قفل صف على الوحدة الهدف (على عكس create_visit) — عمدًا: على عكس
    حجز زيارة فعلي، أكتر من عقد ممكن يشير لنفس unit_id بالفعل في التصميم
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


# ── Units ────────────────────────────────────────────────────────────
# 2026-08-03: TimeshareUnit (مخزون الوحدات الفعلي) كان بدون أي مسار
# إنشاء/تعديل خالص — إضافة وحدة جديدة أو تعليمها "تحت الصيانة" مكان
# ممكن غير عن طريق الداتابيز مباشرة أو app.seed. مفيش DELETE عمدًا (زي
# باقي الكيانات المرجعية في المشروع — Outlet مثلاً) — تعطيل وحدة بيتم عبر
# status="maintenance"، مش حذف صف عليه FK حقيقية (عقود/زيارات).

def create_unit(db: Session, data: TimeshareUnitCreate) -> TimeshareUnit:
    if crud.get_unit_by_number(db, data.branch_id, data.unit_number):
        raise ValueError(f"الوحدة '{data.unit_number}' موجودة بالفعل في هذا الفرع")
    unit = crud.create_unit(db, data)
    db.commit()
    db.refresh(unit)
    return unit


def update_unit(db: Session, unit_id: int, data: TimeshareUnitUpdate) -> TimeshareUnit:
    unit = crud.get_unit(db, unit_id)
    if not unit:
        raise ValueError(f"الوحدة {unit_id} غير موجودة")
    changes = data.model_dump(exclude_unset=True)
    new_number = changes.get("unit_number")
    if new_number and new_number != unit.unit_number:
        existing = crud.get_unit_by_number(db, unit.branch_id, new_number)
        if existing and existing.id != unit.id:
            raise ValueError(f"الوحدة '{new_number}' موجودة بالفعل في هذا الفرع")
    unit = crud.update_unit(db, unit, data)
    db.commit()
    db.refresh(unit)
    return unit


# ── Visits ───────────────────────────────────────────────────────────

def create_visit(db: Session, data: TimeshareVisitCreate) -> TimeshareVisit:
    """يخصّص وحدة تايم شير فعلية للزيارة (real allocation، مش مجرد سطر تاريخ
    بلا أي حجز حقيقي) — مع منع تعارض حجز حقيقي (double-booking) على نفس
    الوحدة، بنفس منطق date-overlap المستخدم في pms.crud.get_available_rooms.

    ⚠️ باج تزامن حقيقي كان هنا: التحقق من التعارض (has_overlapping_visit/
    find_available_unit) وعملية الـ INSERT ما كانوش محميين بأي SELECT FOR
    UPDATE NOWAIT — يعني لو حصلت محاولتين حقيقيتين متزامنتين لتخصيص نفس
    الوحدة لنفس الفترة (نفس race condition اللي pms.services.create_booking
    بيمنعها بالظبط بقفل صف الغرفة)، الاتنين كانوا ممكن يعدّوا التحقق قبل ما
    أي واحدة تعمل commit ويتم تخصيص نفس الوحدة مرتين فعليًا. اتصلح بقفل صف
    الوحدة (with_for_update(nowait=True)) قبل إعادة التحقق من التعارض،
    بنفس نمط lock_room_for_booking بالظبط.

    ⚠️ باجان حقيقيان تانيان اتكشفوا واتصلحوا هنا (اختبار حي كمدير خدمة عملاء
    تايم شير): كان ممكن تخصيص وحدة فعلية لزيارة على عقد **ملغي بالفعل** (صفر
    تحقق من contract.status)، وكان ممكن كمان تحجز زيارة بتاريخ بعد
    contract.end_date (انتهاء مدة العقد) بدون أي رفض — يعني عميل عقده انتهى
    كان لسه يقدر ياخد وحدة فعلية من مخزون المنتجع."""
    contract = get_contract_or_404(db, data.contract_id)
    if data.check_out <= data.check_in:
        raise ValueError("check_out يجب أن يكون بعد check_in")
    if contract.status == "cancelled":
        raise ValueError(f"العقد {contract.contract_number} ملغي — لا يمكن حجز زيارة عليه")
    if contract.status == "expired":
        raise ValueError(f"العقد {contract.contract_number} منتهي — لا يمكن حجز زيارة عليه")
    if contract.end_date and data.check_in > contract.end_date:
        raise ValueError(
            f"تاريخ الزيارة بعد نهاية مدة العقد {contract.contract_number} "
            f"({contract.end_date.isoformat()}) — العقد منتهي لهذه الفترة"
        )
    if contract.booking_frozen:
        # سبب التجميد بيتحدد فعليًا وقت الرفض (أقساط/صيانة/الاتنين) — بدون
        # أي تغيير في البنية (booking_frozen يفضل flag واحد على العقد).
        reasons = []
        if any(i.status in ("overdue", "partial") for i in contract.installments_list):
            reasons.append("أقساط متأخرة")
        if any(d.status in ("overdue", "partial") for d in contract.maintenance_dues_list):
            reasons.append("رسوم صيانة متأخرة")
        reason_text = " و".join(reasons) if reasons else "متأخرات"
        raise ValueError(f"الحجز مجمَّد لوجود {reason_text} — سدِّد المتأخرات أولاً")
    nights = (data.check_out - data.check_in).days

    if contract.unit_id:
        candidate_id = contract.unit_id
    else:
        # عقد عائم — ابحث عن أي وحدة متاحة من نفس نوع الغرفة (قبل القفل، مجرد
        # ترشيح أولي) ثم اقفلها وأعد التحقق تحت الحماية فعليًا تحت.
        found = crud.find_available_unit(db, contract.branch_id, contract.room_type, data.check_in, data.check_out)
        if not found:
            raise ValueError(f"لا توجد وحدة متاحة من نوع {contract.room_type} في الفترة المطلوبة")
        candidate_id = found.id

    try:
        unit = crud.lock_unit_for_visit(db, candidate_id)
    except OperationalError:
        db.rollback()
        raise VisitConflictError(f"الوحدة {candidate_id} مقفولة الآن من عملية حجز أخرى — حاول مرة أخرى")

    if not unit:
        raise ValueError("الوحدة المخصَّصة لهذا العقد لم تعد موجودة")
    if unit.status == "maintenance":
        raise ValueError(f"الوحدة {unit.unit_number} تحت الصيانة حاليًا")
    # إعادة التحقق من التعارض بعد القفل — مفيش حد تاني يقدر يخصص نفس الوحدة
    # لنفس الفترة لحد ما الـ transaction دي تخلص (commit/rollback)
    if crud.has_overlapping_visit(db, unit.id, data.check_in, data.check_out):
        raise ValueError(f"الوحدة {unit.unit_number} محجوزة بالفعل في هذه الفترة")

    visit = crud.create_visit(db, data, nights, unit_id=unit.id)
    db.commit()
    db.refresh(visit)
    return visit


def update_visit(db: Session, visit_id: int, data: TimeshareVisitUpdate) -> TimeshareVisit:
    visit = crud.get_visit(db, visit_id)
    if not visit:
        raise ValueError(f"الزيارة {visit_id} غير موجودة")
    obj = crud.update_visit(db, visit, data)
    db.commit()
    db.refresh(obj)
    return obj


# ── Excel Batch Import ───────────────────────────────────────────────
# الصف الأول = أسماء الأعمدة (مطابقة لحقول TimeshareContractCreate)،
# الأعمدة الإلزامية: customer_name, room_type, total_value, down_payment,
# installments, start_date, first_installment_date. الباقي اختياري.
# Idempotent: لو form_number موجود بالفعل لنفس الفرع، الصف يتجاهَل (مش يتكرر).

_REQUIRED_COLUMNS = {
    "customer_name", "room_type", "total_value", "down_payment",
    "installments", "start_date", "first_installment_date",
}

_DATE_FIELDS = {"start_date", "end_date", "first_installment_date", "contract_date"}
_DECIMAL_FIELDS = {
    "total_value", "down_payment", "partner_share_pct", "purchase_price",
    "contract_deposit", "maintenance_fee", "maintenance_increase",
    "contract_value", "net_contract_value", "over_under_price",
}
_INT_FIELDS = {"week_number", "nights_per_year", "installments", "installment_period", "batch_number", "years_count"}
_BOOL_FIELDS = {"rci_included"}


def _coerce_cell(field: str, value):
    if value is None or value == "":
        return None
    if field in _DATE_FIELDS:
        from datetime import date as _date, datetime as _datetime  # noqa: PLC0415
        if isinstance(value, _datetime):
            return value.date()
        if isinstance(value, _date):
            return value
        return _datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    if field in _DECIMAL_FIELDS:
        from decimal import Decimal as _Decimal  # noqa: PLC0415
        return _Decimal(str(value))
    if field in _INT_FIELDS:
        return int(value)
    if field in _BOOL_FIELDS:
        return str(value).strip().lower() in ("1", "true", "yes", "y", "نعم")
    return str(value).strip()


def import_contracts_excel(
    db: Session, branch_id: int, file_content: bytes, signed_by: int,
) -> dict:
    import openpyxl  # noqa: PLC0415
    import io as _io  # noqa: PLC0415

    wb = openpyxl.load_workbook(_io.BytesIO(file_content), data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("الملف فاضي")

    headers = [str(h).strip() if h else "" for h in rows[0]]
    valid_fields = set(TimeshareContractCreate.model_fields.keys())
    missing = _REQUIRED_COLUMNS - set(headers)
    if missing:
        raise ValueError(f"أعمدة إلزامية ناقصة: {', '.join(sorted(missing))}")

    imported, skipped, errors = 0, 0, []

    for i, row in enumerate(rows[1:], start=2):
        row_dict = {h: v for h, v in zip(headers, row) if h}
        if not row_dict.get("customer_name"):
            continue
        try:
            payload = {"branch_id": branch_id}
            for field, raw_value in row_dict.items():
                if field in valid_fields:
                    payload[field] = _coerce_cell(field, raw_value)

            form_number = payload.get("form_number")
            if form_number and crud.get_contract_by_form_number(db, branch_id, str(form_number)):
                skipped += 1
                continue

            data = TimeshareContractCreate(**{k: v for k, v in payload.items() if v is not None or k == "branch_id"})

            # ⚠️ باج حقيقي كان هنا: form_number فاضي (شائع في الملفات
            # القديمة) كان بيتخطى فحص التكرار بالكامل — رفع نفس الملف مرتين
            # كان بيضاعف كل عقوده اللي من غير رقم فورمة. راجع
            # crud.get_contract_by_natural_key لتفاصيل المفتاح البديل.
            if not form_number and crud.get_contract_by_natural_key(
                db, branch_id, data.customer_name, data.unit_id, data.start_date, data.total_value,
            ):
                skipped += 1
                continue

            create_contract(db, data, signed_by)
            imported += 1
        except Exception as exc:
            errors.append(f"صف {i}: {str(exc)[:120]}")

    return {"imported": imported, "skipped": skipped, "errors": errors[:20]}


# ═══════════════════════════════════════════════════════════════════════════
# Owner Portal — بوابة صاحب العقد العامة (طلب Mohamed 2026-08-03)
#
# صفحة على الموقع العام يتحقق فيها صاحب عقد تايم شير من هويته (رقم العقد +
# رقم موبايله المسجّل على العقد + كود OTP يوصله واتساب — مفيش باسورد
# ولا حساب دائم، وده عمدًا: "ما يكونش معقد" + "السرية"). بعد التحقق بيشوف
# عقده وحالة دفعاته، ويقدر يقدّم طلب حجز زيارة (المدير هو اللي يوافق
# ويحدد الأسبوع الفعلي فعليًا — راجع approve_visit_request تحت، بتنادي
# create_visit الموجودة فوق فمفيش تكرار لمنطق التجميد/التعارض) أو يفتح
# تذكرة دعم (نظام مستقل عن استفسارات الموقع العام، مش نفس صندوق CRM Lead).
# ═══════════════════════════════════════════════════════════════════════════


class OwnerVerificationError(Exception):
    """كود OTP غلط/منتهي/العدد المسموح للمحاولات اتخلص، أو JWT owner-portal
    token غير صالح/منتهي."""


def _hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _normalize_phone_for_match(phone: str) -> str:
    """مقارنة أرقام الموبايل بعد تجريدها من أي رموز غير رقمية، ومقارنة آخر
    10 أرقام بس — العميل ممكن يكتب رقمه بصيغة دولية (+20...) مختلفة شوية
    عن الصيغة المسجّلة على العقد (01...)، من غير ما نطلب صيغة واحدة صارمة
    (طلب Mohamed: "سهولة المستخدم")."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def request_owner_otp(db: Session, contract_number: str, phone: str) -> None:
    """⚠️ أمان (anti-enumeration): الدالة دايمًا "تنجح" بصمت (بدون أي
    استثناء أو قيمة رجوع تكشف الفرق) بغض النظر عن تطابق رقم العقد/الموبايل
    من عدمه — لو فرّقنا الرد هيبقى oracle يقدر أي حد يجرّب أرقام عقود
    عشوائية ويكتشف أيها حقيقي بمجرد الفرق في رسالة الرد. الـOTP بيتبعت
    فعليًا واتساب بس لو التطابق صحيح فعلاً."""
    from app.core.config import settings  # noqa: PLC0415
    from app.core.kernel.cache import rate_limit, set_cache  # noqa: PLC0415
    from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415

    # مفتاحان منفصلان (رقم العقد + رقم الموبايل) — يمنعوا (أ) قصف نفس رقم
    # العقد بطلبات OTP متكررة، و(ب) محاولة تجربة أرقام عقود كتير مختلفة من
    # نفس رقم الموبايل.
    if not rate_limit(f"timeshare_otp_req_contract:{contract_number}", max_requests=3, window_seconds=600):
        return
    if not rate_limit(f"timeshare_otp_req_phone:{_normalize_phone_for_match(phone)}", max_requests=5, window_seconds=600):
        return

    contract = crud.get_contract_by_number(db, contract_number)
    if not contract or not contract.customer_phone:
        return
    if _normalize_phone_for_match(contract.customer_phone) != _normalize_phone_for_match(phone):
        return
    if contract.status == "cancelled":
        return

    code = f"{secrets.randbelow(1_000_000):06d}"
    set_cache(
        f"timeshare_otp:{contract_number}",
        {"code_hash": _hash_otp(code), "attempts": 0, "contract_id": contract.id},
        ttl=settings.TIMESHARE_OTP_TTL_SECONDS,
    )
    minutes = settings.TIMESHARE_OTP_TTL_SECONDS // 60
    send_whatsapp_message(
        contract.customer_phone,
        f"كود التحقق لبوابة عقدك في El Kheima Beach Resort: {code}\n"
        f"صالح لمدة {minutes} دقائق. لا تشارك هذا الكود مع أحد.",
    )


def _issue_owner_portal_token(contract_id: int) -> str:
    from app.core.config import settings  # noqa: PLC0415

    payload = {
        "sub": str(contract_id),
        "purpose": "timeshare_owner_portal",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.TIMESHARE_PORTAL_TOKEN_TTL_MINUTES),
    }
    return jwt.encode(payload, settings.TIMESHARE_PORTAL_TOKEN_SECRET, algorithm="HS256")


def confirm_owner_otp(db: Session, contract_number: str, otp_code: str) -> str:
    """يتحقق من الكود المُدخَل مقابل المخزَّن في الكاش (مقارنة زمن ثابت،
    نفس نمط TOTP consumption في kernel.auth.service)، ولو صح بيرجّع owner
    portal token (JWT) جاهز. الكود يُستهلك (single-use) عند النجاح، ويُلغى
    نهائيًا لو عدد المحاولات الخاطئة وصل الحد الأقصى (يمنع تخمين الكود
    بالقوة الغاشمة خلال نافذة الصلاحية القصيرة)."""
    from app.core.config import settings  # noqa: PLC0415
    from app.core.kernel.cache import clear_cache, get_cache, set_cache  # noqa: PLC0415

    cache_key = f"timeshare_otp:{contract_number}"
    entry = get_cache(cache_key)
    if not entry:
        raise OwnerVerificationError("الكود منتهي الصلاحية أو غير موجود — اطلب كود جديد")

    if not secrets.compare_digest(_hash_otp(otp_code), entry["code_hash"]):
        entry["attempts"] = entry.get("attempts", 0) + 1
        if entry["attempts"] >= settings.TIMESHARE_OTP_MAX_ATTEMPTS:
            clear_cache(cache_key)
            raise OwnerVerificationError("عدد محاولات خاطئة كبير — اطلب كود جديد")
        set_cache(cache_key, entry, ttl=settings.TIMESHARE_OTP_TTL_SECONDS)
        raise OwnerVerificationError("كود التحقق غير صحيح")

    clear_cache(cache_key)
    return _issue_owner_portal_token(entry["contract_id"])


def verify_owner_portal_token(token: str) -> int:
    """يرجّع contract_id لو التوكن صالح وموقّع صح، وإلا يرفع
    OwnerVerificationError (الراوتر بيترجمها 401)."""
    from app.core.config import settings  # noqa: PLC0415

    try:
        payload = jwt.decode(token, settings.TIMESHARE_PORTAL_TOKEN_SECRET, algorithms=["HS256"])
    except Exception:
        raise OwnerVerificationError("انتهت صلاحية الجلسة — تحقق من هويتك مرة أخرى")
    if payload.get("purpose") != "timeshare_owner_portal":
        raise OwnerVerificationError("جلسة غير صالحة")
    return int(payload["sub"])


def request_visit(db: Session, contract_id: int, data: TimeshareVisitRequestCreate) -> TimeshareVisitRequest:
    """طلب العميل نفسه — تحقق مبكر (عقد نشط، مش مجمَّد) عشان العميل ياخد
    رسالة واضحة فورًا بدل ما يقدّم طلب مصيره الرفض التلقائي عند المراجعة."""
    contract = get_contract_or_404(db, contract_id)
    if data.preferred_end <= data.preferred_start:
        raise ValueError("تاريخ النهاية يجب أن يكون بعد تاريخ البداية")
    if contract.status in ("cancelled", "expired"):
        raise ValueError("هذا العقد غير نشط حاليًا — يرجى التواصل مع خدمة العملاء")
    if contract.booking_frozen:
        raise ValueError("الحجز مجمَّد حاليًا بسبب متأخرات على العقد — يرجى التواصل مع خدمة العملاء")
    req = crud.create_visit_request(db, contract, data)
    db.commit()
    db.refresh(req)
    # 2026-08-04: مفيش أي تنبيه كان بيوصل لحد لما عميل يقدّم طلب زيارة — لازم
    # موظف يفتح تاب "طلبات الزيارة" بالصدفة يشوفه. باقي الموديول كله (أقساط/
    # صيانة/انتهاء عقد) بيستخدم واتساب حقيقي، فده كان استثناء غير مقصود.
    _notify_admin_new_visit_request(contract, req)
    return req


def _notify_admin_new_visit_request(contract: "TimeshareContract", req: "TimeshareVisitRequest") -> None:
    from app.core.kernel.whatsapp import notify_admin  # noqa: PLC0415

    notify_admin(
        f"📅 طلب زيارة جديد — {contract.customer_name} (عقد {contract.contract_number})\n"
        f"من {req.preferred_start.isoformat()} إلى {req.preferred_end.isoformat()}"
    )


def approve_visit_request(
    db: Session, request_id: int, check_in, check_out, approved_by: int,
) -> TimeshareVisitRequest:
    """موافقة مدير — بيحدد التواريخ الفعلية بنفسه (مش بالضرورة نفس تفضيل
    العميل)، وبتمرّ بنفس create_visit الموجودة فوق حرفيًا — صفر تكرار
    لمنطق منع التعارض/التجميد/انتهاء العقد."""
    req = crud.get_visit_request(db, request_id)
    if not req:
        raise ValueError(f"طلب الزيارة {request_id} غير موجود")
    if req.status != "pending":
        raise ValueError(f"طلب الزيارة {request_id} تمت مراجعته بالفعل ({req.status})")

    visit = create_visit(db, TimeshareVisitCreate(
        branch_id=req.branch_id, contract_id=req.contract_id,
        check_in=check_in, check_out=check_out, notes=req.notes,
    ))
    req.status = "approved"
    req.reviewed_by = approved_by
    req.reviewed_at = datetime.now(timezone.utc)
    req.visit_id = visit.id
    db.commit()
    db.refresh(req)
    # العميل مالوش أي جلسة دائمة (بوابة OTP بس) — من غير واتساب، الطريقة
    # الوحيدة إنه يعرف إن طلبه اتوافق عليه هي إنه يرجع يعمل OTP تاني بنفسه.
    if req.contract.customer_phone:
        from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415

        send_whatsapp_message(
            req.contract.customer_phone,
            f"تمت الموافقة على طلب زيارتك في El Kheima Beach Resort ✅\n"
            f"من {check_in.isoformat()} إلى {check_out.isoformat()}\n"
            f"للتفاصيل، ادخل على بوابة عقدك.",
        )
    return req


def reject_visit_request(db: Session, request_id: int, reason: str, reviewed_by: int) -> TimeshareVisitRequest:
    req = crud.get_visit_request(db, request_id)
    if not req:
        raise ValueError(f"طلب الزيارة {request_id} غير موجود")
    if req.status != "pending":
        raise ValueError(f"طلب الزيارة {request_id} تمت مراجعته بالفعل ({req.status})")
    req.status = "rejected"
    req.reviewed_by = reviewed_by
    req.reviewed_at = datetime.now(timezone.utc)
    req.rejection_reason = reason
    db.commit()
    db.refresh(req)
    if req.contract.customer_phone:
        from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415

        send_whatsapp_message(
            req.contract.customer_phone,
            f"للأسف تعذّرت الموافقة على طلب زيارتك في El Kheima Beach Resort.\n"
            f"السبب: {reason}\n"
            f"للتواصل مع خدمة العملاء، افتح تذكرة دعم من بوابة عقدك.",
        )
    return req


def submit_support_ticket(
    db: Session, contract_id: int, data: TimeshareSupportTicketCreate,
) -> TimeshareSupportTicket:
    contract = get_contract_or_404(db, contract_id)
    ticket = crud.create_support_ticket(db, contract, data)
    db.commit()
    db.refresh(ticket)
    from app.core.kernel.whatsapp import notify_admin  # noqa: PLC0415

    notify_admin(
        f"🎫 تذكرة دعم جديدة — {contract.customer_name} (عقد {contract.contract_number})\n"
        f"الموضوع: {ticket.subject}"
    )
    return ticket


def reply_to_ticket(
    db: Session, ticket_id: int, message: str,
    author_type: str, author_user_id: Optional[int] = None,
):
    ticket = crud.get_support_ticket(db, ticket_id)
    if not ticket:
        raise ValueError(f"تذكرة الدعم {ticket_id} غير موجودة")
    if ticket.status == "closed":
        raise ValueError("التذكرة مغلقة — لا يمكن الرد عليها")
    reply = crud.add_ticket_reply(db, ticket, message, author_type, author_user_id)
    # رد موظف على تذكرة "مفتوحة" جديدة يحوّلها "قيد المعالجة" تلقائيًا —
    # مؤشر بصري بسيط إنها اتشافت، من غير ما يحتاج الموظف يعدّل الحالة يدويًا
    # كل مرة يرد فيها.
    if author_type == "staff" and ticket.status == "open":
        ticket.status = "in_progress"
    db.commit()
    db.refresh(reply)
    # 2026-08-04: نفس الفجوة اللي في طلبات الزيارة — مفيش تنبيه في أي اتجاه.
    # رد الموظف لازم يوصل للعميل واتساب (مفيش جلسة دائمة يشوفها فيها)، ورد
    # العميل التاني (متابعة على تذكرة موجودة، مش أول رسالة) لازم يوصل
    # للموظف زي ما التذكرة الجديدة نفسها كانت بتوصّل بالفعل.
    if author_type == "staff" and ticket.contract.customer_phone:
        from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415

        send_whatsapp_message(
            ticket.contract.customer_phone,
            f"عندك رد جديد من خدمة العملاء على تذكرتك \"{ticket.subject}\" في El Kheima Beach Resort.\n"
            f"للاطلاع، ادخل على بوابة عقدك.",
        )
    elif author_type == "owner":
        from app.core.kernel.whatsapp import notify_admin  # noqa: PLC0415

        notify_admin(
            f"🎫 رد جديد من {ticket.contract.customer_name} على تذكرة \"{ticket.subject}\" "
            f"(عقد {ticket.contract.contract_number})"
        )
    return reply


def update_ticket_status(db: Session, ticket_id: int, new_status: str) -> TimeshareSupportTicket:
    ticket = crud.get_support_ticket(db, ticket_id)
    if not ticket:
        raise ValueError(f"تذكرة الدعم {ticket_id} غير موجودة")
    ticket.status = new_status
    if new_status in ("resolved", "closed"):
        ticket.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ticket)
    return ticket


# ═══════════════════════════════════════════════════════════════════════════
# Timeshare Staff — مدير التايم شير بيدير موظفي وحدته (طلب Mohamed 2026-08-03:
# "يتحكم بالموظفين التيم شير وحساباتهم"). نسخة مبسّطة ومعزولة من
# core.kernel.auth.service.AuthService.provision_staff_account — مقفولة على
# super_admin+step-up عمدًا (Gate 2B3A، مناسبة لإنشاء أي دور بما فيه أدوار
# حساسة)، مش مناسبة لمدير وحدة معزولة زي ده بيعمل حاجة واحدة بس (إنشاء
# timeshare_agent). role هنا ثابت دايمًا، مش قيمة بييجي بيها الطلب.
# ═══════════════════════════════════════════════════════════════════════════


def provision_timeshare_agent(
    db: Session, *, email: str, full_name: str, phone: Optional[str],
    branch_id: int, created_by: int, preferred_language: str = "ar",
) -> dict:
    """⚠️ باج توثيقي حقيقي اتصلح هنا: deps.py's get_timeshare_user كان
    بيدّعي إن timeshare_agent "بيحصل على UserPermission صريح على
    timeshare.access/view تلقائيًا عند إنشاء الحساب" — بس محدّش كان
    بيعمل ده فعليًا في provision_staff_account خالص (صفر استخدام لـ
    UserPermission هناك). هنا فعليًا بيتعمل، مش مجرد كومنت."""
    import json  # noqa: PLC0415
    import secrets as _secrets  # noqa: PLC0415

    from sqlalchemy import func  # noqa: PLC0415

    from app.core.kernel.models.user import User  # noqa: PLC0415
    from app.core.kernel.security import get_password_hash, validate_email_format  # noqa: PLC0415
    from app.modules.core.models import AuditLog, Branch, UserBranchMembership, UserPermission  # noqa: PLC0415

    normalized_email = (email or "").strip().casefold()
    normalized_name = (full_name or "").strip()
    normalized_phone = (phone or "").strip() or None

    if not validate_email_format(normalized_email):
        raise ValueError("بريد إلكتروني غير صالح")
    if len(normalized_name) < 3:
        raise ValueError("الاسم الكامل مطلوب")
    if preferred_language not in {"ar", "en"}:
        raise ValueError("لغة غير مدعومة")

    branch = db.query(Branch).filter(Branch.id == branch_id, Branch.is_active.is_(True)).first()
    if branch is None:
        raise ValueError("الفرع غير موجود أو غير نشط")

    existing = db.query(User).filter(func.lower(User.email) == normalized_email).first()
    if existing is not None:
        raise ValueError("يوجد حساب بهذا البريد الإلكتروني بالفعل")

    temporary_password = _secrets.token_urlsafe(12)
    user = User(
        email=normalized_email,
        password_hash=get_password_hash(temporary_password),
        full_name=normalized_name,
        phone=normalized_phone,
        role="timeshare_agent",
        is_active=True,
        preferred_language=preferred_language,
        must_change_password=True,
        # timeshare_agent مش من MANDATORY_2FA_ROLES (super_admin/accountant
        # بس) — مفيش داعي لرحلة enrollment token زي الأدوار الحساسة.
        two_factor_enabled=False,
        two_factor_bootstrap_required=False,
    )
    db.add(user)
    db.flush()
    db.add(UserBranchMembership(
        user_id=user.id, branch_id=branch_id, is_default=True, is_active=True, created_by=created_by,
    ))
    db.add(UserPermission(
        user_id=user.id, resource="timeshare.access", action="view",
        allowed=True, branch_id=None, granted_by=created_by,
    ))
    db.add(AuditLog(
        user_id=created_by, branch_id=branch_id, action="timeshare_agent_provisioned",
        entity_type="user", entity_id=user.id, old_data=None,
        new_data=json.dumps({"email": normalized_email, "full_name": normalized_name}, ensure_ascii=False),
    ))
    db.commit()
    db.refresh(user)
    return {
        "id": user.id, "email": user.email, "full_name": user.full_name,
        "temporary_password": temporary_password, "must_change_password": True,
    }


def list_timeshare_staff(db: Session, branch_id: int) -> list:
    from app.core.kernel.models.user import User  # noqa: PLC0415
    from app.modules.core.models import UserBranchMembership  # noqa: PLC0415

    return (
        db.query(User)
        .join(UserBranchMembership, UserBranchMembership.user_id == User.id)
        .filter(
            UserBranchMembership.branch_id == branch_id,
            User.role == "timeshare_agent",
        )
        .order_by(User.full_name)
        .all()
    )


def set_timeshare_staff_active(db: Session, staff_user_id: int, is_active: bool):
    """تفعيل/تعطيل حساب موظف تايم شير — لازم revoke_user_tokens() (قاعدة
    ❻ في CLAUDE.md: أي تغيير is_active لازم يُبطل التوكنات القديمة فورًا،
    وإلا موظف اتعطّل حسابه يقدر يفضل شغال بتوكن قديم لحد ما ينتهي وحده)."""
    from app.core.deps import revoke_user_tokens  # noqa: PLC0415
    from app.core.kernel.models.user import User  # noqa: PLC0415

    user = db.query(User).filter(User.id == staff_user_id, User.role == "timeshare_agent").first()
    if not user:
        raise ValueError(f"موظف التايم شير {staff_user_id} غير موجود")
    user.is_active = is_active
    db.commit()
    revoke_user_tokens(user.id)
    db.refresh(user)
    return user
