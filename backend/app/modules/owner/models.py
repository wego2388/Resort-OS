"""
app/modules/owner/models.py
═══════════════════════════════════════════════════════════════════════
Owner Intelligence Cockpit — Database Models (Decision 0004).

جدولان فقط — المالك يملك بيانات قليلة جداً:
  1. OwnerWatchlist      — metrics مثبّتة وتفضيلات شخصية.
  2. OwnerAllocationRule — قواعد تخصيص التكلفة (مسودات + منشورة).

قاعدة صارمة: لا جداول أعمال (business tables) هنا. هذا الموديول
طبقة تجميع قراءة + سطح تكوين رفيع فوق الموديولات الموجودة.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.kernel.database import Base
from app.core.kernel.models.mixins import TimestampMixin


class OwnerWatchlist(Base, TimestampMixin):
    """Metrics مثبّتة وتفضيلات شخصية للمالك.

    الكتابة: owner فقط (unilateral per Decision 0004 §Unit economics governance).
    مفيش business data هنا — بس identifiers وترتيب وتسميات.
    """
    __tablename__ = "owner_watchlist"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "metric_key", name="uq_owner_watchlist_user_metric"),
    )

    id:            Mapped[int]        = mapped_column(primary_key=True)
    # owner_user_id: FK للـ User — int خام بدون FK مباشر لتجنب circular
    # dependency مع kernel.models.user (نفس نمط CashierShift.cashier_id).
    owner_user_id: Mapped[int]        = mapped_column(Integer, index=True)
    # metric_key: معرّف المقياس المثبّت (e.g. "revenue_today", "b2b_overdue")
    # — يطابق مفاتيح KPI dictionary في docs/owner/kpi-contracts.md.
    metric_key:    Mapped[str]        = mapped_column(String(100))
    # display_order: ترتيب العرض على الشاشة (أصغر = أول).
    display_order: Mapped[int]        = mapped_column(Integer, default=0)
    # label_override: تسمية مخصصة يختارها المالك — None = اسم المقياس الافتراضي.
    label_override: Mapped[str | None] = mapped_column(String(200), nullable=True)
    branch_id:     Mapped[int]        = mapped_column(Integer, index=True)


class OwnerAllocationRule(Base, TimestampMixin):
    """قاعدة تخصيص التكلفة — تحكم في unit economics (Decision 0004 §Unit
    economics governance).

    سير العمل:
      draft     → المالك يعمل مسودات ويجرّب في sandbox. لا تؤثر على أي
                  تقرير خارج sandbox.
      published → يفعّلها super_admin أو accountant فقط بعد موافقة محمد،
                  step-up auth، وسبب مكتوب. تدخل في تقارير unit economics.

    كل إصدار منشور immutable — التغيير ينشئ إصداراً جديداً (نفس مبدأ
    posted financial records في AGENTS.md §5).

    effective_from / effective_to: يحدد أي إصدار يُستخدم لأي فترة محاسبية.
    التقرير التاريخي يختار الإصدار الفعّال في وقته — لا يتأثر بإصدار لاحق.
    """
    __tablename__ = "owner_allocation_rules"

    id:             Mapped[int]        = mapped_column(primary_key=True)
    branch_id:      Mapped[int]        = mapped_column(Integer, index=True)
    version:        Mapped[int]        = mapped_column(Integer, default=1)
    status:         Mapped[str]        = mapped_column(String(20), default="draft", index=True)
    # draft | published
    # ── نسب التخصيص (Decimal — لا float) ──────────────────────────────
    # كل حقل يمثل نسبة مئوية (0-100) من التكلفة المشتركة المخصصة لهذا القطاع.
    # المجموع لا يُفرض على مستوى الـ DB (يُفرض في validation) — القطاعات
    # الممثّلة في المنتجع قد لا تغطي 100% (قطاعات غير مُفعَّلة = 0).
    pct_rooms:       Mapped[Decimal]   = mapped_column(Numeric(5, 2), default=Decimal("0"))
    pct_beach:       Mapped[Decimal]   = mapped_column(Numeric(5, 2), default=Decimal("0"))
    pct_dining:      Mapped[Decimal]   = mapped_column(Numeric(5, 2), default=Decimal("0"))
    pct_timeshare:   Mapped[Decimal]   = mapped_column(Numeric(5, 2), default=Decimal("0"))
    # ── نشر ──────────────────────────────────────────────────────────────
    effective_from:  Mapped[date | None]     = mapped_column(Date, nullable=True)
    effective_to:    Mapped[date | None]     = mapped_column(Date, nullable=True)
    published_by:    Mapped[int | None]      = mapped_column(Integer, nullable=True)
    published_at:    Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # step-up token ref للتدقيق — اختياري لكن موصى به
    publish_step_up_ref: Mapped[str | None]  = mapped_column(String(100), nullable=True)
    publish_reason:  Mapped[str | None]      = mapped_column(Text, nullable=True)
    # ── مسودة ────────────────────────────────────────────────────────────
    created_by:      Mapped[int]             = mapped_column(Integer)
    notes:           Mapped[str | None]      = mapped_column(Text, nullable=True)
