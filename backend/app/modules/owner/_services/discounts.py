"""
app/modules/owner/_services/discounts.py
Extracted from app/modules/owner/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from app.modules.owner.schemas import (
    CustomerGroupDiscountRow,
    CustomerGroupMember,
    DiscountAnalyticsResponse,
    DiscountTypeRow,
    ManualDiscountPerCashier,
)


# Phase 7d — Discount Analytics
# Decision 0004 §7d: أنواع خصم + يدوي per cashier + مجموعات بالاسم.
# لا هاتف/email/national_id. لا عملاء بدون مجموعة.
# ══════════════════════════════════════════════════════════════════════

def get_discount_analytics(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
) -> DiscountAnalyticsResponse:
    """
    تحليل الخصومات: أنواع + يدوي per cashier + مجموعات بالاسم.
    مصدر: DiningOrder + CustomerGroup + Customer (الاسم فقط).
    """
    from sqlalchemy import func  # noqa: PLC0415
    from app.modules.dining.models import DiningOrder  # noqa: PLC0415
    from app.modules.crm.models import CustomerGroup, Customer  # noqa: PLC0415
    from app.core.kernel.models.user import User  # noqa: PLC0415

    # الطلبات المدفوعة في الفترة
    paid_orders = (
        db.query(DiningOrder)
        .filter(
            DiningOrder.branch_id == branch_id,
            DiningOrder.status == "paid",
            func.date(DiningOrder.created_at) >= date_from,
            func.date(DiningOrder.created_at) <= date_to,
        )
        .all()
    )

    total_revenue = sum(o.subtotal + o.vat_amount + o.service_charge - o.discount_amount
                        for o in paid_orders
                        if hasattr(o, 'subtotal'))
    if not total_revenue:
        # fallback: مجموع الطلبات المدفوعة بدون subtotal
        total_revenue = sum(getattr(o, 'total_amount', Decimal("0")) for o in paid_orders)

    total_discount = sum(o.discount_amount for o in paid_orders)

    # ── أنواع الخصم ──────────────────────────────────────────────────
    # نوع 1: conditional (applied_discount_rule_id != None وليس customer_group)
    # نوع 2: customer_group (discount من CustomerGroup)
    # نوع 3: manual (discount_amount > 0 بدون rule أو group)
    discount_types_data: dict[str, dict] = {
        "conditional":    {"label": "خصم شرطي",       "count": 0, "amount": Decimal("0")},
        "customer_group": {"label": "خصم مجموعة",     "count": 0, "amount": Decimal("0")},
        "manual":         {"label": "خصم يدوي",        "count": 0, "amount": Decimal("0")},
    }

    manual_per_cashier_map: dict[int, dict] = {}

    for order in paid_orders:
        disc = getattr(order, 'discount_amount', Decimal("0"))
        if disc <= 0:
            continue
        rule_id  = getattr(order, 'applied_discount_rule_id', None)
        cust_id  = getattr(order, 'customer_id', None)
        cashier_id = getattr(order, 'cashier_id', None)

        # تحديد نوع الخصم
        if rule_id:
            dtype = "conditional"
        elif cust_id:
            # نتحقق لو العميل ده في مجموعة
            cust = db.query(Customer.customer_group_id).filter(Customer.id == cust_id).first()
            dtype = "customer_group" if (cust and cust.customer_group_id) else "manual"
        else:
            dtype = "manual"

        discount_types_data[dtype]["count"] += 1
        discount_types_data[dtype]["amount"] += disc

        # manual per cashier
        if dtype == "manual" and cashier_id:
            if cashier_id not in manual_per_cashier_map:
                manual_per_cashier_map[cashier_id] = {"count": 0, "amount": Decimal("0")}
            manual_per_cashier_map[cashier_id]["count"] += 1
            manual_per_cashier_map[cashier_id]["amount"] += disc

    discount_pct = (total_discount / total_revenue * 100) if total_revenue > 0 else None

    discount_type_rows = [
        DiscountTypeRow(
            type=k,
            type_label=v["label"],
            order_count=v["count"],
            total_amount=v["amount"],
            pct_of_revenue=(v["amount"] / total_revenue * 100) if total_revenue > 0 else None,
        )
        for k, v in discount_types_data.items()
        if v["count"] > 0
    ]

    # cashier names
    cashier_ids = list(manual_per_cashier_map.keys())
    cashier_names: dict[int, str] = {}
    if cashier_ids:
        rows = db.query(User.id, User.full_name).filter(User.id.in_(cashier_ids)).all()
        cashier_names = {r.id: r.full_name for r in rows}

    manual_cashier_rows = sorted(
        [
            ManualDiscountPerCashier(
                cashier_id=cid,
                cashier_name=cashier_names.get(cid, f"كاشير {cid}"),
                order_count=v["count"],
                total_manual_discount=v["amount"],
            )
            for cid, v in manual_per_cashier_map.items()
        ],
        key=lambda x: x.total_manual_discount,
        reverse=True,
    )[:10]  # top 10 فقط

    # ── مجموعات العملاء بالاسم ───────────────────────────────────────
    # Decision 0004 §7d: الاسم فقط — لا هاتف/email/national_id
    # لا عملاء بدون مجموعة
    groups = (
        db.query(CustomerGroup)
        .filter(
            CustomerGroup.branch_id == branch_id,
            CustomerGroup.is_active == True,
        )
        .all()
    )

    # العملاء الذين لهم طلبات في الفترة
    customer_ids_with_orders = {
        getattr(o, 'customer_id', None)
        for o in paid_orders
        if getattr(o, 'customer_id', None)
    }

    group_rows: list[CustomerGroupDiscountRow] = []
    for group in groups:
        # أعضاء المجموعة
        members = (
            db.query(Customer.id, Customer.full_name)
            .filter(
                Customer.customer_group_id == group.id,
                Customer.is_active == True,
            )
            .all()
        )
        member_ids = {m.id for m in members}
        active_member_ids = member_ids & customer_ids_with_orders

        if not active_member_ids:
            continue  # مجموعة بدون أي نشاط في الفترة — لا تُعرض

        # تجميع مبيعات كل عضو
        member_sales: dict[int, dict] = {}
        for order in paid_orders:
            cid = getattr(order, 'customer_id', None)
            if cid not in active_member_ids:
                continue
            if cid not in member_sales:
                member_sales[cid] = {"invoices": 0, "sales": Decimal("0")}
            member_sales[cid]["invoices"] += 1
            member_sales[cid]["sales"] += getattr(order, 'total_amount',
                order.subtotal + order.vat_amount + order.service_charge - order.discount_amount
                if hasattr(order, 'subtotal') else Decimal("0"))

        member_name_map = {m.id: m.full_name for m in members}
        member_rows = [
            CustomerGroupMember(
                customer_id=cid,
                full_name=member_name_map.get(cid, f"عميل {cid}"),
                invoice_count=data["invoices"],
                total_sales=data["sales"],
            )
            for cid, data in sorted(member_sales.items(), key=lambda x: x[1]["sales"], reverse=True)
        ]

        group_rows.append(CustomerGroupDiscountRow(
            group_id=group.id,
            group_name=group.name_ar or group.name,
            discount_pct=group.discount_percentage,
            member_count=len(members),
            total_invoices=sum(d["invoices"] for d in member_sales.values()),
            total_sales_after_discount=sum(d["sales"] for d in member_sales.values()),
            members=member_rows,
        ))

    return DiscountAnalyticsResponse(
        period_from=date_from.isoformat(),
        period_to=date_to.isoformat(),
        total_revenue=total_revenue,
        total_discount=total_discount,
        discount_pct_of_revenue=discount_pct,
        discount_types=discount_type_rows,
        manual_per_cashier=manual_cashier_rows,
        customer_groups=sorted(group_rows, key=lambda x: x.total_sales_after_discount, reverse=True),
        computed_at=datetime.utcnow(),
    )


# ══════════════════════════════════════════════════════════════════════
