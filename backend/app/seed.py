"""
app/seed.py
إعداد البيانات الأولية — idempotent (آمن للتشغيل أكثر من مرة)

تشغيل:
    python -m app.seed
    python -m app.seed --reset   ← يمسح ويعيد (dev فقط)
"""
from __future__ import annotations

import sys
from decimal import Decimal
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.modules.timeshare.models import TimeshareContract

from app.core.database import SessionLocal, Base, get_engine
from app.core.config import settings


def seed_all(db: Session, *, reset: bool = False) -> None:
    """نقطة الدخول الرئيسية لبيانات التطوير/الاختبار فقط.

    This module creates known demo identities and a full synthetic operating
    dataset.  It is not a production bootstrap mechanism.  Production and
    unknown environments must use Alembic plus ``python -m
    app.admin_bootstrap`` so a typo cannot silently install public demo
    credentials or financial sample data.
    """
    normalized_environment = (settings.ENVIRONMENT or "").strip().lower()
    if normalized_environment not in {"development", "test", "testing"}:
        raise RuntimeError(
            "app.seed is restricted to development/test/testing. "
            "Run Alembic migrations, then use `python -m app.admin_bootstrap create` "
            "for a named production super-admin."
        )

    if reset:
        print("⚠️  Dropping all tables...")
        Base.metadata.drop_all(bind=get_engine())

    print("📦 Creating tables...")
    # import all models to register them in Base.metadata
    _import_all_models()
    Base.metadata.create_all(bind=get_engine())

    print("🌱 Seeding data...")
    _seed_branch(db)
    _seed_super_admin(db)
    _seed_demo_accounts(db)
    _seed_social_insurance(db)
    _seed_tax_brackets(db)
    _seed_attendance_policy(db)
    _seed_settings(db)
    _seed_leave_types(db)
    _seed_employees(db)
    _seed_chart_of_accounts(db)
    _seed_payroll(db)
    _seed_room_types(db)
    _seed_rooms(db)
    _seed_bookings(db)
    _seed_timeshare_units(db)
    _seed_timeshare_contracts(db)
    _seed_lease_contracts(db)
    _seed_maintenance(db)
    _seed_menus(db)
    _seed_inventory_recipes(db)
    _seed_dining_tables(db)
    _seed_crm(db)
    _seed_b2b_contracts(db)
    _seed_beach_reservations(db)
    _seed_beach_locations(db)
    _seed_inventory_categories(db)
    _seed_hr_departments(db)
    _seed_rate_plans(db)
    _seed_inventory_products_full(db)
    _seed_restaurant_recipes(db)
    _seed_cafe_recipes(db)
    _seed_suppliers_and_purchase_orders(db)

    db.commit()
    print("✅ Seed complete.")


# ── Food & Recipes (imported from seed_food.py) ───────────────────────────────
from app.seed_food import (  # noqa: E402
    _seed_inventory_products_full,
    _seed_restaurant_recipes,
    _seed_cafe_recipes,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _import_all_models() -> None:
    """يستورد كل الـ models لتسجيلها في Base.metadata."""
    import app.modules.core.models         # noqa: F401
    import app.modules.finance.models      # noqa: F401
    import app.modules.hr.models           # noqa: F401
    import app.modules.dining.models       # noqa: F401
    import app.modules.pms.models          # noqa: F401
    import app.modules.beach.models        # noqa: F401
    import app.modules.maintenance.models  # noqa: F401
    import app.modules.crm.models          # noqa: F401
    import app.modules.hub.models          # noqa: F401
    import app.modules.inventory.models    # noqa: F401
    import app.modules.timeshare.models    # noqa: F401
    import app.modules.leasing.models      # noqa: F401
    import app.modules.analytics.models    # noqa: F401


def _seed_branch(db: Session) -> None:
    from app.modules.core.models import Branch
    if db.query(Branch).first():
        return
    db.add(Branch(
        name="El Kheima Beach Resort",
        name_ar="منتجع الخيمة بيتش",
        code="EKB-001",
        timezone=settings.TIMEZONE,
    ))
    db.flush()
    print("  ✓ Branch created")


def _seed_super_admin(db: Session) -> None:
    """Create the development-only demo super-admin."""
    from app.core.kernel.auth.repository import UserRepository
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash

    repo = UserRepository(User, db)
    if repo.get_by_field("email", "admin@resortos.local"):
        return

    repo.create({
        "email": "admin@resortos.local",
        "password_hash": get_password_hash("Admin@123456"),   # يجب تغييره فور الدخول
        "full_name": "Super Admin",
        "role": "super_admin",
        "is_active": True,
    })
    print("  ✓ Development super admin created")


def _seed_demo_accounts(db: Session) -> None:
    """حساب تجريبي واحد لكل دور (غير super_admin، مُنشأ في _seed_super_admin) —
    عشان أي بيئة تطوير/عرض تقدر تسجّل دخول بأي دور فورًا من غير ما تحتاج
    تنشئ مستخدمين يدويًا من شاشة الإدارة الأول. كلمة السر واحدة لكل الحسابات
    دي (Demo@123456) — غيّرها فورًا لو البيئة دي هتتعرض لحد برّه الفريق."""
    from app.core.kernel.auth.repository import UserRepository
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash

    repo = UserRepository(User, db)
    demo_password_hash = get_password_hash("Demo@123456")

    accounts = [
        ("branch_admin@resortos.local", "مدير إداري تجريبي", "admin"),
        ("accountant@resortos.local",   "محاسب تجريبي",      "accountant"),
        ("hr@resortos.local",           "موارد بشرية تجريبي", "hr_manager"),
        ("manager@resortos.local",      "مدير تجريبي",        "manager"),
        ("supervisor@resortos.local",   "مشرف تجريبي",        "supervisor"),
        ("reception@resortos.local",    "استقبال تجريبي",     "receptionist"),
        ("cashier@resortos.local",      "كاشير تجريبي",       "cashier"),
        ("waiter@resortos.local",       "جرسون تجريبي",       "waiter"),
        ("chef@resortos.local",         "شيف تجريبي",         "chef"),
        ("kitchen@resortos.local",      "مطبخ تجريبي",        "kitchen"),
        ("employee@resortos.local",     "موظف تجريبي",        "employee"),
    ]
    created = 0
    for email, full_name, role in accounts:
        if repo.get_by_field("email", email):
            continue
        repo.create({
            "email": email, "password_hash": demo_password_hash,
            "full_name": full_name, "role": role, "is_active": True,
        })
        created += 1
    if created:
        print(f"  ✓ Development demo accounts seeded ({created} roles)")


def _seed_social_insurance(db: Session) -> None:
    """شرائح التأمينات الاجتماعية 2024 — من DB لا من الكود."""
    try:
        from app.modules.hr.models import SocialInsuranceConfig
    except ImportError:
        return  # HR module لم يُبنَ بعد

    if db.query(SocialInsuranceConfig).first():
        return

    db.add(SocialInsuranceConfig(
        max_insurable_salary=Decimal("14000"),   # الحد الأقصى 2024
        employee_rate=Decimal("0.11"),            # 11%
        employer_rate=Decimal("0.1875"),          # 18.75%
        personal_exemption_annual=Decimal("15000"),
        max_penalty_days_monthly=5,
        effective_from=date(2024, 1, 1),
        is_active=True,
    ))
    db.flush()
    print("  ✓ Social insurance config seeded (2024)")


def _seed_tax_brackets(db: Session) -> None:
    """شرائح ضريبة الدخل 2024."""
    try:
        from app.modules.hr.models import TaxBracketConfig
    except ImportError:
        return

    if db.query(TaxBracketConfig).first():
        return

    brackets = [
        (Decimal("0"),      Decimal("15000"),   Decimal("0.000")),
        (Decimal("15001"),  Decimal("30000"),   Decimal("0.100")),
        (Decimal("30001"),  Decimal("45000"),   Decimal("0.150")),
        (Decimal("45001"),  Decimal("60000"),   Decimal("0.200")),
        (Decimal("60001"),  Decimal("200000"),  Decimal("0.225")),
        (Decimal("200001"), Decimal("400000"),  Decimal("0.250")),
        (Decimal("400001"), None,               Decimal("0.275")),
    ]
    for lower, upper, rate in brackets:
        db.add(TaxBracketConfig(
            lower_bound=lower,
            upper_bound=upper,
            rate=rate,
            effective_from=date(2024, 1, 1),
            is_active=True,
        ))
    db.flush()
    print("  ✓ Tax brackets seeded (2024)")


def _seed_attendance_policy(db: Session) -> None:
    """سياسة حضور افتراضية معقولة للفرع الأساسي — عشان تشغيل الرواتب يحسب
    تأخير/أوفرتايم حقيقي من أول تشغيل بدل ما يفضل صفر لكل الموظفين لحد ما
    حد يدخل يضبط السياسة يدويًا من شاشة الإدارة."""
    try:
        from app.modules.hr.models import AttendancePolicy
        from app.modules.core.models import Branch
    except ImportError:
        return

    branch = db.query(Branch).first()
    if not branch or db.query(AttendancePolicy).filter(AttendancePolicy.branch_id == branch.id).first():
        return

    db.add(AttendancePolicy(
        branch_id=branch.id,
        late_grace_minutes=10,
        early_leave_grace_minutes=10,
        standard_shift_start="09:00",
        standard_shift_end="17:00",
        overtime_rate_multiplier=Decimal("1.50"),
        late_penalty_rate_multiplier=Decimal("1.00"),
        is_active=True,
    ))
    db.flush()
    print("  ✓ Attendance policy seeded (default: 10min grace, 09:00-17:00, 1.5x OT)")


def _seed_leave_types(db: Session) -> None:
    """8 أنواع إجازات قانون العمل المصري."""
    try:
        from app.modules.hr.models import LeaveType
        from app.modules.core.models import Branch
    except ImportError:
        return

    branch = db.query(Branch).first()
    if not branch or db.query(LeaveType).filter(LeaveType.branch_id == branch.id).first():
        return

    leave_types = [
        {"name": "إجازة سنوية",         "name_ar": "إجازة سنوية",          "is_paid": True,  "max_days_per_year": 21,  "requires_approval": True},
        {"name": "إجازة مرضية",          "name_ar": "إجازة مرضية",           "is_paid": True,  "max_days_per_year": 90,  "requires_approval": True},
        {"name": "إجازة أمومة",          "name_ar": "إجازة أمومة",           "is_paid": True,  "max_days_per_year": 90,  "requires_approval": True},
        {"name": "إجازة بدون أجر",       "name_ar": "إجازة بدون أجر",        "is_paid": False, "max_days_per_year": 30,  "requires_approval": True},
        {"name": "إجازة عارضة",          "name_ar": "إجازة عارضة",           "is_paid": True,  "max_days_per_year": 6,   "requires_approval": False},
        {"name": "إجازة رسمية",          "name_ar": "إجازة رسمية",           "is_paid": True,  "max_days_per_year": 14,  "requires_approval": False},
        {"name": "إجازة حج",             "name_ar": "إجازة حج",              "is_paid": True,  "max_days_per_year": 30,  "requires_approval": True},
        {"name": "إجازة وفاة",           "name_ar": "إجازة وفاة",            "is_paid": True,  "max_days_per_year": 7,   "requires_approval": False},
    ]
    for lt in leave_types:
        db.add(LeaveType(branch_id=branch.id, **lt))
    db.flush()
    print(f"  ✓ Leave types seeded ({len(leave_types)} types)")


def _seed_employees(db: Session) -> None:
    """⚠️ جدول employees كان فاضيًا تمامًا (0 صف) رغم إن كل منطق الرواتب/
    الحضور/الإجازات مبني وشغال بالكامل — يعني موديول الموارد البشرية بالكامل
    كان بيفتح فاضي أول مرة: مفيش موظف واحد للـ HR manager يشوفه، وأخطر من كده
    حسابات /hr/me/* التجريبية (employee@resortos.local, manager@resortos.local,
    hr@resortos.local) مكنش ليها أي Employee مرتبط (Employee.user_id) — يعني
    تسجيل حضور/طلب إجازة/قسيمة راتب self-service كان بيرجّع 404 "لا يوجد ملف
    موظف مرتبط بحسابك" فورًا لأي حد يجرّب الحساب التجريبي، من أول يوم.
    اتكشف أثناء اختبار حي لمسار HR الكامل (نفس فئة باج rooms/dining_tables
    الفاضية اللي اتصلحت قبل كده). ازرع فريق واقعي (13 موظف، أقسام مختلفة) +
    بدلات/أنواع جزاءات/رصيد إجازات/سجل حضور/طلب إجازة معلّق عشان الشاشة تفتح
    بحالة واقعية مش فاضية.

    تحديث 2026-07-06 (جولة اختبار حي عبر كل الـ 11 حساب تجريبي): من الـ 8
    موظفين الأصليين كان 3 بس مربوطين بحساب دخول (employee@/manager@/hr@) —
    يعني 7 من 8 أدوار تجريبية تانية (accountant/supervisor/reception/cashier/
    waiter/chef/kitchen) كانت بتاخد 404 فورية على كل شاشات HR self-service
    رغم إن الحساب نفسه شغال 100%. ضفنا 5 موظفين جداد (EMP-009..013) لتغطية
    الأدوار الناقصة، ووصّلنا EMP-004/EMP-005 الموجودين أصلاً (نفس الوظيفة
    الحقيقية) بحساباتهم (reception@/chef@) بدل ما نسيبهم من غير حساب."""
    from datetime import timedelta
    from app.core.kernel.auth.repository import UserRepository
    from app.core.kernel.models.user import User
    from app.modules.core.models import Branch
    from app.modules.hr.models import (
        AttendanceRecord, Employee, EmployeeAllowance, LeaveBalance,
        LeaveRequest, LeaveType, PenaltyType,
    )

    branch = db.query(Branch).first()
    if not branch or db.query(Employee).filter(Employee.branch_id == branch.id).first():
        return

    repo = UserRepository(User, db)

    def _user_id(email: str) -> int | None:
        u = repo.get_by_field("email", email)
        return u.id if u else None

    today = date.today()
    # (employee_code, full_name, position, department, basic_salary, hire_date, birth_date, linked_user_email)
    roster = [
        ("EMP-001", "أحمد فتحي السيد",    "جرسون",              "المطعم",     Decimal("3800.00"), today - timedelta(days=730),  date(1996, 3, 12), "employee@resortos.local"),
        ("EMP-002", "منى صلاح الدين",     "مديرة عمليات",        "الإدارة",    Decimal("14000.00"), today - timedelta(days=1460), date(1988, 7, 21), "manager@resortos.local"),
        ("EMP-003", "كريم عبد الوهاب",    "مسؤول موارد بشرية",   "الموارد البشرية", Decimal("9500.00"), today - timedelta(days=1095), date(1991, 11, 3), "hr@resortos.local"),
        ("EMP-004", "ياسمين ماهر",        "موظفة استقبال",       "الاستقبال",  Decimal("5200.00"), today - timedelta(days=400),  date(1998, 1, 30), "reception@resortos.local"),
        ("EMP-005", "سامح جلال",          "شيف",                "المطبخ",     Decimal("11000.00"), today - timedelta(days=2200), date(1985, 5, 9), "chef@resortos.local"),
        ("EMP-006", "هدى عزت",            "عاملة تدبير منزلي",   "التدبير المنزلي", Decimal("3400.00"), today - timedelta(days=180), date(2000, 9, 17), None),
        ("EMP-007", "مينا رفعت",          "منقذ شاطئ",           "الشاطئ",     Decimal("4200.00"), today - timedelta(days=545), date(1994, 2, 25), None),
        ("EMP-008", "عماد شحاتة",         "فني صيانة",           "الصيانة",    Decimal("4800.00"), today - timedelta(days=900), date(1990, 4, 18), None),
        ("EMP-009", "نيفين طارق",         "محاسبة",             "الحسابات",   Decimal("8500.00"), today - timedelta(days=620), date(1993, 6, 14), "accountant@resortos.local"),
        ("EMP-010", "عمرو حلمي",          "مشرف عمليات",         "الإدارة",    Decimal("7200.00"), today - timedelta(days=860), date(1990, 10, 2), "supervisor@resortos.local"),
        ("EMP-011", "دينا عادل",          "كاشير",               "المطعم",     Decimal("4100.00"), today - timedelta(days=310), date(1997, 8, 19), "cashier@resortos.local"),
        ("EMP-012", "خالد سمير",          "جرسون",               "المطعم",     Decimal("3900.00"), today - timedelta(days=200), date(1999, 4, 5), "waiter@resortos.local"),
        ("EMP-013", "أميرة فوزي",         "مساعدة شيف",          "المطبخ",     Decimal("4400.00"), today - timedelta(days=150), date(1998, 12, 22), "kitchen@resortos.local"),
    ]

    employees: dict[str, Employee] = {}
    for code, name, position, dept, salary, hire, birth, linked_email in roster:
        emp = Employee(
            branch_id=branch.id, employee_code=code, full_name=name,
            position=position, department=dept, basic_salary=salary,
            hire_date=hire, birth_date=birth, status="active",
            user_id=_user_id(linked_email) if linked_email else None,
        )
        db.add(emp)
        db.flush()
        employees[code] = emp

    # ── رصيد إجازات السنة الحالية — 21 يوم سنوي قانوني لكل موظف ──────────
    for emp in employees.values():
        db.add(LeaveBalance(
            employee_id=emp.id, year=today.year,
            annual_entitled=21, annual_taken=0, sick_taken=0,
        ))

    # ── بدلات حقيقية (EmployeeAllowance) — عشان endpoint النهارده مش فاضي ─
    db.add(EmployeeAllowance(
        employee_id=employees["EMP-001"].id, name="بدل انتقال",
        amount=Decimal("300.00"), is_taxable=True, is_pensionable=False,
    ))
    db.add(EmployeeAllowance(
        employee_id=employees["EMP-002"].id, name="بدل سكن",
        amount=Decimal("2000.00"), is_taxable=True, is_pensionable=True,
    ))
    db.add(EmployeeAllowance(
        employee_id=employees["EMP-005"].id, name="بدل وجبات",
        amount=Decimal("500.00"), is_taxable=False, is_pensionable=False,
    ))

    # ── أنواع جزاءات شائعة (PenaltyType) ─────────────────────────────────
    db.add(PenaltyType(branch_id=branch.id, name="Late arrival", name_ar="تأخر عن الحضور", penalty_days=1))
    db.add(PenaltyType(branch_id=branch.id, name="Unauthorized absence", name_ar="غياب بدون إذن", penalty_days=3))

    # ── سجل حضور آخر 5 أيام لكل موظف مرتبط بحساب دخول تجريبي (مش بس اتنين) ─
    # عشان تبويب الحضور في /hr/me/attendance يبقى واقعي لأي دور تجرّبه، مش
    # بس اللي كانوا مربوطين وقت أول seed.
    for emp in employees.values():
        if emp.user_id is None:
            continue
        for days_ago in range(1, 6):
            rec_date = today - timedelta(days=days_ago)
            check_in = datetime.combine(rec_date, datetime.min.time()) + timedelta(hours=9)
            check_out = check_in + timedelta(hours=8)
            db.add(AttendanceRecord(
                employee_id=emp.id, branch_id=branch.id, record_date=rec_date,
                check_in=check_in, check_out=check_out, status="present",
            ))

    # ── طلب إجازة معلّق واحد — عشان قائمة اعتماد الإجازات متبقاش فاضية ────
    annual_leave = db.query(LeaveType).filter(
        LeaveType.branch_id == branch.id, LeaveType.name == "إجازة سنوية",
    ).first()
    if annual_leave:
        start = today + timedelta(days=10)
        end = today + timedelta(days=12)
        db.add(LeaveRequest(
            employee_id=employees["EMP-001"].id, branch_id=branch.id,
            leave_type_id=annual_leave.id, start_date=start, end_date=end,
            days_requested=(end - start).days + 1, reason="سفر عائلي",
            status="pending",
        ))

    db.flush()
    linked = sum(1 for emp in employees.values() if emp.user_id is not None)
    print(f"  ✓ Employees seeded ({len(employees)}, linked to {linked} demo login accounts)")


def _seed_payroll(db: Session) -> None:
    """⚠️ مفيش أي PayrollRun كان متزروع خالص — يعني `GET /hr/me/payslips`
    (self-service) و`GET /hr/payroll/runs` (شاشة HR الإدارية) كانوا بيفتحوا
    فاضيين تمامًا لكل حساب، حتى بعد ما _seed_employees اتحدّثت تربط كل
    الأدوار بموظف حقيقي. اتكشف في نفس جولة الاختبار الحي 2026-07-06.

    الحل: شغّل كشف رواتب حقيقي فعليًا (`run_payroll_for_branch` — نفس محرك
    الرواتب المصري الحقيقي: تأمينات + ضرائب + جزاءات، مش أرقام موضوعة
    يدويًا) لشهر الشهر الماضي، واعتمده (`approve_payroll_run`) عشان يبقى
    فيه قسيمة راتب حقيقية معتمدة يشوفها أي موظف مرتبط بحساب دخول."""
    from dateutil.relativedelta import relativedelta

    from app.core.kernel.auth.repository import UserRepository
    from app.core.kernel.models.user import User
    from app.modules.core.models import Branch
    from app.modules.hr.models import PayrollRun
    from app.modules.hr.services import approve_payroll_run, run_payroll_for_branch
    from app.resort_os.timezone_utils import business_today

    branch = db.query(Branch).first()
    if not branch or db.query(PayrollRun).filter(PayrollRun.branch_id == branch.id).first():
        return

    approver = UserRepository(User, db).get_by_field("email", "admin@resortos.local")
    if not approver:
        return  # لسه مفيش super admin — من المفروض مستحيل بعد _seed_super_admin

    period = business_today(settings.TIMEZONE).replace(day=1) - relativedelta(months=1)
    try:
        run = run_payroll_for_branch(db, branch.id, period.year, period.month)
        approve_payroll_run(db, run.id, approved_by=approver.id)
    except ValueError as exc:
        print(f"  ⚠ Payroll seed skipped: {exc}")
        return
    print(f"  ✓ Payroll run seeded ({period.year}-{period.month:02d}, {len(run.lines)} payslip lines, approved)")


def _seed_chart_of_accounts(db: Session) -> None:
    """حسابات الرواتب والتأمينات الضرورية للقيود.

    Batch 3 (تفعيل تسلسل الحسابات — Account.parent_id): 4 حسابات أب (رؤوس
    مجموعات) بمستوى واحد بس — الأصول/الخصوم/الإيرادات/المصروفات — كل حساب
    من الـ 22 المزروعين تحته بيتبع أبوه حسب account_type. مفيش مستوى تاني
    (زي "أصول متداولة" تحت "الأصول") — الشجرة المزروعة (22 حساب) مش
    مبررة لتسلسل أعمق من ده (توصية البحث الصريحة بعدم بناء هرمية عميقة).
    equity مالهاش حساب مزروع لحد دلوقتي فمفيهوش حساب أب equity."""
    try:
        from app.modules.finance.models import Account
        from app.modules.core.models import Branch
    except ImportError:
        return

    branch = db.query(Branch).first()
    if not branch:
        return

    PARENT_HEADERS = {
        "asset":     {"code": "1000", "name": "الأصول",      "account_type": "asset"},
        "liability": {"code": "2000", "name": "الخصوم",      "account_type": "liability"},
        "revenue":   {"code": "4000", "name": "الإيرادات",   "account_type": "revenue"},
        "expense":   {"code": "5000", "name": "المصروفات",   "account_type": "expense"},
    }

    accounts = [
        {"code": "5100", "name": "مصروف رواتب وأجور",           "account_type": "expense"},
        {"code": "5110", "name": "مصروف تأمينات اجتماعية",       "account_type": "expense"},
        {"code": "2100", "name": "ضريبة دخل مستحقة",             "account_type": "liability"},
        {"code": "2110", "name": "تأمينات اجتماعية مستحقة",      "account_type": "liability"},
        {"code": "2120", "name": "رواتب مستحقة الدفع",           "account_type": "liability"},
        {"code": "4100", "name": "إيرادات الغرف",                 "account_type": "revenue"},
        {"code": "4200", "name": "إيرادات المطعم",               "account_type": "revenue"},
        {"code": "4300", "name": "إيرادات الشاطئ",               "account_type": "revenue"},
        {"code": "4400", "name": "إيرادات الكافيه",              "account_type": "revenue"},
        {"code": "1100", "name": "الصندوق / النقدية",            "account_type": "asset"},
        {"code": "1150", "name": "ذمم الفوليو (نزلاء)",          "account_type": "asset"},
        {"code": "1200", "name": "مخزون البضاعة",               "account_type": "asset"},
        {"code": "5200", "name": "تكلفة البضاعة المباعة (COGS)", "account_type": "expense"},
        {"code": "2300", "name": "إيرادات مؤجَّلة (تايم شير) — قديم، لا يُستخدم في قيود جديدة", "account_type": "liability"},
        {"code": "4600", "name": "إيرادات عقود التايم شير",      "account_type": "revenue"},
        {"code": "1260", "name": "ذمم مستأجرين (إيجارات)",      "account_type": "asset"},
        {"code": "2150", "name": "تأمينات مستأجرين",            "account_type": "liability"},
        {"code": "4500", "name": "إيرادات إيجارات تجارية",      "account_type": "revenue"},
        {"code": "5300", "name": "مصروفات مرافق (كهرباء/مياه/غاز)", "account_type": "expense"},
        {"code": "1110", "name": "حساب بنكي",                     "account_type": "asset"},
        {"code": "5500", "name": "مصروف إهلاك الأصول الثابتة",     "account_type": "expense"},
        {"code": "1590", "name": "مجمّع إهلاك الأصول الثابتة",     "account_type": "asset"},
        {"code": "2200", "name": "موردون — ذمم دائنة",            "account_type": "liability"},
    ]

    existing = {
        r.code: r for r in db.query(Account).filter(Account.branch_id == branch.id).all()
    }

    # رؤوس المجموعات أولاً (idempotent — بيتزرعوا مرة واحدة بس)
    header_by_type: dict[str, Account] = {}
    for acc_type, header in PARENT_HEADERS.items():
        existing_header = existing.get(header["code"])
        if not existing_header:
            existing_header = Account(branch_id=branch.id, is_active=True, **header)
            db.add(existing_header)
            db.flush()
            existing[header["code"]] = existing_header
        header_by_type[acc_type] = existing_header

    added = 0
    for acc in accounts:
        row = existing.get(acc["code"])
        if not row:
            row = Account(branch_id=branch.id, is_active=True, parent_id=header_by_type[acc["account_type"]].id, **acc)
            db.add(row)
            added += 1
        elif row.parent_id is None:
            # حساب موجود من قبل (زُرع قبل تفعيل التسلسل) — نلحقه بأبوه
            # بأثر رجعي، idempotent (بيتخطى لو parent_id متحدد بالفعل).
            row.parent_id = header_by_type[acc["account_type"]].id
    if added:
        db.flush()
        print(f"  ✓ Chart of accounts seeded ({added} accounts)")


def _seed_room_types(db: Session) -> None:
    """كتالوج غرف حقيقي — منقول من elkheima-beach-resort (النسخة القديمة من
    نفس المنتجع، /home/wego/projects/elkheima-beach-resort/backend/app/seed_data.py،
    كانت "production ready" فعليًا) بدل بيانات اختبار وهمية. الأسعار جنيه مصري
    (لليلة الواحدة)، والـ occupancy اتحدد حسب فئة كل غرفة."""
    try:
        from app.modules.pms.models import RoomType
        from app.modules.core.models import Branch
    except ImportError:
        return

    branch = db.query(Branch).first()
    if not branch or db.query(RoomType).filter(RoomType.branch_id == branch.id).first():
        return

    room_types = [
        {"name": "Standard Single Room", "name_ar": "غرفة مفردة عادية",
         "base_rate": Decimal("800.00"), "max_occupancy": 1,
         "amenities": '["garden_view", "standard"]'},
        {"name": "Standard Double Room", "name_ar": "غرفة مزدوجة عادية",
         "base_rate": Decimal("1200.00"), "max_occupancy": 2,
         "amenities": '["modern_amenities", "standard"]'},
        {"name": "Deluxe Sea View Room", "name_ar": "غرفة ديلوكس بإطلالة بحرية",
         "base_rate": Decimal("1800.00"), "max_occupancy": 2,
         "amenities": '["sea_view", "balcony", "deluxe"]'},
        {"name": "Family Suite", "name_ar": "جناح عائلي",
         "base_rate": Decimal("2500.00"), "max_occupancy": 4,
         "amenities": '["living_area", "family", "suite"]'},
        {"name": "Presidential Suite", "name_ar": "الجناح الرئاسي",
         "base_rate": Decimal("4000.00"), "max_occupancy": 4,
         "amenities": '["private_terrace", "jacuzzi", "luxury"]'},
    ]
    for rt in room_types:
        db.add(RoomType(branch_id=branch.id, **rt))
    db.flush()
    print(f"  ✓ Room types seeded ({len(room_types)} types)")


def _seed_rooms(db: Session) -> None:
    """⚠️ ترقيم منطقي افتراضي مش أرقام غرف حقيقية موثّقة — لم يوجد أي مصدر
    بيانات فعلي لعدد/ترقيم غرف المنتجع الحقيقي وقت كتابة هذا الكود (2026-07-04).
    قبل هذا التعديل كان جدول rooms فاضي تمامًا (0 صف) رغم وجود 5 room_types
    حقيقية — يعني حتى حجوزات الفندق العادية (مش بس التايم شير) كانت مستحيلة
    تتربط بغرفة فعلية، وده كان بيمنع أي منع تعارض حجز حقيقي (double-booking)
    على مستوى الغرفة. قرار صاحب المنتجع: ازرع ترقيم منطقي متسلسل دلوقتي
    (مش نأجّله) — 101-110 مفردة، 201-220 مزدوجة، 301-315 ديلوكس بحري،
    401-405 جناح عائلي، 501-502 جناح رئاسي (54 غرفة إجمالاً)."""
    from app.modules.pms.models import Room, RoomType
    from app.modules.core.models import Branch

    branch = db.query(Branch).first()
    if not branch or db.query(Room).filter(Room.branch_id == branch.id).first():
        return

    room_types = {
        rt.name: rt for rt in db.query(RoomType).filter(RoomType.branch_id == branch.id).all()
    }
    # (اسم room_type، بادئة رقم الغرفة، رقم الطابق، عدد الغرف)
    plan = [
        ("Standard Single Room",   101, 1, 10),
        ("Standard Double Room",   201, 2, 20),
        ("Deluxe Sea View Room",   301, 3, 15),
        ("Family Suite",           401, 4, 5),
        ("Presidential Suite",     501, 5, 2),
    ]

    total = 0
    for rt_name, start_number, floor, count in plan:
        rt = room_types.get(rt_name)
        if not rt:
            continue
        for i in range(count):
            db.add(Room(
                branch_id=branch.id, room_type_id=rt.id,
                name=str(start_number + i), floor=floor,
            ))
            total += 1
    db.flush()
    print(f"  ✓ Rooms seeded ({total} rooms — logical default numbering, not verified real numbers)")


def _seed_bookings(db: Session) -> None:
    """⚠️ جدول bookings كان فاضيًا تمامًا (0 صف) رغم إن 52 غرفة متزروعة —
    يعني شاشة الاستقبال الأساسية اليومية (`/ops/bookings`) كانت هتفتح فاضية
    100% لأي حد يجرّب حساب reception@/supervisor@ التجريبي، من غير أي حجز
    واحد يسجّل عليه دخول أو يشوف تفاصيله. اتكشف في جولة اختبار حي كاستقبال
    2026-07-06 (نفس فئة باج rooms/dining_tables الفاضية الموثّقة قبل كده).

    3 حجوزات توضيحية عبر 3 حالات واقعية مختلفة — عشان استقبال يقدر يجرّب
    فعليًا: (1) confirmed قادم النهاردة → زر "تسجيل دخول" حقيقي، (2)
    checked_in فعلاً (نزيل مقيم دلوقتي) → "الدفع على حساب الغرفة"/فوليو
    شغال، (3) checked_out (تاريخ مغادرة). الحجزين الأولين بيتعملوا عن طريق
    `services.create_booking`/`checkin_booking` الحقيقيين (منهمش بيرحّلوا أي
    قيد محاسبي) — لكن الحجز التالت اتعمل مباشرة بالـ ORM (مش
    `services.checkout_booking`) عشان منولّدش قيد إيراد حقيقي في الدفاتر
    لضيف مُلفَّق، نفس القرار المتبع بالظبط في _seed_timeshare_contracts/
    _seed_lease_contracts."""
    from datetime import timedelta

    from app.modules.core.models import Branch
    from app.modules.pms.models import Booking, BookingRoom, Room
    from app.modules.pms.schemas import BookingCreate
    from app.modules.pms.services import checkin_booking, create_booking

    branch = db.query(Branch).first()
    if not branch or db.query(Booking).filter(Booking.branch_id == branch.id).first():
        return

    rooms = db.query(Room).filter(Room.branch_id == branch.id).order_by(Room.id).all()
    if len(rooms) < 3:
        return
    today = date.today()

    # (1) قادم النهاردة — لسه confirmed، جاهز لاختبار "تسجيل دخول" حي.
    create_booking(db, BookingCreate(
        branch_id=branch.id, guest_name="محمود عادل ربيع", guest_phone="01012345678",
        guest_email="mahmoud.adel@example.com", check_in=today, check_out=today + timedelta(days=3),
        adults=2, children=0, source="direct", room_ids=[rooms[0].id],
    ))

    # (2) نزيل مقيم فعلاً دلوقتي (checked_in) — لاختبار الدفع على حساب الغرفة.
    b2 = create_booking(db, BookingCreate(
        branch_id=branch.id, guest_name="ريم حسام الدين", guest_phone="01123456789",
        guest_email="reem.hossam@example.com", check_in=today - timedelta(days=1),
        check_out=today + timedelta(days=2), adults=1, children=1, source="online",
        room_ids=[rooms[1].id],
    ))
    checkin_booking(db, b2.id)

    # (3) غادر بالفعل (checked_out) — ORM مباشرة (مش services.checkout_booking)
    # عشان منسجّلش قيد إيراد حقيقي في الدفاتر لضيف مُلفَّق.
    nights3 = 2
    b3 = Booking(
        branch_id=branch.id, booking_number=f"BKG-SEED-{today.strftime('%Y%m%d')}-0003",
        guest_name="طارق منير فهمي", guest_phone="01234567890", guest_email=None,
        check_in=today - timedelta(days=4), check_out=today - timedelta(days=2),
        adults=2, children=0, status="checked_out", source="phone",
        total_rate=rooms[2].room_type.base_rate * nights3 if rooms[2].room_type else Decimal("0"),
    )
    db.add(b3)
    db.flush()
    db.add(BookingRoom(
        booking_id=b3.id, room_id=rooms[2].id,
        daily_rate=(b3.total_rate / nights3) if nights3 else Decimal("0"),
        nights=nights3, total=b3.total_rate,
    ))
    db.flush()
    print("  ✓ Bookings seeded (3 illustrative: confirmed / checked_in / checked_out)")


def _seed_timeshare_units(db: Session) -> None:
    """⚠️ نفس ملاحظة _seed_rooms — ترقيم منطقي افتراضي، مش أرقام وحدات
    حقيقية موثّقة. وحدات التايم شير مبنى/مسكن منفصل فعليًا عن غرف الفندق
    (قرار صاحب المنتجع 2026-07-04) — لذلك جدول منفصل (timeshare_units)
    بترقيم مستقل (A-xxx بدل أرقام الغرف العادية)."""
    from app.modules.timeshare.models import TimeshareUnit
    from app.modules.core.models import Branch

    branch = db.query(Branch).first()
    if not branch or db.query(TimeshareUnit).filter(TimeshareUnit.branch_id == branch.id).first():
        return

    # (unit_type، بادئة الحرف، عدد الوحدات)
    plan = [("2R", "A", 10), ("4R", "B", 8), ("6R", "C", 4)]

    total = 0
    for unit_type, prefix, count in plan:
        for i in range(1, count + 1):
            db.add(TimeshareUnit(
                branch_id=branch.id, unit_number=f"{prefix}-{100 + i}", unit_type=unit_type,
            ))
            total += 1
    db.flush()
    print(f"  ✓ Timeshare units seeded ({total} units — logical default numbering, not verified real numbers)")


def _seed_timeshare_contracts(db: Session) -> None:
    """⚠️ عملاء وعقود تايم شير توضيحية (illustrative sample data) — مش سجلات
    عملاء حقيقية للمنتجع. الغرض: تشغيل لوحات التايم شير (cs-summary / sales-
    dashboard / calendar / upcoming-visits / stats / installments) ببيانات
    متنوّعة واقعية بدل قواعد فاضية. الأسماء مصرية معقولة والأرقام بصيغة
    الموبايل المصري — لكنها مُلفَّقة للعرض فقط.

    Idempotent: لو فيه أي عقد بادئته 'TS-SEED-' للفرع → يتجاهَل (check-then-create)."""
    from datetime import datetime, timedelta
    from app.modules.timeshare.models import TimeshareContract, TimeshareInstallment, TimeshareUnit
    from app.modules.core.models import Branch
    from app.resort_os.timeshare_engine import generate_installment_schedule

    branch = db.query(Branch).first()
    if not branch:
        return
    if db.query(TimeshareContract).filter(
        TimeshareContract.branch_id == branch.id,
        TimeshareContract.contract_number.like("TS-SEED-%"),
    ).first():
        return

    units: dict[str, list] = {}
    for u in db.query(TimeshareUnit).filter(TimeshareUnit.branch_id == branch.id).all():
        units.setdefault(u.unit_type, []).append(u)

    today = date.today()
    anchor = date(today.year, 1, 1)   # بداية السنة كمرساة ثابتة للأقساط

    # كل عنصر: بيانات العقد + خطة السداد (paid / overdue / partial / بقية pending)
    specs = [
        # (name, phone, email, nationality, room, week, season, total, down, insts,
        #  period, status, partner_company, partner_pct, batch, rci, assign_unit,
        #  paid, overdue, partial)
        ("أحمد جمال منصور", "01001234567", "ahmed.g@example.com", "مصري", "2R", 12, "high",
         "180000", "40000", 12, 1, "active", "شركة النخبة العقارية", "25", 1, False, True, 12, 0, 0),
        ("منى عبد الرحمن", "01112345678", "mona.a@example.com", "مصري", "2R", 28, "high",
         "180000", "36000", 12, 1, "active", "شركة النخبة العقارية", "25", 1, True, True, 5, 2, 0),
        ("خالد سمير فؤاد", "01223456789", None, "مصري", "4R", 33, "both",
         "320000", "80000", 10, 1, "active", "دار الاستثمار السياحي", "30", 2, False, True, 3, 0, 1),
        ("سلمى إبراهيم حسن", "01098765432", "salma.i@example.com", "مصري", "4R", None, "high",
         "300000", "60000", 12, 1, "active", "دار الاستثمار السياحي", "30", 2, False, False, 0, 0, 0),
        ("عمر ياسر الشناوي", "01155667788", None, "مصري", "2R", 40, "low",
         "160000", "20000", 12, 1, "suspended", "شركة النخبة العقارية", "25", 1, True, True, 2, 3, 0),
        ("هالة مصطفى كامل", "01266778899", "hala.m@example.com", "مصري", "6R", 45, "high",
         "540000", "120000", 12, 1, "active", "المجموعة الدولية للمنتجعات", "20", 3, True, True, 8, 0, 0),
        ("طارق نبيل عوض", "01033445566", None, "أردني", "6R", 20, "both",
         "500000", "500000", 1, 1, "active", "المجموعة الدولية للمنتجعات", "20", 3, False, True, 0, 0, 0),
        ("داليا فتحي زكي", "01144556677", "dalia.f@example.com", "مصري", "4R", 8, "high",
         "310000", "62000", 10, 1, "cancelled", "دار الاستثمار السياحي", "30", 2, False, False, 1, 0, 0),
    ]

    created = 0
    contracts_by_seq: dict[int, TimeshareContract] = {}
    for i, s in enumerate(specs, start=1):
        (name, phone, email, nat, room, week, season, total, down, insts, period,
         status, partner, pct, batch, rci, assign_unit, paid_n, overdue_n, partial_n) = s

        total_d, down_d = Decimal(total), Decimal(down)
        unit_id = None
        if assign_unit and units.get(room):
            # وحدة مخصَّصة دائمًا للعقد (نفس الوحدة كل سنة) — لو متاح لنوع الغرفة
            unit_id = units[room][(i - 1) % len(units[room])].id

        contract = TimeshareContract(
            branch_id=branch.id,
            contract_number=f"TS-SEED-{i:04d}",
            customer_name=name, customer_phone=phone, customer_email=email,
            nationality=nat, room_type=room, unit_id=unit_id,
            week_number=week, nights_per_year=7, season=season,
            total_value=total_d, down_payment=down_d,
            installments=insts, installment_period=period,
            first_installment_date=anchor + timedelta(days=30),
            start_date=anchor, partner_company=partner,
            partner_share_pct=Decimal(pct), batch_number=batch, rci_included=rci,
            maintenance_fee=Decimal("3500"), status=status,
            cancelled_at=(today if status == "cancelled" else None),
            cancel_amount=(Decimal("15000") if status == "cancelled" else Decimal("0")),
            signed_by=None,
        )
        db.add(contract)
        db.flush()

        schedule = generate_installment_schedule(
            total_value=total_d, down_payment=down_d,
            installments=insts, installment_period=period,
            first_installment_date=contract.first_installment_date,
        )
        for idx, item in enumerate(schedule):
            inst = TimeshareInstallment(
                contract_id=contract.id, installment_no=item.installment_no,
                due_date=item.due_date, amount=item.amount,
            )
            # توزيع حالات واقعية: مدفوع كامل → متأخر → جزئي → بقية معلّقة
            if idx < paid_n:
                inst.status = "paid"
                inst.paid_amount = item.amount
                inst.paid_at = datetime.combine(item.due_date, datetime.min.time())
                inst.payment_method = "cash"
            elif idx < paid_n + overdue_n:
                inst.status = "overdue"
            elif idx < paid_n + overdue_n + partial_n:
                inst.status = "partial"
                inst.paid_amount = (item.amount / 2).quantize(Decimal("0.01"))
                inst.payment_method = "bank_transfer"
            db.add(inst)

        # عقد موقوف بسبب متأخرات → حجزه مجمّد (نفس منطق الخدمة الحقيقي)
        if status == "suspended" and overdue_n > 0:
            contract.booking_frozen = True
        created += 1
        contracts_by_seq[i] = contract

    db.flush()
    print(f"  ✓ Timeshare contracts seeded ({created} illustrative sample customers — not real records)")

    # ── زيارات فعلية (TimeshareVisit) — 3 عقود توضيحية (نفس تقليد "3 أمثلة
    # مش مثال واحد" المتّبع في بقية الـ seed) ────────────────────────────
    # ⚠️ جدول timeshare_visits كان فاضيًا تمامًا حتى لو عندك عقود/عملاء —
    # يعني تبويب "الزيارات" في بروفايل أي عميل كان دايمًا بيرجّع "لا توجد
    # زيارات مسجّلة"، وأخطر من كده: زر "📨 استبيان الرضا" الجديد
    # (TimeshareView.vue) شرطه `v.status === 'completed'` — يعني الزر ده
    # كان عمليًا مستحيل يظهر لأي حد يجرّب الشاشة حتى بمدير عنده الصلاحية،
    # من غير زيارة واحدة completed حقيقية في الداتابيز. اتكشف في جولة
    # الاختبار الحي 2026-07-06 وقت تجربة الزر الجديد فعليًا كمدير.
    _seed_timeshare_visits(db, branch.id, contracts_by_seq, today)


def _seed_timeshare_visits(
    db: Session, branch_id: int, contracts_by_seq: dict[int, "TimeshareContract"], today: date,
) -> None:
    """3 زيارات توضيحية عبر 3 عقود مختلفة: زيارة *منتهية* (completed) —
    عشان زر "استبيان الرضا" يبقى له حالة حقيقية يظهر فيها فعليًا — + زيارة
    نشطة (active، الضيف في المنتجع دلوقتي) + زيارة مجدولة (scheduled،
    قادمة). Idempotent عن طريق فحص وجود أي زيارة لأول عقد seed أصلاً."""
    from datetime import timedelta

    from app.modules.timeshare.models import TimeshareVisit

    first_contract = contracts_by_seq.get(1)
    if not first_contract:
        return
    if db.query(TimeshareVisit).filter(TimeshareVisit.contract_id == first_contract.id).first():
        return

    plans = [
        (1, "completed", today - timedelta(days=45), 7),
        (2, "active",    today - timedelta(days=2),  7),
        (3, "scheduled", today + timedelta(days=20),  7),
    ]
    created = 0
    for seq, status, check_in, nights in plans:
        contract = contracts_by_seq.get(seq)
        if not contract:
            continue
        db.add(TimeshareVisit(
            branch_id=branch_id, contract_id=contract.id, unit_id=contract.unit_id,
            check_in=check_in, check_out=check_in + timedelta(days=nights),
            nights=nights, status=status,
        ))
        created += 1
    db.flush()
    print(f"  ✓ Timeshare visits seeded ({created} illustrative visits — incl. 1 completed, for survey button testing)")


def _seed_lease_contracts(db: Session) -> None:
    """⚠️ جدول lease_contracts كان فاضيًا تمامًا (0 صف) رغم إن موديول الإيجارات
    عنده باك إند كامل (9 endpoints: عقود، جدول دفعات، غرامات تأخير، سجل كاش
    مستأجرين، إيصال PDF) وفرونت إند كامل (LeasingView.vue) — يعني الشاشة كانت
    هتفتح فاضية 100% أول مرة، بالظبط نفس فئة الباج الموثّقة في rooms/dining_tables
    الفاضية (اتكشف أثناء اختبار حي كمدير إيجارات، 2026-07-06).

    عملاء وعقود تجريبية توضيحية (illustrative sample data) — مش سجلات حقيقية
    للمنتجع، بأسماء كشوك/محلات تجارية واقعية (تأجير معدات غطس، مظلات شاطئ،
    بازار هدايا) بدل قواعد فاضية. الجدول بيُبنى مباشرة بالـ ORM + الـ pure
    engine (`generate_lease_monthly_schedule`/`calculate_lease_penalty`) — مش
    عن طريق `services.create_contract` — عشان منولّدش قيود محاسبية حقيقية على
    الدفاتر لعملاء مُلفَّقين (نفس القرار المتبع في `_seed_timeshare_contracts`).

    Idempotent: لو فيه أي عقد بادئته 'LC-SEED-' للفرع → يتجاهَل (check-then-create)."""
    from datetime import timedelta
    from app.modules.leasing.models import LeaseContract, LeasePayment, TenantCashLog
    from app.modules.core.models import Branch
    from app.resort_os.timeshare_engine import calculate_lease_penalty, generate_lease_monthly_schedule

    branch = db.query(Branch).first()
    if not branch:
        return
    if db.query(LeaseContract).filter(
        LeaseContract.branch_id == branch.id,
        LeaseContract.contract_number.like("LC-SEED-%"),
    ).first():
        return

    today = date.today()

    # كل عنصر: بيانات العقد + عدد الدفعات المدفوعة/المتأخرة (الباقي pending)
    specs = [
        dict(suffix="0001", tenant="كابتن سيف - كشك تأجير معدات الغطس", phone="01011122233",
             unit="كشك رقم 5 - أمام الرصيف البحري",
             start=today - timedelta(days=240), end=today + timedelta(days=490),
             base_rent=Decimal("4500.00"), increase_rate=Decimal("0"), deposit=Decimal("8000.00"),
             status="active", paid_n=6, overdue_n=2),
        dict(suffix="0002", tenant="شركة نور للمظلات والشماسي", phone="01122334455",
             unit="امتداد الشاطئ الشمالي - قطاع B",
             start=today - timedelta(days=420), end=today + timedelta(days=310),
             base_rent=Decimal("6000.00"), increase_rate=Decimal("5.0"), deposit=Decimal("12000.00"),
             status="active", paid_n=10, overdue_n=3),
        dict(suffix="0003", tenant="بازار الخيمة للهدايا والتذكارات", phone="01288997766",
             unit="محل رقم 2 - الممر التجاري",
             start=today - timedelta(days=760), end=today - timedelta(days=30),
             base_rent=Decimal("3200.00"), increase_rate=Decimal("5.0"), deposit=Decimal("5000.00"),
             status="expired", paid_n=None, overdue_n=0),   # paid_n=None → كل الجدول (عقد منتهي مسدد بالكامل)
    ]

    created_contracts: list[LeaseContract] = []
    for s in specs:
        contract = LeaseContract(
            branch_id=branch.id, contract_number=f"LC-SEED-{s['suffix']}",
            tenant_name=s["tenant"], tenant_phone=s["phone"], unit_description=s["unit"],
            start_date=s["start"], end_date=s["end"],
            base_rent=s["base_rent"], increase_rate=s["increase_rate"],
            billing_day=1, grace_months=0, payment_period="monthly",
            security_deposit=s["deposit"], status=s["status"],
            notes="بيانات تجريبية للعرض فقط — مش عقد إيجار حقيقي",
        )
        db.add(contract)
        db.flush()

        schedule = generate_lease_monthly_schedule(
            base_rent=s["base_rent"], increase_rate=float(s["increase_rate"]),
            start_date=s["start"], end_date=s["end"],
        )
        paid_n = s["paid_n"] if s["paid_n"] is not None else len(schedule)
        for idx, item in enumerate(schedule):
            p = LeasePayment(
                contract_id=contract.id, due_date=item["due_date"],
                amount=item["amount"], year_n=item["year_n"],
            )
            if idx < paid_n:
                p.status = "paid"
                p.paid_amount = item["amount"]
                p.paid_at = datetime.combine(item["due_date"], datetime.min.time())
                p.payment_method = "cash"
                p.receipt_number = f"LP-SEED-{contract.id}-{idx + 1:03d}"
            elif idx < paid_n + s["overdue_n"] and item["due_date"] < today:
                p.status = "overdue"
                p.penalty = calculate_lease_penalty(item["amount"], item["due_date"], today)
            db.add(p)
        created_contracts.append(contract)

    # سجل كاش تجريبي — تسوية حصة إيراد لكشك الغطس + ملاحظة صيانة لكشك المظلات
    if len(created_contracts) >= 2:
        db.add(TenantCashLog(
            branch_id=branch.id, contract_id=created_contracts[0].id, amount=Decimal("1200.00"),
            activity_type="revenue_share", payment_method="cash", reference="RS-SEED-01",
            notes="تسوية حصة إيراد تأجير معدات شهرية",
        ))
        db.add(TenantCashLog(
            branch_id=branch.id, contract_id=created_contracts[1].id, amount=Decimal("450.00"),
            activity_type="maintenance", payment_method="cash", reference="MNT-SEED-01",
            notes="إصلاح عمود مظلة تالف",
        ))

    db.flush()
    print(f"  ✓ Lease contracts seeded ({len(created_contracts)} illustrative sample tenants — not real records)")


def _seed_maintenance(db: Session) -> None:
    """⚠️ موديول الصيانة كان بيفتح فاضي تمامًا (0 أصل، 0 أمر صيانة، 0 جدول
    وقائي) رغم إن الفرونت إند والباك إند كاملين وشغالين — نفس فئة باج
    rooms/dining_tables الفاضية اللي اتصلحت قبل كده، اتكشف أثناء تجربة حية
    كمدير صيانة حقيقي (مفيش حتى فني صيانة واحد بين الـ 7 موظفين المزروعين،
    فاتضاف EMP-008 في _seed_employees فوق). ازرع 6 أصول واقعية عبر كل
    الفئات، فني صيانة واحد مربوط بجدول وقائي، و3 أوامر صيانة في 3 حالات
    مختلفة (مفتوح غير مُكلَّف، قيد التنفيذ بقطعة مضافة، مكتمل بقطع+عمالة)
    عشان الشاشة تفتح بحالة واقعية تعكس دورة حياة العمل الحقيقية، مش فاضية."""
    from datetime import timedelta
    from app.modules.core.models import Branch
    from app.modules.hr.models import Employee
    from app.modules.maintenance.models import (
        Asset, PreventiveSchedule, WorkOrder, WorkOrderPart,
    )

    branch = db.query(Branch).first()
    if not branch or db.query(Asset).filter(Asset.branch_id == branch.id).first():
        return

    technician = db.query(Employee).filter(
        Employee.branch_id == branch.id, Employee.employee_code == "EMP-008",
    ).first()
    today = date.today()

    # ── الأصول — عبر كل الفئات الستة (hvac|electrical|plumbing|furniture|vehicle|other) ──
    asset_defs = [
        ("مكيف اللوبي الرئيسي",           "AST-001", "hvac",       "اللوبي الرئيسي"),
        ("مضخة حمام السباحة الرئيسية",    "AST-002", "plumbing",   "غرفة المكينة — حمام السباحة"),
        ("مولد الكهرباء الاحتياطي",       "AST-003", "electrical", "غرفة المولدات"),
        ("ثلاجة المطبخ الكبيرة (Walk-in)", "AST-004", "other",      "المطبخ الرئيسي"),
        ("عربة نقل النزلاء",              "AST-005", "vehicle",    "الجراج"),
        ("جلسات الشاطئ الخشبية",          "AST-006", "furniture",  "الشاطئ"),
    ]
    assets: dict[str, Asset] = {}
    for name, code, category, location in asset_defs:
        a = Asset(branch_id=branch.id, name=name, code=code, category=category,
                   location=location, status="operational")
        db.add(a)
        db.flush()
        assets[code] = a

    # ── جدول صيانة وقائية — مكيف اللوبي كل 90 يوم، مستحق خلال 3 أسابيع ──
    if technician:
        db.add(PreventiveSchedule(
            branch_id=branch.id, asset_id=assets["AST-001"].id,
            title="فحص وتنظيف فلاتر مكيف اللوبي", frequency_days=90,
            last_done=today - timedelta(days=69), next_due=today + timedelta(days=21),
            assigned_to=technician.id,
            checklist='["فحص الفلتر", "تنظيف الكويل", "قياس ضغط الفريون"]',
        ))

    # ── أوامر الصيانة — 3 حالات واقعية مختلفة من دورة الحياة ──
    wo_open = WorkOrder(
        branch_id=branch.id, asset_id=assets["AST-002"].id,
        order_number=f"WO-{today.strftime('%Y%m%d')}-0001",
        title="مضخة حمام السباحة تصدر صوت غريب وتسرب مياه",
        description="لاحظ منقذ الشاطئ تسريب بسيط من وصلة المضخة الرئيسية صباح اليوم.",
        order_type="corrective", priority="high", status="open",
        reported_by=None, scheduled_date=today + timedelta(days=1),
    )
    db.add(wo_open)

    wo_in_progress = WorkOrder(
        branch_id=branch.id, asset_id=assets["AST-001"].id,
        order_number=f"WO-{today.strftime('%Y%m%d')}-0002",
        title="تسريب مياه خفيف من مكيف اللوبي",
        description="قطرات مياه على الأرضية أسفل الوحدة الداخلية.",
        order_type="corrective", priority="medium", status="in_progress",
        assigned_to=technician.id if technician else None, reported_by=None,
        scheduled_date=today, labour_hours=Decimal("1.5"),
    )
    db.add(wo_in_progress)
    db.flush()
    db.add(WorkOrderPart(
        work_order_id=wo_in_progress.id, part_name="فلتر هواء مكيف",
        part_number="FLT-AC-12", quantity=Decimal("2"), unit_cost=Decimal("45.00"),
        total_cost=Decimal("90.00"),
    ))
    wo_in_progress.parts_cost = Decimal("90.00")

    wo_completed = WorkOrder(
        branch_id=branch.id, asset_id=assets["AST-003"].id,
        order_number=f"WO-{today.strftime('%Y%m%d')}-0003",
        title="استبدال بطارية تشغيل المولد الاحتياطي",
        description="المولد فشل يبدأ تلقائيًا أثناء الاختبار الأسبوعي — بطارية التشغيل فارغة.",
        order_type="corrective", priority="critical", status="completed",
        assigned_to=technician.id if technician else None, reported_by=None,
        scheduled_date=today - timedelta(days=3),
        completed_at=datetime.combine(today - timedelta(days=2), datetime.min.time()) + timedelta(hours=14),
        labour_hours=Decimal("2.0"), labour_cost=Decimal("300.00"),
    )
    db.add(wo_completed)
    db.flush()
    db.add(WorkOrderPart(
        work_order_id=wo_completed.id, part_name="بطارية تشغيل 12 فولت",
        part_number="BAT-GEN-12V", quantity=Decimal("1"), unit_cost=Decimal("1200.00"),
        total_cost=Decimal("1200.00"),
    ))
    wo_completed.parts_cost = Decimal("1200.00")

    db.flush()
    print(f"  ✓ Maintenance seeded ({len(assets)} assets, "
          f"{'1' if technician else '0'} preventive schedule, 3 work orders — "
          f"open/in-progress/completed)")


def _get_or_create_outlet(db: Session, branch_id: int, outlet_type: str,
                           name_ar: str, revenue_account_code: str):
    """راجع dining.models.Outlet — get-or-create مشتركة بين كل دوال الـ seed
    اللي محتاجة outlet مطعم/كافيه (DINING_CUTOVER_PLAN.md Batch 6: كانت
    _seed_menus و_seed_dining_tables بتكرر نفس المنطق ده لحالها بعد ما
    اتحوّلوا من restaurant.models/cafe.models القديمين لـ dining.models)."""
    from app.modules.dining.models import Outlet

    outlet = db.query(Outlet).filter(
        Outlet.branch_id == branch_id, Outlet.outlet_type == outlet_type,
    ).first()
    if not outlet:
        outlet = Outlet(branch_id=branch_id, name=name_ar, name_ar=name_ar,
                         outlet_type=outlet_type, revenue_account_code=revenue_account_code)
        db.add(outlet)
        db.flush()
    return outlet


def _seed_dining_tables(db: Session, branch_id: int | None = None) -> None:
    """⚠️ نفس ملاحظة _seed_rooms — ترقيم منطقي افتراضي مش أرقام طاولات حقيقية
    موثّقة. قبل هذا التعديل كان جدول dining_tables (مطعم) و cafe_tables (كافيه)
    فاضيين تمامًا (0 صف) — يعني شاشة "الطاولات" بتاعة الجرسون كانت بتعرض
    "لا توجد طاولات مسجّلة لهذا الفرع" دايمًا، فمفيش أي طريقة حقيقية لعمل أوردر
    dine_in مربوط بطاولة فعلية (اتكشف أثناء اختبار حي لمسار الجرسون الكامل —
    نفس فئة باج rooms الفاضية اللي اتصلحت قبل كده). ازرع ترقيم منطقي متسلسل
    دلوقتي: 12 طاولة (1-10 لـ4 أفراد، 11-12 لـ8 أفراد لمجموعات كبيرة).

    `branch_id` اختياري — للتستات بس (عشان تحدد فرع بعينه بدل الاعتماد على
    'أول فرع في الداتابيز' اللي مش مضمون يكون معزول في session-scoped test DB
    فيها فروع تانية من تستات HTTP بتعمل commit حقيقي). الاستخدام الحقيقي من
    seed_all() مبيبعتش الحجة دي خالص — بيعتمد على أول فرع زي باقي دوال الـ seed.

    ⚠️ **طاولات مشتركة (2026-07-21)**: كانت الدالة دي بتزرع مجموعتين منفصلتين
    (12 طاولة "مطعم" + 8 طاولة "كافيه"، كل مجموعة أرقامها من 1) — باج حقيقي
    اكتشفه Mohamed: الكاشير كان يشوف شبكة طاولات مختلفة تمامًا كل ما يبدّل
    المنفذ، عكس الواقع (نفس الصالة الفعلية بتخدم المطعم والكافيه). بقت الطاولة
    ملك للفرع بس (VenueTable.outlet_id اتشال، راجع migration 9b4e1a2c7f30) —
    مجموعة واحدة، والمنفذ بقى بيفلتر المنيو المعروض مش الطاولات."""
    from app.modules.dining.models import VenueTable
    from app.modules.core.models import Branch

    branch = db.query(Branch).filter(Branch.id == branch_id).first() if branch_id else db.query(Branch).first()
    if not branch:
        return

    if db.query(VenueTable).filter(VenueTable.branch_id == branch.id).first():
        return

    total = 0
    for i in range(1, 11):
        db.add(VenueTable(branch_id=branch.id, table_number=str(i), capacity=4))
        total += 1
    for i in range(11, 13):
        db.add(VenueTable(branch_id=branch.id, table_number=str(i), capacity=8))
        total += 1
    db.flush()
    print(f"  ✓ Dining tables seeded ({total} tables, shared across outlets — logical default numbering, not verified real numbers)")


def _seed_beach_reservations(db: Session, branch_id: int | None = None) -> None:
    """⚠️ جدول beach_reservations كان فاضيًا تمامًا (0 صف) — يعني شاشة
    الضيف بتاعة "تسجيل دخول الشاطئ عبر QR" (`public` app's BeachCheckinView،
    مدموجة من apps/qr القديم 2026-07-06) مستحيل تتفتح فعليًا بأي ID حقيقي،
    من غير أي حجز واحد يتفحص عليه QR. اتكشف أثناء جولة اختبار حي شاملة
    2026-07-06. حجزين توضيحيين (pending) بتاريخ النهاردة — عن طريق
    `services.create_reservation` الحقيقي (بيحسب `total_amount` تقديري من
    إعدادات تسعير الشاطئ الفعلية، من غير ما يرحّل أي قيد محاسبي — الترحيل
    الحقيقي بيحصل بس وقت check_in_reservation، لما موظف حقيقي يأكّد الدخول)."""
    from app.modules.beach.models import BeachReservation
    from app.modules.beach.schemas import BeachReservationCreate
    from app.modules.beach.services import create_reservation
    from app.modules.core.models import Branch

    branch = db.query(Branch).filter(Branch.id == branch_id).first() if branch_id else db.query(Branch).first()
    if not branch or db.query(BeachReservation).filter(BeachReservation.branch_id == branch.id).first():
        return

    today = date.today()
    specs = [
        ("سارة يوسف عبد الله", "01055667788", 4, True),
        ("وليد أحمد ثابت",     "01166778899", 2, False),
    ]
    for name, phone, guests, towel in specs:
        create_reservation(db, BeachReservationCreate(
            branch_id=branch.id, guest_name=name, guest_phone=phone,
            reservation_date=today, guests_count=guests, with_towel=towel,
        ))
    print(f"  ✓ Beach reservations seeded ({len(specs)} illustrative, pending QR check-in)")


def _seed_beach_locations(db: Session, branch_id: int | None = None) -> None:
    """⚠️ جدول beach_locations كان غير موجود خالص قبل الخريطة الحية — يعني
    شاشة "خريطة الشاطئ" (/pos/beach-map) كانت هتفتح فاضية تمامًا بأول تشغيل،
    نفس فئة فجوة الـ seed اللي اتكشفت قبل كده في rooms/dining_tables/b2b
    (نموذج البيانات موجود، الصفوف صفر). بيزرع 12 شمسية + 6 برجولة (ترقيم
    منطقي تسلسلي، نفس أسلوب _seed_dining_tables — مش أرقام حقيقية موثّقة)
    عبر services.bulk_add_locations الحقيقية، وبعدين يسجّل دخول ضيفين
    توضيحيين فعليًا (services.checkin_location — عملية بيع حقيقية بقيد
    محاسبي، مش صفوف مُدرَجة مباشرة) عشان الخريطة تبان "شغالة" من التشغيلة
    الأولى بدل ما تكون كل المواقع فاضية على طول."""
    from app.modules.beach.models import BeachLocation
    from app.modules.beach.schemas import BeachLocationCheckinRequest
    from app.modules.beach.services import bulk_add_locations, checkin_location
    from app.core.kernel.models.user import User
    from app.modules.core.models import Branch

    branch = db.query(Branch).filter(Branch.id == branch_id).first() if branch_id else db.query(Branch).first()
    if not branch or db.query(BeachLocation).filter(BeachLocation.branch_id == branch.id).first():
        return

    umbrellas = bulk_add_locations(db, branch.id, "umbrella", 12)
    pergolas  = bulk_add_locations(db, branch.id, "pergola", 6)

    cashier = db.query(User).filter(User.email == "cashier@resortos.local").first()
    cashier_id = cashier.id if cashier else None

    demo_checkins = [
        (umbrellas[0], "منى إبراهيم السيد", "01012345678", 2, True),
        (umbrellas[3], "كريم عبد الرحمن",    "01298765432", 1, False),
    ]
    for loc, name, phone, guests, towel in demo_checkins:
        checkin_location(
            db, branch.id, loc.id,
            BeachLocationCheckinRequest(
                guest_name=name, guest_phone=phone, guests_count=guests, with_towel=towel,
            ),
            cashier_id=cashier_id,
        )

    print(
        f"  ✓ Beach locations seeded ({len(umbrellas)} umbrellas + {len(pergolas)} pergolas, "
        f"{len(demo_checkins)} illustrative live check-ins)"
    )


def _seed_b2b_contracts(db: Session, branch_id: int | None = None) -> None:
    """⚠️ باج حقيقي كان هنا (اتكشف بتجربة حية لموديول الشاطئ): جدول
    b2b_contracts كان فاضي تمامًا (0 صف) من أول ما الموديول اتعمل — يعني
    شاشة "عقود B2B" في الإدارة كانت بتعرض قائمة فاضية دايمًا، ومفيش أي طريقة
    لتجربة مسار "تسجيل دخول ضيف فندق شريك" (B2B check-in) من غير ما حد
    يدخل بيانات عقد يدويًا الأول — نفس فئة فجوة الـ seed اللي اتكشفت قبل
    كده في HR (صفر موظفين) وPMS (صفر غرف).

    عقود توضيحية (illustrative sample data) — أسماء فنادق شرم الشيخ منطقية
    بس **مش شراكات حقيقية موثّقة**، الغرض بس تشغيل شاشة B2B/اللوحة الحيّة
    وتسجيل دخول B2B فعلي بأول تشغيل بدل قائمة فاضية:
    - فندق بحصة صحية عادية + حد ائتمان مريح (لعرض الحالة الطبيعية).
    - فندق قريب من استنفاد الحصة اليومية + حد ائتمان ضيّق **متخطّى بالفعل**
      ورصيد قديم متأخر عن مهلة السداد (لعرض تنبيهي quota_warning وis_overdue
      سوا — نفس السيناريو الواقعي: فندق بطيء في التحصيل غالبًا هو نفسه اللي
      بيستهلك حصته بسرعة) — من غير ما حد يحتاج يعمل تشيك-إن حقيقي الأول
      عشان يشوف الميزة شغالة.
    - فندق بحصة كبيرة غير مستخدمة وبدون حد ائتمان خالص (لعرض إن الحد
      اختياري فعليًا — مش كل شريك محتاجه).

    Idempotent: لو فيه أي عقد للفرع أصلاً → يتجاهَل تمامًا (مايكررش)."""
    from datetime import timedelta

    from app.modules.beach.models import B2BContract, B2BContractDay
    from app.modules.core.models import Branch

    branch = db.query(Branch).filter(Branch.id == branch_id).first() if branch_id else db.query(Branch).first()
    if not branch:
        return
    if db.query(B2BContract).filter(B2BContract.branch_id == branch.id).first():
        return

    today = date.today()
    specs = [
        # (hotel_name, hotel_name_ar, phone, daily_quota, entry_price, towel_price,
        #  checked_in_today, credit_limit, is_overdue_demo)
        ("Sunrise Grand Sharm",   "صنرايز جراند شرم",   "+201001112233", 40, Decimal("120"), Decimal("30"),
         6,  Decimal("5000"), False),
        ("Palm Oasis Resort",    "بالم أوازيس ريزورت", "+201002223344", 15, Decimal("100"), Decimal("25"),
         12, Decimal("2000"), True),
        ("Coral Bay Hotel",      "كورال باي هوتيل",    "+201003334455", 60, Decimal("150"), Decimal("40"),
         0,  None,            False),
    ]

    created = 0
    for hotel_en, hotel_ar, phone, quota, entry_price, towel_price, checked_in, credit_limit, overdue_demo in specs:
        contract = B2BContract(
            branch_id=branch.id,
            hotel_name=hotel_en, hotel_name_ar=hotel_ar, contact_phone=phone,
            daily_quota=quota, entry_price=entry_price, towel_price=towel_price,
            valid_from=today.replace(day=1),
            valid_until=date(today.year, 12, 31),
            is_active=True,
            credit_limit=credit_limit,
            payment_terms_days=30,
            is_overdue=overdue_demo,
            notes="عقد توضيحي (illustrative) — لتشغيل شاشة B2B وتجربة تسجيل الدخول، مش شراكة حقيقية موثّقة.",
        )
        db.add(contract)
        db.flush()
        if checked_in:
            db.add(B2BContractDay(
                contract_id=contract.id, day=today,
                checked_in_count=checked_in,
                total_amount=entry_price * checked_in,
            ))
        if overdue_demo:
            # رصيد قديم (45 يوم) لسه مش متسوّى — أقدم من مهلة السداد
            # (30 يوم)، فهو اللي فعليًا بيخلي is_overdue=True صحيح حسابيًا
            # (مش بس علم مضبوط يدويًا) لو الـ Celery task اتشغّل، وبيخلي
            # outstanding_balance يتخطى credit_limit من أول تشغيل.
            old_day = today - timedelta(days=45)
            db.add(B2BContractDay(
                contract_id=contract.id, day=old_day,
                checked_in_count=20, total_amount=Decimal("2500"),
            ))
        created += 1

    db.flush()
    print(f"  ✓ B2B contracts seeded ({created} illustrative sample partner hotels — not real partnerships)")


def _seed_menus(db: Session) -> None:
    """قوائم مطعم وكافيه حقيقية — منقولة من ملفات المنيو الحقيقية اللي Mohamed
    بعتها (Restaurant_menu.json + beverages_menu.json)، بعد مراجعة كاملة.

    ⚠️ باج تصنيف حقيقي كان هنا اتصلح (2026-07-08): النسخة القديمة من الدالة دي
    كانت بتحط كل الأكل الحقيقي (بيتزا/باستا/حواوشي/ساندوتشات/فطار — أطباق
    محتاجة مطبخ فعلي) في موديول *الكافيه*، بينما موديول *المطعم* فضل بـ4
    أصناف بس. النتيجة كانت خطأين مركّبين: (1) المنيو نفسه غلط — كاشير المطعم
    شايف 4 أصناف بس، وكاشير الكافيه شايف بيتزا/حواوشي بدل مشروبات، (2) شاشات
    الـ KDS كانت متأثرة فعليًا — كل تذاكر الكافيه كانت متوجّهة لمحطة "bar"
    ثابتة (راجع CafeItem.station الجديد وقتها + CLAUDE.md §13 بند ⓭)، يعني
    بيتزا/باستا/حواوشي عمرها ما وصلت لشاشة kds/kitchen، وشاشة kds/bar كانت
    مزدحمة بأطباق كاملة مش مشروبات. الحل: المطعم = المنيو الحقيقي الكامل
    (9 فئات، ~44 صنف، من Restaurant_menu.json)، والكافيه = مشروبات حقيقية
    بس (6 فئات، من beverages_menu.json) — كل صنف بمحطة KDS صحيحة.

    DINING_CUTOVER_PLAN.md Batch 6 — بعد حذف restaurant/cafe، الدالة دي بقت
    بتزرع مباشرة في dining.models (Outlet outlet_type='restaurant'|'cafe' +
    DiningCategory + DiningItem) بدل MenuCategory/MenuItem/CafeCategory/
    CafeItem القديمين اللي اتحذفوا — نفس البيانات الحقيقية بالحرف الواحد،
    مصدر واحد بدل جدولين (dining هو الوحيد اللي أي بيئة جديدة (VPS جديد،
    clone جديد) هتتزرع فيه من الأول)."""
    from app.modules.dining.models import DiningCategory, DiningItem
    from app.modules.core.models import Branch

    branch = db.query(Branch).first()
    if not branch:
        return

    # ══════════════════════ المطعم (Restaurant_menu.json) ══════════════════
    restaurant_outlet = _get_or_create_outlet(db, branch.id, "restaurant", "المطعم", "4200")

    if not db.query(DiningItem).filter(DiningItem.outlet_id == restaurant_outlet.id).first():
        # (category_key, name_ar) — بالترتيب اللي هيظهر بيه في POS
        restaurant_categories = [
            ("appetizers", "المقبلات"),
            ("soup", "الشوربة"),
            ("salad", "السلطة"),
            ("sandwiches", "سندوتشات"),
            ("main_dish", "الأطباق الرئيسية"),
            ("pizza", "البيتزا"),
            ("pasta", "الباستا"),
            ("extra", "الإضافات"),
            ("dessert", "الحلويات"),
        ]
        cat_map: dict[str, int] = {}
        for i, (key, name_ar) in enumerate(restaurant_categories):
            c = DiningCategory(branch_id=branch.id, outlet_id=restaurant_outlet.id,
                                name=key.replace("_", " ").title(), name_ar=name_ar, sort_order=i)
            db.add(c)
            db.flush()
            cat_map[key] = c.id

        # (category_key, name_en, name_ar, price, station)
        # station: hot|grill|cold|bar|dessert — مبنية على طريقة التحضير
        # الفعلية المذكورة في وصف كل صنف (مشوي→grill، مقلي/ووك→hot، بدون
        # طهي→cold)، مش تخمين — راجع description_en في الملف المصدر.
        restaurant_items = [
            ("appetizers", "Chicken Satay", "ساتيه فراخ", Decimal("310"), "grill"),
            ("appetizers", "Shrimp Kunafa", "كنافة جمبري", Decimal("380"), "hot"),
            ("appetizers", "Fried Calamari", "فرايد كاليماري", Decimal("260"), "hot"),
            ("appetizers", "Vegetable Spring Rolls", "اسبرنج رول خضار", Decimal("230"), "hot"),

            ("soup", "Seafood Soup", "سي فوود شوربة", Decimal("350"), "hot"),
            ("soup", "Vegetable Soup", "شوربة خضار", Decimal("225"), "hot"),
            ("soup", "Thai Beef Soup", "تاي بيف سوب", Decimal("330"), "hot"),

            ("salad", "Green Salad", "سلطة خضراء", Decimal("125"), "cold"),
            ("salad", "Caesar Salad", "سلطة سيزار", Decimal("160"), "cold"),
            ("salad", "Greek Salad", "سلطة جريك", Decimal("140"), "cold"),
            ("salad", "Fattoush Salad", "سلطة فتوش", Decimal("130"), "cold"),
            ("salad", "Caprese Salad", "سلطة كابريزي", Decimal("160"), "cold"),

            ("sandwiches", "Beef Burger", "برجر لحمة", Decimal("260"), "grill"),
            ("sandwiches", "Steak Sandwich", "أستيك ساندوتش", Decimal("320"), "grill"),
            ("sandwiches", "Battaya Sandwich", "بطاطا ساندوتش", Decimal("260"), "hot"),
            ("sandwiches", "Fried Chicken", "فرايد تشيكن", Decimal("240"), "hot"),

            ("main_dish", "Chicken Grill", "جريل دجاج", Decimal("350"), "grill"),
            ("main_dish", "Beef Grill", "جريل لحمة", Decimal("480"), "grill"),
            ("main_dish", "Mixed Grill", "ميكس جريل", Decimal("500"), "grill"),
            ("main_dish", "Shrimp Grill", "جمبري جريل", Decimal("550"), "grill"),
            ("main_dish", "Cashew Chicken", "دجاج بالكاجو", Decimal("330"), "hot"),
            ("main_dish", "Black Pepper Beef", "لحمة بالفلفل الأسود", Decimal("420"), "hot"),
            ("main_dish", "Green Curry Chicken", "دجاج جرين كاري", Decimal("330"), "hot"),
            ("main_dish", "Sweet Sour Chicken", "دجاج سويت سور", Decimal("300"), "hot"),
            ("main_dish", "Fish", "سمك", Decimal("450"), "grill"),

            ("pizza", "Margherita Pizza", "بيتزا مارجريتا", Decimal("200"), "hot"),
            ("pizza", "Cutroforma", "كوتروفورماج", Decimal("270"), "hot"),
            ("pizza", "Salami Pizza", "بيتزا سلامي", Decimal("280"), "hot"),
            ("pizza", "Tuna Pizza", "بيتزا تونة", Decimal("300"), "hot"),
            ("pizza", "Smoked Turkey Pizza", "بيتزا تركي مدخن", Decimal("320"), "hot"),
            ("pizza", "Cutro Estagoini", "كوترو استاجويني", Decimal("350"), "hot"),
            ("pizza", "White Penca", "بنكا بيضاء", Decimal("420"), "hot"),
            ("pizza", "Ricola", "ريكولا", Decimal("250"), "hot"),
            ("pizza", "Seafood Pizza", "بيتزا سي فوود", Decimal("360"), "hot"),
            ("pizza", "Shrimp Pizza", "بيتزا جمبري", Decimal("400"), "hot"),

            ("pasta", "Pen Red Sauce", "مكرونة صوص أحمر", Decimal("240"), "hot"),
            ("pasta", "Pen White Sauce", "مكرونة صوص أبيض", Decimal("300"), "hot"),
            ("pasta", "Seafood Spaghetti", "اسباجيتي سي فوود", Decimal("340"), "hot"),
            ("pasta", "Pink Shrimp Spaghetti", "اسباجيتي بينك جمبري", Decimal("400"), "hot"),
            ("pasta", "Pad Thai", "باد تاي", Decimal("320"), "hot"),

            ("extra", "French Fries", "فرنش فرايز", Decimal("80"), "hot"),
            ("extra", "White Rice", "أرز أبيض", Decimal("60"), "hot"),

            ("dessert", "Fried Ice Cream", "آيس كريم مقلي", Decimal("250"), "dessert"),
            ("dessert", "Fried Banana", "موز مقلي", Decimal("250"), "dessert"),
        ]
        for cat_key, name, name_ar, price, station in restaurant_items:
            db.add(DiningItem(
                branch_id=branch.id, outlet_id=restaurant_outlet.id, category_id=cat_map[cat_key],
                name=name, name_ar=name_ar, price=price, station=station,
            ))
        db.flush()
        print(f"  ✓ Restaurant menu seeded ({len(restaurant_items)} items across {len(restaurant_categories)} categories)")

    # ══════════════════════ الكافيه (beverages_menu.json) ═══════════════════
    # مشروبات بس — station="bar" لكل الأصناف (كافيه المنتجع مش عنده مطبخ
    # حقيقي، بس بار/باريستا). الأصناف اللي status="removed" في المصدر
    # (متوقفة فعليًا) اتستبعدت عمدًا.
    cafe_outlet = _get_or_create_outlet(db, branch.id, "cafe", "الكافيه", "4400")

    if not db.query(DiningItem).filter(DiningItem.outlet_id == cafe_outlet.id).first():
        cafe_categories = [
            ("Cocktails", "كوكتيلات"),
            ("Fresh Juices", "عصائر طازجة"),
            ("Soda Corner", "ركنة الصودا"),
            ("Fruit Salad", "سلطة فواكه"),
            ("Cold Drinks", "مشروبات باردة"),
            ("Hot Drinks", "مشروبات ساخنة"),
        ]
        cat_map2: dict[str, int] = {}
        for i, (name_en, name_ar) in enumerate(cafe_categories):
            c = DiningCategory(branch_id=branch.id, outlet_id=cafe_outlet.id,
                                name=name_en, name_ar=name_ar, sort_order=i)
            db.add(c)
            db.flush()
            cat_map2[name_en] = c.id

        # (category_en, name_en, name_ar, price) — السعر = new_price من الملف
        # المصدر (السعر الحالي المعتمد بعد آخر تحديث تسعير)، مش current_price
        # (السعر القديم قبل الزيادة).
        cafe_items = [
            ("Cocktails", "Al Khaima Cocktail", "كوكتيل الخيمة", Decimal("185")),
            ("Cocktails", "Hawaiian Cocktail", "كوكتيل هاواي", Decimal("185")),
            ("Cocktails", "Power Cocktail", "كوكتيل باور", Decimal("185")),
            ("Cocktails", "Cup Jack", "كب جاك", Decimal("185")),
            ("Cocktails", "Fakhfakhina Ace", "فخفخينة إيس", Decimal("190")),
            ("Cocktails", "Super Viagra", "سوبر فياجرا", Decimal("220")),
            ("Cocktails", "Africano Cocktail", "كوكتيل أفريكانو", Decimal("185")),
            ("Cocktails", "Fruit Yogurt", "زبادي بالفواكه", Decimal("185")),

            ("Fresh Juices", "Mango", "مانجو", Decimal("160")),
            ("Fresh Juices", "Strawberry", "فراولة", Decimal("145")),
            ("Fresh Juices", "Guava", "جوافة", Decimal("145")),
            ("Fresh Juices", "Cantaloupe", "كانتالوب", Decimal("145")),
            ("Fresh Juices", "Pomegranate", "رمان", Decimal("145")),
            ("Fresh Juices", "Watermelon", "بطيخ", Decimal("160")),
            ("Fresh Juices", "Boreo", "بوريو", Decimal("165")),
            ("Fresh Juices", "Oreo", "أوريو", Decimal("145")),
            ("Fresh Juices", "Fresh Lemon", "ليمون فريش", Decimal("160")),
            ("Fresh Juices", "Lemon Mint", "ليمون بالنعناع", Decimal("160")),
            ("Fresh Juices", "French Lemon", "ليمون فرنساوي", Decimal("160")),
            ("Fresh Juices", "Jujube", "نبق", Decimal("145")),
            ("Fresh Juices", "Apple Juice with Yogurt", "تفاح بالزبادي", Decimal("165")),
            ("Fresh Juices", "Red Grape Juice", "عنب أحمر", Decimal("165")),
            ("Fresh Juices", "Pineapple Juice", "أناناس", Decimal("190")),
            ("Fresh Juices", "Peach Juice", "خوخ", Decimal("165")),
            ("Fresh Juices", "Avocado", "أفوكادو", Decimal("165")),
            ("Fresh Juices", "Dates with Yogurt", "تمر بالزبادي", Decimal("165")),
            ("Fresh Juices", "Plain Yogurt", "زبادي سادة", Decimal("165")),
            ("Fresh Juices", "Honey Yogurt", "زبادي بالعسل", Decimal("160")),
            ("Fresh Juices", "Chocolate Yogurt", "زبادي بالشوكولاتة", Decimal("160")),
            ("Fresh Juices", "Banana with Yogurt", "موز بالزبادي", Decimal("160")),
            ("Fresh Juices", "Fresh Orange Juice", "برتقال فريش", Decimal("145")),
            ("Fresh Juices", "Kiwi", "كيوي", Decimal("160")),

            ("Soda Corner", "Sunshine", "صنشاين", Decimal("145")),
            ("Soda Corner", "Mojito Soda", "موهيتو صودا", Decimal("160")),
            ("Soda Corner", "Mojito Red Bull", "موهيتو ريد بول", Decimal("195")),
            ("Soda Corner", "Sunrise", "صنرايز", Decimal("160")),

            ("Fruit Salad", "Fruit Salad Tent", "سلطة فواكه تنت", Decimal("160")),
            ("Fruit Salad", "Tropical Fruit Salad", "سلطة فواكه استوائية", Decimal("160")),
            ("Fruit Salad", "Cinderella Fruit Salad", "سلطة فواكه سندريلا", Decimal("160")),
            ("Fruit Salad", "Dahab Fruit Salad", "سلطة فواكه دهب", Decimal("160")),

            ("Cold Drinks", "Cola", "كولا", Decimal("70")),
            ("Cold Drinks", "Sprite", "سبرايت", Decimal("70")),
            ("Cold Drinks", "Schweppes", "شويبس", Decimal("70")),
            ("Cold Drinks", "Fayrouz", "فيروز", Decimal("80")),
            ("Cold Drinks", "Bearl", "بيرل", Decimal("80")),
            ("Cold Drinks", "Redbull", "ريد بول", Decimal("160")),
            ("Cold Drinks", "Small Water", "مياه صغيرة", Decimal("20")),
            # ⚠️ "Small Water" سعره في المصدر "20/30" (نص، مش رقم — على الأرجح
            # سعرين لحجمين مختلفين). اتاخد أقل سعر (20) كقيمة افتراضية مؤقتة —
            # لو الفرق بين الحجمين مهم فعليًا، ده مرشّح طبيعي لـ DiningItemVariant
            # بدل صنف واحد بسعر تقريبي، محتاج تأكيد من Mohamed للسعرين الحقيقيين الأول.

            ("Hot Drinks", "Single Espresso", "إسبريسو سنجل", Decimal("70")),
            ("Hot Drinks", "Double Espresso", "إسبريسو دبل", Decimal("85")),
            ("Hot Drinks", "Single Shot Cappuccino", "كابتشينو سنجل شوت", Decimal("110")),
            ("Hot Drinks", "Latte", "لاتيه", Decimal("115")),
            ("Hot Drinks", "Hot Chocolate", "شوكولاتة ساخنة", Decimal("115")),
            ("Hot Drinks", "Nescafe", "نسكافيه", Decimal("115")),
            ("Hot Drinks", "American Coffee", "قهوة أمريكاني", Decimal("95")),
            ("Hot Drinks", "Micato", "ميكاتو", Decimal("100")),
            ("Hot Drinks", "Anise-Hibiscus-Mint", "ينسون كركديه نعناع", Decimal("65")),
            ("Hot Drinks", "Lipton Tea", "شاي ليبتون", Decimal("65")),
            ("Hot Drinks", "Turkish Coffee", "قهوة تركي", Decimal("75")),
            ("Hot Drinks", "French Coffee", "قهوة فرنساوي", Decimal("85")),
            ("Hot Drinks", "Tea with Milk", "شاي باللبن", Decimal("90")),
        ]
        for cat_en, name, name_ar, price in cafe_items:
            db.add(DiningItem(
                branch_id=branch.id, outlet_id=cafe_outlet.id, category_id=cat_map2[cat_en],
                name=name, name_ar=name_ar, price=price, station="bar",
            ))
        db.flush()
        print(f"  ✓ Cafe menu seeded ({len(cafe_items)} beverage items across {len(cafe_categories)} categories)")


def _seed_inventory_recipes(db: Session) -> None:
    """مخزون + وصفات (Recipe/BOM) حقيقية — مربوطة بالمنيو الحقيقي المُصحّح
    (`_seed_menus`، بعد إصلاح 2026-07-08). كانت الوصفات القديمة (3 بس) مربوطة
    بأصناف كافيه غلط أصلاً (برجر/مارجريتا/حواوشي كانت CafeItem مش MenuItem) —
    اتصلحت هنا مع باقي المنيو، وبقى العدد 13 وصفة حقيقية تغطي كل محطات
    المطبخ (grill/hot/cold/dessert) بدل 3 أمثلة توضيحية بس، عشان تقرير تكلفة
    الطعام (`/admin/food-cost`) يبقى له معنى حقيقي عبر المنيو مش صنف واحد.

    DINING_CUTOVER_PLAN.md Batch 6 — dining.DiningItem/DiningItemRecipeLine
    بدل restaurant.MenuItem/MenuItemRecipeLine القديمين. مفلترة بـ outlet
    outlet_type='restaurant' صراحةً (dining_items جدول موحّد بين المطعم
    والكافيه دلوقتي، فلازم فلتر outlet عشان مانخلطش لو صنف بنفس الاسم
    موجود في الاتنين — نظريًا مش عمليًا هنا، لكن الفلتر الصريح أسلم)."""
    try:
        from app.modules.inventory.models import Product, StockMovement, Warehouse
        from app.modules.dining.models import DiningItem, DiningItemRecipeLine
        from app.modules.core.models import Branch
    except ImportError:
        return

    branch = db.query(Branch).first()
    if not branch:
        return
    if db.query(Warehouse).filter(Warehouse.branch_id == branch.id).first():
        return

    restaurant_outlet = _get_or_create_outlet(db, branch.id, "restaurant", "المطعم", "4200")

    warehouse = Warehouse(branch_id=branch.id, name="Main Kitchen Store",
                           name_ar="مخزن المطبخ الرئيسي", code="WH-KITCHEN")
    db.add(warehouse)
    db.flush()

    # (name_en, name_ar, unit, cost_price, initial_stock) — تكاليف تقريبية
    # واقعية للسوق المصري (2026)، مش أرقام عشوائية.
    ingredients = [
        ('Ground Beef',       'لحم مفروم',       'kg',    Decimal('180'), Decimal('20')),
        ('Burger Bun',        'خبز برجر',        'piece', Decimal('3'),   Decimal('100')),
        ('Cheddar Cheese',    'جبنة شيدر',       'kg',    Decimal('220'), Decimal('10')),
        ('Pizza Dough',       'عجينة بيتزا',     'kg',    Decimal('40'),  Decimal('15')),
        ('Mozzarella Cheese', 'جبنة موتزاريلا',  'kg',    Decimal('250'), Decimal('10')),
        ('Tomato Sauce',      'صلصة طماطم',      'kg',    Decimal('35'),  Decimal('10')),
        ('Salami',            'سلامي',           'kg',    Decimal('280'), Decimal('5')),
        ('Canned Tuna',       'تونة معلبة',      'kg',    Decimal('150'), Decimal('5')),
        ('Penne Pasta',       'مكرونة بني',      'kg',    Decimal('45'),  Decimal('10')),
        ('Chicken Breast',    'صدور فراخ',       'kg',    Decimal('130'), Decimal('15')),
        ('Beef Fillet',       'فيليه لحمة',      'kg',    Decimal('380'), Decimal('10')),
        ('Shrimp',            'جمبري',           'kg',    Decimal('320'), Decimal('8')),
        ('Calamari',          'كاليماري',        'kg',    Decimal('200'), Decimal('6')),
        ('White Rice (raw)',  'أرز أبيض خام',    'kg',    Decimal('25'),  Decimal('20')),
        ('Potato',            'بطاطس',           'kg',    Decimal('18'),  Decimal('25')),
        ('Lettuce',           'خس',              'kg',    Decimal('15'),  Decimal('8')),
        ('Fresh Tomato',      'طماطم طازجة',     'kg',    Decimal('20'),  Decimal('10')),
        ('Cucumber',          'خيار',            'kg',    Decimal('15'),  Decimal('8')),
        ('Feta Cheese',       'جبنة فيتا',       'kg',    Decimal('200'), Decimal('6')),
        ('Parmesan Cheese',   'جبنة بارميزان',   'kg',    Decimal('350'), Decimal('4')),
        ('Banana',            'موز',             'kg',    Decimal('30'),  Decimal('10')),
    ]
    products: dict[str, Product] = {}
    for name_en, name_ar, unit, cost, stock in ingredients:
        product = Product(
            branch_id=branch.id, warehouse_id=warehouse.id, name=name_en, name_ar=name_ar,
            sku=f"ING-{name_en.upper().replace(' ', '-')}", unit=unit, cost_price=cost,
            current_stock=stock, min_stock=Decimal('2'), reorder_point=Decimal('5'),
        )
        db.add(product)
        db.flush()
        products[name_ar] = product
        db.add(StockMovement(
            branch_id=branch.id, product_id=product.id, warehouse_id=warehouse.id,
            movement_type='purchase_in', quantity=stock, unit_cost=cost,
            reference_type='seed', moved_at=datetime.utcnow(),
        ))
    db.flush()

    def _link_recipe(menu_item_name_ar: str, lines: list[tuple[str, Decimal]]) -> None:
        item = db.query(DiningItem).filter(
            DiningItem.outlet_id == restaurant_outlet.id, DiningItem.name_ar == menu_item_name_ar,
        ).first()
        if not item:
            return
        for product_name_ar, qty in lines:
            product = products.get(product_name_ar)
            if product:
                db.add(DiningItemRecipeLine(item_id=item.id, product_id=product.id, quantity_per_unit=qty))

    recipes: list[tuple[str, list[tuple[str, Decimal]]]] = [
        # سندوتشات
        ('برجر لحمة', [
            ('لحم مفروم', Decimal('0.150')), ('خبز برجر', Decimal('1')),
            ('جبنة شيدر', Decimal('0.030')), ('خس', Decimal('0.020')), ('طماطم طازجة', Decimal('0.020')),
        ]),
        # البيتزا
        ('بيتزا مارجريتا', [
            ('عجينة بيتزا', Decimal('0.300')), ('جبنة موتزاريلا', Decimal('0.150')), ('صلصة طماطم', Decimal('0.100')),
        ]),
        ('بيتزا سلامي', [
            ('عجينة بيتزا', Decimal('0.300')), ('جبنة موتزاريلا', Decimal('0.120')),
            ('صلصة طماطم', Decimal('0.100')), ('سلامي', Decimal('0.080')),
        ]),
        ('بيتزا تونة', [
            ('عجينة بيتزا', Decimal('0.300')), ('جبنة موتزاريلا', Decimal('0.120')),
            ('صلصة طماطم', Decimal('0.100')), ('تونة معلبة', Decimal('0.070')),
        ]),
        # الباستا
        ('مكرونة صوص أحمر', [
            ('مكرونة بني', Decimal('0.200')), ('صلصة طماطم', Decimal('0.150')),
        ]),
        # الأطباق الرئيسية
        ('جريل دجاج', [
            ('صدور فراخ', Decimal('0.300')), ('أرز أبيض خام', Decimal('0.150')), ('بطاطس', Decimal('0.150')),
        ]),
        ('جريل لحمة', [
            ('فيليه لحمة', Decimal('0.250')), ('أرز أبيض خام', Decimal('0.150')), ('بطاطس', Decimal('0.150')),
        ]),
        ('جمبري جريل', [
            ('جمبري', Decimal('0.250')), ('بطاطس', Decimal('0.150')),
        ]),
        # المقبلات
        ('فرايد كاليماري', [
            ('كاليماري', Decimal('0.200')),
        ]),
        # السلطة
        ('سلطة سيزار', [
            ('خس', Decimal('0.100')), ('جبنة بارميزان', Decimal('0.030')), ('صدور فراخ', Decimal('0.080')),
        ]),
        ('سلطة جريك', [
            ('طماطم طازجة', Decimal('0.080')), ('خيار', Decimal('0.080')), ('جبنة فيتا', Decimal('0.050')),
        ]),
        # الإضافات
        ('فرنش فرايز', [
            ('بطاطس', Decimal('0.250')),
        ]),
        # الحلويات
        ('موز مقلي', [
            ('موز', Decimal('0.150')),
        ]),
    ]
    for menu_item_name_ar, lines in recipes:
        _link_recipe(menu_item_name_ar, lines)

    db.flush()
    print(f"  ✓ Inventory seeded ({len(ingredients)} ingredients) + {len(recipes)} real recipes across the restaurant menu")


def _seed_settings(db: Session) -> None:
    """إعدادات النظام الأساسية."""
    from app.modules.core.models import Setting, Branch

    branch = db.query(Branch).first()
    if not branch:
        return

    defaults = {
        "vat_percentage":               str(settings.VAT_PERCENTAGE),
        "service_charge_percentage":    str(settings.SERVICE_CHARGE_PERCENTAGE),
        "default_currency":             settings.DEFAULT_CURRENCY,
        "timezone":                     settings.TIMEZONE,
        "beach.capacity_max":           "200",
        "beach.price.adult":            "100",
        "beach.price.child":            "50",
        "beach.price.resident":         "70",
        "beach.price.towel":            "30",
        "no_show_policy":               "full_first_night",
        "no_show_deadline_hour":        "18",
        "discount_approval_threshold":  "500",
    }

    existing_keys = {
        r.key for r in db.query(Setting).filter(Setting.branch_id == branch.id).all()
    }

    for key, value in defaults.items():
        if key not in existing_keys:
            db.add(Setting(key=key, value=value, branch_id=branch.id))

    db.flush()
    print("  ✓ Default settings seeded")


def _seed_crm(db: Session) -> None:
    """⚠️ باج حقيقي كان هنا: موديول CRM كامل (leads/lead_sources/call_notes/
    campaigns/customers/opportunities/activities) كان بيرجع فاضي 100% في أي
    تثبيت جديد — مفيش أي seed خالص، رغم إن الـ API لكل الجداول دي اشتغل
    فعليًا (LeadSource/CallNote/GuestProfile اتوصلوا حديثًا). يعني أول ما مدير
    CRM يفتح الشاشة، هيلاقيها فاضية تمامًا من غير أي تفسير — نفس فئة باج HR
    (499fe5c) قبل كده بالظبط.

    بيانات توضيحية (illustrative) واقعية — مش سجلات عملاء حقيقية.
    Idempotent: لو فيه أي LeadSource للفرع بالفعل → يتجاهَل بالكامل."""
    from datetime import datetime, timedelta
    from app.modules.core.models import Branch
    from app.core.kernel.models.user import User
    from app.modules.crm.models import (
        Activity, CallNote, Campaign, Customer, LeadSource, Lead, Opportunity,
    )

    branch = db.query(Branch).first()
    if not branch:
        return
    if db.query(LeadSource).filter(LeadSource.branch_id == branch.id).first():
        return

    manager = db.query(User).filter(User.email == "manager@resortos.local").first()
    handler_id = manager.id if manager else db.query(User).first().id

    today = date.today()

    # ── Lead Sources ──────────────────────────────────────────────────────
    source_specs = [
        ("الموقع الإلكتروني", True),
        ("إحالة عميل", True),
        ("سوشيال ميديا", True),
        ("زيارة مباشرة", True),
        ("معرض سياحي", True),
        ("إعلان قديم (متوقف)", False),
    ]
    sources: dict[str, LeadSource] = {}
    for name, active in source_specs:
        src = LeadSource(branch_id=branch.id, name=name, is_active=active)
        db.add(src)
        db.flush()
        sources[name] = src

    # ── Customers ─────────────────────────────────────────────────────────
    customer_specs = [
        # (name, phone, email, nationality, segment, source, total_spent, visits, last_visit_days_ago)
        ("محمود عادل حلمي", "01011122233", "mahmoud.a@example.com", "مصري", "vip", "referral", "45200", 9, 5),
        ("Sarah Whitfield", "01122233344", "sarah.w@example.com", "بريطاني", "regular", "online", "3800", 2, 40),
        ("شركة النور للسياحة", "01233344455", "info@alnoor-travel.example", "مصري", "travel_agent", "corporate", "128500", 14, 12),
        ("ياسمين طارق سعد", "01344455566", "yasmin.t@example.com", "مصري", "corporate", "walk_in", "9600", 4, 20),
        ("Ahmed Reception Walk-in", None, None, "مصري", "regular", "walk_in", "0", 0, None),
        ("كريم فتحي البدوي", "01455566677", "karim.f@example.com", "مصري", "regular", "social_media", "2100", 1, 90),
    ]
    customers: dict[str, Customer] = {}
    for name, phone, email, nat, segment, source, spent, visits, days_ago in customer_specs:
        cust = Customer(
            branch_id=branch.id, full_name=name, phone=phone, email=email,
            nationality=nat, segment=segment, source=source,
            total_spent=Decimal(spent), visits_count=visits,
            last_visit=(today - timedelta(days=days_ago)) if days_ago is not None else None,
        )
        db.add(cust)
        db.flush()
        customers[name] = cust

    # عميل واحد على القائمة السوداء — لاختبار سيناريو الحظر الحقيقي
    blacklisted = Customer(
        branch_id=branch.id, full_name="عصام رجب فهمي", phone="01566677788",
        nationality="مصري", segment="regular", source="walk_in",
        total_spent=Decimal("1200"), visits_count=3,
        last_visit=today - timedelta(days=200),
        blacklisted=True, blacklist_reason="شيك بدون رصيد + سلوك عدواني تجاه الموظفين",
    )
    db.add(blacklisted)
    db.flush()

    # ── Leads (pipeline كامل: new → contacted → qualified → proposal → won/lost) ──
    lead_specs = [
        # (name, phone, email, nat, source_name_or_None, interest, stage, expected_value)
        ("عمر شريف نبيل", "01611122233", "omar.s@example.com", "مصري", "الموقع الإلكتروني", "timeshare", "new", "180000"),
        ("Isabella Conti", "01622233344", "isabella.c@example.com", "إيطالي", None, "booking", "new", "25000"),
        ("منال حسني عبده", "01633344455", "manal.h@example.com", "مصري", "سوشيال ميديا", "membership", "contacted", "15000"),
        ("طارق مجدي سيد", "01644455566", "tarek.m@example.com", "مصري", "إحالة عميل", "timeshare", "qualified", "220000"),
        ("Fatima Al-Rashid", "01655566677", "fatima.r@example.com", "إماراتي", "معرض سياحي", "leasing", "proposal", "95000"),
        ("رانيا كمال شوقي", "01666677788", "rania.k@example.com", "مصري", "زيارة مباشرة", "timeshare", "won", "310000"),
        ("حسام الدين فوزي", "01677788899", "hossam.f@example.com", "مصري", "الموقع الإلكتروني", "membership", "lost", "12000"),
    ]
    leads: dict[str, Lead] = {}
    for name, phone, email, nat, source_name, interest, stage, value in lead_specs:
        lead = Lead(
            branch_id=branch.id, full_name=name, phone=phone, email=email,
            nationality=nat,
            source_id=sources[source_name].id if source_name else None,
            interest=interest, stage=stage, assigned_to=handler_id,
            expected_value=Decimal(value),
            won_at=datetime.utcnow() - timedelta(days=3) if stage == "won" else None,
            lost_at=datetime.utcnow() - timedelta(days=7) if stage == "lost" else None,
            lost_reason="الميزانية غير متاحة حاليًا" if stage == "lost" else None,
        )
        db.add(lead)
        db.flush()
        leads[name] = lead

    # ── Call Notes — على أكتر من lead لعرض سجل مكالمات حقيقي ────────────────
    call_note_specs = [
        ("عمر شريف نبيل", "outbound", 8, "اتصال أول تعريفي بعرض التايم شير، مهتم بمعرفة التفاصيل", "interested", 2),
        ("طارق مجدي سيد", "outbound", 15, "شرح تفصيلي للعقد والأقساط، طلب وقت للتفكير", "callback", 1),
        ("طارق مجدي سيد", "inbound", 5, "اتصل يسأل عن حالة العرض المُرسل بالإيميل", "no_decision", 0),
        ("حسام الدين فوزي", "outbound", 6, "أبلغ إنه غير مهتم حاليًا بسبب الميزانية", "not_interested", 8),
    ]
    for lead_name, direction, duration, summary, outcome, days_ago in call_note_specs:
        db.add(CallNote(
            branch_id=branch.id, lead_id=leads[lead_name].id, direction=direction,
            duration_min=duration, summary=summary, outcome=outcome,
            called_by=handler_id,
            called_at=datetime.utcnow() - timedelta(days=days_ago),
        ))

    # ── Campaigns ─────────────────────────────────────────────────────────
    campaign_specs = [
        ("عروض الصيف 2026", "social_media", -60, -10, "50000", "72000", 18, "completed"),
        ("حملة التايم شير الخريفية", "email", -10, 20, "20000", "8500", 6, "active"),
        ("معرض السياحة القادم", "event", 15, 20, "35000", "0", 0, "planned"),
    ]
    for name, ctype, start_off, end_off, budget, revenue, leads_gen, status in campaign_specs:
        db.add(Campaign(
            branch_id=branch.id, name=name, campaign_type=ctype,
            start_date=today + timedelta(days=start_off),
            end_date=today + timedelta(days=end_off),
            budget=Decimal(budget), revenue_attributed=Decimal(revenue),
            leads_generated=leads_gen, status=status, created_by=handler_id,
        ))

    # ── Opportunities ─────────────────────────────────────────────────────
    db.add(Opportunity(
        branch_id=branch.id, customer_id=customers["محمود عادل حلمي"].id,
        title="تجديد عضوية VIP + وحدة تايم شير إضافية", product_type="timeshare",
        stage="negotiation", expected_value=Decimal("250000"), probability=60,
        assigned_to=handler_id, expected_close=today + timedelta(days=25),
    ))
    db.add(Opportunity(
        branch_id=branch.id, customer_id=customers["شركة النور للسياحة"].id,
        title="عقد إيجار مجموعات سياحية سنوي", product_type="leasing",
        stage="proposal", expected_value=Decimal("180000"), probability=40,
        assigned_to=handler_id, expected_close=today + timedelta(days=45),
    ))

    # ── Activities — بعضها متأخر عمدًا لاختبار get_overdue_activities ───────
    db.add(Activity(
        branch_id=branch.id, customer_id=customers["محمود عادل حلمي"].id,
        activity_type="follow_up", title="متابعة تليفونية لتجديد العضوية",
        due_date=today - timedelta(days=2), assigned_to=handler_id, status="pending",
    ))
    db.add(Activity(
        branch_id=branch.id, customer_id=customers["ياسمين طارق سعد"].id,
        activity_type="meeting", title="اجتماع لعرض باقة الشركات",
        due_date=today + timedelta(days=5), assigned_to=handler_id, status="pending",
    ))

    db.flush()
    print(f"  ✓ CRM seeded ({len(sources)} lead sources, {len(customers) + 1} customers, "
          f"{len(leads)} leads, {len(call_note_specs)} call notes, {len(campaign_specs)} campaigns)")


def _seed_inventory_categories(db: Session) -> None:
    """فئات المخزون الأساسية."""
    from app.modules.inventory.models import Category
    from app.modules.core.models import Branch

    branch = db.query(Branch).first()
    if not branch:
        return

    existing = db.query(Category).filter(Category.branch_id == branch.id).count()
    if existing:
        return

    cats = [
        ("Food Items",      "مواد غذائية"),
        ("Beverages",       "مشروبات"),
        ("Cleaning Supplies", "لوازم نظافة"),
        ("Beach Supplies",  "لوازم شاطئ"),
        ("Spare Parts",     "قطع غيار"),
        ("Kitchen Supplies", "مستلزمات مطبخ"),
        ("Furniture",       "أثاث ومفروشات"),
        ("Raw Materials",   "مواد خام"),
    ]
    for name, name_ar in cats:
        db.add(Category(name=name, name_ar=name_ar, branch_id=branch.id))
    db.flush()
    print(f"  ✓ Inventory categories seeded ({len(cats)})")


def _seed_hr_departments(db: Session) -> None:
    """الأقسام الوظيفية الأساسية."""
    from app.modules.hr.models import Department
    from app.modules.core.models import Branch
    from decimal import Decimal

    branch = db.query(Branch).first()
    if not branch:
        return

    existing = db.query(Department).filter(Department.branch_id == branch.id).count()
    if existing:
        return

    depts = [
        ("Management",     "الإدارة"),
        ("Reception",      "الاستقبال"),
        ("Restaurant",     "المطعم"),
        ("Cafe",           "الكافيه"),
        ("Beach",          "الشاطئ"),
        ("Rooms",          "الغرف"),
        ("Kitchen",        "المطبخ"),
        ("Maintenance",    "الصيانة"),
        ("Finance",        "الحسابات"),
        ("Human Resources", "الموارد البشرية"),
        ("Security",       "الأمن"),
        ("Housekeeping",   "النظافة"),
    ]
    for name, name_ar in depts:
        db.add(Department(name=name, name_ar=name_ar, branch_id=branch.id,
                          budget_limit=Decimal("0")))
    db.flush()
    print(f"  ✓ HR departments seeded ({len(depts)})")


def _seed_rate_plans(db: Session) -> None:
    """خطط أسعار الغرف الأساسية."""
    from app.modules.pms.models import RatePlan
    from app.modules.core.models import Branch
    from decimal import Decimal
    from datetime import date

    branch = db.query(Branch).first()
    if not branch:
        return

    existing = db.query(RatePlan).filter(RatePlan.branch_id == branch.id).count()
    if existing:
        return

    year = date.today().year
    plans = [
        ("Standard Rate",        "السعر القياسي",            Decimal("1.0000"), 1),
        ("Weekend Rate",         "سعر نهاية الأسبوع",         Decimal("1.2000"), 1),
        ("Summer Season",        "موسم الصيف",               Decimal("1.4000"), 2),
        ("Long Stay Discount",   "خصم الإقامة الطويلة",       Decimal("0.8500"), 7),
    ]
    for name, name_ar, multiplier, min_nights in plans:
        db.add(RatePlan(
            branch_id=branch.id,
            name=name, name_ar=name_ar,
            rate_multiplier=multiplier,
            valid_from=date(year, 1, 1),
            valid_until=date(year, 12, 31),
            min_nights=min_nights,
            is_active=True,
        ))
    db.flush()
    print(f"  ✓ Rate plans seeded ({len(plans)})")


def _seed_suppliers_and_purchase_orders(db: Session) -> None:
    """⚠️ الموردين وأوامر الشراء (inventory.Supplier/PurchaseOrder، اتضافوا
    2026-07-14) كان مفيهمش أي بيانات seed خالص — يعني شاشة "الموردين"
    وتاب "أوامر الشراء" في InventoryView.vue كانت هتفتح فاضية 100% بأول
    تشغيل، نفس فئة فجوة الـ seed الموثّقة قبل كده (rooms/dining_tables/
    b2b/beach_locations). 4 موردين مصريين واقعيين (توزيع أغذية/مشروبات/
    مستلزمات نظافة/قطع صيانة) + 5 أوامر شراء عبر كل الحالات (draft/sent/
    partial/received/cancelled) — مش صفوف مُدرَجة مباشرة، بل عن طريق
    services.create_purchase_order/receive_purchase_order الحقيقيين عشان
    (أ) StockMovement حقيقي يترحّل زي ما هيحصل في التشغيل الفعلي، و(ب)
    قيد محاسبي حقيقي Dr مخزون/Cr موردين يترحّل (services._post_purchase_
    receipt_journal، إصلاح باج حقيقي كان هنا — راجع تعليقه) — عشان
    الميزانية العمومية/ميزان المراجعة يبقى فيهم عمق حقيقي بدل ما يفضلوا
    شبه فاضيين، نفس فلسفة _seed_beach_locations (بيع حقيقي بقيد محاسبي)
    مش فلسفة _seed_timeshare_contracts/_seed_lease_contracts (عمدًا من
    غير قيد — عقود كبيرة مُلفَّقة لعملاء وهميين هتشوّه التقارير المالية
    بمبالغ كبيرة، مختلف تمامًا عن أمر شراء تشغيلي عادي بمبالغ واقعية)."""
    from datetime import timedelta
    from app.modules.inventory.models import Product, Supplier, Warehouse
    from app.modules.inventory.schemas import (
        PurchaseOrderCreate, PurchaseOrderItemCreate, ReceiveItemsRequest, SupplierCreate,
    )
    from app.modules.inventory.services import (
        create_purchase_order, create_supplier, receive_purchase_order,
    )
    from app.modules.core.models import Branch

    branch = db.query(Branch).first()
    if not branch:
        return
    if db.query(Supplier).filter(Supplier.branch_id == branch.id).first():
        return

    warehouse = db.query(Warehouse).filter(Warehouse.branch_id == branch.id).first()
    products = db.query(Product).filter(Product.branch_id == branch.id).order_by(Product.id).all()
    if not warehouse or len(products) < 4:
        return  # لازم _seed_inventory_products_full يشتغل قبل كده (مسجّل قبله في seed_all)

    supplier_specs = [
        ("توريدات المائدة الذهبية", "Golden Table Supplies", "أحمد فتحي", "0693456789",
         "sales@goldentable-eg.com", "طريق الأنبا شنودة، شرم الشيخ", "food", 30, Decimal("50000")),
        ("مشروبات البحر الأحمر", "Red Sea Beverages Co.", "منى سامي", "0693567890",
         "orders@redseabeverages.com", "المنطقة الصناعية، شرم الشيخ", "beverage", 15, Decimal("30000")),
        ("النظافة المتكاملة للفنادق", "Integrated Hotel Cleaning", "كريم عادل", "01123456780",
         "info@ihc-eg.com", "القاهرة الجديدة، القاهرة", "cleaning", 0, None),
        ("قطع غيار المعدات الفندقية", "Hospitality Parts Egypt", "سامح رفعت", "01098765430",
         None, "مدينة نصر، القاهرة", "maintenance", 45, Decimal("20000")),
    ]
    suppliers: list[Supplier] = []
    for name, name_en, contact, phone, email, address, category, terms, credit in supplier_specs:
        s = create_supplier(db, SupplierCreate(
            branch_id=branch.id, name=name_en, name_ar=name,
            contact_person=contact, phone=phone, email=email, address=address,
            category=category, payment_terms_days=terms, credit_limit=credit,
        ))
        suppliers.append(s)
    db.flush()

    today = date.today()

    def _po(supplier: Supplier, items: list[tuple], ordered_days_ago: int) -> "object":
        return create_purchase_order(db, PurchaseOrderCreate(
            branch_id=branch.id, supplier_id=supplier.id,
            ordered_at=today - timedelta(days=ordered_days_ago),
            expected_at=today - timedelta(days=ordered_days_ago - 5),
            items=[PurchaseOrderItemCreate(product_id=p.id, ordered_qty=qty, unit_cost=p.cost_price or Decimal("10"))
                   for p, qty in items],
        ))

    # (1) draft — لسه ما اترسلش للمورد، مفيش أي أثر على المخزون/الدفاتر
    _po(suppliers[0], [(products[0], Decimal("30")), (products[1], Decimal("200"))], ordered_days_ago=1)

    # (2) sent — اترسل للمورد، لسه منتظر التسليم (مفيش حالة "sent" service-level
    # فعلية في النظام، بس الـ status نفسه معرّف في الموديل — نفس نمط seed
    # بيانات تايم شير "suspended" اللي اتحطّت مباشرة برضو)
    po_sent = _po(suppliers[1], [(products[2], Decimal("20"))], ordered_days_ago=3)
    po_sent.status = "sent"

    # (3) partial — نص الكمية المطلوبة اتسلّمت بس (StockMovement + قيد محاسبي حقيقي)
    po_partial = _po(suppliers[0], [(products[3], Decimal("40")), (products[4], Decimal("15"))], ordered_days_ago=7)
    receive_purchase_order(db, po_partial.id, ReceiveItemsRequest(
        items=[{"item_id": po_partial.items[0].id, "received_qty": "20.00"}],
        warehouse_id=warehouse.id, received_at=today - timedelta(days=5),
    ), received_by=1)

    # (4) received — استلام كامل (كل الأصناف)، أقدم أمر عشان يبان في تاريخ الحركات
    po_received = _po(suppliers[1], [(products[5], Decimal("10")), (products[0], Decimal("15"))], ordered_days_ago=14)
    receive_purchase_order(db, po_received.id, ReceiveItemsRequest(
        items=[{"item_id": item.id, "received_qty": str(item.ordered_qty)} for item in po_received.items],
        warehouse_id=warehouse.id, received_at=today - timedelta(days=12),
    ), received_by=1)

    # (5) cancelled — اتلغى قبل أي استلام
    po_cancelled = _po(suppliers[2], [(products[1], Decimal("500"))], ordered_days_ago=2)
    po_cancelled.status = "cancelled"

    db.flush()
    print(f"  ✓ Suppliers & purchase orders seeded ({len(suppliers)} suppliers, "
          f"5 POs across draft/sent/partial/received/cancelled — real StockMovement + AP journal entries)")


# ── CLI Entry Point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv
    with SessionLocal() as db:
        seed_all(db, reset=reset_flag)
