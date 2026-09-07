"""
app/modules/dining/_services/reports.py
Extracted from app/modules/dining/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.dining import crud
from app.modules.dining.models import DiningItem, DiningOrder, Outlet
from app.modules.dining.schemas import (
    CogsTrendPoint,
    FoodCostReportLine,
    FoodCostReportResponse,
    GrossMarginSummary,
)
from app.resort_os.food_cost_engine import DEFAULT_FOOD_COST_THRESHOLD_PCT, compute_food_cost_result, exceeds_threshold
from app.resort_os.timezone_utils import (
    local_date_to_utc_range,
    utc_naive_to_local_date,
)
from app.modules.dining._services._helpers import (
    _effective_recipe,
)


class ShiftSoldItemLine:
    __slots__ = ("item_id", "name", "name_ar", "category_name", "category_name_ar", "quantity", "revenue")

    def __init__(self, item_id, name, name_ar, category_name, category_name_ar, quantity, revenue):
        self.item_id = item_id
        self.name = name
        self.name_ar = name_ar
        self.category_name = category_name
        self.category_name_ar = category_name_ar
        self.quantity = quantity
        self.revenue = revenue


class ShiftOrderItems:
    __slots__ = ("order_id", "order_number", "outlet_name", "items")

    def __init__(self, order_id, order_number, outlet_name, items):
        self.order_id = order_id
        self.order_number = order_number
        self.outlet_name = outlet_name
        self.items = items


def get_shift_sold_items(db: Session, shift_id: int) -> list[ShiftOrderItems]:
    """كل الأصناف الحقيقية المباعة في وردية معيّنة، مجمّعة حسب الطلب. أصناف
    الطلب الملغاة/المرتجعة مستبعدة (status in cancelled|refunded) — الهدف
    هنا "إيه اللي بيعناه فعلاً" مش سجل تاريخي كامل لكل حركة."""
    from app.modules.dining.models import DiningCategory, DiningOrderItem, DiningSettlement  # noqa: PLC0415

    order_ids = [
        r[0] for r in
        db.query(DiningSettlement.order_id).filter(DiningSettlement.shift_id == shift_id).all()
    ]
    if not order_ids:
        return []

    orders = {
        o.id: o for o in db.query(DiningOrder).filter(DiningOrder.id.in_(order_ids)).all()
    }
    outlet_ids = {o.outlet_id for o in orders.values()}
    outlet_names = {
        out.id: (out.name_ar or out.name)
        for out in db.query(Outlet).filter(Outlet.id.in_(outlet_ids)).all()
    }

    rows = (
        db.query(DiningOrderItem, DiningCategory.name, DiningCategory.name_ar)
        .join(DiningItem, DiningItem.id == DiningOrderItem.item_id)
        .outerjoin(DiningCategory, DiningCategory.id == DiningItem.category_id)
        .filter(DiningOrderItem.order_id.in_(order_ids))
        .filter(DiningOrderItem.status.notin_(("cancelled", "refunded")))
        .all()
    )

    by_order: dict[int, list[ShiftSoldItemLine]] = defaultdict(list)
    for oi, cat_name, cat_name_ar in rows:
        unit = oi.listed_unit_price if oi.listed_unit_price is not None else oi.unit_price
        by_order[oi.order_id].append(ShiftSoldItemLine(
            item_id=oi.item_id, name=oi.name, name_ar=oi.name_ar,
            category_name=cat_name, category_name_ar=cat_name_ar,
            quantity=oi.quantity, revenue=(unit * oi.quantity).quantize(Decimal("0.01")),
        ))

    return [
        ShiftOrderItems(
            order_id=order_id,
            order_number=orders[order_id].order_number,
            outlet_name=outlet_names.get(orders[order_id].outlet_id, "—"),
            items=items,
        )
        for order_id, items in by_order.items()
        if order_id in orders
    ]


def get_shift_category_summary(db: Session, shift_id: int) -> list[dict]:
    """ملخص سريع مجمّع حسب الفئة لكارت الوردية (مطعم/كافيه/كل فئة على
    حدة) — نفس مصدر get_shift_sold_items، مجمّع بس. يرجّع list[{name, name_ar,
    quantity, revenue}] مرتبة الأعلى إيرادًا أولًا."""
    orders = get_shift_sold_items(db, shift_id)
    agg: dict[str, dict] = {}
    for order in orders:
        for item in order.items:
            key = item.category_name or "أخرى"
            bucket = agg.setdefault(key, {
                "name": item.category_name or "Other",
                "name_ar": item.category_name_ar or "أخرى",
                "quantity": 0,
                "revenue": Decimal("0"),
            })
            bucket["quantity"] += item.quantity
            bucket["revenue"] += item.revenue
    return sorted(agg.values(), key=lambda b: b["revenue"], reverse=True)


# ─────────────────────── Reporting / Food Cost ────────────────────────

def get_food_cost_report(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
    outlet_id: Optional[int] = None,
    threshold_pct: Decimal = DEFAULT_FOOD_COST_THRESHOLD_PCT,
) -> FoodCostReportResponse:
    """راجع restaurant.services.get_food_cost_report للتبرير الكامل — نفس
    منطق التجميع بمفتاح (item_id, variant_id) بالظبط. ``outlet_id`` اختياري
    (None = كل الـ outlets في الفرع مجمّعين معًا)."""
    range_start, _ = local_date_to_utc_range(date_from, settings.TIMEZONE)
    _, range_end = local_date_to_utc_range(date_to, settings.TIMEZONE)

    items = crud.list_items_for_food_cost(db, branch_id, outlet_id)
    sales_rows = crud.get_paid_order_items_for_food_cost(db, branch_id, range_start, range_end, outlet_id)

    ReportKey = tuple[int, Optional[int]]  # (item_id, variant_id)
    qty_by_key: dict[ReportKey, int] = defaultdict(int)
    revenue_by_key: dict[ReportKey, Decimal] = defaultdict(lambda: Decimal("0"))
    by_day: dict[date, dict[ReportKey, list]] = defaultdict(lambda: defaultdict(lambda: [0, Decimal("0")]))

    for item_id, variant_id, unit_price, quantity, created_at in sales_rows:
        key = (item_id, variant_id)
        line_revenue = unit_price * quantity
        qty_by_key[key] += quantity
        revenue_by_key[key] += line_revenue
        local_day = utc_naive_to_local_date(created_at, settings.TIMEZONE)
        day_entry = by_day[local_day][key]
        day_entry[0] += quantity
        day_entry[1] += line_revenue

    lines: list[FoodCostReportLine] = []
    unit_cost_by_key: dict[ReportKey, Decimal] = {}
    recipe_key_ids: set[ReportKey] = set()
    total_revenue = Decimal("0")
    total_theoretical_cost = Decimal("0")
    items_missing_recipe = 0
    items_missing_recipe_revenue = Decimal("0")

    for item in items:
        available_variants = [v for v in item.variants if v.is_available]
        report_units: list[tuple[Optional[int], str, list]] = (
            [(v.id, f"{item.name} - {v.name}", _effective_recipe(item, v)) for v in available_variants]
            if available_variants
            else [(None, item.name, item.recipe_lines)]
        )

        for variant_id, display_name, effective_recipe_lines in report_units:
            key = (item.id, variant_id)
            has_recipe = bool(effective_recipe_lines)
            recipe_lines = [
                ((line.product.cost_price if line.product else None) or Decimal("0"), line.quantity_per_unit)
                for line in effective_recipe_lines
            ]
            quantity_sold = qty_by_key.get(key, 0)
            revenue = revenue_by_key.get(key, Decimal("0"))
            result = compute_food_cost_result(recipe_lines, quantity_sold, revenue)
            unit_cost_by_key[key] = result.theoretical_unit_cost
            if has_recipe:
                recipe_key_ids.add(key)

            if quantity_sold > 0:
                if has_recipe:
                    total_revenue += revenue
                    total_theoretical_cost += result.theoretical_total_cost
                else:
                    items_missing_recipe += 1
                    items_missing_recipe_revenue += revenue

            lines.append(FoodCostReportLine(
                item_id=item.id,
                item_name=display_name,
                variant_id=variant_id,
                has_recipe=has_recipe,
                quantity_sold=quantity_sold,
                revenue=revenue,
                theoretical_unit_cost=result.theoretical_unit_cost,
                theoretical_total_cost=result.theoretical_total_cost,
                food_cost_pct=result.food_cost_pct if has_recipe else None,
                gross_margin_amount=result.gross_margin_amount,
                gross_margin_pct=result.gross_margin_pct if has_recipe else None,
                exceeds_threshold=has_recipe and exceeds_threshold(result.food_cost_pct, threshold_pct),
            ))

    trend: list[CogsTrendPoint] = []
    current = date_from
    while current <= date_to:
        day_revenue = Decimal("0")
        day_cost = Decimal("0")
        for key, (qty, item_revenue) in by_day.get(current, {}).items():
            if key in recipe_key_ids:
                day_revenue += item_revenue
                day_cost += unit_cost_by_key.get(key, Decimal("0")) * qty
        day_cost = day_cost.quantize(Decimal("0.01"))
        trend.append(CogsTrendPoint(
            date=current,
            revenue=day_revenue,
            theoretical_cost=day_cost,
            food_cost_pct=(day_cost / day_revenue * 100).quantize(Decimal("0.01")) if day_revenue > 0 else None,
        ))
        current += timedelta(days=1)

    summary_pct = (total_theoretical_cost / total_revenue * 100).quantize(Decimal("0.01")) if total_revenue > 0 else None
    summary_margin_pct = (
        ((total_revenue - total_theoretical_cost) / total_revenue * 100).quantize(Decimal("0.01"))
        if total_revenue > 0 else None
    )
    summary = GrossMarginSummary(
        branch_id=branch_id,
        outlet_id=outlet_id,
        date_from=date_from,
        date_to=date_to,
        threshold_pct=threshold_pct,
        total_revenue=total_revenue,
        total_theoretical_cost=total_theoretical_cost,
        food_cost_pct=summary_pct,
        gross_margin_amount=(total_revenue - total_theoretical_cost).quantize(Decimal("0.01")),
        gross_margin_pct=summary_margin_pct,
        items_missing_recipe=items_missing_recipe,
        items_missing_recipe_revenue=items_missing_recipe_revenue,
    )

    alerts = [line for line in lines if line.exceeds_threshold]
    return FoodCostReportResponse(lines=lines, alerts=alerts, trend=trend, summary=summary)


def generate_food_cost_excel(
    db: Session, branch_id: int, date_from: date, date_to: date,
    outlet_id: Optional[int] = None,
    threshold_pct: Decimal = DEFAULT_FOOD_COST_THRESHOLD_PCT,
) -> bytes:
    """راجع restaurant.services.generate_food_cost_excel — نفس المنطق بالظبط."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    report = get_food_cost_report(db, branch_id, date_from, date_to, outlet_id, threshold_pct)

    rows = [
        [
            line.item_name, "نعم" if line.has_recipe else "لا (تكلفة غير معروفة)",
            line.quantity_sold, line.revenue, line.theoretical_total_cost,
            line.food_cost_pct if line.food_cost_pct is not None else "—",
            line.gross_margin_amount, "نعم" if line.exceeds_threshold else "لا",
        ]
        for line in report.lines
    ]

    return builder.excel(
        sheets=[{
            "name": "تكلفة الطعام",
            "headers": ["الصنف", "وصفة مسجّلة؟", "الكمية المباعة", "الإيراد",
                        "التكلفة النظرية", "نسبة التكلفة %", "هامش الربح", "تخطّى الحد؟"],
            "rows": rows,
            "col_types": ["text", "text", "number", "currency", "currency", "text", "currency", "text"],
            "summary": {
                "إجمالي الإيراد": report.summary.total_revenue,
                "إجمالي التكلفة النظرية": report.summary.total_theoretical_cost,
                "هامش الربح الإجمالي": report.summary.gross_margin_amount,
                "أصناف بدون وصفة": report.summary.items_missing_recipe,
            },
        }],
        title=f"تقرير تكلفة الطعام (دايننج) — {date_from} إلى {date_to}",
    )


# ─────────────────────── Outlet ────────────────────────────────────────
