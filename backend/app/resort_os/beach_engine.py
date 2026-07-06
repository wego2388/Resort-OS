"""
beach_engine.py — Pure beach domain logic.
No database, no HTTP framework, no external services.

يُعزل منطق الشاطئ (capacity, towel, surge, B2B) بعيداً عن الـ service layer.
"""
from dataclasses import dataclass
from datetime import date
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
    valid_from: date
    valid_until: date

    def is_valid_on(self, check_date: date) -> bool:
        """True لو ``check_date`` داخل [valid_from, valid_until] العقد."""
        return self.valid_from <= check_date <= self.valid_until

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
    check_date: Optional[date] = None,
) -> BeachValidationResult:
    """تحقق من حصة الفندق قبل تسجيل دخول B2B.

    ⚠️ باج حقيقي كان هنا: التحقق كان بيقتصر على `is_active` بس — عقد فندق
    منتهي فعليًا (valid_until فات معاده من شهور) بس لسه `is_active=True` في
    الداتابيز (محدش رجع يقفله يدويًا) كان يعدّي تسجيل الدخول عادي وبيستهلك
    سعة/فوط حقيقية ويتحاسب الفندق عليه، رغم إن العقد انتهى فعليًا. دلوقتي
    بيتحقق كمان من نافذة الصلاحية (valid_from/valid_until) بالنسبة لتاريخ
    العملية نفسه (مش دايمًا النهاردة، عشان check-in بتاريخ سابق يتحقق صح)."""
    check_date = check_date or date.today()
    if not contract.is_active:
        return BeachValidationResult(False, "عقد الفندق غير نشط")
    if not contract.is_valid_on(check_date):
        return BeachValidationResult(
            False,
            f"عقد {contract.hotel_name} غير سارٍ في هذا التاريخ "
            f"(سارٍ من {contract.valid_from} إلى {contract.valid_until})"
        )
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


# ── Credit limit & dunning (B2B فقط — راجع تعليق B2BContract في models.py) ────

def would_exceed_credit_limit(
    outstanding_balance: Decimal,
    new_charge: Decimal,
    credit_limit: Optional[Decimal],
) -> bool:
    """True لو إضافة ``new_charge`` للرصيد الحالي هتتخطى حد الائتمان.
    ``credit_limit=None`` يعني مفيش حد مضبوط لهذا الفندق — دايمًا False
    (نفس سلوك daily_quota لو contract مفيهوش حد بمعنى "مسموح دايمًا")."""
    if credit_limit is None:
        return False
    return (outstanding_balance + new_charge) > credit_limit


def is_contract_overdue(
    oldest_unsettled_day: Optional[date],
    today: date,
    payment_terms_days: int,
) -> bool:
    """العقد متأخر السداد لو أقدم يوم فيه رصيد غير مسوّى أقدم من مهلة السداد
    (net-N) من النهاردة. ``oldest_unsettled_day=None`` يعني مفيش رصيد غير
    مسوّى خالص (كل حاجة اتسوّت أو العقد لسه ما استخدمش) → مش متأخر."""
    if oldest_unsettled_day is None:
        return False
    return (today - oldest_unsettled_day).days > payment_terms_days


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
