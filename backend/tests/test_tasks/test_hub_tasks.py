"""
tests/test_tasks/test_hub_tasks.py
اختبارات الـ hub_tasks.py — expire_old_offers, process_pending_bookings_reminder,
refresh_sitemap — بدون Celery runtime
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest


# ─── helpers ────────────────────────────────────────────────────────────────

def _make_branch(db, active=True):
    from app.modules.core.models import Branch
    b = Branch(
        name=f"Hub-Branch-{uuid.uuid4().hex[:6]}",
        code=f"HB{uuid.uuid4().hex[:4].upper()}",
        is_active=active,
    )
    db.add(b)
    db.commit()
    return b


def _make_offer(db, branch, is_active=True, valid_until=None):
    from app.modules.hub.models import HubOffer
    today = date.today()
    o = HubOffer(
        branch_id=branch.id,
        title=f"Offer-{uuid.uuid4().hex[:4]}",
        offer_type="package",
        original_price=Decimal("500"),
        offer_price=Decimal("400"),
        valid_from=today - timedelta(days=7),
        valid_until=valid_until or today + timedelta(days=30),
        is_active=is_active,
    )
    db.add(o)
    db.commit()
    return o


def _make_online_booking(db, branch, status="pending", created_at=None):
    from app.modules.hub.models import HubOnlineBooking
    booking = HubOnlineBooking(
        branch_id=branch.id,
        guest_name=f"Guest-{uuid.uuid4().hex[:4]}",
        guest_phone="01000000000",
        requested_date=date.today() + timedelta(days=7),
        status=status,
        source="website",
    )
    db.add(booking)
    db.flush()
    if created_at:
        booking.created_at = created_at
    db.commit()
    return booking


def _make_contact_form(db, branch, purpose="general_inquiry"):
    from app.modules.hub.models import ContactForm
    form = ContactForm(
        branch_id=branch.id,
        full_name="Guest Name",
        phone="01000000000",
        email="guest@example.com",
        subject="Question",
        message="Test message",
        purpose=purpose,
        service_contact_authorized=True,
    )
    db.add(form)
    db.commit()
    return form


def _db_ctx(db):
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=db)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


# ─── expire_old_offers ────────────────────────────────────────────────────────

class TestExpireOldOffers:

    def test_expired_active_offer_deactivated(self, db):
        """عرض منتهي الصلاحية ونشط يُعطَّل"""
        branch = _make_branch(db)
        yesterday = date.today() - timedelta(days=1)
        offer = _make_offer(db, branch, is_active=True, valid_until=yesterday)

        from app.modules.hub.models import HubOffer
        today = date.today()
        expired = (
            db.query(HubOffer)
            .filter(HubOffer.is_active.is_(True), HubOffer.valid_until < today)
            .all()
        )
        for o in expired:
            o.is_active = False
        db.commit()
        db.refresh(offer)

        assert offer.is_active is False

    def test_valid_offer_not_deactivated(self, db):
        """عرض صالح لا يُعطَّل"""
        branch = _make_branch(db)
        next_week = date.today() + timedelta(days=7)
        offer = _make_offer(db, branch, is_active=True, valid_until=next_week)

        from app.modules.hub.models import HubOffer
        today = date.today()
        expired = (
            db.query(HubOffer)
            .filter(HubOffer.id == offer.id, HubOffer.is_active.is_(True), HubOffer.valid_until < today)
            .all()
        )
        assert len(expired) == 0

    def test_already_inactive_offer_not_touched(self, db):
        """عرض غير نشط لا يُغيَّر"""
        branch = _make_branch(db)
        yesterday = date.today() - timedelta(days=1)
        offer = _make_offer(db, branch, is_active=False, valid_until=yesterday)

        from app.modules.hub.models import HubOffer
        today = date.today()
        expired = (
            db.query(HubOffer)
            .filter(HubOffer.is_active.is_(True), HubOffer.valid_until < today)
            .all()
        )
        assert offer.id not in [o.id for o in expired]

    def test_count_returned_correctly(self, db):
        """عدد العروض المُعطَّلة صحيح"""
        branch = _make_branch(db)
        yesterday = date.today() - timedelta(days=1)
        o1 = _make_offer(db, branch, is_active=True, valid_until=yesterday)
        o2 = _make_offer(db, branch, is_active=True, valid_until=yesterday)
        o3 = _make_offer(db, branch, is_active=True, valid_until=date.today() + timedelta(days=5))

        from app.modules.hub.models import HubOffer
        today = date.today()
        expired = (
            db.query(HubOffer)
            .filter(HubOffer.is_active.is_(True), HubOffer.valid_until < today)
            .all()
        )
        assert o1.id in [o.id for o in expired]
        assert o2.id in [o.id for o in expired]
        assert o3.id not in [o.id for o in expired]

    def test_task_runs_without_error(self, db):
        """task يشتغل بدون exception"""
        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
            from app.tasks.hub_tasks import expire_old_offers
            expire_old_offers()


# ─── process_pending_bookings_reminder ───────────────────────────────────────

class TestPendingBookingsReminder:

    def test_old_pending_booking_detected(self, db):
        """حجز pending من أكثر من 24 ساعة يُكتشف"""
        branch = _make_branch(db)
        old_time = datetime.utcnow() - timedelta(hours=25)
        booking = _make_online_booking(db, branch, status="pending", created_at=old_time)

        from app.modules.hub.models import HubOnlineBooking
        cutoff = datetime.utcnow() - timedelta(hours=24)
        pending = (
            db.query(HubOnlineBooking)
            .filter(
                HubOnlineBooking.id == booking.id,
                HubOnlineBooking.status == "pending",
                HubOnlineBooking.created_at <= cutoff,
            )
            .all()
        )
        assert len(pending) >= 1

    def test_recent_pending_booking_not_included(self, db):
        """حجز pending جديد (أقل من 24 ساعة) لا يظهر"""
        branch = _make_branch(db)
        booking = _make_online_booking(db, branch, status="pending")
        # created_at الافتراضي = الآن

        from app.modules.hub.models import HubOnlineBooking
        cutoff = datetime.utcnow() - timedelta(hours=24)
        pending = (
            db.query(HubOnlineBooking)
            .filter(
                HubOnlineBooking.id == booking.id,
                HubOnlineBooking.status == "pending",
                HubOnlineBooking.created_at <= cutoff,
            )
            .all()
        )
        assert len(pending) == 0

    def test_confirmed_booking_excluded(self, db):
        """حجز confirmed لا يظهر في نتائج pending"""
        branch = _make_branch(db)
        old_time = datetime.utcnow() - timedelta(hours=25)
        booking = _make_online_booking(db, branch, status="confirmed", created_at=old_time)

        from app.modules.hub.models import HubOnlineBooking
        cutoff = datetime.utcnow() - timedelta(hours=24)
        pending = (
            db.query(HubOnlineBooking)
            .filter(
                HubOnlineBooking.id == booking.id,
                HubOnlineBooking.status == "pending",
                HubOnlineBooking.created_at <= cutoff,
            )
            .all()
        )
        assert len(pending) == 0

    def test_task_runs_without_error(self, db):
        """task يشتغل بدون exception"""
        branch = _make_branch(db)
        old_time = datetime.utcnow() - timedelta(hours=26)
        _make_online_booking(db, branch, status="pending", created_at=old_time)
        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
            from app.tasks.hub_tasks import process_pending_bookings_reminder
            process_pending_bookings_reminder()


# ─── refresh_sitemap ──────────────────────────────────────────────────────────

class TestRefreshSitemap:

    def test_refresh_returns_page_count(self, db):
        """refresh_sitemap يرجع عدد الصفحات"""
        branch = _make_branch(db)
        from app.modules.hub.services import refresh_sitemap
        count = refresh_sitemap(db, branch.id)
        assert isinstance(count, int)
        assert count >= 0

    def test_task_runs_without_error(self, db):
        """task refresh_sitemap يشتغل بدون exception"""
        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
            from app.tasks.hub_tasks import refresh_sitemap
            refresh_sitemap()


# ─── notify_new_room_booking / notify_new_contact_form ───────────────────────

class TestNotifyNewRoomBooking:

    def test_sends_to_reservation_email_with_booking_details(self, db):
        branch = _make_branch(db)
        booking = _make_online_booking(db, branch)
        booking.guest_email = None  # isolate: no guest reply expected here
        booking.public_reference = f"BK-{uuid.uuid4().hex[:8]}"
        db.commit()

        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)), \
             patch("app.tasks.hub_tasks.send_email", return_value=True) as mock_send:
            from app.tasks.hub_tasks import notify_new_room_booking
            notify_new_room_booking(booking.id)

        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        assert kwargs["to"] == "reservation@elkheima.com"
        assert booking.public_reference in kwargs["subject"]
        assert booking.guest_name in kwargs["body"]
        assert booking.guest_phone in kwargs["body"]

    def test_guest_with_email_also_gets_confirmation_reply(self, db):
        """Mohamed 2026-09-09: 'الهدف التأكد من المراسلة بالإيميلات شغالة' —
        مراسلة باتجاهين، مش بس تنبيه للموظفين."""
        branch = _make_branch(db)
        booking = _make_online_booking(db, branch)
        booking.guest_email = "guest@example.com"
        booking.public_reference = f"BK-{uuid.uuid4().hex[:8]}"
        db.commit()

        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)), \
             patch("app.tasks.hub_tasks.send_email", return_value=True) as mock_send:
            from app.tasks.hub_tasks import notify_new_room_booking
            notify_new_room_booking(booking.id, "en")

        assert mock_send.call_count == 2
        staff_call, guest_call = mock_send.call_args_list
        assert staff_call.kwargs["to"] == "reservation@elkheima.com"
        assert guest_call.kwargs["to"] == "guest@example.com"
        assert booking.public_reference in guest_call.kwargs["subject"]
        assert booking.guest_name in guest_call.kwargs["body"]

    def test_guest_without_email_gets_no_second_send(self, db):
        branch = _make_branch(db)
        booking = _make_online_booking(db, branch)
        booking.guest_email = None
        db.commit()

        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)), \
             patch("app.tasks.hub_tasks.send_email", return_value=True) as mock_send:
            from app.tasks.hub_tasks import notify_new_room_booking
            notify_new_room_booking(booking.id)

        assert mock_send.call_count == 1

    def test_guest_reply_language_defaults_to_arabic(self, db):
        branch = _make_branch(db)
        booking = _make_online_booking(db, branch)
        booking.guest_email = "guest@example.com"
        db.commit()

        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)), \
             patch("app.tasks.hub_tasks.send_email", return_value=True) as mock_send:
            from app.tasks.hub_tasks import notify_new_room_booking
            notify_new_room_booking(booking.id)  # no language arg

        _, guest_call = mock_send.call_args_list
        assert "تأكيد استلام طلب حجزك" in guest_call.kwargs["subject"]

    def test_missing_booking_does_not_raise(self, db):
        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)), \
             patch("app.tasks.hub_tasks.send_email") as mock_send:
            from app.tasks.hub_tasks import notify_new_room_booking
            notify_new_room_booking(999999)
        mock_send.assert_not_called()

    def test_send_failure_triggers_retry(self, db):
        branch = _make_branch(db)
        booking = _make_online_booking(db, branch)

        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)), \
             patch("app.tasks.hub_tasks.send_email", return_value=False):
            from app.tasks.hub_tasks import notify_new_room_booking
            with pytest.raises(Exception):
                notify_new_room_booking(booking.id)


class TestNotifyNewContactForm:

    def test_general_inquiry_sends_to_info_email(self, db):
        branch = _make_branch(db)
        form = _make_contact_form(db, branch, purpose="general_inquiry")

        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)), \
             patch("app.tasks.hub_tasks.send_email", return_value=True) as mock_send:
            from app.tasks.hub_tasks import notify_new_contact_form
            notify_new_contact_form(form.id)

        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        assert kwargs["to"] == "info@elkheima.com"
        assert form.public_reference in kwargs["subject"]

    def test_non_general_purpose_skipped_no_channel_yet(self, db):
        """beach_service/activity_request/... لسه بتنتظر قناة واتساب — مفيش
        إيميل يتبعت ليهم لحد ما تُبنى (راجع docstring في notify_new_contact_form)."""
        branch = _make_branch(db)
        form = _make_contact_form(db, branch, purpose="beach_service")

        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)), \
             patch("app.tasks.hub_tasks.send_email") as mock_send:
            from app.tasks.hub_tasks import notify_new_contact_form
            notify_new_contact_form(form.id)

        mock_send.assert_not_called()

    def test_missing_form_does_not_raise(self, db):
        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)), \
             patch("app.tasks.hub_tasks.send_email") as mock_send:
            from app.tasks.hub_tasks import notify_new_contact_form
            notify_new_contact_form(999999)
        mock_send.assert_not_called()
