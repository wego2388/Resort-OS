"""
tests/test_api/test_hub.py
Integration tests for hub module.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.modules.hub.schemas import (
    HubOfferCreate, HubOfferUpdate,
    HubPageCreate, HubPageUpdate,
    OnlineBookingCreate, OnlineBookingUpdate,
)
from app.modules.hub import services, crud


@pytest.fixture
def branch(db: Session):
    from app.modules.core.models import Branch
    b = Branch(name="Test Hub", name_ar="هاب اختباري",
               code=f"HUB-{uuid.uuid4().hex[:6].upper()}")
    db.add(b)
    db.flush()
    return b


@pytest.fixture
def page(db: Session, branch):
    data = HubPageCreate(
        branch_id=branch.id,
        slug=f"test-page-{uuid.uuid4().hex[:8]}",
        title="Test Page",
        title_ar="صفحة اختبار",
        page_type="info",
    )
    return services.create_page(db, data)


@pytest.fixture
def offer(db: Session, branch):
    data = HubOfferCreate(
        branch_id=branch.id,
        title="عرض الصيف",
        offer_type="room",
        original_price=Decimal("1000.00"),
        offer_price=Decimal("750.00"),
        valid_from=date.today(),
        valid_until=date.today() + timedelta(days=30),
    )
    return services.create_offer(db, data)


class TestHubPage:

    def test_create_page(self, db, branch):
        data = HubPageCreate(
            branch_id=branch.id,
            slug=f"about-{uuid.uuid4().hex[:8]}",
            title="About Us",
            page_type="info",
        )
        page = services.create_page(db, data)
        assert page.id is not None
        assert page.is_published is False

    def test_duplicate_slug_raises(self, db, branch, page):
        data = HubPageCreate(
            branch_id=branch.id,
            slug=page.slug,  # نفس الـ slug
            title="صفحة أخرى",
        )
        with pytest.raises(ValueError, match="slug"):
            services.create_page(db, data)

    def test_update_page(self, db, page):
        updated = services.update_page(db, page.id, HubPageUpdate(title="Updated Title"))
        assert updated.title == "Updated Title"

    def test_publish_page(self, db, page):
        updated = services.update_page(db, page.id, HubPageUpdate(is_published=True))
        assert updated.is_published is True

    def test_page_not_found_raises(self, db):
        with pytest.raises(ValueError):
            services.get_page_or_404(db, 9999)

    def test_delete_page(self, db, branch):
        data = HubPageCreate(
            branch_id=branch.id,
            slug=f"delete-me-{uuid.uuid4().hex[:8]}",
            title="To Delete",
        )
        pg = services.create_page(db, data)
        page_id = pg.id
        services.delete_page(db, page_id)
        assert crud.get_page(db, page_id) is None


class TestHubOffer:

    def test_create_offer(self, db, offer):
        assert offer.id is not None
        assert offer.is_active is True
        assert offer.bookings_count == 0

    def test_offer_price_lower_than_original(self, db, branch):
        data = HubOfferCreate(
            branch_id=branch.id,
            title="عرض سيئ",
            offer_type="beach",
            original_price=Decimal("500.00"),
            offer_price=Decimal("800.00"),  # أعلى من الأصلي!
            valid_from=date.today(),
            valid_until=date.today() + timedelta(days=10),
        )
        with pytest.raises(ValueError, match="أقل من"):
            services.create_offer(db, data)

    def test_invalid_dates_raises(self, db, branch):
        data = HubOfferCreate(
            branch_id=branch.id,
            title="عرض تواريخ خاطئة",
            offer_type="restaurant",
            original_price=Decimal("300.00"),
            offer_price=Decimal("200.00"),
            valid_from=date.today() + timedelta(days=10),
            valid_until=date.today(),  # نهاية قبل البداية
        )
        with pytest.raises(ValueError, match="valid_from"):
            services.create_offer(db, data)

    def test_update_offer(self, db, offer):
        updated = services.update_offer(db, offer.id, HubOfferUpdate(offer_price=Decimal("700.00")))
        assert updated.offer_price == Decimal("700.00")

    def test_offer_not_found_raises(self, db):
        with pytest.raises(ValueError):
            services.get_offer_or_404(db, 9999)


class TestOnlineBooking:

    def test_create_booking_without_offer(self, db, branch):
        data = OnlineBookingCreate(
            branch_id=branch.id,
            guest_name="محمد أحمد",
            guest_phone="01001000000",
            guests_count=2,
            requested_date=date.today() + timedelta(days=7),
        )
        booking = services.create_online_booking(db, data)
        assert booking.id is not None
        assert booking.status == "pending"

    def test_create_booking_with_valid_offer(self, db, branch, offer):
        data = OnlineBookingCreate(
            branch_id=branch.id,
            offer_id=offer.id,
            guest_name="سارة عمر",
            guest_phone="01002000000",
            guests_count=1,
            requested_date=date.today() + timedelta(days=5),
        )
        booking = services.create_online_booking(db, data)
        assert booking.offer_id == offer.id
        db.refresh(offer)
        assert offer.bookings_count == 1

    def test_booking_with_inactive_offer_raises(self, db, branch, offer):
        offer.is_active = False
        db.flush()
        data = OnlineBookingCreate(
            branch_id=branch.id,
            offer_id=offer.id,
            guest_name="عميل",
            guest_phone="01000000000",
            guests_count=1,
            requested_date=date.today() + timedelta(days=3),
        )
        with pytest.raises(ValueError, match="غير متاح"):
            services.create_online_booking(db, data)

    def test_booking_with_expired_offer_raises(self, db, branch):
        from app.modules.hub.models import HubOffer
        expired = HubOffer(
            branch_id=branch.id,
            title="عرض منتهي",
            offer_type="beach",
            original_price=Decimal("500"),
            offer_price=Decimal("300"),
            valid_from=date.today() - timedelta(days=30),
            valid_until=date.today() - timedelta(days=1),
            is_active=True,
        )
        db.add(expired)
        db.flush()
        data = OnlineBookingCreate(
            branch_id=branch.id,
            offer_id=expired.id,
            guest_name="عميل",
            guest_phone="01000000000",
            guests_count=1,
            requested_date=date.today(),
        )
        with pytest.raises(ValueError, match="منتهي"):
            services.create_online_booking(db, data)

    def test_confirm_booking(self, db, branch):
        data = OnlineBookingCreate(
            branch_id=branch.id,
            guest_name="فاطمة علي",
            guest_phone="01003000000",
            guests_count=2,
            requested_date=date.today() + timedelta(days=10),
        )
        booking = services.create_online_booking(db, data)
        confirmed = services.confirm_booking(db, booking.id, confirmed_by=1)
        assert confirmed.status == "confirmed"
        assert confirmed.confirmed_by == 1

    def test_cannot_confirm_already_confirmed(self, db, branch):
        data = OnlineBookingCreate(
            branch_id=branch.id,
            guest_name="عميل",
            guest_phone="01000000000",
            guests_count=1,
            requested_date=date.today() + timedelta(days=2),
        )
        booking = services.create_online_booking(db, data)
        services.confirm_booking(db, booking.id, confirmed_by=1)
        with pytest.raises(ValueError, match="confirmed"):
            services.confirm_booking(db, booking.id, confirmed_by=1)

    def test_cancel_pending_booking(self, db, branch):
        data = OnlineBookingCreate(
            branch_id=branch.id,
            guest_name="عميل للإلغاء",
            guest_phone="01004000000",
            guests_count=1,
            requested_date=date.today() + timedelta(days=4),
        )
        booking = services.create_online_booking(db, data)
        cancelled = services.cancel_booking(db, booking.id)
        assert cancelled.status == "cancelled"
