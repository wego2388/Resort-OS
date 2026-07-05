"""
tests/test_api/test_beach.py
Integration tests for beach module — sell tickets, B2B, reservations, surge.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.modules.beach import crud, services
from app.modules.beach.schemas import (
    B2BCheckinRequest,
    B2BContractCreate,
    BeachReservationCreate,
    BeachSellRequest,
)


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(
        name=f"Beach Branch {uuid.uuid4().hex[:6]}",
        name_ar="شاطئ",
        code=f"BCH-{uuid.uuid4().hex[:8].upper()}",
    )
    db.add(b)
    db.commit()
    return b


def make_contract(db, branch, quota=10, entry_price=Decimal("80"), towel_price=Decimal("30")):
    today = date.today()
    data = B2BContractCreate(
        branch_id=branch.id,
        hotel_name=f"Hotel {uuid.uuid4().hex[:6]}",
        daily_quota=quota,
        entry_price=entry_price,
        towel_price=towel_price,
        valid_from=today - timedelta(days=1),
        valid_until=today + timedelta(days=30),
        is_active=True,
    )
    obj = crud.create_b2b_contract(db, data)
    db.commit()
    return obj


class TestBeachInventory:

    def test_get_or_create_inventory(self, db):
        branch = make_branch(db)
        inv = crud.get_or_create_inventory(db, branch.id, date.today())
        db.commit()
        assert inv.id is not None
        assert inv.capacity_max == 200
        assert inv.towels_available == 200

    def test_idempotent_inventory_creation(self, db):
        branch = make_branch(db)
        today = date.today()
        inv1 = crud.get_or_create_inventory(db, branch.id, today)
        db.commit()
        inv2 = crud.get_or_create_inventory(db, branch.id, today)
        db.commit()
        assert inv1.id == inv2.id

    def test_auto_surge_at_80_pct(self, db):
        branch = make_branch(db)
        today = date.today()
        inv = crud.get_or_create_inventory(db, branch.id, today, capacity_max=10, towels_total=20)
        # فعّل capacity_used إلى 8 (80%)
        inv.capacity_used = 8
        db.flush()
        # استهلك مقعداً واحداً آخر — يجب أن يُفعَّل surge تلقائياً
        crud.apply_inventory_delta(db, inv, capacity_delta=-1, towel_delta=0)
        db.commit()
        assert inv.surge_pct > 0

    def test_no_surge_below_80_pct(self, db):
        branch = make_branch(db)
        today = date.today()
        inv = crud.get_or_create_inventory(db, branch.id, today, capacity_max=10, towels_total=20)
        inv.capacity_used = 5
        db.flush()
        crud.apply_inventory_delta(db, inv, capacity_delta=-1, towel_delta=0)
        db.commit()
        assert inv.surge_pct == Decimal("0")


class TestSellTicket:

    def test_sell_adult_entry(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.id is not None
        assert tx.tx_type == "entry"
        assert tx.quantity == 1
        assert tx.unit_price > 0
        assert tx.total_amount > 0

    def test_sell_uses_branch_configured_price_not_hardcoded_default(self, db):
        """باج حقيقي اتصلح 2026-07-03: _get_base_prices كانت بتحاول تبني
        Decimal من صف Setting كامل (ORM object) مباشرة بدل .value بتاعه —
        ده كان بيرمي استثناء دايمًا لما فيه إعداد فعلي محفوظ، والـ
        `except Exception` كان بيبلعه ويرجّع القيم الافتراضية الجاهزة
        (200/100/150/50) دايمًا. يعني أي سعر شاطئ يتظبط من الإعدادات كان
        بيتجاهل تمامًا وقت البيع الحقيقي."""
        from app.modules.core.crud import upsert_setting
        branch = make_branch(db)
        upsert_setting(db, "beach.price.adult", "999", branch_id=branch.id)
        db.commit()

        req = BeachSellRequest(tx_type="entry", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.unit_price == Decimal("999")

    def test_sell_child_entry(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry_child", quantity=2)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.tx_type == "entry_child"
        assert tx.quantity == 2

    def test_sell_resident_entry(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry_resident", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.tx_type == "entry_resident"

    def test_sell_entry_with_towel(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry_towel", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.tx_type == "entry_towel"
        # يجب أن السعر أعلى من entry عادي
        req_entry = BeachSellRequest(tx_type="entry", quantity=1)
        tx_entry = services.sell_ticket(db, branch.id, req_entry)
        assert tx.unit_price > tx_entry.unit_price

    def test_sell_towel_rent(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="towel_rent", quantity=3)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.tx_type == "towel_rent"
        assert tx.quantity == 3

    def test_inventory_updated_after_sale(self, db):
        branch = make_branch(db)
        inv_before = crud.get_or_create_inventory(db, branch.id, date.today())
        db.commit()
        used_before = inv_before.capacity_used

        req = BeachSellRequest(tx_type="entry", quantity=2)
        services.sell_ticket(db, branch.id, req)

        db.refresh(inv_before)
        assert inv_before.capacity_used == used_before + 2

    def test_towel_inventory_decreases(self, db):
        branch = make_branch(db)
        inv = crud.get_or_create_inventory(db, branch.id, date.today())
        db.commit()
        towels_before = inv.towels_available

        req = BeachSellRequest(tx_type="entry_towel", quantity=1)
        services.sell_ticket(db, branch.id, req)

        db.refresh(inv)
        assert inv.towels_available == towels_before - 1

    def test_vat_applied(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.vat_amount >= Decimal("0")

    def test_full_capacity_raises(self, db):
        branch = make_branch(db)
        today = date.today()
        inv = crud.get_or_create_inventory(db, branch.id, today, capacity_max=2, towels_total=10)
        inv.capacity_used = 2
        db.commit()

        req = BeachSellRequest(tx_type="entry", quantity=1)
        with pytest.raises(ValueError, match="ممتلئ"):
            services.sell_ticket(db, branch.id, req, tx_date=today)

    def test_no_towels_raises(self, db):
        branch = make_branch(db)
        today = date.today()
        inv = crud.get_or_create_inventory(db, branch.id, today, capacity_max=50, towels_total=2)
        inv.towels_available = 0
        inv.towels_used = 2
        db.commit()

        req = BeachSellRequest(tx_type="entry_towel", quantity=1)
        with pytest.raises(ValueError, match="فوط"):
            services.sell_ticket(db, branch.id, req, tx_date=today)

    def test_concurrent_sale_raises_concurrency_error(self, db, monkeypatch):
        """باج حقيقي كان هنا: sell_ticket كان بيقرا/يعدّل capacity_used من غير
        أي قفل صف (عكس pms.crud.lock_room_for_booking للغرف) — تحت حمل متزامن
        حقيقي (كذا كاشير بيبيعوا في نفس اللحظة والسعة قريبة من الحد)، عمليتين
        كانوا ممكن يعدّوا validate_entry بنفس القيمة القديمة ويتسبب تجاوز
        فعلي للسعة. اتصلح بقفل صف BeachInventory (SELECT FOR UPDATE NOWAIT)
        قبل أي تحقق/تعديل — هنا بنحاكي عملية تانية ماسكة الصف بمحاكاة
        OperationalError من الـ lock نفسه."""
        from sqlalchemy.exc import OperationalError

        branch = make_branch(db)

        def _raise_locked(*_args, **_kwargs):
            raise OperationalError("SELECT ... FOR UPDATE NOWAIT", {}, Exception("could not obtain lock"))

        monkeypatch.setattr(crud, "lock_inventory_for_update", _raise_locked)

        req = BeachSellRequest(tx_type="entry", quantity=1)
        with pytest.raises(services.BeachConcurrencyError, match="مشغولة"):
            services.sell_ticket(db, branch.id, req)


class TestVoidTransaction:

    def test_void_transaction(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)

        voided = services.void_transaction(db, tx.id, voided_by=1, reason="اختبار")
        assert voided.voided_at is not None
        assert voided.voided_by == 1

    def test_void_reverses_inventory(self, db):
        branch = make_branch(db)
        today = date.today()
        inv = crud.get_or_create_inventory(db, branch.id, today)
        db.commit()

        req = BeachSellRequest(tx_type="entry", quantity=3)
        tx = services.sell_ticket(db, branch.id, req, tx_date=today)
        db.refresh(inv)
        used_after_sale = inv.capacity_used

        services.void_transaction(db, tx.id, voided_by=1, reason="اختبار")
        db.refresh(inv)
        assert inv.capacity_used == used_after_sale - 3

    def test_double_void_raises(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)
        services.void_transaction(db, tx.id, voided_by=1, reason="اختبار")

        with pytest.raises(ValueError, match="ملغاة"):
            services.void_transaction(db, tx.id, voided_by=1, reason="اختبار")

    def test_void_nonexistent_raises(self, db):
        with pytest.raises(ValueError):
            services.void_transaction(db, 9999, voided_by=1, reason="اختبار")

    def test_void_records_reason(self, db):
        """التبرير إجباري — نفس منطق المطعم (void بسبب موثّق)."""
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)

        voided = services.void_transaction(db, tx.id, voided_by=1, reason="غلط في الكمية")
        assert voided.voided_reason == "غلط في الكمية"


class TestShiftAttachment:

    def test_sale_attaches_open_shift(self, db):
        """بيع الشاطئ بيتربط بوردية الكاشير المفتوحة — عشان يظهر في تقرير
        نهاية الوردية، نفس الباترن المستخدم في finance.services.add_payment."""
        from app.modules.finance import services as finance_services
        from app.modules.finance.schemas import CashierShiftOpen

        branch = make_branch(db)
        shift = finance_services.open_shift(
            db, cashier_id=42, opened_by=42,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")),
        )
        req = BeachSellRequest(tx_type="entry", quantity=1, cashier_id=42)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.shift_id == shift.id

    def test_sale_without_open_shift_has_no_shift_id(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry", quantity=1, cashier_id=999)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.shift_id is None

    def test_sale_without_cashier_id_has_no_shift_id(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.shift_id is None


class TestSurgeToggle:

    def test_set_surge_manual(self, db):
        branch = make_branch(db)
        inv = services.set_surge(db, branch.id, Decimal("50"))
        assert inv.surge_pct == Decimal("50")

    def test_disable_surge(self, db):
        branch = make_branch(db)
        services.set_surge(db, branch.id, Decimal("50"))
        inv = services.set_surge(db, branch.id, Decimal("0"))
        assert inv.surge_pct == Decimal("0")

    def test_invalid_surge_pct_raises(self, db):
        branch = make_branch(db)
        with pytest.raises(ValueError):
            services.set_surge(db, branch.id, Decimal("201"))

    def test_surge_affects_price(self, db):
        branch = make_branch(db)
        today = date.today()

        req_no_surge = BeachSellRequest(tx_type="entry", quantity=1)
        tx_no_surge = services.sell_ticket(db, branch.id, req_no_surge, tx_date=today)

        services.set_surge(db, branch.id, Decimal("50"), inv_date=today)
        req_surge = BeachSellRequest(tx_type="entry", quantity=1)
        tx_surge = services.sell_ticket(db, branch.id, req_surge, tx_date=today)

        assert tx_surge.unit_price > tx_no_surge.unit_price
        assert tx_surge.surge_applied is True


class TestB2BCheckin:

    def test_b2b_checkin_basic(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch)
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=3)
        tx = services.b2b_checkin(db, branch.id, req)
        assert tx.id is not None
        assert tx.b2b_contract_id == contract.id
        assert tx.quantity == 3

    def test_b2b_checkin_with_towel(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch)
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=2, with_towel=True)
        tx = services.b2b_checkin(db, branch.id, req)
        assert tx.tx_type == "entry_towel"
        assert tx.total_amount == (contract.entry_price + contract.towel_price) * 2

    def test_b2b_quota_tracking(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, quota=5)
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=3)
        services.b2b_checkin(db, branch.id, req)

        day = crud.get_or_create_contract_day(db, contract.id, date.today())
        assert day.checked_in_count == 3

    def test_b2b_quota_exceeded_raises(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, quota=2)
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=3)
        with pytest.raises(ValueError, match="حصة"):
            services.b2b_checkin(db, branch.id, req)

    def test_b2b_nonexistent_contract_raises(self, db):
        branch = make_branch(db)
        req = B2BCheckinRequest(contract_id=9999, guests_count=1)
        with pytest.raises(ValueError):
            services.b2b_checkin(db, branch.id, req)

    def test_b2b_price_calculation(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, entry_price=Decimal("100"), towel_price=Decimal("40"))
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=4, with_towel=False)
        tx = services.b2b_checkin(db, branch.id, req)
        assert tx.total_amount == Decimal("400")

    def test_concurrent_checkin_raises_concurrency_error(self, db, monkeypatch):
        """باج حقيقي كان هنا: b2b_checkin كان بيقرا/يعدّل
        B2BContractDay.checked_in_count من غير أي قفل صف — تحت حمل متزامن
        حقيقي (كذا كاشير بيسجّلوا دخول لنفس العقد في نفس اللحظة والحصة قريبة
        من الحد)، عمليتين كانوا ممكن يعدّوا validate_b2b_checkin بنفس القيمة
        القديمة ويتسبب تجاوز فعلي لحصة الفندق الشريك اليومية. اتصلح بقفل صف
        B2BContractDay (SELECT FOR UPDATE NOWAIT) قبل أي تحقق/تعديل — هنا
        بنحاكي عملية تانية ماسكة الصف بمحاكاة OperationalError من القفل نفسه
        (نفس أسلوب test_concurrent_sale_raises_concurrency_error فوق)."""
        from sqlalchemy.exc import OperationalError

        branch = make_branch(db)
        contract = make_contract(db, branch)

        def _raise_locked(*_args, **_kwargs):
            raise OperationalError("SELECT ... FOR UPDATE NOWAIT", {}, Exception("could not obtain lock"))

        monkeypatch.setattr(crud, "lock_contract_day_for_update", _raise_locked)

        req = B2BCheckinRequest(contract_id=contract.id, guests_count=1)
        with pytest.raises(services.BeachConcurrencyError, match="مشغولة"):
            services.b2b_checkin(db, branch.id, req)


class TestB2BQuotaStatus:
    """حالة حصة B2B اليوم — للوحة الحيّة (quota_warning ≤5 متبقين)."""

    def test_no_usage_yet_shows_full_quota(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, quota=10)
        status = services.get_b2b_quota_status(db, branch.id)
        assert len(status) == 1
        assert status[0]["checked_in_today"] == 0
        assert status[0]["remaining_quota"] == 10
        assert status[0]["quota_warning"] is False

    def test_quota_warning_triggers_at_5_or_fewer_remaining(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, quota=8)
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=4)
        services.b2b_checkin(db, branch.id, req)  # remaining = 4

        status = services.get_b2b_quota_status(db, branch.id)
        assert status[0]["checked_in_today"] == 4
        assert status[0]["remaining_quota"] == 4
        assert status[0]["quota_warning"] is True

    def test_quota_warning_sends_whatsapp_to_contract_contact(self, db):
        from unittest.mock import patch
        branch = make_branch(db)
        contract = make_contract(db, branch, quota=8)
        contract.contact_phone = "01055555555"
        db.commit()

        req = B2BCheckinRequest(contract_id=contract.id, guests_count=4)  # remaining = 4 → warning
        with patch("app.core.kernel.whatsapp.send_whatsapp_message", return_value=True) as mock_send:
            services.b2b_checkin(db, branch.id, req)

        mock_send.assert_called_once()
        phone_arg, message_arg = mock_send.call_args[0]
        assert phone_arg == "01055555555"
        assert contract.hotel_name in message_arg

    def test_quota_exhausted(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, quota=3)
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=3)
        services.b2b_checkin(db, branch.id, req)

        status = services.get_b2b_quota_status(db, branch.id)
        assert status[0]["is_quota_exhausted"] is True
        assert status[0]["remaining_quota"] == 0

    def test_inactive_contracts_excluded(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch)
        contract.is_active = False
        db.flush()
        status = services.get_b2b_quota_status(db, branch.id)
        assert status == []


class TestBeachReservation:

    def test_create_reservation(self, db):
        branch = make_branch(db)
        tomorrow = date.today() + timedelta(days=1)
        data = BeachReservationCreate(
            branch_id=branch.id,
            guest_name="أحمد محمد",
            guest_phone="01012345678",
            reservation_date=tomorrow,
            guests_count=2,
            with_towel=False,
        )
        res = services.create_reservation(db, data)
        assert res.id is not None
        assert res.status == "pending"
        assert res.guests_count == 2
        assert res.total_amount > 0

    def test_reservation_with_towel_costs_more(self, db):
        branch = make_branch(db)
        tomorrow = date.today() + timedelta(days=1)
        base = BeachReservationCreate(
            branch_id=branch.id,
            guest_name="نادية",
            reservation_date=tomorrow,
            guests_count=1,
            with_towel=False,
        )
        with_towel = BeachReservationCreate(
            branch_id=branch.id,
            guest_name="نادية",
            reservation_date=tomorrow,
            guests_count=1,
            with_towel=True,
        )
        res_base = services.create_reservation(db, base)
        res_towel = services.create_reservation(db, with_towel)
        assert res_towel.total_amount > res_base.total_amount

    def test_list_reservations(self, db):
        branch = make_branch(db)
        tomorrow = date.today() + timedelta(days=1)
        for i in range(3):
            data = BeachReservationCreate(
                branch_id=branch.id,
                guest_name=f"Guest {i}",
                reservation_date=tomorrow,
                guests_count=1,
            )
            services.create_reservation(db, data)

        items, total = crud.list_reservations(db, branch.id, res_date=tomorrow)
        assert total >= 3


class TestQRCheckin:
    """تسجيل دخول فوري عبر QR — يحوّل الحجز لعملية بيع حقيقية (يستهلك capacity/فوط)."""

    def test_checkin_creates_transaction_and_consumes_capacity(self, db):
        branch = make_branch(db)
        today = date.today()
        data = BeachReservationCreate(
            branch_id=branch.id, guest_name="Ahmed", guest_phone="01001234567",
            reservation_date=today, guests_count=3, with_towel=True,
        )
        res = services.create_reservation(db, data)
        assert res.status == "pending"

        checked_in = services.check_in_reservation(db, res.id, cashier_id=1)
        assert checked_in.status == "checked_in"
        assert checked_in.tx_id is not None

        tx = crud.get_transaction(db, checked_in.tx_id)
        assert tx.tx_type == "entry_towel"
        assert tx.quantity == 3

        inv = crud.get_or_create_inventory(db, branch.id, today)
        db.commit()
        assert inv.capacity_used == 3
        assert inv.towels_used == 3

    def test_checkin_without_towel(self, db):
        branch = make_branch(db)
        data = BeachReservationCreate(
            branch_id=branch.id, guest_name="Sara", reservation_date=date.today(),
            guests_count=2, with_towel=False,
        )
        res = services.create_reservation(db, data)
        checked_in = services.check_in_reservation(db, res.id)
        tx = crud.get_transaction(db, checked_in.tx_id)
        assert tx.tx_type == "entry"

    def test_double_checkin_raises(self, db):
        branch = make_branch(db)
        data = BeachReservationCreate(
            branch_id=branch.id, guest_name="Omar", reservation_date=date.today(),
            guests_count=1,
        )
        res = services.create_reservation(db, data)
        services.check_in_reservation(db, res.id)
        with pytest.raises(ValueError, match="بالفعل"):
            services.check_in_reservation(db, res.id)

    def test_checkin_nonexistent_reservation_raises(self, db):
        with pytest.raises(ValueError):
            services.check_in_reservation(db, 999999)

    def test_checkin_cancelled_reservation_raises(self, db):
        branch = make_branch(db)
        data = BeachReservationCreate(
            branch_id=branch.id, guest_name="Laila", reservation_date=date.today(),
            guests_count=1,
        )
        res = services.create_reservation(db, data)
        res = crud.update_reservation_status(db, res, "cancelled")
        db.commit()
        with pytest.raises(ValueError, match="ملغى"):
            services.check_in_reservation(db, res.id)

    def test_checkin_respects_capacity_limit(self, db):
        branch = make_branch(db)
        today = date.today()
        # عمّر السعة تقريباً بالكامل
        inv = crud.get_or_create_inventory(db, branch.id, today, capacity_max=5)
        db.commit()
        data = BeachReservationCreate(
            branch_id=branch.id, guest_name="Big Group", reservation_date=today,
            guests_count=10,
        )
        res = services.create_reservation(db, data)
        with pytest.raises(ValueError, match="ممتلئ"):
            services.check_in_reservation(db, res.id)


class TestDailySummary:

    def test_daily_summary_empty(self, db):
        branch = make_branch(db)
        today = date.today()
        summary = crud.get_daily_summary(db, branch.id, today)
        assert summary["total_entries"] == 0
        assert summary["total_revenue"] == 0

    def test_daily_summary_after_sales(self, db):
        branch = make_branch(db)
        today = date.today()

        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=3), tx_date=today)
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="towel_rent", quantity=2), tx_date=today)

        summary = crud.get_daily_summary(db, branch.id, today)
        assert summary["total_entries"] == 3
        assert summary["towels_rented"] == 2
        assert summary["total_revenue"] > 0

    def test_voided_not_in_summary(self, db):
        branch = make_branch(db)
        today = date.today()

        tx = services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=1), tx_date=today)
        services.void_transaction(db, tx.id, voided_by=1, reason="اختبار")

        summary = crud.get_daily_summary(db, branch.id, today)
        assert summary["total_entries"] == 0

    def test_b2b_tracked_separately(self, db):
        branch = make_branch(db)
        today = date.today()
        contract = make_contract(db, branch)

        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=2), tx_date=today)
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=5)
        services.b2b_checkin(db, branch.id, req, tx_date=today)

        summary = crud.get_daily_summary(db, branch.id, today)
        assert summary["b2b_entries"] == 5
        assert summary["total_entries"] >= 7


class TestEODReport:
    """تقرير نهاية اليوم — تفصيل حسب النوع، إيرادات الفوط، مقارنة بالأمس/الأسبوع الماضي."""

    def test_empty_day_report(self, db):
        branch = make_branch(db)
        report = services.get_eod_report(db, branch.id, date.today())
        assert report["total_entries"] == 0
        assert report["total_revenue"] == 0
        assert report["by_type"] == []
        assert report["vs_yesterday_pct"] is None

    def test_breakdown_by_type(self, db):
        branch = make_branch(db)
        today = date.today()
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=3), tx_date=today)
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry_towel", quantity=2), tx_date=today)
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="towel_rent", quantity=1), tx_date=today)

        report = services.get_eod_report(db, branch.id, today)
        types = {r["tx_type"]: r for r in report["by_type"]}
        assert types["entry"]["quantity"] == 3
        assert types["entry_towel"]["quantity"] == 2
        assert types["towel_rent"]["quantity"] == 1
        assert report["total_entries"] == 5  # entry(3) + entry_towel(2), not towel_rent

    def test_towel_revenue_combines_standalone_and_bundled(self, db):
        branch = make_branch(db)
        today = date.today()
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="towel_rent", quantity=2), tx_date=today)
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry_towel", quantity=3), tx_date=today)

        report = services.get_eod_report(db, branch.id, today)
        # towel_rent (2 * 50) + entry_towel's bundled towel portion (3 * 50) = 250
        assert report["towel_revenue"] == Decimal("250")

    def test_voided_excluded_from_report(self, db):
        branch = make_branch(db)
        today = date.today()
        tx = services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=1), tx_date=today)
        services.void_transaction(db, tx.id, voided_by=1, reason="اختبار")

        report = services.get_eod_report(db, branch.id, today)
        assert report["total_entries"] == 0
        assert report["voided_count"] == 1

    def test_comparison_vs_yesterday(self, db):
        branch = make_branch(db)
        today = date.today()
        yesterday = today - timedelta(days=1)
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=1), tx_date=yesterday)
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=2), tx_date=today)

        report = services.get_eod_report(db, branch.id, today)
        assert report["yesterday"]["total_entries"] == 1
        assert report["vs_yesterday_pct"] == 100.0  # ضعف الإيراد (2x)

    def test_b2b_tracked_in_report(self, db):
        branch = make_branch(db)
        today = date.today()
        contract = make_contract(db, branch)
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=4)
        services.b2b_checkin(db, branch.id, req, tx_date=today)

        report = services.get_eod_report(db, branch.id, today)
        assert report["b2b_entries"] == 4
        assert report["b2b_revenue"] > 0

    def test_generate_eod_pdf(self, db):
        branch = make_branch(db)
        today = date.today()
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=1), tx_date=today)
        pdf = services.generate_eod_report_pdf(db, branch.id, today)
        assert pdf[:4] == b"%PDF"


def make_finance_accounts(db, branch):
    """يزرع 1100 (نقدية) و4300 (إيرادات الشاطئ) — الحسابين اللي beach.services
    بيدوّر عليهم بالكود عند ترحيل قيد الإيراد."""
    from app.modules.finance.models import Account
    cash = Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset")
    revenue = Account(branch_id=branch.id, code="4300", name="Beach Revenue", account_type="revenue")
    db.add_all([cash, revenue])
    db.commit()
    return cash, revenue


class TestBeachRevenueJournalPosting:
    """Gap حقيقي: beach لم يكن يرحّل أي شيء لدفتر اليومية — كل بيع كان
    يُنشئ BeachTransaction بس من غير أي أثر محاسبي (حساب 4300 كان صفر دايماً)."""

    def test_sell_ticket_posts_balanced_journal_entry(self, db):
        from app.modules.finance import crud as finance_crud
        branch = make_branch(db)
        cash, revenue = make_finance_accounts(db, branch)

        tx = services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=2))

        entries, total = finance_crud.list_journal_entries(db, branch.id, source="beach")
        assert total == 1
        entry = entries[0]
        assert entry.source_id == tx.id
        total_debit = sum(l.debit for l in entry.lines)
        total_credit = sum(l.credit for l in entry.lines)
        assert total_debit == total_credit
        expected_amount = tx.total_amount + tx.vat_amount
        assert total_debit == expected_amount

        db.refresh(cash)
        db.refresh(revenue)
        cash_line = next(l for l in entry.lines if l.account_id == cash.id)
        revenue_line = next(l for l in entry.lines if l.account_id == revenue.id)
        assert cash_line.debit == expected_amount
        assert revenue_line.credit == expected_amount

    def test_sell_ticket_updates_linked_customer_stats(self, db):
        from app.modules.crm import services as crm_services
        from app.modules.crm.schemas import CustomerCreate

        branch = make_branch(db)
        customer = crm_services.create_customer(db, CustomerCreate(
            branch_id=branch.id, full_name="عميل شاطئ دائم",
        ))
        tx = services.sell_ticket(db, branch.id, BeachSellRequest(
            tx_type="entry", quantity=2, customer_id=customer.id,
        ))
        db.refresh(customer)
        assert customer.visits_count == 1
        assert customer.total_spent == tx.total_amount + tx.vat_amount

    def test_b2b_checkin_posts_journal_entry(self, db):
        from app.modules.finance import crud as finance_crud
        branch = make_branch(db)
        make_finance_accounts(db, branch)
        contract = make_contract(db, branch)

        tx = services.b2b_checkin(db, branch.id, B2BCheckinRequest(contract_id=contract.id, guests_count=3))

        entries, total = finance_crud.list_journal_entries(db, branch.id, source="beach")
        assert total == 1
        assert entries[0].source_id == tx.id

    def test_missing_accounts_does_not_block_sale(self, db):
        """لو الحسابات مش موجودة في الفرع، البيع لازم ينجح عادي (نفس فلسفة
        pms._post_checkout_journal — الفشل المحاسبي ميوقفش العملية الأساسية)."""
        branch = make_branch(db)
        tx = services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=1))
        assert tx.id is not None

        from app.modules.finance import crud as finance_crud
        _, total = finance_crud.list_journal_entries(db, branch.id, source="beach")
        assert total == 0

    def test_towel_return_zero_amount_does_not_post(self, db):
        """towel_return مفهوش قيمة مالية (إعادة فوطة) — من غير المفروض
        يرحّل أي قيد إيراد."""
        from app.modules.finance import crud as finance_crud
        branch = make_branch(db)
        make_finance_accounts(db, branch)

        # لازم فوطة مستأجرة الأول عشان نقدر نرجّعها
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="towel_rent", quantity=1))
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="towel_return", quantity=1))

        _, total = finance_crud.list_journal_entries(db, branch.id, source="beach")
        assert total == 1  # بس من towel_rent، مش من towel_return


class TestBeachVoidReversesFinancials:
    """⚠️ باج محاسبي حقيقي كان هنا (اتصلح 2026-07-04): void_transaction كانت
    بتعكس المخزون بس — الإيراد المسجّل في دفتر اليومية (كاش فوري) أو الشحنة
    على فاتورة الغرفة (Charge to Room) كانت تفضل زي ما هي حتى بعد الإلغاء،
    يعني مبالغة دائمة في الإيرادات/فاتورة الضيف لأي عملية اتلغت."""

    def test_void_cash_sale_posts_reversal_journal_entry(self, db):
        from app.modules.finance import crud as finance_crud
        branch = make_branch(db)
        cash, revenue = make_finance_accounts(db, branch)

        tx = services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=2))
        expected_amount = tx.total_amount + tx.vat_amount

        services.void_transaction(db, tx.id, voided_by=1, reason="اختبار عكس القيد")

        entries, total = finance_crud.list_journal_entries(db, branch.id, source="beach_void")
        assert total == 1
        entry = entries[0]
        assert entry.source_id == tx.id
        total_debit = sum(l.debit for l in entry.lines)
        total_credit = sum(l.credit for l in entry.lines)
        assert total_debit == total_credit == expected_amount

        db.refresh(cash)
        db.refresh(revenue)
        cash_line = next(l for l in entry.lines if l.account_id == cash.id)
        revenue_line = next(l for l in entry.lines if l.account_id == revenue.id)
        assert cash_line.credit == expected_amount  # عكس البيع: دلوقتي دائن مش مدين
        assert revenue_line.debit == expected_amount  # عكس البيع: دلوقتي مدين مش دائن

    def test_void_room_charged_ticket_removes_folio_charge(self, db):
        from app.modules.finance import crud as finance_crud
        from app.modules.finance.models import Folio
        from app.modules.pms.models import Room, Booking
        from datetime import datetime, timedelta

        branch = make_branch(db)
        folio = Folio(
            branch_id=branch.id, guest_name="نزيل شاطئ", status="open",
            check_in=datetime.utcnow(), check_out=datetime.utcnow() + timedelta(days=2),
        )
        db.add(folio)
        db.commit()

        tx = services.sell_ticket(
            db, branch.id, BeachSellRequest(tx_type="entry", quantity=1, folio_id=folio.id),
        )
        charge = finance_crud.get_charge_by_ref_beach_tx(db, tx.id)
        assert charge is not None
        db.refresh(folio)
        assert folio.total == tx.total_amount + tx.vat_amount

        services.void_transaction(db, tx.id, voided_by=1, reason="اختبار إلغاء شحنة الغرفة")

        assert finance_crud.get_charge_by_ref_beach_tx(db, tx.id) is None
        db.refresh(folio)
        assert folio.total == Decimal("0")

    def test_void_rejected_on_closed_folio(self, db):
        from app.modules.finance.models import Folio
        from datetime import datetime, timedelta

        branch = make_branch(db)
        folio = Folio(
            branch_id=branch.id, guest_name="نزيل شاطئ", status="open",
            check_in=datetime.utcnow(), check_out=datetime.utcnow() + timedelta(days=2),
        )
        db.add(folio)
        db.commit()

        tx = services.sell_ticket(
            db, branch.id, BeachSellRequest(tx_type="entry", quantity=1, folio_id=folio.id),
        )
        folio.status = "closed"
        db.commit()

        with pytest.raises(ValueError, match="مقفولة"):
            services.void_transaction(db, tx.id, voided_by=1, reason="اختبار")
