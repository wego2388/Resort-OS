"""
app/modules/owner/_services/sales_analytics.py
Extracted from app/modules/owner/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.modules.owner.schemas import (
    BeachPerformanceResponse,
    BeachTicketTypeRow,
    ChannelAnalyticsResponse,
    ChannelContractRow,
    ExpenseAnalyticsResponse,
    ExpenseLineResponse,
    ItemMetricResponse,
    PayrollSummary,
    PRPOVarianceRow,
    ProcurementAnalyticsResponse,
    RevenueBreakdownResponse,
    RevenueLineResponse,
    SalesPerformanceResponse,
    SupplierSpendRow,
)
from app.resort_os.owner_analytics_engine import (
    ItemMetric,
    ExpenseLine,
    SupplierSpend,
    PRPOVarianceLine,
    classify_abc,
    enrich_items_with_margin,
    detect_variance,
    score_supplier_concentration,
    compute_pr_po_variance,
)
from app.modules.owner._services._helpers import (
    _utc_date_bounds,
    _is_period_provisional,
    _safe_pct,
    _fetch_b2b_receivables,
)


# Phase 6 — Sales Performance (C-1, C-2)
# ══════════════════════════════════════════════════════════════════════

def get_sales_performance(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
    outlet: str = "dining",
    limit: int = 50,
) -> SalesPerformanceResponse:
    """
    أداء المبيعات: top items مرتّبة بالإيراد + ABC Pareto + هامش ربح.

    outlet: 'dining' | 'beach' | 'all' (dining + beach مدمجَين)
    مصدر dining: DiningOrderItem (paid orders فقط)
    مصدر beach: BeachTransaction (non-voided فقط)
    هامش الربح: من MenuItemRecipeLine + Product.cost_price (لو موجود)
    لا float — Decimal طول الوقت.
    """
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.dining.models import DiningOrder, DiningOrderItem  # noqa: PLC0415
    from app.modules.beach.models import BeachTransaction  # noqa: PLC0415

    range_start_utc, range_end_utc = _utc_date_bounds(date_from, date_to)
    items: list[ItemMetric] = []

    # ── Dining items ──────────────────────────────────────────────────
    if outlet in ("dining", "all"):
        rows = (
            db.query(
                DiningOrderItem.item_id.label("item_id"),
                DiningOrderItem.name.label("name"),
                sa_func.sum(DiningOrderItem.quantity).label("qty"),
                sa_func.sum(
                    DiningOrderItem.unit_price * DiningOrderItem.quantity
                ).label("revenue"),
            )
            .join(DiningOrder, DiningOrder.id == DiningOrderItem.order_id)
            .filter(
                DiningOrder.branch_id == branch_id,
                DiningOrder.status == "paid",
                DiningOrder.created_at >= range_start_utc,
                DiningOrder.created_at <= range_end_utc,
                DiningOrderItem.status != "cancelled",
            )
            .group_by(DiningOrderItem.item_id, DiningOrderItem.name)
            .order_by(sa_func.sum(
                DiningOrderItem.unit_price * DiningOrderItem.quantity
            ).desc())
            .all()
        )

        # نجلب recipe costs بـ batch query لتجنّب N+1
        item_ids = [r.item_id for r in rows if r.item_id is not None]
        recipe_costs: dict[int, Decimal] = {}
        if item_ids:
            recipe_costs = _fetch_recipe_costs(db, item_ids)

        for r in rows:
            items.append(ItemMetric(
                item_id=r.item_id or 0,
                name=r.name,
                quantity_sold=int(r.qty or 0),
                revenue=Decimal(str(r.revenue or 0)),
                recipe_cost=recipe_costs.get(r.item_id) if r.item_id else None,
            ))

    # ── Beach ticket types (كـ items) ────────────────────────────────
    if outlet in ("beach", "all"):
        beach_rows = (
            db.query(
                BeachTransaction.tx_type.label("tx_type"),
                sa_func.count(BeachTransaction.id).label("cnt"),
                sa_func.sum(BeachTransaction.total_amount).label("revenue"),
            )
            .filter(
                BeachTransaction.branch_id == branch_id,
                BeachTransaction.voided_at.is_(None),
                BeachTransaction.tx_date >= date_from,
                BeachTransaction.tx_date <= date_to,
            )
            .group_by(BeachTransaction.tx_type)
            .all()
        )
        for br in beach_rows:
            items.append(ItemMetric(
                item_id=0,
                name=f"شاطئ — {br.tx_type}",
                quantity_sold=int(br.cnt or 0),
                revenue=Decimal(str(br.revenue or 0)),
                recipe_cost=None,
            ))

    # ── ABC + Margin ───────────────────────────────────────────────────
    items = classify_abc(items)
    items = enrich_items_with_margin(items)

    total_revenue = sum(i.revenue for i in items)
    visible_items = items[:limit]
    is_prov = _is_period_provisional(db, branch_id, date_to)

    return SalesPerformanceResponse(
        period_from=date_from,
        period_to=date_to,
        outlet=outlet,
        items=[
            ItemMetricResponse(
                item_id=i.item_id,
                name=i.name,
                quantity_sold=i.quantity_sold,
                revenue=i.revenue,
                recipe_cost=i.recipe_cost,
                margin_pct=i.margin_pct,
                margin_amount=i.margin_amount,
                abc_class=i.abc_class,
                cumulative_pct=i.cumulative_pct,
            )
            for i in visible_items
        ],
        total_revenue=total_revenue,
        is_provisional=is_prov,
        computed_at=datetime.utcnow(),
    )


def _fetch_recipe_costs(db: Session, menu_item_ids: list[int]) -> dict[int, Decimal]:
    """Batch: يجلب تكلفة وصفة الوحدة لقائمة dining item_ids.

    التكلفة = SUM(Product.cost_price × DiningItemRecipeLine.quantity_per_unit)
    per item_id.
    """
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.dining.models import DiningItemRecipeLine  # noqa: PLC0415
    from app.modules.inventory.models import Product  # noqa: PLC0415

    if not menu_item_ids:
        return {}

    rows = (
        db.query(
            DiningItemRecipeLine.item_id,
            sa_func.sum(Product.cost_price * DiningItemRecipeLine.quantity_per_unit).label("unit_cost"),
        )
        .join(Product, Product.id == DiningItemRecipeLine.product_id)
        .filter(DiningItemRecipeLine.item_id.in_(menu_item_ids))
        .group_by(DiningItemRecipeLine.item_id)
        .all()
    )

    return {r.item_id: Decimal(str(r.unit_cost or 0)) for r in rows}


# ══════════════════════════════════════════════════════════════════════
# Phase 6 — Beach Performance by Ticket Type (C-3)
# ══════════════════════════════════════════════════════════════════════

def get_beach_performance(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
) -> BeachPerformanceResponse:
    """
    C-3: أداء الشاطئ مقسّم بنوع التذكرة.
    مصدر: BeachTransaction (non-voided, tx_date في المدى).
    """
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.beach.models import BeachTransaction  # noqa: PLC0415

    rows = (
        db.query(
            BeachTransaction.tx_type,
            sa_func.count(BeachTransaction.id).label("cnt"),
            sa_func.sum(BeachTransaction.total_amount).label("total"),
            sa_func.avg(BeachTransaction.unit_price).label("avg_price"),
        )
        .filter(
            BeachTransaction.branch_id == branch_id,
            BeachTransaction.voided_at.is_(None),
            BeachTransaction.tx_date >= date_from,
            BeachTransaction.tx_date <= date_to,
        )
        .group_by(BeachTransaction.tx_type)
        .order_by(sa_func.sum(BeachTransaction.total_amount).desc())
        .all()
    )

    ticket_types = [
        BeachTicketTypeRow(
            tx_type=r.tx_type,
            count=int(r.cnt or 0),
            total_amount=Decimal(str(r.total or 0)),
            avg_unit_price=Decimal(str(r.avg_price or 0)).quantize(Decimal("0.01")),
        )
        for r in rows
    ]

    total_revenue = sum(t.total_amount for t in ticket_types)
    total_count   = sum(t.count for t in ticket_types)

    return BeachPerformanceResponse(
        period_from=date_from,
        period_to=date_to,
        ticket_types=ticket_types,
        total_revenue=total_revenue,
        total_count=total_count,
        computed_at=datetime.utcnow(),
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 6 — Channel Analytics / B2B (C-4)
# ══════════════════════════════════════════════════════════════════════

def get_channel_analytics(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
) -> ChannelAnalyticsResponse:
    """
    C-4: أداء قنوات B2B — per hotel/contract.
    لا بيانات ضيف فردية (Decision 0004 §Isolation model item 7).

    البيانات:
    - B2BContractDay: check-ins وإيراد الشاطئ في الفترة
    - DiningOrder.b2b_contract_id: F&B attach (REL-10)
    - B2BContract: outstanding وoverdue (من _fetch_b2b_receivables)
    """
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.beach.models import B2BContract, B2BContractDay, B2BContractMonth  # noqa: PLC0415
    from app.modules.dining.models import DiningOrder  # noqa: PLC0415

    range_start_utc, range_end_utc = _utc_date_bounds(date_from, date_to)
    contracts = (
        db.query(B2BContract)
        .filter(B2BContract.branch_id == branch_id, B2BContract.is_active.is_(True))
        .all()
    )

    if not contracts:
        return ChannelAnalyticsResponse(
            period_from=date_from,
            period_to=date_to,
            contracts=[],
            total_checkins=0,
            total_beach_revenue=Decimal("0"),
            total_fnb_attach=Decimal("0"),
            computed_at=datetime.utcnow(),
        )

    contract_ids = [c.id for c in contracts]

    # Beach checkins في الفترة — عدّاد بحت (راجع models.B2BContractDay).
    checkin_rows = (
        db.query(
            B2BContractDay.contract_id,
            sa_func.sum(B2BContractDay.checked_in_count).label("checkins"),
        )
        .filter(
            B2BContractDay.contract_id.in_(contract_ids),
            B2BContractDay.day >= date_from,
            B2BContractDay.day <= date_to,
        )
        .group_by(B2BContractDay.contract_id)
        .all()
    )
    checkins_by_contract = {r.contract_id: int(r.checkins or 0) for r in checkin_rows}

    # Beach revenue في الفترة (2026-08-20: الرسم الشهري الثابت المُرحَّل —
    # راجع models.B2BContract/B2BContractMonth — مش مبلغ لكل تشيك-إن فردي.
    # بيتحسب حسب الشهر اللي اتُرحّل فيه (period_month)، مش تاريخ تشيك-إن
    # ضيف بعينه.
    revenue_rows = (
        db.query(
            B2BContractMonth.contract_id,
            sa_func.sum(B2BContractMonth.amount).label("beach_rev"),
        )
        .filter(
            B2BContractMonth.contract_id.in_(contract_ids),
            B2BContractMonth.period_month >= date_from,
            B2BContractMonth.period_month <= date_to,
        )
        .group_by(B2BContractMonth.contract_id)
        .all()
    )
    revenue_by_contract = {r.contract_id: Decimal(str(r.beach_rev or 0)) for r in revenue_rows}

    # F&B attach: مجموع dining orders بـ b2b_contract_id في الفترة
    fnb_rows = (
        db.query(
            DiningOrder.b2b_contract_id,
            sa_func.sum(DiningOrder.total).label("fnb_total"),
        )
        .filter(
            DiningOrder.b2b_contract_id.in_(contract_ids),
            DiningOrder.status == "paid",
            DiningOrder.created_at >= range_start_utc,
            DiningOrder.created_at <= range_end_utc,
        )
        .group_by(DiningOrder.b2b_contract_id)
        .all()
    )
    fnb_by_contract = {r.b2b_contract_id: Decimal(str(r.fnb_total or 0)) for r in fnb_rows}

    # Outstanding per contract (نفس منطق _fetch_b2b_receivables)
    b2b_items_map, _ = _fetch_b2b_receivables(db, branch_id)
    outstanding_map = {item.contract_id: item.outstanding for item in b2b_items_map}
    overdue_map     = {item.contract_id: item.is_overdue  for item in b2b_items_map}
    credit_map      = {item.contract_id: item.credit_limit for item in b2b_items_map}

    contract_rows = []
    for c in contracts:
        checkins    = checkins_by_contract.get(c.id, 0)
        beach_rev   = revenue_by_contract.get(c.id, Decimal("0"))
        fnb_attach  = fnb_by_contract.get(c.id, Decimal("0"))
        fnb_avg     = (fnb_attach / checkins).quantize(Decimal("0.01")) if checkins > 0 else Decimal("0")

        contract_rows.append(ChannelContractRow(
            contract_id=c.id,
            hotel_name=c.hotel_name,
            period_checkins=checkins,
            period_revenue=beach_rev,
            outstanding=outstanding_map.get(c.id, Decimal("0")),
            is_overdue=overdue_map.get(c.id, False),
            credit_limit=credit_map.get(c.id),
            fnb_attach=fnb_attach,
            fnb_avg_per_checkin=fnb_avg,
        ))

    # ترتيب: الأعلى إيراداً أولاً
    contract_rows.sort(key=lambda x: -x.period_revenue)

    return ChannelAnalyticsResponse(
        period_from=date_from,
        period_to=date_to,
        contracts=contract_rows,
        total_checkins=sum(r.period_checkins for r in contract_rows),
        total_beach_revenue=sum(r.period_revenue for r in contract_rows),
        total_fnb_attach=sum(r.fnb_attach for r in contract_rows),
        computed_at=datetime.utcnow(),
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 6 — Expense Analytics (D-1, D-2)
# ══════════════════════════════════════════════════════════════════════

def get_expense_analytics(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
) -> ExpenseAnalyticsResponse:
    """
    D-1 + D-2: كل فئة مصروف كنسبة % من الإيراد مع variance flags.

    الفترة المقارنة = نفس المدة الزمنية بالضبط في الشهر السابق.
    مصدر: finance.services.get_income_statement (نفس كل مقياس مالي آخر).
    رواتب: PayrollRun.total_net aggregate — لا per employee.
    """
    from app.modules.finance.services import get_income_statement  # noqa: PLC0415
    from app.modules.hr.models import PayrollRun  # noqa: PLC0415

    # فترة المقارنة: نفس المدة في الشهر الماضي
    delta = date_to - date_from
    prior_to   = date_from - timedelta(days=1)
    prior_from = prior_to - delta

    current_stmt = get_income_statement(db, branch_id, date_from, date_to)
    prior_stmt   = get_income_statement(db, branch_id, prior_from, prior_to)
    is_prov = _is_period_provisional(db, branch_id, date_to)

    # بناء expense lines من account breakdown
    current_by_code = {
        line.account_code: line
        for line in getattr(current_stmt, "expense_lines", [])
    }
    prior_by_code = {
        line.account_code: line
        for line in getattr(prior_stmt, "expense_lines", [])
    }

    all_codes = set(current_by_code) | set(prior_by_code)
    expense_lines_raw: list[ExpenseLine] = []
    for code in sorted(all_codes):
        cur  = current_by_code.get(code)
        prev = prior_by_code.get(code)
        expense_lines_raw.append(ExpenseLine(
            account_code=code,
            account_name=getattr(cur or prev, "account_name", code),
            current_amount=Decimal(str(getattr(cur,  "amount", 0) or 0)),
            prior_amount  =Decimal(str(getattr(prev, "amount", 0) or 0)),
            current_revenue=current_stmt.total_revenue,
            prior_revenue  =prior_stmt.total_revenue,
        ))

    enriched = detect_variance(expense_lines_raw)

    # رواتب الشهر الحالي (aggregate فقط)
    payroll_summary: Optional[PayrollSummary] = None
    payroll_run = (
        db.query(PayrollRun)
        .filter(
            PayrollRun.branch_id == branch_id,
            PayrollRun.period_year  == date_from.year,
            PayrollRun.period_month == date_from.month,
        )
        .first()
    )
    if payroll_run:
        payroll_pct = _safe_pct(payroll_run.total_net, current_stmt.total_revenue) \
                      if current_stmt.total_revenue > Decimal("0") else None
        payroll_summary = PayrollSummary(
            period_year=payroll_run.period_year,
            period_month=payroll_run.period_month,
            total_net=payroll_run.total_net,
            revenue=current_stmt.total_revenue,
            payroll_pct=payroll_pct,
            status=payroll_run.status,
        )

    return ExpenseAnalyticsResponse(
        period_from=date_from,
        period_to=date_to,
        prior_from=prior_from,
        prior_to=prior_to,
        current_revenue=current_stmt.total_revenue,
        prior_revenue=prior_stmt.total_revenue,
        expense_lines=[
            ExpenseLineResponse(
                account_code=el.account_code,
                account_name=el.account_name,
                current_amount=el.current_amount,
                prior_amount=el.prior_amount,
                current_pct=el.current_pct,
                prior_pct=el.prior_pct,
                variance_flag=el.variance_flag,
                variance_delta=el.variance_delta,
            )
            for el in enriched
        ],
        payroll=payroll_summary,
        is_provisional=is_prov,
        computed_at=datetime.utcnow(),
    )


def get_revenue_breakdown(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
) -> RevenueBreakdownResponse:
    """
    تفصيل الإيراد بالحساب لأي فترة (2026-08-17، طلب Mohamed الصريح بعد
    تجربة تطبيق المالك: الضغط على كارت إيراد اليوم لازم يوريه من أنهي
    حسابات جه الرقم ده).

    مصدر: finance.services.get_income_statement — نفس الدالة المستخدمة
    لكل رقم مالي أساسي تاني في التطبيق (Decision 0004 §Numbers must equal
    source). صفر حساب جديد هنا — مجرد تحويل شكل الاستجابة.
    """
    from app.modules.finance.services import get_income_statement  # noqa: PLC0415

    stmt = get_income_statement(db, branch_id, date_from, date_to)
    is_prov = _is_period_provisional(db, branch_id, date_to)

    revenue_lines = sorted(
        (
            RevenueLineResponse(
                account_code=line.account_code,
                account_name=line.account_name,
                amount=line.amount,
            )
            for line in stmt.revenue_lines
        ),
        key=lambda item: item.amount,
        reverse=True,
    )

    return RevenueBreakdownResponse(
        period_from=date_from,
        period_to=date_to,
        total_revenue=stmt.total_revenue,
        revenue_lines=revenue_lines,
        is_provisional=is_prov,
        computed_at=datetime.utcnow(),
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 6 — Procurement Analytics (E-1, E-2)
# ══════════════════════════════════════════════════════════════════════

def get_procurement_analytics(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
) -> ProcurementAnalyticsResponse:
    """
    E-1: تركّز الإنفاق بالموردين.
    E-2: فرق PR estimate vs PO actual (عبر source_request_id — Phase 2 fix).

    PurchaseOrder.status IN ('received','partial') — أوامر مستلمة فعلاً.
    لا float — Decimal طول الوقت.
    """
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.inventory.models import (  # noqa: PLC0415
        PurchaseOrder, PurchaseOrderItem,
        PurchaseRequest, PurchaseRequestItem,
        Supplier, Product,
    )

    # E-1: إنفاق بالمورد
    supplier_rows = (
        db.query(
            PurchaseOrder.supplier_id,
            sa_func.coalesce(Supplier.name, PurchaseOrder.supplier_name, "غير محدد").label("supplier_name"),
            sa_func.sum(PurchaseOrder.total_amount).label("total_spend"),
            sa_func.count(PurchaseOrder.id).label("order_count"),
        )
        .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .filter(
            PurchaseOrder.branch_id == branch_id,
            PurchaseOrder.status.in_(["received", "partial"]),
            PurchaseOrder.ordered_at >= date_from,
            PurchaseOrder.ordered_at <= date_to,
        )
        .group_by(PurchaseOrder.supplier_id, Supplier.name, PurchaseOrder.supplier_name)
        .all()
    )

    supplier_spends = [
        SupplierSpend(
            supplier_id=r.supplier_id or 0,
            supplier_name=r.supplier_name or "غير محدد",
            total_spend=Decimal(str(r.total_spend or 0)),
        )
        for r in supplier_rows
    ]
    supplier_spends = score_supplier_concentration(supplier_spends)
    order_counts = {r.supplier_id: int(r.order_count) for r in supplier_rows}
    total_spend = sum(s.total_spend for s in supplier_spends)

    # E-2: PR→PO variance عبر source_request_id
    variance_rows = (
        db.query(
            PurchaseOrderItem.product_id,
            Product.name.label("product_name"),
            sa_func.sum(PurchaseRequestItem.estimated_unit_cost).label("est_cost"),
            sa_func.sum(PurchaseOrderItem.unit_cost).label("act_cost"),
        )
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
        .join(PurchaseRequest, PurchaseRequest.id == PurchaseOrder.source_request_id)
        .join(
            PurchaseRequestItem,
            (PurchaseRequestItem.request_id == PurchaseRequest.id) &
            (PurchaseRequestItem.product_id == PurchaseOrderItem.product_id),
        )
        .join(Product, Product.id == PurchaseOrderItem.product_id)
        .filter(
            PurchaseOrder.branch_id == branch_id,
            PurchaseOrder.status.in_(["received", "partial"]),
            PurchaseOrder.ordered_at >= date_from,
            PurchaseOrder.ordered_at <= date_to,
            PurchaseOrder.source_request_id.isnot(None),
        )
        .group_by(PurchaseOrderItem.product_id, Product.name)
        .all()
    )

    variance_lines = [
        PRPOVarianceLine(
            product_id=r.product_id,
            product_name=r.product_name,
            estimated_cost=Decimal(str(r.est_cost or 0)),
            actual_cost=Decimal(str(r.act_cost or 0)),
            variance_amount=Decimal("0"),
            variance_pct=None,
        )
        for r in variance_rows
    ]
    variance_lines = compute_pr_po_variance(variance_lines)

    return ProcurementAnalyticsResponse(
        period_from=date_from,
        period_to=date_to,
        total_spend=total_spend,
        suppliers=[
            SupplierSpendRow(
                supplier_id=s.supplier_id,
                supplier_name=s.supplier_name,
                total_spend=s.total_spend,
                spend_pct=s.spend_pct,
                order_count=order_counts.get(s.supplier_id, 0),
                concentration_flag=s.concentration_flag,
            )
            for s in supplier_spends
        ],
        pr_po_variance=[
            PRPOVarianceRow(
                product_id=v.product_id,
                product_name=v.product_name,
                estimated_cost=v.estimated_cost,
                actual_cost=v.actual_cost,
                variance_amount=v.variance_amount,
                variance_pct=v.variance_pct,
            )
            for v in variance_lines
        ],
        computed_at=datetime.utcnow(),
    )
