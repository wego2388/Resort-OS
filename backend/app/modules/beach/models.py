"""
app/modules/beach/models.py
Beach Module
Tables: beach_inventory, beach_transactions, b2b_contracts, b2b_contract_days,
        beach_reservations, beach_locations
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.kernel.models.mixins import TimestampMixin
from app.core.database import Base


class BeachInventory(Base, TimestampMixin):
    """حالة الشاطئ اليومية — snapshot per day."""
    __tablename__ = "beach_inventory"
    __table_args__ = (
        UniqueConstraint("branch_id", "inventory_date", name="uq_beach_inventory_date"),
    )

    id:               Mapped[int]     = mapped_column(primary_key=True)
    branch_id:        Mapped[int]     = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    inventory_date:   Mapped[date]    = mapped_column(Date, index=True)
    capacity_max:     Mapped[int]     = mapped_column(Integer, default=200)
    capacity_used:    Mapped[int]     = mapped_column(Integer, default=0)
    towels_total:     Mapped[int]     = mapped_column(Integer, default=200)
    towels_available: Mapped[int]     = mapped_column(Integer, default=200)
    towels_used:      Mapped[int]     = mapped_column(Integer, default=0)
    surge_pct:        Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    # surge يُفعَّل تلقائياً عند capacity > 80%


class BeachTransaction(Base, TimestampMixin):
    """كل عملية بيع في الشاطئ."""
    __tablename__ = "beach_transactions"

    id:              Mapped[int]          = mapped_column(primary_key=True)
    branch_id:       Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    tx_type:         Mapped[str]          = mapped_column(String(30))
    # entry|entry_towel|towel_rent|towel_return
    quantity:        Mapped[int]          = mapped_column(Integer, default=1)
    unit_price:      Mapped[Decimal]      = mapped_column(Numeric(10, 2))
    total_amount:    Mapped[Decimal]      = mapped_column(Numeric(10, 2))
    vat_amount:      Mapped[Decimal]      = mapped_column(Numeric(10, 2), default=Decimal("0"))
    surge_applied:   Mapped[bool]         = mapped_column(Boolean, default=False)
    tx_date:         Mapped[date]         = mapped_column(Date, index=True)
    cashier_id:      Mapped[int | None]   = mapped_column(Integer, nullable=True)
    folio_id:        Mapped[int | None]   = mapped_column(ForeignKey("folios.id", ondelete="SET NULL"), nullable=True)
    b2b_contract_id: Mapped[int | None]   = mapped_column(ForeignKey("b2b_contracts.id", ondelete="SET NULL"), nullable=True)
    notes:           Mapped[str | None]   = mapped_column(String(300), nullable=True)
    voided_at:       Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    voided_by:       Mapped[int | None]      = mapped_column(Integer, nullable=True)
    voided_reason:   Mapped[str | None]      = mapped_column(String(200), nullable=True)
    shift_id:        Mapped[int | None]      = mapped_column(ForeignKey("cashier_shifts.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_id:     Mapped[int | None]      = mapped_column(ForeignKey("crm_customers.id", ondelete="SET NULL"), nullable=True)
    # الموقع الفعلي (شمسية/برجولة) اللي العملية دي اتباعت عشانه — nullable
    # لأن مش كل بيع مرتبط بموقع فعلي (تذاكر دخول عادية من POS من غير خريطة
    # حية، تسجيل دخول B2B، مرتجع فوطة عام...). راجع BeachLocation تحت —
    # تسجيل الدخول لموقع فعلي بيعمل BeachTransaction حقيقي (مش تتبع منفصل)
    # ويربطها هنا للتاريخ، حتى بعد ما الموقع نفسه يتفضّى (checkout).
    location_id:     Mapped[int | None]      = mapped_column(ForeignKey("beach_locations.id", ondelete="SET NULL"), nullable=True, index=True)


class B2BContract(Base, TimestampMixin):
    """عقد فندق B2B — علاقة ائتمانية متكررة: الفندق الشريك بيبعت ضيوفه للشاطئ
    على مدار الشهر وبيتحاسب (يتسوّى) دوريًا، مش كاش فوري لحظة الدخول (راجع
    _post_beach_revenue_journal في services.py — القيد المحاسبي الحالي
    بيسجّل الإيراد كأنه كاش فوري حتى لعقود B2B، فجوة معمارية معروفة، خارج
    نطاق هذا التعديل). الحقول التالية (credit_limit/payment_terms_days/
    last_settled_at/is_overdue/notified_overdue) بتضيف ضبط ائتماني حقيقي:
    حد أقصى للرصيد المستحق + تتبّع تأخر السداد، بدل ما ده يفضل بلا حدود."""
    __tablename__ = "b2b_contracts"

    id:             Mapped[int]        = mapped_column(primary_key=True)
    branch_id:      Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    hotel_name:     Mapped[str]        = mapped_column(String(200))
    hotel_name_ar:  Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_phone:  Mapped[str | None] = mapped_column(String(20), nullable=True)
    daily_quota:    Mapped[int]        = mapped_column(Integer, default=50)
    entry_price:    Mapped[Decimal]    = mapped_column(Numeric(10, 2))
    towel_price:    Mapped[Decimal]    = mapped_column(Numeric(10, 2), default=Decimal("0"))
    valid_from:     Mapped[date]       = mapped_column(Date)
    valid_until:    Mapped[date]       = mapped_column(Date)
    is_active:      Mapped[bool]       = mapped_column(Boolean, default=True)
    notes:          Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── ائتمان/تحصيل (credit & dunning) ─────────────────────────────────
    # nullable: مش كل فندق شريك محتاج حد ائتمان — الافتراضي بلا حد (زي
    # الوضع الحالي فعليًا)، ويتفعّل بس لما مدير الإيرادات يحدده صراحةً.
    credit_limit:        Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # مهلة السداد بالأيام (نمط net-30) — بيُستخدم لتحديد "الرصيد المتأخر":
    # أول يوم فيه رصيد غير مسوّى أقدم من المهلة دي من النهاردة.
    payment_terms_days:  Mapped[int]            = mapped_column(Integer, default=30)
    # آخر تاريخ اتسوّى فيه رصيد العقد بالكامل (تحصيل الفاتورة الدورية من
    # الفندق) — None يعني لسه مفيش تسوية خالص من بداية العقد.
    last_settled_at:     Mapped[date | None]    = mapped_column(Date, nullable=True)
    is_overdue:          Mapped[bool]           = mapped_column(Boolean, default=False)
    # يمنع تكرار إشعار واتساب التأخر كل يوم — بيترجع False تلقائيًا عند
    # التسوية (raise settle_b2b_contract) عشان لو اتأخر تاني يتبعت تنبيه جديد.
    notified_overdue:    Mapped[bool]           = mapped_column(Boolean, default=False)

    days: Mapped[list["B2BContractDay"]] = relationship("B2BContractDay", back_populates="contract", lazy="select")


class B2BContractDay(Base, TimestampMixin):
    """تتبع استخدام حصة الفندق يومياً."""
    __tablename__ = "b2b_contract_days"
    __table_args__ = (
        UniqueConstraint("contract_id", "day", name="uq_b2b_contract_day"),
    )

    id:               Mapped[int]     = mapped_column(primary_key=True)
    contract_id:      Mapped[int]     = mapped_column(ForeignKey("b2b_contracts.id", ondelete="CASCADE"))
    day:              Mapped[date]    = mapped_column(Date)
    checked_in_count: Mapped[int]     = mapped_column(Integer, default=0)
    total_amount:     Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    notified_quota_warning: Mapped[bool] = mapped_column(Boolean, default=False)

    contract: Mapped["B2BContract"] = relationship("B2BContract", back_populates="days")


class BeachReservation(Base, TimestampMixin):
    """حجز مسبق للشاطئ."""
    __tablename__ = "beach_reservations"

    id:             Mapped[int]          = mapped_column(primary_key=True)
    branch_id:      Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    guest_name:     Mapped[str]          = mapped_column(String(200))
    guest_phone:    Mapped[str | None]   = mapped_column(String(20), nullable=True)
    reservation_date: Mapped[date]       = mapped_column(Date, index=True)
    guests_count:   Mapped[int]          = mapped_column(Integer, default=1)
    with_towel:     Mapped[bool]         = mapped_column(Boolean, default=False)
    status:         Mapped[str]          = mapped_column(String(20), default="pending")
    # pending|confirmed|checked_in|no_show|cancelled
    total_amount:   Mapped[Decimal]      = mapped_column(Numeric(10, 2), default=Decimal("0"))
    tx_id:          Mapped[int | None]   = mapped_column(ForeignKey("beach_transactions.id", ondelete="SET NULL"), nullable=True)
    notes:          Mapped[str | None]   = mapped_column(String(300), nullable=True)


class BeachLocation(Base, TimestampMixin):
    """خريطة الشاطئ الحية — موقع فعلي واحد (شمسية/برجولة/كابانا...) يشوفه
    الموظفين على شاشة واحدة طول اليوم (زي DiningTable للمطعم، بس مع حالة
    ضيف فعلية بدل مجرد status).

    العلاقة بـ BeachTransaction/BeachReservation (قرار معماري متعمد):
    - تسجيل دخول ضيف لموقع = عملية بيع حقيقية عبر services.checkin_location
      (بيستدعي نفس services.sell_ticket الداخلي، مفيش تتبع مواز غير مرتبط
      بأي أثر مالي) — current_transaction_id بيأشّر على الـ BeachTransaction
      الحقيقي الناتج، وBeachTransaction.location_id بيأشّر بالعكس (يفضل
      موجود حتى بعد checkout يصفّر current_transaction_id، عشان تاريخ/تقارير
      "مين قعد على الموقع ده وإمتى" يفضل قابل للاسترجاع).
    - مختلف عن BeachReservation (حجز مسبق باسم/تليفون قبل الوصول، ممكن يتحول
      لعملية بيع لاحقًا بـ check_in_reservation) — BeachLocation هو الحالة
      *الفعلية اللحظية* لمكان مادي على الرمل، مش حجز مستقبلي. حجز مؤكد ممكن
      (لاحقًا، خارج نطاق هذا التعديل) يتربط بموقع فعلي وقت وصول الضيف، بس
      دلوقتي الاتنين مسارين مستقلين تمامًا.

    الإشغال هنا حالة *فورية* (موقع واحد لضيف واحد دلوقتي) — مختلف عن
    BeachInventory.capacity_used اللي بيتراكم لليوم كله (تذاكر مباعة النهاردة)
    ومبيرجعش لما الموقع يتفضّى (checkout مبيلمسش capacity_used خالص، نفس
    سلوك النظام المرجعي — الشاطئ عنده "تذكرة دخول يومية" مش "حجز وقتي لمقعد").
    """
    __tablename__ = "beach_locations"
    __table_args__ = (
        UniqueConstraint("branch_id", "location_type", "number",
                         name="uq_beach_location_branch_type_number"),
    )

    id:                     Mapped[int]        = mapped_column(primary_key=True)
    branch_id:              Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), index=True)
    location_type:          Mapped[str]        = mapped_column(String(20))
    # umbrella|pergola|sunbed|cabana — قائمة مفتوحة، مش enum محكم (المدير
    # بيقرر أسماء أنواع المواقع الفعلية في المنتجع بتاعه).
    number:                 Mapped[str]        = mapped_column(String(10))
    # "1", "12", "VIP-1" — نص مش رقم، لأن بعض المنتجعات بترقّم بحروف/بادئات.
    grid_row:               Mapped[int]        = mapped_column(Integer, default=1)
    grid_col:               Mapped[int]        = mapped_column(Integer, default=1)
    status:                 Mapped[str]        = mapped_column(String(20), default="available", index=True)
    # available|occupied|out_of_service
    # use_alter=True: beach_locations وbeach_transactions بيرجعوا لبعض (دورة
    # FK حقيقية — location.current_transaction_id ↔ transaction.location_id).
    # من غيره SQLAlchemy مش عارف يرتّب drop_all/create_all (Base.metadata) —
    # اتكشف فعليًا (SAWarning + OperationalError عند teardown التستات).
    # الميجريشن نفسها (alembic) بتنشئ الجدولين بترتيب صريح فمش محتاجة هذا
    # الحل، بس create_all المستخدم في seed.py/conftest.py محتاجه.
    current_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("beach_transactions.id", ondelete="SET NULL", use_alter=True,
                   name="fk_beach_locations_current_transaction_id"),
        nullable=True,
    )
    guest_name:             Mapped[str | None] = mapped_column(String(200), nullable=True)
    guest_phone:            Mapped[str | None] = mapped_column(String(20), nullable=True)
    guests_count:           Mapped[int]        = mapped_column(Integer, default=0)
    towels_given:           Mapped[int]        = mapped_column(Integer, default=0)
    checked_in_at:          Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    checked_in_by:          Mapped[int | None] = mapped_column(Integer, nullable=True)
    # user id اللي عمل التشيك-إن — int خام زي BeachTransaction.cashier_id
    # (مفيش FK لـ users هنا في باقي الموديول أصلاً)، مش EncryptedString لأن
    # ده مش PII حساس (اسم ضيف بيقعد على شمسية يوم واحد، زي BeachReservation
    # الموجود بالفعل بنفس النمط بالظبط — مش رقم قومي/جواز سفر).
