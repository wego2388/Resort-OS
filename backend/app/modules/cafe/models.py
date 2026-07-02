"""
app/modules/cafe/models.py
Cafe Module — يشارك نفس منطق الـ restaurant لكن جداول منفصلة
Tables: cafe_categories, cafe_items, cafe_tables, cafe_orders, cafe_order_items
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wego_core.models.mixins import TimestampMixin
from app.core.database import Base


class CafeCategory(Base, TimestampMixin):
    __tablename__ = "cafe_categories"

    id:         Mapped[int]        = mapped_column(primary_key=True)
    branch_id:  Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    name:       Mapped[str]        = mapped_column(String(100))
    name_ar:    Mapped[str | None] = mapped_column(String(100), nullable=True)
    sort_order: Mapped[int]        = mapped_column(Integer, default=0)
    is_active:  Mapped[bool]       = mapped_column(Boolean, default=True)

    items: Mapped[list["CafeItem"]] = relationship("CafeItem", back_populates="category", lazy="select")


class CafeItem(Base, TimestampMixin):
    __tablename__ = "cafe_items"

    id:                  Mapped[int]         = mapped_column(primary_key=True)
    branch_id:           Mapped[int]         = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    category_id:         Mapped[int | None]  = mapped_column(ForeignKey("cafe_categories.id", ondelete="SET NULL"), nullable=True)
    name:                Mapped[str]         = mapped_column(String(200))
    name_ar:             Mapped[str | None]  = mapped_column(String(200), nullable=True)
    price:               Mapped[Decimal]     = mapped_column(Numeric(10, 2))
    cost:                Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    is_available:        Mapped[bool]        = mapped_column(Boolean, default=True)
    preparation_minutes: Mapped[int]         = mapped_column(Integer, default=5)
    image_url:           Mapped[str | None]  = mapped_column(String(500), nullable=True)

    category: Mapped["CafeCategory"] = relationship("CafeCategory", back_populates="items")


class CafeTable(Base, TimestampMixin):
    __tablename__ = "cafe_tables"

    id:           Mapped[int]        = mapped_column(primary_key=True)
    branch_id:    Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    table_number: Mapped[str]        = mapped_column(String(20))
    capacity:     Mapped[int]        = mapped_column(Integer, default=2)
    status:       Mapped[str]        = mapped_column(String(30), default="available")
    section:      Mapped[str | None] = mapped_column(String(50), nullable=True)


class CafeOrder(Base, TimestampMixin):
    __tablename__ = "cafe_orders"

    id:             Mapped[int]        = mapped_column(primary_key=True)
    branch_id:      Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    table_id:       Mapped[int | None] = mapped_column(ForeignKey("cafe_tables.id", ondelete="SET NULL"), nullable=True)
    order_number:   Mapped[str]        = mapped_column(String(30), unique=True)
    status:         Mapped[str]        = mapped_column(String(30), default="open")
    order_type:     Mapped[str]        = mapped_column(String(30), default="dine_in")
    subtotal:       Mapped[Decimal]    = mapped_column(Numeric(10, 2), default=Decimal("0"))
    vat_amount:     Mapped[Decimal]    = mapped_column(Numeric(10, 2), default=Decimal("0"))
    service_charge: Mapped[Decimal]    = mapped_column(Numeric(10, 2), default=Decimal("0"))
    discount_amount:Mapped[Decimal]    = mapped_column(Numeric(10, 2), default=Decimal("0"))
    total:          Mapped[Decimal]    = mapped_column(Numeric(10, 2), default=Decimal("0"))
    notes:          Mapped[str | None] = mapped_column(String(500), nullable=True)
    waiter_id:      Mapped[int | None] = mapped_column(Integer, nullable=True)
    folio_id:       Mapped[int | None] = mapped_column(Integer, nullable=True)

    table: Mapped["CafeTable"] = relationship("CafeTable", lazy="select")
    items: Mapped[list["CafeOrderItem"]] = relationship(
        "CafeOrderItem", back_populates="order", lazy="select", cascade="all, delete-orphan"
    )


class CafeOrderItem(Base, TimestampMixin):
    __tablename__ = "cafe_order_items"

    id:          Mapped[int]        = mapped_column(primary_key=True)
    order_id:    Mapped[int]        = mapped_column(ForeignKey("cafe_orders.id", ondelete="CASCADE"))
    item_id:     Mapped[int]        = mapped_column(ForeignKey("cafe_items.id", ondelete="RESTRICT"))
    name:        Mapped[str]        = mapped_column(String(200))
    unit_price:  Mapped[Decimal]    = mapped_column(Numeric(10, 2))
    quantity:    Mapped[int]        = mapped_column(Integer, default=1)
    notes:       Mapped[str | None] = mapped_column(String(200), nullable=True)
    status:      Mapped[str]        = mapped_column(String(20), default="pending")

    order: Mapped["CafeOrder"] = relationship("CafeOrder", back_populates="items")
