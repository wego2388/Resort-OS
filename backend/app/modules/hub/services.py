"""app/modules/hub/services.py — Business logic"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.resort_os.timezone_utils import local_today

from app.modules.hub import crud

logger = logging.getLogger(__name__)
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
        today = local_today(settings.TIMEZONE)
        # #tz-fix: local_today بدل date.today() — نفس فئة الباج في hub/crud.py:
        # صلاحية العرض بتُقيَّم وقت حجز الضيف — لازم تكون بتوقيت المنتجع
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
    """يُؤكِّد طلب الحجز الأونلاين.

    لو الطلب عنده check_in + check_out + room_type_id:
      → بيُنشئ PMS Booking تلقائياً ويحفظ pms_booking_id
      → الريسبشن يشوف الحجز فوراً في شاشة الحجوزات
    لو البيانات ناقصة:
      → بيُؤكِّد فقط بدون PMS — المدير يعمل الحجز يدوياً لاحقاً
    """
    booking = get_booking_or_404(db, booking_id)
    if booking.status != "pending":
        raise ValueError(f"الحجز في حالة '{booking.status}' ولا يمكن تأكيده")

    pms_booking_id = None

    # محاولة إنشاء PMS booking تلقائياً لو البيانات مكتملة
    if booking.check_in and booking.check_out and booking.room_type_id:
        try:
            from app.modules.pms.services import create_booking as pms_create  # noqa: PLC0415
            from app.modules.pms.schemas import BookingCreate                  # noqa: PLC0415

            nights = (booking.check_out - booking.check_in).days
            if nights > 0:
                # ابحث عن غرفة متاحة من هذا النوع في الفترة المطلوبة
                from app.modules.pms.crud import get_available_rooms  # noqa: PLC0415
                available = get_available_rooms(
                    db,
                    branch_id=booking.branch_id,
                    check_in=booking.check_in,
                    check_out=booking.check_out,
                    room_type_id=booking.room_type_id,
                )
                if not available:
                    logger.warning(
                        "Hub #%s: لا توجد غرف متاحة من النوع %s في الفترة %s→%s",
                        booking.id, booking.room_type_id, booking.check_in, booking.check_out,
                    )
                else:
                    pms_b = pms_create(db, BookingCreate(
                        branch_id=booking.branch_id,
                        guest_name=booking.guest_name,
                        guest_phone=booking.guest_phone,
                        guest_email=booking.guest_email,
                        check_in=booking.check_in,
                        check_out=booking.check_out,
                        adults=booking.adults or 1,
                        children=0,
                        room_ids=[available[0].id],
                        source="online",
                        notes=f"حجز من الموقع — Hub #{booking.id}\n{booking.notes or ''}".strip(),
                    ))
                    pms_booking_id = pms_b.id
                    logger.info(
                        "Hub booking #%s → PMS booking #%s (room #%s) created automatically",
                        booking.id, pms_b.id, available[0].id,
                    )
                pms_booking_id = pms_b.id
                logger.info(
                    "Hub booking #%s → PMS booking #%s created automatically",
                    booking.id, pms_b.id,
                )
        except Exception:
            logger.error(
                "confirm_booking: فشل إنشاء PMS booking لـ Hub #%s — يحتاج إنشاء يدوي",
                booking.id, exc_info=True,
            )

    update = OnlineBookingUpdate(status="confirmed")
    obj = crud.update_online_booking(db, booking, update, confirmed_by=confirmed_by)
    if pms_booking_id:
        obj.pms_booking_id = pms_booking_id
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
