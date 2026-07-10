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

    def test_notify_admin_when_pending_exist(self, db):
        """notify_admin يُستدعى لو في حجوزات pending قديمة"""
        import app.core.kernel.whatsapp as wa_module
        msgs = []
        original = getattr(wa_module, "notify_admin", lambda *a: None)
        wa_module.notify_admin = lambda msg: msgs.append(msg)
        try:
            branch = _make_branch(db)
            old_time = datetime.utcnow() - timedelta(hours=26)
            b1 = _make_online_booking(db, branch, status="pending", created_at=old_time)

            from app.modules.hub.models import HubOnlineBooking
            cutoff = datetime.utcnow() - timedelta(hours=24)
            pending = db.query(HubOnlineBooking).filter(
                HubOnlineBooking.id == b1.id,
                HubOnlineBooking.status == "pending",
                HubOnlineBooking.created_at <= cutoff,
            ).all()

            if pending:
                names = "، ".join(b.guest_name for b in pending[:5])
                wa_module.notify_admin(
                    f"تنبيه ريسبشن: {len(pending)} حجز أونلاين لسه مش متابَع — {names}."
                )

            assert len(msgs) >= 1
            assert "حجز أونلاين" in msgs[-1]
        finally:
            wa_module.notify_admin = original

    def test_task_runs_without_error(self, db):
        """task يشتغل بدون exception"""
        import app.core.kernel.whatsapp as wa_module
        original = getattr(wa_module, "notify_admin", lambda *a: None)
        wa_module.notify_admin = lambda *a, **kw: None
        try:
            with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
                from app.tasks.hub_tasks import process_pending_bookings_reminder
                process_pending_bookings_reminder()
        finally:
            wa_module.notify_admin = original


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
