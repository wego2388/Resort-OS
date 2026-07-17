"""app/modules/finance/crud.py — CRUD خالص، لا business logic"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.resort_os.timezone_utils import local_today, utc_naive_to_local_date

from app.modules.finance.models import (
    Account, AccountingPeriod, AssetDepreciationEntry, BankAccount, BankStatementLine,
    CashierShift, CashierShiftCashCount, CashMovement, ConditionalDiscount,
    CostCenter, ETAInvoice, ExchangeRate, Folio, FolioCharge, JournalEntry, JournalLine, Payment,
    Check, CheckMovement, RevenueAuditLog,
)
from app.modules.finance.schemas import (
    AccountCreate, BankAccountCreate, BankAccountUpdate, BankStatementLineCreate,
    ConditionalDiscountCreate, ConditionalDiscountUpdate,
    CostCenterCreate, ExchangeRateCreate, FolioCreate, FolioChargeCreate,
    JournalEntryCreate, PaymentCreate,
)


# ── ETA Invoice ──────────────────────────────────────────────────────

def create_eta_invoice(
    db: Session, branch_id: int, folio_id: Optional[int],
    internal_id: str, document_json: str,
) -> ETAInvoice:
    inv = ETAInvoice(
        branch_id=branch_id, folio_id=folio_id,
        internal_id=internal_id, document_json=document_json,
        status="pending",
    )
    db.add(inv)
    db.flush()
    return inv


def get_eta_invoice(db: Session, invoice_id: int) -> Optional[ETAInvoice]:
    return db.query(ETAInvoice).filter(ETAInvoice.id == invoice_id).first()


def list_eta_invoices(
    db: Session, branch_id: int, status: Optional[str] = None,
    skip: int = 0, limit: int = 50,
) -> tuple[list[ETAInvoice], int]:
    q = db.query(ETAInvoice).filter(ETAInvoice.branch_id == branch_id)
    if status:
        q = q.filter(ETAInvoice.status == status)
    total = q.count()
    items = q.order_by(ETAInvoice.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def mark_eta_invoice_submitted(
    db: Session, invoice: ETAInvoice, *,
    status: str, submission_uuid: Optional[str] = None,
    long_id: Optional[str] = None, response_json: Optional[str] = None,
    error_message: Optional[str] = None,
) -> ETAInvoice:
    invoice.status = status
    invoice.submission_uuid = submission_uuid
    invoice.long_id = long_id
    invoice.response_json = response_json
    invoice.error_message = error_message
    invoice.submitted_at = datetime.utcnow()
    db.commit()
    db.refresh(invoice)
    return invoice


# ── ConditionalDiscount ───────────────────────────────────────────────

def get_discount(db: Session, discount_id: int) -> Optional[ConditionalDiscount]:
    return db.query(ConditionalDiscount).filter(ConditionalDiscount.id == discount_id).first()


def list_discounts(
    db: Session,
    branch_id: int,
    active_only: bool = True,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[ConditionalDiscount], int]:
    q = db.query(ConditionalDiscount).filter(ConditionalDiscount.branch_id == branch_id)
    if active_only:
        q = q.filter(ConditionalDiscount.is_active.is_(True))
    total = q.count()
    items = q.order_by(ConditionalDiscount.priority.desc()).offset(skip).limit(limit).all()
    return items, total


def create_discount(db: Session, data: ConditionalDiscountCreate) -> ConditionalDiscount:
    obj = ConditionalDiscount(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def update_discount(
    db: Session,
    discount: ConditionalDiscount,
    data: ConditionalDiscountUpdate,
) -> ConditionalDiscount:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(discount, field, value)
    db.flush()
    return discount


def delete_discount(db: Session, discount: ConditionalDiscount) -> None:
    db.delete(discount)
    db.flush()


def increment_discount_uses(db: Session, discount_id: int) -> None:
    row = get_discount(db, discount_id)
    if row:
        row.uses_count += 1
        db.flush()


# ── Folio ─────────────────────────────────────────────────────────────

def get_folio(db: Session, folio_id: int) -> Optional[Folio]:
    return db.query(Folio).filter(Folio.id == folio_id).first()


def list_folios(
    db: Session,
    branch_id: int,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Folio], int]:
    q = db.query(Folio).filter(Folio.branch_id == branch_id)
    if status:
        q = q.filter(Folio.status == status)
    if date_from:
        q = q.filter(Folio.check_in >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(Folio.check_in <= datetime.combine(date_to, datetime.max.time()))
    total = q.count()
    items = q.order_by(Folio.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def create_folio(db: Session, data: FolioCreate) -> Folio:
    folio = Folio(**data.model_dump())
    db.add(folio)
    db.flush()
    return folio


def close_folio(db: Session, folio: Folio) -> Folio:
    folio.status = "closed"
    db.flush()
    return folio


# ── FolioCharge ───────────────────────────────────────────────────────

def add_charge(db: Session, folio_id: int, data: FolioChargeCreate) -> FolioCharge:
    charge = FolioCharge(folio_id=folio_id, **data.model_dump())
    db.add(charge)
    db.flush()
    return charge


def get_charge_by_ref_beach_tx(db: Session, beach_tx_id: int) -> Optional[FolioCharge]:
    """يجيب شحنة الفوليو المرتبطة بعملية شاطئ معيّنة (Charge to Room) — يُستخدم
    عند إلغاء (void) عملية شاطئ محمّلة على غرفة، عشان الإلغاء يشيل الشحنة من
    فاتورة الضيف كمان مش بس يعكس المخزون."""
    return db.query(FolioCharge).filter(FolioCharge.ref_beach_tx_id == beach_tx_id).first()


def delete_charge(db: Session, charge: FolioCharge) -> None:
    db.delete(charge)
    db.flush()


def settle_all_charges(db: Session, folio: Folio) -> None:
    for charge in folio.charges:
        charge.is_settled = True
    db.flush()


def recalculate_folio_total(db: Session, folio: Folio) -> Folio:
    db.expire(folio, ["charges"])
    folio.total = sum(
        (
            c.amount + (c.vat_amount or Decimal("0")) + (c.service_charge or Decimal("0"))
            for c in folio.charges
        ),
        Decimal("0"),
    )
    db.flush()
    return folio


# ── Payment ───────────────────────────────────────────────────────────

def get_payment(db: Session, payment_id: int) -> Optional[Payment]:
    return db.query(Payment).filter(Payment.id == payment_id).first()


def list_payments(db: Session, folio_id: int) -> list[Payment]:
    return (
        db.query(Payment)
        .filter(Payment.folio_id == folio_id, Payment.voided_at.is_(None))
        .order_by(Payment.posted_at)
        .all()
    )


def get_direct_payment_by_reference(db: Session, branch_id: int, reference: str) -> Optional[Payment]:
    """يلاقي دفعة POS مباشرة (folio_id=None، راجع create_direct_payment) بالـ
    reference الفريد بتاعها (زي "BCH-000123") — مستخدمة وقت إلغاء بيع مباشر
    عشان نعكس/نلغي الدفعة المقابلة، مش القيد المحاسبي بس."""
    return (
        db.query(Payment)
        .filter(
            Payment.branch_id == branch_id,
            Payment.folio_id.is_(None),
            Payment.reference == reference,
            Payment.voided_at.is_(None),
        )
        .first()
    )


def create_payment(
    db: Session, data: PaymentCreate, shift_id: Optional[int] = None, currency: str = "EGP",
) -> Payment:
    payment = Payment(**data.model_dump(), shift_id=shift_id, currency=currency)
    db.add(payment)
    db.flush()
    return payment


def create_direct_payment(
    db: Session,
    branch_id: int,
    amount: Decimal,
    method: str,
    posted_at: datetime,
    shift_id: Optional[int] = None,
    cashier_id: Optional[int] = None,
    reference: Optional[str] = None,
    ref_order_id: Optional[int] = None,
    currency: str = "EGP",
) -> Payment:
    """يسجّل دفعة POS مباشرة (folio_id=None) — بيع نقدي/كارت فوري من موديول
    عمل تاني (شاطئ/دايننج) مش محمّل على فوليو غرفة، عشان يظهر في تقرير نهاية
    الوردية (build_shift_end_report بيقرا Payment.shift_id بس — راجع تعليق
    Payment في models.py). دالة داخلية (مش عبر PaymentCreate العامة اللي
    folio_id فيها إجباري لمسار تسوية الفوليو)، مفيش HTTPException هنا زي
    باقي crud.py."""
    payment = Payment(
        folio_id=None, branch_id=branch_id, amount=amount, currency=currency,
        method=method, reference=reference, posted_at=posted_at,
        cashier_id=cashier_id, shift_id=shift_id, ref_order_id=ref_order_id,
    )
    db.add(payment)
    db.flush()
    return payment


def void_payment(db: Session, payment: Payment, voided_by: int) -> Payment:
    payment.voided_at = datetime.utcnow()
    payment.voided_by = voided_by
    db.flush()
    return payment


# ── Revenue Audit Log ────────────────────────────────────────────────

def create_revenue_audit_log(
    db: Session,
    branch_id: int,
    entity_type: str,
    entity_id: int,
    old_value: Decimal,
    new_value: Decimal,
    reason: str,
    changed_by: int,
    approved_by: Optional[int] = None,
) -> RevenueAuditLog:
    log = RevenueAuditLog(
        branch_id=branch_id, entity_type=entity_type, entity_id=entity_id,
        old_value=old_value, new_value=new_value, reason=reason,
        changed_by=changed_by, approved_by=approved_by,
    )
    db.add(log)
    db.flush()
    return log


def list_revenue_audit_logs(
    db: Session,
    branch_id: int,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
) -> list[RevenueAuditLog]:
    q = db.query(RevenueAuditLog).filter(RevenueAuditLog.branch_id == branch_id)
    if entity_type:
        q = q.filter(RevenueAuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(RevenueAuditLog.entity_id == entity_id)
    return q.order_by(RevenueAuditLog.created_at.desc()).all()


# ── CashierShift (POS Day / Safe) ──────────────────────────────────────

def get_open_shift(db: Session, branch_id: int, cashier_id: int) -> Optional[CashierShift]:
    return (
        db.query(CashierShift)
        .filter(
            CashierShift.branch_id == branch_id,
            CashierShift.cashier_id == cashier_id,
            CashierShift.status == "open",
        )
        .first()
    )


def get_shift(db: Session, shift_id: int) -> Optional[CashierShift]:
    return db.query(CashierShift).filter(CashierShift.id == shift_id).first()


def create_shift(
    db: Session, branch_id: int, cashier_id: int, opened_by: int,
    opening_float: Decimal, notes: Optional[str] = None,
) -> CashierShift:
    row = CashierShift(
        branch_id=branch_id, cashier_id=cashier_id,
        opened_at=datetime.utcnow(), opened_by=opened_by,
        opening_float=opening_float, notes=notes,
    )
    db.add(row)
    db.flush()
    return row


def list_shifts(
    db: Session, branch_id: int,
    cashier_id: Optional[int] = None, status: Optional[str] = None,
    skip: int = 0, limit: int = 50,
) -> tuple[list[CashierShift], int]:
    q = db.query(CashierShift).filter(CashierShift.branch_id == branch_id)
    if cashier_id:
        q = q.filter(CashierShift.cashier_id == cashier_id)
    if status:
        q = q.filter(CashierShift.status == status)
    total = q.count()
    items = q.order_by(CashierShift.opened_at.desc()).offset(skip).limit(limit).all()
    return items, total


def create_cash_movement(
    db: Session, branch_id: int, shift_id: int, movement_type: str,
    amount: Decimal, reason: str, performed_by: int, approved_by: Optional[int] = None,
) -> CashMovement:
    row = CashMovement(
        branch_id=branch_id, shift_id=shift_id, movement_type=movement_type,
        amount=amount, reason=reason, performed_by=performed_by, approved_by=approved_by,
    )
    db.add(row)
    db.flush()
    return row


def list_cash_movements(db: Session, shift_id: int) -> list[CashMovement]:
    # created_at وحدها مش كافية للترتيب — أكتر من حركة في نفس المعاملة/نفس
    # المللي ثانية ممكن ياخدوا نفس القيمة بالظبط، فـ id.desc() (تايبريك
    # حتمي، بيزيد بترتيب الإدخال دايمًا) هو الأدق لـ "الأحدث الأول".
    return (
        db.query(CashMovement)
        .filter(CashMovement.shift_id == shift_id)
        .order_by(CashMovement.created_at.desc(), CashMovement.id.desc())
        .all()
    )


def get_latest_closed_shift(db: Session, branch_id: int) -> Optional[CashierShift]:
    return (
        db.query(CashierShift)
        .filter(CashierShift.branch_id == branch_id, CashierShift.status == "closed")
        .order_by(CashierShift.closed_at.desc())
        .first()
    )


def create_cash_count_lines(
    db: Session, shift_id: int, lines: list[dict],
) -> list[CashierShiftCashCount]:
    """
    lines: قائمة dicts بالمفاتيح التالية:
      - denomination: Decimal — قيمة الورقة/القطعة
      - currency: str — عملة هذا السطر (افتراضي "EGP")
      - quantity: int
      - fx_rate: Decimal — سعر الصرف لـ EGP (افتراضي 1.0 للـ EGP)
    egp_equivalent يتحسب تلقائياً = denomination × quantity × fx_rate
    """
    from decimal import Decimal  # noqa: PLC0415
    rows = []
    for line in lines:
        denom    = line["denomination"]
        currency = line.get("currency", "EGP") or "EGP"
        qty      = line["quantity"]
        fx_rate  = line.get("fx_rate", Decimal("1")) or Decimal("1")
        subtotal = denom * qty
        egp_eq   = (subtotal * fx_rate).quantize(Decimal("0.01"))
        rows.append(CashierShiftCashCount(
            shift_id=shift_id,
            denomination=denom,
            currency=currency.upper(),
            quantity=qty,
            subtotal=subtotal,
            fx_rate=fx_rate,
            egp_equivalent=egp_eq,
        ))
    db.add_all(rows)
    db.flush()
    return rows


def list_cash_count_lines(db: Session, shift_id: int) -> list[CashierShiftCashCount]:
    return (
        db.query(CashierShiftCashCount)
        .filter(CashierShiftCashCount.shift_id == shift_id)
        .order_by(CashierShiftCashCount.denomination.desc())
        .all()
    )


def get_previous_closed_shift(
    db: Session, branch_id: int, cashier_id: int, before_shift_id: int, before_opened_at: datetime,
) -> Optional[CashierShift]:
    return (
        db.query(CashierShift)
        .filter(
            CashierShift.branch_id == branch_id,
            CashierShift.cashier_id == cashier_id,
            CashierShift.status == "closed",
            CashierShift.id != before_shift_id,
            CashierShift.opened_at < before_opened_at,
        )
        .order_by(CashierShift.opened_at.desc())
        .first()
    )


def payments_for_shift(db: Session, shift_id: int) -> list[Payment]:
    return db.query(Payment).filter(Payment.shift_id == shift_id).all()


def list_shift_payments_with_folio(db: Session, shift_id: int) -> list[Payment]:
    """دفعات الوردية مع الفوليو محمّل مسبقًا (joinedload) — لسجل فواتير
    الوردية (InvoiceLogModal، wagdy.md بند S-02)، عشان نعرض اسم الضيف بدون
    N+1 query لكل دفعة (مختلف عن payments_for_shift فوق، المستخدمة للتجميع
    الرقمي بس في build_shift_end_report من غير أي حاجة لبيانات الفوليو)."""
    return (
        db.query(Payment)
        .options(joinedload(Payment.folio))
        .filter(Payment.shift_id == shift_id)
        .order_by(Payment.posted_at.desc())
        .all()
    )


# ── Account (Chart of Accounts) ───────────────────────────────────────

def create_account(db: Session, data: AccountCreate) -> Account:
    account = Account(**data.model_dump())
    db.add(account)
    db.flush()
    return account


def get_account_by_code(db: Session, branch_id: int, code: str) -> Optional[Account]:
    return (
        db.query(Account)
        .filter(Account.branch_id == branch_id, Account.code == code)
        .first()
    )


def list_accounts(
    db: Session,
    branch_id: int,
    active_only: bool = True,
    skip: int = 0,
    limit: int = 200,
) -> tuple[list[Account], int]:
    q = db.query(Account).filter(Account.branch_id == branch_id)
    if active_only:
        q = q.filter(Account.is_active.is_(True))
    total = q.count()
    items = q.order_by(Account.code).offset(skip).limit(limit).all()
    return items, total


# ── JournalEntry ──────────────────────────────────────────────────────

def create_journal_entry(
    db: Session,
    data: JournalEntryCreate,
    user_id: int,
) -> JournalEntry:
    entry = JournalEntry(
        branch_id=data.branch_id,
        entry_date=data.entry_date,
        reference=data.reference,
        description=data.description,
        status="posted",
        created_by=user_id,
        source=data.source,
        source_id=data.source_id,
        currency=data.currency,
        fx_rate=data.fx_rate,
    )
    db.add(entry)
    db.flush()
    for line_data in data.lines:
        line = JournalLine(
            entry_id=entry.id,
            account_id=line_data.account_id,
            debit=line_data.debit,
            credit=line_data.credit,
            description=line_data.description,
            cost_center_id=line_data.cost_center_id,
        )
        db.add(line)
    db.flush()
    return entry


def get_journal_entry(db: Session, entry_id: int) -> Optional[JournalEntry]:
    return db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()


def list_journal_entries(
    db: Session,
    branch_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    source: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[JournalEntry], int]:
    q = db.query(JournalEntry).filter(JournalEntry.branch_id == branch_id)
    if date_from:
        q = q.filter(JournalEntry.entry_date >= date_from)
    if date_to:
        q = q.filter(JournalEntry.entry_date <= date_to)
    if source:
        q = q.filter(JournalEntry.source == source)
    total = q.count()
    items = q.order_by(JournalEntry.entry_date.desc()).offset(skip).limit(limit).all()
    return items, total


# ── AccountingPeriod ──────────────────────────────────────────────────

def get_period_status(
    db: Session,
    branch_id: int,
    year: int,
    month: int,
) -> Optional[AccountingPeriod]:
    return (
        db.query(AccountingPeriod)
        .filter(
            AccountingPeriod.branch_id == branch_id,
            AccountingPeriod.year == year,
            AccountingPeriod.month == month,
        )
        .first()
    )


def close_period(
    db: Session,
    branch_id: int,
    year: int,
    month: int,
    closed_by: int,
) -> AccountingPeriod:
    period = get_period_status(db, branch_id, year, month)
    if not period:
        period = AccountingPeriod(
            branch_id=branch_id,
            year=year,
            month=month,
            status="closed",
            closed_by=closed_by,
            closed_at=datetime.utcnow(),
        )
        db.add(period)
    else:
        period.status = "closed"
        period.closed_by = closed_by
        period.closed_at = datetime.utcnow()
    db.flush()
    return period


def list_periods(
    db: Session,
    branch_id: int,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[AccountingPeriod], int]:
    q = db.query(AccountingPeriod).filter(AccountingPeriod.branch_id == branch_id)
    total = q.count()
    items = (
        q.order_by(AccountingPeriod.year.desc(), AccountingPeriod.month.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return items, total


# ── Check ─────────────────────────────────────────────────────────────

def create_check(db: Session, data: dict) -> Check:
    obj = Check(**data)
    db.add(obj)
    db.flush()
    return obj

def list_checks(db: Session, branch_id: int, status: str | None = None) -> list[Check]:
    q = db.query(Check).filter(Check.branch_id == branch_id)
    if status:
        q = q.filter(Check.status == status)
    return q.order_by(Check.due_date).all()

def get_check(db: Session, check_id: int) -> Check | None:
    return db.query(Check).filter(Check.id == check_id).first()

def move_check_status(db: Session, check_obj: Check, to_status: str, moved_by: int, notes: str | None = None) -> Check:
    movement = CheckMovement(
        check_id=check_obj.id,
        from_status=check_obj.status,
        to_status=to_status,
        moved_by=moved_by,
        notes=notes,
    )
    check_obj.status = to_status
    if to_status == "deposited":
        check_obj.deposited_at = local_today(settings.TIMEZONE)
    elif to_status == "cleared":
        check_obj.cleared_at = local_today(settings.TIMEZONE)
    elif to_status == "bounced":
        check_obj.bounced_at = local_today(settings.TIMEZONE)
    db.add(movement)
    db.flush()
    return check_obj


# ── Cost Centers ─────────────────────────────────────────────────────

def list_cost_centers(db: Session, branch_id: int, active_only: bool = True) -> list[CostCenter]:
    q = db.query(CostCenter).filter(CostCenter.branch_id == branch_id)
    if active_only:
        q = q.filter(CostCenter.is_active.is_(True))
    return q.order_by(CostCenter.code).all()


def create_cost_center(db: Session, data: CostCenterCreate) -> CostCenter:
    obj = CostCenter(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def get_cost_center_by_code(db: Session, branch_id: int, code: str) -> Optional[CostCenter]:
    return (
        db.query(CostCenter)
        .filter(CostCenter.branch_id == branch_id, CostCenter.code == code)
        .first()
    )


def sum_journal_lines_by_cost_center(
    db: Session, branch_id: int, date_from: date, date_to: date,
) -> dict[int, dict[str, Decimal]]:
    """إجمالي مدين/دائن لكل (مركز تكلفة × نوع حساب) خلال المدى المطلوب —
    يُستخدم في services.get_cost_center_report عشان يحسب الإيراد
    (دائن-مدين لحسابات revenue) والمصروف (مدين-دائن لحسابات expense) لكل
    مركز تكلفة من journal_lines.cost_center_id مباشرة، بدل استنتاجه من
    جداول عمليات منفصلة (folio_charges/beach_transactions) زي قبل كده.
    بيرجّع {cost_center_id: {"revenue": Decimal, "expense": Decimal}}."""
    from sqlalchemy import func  # noqa: PLC0415

    rows = (
        db.query(
            JournalLine.cost_center_id,
            Account.account_type,
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .join(Account, Account.id == JournalLine.account_id)
        .filter(
            JournalEntry.branch_id == branch_id,
            JournalEntry.entry_date >= date_from,
            JournalEntry.entry_date <= date_to,
            JournalLine.cost_center_id.isnot(None),
            Account.account_type.in_(("revenue", "expense")),
        )
        .group_by(JournalLine.cost_center_id, Account.account_type)
        .all()
    )

    result: dict[int, dict[str, Decimal]] = {}
    for cost_center_id, account_type, debit_sum, credit_sum in rows:
        bucket = result.setdefault(cost_center_id, {"revenue": Decimal("0"), "expense": Decimal("0")})
        if account_type == "revenue":
            bucket["revenue"] += (credit_sum or Decimal("0")) - (debit_sum or Decimal("0"))
        else:  # expense
            bucket["expense"] += (debit_sum or Decimal("0")) - (credit_sum or Decimal("0"))
    return result


def sum_journal_lines_by_account(
    db: Session,
    branch_id: int,
    date_from: Optional[date],
    date_to: date,
) -> dict[int, tuple[Decimal, Decimal]]:
    """إجمالي مدين/دائن لكل حساب من دفتر اليومية خلال المدى المطلوب
    (date_from=None يعني من بداية الحسابات — لاستخدامه في trial balance
    و balance sheet اللي بيحتاجوا الرصيد التراكمي وقت as_of)."""
    from sqlalchemy import func  # noqa: PLC0415

    q = (
        db.query(
            JournalLine.account_id,
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(JournalEntry.branch_id == branch_id, JournalEntry.entry_date <= date_to)
    )
    if date_from:
        q = q.filter(JournalEntry.entry_date >= date_from)
    q = q.group_by(JournalLine.account_id)

    return {
        row[0]: (row[1] or Decimal("0"), row[2] or Decimal("0"))
        for row in q.all()
    }


# ── Exchange Rates (Multi-Currency) ───────────────────────────────────

def create_exchange_rate(db: Session, data: ExchangeRateCreate, created_by: int) -> ExchangeRate:
    obj = ExchangeRate(
        from_currency=data.from_currency,
        to_currency=data.to_currency,
        rate=data.rate,
        effective_date=data.effective_date,
        created_by=created_by,
    )
    db.add(obj)
    db.flush()
    return obj


def get_exchange_rate_exact(
    db: Session, from_currency: str, to_currency: str, effective_date: date,
) -> Optional[ExchangeRate]:
    return (
        db.query(ExchangeRate)
        .filter(
            ExchangeRate.from_currency == from_currency,
            ExchangeRate.to_currency == to_currency,
            ExchangeRate.effective_date == effective_date,
        )
        .first()
    )


def get_latest_exchange_rate(
    db: Session, from_currency: str, to_currency: str, as_of: date,
) -> Optional[ExchangeRate]:
    """أحدث سعر صرف بتاريخ <= as_of لنفس زوج العملة — fallback منطقي بدل
    اعتماد سعر يوم بعينه (لو مفيش سعر مسجل بالظبط في as_of)."""
    return (
        db.query(ExchangeRate)
        .filter(
            ExchangeRate.from_currency == from_currency,
            ExchangeRate.to_currency == to_currency,
            ExchangeRate.effective_date <= as_of,
        )
        .order_by(ExchangeRate.effective_date.desc())
        .first()
    )


def list_exchange_rates(
    db: Session,
    from_currency: Optional[str] = None,
    to_currency: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[ExchangeRate], int]:
    q = db.query(ExchangeRate)
    if from_currency:
        q = q.filter(ExchangeRate.from_currency == from_currency)
    if to_currency:
        q = q.filter(ExchangeRate.to_currency == to_currency)
    total = q.count()
    items = (
        q.order_by(ExchangeRate.effective_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return items, total


# ── Fixed-Asset Depreciation ────────────────────────────────────────────

def get_depreciable_assets(db: Session, branch_id: int):
    """يرجّع كل الأصول (maintenance module) المؤهّلة لدورة إهلاك — عندها
    purchase_cost وuseful_life_years ومش متبّعة (disposed)."""
    from app.modules.maintenance.models import Asset  # noqa: PLC0415
    return (
        db.query(Asset)
        .filter(
            Asset.branch_id == branch_id,
            Asset.purchase_cost.isnot(None),
            Asset.useful_life_years.isnot(None),
            Asset.status != "disposed",
        )
        .order_by(Asset.code)
        .all()
    )


def get_depreciation_entry_for_period(
    db: Session, asset_id: int, year: int, month: int,
) -> Optional[AssetDepreciationEntry]:
    return (
        db.query(AssetDepreciationEntry)
        .filter(
            AssetDepreciationEntry.asset_id == asset_id,
            AssetDepreciationEntry.year == year,
            AssetDepreciationEntry.month == month,
        )
        .first()
    )


def create_depreciation_entry(
    db: Session,
    *,
    asset_id: int,
    branch_id: int,
    year: int,
    month: int,
    amount: Decimal,
    accumulated_after: Decimal,
    posted_by: int,
    journal_entry_id: Optional[int] = None,
) -> AssetDepreciationEntry:
    entry = AssetDepreciationEntry(
        asset_id=asset_id, branch_id=branch_id, year=year, month=month,
        amount=amount, accumulated_after=accumulated_after,
        posted_by=posted_by, journal_entry_id=journal_entry_id,
    )
    db.add(entry)
    db.flush()
    return entry


def list_depreciation_entries(
    db: Session,
    branch_id: int,
    asset_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[AssetDepreciationEntry], int]:
    q = db.query(AssetDepreciationEntry).filter(AssetDepreciationEntry.branch_id == branch_id)
    if asset_id is not None:
        q = q.filter(AssetDepreciationEntry.asset_id == asset_id)
    total = q.count()
    items = (
        q.order_by(AssetDepreciationEntry.year.desc(), AssetDepreciationEntry.month.desc())
        .offset(skip).limit(limit).all()
    )
    return items, total


# ── Bank Reconciliation ──────────────────────────────────────────────

def create_bank_account(db: Session, data: BankAccountCreate) -> BankAccount:
    account = BankAccount(**data.model_dump())
    db.add(account)
    db.flush()
    return account


def get_bank_account(db: Session, bank_account_id: int) -> Optional[BankAccount]:
    return db.query(BankAccount).filter(BankAccount.id == bank_account_id).first()


def list_bank_accounts(
    db: Session, branch_id: int, active_only: bool = True,
) -> list[BankAccount]:
    q = db.query(BankAccount).filter(BankAccount.branch_id == branch_id)
    if active_only:
        q = q.filter(BankAccount.is_active.is_(True))
    return q.order_by(BankAccount.bank_name).all()


def update_bank_account(db: Session, account: BankAccount, data: BankAccountUpdate) -> BankAccount:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    db.flush()
    return account


def create_bank_statement_lines(
    db: Session, bank_account_id: int, branch_id: int, uploaded_by: int,
    lines: list[BankStatementLineCreate],
) -> list[BankStatementLine]:
    objs = [
        BankStatementLine(
            bank_account_id=bank_account_id, branch_id=branch_id, uploaded_by=uploaded_by,
            **line.model_dump(),
        )
        for line in lines
    ]
    db.add_all(objs)
    db.flush()
    return objs


def get_bank_statement_line(db: Session, line_id: int) -> Optional[BankStatementLine]:
    return db.query(BankStatementLine).filter(BankStatementLine.id == line_id).first()


def list_bank_statement_lines(
    db: Session,
    bank_account_id: int,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[BankStatementLine], int]:
    q = db.query(BankStatementLine).filter(BankStatementLine.bank_account_id == bank_account_id)
    if status:
        q = q.filter(BankStatementLine.status == status)
    total = q.count()
    items = q.order_by(BankStatementLine.line_date.desc()).offset(skip).limit(limit).all()
    return items, total


def find_matching_payment_candidates(
    db: Session, branch_id: int, amount: Decimal, target_date, window_days: int = 3,
) -> list[Payment]:
    """دفعات غير مربوطة بأي سطر كشف حساب حتى الآن، بنفس المبلغ (± قرش) وفي
    نطاق تاريخ قريب — أساس المطابقة الأوتوماتيكية."""
    from datetime import timedelta  # noqa: PLC0415
    already_matched = db.query(BankStatementLine.matched_payment_id).filter(
        BankStatementLine.matched_payment_id.isnot(None),
    )
    return (
        db.query(Payment)
        .filter(
            Payment.branch_id == branch_id,
            Payment.voided_at.is_(None),
            Payment.amount == amount,
            Payment.posted_at >= target_date - timedelta(days=window_days),
            Payment.posted_at <= target_date + timedelta(days=window_days),
            Payment.id.notin_(already_matched),
        )
        .all()
    )


def match_statement_line(
    db: Session, line: BankStatementLine, payment_id: int, matched_by: int,
) -> BankStatementLine:
    line.matched_payment_id = payment_id
    line.status = "matched"
    line.matched_at = datetime.utcnow()
    line.matched_by = matched_by
    db.flush()
    return line


def unmatch_statement_line(db: Session, line: BankStatementLine) -> BankStatementLine:
    line.matched_payment_id = None
    line.status = "unmatched"
    line.matched_at = None
    line.matched_by = None
    db.flush()
    return line


def sum_matched_payments(db: Session, bank_account_id: int, as_of) -> Decimal:
    from sqlalchemy import func  # noqa: PLC0415
    total = (
        db.query(func.coalesce(func.sum(Payment.amount), Decimal("0")))
        .join(BankStatementLine, BankStatementLine.matched_payment_id == Payment.id)
        .filter(
            BankStatementLine.bank_account_id == bank_account_id,
            BankStatementLine.line_date <= as_of,
        )
        .scalar()
    )
    return Decimal(total or 0)


def sum_statement_lines(db: Session, bank_account_id: int, as_of, exclude_ignored: bool = True) -> Decimal:
    from sqlalchemy import func  # noqa: PLC0415
    q = db.query(func.coalesce(func.sum(BankStatementLine.amount), Decimal("0"))).filter(
        BankStatementLine.bank_account_id == bank_account_id,
        BankStatementLine.line_date <= as_of,
    )
    if exclude_ignored:
        q = q.filter(BankStatementLine.status != "ignored")
    return Decimal(q.scalar() or 0)


def count_unmatched_statement_lines(db: Session, bank_account_id: int) -> int:
    return (
        db.query(BankStatementLine)
        .filter(BankStatementLine.bank_account_id == bank_account_id, BankStatementLine.status == "unmatched")
        .count()
    )


def unmatched_payments_summary(db: Session, branch_id: int, as_of) -> tuple[int, Decimal]:
    """دفعات حقيقية مسجّلة في النظام لسه ملهاش سطر كشف حساب مطابق — مؤشر
    محتمل على تأخير بنكي أو دفعة لم تصل فعلياً للحساب البنكي بعد."""
    from sqlalchemy import func  # noqa: PLC0415
    already_matched = db.query(BankStatementLine.matched_payment_id).filter(
        BankStatementLine.matched_payment_id.isnot(None),
    )
    q = db.query(Payment).filter(
        Payment.branch_id == branch_id,
        Payment.voided_at.is_(None),
        Payment.posted_at <= as_of,
        Payment.id.notin_(already_matched),
    )
    count = q.count()
    total = db.query(func.coalesce(func.sum(Payment.amount), Decimal("0"))).filter(
        Payment.branch_id == branch_id,
        Payment.voided_at.is_(None),
        Payment.posted_at <= as_of,
        Payment.id.notin_(already_matched),
    ).scalar()
    return count, Decimal(total or 0)
