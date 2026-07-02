"""app/modules/leasing/services.py"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.leasing import crud
from app.modules.leasing.models import LeaseContract, LeasePayment, TenantCashLog
from app.modules.leasing.schemas import (
    LeaseContractCreate, LeaseContractUpdate, PayLeaseRequest, TenantCashLogCreate,
)
from app.resort_os.timeshare_engine import generate_lease_monthly_schedule

# عقوبة تأخر الإيجار (resort-os-docs/12-TIMESHARE-COMPLETE.md § "عقوبة تأخر
# الإيجار"): 5% للتأخير 8-30 يوم، 10% لأكثر من 30 يوم. القيم القديمة هنا
# (3/15 يوم) كانت غير مطابقة للسبيك — اتصححت 2026-07-01 بعد مراجعة Task B.
PENALTY_TIER1_DAYS = 8
PENALTY_TIER1_RATE = Decimal("0.05")
PENALTY_TIER2_DAYS = 30
PENALTY_TIER2_RATE = Decimal("0.10")


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

    # قيد التأمين (12-TIMESHARE-COMPLETE.md § "قيود الإيجار التلقائية"):
    # Dr. الصندوق (1100) / Cr. تأمينات مستأجرين (2150) — كان مفقود بالكامل
    # قبل مراجعة Task B، فمالوش أي عقد إيجار قيد محاسبي رغم إنه موديول مالي.
    _post_deposit_journal(db, contract)

    db.commit()
    db.refresh(contract)
    return contract


def _post_deposit_journal(db: "Session", contract: "LeaseContract") -> None:
    """Dr. الصندوق (1100) / Cr. تأمينات مستأجرين (2150) عند إنشاء عقد بتأمين."""
    try:
        from app.modules.finance.crud import get_account_by_code, create_journal_entry  # noqa: PLC0415
        from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate  # noqa: PLC0415
        from datetime import date as _date  # noqa: PLC0415

        amount = contract.security_deposit or Decimal("0")
        if amount <= 0:
            return

        cash_acc    = get_account_by_code(db, contract.branch_id, "1100")
        deposit_acc = get_account_by_code(db, contract.branch_id, "2150")
        if not cash_acc or not deposit_acc:
            return

        entry_data = JournalEntryCreate(
            branch_id=contract.branch_id,
            entry_date=_date.today(),
            reference=f"LC-DEP-{contract.contract_number}",
            description=f"تأمين عقد إيجار — {contract.contract_number} ({contract.tenant_name})",
            source="leasing",
            source_id=contract.id,
            lines=[
                JournalLineCreate(account_id=cash_acc.id,    debit=amount,  credit=Decimal("0")),
                JournalLineCreate(account_id=deposit_acc.id, debit=Decimal("0"), credit=amount),
            ],
        )
        create_journal_entry(db, entry_data, contract.signed_by or 0)
    except Exception:
        pass


def _post_rent_collection_journal(db: "Session", source_obj, contract: "LeaseContract", collected_amount: Decimal) -> None:
    """قيدان عند تحصيل الإيجار (12-TIMESHARE-COMPLETE.md):
    1) Dr. الصندوق (1100) / Cr. ذمم مستأجرين (1260) — تحصيل نقدي
    2) Dr. ذمم مستأجرين (1260) / Cr. إيرادات إيجارات تجارية (4500) — إثبات الإيراد

    `source_obj` أي صف عنده `.id` (LeasePayment أو TenantCashLog) — بيُستخدم
    كمرجع بس في الـ reference/source_id.
    """
    try:
        from app.modules.finance.crud import get_account_by_code, create_journal_entry  # noqa: PLC0415
        from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate  # noqa: PLC0415
        from datetime import date as _date  # noqa: PLC0415

        if collected_amount <= 0:
            return

        cash_acc    = get_account_by_code(db, contract.branch_id, "1100")
        tenant_ar    = get_account_by_code(db, contract.branch_id, "1260")
        revenue_acc = get_account_by_code(db, contract.branch_id, "4500")
        if not cash_acc or not tenant_ar or not revenue_acc:
            return

        ref = f"LSE-{source_obj.id:06d}"
        create_journal_entry(db, JournalEntryCreate(
            branch_id=contract.branch_id,
            entry_date=_date.today(),
            reference=ref,
            description=f"تحصيل إيجار — {contract.contract_number} ({contract.tenant_name})",
            source="leasing",
            source_id=source_obj.id,
            lines=[
                JournalLineCreate(account_id=cash_acc.id, debit=collected_amount, credit=Decimal("0")),
                JournalLineCreate(account_id=tenant_ar.id, debit=Decimal("0"), credit=collected_amount),
            ],
        ), contract.signed_by or 0)
        create_journal_entry(db, JournalEntryCreate(
            branch_id=contract.branch_id,
            entry_date=_date.today(),
            reference=ref,
            description=f"إثبات إيراد إيجار — {contract.contract_number}",
            source="leasing",
            source_id=source_obj.id,
            lines=[
                JournalLineCreate(account_id=tenant_ar.id, debit=collected_amount, credit=Decimal("0")),
                JournalLineCreate(account_id=revenue_acc.id, debit=Decimal("0"), credit=collected_amount),
            ],
        ), contract.signed_by or 0)
    except Exception:
        pass


def update_contract(db: Session, contract_id: int, data: LeaseContractUpdate) -> LeaseContract:
    contract = get_contract_or_404(db, contract_id)
    obj = crud.update_contract(db, contract, data)
    db.commit()
    db.refresh(obj)
    return obj


def calculate_penalty(payment: LeasePayment, as_of: date | None = None) -> Decimal:
    """يحسب الغرامة بناءً على أيام التأخير: 5% بعد 8 أيام، 10% بعد 30 يوماً
    (مطابق لـ resort-os-docs/12-TIMESHARE-COMPLETE.md)."""
    today = as_of or date.today()
    if payment.status == "paid" or payment.due_date >= today:
        return Decimal("0")
    overdue_days = (today - payment.due_date).days
    if overdue_days >= PENALTY_TIER2_DAYS:
        return (payment.amount * PENALTY_TIER2_RATE).quantize(Decimal("0.01"))
    if overdue_days >= PENALTY_TIER1_DAYS:
        return (payment.amount * PENALTY_TIER1_RATE).quantize(Decimal("0.01"))
    return Decimal("0")


def apply_penalties(db: Session, contract_id: int) -> list[LeasePayment]:
    """يحدّث غرامات التأخير لجميع الدفعات المتأخرة."""
    contract = get_contract_or_404(db, contract_id)
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


def pay_payment(db: Session, payment_id: int, req: PayLeaseRequest) -> LeasePayment:
    payment = crud.get_payment(db, payment_id)
    if not payment:
        raise ValueError(f"الدفعة {payment_id} غير موجودة")
    if payment.status == "paid":
        raise ValueError("الدفعة مسددة بالكامل مسبقاً")
    contract = get_contract_or_404(db, payment.contract_id)
    obj = crud.pay_payment(db, payment, req)
    _post_rent_collection_journal(db, obj, contract, req.paid_amount)
    db.commit()
    db.refresh(obj)
    return obj


def record_cash_log(db: Session, data: TenantCashLogCreate, recorded_by: int) -> TenantCashLog:
    """تسجيل تسوية كاش يومية مع مستأجر (مركز غوص/واتر سبورت) — خارج دورة
    الاستحقاق الشهرية العادية. لو النوع rent_payment أو revenue_share، بيرحّل
    قيد محاسبي زي تحصيل الإيجار العادي (نفس حسابات 1100/1260/4500)."""
    contract = get_contract_or_404(db, data.contract_id)
    log = crud.create_cash_log(db, data, recorded_by)

    if data.activity_type in ("rent_payment", "revenue_share"):
        _post_rent_collection_journal(db, log, contract, data.amount)

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

    penalty = calculate_penalty(payment)
    total = float(payment.paid_amount or payment.amount) + float(payment.penalty or 0)

    fields = [
        ("المستأجر",       contract.tenant_name),
        ("الوحدة",         contract.unit_description),
        ("رقم العقد",      contract.contract_number),
        ("تاريخ الاستحقاق", str(payment.due_date)),
        ("مبلغ الإيجار",   f"{payment.amount:,.2f} EGP"),
    ]
    if payment.penalty and payment.penalty > 0:
        fields.append(("غرامة التأخير", f"{payment.penalty:,.2f} EGP"))
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
