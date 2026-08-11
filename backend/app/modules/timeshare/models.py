"""
app/modules/timeshare/models.py
Timeshare Module — عقود الملكية الجزئية
Tables: timeshare_contracts, timeshare_installments, timeshare_maintenance_dues,
timeshare_waitlist
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


class TimeshareContract(Base, TimestampMixin):
    __tablename__ = "timeshare_contracts"

    id:                    Mapped[int]           = mapped_column(primary_key=True)
    branch_id:             Mapped[int]           = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    contract_number:       Mapped[str]           = mapped_column(String(30), unique=True)  # TS-20260630-0001
    customer_name:         Mapped[str]           = mapped_column(String(200))
    customer_phone:        Mapped[str | None]    = mapped_column(String(20), nullable=True)
    customer_email:        Mapped[str | None]    = mapped_column(String(150), nullable=True)
    customer_national_id:  Mapped[str | None]    = mapped_column(EncryptedString(255), nullable=True)
    room_type:             Mapped[str]           = mapped_column(String(10))   # Studio|Chalet
    # عدد الأفراد: 2 (Studio) أو 4/6 (Chalet — 6 = باقة Family Compound).
    # nullable عمدًا (OPS-DATA-02 §8 نقطة 2): عقود مستوردة قديمة كان
    # room_type بتاعها 2R/4R/6R قبل migration f2a3b4c5d6e7 اللي وحّدت
    # 4R/6R في "Chalet" واحد — يعني السعة الحقيقية (4 ولا 6) ضاعت وقتها
    # لعقود Chalet القديمة، ومفيش استنتاج آمن ممكن من البيانات الحالية
    # لوحدها. Studio دايمًا 2 (استنتاج آمن 100%، اتعمل في migration
    # الـbackfill). عقود Chalet القديمة تفضل None لحد ما تُراجَع يدويًا —
    # صفر default=2 عشوائي بيغيّر مبلغ الصيانة المستحق بصمت.
    unit_capacity:         Mapped[int | None]    = mapped_column(Integer, nullable=True)
    beneficiary_name:      Mapped[str | None]    = mapped_column(String(200), nullable=True)
    # اسم الزوجة/المستفيد الآخر — من نموذج الحجز الداخلي
    customer_phone_work:   Mapped[str | None]    = mapped_column(String(20), nullable=True)
    customer_phone_home:   Mapped[str | None]    = mapped_column(String(20), nullable=True)
    mailing_address:       Mapped[str | None]    = mapped_column(String(300), nullable=True)
    # عنوان المراسلة — قد يختلف عن address (عنوان الإقامة الموجود بالفعل)
    unit_id:               Mapped[int | None]    = mapped_column(ForeignKey("timeshare_units.id", ondelete="SET NULL"), nullable=True)
    # وحدة مخصَّصة بشكل دائم للعقد (نفس الوحدة كل سنة) — None=عائم (أي وحدة متاحة
    # من نفس room_type وقت الحجز، بنفس منطق week_number: 1-52 ثابت مقابل None=عائم)
    week_number:           Mapped[int | None]    = mapped_column(Integer, nullable=True)  # 1-52 fixed, None=floating
    nights_per_year:       Mapped[int]           = mapped_column(Integer, default=7)
    season:                Mapped[str]           = mapped_column(String(10), default="high")  # high|low|both
    total_value:           Mapped[Decimal]       = mapped_column(Numeric(14, 2))
    down_payment:          Mapped[Decimal]       = mapped_column(Numeric(14, 2))
    down_payment_method:   Mapped[str | None]    = mapped_column(String(30), nullable=True)
    installments:          Mapped[int]           = mapped_column(Integer, default=12)
    installment_period:    Mapped[int]           = mapped_column(Integer, default=1)  # 1=monthly,3=quarterly,6=biannual
    first_installment_date: Mapped[date]         = mapped_column(Date)
    partner_share_pct:     Mapped[Decimal]       = mapped_column(Numeric(5, 2), default=Decimal("0"))
    partner_company:       Mapped[str | None]    = mapped_column(String(200), nullable=True)
    status:                Mapped[str]           = mapped_column(String(20), default="active")
    # draft|active|suspended|cancelled|expired
    booking_frozen:        Mapped[bool]          = mapped_column(Boolean, default=False)
    start_date:            Mapped[date]          = mapped_column(Date)
    end_date:              Mapped[date | None]   = mapped_column(Date, nullable=True)
    signed_by:             Mapped[int | None]    = mapped_column(Integer, nullable=True)
    notes:                 Mapped[str | None]    = mapped_column(Text, nullable=True)

    # ── بيانات العميل الموسّعة (من نظام إنتاج فعلي — elkheima-beach-resort) ──
    nationality:           Mapped[str | None]    = mapped_column(String(50), nullable=True)
    occupation:             Mapped[str | None]    = mapped_column(String(100), nullable=True)
    passport_number:        Mapped[str | None]    = mapped_column(EncryptedString(255), nullable=True)
    address:                Mapped[str | None]    = mapped_column(String(300), nullable=True)

    # ── بيانات العقد التجارية الموسّعة ──
    contract_date:          Mapped[date | None]   = mapped_column(Date, nullable=True)
    purchase_price:         Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    contract_deposit:       Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    maintenance_fee:        Mapped[Decimal]       = mapped_column(Numeric(10, 2), default=Decimal("0"))
    maintenance_increase:   Mapped[Decimal]       = mapped_column(Numeric(5, 2), default=Decimal("10"))  # % سنوي
    batch_number:           Mapped[int | None]    = mapped_column(Integer, nullable=True)   # رقم دفعة الاستيراد
    form_number:            Mapped[str | None]    = mapped_column(String(50), nullable=True)  # رقم الاستمارة
    receipt_number:         Mapped[str | None]    = mapped_column(String(50), nullable=True)
    rci_included:           Mapped[bool]          = mapped_column(Boolean, default=False)
    contract_value:         Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)  # القيمة الإجمالية في الاستمارة
    net_contract_value:     Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    over_under_price:       Mapped[Decimal]       = mapped_column(Numeric(14, 2), default=Decimal("0"))
    years_count:            Mapped[int]           = mapped_column(Integer, default=99)
    payment_type:           Mapped[str]           = mapped_column(String(20), default="installment")  # installment|cash

    # ── إلغاء ──
    cancelled_at:           Mapped[date | None]   = mapped_column(Date, nullable=True)
    cancel_amount:          Mapped[Decimal]       = mapped_column(Numeric(14, 2), default=Decimal("0"))
    cancelled_by:           Mapped[int | None]    = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    refund_method:          Mapped[str | None]    = mapped_column(String(30), nullable=True)

    installments_list: Mapped[list["TimeshareInstallment"]] = relationship(
        "TimeshareInstallment", back_populates="contract", lazy="select",
        foreign_keys="TimeshareInstallment.contract_id",
    )
    maintenance_dues_list: Mapped[list["TimeshareMaintenanceDue"]] = relationship(
        "TimeshareMaintenanceDue", back_populates="contract", lazy="select",
        foreign_keys="TimeshareMaintenanceDue.contract_id",
    )
    waitlist: Mapped[list["TimeshareWaitlist"]] = relationship(
        "TimeshareWaitlist", back_populates="contract", lazy="select"
    )
    unit: Mapped["TimeshareUnit | None"] = relationship(
        "TimeshareUnit", foreign_keys=[unit_id], lazy="select",
    )


class TimeshareInstallment(Base, TimestampMixin):
    __tablename__ = "timeshare_installments"

    id:              Mapped[int]            = mapped_column(primary_key=True)
    contract_id:     Mapped[int]            = mapped_column(ForeignKey("timeshare_contracts.id", ondelete="CASCADE"))
    installment_no:  Mapped[int]            = mapped_column(Integer)
    due_date:        Mapped[date]           = mapped_column(Date, index=True)
    amount:          Mapped[Decimal]        = mapped_column(Numeric(14, 2))
    paid_amount:     Mapped[Decimal]        = mapped_column(Numeric(14, 2), default=Decimal("0"))
    status:          Mapped[str]            = mapped_column(String(20), default="pending")
    # pending|paid|partial|overdue
    paid_at:         Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payment_method:  Mapped[str | None]     = mapped_column(String(30), nullable=True)
    receipt_number:  Mapped[str | None]     = mapped_column(String(50), nullable=True)
    notes:           Mapped[str | None]     = mapped_column(String(300), nullable=True)

    contract: Mapped["TimeshareContract"] = relationship(
        "TimeshareContract", back_populates="installments_list",
        foreign_keys=[contract_id],
    )


class TimeshareMaintenanceDue(Base, TimestampMixin):
    """رسم الصيانة السنوي المستحق على عقد لسنة تقويمية معيّنة (fee_year) —
    دورة سداد واحدة موحّدة (يناير-ديسمبر) لكل العقود، تطابق شكل التعميم
    الرسمي ("مصروفات الصيانة عام 2026"). المبلغ يُنسخ من
    TimeshareContract.maintenance_fee وقت التوليد (لقطة/snapshot) — تغيير
    maintenance_fee لاحقًا (تعميم سنة جديدة) لا يُعدِّل مستحقات سنوات سابقة
    مولَّدة بالفعل، بالضبط زي جدول أقساط العقد نفسه. لا تُستخدم
    maintenance_increase في أي حساب تلقائي — الزيادات الحقيقية قفزات غير
    منتظمة بقرار خارجي (لجنة فض منازعات + وزارة السياحة)، مش نسبة سنوية
    ثابتة، فالمبلغ الجديد كل سنة بيتحدد يدويًا في maintenance_fee."""
    __tablename__ = "timeshare_maintenance_dues"
    __table_args__ = (
        UniqueConstraint("contract_id", "fee_year", name="uq_maintenance_due_contract_year"),
    )

    id:              Mapped[int]            = mapped_column(primary_key=True)
    contract_id:     Mapped[int]            = mapped_column(ForeignKey("timeshare_contracts.id", ondelete="CASCADE"))
    fee_year:        Mapped[int]            = mapped_column(Integer, index=True)
    due_date:        Mapped[date]           = mapped_column(Date, index=True)
    amount:          Mapped[Decimal]        = mapped_column(Numeric(14, 2))
    paid_amount:     Mapped[Decimal]        = mapped_column(Numeric(14, 2), default=Decimal("0"))
    status:          Mapped[str]            = mapped_column(String(20), default="pending")
    # pending|paid|partial|overdue
    paid_at:         Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payment_method:  Mapped[str | None]     = mapped_column(String(30), nullable=True)
    receipt_number:  Mapped[str | None]     = mapped_column(String(50), nullable=True)
    notes:           Mapped[str | None]     = mapped_column(String(300), nullable=True)

    contract: Mapped["TimeshareContract"] = relationship(
        "TimeshareContract", back_populates="maintenance_dues_list",
        foreign_keys=[contract_id],
    )


class TimeshareMaintenanceFeeRule(Base, TimestampMixin):
    """قاعدة صيانة سنوية مُعتمَدة (تعميم رسمي) — effective-dated بحسب تاريخ
    توقيع العقد (contract_tier_from) + السعة، بدل dict ثابت في الكود
    بيتصحّح يدويًا كل سنة. راجع OPS-DATA-02 §8 نقطة 3: "لا hard-code سنة
    2026 ثم تعدل contracts يدويًا سنويًا. أضف جدول قواعد effective-dated/
    versioned حسب contract-date tier والسعة والسنة."

    مثال: تعميم 2026 بيقول عقد اتوقّع قبل 1 مايو 2026 بسعة 4 أفراد يدفع
    2000 ج، وعقد اتوقّع من 1 مايو بنفس السعة يدفع 3000 ج — كل واحد من دول
    صف منفصل هنا (fee_year=2026، contract_tier_from مختلف). الدالة
    services.get_recommended_maintenance_fee بتدوّر على أحدث صف
    (contract_tier_from <= تاريخ توقيع العقد) لنفس (fee_year, capacity).

    ده للعرض/التحقق فقط — القرار النهائي يفضل TimeshareContract.
    maintenance_fee المُدخَل يدويًا (زي ما هو، مش تغيير سلوك). لا حذف
    حقيقي أبدًا لقاعدة استُخدمت فعليًا في أي due — is_active بس."""
    __tablename__ = "timeshare_maintenance_fee_rules"
    __table_args__ = (
        UniqueConstraint(
            "branch_id", "fee_year", "contract_tier_from", "capacity",
            name="uq_maintenance_fee_rule_branch_year_tier_capacity",
        ),
    )

    id:                  Mapped[int]           = mapped_column(primary_key=True)
    branch_id:           Mapped[int]           = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    version:             Mapped[str]           = mapped_column(String(60))
    fee_year:            Mapped[int]           = mapped_column(Integer, index=True)
    contract_tier_from:  Mapped[date]          = mapped_column(Date)
    capacity:            Mapped[int]           = mapped_column(Integer)  # 2|4|6
    fee:                 Mapped[Decimal]       = mapped_column(Numeric(10, 2))
    is_active:           Mapped[bool]          = mapped_column(Boolean, default=True)
    created_by:          Mapped[int | None]    = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes:               Mapped[str | None]    = mapped_column(String(300), nullable=True)


class TimesharePeakSeason(Base, TimestampMixin):
    """فترة ذروة يدخلها timeshare_admin سنويًا — مثال: "صيف 2026"
    (1 يونيو → 30 سبتمبر، peak_kind=regular) أو "عيد الأضحى 2026"
    (peak_kind=official_holiday). الأعياد الهجرية بتتغيّر كل سنة —
    Mohamed هو اللي يدخلها يدويًا بدل أي حساب تلقائي قد يكون غلط
    (نفس فلسفة TIMESHARE-01_FULL_PLAN_AR.md §3-أ).

    peak_kind بيفرّق مواسم العيد الرسمي عن الموسم العادي (صيف) — راجع
    OPS-DATA-02 §8 نقطة 5: قاعدة "مفيش أعياد متتالية" بتتحقق بس لو
    الموسم official_holiday؛ الصيف/الموسم العادي مش "عيد" ومعفى منها
    تمامًا (بس لسه خاضع لحد أسبوع الذروة الواحد سنويًا زي أي ذروة).

    created_by nullable لأن FK بتاعها ondelete=SET NULL — عمود not-null
    مع SET NULL تناقض فعلي (OPS-DATA-02 §8 نقطة 4، باج حقيقي في الخطة
    الأصلية). لا حذف حقيقي أبدًا لموسم استُخدم في أي قرار قبول/رفض —
    is_active بس (soft)."""
    __tablename__ = "timeshare_peak_seasons"

    id:          Mapped[int]        = mapped_column(primary_key=True)
    branch_id:   Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    name:        Mapped[str]        = mapped_column(String(100))
    name_ar:     Mapped[str | None] = mapped_column(String(100), nullable=True)
    peak_kind:   Mapped[str]        = mapped_column(String(20), default="regular")
    # official_holiday|regular
    season_year: Mapped[int]        = mapped_column(Integer, index=True)
    start_date:  Mapped[date]       = mapped_column(Date, index=True)
    end_date:    Mapped[date]       = mapped_column(Date)
    is_active:   Mapped[bool]       = mapped_column(Boolean, default=True)
    created_by:  Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes:       Mapped[str | None] = mapped_column(String(300), nullable=True)


class TimeshareVisit(Base, TimestampMixin):
    """زيارة فعلية لصاحب الملكية الجزئية — تحجز غرفة في PMS."""
    __tablename__ = "timeshare_visits"

    id:              Mapped[int]            = mapped_column(primary_key=True)
    branch_id:       Mapped[int]            = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    contract_id:     Mapped[int]            = mapped_column(ForeignKey("timeshare_contracts.id", ondelete="CASCADE"))
    booking_id:      Mapped[int | None]     = mapped_column(ForeignKey("bookings.id",  ondelete="SET NULL"), nullable=True)
    unit_id:         Mapped[int | None]     = mapped_column(ForeignKey("timeshare_units.id", ondelete="SET NULL"), nullable=True)
    # الوحدة الفعلية المخصَّصة لهذه الزيارة تحديدًا — لعقد عائم ممكن تختلف كل سنة
    paired_unit_id:  Mapped[int | None]     = mapped_column(ForeignKey("timeshare_units.id", ondelete="SET NULL"), nullable=True)
    # الوحدة التانية في زوج Family Compound (لعقود سعة 6 بس) — راجع
    # TimeshareUnitPair. None لأي زيارة عادية (سعة 2/4).
    entitlement_visit: Mapped[bool]         = mapped_column(Boolean, default=False)
    # True لزيارة استحقاق تعاقدي (العقد سعة 6 مسدد بالكامل بقيمة العقد، مفيش
    # رسم ليلة جديد) — راجع OPS-DATA-02 §8 نقطة 11. create_visit عمرها ما
    # كانت بترحّل إيراد غرف أصلًا (بتخصّص وحدة ملكية جزئية بس، مش حجز PMS)،
    # فالعمود ده بيوثّق الحقيقة دي صراحةً بدل ما تفضل ضمنية.
    check_in:        Mapped[date]           = mapped_column(Date)
    check_out:       Mapped[date]           = mapped_column(Date)
    nights:          Mapped[int]            = mapped_column(Integer)
    status:          Mapped[str]            = mapped_column(String(20), default="scheduled")
    # scheduled|active|completed|cancelled
    notes:           Mapped[str | None]     = mapped_column(Text, nullable=True)

    contract: Mapped["TimeshareContract"] = relationship("TimeshareContract")
    unit: Mapped["TimeshareUnit | None"] = relationship("TimeshareUnit", foreign_keys=[unit_id], lazy="select")
    paired_unit: Mapped["TimeshareUnit | None"] = relationship("TimeshareUnit", foreign_keys=[paired_unit_id], lazy="select")


class TimeshareUnit(Base, TimestampMixin):
    """وحدة ملكية جزئية فعلية (شاليه/شقة) — منفصلة تمامًا عن غرف الفندق العادية
    (pms.Room). قرار معماري متعمد (2026-07-04، بعد سؤال صاحب المنتجع مباشرة):
    وحدات الملكية الجزئية مبنى/مسكن منفصل فعليًا عن غرف الفندق (Standard/Deluxe/
    Family Suite/Presidential) — لا تُوحَّد مع room_types/rooms الفندق."""
    __tablename__ = "timeshare_units"
    __table_args__ = (
        UniqueConstraint("branch_id", "unit_number", name="uq_timeshare_unit_branch_number"),
    )

    id:           Mapped[int]        = mapped_column(primary_key=True)
    branch_id:    Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    unit_number:  Mapped[str]        = mapped_column(String(20))     # "A-101"
    unit_type:    Mapped[str]        = mapped_column(String(10))     # Studio|Chalet — يطابق TimeshareContract.room_type
    status:       Mapped[str]        = mapped_column(String(20), default="available")
    # available|occupied|maintenance
    notes:        Mapped[str | None] = mapped_column(String(300), nullable=True)


class TimeshareUnitPair(Base, TimestampMixin):
    """زوج وحدات معتمد (شاليه + استوديو بنفس رقم الوحدة) لعقود سعة 6 —
    Family Compound entitlement (راجع pms.RoomBundle لنفس المفهوم عند حجوزات
    الضيوف العاديين؛ نسخة منفصلة عمدًا هنا لأن TimeshareUnit مخزون منفصل
    تمامًا عن pms.Room — راجع docstring TimeshareUnit فوق). UniqueConstraint
    يمنع نفس الوحدة تنضم لأكتر من زوج واحد بالغلط."""
    __tablename__ = "timeshare_unit_pairs"
    __table_args__ = (
        UniqueConstraint("chalet_unit_id", name="uq_timeshare_unit_pair_chalet"),
        UniqueConstraint("studio_unit_id", name="uq_timeshare_unit_pair_studio"),
    )

    id:              Mapped[int]        = mapped_column(primary_key=True)
    branch_id:       Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    chalet_unit_id:  Mapped[int]        = mapped_column(ForeignKey("timeshare_units.id", ondelete="RESTRICT"))
    studio_unit_id:  Mapped[int]        = mapped_column(ForeignKey("timeshare_units.id", ondelete="RESTRICT"))
    is_active:       Mapped[bool]       = mapped_column(Boolean, default=True)
    notes:           Mapped[str | None] = mapped_column(String(300), nullable=True)

    chalet_unit: Mapped["TimeshareUnit"] = relationship("TimeshareUnit", foreign_keys=[chalet_unit_id])
    studio_unit: Mapped["TimeshareUnit"] = relationship("TimeshareUnit", foreign_keys=[studio_unit_id])


class TimeshareVisitRequest(Base, TimestampMixin):
    """طلب زيارة من صاحب العقد نفسه عبر بوابة العميل العامة (طلب Mohamed
    2026-08-03) — مش حجز مباشر، مجرد طلب بتواريخ مفضّلة يراجعه موظف/مدير
    ويوافق عليه (بيحدد التواريخ الفعلية والوحدة عبر services.create_visit
    الموجودة بالفعل — نفس كل قواعدها: منع التعارض، منع الحجز على عقد مجمَّد/
    ملغي/منتهي). لا نكرر منطق الحجز هنا خالص، بس نضيف طبقة "طلب ← موافقة"
    فوقه."""
    __tablename__ = "timeshare_visit_requests"

    id:               Mapped[int]             = mapped_column(primary_key=True)
    branch_id:        Mapped[int]             = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    contract_id:      Mapped[int]             = mapped_column(ForeignKey("timeshare_contracts.id", ondelete="CASCADE"), index=True)
    preferred_start:  Mapped[date]            = mapped_column(Date)
    preferred_end:    Mapped[date]            = mapped_column(Date)
    # حتى بديلين إضافيين (نموذج الحجز الداخلي: 3 فترات — الثالثة =
    # preferred_start/end نفسهم). العميل حر في اختيارهم، مش لازم يبدأوا سبت.
    alt_start_1:      Mapped[date | None]     = mapped_column(Date, nullable=True)
    alt_end_1:        Mapped[date | None]     = mapped_column(Date, nullable=True)
    alt_start_2:      Mapped[date | None]     = mapped_column(Date, nullable=True)
    alt_end_2:        Mapped[date | None]     = mapped_column(Date, nullable=True)
    notes:            Mapped[str | None]      = mapped_column(Text, nullable=True)
    status:           Mapped[str]             = mapped_column(String(20), default="pending", index=True)
    # pending|approved|rejected|cancelled
    reviewed_by:      Mapped[int | None]      = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at:      Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str | None]      = mapped_column(String(300), nullable=True)
    # الزيارة الفعلية اللي اتعملت لما الطلب اتوافق عليه (services.create_visit)
    visit_id:         Mapped[int | None]      = mapped_column(ForeignKey("timeshare_visits.id", ondelete="SET NULL"), nullable=True)

    # ── إثبات موافقة (OPS-DATA-02 §8 نقطة 1) — راجع schemas.py للتفاصيل ──
    # الصف ده immutable بعد الإنشاء (زي preferred_start/notes)، فالأعمدة
    # دي لقطة دائمة لحظة تقديم الطلب — مش قابلة للتعديل لاحقًا.
    terms_version:            Mapped[str]           = mapped_column(String(60))
    terms_accepted_at:         Mapped[datetime]      = mapped_column(DateTime)
    booking_rules_version:     Mapped[str]           = mapped_column(String(60))
    booking_rules_accepted_at: Mapped[datetime]      = mapped_column(DateTime)

    contract: Mapped["TimeshareContract"] = relationship("TimeshareContract")
    visit:    Mapped["TimeshareVisit | None"] = relationship("TimeshareVisit", foreign_keys=[visit_id])


class TimeshareSupportTicket(Base, TimestampMixin):
    """دعم فني/خدمة عملاء خاص بمالكي عقود الملكية الجزئية — منفصل تمامًا عن
    نظام استفسارات الموقع العام (crm.Lead عبر /hub/contact)، اللي كان
    البديل الوحيد قبل كده وبيخلط شكاوى أصحاب العقود مع استفسارات عملاء
    عاديين في نفس الصندوق بدون أي ربط بالعقد الحقيقي (طلب Mohamed
    2026-08-03: "خاصة بنفسها في خدمة العملاء")."""
    __tablename__ = "timeshare_support_tickets"

    id:           Mapped[int]             = mapped_column(primary_key=True)
    branch_id:    Mapped[int]             = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    contract_id:  Mapped[int]             = mapped_column(ForeignKey("timeshare_contracts.id", ondelete="CASCADE"), index=True)
    subject:      Mapped[str]             = mapped_column(String(200))
    status:       Mapped[str]             = mapped_column(String(20), default="open", index=True)
    # open|in_progress|resolved|closed
    assigned_to:  Mapped[int | None]      = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at:  Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    contract: Mapped["TimeshareContract"] = relationship("TimeshareContract")
    replies:  Mapped[list["TimeshareSupportTicketReply"]] = relationship(
        "TimeshareSupportTicketReply", back_populates="ticket",
        order_by="TimeshareSupportTicketReply.created_at", lazy="select",
    )


class TimeshareSupportTicketReply(Base, TimestampMixin):
    """رسالة واحدة في محادثة التذكرة — من صاحب العقد نفسه (author_type=owner،
    author_user_id=None) أو من موظف (author_type=staff). الرسالة الأولى
    (subject/message الأصليين) بتتخزن كأول رد من النوع owner، مش حقل منفصل
    على التذكرة — عشان المحادثة كلها تبقى في مكان واحد بالترتيب الزمني."""
    __tablename__ = "timeshare_support_ticket_replies"

    id:              Mapped[int]        = mapped_column(primary_key=True)
    ticket_id:       Mapped[int]        = mapped_column(ForeignKey("timeshare_support_tickets.id", ondelete="CASCADE"), index=True)
    author_type:     Mapped[str]        = mapped_column(String(10))  # owner|staff
    author_user_id:  Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    message:         Mapped[str]        = mapped_column(Text)

    ticket: Mapped["TimeshareSupportTicket"] = relationship("TimeshareSupportTicket", back_populates="replies")


class TimeshareWaitlist(Base, TimestampMixin):
    """قائمة انتظار لأسابيع الملكية الجزئية العائم."""
    __tablename__ = "timeshare_waitlist"

    id:               Mapped[int]             = mapped_column(primary_key=True)
    branch_id:        Mapped[int]             = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    contract_id:      Mapped[int]             = mapped_column(ForeignKey("timeshare_contracts.id", ondelete="CASCADE"))
    requested_start:  Mapped[date]            = mapped_column(Date)
    requested_end:    Mapped[date]            = mapped_column(Date)
    position:         Mapped[int]             = mapped_column(Integer)
    status:           Mapped[str]             = mapped_column(String(20), default="waiting")
    # waiting|notified|confirmed|expired|cancelled
    notified_at:      Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at:       Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    contract: Mapped["TimeshareContract"] = relationship("TimeshareContract", back_populates="waitlist")
