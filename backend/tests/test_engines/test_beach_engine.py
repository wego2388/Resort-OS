"""
tests/test_engines/test_beach_engine.py
اختبارات كاملة لـ Beach Engine — شاطئ، فوط، B2B، surge pricing
بدون DB، بدون fixtures — pure functions فقط
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.resort_os.beach_engine import (
    TX_CONFIG,
    TX_TYPES,
    B2BContractState,
    BeachInventoryState,
    calculate_b2b_price,
    calculate_inventory_delta,
    calculate_tx_price,
    is_contract_overdue,
    validate_b2b_checkin,
    validate_entry,
    would_exceed_credit_limit,
)


# ─── Helpers ──────────────────────────────────────────────────────────

def _state(
    towels_available: int = 100,
    towels_used: int = 0,
    capacity_used: int = 0,
    capacity_max: int = 200,
) -> BeachInventoryState:
    return BeachInventoryState(
        towels_available=towels_available,
        towels_used=towels_used,
        capacity_used=capacity_used,
        capacity_max=capacity_max,
    )


def _b2b(
    contract_id: int = 1,
    hotel_name: str = "Hilton",
    daily_quota: int = 50,
    checked_in_today: int = 0,
    entry_price: Decimal = Decimal("150"),
    towel_price: Decimal = Decimal("50"),
    is_active: bool = True,
    valid_from: date = date(2000, 1, 1),
    valid_until: date = date(2099, 12, 31),
) -> B2BContractState:
    return B2BContractState(
        contract_id=contract_id,
        hotel_name=hotel_name,
        daily_quota=daily_quota,
        checked_in_today=checked_in_today,
        entry_price=entry_price,
        towel_price=towel_price,
        is_active=is_active,
        valid_from=valid_from,
        valid_until=valid_until,
    )


def _base_prices() -> dict[str, Decimal]:
    return {
        "entry":       Decimal("200"),
        "entry_towel": Decimal("250"),
        "towel_rent":  Decimal("50"),
    }


# ─── BeachInventoryState Properties ──────────────────────────────────

class TestBeachInventoryStateProperties:

    def test_not_full(self):
        assert _state(capacity_used=100, capacity_max=200).is_full is False

    def test_exactly_full(self):
        assert _state(capacity_used=200, capacity_max=200).is_full is True

    def test_over_capacity(self):
        """فوق الطاقة (حالة طارئة) → is_full"""
        assert _state(capacity_used=201, capacity_max=200).is_full is True

    def test_available_slots(self):
        s = _state(capacity_used=150, capacity_max=200)
        assert s.available_slots == 50

    def test_available_slots_zero_when_full(self):
        s = _state(capacity_used=200, capacity_max=200)
        assert s.available_slots == 0

    def test_available_slots_never_negative(self):
        s = _state(capacity_used=210, capacity_max=200)
        assert s.available_slots == 0

    def test_capacity_pct_zero(self):
        assert _state(capacity_used=0, capacity_max=100).capacity_pct == 0

    def test_capacity_pct_fifty(self):
        assert _state(capacity_used=50, capacity_max=100).capacity_pct == 50

    def test_capacity_pct_full(self):
        assert _state(capacity_used=100, capacity_max=100).capacity_pct == 100

    def test_capacity_pct_capped_at_100(self):
        assert _state(capacity_used=110, capacity_max=100).capacity_pct == 100

    def test_capacity_pct_zero_max(self):
        """capacity_max=0 → لا نقسم على صفر"""
        s = BeachInventoryState(0, 0, 0, 0)
        assert s.capacity_pct == 100


# ─── B2BContractState Properties ─────────────────────────────────────

class TestB2BContractStateProperties:

    def test_remaining_quota(self):
        assert _b2b(daily_quota=50, checked_in_today=20).remaining_quota == 30

    def test_remaining_quota_zero_when_exhausted(self):
        assert _b2b(daily_quota=50, checked_in_today=50).remaining_quota == 0

    def test_remaining_quota_never_negative(self):
        assert _b2b(daily_quota=50, checked_in_today=60).remaining_quota == 0

    def test_quota_not_exhausted(self):
        assert _b2b(checked_in_today=49, daily_quota=50).is_quota_exhausted is False

    def test_quota_exhausted(self):
        assert _b2b(checked_in_today=50, daily_quota=50).is_quota_exhausted is True

    def test_quota_warning_at_threshold(self):
        """5 أشخاص متبقين → warning"""
        assert _b2b(daily_quota=50, checked_in_today=45).quota_warning is True

    def test_quota_warning_more_than_5(self):
        assert _b2b(daily_quota=50, checked_in_today=44).quota_warning is False

    def test_quota_warning_exhausted(self):
        """صفر متبقي → لا warning (quota_warning = 0 < remaining ≤ 5)"""
        assert _b2b(daily_quota=50, checked_in_today=50).quota_warning is False


# ─── validate_entry ───────────────────────────────────────────────────

class TestValidateEntry:

    def test_valid_entry_passes(self):
        result = validate_entry(_state(), "entry")
        assert result.valid is True

    def test_valid_entry_with_towel(self):
        result = validate_entry(_state(towels_available=5), "entry_towel")
        assert result.valid is True

    def test_invalid_tx_type(self):
        result = validate_entry(_state(), "vip_entry")
        assert result.valid is False
        assert "vip_entry" in result.error

    def test_beach_full_blocks_entry(self):
        full_state = _state(capacity_used=200, capacity_max=200)
        result = validate_entry(full_state, "entry")
        assert result.valid is False
        assert "200" in result.error

    def test_beach_full_blocks_entry_with_towel(self):
        full_state = _state(capacity_used=200, capacity_max=200)
        result = validate_entry(full_state, "entry_towel")
        assert result.valid is False

    def test_towel_rent_no_capacity_check(self):
        """towel_rent لا يستهلك مقعداً — يمر حتى لو الشاطئ ممتلئ"""
        full_state = _state(capacity_used=200, capacity_max=200)
        result = validate_entry(_state(towels_available=5), "towel_rent")
        assert result.valid is True

    def test_no_towels_blocks_towel_transaction(self):
        empty_towels = _state(towels_available=0)
        result = validate_entry(empty_towels, "entry_towel")
        assert result.valid is False
        assert "0" in result.error

    def test_no_towels_blocks_towel_rent(self):
        empty_towels = _state(towels_available=0)
        result = validate_entry(empty_towels, "towel_rent")
        assert result.valid is False

    def test_towel_return_always_valid(self):
        """إرجاع الفوطة دائماً صحيح"""
        result = validate_entry(_state(), "towel_return")
        assert result.valid is True

    def test_quantity_multiple_entries(self):
        """4 دخلات في شاطئ سعته 3 → ممتلئ"""
        state = _state(capacity_used=0, capacity_max=3)
        result = validate_entry(state, "entry", quantity=4)
        assert result.valid is False

    def test_quantity_exactly_fills_capacity(self):
        state = _state(capacity_used=0, capacity_max=5)
        result = validate_entry(state, "entry", quantity=5)
        assert result.valid is True

    def test_all_valid_tx_types_pass_normal_state(self):
        state = _state(towels_available=100, capacity_used=0, capacity_max=200)
        for tx in TX_TYPES:
            result = validate_entry(state, tx)
            assert result.valid is True, f"Expected valid for tx: {tx}"


# ─── validate_b2b_checkin ─────────────────────────────────────────────

class TestValidateB2bCheckin:

    def test_valid_checkin(self):
        result = validate_b2b_checkin(_b2b(daily_quota=50, checked_in_today=10), 5)
        assert result.valid is True

    def test_inactive_contract_blocked(self):
        result = validate_b2b_checkin(_b2b(is_active=False), 2)
        assert result.valid is False
        assert "غير نشط" in result.error

    def test_quota_exhausted_blocked(self):
        result = validate_b2b_checkin(_b2b(daily_quota=50, checked_in_today=50), 1)
        assert result.valid is False
        assert "50" in result.error

    def test_exceeds_remaining_quota(self):
        """10 متبقين، يطلب 15 → ممنوع"""
        result = validate_b2b_checkin(
            _b2b(daily_quota=50, checked_in_today=40), guests_count=15
        )
        assert result.valid is False
        assert "10" in result.error

    def test_exactly_fills_quota(self):
        result = validate_b2b_checkin(
            _b2b(daily_quota=50, checked_in_today=40), guests_count=10
        )
        assert result.valid is True

    def test_expired_contract_blocked(self):
        """باج حقيقي كان هنا: عقد فندق منتهي (valid_until فات) بس لسه
        is_active=True كان يعدّي تسجيل الدخول عادي — دلوقتي بيترفض حتى لو
        is_active=True."""
        expired = _b2b(
            valid_from=date(2025, 1, 1), valid_until=date(2025, 12, 31),
        )
        result = validate_b2b_checkin(expired, guests_count=1, check_date=date(2026, 7, 6))
        assert result.valid is False
        assert "غير سارٍ" in result.error

    def test_not_yet_started_contract_blocked(self):
        """عقد لسه ماوصلش تاريخ valid_from — نفس المنطق بالظبط."""
        future = _b2b(
            valid_from=date(2027, 1, 1), valid_until=date(2027, 12, 31),
        )
        result = validate_b2b_checkin(future, guests_count=1, check_date=date(2026, 7, 6))
        assert result.valid is False
        assert "غير سارٍ" in result.error

    def test_contract_valid_on_boundary_dates(self):
        """أول وآخر يوم في نافذة الصلاحية لازم يعدّوا (inclusive boundaries)."""
        contract = _b2b(valid_from=date(2026, 1, 1), valid_until=date(2026, 12, 31))
        assert validate_b2b_checkin(contract, 1, check_date=date(2026, 1, 1)).valid is True
        assert validate_b2b_checkin(contract, 1, check_date=date(2026, 12, 31)).valid is True
        assert validate_b2b_checkin(contract, 1, check_date=date(2027, 1, 1)).valid is False

    def test_inactive_takes_priority_over_date_message(self):
        """لو العقد غير نشط ومنتهي مع بعض، رسالة 'غير نشط' هي اللي تظهر أولاً."""
        result = validate_b2b_checkin(
            _b2b(is_active=False, valid_from=date(2025, 1, 1), valid_until=date(2025, 12, 31)),
            guests_count=1, check_date=date(2026, 7, 6),
        )
        assert result.valid is False
        assert "غير نشط" in result.error


# ─── calculate_tx_price ───────────────────────────────────────────────

class TestCalculateTxPrice:

    def test_entry_base_price(self):
        result = calculate_tx_price("entry", _base_prices(), surge_pct=0.0)
        assert result == Decimal("200")

    def test_entry_towel_base_price(self):
        result = calculate_tx_price("entry_towel", _base_prices(), surge_pct=0.0)
        assert result == Decimal("250")

    def test_towel_return_always_zero(self):
        result = calculate_tx_price("towel_return", _base_prices(), surge_pct=50.0)
        assert result == Decimal("0")

    def test_surge_50_pct(self):
        """200 × 1.5 = 300"""
        result = calculate_tx_price("entry", _base_prices(), surge_pct=50.0)
        assert result == Decimal("300")

    def test_surge_100_pct_doubles_price(self):
        result = calculate_tx_price("entry", _base_prices(), surge_pct=100.0)
        assert result == Decimal("400")

    def test_zero_surge_no_change(self):
        result = calculate_tx_price("entry", _base_prices(), surge_pct=0.0)
        assert result == Decimal("200")

    def test_quantity_multiplied(self):
        result = calculate_tx_price("entry", _base_prices(), surge_pct=0.0, quantity=3)
        assert result == Decimal("600")

    def test_quantity_with_surge(self):
        """200 × 1.5 × 3 = 900"""
        result = calculate_tx_price("entry", _base_prices(), surge_pct=50.0, quantity=3)
        assert result == Decimal("900")

    def test_falls_back_to_tx_config_defaults(self):
        """بدون base_prices → يستخدم TX_CONFIG الافتراضي"""
        result = calculate_tx_price("entry", {}, surge_pct=0.0)
        assert result == Decimal(str(TX_CONFIG["entry"]["base_amount"]))


# ─── calculate_b2b_price ─────────────────────────────────────────────

class TestCalculateB2bPrice:

    def test_entry_only(self):
        contract = _b2b(entry_price=Decimal("150"), towel_price=Decimal("50"))
        result = calculate_b2b_price(contract, guests_count=3, with_towel=False)
        assert result == Decimal("450")  # 150 × 3

    def test_entry_with_towel(self):
        contract = _b2b(entry_price=Decimal("150"), towel_price=Decimal("50"))
        result = calculate_b2b_price(contract, guests_count=3, with_towel=True)
        assert result == Decimal("600")  # (150+50) × 3

    def test_single_guest_no_towel(self):
        contract = _b2b(entry_price=Decimal("200"), towel_price=Decimal("60"))
        result = calculate_b2b_price(contract, guests_count=1, with_towel=False)
        assert result == Decimal("200")

    def test_zero_guests(self):
        contract = _b2b(entry_price=Decimal("200"))
        result = calculate_b2b_price(contract, guests_count=0, with_towel=False)
        assert result == Decimal("0")


# ─── calculate_inventory_delta ────────────────────────────────────────

class TestCalculateInventoryDelta:

    def test_entry_consumes_capacity(self):
        cap_delta, towel_delta = calculate_inventory_delta("entry", quantity=1)
        assert cap_delta == -1
        assert towel_delta == 0

    def test_entry_towel_consumes_both(self):
        cap_delta, towel_delta = calculate_inventory_delta("entry_towel", quantity=1)
        assert cap_delta == -1
        assert towel_delta == -1

    def test_towel_rent_only_towel(self):
        cap_delta, towel_delta = calculate_inventory_delta("towel_rent", quantity=1)
        assert cap_delta == 0
        assert towel_delta == -1

    def test_towel_return_increases_towels(self):
        cap_delta, towel_delta = calculate_inventory_delta("towel_return", quantity=1)
        assert cap_delta == 0
        assert towel_delta == +1

    def test_quantity_multiplies_delta(self):
        cap_delta, towel_delta = calculate_inventory_delta("entry_towel", quantity=4)
        assert cap_delta == -4
        assert towel_delta == -4

    def test_unknown_tx_returns_zero_delta(self):
        cap_delta, towel_delta = calculate_inventory_delta("unknown_type")
        assert cap_delta == 0
        assert towel_delta == 0


class TestCreditLimit:
    """B2B partner-hotel credit control — راجع ملحوظة B2BContract في
    app/modules/beach/models.py: عقود B2B علاقة ائتمانية متكررة، مش كاش
    فوري، وده أول ضبط ائتماني حقيقي في المشروع كله (finance/crm/beach)."""

    def test_no_limit_never_exceeded(self):
        assert would_exceed_credit_limit(Decimal("100000"), Decimal("500"), None) is False

    def test_within_limit_ok(self):
        assert would_exceed_credit_limit(Decimal("1000"), Decimal("500"), Decimal("2000")) is False

    def test_exactly_at_limit_ok(self):
        """الحد نفسه مسموح — الرفض بس لو *تخطّاه* فعليًا (> مش >=)."""
        assert would_exceed_credit_limit(Decimal("1500"), Decimal("500"), Decimal("2000")) is False

    def test_over_limit_rejected(self):
        assert would_exceed_credit_limit(Decimal("1800"), Decimal("500"), Decimal("2000")) is True

    def test_already_over_limit_before_new_charge(self):
        assert would_exceed_credit_limit(Decimal("2500"), Decimal("1"), Decimal("2000")) is True


class TestContractOverdue:
    """راجع ملحوظة B2BContract: مهلة سداد net-N — العقد متأخر لو أقدم يوم
    فيه رصيد غير مسوّى أقدم من المهلة."""

    def test_no_unsettled_day_never_overdue(self):
        assert is_contract_overdue(None, date(2026, 7, 6), 30) is False

    def test_within_terms_not_overdue(self):
        today = date(2026, 7, 6)
        oldest = today - timedelta(days=29)
        assert is_contract_overdue(oldest, today, 30) is False

    def test_exactly_at_terms_not_overdue(self):
        today = date(2026, 7, 6)
        oldest = today - timedelta(days=30)
        assert is_contract_overdue(oldest, today, 30) is False

    def test_past_terms_overdue(self):
        today = date(2026, 7, 6)
        oldest = today - timedelta(days=31)
        assert is_contract_overdue(oldest, today, 30) is True
