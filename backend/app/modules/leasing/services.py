"""app/modules/leasing/services.py"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.leasing import crud
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
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db, contract.branch_id, local_today(settings.TIMEZONE),
        debit_account_code="1100", credit_account_code="2150",
        amount=contract.security_deposit or Decimal("0"),
        reference=f"LC-DEP-{contract.contract_number}",
        description=f"تأمين عقد إيجار — {contract.contract_number} ({contract.tenant_name})",
        source="leasing", source_id=contract.id,
        created_by=contract.signed_by or 0,
    )


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

        if collected_amount <= 0:
            return

        cash_acc    = get_account_by_code(db, contract.branch_id, "1100")
        tenant_ar    = get_account_by_code(db, contract.branch_id, "1260")
        revenue_acc = get_account_by_code(db, contract.branch_id, "4500")
        if not cash_acc or not tenant_ar or not revenue_acc:
            return

        entry_date = local_today(settings.TIMEZONE)
        ref = f"LSE-{source_obj.id:06d}"
        create_journal_entry(db, JournalEntryCreate(
            branch_id=contract.branch_id,
            entry_date=entry_date,
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
            entry_date=entry_date,
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


def pay_payment(db: Session, payment_id: int, req: PayLeaseRequest) -> LeasePayment:
    """⚠️ نفس فئة الباجين اللي اتصلحوا قبل كده في `timeshare.services.pay_installment`
    (الموديول الشقيق)، اتكشفوا هنا كمان أثناء اختبار حي كمدير إيجارات — الكود كان
    منسوخ جزئيًا من غير الإصلاحين:
    1. مفيش أي تحقق من حالة العقد — كان ممكن تسجّل تحصيل إيجار على عقد **مفسوخ**
       أو **منتهي** فعليًا.
    2. مفيش أي حد أقصى على المبلغ — إدخال 50,000 على دفعة قيمتها 5,000 كان
       بيتقبل بصمت (paid_amount بيبقى أكبر من amount+penalty، والحالة بتبقى
       "paid" من غير أي تنبيه أو تسجيل فرق) — باج مالي حقيقي، مش نظري.
    """
    payment = crud.get_payment(db, payment_id)
    if not payment:
        raise ValueError(f"الدفعة {payment_id} غير موجودة")
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
