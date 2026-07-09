"""app/modules/finance/services.py — Business logic"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.finance import crud
from app.modules.finance.models import (
    AccountingPeriod, BankAccount, BankStatementLine, CashierShift, Check, CostCenter, ETAInvoice,
    ExchangeRate, Folio, FolioCharge, JournalEntry, Payment,
)
from app.modules.finance.schemas import (
    AssetDepreciationEntryRead,
    BalanceSheetLine, BalanceSheetReport,
    BankAccountCreate, BankAccountUpdate, BankReconciliationSummary, BankStatementImportRequest,
    CashCountLineRead, CashierShiftClose, CashierShiftOpen, CheckCreate, ConditionalDiscountCreate,
    ForeignCurrencySummary,
    CostCenterCreate,
    CostCenterReport, CostCenterReportLine, DepreciationRunResult, ExchangeRateCreate, FolioChargeCreate,
    FolioCreate,
    IncomeStatementLine, IncomeStatementReport,
    JournalEntryCreate, JournalLineCreate, PaymentCreate, ShiftEndReport,
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
from app.resort_os.timezone_utils import local_today

if TYPE_CHECKING:
    from app.modules.finance.models import ConditionalDiscount


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
                service_charge=c.service_charge or Decimal("0"),
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
        charge_total = c.amount + c.vat_amount + (c.service_charge or Decimal("0"))
        movements.append((c.posted_at, c.description, "charge", charge_total, Decimal("0")))
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
    post_simple_revenue_journal(
        db, data.branch_id, data.posted_at.date(),
        debit_account_code="1100", credit_account_code="1150",
        amount=data.amount,
        reference=f"PAY-{payment.id}",
        description=f"تحصيل دفعة فوليو #{folio_id}",
        source="folio_payment", source_id=payment.id,
        currency=folio.currency,
    )
    db.commit()
    db.refresh(payment)
    return payment


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
    folio = crud.get_folio(db, payment.folio_id)
    if folio and folio.status == "closed":
        raise ValueError("لا يمكن إلغاء دفعة من فوليو مغلق")
    original_amount = payment.amount
    payment = crud.void_payment(db, payment, voided_by)
    # سجل تدقيق إلزامي — أي تغيير فعلي في قيمة دفعة/فاتورة/حجز لازم يترك أثر
    crud.create_revenue_audit_log(
        db, branch_id=payment.branch_id, entity_type="payment", entity_id=payment.id,
        old_value=original_amount, new_value=Decimal("0.00"), reason=reason, changed_by=voided_by,
    )
    # عكس قيد التحصيل اللي add_payment رحّله (Dr Cash/Cr ذمم الفوليو) — الدفعة
    # اتلغت يبقى الكاش ده ما اتحصّلش فعليًا، والذمة ترجع زي ما كانت.
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415
    post_simple_revenue_journal(
        db, payment.branch_id, business_today(settings.TIMEZONE),
        debit_account_code="1150", credit_account_code="1100",
        amount=original_amount,
        reference=f"PAY-VOID-{payment.id}",
        description=f"إلغاء دفعة فوليو #{payment.folio_id}",
        source="folio_payment_void", source_id=payment.id,
        currency=payment.currency,
    )
    db.commit()
    db.refresh(payment)
    return payment


# ── Checks ────────────────────────────────────────────────────────────
# ⚠️ باج معماري حقيقي كان هنا: الـ router كان بينادي crud.create_check/
# move_check_status مباشرة (بما فيه db.commit() جوه crud نفسها) من غير أي
# services.py function خالص — كسر Architecture rule (§4/§7: router لا يكلّم
# crud مباشرة، والـ commit بتاع الـ business transaction مسؤولية services
# مش crud). اتصلح بنفس نمط void_payment فوق بالظبط: crud بقت DB عمليات خالص
# (flush بس، من غير commit)، والـ commit/refresh + "الشيك غير موجود"
# (ValueError → 404 في الـ router) بقوا هنا.

def create_check(db: Session, data: CheckCreate, created_by: int) -> Check:
    """يسجّل شيك بنكي جديد (وارد من عميل/مورد)."""
    payload = data.model_dump()
    payload["created_by"] = created_by
    check = crud.create_check(db, payload)
    db.commit()
    db.refresh(check)
    return check


class CheckStatusTransitionError(Exception):
    """انتقال حالة شيك غير منطقي (مثلاً تصفية شيك مرتجع مباشرة، أو التراجع عن
    شيك مُحصَّل). لا ترث من ValueError عمدًا عشان الـ router يقدر يميّزها عن
    "الشيك غير موجود" ويرجّع 400 (طلب خاطئ) مش 404."""


# خريطة الانتقالات المسموحة فعليًا لدورة حياة شيك بنكي حقيقي — كانت مفقودة
# بالكامل قبل كده (باج حقيقي اتكشف أثناء اختبار قبول حقيقي): move_check_status
# كانت بتقبل أي to_status من الأربعة المسموحين في الـ schema بغض النظر عن
# الحالة الحالية، يعني مدير (حتى بحسن نية تحت ضغط) كان يقدر يرجّع شيك
# "cleared" لـ "received"، أو يصفّي (cleared) شيك "bounced" مباشرة من غير ما
# يعدي بمرحلة إعادة إيداع حقيقية — كله كان بينفّذ من غير أي رفض.
CHECK_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "received":  {"deposited", "bounced"},
    "deposited": {"cleared", "bounced"},
    "cleared":   set(),  # حالة نهائية — شيك اتحصّل فعليًا، ملوش رجوع
    "bounced":   set(),  # حالة نهائية — شيك ارتد؛ أي متابعة (إعادة إيداع) شيك/سجل جديد
}


def move_check_status(
    db: Session, check_id: int, to_status: str, moved_by: int, notes: Optional[str] = None,
) -> Check:
    """ينقل حالة شيك (received → deposited → cleared/bounced) ويسجّل الحركة
    في CheckMovement. يرفض أي انتقال مش موجود في CHECK_STATUS_TRANSITIONS —
    راجع الملاحظة فوق."""
    check_obj = crud.get_check(db, check_id)
    if not check_obj:
        raise ValueError(f"الشيك {check_id} غير موجود")

    allowed = CHECK_STATUS_TRANSITIONS.get(check_obj.status, set())
    if to_status not in allowed:
        if check_obj.status == to_status:
            reason = "الشيك بالفعل في هذه الحالة"
        elif not allowed:
            reason = f"'{check_obj.status}' حالة نهائية — لا يمكن تغييرها"
        else:
            reason = f"المسموح فقط: {', '.join(sorted(allowed))}"
        raise CheckStatusTransitionError(
            f"لا يمكن نقل الشيك من '{check_obj.status}' إلى '{to_status}' — {reason}"
        )

    updated = crud.move_check_status(db, check_obj, to_status, moved_by, notes)
    db.commit()
    db.refresh(updated)
    return updated


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

    cash_count_lines = crud.list_cash_count_lines(db, shift_id)

    # ملخص العملات الأجنبية — نجمّع لكل عملة غير EGP
    foreign: dict[str, dict] = {}
    counted_cash_egp = Decimal("0")
    for line in cash_count_lines:
        cur = line.currency or "EGP"
        counted_cash_egp += line.egp_equivalent
        if cur != "EGP":
            if cur not in foreign:
                foreign[cur] = {
                    "currency": cur,
                    "total_foreign": Decimal("0"),
                    "fx_rate": line.fx_rate,
                    "egp_equivalent": Decimal("0"),
                }
            foreign[cur]["total_foreign"]  += line.subtotal
            foreign[cur]["egp_equivalent"] += line.egp_equivalent

    foreign_summary = [ForeignCurrencySummary(**v) for v in foreign.values()]

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
        cash_count=[CashCountLineRead.model_validate(line) for line in cash_count_lines],
        foreign_currency_summary=foreign_summary,
        counted_cash_egp=counted_cash_egp if cash_count_lines else shift.counted_cash,
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
            cur = line.currency or "EGP"
            if cur == "EGP":
                label = f"{line.denomination:,.2f} ج × {line.quantity}"
                value = f"{line.subtotal:,.2f} EGP"
            else:
                label = f"{line.denomination:,.2f} {cur} × {line.quantity}"
                value = f"{line.subtotal:,.2f} {cur}  (= {line.egp_equivalent:,.2f} ج @ {line.fx_rate:,.4f})"
            summary.append((label, value))

    if r.foreign_currency_summary:
        summary.append(("— عملات أجنبية (إجمالي) —", ""))
        for fc in r.foreign_currency_summary:
            summary.append((
                f"إجمالي {fc.currency}",
                f"{fc.total_foreign:,.2f} {fc.currency}  = {fc.egp_equivalent:,.2f} ج",
            ))
        if r.counted_cash_egp is not None:
            summary.append(("إجمالي الخزينة (EGP)", f"{r.counted_cash_egp:,.2f} EGP"))

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

    # لو الكاشير عدّ الكاش بالفئة، الإجمالي المعدود بيتحسب من العدّ الفعلي مش من رقم
    # يكتبه الكاشير بنفسه — ده أساس أي نظام POS جاد لتجنب الغش أو الغلط في الجمع.
    # بيدعم عملات متعددة: كل سطر بيتحوّل لـ EGP باستخدام أسعار الصرف المسجّلة.
    if data.cash_count:
        from app.resort_os.timezone_utils import local_today  # noqa: PLC0415
        today = local_today(settings.TIMEZONE)

        lines_for_db = []
        for line in data.cash_count:
            currency = (line.currency or "EGP").upper()
            if currency == "EGP":
                fx_rate = Decimal("1")
            else:
                rate_row = crud.get_latest_exchange_rate(db, currency, "EGP", today)
                if rate_row is None:
                    raise ValueError(
                        f"لا يوجد سعر صرف مسجّل لـ {currency}/EGP — "                        f"أضفه من إعدادات أسعار الصرف أولاً"
                    )
                fx_rate = rate_row.rate
            lines_for_db.append({
                "denomination": line.denomination,
                "currency":     currency,
                "quantity":     line.quantity,
                "fx_rate":      fx_rate,
            })

        crud.create_cash_count_lines(db, shift_id, lines_for_db)
        # counted_cash (EGP) = مجموع egp_equivalent لكل السطور
        counted_cash = sum(
            (
                (ln["denomination"] * ln["quantity"] * ln["fx_rate"]).quantize(Decimal("0.01"))
                for ln in lines_for_db
            ),
            Decimal("0"),
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
    if data.handover_note:
        shift.handover_note = data.handover_note

    db.commit()
    db.refresh(shift)
    return shift


def get_latest_handover_note(db: Session, branch_id: int) -> Optional[str]:
    """آخر ملاحظة تسليم من آخر وردية مقفولة في الفرع ده — بيشوفها اللي هيفتح
    الوردية الجاية قبل ما يبدأ، عشان يعرف أي حاجة معلّقة من الوردية اللي قبله."""
    shift = crud.get_latest_closed_shift(db, branch_id)
    return shift.handover_note if shift else None


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
    order_time: Optional[time] = None,
) -> DiscountResult:
    # اليوم المحلي بتوقيت المنتجع (Africa/Cairo) لو المستخدم مبعتش تاريخ صريح —
    # مش date.today() (توقيت السيرفر، راجع §13 CLAUDE.md لفئة الباج دي).
    order_date = order_date or local_today(settings.TIMEZONE)
    rules_orm, _ = crud.list_discounts(db, branch_id, active_only=True, limit=200)
    rules = [discount_rule_from_orm(r) for r in rules_orm]
    ctx = OrderContext(
        total_amount=order_total,
        item_count=item_count,
        order_date=order_date,
        order_time=order_time or time(0, 0),
        customer_group=customer_group,
    )
    return calculate_discount(order_total, rules, ctx)


def discount_rule_from_orm(r: "ConditionalDiscount") -> DiscountRule:
    """يحوّل صف ConditionalDiscount (ORM) لـ DiscountRule (plain dataclass) —
    نفس التحويل مُكرر سابقًا في finance/restaurant/cafe services، مُوحَّد هنا
    كمصدر وحيد للحقيقة (عشان أي حقل جديد يُضاف مرة واحدة بس)."""
    return DiscountRule(
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
        scope_type=r.scope_type,
        scope_outlet=r.scope_outlet,
        scope_id=r.scope_id,
    )


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


def post_simple_revenue_journal(
    db: Session,
    branch_id: int,
    entry_date: date,
    debit_account_code: str,
    credit_account_code: str,
    amount: Decimal,
    reference: str,
    description: str,
    source: str,
    source_id: Optional[int],
    created_by: int = 0,
    currency: str = "EGP",
) -> Optional[JournalEntry]:
    """يرحّل قيد بسيط بسطرين (Dr. حساب / Cr. حساب) — النمط المتكرر اللي كان
    منسوخ في 6 موديولات (مطعم/كافيه/شاطئ/PMS/تايم شير/إيجارات) كل واحد بنسخته
    الخاصة. بيبتلع أي خطأ عمدًا (حساب مش معرّف للفرع، مبلغ صفري...) وبيرجّع
    None بدل ما يرفع — عشان فشل الترحيل المحاسبي ميمنعش إتمام العملية
    التشغيلية الحقيقية (بيع/حجز/عقد) اللي استدعته. لاحظ إنه بينادي
    crud.create_journal_entry مباشرة مش post_journal_entry — يعني من غير
    التحقق من قفل الفترة المحاسبية، بنفس السلوك القديم قبل التوحيد.

    لو currency مش EGP: amount هي القيمة بالعملة الأصلية، وبتتحوّل هنا لـ EGP
    بسعر الصرف وقت entry_date (نفس آلية convert_to_egp المستخدمة للفواتير) —
    السطور (debit/credit) دايمًا EGP-equivalent عشان التقارير المجمّعة تفضل
    صح، وbعملة/سعر الصرف الأصليين بيتسجّلوا على القيد نفسه للمراجعة."""
    try:
        if amount <= 0:
            return None
        debit_acc = crud.get_account_by_code(db, branch_id, debit_account_code)
        credit_acc = crud.get_account_by_code(db, branch_id, credit_account_code)
        if not debit_acc or not credit_acc:
            return None

        currency = (currency or "EGP").upper()
        if currency == "EGP":
            egp_amount, fx_rate = amount, Decimal("1")
        else:
            egp_amount = convert_to_egp(db, amount, currency, entry_date)
            if egp_amount <= 0:
                return None
            fx_rate = (egp_amount / amount).quantize(Decimal("0.000001"))

        entry_data = JournalEntryCreate(
            branch_id=branch_id,
            entry_date=entry_date,
            reference=reference,
            description=description,
            source=source,
            source_id=source_id,
            currency=currency,
            fx_rate=fx_rate,
            lines=[
                JournalLineCreate(account_id=debit_acc.id, debit=egp_amount, credit=Decimal("0")),
                JournalLineCreate(account_id=credit_acc.id, debit=Decimal("0"), credit=egp_amount),
            ],
        )
        return crud.create_journal_entry(db, entry_data, created_by)
    except Exception:
        return None


def close_accounting_period(
    db: Session,
    branch_id: int,
    year: int,
    month: int,
    closed_by: int,
) -> AccountingPeriod:
    """يقفل فترة محاسبية — إجراء تدقيقي (audited) لازم يحصل مرة واحدة بس، زي
    قفل الوردية بالظبط. لو الفترة مقفولة بالفعل بنرفض (بدل ما نسمح لأي حد
    يعيد قفلها ويغيّر closed_by/closed_at بصمت فوق سجل التدقيق الأصلي)."""
    existing = crud.get_period_status(db, branch_id, year, month)
    if existing and existing.status in ("closed", "locked"):
        raise ValueError(f"الفترة المحاسبية {year}-{month:02d} مقفولة بالفعل")

    period = crud.close_period(db, branch_id, year, month, closed_by)

    from app.modules.core.crud import create_audit_log  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415
    create_audit_log(db, AuditLogCreate(
        user_id=closed_by, branch_id=branch_id, action="close_period",
        entity_type="accounting_period", entity_id=period.id,
        new_data=f'{{"year": {year}, "month": {month}, "status": "{period.status}"}}',
    ))

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

    # ⚠️ internal_id فريد globally على مستوى الداتابيز كلها (ETAInvoice.internal_id
    # unique=True بدون branch_id) — لأن ETA_TAXPAYER_RIN/ETA_TAXPAYER_NAME إعداد
    # واحد للمنتجع كله (كيان ضريبي واحد)، مش لكل فرع. العدّاد هنا لازم يبقى
    # عالمي (كل الفروع) مش مقصور على data.branch_id، وإلا فرعين مختلفين
    # بيبعتوا أول فاتورة ETA في نفس اليوم كانوا هيتصادموا على نفس internal_id
    # ويطيحوا بـ IntegrityError (باج حقيقي اتكشف بالتستات — راجع تاريخ الالتزام).
    today = date.today()
    count = db.query(ETAInvoice).filter(
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
    """يجمع مصاريف الفوليو حسب النوع بس بيحوّل كل حركة لـ EGP equivalent
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


# ── Fixed-Asset Depreciation (straight-line MVP) ────────────────────────
# نطاق مقصود: خطي (straight-line) بس — أكتر طريقة إهلاك استخدامًا وأبسطها
# للمراجعة، وكافية لأصول منتجع حقيقي (تكييف/معدات مطبخ/أثاث/عربيات). أي
# طريقة تانية (متناقصة/وحدات إنتاج) ممكن تتضاف لاحقًا لو ظهرت حاجة تشغيلية.

DEPRECIATION_EXPENSE_ACCOUNT_CODE = "5500"
ACCUMULATED_DEPRECIATION_ACCOUNT_CODE = "1590"


def _get_or_create_account(db: Session, branch_id: int, code: str, name: str, account_type: str):
    """حسابات الإهلاك (مصروف/مجمّع) داخلية للنظام — بتتنشئ تلقائيًا أول مرة
    تُستخدم بدل ما تفشل الدورة كلها لمجرد إن حد نسي يضيفها لدليل الحسابات."""
    from app.modules.finance.models import Account  # noqa: PLC0415
    account = crud.get_account_by_code(db, branch_id, code)
    if account:
        return account
    account = Account(branch_id=branch_id, code=code, name=name, account_type=account_type, is_active=True)
    db.add(account)
    db.flush()
    return account


def run_depreciation(db: Session, branch_id: int, year: int, month: int, user_id: int) -> DepreciationRunResult:
    """يشغّل دورة إهلاك خطي شهرية لكل الأصول المؤهّلة في الفرع (عندها
    purchase_cost + useful_life_years وحالتها مش disposed)، ويرحّل قيد يومية
    واحد مجمّع (Dr. مصروف إهلاك / Cr. مجمّع إهلاك) لإجمالي المبلغ.

    Idempotent فعليًا: UniqueConstraint(asset_id, year, month) في
    AssetDepreciationEntry يمنع ترحيل نفس الأصل لنفس الشهر مرتين — إعادة
    تشغيل الدورة نفسها بأمان بترحّل بس الأصول اللي لسه ماترحّلتش."""
    import calendar  # noqa: PLC0415
    from app.modules.finance.models import AssetDepreciationEntry  # noqa: PLC0415

    last_day = calendar.monthrange(year, month)[1]
    period_end = date(year, month, last_day)
    validate_period_open(db, branch_id, period_end)

    assets = crud.get_depreciable_assets(db, branch_id)
    created_entries: list[AssetDepreciationEntry] = []
    skipped: list[str] = []
    total_amount = Decimal("0")

    for asset in assets:
        if asset.depreciation_start_date and asset.depreciation_start_date > period_end:
            skipped.append(f"{asset.code} — لسه ماجاش تاريخ بداية الإهلاك")
            continue
        if crud.get_depreciation_entry_for_period(db, asset.id, year, month):
            skipped.append(f"{asset.code} — اترحّل الشهر ده قبل كده")
            continue

        depreciable_base = (asset.purchase_cost or Decimal("0")) - (asset.salvage_value or Decimal("0"))
        if depreciable_base <= 0 or not asset.useful_life_years:
            skipped.append(f"{asset.code} — لا توجد قيمة قابلة للإهلاك")
            continue

        remaining = depreciable_base - (asset.accumulated_depreciation or Decimal("0"))
        if remaining <= 0:
            skipped.append(f"{asset.code} — مُهلَك بالكامل بالفعل")
            continue

        monthly_amount = (depreciable_base / Decimal(asset.useful_life_years * 12)).quantize(Decimal("0.01"))
        actual_amount = min(monthly_amount, remaining)  # الشهر الأخير غالبًا أصغر بسبب التقريب
        new_accumulated = (asset.accumulated_depreciation or Decimal("0")) + actual_amount

        entry = crud.create_depreciation_entry(
            db, asset_id=asset.id, branch_id=branch_id, year=year, month=month,
            amount=actual_amount, accumulated_after=new_accumulated, posted_by=user_id,
        )
        asset.accumulated_depreciation = new_accumulated
        created_entries.append(entry)
        total_amount += actual_amount

    journal_entry_id: Optional[int] = None
    if created_entries:
        expense_acc = _get_or_create_account(
            db, branch_id, DEPRECIATION_EXPENSE_ACCOUNT_CODE, "مصروف إهلاك الأصول الثابتة", "expense",
        )
        accum_acc = _get_or_create_account(
            db, branch_id, ACCUMULATED_DEPRECIATION_ACCOUNT_CODE, "مجمّع إهلاك الأصول الثابتة", "asset",
        )
        entry_data = JournalEntryCreate(
            branch_id=branch_id,
            entry_date=period_end,
            reference=f"DEPR-{year}{month:02d}",
            description=f"إهلاك شهري ({len(created_entries)} أصل) — {year}-{month:02d}",
            source="depreciation",
            source_id=None,
            lines=[
                JournalLineCreate(account_id=expense_acc.id, debit=total_amount, credit=Decimal("0")),
                JournalLineCreate(account_id=accum_acc.id, debit=Decimal("0"), credit=total_amount),
            ],
        )
        je = post_journal_entry(db, entry_data, user_id)
        journal_entry_id = je.id
        for entry in created_entries:
            entry.journal_entry_id = journal_entry_id

    db.commit()
    for entry in created_entries:
        db.refresh(entry)

    return DepreciationRunResult(
        branch_id=branch_id, year=year, month=month,
        entries=[AssetDepreciationEntryRead.model_validate(e) for e in created_entries],
        total_amount=total_amount,
        journal_entry_id=journal_entry_id,
        skipped_assets=skipped,
    )


def list_depreciation_entries(db: Session, branch_id: int, asset_id: Optional[int], page: int, size: int):
    items, total = crud.list_depreciation_entries(db, branch_id, asset_id, skip=(page - 1) * size, limit=size)
    return items, total


# ── Bank Reconciliation ──────────────────────────────────────────────

def get_bank_account_or_404(db: Session, bank_account_id: int) -> BankAccount:
    account = crud.get_bank_account(db, bank_account_id)
    if not account:
        raise ValueError(f"الحساب البنكي {bank_account_id} غير موجود")
    return account


def create_bank_account(db: Session, data: BankAccountCreate) -> BankAccount:
    account = crud.create_bank_account(db, data)
    db.commit()
    db.refresh(account)
    return account


def update_bank_account(db: Session, bank_account_id: int, data: BankAccountUpdate) -> BankAccount:
    account = get_bank_account_or_404(db, bank_account_id)
    account = crud.update_bank_account(db, account, data)
    db.commit()
    db.refresh(account)
    return account


def import_bank_statement_lines(
    db: Session, bank_account_id: int, uploaded_by: int, data: BankStatementImportRequest,
) -> list[BankStatementLine]:
    account = get_bank_account_or_404(db, bank_account_id)
    lines = crud.create_bank_statement_lines(db, account.id, account.branch_id, uploaded_by, data.lines)
    db.commit()
    for line in lines:
        db.refresh(line)
    return lines


def auto_match_bank_statement_lines(db: Session, bank_account_id: int, matched_by: int) -> int:
    """محافظ (مش تخميني): يطابق تلقائيًا بس لو فيه مرشح دفعة واحد بالظبط
    (نفس المبلغ ± قرش، وتاريخ قريب، غير مرتبط بسطر تاني) — أي غموض (صفر أو
    أكتر من مرشح) بيتسيب للمطابقة اليدوية بدل ما يخمّن ويغلط."""
    account = get_bank_account_or_404(db, bank_account_id)
    lines, _ = crud.list_bank_statement_lines(db, account.id, status="unmatched", limit=1000)
    matched_count = 0
    for line in lines:
        if line.amount <= 0:
            continue  # مطابقة السحوبات/العمولات البنكية يدوية دايمًا (مفيش Payment مقابل)
        candidates = crud.find_matching_payment_candidates(db, account.branch_id, line.amount, line.line_date)
        if len(candidates) == 1:
            crud.match_statement_line(db, line, candidates[0].id, matched_by)
            matched_count += 1
    db.commit()
    return matched_count


def match_bank_statement_line(
    db: Session, bank_account_id: int, line_id: int, payment_id: int, matched_by: int,
) -> BankStatementLine:
    account = get_bank_account_or_404(db, bank_account_id)
    line = crud.get_bank_statement_line(db, line_id)
    if not line or line.bank_account_id != account.id:
        raise ValueError(f"سطر كشف الحساب {line_id} غير موجود")
    if line.status == "matched":
        raise ValueError("السطر ده متطابق بالفعل — ألغِ المطابقة أولاً لو عايز تغيّرها")
    payment = crud.get_payment(db, payment_id)
    if not payment or payment.branch_id != account.branch_id:
        raise ValueError(f"الدفعة {payment_id} غير موجودة")
    if payment.voided_at is not None:
        raise ValueError("الدفعة ملغاة — لا يمكن مطابقتها بسطر كشف حساب")
    line = crud.match_statement_line(db, line, payment_id, matched_by)
    db.commit()
    db.refresh(line)
    return line


def unmatch_bank_statement_line(db: Session, bank_account_id: int, line_id: int) -> BankStatementLine:
    account = get_bank_account_or_404(db, bank_account_id)
    line = crud.get_bank_statement_line(db, line_id)
    if not line or line.bank_account_id != account.id:
        raise ValueError(f"سطر كشف الحساب {line_id} غير موجود")
    if line.status != "matched":
        raise ValueError("السطر ده مش متطابق أصلاً")
    line = crud.unmatch_statement_line(db, line)
    db.commit()
    db.refresh(line)
    return line


def get_bank_reconciliation_summary(db: Session, bank_account_id: int, as_of: date) -> BankReconciliationSummary:
    """رصيد الدفاتر (من دفتر اليومية لو الحساب مربوط بـ gl_account_id، وإلا
    من الدفعات المطابقة فقط) مقابل رصيد كشف الحساب (كل السطور غير المتجاهلة)
    — الفرق بينهم + عدد السطور/الدفعات غير المطابقة هو تقرير المطابقة."""
    account = get_bank_account_or_404(db, bank_account_id)

    if account.gl_account_id:
        sums = crud.sum_journal_lines_by_account(db, account.branch_id, None, as_of)
        debit_sum, credit_sum = sums.get(account.gl_account_id, (Decimal("0"), Decimal("0")))
        book_balance = account.opening_balance + (debit_sum - credit_sum)
    else:
        book_balance = account.opening_balance + crud.sum_matched_payments(db, account.id, as_of)

    statement_balance = account.opening_balance + crud.sum_statement_lines(db, account.id, as_of)
    unmatched_lines = crud.count_unmatched_statement_lines(db, account.id)
    unmatched_pay_count, unmatched_pay_total = crud.unmatched_payments_summary(db, account.branch_id, as_of)
    difference = statement_balance - book_balance

    return BankReconciliationSummary(
        bank_account_id=account.id, as_of=as_of,
        opening_balance=account.opening_balance,
        book_balance=book_balance, statement_balance=statement_balance,
        difference=difference,
        is_reconciled=(abs(difference) <= Decimal("0.01") and unmatched_lines == 0),
        unmatched_statement_lines=unmatched_lines,
        unmatched_payments_count=unmatched_pay_count,
        unmatched_payments_total=unmatched_pay_total,
    )
