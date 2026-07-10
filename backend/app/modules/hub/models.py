"""
app/modules/hub/models.py
Hub Module — المنصة الرقمية (موقع الريزورت + حجوزات أونلاين)
Tables: hub_pages, hub_offers, hub_online_bookings, hub_sitemap_logs
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer,
    Numeric, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.kernel.models.mixins import TimestampMixin
from app.core.database import Base


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
    guest_name:    Mapped[str]          = mapped_column(String(200))
    guest_phone:   Mapped[str]          = mapped_column(String(20))
    guest_email:   Mapped[str | None]   = mapped_column(String(150), nullable=True)
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
    """استفسار من موقع الويب → يتحول لـ Lead في CRM."""
    __tablename__ = "contact_forms"

    id:          Mapped[int]         = mapped_column(primary_key=True)
    branch_id:   Mapped[int]         = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    full_name:   Mapped[str]         = mapped_column(String(200))
    phone:       Mapped[str | None]  = mapped_column(String(20), nullable=True)
    email:       Mapped[str | None]  = mapped_column(String(150), nullable=True)
    subject:     Mapped[str]         = mapped_column(String(200))
    message:     Mapped[str]         = mapped_column(Text)
    source_page: Mapped[str | None]  = mapped_column(String(100), nullable=True)
    lead_id:     Mapped[int | None]  = mapped_column(Integer, nullable=True)
    # يُعبأ تلقائياً عند إنشاء Lead من هذا النموذج
    status:      Mapped[str]         = mapped_column(String(20), default="new")
    # new|converted|spam
