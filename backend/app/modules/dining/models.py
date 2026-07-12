"""
app/modules/dining/models.py
Unified Dining Platform — superset of app.modules.restaurant.models +
app.modules.cafe.models. راجع wagdy.md "المرحلة الثالثة — المشروع الكبير
(Dining Module Merge)" §D-01 والدستور CLAUDE.md §13 بند ⓭ / §18 "Variants
حقيقية" — القواعد التجارية اللي لازم تتحفظ من غير أي تراجع موثّقة تفصيليًا
في docstring كل كلاس تحت.

Tables: dining_outlets, dining_categories, dining_items,
        dining_item_extra_groups, dining_item_extras,
        dining_item_recipe_lines, dining_item_variants,
        dining_item_variant_recipe_lines, dining_tables, dining_orders,
        dining_order_items, dining_order_item_extras,
        dining_kitchen_tickets, dining_kds_screens

⚠️ Batch A: موديول إضافي بالكامل — لا restaurant/cafe اتلمسوا ولا هيتلمسوا
حتى D-05/D-08 (راجع DINING_CUTOVER_PLAN.md). الجداول هنا بتتملى بنسخة
(copy، مش نقل) من بيانات restaurant/cafe عبر migration D-02، وexistant IDs
بتتحافظ عليها كـ legacy_module/legacy_id (مش كـ PK حرفي — راجع تعليق
_LegacyTrackedMixin تحت لسبب الاستحالة المعمارية لحفظ PK حرفي هنا).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, JSON,
    Numeric, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.kernel.models.mixins import TimestampMixin
from app.core.database import Base

if TYPE_CHECKING:
    from app.modules.inventory.models import Product


# ─────────────────────── Outlet ────────────────────────────────────────

class Outlet(Base, TimestampMixin):
    """منفذ بيع واحد — بديل الفصل بين موديولين منفصلين (restaurant/cafe)
    بعمود outlet_type + إعدادات per-outlet بدل تكرار الكود. راجع مذكرة
    Mohamed المعمارية الأخيرة (wagdy.md، آخر الملف): "نفس محرك الطلبات،
    نفس شاشة POS، نفس إدارة الطاولات، نفس المطبخ (KDS)، نفس الفواتير
    والخصومات والمدفوعات — والاختلافات (مطعم، كافيه، بار، Beach Service)
    تكون Configuration أو Outlet Type وليس نسخًا مختلفة من الواجهة أو الكود."

    outlet_type مش عمود مقيّد بـ CHECK constraint عمدًا — إضافة outlet
    جديد (Pool Bar، Rooftop) المفروض تبقى صف جديد بس، صفر migration، صفر
    كود جديد (نفس هدف الدمج بالظبط). التحقق (لو احتجناه) على مستوى
    schema/validation، مش DB — نفس فلسفة MenuItem.station قبل الدمج."""
    __tablename__ = "dining_outlets"
    __table_args__ = (
        UniqueConstraint("branch_id", "name", name="uq_dining_outlet_branch_name"),
    )

    id:           Mapped[int]        = mapped_column(primary_key=True)
    branch_id:    Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    name:         Mapped[str]        = mapped_column(String(100))
    name_ar:      Mapped[str | None] = mapped_column(String(100), nullable=True)
    outlet_type:  Mapped[str]        = mapped_column(String(30), default="restaurant")
    # restaurant|cafe|bar|buffet|pool_bar|rooftop|beach_service|... — قيمة
    # مفتوحة عمدًا (راجع docstring الكلاس)، نفس القيمة المستخدمة في
    # discount_engine.OrderContext.outlet (scope_type="outlet" بيقارن
    # نصيًا — أي outlet_type جديد شغال معاه من غير أي تعديل في المحرك).
    revenue_account_code: Mapped[str] = mapped_column(String(10), default="4200")
    # حساب إيراد المنفذ ده في دليل الحسابات (Chart of Accounts) — بديل
    # الأكواد الثابتة 4200 (مطعم) / 4400 (كافيه) اللي كانت مكتوبة حرفيًا في
    # restaurant/cafe services.py (راجع wagdy.md D-03: "استبدال حسابات
    # الإيراد الثابتة 4200/4400 بـ outlet.revenue_account_code"). منفذ جديد
    # (بار المسبح مثلاً) ياخد حساب فرعي منفصل من دليل الحسابات من غير أي
    # تعديل كود — مجرد صف Account جديد + قيمة العمود ده.
    default_service_charge_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    # NULL = استخدم settings.SERVICE_CHARGE_PERCENTAGE العام (نفس سلوك
    # restaurant/cafe الحالي بالظبط) — override اختياري لكل منفذ (مثلاً بار
    # مسبح من غير رسم خدمة).
    is_active:    Mapped[bool]       = mapped_column(Boolean, default=True)
    legacy_module: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # "restaurant" | "cafe" | None — الـ outlet ده اتعمل من هجرة D-02 وﻻ
    # جديد كليًا (Pool Bar مستقبلاً). للتتبع/التقارير بس، صفر منطق عمل.

    categories: Mapped[list["DiningCategory"]] = relationship("DiningCategory", back_populates="outlet", lazy="select")
    items:      Mapped[list["DiningItem"]]     = relationship("DiningItem", back_populates="outlet", lazy="select")
    tables:     Mapped[list["VenueTable"]]    = relationship("VenueTable", back_populates="outlet", lazy="select")


# ─────────────────────── Menu ──────────────────────────────────────────

class DiningCategory(Base, TimestampMixin):
    """يدمج restaurant.MenuCategory + cafe.CafeCategory — نفس الشكل بالظبط،
    outlet_id بدل الفصل بين جدولين."""
    __tablename__ = "dining_categories"
    __table_args__ = (
        UniqueConstraint("legacy_module", "legacy_id", name="uq_dining_category_legacy"),
    )

    id:            Mapped[int]        = mapped_column(primary_key=True)
    branch_id:     Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    outlet_id:     Mapped[int]        = mapped_column(ForeignKey("dining_outlets.id", ondelete="CASCADE"))
    name:          Mapped[str]        = mapped_column(String(100))
    name_ar:       Mapped[str | None] = mapped_column(String(100), nullable=True)
    sort_order:    Mapped[int]        = mapped_column(Integer, default=0)
    is_active:     Mapped[bool]       = mapped_column(Boolean, default=True)
    legacy_module: Mapped[str | None] = mapped_column(String(20), nullable=True)
    legacy_id:     Mapped[int | None] = mapped_column(Integer, nullable=True)
    # (legacy_module, legacy_id) = (restaurant.MenuCategory.id) أو
    # (cafe.CafeCategory.id) الأصلي — راجع docstring DiningOrder لتبرير
    # ليه ده مش PK حرفي.

    outlet: Mapped["Outlet"] = relationship("Outlet", back_populates="categories")
    items:  Mapped[list["DiningItem"]] = relationship("DiningItem", back_populates="category", lazy="select")


class DiningItem(Base, TimestampMixin):
    """يدمج restaurant.MenuItem + cafe.CafeItem — نفس الأعمدة بالظبط بما
    فيها ``station`` (hot|grill|cold|bar|dessert) اللي توجّه تذكرة الـ KDS
    تلقائيًا. راجع CLAUDE.md §13 بند ⓭: cafe.CafeItem ماكانش عنده العمود ده
    خالص في الأصل (باج حقيقي اتصلح 2026-07-08، كل تذكرة كافيه كانت
    بتتوجّه لمحطة "bar" ثابتة في الكود) — هنا العمود إجباري على كل
    DiningItem من الأساس، مفيش أي outlet يقدر يفوّته."""
    __tablename__ = "dining_items"
    __table_args__ = (
        UniqueConstraint("legacy_module", "legacy_id", name="uq_dining_item_legacy"),
    )

    id:                  Mapped[int]         = mapped_column(primary_key=True)
    branch_id:           Mapped[int]         = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    outlet_id:           Mapped[int]         = mapped_column(ForeignKey("dining_outlets.id", ondelete="CASCADE"))
    category_id:         Mapped[int | None]  = mapped_column(ForeignKey("dining_categories.id", ondelete="SET NULL"), nullable=True)
    name:                Mapped[str]         = mapped_column(String(200))
    name_ar:             Mapped[str | None]  = mapped_column(String(200), nullable=True)
    price:               Mapped[Decimal]     = mapped_column(Numeric(10, 2))
    cost:                Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    is_available:        Mapped[bool]        = mapped_column(Boolean, default=True)
    preparation_minutes: Mapped[int]         = mapped_column(Integer, default=10)
    image_url:           Mapped[str | None]  = mapped_column(String(500), nullable=True)
    station:             Mapped[str]         = mapped_column(String(50), default="hot")
    # hot|grill|cold|bar|dessert — لتوجيه الـ KDS تلقائياً (راجع docstring
    # الكلاس فوق). إجباري بعمود حقيقي على كل صنف من كل outlet — مفيش أي
    # fallback ثابت في الكود زي الباج القديم.
    linked_product_id:   Mapped[int | None]  = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    # ربط اختياري بصنف مخزني (inventory.Product) — fallback خصم مخزون 1:1
    # لو الصنف مفهوش وصفة حقيقية (راجع services._deduct_inventory_for_order).
    legacy_module: Mapped[str | None] = mapped_column(String(20), nullable=True)
    legacy_id:     Mapped[int | None] = mapped_column(Integer, nullable=True)

    outlet:       Mapped["Outlet"]        = relationship("Outlet", back_populates="items")
    category:     Mapped["DiningCategory"] = relationship("DiningCategory", back_populates="items")
    extra_groups: Mapped[list["DiningItemExtraGroup"]] = relationship(
        "DiningItemExtraGroup", back_populates="item", lazy="select",
        cascade="all, delete-orphan", order_by="DiningItemExtraGroup.sort_order",
    )
    recipe_lines: Mapped[list["DiningItemRecipeLine"]] = relationship(
        "DiningItemRecipeLine", back_populates="item", lazy="selectin",
        cascade="all, delete-orphan",
    )
    variants: Mapped[list["DiningItemVariant"]] = relationship(
        "DiningItemVariant", back_populates="item", lazy="selectin",
        cascade="all, delete-orphan", order_by="DiningItemVariant.sort_order",
    )


class DiningItemExtraGroup(Base, TimestampMixin):
    """مجموعة اختيارات لصنف — يدمج restaurant.MenuItemExtraGroup +
    cafe.CafeMenuItemExtraGroup (نفس الشكل بالظبط).

    legacy_module/legacy_id هنا برضه (رغم إنها "مجرد" جدول ابن لـ
    DiningItem) — عشان migration D-02 تقدر تنسخ dining_item_extras بـ
    INSERT...SELECT خالص (SQL-only، بدون loop في Python) وهي محتاجة تلاقي
    المجموعة الجديدة المقابلة لـ menu_item_extra_group_id/
    cafe_menu_item_extra_group_id الأصلي. من غيرها مفيش مفتاح طبيعي موثوق
    (name مش unique constraint فعليًا حتى في الجداول الأصلية) تربط بيه."""
    __tablename__ = "dining_item_extra_groups"
    __table_args__ = (
        UniqueConstraint("legacy_module", "legacy_id", name="uq_dining_item_extra_group_legacy"),
    )

    id:         Mapped[int]        = mapped_column(primary_key=True)
    item_id:    Mapped[int]        = mapped_column(ForeignKey("dining_items.id", ondelete="CASCADE"))
    name:       Mapped[str]        = mapped_column(String(100))
    name_ar:    Mapped[str | None] = mapped_column(String(100), nullable=True)
    min_select: Mapped[int]        = mapped_column(Integer, default=0)
    max_select: Mapped[int]        = mapped_column(Integer, default=1)
    sort_order: Mapped[int]        = mapped_column(Integer, default=0)
    legacy_module: Mapped[str | None] = mapped_column(String(20), nullable=True)
    legacy_id:     Mapped[int | None] = mapped_column(Integer, nullable=True)

    item: Mapped["DiningItem"] = relationship("DiningItem", back_populates="extra_groups")
    options: Mapped[list["DiningItemExtra"]] = relationship(
        "DiningItemExtra", back_populates="group", lazy="select",
        cascade="all, delete-orphan", order_by="DiningItemExtra.sort_order",
    )


class DiningItemExtra(Base, TimestampMixin):
    """خيار داخل مجموعة — يدمج restaurant.MenuItemExtra + cafe.CafeMenuItemExtra."""
    __tablename__ = "dining_item_extras"

    id:             Mapped[int]     = mapped_column(primary_key=True)
    group_id:       Mapped[int]     = mapped_column(ForeignKey("dining_item_extra_groups.id", ondelete="CASCADE"))
    name:           Mapped[str]     = mapped_column(String(100))
    name_ar:        Mapped[str | None] = mapped_column(String(100), nullable=True)
    price_addition: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    is_available:   Mapped[bool]    = mapped_column(Boolean, default=True)
    sort_order:     Mapped[int]     = mapped_column(Integer, default=0)

    group: Mapped["DiningItemExtraGroup"] = relationship("DiningItemExtraGroup", back_populates="options")


class DiningItemRecipeLine(Base, TimestampMixin):
    """سطر وصفة (Recipe/BOM) — يدمج restaurant.MenuItemRecipeLine +
    cafe.CafeItemRecipeLine. مطلوبة لخصم المخزون تلقائيًا + تقرير تكلفة
    الطعام (راجع resort_os/food_cost_engine.py)."""
    __tablename__ = "dining_item_recipe_lines"
    __table_args__ = (
        UniqueConstraint("item_id", "product_id", name="uq_dining_item_recipe_product"),
    )

    id:                Mapped[int]     = mapped_column(primary_key=True)
    item_id:           Mapped[int]     = mapped_column(ForeignKey("dining_items.id", ondelete="CASCADE"))
    product_id:        Mapped[int]     = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    quantity_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    notes:             Mapped[str | None] = mapped_column(String(200), nullable=True)

    item:    Mapped["DiningItem"] = relationship("DiningItem", back_populates="recipe_lines")
    product: Mapped["Product"]    = relationship("Product", lazy="joined")


class DiningItemVariant(Base, TimestampMixin):
    """متغيّر حقيقي لصنف — يدمج restaurant.MenuItemVariant +
    cafe.CafeItemVariant. سعر ووصفة مستقلين تمامًا عن الصنف الأساسي، مش
    رسم إضافي فوق وصفة ثابتة (ده دور DiningItemExtra). راجع CLAUDE.md §18
    "Variants حقيقية" — القرار المعماري المتعمّد الأساسي المحفوظ هنا:
    وصفة كل متغيّر في جدول منفصل (DiningItemVariantRecipeLine) مش عمود
    variant_id nullable على DiningItemRecipeLine نفسه، عشان
    ``item.recipe_lines`` (المستخدمة في compute_item_cost/
    _deduct_inventory_for_order/get_food_cost_report) تفضل تعني بالظبط
    "وصفة الصنف الأساسي" من غير أي فلترة إضافية لازم تتضاف في كل نقطة
    استخدام موجودة. صنف بدون متغيّرات يفضل شغال بسلوكه الحالي 100%
    (price/recipe_lines بتاعت DiningItem نفسه)."""
    __tablename__ = "dining_item_variants"
    __table_args__ = (
        UniqueConstraint("item_id", "name", name="uq_dining_item_variant_name"),
        UniqueConstraint("legacy_module", "legacy_id", name="uq_dining_item_variant_legacy"),
    )

    id:           Mapped[int]        = mapped_column(primary_key=True)
    item_id:      Mapped[int]        = mapped_column(ForeignKey("dining_items.id", ondelete="CASCADE"))
    name:         Mapped[str]        = mapped_column(String(100))
    name_ar:      Mapped[str | None] = mapped_column(String(100), nullable=True)
    price:        Mapped[Decimal]    = mapped_column(Numeric(10, 2))
    # سعر مطلق (مش delta فوق DiningItem.price) — بيحل محل سعر الصنف
    # الأساسي بالكامل لما يتم اختياره.
    is_available: Mapped[bool]       = mapped_column(Boolean, default=True)
    sort_order:   Mapped[int]        = mapped_column(Integer, default=0)
    legacy_module: Mapped[str | None] = mapped_column(String(20), nullable=True)
    legacy_id:     Mapped[int | None] = mapped_column(Integer, nullable=True)

    item: Mapped["DiningItem"] = relationship("DiningItem", back_populates="variants")
    recipe_lines: Mapped[list["DiningItemVariantRecipeLine"]] = relationship(
        "DiningItemVariantRecipeLine", back_populates="variant", lazy="selectin",
        cascade="all, delete-orphan",
    )


class DiningItemVariantRecipeLine(Base, TimestampMixin):
    """سطر وصفة خاص بمتغيّر واحد — يدمج restaurant.MenuItemVariantRecipeLine
    + cafe.CafeItemVariantRecipeLine. جدول منفصل عمدًا عن
    DiningItemRecipeLine — راجع docstring DiningItemVariant."""
    __tablename__ = "dining_item_variant_recipe_lines"
    __table_args__ = (
        UniqueConstraint("variant_id", "product_id", name="uq_dining_item_variant_recipe_product"),
    )

    id:                Mapped[int]     = mapped_column(primary_key=True)
    variant_id:        Mapped[int]     = mapped_column(ForeignKey("dining_item_variants.id", ondelete="CASCADE"))
    product_id:        Mapped[int]     = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    quantity_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    notes:             Mapped[str | None] = mapped_column(String(200), nullable=True)

    variant: Mapped["DiningItemVariant"] = relationship("DiningItemVariant", back_populates="recipe_lines")
    product: Mapped["Product"]           = relationship("Product", lazy="joined")


# ─────────────────────── Tables / Orders ───────────────────────────────

class VenueTable(Base, TimestampMixin):
    """يدمج restaurant.DiningTable + cafe.CafeTable — نفس الشكل، outlet_id
    بدل جدولين منفصلين. grid_row/grid_col للخريطة الحية (راجع
    restaurant.DiningTable الأصلي — أول outlet ضاف الميزة دي).

    ⚠️ الكلاس هنا اسمه ``VenueTable`` مش ``DiningTable`` عمدًا (رغم إن
    الاسم المقترح في wagdy.md "المرحلة الثالثة" هو ``VenueTable`` أصلًا) —
    ``restaurant.models.DiningTable`` كلاس حقيقي مُسجَّل بالفعل في نفس
    declarative registry المشترك (``Base`` واحد لكل الموديولات)، فاستخدام
    نفس اسم الكلاس هنا كان بيسبب ``Multiple classes found for path
    "DiningTable"`` وقت resolve أي ``relationship("DiningTable", ...)``
    نصي — تصادم اسم كلاس حقيقي، مش مجرد تصادم اسم جدول. نفس السبب خلّى
    اسم الجدول نفسه ``dining_venue_tables`` مش ``dining_tables`` (تصادم
    اسم جدول مباشر مع restaurant.DiningTable.__tablename__)."""
    __tablename__ = "dining_venue_tables"
    __table_args__ = (
        UniqueConstraint("legacy_module", "legacy_id", name="uq_dining_table_legacy"),
    )

    id:           Mapped[int]        = mapped_column(primary_key=True)
    branch_id:    Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    outlet_id:    Mapped[int]        = mapped_column(ForeignKey("dining_outlets.id", ondelete="CASCADE"))
    table_number: Mapped[str]        = mapped_column(String(20))
    capacity:     Mapped[int]        = mapped_column(Integer, default=4)
    status:       Mapped[str]        = mapped_column(String(30), default="available")  # available|occupied|reserved|out_of_service
    section:      Mapped[str | None] = mapped_column(String(50), nullable=True)
    occupied_at:  Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    grid_row:     Mapped[int | None] = mapped_column(Integer, nullable=True)
    grid_col:     Mapped[int | None] = mapped_column(Integer, nullable=True)
    legacy_module: Mapped[str | None] = mapped_column(String(20), nullable=True)
    legacy_id:     Mapped[int | None] = mapped_column(Integer, nullable=True)

    outlet: Mapped["Outlet"] = relationship("Outlet", back_populates="tables")


class DiningOrder(Base, TimestampMixin):
    """يدمج restaurant.Order + cafe.CafeOrder — نفس الأعمدة بالظبط،
    outlet_id بدل جدولين منفصلين بالكامل (Orders/CafeOrders).

    ⚠️ ليه legacy_module/legacy_id مش PK حرفي: restaurant.Order.id
    وcafe.CafeOrder.id مصدرهم sequence منفصل تمامًا (كل واحد بيبدأ من 1) —
    الرقمين بيتصادفوا بشكل طبيعي (مثال: Order#42 وCafeOrder#42 موجودين
    الاتنين فعليًا كطلبين مختلفين تمامًا). دمجهم في PK واحد مش ممكن معماريًا
    من غير إعادة ترقيم PK أحدهم على الأقل — فبدل كده، dining_orders.id
    PK جديد تمامًا (auto-increment)، و(legacy_module, legacy_id) هو
    المرجع الوحيد للطلب الأصلي (unique constraint يمنع نسخ نفس الطلب
    مرتين لو الـ migration اتشغّلت أكتر من مرة). ``created_at``/``updated_at``
    (من TimestampMixin) بتتنسخ بالقيمة الأصلية حرفيًا وقت الـ migration
    (راجع alembic/versions/.../dining_initial_schema — data copy)، مش
    server_default وقت النسخ."""
    __tablename__ = "dining_orders"
    __table_args__ = (
        UniqueConstraint("legacy_module", "legacy_id", name="uq_dining_order_legacy"),
    )

    id:                       Mapped[int]         = mapped_column(primary_key=True)
    branch_id:                Mapped[int]         = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    outlet_id:                Mapped[int]         = mapped_column(ForeignKey("dining_outlets.id", ondelete="CASCADE"))
    table_id:                 Mapped[int | None]  = mapped_column(ForeignKey("dining_venue_tables.id", ondelete="SET NULL"), nullable=True)
    order_number:             Mapped[str]         = mapped_column(String(30), unique=True)  # ORD-20260630-0001
    status:                   Mapped[str]         = mapped_column(String(30), default="open")   # held|open|in_kitchen|served|paid|cancelled|refunded
    order_type:               Mapped[str]         = mapped_column(String(30), default="dine_in") # dine_in|takeaway|delivery|room_service
    subtotal:                 Mapped[Decimal]     = mapped_column(Numeric(10, 2), default=Decimal("0"))
    vat_amount:                Mapped[Decimal]     = mapped_column(Numeric(10, 2), default=Decimal("0"))
    service_charge:            Mapped[Decimal]     = mapped_column(Numeric(10, 2), default=Decimal("0"))
    discount_amount:           Mapped[Decimal]     = mapped_column(Numeric(10, 2), default=Decimal("0"))
    total:                     Mapped[Decimal]     = mapped_column(Numeric(10, 2), default=Decimal("0"))
    refunded_amount:           Mapped[Decimal]     = mapped_column(Numeric(10, 2), default=Decimal("0"))
    guests_count:              Mapped[int]         = mapped_column(Integer, default=1)
    notes:                     Mapped[str | None]  = mapped_column(String(500), nullable=True)
    waiter_id:                 Mapped[int | None]  = mapped_column(Integer, nullable=True)
    folio_id:                  Mapped[int | None]  = mapped_column(Integer, nullable=True)
    applied_discount_rule_id:  Mapped[int | None]  = mapped_column(Integer, nullable=True)
    customer_id:               Mapped[int | None]  = mapped_column(ForeignKey("crm_customers.id", ondelete="SET NULL"), nullable=True)
    client_local_id:           Mapped[str | None]  = mapped_column(String(60), nullable=True, unique=True)
    # UUID من IndexedDB عند الـ offline POS — idempotency key (راجع
    # services.sync_offline_order).
    payment_method:            Mapped[str | None]  = mapped_column(String(20), nullable=True)
    # cash | card | room | wallet
    legacy_module: Mapped[str | None] = mapped_column(String(20), nullable=True)
    legacy_id:     Mapped[int | None] = mapped_column(Integer, nullable=True)

    outlet: Mapped["Outlet"]      = relationship("Outlet")
    table:  Mapped["VenueTable"] = relationship("VenueTable", lazy="select")
    items:  Mapped[list["DiningOrderItem"]] = relationship(
        "DiningOrderItem", back_populates="order", lazy="select", cascade="all, delete-orphan",
    )


class DiningOrderItem(Base, TimestampMixin):
    """يدمج restaurant.OrderItem + cafe.CafeOrderItem — نفس الأعمدة، بما
    فيها snapshot الاسم/السعر وقت الطلب (name/unit_price) ومين ألغى/رجّع
    الصنف (voided_by/voided_reason/voided_at، للحالتين cancelled وrefunded
    — راجع restaurant.schemas.OrderItemRead)."""
    __tablename__ = "dining_order_items"
    __table_args__ = (
        UniqueConstraint("legacy_module", "legacy_id", name="uq_dining_order_item_legacy"),
    )

    id:           Mapped[int]        = mapped_column(primary_key=True)
    order_id:     Mapped[int]        = mapped_column(ForeignKey("dining_orders.id", ondelete="CASCADE"))
    item_id:      Mapped[int]        = mapped_column(ForeignKey("dining_items.id", ondelete="RESTRICT"))
    variant_id:   Mapped[int | None] = mapped_column(ForeignKey("dining_item_variants.id", ondelete="SET NULL"), nullable=True)
    name:         Mapped[str]        = mapped_column(String(200))          # snapshot
    unit_price:   Mapped[Decimal]    = mapped_column(Numeric(10, 2))       # snapshot
    quantity:     Mapped[int]        = mapped_column(Integer, default=1)
    notes:        Mapped[str | None] = mapped_column(String(200), nullable=True)
    status:       Mapped[str]        = mapped_column(String(20), default="pending")  # pending|in_kitchen|ready|served|cancelled|refunded
    voided_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    voided_by:    Mapped[int | None] = mapped_column(Integer, nullable=True)
    voided_at:    Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    legacy_module: Mapped[str | None] = mapped_column(String(20), nullable=True)
    legacy_id:     Mapped[int | None] = mapped_column(Integer, nullable=True)

    order: Mapped["DiningOrder"] = relationship("DiningOrder", back_populates="items")
    extras: Mapped[list["DiningOrderItemExtra"]] = relationship(
        "DiningOrderItemExtra", back_populates="order_item", lazy="select", cascade="all, delete-orphan",
    )


class DiningOrderItemExtra(Base, TimestampMixin):
    """snapshot للإضافة المختارة وقت الطلب — يدمج restaurant.OrderItemExtra
    + cafe.CafeOrderItemExtra."""
    __tablename__ = "dining_order_item_extras"

    id:             Mapped[int]      = mapped_column(primary_key=True)
    order_item_id:  Mapped[int]      = mapped_column(ForeignKey("dining_order_items.id", ondelete="CASCADE"))
    extra_id:       Mapped[int | None] = mapped_column(ForeignKey("dining_item_extras.id", ondelete="SET NULL"), nullable=True)
    extra_name:     Mapped[str]      = mapped_column(String(100))
    price_addition: Mapped[Decimal]  = mapped_column(Numeric(10, 2), default=Decimal("0"))

    order_item: Mapped["DiningOrderItem"] = relationship("DiningOrderItem", back_populates="extras")


# ─────────────────────── KDS ────────────────────────────────────────────

class DiningKitchenTicket(Base, TimestampMixin):
    """تذكرة تتبعت للمطبخ لما الطلب يروح in_kitchen — يدمج
    restaurant.KitchenTicket (اللي كان بالفعل مشترك بين المطعم/الكافيه عبر
    عمود ``module`` نصي، لأن order_id كان Integer خام بدون FK حقيقي —
    ماكانش يقدر يشاور على جدولين مختلفين). هنا order_id FK حقيقي على
    dining_orders (تحسين حقيقي: مفيش أي ambiguity زي الأصل)."""
    __tablename__ = "dining_kitchen_tickets"

    id:             Mapped[int]  = mapped_column(primary_key=True)
    branch_id:      Mapped[int]  = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    outlet_id:      Mapped[int]  = mapped_column(ForeignKey("dining_outlets.id", ondelete="CASCADE"))
    order_id:       Mapped[int]  = mapped_column(ForeignKey("dining_orders.id", ondelete="CASCADE"))
    station:        Mapped[str]  = mapped_column(String(50))  # hot|grill|cold|bar|dessert
    items_snapshot: Mapped[dict] = mapped_column(JSON)  # الأصناف الخاصة بالمحطة دي بس
    status:         Mapped[str]  = mapped_column(String(20), default="pending")  # pending|in_progress|done


class DiningKDSScreen(Base, TimestampMixin):
    """إعداد شاشة KDS — يدمج restaurant.KDSScreen. outlet_id NULLable
    عمدًا: NULL = شاشة موحّدة بتعرض تذاكر كل الـ outlets في الفرع (رؤية
    Foodics/Toast الموحّدة نفسها اللي طلبها Mohamed)، قيمة محددة = شاشة
    مخصوصة لـ outlet واحد بس (لو المنتجع عايز يفصل مطبخ المطعم عن بار
    الكافيه فعليًا)."""
    __tablename__ = "dining_kds_screens"

    id:                   Mapped[int]        = mapped_column(primary_key=True)
    branch_id:            Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    outlet_id:            Mapped[int | None] = mapped_column(ForeignKey("dining_outlets.id", ondelete="CASCADE"), nullable=True)
    name:                 Mapped[str]        = mapped_column(String(100))
    stations:             Mapped[list]       = mapped_column(JSON)  # ["hot", "grill"]
    display_mode:         Mapped[str]        = mapped_column(String(20), default="kanban")  # kanban|list|grid
    alert_after_minutes:  Mapped[int]        = mapped_column(Integer, default=15)
    is_active:            Mapped[bool]       = mapped_column(Boolean, default=True)
