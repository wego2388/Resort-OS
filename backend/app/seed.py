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

from sqlalchemy.orm import Session

from app.core.database import SessionLocal, Base, get_engine
from app.core.config import settings


def seed_all(db: Session, *, reset: bool = False) -> None:
    """نقطة الدخول الرئيسية."""
    if reset and settings.ENVIRONMENT == "production":
        raise RuntimeError("❌ لا يمكن reset في production")

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
    _seed_settings(db)
    _seed_leave_types(db)
    _seed_employees(db)
    _seed_chart_of_accounts(db)
    _seed_room_types(db)
    _seed_rooms(db)
    _seed_timeshare_units(db)
    _seed_timeshare_contracts(db)
    _seed_lease_contracts(db)
    _seed_menus(db)
    _seed_dining_tables(db)
    _seed_crm(db)

    db.commit()
    print("✅ Seed complete.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _import_all_models() -> None:
    """يستورد كل الـ models لتسجيلها في Base.metadata."""
    import app.modules.core.models         # noqa: F401
    import app.modules.finance.models      # noqa: F401
    import app.modules.hr.models           # noqa: F401
    import app.modules.restaurant.models   # noqa: F401
    import app.modules.pms.models          # noqa: F401
    import app.modules.beach.models        # noqa: F401
    import app.modules.maintenance.models  # noqa: F401
    import app.modules.crm.models          # noqa: F401
    import app.modules.hub.models          # noqa: F401
    import app.modules.inventory.models    # noqa: F401
    import app.modules.timeshare.models    # noqa: F401
    import app.modules.leasing.models      # noqa: F401
    import app.modules.cafe.models         # noqa: F401
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
    """يُنشئ super_admin إذا لم يوجد — password من .env أو default."""
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
    print("  ✓ Super admin created (admin@resortos.local / change password immediately!)")


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
        print(f"  ✓ Demo accounts seeded ({created} roles, password: Demo@123456)")


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
    الفاضية اللي اتصلحت قبل كده). ازرع فريق واقعي صغير (7 موظفين، أقسام
    مختلفة) + بدلات/أنواع جزاءات/رصيد إجازات/سجل حضور/طلب إجازة معلّق
    عشان الشاشة تفتح بحالة واقعية مش فاضية."""
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
        ("EMP-004", "ياسمين ماهر",        "موظفة استقبال",       "الاستقبال",  Decimal("5200.00"), today - timedelta(days=400),  date(1998, 1, 30), None),
        ("EMP-005", "سامح جلال",          "شيف",                "المطبخ",     Decimal("11000.00"), today - timedelta(days=2200), date(1985, 5, 9), None),
        ("EMP-006", "هدى عزت",            "عاملة تدبير منزلي",   "التدبير المنزلي", Decimal("3400.00"), today - timedelta(days=180), date(2000, 9, 17), None),
        ("EMP-007", "مينا رفعت",          "منقذ شاطئ",           "الشاطئ",     Decimal("4200.00"), today - timedelta(days=545), date(1994, 2, 25), None),
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

    # ── سجل حضور آخر 5 أيام لموظفَين مرتبطين بحساب دخول ──────────────────
    for emp in (employees["EMP-001"], employees["EMP-002"]):
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
    print(f"  ✓ Employees seeded ({len(employees)}, linked to 3 demo login accounts)")


def _seed_chart_of_accounts(db: Session) -> None:
    """حسابات الرواتب والتأمينات الضرورية للقيود."""
    try:
        from app.modules.finance.models import Account
        from app.modules.core.models import Branch
    except ImportError:
        return

    branch = db.query(Branch).first()
    if not branch:
        return

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
        {"code": "1200", "name": "مخزون البضاعة",               "account_type": "asset"},
        {"code": "5200", "name": "تكلفة البضاعة المباعة (COGS)", "account_type": "expense"},
        {"code": "2300", "name": "إيرادات مؤجَّلة (تايم شير)",  "account_type": "liability"},
        {"code": "1260", "name": "ذمم مستأجرين (إيجارات)",      "account_type": "asset"},
        {"code": "2150", "name": "تأمينات مستأجرين",            "account_type": "liability"},
        {"code": "4500", "name": "إيرادات إيجارات تجارية",      "account_type": "revenue"},
        {"code": "5300", "name": "مصروفات مرافق (كهرباء/مياه/غاز)", "account_type": "expense"},
        {"code": "1110", "name": "حساب بنكي",                     "account_type": "asset"},
        {"code": "5500", "name": "مصروف إهلاك الأصول الثابتة",     "account_type": "expense"},
        {"code": "1590", "name": "مجمّع إهلاك الأصول الثابتة",     "account_type": "asset"},
    ]

    existing_codes = {
        r.code for r in db.query(Account).filter(Account.branch_id == branch.id).all()
    }
    added = 0
    for acc in accounts:
        if acc["code"] not in existing_codes:
            db.add(Account(branch_id=branch.id, is_active=True, **acc))
            added += 1
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

    db.flush()
    print(f"  ✓ Timeshare contracts seeded ({created} illustrative sample customers — not real records)")


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


def _seed_dining_tables(db: Session, branch_id: int | None = None) -> None:
    """⚠️ نفس ملاحظة _seed_rooms — ترقيم منطقي افتراضي مش أرقام طاولات حقيقية
    موثّقة. قبل هذا التعديل كان جدول dining_tables (مطعم) و cafe_tables (كافيه)
    فاضيين تمامًا (0 صف) — يعني شاشة "الطاولات" بتاعة الجرسون كانت بتعرض
    "لا توجد طاولات مسجّلة لهذا الفرع" دايمًا، فمفيش أي طريقة حقيقية لعمل أوردر
    dine_in مربوط بطاولة فعلية (اتكشف أثناء اختبار حي لمسار الجرسون الكامل —
    نفس فئة باج rooms الفاضية اللي اتصلحت قبل كده). ازرع ترقيم منطقي متسلسل
    دلوقتي: 12 طاولة مطعم (1-10 لـ4 أفراد، 11-12 لـ8 أفراد لمجموعات كبيرة)
    + 8 طاولات كافيه (1-8 لـ2 فرد).

    `branch_id` اختياري — للتستات بس (عشان تحدد فرع بعينه بدل الاعتماد على
    'أول فرع في الداتابيز' اللي مش مضمون يكون معزول في session-scoped test DB
    فيها فروع تانية من تستات HTTP بتعمل commit حقيقي). الاستخدام الحقيقي من
    seed_all() مبيبعتش الحجة دي خالص — بيعتمد على أول فرع زي باقي دوال الـ seed."""
    from app.modules.restaurant.models import DiningTable
    from app.modules.cafe.models import CafeTable
    from app.modules.core.models import Branch

    branch = db.query(Branch).filter(Branch.id == branch_id).first() if branch_id else db.query(Branch).first()
    if not branch:
        return

    if not db.query(DiningTable).filter(DiningTable.branch_id == branch.id).first():
        total = 0
        for i in range(1, 11):
            db.add(DiningTable(branch_id=branch.id, table_number=str(i), capacity=4))
            total += 1
        for i in range(11, 13):
            db.add(DiningTable(branch_id=branch.id, table_number=str(i), capacity=8))
            total += 1
        db.flush()
        print(f"  ✓ Restaurant tables seeded ({total} tables — logical default numbering, not verified real numbers)")

    if not db.query(CafeTable).filter(CafeTable.branch_id == branch.id).first():
        total = 0
        for i in range(1, 9):
            db.add(CafeTable(branch_id=branch.id, table_number=str(i), capacity=2))
            total += 1
        db.flush()
        print(f"  ✓ Cafe tables seeded ({total} tables — logical default numbering, not verified real numbers)")


def _seed_menus(db: Session) -> None:
    """قوائم مطعم وكافيه حقيقية — منقولة من المحتوى التسويقي الحقيقي للمنتجع
    (/home/wego/projects/elkheima-beach-resort-marketing/02_products/
    RESTAURANT_MENU.json + MENU_RESTAURANT_CAFE.csv) بدل قوائم فاضية تمامًا —
    كانت 0 عنصر في كل من المطعم والكافيه قبل كده (لاحظه وكيل الـ QA أثناء محاولة
    اختبار مسار طلب حقيقي في POS المطعم). الأسعار جنيه مصري."""
    try:
        from app.modules.restaurant.models import MenuCategory, MenuItem
        from app.modules.cafe.models import CafeCategory, CafeItem
        from app.modules.core.models import Branch
    except ImportError:
        return

    branch = db.query(Branch).first()
    if not branch:
        return

    # ── مطعم (fine dining) ── من RESTAURANT_MENU.json → categories.restaurant
    if not db.query(MenuItem).filter(MenuItem.branch_id == branch.id).first():
        cat = db.query(MenuCategory).filter(MenuCategory.branch_id == branch.id).first()
        if not cat:
            cat = MenuCategory(branch_id=branch.id, name="Restaurant", name_ar="مطعم")
            db.add(cat)
            db.flush()

        restaurant_items = [
            # (name_en, name_ar, price, station)
            ('Grilled Sea Bass', 'سمك قاروص مشوي', Decimal('85.0'), 'grill'),
            ('Mixed Grill Platter', 'مشويات مشكلة', Decimal('120.0'), 'grill'),
            ('Seafood Pasta', 'باستا بالمأكولات البحرية', Decimal('75.0'), 'hot'),
            ('Arabic Mezze Set', 'سيت مقبلات عربية', Decimal('55.0'), 'cold'),
        ]
        for name, name_ar, price, station in restaurant_items:
            db.add(MenuItem(branch_id=branch.id, category_id=cat.id, name=name, name_ar=name_ar,
                             price=price, station=station))
        db.flush()
        print(f"  ✓ Restaurant menu seeded ({len(restaurant_items)} items)")

    # ── كافيه ── من MENU_RESTAURANT_CAFE.csv (8 أقسام) + RESTAURANT_MENU.json → categories.cafe
    if not db.query(CafeItem).filter(CafeItem.branch_id == branch.id).first():
        cafe_categories = [
            ('Pizza', 'بيتزا'),
            ('Pasta', 'باستا'),
            ('Salads', 'سلاطات'),
            ('Desserts', 'حلويات'),
            ('Sandwiches', 'ساندوتش'),
            ('Hawawshi & Grill', 'حواوشي وجريل'),
            ('Extras', 'إضافات'),
            ('Breakfast & Brunch', 'فطار وبرانش'),
            ('Café', 'كافيه'),
        ]
        cat_map: dict[str, int] = {}
        for i, (name_en, name_ar) in enumerate(cafe_categories):
            c = CafeCategory(branch_id=branch.id, name=name_en, name_ar=name_ar, sort_order=i)
            db.add(c)
            db.flush()
            cat_map[name_ar] = c.id

        cafe_items = [
            # (category_ar, name_en, name_ar, price)
            ('بيتزا', 'Margherita', 'مارجريتا', Decimal('220')),
            ('بيتزا', 'Four Cheese Quattro Formaggi', 'كواترو فورماجي', Decimal('345')),
            ('بيتزا', 'Four Seasons Quattro Stagioni', 'كواترو استاجوني', Decimal('345')),
            ('بيتزا', 'Salami Salame', 'سلامي', Decimal('315')),
            ('بيتزا', 'Chicken Pollo', 'تشيكن', Decimal('315')),
            ('بيتزا', 'Sausage Salsiccia', 'سجق', Decimal('315')),
            ('بيتزا', 'Naples Napoli', 'نابولي', Decimal('280')),
            ('بيتزا', 'Tuna Tonno', 'تونة', Decimal('315')),
            ('بيتزا', 'Shrimp Gamberetti', 'جمبري', Decimal('420')),
            ('بيتزا', 'Fruits of the Sea Frutti del Mare', 'فروت دي ماري', Decimal('440')),
            ('بيتزا', 'Pizza ElKeima', 'بيتزا الخيمة', Decimal('375')),
            ('باستا', 'Arrabbiata', 'ارابياتا', Decimal('190')),
            ('باستا', 'Quattro Formaggi Pasta', 'كواترو فورماجي', Decimal('250')),
            ('باستا', 'Pasta Tuna', 'باستا تونة', Decimal('250')),
            ('باستا', 'Chicken Pasta', 'تشيكن', Decimal('280')),
            ('باستا', 'Pesto', 'بيستو', Decimal('250')),
            ('باستا', 'Carbonara', 'كاربونارا', Decimal('280')),
            ('باستا', 'Lasagna', 'لازانيا', Decimal('190')),
            ('باستا', 'Aglio Olio', 'اليو اوليو', Decimal('250')),
            ('باستا', 'Frutti del Mare Pasta', 'فروت دي ماري', Decimal('405')),
            ('باستا', 'Shrimp Pasta', 'جمبري', Decimal('375')),
            ('سلاطات', 'Tuna Salad', 'تونة سلاط', Decimal('250')),
            ('سلاطات', 'Greece Salad', 'جريك سلاط', Decimal('190')),
            ('سلاطات', 'Caesar Salad', 'سيزر سلاط', Decimal('250')),
            ('سلاطات', 'Sea Food Salad', 'سيفود سلاط', Decimal('405')),
            ('سلاطات', 'Shrimp Salad', 'جمبري سلاط', Decimal('440')),
            ('سلاطات', 'French Fries', 'بوم فريت', Decimal('115')),
            ('حلويات', 'Cheese Cake', 'شيز كيك', Decimal('140')),
            ('حلويات', 'Om Ali', 'ام علي', Decimal('140')),
            ('حلويات', 'Molten Cake', 'مولتن كيك', Decimal('155')),
            ('ساندوتش', 'Zinger Sandwich', 'زينجر ساندوتش', Decimal('175')),
            ('ساندوتش', 'Pane', 'بانيه', Decimal('145')),
            ('ساندوتش', 'Burger', 'برجر', Decimal('145')),
            ('ساندوتش', 'Mexico', 'ميكسيكان', Decimal('145')),
            ('ساندوتش', 'Beef Fajita', 'فاهيتا لحم', Decimal('190')),
            ('ساندوتش', 'Chicken Fajita', 'فاهيتا فراخ', Decimal('175')),
            ('حواوشي وجريل', 'Classic Hawawshi', 'حواوشي كلاسيك', Decimal('95')),
            ('حواوشي وجريل', 'Special Hawawshi', 'حواوشي سبيشال', Decimal('215')),
            ('حواوشي وجريل', 'Al-Kheima Hawawshi', 'حواوشي الخيمة', Decimal('135')),
            ('حواوشي وجريل', 'Sausage Sandwich', 'ساندوتش سجق', Decimal('85')),
            ('حواوشي وجريل', 'Special Sausage', 'سجق سبيشال', Decimal('185')),
            ('حواوشي وجريل', 'Liver Sandwich', 'ساندوتش كبدة', Decimal('75')),
            ('إضافات', 'Rouabi Fries', 'روابي فريز', Decimal('110')),
            ('إضافات', 'Romani Cheese', 'جبنة رومي', Decimal('75')),
            ('إضافات', 'Plain Fries', 'فريز عادي', Decimal('85')),
            ('فطار وبرانش', 'Classic Breakfast', 'فطار كلاسيك', Decimal('300')),
            ('فطار وبرانش', 'Savory Deluxe Set', 'سيفوري ديلوكس', Decimal('400')),
            ('كافيه', 'Cappuccino', 'كابتشينو', Decimal('18.0')),
            ('كافيه', 'Fresh Orange Juice', 'عصير برتقال طازج', Decimal('22.0')),
            ('كافيه', 'Chocolate Cake', 'كيك شوكولاتة', Decimal('35.0')),
            ('كافيه', 'Arabic Coffee', 'قهوة عربية', Decimal('15.0')),
            ('كافيه', 'Morning Bliss Package', 'باقة الصباح المنعشة', Decimal('85.0')),
            ('كافيه', 'Sea Breeze Coffee', 'قهوة نسيم البحر', Decimal('45.0')),
            ('كافيه', 'Sunset Signature Drink', 'مشروب الغروب المميز', Decimal('120.0')),
            ('كافيه', 'Fresh Juice Bar', 'بار العصائر الطازجة', Decimal('50.0')),
            ('كافيه', 'Ice Cream Delight', 'متعة الآيس كريم', Decimal('60.0')),
            ('كافيه', 'Smoothie Bowl', 'سموذي بول صحي', Decimal('95.0')),
            ('كافيه', 'Premium Hookah Lounge', 'شيشة فاخرة مع جلسة', Decimal('180.0')),
            ('كافيه', 'VIP Shisha Experience', 'تجربة الشيشة VIP', Decimal('350.0')),
            ('كافيه', "Couple's Chill Package", 'باقة الاسترخاء للأزواج', Decimal('400.0')),
        ]
        for cat_ar, name, name_ar, price in cafe_items:
            db.add(CafeItem(branch_id=branch.id, category_id=cat_map[cat_ar], name=name, name_ar=name_ar, price=price))
        db.flush()
        print(f"  ✓ Cafe menu seeded ({len(cafe_items)} items across {len(cafe_categories)} categories)")


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


# ── CLI Entry Point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv
    with SessionLocal() as db:
        seed_all(db, reset=reset_flag)
