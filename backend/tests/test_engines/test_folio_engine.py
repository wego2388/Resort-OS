"""
tests/test_engines/test_folio_engine.py
اختبارات كاملة لـ Folio Engine — مركز ثقل النظام
بدون DB، بدون fixtures — pure functions فقط
"""

from datetime import datetime
from decimal import Decimal

import pytest

from app.resort_os.folio_engine import (
    CHARGE_LABELS_AR,
    CHARGE_TYPES,
    FolioChargeItem,
    FolioSummary,
    build_receipt_lines,
    calculate_vat,
    can_checkout,
    validate_charge,
)


# ─── Helpers ──────────────────────────────────────────────────────────

def _charge(
    charge_type: str = "room",
    amount: Decimal = Decimal("200"),
    vat_amount: Decimal = Decimal("28"),
    is_settled: bool = False,
) -> FolioChargeItem:
    return FolioChargeItem(
        charge_type=charge_type,
        description=f"test {charge_type}",
        amount=amount,
        vat_amount=vat_amount,
        posted_at=datetime(2026, 6, 15, 12, 0),
        is_settled=is_settled,
    )


def _folio(
    charges: list | None = None,
    is_checked_out: bool = False,
) -> FolioSummary:
    return FolioSummary(
        folio_id=1,
        guest_name="أحمد محمد",
        check_in=datetime(2026, 6, 10, 14, 0),
        check_out=datetime(2026, 6, 15, 12, 0),
        is_checked_out=is_checked_out,
        charges=charges or [],
    )


# ─── FolioSummary Properties ──────────────────────────────────────────

class TestFolioSummaryProperties:

    def test_total_amount_empty(self):
        folio = _folio()
        assert folio.total_amount == Decimal("0")

    def test_total_amount_with_charges(self):
        folio = _folio(charges=[
            _charge("room",       Decimal("500")),
            _charge("restaurant", Decimal("150")),
        ])
        assert folio.total_amount == Decimal("650")

    def test_total_vat(self):
        folio = _folio(charges=[
            _charge("room", Decimal("500"), vat_amount=Decimal("70")),
            _charge("cafe", Decimal("100"), vat_amount=Decimal("14")),
        ])
        assert folio.total_vat == Decimal("84")

    def test_total_with_vat(self):
        folio = _folio(charges=[
            _charge("room", Decimal("500"), vat_amount=Decimal("70")),
        ])
        assert folio.total_with_vat == Decimal("570")

    def test_unsettled_amount_all_unsettled(self):
        folio = _folio(charges=[
            _charge("room", Decimal("500"), vat_amount=Decimal("70"), is_settled=False),
            _charge("restaurant", Decimal("100"), vat_amount=Decimal("14"), is_settled=False),
        ])
        assert folio.unsettled_amount == Decimal("684")  # (500+70) + (100+14)

    def test_unsettled_amount_some_settled(self):
        folio = _folio(charges=[
            _charge("room", Decimal("500"), vat_amount=Decimal("70"), is_settled=True),
            _charge("cafe", Decimal("100"), vat_amount=Decimal("14"), is_settled=False),
        ])
        assert folio.unsettled_amount == Decimal("114")  # فقط الـ cafe

    def test_unsettled_amount_all_settled(self):
        folio = _folio(charges=[
            _charge("room", Decimal("500"), vat_amount=Decimal("70"), is_settled=True),
        ])
        assert folio.unsettled_amount == Decimal("0")

    def test_by_type_groups_charges(self):
        folio = _folio(charges=[
            _charge("room",       Decimal("300")),
            _charge("room",       Decimal("200")),
            _charge("restaurant", Decimal("100")),
        ])
        by_type = folio.by_type
        assert by_type["room"] == Decimal("500")
        assert by_type["restaurant"] == Decimal("100")
        assert len(by_type) == 2

    def test_by_type_empty_folio(self):
        assert _folio().by_type == {}


# ─── validate_charge ──────────────────────────────────────────────────

class TestValidateCharge:

    def test_valid_charge_passes(self):
        folio = _folio()
        result = validate_charge(folio, "room", Decimal("500"))
        assert result.valid is True
        assert result.error == ""

    def test_checked_out_folio_rejected(self):
        folio = _folio(is_checked_out=True)
        result = validate_charge(folio, "room", Decimal("500"))
        assert result.valid is False
        assert "checkout" in result.error.lower() or "مغلق" in result.error

    def test_invalid_charge_type_rejected(self):
        folio = _folio()
        result = validate_charge(folio, "parking", Decimal("50"))
        assert result.valid is False
        assert "parking" in result.error

    def test_zero_amount_rejected(self):
        folio = _folio()
        result = validate_charge(folio, "room", Decimal("0"))
        assert result.valid is False

    def test_negative_amount_rejected(self):
        folio = _folio()
        result = validate_charge(folio, "room", Decimal("-100"))
        assert result.valid is False

    def test_all_valid_charge_types(self):
        folio = _folio()
        for ct in CHARGE_TYPES:
            result = validate_charge(folio, ct, Decimal("100"))
            assert result.valid is True, f"Expected valid for type: {ct}"


# ─── can_checkout ─────────────────────────────────────────────────────

class TestCanCheckout:

    def test_all_settled_can_checkout(self):
        folio = _folio(charges=[
            _charge("room", Decimal("500"), vat_amount=Decimal("70"), is_settled=True),
        ])
        result = can_checkout(folio)
        assert result.valid is True

    def test_empty_folio_can_checkout(self):
        """فوليو بدون charges يمكن checkout"""
        result = can_checkout(_folio())
        assert result.valid is True

    def test_unsettled_blocks_checkout(self):
        folio = _folio(charges=[
            _charge("room", Decimal("500"), vat_amount=Decimal("70"), is_settled=False),
        ])
        result = can_checkout(folio)
        assert result.valid is False
        assert "570" in result.error  # يذكر المبلغ غير المسدد

    def test_already_checked_out_blocked(self):
        folio = _folio(is_checked_out=True)
        result = can_checkout(folio)
        assert result.valid is False
        assert "مغلق" in result.error

    def test_partial_settlement_blocks_checkout(self):
        folio = _folio(charges=[
            _charge("room",       Decimal("500"), vat_amount=Decimal("70"), is_settled=True),
            _charge("restaurant", Decimal("100"), vat_amount=Decimal("14"), is_settled=False),
        ])
        result = can_checkout(folio)
        assert result.valid is False


# ─── calculate_vat ────────────────────────────────────────────────────

class TestCalculateVat:

    def test_standard_14_percent(self):
        result = calculate_vat(Decimal("100"), vat_pct=14.0)
        assert result == Decimal("14.00")

    def test_zero_amount(self):
        result = calculate_vat(Decimal("0"), vat_pct=14.0)
        assert result == Decimal("0.00")

    def test_rounding_half_up(self):
        """385 × 14% = 53.9 → 53.90"""
        result = calculate_vat(Decimal("385"), vat_pct=14.0)
        assert result == Decimal("53.90")

    def test_zero_vat_rate(self):
        result = calculate_vat(Decimal("500"), vat_pct=0.0)
        assert result == Decimal("0.00")

    def test_fractional_result_rounded(self):
        """100 × 14% = 14.00 — مباشر"""
        result = calculate_vat(Decimal("100"), vat_pct=14.0)
        assert result == Decimal("14.00")


# ─── build_receipt_lines ──────────────────────────────────────────────

class TestBuildReceiptLines:

    def test_empty_folio_empty_lines(self):
        lines = build_receipt_lines(_folio())
        assert lines == []

    def test_single_type_single_line(self):
        folio = _folio(charges=[
            _charge("room", Decimal("500"), vat_amount=Decimal("0")),
        ])
        lines = build_receipt_lines(folio, vat_pct=14.0)
        assert len(lines) == 1
        line = lines[0]
        assert line["amount"] == Decimal("500")
        assert line["vat"] == Decimal("70.00")     # 500 × 14%
        assert line["total"] == Decimal("570.00")

    def test_multiple_types_multiple_lines(self):
        folio = _folio(charges=[
            _charge("room",       Decimal("500"), vat_amount=Decimal("0")),
            _charge("restaurant", Decimal("150"), vat_amount=Decimal("0")),
            _charge("cafe",       Decimal("80"),  vat_amount=Decimal("0")),
        ])
        lines = build_receipt_lines(folio, vat_pct=14.0)
        assert len(lines) == 3

    def test_same_type_merged(self):
        """نفس النوع يتحمج في سطر واحد"""
        folio = _folio(charges=[
            _charge("room", Decimal("300"), vat_amount=Decimal("0")),
            _charge("room", Decimal("200"), vat_amount=Decimal("0")),
        ])
        lines = build_receipt_lines(folio, vat_pct=14.0)
        assert len(lines) == 1
        assert lines[0]["amount"] == Decimal("500")

    def test_arabic_labels(self):
        """التسميات بالعربي"""
        folio = _folio(charges=[_charge("room", Decimal("100"))])
        lines = build_receipt_lines(folio, vat_pct=14.0)
        assert lines[0]["label"] == CHARGE_LABELS_AR["room"]

    def test_all_charge_types_have_labels(self):
        """كل الأنواع لها تسمية"""
        for ct in CHARGE_TYPES:
            assert ct in CHARGE_LABELS_AR
