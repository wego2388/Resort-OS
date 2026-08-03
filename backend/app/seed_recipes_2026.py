"""
app/seed_recipes_2026.py
──────────────────────────────────────────────────────────────────────────────
وصفات (Recipe/BOM) واقعية لمنيو 2026 — مستقل عن app/seed.py، آمن يتشغّل
على production مباشرة (بعد seed_menu_2026.py).

الكميات بالكيلوجرام/باللتر إلا البيض والمعبآت والأرغفة (قطعة).
Food Cost % المستهدف: مطعم (أطباق) 25–32%، مشروبات/كافيه 12–20%.

⚠️ نسخة مُصلَّحة (2026-08-03) من data/menu/seed_recipes_2026.py الأصلية —
3 مشاكل حقيقية اتصلحت:

1. **الملف الأصلي معندوش syntax صحيح خالص** — كان فيه docstring مقفول
   (```\"\"\"```) من غير ما يتفتح، متبقّي من دمج ملفات _recipes_part1/2/3.py
   التلاتة في ملف واحد من غير تنضيف الرؤوس بتاعتهم — `ast.parse()` كان
   بيرمي `SyntaxError: unterminated triple-quoted string literal` فورًا،
   يعني الملف الأصلي عمره ما كان قابل للاستيراد خالص.

2. **كل أكواد المكوّنات (POTATO/VEG-OIL/CHKN-BRS/...) مكانتش SKUs حقيقية
   موجودة في المخزون خالص** — المخزون الحالي (app.seed._seed_inventory_
   recipes) عنده 21 مكوّن بس بـSKUs بادئتها `ING-` (زي `ING-POTATO`،
   `ING-CHICKEN-BREAST`) مش الأكواد المختصرة دي. تشغيل السكريبت الأصلي
   كان هيمسح أي وصفة موجودة فعلاً لصنف بنفس الاسم في المنيو الجديد (5
   أصناف على الأقل: Margherita/Salami/Tuna Pizza، Caesar/Greek Salad —
   `DELETE FROM dining_item_recipe_lines WHERE item_id=...` غير مشروط قبل
   أي محاولة إدراج) وبعدين ميحطش حاجة مكانها لأن كل الـSKUs كانت "WARN
   not found" — يعني تدمير صامت لبيانات تكلفة طعام شغالة فعليًا.

3. الحل: (أ) `SKU_ALIASES` تحت — يربط كل كود من أكواد الوصفات المختصرة
   اللي بتتوافق مع مكوّن موجود فعلاً في المخزون (21 مكوّن) بالـSKU
   الحقيقي بتاعه، (ب) `_seed_new_ingredients_2026()` جديدة تزرع باقي
   الـ62 مكوّن الناقص (بادئة `ING-` زي الموجودين بالظبط، idempotent
   بالتحقق من الـSKU مش زي `_seed_inventory_recipes` القديمة اللي بتشتغل
   مرة واحدة بس على قاعدة بيانات فاضية).

الاستخدام:
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
# مكوّنات جديدة لازمة لمنيو 2026 (name_en, name_ar, unit, cost_price, initial_stock)
# ══════════════════════════════════════════════════════════════════════════════
# الـ21 مكوّن الموجودين فعلاً في المخزون (app.seed._seed_inventory_recipes)
# اتغطوا عبر SKU_ALIASES تحت — الـ62 دول بس هم الناقصين فعليًا. تكاليف
# تقريبية واقعية للسوق المصري (2026)، بنفس أسلوب الـ21 الموجودين.
NEW_INGREDIENTS: list[tuple[str, str, str, str, D, D]] = [
    # (sku_code, name_en, name_ar, unit, cost_price, initial_stock)
    # — فواكه طازجة (كيلو) —
    ("APPLE-F",  "Apple",       "تفاح",   "kg", D("35"), D("15")),
    ("AVOC-F",   "Avocado",     "أفوكادو", "kg", D("90"), D("8")),
    ("CANT-F",   "Cantaloupe",  "كنتالوب", "kg", D("20"), D("15")),
    ("DATES-F",  "Dates",       "تمر",    "kg", D("60"), D("5")),
    ("GUAVA-F",  "Guava",       "جوافة",  "kg", D("30"), D("10")),
    ("KIWI-F",   "Kiwi",        "كيوي",   "kg", D("90"), D("10")),
    ("MANGO-F",  "Mango",       "مانجو",  "kg", D("45"), D("20")),
    ("ORANGE-F", "Orange",      "برتقال", "kg", D("20"), D("20")),
    ("PEACH-F",  "Peach",       "خوخ",    "kg", D("50"), D("10")),
    ("PINEAP-F", "Pineapple",   "أناناس", "kg", D("40"), D("10")),
    ("POMG-F",   "Pomegranate", "رمان",   "kg", D("60"), D("8")),
    ("STRAW-F",  "Strawberry",  "فراولة", "kg", D("60"), D("15")),
    ("WATER-F",  "Watermelon",  "بطيخ",   "kg", D("12"), D("30")),
    # — خضار (كيلو) —
    ("CORIANDER", "Coriander", "كزبرة",  "kg", D("25"),  D("3")),
    ("GARLIC",    "Garlic",    "ثوم",    "kg", D("50"),  D("5")),
    ("LEMON",     "Lemon",     "ليمون",  "kg", D("25"),  D("15")),
    ("MUSHROOM",  "Mushroom",  "مشروم",  "kg", D("90"),  D("8")),
    ("ONION",     "Onion",     "بصل",    "kg", D("15"),  D("15")),
    ("SPINACH",   "Spinach",   "سبانخ",  "kg", D("25"),  D("5")),
    # — بروتين —
    ("FISH-FIL", "Fish Fillet", "فيليه سمك", "kg", D("220"), D("8")),
    # — ألبان وبيض —
    ("BUTTER",    "Butter",             "زبدة",              "kg",    D("220"), D("5")),
    ("CREAM",     "Cooking Cream",      "كريمة طبخ",         "kg",    D("140"), D("8")),
    ("CREAM-CHSE","Cream Cheese",       "جبنة كريمي",        "kg",    D("200"), D("5")),
    ("EGGS",      "Eggs",               "بيض",               "piece", D("5"),   D("300")),
    ("MILK-FULL", "Full-fat Milk",      "حليب كامل الدسم",   "liter", D("45"),  D("30")),
    # — مخبوزات وبقالة جافة —
    ("BREAD-SND", "Sandwich Bread",  "خبز ساندوتش",      "piece", D("5"),  D("200")),
    ("BREADCRUM", "Breadcrumbs",     "بقسماط",           "kg",    D("40"), D("5")),
    ("FLOUR",     "Flour",           "دقيق",             "kg",    D("20"), D("10")),
    ("HONEY",     "Honey",           "عسل",              "kg",    D("150"),D("5")),
    ("KETCHUP",   "Ketchup",         "كاتشب",            "kg",    D("60"), D("5")),
    ("MAYO",      "Mayonnaise",      "مايونيز",          "kg",    D("90"), D("8")),
    ("MIXED-SP",  "Mixed Spices",    "بهارات مشكلة",     "kg",    D("100"),D("3")),
    ("OLIVE-OIL", "Olive Oil",       "زيت زيتون",        "liter", D("180"),D("10")),
    ("PANKO",     "Panko Breadcrumbs","بانكو",           "kg",    D("70"), D("5")),
    ("PEPPER-B",  "Black Pepper",    "فلفل أسود",        "kg",    D("300"),D("2")),
    ("SALT",      "Salt",            "ملح",              "kg",    D("8"),  D("10")),
    ("SUGAR",     "Sugar",           "سكر",              "kg",    D("25"), D("20")),
    ("TAHINI",    "Tahini",          "طحينة",            "kg",    D("90"), D("5")),
    ("VEG-OIL",   "Vegetable Oil",   "زيت نباتي",        "liter", D("50"), D("20")),
    ("CESAR-S",   "Caesar Dressing", "صوص سيزر",         "kg",    D("150"),D("5")),
    ("CASHEW",    "Cashew Nuts",     "كاجو",             "kg",    D("400"),D("3")),
    ("SPAGHET",   "Spaghetti",       "اسباجيتي",         "kg",    D("45"), D("10")),
    # — مستلزمات الكافيه —
    ("CARAML-S",  "Caramel Syrup",     "شراب كراميل",      "liter", D("120"), D("5")),
    ("CHOC-DARK", "Dark Chocolate",    "شوكولاتة داكنة",   "kg",    D("250"), D("3")),
    ("CHOC-SYR",  "Chocolate Syrup",   "شراب شوكولاتة",    "liter", D("100"), D("5")),
    ("CINNAMON",  "Cinnamon",          "قرفة",             "kg",    D("200"), D("1")),
    ("COCOA-P",   "Cocoa Powder",      "كاكاو بودر",       "kg",    D("180"), D("3")),
    ("COCONUT-M", "Coconut Milk",      "حليب جوز الهند",   "liter", D("90"),  D("5")),
    ("COFFEE-B",  "Coffee Beans",      "بن قهوة",          "kg",    D("450"), D("8")),
    ("ESPRESSO-P","Espresso Ground",   "بن إسبريسو مطحون","kg",    D("450"), D("5")),
    ("ICE-CREAM", "Vanilla Ice Cream", "آيس كريم فانيليا", "kg",    D("120"), D("10")),
    ("MINT-DRY",  "Dried Mint",        "نعناع مجفف",       "kg",    D("150"), D("2")),
    ("MINT-SYR",  "Mint Syrup",        "شراب نعناع",       "liter", D("90"),  D("5")),
    ("NESCAFE-P", "Instant Coffee",    "نسكافيه",          "kg",    D("400"), D("3")),
    ("TEA-BAG",   "Tea Bag",           "كيس شاي",          "piece", D("1"),   D("500")),
    ("TURK-COFFE","Turkish Coffee Ground","قهوة تركي مطحونة","kg", D("350"), D("3")),
    ("VANILLA",   "Vanilla Syrup",     "فانيليا",          "liter", D("150"), D("3")),
    # — مشروبات معبأة (بالقطعة) —
    ("COLA-C",    "Cola/Fanta/Sprite Can", "كولا/فانتا/سبرايت", "piece", D("12"), D("100")),
    ("FAYROUZ-C", "Fayrouz Can",           "فيروز",             "piece", D("14"), D("60")),
    ("BEARL-C",   "Barrel Can",            "بريل",              "piece", D("14"), D("60")),
    ("REDBULL-C", "Red Bull Can",          "ريد بول",           "piece", D("35"), D("40")),
    ("WATER-SM",  "Small Water Bottle",    "مياه صغيرة",        "piece", D("4"),  D("200")),
]

# الـ21 مكوّن الموجودين فعلاً — كود الوصفة المختصر → الـSKU الحقيقي في
# المخزون (بادئة ING- من app.seed._seed_inventory_recipes، أسماء كاملة
# مش مختصرة زي أكواد الوصفة). راجع docstring الملف فوق للسبب.
SKU_ALIASES: dict[str, str] = {
    "POTATO":    "ING-POTATO",
    "CHKN-BRS":  "ING-CHICKEN-BREAST",
    "BEEF-FIL":  "ING-BEEF-FILLET",
    "GRD-BEEF":  "ING-GROUND-BEEF",
    "BRG-BUN":   "ING-BURGER-BUN",
    "CHED-CHSE": "ING-CHEDDAR-CHEESE",
    "PIZZA-DGH": "ING-PIZZA-DOUGH",
    "MOZ-CHSE":  "ING-MOZZARELLA-CHEESE",
    "TOM-SAUCE": "ING-TOMATO-SAUCE",
    "SALAMI":    "ING-SALAMI",
    "TUNA-CAN":  "ING-CANNED-TUNA",
    "PENNE":     "ING-PENNE-PASTA",
    "SHRIMP":    "ING-SHRIMP",
    "CALAMARI":  "ING-CALAMARI",
    "RICE-RAW":  "ING-WHITE-RICE-(RAW)",
    "LETTUCE":   "ING-LETTUCE",
    "TOMATO":    "ING-FRESH-TOMATO",
    "CUCUMBER":  "ING-CUCUMBER",
    "FETA-CHSE": "ING-FETA-CHEESE",
    "PARM-CHSE": "ING-PARMESAN-CHEESE",
    "BANANA-F":  "ING-BANANA",
}


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def seed_recipes_2026(db: Session) -> None:
    """نقطة الدخول الرئيسية — استدعِها وبعدين db.commit()"""
    print("▶ seed_recipes_2026: starting...")
    _seed_new_ingredients_2026(db)
    _seed_restaurant_recipes_2026(db)
    _seed_cafe_recipes_2026(db)
    db.flush()
    print("✓ seed_recipes_2026: done. Call db.commit() to persist.")


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _seed_new_ingredients_2026(db: Session) -> None:
    """upsert-by-SKU حقيقي (مش "شغّل مرة واحدة على قاعدة فاضية" زي
    app.seed._seed_inventory_recipes) — آمن يتشغّل على مخزون production
    فيه بيانات فعلاً. مخزن NEW_INGREDIENTS بيروح لأي مخزن موجود فعلاً
    للفرع (بيتعمله get، مش create) — ⚠️ باج حقيقي اتصلح (2026-08-03):
    كان بيدوّر على code="WH-KITCHEN" تحديدًا (كود app.seed's warehouse
    الافتراضي)، فوقع فورًا على بيئة محلية حقيقية عندها مخزن بكود مختلف
    (WHLIVE01) — أي بيئة اتزرعت بطريقة تانية غير app.seed كانت هتقع نفس
    الوقعة. مفيش أي اعتماد فعلي على الكود نفسه في باقي الكود، بس محتاجين
    مخزن موجود نربط بيه المنتجات الجديدة."""
    from datetime import datetime
    from app.modules.inventory.models import Product, StockMovement, Warehouse
    from app.modules.core.models import Branch

    branch = db.query(Branch).first()
    if not branch:
        raise RuntimeError("No branch found — run main seed first.")
    warehouse = db.query(Warehouse).filter(Warehouse.branch_id == branch.id).first()
    if not warehouse:
        raise RuntimeError("No warehouse found for this branch — run main seed first.")

    existing_skus = {
        sku for (sku,) in db.query(Product.sku).filter(Product.branch_id == branch.id).all()
    }
    inserted = 0
    for code, name_en, name_ar, unit, cost, stock in NEW_INGREDIENTS:
        # الكود نفسه هو الـSKU مباشرة (مش بادئة ING- زي أول نسخة) — ⚠️ باج
        # حقيقي اتصلح (2026-08-03): بيئة محلية حقيقية اتفحصت وقت التطبيق
        # الفعلي كان عندها بالفعل 83/83 مكوّن مزروع بنفس أكواد الوصفات
        # المختصرة دي كـSKU مباشر (بادئة ING- صفر استخدام حقيقي في أي
        # بيئة حقيقية اتفحصت) — فالتصميم الأول كان هيزرع 62 منتج مكرر
        # (ING-POTATO جنب POTATO الموجود بالفعل) بدل ما يلاقي الموجود
        # ويستخدمه. الكود المختصر بقى الـSKU الحقيقي مباشرة، وSKU_ALIASES
        # تحت بقت fallback بس للـ21 مكوّن اللي أسماؤهم مختلفة تمامًا في
        # app.seed._seed_inventory_recipes (بيئة فاضية اتزرعت بـapp.seed
        # لوحده بس، من غير أي زرع تاني فوقه).
        if code in existing_skus:
            continue
        product = Product(
            branch_id=branch.id, warehouse_id=warehouse.id, name=name_en, name_ar=name_ar,
            sku=code, unit=unit, cost_price=cost,
            current_stock=stock, min_stock=D("2"), reorder_point=D("5"),
        )
        db.add(product)
        db.flush()
        db.add(StockMovement(
            branch_id=branch.id, product_id=product.id, warehouse_id=warehouse.id,
            movement_type="purchase_in", quantity=stock, unit_cost=cost,
            reference_type="seed", moved_at=datetime.utcnow(),
        ))
        inserted += 1
    db.flush()
    print(f"  ✓ New ingredients 2026: {inserted} inserted, {len(NEW_INGREDIENTS) - inserted} already existed")


def _resolve_product(prods: dict, code: str):
    """كود وصفة مختصر (POTATO/VEG-OIL/...) → Product حقيقي. الكود نفسه
    SKU مباشر أولاً (الاتفاقية الفعلية — راجع _seed_new_ingredients_2026)،
    وSKU_ALIASES fallback بس للـ21 مكوّن اللي أسماؤهم مختلفة في app.seed
    الأصلي (بيئة فاضية اتزرعت بـapp.seed لوحده، زي بيئات الاختبار المعزولة)."""
    if code in prods:
        return prods[code]
    alias = SKU_ALIASES.get(code)
    return prods.get(alias) if alias else None


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
    prods = {p.sku: p for p in db.query(Product).filter(Product.branch_id == branch.id).all()}
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
        new_lines = []
        missing = False
        for code, qty in lines:
            prod = _resolve_product(prods, code)
            if prod is None:
                skipped_sku += 1
                missing = True
                print(f"    WARN SKU not found: \'{code}\' (item \'{item_name}\')")
                continue
            new_lines.append((prod.id, qty))
        if missing:
            # لا تمسح الوصفة القديمة الشغالة لو مكوّن جديد ناقص — سطر
            # واحد مفقود يوقف كل الوصفة، مش يمسحها ويسيب الصنف من غير
            # وصفة خالص (نفس الباج اللي كان في النسخة الأصلية).
            print(f"    SKIPPED (kept existing recipe): \'{item_name}\'")
            continue
        db.query(DiningItemRecipeLine).filter(
            DiningItemRecipeLine.item_id == item.id
        ).delete()
        for product_id, qty in new_lines:
            db.add(DiningItemRecipeLine(item_id=item.id, product_id=product_id, quantity_per_unit=qty))
        inserted += 1
    db.flush()
    print(f"  ✓ {outlet_type}: {inserted} items written, {skipped_item} items skipped, {skipped_sku} SKUs skipped")


# ══════════════════════════════════════════════════════════════════════════════
# RESTAURANT RECIPES — PART 1: Starters + Sandwiches + Main Course
# ══════════════════════════════════════════════════════════════════════════════

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
