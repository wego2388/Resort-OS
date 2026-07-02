"""
app/modules/analytics/models.py
Analytics Module — KPI snapshots + Guest Reviews
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer,
    Numeric, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wego_core.models.mixins import TimestampMixin
from app.core.database import Base


class DailyStats(Base, TimestampMixin):
    """لقطة يومية للمؤشرات الرئيسية — تُولَّد بواسطة Celery أو Night Audit."""
    __tablename__ = "daily_stats"

    id:                Mapped[int]           = mapped_column(primary_key=True)
    branch_id:         Mapped[int]           = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    stat_date:         Mapped[date]          = mapped_column(Date, index=True)

    # PMS
    occupied_rooms:    Mapped[int]           = mapped_column(Integer, default=0)
    total_rooms:       Mapped[int]           = mapped_column(Integer, default=0)
    occupancy_pct:     Mapped[Decimal]       = mapped_column(Numeric(5, 2), default=Decimal("0"))
    adr:               Mapped[Decimal]       = mapped_column(Numeric(10, 2), default=Decimal("0"))   # Average Daily Rate
    revpar:            Mapped[Decimal]       = mapped_column(Numeric(10, 2), default=Decimal("0"))   # RevPAR
    room_revenue:      Mapped[Decimal]       = mapped_column(Numeric(12, 2), default=Decimal("0"))

    # Beach
    beach_visitors:    Mapped[int]           = mapped_column(Integer, default=0)
    beach_revenue:     Mapped[Decimal]       = mapped_column(Numeric(12, 2), default=Decimal("0"))

    # F&B
    restaurant_covers: Mapped[int]           = mapped_column(Integer, default=0)
    restaurant_revenue:Mapped[Decimal]       = mapped_column(Numeric(12, 2), default=Decimal("0"))
    cafe_revenue:      Mapped[Decimal]       = mapped_column(Numeric(12, 2), default=Decimal("0"))

    # Totals
    total_revenue:     Mapped[Decimal]       = mapped_column(Numeric(12, 2), default=Decimal("0"))
    generated_at:      Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class GuestReview(Base, TimestampMixin):
    """تقييم ضيف — يُربط بحجز أو يُدخل يدوياً."""
    __tablename__ = "guest_reviews"

    id:              Mapped[int]           = mapped_column(primary_key=True)
    branch_id:       Mapped[int]           = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    booking_id:      Mapped[int | None]    = mapped_column(ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True)
    guest_name:      Mapped[str]           = mapped_column(String(200))
    overall_rating:  Mapped[int]           = mapped_column(Integer)        # 1-5
    comment:         Mapped[str | None]    = mapped_column(Text, nullable=True)
    source:          Mapped[str]           = mapped_column(String(30), default="direct")
    # direct | booking.com | google | tripadvisor
    is_published:    Mapped[bool]          = mapped_column(Boolean, default=True)
    reviewed_at:     Mapped[date]          = mapped_column(Date)

    categories: Mapped[list["ReviewCategory"]] = relationship(
        "ReviewCategory", back_populates="review", lazy="select", cascade="all, delete-orphan"
    )


class ReviewCategory(Base, TimestampMixin):
    """تقييم تفصيلي لكل فئة: نظافة، خدمة، قيمة، شاطئ، إطعام."""
    __tablename__ = "review_categories"

    id:         Mapped[int]  = mapped_column(primary_key=True)
    review_id:  Mapped[int]  = mapped_column(ForeignKey("guest_reviews.id", ondelete="CASCADE"))
    category:   Mapped[str]  = mapped_column(String(30))     # service|cleanliness|value|beach|food|location
    rating:     Mapped[int]  = mapped_column(Integer)         # 1-5

    review: Mapped["GuestReview"] = relationship("GuestReview", back_populates="categories")


class UtilityReading(Base, TimestampMixin):
    """قراءات عدادات المرافق (كهرباء/مياه/غاز/ديزل) — مع تكلفة الوحدة والإجمالي
    لحساب مؤشر الطاقة (تكلفة كيلوواط/نزيل) وترحيل قيد مصروف تلقائي."""
    __tablename__ = "utility_readings"

    id:            Mapped[int]      = mapped_column(primary_key=True)
    branch_id:     Mapped[int]      = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    reading_date:  Mapped[date]     = mapped_column(Date, index=True)
    utility_type:  Mapped[str]      = mapped_column(String(20))   # electricity | water | gas | diesel
    reading_value: Mapped[Decimal]  = mapped_column(Numeric(12, 3))  # consumption
    unit:          Mapped[str]      = mapped_column(String(10), default="kWh")
    unit_cost:     Mapped[Decimal]  = mapped_column(Numeric(10, 2), default=Decimal("0"))
    total_cost:    Mapped[Decimal]  = mapped_column(Numeric(12, 2), default=Decimal("0"))
    notes:         Mapped[str | None] = mapped_column(String(300), nullable=True)
    recorded_by:   Mapped[int | None] = mapped_column(Integer, nullable=True)
