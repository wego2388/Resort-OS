"""
beach_engine.py — Pure beach domain logic.
No database, no HTTP framework, no external services.

يُعزل منطق الشاطئ (capacity, towel, surge, B2B) بعيداً عن الـ service layer.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


# ── Daily capacity setting ────────────────────────────────────────────────────

BEACH_CAPACITY_SETTING_KEY = "beach.capacity_max"
DEFAULT_BEACH_CAPACITY_MAX = 200
# Operational guard, not a commercial assumption: keeps a malformed setting
# within PostgreSQL Integer and prevents accidental multi-million-entry limits.
BEACH_CAPACITY_MAX_LIMIT = 100_000


def parse_beach_capacity_max(value: object) -> int:
    """Parse the typed daily-capacity setting or reject it explicitly."""
    if isinstance(value, bool):
        raise ValueError("سعة الشاطئ لازم تكون رقمًا صحيحًا موجبًا")
    raw = str(value).strip()
    if not raw or not raw.isascii() or not raw.isdecimal():
        raise ValueError("سعة الشاطئ لازم تكون رقمًا صحيحًا موجبًا")
    parsed = int(raw)
    if parsed < 1 or parsed > BEACH_CAPACITY_MAX_LIMIT:
        raise ValueError(
            f"سعة الشاطئ لازم تكون بين 1 و{BEACH_CAPACITY_MAX_LIMIT:,} شخص"
        )
    return parsed


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
    """2026-08-20، طلب Mohamed صراحةً — نموذج "مبلغ شهري ثابت + حد أقصى
    استرشادي" بدل "سعر لكل ضيف × حصة يومية" القديم. ``monthly_guest_cap``
    مش حد رفض — تخطيه مسموح صراحةً (قرار Mohamed)، بيولّد بس تنبيه واحد
    للفندق (راجع quota_warning) زي تحذير الحصة القديم بالظبط."""
    contract_id: int
    hotel_name: str
    monthly_guest_cap: int
    checked_in_this_month: int
    monthly_fee: Decimal
    is_active: bool
    valid_from: date
    valid_until: date

    def is_valid_on(self, check_date: date) -> bool:
        """True لو ``check_date`` داخل [valid_from, valid_until] العقد."""
        return self.valid_from <= check_date <= self.valid_until

    @property
    def remaining_monthly_quota(self) -> int:
        return max(0, self.monthly_guest_cap - self.checked_in_this_month)

    @property
    def quota_warning(self) -> bool:
        """يُرسل WhatsApp للفندق لما يبقى 5 أشخاص أو أقل من الحد الشهري —
        تنبيه بس، مش رفض (تخطي الحد مسموح صراحةً)."""
        return 0 < self.remaining_monthly_quota <= 5


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
    check_date: Optional[date] = None,
) -> BeachValidationResult:
    """تحقق من صلاحية عقد الفندق قبل تسجيل دخول B2B — الحد الشهري (2026-08-20)
    مش جزء من التحقق ده خالص: تخطي الحد مسموح صراحةً (قرار Mohamed)، فمفيش
    رفض بسببه هنا — بس تنبيه واتساب منفصل (راجع services.b2b_checkin).

    ⚠️ باج حقيقي كان هنا: التحقق كان بيقتصر على `is_active` بس — عقد فندق
    منتهي فعليًا (valid_until فات معاده من شهور) بس لسه `is_active=True` في
    الداتابيز (محدش رجع يقفله يدويًا) كان يعدّي تسجيل الدخول عادي وبيستهلك
    سعة/فوط حقيقية، رغم إن العقد انتهى فعليًا. دلوقتي بيتحقق كمان من نافذة
    الصلاحية (valid_from/valid_until) بالنسبة لتاريخ العملية نفسه (مش دايمًا
    النهاردة، عشان check-in بتاريخ سابق يتحقق صح)."""
    check_date = check_date or date.today()
    if not contract.is_active:
        return BeachValidationResult(False, "عقد الفندق غير نشط")
    if not contract.is_valid_on(check_date):
        return BeachValidationResult(
            False,
            f"عقد {contract.hotel_name} غير سارٍ في هذا التاريخ "
            f"(سارٍ من {contract.valid_from} إلى {contract.valid_until})"
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


# ── Dunning (تأخر السداد — B2B فقط، راجع تعليق B2BContract في models.py) ──

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
