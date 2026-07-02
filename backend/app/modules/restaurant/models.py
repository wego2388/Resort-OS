"""
app/modules/restaurant/models.py
Restaurant Module
Tables: menu_categories, menu_items, menu_item_extra_groups, menu_item_extras,
        dining_tables, orders, order_items, order_item_extras
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, JSON,
    Numeric, String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wego_core.models.mixins import TimestampMixin
from app.core.database import Base


class MenuCategory(Base, TimestampMixin):
    __tablename__ = "menu_categories"

    id:         Mapped[int]        = mapped_column(primary_key=True)
    branch_id:  Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    name:       Mapped[str]        = mapped_column(String(100))
    name_ar:    Mapped[str | None] = mapped_column(String(100), nullable=True)
    sort_order: Mapped[int]        = mapped_column(Integer, default=0)
    is_active:  Mapped[bool]       = mapped_column(Boolean, default=True)

    items: Mapped[list["MenuItem"]] = relationship("MenuItem", back_populates="category", lazy="select")


class MenuItem(Base, TimestampMixin):
    __tablename__ = "menu_items"

    id:                   Mapped[int]         = mapped_column(primary_key=True)
    branch_id:            Mapped[int]         = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    category_id:          Mapped[int | None]  = mapped_column(ForeignKey("menu_categories.id", ondelete="SET NULL"), nullable=True)
    name:                 Mapped[str]         = mapped_column(String(200))
    name_ar:              Mapped[str | None]  = mapped_column(String(200), nullable=True)
    price:                Mapped[Decimal]     = mapped_column(Numeric(10, 2))
    cost:                 Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    is_available:         Mapped[bool]        = mapped_column(Boolean, default=True)
    preparation_minutes:  Mapped[int]         = mapped_column(Integer, default=10)
    image_url:            Mapped[str | None]  = mapped_column(String(500), nullable=True)
    station:              Mapped[str]         = mapped_column(String(50), default="hot")  # hot|grill|cold|bar|dessert — لتوجيه الـ KDS تلقائياً
    linked_product_id:    Mapped[int | None]  = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    # ربط اختياري بصنف مخزني (inventory.Product) — لو موجود، دفع الطلب بيخصم
    # المخزون تلقائياً (استهلاك). معظم الأصناف مفهاش ربط، وده متوقع.

    category: Mapped["MenuCategory"] = relationship("MenuCategory", back_populates="items")
    extra_groups: Mapped[list["MenuItemExtraGroup"]] = relationship(
        "MenuItemExtraGroup", back_populates="menu_item", lazy="select",
        cascade="all, delete-orphan", order_by="MenuItemExtraGroup.sort_order",
    )


class MenuItemExtraGroup(Base, TimestampMixin):
    """مجموعة اختيارات لصنف — مثال: 'اختر الحجم' أو 'إضافات'."""
    __tablename__ = "menu_item_extra_groups"

    id:           Mapped[int]        = mapped_column(primary_key=True)
    menu_item_id: Mapped[int]        = mapped_column(ForeignKey("menu_items.id", ondelete="CASCADE"))
    name:         Mapped[str]        = mapped_column(String(100))
    name_ar:      Mapped[str | None] = mapped_column(String(100), nullable=True)
    min_select:   Mapped[int]        = mapped_column(Integer, default=0)   # 0 = اختياري
    max_select:   Mapped[int]        = mapped_column(Integer, default=1)   # 1 = اختيار واحد (radio)، أكثر = متعدد (checkboxes)
    sort_order:   Mapped[int]        = mapped_column(Integer, default=0)

    menu_item: Mapped["MenuItem"] = relationship("MenuItem", back_populates="extra_groups")
    options: Mapped[list["MenuItemExtra"]] = relationship(
        "MenuItemExtra", back_populates="group", lazy="select",
        cascade="all, delete-orphan", order_by="MenuItemExtra.sort_order",
    )


class MenuItemExtra(Base, TimestampMixin):
    """خيار داخل مجموعة — مثال: 'كبير' أو 'جبنة إضافية'."""
    __tablename__ = "menu_item_extras"

    id:              Mapped[int]     = mapped_column(primary_key=True)
    group_id:        Mapped[int]     = mapped_column(ForeignKey("menu_item_extra_groups.id", ondelete="CASCADE"))
    name:            Mapped[str]     = mapped_column(String(100))
    name_ar:         Mapped[str | None] = mapped_column(String(100), nullable=True)
    price_addition:  Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    is_available:    Mapped[bool]    = mapped_column(Boolean, default=True)
    sort_order:      Mapped[int]     = mapped_column(Integer, default=0)

    group: Mapped["MenuItemExtraGroup"] = relationship("MenuItemExtraGroup", back_populates="options")


class DiningTable(Base, TimestampMixin):
    __tablename__ = "dining_tables"

    id:           Mapped[int]        = mapped_column(primary_key=True)
    branch_id:    Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    table_number: Mapped[str]        = mapped_column(String(20))
    capacity:     Mapped[int]        = mapped_column(Integer, default=4)
    status:       Mapped[str]        = mapped_column(String(30), default="available")  # available|occupied|reserved|out_of_service
    section:      Mapped[str | None] = mapped_column(String(50), nullable=True)
    occupied_at:  Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # وقت آخر ما بقت occupied — لمعرفة مدة الجلوس


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id:                      Mapped[int]         = mapped_column(primary_key=True)
    branch_id:               Mapped[int]         = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    table_id:                Mapped[int | None]  = mapped_column(ForeignKey("dining_tables.id", ondelete="SET NULL"), nullable=True)
    order_number:            Mapped[str]         = mapped_column(String(30), unique=True)  # ORD-20260630-0001
    status:                  Mapped[str]         = mapped_column(String(30), default="open")   # open|in_kitchen|served|paid|cancelled
    order_type:              Mapped[str]         = mapped_column(String(30), default="dine_in") # dine_in|takeaway|delivery|room_service
    subtotal:                Mapped[Decimal]     = mapped_column(Numeric(10, 2), default=Decimal("0"))
    vat_amount:              Mapped[Decimal]     = mapped_column(Numeric(10, 2), default=Decimal("0"))
    service_charge:          Mapped[Decimal]     = mapped_column(Numeric(10, 2), default=Decimal("0"))
    discount_amount:         Mapped[Decimal]     = mapped_column(Numeric(10, 2), default=Decimal("0"))
    total:                   Mapped[Decimal]     = mapped_column(Numeric(10, 2), default=Decimal("0"))
    guests_count:            Mapped[int]         = mapped_column(Integer, default=1)
    notes:                   Mapped[str | None]  = mapped_column(String(500), nullable=True)
    waiter_id:               Mapped[int | None]  = mapped_column(Integer, nullable=True)
    folio_id:                Mapped[int | None]  = mapped_column(Integer, nullable=True)
    applied_discount_rule_id:Mapped[int | None]  = mapped_column(Integer, nullable=True)
    customer_id:             Mapped[int | None]  = mapped_column(ForeignKey("crm_customers.id", ondelete="SET NULL"), nullable=True)
    # ربط اختياري بعميل CRM — لو موجود، دفع الطلب بيحدّث total_spent/visits_count
    # بتاعه تلقائيًا (راجع crm.services.record_visit)
    client_local_id:         Mapped[str | None]  = mapped_column(String(60), nullable=True, unique=True)
    # UUID من IndexedDB عند الـ offline POS — يمنع تكرار الطلب لو الـ client
    # حاول الـ sync تاني بعد انقطاع اتصال جزئي (نفس الطلب يرجع بدل ما يتكرر)

    table: Mapped["DiningTable"] = relationship("DiningTable", lazy="select")
    items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order", lazy="select", cascade="all, delete-orphan")


class OrderItem(Base, TimestampMixin):
    __tablename__ = "order_items"

    id:           Mapped[int]        = mapped_column(primary_key=True)
    order_id:     Mapped[int]        = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    menu_item_id: Mapped[int]        = mapped_column(ForeignKey("menu_items.id", ondelete="RESTRICT"))
    name:         Mapped[str]        = mapped_column(String(200))          # snapshot
    unit_price:   Mapped[Decimal]    = mapped_column(Numeric(10, 2))       # snapshot
    quantity:     Mapped[int]        = mapped_column(Integer, default=1)
    notes:        Mapped[str | None] = mapped_column(String(200), nullable=True)
    status:       Mapped[str]        = mapped_column(String(20), default="pending")  # pending|in_kitchen|ready|served|cancelled
    voided_reason:Mapped[str | None] = mapped_column(String(200), nullable=True)
    voided_by:    Mapped[int | None] = mapped_column(Integer, nullable=True)  # user.id اللي لغى الصنف — للمحاسبية
    voided_at:    Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    extras: Mapped[list["OrderItemExtra"]] = relationship(
        "OrderItemExtra", back_populates="order_item", lazy="select", cascade="all, delete-orphan",
    )


class OrderItemExtra(Base, TimestampMixin):
    """snapshot للإضافة المختارة وقت الطلب — زي name/unit_price في OrderItem،
    لو الاختيار الأصلي (MenuItemExtra) اتغيّر سعره بعدين ميأثرش على طلبات قديمة."""
    __tablename__ = "order_item_extras"

    id:             Mapped[int]      = mapped_column(primary_key=True)
    order_item_id:  Mapped[int]      = mapped_column(ForeignKey("order_items.id", ondelete="CASCADE"))
    extra_id:       Mapped[int | None] = mapped_column(ForeignKey("menu_item_extras.id", ondelete="SET NULL"), nullable=True)
    extra_name:     Mapped[str]      = mapped_column(String(100))
    price_addition: Mapped[Decimal]  = mapped_column(Numeric(10, 2), default=Decimal("0"))

    order_item: Mapped["OrderItem"] = relationship("OrderItem", back_populates="extras")


class KitchenTicket(Base, TimestampMixin):
    """تذكرة تتبعت للمطبخ لما الطلب يروح in_kitchen."""
    __tablename__ = "kitchen_tickets"

    id:             Mapped[int]  = mapped_column(primary_key=True)
    branch_id:      Mapped[int]  = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    order_id:       Mapped[int]  = mapped_column(Integer)  # ID من orders أو cafe_orders حسب module
    module:         Mapped[str]  = mapped_column(String(20), default="restaurant")  # restaurant|cafe
    station:        Mapped[str]  = mapped_column(String(50))  # hot|grill|cold|bar|...
    items_snapshot: Mapped[dict] = mapped_column(JSON)  # الأصناف الخاصة بالمحطة دي بس
    status:         Mapped[str]  = mapped_column(String(20), default="pending")  # pending|in_progress|done


class KDSScreen(Base, TimestampMixin):
    """إعداد شاشة KDS (Kitchen Display System)."""
    __tablename__ = "kds_screens"

    id:                   Mapped[int]  = mapped_column(primary_key=True)
    branch_id:            Mapped[int]  = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    name:                 Mapped[str]  = mapped_column(String(100))
    module:               Mapped[str]  = mapped_column(String(20), default="restaurant")  # restaurant|cafe
    stations:             Mapped[list] = mapped_column(JSON)  # ["hot", "grill"]
    display_mode:         Mapped[str]  = mapped_column(String(20), default="kanban")  # kanban|list|grid
    alert_after_minutes:  Mapped[int]  = mapped_column(Integer, default=15)
    is_active:            Mapped[bool] = mapped_column(Boolean, default=True)
