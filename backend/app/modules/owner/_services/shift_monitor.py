"""
app/modules/owner/_services/shift_monitor.py
Extracted from app/modules/owner/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from app.modules.owner.schemas import (
    CashMovementItem,
    ExceptionsResponse,
    OwnerExceptionItem,
    ShiftCategorySummaryLine,
    ShiftHistoryItem,
    ShiftHistoryResponse,
    ShiftMonitorItem,
    ShiftMonitorResponse,
)
from app.resort_os.owner_analytics_engine import (
    OwnerException,
    score_shift_variance,
    rank_exceptions,
    build_fraud_exceptions,
    build_shift_variance_exceptions,
)


# Phase 7 — Shift Monitoring
# ══════════════════════════════════════════════════════════════════════

def get_shift_monitor(db: Session, branch_id: int) -> ShiftMonitorResponse:
    """
    F-1 + F-2 + F-3: مراقبة الورديات — من يعمل الآن + cash movements.

    المالك يقرأ فقط — لا approve/close/dispute من هذه الواجهة.
    مصدر: finance.services.build_active_shifts_response + list_cash_movements.
    اسم الكاشير موجود فقط في سياق مراقبة الوردية (Decision 0004 §Isolation item 7).
    """
    from app.modules.finance.services import (  # noqa: PLC0415
        build_active_shifts_response,
        list_cash_movements,
    )
    from app.core.kernel.models.user import User  # noqa: PLC0415

    active_resp = build_active_shifts_response(db, branch_id)

    # نجلب أسماء performed_by لحركات الكاش — batch
    shift_items: list[ShiftMonitorItem] = []

    for s in active_resp.shifts:
        # حركات الكاش لهذه الوردية
        try:
            movements_raw = list_cash_movements(db, s.shift_id)
        except ValueError:
            movements_raw = []

        # نجلب أسماء performed_by بـ batch
        performer_ids = list({m.performed_by for m in movements_raw})
        performer_names: dict[int, str] = {}
        if performer_ids:
            users = db.query(User).filter(User.id.in_(performer_ids)).all()
            performer_names = {u.id: (u.full_name or f"#{u.id}") for u in users}

        cash_movements = [
            CashMovementItem(
                id=m.id,
                movement_type=m.movement_type,
                amount=m.amount,
                direction=getattr(m, "direction", None),
                reason=m.reason or "",
                performed_by_name=performer_names.get(m.performed_by, f"#{m.performed_by}"),
                created_at=m.created_at,
            )
            for m in movements_raw
        ]

        # تقييم الوردية — مفتوحة → variance=None → tier=normal
        variance_result = score_shift_variance(
            shift_id=s.shift_id,
            cashier_id=s.cashier_id,
            cashier_name=s.cashier_name,
            variance=None,   # open shift — no counted_cash yet
            is_closed=False,
        )

        from app.modules.dining.services import get_shift_category_summary  # noqa: PLC0415

        shift_items.append(ShiftMonitorItem(
            shift_id=s.shift_id,
            cashier_id=s.cashier_id,
            cashier_name=s.cashier_name,
            opened_at=s.opened_at,
            opening_float=s.opening_float,
            total_sales=s.total_sales,
            total_cash=s.total_cash,
            expected_cash=s.expected_cash,
            invoice_count=s.invoice_count,
            variance=None,
            is_closed=False,
            cash_movements=cash_movements,
            variance_tier=variance_result.tier,
            category_summary=[ShiftCategorySummaryLine(**row) for row in get_shift_category_summary(db, s.shift_id)],
        ))

    return ShiftMonitorResponse(
        branch_id=branch_id,
        open_count=len(shift_items),
        shifts=shift_items,
        computed_at=datetime.utcnow(),
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 7 — Exceptions Engine
# ══════════════════════════════════════════════════════════════════════

def get_exceptions(db: Session, branch_id: int) -> ExceptionsResponse:
    """
    G-1 + G-2: قائمة استثناءات مرتّبة بالخطورة.

    مصادر:
    1. fraud_tasks.find_fraud_signals → critical tier
    2. shift variance (مغلقة) → critical/attention
    3. expense variance flags (من get_expense_analytics) → attention
    4. B2B overdue → attention
    5. Supplier concentration → watch
    6. Long open shifts (>12h) → watch

    الاستثناءات الفعلية (realized) تأتي من بيانات حقيقية.
    لا تكرار لمنطق fraud_tasks — نستدعيه مباشرة.
    """
    from app.tasks.fraud_tasks import find_fraud_signals  # noqa: PLC0415
    from app.modules.finance.models import CashierShift   # noqa: PLC0415
    from app.modules.beach.models import B2BContract      # noqa: PLC0415
    from app.core.config import get_settings              # noqa: PLC0415
    from app.core.kernel.models.user import User          # noqa: PLC0415

    cfg = get_settings()
    exceptions: list[OwnerException] = []

    # ── 1. Fraud signals ────────────────────────────────────────────────
    try:
        fraud_signals = find_fraud_signals(
            db,
            now=datetime.utcnow(),
            refund_threshold=cfg.FRAUD_REFUND_COUNT_THRESHOLD,
            refund_window_minutes=cfg.FRAUD_REFUND_WINDOW_MINUTES,
            void_threshold=cfg.FRAUD_VOID_COUNT_THRESHOLD,
            void_window_minutes=cfg.FRAUD_VOID_WINDOW_MINUTES,
            discount_threshold=cfg.FRAUD_DISCOUNT_COUNT_THRESHOLD,
            discount_window_minutes=cfg.FRAUD_DISCOUNT_WINDOW_MINUTES,
            drawer_open_threshold=cfg.FRAUD_DRAWER_OPEN_COUNT_THRESHOLD,
            drawer_open_window_minutes=cfg.FRAUD_DRAWER_OPEN_WINDOW_MINUTES,
        )
        exceptions.extend(build_fraud_exceptions(fraud_signals))
    except Exception:
        pass  # لو فشل fetch الـ fraud signals — لا نوقف كل القائمة

    # ── 2. Shift variance (closed shifts — آخر 24 ساعة) ────────────────
    since_24h = datetime.utcnow() - timedelta(hours=24)
    closed_shifts = (
        db.query(CashierShift)
        .filter(
            CashierShift.branch_id == branch_id,
            CashierShift.status == "closed",
            CashierShift.closed_at >= since_24h,
            CashierShift.variance.isnot(None),
        )
        .all()
    )

    cashier_ids = [s.cashier_id for s in closed_shifts]
    cashier_names_map: dict[int, str] = {}
    if cashier_ids:
        users = db.query(User).filter(User.id.in_(cashier_ids)).all()
        cashier_names_map = {u.id: (u.full_name or f"#{u.id}") for u in users}

    variance_results = [
        score_shift_variance(
            shift_id=s.id,
            cashier_id=s.cashier_id,
            cashier_name=cashier_names_map.get(s.cashier_id, f"#{s.cashier_id}"),
            variance=s.variance,
            is_closed=True,
        )
        for s in closed_shifts
    ]
    exceptions.extend(build_shift_variance_exceptions(variance_results))

    # ── 3. B2B overdue contracts → attention ──────────────────────────
    overdue_contracts = (
        db.query(B2BContract)
        .filter(
            B2BContract.branch_id == branch_id,
            B2BContract.is_active.is_(True),
            B2BContract.is_overdue.is_(True),
        )
        .all()
    )
    for c in overdue_contracts:
        exceptions.append(OwnerException(
            exception_id=f"b2b_overdue:{c.id}",
            tier="attention",
            category="b2b_overdue",
            title=f"ذمة متأخرة — {c.hotel_name}",
            detail=f"عقد B2B متأخر السداد منذ {c.last_settled_at or 'غير محدد'}",
            entity_id=c.id,
            entity_name=c.hotel_name,
            impact=Decimal("0"),
            confidence=Decimal("1.0"),
            status="realized",
            source="b2b_contracts",
        ))

    # ── 4. Long open shifts (> 12 ساعة) → watch ────────────────────────
    cutoff_12h = datetime.utcnow() - timedelta(hours=12)
    long_shifts = (
        db.query(CashierShift)
        .filter(
            CashierShift.branch_id == branch_id,
            CashierShift.status == "open",
            CashierShift.opened_at <= cutoff_12h,
        )
        .all()
    )
    for s in long_shifts:
        name = cashier_names_map.get(s.cashier_id)
        if not name:
            user = db.query(User).filter(User.id == s.cashier_id).first()
            name = (user.full_name if user else None) or f"#{s.cashier_id}"
        hours_open = int((datetime.utcnow() - s.opened_at).total_seconds() // 3600)
        exceptions.append(OwnerException(
            exception_id=f"long_shift:{s.id}",
            tier="watch",
            category="long_open_shift",
            title=f"وردية مفتوحة {hours_open} ساعة — {name}",
            detail=f"الوردية مفتوحة منذ {s.opened_at.strftime('%H:%M')} — لم تُغلق بعد",
            entity_id=s.cashier_id,
            entity_name=name,
            impact=Decimal("0"),
            confidence=Decimal("1.0"),
            status="realized",
            source="cashier_shifts",
        ))

    ranked = rank_exceptions(exceptions)

    return ExceptionsResponse(
        critical_count=sum(1 for e in ranked if e.tier == "critical"),
        attention_count=sum(1 for e in ranked if e.tier == "attention"),
        watch_count=sum(1 for e in ranked if e.tier == "watch"),
        exceptions=[
            OwnerExceptionItem(
                exception_id=e.exception_id,
                tier=e.tier,
                category=e.category,
                title=e.title,
                detail=e.detail,
                entity_id=e.entity_id,
                entity_name=e.entity_name,
                impact=e.impact,
                confidence=e.confidence,
                status=e.status,
                source=e.source,
                score=e.score,
            )
            for e in ranked
        ],
        computed_at=datetime.utcnow(),
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 7b — Shift History
# ══════════════════════════════════════════════════════════════════════

def get_shift_history(db: Session, branch_id: int, days: int = 7) -> ShiftHistoryResponse:
    """
    الورديات المغلقة خلال آخر N أيام — للمراجعة التاريخية.
    مصدر: CashierShift (status='closed') + CashMovement.
    المالك يقرأ فقط — لا actions.
    """
    from app.modules.finance.models import CashierShift, CashMovement, Payment  # noqa: PLC0415
    from app.core.kernel.models.user import User  # noqa: PLC0415

    cutoff = datetime.utcnow() - timedelta(days=max(1, min(days, 30)))

    raw_shifts = (
        db.query(CashierShift)
        .filter(
            CashierShift.branch_id == branch_id,
            CashierShift.status == "closed",
            CashierShift.closed_at >= cutoff,
        )
        .order_by(CashierShift.closed_at.desc())
        .all()
    )

    # جلب أسماء الكاشيرين دفعة واحدة
    cashier_ids = list({s.cashier_id for s in raw_shifts})
    cashier_names: dict[int, str] = {}
    if cashier_ids:
        rows = db.query(User.id, User.full_name).filter(User.id.in_(cashier_ids)).all()
        cashier_names = {r.id: r.full_name for r in rows}

    shift_ids = [s.id for s in raw_shifts]
    movements_map: dict[int, list[CashMovement]] = {sid: [] for sid in shift_ids}
    if shift_ids:
        mvs = (
            db.query(CashMovement)
            .filter(CashMovement.shift_id.in_(shift_ids))
            .order_by(CashMovement.created_at)
            .all()
        )
        # أسماء المنفذين
        performer_ids = list({m.performed_by for m in mvs})
        performer_names: dict[int, str] = {}
        if performer_ids:
            rows2 = db.query(User.id, User.full_name).filter(User.id.in_(performer_ids)).all()
            performer_names = {r.id: r.full_name for r in rows2}
        for mv in mvs:
            movements_map[mv.shift_id].append(mv)
    else:
        performer_names = {}

    # 2026-09-05 — باج حقيقي اتكشف: total_sales/invoice_count كانوا بيتحسبوا
    # غلط للورديات المغلقة (شيلهم تحت). المصدر الصح هو Payment.shift_id
    # نفسه المستخدم في build_active_shifts_response للورديات المفتوحة —
    # مُجمَّع دفعة واحدة لكل الورديات هنا (مش N+1) بنفس نمط cash_movements فوق.
    sales_map: dict[int, tuple["Decimal", int]] = {sid: (Decimal("0"), 0) for sid in shift_ids}
    if shift_ids:
        payments = (
            db.query(Payment)
            .filter(Payment.shift_id.in_(shift_ids), Payment.voided_at.is_(None))
            .all()
        )
        totals: dict[int, Decimal] = {sid: Decimal("0") for sid in shift_ids}
        counts: dict[int, int] = {sid: 0 for sid in shift_ids}
        for p in payments:
            if p.amount > 0:
                totals[p.shift_id] += p.amount
                counts[p.shift_id] += 1
        sales_map = {sid: (totals[sid], counts[sid]) for sid in shift_ids}

    result_shifts: list[ShiftHistoryItem] = []
    for shift in raw_shifts:
        mvs_list = movements_map.get(shift.id, [])
        variance = shift.variance
        if variance is not None:
            from app.resort_os.owner_analytics_engine import score_shift_variance  # noqa: PLC0415
            # باج حقيقي حي اتكشف (2026-08-11، فحص جودة نهائي): الدالة بتاخد
            # 5 args إجباري (shift_id/cashier_id/cashier_name/variance/
            # is_closed)، مش variance بس — /owner/shifts/history كان بيرمي
            # 500 مضمون في أي وردية مغلقة عندها variance (يعني أي بيانات
            # تاريخية حقيقية). كل ورديات الاستعلام هنا closed بالتعريف
            # (فلتر status=='closed' فوق) → is_closed=True دايمًا هنا.
            svr = score_shift_variance(
                shift_id=shift.id,
                cashier_id=shift.cashier_id,
                cashier_name=cashier_names.get(shift.cashier_id, f"كاشير {shift.cashier_id}"),
                variance=variance,
                is_closed=True,
            )
            variance_tier = svr.tier
        else:
            variance_tier = "normal"

        from app.modules.dining.services import get_shift_category_summary  # noqa: PLC0415

        shift_total_sales, shift_invoice_count = sales_map.get(shift.id, (Decimal("0"), 0))
        result_shifts.append(ShiftHistoryItem(
            shift_id=shift.id,
            cashier_id=shift.cashier_id,
            cashier_name=cashier_names.get(shift.cashier_id, f"كاشير {shift.cashier_id}"),
            opened_at=shift.opened_at,
            closed_at=shift.closed_at,
            opening_float=shift.opening_float or Decimal("0"),
            total_sales=shift_total_sales,
            total_cash=shift.counted_cash or Decimal("0"),
            expected_cash=shift.expected_cash or Decimal("0"),
            invoice_count=shift_invoice_count,
            category_summary=[ShiftCategorySummaryLine(**row) for row in get_shift_category_summary(db, shift.id)],
            variance=variance,
            variance_tier=variance_tier,
            cash_movements=[
                CashMovementItem(
                    id=mv.id,
                    movement_type=mv.movement_type,
                    amount=mv.amount,
                    direction=mv.direction,
                    reason=mv.reason,
                    performed_by_name=performer_names.get(mv.performed_by, f"مستخدم {mv.performed_by}"),
                    created_at=mv.created_at,
                )
                for mv in mvs_list
            ],
        ))

    return ShiftHistoryResponse(
        branch_id=branch_id,
        days=days,
        shifts=result_shifts,
        computed_at=datetime.utcnow(),
    )


def get_shift_invoices(db: Session, shift_id: int, branch_id: int):
    """2026-09-05 — طلب Mohamed: تفصيل حقيقي لكل فاتورة في وردية معيّنة
    (مش بس ملخص فئات) — نفس بيانات شاشة "سجل الفواتير" في FinanceView
    (المحاسب)، بس من غير قيد ownership/موافقة PIN لأن get_owner_reader
    (owner أو super_admin بس) هو البوابة الكافية هنا — راجع
    finance.services.list_shift_invoices's bypass_ownership_check.

    branch_id هنا مش تحسين اختياري — bypass_ownership_check يشيل قيد
    "كاشير يشوف وردية نفسه بس" بالكامل، فمن غيره أي owner (أو super_admin)
    يقدر يجيب فواتير أي وردية في أي فرع بمجرد تخمين shift_id (نفس فئة باج
    C-01/H-01/SEC-06/SEC-07 المُصلَّحين قبل كده — راجع CLAUDE.md §18)."""
    from app.modules.finance import crud as finance_crud  # noqa: PLC0415
    from app.modules.finance import services as finance_services  # noqa: PLC0415

    shift = finance_crud.get_shift(db, shift_id)
    if not shift or shift.branch_id != branch_id:
        raise ValueError(f"الوردية {shift_id} غير موجودة")

    return finance_services.list_shift_invoices(
        db, shift_id, requesting_user=None, bypass_ownership_check=True,
    )


# ══════════════════════════════════════════════════════════════════════
