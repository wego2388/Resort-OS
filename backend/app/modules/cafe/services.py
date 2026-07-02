"""app/modules/cafe/services.py — نفس منطق restaurant مع جداول cafe"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.cafe import crud
from app.modules.cafe.models import CafeOrder
from app.modules.cafe.schemas import CafeOrderCreate


def _get_order_or_404(db: Session, order_id: int) -> CafeOrder:
    order = crud.get_order(db, order_id)
    if not order:
        raise ValueError(f"الطلب {order_id} غير موجود")
    return order


def create_order(db: Session, data: CafeOrderCreate, waiter_id: Optional[int] = None) -> CafeOrder:
    items_data = []
    subtotal = Decimal("0")

    for item_req in data.items:
        item = crud.get_item(db, item_req.item_id)
        if not item:
            raise ValueError(f"الصنف {item_req.item_id} غير موجود")
        if not item.is_available:
            raise ValueError(f"الصنف '{item.name}' غير متاح حالياً")
        subtotal += item.price * item_req.quantity
        items_data.append({
            "item_id":    item_req.item_id,
            "name":       item.name,
            "unit_price": item.price,
            "quantity":   item_req.quantity,
            "notes":      item_req.notes,
        })

    vat_pct    = Decimal(str(settings.VAT_PERCENTAGE)) / Decimal("100")
    svc_pct    = Decimal(str(settings.SERVICE_CHARGE_PERCENTAGE)) / Decimal("100")
    vat_amount = (subtotal * vat_pct).quantize(Decimal("0.01"))
    svc_charge = (subtotal * svc_pct).quantize(Decimal("0.01"))
    total      = subtotal + vat_amount + svc_charge

    order = crud.create_order(
        db=db, branch_id=data.branch_id, order_type=data.order_type,
        table_id=data.table_id, notes=data.notes,
        subtotal=subtotal, vat_amount=vat_amount,
        service_charge=svc_charge, total=total,
        waiter_id=waiter_id, items_data=items_data,
    )
    db.commit()
    db.refresh(order)
    return order


def generate_receipt_pdf(db: Session, order_id: int) -> bytes:
    """يُولّد PDF إيصال طلب كافيه."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    order = _get_order_or_404(db, order_id)
    items_text = "\n".join(
        f"{item.name} × {item.quantity}  ({item.unit_price:,.2f} EGP)"
        for item in order.items
    )
    fields = [
        ("رقم الطلب",    order.order_number),
        ("نوع الطلب",    order.order_type),
        ("الأصناف",      items_text),
        ("المجموع قبل الضريبة", f"{order.subtotal:,.2f} EGP"),
        ("ضريبة (VAT)",  f"{order.vat_amount:,.2f} EGP"),
        ("رسوم الخدمة",  f"{order.service_charge:,.2f} EGP"),
    ]
    return builder.receipt_pdf(
        reference=order.order_number,
        title="إيصال الكافيه",
        fields=fields,
        total=float(order.total),
        currency="EGP",
        note="شكراً لزيارتكم — الخيمة بيتش ريزورت",
    )


def update_order_status(db: Session, order_id: int, new_status: str) -> CafeOrder:
    order = _get_order_or_404(db, order_id)
    if order.status in ("paid", "cancelled"):
        raise ValueError(f"لا يمكن تغيير حالة طلب '{order.status}'")
    order = crud.update_order_status(db, order, new_status)

    # إرسال ticket للمطبخ عند تحويل الطلب لـ in_kitchen
    if new_status == "in_kitchen":
        from app.modules.restaurant.crud import create_kitchen_ticket  # noqa: PLC0415
        items_snapshot = [
            {
                "order_item_id": item.id,
                "name":          item.name,
                "quantity":      item.quantity,
                "notes":         item.notes,
            }
            for item in order.items
        ]
        create_kitchen_ticket(
            db,
            order_id=order.id,
            branch_id=order.branch_id,
            station="kitchen",
            items_snapshot=items_snapshot,
            module="cafe",
        )

    # نشر charge على folio الغرفة عند الدفع
    if new_status == "paid" and order.folio_id:
        try:
            from app.modules.finance.crud import add_charge  # noqa: PLC0415
            from app.modules.finance.schemas import FolioChargeCreate  # noqa: PLC0415
            charge_data = FolioChargeCreate(
                charge_type="cafe",
                description=f"Ordine {order.order_number}",
                amount=order.subtotal,
                vat_amount=order.vat_amount,
                posted_at=datetime.utcnow(),
                ref_order_id=order.id,
            )
            add_charge(db, order.folio_id, charge_data)
        except Exception:
            pass  # non bloccare il pagamento se il folio fallisce

    # قيد إيراد الكافيه عند الدفع
    if new_status == "paid":
        _post_order_revenue_journal(db, order)

    db.commit()
    db.refresh(order)
    return order


def _post_order_revenue_journal(db: Session, order: "CafeOrder") -> None:
    """Dr. Cash (1100) / Cr. Cafe Revenue (4400) — نفس نمط
    pms.services._post_checkout_journal: يبتلع أي خطأ حتى لا يمنع إتمام
    الدفع الفعلي إذا فشل الترحيل المحاسبي."""
    try:
        from app.modules.finance.crud import get_account_by_code, create_journal_entry  # noqa: PLC0415
        from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate  # noqa: PLC0415
        from datetime import date as _date  # noqa: PLC0415

        cash_acc = get_account_by_code(db, order.branch_id, "1100")
        rev_acc  = get_account_by_code(db, order.branch_id, "4400")
        if not cash_acc or not rev_acc:
            return

        amount = order.total or Decimal("0")
        if amount <= 0:
            return

        entry_data = JournalEntryCreate(
            branch_id=order.branch_id,
            entry_date=_date.today(),
            reference=f"ORD-{order.order_number}",
            description=f"إيرادات كافيه — {order.order_number}",
            source="cafe",
            source_id=order.id,
            lines=[
                JournalLineCreate(account_id=cash_acc.id, debit=amount,  credit=Decimal("0")),
                JournalLineCreate(account_id=rev_acc.id,  debit=Decimal("0"), credit=amount),
            ],
        )
        create_journal_entry(db, entry_data, 0)
    except Exception:
        pass
