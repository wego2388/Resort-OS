"""
app/modules/dining/_services/receipts.py
Extracted from app/modules/dining/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from decimal import Decimal
from sqlalchemy.orm import Session
from app.modules.dining._services._helpers import (
    _get_order_or_404,
)


_ORDER_TYPE_LABELS_AR = {
    "dine_in": "صالة",
    "takeaway": "تيك أواي",
    "delivery": "دليفري",
    "room_service": "خدمة الغرف",
}


def generate_receipt_pdf(db: Session, order_id: int) -> bytes:
    """راجع restaurant.services.generate_receipt_pdf — نفس شكل الإيصال
    الحراري 80mm.

    2026-08-04 (طلب Mohamed بعد مراجعة إيصال حقيقي): كانت بتحط كل حاجة —
    رقم الطلب، نوع الطلب، الأصناف، الضريبة — في نفس قائمة fields المسطّحة،
    فمفيش أي تمييز بصري بين البيانات الوصفية والأصناف والملخص المالي (فوق
    كده، كل النص العربي كان بيظهر كمربعات سودة أصلاً — راجع تعليق
    _register_arabic_fonts في core/kernel/reports.py للباج الحقيقي).
    دلوقتي بتستخدم الأقسام المنفصلة (items/summary) في receipt_pdf_thermal
    عشان جدول أصناف حقيقي وملخص مالي واضح، ونوع الطلب بتسمية عربية مفهومة
    بدل القيمة الخام (dine_in) اللي كانت بتتعرض للعميل زي ما هي."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    order = _get_order_or_404(db, order_id)

    fields: list[tuple[str, str]] = [
        (f"{_ORDER_TYPE_LABELS_AR.get(order.order_type, order.order_type)} · Order Type",
         order.order_number),
    ]
    if order.table:
        fields.append(("الطاولة · Table", order.table.table_number))

    active_items = [
        item for item in order.items
        if item.status not in ("cancelled", "refunded")
    ]

    def displayed_unit_price(item) -> Decimal:
        base_price = item.listed_unit_price if item.listed_unit_price is not None else item.unit_price
        extras_price = sum(
            (
                extra.listed_price_addition
                if extra.listed_price_addition is not None
                else extra.price_addition
            )
            for extra in item.extras
        )
        return base_price + extras_price

    items = [
        (
            item.name,
            item.quantity,
            float(displayed_unit_price(item)),
            float(displayed_unit_price(item) * item.quantity),
        )
        for item in active_items
    ]

    all_prices_are_final = bool(active_items) and all(
        item.listed_unit_price is not None
        and all(extra.listed_price_addition is not None for extra in item.extras)
        for item in active_items
    )
    displayed_subtotal = (
        sum((displayed_unit_price(item) * item.quantity for item in active_items), Decimal("0"))
        if all_prices_are_final
        else order.subtotal
    )
    subtotal_label = (
        "إجمالي أسعار المنيو · Menu prices total"
        if all_prices_are_final
        else "المجموع قبل الضريبة · Subtotal"
    )
    summary = [(subtotal_label, f"{displayed_subtotal:,.2f} EGP")]
    if order.vat_amount:
        vat_label = "ضريبة القيمة المضافة (شاملة) · VAT (included)" if all_prices_are_final else "ضريبة القيمة المضافة · VAT"
        summary.append((vat_label, f"{order.vat_amount:,.2f} EGP"))
    if order.service_charge:
        service_label = "رسوم الخدمة (شاملة) · Service (included)" if all_prices_are_final else "رسوم الخدمة · Service"
        summary.append((service_label, f"{order.service_charge:,.2f} EGP"))
    if order.discount_amount and order.discount_amount > 0:
        summary.append(("الخصم · Discount", f"-{order.discount_amount:,.2f} EGP"))

    return builder.receipt_pdf_thermal(
        reference=order.order_number,
        title="إيصال الطلب · Order Receipt",
        subtitle="El Kheima Beach Resort",
        fields=fields,
        items=items,
        summary=summary,
        total=float(order.total),
        currency="EGP",
        note="شكراً لزيارتكم — نتمنى لكم إقامة سعيدة",
    )
