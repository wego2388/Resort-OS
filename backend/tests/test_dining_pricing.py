from decimal import Decimal

from app.resort_os.dining_pricing import (
    calculate_mixed_pricing,
    snapshot_price_component,
)


def test_final_price_is_split_without_changing_guest_total():
    net, listed = snapshot_price_component(
        Decimal("50.00"),
        is_final_price=True,
        vat_pct=Decimal("0.14"),
        service_pct=Decimal("0.12"),
    )

    assert net == Decimal("39.68")
    assert listed == Decimal("50.00")
    assert calculate_mixed_pricing(
        subtotal=net,
        exclusive_subtotal=Decimal("0"),
        listed_gross_total=listed,
        vat_pct=Decimal("0.14"),
        service_pct=Decimal("0.12"),
    ) == (Decimal("5.56"), Decimal("4.76"), Decimal("50.00"))


def test_zero_service_rounding_never_creates_negative_service():
    net, listed = snapshot_price_component(
        Decimal("80.00"),
        is_final_price=True,
        vat_pct=Decimal("0.14"),
        service_pct=Decimal("0"),
    )

    assert calculate_mixed_pricing(
        subtotal=net * 2,
        exclusive_subtotal=Decimal("0"),
        listed_gross_total=listed * 2,
        vat_pct=Decimal("0.14"),
        service_pct=Decimal("0"),
    ) == (Decimal("19.64"), Decimal("0.00"), Decimal("160.00"))


def test_legacy_and_final_components_can_share_a_bill():
    assert calculate_mixed_pricing(
        subtotal=Decimal("139.68"),
        exclusive_subtotal=Decimal("100.00"),
        listed_gross_total=Decimal("50.00"),
        vat_pct=Decimal("0.14"),
        service_pct=Decimal("0.12"),
    ) == (Decimal("19.56"), Decimal("16.76"), Decimal("176.00"))
