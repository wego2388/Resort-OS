"""
app/modules/finance/_services/shifts.py
Extracted from app/modules/finance/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.finance import crud
from app.modules.finance.models import CashierShift, Payment
from app.modules.finance.schemas import (
    ActiveShiftSummary,
    ActiveShiftsResponse,
    CashCountLineRead,
    CashierShiftClose,
    CashierShiftOpen,
    CashMovementCreate,
    ForeignCurrencySummary,
    ShiftCategorySummary,
    ShiftChannelSummary,
    ShiftEndReport,
    ShiftInvoiceItemLine,
    ShiftInvoiceLine,
)
from app.modules.finance._services.exchange_rates import (
    ensure_default_exchange_rates,
    get_rate,
)


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
        target_branch_id=shift.branch_id,
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

    from app.modules.dining.services import get_shift_category_summary  # noqa: PLC0415
    category_summary = [ShiftCategorySummary(**row) for row in get_shift_category_summary(db, shift_id)]

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
        category_summary=category_summary,
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

    # 2026-09-05 — طلب Mohamed: الفاتورة المطبوعة عند قفل الوردية تفصّل
    # إيه اللي اتباع فعليًا (ساندوتش/بيتزا/مشروبات)، مش أرقام مالية بس.
    if r.category_summary:
        summary.append(("— أصناف المبيعات حسب الفئة —", ""))
        for cat in r.category_summary:
            summary.append((f"{cat.name_ar} ({cat.quantity} قطعة)", f"{cat.revenue:,.2f} EGP"))

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
            min_approver_level=60, target_branch_id=shift.branch_id,
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
    *, bypass_ownership_check: bool = False,
) -> list[ShiftInvoiceLine]:
    """سجل فواتير الوردية (InvoiceLogModal، wagdy.md بند S-02) — كل دفعة
    حقيقية مربوطة بالوردية عبر Payment.shift_id، مع اسم ضيف كل فاتورة.

    قيدين محكومين هنا (مش endpoint عرض عام):
    1. كاشير (level < مدير) يقدر يشوف وردية نفسه بس — أي وردية غيره PermissionError.
    2. حتى وردية نفسه، لازم موافقة PIN من مدير+ (أو يكون هو نفسه مدير+) —
       بيانات مالية تفصيلية حسّاسة (راجع core.services.resolve_pin_approval
       وwagdy.md بند S-03: PinGuardModal هي البوابة على الفرونت إند لده).

    bypass_ownership_check (2026-09-05): للمالك (owner role، level=10 عمدًا —
    راجع deps.ROLE_LEVELS) القيدين فوق مالهمش معنى أصلًا: مش كاشير أصلًا
    يطلب موافقة مدير، وget_owner_reader نفسه (owner أو super_admin بس) هو
    البوابة الوحيدة الكافية. افتراضي False — صفر تغيير سلوك لأي استدعاء حالي."""
    shift = crud.get_shift(db, shift_id)
    if not shift:
        raise ValueError(f"الوردية {shift_id} غير موجودة")

    if not bypass_ownership_check:
        from app.core.deps import user_level  # noqa: PLC0415
        from app.modules.core import policy_engine  # noqa: PLC0415

        acting_level = user_level(requesting_user)
        if acting_level < 60 and shift.cashier_id != requesting_user.id:
            raise PermissionError("لا يمكنك عرض فواتير وردية غيرك")

        policy_engine.require_approval(
            db, "view_other_cashier_shift_invoices",
            acting_user_level=acting_level,
            approver_user_id=approver_user_id, approver_pin=approver_pin,
            target_branch_id=shift.branch_id,
        )

    payments = crud.list_shift_payments_with_folio(db, shift_id)

    # 2026-09-05 — طلب Mohamed: كل فاتورة تعرض الأصناف الحقيقية اللي فيها،
    # مش رقم/اسم بس. مبني على ref_order_id — موجود لتسويات دايننج المباشرة
    # بس (مش شاطئ/فوليو مستقل)، فأي فاتورة تانية items فاضية بأمان.
    from app.modules.dining.services import get_shift_sold_items  # noqa: PLC0415
    items_by_order = {o.order_id: o.items for o in get_shift_sold_items(db, shift_id)}

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
            items=[
                ShiftInvoiceItemLine(
                    item_id=i.item_id, name=i.name, name_ar=i.name_ar,
                    category_name=i.category_name, category_name_ar=i.category_name_ar,
                    quantity=i.quantity, revenue=i.revenue,
                )
                for i in items_by_order.get(p.ref_order_id, [])
            ] if p.ref_order_id else [],
        )
        for p in payments
    ]


# ── Discount ──────────────────────────────────────────────────────────
