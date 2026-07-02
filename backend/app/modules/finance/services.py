"""app/modules/finance/services.py — Business logic"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.finance import crud
from app.modules.finance.models import (
    AccountingPeriod, CashierShift, CostCenter, ETAInvoice, ExchangeRate,
    Folio, FolioCharge, JournalEntry, Payment,
)
from app.modules.finance.schemas import (
    BalanceSheetLine, BalanceSheetReport,
    CashCountLineRead, CashierShiftClose, CashierShiftOpen, ConditionalDiscountCreate, CostCenterCreate,
    CostCenterReport, CostCenterReportLine, ExchangeRateCreate, FolioChargeCreate, FolioCreate,
    IncomeStatementLine, IncomeStatementReport,
    JournalEntryCreate, PaymentCreate, ShiftEndReport,
    TrialBalanceLine, TrialBalanceReport,
)
from app.resort_os.discount_engine import (
    DiscountResult, DiscountRule, OrderContext, calculate_discount,
)
from app.resort_os.folio_engine import (
    FolioChargeItem,
    FolioSummary,
    can_checkout,
    validate_charge,
)


# ── Folio ─────────────────────────────────────────────────────────────

def get_folio_or_404(db: Session, folio_id: int) -> Folio:
    folio = crud.get_folio(db, folio_id)
    if not folio:
        raise ValueError(f"الفوليو {folio_id} غير موجود")
    return folio


def _to_folio_summary(folio: Folio) -> FolioSummary:
    return FolioSummary(
        folio_id=folio.id,
        guest_name=folio.guest_name,
        check_in=folio.check_in,
        check_out=folio.check_out,
        is_checked_out=folio.status == "closed",
        charges=[
            FolioChargeItem(
                charge_type=c.charge_type,
                description=c.description,
                amount=c.amount,
                vat_amount=c.vat_amount,
                posted_at=c.posted_at,
                ref_order_id=c.ref_order_id,
                ref_beach_tx_id=c.ref_beach_tx_id,
                is_settled=c.is_settled,
            )
            for c in folio.charges
        ],
    )


def create_folio(db: Session, data: FolioCreate) -> Folio:
    supported = {c.strip().upper() for c in settings.SUPPORTED_CURRENCIES.split(",") if c.strip()}
    if data.currency not in supported:
        raise ValueError(
            f"العملة {data.currency} غير مدعومة — العملات المتاحة: {', '.join(sorted(supported))}"
        )
    folio = crud.create_folio(db, data)
    db.commit()
    db.refresh(folio)
    return folio


def post_charge(db: Session, folio_id: int, data: FolioChargeCreate) -> FolioCharge:
    folio = get_folio_or_404(db, folio_id)
    summary = _to_folio_summary(folio)

    validation = validate_charge(summary, data.charge_type, data.amount)
    if not validation.valid:
        raise ValueError(validation.error)

    charge = crud.add_charge(db, folio_id, data)
    crud.recalculate_folio_total(db, folio)
    db.commit()
    db.refresh(charge)
    return charge


def settle_folio(db: Session, folio_id: int) -> Folio:
    folio = get_folio_or_404(db, folio_id)
    summary = _to_folio_summary(folio)

    validation = can_checkout(summary)
    if not validation.valid:
        raise ValueError(validation.error)

    crud.settle_all_charges(db, folio)
    crud.close_folio(db, folio)
    db.commit()
    db.refresh(folio)
    return folio


def generate_folio_statement_pdf(db: Session, folio_id: int) -> bytes:
    """كشف حساب النزيل (Account Statement) — كل الحركات مدين/دائن + رصيد جاري،
    مطلوب عند تسليم الفاتورة أو استفسار نزيل عن رصيده."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    folio = get_folio_or_404(db, folio_id)

    movements: list[tuple[datetime, str, str, Decimal, Decimal]] = []
    # (date, description, type, debit, credit)
    for c in folio.charges:
        movements.append((c.posted_at, c.description, "charge", c.amount + c.vat_amount, Decimal("0")))
    for p in folio.payments:
        if p.voided_at is not None:
            continue
        movements.append((p.posted_at, f"دفعة — {p.method}", "payment", Decimal("0"), p.amount))
    movements.sort(key=lambda m: m[0])

    headers = ["التاريخ", "البيان", "مدين", "دائن", "الرصيد"]
    rows = []
    balance = Decimal("0")
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for posted_at, desc, _kind, debit, credit in movements:
        balance += debit - credit
        total_debit += debit
        total_credit += credit
        rows.append([
            posted_at.strftime("%Y-%m-%d %H:%M"),
            desc,
            f"{debit:,.2f}" if debit else "—",
            f"{credit:,.2f}" if credit else "—",
            f"{balance:,.2f}",
        ])

    summary = [
        ("إجمالي المدين (المصروفات)", f"{total_debit:,.2f} EGP"),
        ("إجمالي الدائن (المدفوعات)", f"{total_credit:,.2f} EGP"),
        ("الرصيد النهائي",            f"{balance:,.2f} EGP"),
        ("حالة الفاتورة",             folio.status),
    ]

    return builder.table_pdf(
        title="كشف حساب",
        subtitle=f"{folio.guest_name} — فاتورة #{folio.id}",
        headers=headers,
        rows=rows,
        summary=summary,
        footer=f"تسجيل الدخول: {folio.check_in:%Y-%m-%d} — تسجيل الخروج: {folio.check_out:%Y-%m-%d}",
    )


def generate_folios_report_excel(
    db: Session, branch_id: int,
    date_from: Optional[date] = None, date_to: Optional[date] = None,
    status: Optional[str] = None,
) -> bytes:
    """تصدير كل الفواتير (All Invoices) في مدى تاريخي — Excel، للمراجعة والأرشفة."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    folios, _total = crud.list_folios(
        db, branch_id, status=status, date_from=date_from, date_to=date_to,
        skip=0, limit=10_000,
    )

    rows = []
    total_amount = Decimal("0")
    for f in folios:
        paid = sum((p.amount for p in f.payments if p.voided_at is None), Decimal("0"))
        rows.append([
            f.id, f.guest_name,
            f.check_in.strftime("%Y-%m-%d"), f.check_out.strftime("%Y-%m-%d"),
            f.status, float(f.total), float(paid), float(f.total - paid),
        ])
        total_amount += f.total

    return builder.excel(
        sheets=[{
            "name": "الفواتير",
            "headers": ["رقم", "اسم النزيل", "تسجيل الدخول", "تسجيل الخروج",
                        "الحالة", "الإجمالي", "المدفوع", "المتبقي"],
            "rows": rows,
            "col_types": ["text", "text", "text", "text", "text",
                          "currency", "currency", "currency"],
            "summary": {"إجمالي الفواتير": len(rows), "إجمالي القيمة": float(total_amount)},
        }],
        title=f"تقرير كل الفواتير — فرع {branch_id}",
    )


def add_payment(db: Session, folio_id: int, data: PaymentCreate, cashier_id: Optional[int] = None) -> Payment:
    folio = get_folio_or_404(db, folio_id)
    if cashier_id and not data.cashier_id:
        data = data.model_copy(update={"cashier_id": cashier_id})
    shift_id = None
    if data.cashier_id:
        open_shift = crud.get_open_shift(db, data.branch_id, data.cashier_id)
        if open_shift:
            shift_id = open_shift.id
    # عملة الدفعة موروثة من الفوليو دايماً — مش قابلة للتحديد من العميل، عشان
    # نضمن ما يحصلش mismatch بين عملة الفوليو وعملة دفعاته.
    payment = crud.create_payment(db, data, shift_id=shift_id, currency=folio.currency)
    db.commit()
    db.refresh(payment)
    return payment


def void_payment(db: Session, payment_id: int, voided_by: int) -> Payment:
    payment = crud.get_payment(db, payment_id)
    if not payment:
        raise ValueError(f"الدفعة {payment_id} غير موجودة")
    folio = crud.get_folio(db, payment.folio_id)
    if folio and folio.status == "closed":
        raise ValueError("لا يمكن إلغاء دفعة من فوليو مغلق")
    payment = crud.void_payment(db, payment, voided_by)
    db.commit()
    db.refresh(payment)
    return payment


# ── Cashier Shift / Safe (POS Day) ──────────────────────────────────────

def open_shift(db: Session, cashier_id: int, opened_by: int, data: CashierShiftOpen) -> CashierShift:
    existing = crud.get_open_shift(db, data.branch_id, cashier_id)
    if existing:
        raise ValueError(f"يوجد وردية مفتوحة بالفعل (#{existing.id}) لهذا الكاشير — لازم تقفلها الأول")
    shift = crud.create_shift(db, data.branch_id, cashier_id, opened_by, data.opening_float, data.notes)
    db.commit()
    db.refresh(shift)
    return shift


def build_shift_end_report(db: Session, shift_id: int) -> ShiftEndReport:
    shift = crud.get_shift(db, shift_id)
    if not shift:
        raise ValueError(f"الوردية {shift_id} غير موجودة")

    payments = crud.payments_for_shift(db, shift_id)
    active = [p for p in payments if p.voided_at is None]
    voided = [p for p in payments if p.voided_at is not None]

    def _sum(method: str) -> Decimal:
        return sum((p.amount for p in active if p.method == method), Decimal("0"))

    total_cash   = _sum("cash")
    total_card   = _sum("card")
    total_credit = _sum("credit")
    known = {"cash", "card", "credit"}
    total_other  = sum((p.amount for p in active if p.method not in known), Decimal("0"))
    total_sales  = sum((p.amount for p in active), Decimal("0"))
    voided_amount = sum((p.amount for p in voided), Decimal("0"))

    expected_cash = shift.expected_cash if shift.status == "closed" and shift.expected_cash is not None \
        else (shift.opening_float + total_cash)

    prev = crud.get_previous_closed_shift(db, shift.branch_id, shift.cashier_id, shift.id, shift.opened_at)
    previous_total_sales = None
    delta_vs_previous = None
    if prev:
        prev_payments = crud.payments_for_shift(db, prev.id)
        prev_active = [p for p in prev_payments if p.voided_at is None]
        previous_total_sales = sum((p.amount for p in prev_active), Decimal("0"))
        delta_vs_previous = total_sales - previous_total_sales

    return ShiftEndReport(
        shift_id=shift.id,
        branch_id=shift.branch_id,
        cashier_id=shift.cashier_id,
        status=shift.status,
        opened_at=shift.opened_at,
        closed_at=shift.closed_at,
        opening_float=shift.opening_float,
        total_cash=total_cash,
        total_card=total_card,
        total_credit=total_credit,
        total_other=total_other,
        total_sales=total_sales,
        invoice_count=len(active),
        voided_count=len(voided),
        voided_amount=voided_amount,
        expected_cash=expected_cash,
        counted_cash=shift.counted_cash,
        variance=shift.variance,
        cash_count=[
            CashCountLineRead.model_validate(line)
            for line in crud.list_cash_count_lines(db, shift_id)
        ],
        previous_shift_id=prev.id if prev else None,
        previous_total_sales=previous_total_sales,
        delta_vs_previous=delta_vs_previous,
    )


def generate_shift_end_report_pdf(db: Session, shift_id: int) -> bytes:
    """تقرير نهاية الوردية جاهز للطباعة (يقابل rpt_shift_end في الأنظمة التجارية)."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    r = build_shift_end_report(db, shift_id)

    headers = ["طريقة الدفع", "الإجمالي (EGP)"]
    rows = [
        ["نقدي",  f"{r.total_cash:,.2f}"],
        ["كارت",  f"{r.total_card:,.2f}"],
        ["آجل",   f"{r.total_credit:,.2f}"],
        ["أخرى",  f"{r.total_other:,.2f}"],
    ]

    def _fmt_delta(val: Optional[Decimal]) -> str:
        if val is None:
            return "—"
        arrow = "▲" if val >= 0 else "▼"
        return f"{arrow} {abs(val):,.2f}"

    summary = [
        ("رصيد الافتتاح",        f"{r.opening_float:,.2f} EGP"),
        ("إجمالي المبيعات",       f"{r.total_sales:,.2f} EGP"),
        ("عدد الفواتير",          str(r.invoice_count)),
        ("عدد الملغاة",           str(r.voided_count)),
        ("قيمة الملغاة",          f"{r.voided_amount:,.2f} EGP"),
        ("الكاش المتوقع",         f"{r.expected_cash:,.2f} EGP"),
        ("الكاش المعدود",         f"{r.counted_cash:,.2f} EGP" if r.counted_cash is not None else "—"),
        ("الفرق (Variance)",      f"{r.variance:,.2f} EGP" if r.variance is not None else "—"),
        ("مقارنة بالوردية السابقة", _fmt_delta(r.delta_vs_previous)),
    ]

    if r.cash_count:
        summary.append(("— عدّ الكاش بالفئة —", ""))
        for line in r.cash_count:
            summary.append((f"{line.denomination:,.2f} EGP × {line.quantity}", f"{line.subtotal:,.2f} EGP"))

    return builder.table_pdf(
        title="تقرير نهاية الوردية",
        subtitle=f"وردية #{r.shift_id} — كاشير #{r.cashier_id}",
        headers=headers,
        rows=rows,
        summary=summary,
        footer=f"فُتحت: {r.opened_at:%Y-%m-%d %H:%M}" + (f" — أُغلقت: {r.closed_at:%Y-%m-%d %H:%M}" if r.closed_at else ""),
    )


def close_shift(db: Session, shift_id: int, closed_by: int, data: CashierShiftClose) -> CashierShift:
    shift = crud.get_shift(db, shift_id)
    if not shift:
        raise ValueError(f"الوردية {shift_id} غير موجودة")
    if shift.status == "closed":
        raise ValueError("الوردية مقفولة بالفعل")

    # لو الكاشير عدّ الكاش بالفئة (200ج × 5، 100ج × 3...)، الإجمالي المعدود بيتحسب من
    # العدّ الفعلي مش من رقم يكتبه الكاشير بنفسه — ده أساس أي نظام POS جاد لتجنب الغش
    # أو الغلط في الجمع، والتفاصيل بتتحفظ للتدقيق (راجع cashier_shift_cash_counts).
    if data.cash_count:
        counted_cash = sum(
            (line.denomination * line.quantity for line in data.cash_count), Decimal("0")
        )
        crud.create_cash_count_lines(
            db, shift_id,
            [{"denomination": line.denomination, "quantity": line.quantity} for line in data.cash_count],
        )
    else:
        assert data.counted_cash is not None  # مضمون بالـ model_validator في CashierShiftClose
        counted_cash = data.counted_cash

    report = build_shift_end_report(db, shift_id)
    shift.expected_cash = report.expected_cash
    shift.counted_cash = counted_cash
    shift.variance = counted_cash - report.expected_cash
    shift.status = "closed"
    shift.closed_at = datetime.utcnow()
    shift.closed_by = closed_by
    if data.notes:
        shift.notes = f"{shift.notes}\n{data.notes}" if shift.notes else data.notes

    db.commit()
    db.refresh(shift)
    return shift


# ── Discount ──────────────────────────────────────────────────────────

def create_discount(db: Session, data: ConditionalDiscountCreate):
    if data.valid_from > data.valid_until:
        raise ValueError("valid_from يجب أن يكون قبل valid_until")
    obj = crud.create_discount(db, data)
    db.commit()
    db.refresh(obj)
    return obj


def calculate_order_discount(
    db: Session,
    branch_id: int,
    order_total: Decimal,
    item_count: int = 1,
    customer_group: str = "default",
    order_date: Optional[date] = None,
) -> DiscountResult:
    order_date = order_date or date.today()
    rules_orm, _ = crud.list_discounts(db, branch_id, active_only=True, limit=200)
    rules = [
        DiscountRule(
            id=r.id,
            condition_type=r.condition_type,
            condition_value=r.condition_value,
            discount_type=r.discount_type,
            discount_value=r.discount_value,
            max_uses=r.max_uses,
            valid_from=r.valid_from,
            valid_until=r.valid_until,
            priority=r.priority,
            uses_count=r.uses_count,
        )
        for r in rules_orm
    ]
    ctx = OrderContext(
        total_amount=order_total,
        item_count=item_count,
        order_date=order_date,
        customer_group=customer_group,
    )
    return calculate_discount(order_total, rules, ctx)


# ── Double-Entry Accounting ────────────────────────────────────────────

def validate_period_open(db: Session, branch_id: int, entry_date: date) -> None:
    """يرفع ValueError لو الفترة المحاسبية دي مقفولة (closed/locked)."""
    period = crud.get_period_status(db, branch_id, entry_date.year, entry_date.month)
    if period and period.status in ("closed", "locked"):
        raise ValueError(f"الفترة المحاسبية {entry_date.year}-{entry_date.month:02d} مقفولة")


def post_journal_entry(db: Session, data: JournalEntryCreate, user_id: int) -> JournalEntry:
    """ينشئ قيد يومية متوازن (Debit = Credit)."""
    validate_period_open(db, data.branch_id, data.entry_date)
    total_debit = sum((l.debit for l in data.lines), Decimal("0"))
    total_credit = sum((l.credit for l in data.lines), Decimal("0"))
    if abs(total_debit - total_credit) > Decimal("0.01"):
        raise ValueError(f"القيد غير متوازن: مدين={total_debit}, دائن={total_credit}")
    entry = crud.create_journal_entry(db, data, user_id)
    db.commit()
    db.refresh(entry)
    return entry


def close_accounting_period(
    db: Session,
    branch_id: int,
    year: int,
    month: int,
    closed_by: int,
) -> AccountingPeriod:
    period = crud.close_period(db, branch_id, year, month, closed_by)
    db.commit()
    db.refresh(period)
    return period


# ── ETA E-Invoice ────────────────────────────────────────────────────

async def submit_eta_invoice(db: Session, settings, data) -> ETAInvoice:
    """يبني مستند ETA ويرسله، ويسجّل النتيجة دايماً (نجاح أو فشل) في
    eta_invoices للتدقيق وإعادة المحاولة لاحقاً."""
    from app.modules.finance.eta_service import ETAConfigError, ETAService, ETASubmissionError

    if not settings.ETA_ENABLED:
        raise ValueError("ETA e-invoicing غير مفعّل — ETA_ENABLED=false في .env")

    today = date.today()
    count = db.query(ETAInvoice).filter(
        ETAInvoice.branch_id == data.branch_id,
        ETAInvoice.internal_id.like(f"ETA-{today:%Y%m%d}-%"),
    ).count()
    internal_id = f"ETA-{today:%Y%m%d}-{count + 1:04d}"

    try:
        eta = ETAService(settings)
        document = eta.build_invoice_document(
            internal_id=internal_id,
            issued_at_iso=datetime.utcnow().isoformat() + "Z",
            receiver_name=data.receiver_name,
            receiver_rin=data.receiver_rin,
            line_items=[item.model_dump() for item in data.line_items],
        )
    except ETAConfigError as exc:
        raise ValueError(str(exc))

    import json as _json
    invoice = crud.create_eta_invoice(
        db, data.branch_id, data.folio_id, internal_id, _json.dumps(document, ensure_ascii=False),
    )

    try:
        result = await eta.submit_invoice(document)
        accepted = result.get("acceptedDocuments") or []
        rejected = result.get("rejectedDocuments") or []
        if accepted:
            crud.mark_eta_invoice_submitted(
                db, invoice, status="submitted",
                submission_uuid=accepted[0].get("uuid"),
                long_id=accepted[0].get("longId"),
                response_json=_json.dumps(result, ensure_ascii=False),
            )
        else:
            crud.mark_eta_invoice_submitted(
                db, invoice, status="invalid",
                response_json=_json.dumps(result, ensure_ascii=False),
                error_message=str(rejected[:1] or result),
            )
    except ETASubmissionError as exc:
        crud.mark_eta_invoice_submitted(db, invoice, status="failed", error_message=str(exc))

    db.refresh(invoice)
    return invoice


# ── Exchange Rates (Multi-Currency) ───────────────────────────────────
# ⚠️ ensure_default_exchange_rates() بيزرع أسعار dummy للتطوير/العرض بس (مش
# حية/رسمية) — أي استخدام إنتاجي حقيقي محتاج ربط بمصدر رسمي (البنك المركزي
# المصري مثلاً) واستبدال هذه الدالة أو تعطيلها.

_DEFAULT_SEED_RATES: list[tuple[str, str, Decimal]] = [
    ("USD", "EGP", Decimal("48.00")),
    ("EUR", "EGP", Decimal("52.00")),
]


def ensure_default_exchange_rates(db: Session, created_by: int = 0) -> list[ExchangeRate]:
    """يزرع سعر صرف افتراضي (dummy/dev) لـ USD وEUR مقابل EGP أول مرة بس —
    idempotent زي ensure_default_cost_centers: لو أي زوج عملة عنده سعر
    مسجّل بالفعل (أي تاريخ) منزرعش فوقه. لا تُستخدم كمصدر حقيقي في إنتاج."""
    created: list[ExchangeRate] = []
    for from_cur, to_cur, rate in _DEFAULT_SEED_RATES:
        _, existing_count = crud.list_exchange_rates(db, from_cur, to_cur, limit=1)
        if existing_count == 0:
            obj = crud.create_exchange_rate(
                db,
                ExchangeRateCreate(
                    from_currency=from_cur, to_currency=to_cur,
                    rate=rate, effective_date=date.today(),
                ),
                created_by=created_by,
            )
            created.append(obj)
    if created:
        db.commit()
    return created


def get_rate(db: Session, from_currency: str, to_currency: str, as_of: date) -> Decimal:
    """سعر الصرف من from_currency لـ to_currency بتاريخ as_of — بيرجّع أحدث
    سعر مسجّل في as_of أو قبله (fallback منطقي، مش أحدث سعر مطلق). لو مفيش
    سعر مباشر بيجرّب المعكوس (to→from) ويقلبه. لو مفيش أي سعر خالص بيرمي
    ValueError واضح — من غير ما يفترض 1.0 بصمت (ده كان ممكن يطلع رقم غلط
    تماماً في تقرير مالي حقيقي)."""
    if from_currency == to_currency:
        return Decimal("1")

    ensure_default_exchange_rates(db)

    direct = crud.get_latest_exchange_rate(db, from_currency, to_currency, as_of)
    if direct:
        return direct.rate

    inverse = crud.get_latest_exchange_rate(db, to_currency, from_currency, as_of)
    if inverse and inverse.rate != 0:
        return Decimal("1") / inverse.rate

    raise ValueError(
        f"لا يوجد سعر صرف مسجّل من {from_currency} إلى {to_currency} "
        f"بتاريخ {as_of} أو قبله — أضف سعر صرف عبر POST /finance/exchange-rates"
    )


def convert_to_egp(db: Session, amount: Decimal, currency: str, as_of: date) -> Decimal:
    """اختصار شائع: تحويل مبلغ لـ EGP equivalent بسعر الصرف في تاريخ as_of."""
    if currency == "EGP":
        return amount
    rate = get_rate(db, currency, "EGP", as_of)
    return (amount * rate).quantize(Decimal("0.01"))


def create_exchange_rate(db: Session, data: ExchangeRateCreate, created_by: int) -> ExchangeRate:
    if data.from_currency == data.to_currency:
        raise ValueError("from_currency و to_currency لازم يكونوا مختلفين")
    existing = crud.get_exchange_rate_exact(db, data.from_currency, data.to_currency, data.effective_date)
    if existing:
        raise ValueError(
            f"يوجد سعر صرف مسجّل بالفعل من {data.from_currency} إلى {data.to_currency} "
            f"بتاريخ {data.effective_date} — عدّل السعر عن طريق تسجيل سعر جديد بتاريخ مختلف"
        )
    obj = crud.create_exchange_rate(db, data, created_by)
    db.commit()
    db.refresh(obj)
    return obj


def list_exchange_rates(
    db: Session,
    from_currency: Optional[str] = None,
    to_currency: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
):
    return crud.list_exchange_rates(db, from_currency, to_currency, skip, limit)


# ── Cost Centers ─────────────────────────────────────────────────────

DEFAULT_COST_CENTERS = [
    {"code": "ROOM",  "name": "الفندق / الغرف"},
    {"code": "REST",  "name": "المطعم"},
    {"code": "CAFE",  "name": "الكافيه"},
    {"code": "BEACH", "name": "الشاطئ"},
    {"code": "TS",    "name": "التايم شير"},
]


def ensure_default_cost_centers(db: Session, branch_id: int) -> list[CostCenter]:
    """يزرع مراكز التكلفة الافتراضية أول مرة بس — idempotent زي seed.py."""
    existing_codes = {c.code for c in crud.list_cost_centers(db, branch_id, active_only=False)}
    created_any = False
    for defn in DEFAULT_COST_CENTERS:
        if defn["code"] not in existing_codes:
            crud.create_cost_center(db, CostCenterCreate(branch_id=branch_id, **defn))
            created_any = True
    if created_any:
        db.commit()
    return crud.list_cost_centers(db, branch_id, active_only=False)


def _sum_folio_charges_in_egp(
    db: Session, branch_id: int, charge_type: str, date_from: date, date_to: date,
) -> Decimal:
    """زي crud.sum_folio_charges_by_type بس بيحوّل كل حركة لـ EGP equivalent
    بسعر الصرف في تاريخها قبل الجمع — لازم عشان فوليوهات مختلطة العملة
    (بعد إضافة Folio.currency) ما تدّيش مجموع غلط لو جُمعت كأرقام خام."""
    rows = crud.list_folio_charges_by_type_with_currency(db, branch_id, charge_type, date_from, date_to)
    return sum((convert_to_egp(db, amount, currency, posted_date) for amount, currency, posted_date in rows),
               Decimal("0"))


def get_cost_center_report(db: Session, branch_id: int, date_from: date, date_to: date) -> CostCenterReport:
    """تقرير الإيراد حسب مركز التكلفة — المطعم/الكافيه/الشاطئ كل واحد سطر
    منفصل. البيانات بتيجي من مصدرين حسب الموديول: دفتر اليومية للي بيرحّل فعلياً
    (الفندق عبر حساب 4100)، أو الجداول المباشرة للي لسه ميرحّلش (مطعم/كافيه/شاطئ).
    كل مبلغ من folio_charges بيتحوّل لـ EGP equivalent بسعر الصرف وقت الحركة
    نفسها لو الفوليو مش EGP — التقرير كله EGP-only (reporting_currency)."""
    centers = {c.code: c for c in ensure_default_cost_centers(db, branch_id)}

    room_rev  = crud.sum_revenue_account_by_code(db, branch_id, "4100", date_from, date_to)
    rest_rev  = _sum_folio_charges_in_egp(db, branch_id, "restaurant", date_from, date_to)
    cafe_rev  = _sum_folio_charges_in_egp(db, branch_id, "cafe", date_from, date_to)
    beach_rev = crud.sum_beach_revenue(db, branch_id, date_from, date_to)
    ts_rev    = crud.sum_timeshare_revenue(db, branch_id, date_from, date_to)

    lines = [
        CostCenterReportLine(code="ROOM",  name=centers["ROOM"].name,  revenue=room_rev,  source="ledger"),
        CostCenterReportLine(code="REST",  name=centers["REST"].name,  revenue=rest_rev,  source="direct"),
        CostCenterReportLine(code="CAFE",  name=centers["CAFE"].name,  revenue=cafe_rev,  source="direct"),
        CostCenterReportLine(code="BEACH", name=centers["BEACH"].name, revenue=beach_rev, source="direct"),
        CostCenterReportLine(code="TS",    name=centers["TS"].name,    revenue=ts_rev,    source="direct"),
    ]
    total = sum((l.revenue for l in lines), Decimal("0"))

    return CostCenterReport(
        branch_id=branch_id, date_from=date_from, date_to=date_to,
        lines=lines, total_revenue=total,
    )


# ── Financial Reports ────────────────────────────────────────────────
# ملاحظة محاسبية: بما إن post_journal_entry() بيرفض أي قيد غير متزن (debit
# != credit)، فإجمالي المدين = إجمالي الدائن على مستوى دفتر اليومية كله
# بالضرورة — وده اللي بيخلي trial balance وbalance sheet بيوازنوا تلقائياً
# من غير ما نحتاج قيد "إقفال" فعلي لنقل الأرباح لحساب حقوق ملكية.

def get_trial_balance(db: Session, branch_id: int, as_of: date) -> TrialBalanceReport:
    """ميزان المراجعة — كل حساب له نشاط حتى تاريخ as_of، برصيده الختامي في
    عمود المدين أو الدائن حسب طبيعته. إجمالي المدين لازم يساوي إجمالي الدائن."""
    accounts, _ = crud.list_accounts(db, branch_id, active_only=False, limit=1000)
    sums = crud.sum_journal_lines_by_account(db, branch_id, None, as_of)

    lines: list[TrialBalanceLine] = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for acc in accounts:
        debit_sum, credit_sum = sums.get(acc.id, (Decimal("0"), Decimal("0")))
        if debit_sum == 0 and credit_sum == 0:
            continue
        net = debit_sum - credit_sum
        if net >= 0:
            debit_display, credit_display = net, Decimal("0")
        else:
            debit_display, credit_display = Decimal("0"), -net
        total_debit += debit_display
        total_credit += credit_display
        lines.append(TrialBalanceLine(
            account_code=acc.code, account_name=acc.name, account_type=acc.account_type,
            debit=debit_display, credit=credit_display,
        ))

    return TrialBalanceReport(
        branch_id=branch_id, as_of=as_of, lines=lines,
        total_debit=total_debit, total_credit=total_credit,
        is_balanced=abs(total_debit - total_credit) <= Decimal("0.01"),
    )


def get_income_statement(
    db: Session, branch_id: int, date_from: date, date_to: date,
) -> IncomeStatementReport:
    """قائمة الدخل — الإيرادات (حسابات revenue) ناقص المصروفات (حسابات
    expense) خلال المدى المطلوب، وصافي الربح/الخسارة."""
    accounts, _ = crud.list_accounts(db, branch_id, active_only=False, limit=1000)
    sums = crud.sum_journal_lines_by_account(db, branch_id, date_from, date_to)

    revenue_lines: list[IncomeStatementLine] = []
    expense_lines: list[IncomeStatementLine] = []
    total_revenue = Decimal("0")
    total_expense = Decimal("0")
    for acc in accounts:
        debit_sum, credit_sum = sums.get(acc.id, (Decimal("0"), Decimal("0")))
        if debit_sum == 0 and credit_sum == 0:
            continue
        if acc.account_type == "revenue":
            amount = credit_sum - debit_sum
            total_revenue += amount
            revenue_lines.append(IncomeStatementLine(account_code=acc.code, account_name=acc.name, amount=amount))
        elif acc.account_type == "expense":
            amount = debit_sum - credit_sum
            total_expense += amount
            expense_lines.append(IncomeStatementLine(account_code=acc.code, account_name=acc.name, amount=amount))

    return IncomeStatementReport(
        branch_id=branch_id, date_from=date_from, date_to=date_to,
        revenue_lines=revenue_lines, expense_lines=expense_lines,
        total_revenue=total_revenue, total_expense=total_expense,
        net_income=total_revenue - total_expense,
    )


def get_balance_sheet(db: Session, branch_id: int, as_of: date) -> BalanceSheetReport:
    """الميزانية العمومية — الأصول = الخصوم + حقوق الملكية + الأرباح
    المحتجزة (صافي الإيرادات-المصروفات التراكمي حتى as_of، لعدم وجود قيد
    إقفال فعلي في هذا المشروع)."""
    accounts, _ = crud.list_accounts(db, branch_id, active_only=False, limit=1000)
    sums = crud.sum_journal_lines_by_account(db, branch_id, None, as_of)

    asset_lines: list[BalanceSheetLine] = []
    liability_lines: list[BalanceSheetLine] = []
    equity_lines: list[BalanceSheetLine] = []
    total_assets = Decimal("0")
    total_liabilities = Decimal("0")
    total_equity = Decimal("0")
    total_revenue = Decimal("0")
    total_expense = Decimal("0")

    for acc in accounts:
        debit_sum, credit_sum = sums.get(acc.id, (Decimal("0"), Decimal("0")))
        if debit_sum == 0 and credit_sum == 0:
            continue
        if acc.account_type == "asset":
            amount = debit_sum - credit_sum
            total_assets += amount
            asset_lines.append(BalanceSheetLine(account_code=acc.code, account_name=acc.name, amount=amount))
        elif acc.account_type == "liability":
            amount = credit_sum - debit_sum
            total_liabilities += amount
            liability_lines.append(BalanceSheetLine(account_code=acc.code, account_name=acc.name, amount=amount))
        elif acc.account_type == "equity":
            amount = credit_sum - debit_sum
            total_equity += amount
            equity_lines.append(BalanceSheetLine(account_code=acc.code, account_name=acc.name, amount=amount))
        elif acc.account_type == "revenue":
            total_revenue += credit_sum - debit_sum
        elif acc.account_type == "expense":
            total_expense += debit_sum - credit_sum

    retained_earnings = total_revenue - total_expense
    total_liabilities_and_equity = total_liabilities + total_equity + retained_earnings

    return BalanceSheetReport(
        branch_id=branch_id, as_of=as_of,
        asset_lines=asset_lines, liability_lines=liability_lines, equity_lines=equity_lines,
        retained_earnings=retained_earnings,
        total_assets=total_assets, total_liabilities=total_liabilities, total_equity=total_equity,
        total_liabilities_and_equity=total_liabilities_and_equity,
        is_balanced=abs(total_assets - total_liabilities_and_equity) <= Decimal("0.01"),
    )
