"""
app/modules/maintenance/models.py
Maintenance Module — الصيانة والأصول
Tables: assets, work_orders, preventive_schedules, work_order_parts
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


class Asset(Base, TimestampMixin):
    """الأصول والمعدات القابلة للصيانة."""
    __tablename__ = "assets"

    id:              Mapped[int]          = mapped_column(primary_key=True)
    branch_id:       Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    name:            Mapped[str]          = mapped_column(String(200))
    code:            Mapped[str]          = mapped_column(String(50), unique=True)  # AST-001
    category:        Mapped[str]          = mapped_column(String(50))               # hvac|electrical|plumbing|furniture|vehicle|other
    location:        Mapped[str | None]   = mapped_column(String(200), nullable=True)
    serial_number:   Mapped[str | None]   = mapped_column(String(100), nullable=True)
    purchase_date:   Mapped[date | None]  = mapped_column(Date, nullable=True)
    warranty_until:  Mapped[date | None]  = mapped_column(Date, nullable=True)
    status:          Mapped[str]          = mapped_column(String(30), default="operational")
    # operational|under_maintenance|out_of_service|disposed
    notes:           Mapped[str | None]   = mapped_column(Text, nullable=True)

    # ── Fixed-asset depreciation (straight-line — راجع finance/services.py::run_depreciation) ──
    # كل الحقول دي اختيارية عمدًا: أصل مش محتاج إهلاك (زي عقار مؤجَّر) أو لسه
    # مالياً مش متسجّل بيفضل purchase_cost=None وما يدخلش في أي عملية إهلاك.
    purchase_cost:            Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    salvage_value:             Mapped[Decimal]        = mapped_column(Numeric(12, 2), default=Decimal("0"))
    # القيمة المتبقية المتوقعة آخر العمر الإنتاجي — بتتخصم من التكلفة قبل حساب الإهلاك الشهري
    useful_life_years:        Mapped[int | None]     = mapped_column(Integer, nullable=True)
    depreciation_method:      Mapped[str]            = mapped_column(String(20), default="straight_line")
    depreciation_start_date:  Mapped[date | None]     = mapped_column(Date, nullable=True)
    accumulated_depreciation: Mapped[Decimal]         = mapped_column(Numeric(12, 2), default=Decimal("0"))
    # قيمة مجمّعة (cached) بتتحدّث مع كل AssetDepreciationEntry جديد (finance module)
    # — بديل أسرع من SUM() على كل قراءة، الرقم الرسمي دايمًا مطابق لمجموع سطور
    # asset_depreciation_entries الخاصة بنفس الأصل.

    work_orders:           Mapped[list["WorkOrder"]]          = relationship("WorkOrder",          back_populates="asset",    lazy="select")
    preventive_schedules:  Mapped[list["PreventiveSchedule"]] = relationship("PreventiveSchedule", back_populates="asset",    lazy="select")


class WorkOrder(Base, TimestampMixin):
    """أوامر الصيانة — تصحيحية أو وقائية."""
    __tablename__ = "work_orders"

    id:              Mapped[int]            = mapped_column(primary_key=True)
    branch_id:       Mapped[int]            = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    asset_id:        Mapped[int | None]     = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"), nullable=True)
    order_number:    Mapped[str]            = mapped_column(String(30), unique=True)  # WO-20260630-0001
    title:           Mapped[str]            = mapped_column(String(300))
    description:     Mapped[str | None]     = mapped_column(Text, nullable=True)
    order_type:      Mapped[str]            = mapped_column(String(30), default="corrective")
    # corrective|preventive|inspection
    schedule_id:     Mapped[int | None]     = mapped_column(ForeignKey("preventive_schedules.id", ondelete="SET NULL"), nullable=True)
    # الجدول الوقائي اللي ولّد أمر الصيانة ده (لو order_type="preventive") — لازم
    # نعرف نرجع نحدّث next_due بتاعه لما الأمر يخلص، وإلا هيتعمل أمر جديد كل يوم للأبد
    priority:        Mapped[str]            = mapped_column(String(20), default="medium")
    # low|medium|high|critical
    status:          Mapped[str]            = mapped_column(String(30), default="open")
    # open|in_progress|pending_parts|completed|cancelled
    assigned_to:     Mapped[int | None]     = mapped_column(Integer, nullable=True)
    reported_by:     Mapped[int | None]     = mapped_column(Integer, nullable=True)
    scheduled_date:  Mapped[date | None]    = mapped_column(Date, nullable=True)
    completed_at:    Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    labour_hours:    Mapped[Decimal]        = mapped_column(Numeric(6, 2), default=Decimal("0"))
    labour_cost:     Mapped[Decimal]        = mapped_column(Numeric(10, 2), default=Decimal("0"))
    parts_cost:      Mapped[Decimal]        = mapped_column(Numeric(10, 2), default=Decimal("0"))
    notes:           Mapped[str | None]     = mapped_column(Text, nullable=True)

    asset: Mapped["Asset | None"] = relationship("Asset", back_populates="work_orders")
    parts: Mapped[list["WorkOrderPart"]] = relationship("WorkOrderPart", back_populates="work_order", lazy="select")


class WorkOrderPart(Base, TimestampMixin):
    """قطع الغيار المستخدمة في أمر الصيانة.

    لو product_id مضبوط: القطعة مسحوبة من inventory (بيتخصم من current_stock عند الإضافة).
    لو product_id = None: قطعة خارجية (اشتريناها خصيصًا لهذا الأمر، unit_cost يدوي).
    """
    __tablename__ = "work_order_parts"

    id:             Mapped[int]          = mapped_column(primary_key=True)
    work_order_id:  Mapped[int]          = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"))
    product_id:     Mapped[int | None]   = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    part_name:      Mapped[str]          = mapped_column(String(200))
    part_number:    Mapped[str | None]   = mapped_column(String(100), nullable=True)
    quantity:       Mapped[Decimal]      = mapped_column(Numeric(8, 2), default=Decimal("1"))
    unit_cost:      Mapped[Decimal]      = mapped_column(Numeric(10, 2), default=Decimal("0"))
    total_cost:     Mapped[Decimal]      = mapped_column(Numeric(10, 2), default=Decimal("0"))

    work_order: Mapped["WorkOrder"] = relationship("WorkOrder", back_populates="parts")


class PreventiveSchedule(Base, TimestampMixin):
    """جدول الصيانة الوقائية الدورية."""
    __tablename__ = "preventive_schedules"

    id:               Mapped[int]          = mapped_column(primary_key=True)
    branch_id:        Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    asset_id:         Mapped[int]          = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    title:            Mapped[str]          = mapped_column(String(300))
    frequency_days:   Mapped[int]          = mapped_column(Integer)   # كل N يوم
    last_done:        Mapped[date | None]  = mapped_column(Date, nullable=True)
    next_due:         Mapped[date]         = mapped_column(Date)
    is_active:        Mapped[bool]         = mapped_column(Boolean, default=True)
    assigned_to:      Mapped[int | None]   = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    checklist:        Mapped[str | None]   = mapped_column(Text, nullable=True)  # JSON list of steps

    asset: Mapped["Asset"] = relationship("Asset", back_populates="preventive_schedules")
