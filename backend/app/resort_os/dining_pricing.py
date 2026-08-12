"""Pure money calculations for final and legacy dining menu prices."""

from __future__ import annotations

from decimal import Decimal

MONEY = Decimal("0.01")


def snapshot_price_component(
    listed_price: Decimal,
    *,
    is_final_price: bool,
    vat_pct: Decimal,
    service_pct: Decimal,
) -> tuple[Decimal, Decimal | None]:
    """Return the accounting-net snapshot and optional final listed snapshot."""
    price = Decimal(listed_price)
    if not is_final_price:
        return price, None
    divisor = Decimal("1") + vat_pct + service_pct
    if divisor <= 0:
        raise ValueError("إعدادات الضريبة/الخدمة غير صالحة لحساب السعر النهائي")
    return (price / divisor).quantize(MONEY), price.quantize(MONEY)


def calculate_mixed_pricing(
    *,
    subtotal: Decimal,
    exclusive_subtotal: Decimal,
    listed_gross_total: Decimal,
    vat_pct: Decimal,
    service_pct: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """Calculate VAT/service while preserving approved final prices exactly.

    Legacy components are tax-exclusive and retain their previous calculation.
    Final-price components target their listed gross total exactly. Any cent
    introduced by per-unit net snapshots is absorbed in tax/service rounding,
    never in revenue or the amount displayed and collected from the guest.
    """
    subtotal = subtotal.quantize(MONEY)
    exclusive_subtotal = exclusive_subtotal.quantize(MONEY)
    listed_gross_total = listed_gross_total.quantize(MONEY)
    vat_amount = (subtotal * vat_pct).quantize(MONEY)
    exclusive_total = (
        exclusive_subtotal
        + (exclusive_subtotal * vat_pct).quantize(MONEY)
        + (exclusive_subtotal * service_pct).quantize(MONEY)
    )
    target_total = (exclusive_total + listed_gross_total).quantize(MONEY)
    service_charge = (target_total - subtotal - vat_amount).quantize(MONEY)
    # With service=0, per-unit net rounding can make aggregated VAT one cent
    # too high. Move that rounding cent out of VAT rather than producing a
    # negative service amount; the approved total remains unchanged.
    if service_charge < 0 and vat_amount > 0:
        rounding_shift = min(vat_amount, -service_charge)
        vat_amount = (vat_amount - rounding_shift).quantize(MONEY)
        service_charge = (service_charge + rounding_shift).quantize(MONEY)
    if service_charge < 0:
        raise ValueError("تعذر فصل السعر النهائي إلى صافي وضريبة وخدمة")
    return vat_amount, service_charge, target_total
