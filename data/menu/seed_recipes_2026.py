"""
data/menu/seed_recipes_2026.py  —  SELF-CONTAINED VERSION
──────────────────────────────────────────────────────────────────────────────
وصفات (Recipe/BOM) واقعية للمنيو الجديد 2026.
كل الوصفات مدمجة في ملف واحد — جاهز للنسخ مباشرة لـ backend/app/

الكميات بالكيلوجرام إلا البيض (قطعة) والمعبآت (علبة).
Food Cost % المستهدف:
  - مطعم (أطباق): 25–32%
  - مشروبات/كافيه: 12–20%

HOW TO APPLY:
  cp data/menu/seed_recipes_2026.py backend/app/seed_recipes_2026.py

  from app.seed_recipes_2026 import seed_recipes_2026
  from app.core.database import SessionLocal
  db = SessionLocal()
  seed_recipes_2026(db)
  db.commit()
  db.close()

IDEMPOTENT: يحذف recipe lines القديمة ويعيد كتابتها — آمن للتشغيل مرات متعددة.
"""
from __future__ import annotations
from decimal import Decimal as D
from sqlalchemy.orm import Session


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def seed_recipes_2026(db: Session) -> None:
    """نقطة الدخول الرئيسية — استدعِها وبعدين db.commit()"""
    print("▶ seed_recipes_2026: starting...")
    _seed_restaurant_recipes_2026(db)
    _seed_cafe_recipes_2026(db)
    db.flush()
    print("✓ seed_recipes_2026: done. Call db.commit() to persist.")


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _get_maps(db: Session, outlet_type: str):
    from app.modules.dining.models import DiningItem, Outlet
    from app.modules.inventory.models import Product
    from app.modules.core.models import Branch
    branch = db.query(Branch).first()
    outlet = db.query(Outlet).filter(
        Outlet.branch_id == branch.id, Outlet.outlet_type == outlet_type
    ).first()
    if not outlet:
        raise RuntimeError(f"Outlet \'{outlet_type}\' not found — run seed first.")
    prods = {p.sku: p for p in db.query(Product).all()}
    items = {i.name: i for i in db.query(DiningItem).filter(DiningItem.outlet_id == outlet.id).all()}
    return prods, items, outlet.id


def _apply_recipes(db: Session, outlet_type: str,
                   recipes: list[tuple[str, list[tuple[str, D]]]]) -> None:
    from app.modules.dining.models import DiningItemRecipeLine
    prods, items, outlet_id = _get_maps(db, outlet_type)
    inserted = skipped_item = skipped_sku = 0
    for item_name, lines in recipes:
        item = items.get(item_name)
        if item is None:
            skipped_item += 1
            print(f"    WARN item not found: \'{item_name}\'")
            continue
        db.query(DiningItemRecipeLine).filter(
            DiningItemRecipeLine.item_id == item.id
        ).delete()
        for sku, qty in lines:
            prod = prods.get(sku)
            if prod is None:
                skipped_sku += 1
                print(f"    WARN SKU not found: \'{sku}\' (item \'{item_name}\')")
                continue
            db.add(DiningItemRecipeLine(item_id=item.id, product_id=prod.id, quantity_per_unit=qty))
        inserted += 1
    db.flush()
    print(f"  ✓ {outlet_type}: {inserted} items written, {skipped_item} items skipped, {skipped_sku} SKUs skipped")


# ══════════════════════════════════════════════════════════════════════════════
# RESTAURANT RECIPES — PART 1: Starters + Sandwiches + Main Course
# ══════════════════════════════════════════════════════════════════════════════

Restaurant recipes part 1: Starters + Sandwiches + Main Course
"""

STARTERS = [
    # بطاطس حارة — 200g بطاطس + زيت + بهارات + كزبرة
    ("Spicy Potato", [
        ("POTATO",    D("0.200")),
        ("VEG-OIL",   D("0.040")),
        ("MIXED-SP",  D("0.008")),
        ("CORIANDER", D("0.005")),
        ("SALT",      D("0.003")),
    ]),
    # أجنحة دجاج 8 قطع — ~400g جناح + تتبيلة
    ("Chicken Wings", [
        ("CHKN-BRS",  D("0.400")),
        ("FLOUR",     D("0.040")),
        ("MIXED-SP",  D("0.012")),
        ("GARLIC",    D("0.010")),
        ("VEG-OIL",   D("0.060")),
        ("SALT",      D("0.004")),
        ("LEMON",     D("0.030")),
    ]),
    # بروشيتا 2 قطعة — خبز تورتيلا + طماطم + ثوم + زيت زيتون
    ("Bruschetta", [
        ("BREAD-SND", D("2")),
        ("TOMATO",    D("0.080")),
        ("GARLIC",    D("0.008")),
        ("OLIVE-OIL", D("0.015")),
        ("SALT",      D("0.002")),
    ]),
    # بطاطس مقلية — 250g بطاطس خام
    ("Chips", [
        ("POTATO",   D("0.250")),
        ("VEG-OIL",  D("0.080")),
        ("SALT",     D("0.004")),
    ]),
]

SANDWICHES = [
    # شيش طاووق — 200g دجاج + خبز تورتيلا + إضافات
    ("Shish Tawook Sandwich", [
        ("CHKN-BRS",  D("0.200")),
        ("BREAD-SND", D("1")),
        ("LETTUCE",   D("0.030")),
        ("TOMATO",    D("0.040")),
        ("GARLIC",    D("0.010")),
        ("MAYO",      D("0.020")),
        ("MIXED-SP",  D("0.008")),
        ("LEMON",     D("0.020")),
        ("VEG-OIL",   D("0.015")),
    ]),
    # شاورما دجاج — 180g دجاج + خبز + مخللات
    ("Chicken Shawarma Sandwich", [
        ("CHKN-BRS",  D("0.180")),
        ("BREAD-SND", D("1")),
        ("LETTUCE",   D("0.030")),
        ("TOMATO",    D("0.040")),
        ("GARLIC",    D("0.010")),
        ("MAYO",      D("0.015")),
        ("MIXED-SP",  D("0.008")),
        ("VEG-OIL",   D("0.015")),
    ]),
    # كفتة — 180g لحم مفروم + خبز
    ("Kofta Sandwich", [
        ("GRD-BEEF",  D("0.180")),
        ("BREAD-SND", D("1")),
        ("TOMATO",    D("0.040")),
        ("ONION",     D("0.030")),
        ("MIXED-SP",  D("0.010")),
        ("TAHINI",    D("0.020")),
        ("SALT",      D("0.003")),
    ]),
    # فاهيتا — 170g دجاج + فلفل + خبز تورتيلا
    ("Fajita Sandwich", [
        ("CHKN-BRS",  D("0.170")),
        ("BREAD-SND", D("1")),
        ("ONION",     D("0.040")),
        ("TOMATO",    D("0.030")),
        ("MAYO",      D("0.025")),
        ("CHED-CHSE", D("0.030")),
        ("MIXED-SP",  D("0.008")),
        ("VEG-OIL",   D("0.015")),
    ]),
    # دجاج كريسبي — 180g دجاج + بانكو + خبز
    ("Chicken Crispy Sandwich", [
        ("CHKN-BRS",  D("0.180")),
        ("BREAD-SND", D("1")),
        ("PANKO",     D("0.040")),
        ("FLOUR",     D("0.030")),
        ("EGGS",      D("1")),
        ("VEG-OIL",   D("0.080")),
        ("LETTUCE",   D("0.025")),
        ("TOMATO",    D("0.030")),
        ("MAYO",      D("0.025")),
    ]),
    # مكسيكان — 170g دجاج + فلفل ألوان + خبز
    ("Mexican Sandwich", [
        ("CHKN-BRS",  D("0.170")),
        ("BREAD-SND", D("1")),
        ("ONION",     D("0.050")),
        ("MIXED-SP",  D("0.008")),
        ("VEG-OIL",   D("0.015")),
        ("GARLIC",    D("0.008")),
    ]),
    # كريستال — دجاج + بطاطس مقلية + خبز
    ("Crystal Sandwich", [
        ("CHKN-BRS",  D("0.160")),
        ("BREAD-SND", D("1")),
        ("POTATO",    D("0.150")),
        ("VEG-OIL",   D("0.060")),
        ("LETTUCE",   D("0.025")),
        ("GARLIC",    D("0.008")),
        ("MAYO",      D("0.020")),
        ("SALT",      D("0.003")),
    ]),
]

MAIN_COURSE = [
    # صدر دجاج مشوي — 280g دجاج + خضار مشوية
    ("Grilled Chicken Breast", [
        ("CHKN-BRS",  D("0.280")),
        ("OLIVE-OIL", D("0.020")),
        ("GARLIC",    D("0.010")),
        ("LEMON",     D("0.040")),
        ("MIXED-SP",  D("0.010")),
        ("TOMATO",    D("0.060")),
        ("CUCUMBER",  D("0.040")),
        ("LETTUCE",   D("0.040")),
        ("SALT",      D("0.003")),
    ]),
    # صدر دجاج بصوص المشروم — 280g دجاج + مشروم + كريمة
    ("Chicken Breast with Mushroom Sauce", [
        ("CHKN-BRS",  D("0.280")),
        ("MUSHROOM",  D("0.100")),
        ("CREAM",     D("0.080")),
        ("BUTTER",    D("0.020")),
        ("GARLIC",    D("0.008")),
        ("MIXED-SP",  D("0.008")),
        ("SALT",      D("0.003")),
    ]),
    # دجاجة مشوية كاملة — ~900g دجاج كامل
    ("Grilled Whole Chicken", [
        ("CHKN-BRS",  D("0.900")),
        ("OLIVE-OIL", D("0.030")),
        ("GARLIC",    D("0.015")),
        ("LEMON",     D("0.060")),
        ("MIXED-SP",  D("0.015")),
        ("SALT",      D("0.005")),
        ("LETTUCE",   D("0.060")),
        ("TOMATO",    D("0.060")),
        ("RICE-RAW",  D("0.100")),
    ]),
    # نصف دجاجة مشوية
    ("Grilled Half Chicken", [
        ("CHKN-BRS",  D("0.480")),
        ("OLIVE-OIL", D("0.020")),
        ("GARLIC",    D("0.010")),
        ("LEMON",     D("0.040")),
        ("MIXED-SP",  D("0.010")),
        ("SALT",      D("0.004")),
        ("LETTUCE",   D("0.040")),
        ("TOMATO",    D("0.040")),
        ("RICE-RAW",  D("0.080")),
    ]),
    # إسكالوب بانيه — 200g لحم بانيه + بطاطس
    ("Escalope Panne & Chips", [
        ("BEEF-FIL",  D("0.200")),
        ("PANKO",     D("0.040")),
        ("FLOUR",     D("0.030")),
        ("EGGS",      D("1")),
        ("VEG-OIL",   D("0.080")),
        ("POTATO",    D("0.200")),
        ("SALT",      D("0.004")),
        ("MIXED-SP",  D("0.006")),
    ]),
    # دجاج كريسبي مع بطاطس
    ("Chicken Crispy & Chips", [
        ("CHKN-BRS",  D("0.200")),
        ("PANKO",     D("0.040")),
        ("FLOUR",     D("0.030")),
        ("EGGS",      D("1")),
        ("VEG-OIL",   D("0.080")),
        ("POTATO",    D("0.200")),
        ("SALT",      D("0.004")),
        ("MIXED-SP",  D("0.008")),
    ]),
    # ناجتس دجاج 8 قطع مع بطاطس
    ("Chicken Nuggets & Chips", [
        ("CHKN-BRS",  D("0.160")),
        ("PANKO",     D("0.035")),
        ("FLOUR",     D("0.025")),
        ("EGGS",      D("1")),
        ("VEG-OIL",   D("0.070")),
        ("POTATO",    D("0.200")),
        ("SALT",      D("0.003")),
        ("MIXED-SP",  D("0.006")),
    ]),
    # تشيز برجر مع بطاطس
    ("Cheese Burger & Chips", [
        ("GRD-BEEF",  D("0.180")),
        ("BRG-BUN",   D("1")),
        ("CHED-CHSE", D("0.040")),
        ("TOMATO",    D("0.040")),
        ("LETTUCE",   D("0.025")),
        ("ONION",     D("0.020")),
        ("MAYO",      D("0.020")),
        ("KETCHUP",   D("0.015")),
        ("POTATO",    D("0.200")),
        ("VEG-OIL",   D("0.070")),
        ("SALT",      D("0.003")),
    ]),
    # بيف برجر مع بطاطس
    ("Beef Burger & Chips", [
        ("GRD-BEEF",  D("0.180")),
        ("BRG-BUN",   D("1")),
        ("TOMATO",    D("0.040")),
        ("LETTUCE",   D("0.025")),
        ("ONION",     D("0.020")),
        ("MAYO",      D("0.020")),
        ("KETCHUP",   D("0.015")),
        ("POTATO",    D("0.200")),
        ("VEG-OIL",   D("0.070")),
        ("SALT",      D("0.003")),
    ]),
    # تشيكن برجر مع بطاطس
    ("Chicken Burger & Chips", [
        ("CHKN-BRS",  D("0.200")),
        ("BRG-BUN",   D("1")),
        ("TOMATO",    D("0.040")),
        ("LETTUCE",   D("0.025")),
        ("MAYO",      D("0.020")),
        ("POTATO",    D("0.200")),
        ("VEG-OIL",   D("0.070")),
        ("MIXED-SP",  D("0.008")),
        ("SALT",      D("0.003")),
    ]),
    # شيش طاووق بلاتر — 280g دجاج + أرز أو بطاطس
    ("Shish Tawook Platter", [
        ("CHKN-BRS",  D("0.280")),
        ("OLIVE-OIL", D("0.020")),
        ("GARLIC",    D("0.012")),
        ("LEMON",     D("0.040")),
        ("MIXED-SP",  D("0.010")),
        ("RICE-RAW",  D("0.100")),
        ("LETTUCE",   D("0.040")),
        ("TOMATO",    D("0.040")),
        ("SALT",      D("0.003")),
    ]),
    # بيري بيري شيش طاووق
    ("Peri-Peri Shish Tawook", [
        ("CHKN-BRS",  D("0.280")),
        ("OLIVE-OIL", D("0.020")),
        ("GARLIC",    D("0.012")),
        ("LEMON",     D("0.040")),
        ("MIXED-SP",  D("0.012")),
        ("PEPPER-B",  D("0.005")),
        ("RICE-RAW",  D("0.100")),
        ("LETTUCE",   D("0.040")),
        ("TOMATO",    D("0.040")),
        ("SALT",      D("0.003")),
    ]),
    # طبق كفتة — 300g لحم مفروم
    ("Kofta Platter", [
        ("GRD-BEEF",  D("0.300")),
        ("ONION",     D("0.040")),
        ("MIXED-SP",  D("0.012")),
        ("CORIANDER", D("0.005")),
        ("RICE-RAW",  D("0.100")),
        ("LETTUCE",   D("0.040")),
        ("TOMATO",    D("0.040")),
        ("SALT",      D("0.004")),
    ]),
    # طبق شاورما دجاج
    ("Chicken Shawarma Platter", [
        ("CHKN-BRS",  D("0.260")),
        ("VEG-OIL",   D("0.020")),
        ("GARLIC",    D("0.012")),
        ("MIXED-SP",  D("0.010")),
        ("RICE-RAW",  D("0.100")),
        ("LETTUCE",   D("0.040")),
        ("TOMATO",    D("0.040")),
        ("MAYO",      D("0.020")),
        ("SALT",      D("0.003")),
    ]),
    # طبق مشويات مشكلة — دجاج + لحم + كفتة
    ("Mixed Grill Platter", [
        ("CHKN-BRS",  D("0.150")),
        ("BEEF-FIL",  D("0.120")),
        ("GRD-BEEF",  D("0.100")),
        ("OLIVE-OIL", D("0.025")),
        ("GARLIC",    D("0.015")),
        ("LEMON",     D("0.050")),
        ("MIXED-SP",  D("0.012")),
        ("RICE-RAW",  D("0.100")),
        ("LETTUCE",   D("0.040")),
        ("TOMATO",    D("0.040")),
        ("SALT",      D("0.004")),
    ]),
]

# ══════════════════════════════════════════════════════════════════════════════
# RESTAURANT RECIPES — PART 2: Salads + Breakfast + Seafood + Pizza + Pasta
# ══════════════════════════════════════════════════════════════════════════════

Restaurant recipes part 2: Salads + Breakfast + Seafood + Pizza + Pasta
"""

SALADS = [
    # سيزر — خس + دجاج + بارميزان + صوص سيزر
    ("Caesar Salad", [
        ("LETTUCE",   D("0.120")),
        ("CHKN-BRS",  D("0.100")),
        ("PARM-CHSE", D("0.025")),
        ("CESAR-S",   D("0.040")),
        ("BREADCRUM", D("0.015")),
        ("OLIVE-OIL", D("0.010")),
        ("LEMON",     D("0.015")),
    ]),
    # يونانية — جبنة فيتا + خضار
    ("Greek Salad", [
        ("FETA-CHSE", D("0.060")),
        ("TOMATO",    D("0.080")),
        ("CUCUMBER",  D("0.080")),
        ("ONION",     D("0.030")),
        ("OLIVE-OIL", D("0.025")),
        ("LETTUCE",   D("0.060")),
        ("SALT",      D("0.002")),
        ("PEPPER-B",  D("0.002")),
    ]),
    # تونة
    ("Tuna Salad", [
        ("TUNA-CAN",  D("0.100")),
        ("LETTUCE",   D("0.080")),
        ("TOMATO",    D("0.060")),
        ("CUCUMBER",  D("0.040")),
        ("ONION",     D("0.025")),
        ("LEMON",     D("0.025")),
        ("OLIVE-OIL", D("0.015")),
        ("SALT",      D("0.002")),
    ]),
    # كريستال
    ("Crystal Salad", [
        ("CHKN-BRS",  D("0.100")),
        ("LETTUCE",   D("0.080")),
        ("TOMATO",    D("0.060")),
        ("CUCUMBER",  D("0.040")),
        ("FETA-CHSE", D("0.040")),
        ("OLIVE-OIL", D("0.015")),
        ("CESAR-S",   D("0.025")),
        ("LEMON",     D("0.020")),
    ]),
    # دايت
    ("Fit Salad", [
        ("LETTUCE",   D("0.100")),
        ("TOMATO",    D("0.060")),
        ("CUCUMBER",  D("0.060")),
        ("FETA-CHSE", D("0.040")),
        ("EGGS",      D("1")),
        ("OLIVE-OIL", D("0.020")),
        ("SALT",      D("0.002")),
        ("PEPPER-B",  D("0.002")),
    ]),
    # تبولة
    ("Tabbouleh", [
        ("TOMATO",    D("0.080")),
        ("ONION",     D("0.030")),
        ("LEMON",     D("0.030")),
        ("OLIVE-OIL", D("0.020")),
        ("CORIANDER", D("0.020")),
        ("SALT",      D("0.002")),
    ]),
    # فتوش
    ("Fattoush", [
        ("TOMATO",    D("0.080")),
        ("CUCUMBER",  D("0.060")),
        ("LETTUCE",   D("0.080")),
        ("ONION",     D("0.025")),
        ("LEMON",     D("0.025")),
        ("OLIVE-OIL", D("0.020")),
        ("BREAD-SND", D("1")),
        ("SALT",      D("0.002")),
    ]),
    # متوسط
    ("Mediterranean Salad", [
        ("TOMATO",    D("0.080")),
        ("CUCUMBER",  D("0.080")),
        ("LETTUCE",   D("0.060")),
        ("ONION",     D("0.025")),
        ("LEMON",     D("0.020")),
        ("OLIVE-OIL", D("0.020")),
        ("SALT",      D("0.002")),
    ]),
]

BREAKFAST = [
    # بيض مخفوق — 3 بيضات + خضار + توست
    ("Scrambled Eggs", [
        ("EGGS",      D("3")),
        ("BUTTER",    D("0.015")),
        ("MILK-FULL", D("0.030")),
        ("TOMATO",    D("0.040")),
        ("CUCUMBER",  D("0.030")),
        ("LETTUCE",   D("0.025")),
        ("BREAD-SND", D("2")),
        ("SALT",      D("0.002")),
    ]),
    # بيض مقلي بالجبن
    ("Fried Eggs with Cheese", [
        ("EGGS",      D("2")),
        ("CHED-CHSE", D("0.030")),
        ("BUTTER",    D("0.015")),
        ("TOMATO",    D("0.040")),
        ("LETTUCE",   D("0.025")),
        ("BREAD-SND", D("2")),
        ("SALT",      D("0.002")),
    ]),
    # أومليت
    ("Omelette", [
        ("EGGS",      D("3")),
        ("BUTTER",    D("0.015")),
        ("TOMATO",    D("0.040")),
        ("CUCUMBER",  D("0.030")),
        ("BREAD-SND", D("2")),
        ("SALT",      D("0.002")),
    ]),
    # أومليت بالخضار
    ("Omelette with Vegetables", [
        ("EGGS",      D("3")),
        ("BUTTER",    D("0.020")),
        ("TOMATO",    D("0.040")),
        ("CUCUMBER",  D("0.030")),
        ("MUSHROOM",  D("0.040")),
        ("ONION",     D("0.020")),
        ("SPINACH",   D("0.030")),
        ("BREAD-SND", D("2")),
        ("SALT",      D("0.002")),
    ]),
]

SEAFOOD = [
    # كاليماري — 300g كاليماري (مقلي أو مشوي)
    ("Calamari", [
        ("CALAMARI",  D("0.300")),
        ("FLOUR",     D("0.040")),
        ("PANKO",     D("0.030")),
        ("VEG-OIL",   D("0.080")),
        ("LEMON",     D("0.040")),
        ("MIXED-SP",  D("0.008")),
        ("SALT",      D("0.003")),
        ("MAYO",      D("0.025")),
    ]),
    # جمبري — 300g جمبري
    ("Shrimps", [
        ("SHRIMP",    D("0.300")),
        ("GARLIC",    D("0.012")),
        ("BUTTER",    D("0.025")),
        ("LEMON",     D("0.040")),
        ("OLIVE-OIL", D("0.020")),
        ("MIXED-SP",  D("0.008")),
        ("SALT",      D("0.003")),
    ]),
    # جمبري مع كاليماري
    ("Shrimps with Calamari", [
        ("SHRIMP",    D("0.200")),
        ("CALAMARI",  D("0.150")),
        ("GARLIC",    D("0.012")),
        ("BUTTER",    D("0.025")),
        ("LEMON",     D("0.040")),
        ("VEG-OIL",   D("0.040")),
        ("MIXED-SP",  D("0.008")),
        ("SALT",      D("0.003")),
        ("MAYO",      D("0.020")),
    ]),
    # سمك مع بطاطس
    ("Fish & Chips", [
        ("FISH-FIL",  D("0.280")),
        ("PANKO",     D("0.040")),
        ("FLOUR",     D("0.030")),
        ("EGGS",      D("1")),
        ("VEG-OIL",   D("0.080")),
        ("POTATO",    D("0.200")),
        ("LEMON",     D("0.030")),
        ("SALT",      D("0.003")),
        ("MAYO",      D("0.025")),
    ]),
]

PIZZA = [
    # مارجريتا — عجينة 200g + صوص طماطم + موزاريلا + ريحان
    ("Margherita Pizza", [
        ("PIZZA-DGH", D("0.200")),
        ("TOM-SAUCE", D("0.080")),
        ("MOZ-CHSE",  D("0.150")),
        ("OLIVE-OIL", D("0.015")),
        ("SALT",      D("0.002")),
    ]),
    # سلامي
    ("Salami Pizza", [
        ("PIZZA-DGH", D("0.200")),
        ("TOM-SAUCE", D("0.080")),
        ("MOZ-CHSE",  D("0.120")),
        ("SALAMI",    D("0.070")),
        ("OLIVE-OIL", D("0.015")),
        ("SALT",      D("0.002")),
    ]),
    # أربع أنواع جبن
    ("Four Cheese Pizza", [
        ("PIZZA-DGH", D("0.200")),
        ("MOZ-CHSE",  D("0.080")),
        ("CHED-CHSE", D("0.050")),
        ("PARM-CHSE", D("0.040")),
        ("CREAM-CHSE",D("0.050")),
        ("OLIVE-OIL", D("0.015")),
    ]),
    # دجاج
    ("Chicken Pizza", [
        ("PIZZA-DGH", D("0.200")),
        ("TOM-SAUCE", D("0.080")),
        ("MOZ-CHSE",  D("0.120")),
        ("CHKN-BRS",  D("0.120")),
        ("OLIVE-OIL", D("0.015")),
        ("GARLIC",    D("0.008")),
        ("MIXED-SP",  D("0.005")),
    ]),
    # تونة
    ("Tuna Pizza", [
        ("PIZZA-DGH", D("0.200")),
        ("TOM-SAUCE", D("0.080")),
        ("MOZ-CHSE",  D("0.110")),
        ("TUNA-CAN",  D("0.080")),
        ("ONION",     D("0.030")),
        ("OLIVE-OIL", D("0.015")),
    ]),
    # خضار
    ("Vegetariana Pizza", [
        ("PIZZA-DGH", D("0.200")),
        ("TOM-SAUCE", D("0.080")),
        ("MOZ-CHSE",  D("0.120")),
        ("TOMATO",    D("0.050")),
        ("CUCUMBER",  D("0.040")),
        ("ONION",     D("0.030")),
        ("MUSHROOM",  D("0.040")),
        ("OLIVE-OIL", D("0.015")),
    ]),
    # فروتي دي ماري
    ("Frutti Di Mare Pizza", [
        ("PIZZA-DGH", D("0.200")),
        ("TOM-SAUCE", D("0.080")),
        ("MOZ-CHSE",  D("0.100")),
        ("SHRIMP",    D("0.080")),
        ("CALAMARI",  D("0.060")),
        ("FISH-FIL",  D("0.060")),
        ("GARLIC",    D("0.008")),
        ("OLIVE-OIL", D("0.015")),
    ]),
    # جمبري
    ("Shrimps Pizza", [
        ("PIZZA-DGH", D("0.200")),
        ("TOM-SAUCE", D("0.080")),
        ("MOZ-CHSE",  D("0.110")),
        ("SHRIMP",    D("0.120")),
        ("GARLIC",    D("0.010")),
        ("OLIVE-OIL", D("0.015")),
    ]),
]

PASTA = [
    # دجاج — 120g بيني + 120g دجاج + مشروم + صوص طماطم
    ("Chicken Pasta", [
        ("PENNE",     D("0.120")),
        ("CHKN-BRS",  D("0.120")),
        ("MUSHROOM",  D("0.060")),
        ("TOM-SAUCE", D("0.080")),
        ("GARLIC",    D("0.008")),
        ("OLIVE-OIL", D("0.020")),
        ("PARM-CHSE", D("0.020")),
        ("SALT",      D("0.002")),
    ]),
    # بولونيز — لحم مفروم + صوص طماطم
    ("Bolognese Pasta", [
        ("PENNE",     D("0.120")),
        ("GRD-BEEF",  D("0.150")),
        ("TOM-SAUCE", D("0.100")),
        ("ONION",     D("0.040")),
        ("GARLIC",    D("0.008")),
        ("OLIVE-OIL", D("0.020")),
        ("PARM-CHSE", D("0.025")),
        ("MIXED-SP",  D("0.006")),
        ("SALT",      D("0.002")),
    ]),
    # أرابياتا — صوص طماطم حار
    ("Arrabiata Pasta", [
        ("SPAGHET",   D("0.120")),
        ("TOM-SAUCE", D("0.100")),
        ("GARLIC",    D("0.010")),
        ("OLIVE-OIL", D("0.025")),
        ("PEPPER-B",  D("0.005")),
        ("MIXED-SP",  D("0.008")),
        ("SALT",      D("0.002")),
    ]),
    # لورو روسو — دجاج + صوص طماطم وكريمة
    ("Loro Rosso Pasta", [
        ("SPAGHET",   D("0.120")),
        ("CHKN-BRS",  D("0.120")),
        ("TOM-SAUCE", D("0.060")),
        ("CREAM",     D("0.060")),
        ("GARLIC",    D("0.008")),
        ("OLIVE-OIL", D("0.015")),
        ("PARM-CHSE", D("0.020")),
        ("SALT",      D("0.002")),
    ]),
    # كواترو فورماجي — أربع أنواع جبن + كريمة
    ("Quattro Formaggi Pasta", [
        ("PENNE",     D("0.120")),
        ("MOZ-CHSE",  D("0.060")),
        ("CHED-CHSE", D("0.040")),
        ("PARM-CHSE", D("0.030")),
        ("CREAM-CHSE",D("0.040")),
        ("CREAM",     D("0.060")),
        ("BUTTER",    D("0.020")),
        ("SALT",      D("0.002")),
    ]),
    # جمبري
    ("Shrimp Pasta", [
        ("SPAGHET",   D("0.120")),
        ("SHRIMP",    D("0.150")),
        ("GARLIC",    D("0.010")),
        ("OLIVE-OIL", D("0.025")),
        ("LEMON",     D("0.030")),
        ("PEPPER-B",  D("0.004")),
        ("SALT",      D("0.003")),
    ]),
]

# ══════════════════════════════════════════════════════════════════════════════
# CAFE & BAR RECIPES
# ══════════════════════════════════════════════════════════════════════════════

Cafe & Bar recipes: Hot Beverages + Fresh Juices + Mix Juices +
Frappuccino/Iced Coffee + Milkshakes + Mojito + Cold Drinks + Fruit Salad
"""

HOT_BEVERAGES = [
    # إسبريسو سنجل — 7g قهوة
    ("Espresso Single", [
        ("COFFEE-B", D("0.007")),
    ]),
    # إسبريسو دبل — 14g قهوة
    ("Espresso Double", [
        ("COFFEE-B", D("0.014")),
    ]),
    # كابتشينو — إسبريسو + حليب + رغوة
    ("Cappuccino", [
        ("COFFEE-B",  D("0.007")),
        ("MILK-FULL", D("0.120")),
        ("SUGAR",     D("0.010")),
    ]),
    # لاتيه
    ("Latte", [
        ("COFFEE-B",  D("0.007")),
        ("MILK-FULL", D("0.200")),
        ("SUGAR",     D("0.010")),
    ]),
    # ماكياتو
    ("Macchiato", [
        ("COFFEE-B",  D("0.007")),
        ("MILK-FULL", D("0.060")),
        ("SUGAR",     D("0.008")),
    ]),
    # نسكافيه بالحليب
    ("Nescafe with Milk", [
        ("NESCAFE-P", D("0.010")),
        ("MILK-FULL", D("0.150")),
        ("SUGAR",     D("0.012")),
    ]),
    # نسكافيه كلاسيك
    ("Nescafe Classic", [
        ("NESCAFE-P", D("0.010")),
        ("SUGAR",     D("0.010")),
    ]),
    # أمريكانو
    ("Americano", [
        ("COFFEE-B",  D("0.010")),
        ("SUGAR",     D("0.008")),
    ]),
    # هوت شوكليت — كاكاو + حليب + سكر
    ("Hot Chocolate", [
        ("COCOA-P",   D("0.025")),
        ("MILK-FULL", D("0.200")),
        ("SUGAR",     D("0.020")),
    ]),
    # هوت سيدر — عصير تفاح دافئ + قرفة
    ("Hot Cider", [
        ("APPLE-F",   D("0.300")),
        ("SUGAR",     D("0.015")),
        ("CINNAMON",  D("0.002")),
    ]),
    # قهوة تركي
    ("Turkish Coffee", [
        ("TURK-COFFE", D("0.012")),
        ("SUGAR",      D("0.010")),
    ]),
    # قهوة فرنساوي — إسبريسو + حليب + كراميل
    ("French Coffee", [
        ("ESPRESSO-P", D("0.012")),
        ("MILK-FULL",  D("0.100")),
        ("CARAML-S",   D("0.020")),
        ("SUGAR",      D("0.008")),
    ]),
    # شاي/ينسون/نعناع/كركديه
    ("Tea Anise Mint Hibiscus", [
        ("TEA-BAG",  D("1")),
        ("SUGAR",    D("0.015")),
    ]),
    # شاي بالحليب
    ("Milk Tea", [
        ("TEA-BAG",   D("1")),
        ("MILK-FULL", D("0.120")),
        ("SUGAR",     D("0.015")),
    ]),
]

FRESH_JUICES = [
    ("Mango Juice",         [("MANGO-F",  D("0.300")), ("SUGAR", D("0.015")), ("MILK-FULL", D("0.050"))]),
    ("Strawberry Juice",    [("STRAW-F",  D("0.250")), ("SUGAR", D("0.015")), ("MILK-FULL", D("0.050"))]),
    ("Guava Juice",         [("GUAVA-F",  D("0.280")), ("SUGAR", D("0.015")), ("MILK-FULL", D("0.040"))]),
    ("Cantaloupe Juice",    [("CANT-F",   D("0.350")), ("SUGAR", D("0.012"))]),
    ("Pomegranate Juice",   [("POMG-F",  D("0.300")), ("SUGAR", D("0.012"))]),
    ("Orange Juice",        [("ORANGE-F", D("0.400")), ("SUGAR", D("0.010"))]),
    ("Watermelon Juice",    [("WATER-F",  D("0.450")), ("SUGAR", D("0.010"))]),
    ("Kiwi Juice",          [("KIWI-F",   D("0.220")), ("SUGAR", D("0.015")), ("MILK-FULL", D("0.050"))]),
    ("Lemon Juice",         [("LEMON",    D("0.100")), ("SUGAR", D("0.025"))]),
    ("Lemon Mint",          [("LEMON",    D("0.090")), ("SUGAR", D("0.025")), ("MINT-DRY", D("0.005"))]),
    ("Apple Juice",         [("APPLE-F",  D("0.300")), ("SUGAR", D("0.015"))]),
    ("Pineapple Juice",     [("PINEAP-F", D("0.280")), ("SUGAR", D("0.015"))]),
    ("Peach Juice",         [("PEACH-F",  D("0.260")), ("SUGAR", D("0.015")), ("MILK-FULL", D("0.040"))]),
    ("Avocado Juice",       [("AVOC-F",   D("0.180")), ("MILK-FULL", D("0.150")), ("SUGAR", D("0.015"))]),
    ("Avocado Honey Nuts",  [("AVOC-F",   D("0.180")), ("MILK-FULL", D("0.120")), ("HONEY", D("0.025")), ("CASHEW", D("0.020"))]),
    ("Dates Juice",         [("DATES-F",  D("0.100")), ("MILK-FULL", D("0.200")), ("HONEY", D("0.015"))]),
]

MIX_JUICES = [
    ("Pina Colada Mix",      [("PINEAP-F", D("0.150")), ("COCONUT-M", D("0.080")), ("SUGAR", D("0.020")), ("MILK-FULL", D("0.050"))]),
    ("Mango Kiwi Mix",       [("MANGO-F",  D("0.160")), ("KIWI-F",   D("0.100")), ("SUGAR", D("0.015"))]),
    ("Mango Plum Mix",       [("MANGO-F",  D("0.160")), ("PEACH-F",  D("0.100")), ("SUGAR", D("0.015"))]),
    ("Mango Strawberry Mix", [("MANGO-F",  D("0.150")), ("STRAW-F",  D("0.120")), ("SUGAR", D("0.015"))]),
    ("Mango Cantaloupe Mix", [("MANGO-F",  D("0.150")), ("CANT-F",   D("0.150")), ("SUGAR", D("0.012"))]),
    ("Kiwi Cantaloupe Mix",  [("KIWI-F",   D("0.120")), ("CANT-F",   D("0.150")), ("SUGAR", D("0.012"))]),
    ("Kiwi Pineapple Mix",   [("KIWI-F",   D("0.120")), ("PINEAP-F", D("0.150")), ("SUGAR", D("0.012"))]),
    ("Mango Banana Mix",     [("MANGO-F",  D("0.150")), ("BANANA-F", D("0.100")), ("MILK-FULL", D("0.060")), ("SUGAR", D("0.015"))]),
    ("Strawberry Banana Mix",[("STRAW-F",  D("0.150")), ("BANANA-F", D("0.100")), ("MILK-FULL", D("0.060")), ("SUGAR", D("0.015"))]),
    ("Khayma Mix",           [("MANGO-F",  D("0.100")), ("STRAW-F",  D("0.080")), ("ORANGE-F", D("0.100")), ("BANANA-F", D("0.080")), ("SUGAR", D("0.015")), ("MILK-FULL", D("0.050"))]),
]

FRAPPUCCINO = [
    ("Frappuccino Classic",  [("COFFEE-B",  D("0.010")), ("MILK-FULL", D("0.150")), ("SUGAR", D("0.025")), ("ICE-CREAM", D("0.060"))]),
    ("Frappuccino Vanilla",  [("COFFEE-B",  D("0.010")), ("MILK-FULL", D("0.150")), ("VANILLA", D("0.005")), ("SUGAR", D("0.025")), ("ICE-CREAM", D("0.060"))]),
    ("Frappuccino Hazelnut", [("COFFEE-B",  D("0.010")), ("MILK-FULL", D("0.150")), ("CARAML-S", D("0.020")), ("SUGAR", D("0.020")), ("ICE-CREAM", D("0.060"))]),
    ("Iced Coffee",          [("COFFEE-B",  D("0.010")), ("MILK-FULL", D("0.100")), ("SUGAR", D("0.020")), ("ICE-CREAM", D("0.040"))]),
    ("Iced Latte",           [("COFFEE-B",  D("0.007")), ("MILK-FULL", D("0.200")), ("SUGAR", D("0.015")), ("ICE-CREAM", D("0.040"))]),
    ("Spanish Latte",        [("COFFEE-B",  D("0.007")), ("MILK-FULL", D("0.150")), ("SUGAR", D("0.025")), ("CARAML-S", D("0.015")), ("ICE-CREAM", D("0.040"))]),
]

MILKSHAKES = [
    ("Vanilla Milkshake",     [("MILK-FULL", D("0.200")), ("ICE-CREAM", D("0.120")), ("VANILLA",  D("0.005")), ("SUGAR", D("0.020"))]),
    ("Chocolate Milkshake",   [("MILK-FULL", D("0.200")), ("ICE-CREAM", D("0.120")), ("CHOC-SYR", D("0.040")), ("SUGAR", D("0.015"))]),
    ("Caramel Milkshake",     [("MILK-FULL", D("0.200")), ("ICE-CREAM", D("0.120")), ("CARAML-S", D("0.040")), ("SUGAR", D("0.010"))]),
    ("Oreo Milkshake",        [("MILK-FULL", D("0.200")), ("ICE-CREAM", D("0.120")), ("CHOC-SYR", D("0.030")), ("SUGAR", D("0.020"))]),
    ("Tonkeys Milkshake",     [("MILK-FULL", D("0.200")), ("ICE-CREAM", D("0.120")), ("CHOC-DARK", D("0.030")), ("CARAML-S", D("0.020"))]),
    ("Berries Milkshake",     [("MILK-FULL", D("0.200")), ("ICE-CREAM", D("0.100")), ("STRAW-F",  D("0.080")), ("SUGAR", D("0.020"))]),
    ("Mango Milkshake",       [("MILK-FULL", D("0.150")), ("ICE-CREAM", D("0.100")), ("MANGO-F",  D("0.100")), ("SUGAR", D("0.015"))]),
    ("Strawberry Milkshake",  [("MILK-FULL", D("0.150")), ("ICE-CREAM", D("0.100")), ("STRAW-F",  D("0.100")), ("SUGAR", D("0.015"))]),
]

MOJITO = [
    ("Mojito Classic",          [("LEMON",    D("0.080")), ("MINT-DRY",  D("0.005")), ("MINT-SYR",   D("0.025")), ("SUGAR", D("0.020"))]),
    ("Mojito Soda",             [("LEMON",    D("0.070")), ("MINT-DRY",  D("0.005")), ("MINT-SYR",   D("0.025")), ("SUGAR", D("0.018"))]),
    ("Mojito Sunshine",         [("LEMON",    D("0.070")), ("ORANGE-F",  D("0.100")), ("MINT-SYR",   D("0.020")), ("SUGAR", D("0.018"))]),
    ("Mojito Red Bull Special", [("LEMON",    D("0.060")), ("MINT-DRY",  D("0.005")), ("MINT-SYR",   D("0.025")), ("REDBULL-C", D("1"))]),
]

COLD_DRINKS = [
    ("Cola Fanta Sprite",    [("COLA-C",    D("1"))]),
    ("Fayrouz",              [("FAYROUZ-C", D("1"))]),
    ("Barrel",               [("BEARL-C",   D("1"))]),
    ("Red Bull",             [("REDBULL-C", D("1"))]),
    ("Water Small",          [("WATER-SM",  D("1"))]),
    ("Water Large",          [("WATER-SM",  D("1"))]),  # نفس SKU، حجم مختلف
]

FRUIT_SALAD = [
    # فروت سلاط صغير — 300g فاكهة مشكلة
    ("Fruit Salad Small", [
        ("BANANA-F",  D("0.060")),
        ("STRAW-F",   D("0.060")),
        ("MANGO-F",   D("0.060")),
        ("ORANGE-F",  D("0.060")),
        ("KIWI-F",    D("0.040")),
        ("HONEY",     D("0.015")),
    ]),
    # فروت سلاط كبير — 600g فاكهة مشكلة
    ("Fruit Salad Large", [
        ("BANANA-F",  D("0.120")),
        ("STRAW-F",   D("0.120")),
        ("MANGO-F",   D("0.120")),
        ("ORANGE-F",  D("0.100")),
        ("KIWI-F",    D("0.080")),
        ("PINEAP-F",  D("0.080")),
        ("HONEY",     D("0.025")),
    ]),
    # طبق بطيخ صغير
    ("Watermelon Plate Small", [
        ("WATER-F",   D("0.500")),
    ]),
    # طبق بطيخ كبير
    ("Watermelon Plate Large", [
        ("WATER-F",   D("1.000")),
    ]),
]


# ══════════════════════════════════════════════════════════════════════════════
# SEED FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def _seed_restaurant_recipes_2026(db: Session) -> None:
    all_recipes = (
        STARTERS + SANDWICHES + MAIN_COURSE
        + SALADS + BREAKFAST + SEAFOOD + PIZZA + PASTA
    )
    _apply_recipes(db, "restaurant", all_recipes)


def _seed_cafe_recipes_2026(db: Session) -> None:
    all_recipes = (
        HOT_BEVERAGES + FRESH_JUICES + MIX_JUICES + FRAPPUCCINO
        + MILKSHAKES + MOJITO + COLD_DRINKS + FRUIT_SALAD
    )
    _apply_recipes(db, "cafe", all_recipes)
