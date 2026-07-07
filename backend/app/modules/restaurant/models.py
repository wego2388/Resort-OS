"""
app/modules/restaurant/models.py
Restaurant Module
Tables: menu_categories, menu_items, menu_item_extra_groups, menu_item_extras,
        menu_item_recipe_lines, menu_item_variants, menu_item_variant_recipe_lines,
        dining_tables, orders, order_items, order_item_extras
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, JSON,
    Numeric, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.kernel.models.mixins import TimestampMixin
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
    recipe_lines: Mapped[list["MenuItemRecipeLine"]] = relationship(
        "MenuItemRecipeLine", back_populates="menu_item", lazy="selectin",
        cascade="all, delete-orphan",
    )
    variants: Mapped[list["MenuItemVariant"]] = relationship(
        "MenuItemVariant", back_populates="menu_item", lazy="selectin",
        cascade="all, delete-orphan", order_by="MenuItemVariant.sort_order",
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


class MenuItemRecipeLine(Base, TimestampMixin):
    """سطر وصفة (Recipe/BOM) — كمية من صنف مخزني (inventory.Product) بتتستهلك
    لكل وحدة مباعة من الصنف ده. مثال: 'برجر لحم' = 0.150 كجم لحم مفروم + رغيف
    واحد + 0.030 كجم جبنة. الكمية بوحدة الصنف المخزني نفسها (Product.unit) —
    مفيش تحويل وحدات، لو الصنف مخزّن بالكيلو فالكمية هنا بالكيلو.

    مختلف عن linked_product_id (ربط 1:1 قديم، لسه شغال كـ fallback لو الصنف
    مفهوش وصفة حقيقية — راجع services._deduct_inventory_for_order)."""
    __tablename__ = "menu_item_recipe_lines"
    __table_args__ = (
        UniqueConstraint("menu_item_id", "product_id", name="uq_menu_item_recipe_product"),
    )

    id:                Mapped[int]     = mapped_column(primary_key=True)
    menu_item_id:      Mapped[int]     = mapped_column(ForeignKey("menu_items.id", ondelete="CASCADE"))
    product_id:        Mapped[int]     = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    quantity_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    notes:             Mapped[str | None] = mapped_column(String(200), nullable=True)

    menu_item: Mapped["MenuItem"] = relationship("MenuItem", back_populates="recipe_lines")
    product:   Mapped["Product"]  = relationship("Product", lazy="joined")


class MenuItemVariant(Base, TimestampMixin):
    """متغيّر حقيقي لصنف — نفس الصنف بحجم/نوع مختلف له سعر ووصفة مختلفين
    تمامًا، مش إضافة سعر ثابت فوق وصفة واحدة زي MenuItemExtra. مثال:
    'كابتشينو' بحجم 'صغير' (120 مل حليب) مقابل 'كبير' (200 مل حليب) — سعر
    مختلف *و* استهلاك مخزون مختلف فعليًا، مش رسم إضافي بس.

    مختلف جوهريًا عن MenuItemExtra: الإضافة بتُضاف فوق صنف أساسي واحد
    بوصفة ثابتة (مثال: 'شوت إضافي +5ج' على قهوة عادية)، أما المتغيّر فبيحل
    محل الصنف الأساسي بالكامل (سعر ووصفة MenuItem الأصل بيتجاهلوا تمامًا
    لما يتم اختيار متغيّر — راجع services._resolve_variant). صنف بدون
    متغيّرات يفضل شغال بسلوكه الحالي 100% (price/recipe_lines بتاعت
    MenuItem نفسه) — المتغيّرات إضافة اختيارية بحتة، مش استبدال قسري.

    لو الصنف عنده متغيّرات متاحة، الطلب لازم يحدد variant_id إجباريًا —
    مفيش سعر افتراضي غامض لما فيه أكتر من حجم حقيقي للصنف."""
    __tablename__ = "menu_item_variants"
    __table_args__ = (
        UniqueConstraint("menu_item_id", "name", name="uq_menu_item_variant_name"),
    )

    id:           Mapped[int]        = mapped_column(primary_key=True)
    menu_item_id: Mapped[int]        = mapped_column(ForeignKey("menu_items.id", ondelete="CASCADE"))
    name:         Mapped[str]        = mapped_column(String(100))
    name_ar:      Mapped[str | None] = mapped_column(String(100), nullable=True)
    price:        Mapped[Decimal]    = mapped_column(Numeric(10, 2))
    # سعر مطلق (مش delta فوق MenuItem.price) — بيحل محل سعر الصنف الأساسي
    # بالكامل لما يتم اختياره، زي 'كابتشينو كبير = 35ج' مش '+10ج فوق صغير'.
    # أوضح للكاشير على شاشة POS وأسهل في التسعير من فرق مبني على سعر أساسي
    # ممكن يتغيّر لوحده.
    is_available: Mapped[bool]       = mapped_column(Boolean, default=True)
    sort_order:   Mapped[int]        = mapped_column(Integer, default=0)

    menu_item: Mapped["MenuItem"] = relationship("MenuItem", back_populates="variants")
    recipe_lines: Mapped[list["MenuItemVariantRecipeLine"]] = relationship(
        "MenuItemVariantRecipeLine", back_populates="variant", lazy="selectin",
        cascade="all, delete-orphan",
    )


class MenuItemVariantRecipeLine(Base, TimestampMixin):
    """سطر وصفة خاص بمتغيّر واحد — نفس شكل MenuItemRecipeLine بالضبط (كمية
    من inventory.Product بوحدته نفسها) بس مربوط بـ MenuItemVariant مش
    MenuItem مباشرة. جدول منفصل عمدًا (مش عمود variant_id nullable على
    MenuItemRecipeLine نفسه) — عشان العلاقة menu_item.recipe_lines
    (المستخدمة في compute_menu_item_cost/_deduct_inventory_for_order/
    get_food_cost_report، كل ده اتبنى واتأكد منه قبل المتغيّرات) تفضل تعني
    بالظبط نفس الحاجة اللي كانت تعنيها من قبل: وصفة الصنف الأساسي، من غير
    أي فلترة إضافية لازم تتضاف في كل نقطة استخدام موجودة."""
    __tablename__ = "menu_item_variant_recipe_lines"
    __table_args__ = (
        UniqueConstraint("variant_id", "product_id", name="uq_menu_item_variant_recipe_product"),
    )

    id:                Mapped[int]     = mapped_column(primary_key=True)
    variant_id:        Mapped[int]     = mapped_column(ForeignKey("menu_item_variants.id", ondelete="CASCADE"))
    product_id:        Mapped[int]     = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    quantity_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    notes:             Mapped[str | None] = mapped_column(String(200), nullable=True)

    variant: Mapped["MenuItemVariant"] = relationship("MenuItemVariant", back_populates="recipe_lines")
    product: Mapped["Product"]         = relationship("Product", lazy="joined")


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
    refunded_amount:         Mapped[Decimal]     = mapped_column(Numeric(10, 2), default=Decimal("0"))
    # إجمالي المرتجع (مرتجع بعد الدفع، صنف بصنف — راجع services.refund_order_item)
    # — total الأصلي بيفضل زي ما هو كسجل تاريخي للفاتورة، مش بيتعدّل رجوعًا
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
    variant_id:   Mapped[int | None] = mapped_column(ForeignKey("menu_item_variants.id", ondelete="SET NULL"), nullable=True)
    # المتغيّر المختار وقت الطلب (لو الصنف عنده متغيّرات) — name/unit_price
    # فوق دول بالفعل snapshot يعكس اسم/سعر المتغيّر وقت الطلب، فده مرجع
    # هيكلي بس (للتقارير/خصم المخزون)، مش مصدر السعر. NULL لو الصنف اتباع
    # بدون متغيّر (أو المتغيّر اتحذف بعدين — السجل التاريخي (name) بيفضل صحيح).
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
