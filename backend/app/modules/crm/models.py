"""
app/modules/crm/models.py
CRM Module — إدارة العملاء والفرص
Tables: customers, interactions, opportunities, activities
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
from app.core.encryption import EncryptedString


class CustomerGroup(Base, TimestampMixin):
    """مجموعة عملاء بخصم دائم ثابت (standing discount) — مثال: "موظفين"،
    "شركاء B2B صغار"، "أصدقاء المنتجع". مختلفة تمامًا عن
    finance.ConditionalDiscount (شروط/حالات مؤقتة زي Happy Hour أو
    بروموشن) — دي عضوية دائمة مرتبطة بهوية العميل نفسه، مش شرط على الطلب.
    الاتنين يتعايشوا بدون تراكم — راجع dining.services._resolve_order_discount
    وbeach.services.sell_ticket لقرار "الأفضل للضيف يفوز، مش تراكم"."""
    __tablename__ = "crm_customer_groups"

    id:                  Mapped[int]      = mapped_column(primary_key=True)
    branch_id:           Mapped[int]      = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), index=True)
    name:                Mapped[str]      = mapped_column(String(100))
    name_ar:             Mapped[str | None] = mapped_column(String(100), nullable=True)
    discount_percentage: Mapped[Decimal]  = mapped_column(Numeric(5, 2), default=Decimal("0"))
    is_active:           Mapped[bool]     = mapped_column(Boolean, default=True)

    customers: Mapped[list["Customer"]] = relationship("Customer", back_populates="customer_group", lazy="select")


class Customer(Base, TimestampMixin):
    """عميل — قد يكون ضيف فندق، مستأجر، أو عميل مطعم VIP."""
    __tablename__ = "crm_customers"

    id:             Mapped[int]           = mapped_column(primary_key=True)
    branch_id:      Mapped[int]           = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    full_name:      Mapped[str]           = mapped_column(String(200))
    phone:          Mapped[str | None]    = mapped_column(String(20), nullable=True)
    email:          Mapped[str | None]    = mapped_column(String(150), nullable=True)
    national_id:    Mapped[str | None]    = mapped_column(EncryptedString(255), nullable=True)
    nationality:    Mapped[str | None]    = mapped_column(String(50), nullable=True)
    segment:        Mapped[str]           = mapped_column(String(30), default="regular")
    # regular|vip|corporate|travel_agent
    source:         Mapped[str]           = mapped_column(String(30), default="walk_in")
    # walk_in|online|referral|corporate|social_media
    customer_group_id: Mapped[int | None] = mapped_column(ForeignKey("crm_customer_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    total_spent:    Mapped[Decimal]       = mapped_column(Numeric(14, 2), default=Decimal("0"))
    visits_count:   Mapped[int]           = mapped_column(Integer, default=0)
    last_visit:     Mapped[date | None]   = mapped_column(Date, nullable=True)
    birthday:       Mapped[date | None]   = mapped_column(Date, nullable=True)
    notes:          Mapped[str | None]    = mapped_column(Text, nullable=True)
    is_active:      Mapped[bool]          = mapped_column(Boolean, default=True)
    blacklisted:    Mapped[bool]          = mapped_column(Boolean, default=False)
    blacklist_reason: Mapped[str | None]  = mapped_column(String(300), nullable=True)

    customer_group: Mapped["CustomerGroup | None"]     = relationship("CustomerGroup", back_populates="customers")
    interactions:  Mapped[list["CustomerInteraction"]] = relationship("CustomerInteraction", back_populates="customer", lazy="select")
    opportunities: Mapped[list["Opportunity"]]         = relationship("Opportunity",         back_populates="customer", lazy="select")
    activities:    Mapped[list["Activity"]]            = relationship("Activity",            back_populates="customer", lazy="select")


class CustomerInteraction(Base, TimestampMixin):
    """سجل تفاعلات مع العميل (مكالمة، واتساب، زيارة...)."""
    __tablename__ = "crm_interactions"

    id:               Mapped[int]          = mapped_column(primary_key=True)
    customer_id:      Mapped[int]          = mapped_column(ForeignKey("crm_customers.id", ondelete="CASCADE"))
    branch_id:        Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    interaction_type: Mapped[str]          = mapped_column(String(30))
    # call|whatsapp|email|visit|complaint|compliment|inquiry
    direction:        Mapped[str]          = mapped_column(String(10), default="inbound")
    # inbound|outbound
    summary:          Mapped[str]          = mapped_column(String(500))
    outcome:          Mapped[str | None]   = mapped_column(String(100), nullable=True)
    handled_by:       Mapped[int | None]   = mapped_column(Integer, nullable=True)
    occurred_at:      Mapped[datetime]     = mapped_column(DateTime)

    customer: Mapped["Customer"] = relationship("Customer", back_populates="interactions")


class Opportunity(Base, TimestampMixin):
    """فرصة بيعية — تايم شير، إيجار، عضوية..."""
    __tablename__ = "crm_opportunities"

    id:              Mapped[int]           = mapped_column(primary_key=True)
    branch_id:       Mapped[int]           = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    customer_id:     Mapped[int]           = mapped_column(ForeignKey("crm_customers.id", ondelete="CASCADE"))
    title:           Mapped[str]           = mapped_column(String(300))
    product_type:    Mapped[str]           = mapped_column(String(50))
    # timeshare|leasing|membership|group_booking|other
    stage:           Mapped[str]           = mapped_column(String(30), default="lead")
    # lead|qualified|proposal|negotiation|won|lost
    expected_value:  Mapped[Decimal]       = mapped_column(Numeric(14, 2), default=Decimal("0"))
    probability:     Mapped[int]           = mapped_column(Integer, default=20)  # %
    assigned_to:     Mapped[int | None]    = mapped_column(Integer, nullable=True)
    expected_close:  Mapped[date | None]   = mapped_column(Date, nullable=True)
    closed_at:       Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lost_reason:     Mapped[str | None]    = mapped_column(String(300), nullable=True)
    notes:           Mapped[str | None]    = mapped_column(Text, nullable=True)

    customer: Mapped["Customer"] = relationship("Customer", back_populates="opportunities")


class Activity(Base, TimestampMixin):
    """مهمة/نشاط مجدول مرتبط بعميل."""
    __tablename__ = "crm_activities"

    id:            Mapped[int]            = mapped_column(primary_key=True)
    branch_id:     Mapped[int]            = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    customer_id:   Mapped[int]            = mapped_column(ForeignKey("crm_customers.id", ondelete="CASCADE"))
    activity_type: Mapped[str]            = mapped_column(String(30))
    # follow_up|meeting|demo|proposal_send|contract_sign
    title:         Mapped[str]            = mapped_column(String(300))
    due_date:      Mapped[date]           = mapped_column(Date)
    due_time:      Mapped[str | None]     = mapped_column(String(5), nullable=True)  # "09:30"
    assigned_to:   Mapped[int | None]     = mapped_column(Integer, nullable=True)
    status:        Mapped[str]            = mapped_column(String(20), default="pending")
    # pending|done|cancelled
    done_at:       Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes:         Mapped[str | None]     = mapped_column(Text, nullable=True)

    customer: Mapped["Customer"] = relationship("Customer", back_populates="activities")


class LeadSource(Base, TimestampMixin):
    """مصدر العملاء المحتملين."""
    __tablename__ = "lead_sources"

    id:        Mapped[int]  = mapped_column(primary_key=True)
    branch_id: Mapped[int]  = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    name:      Mapped[str]  = mapped_column(String(100))
    # website|referral|social_media|walk_in|event|partner|advertisement|other
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Lead(Base, TimestampMixin):
    """عميل محتمل (lead) — قبل التحويل لفرصة أو حجز."""
    __tablename__ = "leads"

    id:             Mapped[int]            = mapped_column(primary_key=True)
    branch_id:      Mapped[int]            = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    full_name:      Mapped[str]            = mapped_column(String(200))
    phone:          Mapped[str | None]     = mapped_column(String(20), nullable=True)
    email:          Mapped[str | None]     = mapped_column(String(150), nullable=True)
    nationality:    Mapped[str | None]     = mapped_column(String(50), nullable=True)
    source_id:      Mapped[int | None]     = mapped_column(ForeignKey("lead_sources.id", ondelete="SET NULL"), nullable=True)
    interest:       Mapped[str]            = mapped_column(String(50), default="other")
    # timeshare|leasing|booking|membership|other
    stage:          Mapped[str]            = mapped_column(String(30), default="new")
    # new|contacted|qualified|proposal|won|lost
    assigned_to:    Mapped[int | None]     = mapped_column(Integer, nullable=True)
    expected_value: Mapped[Decimal]        = mapped_column(Numeric(14, 2), default=Decimal("0"))
    won_at:         Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lost_at:        Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lost_reason:    Mapped[str | None]     = mapped_column(String(300), nullable=True)
    booking_id:     Mapped[int | None]     = mapped_column(Integer, nullable=True)
    # يُعبأ عند won → إنشاء حجز تلقائي
    notes:          Mapped[str | None]     = mapped_column(Text, nullable=True)

    source:     Mapped["LeadSource | None"] = relationship("LeadSource", lazy="select")
    call_notes: Mapped[list["CallNote"]]    = relationship("CallNote", back_populates="lead", lazy="select")


class CallNote(Base, TimestampMixin):
    """مذكرة مكالمة مع عميل محتمل."""
    __tablename__ = "call_notes"

    id:          Mapped[int]         = mapped_column(primary_key=True)
    branch_id:   Mapped[int]         = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    lead_id:     Mapped[int]         = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    direction:   Mapped[str]         = mapped_column(String(10), default="outbound")
    # inbound|outbound
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary:     Mapped[str]         = mapped_column(String(1000))
    outcome:     Mapped[str]         = mapped_column(String(50), default="no_decision")
    # interested|not_interested|callback|no_decision|appointment_set
    callback_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    called_by:   Mapped[int]         = mapped_column(Integer)
    called_at:   Mapped[datetime]    = mapped_column(DateTime)

    lead: Mapped["Lead"] = relationship("Lead", back_populates="call_notes")


class Campaign(Base, TimestampMixin):
    """حملة تسويقية."""
    __tablename__ = "campaigns"

    id:                  Mapped[int]            = mapped_column(primary_key=True)
    branch_id:           Mapped[int]            = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    name:                Mapped[str]            = mapped_column(String(200))
    campaign_type:       Mapped[str]            = mapped_column(String(30))
    # social_media|email|sms|event|referral|other
    start_date:          Mapped[date]           = mapped_column(Date)
    end_date:            Mapped[date]           = mapped_column(Date)
    budget:              Mapped[Decimal]        = mapped_column(Numeric(12, 2), default=Decimal("0"))
    revenue_attributed:  Mapped[Decimal]        = mapped_column(Numeric(14, 2), default=Decimal("0"))
    leads_generated:     Mapped[int]            = mapped_column(Integer, default=0)
    status:              Mapped[str]            = mapped_column(String(20), default="planned")
    # planned|active|completed|cancelled
    notes:               Mapped[str | None]     = mapped_column(Text, nullable=True)
    created_by:          Mapped[int]            = mapped_column(Integer)


class GuestProfile(Base, TimestampMixin):
    """ملف شامل للضيف — يُحدَّث عند كل checkout."""
    __tablename__ = "guest_profiles"
    __table_args__ = (UniqueConstraint("branch_id", "phone", name="uq_guest_profile_branch_phone"),)

    id:           Mapped[int]          = mapped_column(primary_key=True)
    branch_id:    Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    full_name:    Mapped[str]          = mapped_column(String(200))
    phone:        Mapped[str]          = mapped_column(String(20))
    email:        Mapped[str | None]   = mapped_column(String(150), nullable=True)
    national_id:  Mapped[str | None]   = mapped_column(EncryptedString(255), nullable=True)
    nationality:  Mapped[str | None]   = mapped_column(String(50), nullable=True)
    birthday:     Mapped[date | None]  = mapped_column(Date, nullable=True)
    total_visits: Mapped[int]          = mapped_column(Integer, default=0)
    avg_spend:    Mapped[Decimal]      = mapped_column(Numeric(12, 2), default=Decimal("0"))
    vip_flag:     Mapped[bool]         = mapped_column(Boolean, default=False)
    last_stay:    Mapped[date | None]  = mapped_column(Date, nullable=True)
    preferences:  Mapped[str | None]   = mapped_column(Text, nullable=True)
    # JSON: {"pillow_type":"soft","floor_preference":"high","allergies":["nuts"]}
    notes:        Mapped[str | None]   = mapped_column(Text, nullable=True)
