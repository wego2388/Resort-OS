"""
beach_engine.py — Pure beach domain logic.
No database, no HTTP framework, no external services.

يُعزل منطق الشاطئ (capacity, towel, surge, B2B) بعيداً عن الـ service layer.
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


# ── TX types (المصدر الوحيد للحقيقة) ─────────────────────────────────────────
# base_amount:     السعر الافتراضي (يُحدَّث من Settings في DB)
# capacity_delta:  -1 = يستهلك مقعداً | 0 = لا يؤثر
# towel_delta:     -1 = يستهلك فوطة | +1 = يُعيد | 0 = لا فوطة

TX_CONFIG: dict[str, dict] = {
    "entry":          {"base_amount": 200, "capacity_delta": -1, "towel_delta":  0},
    "entry_child":    {"base_amount": 100, "capacity_delta": -1, "towel_delta":  0},
    "entry_resident": {"base_amount": 150, "capacity_delta": -1, "towel_delta":  0},
    "entry_towel":    {"base_amount": 250, "capacity_delta": -1, "towel_delta": -1},
    "towel_rent":     {"base_amount":  50, "capacity_delta":  0, "towel_delta": -1},
    "towel_return":   {"base_amount":   0, "capacity_delta":  0, "towel_delta": +1},
}

TX_TYPES = tuple(TX_CONFIG.keys())


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class BeachInventoryState:
    towels_available: int
    towels_used: int
    capacity_used: int
    capacity_max: int

    @property
    def is_full(self) -> bool:
        return self.capacity_used >= self.capacity_max

    @property
    def available_slots(self) -> int:
        return max(0, self.capacity_max - self.capacity_used)

    @property
    def capacity_pct(self) -> int:
        if self.capacity_max == 0:
            return 100
        return min(100, int(self.capacity_used / self.capacity_max * 100))


@dataclass
class B2BContractState:
    contract_id: int
    hotel_name: str
    daily_quota: int
    checked_in_today: int
    entry_price: Decimal
    towel_price: Decimal
    is_active: bool

    @property
    def remaining_quota(self) -> int:
        return max(0, self.daily_quota - self.checked_in_today)

    @property
    def is_quota_exhausted(self) -> bool:
        return self.checked_in_today >= self.daily_quota

    @property
    def quota_warning(self) -> bool:
        """يُرسل WhatsApp للفندق لما يبقى 5 أشخاص أو أقل."""
        return 0 < self.remaining_quota <= 5


# ── Validation ────────────────────────────────────────────────────────────────

@dataclass
class BeachValidationResult:
    valid: bool
    error: str = ""


def validate_entry(
    state: BeachInventoryState,
    tx_type: str,
    quantity: int = 1,
) -> BeachValidationResult:
    """تحقق قبل أي عملية بيع — يُستدعى قبل كتابة أي شيء في DB."""
    if tx_type not in TX_CONFIG:
        return BeachValidationResult(False, f"نوع العملية غير معروف: {tx_type}")

    cfg = TX_CONFIG[tx_type]

    if cfg["capacity_delta"] < 0:
        needed = abs(cfg["capacity_delta"]) * quantity
        if state.capacity_used + needed > state.capacity_max:
            return BeachValidationResult(
                False,
                f"الشاطئ ممتلئ — السعة القصوى {state.capacity_max} شخص"
            )

    if cfg["towel_delta"] < 0:
        needed_towels = abs(cfg["towel_delta"]) * quantity
        if state.towels_available < needed_towels:
            return BeachValidationResult(
                False,
                f"لا توجد فوط كافية — المتاح {state.towels_available}"
            )

    return BeachValidationResult(True)


def validate_b2b_checkin(
    contract: B2BContractState,
    guests_count: int,
) -> BeachValidationResult:
    """تحقق من حصة الفندق قبل تسجيل دخول B2B."""
    if not contract.is_active:
        return BeachValidationResult(False, "عقد الفندق غير نشط")
    if contract.is_quota_exhausted:
        return BeachValidationResult(
            False,
            f"استُنفدت الحصة اليومية لـ {contract.hotel_name} ({contract.daily_quota} شخص)"
        )
    if contract.checked_in_today + guests_count > contract.daily_quota:
        return BeachValidationResult(
            False,
            f"الحصة المتبقية {contract.remaining_quota} شخص فقط"
        )
    return BeachValidationResult(True)


# ── Price calculation ─────────────────────────────────────────────────────────

def calculate_tx_price(
    tx_type: str,
    base_prices: dict[str, Decimal],
    surge_pct: float = 0.0,
    quantity: int = 1,
) -> Decimal:
    """
    احسب سعر العملية مع الـ surge.
    base_prices: القيم من DB/Settings (تتجاوز TX_CONFIG الافتراضية).
    surge_pct:   مثلاً 50.0 = +50%.
    """
    if tx_type == "towel_return":
        return Decimal("0")

    base = base_prices.get(
        tx_type, Decimal(str(TX_CONFIG[tx_type]["base_amount"]))
    )

    if surge_pct > 0:
        surge_factor = Decimal(str(1 + surge_pct / 100))
        base = (base * surge_factor).quantize(Decimal("1"), ROUND_HALF_UP)

    return base * quantity


def calculate_b2b_price(
    contract: B2BContractState,
    guests_count: int,
    with_towel: bool,
) -> Decimal:
    """إجمالي دخول B2B (دخول + فوط اختياري)."""
    total = contract.entry_price * guests_count
    if with_towel:
        total += contract.towel_price * guests_count
    return total


# ── Inventory deltas ──────────────────────────────────────────────────────────

def calculate_inventory_delta(
    tx_type: str,
    quantity: int = 1,
) -> tuple[int, int]:
    """
    يُرجع (capacity_delta, towel_delta) للعملية.
    يُستخدم في الـ service لتحديث BeachInventory في DB.
    """
    cfg = TX_CONFIG.get(tx_type, {})
    return (
        cfg.get("capacity_delta", 0) * quantity,
        cfg.get("towel_delta", 0) * quantity,
    )
