"""
app/modules/finance/_services/folios.py
Extracted from app/modules/finance/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.finance import crud
from app.modules.finance.models import Folio, FolioCharge
from app.modules.finance.schemas import (
    FolioChargeCreate,
    FolioCreate,
)
from app.resort_os.folio_engine import (
    FolioChargeItem,
    FolioSummary,
    can_checkout,
    validate_charge,
)
from app.modules.finance._services._exceptions import (
    FolioClosedError,
)


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
