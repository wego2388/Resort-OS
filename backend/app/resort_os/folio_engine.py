"""
folio_engine.py — Pure folio domain logic.
No database, no HTTP framework, no external services.

الـ Folio هو مركز ثقل النظام — كل charge من أي module يمر هنا.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


CHARGE_TYPES = (
    "room", "restaurant", "cafe", "beach",
    "activity", "minibar", "spa", "laundry", "other",
)

CHARGE_LABELS_AR = {
    "room":       "إقامة",
    "restaurant": "مطعم",
    "cafe":       "كافيه",
    "beach":      "شاطئ",
    "activity":   "أنشطة",
    "minibar":    "ميني بار",
    "spa":        "سبا",
    "laundry":    "غسيل",
    "other":      "متنوع",
}


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class FolioChargeItem:
    charge_type: str
    description: str
    amount: Decimal
    vat_amount: Decimal
    posted_at: datetime
    ref_order_id: Optional[int] = None
    ref_beach_tx_id: Optional[int] = None
    is_settled: bool = False
    service_charge: Decimal = Decimal("0")


@dataclass
class FolioSummary:
    folio_id: int
    guest_name: str
    check_in: datetime
    check_out: datetime
    is_checked_out: bool
    charges: list[FolioChargeItem] = field(default_factory=list)

    @property
    def total_amount(self) -> Decimal:
        return sum(c.amount for c in self.charges)

    @property
    def total_vat(self) -> Decimal:
        return sum(c.vat_amount for c in self.charges)

    @property
    def total_service_charge(self) -> Decimal:
        return sum(c.service_charge for c in self.charges)

    @property
    def total_with_vat(self) -> Decimal:
        return self.total_amount + self.total_vat + self.total_service_charge

    @property
    def unsettled_amount(self) -> Decimal:
        return sum(
            c.amount + c.vat_amount + c.service_charge
            for c in self.charges
            if not c.is_settled
        )

    @property
    def by_type(self) -> dict[str, Decimal]:
        result: dict[str, Decimal] = {}
        for c in self.charges:
            result[c.charge_type] = result.get(c.charge_type, Decimal("0")) + c.amount
        return result


# ── Validation ────────────────────────────────────────────────────────────────

@dataclass
class FolioValidationResult:
    valid: bool
    error: str = ""


def validate_charge(
    folio: FolioSummary,
    charge_type: str,
    amount: Decimal,
) -> FolioValidationResult:
    """
    تحقق قبل إضافة أي charge.
    القاعدة الحرجة: الفوليو read-only بعد checkout.
    """
    if folio.is_checked_out:
        return FolioValidationResult(
            False,
            "الفوليو مغلق بعد الـ checkout — استخدم Credit Note للتصحيح"
        )
    if charge_type not in CHARGE_TYPES:
        return FolioValidationResult(False, f"نوع charge غير معروف: {charge_type}")
    if amount <= Decimal("0"):
        return FolioValidationResult(False, "قيمة الـ charge يجب أن تكون موجبة")
    return FolioValidationResult(True)


def can_checkout(folio: FolioSummary) -> FolioValidationResult:
    """هل يمكن checkout؟ — يجب تسوية كل الـ charges."""
    if folio.is_checked_out:
        return FolioValidationResult(False, "الفوليو مغلق مسبقاً")
    if folio.unsettled_amount > Decimal("0"):
        return FolioValidationResult(
            False,
            f"يوجد {folio.unsettled_amount:.2f} جنيه غير مسدد"
        )
    return FolioValidationResult(True)


# ── Calculation helpers ───────────────────────────────────────────────────────

def calculate_vat(amount: Decimal, vat_pct: float = 14.0) -> Decimal:
    return (amount * Decimal(str(vat_pct / 100))).quantize(
        Decimal("0.01"), ROUND_HALF_UP
    )


def build_receipt_lines(folio: FolioSummary, vat_pct: float = 14.0) -> list[dict]:
    """سطور الإيصال النهائي مجمّعة بالنوع — للطباعة أو الفاتورة."""
    lines = []
    for charge_type, total in folio.by_type.items():
        vat = calculate_vat(total, vat_pct)
        lines.append({
            "label":  CHARGE_LABELS_AR.get(charge_type, charge_type),
            "amount": total,
            "vat":    vat,
            "total":  total + vat,
        })
    return lines
