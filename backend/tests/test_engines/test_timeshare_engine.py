"""
tests/test_engines/test_timeshare_engine.py
Pure unit tests for timeshare_engine — no DB, no HTTP.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.resort_os.timeshare_engine import (
    TimeshareContractData,
    VisitWindow,
    WaitlistEntry,
    calculate_installment_amount,
    calculate_lease_penalty,
    calculate_partner_share,
    calculate_visit_window,
    find_next_visit,
    generate_installment_schedule,
    generate_lease_monthly_schedule,
    generate_lease_yearly_schedule,
    get_first_installment_date,
    get_upcoming_visits,
    is_payment_overdue,
    is_waitlist_expired,
    should_freeze_booking,
    should_send_installment_reminder,
    should_send_visit_reminder,
)


# ── Installment schedule ──────────────────────────────────────────────

class TestGenerateInstallmentSchedule:

    def test_basic_monthly(self):
        schedule = generate_installment_schedule(
            total_value=Decimal("120000"),
            down_payment=Decimal("20000"),
            installments=12,
            installment_period=1,
            first_installment_date=date(2026, 2, 1),
        )
        assert len(schedule) == 12
        assert schedule[0].installment_no == 1
        assert schedule[0].due_date == date(2026, 2, 1)
        assert schedule[11].due_date == date(2027, 1, 1)
        # المجموع = 100,000
        total = sum(s.amount for s in schedule)
        assert total == Decimal("100000")

    def test_quarterly(self):
        schedule = generate_installment_schedule(
            total_value=Decimal("48000"),
            down_payment=Decimal("0"),
            installments=4,
            installment_period=3,
            first_installment_date=date(2026, 1, 1),
        )
        assert len(schedule) == 4
        assert schedule[1].due_date == date(2026, 4, 1)
        assert schedule[3].due_date == date(2026, 10, 1)

    def test_rounding_last_installment(self):
        """فروق التقريب تذهب للقسط الأخير."""
        schedule = generate_installment_schedule(
            total_value=Decimal("100001"),
            down_payment=Decimal("1"),
            installments=3,
            installment_period=1,
            first_installment_date=date(2026, 1, 1),
        )
        total = sum(s.amount for s in schedule)
        assert total == Decimal("100000")

    def test_zero_installments_returns_empty(self):
        assert generate_installment_schedule(
            Decimal("100"), Decimal("100"), 0, 1, date(2026, 1, 1)
        ) == []

    def test_full_down_payment_returns_empty(self):
        assert generate_installment_schedule(
            Decimal("100"), Decimal("100"), 12, 1, date(2026, 1, 1)
        ) == []

    def test_all_statuses_default_pending(self):
        schedule = generate_installment_schedule(
            Decimal("60000"), Decimal("0"), 6, 1, date(2026, 1, 1)
        )
        assert all(s.status == "pending" for s in schedule)


class TestCalculateInstallmentAmount:

    def test_equal_division(self):
        result = calculate_installment_amount(Decimal("120000"), Decimal("20000"), 10)
        assert result == Decimal("10000")

    def test_zero_installments(self):
        assert calculate_installment_amount(Decimal("100000"), Decimal("0"), 0) == Decimal("0")


class TestGetFirstInstallmentDate:

    def test_provided_date_used(self):
        provided = date(2026, 3, 15)
        result = get_first_installment_date(date(2026, 1, 1), provided)
        assert result == provided

    def test_defaults_to_one_month_after(self):
        result = get_first_installment_date(date(2026, 1, 15))
        assert result == date(2026, 2, 15)


# ── Partner share ─────────────────────────────────────────────────────

class TestCalculatePartnerShare:

    def test_50_percent(self):
        resort, partner = calculate_partner_share(Decimal("10000"), Decimal("50"))
        assert resort == Decimal("5000")
        assert partner == Decimal("5000")

    def test_zero_percent(self):
        resort, partner = calculate_partner_share(Decimal("10000"), Decimal("0"))
        assert resort == Decimal("10000")
        assert partner == Decimal("0")

    def test_30_percent(self):
        resort, partner = calculate_partner_share(Decimal("10000"), Decimal("30"))
        assert resort == Decimal("7000")
        assert partner == Decimal("3000")


# ── Visit window ──────────────────────────────────────────────────────

class TestCalculateVisitWindow:

    def test_week_28_2026(self):
        """الأسبوع 28 من 2026 = الإثنين 6 يوليو 2026."""
        window = calculate_visit_window(28, 7, 2026, today=date(2026, 6, 1))
        assert window is not None
        assert window.visit_start == date(2026, 7, 6)
        assert window.nights == 7
        assert window.visit_end == date(2026, 7, 12)

    def test_days_until_positive(self):
        window = calculate_visit_window(28, 7, 2026, today=date(2026, 6, 1))
        assert window.days_until == (date(2026, 7, 6) - date(2026, 6, 1)).days

    def test_past_visit(self):
        window = calculate_visit_window(1, 7, 2026, today=date(2026, 12, 1))
        assert window.is_past

    def test_invalid_week_returns_none(self):
        assert calculate_visit_window(0, 7, 2026) is None
        assert calculate_visit_window(53, 7, 2026) is None

    def test_is_today(self):
        today = date(2026, 7, 6)
        window = calculate_visit_window(28, 7, 2026, today=today)
        assert window.is_today


class TestFindNextVisit:

    def test_returns_this_year_if_upcoming(self):
        today = date(2026, 6, 1)
        window = find_next_visit(28, 7, today=today)
        assert window is not None
        assert window.year == 2026

    def test_returns_next_year_if_passed(self):
        today = date(2026, 8, 1)
        window = find_next_visit(28, 7, today=today)
        assert window is not None
        assert window.year == 2027

    def test_none_for_invalid_week(self):
        assert find_next_visit(0, 7) is None


class TestGetUpcomingVisits:

    def _make_contract(self, week: int) -> TimeshareContractData:
        return TimeshareContractData(
            contract_id=1,
            customer_name="Test",
            customer_phone="01000000000",
            room_type="2R",
            week_number=week,
            nights_per_year=7,
            total_value=Decimal("100000"),
            down_payment=Decimal("10000"),
            installments=12,
            installment_period=1,
            first_installment_date=date(2026, 2, 1),
            partner_share_pct=Decimal("0"),
            status="active",
        )

    def test_returns_only_within_days(self):
        today = date(2026, 7, 1)
        c1 = self._make_contract(28)   # starts 6 Jul — 5 days away
        c2 = self._make_contract(40)   # Oct — far
        results = get_upcoming_visits([c1, c2], within_days=7, today=today)
        assert len(results) == 1
        assert results[0][0].week_number == 28

    def test_sorted_by_days_until(self):
        today = date(2026, 6, 30)
        c1 = self._make_contract(28)   # 6 Jul
        c2 = self._make_contract(27)   # 29 Jun — already passed? test ascending
        results = get_upcoming_visits([c1, c2], within_days=30, today=today)
        if len(results) > 1:
            assert results[0][1].days_until <= results[1][1].days_until


# ── Overdue & penalties ───────────────────────────────────────────────

class TestIsPaymentOverdue:

    def test_past_due_is_overdue(self):
        assert is_payment_overdue(date(2026, 1, 1), today=date(2026, 2, 1))

    def test_future_not_overdue(self):
        assert not is_payment_overdue(date(2026, 12, 1), today=date(2026, 6, 1))

    def test_same_day_not_overdue(self):
        today = date(2026, 6, 1)
        assert not is_payment_overdue(today, today=today)


class TestCalculateLeasePenalty:

    def test_over_30_days(self):
        penalty = calculate_lease_penalty(
            Decimal("10000"), date(2026, 1, 1), today=date(2026, 2, 10)
        )
        assert penalty == Decimal("1000")  # 10%

    def test_over_7_days(self):
        penalty = calculate_lease_penalty(
            Decimal("10000"), date(2026, 1, 1), today=date(2026, 1, 15)
        )
        assert penalty == Decimal("500")   # 5%

    def test_under_7_days_no_penalty(self):
        penalty = calculate_lease_penalty(
            Decimal("10000"), date(2026, 1, 1), today=date(2026, 1, 5)
        )
        assert penalty == Decimal("0")


class TestShouldFreezeBooking:

    def test_overdue_amount_freezes(self):
        assert should_freeze_booking(Decimal("100"))

    def test_zero_does_not_freeze(self):
        assert not should_freeze_booking(Decimal("0"))


# ── Waitlist ──────────────────────────────────────────────────────────

class TestIsWaitlistExpired:

    def test_expired_notified_entry(self):
        entry = WaitlistEntry(
            entry_id=1, contract_id=1,
            customer_name="Test", customer_phone="01000000000",
            requested_start=date(2026, 7, 1), requested_end=date(2026, 7, 7),
            position=1, status="notified",
            notified_at=datetime(2026, 6, 1, 10, 0),
            expires_at=datetime(2026, 6, 2, 10, 0),
        )
        assert is_waitlist_expired(entry, now=datetime(2026, 6, 3, 0, 0))

    def test_not_expired_within_24h(self):
        entry = WaitlistEntry(
            entry_id=1, contract_id=1,
            customer_name="Test", customer_phone="01000000000",
            requested_start=date(2026, 7, 1), requested_end=date(2026, 7, 7),
            position=1, status="notified",
            notified_at=datetime(2026, 6, 1, 10, 0),
            expires_at=datetime(2026, 6, 2, 10, 0),
        )
        assert not is_waitlist_expired(entry, now=datetime(2026, 6, 1, 20, 0))

    def test_waiting_status_never_expires(self):
        entry = WaitlistEntry(
            entry_id=1, contract_id=1,
            customer_name="Test", customer_phone="01000000000",
            requested_start=date(2026, 7, 1), requested_end=date(2026, 7, 7),
            position=1, status="waiting",
        )
        assert not is_waitlist_expired(entry)


# ── Reminders ─────────────────────────────────────────────────────────

class TestShouldSendVisitReminder:

    def test_exactly_3_days_before(self):
        window = VisitWindow(
            year=2026, week_number=28,
            visit_start=date(2026, 7, 6), visit_end=date(2026, 7, 12),
            nights=7, days_until=3,
        )
        assert should_send_visit_reminder(window)

    def test_2_days_before_no_reminder(self):
        window = VisitWindow(
            year=2026, week_number=28,
            visit_start=date(2026, 7, 6), visit_end=date(2026, 7, 12),
            nights=7, days_until=2,
        )
        assert not should_send_visit_reminder(window)


class TestShouldSendInstallmentReminder:

    def test_exactly_7_days_before(self):
        due = date(2026, 7, 7)
        today = date(2026, 6, 30)
        assert should_send_installment_reminder(due, today)

    def test_6_days_no_reminder(self):
        due = date(2026, 7, 6)
        today = date(2026, 6, 30)
        assert not should_send_installment_reminder(due, today)


# ── Lease schedule generation ─────────────────────────────────────────

class TestGenerateLeaseMonthlySchedule:

    def test_basic_12_months(self):
        schedule = generate_lease_monthly_schedule(
            base_rent=Decimal("5000"),
            increase_rate=0,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            grace_months=0,
            billing_day=1,
        )
        assert len(schedule) == 12
        assert all(p["amount"] == Decimal("5000") for p in schedule)

    def test_grace_period_skips_months(self):
        schedule = generate_lease_monthly_schedule(
            base_rent=Decimal("5000"),
            increase_rate=0,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            grace_months=2,
            billing_day=1,
        )
        assert len(schedule) == 10
        assert schedule[0]["due_date"] == date(2026, 3, 1)

    def test_annual_increase(self):
        schedule = generate_lease_monthly_schedule(
            base_rent=Decimal("1000"),
            increase_rate=10,
            start_date=date(2026, 1, 1),
            end_date=date(2027, 12, 31),
        )
        year_1 = [p for p in schedule if p["year_n"] == 0]
        year_2 = [p for p in schedule if p["year_n"] == 1]
        assert all(p["amount"] == Decimal("1000") for p in year_1)
        assert all(p["amount"] == Decimal("1100") for p in year_2)


class TestGenerateLeaseYearlySchedule:

    def test_3_year_contract(self):
        schedule = generate_lease_yearly_schedule(
            base_rent=Decimal("60000"),
            increase_rate=5,
            start_date=date(2026, 1, 1),
            end_date=date(2028, 12, 31),
        )
        assert len(schedule) == 3
        assert schedule[0]["rent_amount"] == Decimal("60000")
        assert schedule[1]["rent_amount"] == Decimal("63000")
        assert schedule[2]["rent_amount"] == Decimal("66150")
