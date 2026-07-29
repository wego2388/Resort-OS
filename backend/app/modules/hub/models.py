"""
app/modules/hub/models.py
Hub Module — المنصة الرقمية (موقع الريزورت + حجوزات أونلاين)
Tables: hub_pages, hub_offers, hub_online_bookings, hub_sitemap_logs
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import secrets

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.kernel.models.mixins import TimestampMixin
from app.core.database import Base
from app.core.encryption import EncryptedString


def _new_contact_reference() -> str:
    return f"contact_{secrets.token_urlsafe(16)}"


def _default_contact_retention() -> datetime:
    return datetime.utcnow() + timedelta(days=180)


class HubPage(Base, TimestampMixin):
    """صفحة محتوى على الموقع (عروض، أخبار، وصف خدمات...)."""
    __tablename__ = "hub_pages"

    id:          Mapped[int]          = mapped_column(primary_key=True)
    branch_id:   Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    slug:        Mapped[str]          = mapped_column(String(100), unique=True)
    title:       Mapped[str]          = mapped_column(String(300))
    title_ar:    Mapped[str | None]   = mapped_column(String(300), nullable=True)
    content:     Mapped[str | None]   = mapped_column(Text, nullable=True)     # HTML/Markdown
    content_ar:  Mapped[str | None]   = mapped_column(Text, nullable=True)
    page_type:   Mapped[str]          = mapped_column(String(30), default="info")
    # info|offer|news|gallery|contact
    is_published: Mapped[bool]        = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    meta_title:   Mapped[str | None]  = mapped_column(String(200), nullable=True)
    meta_desc:    Mapped[str | None]  = mapped_column(String(300), nullable=True)
    sort_order:   Mapped[int]         = mapped_column(Integer, default=100)


class HubOffer(Base, TimestampMixin):
    """عرض مميز قابل للحجز من الموقع."""
    __tablename__ = "hub_offers"

    id:            Mapped[int]          = mapped_column(primary_key=True)
    branch_id:     Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    title:         Mapped[str]          = mapped_column(String(300))
    title_ar:      Mapped[str | None]   = mapped_column(String(300), nullable=True)
    description:   Mapped[str | None]   = mapped_column(Text, nullable=True)
    description_ar: Mapped[str | None]  = mapped_column(Text, nullable=True)
    offer_type:    Mapped[str]          = mapped_column(String(30))
    # room|beach|restaurant|package|event
    original_price: Mapped[Decimal]     = mapped_column(Numeric(10, 2))
    offer_price:    Mapped[Decimal]     = mapped_column(Numeric(10, 2))
    valid_from:    Mapped[date]         = mapped_column(Date)
    valid_until:   Mapped[date]         = mapped_column(Date)
    max_bookings:  Mapped[int]          = mapped_column(Integer, default=-1)  # -1 = unlimited
    bookings_count: Mapped[int]         = mapped_column(Integer, default=0)
    is_active:     Mapped[bool]         = mapped_column(Boolean, default=True)
    image_url:     Mapped[str | None]   = mapped_column(String(500), nullable=True)

    online_bookings: Mapped[list["HubOnlineBooking"]] = relationship(
        "HubOnlineBooking", back_populates="offer", lazy="select"
    )


class HubOnlineBooking(Base, TimestampMixin):
    """طلب حجز وارد من الموقع — ينتظر التأكيد من الفندق."""
    __tablename__ = "hub_online_bookings"

    id:            Mapped[int]          = mapped_column(primary_key=True)
    branch_id:     Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    offer_id:      Mapped[int | None]   = mapped_column(ForeignKey("hub_offers.id", ondelete="SET NULL"), nullable=True)
    # ⚠️ باج حقيقي كان هنا (اتصلح 2026-07-28): بيانات ضيف واردة من الموقع
    # العام كانت متخزّنة عادي (plaintext) — عكس Lead/ContactForm في نفس
    # الموديول اللي بيشفّروا نفس نوع البيانات دي بالظبط. مفيش أي فلترة/بحث
    # WHERE على الحقول دي في crud.py، فالتشفير آمن من غير كسر أي استعلام.
    # الأطوال (512/255) نفس ContactForm تحت بالظبط — ناتج Fernet أطول بكتير
    # من النص الأصلي، String(20) العادي كان هيقطع أي رقم تليفون مشفّر فعليًا.
    guest_name:    Mapped[str]          = mapped_column(EncryptedString(512))
    guest_phone:   Mapped[str]          = mapped_column(EncryptedString(255))
    guest_email:   Mapped[str | None]   = mapped_column(EncryptedString(512), nullable=True)
    guests_count:  Mapped[int]          = mapped_column(Integer, default=1)
    requested_date: Mapped[date]        = mapped_column(Date)
    notes:         Mapped[str | None]   = mapped_column(Text, nullable=True)
    status:        Mapped[str]          = mapped_column(String(30), default="pending")
    # pending|confirmed|cancelled|no_show
    source:        Mapped[str]          = mapped_column(String(30), default="website")
    # website|whatsapp|instagram|tiktok|other
    confirmed_by:  Mapped[int | None]   = mapped_column(Integer, nullable=True)
    confirmed_at:  Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_amount:  Mapped[Decimal]      = mapped_column(Numeric(10, 2), default=Decimal("0"))
    # بيانات الإقامة — اختيارية، لو موجودة بيتنشأ PMS booking تلقائياً عند التأكيد
    check_in:      Mapped[date | None]  = mapped_column(Date, nullable=True)
    check_out:     Mapped[date | None]  = mapped_column(Date, nullable=True)
    room_type_id:  Mapped[int | None]   = mapped_column(Integer, nullable=True)
    adults:        Mapped[int]          = mapped_column(Integer, default=1)
    # الحجز الفعلي في PMS اللي اتنشأ عند التأكيد (None = لو الطلب بيانات ناقصة أو تأكيد يدوي)
    pms_booking_id: Mapped[int | None]  = mapped_column(
        ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True,
    )

    offer: Mapped["HubOffer | None"] = relationship("HubOffer", back_populates="online_bookings")


class HubSitemapLog(Base, TimestampMixin):
    """سجل آخر تحديث للـ sitemap."""
    __tablename__ = "hub_sitemap_logs"

    id:          Mapped[int]      = mapped_column(primary_key=True)
    branch_id:   Mapped[int]      = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    pages_count: Mapped[int]      = mapped_column(Integer, default=0)
    status:      Mapped[str]      = mapped_column(String(20), default="success")
    generated_at: Mapped[datetime] = mapped_column(DateTime)
    error:       Mapped[str | None] = mapped_column(String(500), nullable=True)


class BlogPost(Base, TimestampMixin):
    """مقال في المدونة التسويقية."""
    __tablename__ = "blog_posts"

    id:           Mapped[int]          = mapped_column(primary_key=True)
    branch_id:    Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    title:        Mapped[str]          = mapped_column(String(300))
    slug:         Mapped[str]          = mapped_column(String(300), unique=True)
    excerpt:      Mapped[str | None]   = mapped_column(String(500), nullable=True)
    body:         Mapped[str]          = mapped_column(Text)
    cover_image:  Mapped[str | None]   = mapped_column(String(300), nullable=True)
    # SEO fields
    meta_title:       Mapped[str | None] = mapped_column(String(300), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status:       Mapped[str]          = mapped_column(String(20), default="draft")
    # draft|published|archived
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    author_id:    Mapped[int]          = mapped_column(Integer)
    views_count:  Mapped[int]          = mapped_column(Integer, default=0)


class ContactForm(Base, TimestampMixin):
    """Privacy-scoped public service contact.

    Contact details and free text are encrypted at rest.  A CRM lead is a
    separate, optional outcome that requires explicit marketing consent.
    """
    __tablename__ = "contact_forms"
    __table_args__ = (
        Index(
            "uq_contact_forms_branch_idempotency",
            "branch_id",
            "idempotency_key_hash",
            unique=True,
            postgresql_where=text("idempotency_key_hash IS NOT NULL"),
            sqlite_where=text("idempotency_key_hash IS NOT NULL"),
        ),
        Index(
            "ix_contact_forms_retention_due",
            "retention_until",
            "purged_at",
        ),
    )

    id:          Mapped[int]         = mapped_column(primary_key=True)
    branch_id:   Mapped[int]         = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    public_reference: Mapped[str]     = mapped_column(
        String(48),
        unique=True,
        index=True,
        default=_new_contact_reference,
    )
    full_name:   Mapped[str | None]  = mapped_column(EncryptedString(512), nullable=True)
    phone:       Mapped[str | None]  = mapped_column(EncryptedString(255), nullable=True)
    email:       Mapped[str | None]  = mapped_column(EncryptedString(512), nullable=True)
    subject:     Mapped[str | None]  = mapped_column(EncryptedString(512), nullable=True)
    message:     Mapped[str | None]  = mapped_column(EncryptedString(), nullable=True)
    source_page: Mapped[str | None]  = mapped_column(String(100), nullable=True)
    source:      Mapped[str]         = mapped_column(String(30), default="public_website")
    purpose:     Mapped[str]         = mapped_column(String(40), default="general_inquiry")
    language:    Mapped[str]         = mapped_column(String(5), default="ar")

    service_contact_authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    service_disclosure_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    service_contact_authorized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    marketing_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    marketing_consent_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    marketing_consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requester_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    retention_until: Mapped[datetime] = mapped_column(
        DateTime,
        index=True,
        default=_default_contact_retention,
    )
    purged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    lead_id:     Mapped[int | None]  = mapped_column(Integer, nullable=True)
    # lead_id is populated only after explicit marketing consent.
    crm_sync_status: Mapped[str] = mapped_column(String(20), default="not_requested")
    # not_requested|created|failed
    status:      Mapped[str]         = mapped_column(String(20), default="accepted")
    # accepted|purged|spam
