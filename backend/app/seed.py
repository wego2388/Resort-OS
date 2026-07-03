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
from datetime import date

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
    _seed_social_insurance(db)
    _seed_tax_brackets(db)
    _seed_settings(db)
    _seed_leave_types(db)
    _seed_chart_of_accounts(db)
    _seed_room_types(db)

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
        name="WegoSharm Resort",
        name_ar="منتجع ويغو شرم",
        code="WSR-001",
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


# ── CLI Entry Point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv
    with SessionLocal() as db:
        seed_all(db, reset=reset_flag)
