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
    _seed_demo_accounts(db)
    _seed_social_insurance(db)
    _seed_tax_brackets(db)
    _seed_settings(db)
    _seed_leave_types(db)
    _seed_chart_of_accounts(db)
    _seed_room_types(db)
    _seed_menus(db)

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


# ── CLI Entry Point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv
    with SessionLocal() as db:
        seed_all(db, reset=reset_flag)
