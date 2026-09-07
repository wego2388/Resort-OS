"""app/modules/timeshare/_services/dashboard.py — CS/sales dashboards,
overall stats, and the monthly collection + contract PDF reports."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.timeshare import crud

from .contracts import get_contract_or_404


def generate_monthly_collection_report(
    db: Session, branch_id: int, month: str,
) -> bytes:
    """تقرير التحصيل الشهري — Excel مُنسَّق للإدارة.

    `month` بصيغة "YYYY-MM".

    الشيت الأول: تفاصيل الأقساط (مدفوعة + متأخرة + معلقة) للشهر.
    الشيت الثاني: ملخص تنفيذي (المطلوب / المحصَّل / المتأخر / نسبة التحصيل).

    يستخدم `crud.list_all_installments` الموجود مع فلتر month — نفس البيانات
    التي يعرضها تاب الأقساط في الـ UI، لكن في تقرير Excel مُنسَّق بشكل أفضل
    للاجتماعات الشهرية وبريد الإدارة."""
    from decimal import Decimal as _D  # noqa: PLC0415
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    installments = crud.list_all_installments(
        db, branch_id, month=month, limit=10000,
    )

    # ── حساب ملخص التحصيل ──────────────────────────────────────────
    total_due = _D("0")
    total_collected = _D("0")
    total_overdue = _D("0")
    total_pending = _D("0")

    detail_rows = []
    for i in installments:
        c = i.contract
        customer_name = c.customer_name if c else "—"
        customer_phone = c.customer_phone if c else "—"
        room_type = c.room_type if c else "—"
        contract_number = c.contract_number if c else "—"

        total_due += i.amount
        if i.status == "paid":
            total_collected += i.paid_amount
        elif i.status == "overdue":
            total_overdue += i.amount - i.paid_amount
        elif i.status in ("pending", "partial"):
            total_pending += i.amount - i.paid_amount

        status_label = {
            "paid": "مدفوع", "pending": "معلق",
            "overdue": "متأخر", "partial": "جزئي",
        }.get(i.status, i.status)

        detail_rows.append([
            customer_name,
            customer_phone or "—",
            contract_number,
            room_type,
            i.installment_no,
            str(i.due_date),
            float(i.amount),
            float(i.paid_amount),
            float(i.amount - i.paid_amount),
            status_label,
            i.payment_method or "—",
            i.receipt_number or "—",
        ])

    # ترتيب: متأخر أولاً ثم معلق ثم مدفوع
    status_order = {"متأخر": 0, "جزئي": 1, "معلق": 2, "مدفوع": 3}
    detail_rows.sort(key=lambda r: status_order.get(r[9], 9))

    collection_rate = (
        round(float(total_collected) / float(total_due) * 100, 1)
        if total_due > 0 else 0.0
    )

    summary_rows = [
        ["إجمالي المطلوب للشهر",  float(total_due)],
        ["إجمالي المحصَّل",        float(total_collected)],
        ["إجمالي المتأخر",         float(total_overdue)],
        ["إجمالي المعلق",          float(total_pending)],
        ["نسبة التحصيل %",         collection_rate],
        ["عدد الأقساط",            len(installments)],
    ]

    year, month_num = month.split("-")
    month_label = f"{month_num}-{year}"  # بدون / لأن openpyxl لا يقبله في اسم الشيت

    return builder.excel(
        title=f"تقرير التحصيل الشهري — {month_label}",
        sheets=[
            {
                "name": f"تفاصيل {month_label}",
                "headers": [
                    "العميل", "الهاتف", "رقم العقد", "نوع الوحدة",
                    "القسط #", "تاريخ الاستحقاق",
                    "المبلغ", "المدفوع", "المتبقي",
                    "الحالة", "طريقة الدفع", "رقم الإيصال",
                ],
                "rows": detail_rows,
                "col_types": [
                    "text", "text", "text", "text",
                    "number", "text",
                    "currency", "currency", "currency",
                    "text", "text", "text",
                ],
                "summary": {
                    "إجمالي المطلوب": float(total_due),
                    "المحصَّل": float(total_collected),
                    "المتأخر": float(total_overdue),
                },
            },
            {
                "name": "ملخص تنفيذي",
                "headers": ["البيان", "القيمة"],
                "rows": summary_rows,
                "col_types": ["text", "currency"],
                "summary": {"نسبة التحصيل %": collection_rate},
            },
        ],
    )


def generate_contract_pdf(db: Session, contract_id: int) -> bytes:
    """PDF ملخص عقد الملكية الجزئية."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    contract = get_contract_or_404(db, contract_id)
    week_label = f"أسبوع {contract.week_number}" if contract.week_number else "عائم"
    fields = [
        ("العميل",             contract.customer_name),
        ("رقم العقد",          contract.contract_number),
        ("نوع الغرفة",         contract.room_type),
        ("الأسبوع",            week_label),
        ("الليالي/سنة",        str(contract.nights_per_year)),
        ("إجمالي العقد",       f"{contract.total_value:,.2f} EGP"),
        ("الدفعة الأولى",      f"{contract.down_payment:,.2f} EGP"),
        ("عدد الأقساط",        str(contract.installments)),
        ("تاريخ البداية",      str(contract.start_date)),
        ("الحالة",             contract.status),
    ]
    return builder.receipt_pdf(
        reference=contract.contract_number,
        title="عقد ملكية جزئية",
        fields=fields,
        total=float(contract.total_value),
        currency="EGP",
        note="الخيمة بيتش ريزورت — وثيقة العقد",
    )


# ── CS Dashboard ─────────────────────────────────────────────────────

def get_cs_summary(db: Session, branch_id: int) -> dict:
    """ملخص شامل لخدمة عملاء الملكية الجزئية — زيارات قادمة + متأخرات + نسبة تحصيل.

    ⚠️ "اليوم" هنا بيتحسب بتوقيت المنتجع (business_today) مش توقيت السيرفر
    المحلي — نفس فئة باج تذاكر المطبخ (KDS)، هنا بيأثّر على "الأيام المتبقية
    لزيارة قادمة" و"متأخرات" المعروضة لموظف خدمة العملاء."""
    from app.core.config import settings  # noqa: PLC0415
    from app.resort_os.timeshare_engine import ContractSummary, build_cs_summary, find_next_visit  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    today = business_today(settings.TIMEZONE)
    rows = crud.list_active_contracts_with_aggregates(db, branch_id)

    summaries: list[ContractSummary] = []
    upcoming_visits = []
    for contract, collected, overdue_amount, pending_count, next_due in rows:
        summaries.append(ContractSummary(
            contract_id=contract.id,
            customer_name=contract.customer_name,
            customer_phone=contract.customer_phone,
            room_type=contract.room_type,
            week_number=contract.week_number,
            total_value=contract.total_value,
            collected=collected,
            overdue_amount=overdue_amount,
            pending_count=pending_count,
            next_due=next_due,
        ))
        if contract.week_number:
            visit = find_next_visit(contract.week_number, contract.nights_per_year, today)
            if visit and 0 <= visit.days_until <= 30:
                upcoming_visits.append({
                    "id": contract.id, "contract_number": contract.contract_number,
                    "customer_name": contract.customer_name, "customer_phone": contract.customer_phone,
                    "room_type": contract.room_type, "week_number": contract.week_number,
                    "visit_start": visit.visit_start.isoformat(), "visit_end": visit.visit_end.isoformat(),
                    "days_until": visit.days_until, "overdue_amount": float(overdue_amount),
                })

    this_month_due = crud.get_this_month_due(db, branch_id, today)
    summary = build_cs_summary(summaries, this_month_due)
    summary["upcoming_visits"] = sorted(upcoming_visits, key=lambda x: x["days_until"])

    # مؤشر إشغال مخزون الوحدات (2026-08-03) — نسبة الوحدات المشغولة فعليًا
    # النهاردة من إجمالي المخزون القابل للحجز، مؤشر تشغيلي مفيش له مكان
    # تاني في اللوحة رغم إن كل البيانات اللازمة له موجودة أصلاً.
    occupied_units, total_units = crud.unit_occupancy_today(db, branch_id, today)
    summary["occupied_units"] = occupied_units
    summary["total_units"] = total_units
    summary["occupancy_rate_pct"] = (
        round(occupied_units / total_units * 100, 1) if total_units > 0 else 0.0
    )
    # 2026-08-04: تابا "طلبات الزيارة" و"تذاكر الدعم" مالهومش أي مؤشر في
    # اللوحة قبل كده — الموظف لازم يفتحهم يدويًا كل مرة يتأكد مفيش حاجة
    # جديدة، نفس فئة مؤشر الإشغال فوق ده بالظبط.
    summary["pending_visit_requests"] = crud.count_pending_visit_requests(db, branch_id)
    summary["open_support_tickets"] = crud.count_open_support_tickets(db, branch_id)
    summary["overdue_clients"] = [
        {
            "id": c.contract_id, "customer_name": c.customer_name, "customer_phone": c.customer_phone,
            "room_type": c.room_type, "overdue_amount": float(c.overdue_amount),
            "pending_count": c.pending_count,
            "next_due": c.next_due.isoformat() if c.next_due else None,
        }
        for c in summary["overdue_clients"]
    ]
    return summary


def get_sales_dashboard(db: Session, branch_id: int) -> dict:
    """لوحة مبيعات لفريق المبيعات (مختلفة عن cs-summary الإداري) — pipeline
    (draft→active→...)، متأخرات بأرقام تليفون جاهزة للاتصال، أقساط الشهر الحالي."""
    cs = get_cs_summary(db, branch_id)
    pipeline = crud.count_contracts_by_status(db, branch_id)
    for key in ("draft", "active", "suspended", "cancelled", "expired"):
        pipeline.setdefault(key, 0)

    return {
        "pipeline": pipeline,
        "active_contracts": cs["active_contracts"],
        "overdue_contracts_count": cs["overdue_contracts_count"],
        "expired_contracts_count": pipeline.get("expired", 0),
        "this_month_due": cs["this_month_due"],
        "collection_rate_pct": cs["collection_rate_pct"],
        "total_value": cs["total_value"],
        "total_collected": cs["total_collected"],
        "total_overdue": cs["total_overdue"],
        "overdue_clients": cs["overdue_clients"],  # كل واحد فيه customer_phone جاهز للاتصال
        "upcoming_visits": cs["upcoming_visits"],
    }


def generate_sales_dashboard_excel(db: Session, branch_id: int) -> bytes:
    """تصدير Excel للوحة مبيعات الملكية الجزئية — قائمة اتصال يومية (متأخرات السداد)
    وزيارات قادمة، لمدير المبيعات (طباعة/مشاركة، راجع wagdy.md #12).
    نفس بيانات SalesDashboardView.vue بالظبط، بدون أي منطق عمل إضافي هنا —
    الشيت مجرد عرض مختلف لنفس get_sales_dashboard."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    dash = get_sales_dashboard(db, branch_id)

    overdue_rows = [
        [c["customer_name"], c["customer_phone"] or "—", c["room_type"],
         c["pending_count"], c["overdue_amount"], c["next_due"] or "—"]
        for c in dash["overdue_clients"]
    ]
    total_overdue = sum(c["overdue_amount"] for c in dash["overdue_clients"])

    visit_rows = [
        [v["customer_name"], v["customer_phone"] or "—", v["contract_number"],
         v["room_type"], v["week_number"], v["visit_start"], v["days_until"]]
        for v in dash["upcoming_visits"]
    ]

    return builder.excel(
        sheets=[
            {
                "name": "متأخرات السداد",
                "headers": ["اسم العميل", "رقم الهاتف", "نوع الوحدة",
                            "أقساط معلقة", "المبلغ المتأخر", "أقرب استحقاق"],
                "rows": overdue_rows,
                "col_types": ["text", "text", "text", "number", "currency", "text"],
                "summary": {"عدد العملاء": len(overdue_rows), "إجمالي المتأخر": total_overdue},
            },
            {
                "name": "زيارات قادمة",
                "headers": ["اسم العميل", "رقم الهاتف", "رقم العقد",
                            "نوع الوحدة", "رقم الأسبوع", "تاريخ الزيارة", "الأيام المتبقية"],
                "rows": visit_rows,
                "col_types": ["text", "text", "text", "text", "number", "text", "number"],
                "summary": {"عدد الزيارات": len(visit_rows)},
            },
        ],
        title=f"لوحة مبيعات الملكية الجزئية — فرع {branch_id}",
    )


def get_stats(db: Session, branch_id: int) -> dict:
    by_partner = crud.stats_by_partner(db, branch_id)
    by_room_type = crud.stats_by_room_type(db, branch_id)
    by_batch = crud.stats_by_batch(db, branch_id)
    cancelled = crud.cancellation_summary(db, branch_id)
    collection = crud.overall_collection(db, branch_id)

    collected, pending = collection["collected"], collection["pending"]
    rate = round(float(collected) / float(collected + pending) * 100, 1) if (collected + pending) > 0 else 0

    return {
        "by_partner": [
            {"partner_company": r.partner_company, "contracts": r.contracts,
             "total_value": float(r.total_value), "total_down": float(r.total_down),
             "resort_share": float(r.resort_share)}
            for r in by_partner
        ],
        "by_room_type": [
            {"room_type": r.room_type, "contracts": r.contracts,
             "total_value": float(r.total_value), "avg_value": float(r.avg_value)}
            for r in by_room_type
        ],
        "by_batch": [
            {"batch_number": r.batch_number, "contracts": r.contracts,
             "total_value": float(r.total_value), "total_down": float(r.total_down),
             "batch_date": r.batch_date.date().isoformat() if r.batch_date else None}
            for r in by_batch
        ],
        "cancelled": {"count": cancelled["count"], "refunded": float(cancelled["refunded"])},
        "collection": {
            "collected": float(collection["collected"]),
            "pending": float(collection["pending"]),
            "overdue": float(collection["overdue"]),
            "rate": rate,
        },
    }
