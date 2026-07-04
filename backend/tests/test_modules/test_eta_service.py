"""
tests/test_modules/test_eta_service.py
ETAService — document building (pure logic, no live ETA calls) + config guards
+ HTTP-layer methods (get_access_token/submit_invoice/get_document_status)
against a fake httpx.AsyncClient (no real network calls to ETA's servers,
which aren't reachable/usable from this environment — see module docstring).
"""
from __future__ import annotations

import time

import pytest

from app.core.config import Settings
from app.modules.finance import eta_service as eta_module
from app.modules.finance.eta_service import ETAConfigError, ETAService, ETASubmissionError


class _FakeResponse:
    def __init__(self, status_code: int, json_data: dict | None = None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = str(self._json)

    def json(self):
        return self._json


class _FakeAsyncClient:
    """Records every call made and returns pre-programmed responses in order."""

    calls: list[tuple[str, str, dict]] = []
    post_responses: list[_FakeResponse] = []
    get_responses: list[_FakeResponse] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        type(self).calls.append(("POST", url, kwargs))
        return type(self).post_responses.pop(0)

    async def get(self, url, **kwargs):
        type(self).calls.append(("GET", url, kwargs))
        return type(self).get_responses.pop(0)


@pytest.fixture
def fake_client(monkeypatch):
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.post_responses = []
    _FakeAsyncClient.get_responses = []
    monkeypatch.setattr(eta_module.httpx, "AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


def _settings(**overrides) -> Settings:
    base = {
        "ETA_ENABLED": True,
        "ETA_CLIENT_ID": "test-client",
        "ETA_CLIENT_SECRET": "test-secret",
        "ETA_TAXPAYER_RIN": "123456789",
        "ETA_TAXPAYER_NAME": "Test Resort",
        "VAT_PERCENTAGE": 14.0,
        # strong key so ENVIRONMENT="production" cases pass the SECRET_KEY
        # validator (this test exercises ETA URL selection, not key policy)
        "SECRET_KEY": "Zk9x2Lm7Qw4Tv8Yb1Rn6Pj3Fh5Gd0Sc8Ae2Wu4Io7Kp1Nq9Mz",
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


class TestGetAccessToken:
    async def test_success_returns_token_and_caches_it(self, fake_client):
        fake_client.post_responses = [
            _FakeResponse(200, {"access_token": "abc123", "expires_in": 3600}),
        ]
        eta = ETAService(_settings())
        token = await eta.get_access_token()
        assert token == "abc123"

        # Second call within the cache window must NOT hit the network again.
        token2 = await eta.get_access_token()
        assert token2 == "abc123"
        assert len(fake_client.calls) == 1

    async def test_uses_correct_grant_and_scope_in_request_body(self, fake_client):
        fake_client.post_responses = [
            _FakeResponse(200, {"access_token": "tok", "expires_in": 3600}),
        ]
        eta = ETAService(_settings())
        await eta.get_access_token()
        _method, url, kwargs = fake_client.calls[0]
        assert url == "https://id.preprod.eta.gov.eg/connect/token"
        assert kwargs["data"]["grant_type"] == "client_credentials"
        assert kwargs["data"]["client_id"] == "test-client"
        assert kwargs["data"]["scope"] == "InvoicingAPI"

    async def test_production_environment_uses_production_url(self, fake_client):
        fake_client.post_responses = [
            _FakeResponse(200, {"access_token": "tok", "expires_in": 3600}),
        ]
        eta = ETAService(_settings(ENVIRONMENT="production"))
        await eta.get_access_token()
        _method, url, _kwargs = fake_client.calls[0]
        assert url == "https://id.eta.gov.eg/connect/token"

    async def test_non_200_raises_submission_error(self, fake_client):
        fake_client.post_responses = [_FakeResponse(401, {"error": "invalid_client"})]
        eta = ETAService(_settings())
        with pytest.raises(ETASubmissionError):
            await eta.get_access_token()

    async def test_expired_token_is_refreshed(self, fake_client):
        fake_client.post_responses = [
            _FakeResponse(200, {"access_token": "first-token", "expires_in": 3600}),
            _FakeResponse(200, {"access_token": "second-token", "expires_in": 3600}),
        ]
        eta = ETAService(_settings())
        first = await eta.get_access_token()
        assert first == "first-token"

        # Force the cached token to look expired.
        eta._token_expires_at = time.time() - 1
        second = await eta.get_access_token()
        assert second == "second-token"
        assert len(fake_client.calls) == 2


class TestSubmitInvoice:
    async def test_success_returns_accepted_documents(self, fake_client):
        fake_client.post_responses = [
            _FakeResponse(200, {"access_token": "tok", "expires_in": 3600}),
            _FakeResponse(202, {"acceptedDocuments": [{"uuid": "u-1", "longId": "L1"}]}),
        ]
        eta = ETAService(_settings())
        result = await eta.submit_invoice({"documentType": "I"})
        assert result["acceptedDocuments"][0]["uuid"] == "u-1"
        # Second call in the chain must carry the bearer token from step 1.
        _method, url, kwargs = fake_client.calls[1]
        assert url.endswith("/documentsubmissions")
        assert kwargs["headers"]["Authorization"] == "Bearer tok"

    async def test_rejection_raises_submission_error(self, fake_client):
        fake_client.post_responses = [
            _FakeResponse(200, {"access_token": "tok", "expires_in": 3600}),
            _FakeResponse(400, {"error": "invalid document"}),
        ]
        eta = ETAService(_settings())
        with pytest.raises(ETASubmissionError):
            await eta.submit_invoice({"documentType": "I"})

    async def test_200_status_also_accepted(self, fake_client):
        """ETA's docs list both 200 and 202 as success codes for submission."""
        fake_client.post_responses = [
            _FakeResponse(200, {"access_token": "tok", "expires_in": 3600}),
            _FakeResponse(200, {"acceptedDocuments": [{"uuid": "u-2"}]}),
        ]
        eta = ETAService(_settings())
        result = await eta.submit_invoice({"documentType": "I"})
        assert result["acceptedDocuments"][0]["uuid"] == "u-2"


class TestGetDocumentStatus:
    async def test_success_returns_document_details(self, fake_client):
        fake_client.post_responses = [
            _FakeResponse(200, {"access_token": "tok", "expires_in": 3600}),
        ]
        fake_client.get_responses = [_FakeResponse(200, {"status": "Valid"})]
        eta = ETAService(_settings())
        result = await eta.get_document_status("submission-uuid-1")
        assert result["status"] == "Valid"
        _method, url, kwargs = fake_client.calls[-1]
        assert url.endswith("/documents/submission-uuid-1/details")
        assert kwargs["headers"]["Authorization"] == "Bearer tok"

    async def test_not_found_raises_submission_error(self, fake_client):
        fake_client.post_responses = [
            _FakeResponse(200, {"access_token": "tok", "expires_in": 3600}),
        ]
        fake_client.get_responses = [_FakeResponse(404, {"error": "not found"})]
        eta = ETAService(_settings())
        with pytest.raises(ETASubmissionError):
            await eta.get_document_status("missing-uuid")
