"""app/modules/hub/services.py — Business logic"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.modules.hub import crud
from app.modules.hub.models import HubOffer, HubOnlineBooking, HubPage
from app.modules.hub.schemas import (
    HubOfferCreate, HubOfferUpdate,
    HubPageCreate, HubPageUpdate,
    OnlineBookingCreate, OnlineBookingUpdate,
)


# ── HubPage ───────────────────────────────────────────────────────────

def get_page_or_404(db: Session, page_id: int) -> HubPage:
    page = crud.get_page(db, page_id)
    if not page:
        raise ValueError(f"الصفحة {page_id} غير موجودة")
    return page


def create_page(db: Session, data: HubPageCreate) -> HubPage:
    existing = crud.get_page_by_slug(db, data.slug)
    if existing:
        raise ValueError(f"الـ slug '{data.slug}' مستخدم مسبقاً")
    obj = crud.create_page(db, data)
    db.commit()
    db.refresh(obj)
    return obj


def update_page(db: Session, page_id: int, data: HubPageUpdate) -> HubPage:
    page = get_page_or_404(db, page_id)
    obj = crud.update_page(db, page, data)
    db.commit()
    db.refresh(obj)
    return obj


def delete_page(db: Session, page_id: int) -> None:
    page = get_page_or_404(db, page_id)
    crud.delete_page(db, page)
    db.commit()


# ── HubOffer ──────────────────────────────────────────────────────────

def get_offer_or_404(db: Session, offer_id: int) -> HubOffer:
    offer = crud.get_offer(db, offer_id)
    if not offer:
        raise ValueError(f"العرض {offer_id} غير موجود")
    return offer


def create_offer(db: Session, data: HubOfferCreate) -> HubOffer:
    if data.valid_from > data.valid_until:
        raise ValueError("valid_from يجب أن يكون قبل valid_until")
    if data.offer_price >= data.original_price:
        raise ValueError("سعر العرض يجب أن يكون أقل من السعر الأصلي")
    obj = crud.create_offer(db, data)
    db.commit()
    db.refresh(obj)
    return obj


def update_offer(db: Session, offer_id: int, data: HubOfferUpdate) -> HubOffer:
    offer = get_offer_or_404(db, offer_id)
    obj = crud.update_offer(db, offer, data)
    db.commit()
    db.refresh(obj)
    return obj


# ── HubOnlineBooking ──────────────────────────────────────────────────

def get_booking_or_404(db: Session, booking_id: int) -> HubOnlineBooking:
    b = crud.get_online_booking(db, booking_id)
    if not b:
        raise ValueError(f"الحجز الإلكتروني {booking_id} غير موجود")
    return b


def create_online_booking(db: Session, data: OnlineBookingCreate) -> HubOnlineBooking:
    if data.offer_id:
        offer = crud.get_offer(db, data.offer_id)
        if not offer:
            raise ValueError("العرض المحدد غير موجود")
        if not offer.is_active:
            raise ValueError("هذا العرض غير متاح حالياً")
        today = date.today()
        if not (offer.valid_from <= today <= offer.valid_until):
            raise ValueError("هذا العرض منتهي الصلاحية")
        if offer.max_bookings != -1 and offer.bookings_count >= offer.max_bookings:
            raise ValueError("تم استنفاد طاقة الحجز لهذا العرض")

    obj = crud.create_online_booking(db, data)

    if data.offer_id:
        crud.increment_offer_bookings(db, data.offer_id)

    db.commit()
    db.refresh(obj)
    return obj


def confirm_booking(db: Session, booking_id: int, confirmed_by: int) -> HubOnlineBooking:
    booking = get_booking_or_404(db, booking_id)
    if booking.status != "pending":
        raise ValueError(f"الحجز في حالة '{booking.status}' ولا يمكن تأكيده")
    update = OnlineBookingUpdate(status="confirmed")
    obj = crud.update_online_booking(db, booking, update, confirmed_by=confirmed_by)
    db.commit()
    db.refresh(obj)
    return obj


def cancel_booking(db: Session, booking_id: int) -> HubOnlineBooking:
    booking = get_booking_or_404(db, booking_id)
    if booking.status in ("confirmed", "cancelled"):
        raise ValueError(f"لا يمكن إلغاء حجز في حالة '{booking.status}'")
    update = OnlineBookingUpdate(status="cancelled")
    obj = crud.update_online_booking(db, booking, update)
    db.commit()
    db.refresh(obj)
    return obj


def refresh_sitemap(db: Session, branch_id: int) -> int:
    """
    يُستدعى من Celery task — يُحدّث سجل الـ sitemap.
    يُرجع عدد الصفحات المنشورة.
    """
    try:
        pages_count = crud.count_published_pages(db, branch_id)
        crud.log_sitemap(db, branch_id, pages_count, status="success")
        db.commit()
        return pages_count
    except Exception as exc:
        crud.log_sitemap(db, branch_id, 0, status="failed", error=str(exc))
        db.commit()
        raise
