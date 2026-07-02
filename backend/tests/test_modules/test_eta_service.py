"""
tests/test_modules/test_eta_service.py
ETAService — document building (pure logic, no live ETA calls) + config guards.
"""
from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.finance.eta_service import ETAConfigError, ETAService


def _settings(**overrides) -> Settings:
    base = {
        "ETA_ENABLED": True,
        "ETA_CLIENT_ID": "test-client",
        "ETA_CLIENT_SECRET": "test-secret",
        "ETA_TAXPAYER_RIN": "123456789",
        "ETA_TAXPAYER_NAME": "Test Resort",
        "VAT_PERCENTAGE": 14.0,
    }
    base.update(overrides)
    return Settings(**base)


class TestETAServiceConfig:
    def test_missing_client_credentials_raises(self):
        with pytest.raises(ETAConfigError):
            ETAService(_settings(ETA_CLIENT_ID=None, ETA_CLIENT_SECRET=None))

    def test_missing_taxpayer_rin_raises_on_build(self):
        eta = ETAService(_settings(ETA_TAXPAYER_RIN=None, ETA_TAXPAYER_NAME=None))
        with pytest.raises(ETAConfigError):
            eta.build_invoice_document(
                internal_id="ETA-TEST-0001",
                issued_at_iso="2026-07-01T00:00:00Z",
                receiver_name="Guest",
                receiver_rin=None,
                line_items=[{"description": "Room", "quantity": 1, "unit_price": 100}],
            )


class TestBuildInvoiceDocument:
    def test_vat_math_default_rate(self):
        eta = ETAService(_settings())
        doc = eta.build_invoice_document(
            internal_id="ETA-TEST-0002",
            issued_at_iso="2026-07-01T00:00:00Z",
            receiver_name="Guest",
            receiver_rin=None,
            line_items=[
                {"description": "Room charge", "quantity": 1, "unit_price": 1000.0},
                {"description": "Towel rental", "quantity": 2, "unit_price": 50.0},
            ],
        )
        assert doc["totalSalesAmount"] == 1100.0
        assert doc["taxTotals"][0]["amount"] == pytest.approx(154.0)
        assert doc["totalAmount"] == pytest.approx(1254.0)
        assert doc["issuer"]["id"] == "123456789"
        assert doc["receiver"]["type"] == "P"  # no RIN → B2C

    def test_vat_rate_override_per_line(self):
        eta = ETAService(_settings())
        doc = eta.build_invoice_document(
            internal_id="ETA-TEST-0003",
            issued_at_iso="2026-07-01T00:00:00Z",
            receiver_name="Guest",
            receiver_rin=None,
            line_items=[{"description": "Zero-rated item", "quantity": 1, "unit_price": 100.0, "vat_rate": 0}],
        )
        assert doc["taxTotals"][0]["amount"] == 0.0

    def test_b2b_receiver_with_rin(self):
        eta = ETAService(_settings())
        doc = eta.build_invoice_document(
            internal_id="ETA-TEST-0004",
            issued_at_iso="2026-07-01T00:00:00Z",
            receiver_name="Corporate Client",
            receiver_rin="987654321",
            line_items=[{"description": "Conference room", "quantity": 1, "unit_price": 5000.0}],
        )
        assert doc["receiver"]["type"] == "B"
        assert doc["receiver"]["id"] == "987654321"

    def test_none_vat_rate_falls_back_to_settings_default(self):
        """Regression: dict.get('vat_rate', default) doesn't fall back when the
        key exists with value None — model_dump() always includes it as None."""
        eta = ETAService(_settings(VAT_PERCENTAGE=10.0))
        doc = eta.build_invoice_document(
            internal_id="ETA-TEST-0005",
            issued_at_iso="2026-07-01T00:00:00Z",
            receiver_name="Guest",
            receiver_rin=None,
            line_items=[{"description": "Item", "quantity": 1, "unit_price": 100.0, "vat_rate": None}],
        )
        assert doc["taxTotals"][0]["amount"] == pytest.approx(10.0)
