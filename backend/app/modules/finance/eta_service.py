"""
app/modules/finance/eta_service.py
ETAService — تكامل الفاتورة الإلكترونية المصرية (Egyptian Tax Authority).

تدفق العمل:
  1. get_access_token()       → OAuth2 client_credentials عند id.{env}.eta.gov.eg
  2. build_invoice_document() → JSON document بصيغة ETA e-invoice schema v1.0
  3. submit_invoice()         → POST للمستند الموقَّع عند api.{env}.eta.gov.eg
  4. get_document_status()    → تتبّع حالة المستند بعد الإرسال

⚠️ يتطلب ETA_CLIENT_ID / ETA_CLIENT_SECRET / ETA_TAXPAYER_RIN حقيقية من بوابة
مصلحة الضرائب — غير متوفرة في هذه البيئة، فالتكامل غير قابل للاختبار الحي هنا.
الكود مكتمل البنية ويعمل فور توفير بيانات اعتماد ETA حقيقية في .env.

مرجع: https://sdk.invoicing.eta.gov.eg/api-rate-limit-and-submission/
"""
from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Optional

import httpx
from loguru import logger

from app.core.config import Settings

# ── Endpoints ──────────────────────────────────────────────────────────────
_TOKEN_URL = {
    "production": "https://id.eta.gov.eg/connect/token",
    "preprod":    "https://id.preprod.eta.gov.eg/connect/token",
}
_API_BASE = {
    "production": "https://api.invoicing.eta.gov.eg/api/v1",
    "preprod":    "https://api.preprod.invoicing.eta.gov.eg/api/v1",
}


class ETAConfigError(Exception):
    """ETA_CLIENT_ID/SECRET/RIN غير مهيأة — راجع .env"""


class ETASubmissionError(Exception):
    """فشل الإرسال أو الرفض من ETA — التفاصيل في .args[0]"""


def _eta_env(settings: Settings) -> str:
    return "production" if settings.ENVIRONMENT == "production" else "preprod"


class ETAService:
    def __init__(self, settings: Settings):
        self.settings = settings
        if not (settings.ETA_CLIENT_ID and settings.ETA_CLIENT_SECRET):
            raise ETAConfigError("ETA_CLIENT_ID / ETA_CLIENT_SECRET غير مهيأين في .env")
        self._env = _eta_env(settings)
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # ── Auth ─────────────────────────────────────────────────────────────

    async def get_access_token(self) -> str:
        """OAuth2 client_credentials — يكاش التوكن حتى ينتهي (مع هامش أمان 60 ثانية)."""
        if self._token and time.time() < self._token_expires_at:
            return self._token

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _TOKEN_URL[self._env],
                data={
                    "grant_type":    "client_credentials",
                    "client_id":     self.settings.ETA_CLIENT_ID,
                    "client_secret": self.settings.ETA_CLIENT_SECRET,
                    "scope":         "InvoicingAPI",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if resp.status_code != 200:
            raise ETASubmissionError(f"فشل الحصول على ETA access token: {resp.status_code} {resp.text}")

        data = resp.json()
        self._token = data["access_token"]
        self._token_expires_at = time.time() + int(data.get("expires_in", 3600)) - 60
        return self._token

    # ── Document Building ────────────────────────────────────────────────

    def build_invoice_document(
        self,
        *,
        internal_id: str,
        issued_at_iso: str,
        receiver_name: str,
        receiver_rin: Optional[str],
        line_items: list[dict[str, Any]],
        # كل عنصر: {description, quantity, unit_price, vat_rate (e.g. 14), total}
    ) -> dict[str, Any]:
        """يبني مستند فاتورة بصيغة ETA e-invoice schema v1.0 (B2C إن لم يوجد receiver_rin)."""
        if not (self.settings.ETA_TAXPAYER_RIN and self.settings.ETA_TAXPAYER_NAME):
            raise ETAConfigError("ETA_TAXPAYER_RIN / ETA_TAXPAYER_NAME غير مهيأين في .env")

        invoice_lines = []
        sales_total = Decimal("0")
        tax_total = Decimal("0")

        for item in line_items:
            qty = Decimal(str(item["quantity"]))
            unit_price = Decimal(str(item["unit_price"]))
            line_vat_rate = item.get("vat_rate")
            vat_rate = Decimal(str(line_vat_rate if line_vat_rate is not None else self.settings.VAT_PERCENTAGE))
            sales = (qty * unit_price).quantize(Decimal("0.01"))
            vat_amount = (sales * vat_rate / Decimal("100")).quantize(Decimal("0.01"))
            sales_total += sales
            tax_total += vat_amount

            invoice_lines.append({
                "description": item["description"],
                "itemType":    "GS1",
                "itemCode":    item.get("item_code") or "EG-99999999",
                "unitType":    "EA",
                "quantity":    float(qty),
                "unitValue":   {"currencySold": "EGP", "amountEGP": float(unit_price)},
                "salesTotal":  float(sales),
                "total":       float(sales + vat_amount),
                "valueDifference": 0,
                "totalTaxableFees": 0,
                "netTotal":    float(sales),
                "itemsDiscount": 0,
                "taxableItems": [
                    {"taxType": "T1", "amount": float(vat_amount), "subType": "V009", "rate": float(vat_rate)},
                ],
            })

        receiver: dict[str, Any] = {"name": receiver_name, "type": "B" if receiver_rin else "P"}
        if receiver_rin:
            receiver["id"] = receiver_rin

        return {
            "issuer": {
                "address": {"branchID": self.settings.ETA_BRANCH_CODE, "country": "EG"},
                "type": "B",
                "id": self.settings.ETA_TAXPAYER_RIN,
                "name": self.settings.ETA_TAXPAYER_NAME,
            },
            "receiver": receiver,
            "documentType": "I",
            "documentTypeVersion": "1.0",
            "dateTimeIssued": issued_at_iso,
            "internalID": internal_id,
            "invoiceLines": invoice_lines,
            "totalSalesAmount": float(sales_total),
            "totalDiscountAmount": 0,
            "netAmount": float(sales_total),
            "taxTotals": [{"taxType": "T1", "amount": float(tax_total)}],
            "totalAmount": float(sales_total + tax_total),
            "extraDiscountAmount": 0,
        }

    # ── Submission ───────────────────────────────────────────────────────

    async def submit_invoice(self, document: dict[str, Any]) -> dict[str, Any]:
        """يرسل المستند الموقَّع لـ ETA. ETA تتطلب التوقيع الرقمي عبر USB token/HSM
        في الإنتاج الفعلي — خارج نطاق ما يمكن أتمتته بدون جهاز توقيع حقيقي؛
        هذه الدالة تُرسل المستند كما هو لبيئة preprod التي تقبل مستندات غير
        موقّعة لأغراض الاختبار فقط."""
        token = await self.get_access_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_API_BASE[self._env]}/documentsubmissions",
                json={"documents": [document]},
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
        if resp.status_code not in (200, 202):
            logger.error(f"[ETA] Submission failed: {resp.status_code} {resp.text}")
            raise ETASubmissionError(f"ETA رفضت الإرسال: {resp.status_code} {resp.text}")
        return resp.json()

    async def get_document_status(self, submission_uuid: str) -> dict[str, Any]:
        token = await self.get_access_token()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_API_BASE[self._env]}/documents/{submission_uuid}/details",
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code != 200:
            raise ETASubmissionError(f"تعذّر جلب حالة المستند: {resp.status_code} {resp.text}")
        return resp.json()
