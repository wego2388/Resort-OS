"""app/modules/hub/crud.py — CRUD خالص، لا business logic"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.resort_os.timezone_utils import local_today

from app.modules.hub.models import HubOffer, HubOnlineBooking, HubPage, HubSitemapLog
from app.modules.hub.schemas import (
    HubOfferCreate, HubOfferUpdate,
    HubPageCreate, HubPageUpdate,
    OnlineBookingCreate, OnlineBookingUpdate,
)


# ── HubPage ───────────────────────────────────────────────────────────

def get_page(db: Session, page_id: int) -> Optional[HubPage]:
    return db.query(HubPage).filter(HubPage.id == page_id).first()


def get_page_by_slug(db: Session, slug: str) -> Optional[HubPage]:
    return db.query(HubPage).filter(HubPage.slug == slug).first()


def list_pages(
    db: Session,
    branch_id: int,
    published_only: bool = False,
    page_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[HubPage], int]:
    q = db.query(HubPage).filter(HubPage.branch_id == branch_id)
    if published_only:
        q = q.filter(HubPage.is_published.is_(True))
    if page_type:
        q = q.filter(HubPage.page_type == page_type)
    total = q.count()
    items = q.order_by(HubPage.sort_order, HubPage.title).offset(skip).limit(limit).all()
    return items, total


def create_page(db: Session, data: HubPageCreate) -> HubPage:
    obj = HubPage(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def update_page(db: Session, page: HubPage, data: HubPageUpdate) -> HubPage:
    updates = data.model_dump(exclude_unset=True)
    if updates.get("is_published") is True and not page.is_published:
        updates["published_at"] = datetime.utcnow()
    for field, value in updates.items():
        setattr(page, field, value)
    db.flush()
    return page


def delete_page(db: Session, page: HubPage) -> None:
    db.delete(page)
    db.flush()


def count_published_pages(db: Session, branch_id: int) -> int:
    return db.query(HubPage).filter(
        HubPage.branch_id == branch_id,
        HubPage.is_published.is_(True),
    ).count()


# ── HubOffer ──────────────────────────────────────────────────────────

def get_offer(db: Session, offer_id: int) -> Optional[HubOffer]:
    return db.query(HubOffer).filter(HubOffer.id == offer_id).first()


def list_offers(
    db: Session,
    branch_id: int,
    active_only: bool = True,
    offer_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[HubOffer], int]:
    q = db.query(HubOffer).filter(HubOffer.branch_id == branch_id)
    if active_only:
        # #tz-fix: local_today بدل date.today() — العروض بتُعرض على الضيوف اللي
        # بيبصوا على hub من توقيتهم المحلي، مش توقيت UTC للسيرفر. عرض valid_until
        # = 2026-07-09 مفروض يظهر طوال يوم 9 يوليو بتوقيت القاهرة، مش يختفي الساعة
        # 9 مساءً بتوقيت UTC (= منتصف ليل Cairo+3).
        today = local_today(settings.TIMEZONE)
        q = q.filter(
            HubOffer.is_active.is_(True),
            HubOffer.valid_from <= today,
            HubOffer.valid_until >= today,
        )
    if offer_type:
        q = q.filter(HubOffer.offer_type == offer_type)
    total = q.count()
    items = q.order_by(HubOffer.valid_until).offset(skip).limit(limit).all()
    return items, total


def create_offer(db: Session, data: HubOfferCreate) -> HubOffer:
    obj = HubOffer(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def update_offer(db: Session, offer: HubOffer, data: HubOfferUpdate) -> HubOffer:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(offer, field, value)
    db.flush()
    return offer


def increment_offer_bookings(db: Session, offer_id: int) -> None:
    offer = get_offer(db, offer_id)
    if offer:
        offer.bookings_count += 1
        db.flush()


# ── HubOnlineBooking ──────────────────────────────────────────────────

def get_online_booking(db: Session, booking_id: int) -> Optional[HubOnlineBooking]:
    return db.query(HubOnlineBooking).filter(HubOnlineBooking.id == booking_id).first()


def list_online_bookings(
    db: Session,
    branch_id: int,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[HubOnlineBooking], int]:
    q = db.query(HubOnlineBooking).filter(HubOnlineBooking.branch_id == branch_id)
    if status:
        q = q.filter(HubOnlineBooking.status == status)
    if date_from:
        q = q.filter(HubOnlineBooking.requested_date >= date_from)
    if date_to:
        q = q.filter(HubOnlineBooking.requested_date <= date_to)
    total = q.count()
    items = q.order_by(HubOnlineBooking.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def create_online_booking(db: Session, data: OnlineBookingCreate) -> HubOnlineBooking:
    obj = HubOnlineBooking(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def update_online_booking(
    db: Session,
    booking: HubOnlineBooking,
    data: OnlineBookingUpdate,
    confirmed_by: Optional[int] = None,
) -> HubOnlineBooking:
    updates = data.model_dump(exclude_unset=True)
    if updates.get("status") == "confirmed" and not booking.confirmed_at:
        updates["confirmed_at"] = datetime.utcnow()
        updates["confirmed_by"] = confirmed_by
    for field, value in updates.items():
        setattr(booking, field, value)
    db.flush()
    return booking


# ── SitemapLog ────────────────────────────────────────────────────────

def log_sitemap(
    db: Session,
    branch_id: int,
    pages_count: int,
    status: str = "success",
    error: Optional[str] = None,
) -> HubSitemapLog:
    obj = HubSitemapLog(
        branch_id=branch_id,
        pages_count=pages_count,
        status=status,
        generated_at=datetime.utcnow(),
        error=error,
    )
    db.add(obj)
    db.flush()
    return obj
