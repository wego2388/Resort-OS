"""app/modules/finance/services.py — Business logic"""
from __future__ import annotations

import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.finance import crud
from app.modules.finance.models import (
    AccountingPeriod, AccountingYearClose, BankAccount, BankStatementLine, CashierShift, CashReceipt,
    Check, CostCenter,
    Custody, ETAInvoice, ExchangeRate, Expense, Folio, FolioCharge, JournalEntry, Payment,
)
from app.modules.finance.schemas import (
    ActiveShiftSummary, ActiveShiftsResponse,
    AssetDepreciationEntryRead,
    BalanceSheetLine, BalanceSheetReport,
    BankAccountCreate, BankAccountUpdate, BankReconciliationSummary, BankStatementImportRequest,
    CashCountLineRead, CashierShiftClose, CashierShiftOpen, CashMovementCreate, CheckCreate,
    ConditionalDiscountCreate,
    ForeignCurrencySummary,
    CostCenterCreate,
    AccountLedgerLine, AccountLedgerReport,
    AgingBucket, AgingReport, PayableAgingLine, ReceivableAgingLine,
    CashReceiptCreate,
    CostCenterReport, CostCenterReportLine, CustodyCreate, CustodySettleRequest,
    DepreciationRunResult, ExchangeRateCreate, ExpenseCreate,
    ExpensePaymentCreate,
    ExpenseRead, FolioChargeCreate,
    FolioCreate,
    IncomeStatementLine, IncomeStatementReport,
    JournalEntryCreate, JournalLineCreate, PaymentChannelCreate, PaymentChannelUpdate, PaymentCreate,
    ShiftChannelSummary, ShiftEndReport, ShiftInvoiceLine,
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
from app.resort_os.timezone_utils import local_today, utc_naive_to_local_date

if TYPE_CHECKING:
    from app.modules.finance.models import ConditionalDiscount

logger = logging.getLogger(__name__)


class FinancialConfigurationError(Exception):
    """Gate 1B (Financial Atomicity): حساب GL أو مركز تكلفة مطلوب غير معرَّف
    للفرع، حتى بعد محاولة التجهيز التلقائي (ensure_default_cost_centers) —
    503، مش خطأ عميل (400) ولا database error عشوائي (500): إعداد ناقص
    محتاج محاسب/مدير يظبطه، مش غلطة في الطلب نفسه. تُرفع فقط من مسارات
    strict=True الصريحة (post_simple_revenue_journal، inventory._post_cogs_
    journal) — كل الاستدعاءات الحالية التانية (strict=False الافتراضي)
    تحافظ على سلوكها القديم تمامًا (ابتلاع صامت، ترجع None)."""


# ── Folio ─────────────────────────────────────────────────────────────

class FolioClosedError(ValueError):
    """محاولة إضافة شحنة لفوليو مقفول/ملغي — بتترفض تحت قفل الفوليو نفسه
    عشان تمنع سباق حقيقي بين إضافة شحنة وتسوية/إقفال نفس الفوليو في نفس
    اللحظة (راجع خطة Gate 1B، بند قفل الفوليو). يرث من ValueError (مراجعة
    Codex الثانية) عشان أي router قديم بيعمل ``except ValueError`` عام
    يفضل يمسكها ويترجمها 400 بدل ما تتسرب كـ 500 غير متوقع."""


def get_folio_or_404(db: Session, folio_id: int) -> Folio:
    folio = crud.get_folio(db, folio_id)
    if not folio:
        raise ValueError(f"الفوليو {folio_id} غير موجود")
    return folio


def add_folio_charge(db: Session, folio_id: int, data: FolioChargeCreate) -> FolioCharge:
    """نقطة الإدخال المركزية الوحيدة لإضافة شحنة فوليو (Gate 1B) — بتقفل صف
    الـ Folio (blocking FOR UPDATE) قبل إدخال الشحنة وإعادة حساب الإجمالي،
    وتعيد التحقق من حالته تحت القفل. كل نداءات crud.add_charge المباشرة
    القديمة (شاطئ/PMS/finance.post_charge) اتنقلت هنا عشان ترث القفل من غير
    تكرار منطقه في كل موديول — دايننج بيستخدمها كمان جوه معاملة الدفع
    الصارمة (نفس القفل، معاد الدخول عليه بأمان جوه نفس المعاملة)."""
    folio = crud.lock_folio_for_update(db, folio_id)
    if not folio:
        raise ValueError(f"الفوليو {folio_id} غير موجود")
    if folio.status in ("closed", "cancelled"):
        raise FolioClosedError(f"لا يمكن إضافة شحنة لفوليو {folio.status} (#{folio_id})")
    charge = crud.add_charge(db, folio_id, data)
    crud.recalculate_folio_total(db, folio)
    return charge


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

    charge = add_folio_charge(db, folio_id, data)
    db.commit()
    db.refresh(charge)
    return charge


def settle_folio(db: Session, folio_id: int) -> Folio:
    """بتقفل صف الفوليو (نفس قفل add_folio_charge) قبل can_checkout/التسوية/
    الإقفال — عشان تمنع سباق حقيقي: شحنة جديدة بتتضاف في نفس اللحظة اللي
    فيها تسوية شغالة على نفس الفوليو (راجع خطة Gate 1B). النتيجة المضمونة:
    إما شحنة جديدة على فوليو لسه مفتوح، أو فوليو مقفول من غير أي شحنة
    فاتت التسوية — مستحيل تحصل الحالتين مع بعض."""
    folio = crud.lock_folio_for_update(db, folio_id)
    if not folio:
        raise ValueError(f"الفوليو {folio_id} غير موجود")
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

class OpenShiftConflictError(ValueError):
    """محاولة فتح وردية تانية لنفس (الفرع، الكاشير) اللي عنده وردية مفتوحة —
    409. يرث من ValueError عشان أي router قديم بيمسك ValueError عام يفضل
    يترجمها 400 لو ما ميّزهاش، لكن الراوتر بيميّزها لـ 409 (سباق فتح مزدوج)."""


class ShiftCloseInProgressError(Exception):
    """Gate 4 (جولة مراجعة Codex الأولى): محاولة نسب Payment/CashMovement
    لوردية بتتقفل الآن بعملية إغلاق أخرى (SELECT FOR UPDATE NOWAIT فشل على
    صف الوردية) — 409 SHIFT_CLOSE_IN_PROGRESS. الكاشير يعيد المحاولة بعد ما
    الإغلاق يخلص؛ من غير القفل ده كان ممكن الدفع ينجح منسوبًا لوردية
    مقفولة فعليًا (لا حالة رمادية — الـ brief §2.5)."""


def _lock_open_shift_or_conflict(db: Session, branch_id: int, cashier_id: int) -> Optional[CashierShift]:
    """يقفل الوردية المفتوحة لـ(الفرع، الكاشير) بـNOWAIT ويترجم فشل القفل
    (وردية بتتقفل الآن) لـ ShiftCloseInProgressError (409) — Gate 4 (جولة
    مراجعة Codex الأولى). المسار الموحّد لأي كود بينسب Payment مباشر لوردية
    مفتوحة (add_payment هنا، settle_order في dining) عشان يتسلسل ضد
    close_shift. بيرجّع None لو مفيش وردية مفتوحة (سلوك get_open_shift نفسه)."""
    from sqlalchemy.exc import OperationalError  # noqa: PLC0415
    from app.core.db_errors import is_lock_not_available  # noqa: PLC0415

    try:
        return crud.lock_open_shift_for_update(db, branch_id, cashier_id)
    except OperationalError as exc:
        if not is_lock_not_available(exc):
            raise
        raise ShiftCloseInProgressError(
            "الوردية بتتقفل الآن — حاول تسجيل الدفع تاني خلال لحظات"
        ) from exc


class OpenCashierShiftRequiredError(ValueError):
    """A live cash receipt/refund cannot exist outside an open drawer shift."""


def record_external_payment(
    db: Session,
    *,
    branch_id: int,
    amount: Decimal,
    payment_method: str,
    collector_id: int,
    reference: str,
    source: str,
    source_id: int,
    require_cash_shift: bool = True,
) -> Payment:
    """Record a module receipt/refund in the shared shift ledger.

    Only physical cash belongs to a drawer. Card and bank transfers retain the
    real collector for auditability but are deliberately excluded from shift
    totals by leaving shift_id unset.
    """
    if collector_id <= 0:
        raise ValueError("المستخدم المحصل مطلوب")
    if amount == 0:
        raise ValueError("مبلغ التحصيل أو الرد لا يمكن أن يكون صفرًا")
    if payment_method not in {"cash", "card", "bank_transfer"}:
        raise ValueError("طريقة الدفع يجب أن تكون cash أو card أو bank_transfer")

    shift_id = None
    if payment_method == "cash" and require_cash_shift:
        shift = _lock_open_shift_or_conflict(db, branch_id, collector_id)
        if not shift:
            raise OpenCashierShiftRequiredError(
                "لا توجد وردية كاشير مفتوحة للمستخدم — افتح الوردية قبل تسجيل حركة كاش"
            )
        shift_id = shift.id

    return crud.create_direct_payment(
        db,
        branch_id=branch_id,
        amount=amount,
        method=payment_method,
        posted_at=datetime.utcnow(),
        shift_id=shift_id,
        cashier_id=collector_id,
        reference=reference,
        ref_order_id=source_id,
        source=source,
    )


def open_shift(db: Session, cashier_id: int, opened_by: int, data: CashierShiftOpen) -> CashierShift:
    """Gate 4B: فتح الوردية بقى محمي بـ DB invariant حقيقي
    (uq_open_shift_per_branch_cashier، partial unique index على status='open')
    مش check-then-insert لوحده — طلبان متزامنان لنفس الكاشير مايقدروش يفتحوا
    ورديتين، التاني بيصطدم بالـ unique constraint. الـ pre-check الودّي باقي
    لرسالة أوضح في الحالة الشائعة (مش سباق)، والـ IntegrityError بيمسك
    السباق الحقيقي (أول واحد commit قبل التاني ما يوصل للـ insert)."""
    existing = crud.get_open_shift(db, data.branch_id, cashier_id)
    if existing:
        raise OpenShiftConflictError(
            f"يوجد وردية مفتوحة بالفعل (#{existing.id}) لهذا الكاشير — لازم تقفلها الأول"
        )
    try:
        shift = crud.create_shift(db, data.branch_id, cashier_id, opened_by, data.opening_float, data.notes)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise OpenShiftConflictError(
            "فيه وردية مفتوحة بالفعل لهذا الكاشير في هذا الفرع (سباق فتح مزدوج) — "
            "افتح صفحة الوردية من جديد"
        ) from exc
    db.refresh(shift)
    return shift


def record_cash_movement(
    db: Session, shift_id: int, data: CashMovementCreate, performed_by: int,
    acting_user_level: int = 100,
):
    """راجع Operations & Control Layer plan §3.2 (Cash Control ledger). كل
    حركة يدوية على الدرج (إيداع/سحب/عهدة نثرية/تنزيل خزنة/فتح الدرج بدون
    بيع/تصحيح) بتتسجّل هنا — قرار Mohamed 2026-07-13: "التصحيح" (correction)
    محتاج موافقة PIN مدير+ دايمًا؛ اتوسّع هنا ليشمل بقية الأنواع الستة كلها
    (نفس فئة الخطر — كل حركة كاش يدوية تستاهل نفس الإشراف، مش بس التصحيح)،
    قرار محافظ صريح مذكور في تقرير الدفعة دي لو Mohamed حابب يضيّق النطاق.

    زي void_order_item/apply_order_discount بالظبط: الموافقة مطلوبة على
    *محاولة* التسجيل نفسها، بغض النظر عن قيمة المبلغ (حتى drawer_open
    بمبلغ صفر — فتح الدرج نفسه فعل حسّاس يستاهل إشراف).

    Gate 4 (جولة مراجعة Codex الأولى): نقفل صف الوردية (lock_shift_for_update،
    blocking FOR UPDATE) قبل فحص حالتها بدل قراءة غير مقفولة — عشان تسجيل
    حركة كاش يتسلسل فعليًا ضد close_shift (اللي بيقفل نفس الصف)، فمستحيل
    تتسجّل حركة على وردية بتتقفل في نفس اللحظة وexpected_cash اتحسب من غيرها.
    """
    shift = crud.lock_shift_for_update(db, shift_id)
    if not shift:
        raise ValueError(f"الوردية {shift_id} غير موجودة")
    if shift.status == "closed":
        raise ValueError("الوردية مقفولة — لا يمكن تسجيل حركة كاش عليها")
    if data.destination and data.movement_type != "safe_drop":
        raise ValueError("الوجهة (destination) بتتحدد بس لحركة 'تنزيل خزنة' (safe_drop)")

    # Gate 4B: التصحيح (correction) لازم يحمل اتجاه صريح (increase|decrease) —
    # مالوش إشارة ضمنية زي باقي الأنواع، ومنعرفش نخمّن هل بيزوّد الكاش المتوقع
    # ولا بينقّصه. باقي الأنواع مايقبلوش direction (إشارتهم من نوعهم).
    if data.movement_type == "correction":
        if data.direction not in ("increase", "decrease"):
            raise ValueError(
                "حركة 'تصحيح' لازم تحدد اتجاه صريح: increase (تزوّد الكاش المتوقع) "
                "أو decrease (تنقّصه)"
            )
    elif data.direction is not None:
        raise ValueError("الاتجاه (direction) بيتحدد بس لحركة 'تصحيح' (correction)")

    from app.modules.core import policy_engine  # noqa: PLC0415

    approved_by = policy_engine.require_approval(
        db, "cash_movement",
        acting_user_level=acting_user_level,
        approver_user_id=data.approver_user_id, approver_pin=data.approver_pin,
    )

    movement = crud.create_cash_movement(
        db, shift.branch_id, shift_id, data.movement_type, data.amount, data.reason, performed_by,
        approved_by=approved_by, destination=data.destination, cost_center_id=data.cost_center_id,
        direction=data.direction,
    )
    policy_engine.record_policy_audit(
        db, f"cash_movement_{data.movement_type}",
        user_id=performed_by, approved_by=approved_by, branch_id=shift.branch_id,
        entity_type="cash_movement", entity_id=movement.id,
        data={
            "shift_id": shift_id, "movement_type": data.movement_type,
            "amount": str(data.amount), "reason": data.reason,
            "destination": data.destination, "cost_center_id": data.cost_center_id,
        },
    )
    db.commit()
    db.refresh(movement)
    return movement


def list_cash_movements(db: Session, shift_id: int):
    shift = crud.get_shift(db, shift_id)
    if not shift:
        raise ValueError(f"الوردية {shift_id} غير موجودة")
    return crud.list_cash_movements(db, shift_id)


def _cash_movement_expected_effect(movement) -> Decimal:
    """أثر حركة كاش يدوية على الكاش المتوقع في الدرج (Gate 4B). الصيغة
    الموثّقة (الـ brief §2.5):
      cash_in           → +amount
      cash_out          → -amount
      petty_cash        → -amount
      safe_drop         → -amount
      drawer_open       → 0 (فتح الدرج بدون بيع، أثره صفر)
      correction        → +amount لو direction=increase، -amount لو decrease
      correction (قديمة بلا اتجاه) → 0 (متتخمّنش — بتظهر في تحذير reconciliation)
    """
    mt = movement.movement_type
    amt = movement.amount or Decimal("0")
    if mt == "cash_in":
        return amt
    if mt in ("cash_out", "petty_cash", "safe_drop"):
        return -amt
    if mt == "drawer_open":
        return Decimal("0")
    if mt == "correction":
        if movement.direction == "increase":
            return amt
        if movement.direction == "decrease":
            return -amt
        return Decimal("0")  # legacy correction بلا اتجاه — مستبعدة
    return Decimal("0")


def build_shift_end_report(db: Session, shift_id: int, requesting_user=None) -> ShiftEndReport:
    """راجع Operations & Control Layer Batch 4 (2026-07-13، سد فجوة أمنية
    حقيقية اتكشفت أثناء مراجعة رؤية سجل التدقيق): ``requesting_user``
    اختياري (``None`` = نداء داخلي موثوق، زي close_shift بينادي عليها
    لملخّص العملات الأجنبية بعد ما هو نفسه أصلاً تأكد من الصلاحية) — لو
    اتبعت، بيفرض نفس قيد list_shift_invoices بالظبط: كاشير (level < مدير)
    يشوف وردية نفسه بس. قبل الإصلاح ده، `GET /finance/shifts/{id}/report`
    كان مقفول على get_cashier_user بس من غير أي تحقق ملكية خالص — أي كاشير
    كان يقدر يشوف تقرير وردية كاشير تاني (مبيعات/فرق كاش/هويته) بمجرد
    تخمين الـ shift_id."""
    shift = crud.get_shift(db, shift_id)
    if not shift:
        raise ValueError(f"الوردية {shift_id} غير موجودة")

    if requesting_user is not None:
        from app.core.deps import user_level  # noqa: PLC0415
        if user_level(requesting_user) < 60 and shift.cashier_id != requesting_user.id:
            raise PermissionError("لا يمكنك عرض تقرير وردية غيرك")

    payments = crud.payments_for_shift(db, shift_id)
    active = [p for p in payments if p.voided_at is None]
    voided = [p for p in payments if p.voided_at is not None]

    # M2 (جولة مراجعة Codex الأولى): نفصل البيع الموجب عن العكوس/المرتجعات
    # (Payment سالب) بدل ما نجمعهم صافي — التقرير بيعرض إجمالي البيع (gross)
    # وسطر مرتجعات منفصل صريح، والكاش المتوقع بيحسب الصافي داخليًا.
    positive = [p for p in active if p.amount > 0]
    reversals = [p for p in active if p.amount < 0]

    def _sum(method: str) -> Decimal:
        return sum((p.amount for p in positive if p.method == method), Decimal("0"))

    total_cash   = _sum("cash")
    total_card   = _sum("card")
    total_credit = _sum("credit")
    known = {"cash", "card", "credit"}
    total_other  = sum((p.amount for p in positive if p.method not in known), Decimal("0"))
    total_sales  = sum((p.amount for p in positive), Decimal("0"))
    voided_amount = sum((p.amount for p in voided), Decimal("0"))

    # مرتجعات صريحة (قيمة موجبة للعرض) + الصافي النقدي للكاش المتوقع.
    refunds_total = -sum((p.amount for p in reversals), Decimal("0"))
    refunds_count = len(reversals)
    cash_refunds  = -sum((p.amount for p in reversals if p.method == "cash"), Decimal("0"))
    net_cash = total_cash - cash_refunds

    # حصة الغرفة (room tenders) — مالهاش صف Payment، بنجمعها من لقطة
    # tender_breakdown على DiningSettlement (late import، زي finance.crud→
    # maintenance.Asset). صفر لو الوردية مفيهاش أي tender غرفة منسوب ليها.
    from app.modules.dining import crud as dining_crud  # noqa: PLC0415
    total_room = dining_crud.sum_room_tenders_for_shift(db, shift_id)

    # Gate 4B: الكاش المتوقع = رصيد الافتتاح + الكاش المحصّل + أثر الحركات
    # اليدوية (cash_in/out، عهدة، تنزيل خزنة، تصحيح موجّه). drawer_open صفر،
    # وأي correction قديمة بلا اتجاه بتتستبعد وبتظهر في تحذير reconciliation
    # بدل تخمين اتجاهها.
    movements = crud.list_cash_movements(db, shift_id)
    movements_effect = sum((_cash_movement_expected_effect(m) for m in movements), Decimal("0"))
    unreconciled_corrections = [
        m for m in movements if m.movement_type == "correction" and m.direction not in ("increase", "decrease")
    ]
    # الكاش المتوقع بيستخدم الصافي النقدي (بيع كاش − مرتجع كاش) — المرتجع
    # النقدي كاش خرج فعليًا من الدرج فلازم يقلّل المتوقع، حتى لو معروض كبند
    # منفصل. مطابق للسلوك القديم رقميًا (كان بيجمع كل دفعات الكاش صافي).
    live_expected_cash = shift.opening_float + net_cash + movements_effect
    expected_cash = shift.expected_cash if shift.status == "closed" and shift.expected_cash is not None \
        else live_expected_cash
    cash_movements_warning = None
    if unreconciled_corrections:
        cash_movements_warning = (
            f"⚠️ {len(unreconciled_corrections)} حركة تصحيح قديمة بلا اتجاه صريح — "
            "مستبعدة من حساب الكاش المتوقع لحد ما تتراجع"
        )

    prev = crud.get_previous_closed_shift(db, shift.branch_id, shift.cashier_id, shift.id, shift.opened_at)
    previous_total_sales = None
    delta_vs_previous = None
    if prev:
        prev_payments = crud.payments_for_shift(db, prev.id)
        prev_active = [p for p in prev_payments if p.voided_at is None]
        previous_total_sales = sum((p.amount for p in prev_active), Decimal("0"))
        delta_vs_previous = total_sales - previous_total_sales

    cash_count_lines = crud.list_cash_count_lines(db, shift_id)

    # POS-03: نحسب الكاش المتوقع لكل عملة أجنبية من الدفعات الفعلية.
    # لو الكاشير استلم 50 USD كاش في بيع حقيقي → هيظهر Payment.currency="USD"
    # وPayment.fx_rate يسجّل سعر الصرف. المبلغ الأصلي بالعملة الأجنبية =
    # payment.amount / payment.fx_rate (لأن amount دايمًا EGP-equivalent).
    expected_by_currency: dict[str, Decimal] = {}
    for p in positive:
        cur = (p.currency or "EGP").upper()
        if cur != "EGP" and p.method == "cash":
            fx = p.fx_rate if (hasattr(p, "fx_rate") and p.fx_rate and p.fx_rate != 0) else Decimal("1")
            original_amount = (p.amount / fx).quantize(Decimal("0.01"))
            expected_by_currency[cur] = expected_by_currency.get(cur, Decimal("0")) + original_amount

    # ملخص العملات الأجنبية — نجمّع لكل عملة غير EGP من عدّ الكاش
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
                    "expected_amount": expected_by_currency.get(cur),
                }
            foreign[cur]["total_foreign"]  += line.subtotal
            foreign[cur]["egp_equivalent"] += line.egp_equivalent

    # POS-03: أضف variance لكل عملة (total_foreign - expected_amount)
    for cur, data in foreign.items():
        if data["expected_amount"] is not None:
            data["variance"] = data["total_foreign"] - data["expected_amount"]

    foreign_summary = [ForeignCurrencySummary(**v) for v in foreign.values()]

    # تفصيل حسب قناة التحصيل الفعلية — لقطة payment_channel_id/code وقت
    # البيع نفسه (تغيير القناة بعد كده ميأثّرش على تقارير ورديات قديمة).
    # دفعات legacy (بلا قناة) بتتجمّع تحت الطريقة الخام، مش بتختفي.
    channel_groups: dict[tuple, dict] = {}
    for p in positive:
        key = (p.payment_channel_id, p.payment_channel_code or p.method)
        group = channel_groups.setdefault(key, {
            "payment_channel_id": p.payment_channel_id,
            "payment_channel_code": p.payment_channel_code,
            "label": p.payment_channel_name or p.method,
            "method": p.method,
            "amount": Decimal("0"),
            "count": 0,
        })
        group["amount"] += p.amount
        group["count"] += 1
    channel_breakdown = [ShiftChannelSummary(**v) for v in channel_groups.values()]

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
        total_room=total_room,
        refunds_total=refunds_total,
        refunds_count=refunds_count,
        invoice_count=len(positive),
        voided_count=len(voided),
        voided_amount=voided_amount,
        expected_cash=expected_cash,
        counted_cash=shift.counted_cash,
        variance=shift.variance,
        cash_count=[CashCountLineRead.model_validate(line) for line in cash_count_lines],
        foreign_currency_summary=foreign_summary,
        channel_breakdown=channel_breakdown,
        # لو الوردية مقفولة وعندها cash_count_lines، نستخدم المجموع المحسوب منها.
        # لو الوردية مقفولة بـ counted_cash مباشر (بدون فئات)، نستخدمه.
        # لو الوردية لسه مفتوحة وما فيش عدّ بعد، نرجع Decimal("0") بدل None
        # لأن null في ملخص المبيعات مربك للكاشير اللي بيتابع مبيعاته خلال اليوم.
        counted_cash_egp=(
            counted_cash_egp if cash_count_lines
            else (shift.counted_cash if shift.counted_cash is not None else Decimal("0"))
        ),
        previous_shift_id=prev.id if prev else None,
        previous_total_sales=previous_total_sales,
        delta_vs_previous=delta_vs_previous,
        cash_movements_effect=movements_effect,
        cash_movements_warning=cash_movements_warning,
    )


def generate_shift_end_report_pdf(db: Session, shift_id: int, requesting_user=None) -> bytes:
    """تقرير نهاية الوردية جاهز للطباعة (يقابل rpt_shift_end في الأنظمة التجارية).
    راجع build_shift_end_report — نفس قيد الملكية بالظبط (Batch 4)."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    r = build_shift_end_report(db, shift_id, requesting_user)

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
        # M2: حصة الغرفة والمرتجعات كبنود مستقلة صريحة (مش مخفية في الصافي).
        ("محمّل على الغرف",        f"{r.total_room:,.2f} EGP"),
        ("المرتجعات/العكوس",      f"-{r.refunds_total:,.2f} EGP ({r.refunds_count})"),
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


def close_shift(
    db: Session, shift_id: int, closed_by: int, data: CashierShiftClose,
    acting_user_level: int = 100,
) -> CashierShift:
    """يقفل وردية الكاشير مع مطابقة (reconciliation) حقيقية للكاش — راجع
    wagdy.md بند 14 (حرج): كان ممكن كاشير يقفل ورديته بفرق ضخم بين المبيعات
    المسجّلة والكاش الفعلي المعدود من غير أي رفض أو حتى تنبيه حقيقي، يعني عجز
    كاش حقيقي (سرقة أو غلط جسيم في العدّ) كان بيتسجّل بصمت للأبد.

    الـ "blind count" (راجع test_blind_cash_count_never_reveals_expected_cash_before_close)
    فضل زي ما هو تمامًا — الكاشير لسه بيعدّ ويبعت رقمه *قبل* ما يشوف أي رقم
    متوقع. المطابقة هنا بتحصل بعد الاستلام مباشرة، سيرفر-سايد بالكامل.

    ``acting_user_level`` الافتراضي (100) مقصود — نفس اتفاقية
    restaurant.services.void_order_item، أي caller داخلي (تستات/سكريبتات) من
    غير ما يحدده معناه "موثوق"، بس الراوتر (المسار الإنتاجي الوحيد) بيمرّر
    المستوى الفعلي دايمًا. راجع wagdy.md بند S-06: فرق كاش أكبر من الحد
    المسموح بيترفض القفل (تحت) — إلا لو ``data.force_close=True`` مع موافقة
    PIN من مدير+ (أو المنفّذ نفسه مدير+، راجع core.services.resolve_pin_approval).

    ملكية الوردية (2026-07-13، Operations & Control Layer): كاشير (level <
    مدير) يقفل وردية نفسه بس — لو حاول يقفل وردية كاشير تاني بـ shift_id
    مخمّن، ``PermissionError``. مدير+ مؤهّل يقفل أي وردية (force-close نيابة
    عن كاشير غائب/عطلان — قرار محمد صراحةً: "من صلاحيات المدير إنه يعمل
    كده")، نفس نمط ``build_shift_end_report``/``list_shift_invoices``.
    """
    # نضمن وجود أسعار صرف افتراضية قبل القفل — هنا قبل lock_shift_for_update
    # عشان ensure_default_exchange_rates بتعمل db.commit() خاص بيها لو زرعت
    # بيانات جديدة، فلازم تتنفّذ خارج transaction القفل الأساسي تمامًا وإلا
    # ممكن يحصل commit مبكر جوه transaction القفل لو الـ session مفتوحة.
    ensure_default_exchange_rates(db)

    # Gate 4B: نقفل صف الوردية (blocking FOR UPDATE) قبل أي فحص/كتابة —
    # إغلاقان متزامنان لنفس الوردية بيتسلسلوا، فالتاني بيشوف status='closed'
    # تحت القفل ويترفض، بدل ما يكتب count lines أو variance مرتين (double-close).
    shift = crud.lock_shift_for_update(db, shift_id)
    if not shift:
        raise ValueError(f"الوردية {shift_id} غير موجودة")
    if shift.status == "closed":
        raise ValueError("الوردية مقفولة بالفعل")
    if acting_user_level < 60 and shift.cashier_id != closed_by:
        raise PermissionError("لا يمكنك قفل وردية غيرك")

    # M3 (جولة مراجعة Codex الأولى — الـ brief §2.5): مدير يقفل وردية شخص
    # تاني (مش ورديته) محتاج سبب صريح + موافقة معتمدة + AuditLog. قبل الجولة
    # دي كان أي مدير+ يقفل أي وردية بلا سبب ولا أثر تدقيق. نعيد استخدام
    # core.services.resolve_pin_approval (نفس نمط void/discount — مدير+ مؤهّل
    # بنفسه فمفيش PIN، لكن لو approver_* اتبعتوا بيتحققوا) بدل آلية موافقة
    # موازية. الحقول approver_*/notes الموجودة أصلاً على CashierShiftClose
    # بتتوصّل هنا فعليًا (كانت stale). force_close باقٍ كحقل متوافق-خلفيًا
    # بلا أثر بوّابي (آلية رفض الفرق أُلغيت — قرار Mohamed 2026-07-14).
    closing_other = shift.cashier_id != closed_by
    other_close_reason = ""
    other_close_approved_by: Optional[int] = None
    if closing_other:
        other_close_reason = (data.notes or "").strip()
        if not other_close_reason:
            raise ValueError(
                "قفل وردية كاشير تاني محتاج سبب صريح في الملاحظات (notes) — "
                "مين بيقفلها نيابةً عنه وليه"
            )
        from app.modules.core.services import resolve_pin_approval  # noqa: PLC0415
        other_close_approved_by = resolve_pin_approval(
            db, acting_user_level, data.approver_user_id, data.approver_pin,
            min_approver_level=60,
        )

    # نحسب الكاش المتوقع (expected_cash) الأول — قبل أي تعديل فعلي على
    # الداتابيز، بنفس مبدأ فحص حد الائتمان في beach.services.checkin_b2b:
    # لو القفل هيترفض، محدش (لا shift ولا cash_count_lines) يتأثر أو
    # يحتاج عكس لاحقًا.
    report = build_shift_end_report(db, shift_id)
    expected_cash = report.expected_cash

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
                # get_rate يجرّب السعر المباشر ثم المعكوس (inverse fallback)
                # ويزرع الأسعار الافتراضية تلقائيًا لو ما فيش أي سعر مسجّل —
                # أكثر مرونة من crud.get_latest_exchange_rate مباشرةً التي كانت
                # ترفض القفل لو السعر مسجّل بالاتجاه المعكوس فقط.
                # ValueError من get_rate بتطلع رسالة واضحة بالعملة الناقصة.
                fx_rate = get_rate(db, currency, "EGP", today)
            lines_for_db.append({
                "denomination": line.denomination,
                "currency":     currency,
                "quantity":     line.quantity,
                "fx_rate":      fx_rate,
            })

        # counted_cash (EGP) = مجموع egp_equivalent لكل السطور — بيتحسب هنا في
        # الذاكرة بس (السطور لسه ما اتكتبتش في الداتابيز) عشان فحص المطابقة
        # تحت يقدر يرفض القفل قبل أي كتابة فعلية.
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
        lines_for_db = None

    variance = counted_cash - expected_cash
    abs_variance = abs(variance)

    # قرار Mohamed (2026-07-14): الوردية تُقفل دايماً بغض النظر عن حجم الفرق.
    # الكاشير مش مسؤوليته الاحتجاز — مسؤوليته العدّ الصح.
    # المحاسب هو اللي يراجع الفروقات في تفاصيل الوردية ويتابع.
    # آلية الرفض (reject_threshold + force_close + PIN) أُلغيت بالكامل.
    # كل الفروقات بتظهر كـ warning للمحاسب في CashierShiftRead.

    if lines_for_db is not None:
        crud.create_cash_count_lines(db, shift_id, lines_for_db)

    # warning تشغيلي — الوردية تُقفل دايماً، الفرق يُسجَّل ويظهر للمحاسب.
    warning_threshold = Decimal(str(settings.CASH_VARIANCE_WARNING_ABS))
    reconciliation_ok = abs_variance <= warning_threshold
    reconciliation_warning = None
    if not reconciliation_ok:
        direction = "زيادة" if variance > 0 else "عجز"
        reconciliation_warning = (
            f"⚠️ فرق كاش: {direction} {abs_variance:,.2f} ج "
            f"(متوقع {expected_cash:,.2f} ج — معدود {counted_cash:,.2f} ج)"
        )

    shift.expected_cash = expected_cash
    shift.counted_cash = counted_cash
    shift.variance = variance
    shift.status = "closed"
    shift.closed_at = datetime.utcnow()
    shift.closed_by = closed_by
    if data.notes:
        shift.notes = f"{shift.notes}\n{data.notes}" if shift.notes else data.notes
    if data.handover_note:
        shift.handover_note = data.handover_note

    # M3: AuditLog إجباري لقفل مدير لوردية شخص تاني — يوثّق مين قفل، وردية مين،
    # السبب، المعتمِد (لو فيه)، والفرق. جزء من نفس معاملة الإغلاق (بيتكوميت تحت).
    if closing_other:
        from app.modules.core import policy_engine  # noqa: PLC0415
        policy_engine.record_policy_audit(
            db, "close_other_shift",
            user_id=closed_by, approved_by=other_close_approved_by, branch_id=shift.branch_id,
            entity_type="cashier_shift", entity_id=shift.id,
            data={
                "target_cashier_id": shift.cashier_id,
                "reason": other_close_reason,
                "variance": str(variance),
            },
        )

    db.commit()
    db.refresh(shift)
    # حقول transient (مش أعمدة DB حقيقية) — بيقرأها الراوتر بس عشان يبنيها
    # في response الـ HTTP، بدون ما يعيد حساب أي منطق عمل بنفسه (راجع §4 CLAUDE.md).
    shift.reconciliation_ok = reconciliation_ok
    shift.reconciliation_warning = reconciliation_warning
    return shift


def get_latest_handover_note(db: Session, branch_id: int) -> Optional[str]:
    """آخر ملاحظة تسليم من آخر وردية مقفولة في الفرع ده — بيشوفها اللي هيفتح
    الوردية الجاية قبل ما يبدأ، عشان يعرف أي حاجة معلّقة من الوردية اللي قبله."""
    shift = crud.get_latest_closed_shift(db, branch_id)
    return shift.handover_note if shift else None


def build_active_shifts_response(db: Session, branch_id: int) -> ActiveShiftsResponse:
    """ملخص كل الورديات المفتوحة في الفرع — للمراقبة اللحظية (مدير+).
    بيجيب كل وردية مفتوحة مع إجماليات مبيعاتها الحالية بدون قفل أو تعديل.
    خفيف عمداً: لا يحسب cash_count_lines أو journal entries — بس الـ Payments.
    """
    from app.core.kernel import models as kernel_models  # noqa: PLC0415

    open_shifts = crud.get_all_open_shifts(db, branch_id)

    # نجيب أسماء الكاشيرين بـ query واحدة بدل N queries
    cashier_ids = list({s.cashier_id for s in open_shifts})
    cashier_names: dict[int, str] = {}
    if cashier_ids:
        users = (
            db.query(kernel_models.user.User)
            .filter(kernel_models.user.User.id.in_(cashier_ids))
            .all()
        )
        cashier_names = {u.id: (u.full_name or u.username) for u in users}

    summaries: list[ActiveShiftSummary] = []
    for shift in open_shifts:
        payments = crud.payments_for_shift(db, shift.id)
        active = [p for p in payments if p.voided_at is None]
        positive = [p for p in active if p.amount > 0]
        reversals = [p for p in active if p.amount < 0]

        total_sales = sum((p.amount for p in positive), Decimal("0"))
        total_cash  = sum((p.amount for p in positive if p.method == "cash"), Decimal("0"))
        total_card  = sum((p.amount for p in positive if p.method == "card"), Decimal("0"))
        cash_refunds = -sum((p.amount for p in reversals if p.method == "cash"), Decimal("0"))
        net_cash = total_cash - cash_refunds

        movements = crud.list_cash_movements(db, shift.id)
        movements_effect = sum((_cash_movement_expected_effect(m) for m in movements), Decimal("0"))
        expected_cash = shift.opening_float + net_cash + movements_effect

        summaries.append(ActiveShiftSummary(
            shift_id=shift.id,
            branch_id=shift.branch_id,
            cashier_id=shift.cashier_id,
            cashier_name=cashier_names.get(shift.cashier_id, f"#{shift.cashier_id}"),
            opened_at=shift.opened_at,
            opening_float=shift.opening_float,
            total_sales=total_sales,
            total_cash=total_cash,
            total_card=total_card,
            expected_cash=expected_cash,
            invoice_count=len(positive),
        ))

    return ActiveShiftsResponse(
        branch_id=branch_id,
        shift_count=len(summaries),
        shifts=summaries,
        as_of=datetime.utcnow(),
    )


def list_shift_invoices(
    db: Session, shift_id: int, requesting_user,
    approver_user_id: Optional[int] = None, approver_pin: Optional[str] = None,
) -> list[ShiftInvoiceLine]:
    """سجل فواتير الوردية (InvoiceLogModal، wagdy.md بند S-02) — كل دفعة
    حقيقية مربوطة بالوردية عبر Payment.shift_id، مع اسم ضيف كل فاتورة.

    قيدين محكومين هنا (مش endpoint عرض عام):
    1. كاشير (level < مدير) يقدر يشوف وردية نفسه بس — أي وردية غيره PermissionError.
    2. حتى وردية نفسه، لازم موافقة PIN من مدير+ (أو يكون هو نفسه مدير+) —
       بيانات مالية تفصيلية حسّاسة (راجع core.services.resolve_pin_approval
       وwagdy.md بند S-03: PinGuardModal هي البوابة على الفرونت إند لده).
    """
    shift = crud.get_shift(db, shift_id)
    if not shift:
        raise ValueError(f"الوردية {shift_id} غير موجودة")

    from app.core.deps import user_level  # noqa: PLC0415
    from app.modules.core import policy_engine  # noqa: PLC0415

    acting_level = user_level(requesting_user)
    if acting_level < 60 and shift.cashier_id != requesting_user.id:
        raise PermissionError("لا يمكنك عرض فواتير وردية غيرك")

    policy_engine.require_approval(
        db, "view_other_cashier_shift_invoices",
        acting_user_level=acting_level,
        approver_user_id=approver_user_id, approver_pin=approver_pin,
    )

    payments = crud.list_shift_payments_with_folio(db, shift_id)
    return [
        ShiftInvoiceLine(
            payment_id=p.id,
            folio_id=p.folio_id,
            guest_name=p.folio.guest_name if p.folio else "—",
            amount=p.amount,
            method=p.method,
            reference=p.reference,
            posted_at=p.posted_at,
            is_voided=p.voided_at is not None,
            voided_at=p.voided_at,
        )
        for p in payments
    ]


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
    total_debit = sum((ln.debit for ln in data.lines), Decimal("0"))
    total_credit = sum((ln.credit for ln in data.lines), Decimal("0"))
    if abs(total_debit - total_credit) > Decimal("0.01"):
        raise ValueError(f"القيد غير متوازن: مدين={total_debit}, دائن={total_credit}")
    # ⚠️ باج حقيقي كان هنا (مراجعة Codex المستقلة قبل الإطلاق، 2026-08-30،
    # C-01): مفيش أي تحقق إن account_id/cost_center_id في كل سطر فعلاً
    # بيتبعوا نفس فرع القيد — قيد على فرع A كان يقدر يستخدم حساب أو مركز
    # تكلفة فرع B، فيلوّث أرصدة الفرعين مع بعض. هذه الدالة هي المسار الوحيد
    # اللي بيقبل account_id من المستخدم مباشرة (post_simple_revenue_journal
    # بتبني حساباتها هي بنفسها بـget_account_by_code(branch_id, code) —
    # آمنة بالبناء، مش محتاجة نفس التحقق).
    for line in data.lines:
        account = crud.get_account(db, line.account_id)
        if not account or account.branch_id != data.branch_id:
            raise ValueError(f"الحساب {line.account_id} غير موجود في فرع القيد")
        if line.cost_center_id is not None:
            cost_center = crud.get_cost_center(db, line.cost_center_id)
            if not cost_center or cost_center.branch_id != data.branch_id:
                raise ValueError(f"مركز التكلفة {line.cost_center_id} غير موجود في فرع القيد")
    entry = crud.create_journal_entry(db, data, user_id)
    db.commit()
    db.refresh(entry)
    return entry


def record_expense(
    db: Session, branch_id: int, data: ExpenseCreate, recorded_by: int,
    acting_user_level: int = 100,
) -> Expense:
    """سند مصروفات حقيقي (2026-08-16، طلب Mohamed صراحةً) — بديل القيد
    اليدوي العام (بلا فئة/تتبّع) اللي كان الخيار الوحيد قبل كده. الفئة هي
    اختيار expense_account_id نفسه (حساب 5xxx). يرحّل Dr. حساب المصروف /
    Cr. حساب التسوية (كاش/بنك)، بنفس مسار post_simple_revenue_journal
    الموحّد (strict=True — فشل تجهيز الحساب لازم يظهر بوضوح للمحاسب، مش
    يتبلع بصمت زي مسارات البيع التلقائية).

    حد الموافقة (2026-08-19، طلب Mohamed): مبلغ >= EXPENSE_APPROVAL_
    THRESHOLD محتاج موافقة PIN مدير حاضر فعليًا (core.policy_engine،
    نفس نمط إلغاء صنف/تطبيق خصم دايننج بالظبط) — تحت الحد، أي محاسب+
    يسجّله لوحده زي ما كان بالظبط. acting_user_level افتراضيًا 100
    (زي apply_order_discount) عشان استدعاءات الاختبار المباشرة القديمة
    تفضل شغالة من غير تعديل — الـ router الحقيقي دايمًا بيمرر المستوى
    الفعلي (راجع user_level(user))."""
    approved_by = None
    if data.amount >= settings.EXPENSE_APPROVAL_THRESHOLD:
        from app.modules.core import policy_engine  # noqa: PLC0415
        approved_by = policy_engine.require_approval(
            db, "record_expense",
            acting_user_level=acting_user_level,
            approver_user_id=data.approver_user_id, approver_pin=data.approver_pin,
        )

    validate_period_open(db, branch_id, data.expense_date)

    expense_account = crud.get_account(db, data.expense_account_id)
    if not expense_account or expense_account.branch_id != branch_id:
        raise ValueError(f"حساب المصروف {data.expense_account_id} غير موجود في هذا الفرع")
    if expense_account.account_type != "expense":
        raise ValueError(f"الحساب «{expense_account.name}» ليس حساب مصروفات")
    if not expense_account.is_active:
        raise ValueError(f"الحساب «{expense_account.name}» معطّل")

    if data.defer_payment:
        # مصروف آجل (2026-08-19، طلب Mohamed) — الحساب الفعلي دايمًا 2180
        # (مصروفات مستحقة)، settlement_account_id من العميل بيتجاهل عمدًا.
        settlement_account = crud.get_account_by_code(db, branch_id, "2180")
        if not settlement_account:
            raise FinancialConfigurationError(
                "حساب المصروفات المستحقة (2180) غير معرَّف لهذا الفرع"
            )
        if settlement_account.account_type != "liability":
            raise FinancialConfigurationError("حساب 2180 لازم يكون حساب التزامات")
    else:
        if not data.settlement_account_id:
            raise ValueError("حساب التسوية مطلوب لسند مصروفات غير آجل")
        settlement_account = crud.get_account(db, data.settlement_account_id)
        if not settlement_account or settlement_account.branch_id != branch_id:
            raise ValueError(f"حساب التسوية {data.settlement_account_id} غير موجود في هذا الفرع")
        if settlement_account.account_type != "asset":
            raise ValueError(f"حساب التسوية «{settlement_account.name}» لازم يكون حساب أصول")
        if not settlement_account.is_active:
            raise ValueError(f"حساب التسوية «{settlement_account.name}» معطّل")

    cost_center_code = None
    if data.cost_center_id:
        cc = crud.get_cost_center(db, data.cost_center_id)
        if not cc or cc.branch_id != branch_id:
            raise ValueError(f"مركز التكلفة {data.cost_center_id} غير موجود في هذا الفرع")
        cost_center_code = cc.code

    entry = post_simple_revenue_journal(
        db, branch_id, data.expense_date,
        debit_account_code=expense_account.code,
        credit_account_code=settlement_account.code,
        amount=data.amount,
        reference=data.reference or f"EXP-{data.expense_date.isoformat()}",
        description=data.description,
        source="manual_expense",
        source_id=None,
        created_by=recorded_by,
        cost_center_code=cost_center_code,
        commit_cost_centers=False,
        strict=True,
    )
    expense = crud.create_expense(
        db, branch_id, data, journal_entry_id=entry.id, recorded_by=recorded_by,
        settlement_account_id=settlement_account.id,
        payment_status="unpaid" if data.defer_payment else "paid",
    )
    if approved_by is not None:
        from app.modules.core import policy_engine  # noqa: PLC0415
        policy_engine.record_policy_audit(
            db, "record_expense", user_id=recorded_by, approved_by=approved_by,
            branch_id=branch_id, entity_type="expense", entity_id=expense.id,
            data={"amount": str(data.amount), "expense_account_id": data.expense_account_id},
        )
    db.commit()
    db.refresh(expense)
    return expense


def void_expense(db: Session, expense_id: int, voided_by: int, reason: str = "voided via API") -> Expense:
    """إلغاء سند مصروفات اتسجّل بالفعل (2026-08-19، طلب Mohamed) — نفس نمط
    void_payment فوق بالظبط (عكس Dr/Cr، سجل تدقيق، commit ذري). مقصور
    عمدًا على سند من غير أي سداد مسجّل عليه بعد (amount_paid == 0) — سند
    آجل (راجع pay_expense لاحقًا) بعد ما يتسدد جزئيًا/كليًا يحتاج مراجعة
    يدوية أوسع (حالة نادرة مؤجَّلة، مش جزء من هذه الدفعة)."""
    expense = crud.get_expense(db, expense_id)
    if not expense:
        raise ValueError(f"سند المصروفات {expense_id} غير موجود")
    if expense.voided_at is not None:
        raise ValueError(f"سند المصروفات {expense_id} ملغى بالفعل")
    if expense.amount_paid and expense.amount_paid > 0:
        raise ValueError(
            f"سند المصروفات {expense_id} عليه سداد مسجّل بالفعل — لا يمكن إلغاؤه مباشرة"
        )
    expense_account = crud.get_account(db, expense.expense_account_id)
    settlement_account = crud.get_account(db, expense.settlement_account_id)
    if not expense_account or not settlement_account:
        raise ValueError(f"حسابات سند المصروفات {expense_id} غير مكتملة")
    try:
        original_amount = expense.amount
        expense = crud.void_expense(db, expense, voided_by)
        crud.create_revenue_audit_log(
            db, branch_id=expense.branch_id, entity_type="expense", entity_id=expense.id,
            old_value=original_amount, new_value=Decimal("0.00"), reason=reason, changed_by=voided_by,
        )
        # عكس القيد اللي record_expense رحّله (Dr.مصروف/Cr.تسوية) — التسوية
        # ترجع لحسابها والمصروف يتصفّر. strict=True زي void_payment بالظبط.
        from app.resort_os.timezone_utils import business_today  # noqa: PLC0415
        post_simple_revenue_journal(
            db, expense.branch_id, business_today(settings.TIMEZONE),
            debit_account_code=settlement_account.code, credit_account_code=expense_account.code,
            amount=original_amount,
            reference=f"EXP-VOID-{expense.id}",
            description=f"إلغاء سند مصروفات #{expense.id}",
            source="expense_void", source_id=expense.id,
            created_by=voided_by,
            strict=True, commit_cost_centers=False,
        )
        db.commit()
        db.refresh(expense)
        return expense
    except Exception:
        db.rollback()
        raise


def pay_expense(
    db: Session, expense_id: int, data: ExpensePaymentCreate, recorded_by: int,
) -> Expense:
    """سداد فعلي لسند مصروفات آجل (2026-08-19، طلب Mohamed) — يقفل حلقة
    2180 (مصروفات مستحقة) اللي record_expense فتحها لما defer_payment=True.
    نفس نمط inventory.services.pay_purchase_order بالظبط (Dr.الحساب
    الآجل/Cr.حساب التسوية لكل دفعة، تحديث amount_paid/payment_status)."""
    expense = crud.get_expense(db, expense_id)
    if not expense:
        raise ValueError(f"سند المصروفات {expense_id} غير موجود")
    if expense.voided_at is not None:
        raise ValueError(f"سند المصروفات {expense_id} ملغى — لا يمكن تسجيل سداد عليه")
    if expense.payment_status == "paid":
        raise ValueError(f"سند المصروفات {expense_id} مسدد بالكامل بالفعل")

    remaining = expense.amount - expense.amount_paid
    if data.amount > remaining + Decimal("0.01"):
        raise ValueError(f"المبلغ ({data.amount}) أكبر من المتبقي على السند ({remaining})")

    settlement_account = crud.get_account(db, data.settlement_account_id)
    if not settlement_account or settlement_account.branch_id != expense.branch_id:
        raise ValueError(f"حساب التسوية {data.settlement_account_id} غير موجود في هذا الفرع")
    if settlement_account.account_type != "asset":
        raise ValueError(f"حساب التسوية «{settlement_account.name}» لازم يكون حساب أصول")
    if not settlement_account.is_active:
        raise ValueError(f"حساب التسوية «{settlement_account.name}» معطّل")

    validate_period_open(db, expense.branch_id, data.paid_at)

    accrued_account = crud.get_account(db, expense.settlement_account_id)
    if not accrued_account:
        raise ValueError(f"حساب المصروفات المستحقة لسند {expense_id} غير موجود")

    entry = post_simple_revenue_journal(
        db, expense.branch_id, data.paid_at,
        debit_account_code=accrued_account.code, credit_account_code=settlement_account.code,
        amount=data.amount,
        reference=data.reference or f"EXP-{expense.id}-PAY",
        description=f"سداد سند مصروفات #{expense.id} — {expense.description}",
        source="expense_payment", source_id=expense.id,
        created_by=recorded_by,
        strict=True,
    )

    crud.create_expense_payment(
        db, expense.branch_id, expense.id, data,
        journal_entry_id=entry.id, recorded_by=recorded_by,
    )
    expense.amount_paid = expense.amount_paid + data.amount
    expense.payment_status = "paid" if expense.amount_paid >= expense.amount - Decimal("0.01") else "partial"
    db.commit()
    db.refresh(expense)
    return expense


def disburse_custody(db: Session, branch_id: int, data: CustodyCreate, disbursed_by: int) -> Custody:
    """صرف عهدة نقدية (2026-08-19، طلب Mohamed) — سلفة لموظف/مقاول لصرف
    بند معيّن (مقاولة/عمالة يومية...). يرحّل Dr.1190 (عهد نقدية تحت
    التسوية) / Cr.حساب المصدر، بنفس نمط record_expense (strict=True)."""
    validate_period_open(db, branch_id, data.disbursed_date)

    source_account = crud.get_account(db, data.source_account_id)
    if not source_account or source_account.branch_id != branch_id:
        raise ValueError(f"حساب المصدر {data.source_account_id} غير موجود في هذا الفرع")
    if source_account.account_type != "asset":
        raise ValueError(f"حساب المصدر «{source_account.name}» لازم يكون حساب أصول")
    if not source_account.is_active:
        raise ValueError(f"حساب المصدر «{source_account.name}» معطّل")

    custody_account = crud.get_account_by_code(db, branch_id, "1190")
    if not custody_account:
        raise FinancialConfigurationError("حساب العهد النقدية تحت التسوية (1190) غير معرَّف لهذا الفرع")
    if custody_account.account_type != "asset":
        raise FinancialConfigurationError("حساب 1190 لازم يكون حساب أصول")

    entry = post_simple_revenue_journal(
        db, branch_id, data.disbursed_date,
        debit_account_code=custody_account.code, credit_account_code=source_account.code,
        amount=data.amount,
        reference=data.reference or f"CUST-{data.disbursed_date.isoformat()}",
        description=f"صرف عهدة نقدية — {data.holder_name} ({data.purpose})",
        source="custody_disbursement", source_id=None,
        created_by=disbursed_by,
        commit_cost_centers=False,
        strict=True,
    )
    custody = crud.create_custody(
        db, branch_id, data, custody_account_id=custody_account.id,
        disbursement_entry_id=entry.id, disbursed_by=disbursed_by,
    )
    db.commit()
    db.refresh(custody)
    return custody


def settle_custody(
    db: Session, custody_id: int, data: CustodySettleRequest, settled_by: int,
) -> Custody:
    """تسوية عهدة (2026-08-19، طلب Mohamed) — توزيع فعلي دفعة واحدة
    (single-shot) لمبلغ العهدة على حسابات مصروفات حقيقية + مرتجع اختياري.
    مجموع lines + returned_amount لازم يساوي مبلغ العهدة بالظبط — تسوية
    جزئية عبر أكتر من جلسة حالة نادرة مؤجَّلة عمدًا.

    بيستخدم crud.create_journal_entry مباشرة (مش post_journal_entry) عشان
    post_journal_entry بتعمل commit داخلي بيكسر الذرّية مع تحديث حالة
    العهدة/بنود التسوية اللي لازم يحصلوا في نفس المعاملة — كل التحقق من
    الحسابات (موجودة/في نفس الفرع/نوعها Expense/مفعّلة) بيتعمل هنا يدويًا
    لأن crud.create_journal_entry نفسها زيرو تحقق (راجع record_expense
    لنفس النمط)."""
    custody = crud.get_custody(db, custody_id)
    if not custody:
        raise ValueError(f"العهدة {custody_id} غير موجودة")
    if custody.voided_at is not None:
        raise ValueError(f"العهدة {custody_id} ملغاة")
    if custody.status != "open":
        raise ValueError(f"العهدة {custody_id} متسواة بالفعل")
    if not data.lines and data.returned_amount <= 0:
        raise ValueError("لازم بند تسوية واحد على الأقل أو مبلغ مرتجع")

    lines_total = sum((line.amount for line in data.lines), Decimal("0"))
    total = lines_total + data.returned_amount
    if abs(total - custody.amount) > Decimal("0.01"):
        raise ValueError(
            f"مجموع بنود التسوية ({lines_total}) + المرتجع ({data.returned_amount}) "
            f"لازم يساوي مبلغ العهدة ({custody.amount}) بالظبط"
        )

    validate_period_open(db, custody.branch_id, data.settlement_date)

    journal_lines: list[JournalLineCreate] = []
    for line in data.lines:
        account = crud.get_account(db, line.expense_account_id)
        if not account or account.branch_id != custody.branch_id:
            raise ValueError(f"حساب المصروف {line.expense_account_id} غير موجود في هذا الفرع")
        if account.account_type != "expense":
            raise ValueError(f"الحساب «{account.name}» ليس حساب مصروفات")
        if not account.is_active:
            raise ValueError(f"الحساب «{account.name}» معطّل")
        if line.cost_center_id:
            cc = crud.get_cost_center(db, line.cost_center_id)
            if not cc or cc.branch_id != custody.branch_id:
                raise ValueError(f"مركز التكلفة {line.cost_center_id} غير موجود في هذا الفرع")
        journal_lines.append(JournalLineCreate(
            account_id=account.id, debit=line.amount, credit=Decimal("0"),
            description=line.description, cost_center_id=line.cost_center_id,
        ))

    if data.returned_amount > 0:
        source_account = crud.get_account(db, custody.source_account_id)
        if not source_account:
            raise ValueError(f"حساب مصدر العهدة {custody_id} غير موجود")
        journal_lines.append(JournalLineCreate(
            account_id=source_account.id, debit=data.returned_amount, credit=Decimal("0"),
            description=f"مرتجع عهدة #{custody.id}",
        ))

    journal_lines.append(JournalLineCreate(
        account_id=custody.custody_account_id, debit=Decimal("0"), credit=custody.amount,
        description=f"تسوية عهدة #{custody.id}",
    ))

    total_debit = sum((ln.debit for ln in journal_lines), Decimal("0"))
    total_credit = sum((ln.credit for ln in journal_lines), Decimal("0"))
    if abs(total_debit - total_credit) > Decimal("0.01"):
        raise ValueError(f"القيد غير متوازن: مدين={total_debit}, دائن={total_credit}")

    entry_data = JournalEntryCreate(
        branch_id=custody.branch_id, entry_date=data.settlement_date,
        reference=f"CUST-{custody.id}-SETTLE",
        description=(f"تسوية عهدة #{custody.id} — {custody.holder_name}")[:500],
        source="custody_settlement", source_id=custody.id,
        lines=journal_lines,
    )

    try:
        entry = crud.create_journal_entry(db, entry_data, settled_by)
        crud.create_custody_settlement_lines(db, custody.id, data.lines)
        custody.settlement_entry_id = entry.id
        custody.returned_amount = data.returned_amount
        custody.status = "settled"
        custody.settled_by = settled_by
        custody.settled_at = datetime.utcnow()
        db.commit()
        db.refresh(custody)
        return custody
    except Exception:
        db.rollback()
        raise


def void_custody(db: Session, custody_id: int, voided_by: int, reason: str = "voided via API") -> Custody:
    """إلغاء عهدة لسه open (لسه من غير أي تسوية) — نفس نمط void_expense
    بالظبط. عهدة متسواة بالفعل حالة نادرة مؤجَّلة (تحتاج مراجعة يدوية
    أوسع، مش إلغاء مباشر)."""
    custody = crud.get_custody(db, custody_id)
    if not custody:
        raise ValueError(f"العهدة {custody_id} غير موجودة")
    if custody.voided_at is not None:
        raise ValueError(f"العهدة {custody_id} ملغاة بالفعل")
    if custody.status != "open":
        raise ValueError(f"العهدة {custody_id} متسواة بالفعل — لا يمكن إلغاؤها مباشرة")

    source_account = crud.get_account(db, custody.source_account_id)
    custody_account = crud.get_account(db, custody.custody_account_id)
    if not source_account or not custody_account:
        raise ValueError(f"حسابات العهدة {custody_id} غير مكتملة")

    try:
        original_amount = custody.amount
        custody = crud.void_custody(db, custody, voided_by)
        crud.create_revenue_audit_log(
            db, branch_id=custody.branch_id, entity_type="custody", entity_id=custody.id,
            old_value=original_amount, new_value=Decimal("0.00"), reason=reason, changed_by=voided_by,
        )
        from app.resort_os.timezone_utils import business_today  # noqa: PLC0415
        post_simple_revenue_journal(
            db, custody.branch_id, business_today(settings.TIMEZONE),
            debit_account_code=source_account.code, credit_account_code=custody_account.code,
            amount=original_amount,
            reference=f"CUST-VOID-{custody.id}",
            description=f"إلغاء عهدة نقدية #{custody.id} — {custody.holder_name}",
            source="custody_void", source_id=custody.id,
            created_by=voided_by,
            strict=True, commit_cost_centers=False,
        )
        db.commit()
        db.refresh(custody)
        return custody
    except Exception:
        db.rollback()
        raise


def record_cash_receipt(db: Session, branch_id: int, data: CashReceiptCreate, recorded_by: int) -> CashReceipt:
    """إذن قبض عام (2026-08-19، طلب Mohamed) — تحصيل نقدية من مصدر متنوع
    مش مرتبط بمسار بيع قائم (سلفة عائدة، تعويض، إيراد متفرّق...). يرحّل
    Dr.destination_account (كاش/بنك) / Cr.source_account، نفس نمط
    record_expense بالظبط بس مقلوب الاتجاه. مفيش قيد على نوع
    source_account عمدًا (عكس expense_account في سند المصروفات)."""
    validate_period_open(db, branch_id, data.receipt_date)

    destination_account = crud.get_account(db, data.destination_account_id)
    if not destination_account or destination_account.branch_id != branch_id:
        raise ValueError(f"حساب الوجهة {data.destination_account_id} غير موجود في هذا الفرع")
    if destination_account.account_type != "asset":
        raise ValueError(f"حساب الوجهة «{destination_account.name}» لازم يكون حساب أصول (كاش/بنك)")
    if not destination_account.is_active:
        raise ValueError(f"حساب الوجهة «{destination_account.name}» معطّل")

    source_account = crud.get_account(db, data.source_account_id)
    if not source_account or source_account.branch_id != branch_id:
        raise ValueError(f"حساب المصدر {data.source_account_id} غير موجود في هذا الفرع")
    if not source_account.is_active:
        raise ValueError(f"حساب المصدر «{source_account.name}» معطّل")

    cost_center_code = None
    if data.cost_center_id:
        cc = crud.get_cost_center(db, data.cost_center_id)
        if not cc or cc.branch_id != branch_id:
            raise ValueError(f"مركز التكلفة {data.cost_center_id} غير موجود في هذا الفرع")
        cost_center_code = cc.code

    entry = post_simple_revenue_journal(
        db, branch_id, data.receipt_date,
        debit_account_code=destination_account.code, credit_account_code=source_account.code,
        amount=data.amount,
        reference=data.reference or f"RCV-{data.receipt_date.isoformat()}",
        description=data.description,
        source="manual_cash_receipt", source_id=None,
        created_by=recorded_by,
        cost_center_code=cost_center_code,
        commit_cost_centers=False,
        strict=True,
    )
    receipt = crud.create_cash_receipt(db, branch_id, data, journal_entry_id=entry.id, recorded_by=recorded_by)
    db.commit()
    db.refresh(receipt)
    return receipt


def void_cash_receipt(
    db: Session, receipt_id: int, voided_by: int, reason: str = "voided via API",
) -> CashReceipt:
    """إلغاء إذن قبض اتسجّل بالفعل — نفس نمط void_expense بالظبط بس مقلوب
    الاتجاه (Dr.source/Cr.destination بدل العكس)."""
    receipt = crud.get_cash_receipt(db, receipt_id)
    if not receipt:
        raise ValueError(f"إذن القبض {receipt_id} غير موجود")
    if receipt.voided_at is not None:
        raise ValueError(f"إذن القبض {receipt_id} ملغى بالفعل")

    destination_account = crud.get_account(db, receipt.destination_account_id)
    source_account = crud.get_account(db, receipt.source_account_id)
    if not destination_account or not source_account:
        raise ValueError(f"حسابات إذن القبض {receipt_id} غير مكتملة")

    try:
        original_amount = receipt.amount
        receipt = crud.void_cash_receipt(db, receipt, voided_by)
        crud.create_revenue_audit_log(
            db, branch_id=receipt.branch_id, entity_type="cash_receipt", entity_id=receipt.id,
            old_value=original_amount, new_value=Decimal("0.00"), reason=reason, changed_by=voided_by,
        )
        from app.resort_os.timezone_utils import business_today  # noqa: PLC0415
        post_simple_revenue_journal(
            db, receipt.branch_id, business_today(settings.TIMEZONE),
            debit_account_code=source_account.code, credit_account_code=destination_account.code,
            amount=original_amount,
            reference=f"RCV-VOID-{receipt.id}",
            description=f"إلغاء إذن قبض #{receipt.id}",
            source="cash_receipt_void", source_id=receipt.id,
            created_by=voided_by,
            strict=True, commit_cost_centers=False,
        )
        db.commit()
        db.refresh(receipt)
        return receipt
    except Exception:
        db.rollback()
        raise


def list_expenses(
    db: Session, branch_id: int,
    date_from: Optional[date] = None, date_to: Optional[date] = None,
    page: int = 1, size: int = 30,
) -> tuple[list[dict], int]:
    items, total = crud.list_expenses(db, branch_id, date_from, date_to, page, size)
    enriched = []
    for exp in items:
        row = ExpenseRead.model_validate(exp).model_dump()
        row["expense_account_code"] = exp.expense_account.code if exp.expense_account else ""
        row["expense_account_name"] = exp.expense_account.name if exp.expense_account else ""
        row["settlement_account_code"] = exp.settlement_account.code if exp.settlement_account else ""
        enriched.append(row)
    return enriched, total


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
    cost_center_code: Optional[str] = None,
    *,
    commit_cost_centers: bool = True,
    strict: bool = False,
) -> Optional[JournalEntry]:
    """يرحّل قيد بسيط بسطرين (Dr. حساب / Cr. حساب) — النمط المتكرر اللي كان
    منسوخ في 6 موديولات (مطعم/كافيه/شاطئ/PMS/ملكية جزئية/إيجارات) كل واحد بنسخته
    الخاصة. بيبتلع أي خطأ عمدًا (حساب مش معرّف للفرع، مبلغ صفري...) وبيرجّع
    None بدل ما يرفع — عشان فشل الترحيل المحاسبي ميمنعش إتمام العملية
    التشغيلية الحقيقية (بيع/حجز/عقد) اللي استدعته. لاحظ إنه بينادي
    crud.create_journal_entry مباشرة مش post_journal_entry — يعني من غير
    التحقق من قفل الفترة المحاسبية، بنفس السلوك القديم قبل التوحيد.

    لو currency مش EGP: amount هي القيمة بالعملة الأصلية، وبتتحوّل هنا لـ EGP
    بسعر الصرف وقت entry_date (نفس آلية convert_to_egp المستخدمة للفواتير) —
    السطور (debit/credit) دايمًا EGP-equivalent عشان التقارير المجمّعة تفضل
    صح، وbعملة/سعر الصرف الأصليين بيتسجّلوا على القيد نفسه للمراجعة.

    cost_center_code (Batch 3): كود مركز التكلفة (ROOM/REST/CAFE/BEACH/TS —
    راجع DEFAULT_COST_CENTERS) — لو متحدد، بيتوسم على السطرين الاتنين (مش
    الحساب الإيرادي/المصروفي بس، السطر المقابل كمان — تبسيط متعمد، والتقرير
    بيفلتر بالفعل حسب account_type فمش بيتأثر). لو مركز التكلفة مش موجود
    بعد لفرع ده (أول قيد يترحّل قبل أي نداء لـ ensure_default_cost_centers)،
    بيتزرع هنا تلقائيًا (idempotent) بدل ما التوسيم يفشل بصمت.

    commit_cost_centers/strict (Gate 1B): لكل الاستدعاءات الحالية، السلوك
    الافتراضي (commit_cost_centers=True, strict=False) **زي ما هو بالظبط
    قبل الجولة دي** — أي فشل بيتبلع ويرجع None. الاستدعاء الجديد الوحيد
    strict=True (دفع طلب دايننج) بيمرّر commit_cost_centers=False عشان
    ensure_default_cost_centers يعمل flush بس مش commit مستقل جوه معاملة
    الدفع، وبيخلي أي فشل تجهيز حساب/مركز تكلفة/تحويل عملة يرفع
    FinancialConfigurationError بدل ما يرجع None بصمت — عشان معاملة الدفع
    تقدر تفشل بوضوح (503) بدل ما تكمل من غير قيد محاسبي حقيقي."""
    try:
        if amount <= 0:
            if strict:
                raise FinancialConfigurationError("مبلغ القيد المحاسبي غير صالح (صفر أو سالب)")
            return None
        # كل حركة مالية حقيقية بتمرر source/source_id/reference ثابتين. إعادة
        # المحاولة (timeout عند العميل، Celery retry، أو reconciliation command
        # اتشغلت مرتين) لازم ترجع نفس القيد بدل ما تسجّل إيراد/تسوية مرتين.
        # reference جزء من المفتاح عمدًا لأن بعض الموديولات تستخدم نفس source
        # وsource_id لأحداث مختلفة على نفس الكيان (مثال عقد + دفعاته).
        if source and source_id is not None:
            existing = (
                db.query(JournalEntry)
                .filter(
                    JournalEntry.branch_id == branch_id,
                    JournalEntry.source == source,
                    JournalEntry.source_id == source_id,
                    JournalEntry.reference == reference,
                )
                .first()
            )
            if existing:
                logger.info(
                    "post_simple_revenue_journal: entry already posted for source=%s "
                    "source_id=%s reference=%s — returning entry %s",
                    source, source_id, reference, existing.id,
                )
                return existing

        debit_acc = crud.get_account_by_code(db, branch_id, debit_account_code)
        credit_acc = crud.get_account_by_code(db, branch_id, credit_account_code)
        if not debit_acc or not credit_acc:
            missing = debit_account_code if not debit_acc else credit_account_code
            if strict:
                raise FinancialConfigurationError(f"حساب محاسبي غير معرّف للفرع: {missing}")
            logger.error(
                "post_simple_revenue_journal: missing account '%s' for branch=%s source=%s "
                "source_id=%s reference=%s — journal entry NOT posted",
                missing, branch_id, source, source_id, reference,
            )
            return None

        cost_center_id = None
        if cost_center_code:
            cc = crud.get_cost_center_by_code(db, branch_id, cost_center_code)
            if not cc:
                ensure_default_cost_centers(db, branch_id, commit=commit_cost_centers)
                cc = crud.get_cost_center_by_code(db, branch_id, cost_center_code)
            if not cc and strict:
                raise FinancialConfigurationError(f"تعذّر تجهيز مركز التكلفة: {cost_center_code}")
            cost_center_id = cc.id if cc else None

        currency = (currency or "EGP").upper()
        if currency == "EGP":
            egp_amount, fx_rate = amount, Decimal("1")
        else:
            egp_amount = convert_to_egp(db, amount, currency, entry_date)
            if egp_amount <= 0:
                if strict:
                    raise FinancialConfigurationError("فشل تحويل العملة لقيمة موجبة")
                logger.error(
                    "post_simple_revenue_journal: currency conversion failed (%s %s) for "
                    "branch=%s source=%s source_id=%s reference=%s — journal entry NOT posted",
                    amount, currency, branch_id, source, source_id, reference,
                )
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
                JournalLineCreate(account_id=debit_acc.id, debit=egp_amount, credit=Decimal("0"),
                                   cost_center_id=cost_center_id),
                JournalLineCreate(account_id=credit_acc.id, debit=Decimal("0"), credit=egp_amount,
                                   cost_center_id=cost_center_id),
            ],
        )
        return crud.create_journal_entry(db, entry_data, created_by)
    except FinancialConfigurationError:
        raise
    except Exception:
        if strict:
            raise
        logger.exception(
            "post_simple_revenue_journal: unexpected failure for branch=%s source=%s "
            "source_id=%s reference=%s — journal entry NOT posted",
            branch_id, source, source_id, reference,
        )
        return None


def _build_taxed_sale_entry(
    db: Session,
    branch_id: int,
    entry_date: date,
    *,
    debit_account_code: str,
    revenue_account_code: str,
    net_revenue_amount: Decimal,
    vat_amount: Decimal,
    service_charge_amount: Decimal,
    reference: str,
    description: str,
    source: str,
    source_id: Optional[int],
    created_by: int,
    cost_center_code: Optional[str],
    tax_profile_version: Optional[str],
    commit_cost_centers: bool,
    reverse: bool,
) -> JournalEntry:
    """المنطق المشترك بين post_taxed_sale_journal وreverse_taxed_sale_journal
    — نفس الحسابات والقيود بالظبط، الفرق الوحيد أي جانب (مدين/دائن) ياخد كل
    سطر. راجع docstring الدالتين العامتين فوق للعقد الكامل."""
    validate_period_open(db, branch_id, entry_date)

    gross_amount = (net_revenue_amount + vat_amount + service_charge_amount).quantize(Decimal("0.01"))
    if gross_amount <= 0:
        raise ValueError("إجمالي القيد المحاسبي غير صالح (صفر أو سالب)")
    if net_revenue_amount < 0 or vat_amount < 0 or service_charge_amount < 0:
        raise ValueError("مكوّنات القيد (الإيراد/الضريبة/الخدمة) لا يجوز أن تكون سالبة")

    existing = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.branch_id == branch_id,
            JournalEntry.source == source,
            JournalEntry.source_id == source_id,
            JournalEntry.reference == reference,
        )
        .first()
    )
    if existing:
        logger.info(
            "_build_taxed_sale_entry: entry already posted for source=%s source_id=%s "
            "reference=%s — returning existing entry %s (idempotent no-op)",
            source, source_id, reference, existing.id,
        )
        return existing

    debit_acc = crud.get_account_by_code(db, branch_id, debit_account_code)
    revenue_acc = crud.get_account_by_code(db, branch_id, revenue_account_code)
    if not debit_acc:
        raise FinancialConfigurationError(f"حساب محاسبي غير معرّف للفرع: {debit_account_code}")
    if not revenue_acc:
        raise FinancialConfigurationError(f"حساب محاسبي غير معرّف للفرع: {revenue_account_code}")

    vat_acc = None
    if vat_amount > 0:
        vat_acc = crud.get_account_by_code(db, branch_id, "2160")
        if not vat_acc:
            raise FinancialConfigurationError("حساب محاسبي غير معرّف للفرع: 2160")

    service_acc = None
    if service_charge_amount > 0:
        service_acc = crud.get_account_by_code(db, branch_id, "2165")
        if not service_acc:
            raise FinancialConfigurationError("حساب محاسبي غير معرّف للفرع: 2165")

    cost_center_id = None
    if cost_center_code:
        cc = crud.get_cost_center_by_code(db, branch_id, cost_center_code)
        if not cc:
            ensure_default_cost_centers(db, branch_id, commit=commit_cost_centers)
            cc = crud.get_cost_center_by_code(db, branch_id, cost_center_code)
        if not cc:
            raise FinancialConfigurationError(f"تعذّر تجهيز مركز التكلفة: {cost_center_code}")
        cost_center_id = cc.id

    full_description = description
    if tax_profile_version:
        full_description = f"{description} [tax_profile={tax_profile_version}]"

    zero = Decimal("0")

    def _line(account_id: int, amount: Decimal) -> JournalLineCreate:
        # reverse=False (بيع عادي): المدين = debit_account، الدائن = الباقي.
        # reverse=True (إلغاء/مرتجع): نفس السطور بالظبط بس معكوسة — الإيراد/
        # الضريبة/الخدمة بيبقوا مدين (بيقللوا رصيدهم) وdebit_account بيبقى
        # دائن (بيرجع الكاش/يقلل الذمة) — مش قيد جديد بإجمالي gross كأنه
        # إيراد جديد، ده بالظبط الباج اللي §11.2 بتطلب تجنبه.
        is_debit_side = (account_id == debit_acc.id) != reverse
        return JournalLineCreate(
            account_id=account_id,
            debit=amount if is_debit_side else zero,
            credit=zero if is_debit_side else amount,
            cost_center_id=cost_center_id,
        )

    lines = [
        _line(debit_acc.id, gross_amount),
        _line(revenue_acc.id, net_revenue_amount),
    ]
    if vat_amount > 0:
        lines.append(_line(vat_acc.id, vat_amount))
    if service_charge_amount > 0:
        lines.append(_line(service_acc.id, service_charge_amount))

    total_debit = sum((ln.debit for ln in lines), zero)
    total_credit = sum((ln.credit for ln in lines), zero)
    if abs(total_debit - total_credit) > Decimal("0.01"):
        raise ValueError(f"القيد غير متوازن: مدين={total_debit}, دائن={total_credit}")

    entry_data = JournalEntryCreate(
        branch_id=branch_id, entry_date=entry_date, reference=reference,
        description=full_description, source=source, source_id=source_id,
        lines=lines,
    )
    return crud.create_journal_entry(db, entry_data, created_by)


def post_taxed_sale_journal(
    db: Session,
    branch_id: int,
    entry_date: date,
    *,
    debit_account_code: str,
    revenue_account_code: str,
    net_revenue_amount: Decimal,
    vat_amount: Decimal = Decimal("0"),
    service_charge_amount: Decimal = Decimal("0"),
    reference: str,
    description: str,
    source: str,
    source_id: Optional[int],
    created_by: int = 0,
    cost_center_code: Optional[str] = None,
    tax_profile_version: Optional[str] = None,
    commit_cost_centers: bool = True,
) -> JournalEntry:
    """OPS-DATA-02 §11.2 (FIN-TAX-01) — يرحّل بيع خاضع للضريبة/الخدمة بفصل
    حقيقي عن الإيراد، بدل ما dining/beach.services يرحّلوا الإجمالي كله
    (أساسي + VAT + خدمة) على حساب الإيراد زي ما كانوا بيعملوا (باج حقيقي:
    الربح وVAT payable كانوا غلط لأي بيع فيه ضريبة/رسم خدمة).

    ```
    Dr <debit_account_code>              = net_revenue_amount + vat + service
        Cr <revenue_account_code>            = net_revenue_amount   (بعد الخصم)
        Cr 2160 ضريبة القيمة المضافة مستحقة  = vat_amount    (لو > 0)
        Cr 2165 رسم خدمة مستحق                = service_charge_amount (لو > 0)
    ```

    على عكس post_simple_revenue_journal القديمة: **دايمًا strict** — لا
    ابتلاع صامت لأي فشل (حساب غير معرّف، فترة مقفولة، مبلغ غير صالح)، كلها
    بترفع استثناء حقيقي يوقف العملية المالية اللي استدعتها. لازم يحترم قفل
    الفترة المحاسبية (post_simple_revenue_journal القديمة كانت بتتخطى الفحص
    ده عمدًا — هنا لأ). مفيش commit داخلي — المسؤولية على المستدعي، زي
    الأصل.

    idempotency: لو قيد بنفس (branch_id, source, source_id, reference)
    موجود بالفعل، بيرجّعه من غير ما ينشئ نسخة تانية (إعادة محاولة آمنة بعد
    فشل شبكة/timeout، مش خطأ). مفيش unique constraint على مستوى الداتابيز
    لسه على الحقول دي (يشمل كل نقاط الترحيل القديمة، تغيير أوسع من نطاق
    هذه الدفعة) — الفحص هنا شبكة أمان تطبيقية إضافية فوق الحماية التشغيلية
    الموجودة بالفعل في كل مسار استدعاء (حالة الطلب/الدفعة نفسها بتمنع
    استدعاء التسوية مرتين أصلاً)، مش الخط الدفاعي الوحيد.

    tax_profile_version: يتحفظ كنص داخل description للتدقيق (مفيش عمود
    مخصص على JournalEntry — إضافة عمود جديد قرار migration أوسع من نطاق
    هذه الدفعة). يدعم splits حسب outlet/cost-center عن طريق استدعاء الدالة
    دي مرة لكل outlet (زي ما dining.services بتعمل بالفعل مع
    post_simple_revenue_journal اليوم) — كل استدعاء قيد متوازن مستقل بحد
    ذاته، لا حاجة لتعقيد إضافي هنا.
    """
    return _build_taxed_sale_entry(
        db, branch_id, entry_date,
        debit_account_code=debit_account_code, revenue_account_code=revenue_account_code,
        net_revenue_amount=net_revenue_amount, vat_amount=vat_amount,
        service_charge_amount=service_charge_amount, reference=reference,
        description=description, source=source, source_id=source_id,
        created_by=created_by, cost_center_code=cost_center_code,
        tax_profile_version=tax_profile_version, commit_cost_centers=commit_cost_centers,
        reverse=False,
    )


def reverse_taxed_sale_journal(
    db: Session,
    branch_id: int,
    entry_date: date,
    *,
    debit_account_code: str,
    revenue_account_code: str,
    net_revenue_amount: Decimal,
    vat_amount: Decimal = Decimal("0"),
    service_charge_amount: Decimal = Decimal("0"),
    reference: str,
    description: str,
    source: str,
    source_id: Optional[int],
    created_by: int = 0,
    cost_center_code: Optional[str] = None,
    tax_profile_version: Optional[str] = None,
    commit_cost_centers: bool = True,
) -> JournalEntry:
    """عكس post_taxed_sale_journal بالضبط — لvoid/refund. نفس الحجج بالظبط
    (net_revenue_amount/vat_amount/service_charge_amount هي نفس قيم القيد
    الأصلي اللي بيتعكس، مش قيمة سالبة)، لكن كل سطر بياخد الجانب المعاكس:

    ```
        Dr <revenue_account_code>            = net_revenue_amount
        Dr 2160 ضريبة القيمة المضافة مستحقة  = vat_amount    (لو > 0)
        Dr 2165 رسم خدمة مستحق                = service_charge_amount (لو > 0)
    Cr <debit_account_code>              = net_revenue_amount + vat + service
    ```

    ده بالظبط الفرق اللي §11.2 بتطلبه: الإلغاء/المرتجع يعكس نفس سطور
    القيد الأصلي ونسبتها، مش قيد جديد بـ Dr Revenue بإجمالي gross كأنه
    "مصروف عكسي" غير مفصّل — VAT/service payable لازم يترد بالضبط زي ما
    اتسجّل، وإلا فضل رصيدهم فيه أثر بيع اتلغى فعليًا."""
    return _build_taxed_sale_entry(
        db, branch_id, entry_date,
        debit_account_code=debit_account_code, revenue_account_code=revenue_account_code,
        net_revenue_amount=net_revenue_amount, vat_amount=vat_amount,
        service_charge_amount=service_charge_amount, reference=reference,
        description=description, source=source, source_id=source_id,
        created_by=created_by, cost_center_code=cost_center_code,
        tax_profile_version=tax_profile_version, commit_cost_centers=commit_cost_centers,
        reverse=True,
    )


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


def close_accounting_year(db: Session, branch_id: int, year: int, closed_by: int) -> AccountingYearClose:
    """إقفال سنة محاسبية (2026-08-19، طلب Mohamed صراحةً) — يترحّل قيد
    إقفال حقيقي يصفّر كل حسابات الإيرادات/المصروفات في 3200 (أرباح
    مرحّلة)، بعد التأكد إن الاتناشر شهر كلهم مقفولين الأول. عملية لمرة
    واحدة بس لكل (فرع، سنة) — مفيش "إعادة فتح سنة" في النطاق الحالي.

    بيستخدم crud.create_journal_entry مباشرة (مش post_journal_entry) —
    نفس سبب settle_custody بالظبط: القيد نفسه لازم يترحّل بتاريخ آخر يوم
    في السنة (31 ديسمبر)، وهو تاريخ جوه شهر لازم يكون *مقفول بالفعل*
    كشرط مسبق — لو استخدمنا post_journal_entry (بينادي validate_period_
    open داخليًا) كان هيرفض القيد على أساس إن الفترة مقفولة، بينما إقفال
    الفترة دي هو بالظبط سبب وجود القيد ده."""
    if crud.get_year_close(db, branch_id, year):
        raise ValueError(f"السنة المحاسبية {year} مقفولة بالفعل")

    closed_months = crud.count_closed_months(db, branch_id, year)
    if closed_months < 12:
        raise ValueError(
            f"لازم تقفل كل شهور سنة {year} الاتناشر الأول قبل إقفال السنة "
            f"(مقفول حاليًا {closed_months}/12)"
        )

    retained_earnings_account = crud.get_account_by_code(db, branch_id, "3200")
    if not retained_earnings_account:
        raise FinancialConfigurationError("حساب الأرباح المحتجزة (3200) غير معرَّف لهذا الفرع")

    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    accounts, _total = crud.list_accounts(db, branch_id, active_only=False, limit=1000)
    sums = crud.sum_journal_lines_by_account(db, branch_id, year_start, year_end)

    lines: list[JournalLineCreate] = []
    total_revenue = Decimal("0")
    total_expense = Decimal("0")
    for acc in accounts:
        debit_sum, credit_sum = sums.get(acc.id, (Decimal("0"), Decimal("0")))
        if acc.account_type == "revenue":
            balance = credit_sum - debit_sum
            if balance != 0:
                lines.append(JournalLineCreate(
                    account_id=acc.id, debit=balance, credit=Decimal("0"),
                    description=f"إقفال سنة {year}",
                ))
                total_revenue += balance
        elif acc.account_type == "expense":
            balance = debit_sum - credit_sum
            if balance != 0:
                lines.append(JournalLineCreate(
                    account_id=acc.id, debit=Decimal("0"), credit=balance,
                    description=f"إقفال سنة {year}",
                ))
                total_expense += balance

    if not lines:
        raise ValueError(f"لا يوجد نشاط مالي (إيرادات/مصروفات) لسنة {year} — لا يوجد ما يُقفل")

    net_income = total_revenue - total_expense
    if net_income > 0:
        lines.append(JournalLineCreate(
            account_id=retained_earnings_account.id, debit=Decimal("0"), credit=net_income,
            description=f"صافي ربح سنة {year}",
        ))
    elif net_income < 0:
        lines.append(JournalLineCreate(
            account_id=retained_earnings_account.id, debit=abs(net_income), credit=Decimal("0"),
            description=f"صافي خسارة سنة {year}",
        ))

    total_debit = sum((ln.debit for ln in lines), Decimal("0"))
    total_credit = sum((ln.credit for ln in lines), Decimal("0"))
    if abs(total_debit - total_credit) > Decimal("0.01"):
        raise ValueError(f"قيد الإقفال غير متوازن: مدين={total_debit}, دائن={total_credit}")

    entry_data = JournalEntryCreate(
        branch_id=branch_id, entry_date=year_end,
        reference=f"YEAR-CLOSE-{year}", description=f"قيد إقفال سنة {year}",
        source="year_close", source_id=None, lines=lines,
    )

    try:
        entry = crud.create_journal_entry(db, entry_data, closed_by)
        year_close = crud.create_year_close(db, branch_id, year, entry.id, net_income, closed_by)
        db.commit()
        db.refresh(year_close)
        return year_close
    except Exception:
        db.rollback()
        raise


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
    today = local_today(settings.TIMEZONE)
    count = db.query(ETAInvoice).filter(
        ETAInvoice.internal_id.like(f"ETA-{today:%Y%m%d}-%"),
    ).count()
    internal_id = f"ETA-{today:%Y%m%d}-{count + 1:04d}"

    from app.modules.core.services import get_effective_vat_percentage  # noqa: PLC0415

    try:
        eta = ETAService(settings)
        document = eta.build_invoice_document(
            internal_id=internal_id,
            issued_at_iso=datetime.utcnow().isoformat() + "Z",
            receiver_name=data.receiver_name,
            receiver_rin=data.receiver_rin,
            default_vat_rate=get_effective_vat_percentage(db, data.branch_id),
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
                    rate=rate, effective_date=local_today(settings.TIMEZONE),
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
    {"code": "TS",    "name": "الملكية الجزئية"},
    # OPS-DATA-02 §11.1
    {"code": "LEASE", "name": "الإيجارات"},
    {"code": "MAINT", "name": "الصيانة"},
    {"code": "ADMIN", "name": "الإدارة"},
]


def ensure_default_cost_centers(db: Session, branch_id: int, *, commit: bool = True) -> list[CostCenter]:
    """يزرع مراكز التكلفة الافتراضية أول مرة بس — idempotent زي seed.py.

    commit=False (Gate 1B، مسارات strict الصارمة زي دفع طلبات الدايننج):
    الزرع بيحصل بـflush بس، من غير commit مستقل — عشان مسار الدفع الصارم
    يفضل بـcommit واحد بس لكل الـtransaction، بدل ما تجهيز مركز تكلفة
    ناقص يعمل commit نص-الطريق قبل ما باقي القيد يترحّل. commit=True
    (الافتراضي) هو نفس السلوك القديم تمامًا لكل الاستدعاءات الحالية."""
    existing_codes = {c.code for c in crud.list_cost_centers(db, branch_id, active_only=False)}
    created_any = False
    for defn in DEFAULT_COST_CENTERS:
        if defn["code"] not in existing_codes:
            crud.create_cost_center(db, CostCenterCreate(branch_id=branch_id, **defn))
            created_any = True
    if created_any:
        if commit:
            db.commit()
        else:
            db.flush()
    return crud.list_cost_centers(db, branch_id, active_only=False)


def get_cost_center_report(db: Session, branch_id: int, date_from: date, date_to: date) -> CostCenterReport:
    """تقرير مركز التكلفة (الفندق/المطعم/الكافيه/الشاطئ/الملكية الجزئية) — إيراد
    *ومصروف* كل واحد سطر منفصل، الاتنين من journal_lines.cost_center_id
    مباشرة (Batch 3) — مش استنتاج بعدي من جداول عمليات منفصلة (folio_charges/
    beach_transactions) زي قبل كده. الوسم بيحصل وقت الترحيل نفسه (راجع
    post_simple_revenue_journal's cost_center_code وكل نقاط الترحيل في
    dining/beach/pms/timeshare/inventory.services).

    ⚠️ قيود قديمة اتُرحّلت قبل هذه الدفعة مالهاش cost_center_id (NULL) —
    مفيش backfill رجعي هنا (قرار نطاق موثّق في CostCenterReport docstring)،
    فتقرير على مدى قبل تاريخ الدفعة دي هيورّي أرقام أقل من الحقيقة الفعلية
    حتى تتراكم قيود جديدة موسومة."""
    centers = ensure_default_cost_centers(db, branch_id)
    sums = crud.sum_journal_lines_by_cost_center(db, branch_id, date_from, date_to)

    lines = [
        CostCenterReportLine(
            code=c.code, name=c.name,
            revenue=sums.get(c.id, {}).get("revenue", Decimal("0")),
            expense=sums.get(c.id, {}).get("expense", Decimal("0")),
            net=sums.get(c.id, {}).get("revenue", Decimal("0")) - sums.get(c.id, {}).get("expense", Decimal("0")),
        )
        for c in centers
    ]
    total_revenue = sum((ln.revenue for ln in lines), Decimal("0"))
    total_expense = sum((ln.expense for ln in lines), Decimal("0"))

    return CostCenterReport(
        branch_id=branch_id, date_from=date_from, date_to=date_to,
        lines=lines, total_revenue=total_revenue, total_expense=total_expense,
        total_net=total_revenue - total_expense,
    )


# ── Financial Reports ────────────────────────────────────────────────
# ملاحظة محاسبية: بما إن post_journal_entry() بيرفض أي قيد غير متزن (debit
# != credit)، فإجمالي المدين = إجمالي الدائن على مستوى دفتر اليومية كله
# بالضرورة — وده اللي بيخلي trial balance وbalance sheet بيوازنوا تلقائياً
# من غير ما نحتاج قيد "إقفال" فعلي لنقل الأرباح لحساب حقوق ملكية.

def get_account_ledger(
    db: Session, branch_id: int, account_id: int, date_from: date, date_to: date,
) -> AccountLedgerReport:
    """كشف حساب (2026-08-19، طلب Mohamed) — كل حركات حساب واحد خلال مدى
    تاريخي، برصيد متحرّك. بدون pagination عمدًا (راجع crud.list_account_
    ledger_lines) — لازم الرصيد المتحرّك يتحسب على التسلسل الكامل، والمدى
    التاريخي بطبيعته بيحصر حجم البيانات (شهر/فترة، مش كل تاريخ الحساب)."""
    account = crud.get_account(db, account_id)
    if not account or account.branch_id != branch_id:
        raise ValueError(f"الحساب {account_id} غير موجود في هذا الفرع")
    if date_from > date_to:
        raise ValueError("تاريخ البداية لازم يكون قبل تاريخ النهاية")

    debit_normal = account.account_type in ("asset", "expense")

    opening_debit, opening_credit = crud.sum_account_before_date(db, account_id, date_from)
    opening_balance = (opening_debit - opening_credit) if debit_normal else (opening_credit - opening_debit)

    rows = crud.list_account_ledger_lines(db, account_id, date_from, date_to)

    lines: list[AccountLedgerLine] = []
    running = opening_balance
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for line, entry in rows:
        delta = (line.debit - line.credit) if debit_normal else (line.credit - line.debit)
        running += delta
        total_debit += line.debit
        total_credit += line.credit
        lines.append(AccountLedgerLine(
            entry_id=entry.id, entry_date=entry.entry_date,
            reference=entry.reference, description=line.description or entry.description,
            debit=line.debit, credit=line.credit, running_balance=running,
        ))

    return AccountLedgerReport(
        account_id=account.id, account_code=account.code, account_name=account.name,
        account_type=account.account_type, date_from=date_from, date_to=date_to,
        opening_balance=opening_balance, closing_balance=running,
        total_debit=total_debit, total_credit=total_credit, lines=lines,
    )


_AGING_BUCKETS = (
    ("0-30", 0, 30),
    ("31-60", 31, 60),
    ("61-90", 61, 90),
    ("90+", 91, None),
)


def _aging_bucket_label(days: int) -> str:
    for label, lo, hi in _AGING_BUCKETS:
        if days >= lo and (hi is None or days <= hi):
            return label
    return "90+"


def get_aging_report(db: Session, branch_id: int, as_of: Optional[date] = None) -> AgingReport:
    """تقرير أعمار الديون (2026-08-19، طلب Mohamed) — مين مديون لنا (فوليوهات
    مفتوحة برصيد مستحق، عمرها من check_in) ومين إحنا مديونين له (أوامر شراء
    + مصروفات آجلة لسه من غير سداد كامل، عمرها من تاريخ الأمر/المصروف).
    مفيش منطق مالي جديد هنا — بس تجميع وترتيب بيانات موجودة أصلاً."""
    if as_of is None:
        as_of = date.today()

    receivables: list[ReceivableAgingLine] = []
    receivables_total = Decimal("0")
    for folio in crud.list_open_folios_for_aging(db, branch_id):
        paid = sum((p.amount for p in folio.payments if p.voided_at is None), Decimal("0"))
        balance_due = folio.total - paid
        if balance_due <= Decimal("0.01"):
            continue
        days = (as_of - folio.check_in.date()).days
        receivables_total += balance_due
        receivables.append(ReceivableAgingLine(
            folio_id=folio.id, guest_name=folio.guest_name, check_in=folio.check_in.date(),
            days_outstanding=days, balance_due=balance_due, bucket=_aging_bucket_label(days),
        ))

    payables: list[PayableAgingLine] = []
    payables_total = Decimal("0")

    from app.modules.inventory import crud as inventory_crud  # noqa: PLC0415
    for po in inventory_crud.list_unpaid_purchase_orders_for_aging(db, branch_id):
        remaining = po.total_amount - po.amount_paid
        if remaining <= Decimal("0.01"):
            continue
        days = (as_of - po.ordered_at).days
        payables_total += remaining
        payables.append(PayableAgingLine(
            source_type="purchase_order", source_id=po.id, reference=po.order_number,
            counterparty=po.supplier.name if po.supplier else (po.supplier_name or "—"),
            due_date=po.ordered_at, days_outstanding=days, remaining=remaining,
            bucket=_aging_bucket_label(days),
        ))

    for exp in crud.list_unpaid_expenses_for_aging(db, branch_id):
        remaining = exp.amount - exp.amount_paid
        if remaining <= Decimal("0.01"):
            continue
        days = (as_of - exp.expense_date).days
        payables_total += remaining
        payables.append(PayableAgingLine(
            source_type="expense", source_id=exp.id, reference=exp.reference or f"EXP-{exp.id}",
            counterparty=exp.description, due_date=exp.expense_date,
            days_outstanding=days, remaining=remaining, bucket=_aging_bucket_label(days),
        ))

    def _bucketize(lines, amount_attr) -> list[AgingBucket]:
        result = []
        for label, _lo, _hi in _AGING_BUCKETS:
            matching = [l for l in lines if l.bucket == label]
            result.append(AgingBucket(
                label=label, count=len(matching),
                amount=sum((getattr(l, amount_attr) for l in matching), Decimal("0")),
            ))
        return result

    return AgingReport(
        branch_id=branch_id, as_of=as_of,
        receivables=receivables, receivables_total=receivables_total,
        receivables_buckets=_bucketize(receivables, "balance_due"),
        payables=payables, payables_total=payables_total,
        payables_buckets=_bucketize(payables, "remaining"),
    )


def get_trial_balance(
    db: Session, branch_id: int, as_of: date, group_by_parent: bool = False,
) -> TrialBalanceReport:
    """ميزان المراجعة — كل حساب له نشاط حتى تاريخ as_of، برصيده الختامي في
    عمود المدين أو الدائن حسب طبيعته. إجمالي المدين لازم يساوي إجمالي الدائن.

    group_by_parent=True (Batch 3): بدل سطر لكل حساب فردي، كل سطر بيمثّل
    حساب أب (Account.parent_id — راجع seed.py's PARENT_HEADERS، 1-2 مستوى
    بس) برصيده المجمّع من كل حساباته الفرعية. حساب من غير أب (نادر، أي
    حساب مستقبلي يتضاف من غير ما يتحدد له parent_id) بيتعامل معاه كأب
    لنفسه — عشان ميختفيش من التقرير المجمّع بصمت."""
    accounts, _ = crud.list_accounts(db, branch_id, active_only=False, limit=1000)
    sums = crud.sum_journal_lines_by_account(db, branch_id, None, as_of)

    if not group_by_parent:
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

    # ── وضع التجميع بالحساب الأب ──────────────────────────────────────
    accounts_by_id = {a.id: a for a in accounts}
    parent_net: dict[int, Decimal] = {}
    parent_account: dict[int, "Account"] = {}
    for acc in accounts:
        debit_sum, credit_sum = sums.get(acc.id, (Decimal("0"), Decimal("0")))
        if debit_sum == 0 and credit_sum == 0:
            continue
        parent = accounts_by_id.get(acc.parent_id) if acc.parent_id else None
        parent_id = parent.id if parent else acc.id  # حساب من غير أب = أب لنفسه
        parent_account.setdefault(parent_id, parent or acc)
        parent_net[parent_id] = parent_net.get(parent_id, Decimal("0")) + (debit_sum - credit_sum)

    lines = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for parent_id, net in parent_net.items():
        header = parent_account[parent_id]
        if net >= 0:
            debit_display, credit_display = net, Decimal("0")
        else:
            debit_display, credit_display = Decimal("0"), -net
        total_debit += debit_display
        total_credit += credit_display
        lines.append(TrialBalanceLine(
            account_code=header.code, account_name=header.name, account_type=header.account_type,
            debit=debit_display, credit=credit_display,
        ))
    lines.sort(key=lambda ln: ln.account_code)

    return TrialBalanceReport(
        branch_id=branch_id, as_of=as_of, lines=lines,
        total_debit=total_debit, total_credit=total_credit,
        is_balanced=abs(total_debit - total_credit) <= Decimal("0.01"),
        grouped_by_parent=True,
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


# ── تصدير التقارير المالية الرئيسية PDF/Excel (2026-08-19، طلب Mohamed) ──
# ميزان المراجعة/قائمة الدخل/الميزانية العمومية كانت شاشة/JSON بس، مفيش
# ملف قابل للتنزيل يتسلّم لمحاسب خارجي أو بنك. نفس نمط generate_folios_
# report_excel فوق بالظبط — بيعيد استخدام get_trial_balance/get_income_
# statement/get_balance_sheet المحسوبة أصلاً، صفر منطق مالي جديد هنا.

def generate_trial_balance_pdf(
    db: Session, branch_id: int, as_of: date, group_by_parent: bool = False,
) -> bytes:
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    report = get_trial_balance(db, branch_id, as_of, group_by_parent)
    headers = ["الكود", "الحساب", "النوع", "مدين", "دائن"]
    rows = [
        [l.account_code, l.account_name, l.account_type,
         f"{l.debit:,.2f}" if l.debit else "—", f"{l.credit:,.2f}" if l.credit else "—"]
        for l in report.lines
    ]
    summary = [
        ("إجمالي المدين", f"{report.total_debit:,.2f} EGP"),
        ("إجمالي الدائن", f"{report.total_credit:,.2f} EGP"),
        ("متوازن؟", "نعم ✓" if report.is_balanced else "لا ✗"),
    ]
    return builder.table_pdf(
        title="ميزان المراجعة", subtitle=f"حتى تاريخ {as_of:%Y-%m-%d}",
        headers=headers, rows=rows, summary=summary,
    )


def generate_trial_balance_excel(
    db: Session, branch_id: int, as_of: date, group_by_parent: bool = False,
) -> bytes:
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    report = get_trial_balance(db, branch_id, as_of, group_by_parent)
    rows = [[l.account_code, l.account_name, l.account_type, float(l.debit), float(l.credit)] for l in report.lines]
    return builder.excel(
        sheets=[{
            "name": "ميزان المراجعة",
            "headers": ["الكود", "الحساب", "النوع", "مدين", "دائن"],
            "rows": rows,
            "col_types": ["text", "text", "text", "currency", "currency"],
            "summary": {
                "إجمالي المدين": float(report.total_debit),
                "إجمالي الدائن": float(report.total_credit),
            },
        }],
        title=f"ميزان المراجعة حتى {as_of:%Y-%m-%d}",
    )


def generate_income_statement_pdf(db: Session, branch_id: int, date_from: date, date_to: date) -> bytes:
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    report = get_income_statement(db, branch_id, date_from, date_to)
    headers = ["الكود", "الحساب", "المبلغ"]
    rows = [["", "— الإيرادات —", ""]]
    rows += [[l.account_code, l.account_name, f"{l.amount:,.2f}"] for l in report.revenue_lines]
    rows += [["", "— المصروفات —", ""]]
    rows += [[l.account_code, l.account_name, f"{l.amount:,.2f}"] for l in report.expense_lines]
    summary = [
        ("إجمالي الإيرادات", f"{report.total_revenue:,.2f} EGP"),
        ("إجمالي المصروفات", f"{report.total_expense:,.2f} EGP"),
        ("صافي الربح/الخسارة", f"{report.net_income:,.2f} EGP"),
    ]
    return builder.table_pdf(
        title="قائمة الدخل", subtitle=f"من {date_from:%Y-%m-%d} إلى {date_to:%Y-%m-%d}",
        headers=headers, rows=rows, summary=summary,
    )


def generate_income_statement_excel(db: Session, branch_id: int, date_from: date, date_to: date) -> bytes:
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    report = get_income_statement(db, branch_id, date_from, date_to)
    rev_rows = [[l.account_code, l.account_name, float(l.amount)] for l in report.revenue_lines]
    exp_rows = [[l.account_code, l.account_name, float(l.amount)] for l in report.expense_lines]
    return builder.excel(
        sheets=[
            {
                "name": "الإيرادات",
                "headers": ["الكود", "الحساب", "المبلغ"],
                "rows": rev_rows, "col_types": ["text", "text", "currency"],
                "summary": {"إجمالي الإيرادات": float(report.total_revenue)},
            },
            {
                "name": "المصروفات",
                "headers": ["الكود", "الحساب", "المبلغ"],
                "rows": exp_rows, "col_types": ["text", "text", "currency"],
                "summary": {
                    "إجمالي المصروفات": float(report.total_expense),
                    "صافي الربح/الخسارة": float(report.net_income),
                },
            },
        ],
        title=f"قائمة الدخل {date_from:%Y-%m-%d} — {date_to:%Y-%m-%d}",
    )


def generate_balance_sheet_pdf(db: Session, branch_id: int, as_of: date) -> bytes:
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    report = get_balance_sheet(db, branch_id, as_of)
    headers = ["الكود", "الحساب", "المبلغ"]
    rows = [["", "— الأصول —", ""]]
    rows += [[l.account_code, l.account_name, f"{l.amount:,.2f}"] for l in report.asset_lines]
    rows += [["", "— الخصوم —", ""]]
    rows += [[l.account_code, l.account_name, f"{l.amount:,.2f}"] for l in report.liability_lines]
    rows += [["", "— حقوق الملكية —", ""]]
    rows += [[l.account_code, l.account_name, f"{l.amount:,.2f}"] for l in report.equity_lines]
    summary = [
        ("إجمالي الأصول", f"{report.total_assets:,.2f} EGP"),
        ("إجمالي الخصوم", f"{report.total_liabilities:,.2f} EGP"),
        ("إجمالي حقوق الملكية", f"{report.total_equity:,.2f} EGP"),
        ("الأرباح المحتجزة", f"{report.retained_earnings:,.2f} EGP"),
        ("متوازنة؟", "نعم ✓" if report.is_balanced else "لا ✗"),
    ]
    return builder.table_pdf(
        title="الميزانية العمومية", subtitle=f"حتى تاريخ {as_of:%Y-%m-%d}",
        headers=headers, rows=rows, summary=summary,
    )


def generate_balance_sheet_excel(db: Session, branch_id: int, as_of: date) -> bytes:
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    report = get_balance_sheet(db, branch_id, as_of)
    asset_rows = [[l.account_code, l.account_name, float(l.amount)] for l in report.asset_lines]
    liability_rows = [[l.account_code, l.account_name, float(l.amount)] for l in report.liability_lines]
    equity_rows = [[l.account_code, l.account_name, float(l.amount)] for l in report.equity_lines]
    return builder.excel(
        sheets=[
            {
                "name": "الأصول", "headers": ["الكود", "الحساب", "المبلغ"],
                "rows": asset_rows, "col_types": ["text", "text", "currency"],
                "summary": {"إجمالي الأصول": float(report.total_assets)},
            },
            {
                "name": "الخصوم", "headers": ["الكود", "الحساب", "المبلغ"],
                "rows": liability_rows, "col_types": ["text", "text", "currency"],
                "summary": {"إجمالي الخصوم": float(report.total_liabilities)},
            },
            {
                "name": "حقوق الملكية", "headers": ["الكود", "الحساب", "المبلغ"],
                "rows": equity_rows, "col_types": ["text", "text", "currency"],
                "summary": {
                    "إجمالي حقوق الملكية": float(report.total_equity),
                    "الأرباح المحتجزة": float(report.retained_earnings),
                },
            },
        ],
        title=f"الميزانية العمومية حتى {as_of:%Y-%m-%d}",
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
        candidates = crud.find_matching_payment_candidates(
            db, account.branch_id, line.amount, line.line_date, bank_account_id=account.id,
        )
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


# ── Payment Channels ─────────────────────────────────────────────────────
#
# قناة تحصيل = وجهة GL حقيقية يختارها الكاشير (صندوق/Visa CIB/Vodafone
# Cash...). التصميم بالكامل مبني على قاعدتين لا يجوز كسرهما:
#   1. لا حذف أبدًا — تعطيل فقط (is_active=False)، عشان أي بيع/قيد تاريخي
#      يفضل يقدر يرجع لنفس القناة اللي استُخدمت وقته.
#   2. أي بيع بيسجّل *لقطة* (snapshot) من القناة وقت الحركة (id/code/name +
#      حساب GL) — مش مرجع حي بيتغيّر لو القناة اتعدّلت بعد كده. المرتجع/الـ
#      void لازم يستخدم اللقطة المحفوظة وقت البيع، مش إعداد القناة الحالي.

def get_payment_channel_or_404(db: Session, channel_id: int):
    channel = crud.get_payment_channel(db, channel_id)
    if not channel:
        raise ValueError(f"قناة التحصيل {channel_id} غير موجودة")
    return channel


def _validate_payment_channel_accounts(
    db: Session, branch_id: int, gl_account_id: int,
    bank_account_id: Optional[int], method: str,
) -> None:
    gl = crud.get_account(db, gl_account_id)
    if not gl or gl.branch_id != branch_id:
        raise ValueError(f"حساب GL {gl_account_id} غير موجود في هذا الفرع")
    if not gl.is_active:
        raise ValueError(f"حساب GL «{gl.name}» غير نشط")
    if gl.account_type != "asset":
        raise ValueError(f"حساب GL «{gl.name}» يجب أن يكون من نوع أصل (Asset) ليصلح لتحصيل قناة دفع")

    if bank_account_id is None:
        return
    if method == "cash":
        raise ValueError("قناة تحصيل نقدية (cash) لا يمكن ربطها بحساب بنكي")
    bank = crud.get_bank_account(db, bank_account_id)
    if not bank or bank.branch_id != branch_id:
        raise ValueError(f"الحساب البنكي {bank_account_id} غير موجود في هذا الفرع")
    if not bank.is_active:
        raise ValueError(f"الحساب البنكي «{bank.account_name}» غير نشط")


def list_payment_channels(
    db: Session, branch_id: int, active_only: bool = False, method: Optional[str] = None,
):
    return crud.list_payment_channels(db, branch_id, active_only, method)


def create_payment_channel(db: Session, data: PaymentChannelCreate):
    _validate_payment_channel_accounts(db, data.branch_id, data.gl_account_id, data.bank_account_id, data.method)
    if crud.get_payment_channel_by_code(db, data.branch_id, data.code):
        raise ValueError(f"كود القناة «{data.code}» مستخدم بالفعل في هذا الفرع")
    channel = crud.create_payment_channel(db, data)
    db.commit()
    return crud.get_payment_channel(db, channel.id)


def update_payment_channel(db: Session, channel_id: int, data: PaymentChannelUpdate):
    channel = get_payment_channel_or_404(db, channel_id)
    gl_account_id = data.gl_account_id if data.gl_account_id is not None else channel.gl_account_id
    if data.clear_bank_account:
        bank_account_id = None
    elif data.bank_account_id is not None:
        bank_account_id = data.bank_account_id
    else:
        bank_account_id = channel.bank_account_id
    _validate_payment_channel_accounts(db, channel.branch_id, gl_account_id, bank_account_id, channel.method)
    channel = crud.update_payment_channel(db, channel, data)
    db.commit()
    return crud.get_payment_channel(db, channel.id)


def resolve_payment_channel(
    db: Session, branch_id: int, method: str, channel_id: Optional[int] = None,
):
    """يحل القناة الفعلية المستخدمة لحركة بيع (Beach/Dining).

    - ``channel_id`` محدد صراحةً → لازم يكون نشط، لنفس الفرع، ولنفس
      ``method``، وإلا يترفض بوضوح.
    - غير محدد وفيه قنوات مُعرَّفة لهذا الفرع/الطريقة → يستخدم الـdefault
      النشط؛ عدم وجود default صالح خطأ صريح (مايترحّلش لحساب عشوائي).
    - غير محدد ومفيش أي قناة مُعرَّفة خالص لهذا الفرع/الطريقة → ``None``
      (توافق مؤقت مع الفروع/البيئات اللي لسه معملتش channels — المسار
      القديم القائم على متغيرات البيئة يفضل شغّال زي ما هو).
    """
    if channel_id is not None:
        channel = crud.get_payment_channel(db, channel_id)
        if not channel or channel.branch_id != branch_id:
            raise ValueError(f"قناة التحصيل {channel_id} غير موجودة في هذا الفرع")
        if not channel.is_active:
            raise ValueError(f"قناة التحصيل «{channel.name}» معطّلة، اختر قناة نشطة")
        if channel.method != method:
            raise ValueError(f"قناة التحصيل «{channel.name}» لا تدعم طريقة الدفع «{method}»")
        return channel

    existing = crud.list_payment_channels(db, branch_id, method=method)
    if not existing:
        return None

    default = crud.get_default_payment_channel(db, branch_id, method)
    if not default:
        raise ValueError(
            f"لا توجد قناة تحصيل افتراضية صالحة لطريقة الدفع «{method}» في هذا الفرع — "
            "اختر قناة يدويًا أو اضبط قناة افتراضية من إدارة قنوات التحصيل",
        )
    return default


def payment_channel_snapshot(channel) -> dict:
    """لقطة تُخزَّن على الحركة نفسها (Payment/BeachTransaction) — مش مرجع
    حي. ``channel=None`` (مسار legacy بلا قنوات مُعرَّفة) يرجّع لقطة فاضية،
    والمرتجع/الـvoid وقتها بيفضل يستخدم حساب البيئة القديم زي ما هو."""
    if channel is None:
        return {
            "payment_channel_id": None,
            "payment_channel_code": None,
            "payment_channel_name": None,
            "settlement_account_code": None,
        }
    return {
        "payment_channel_id": channel.id,
        "payment_channel_code": channel.code,
        "payment_channel_name": channel.name,
        "settlement_account_code": channel.gl_account.code,
    }
