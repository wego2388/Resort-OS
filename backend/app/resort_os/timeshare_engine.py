"""
timeshare_engine.py — Pure timeshare domain logic.
No database, no HTTP framework, no external services.
All functions accept plain Python objects and return plain Python objects.

المصدر الأساسي: elkheima-beach-resort/api/finance/contracts.py
هذا الـ engine يعزل الحسابات الحرجة ويجعلها قابلة للاختبار بدون DB.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


# ── Constants ─────────────────────────────────────────────────────────────────

INSTALLMENT_PERIODS = {
    "monthly":   1,
    "quarterly": 3,
    "biannual":  6,
}

CONTRACT_STATUSES  = ("draft", "active", "suspended", "cancelled", "expired")
PAYMENT_STATUSES   = ("pending", "partial", "paid", "overdue")
WAITLIST_STATUSES  = ("waiting", "notified", "confirmed", "expired", "cancelled")

# عقوبة تأخر الإيجار التجاري فقط — لا تُطبَّق على التايم شير
LEASE_PENALTY_RULES = [
    (30, Decimal("0.10")),   # > 30 يوم → 10%
    (7,  Decimal("0.05")),   # > 7 أيام → 5%
]

WAITLIST_EXPIRY_HOURS         = 24
VISIT_REMINDER_DAYS_BEFORE    = 3
INSTALLMENT_REMINDER_DAYS_BEFORE = 7


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class InstallmentScheduleItem:
    installment_no: int
    due_date: date
    amount: Decimal
    status: str = "pending"


@dataclass
class TimeshareContractData:
    """البيانات الضرورية للحسابات — ليست الـ DB model."""
    contract_id: int
    customer_name: str
    customer_phone: str
    room_type: str                       # 2R / 4R / 6R
    week_number: Optional[int]           # 1-52 للثابت، None للعائم
    nights_per_year: int                 # عادةً 7
    total_value: Decimal
    down_payment: Decimal
    installments: int
    installment_period: int              # 1 / 3 / 6 شهر
    first_installment_date: date
    partner_share_pct: Decimal           # 0-100
    status: str
    overdue_amount: Decimal = Decimal("0")


@dataclass
class VisitWindow:
    """نافذة الزيارة السنوية — تُحسب من week_number ISO."""
    year: int
    week_number: int
    visit_start: date
    visit_end: date
    nights: int
    days_until: int                      # سالب = مضت، 0 = اليوم

    @property
    def is_past(self) -> bool:
        return self.days_until < 0

    @property
    def is_upcoming_within(self) -> bool:
        return 0 <= self.days_until <= 30

    @property
    def is_today(self) -> bool:
        return self.days_until == 0


@dataclass
class WaitlistEntry:
    entry_id: int
    contract_id: int
    customer_name: str
    customer_phone: str
    requested_start: date
    requested_end: date
    position: int
    status: str = "waiting"
    notified_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


@dataclass
class ContractSummary:
    """ملخص مضغوط لـ CS Dashboard."""
    contract_id: int
    customer_name: str
    customer_phone: Optional[str]
    room_type: str
    week_number: Optional[int]
    total_value: Decimal
    collected: Decimal
    overdue_amount: Decimal
    pending_count: int
    next_due: Optional[date]
    upcoming_visit: Optional[VisitWindow] = None

    @property
    def collection_rate_pct(self) -> int:
        if self.total_value == 0:
            return 0
        return min(100, int(self.collected / self.total_value * 100))

    @property
    def has_overdue(self) -> bool:
        return self.overdue_amount > Decimal("0")


# ── Installment generation ────────────────────────────────────────────────────

def generate_installment_schedule(
    total_value: Decimal,
    down_payment: Decimal,
    installments: int,
    installment_period: int,
    first_installment_date: date,
) -> list[InstallmentScheduleItem]:
    """
    يُولِّد جدول الأقساط الكامل — يُستدعى مرة واحدة عند توقيع العقد.

    installment_period: 1=شهري، 3=ربع سنوي، 6=نصف سنوي
    الفرق في التقريب يُضاف لآخر قسط.
    """
    if installments <= 0:
        return []

    remaining = total_value - down_payment
    if remaining <= Decimal("0"):
        return []

    per_inst = (remaining / installments).quantize(Decimal("0.01"), ROUND_HALF_UP)
    schedule = []

    for i in range(installments):
        due = first_installment_date + relativedelta(months=i * installment_period)
        schedule.append(InstallmentScheduleItem(
            installment_no=i + 1,
            due_date=due,
            amount=per_inst,
        ))

    # تسوية فروق التقريب في القسط الأخير
    diff = remaining - (per_inst * installments)
    if diff != 0 and schedule:
        schedule[-1].amount = (schedule[-1].amount + diff).quantize(
            Decimal("0.01"), ROUND_HALF_UP
        )

    return schedule


def calculate_installment_amount(
    total_value: Decimal,
    down_payment: Decimal,
    installments: int,
) -> Decimal:
    """قيمة كل قسط (للعرض قبل الإنشاء)."""
    if installments <= 0:
        return Decimal("0")
    remaining = max(Decimal("0"), total_value - down_payment)
    return (remaining / installments).quantize(Decimal("0.01"), ROUND_HALF_UP)


def get_first_installment_date(
    start_date: date,
    provided: Optional[date] = None,
) -> date:
    """تاريخ أول قسط — لو مش محدد: شهر بعد بداية العقد."""
    return provided or (start_date + relativedelta(months=1))


# ── Partner split ─────────────────────────────────────────────────────────────

def calculate_partner_share(
    down_payment: Decimal,
    partner_share_pct: Decimal,
) -> tuple[Decimal, Decimal]:
    """
    يُرجع (resort_share, partner_share) من الدفعة الأولى.
    partner_share_pct: Decimal("50") = 50%
    """
    partner = (down_payment * partner_share_pct / 100).quantize(
        Decimal("0.01"), ROUND_HALF_UP
    )
    return down_payment - partner, partner


# ── Visit window calculation ──────────────────────────────────────────────────

def calculate_visit_window(
    week_number: int,
    nights_per_year: int,
    year: int,
    today: Optional[date] = None,
) -> Optional[VisitWindow]:
    """
    يحسب نافذة الزيارة من رقم الأسبوع ISO.
    الأسبوع 28 من 2026 = الإثنين 6 يوليو 2026.
    """
    today = today or date.today()
    if not week_number or not (1 <= week_number <= 52):
        return None
    try:
        visit_start = date.fromisocalendar(year, week_number, 1)
    except (ValueError, AttributeError):
        return None

    nights = max(1, nights_per_year)
    visit_end = visit_start + timedelta(days=nights - 1)

    return VisitWindow(
        year=year,
        week_number=week_number,
        visit_start=visit_start,
        visit_end=visit_end,
        nights=nights,
        days_until=(visit_start - today).days,
    )


def find_next_visit(
    week_number: int,
    nights_per_year: int,
    today: Optional[date] = None,
) -> Optional[VisitWindow]:
    """الزيارة القادمة — هذه السنة أو السنة القادمة."""
    today = today or date.today()
    for year in (today.year, today.year + 1):
        w = calculate_visit_window(week_number, nights_per_year, year, today)
        if w and w.visit_start >= today:
            return w
    return None


def get_upcoming_visits(
    contracts: list[TimeshareContractData],
    within_days: int = 30,
    today: Optional[date] = None,
) -> list[tuple[TimeshareContractData, VisitWindow]]:
    """
    يُرجع العقود التي لها زيارة خلال N يوم — مرتّبة من الأقرب.
    يُستخدم في CS Dashboard.
    """
    today = today or date.today()
    results = []
    for c in contracts:
        if not c.week_number or c.status != "active":
            continue
        w = find_next_visit(c.week_number, c.nights_per_year, today)
        if w and 0 <= w.days_until <= within_days:
            results.append((c, w))
    return sorted(results, key=lambda x: x[1].days_until)


# ── Overdue & penalties ───────────────────────────────────────────────────────

def is_payment_overdue(due_date: date, today: Optional[date] = None) -> bool:
    today = today or date.today()
    return due_date < today


def calculate_lease_penalty(
    amount: Decimal,
    due_date: date,
    today: Optional[date] = None,
) -> Decimal:
    """
    عقوبة تأخر الإيجار التجاري فقط (Lease) — لا تُطبَّق على التايم شير.
    > 30 يوم: 10% / > 7 أيام: 5% / أقل: 0
    """
    today = today or date.today()
    days_late = (today - due_date).days
    for threshold, rate in LEASE_PENALTY_RULES:
        if days_late > threshold:
            return (amount * rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return Decimal("0")


def should_freeze_booking(overdue_amount: Decimal) -> bool:
    """يُجمَّد حق المالك في الحجز إذا كان هناك أقساط متأخرة."""
    return overdue_amount > Decimal("0")


# ── Waiting list ──────────────────────────────────────────────────────────────

def calculate_waitlist_expiry(notified_at: datetime) -> datetime:
    """24 ساعة من وقت الإشعار."""
    return notified_at + timedelta(hours=WAITLIST_EXPIRY_HOURS)


def is_waitlist_expired(entry: WaitlistEntry, now: Optional[datetime] = None) -> bool:
    """هل انتهت مهلة الـ 24 ساعة؟"""
    now = now or datetime.utcnow()
    if entry.status != "notified" or entry.expires_at is None:
        return False
    return now > entry.expires_at


def get_next_in_waitlist(entries: list[WaitlistEntry]) -> Optional[WaitlistEntry]:
    """التالي في القائمة — أول 'waiting' مرتّب بالـ position."""
    waiting = [e for e in entries if e.status == "waiting"]
    return min(waiting, key=lambda e: e.position) if waiting else None


# ── Reminders ─────────────────────────────────────────────────────────────────

def should_send_visit_reminder(
    window: VisitWindow,
    days_before: int = VISIT_REMINDER_DAYS_BEFORE,
) -> bool:
    """هل نرسل تذكير الزيارة اليوم؟ (3 أيام قبل)"""
    return window.days_until == days_before


def should_send_installment_reminder(
    due_date: date,
    today: Optional[date] = None,
    days_before: int = INSTALLMENT_REMINDER_DAYS_BEFORE,
) -> bool:
    """هل نرسل تذكير القسط اليوم؟ (7 أيام قبل)"""
    today = today or date.today()
    return (due_date - today).days == days_before


# ── Lease schedule generation ─────────────────────────────────────────────────

def generate_lease_monthly_schedule(
    base_rent: Decimal,
    increase_rate: float,
    start_date: date,
    end_date: date,
    grace_months: int = 0,
    billing_day: int = 1,
) -> list[dict]:
    """
    جدول الدفعات الشهرية لعقد الإيجار التجاري.
    يدعم الزيادة السنوية المركّبة وفترة السماح.

    يُرجع: [{"due_date": date, "amount": Decimal, "year_n": int}]
    """
    actual_start = start_date + relativedelta(months=grace_months)
    current = actual_start.replace(day=min(billing_day, 28))
    schedule = []

    while current <= end_date:
        year_n = current.year - start_date.year
        rent = (
            base_rent * Decimal(str((1 + increase_rate / 100) ** year_n))
        ).quantize(Decimal("0.01"), ROUND_HALF_UP)
        schedule.append({"due_date": current, "amount": rent, "year_n": year_n})
        current += relativedelta(months=1)

    return schedule


def generate_lease_yearly_schedule(
    base_rent: Decimal,
    increase_rate: float,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """
    جدول الإيجار السنوي (للعرض والتخطيط).
    يُرجع: [{"year": int, "rent_amount": Decimal, "effective_date": date}]
    """
    schedule = []
    for n, year in enumerate(range(start_date.year, end_date.year + 1)):
        rent = (
            base_rent * Decimal(str((1 + increase_rate / 100) ** n))
        ).quantize(Decimal("0.01"), ROUND_HALF_UP)
        schedule.append({
            "year": year,
            "rent_amount": rent,
            "effective_date": date(year, start_date.month, start_date.day),
        })
    return schedule


# ── CS Dashboard aggregation ──────────────────────────────────────────────────

def build_cs_summary(
    summaries: list[ContractSummary],
    this_month_due: Decimal,
) -> dict:
    """
    يبني ملخص لوحة CS الشاملة من قائمة ContractSummary.
    يُستدعى في الـ service بعد جلب البيانات من DB.
    """
    total_value     = sum(s.total_value for s in summaries)
    total_collected = sum(s.collected for s in summaries)
    total_overdue   = sum(s.overdue_amount for s in summaries)
    overdue_clients = [s for s in summaries if s.has_overdue]

    return {
        "active_contracts":        len(summaries),
        "total_value":             total_value,
        "total_collected":         total_collected,
        "collection_rate_pct":     (
            round(float(total_collected / total_value * 100), 1)
            if total_value else 0
        ),
        "total_overdue":           total_overdue,
        "overdue_contracts_count": len(overdue_clients),
        "this_month_due":          this_month_due,
        "overdue_clients":         sorted(
            overdue_clients, key=lambda s: s.overdue_amount, reverse=True
        ),
    }
