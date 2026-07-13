"""
app/seed_food.py
────────────────
Seed functions for restaurant & cafe:
  • _seed_inventory_products_full  — 100+ raw-material products with opening stock
  • _seed_restaurant_recipes        — recipe lines for all 44 restaurant items
  • _seed_cafe_recipes              — recipe lines for all 60 cafe items

Called from seed_all() in seed.py. All functions are idempotent:
products are upserted by SKU, recipe lines are deleted+re-inserted per item.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.orm import Session


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_cats(db: Session, branch_id: int) -> dict[str, int | None]:
    from app.modules.inventory.models import Category
    cats = {c.name: c.id for c in db.query(Category).filter(Category.branch_id == branch_id).all()}
    return {
        "food":  cats.get("Food Items"),
        "bev":   cats.get("Beverages"),
        "kit":   cats.get("Kitchen Supplies"),
        "raw":   cats.get("Raw Materials"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1.  INVENTORY PRODUCTS
# ─────────────────────────────────────────────────────────────────────────────

def _seed_inventory_products_full(db: Session) -> None:
    """100+ raw-material products for restaurant + cafe, with opening stock."""
    from app.modules.inventory.models import Product, Warehouse, StockMovement
    from app.modules.core.models import Branch

    branch = db.query(Branch).first()
    if not branch:
        return
    BID = branch.id
    WH  = db.query(Warehouse).filter(Warehouse.branch_id == BID).first()
    if not WH:
        return
    WH_ID = WH.id

    C = _get_cats(db, BID)
    existing = {p.sku: p for p in db.query(Product).filter(Product.branch_id == BID).all()}
    now = datetime.now(timezone.utc)

    # (sku, name, name_ar, unit, cost_egp, min_stock, reorder, cat_key, init_stock)
    PRODUCTS: list[tuple] = [
        # Proteins
        ("GRD-BEEF",    "Ground Beef",            "لحم مفروم",           "kg",    120, 5,  10, "food", 20),
        ("BEEF-FIL",    "Beef Fillet",             "فيليه لحم",           "kg",    250, 3,   6, "food", 10),
        ("CHKN-BRS",    "Chicken Breast",          "صدر دجاج",            "kg",     70, 5,  10, "food", 15),
        ("SHRIMP",      "Shrimp",                  "جمبري",               "kg",    200, 3,   6, "food",  8),
        ("FISH-FIL",    "Fish Fillet",             "فيليه سمك",           "kg",    180, 3,   6, "food",  8),
        ("CALAMARI",    "Calamari",                "كاليماري",            "kg",    150, 3,   5, "food",  6),
        ("SALAMI",      "Salami",                  "سلامي",               "kg",    200, 2,   4, "food",  5),
        ("TUNA-CAN",    "Canned Tuna",             "تونة معلبة",          "kg",     60, 3,   5, "food",  5),
        # Dairy & Eggs
        ("MOZ-CHSE",    "Mozzarella Cheese",       "جبنة موزاريلا",       "kg",    180, 4,   8, "food", 10),
        ("CHED-CHSE",   "Cheddar Cheese",          "جبنة شيدر",           "kg",    160, 3,   6, "food", 10),
        ("PARM-CHSE",   "Parmesan Cheese",         "جبنة بارميزان",       "kg",    280, 2,   4, "food",  4),
        ("FETA-CHSE",   "Feta Cheese",             "جبنة فيتا",           "kg",    150, 2,   4, "food",  6),
        ("CREAM-CHSE",  "Cream Cheese",            "جبنة كريم",           "kg",    120, 2,   4, "food",  4),
        ("MILK-FULL",   "Full Fat Milk",           "حليب كامل الدسم",     "liter",  25,10,  20, "bev",  30),
        ("BUTTER",      "Butter",                  "زبدة",                "kg",    140, 2,   4, "food",  5),
        ("CREAM",       "Cooking Cream",           "كريمة طبخ",           "liter",  80, 3,   5, "food",  6),
        ("YOGURT",      "Plain Yogurt",            "زبادي سادة",          "kg",     35, 5,  10, "food", 15),
        ("EGGS",        "Eggs",                    "بيض",                 "piece",   5,30,  60, "food",120),
        # Bakery
        ("PIZZA-DGH",   "Pizza Dough",             "عجينة بيتزا",         "kg",     20, 5,  10, "raw",  15),
        ("BRG-BUN",     "Burger Bun",              "خبز برجر",            "piece",   5,20,  40, "food",100),
        ("BREAD-SND",   "Sandwich Bread",          "خبز تورتيلا",         "piece",   3,20,  40, "food", 80),
        ("CROISSANT",   "Croissant",               "كرواسون",             "piece",  12, 5,  12, "food", 30),
        # Pasta & Rice
        ("PENNE",       "Penne Pasta",             "مكرونة بيني",         "kg",     25, 5,  10, "raw",  10),
        ("SPAGHET",     "Spaghetti",               "سباغيتي",             "kg",     25, 5,  10, "raw",  10),
        ("RICE-RAW",    "White Rice (raw)",        "أرز أبيض خام",        "kg",     18, 5,  10, "raw",  20),
        # Vegetables
        ("TOMATO",      "Fresh Tomato",            "طماطم طازجة",         "kg",     15, 5,  10, "food", 10),
        ("LETTUCE",     "Lettuce",                 "خس",                  "kg",     20, 3,   6, "food",  8),
        ("CUCUMBER",    "Cucumber",                "خيار",                "kg",     12, 3,   6, "food",  8),
        ("ONION",       "Onion",                   "بصل",                 "kg",      8, 3,   6, "food",  8),
        ("GARLIC",      "Garlic",                  "ثوم",                 "kg",     20, 2,   4, "food",  4),
        ("LEMON",       "Lemon",                   "ليمون",               "kg",     15, 3,   6, "food",  6),
        ("POTATO",      "Potato",                  "بطاطس",               "kg",     10, 5,  10, "food", 25),
        ("MUSHROOM",    "Mushroom",                "فطر",                 "kg",     60, 2,   4, "food",  4),
        ("SPINACH",     "Spinach",                 "سبانخ",               "kg",     25, 2,   4, "food",  4),
        # Fruits
        ("BANANA-F",    "Banana",                  "موز",                 "kg",     15, 5,  10, "food", 10),
        ("MANGO-F",     "Mango",                   "مانجو",               "kg",     20, 3,   6, "food",  6),
        ("STRAW-F",     "Strawberry",              "فراولة",              "kg",     40, 3,   6, "food",  6),
        ("GUAVA-F",     "Guava",                   "جوافة",               "kg",     18, 3,   6, "food",  6),
        ("ORANGE-F",    "Orange",                  "برتقال",              "kg",     12, 5,  10, "food", 10),
        ("WATER-F",     "Watermelon",              "بطيخ",                "kg",      8, 5,  10, "food", 10),
        ("KIWI-F",      "Kiwi",                    "كيوي",                "kg",     35, 2,   4, "food",  4),
        ("PINEAP-F",    "Pineapple",               "أناناس",              "kg",     25, 2,   4, "food",  4),
        ("GRAPE-F",     "Red Grapes",              "عنب أحمر",            "kg",     30, 2,   4, "food",  4),
        ("PEACH-F",     "Peach",                   "خوخ",                 "kg",     25, 2,   4, "food",  4),
        ("POMG-F",      "Pomegranate",             "رمان",                "kg",     30, 2,   4, "food",  4),
        ("CANT-F",      "Cantaloupe",              "شمام",                "kg",     12, 3,   6, "food",  6),
        ("AVOC-F",      "Avocado",                 "أفوكادو",             "kg",     80, 2,   4, "food",  4),
        ("APPLE-F",     "Apple",                   "تفاح",                "kg",     18, 3,   6, "food",  6),
        ("DATES-F",     "Dates",                   "تمر",                 "kg",     50, 2,   4, "food",  3),
        # Sauces & Condiments
        ("TOM-SAUCE",   "Tomato Sauce",            "صلصة طماطم",          "kg",     25, 5,  10, "kit",  10),
        ("WHITE-SAUCE", "White Sauce (Béchamel)",  "صلصة بيشاميل",        "kg",     30, 3,   6, "kit",   5),
        ("PESTO",       "Pesto Sauce",             "صلصة البيستو",        "kg",     80, 2,   4, "kit",   3),
        ("MAYO",        "Mayonnaise",              "مايونيز",             "kg",     40, 3,   6, "kit",   5),
        ("KETCHUP",     "Ketchup",                 "كاتشب",               "kg",     30, 3,   6, "kit",   5),
        ("TAHINI",      "Tahini",                  "طحينة",               "kg",     60, 2,   4, "kit",   4),
        ("SOY-SAUCE",   "Soy Sauce",               "صلصة صويا",           "liter",  45, 2,   4, "kit",   3),
        ("OYSTER-S",    "Oyster Sauce",            "صلصة المحار",         "liter",  55, 2,   3, "kit",   2),
        ("CESAR-S",     "Caesar Dressing",         "صلصة سيزر",           "liter",  90, 2,   4, "kit",   3),
        # Oils & Dry
        ("VEG-OIL",     "Vegetable Oil",           "زيت نباتي",           "liter",  25, 5,  10, "kit",  15),
        ("OLIVE-OIL",   "Olive Oil",               "زيت زيتون",           "liter",  80, 3,   6, "kit",   6),
        ("FLOUR",       "All-Purpose Flour",       "دقيق",                "kg",     12, 5,  10, "raw",  20),
        ("SUGAR",       "Sugar",                   "سكر",                 "kg",      8, 5,  10, "raw",  20),
        ("SALT",        "Salt",                    "ملح",                 "kg",      3, 3,   6, "kit",   5),
        ("PEPPER-B",    "Black Pepper",            "فلفل أسود",           "kg",     80, 1,   2, "kit",   2),
        ("MIXED-SP",    "Mixed Spices",            "بهارات مشكلة",        "kg",     60, 1,   2, "kit",   2),
        ("CORIANDER",   "Coriander",               "كزبرة",               "kg",     40, 1,   2, "kit",   2),
        ("BREADCRUM",   "Breadcrumbs",             "بقسماط",              "kg",     20, 2,   4, "kit",   4),
        ("PANKO",       "Panko",                   "بانكو",               "kg",     35, 2,   4, "kit",   3),
        ("COCONUT-M",   "Coconut Milk",            "حليب جوز هند",        "liter",  45, 2,   4, "kit",   4),
        ("FISH-SAUCE",  "Fish Sauce",              "صلصة السمك",          "liter",  50, 1,   2, "kit",   2),
        ("GREEN-CURRY", "Green Curry Paste",       "معجون كاري أخضر",     "kg",     70, 1,   2, "kit",   2),
        ("SWEET-CHILI", "Sweet Chili Sauce",       "صلصة تشيلي حلوة",    "liter",  40, 2,   4, "kit",   3),
        ("CASHEW",      "Cashew Nuts",             "كاجو",                "kg",    200, 1,   2, "food",  2),
        ("SPRING-W",    "Spring Roll Wrappers",    "أوراق سبرينج رول",    "piece",   2,20,  40, "kit",  50),
        ("SATAY-STICK", "Satay Skewers",           "أسياخ ساتيه",         "piece",   1,30,  60, "kit", 100),
        # Beverages raw materials
        ("COFFEE-B",    "Coffee Beans",            "حبوب قهوة",           "kg",    350, 2,   4, "bev",   5),
        ("ESPRESSO-P",  "Espresso Powder",         "بودرة إسبريسو",       "kg",    280, 2,   4, "bev",   3),
        ("COCOA-P",     "Cocoa Powder",            "كاكاو",               "kg",    120, 2,   4, "bev",   3),
        ("TEA-BAG",     "Lipton Tea Bags",         "أكياس شاي ليبتون",    "piece",   2,20,  50, "bev", 100),
        ("TURK-COFFE",  "Turkish Coffee",          "قهوة تركية",          "kg",    200, 1,   2, "bev",   2),
        ("ANISE",       "Anise",                   "يانسون",              "kg",     40, 1,   2, "bev",   2),
        ("HIBISCUS",    "Hibiscus",                "كركديه",              "kg",     50, 1,   2, "bev",   2),
        ("MINT-DRY",    "Dried Mint",              "نعناع مجفف",          "kg",     60, 1,   2, "bev",   2),
        ("NESCAFE-P",   "Nescafe Powder",          "نسكافيه",             "kg",    400, 1,   2, "bev",   2),
        ("CINNAMON",    "Cinnamon",                "قرفة",                "kg",     80, 1,   2, "bev",   1),
        ("VANILLA",     "Vanilla Extract",         "فانيليا",             "liter", 120, 1,   2, "bev",   2),
        ("HONEY",       "Honey",                   "عسل",                 "kg",    150, 2,   4, "bev",   4),
        ("CARAML-S",    "Caramel Sauce",           "صلصة كراميل",         "kg",     80, 2,   4, "bev",   3),
        ("CHOC-SYR",    "Chocolate Syrup",         "شراب شوكولاتة",       "liter",  60, 2,   4, "bev",   4),
        ("STRAWB-SYR",  "Strawberry Syrup",        "شراب فراولة",         "liter",  55, 2,   4, "bev",   3),
        ("MINT-SYR",    "Mint Syrup",              "شراب نعناع",          "liter",  50, 2,   4, "bev",   3),
        # Canned / bottled (sold as-is — still tracked in inventory)
        ("REDBULL-C",   "Red Bull Can",            "علبة ريد بول",        "piece",  55, 6,  12, "bev",  24),
        ("COLA-C",      "Cola Can/Bottle",         "كولا",                "piece",  15,12,  24, "bev",  48),
        ("SPRITE-C",    "Sprite Can/Bottle",       "سبرايت",              "piece",  15,12,  24, "bev",  48),
        ("SCHWEP-C",    "Schweppes Can",           "شويبس",               "piece",  15, 6,  12, "bev",  24),
        ("FAYROUZ-C",   "Fayrouz Bottle",          "فيروز",               "piece",  18, 6,  12, "bev",  24),
        ("WATER-SM",    "Small Water Bottle",      "مياه صغيرة",          "piece",   3,12,  24, "bev",  48),
        ("BEARL-C",     "Bearl Bottle",            "بيرل",                "piece",  18, 6,  12, "bev",  24),
        # Dessert
        ("ICE-CREAM",   "Ice Cream",               "آيس كريم",            "liter",  80, 3,   6, "food",  8),
        ("KUNAFA-BASE", "Kunafa Base",             "قاعدة كنافة",         "kg",     50, 2,   4, "food",  4),
        ("CHOC-DARK",   "Dark Chocolate",          "شوكولاتة داكنة",      "kg",    160, 1,   3, "food",  3),
        ("RICE-PAPER",  "Rice Paper",              "ورق أرز",             "piece",   3,20,  40, "kit",  40),
    ]

    added = updated = movements_added = 0
    for (sku, name, name_ar, unit, cost, min_s, reorder, cat_key, init_stock) in PRODUCTS:
        cat_id = C.get(cat_key)
        if sku in existing:
            p = existing[sku]
            p.category_id   = cat_id
            p.cost_price    = Decimal(str(cost))
            p.min_stock     = Decimal(str(min_s))
            p.reorder_point = Decimal(str(reorder))
            p.name_ar       = name_ar
            updated += 1
        else:
            p = Product(
                branch_id=BID, sku=sku, name=name, name_ar=name_ar,
                unit=unit, cost_price=Decimal(str(cost)),
                current_stock=Decimal("0"),
                min_stock=Decimal(str(min_s)),
                reorder_point=Decimal(str(reorder)),
                category_id=cat_id, warehouse_id=WH_ID, is_active=True,
            )
            db.add(p)
            db.flush()
            added += 1
            existing[sku] = p

        if float(p.current_stock) == 0 and init_stock > 0:
            p.current_stock = Decimal(str(init_stock))
            db.add(StockMovement(
                branch_id=BID, product_id=p.id, warehouse_id=WH_ID,
                movement_type="adjustment",
                quantity=Decimal(str(init_stock)),
                unit_cost=Decimal(str(cost)),
                reference_type="manual",
                notes="Opening stock — initial seed",
                moved_by=1,
                moved_at=now,
            ))
            movements_added += 1

    db.flush()
    print(f"  ✓ Inventory products: {added} added, {updated} updated, "
          f"{movements_added} opening-stock entries")


# ─────────────────────────────────────────────────────────────────────────────
# 2.  RESTAURANT RECIPES
# ─────────────────────────────────────────────────────────────────────────────

def _seed_restaurant_recipes(db: Session) -> None:
    """Recipe lines for all 44 restaurant menu items. Idempotent.

    DINING_CUTOVER_PLAN.md Batch 6 — dining.DiningItem/DiningItemRecipeLine
    (outlet_type='restaurant') بدل restaurant.MenuItem/MenuItemRecipeLine
    القديمين اللي اتحذفوا."""
    from app.modules.core.models import Branch
    from app.modules.dining.models import DiningItem, DiningItemRecipeLine, Outlet
    from app.modules.inventory.models import Product

    branch = db.query(Branch).first()
    if not branch:
        return
    outlet = db.query(Outlet).filter(Outlet.branch_id == branch.id, Outlet.outlet_type == "restaurant").first()
    if not outlet:
        return

    prods = {p.sku: p.id for p in db.query(Product).all()}
    items = {i.name: i.id for i in db.query(DiningItem).filter(DiningItem.outlet_id == outlet.id).all()}

    def pid(sku: str) -> int:
        v = prods.get(sku)
        if v is None:
            raise KeyError(f"product SKU not found: {sku}")
        return v

    def iid(name: str) -> int | None:
        return items.get(name)

    D = Decimal
    RECIPES: list[tuple[str, list[tuple[str, Decimal]]]] = [
        # Appetizers
        ("Chicken Satay", [("CHKN-BRS", D("0.150")), ("SATAY-STICK", D("5")),
                           ("SOY-SAUCE", D("0.020")), ("SWEET-CHILI", D("0.030")),
                           ("VEG-OIL", D("0.020")), ("GARLIC", D("0.010")), ("MIXED-SP", D("0.005"))]),
        ("Shrimp Kunafa",  [("SHRIMP", D("0.150")), ("KUNAFA-BASE", D("0.100")),
                            ("MOZ-CHSE", D("0.060")), ("BUTTER", D("0.030")), ("SUGAR", D("0.020"))]),
        ("Fried Calamari", [("CALAMARI", D("0.180")), ("FLOUR", D("0.050")), ("PANKO", D("0.040")),
                            ("EGGS", D("1")), ("VEG-OIL", D("0.080")), ("LEMON", D("0.050")),
                            ("MIXED-SP", D("0.008"))]),
        ("Vegetable Spring Rolls", [("SPRING-W", D("4")), ("CUCUMBER", D("0.040")),
                                    ("LETTUCE", D("0.040")), ("MUSHROOM", D("0.040")),
                                    ("SOY-SAUCE", D("0.020")), ("SWEET-CHILI", D("0.030")),
                                    ("VEG-OIL", D("0.060"))]),
        # Soups
        ("Vegetable Soup", [("TOMATO", D("0.080")), ("ONION", D("0.050")), ("POTATO", D("0.080")),
                            ("VEG-OIL", D("0.020")), ("MIXED-SP", D("0.006")), ("SALT", D("0.005"))]),
        ("Thai Beef Soup", [("BEEF-FIL", D("0.120")), ("MUSHROOM", D("0.060")),
                            ("SOY-SAUCE", D("0.020")), ("FISH-SAUCE", D("0.015")),
                            ("COCONUT-M", D("0.100")), ("LEMON", D("0.030")), ("MIXED-SP", D("0.008"))]),
        ("Seafood Soup",   [("SHRIMP", D("0.080")), ("FISH-FIL", D("0.080")), ("CALAMARI", D("0.060")),
                            ("CREAM", D("0.080")), ("ONION", D("0.040")), ("GARLIC", D("0.010")),
                            ("MIXED-SP", D("0.008")), ("BUTTER", D("0.020"))]),
        # Salads
        ("Green Salad",  [("LETTUCE", D("0.100")), ("TOMATO", D("0.060")), ("CUCUMBER", D("0.060")),
                          ("ONION", D("0.030")), ("LEMON", D("0.030")), ("OLIVE-OIL", D("0.020")),
                          ("SALT", D("0.003"))]),
        ("Caesar Salad", [("LETTUCE", D("0.120")), ("PARM-CHSE", D("0.030")),
                          ("CESAR-S", D("0.050")), ("BREADCRUM", D("0.020")), ("LEMON", D("0.020"))]),
        ("Greek Salad",  [("TOMATO", D("0.080")), ("CUCUMBER", D("0.080")), ("FETA-CHSE", D("0.060")),
                          ("ONION", D("0.030")), ("OLIVE-OIL", D("0.030")),
                          ("SALT", D("0.003")), ("PEPPER-B", D("0.002"))]),
        ("Fattoush Salad", [("TOMATO", D("0.080")), ("LETTUCE", D("0.080")), ("CUCUMBER", D("0.060")),
                            ("ONION", D("0.030")), ("LEMON", D("0.030")), ("OLIVE-OIL", D("0.025")),
                            ("BREAD-SND", D("1"))]),
        ("Caprese Salad",  [("TOMATO", D("0.120")), ("MOZ-CHSE", D("0.100")),
                            ("OLIVE-OIL", D("0.030")), ("SALT", D("0.003")), ("PEPPER-B", D("0.002"))]),
        # Sandwiches
        ("Beef Burger",   [("GRD-BEEF", D("0.180")), ("BRG-BUN", D("1")), ("CHED-CHSE", D("0.040")),
                           ("TOMATO", D("0.040")), ("LETTUCE", D("0.030")), ("MAYO", D("0.025")),
                           ("KETCHUP", D("0.020")), ("ONION", D("0.020"))]),
        ("Steak Sandwich",[("BEEF-FIL", D("0.180")), ("BREAD-SND", D("1")), ("CHED-CHSE", D("0.040")),
                           ("TOMATO", D("0.040")), ("LETTUCE", D("0.030")), ("MAYO", D("0.025")),
                           ("ONION", D("0.020"))]),
        ("Fried Chicken", [("CHKN-BRS", D("0.200")), ("BRG-BUN", D("1")), ("FLOUR", D("0.060")),
                           ("PANKO", D("0.040")), ("EGGS", D("1")), ("VEG-OIL", D("0.100")),
                           ("MAYO", D("0.025")), ("MIXED-SP", D("0.008"))]),
        ("Battaya Sandwich", [("CHKN-BRS", D("0.150")), ("BREAD-SND", D("1")),
                              ("TOMATO", D("0.040")), ("LETTUCE", D("0.030")),
                              ("TAHINI", D("0.030")), ("LEMON", D("0.020")), ("MIXED-SP", D("0.006"))]),
        # Main Dishes
        ("Chicken Grill",  [("CHKN-BRS", D("0.280")), ("OLIVE-OIL", D("0.025")),
                            ("GARLIC", D("0.015")), ("LEMON", D("0.050")),
                            ("MIXED-SP", D("0.010")), ("RICE-RAW", D("0.080"))]),
        ("Beef Grill",     [("BEEF-FIL", D("0.280")), ("OLIVE-OIL", D("0.025")),
                            ("GARLIC", D("0.015")), ("LEMON", D("0.050")),
                            ("MIXED-SP", D("0.010")), ("RICE-RAW", D("0.080"))]),
        ("Fish",           [("FISH-FIL", D("0.320")), ("OLIVE-OIL", D("0.030")),
                            ("GARLIC", D("0.015")), ("LEMON", D("0.060")),
                            ("MIXED-SP", D("0.010")), ("TOMATO", D("0.080")), ("ONION", D("0.050"))]),
        ("Shrimp Grill",   [("SHRIMP", D("0.280")), ("BUTTER", D("0.030")),
                            ("GARLIC", D("0.015")), ("LEMON", D("0.050")),
                            ("MIXED-SP", D("0.008")), ("RICE-RAW", D("0.080"))]),
        ("Mixed Grill",    [("BEEF-FIL", D("0.120")), ("CHKN-BRS", D("0.120")),
                            ("SHRIMP", D("0.080")), ("OLIVE-OIL", D("0.025")),
                            ("GARLIC", D("0.015")), ("LEMON", D("0.060")),
                            ("MIXED-SP", D("0.010")), ("RICE-RAW", D("0.080"))]),
        ("Cashew Chicken", [("CHKN-BRS", D("0.200")), ("CASHEW", D("0.040")),
                            ("SOY-SAUCE", D("0.030")), ("OYSTER-S", D("0.020")),
                            ("VEG-OIL", D("0.030")), ("GARLIC", D("0.010")),
                            ("ONION", D("0.050")), ("RICE-RAW", D("0.080"))]),
        ("Sweet Sour Chicken", [("CHKN-BRS", D("0.200")), ("FLOUR", D("0.040")),
                                ("EGGS", D("1")), ("SWEET-CHILI", D("0.050")),
                                ("SOY-SAUCE", D("0.020")), ("VEG-OIL", D("0.060")),
                                ("ONION", D("0.050")), ("RICE-RAW", D("0.080"))]),
        ("Green Curry Chicken", [("CHKN-BRS", D("0.200")), ("GREEN-CURRY", D("0.030")),
                                 ("COCONUT-M", D("0.150")), ("VEG-OIL", D("0.020")),
                                 ("GARLIC", D("0.010")), ("RICE-RAW", D("0.080"))]),
        ("Black Pepper Beef",   [("BEEF-FIL", D("0.200")), ("PEPPER-B", D("0.010")),
                                 ("SOY-SAUCE", D("0.025")), ("OYSTER-S", D("0.020")),
                                 ("ONION", D("0.060")), ("VEG-OIL", D("0.030")),
                                 ("RICE-RAW", D("0.080"))]),
        ("Pad Thai", [("CHKN-BRS", D("0.120")), ("SHRIMP", D("0.080")),
                      ("RICE-RAW", D("0.120")), ("EGGS", D("1")),
                      ("SOY-SAUCE", D("0.025")), ("FISH-SAUCE", D("0.015")),
                      ("VEG-OIL", D("0.030")), ("LEMON", D("0.030"))]),
        # Pizza
        ("Margherita Pizza",   [("PIZZA-DGH", D("0.200")), ("TOM-SAUCE", D("0.080")),
                                ("MOZ-CHSE", D("0.150")), ("OLIVE-OIL", D("0.015")),
                                ("MIXED-SP", D("0.005"))]),
        ("Salami Pizza",       [("PIZZA-DGH", D("0.200")), ("TOM-SAUCE", D("0.080")),
                                ("MOZ-CHSE", D("0.130")), ("SALAMI", D("0.060")),
                                ("OLIVE-OIL", D("0.015"))]),
        ("Smoked Turkey Pizza",[("PIZZA-DGH", D("0.200")), ("WHITE-SAUCE", D("0.080")),
                                ("MOZ-CHSE", D("0.130")), ("MUSHROOM", D("0.060")),
                                ("OLIVE-OIL", D("0.015"))]),
        ("Tuna Pizza",         [("PIZZA-DGH", D("0.200")), ("TOM-SAUCE", D("0.080")),
                                ("MOZ-CHSE", D("0.120")), ("TUNA-CAN", D("0.080")),
                                ("ONION", D("0.040")), ("OLIVE-OIL", D("0.015"))]),
        ("Shrimp Pizza",       [("PIZZA-DGH", D("0.200")), ("WHITE-SAUCE", D("0.080")),
                                ("MOZ-CHSE", D("0.120")), ("SHRIMP", D("0.100")),
                                ("GARLIC", D("0.010")), ("OLIVE-OIL", D("0.015"))]),
        ("Seafood Pizza",      [("PIZZA-DGH", D("0.200")), ("WHITE-SAUCE", D("0.080")),
                                ("MOZ-CHSE", D("0.100")), ("SHRIMP", D("0.060")),
                                ("CALAMARI", D("0.060")), ("FISH-FIL", D("0.060")),
                                ("OLIVE-OIL", D("0.015"))]),
        # Pasta
        ("Pen Red Sauce",   [("PENNE", D("0.120")), ("TOM-SAUCE", D("0.100")),
                             ("GARLIC", D("0.010")), ("OLIVE-OIL", D("0.020")),
                             ("PARM-CHSE", D("0.025"))]),
        ("Pen White Sauce",  [("PENNE", D("0.120")), ("WHITE-SAUCE", D("0.100")),
                              ("CREAM", D("0.060")), ("GARLIC", D("0.010")),
                              ("BUTTER", D("0.020")), ("PARM-CHSE", D("0.025"))]),
        ("Seafood Spaghetti",[("SPAGHET", D("0.120")), ("TOM-SAUCE", D("0.080")),
                              ("SHRIMP", D("0.080")), ("CALAMARI", D("0.060")),
                              ("GARLIC", D("0.015")), ("OLIVE-OIL", D("0.025"))]),
        ("Pink Shrimp Spaghetti", [("SPAGHET", D("0.120")), ("TOM-SAUCE", D("0.050")),
                                   ("CREAM", D("0.080")), ("SHRIMP", D("0.120")),
                                   ("GARLIC", D("0.015")), ("BUTTER", D("0.020"))]),
        ("Ricola",      [("SPAGHET", D("0.120")), ("WHITE-SAUCE", D("0.080")),
                         ("CREAM", D("0.060")), ("CHKN-BRS", D("0.100")),
                         ("MUSHROOM", D("0.050")), ("PARM-CHSE", D("0.025"))]),
        ("White Penca", [("PENNE", D("0.120")), ("CREAM", D("0.080")),
                         ("WHITE-SAUCE", D("0.060")), ("MOZ-CHSE", D("0.060")),
                         ("GARLIC", D("0.010")), ("BUTTER", D("0.020"))]),
        ("Cutroforma",  [("SPAGHET", D("0.120")), ("TOM-SAUCE", D("0.080")),
                         ("BEEF-FIL", D("0.100")), ("GARLIC", D("0.010")),
                         ("OLIVE-OIL", D("0.020")), ("PARM-CHSE", D("0.025"))]),
        ("Cutro Estagoini", [("SPAGHET", D("0.120")), ("PESTO", D("0.060")),
                             ("CHKN-BRS", D("0.100")), ("PARM-CHSE", D("0.030")),
                             ("OLIVE-OIL", D("0.020"))]),
        # Extras
        ("French Fries", [("POTATO", D("0.250")), ("VEG-OIL", D("0.100")),
                          ("SALT", D("0.005")), ("KETCHUP", D("0.030"))]),
        ("White Rice",   [("RICE-RAW", D("0.100")), ("VEG-OIL", D("0.010")), ("SALT", D("0.003"))]),
        # Dessert
        ("Fried Ice Cream", [("ICE-CREAM", D("0.150")), ("RICE-PAPER", D("2")),
                             ("VEG-OIL", D("0.080")), ("CHOC-SYR", D("0.030"))]),
        ("Fried Banana",    [("BANANA-F", D("0.200")), ("FLOUR", D("0.040")),
                             ("EGGS", D("1")), ("VEG-OIL", D("0.080")), ("HONEY", D("0.030"))]),
    ]

    seeded = 0
    for item_name, lines in RECIPES:
        item_id = iid(item_name)
        if item_id is None:
            continue
        db.query(DiningItemRecipeLine).filter(DiningItemRecipeLine.item_id == item_id).delete()
        for sku, qty in lines:
            try:
                db.add(DiningItemRecipeLine(item_id=item_id, product_id=pid(sku),
                                            quantity_per_unit=qty))
            except KeyError as e:
                print(f"    WARN: {e}")
        seeded += 1

    db.flush()
    print(f"  ✓ Restaurant recipes: {seeded} items, "
          f"{sum(len(r[1]) for r in RECIPES)} ingredient lines")


# ─────────────────────────────────────────────────────────────────────────────
# 3.  CAFE RECIPES
# ─────────────────────────────────────────────────────────────────────────────

def _seed_cafe_recipes(db: Session) -> None:
    """Recipe lines for all 60 cafe items. Idempotent.

    DINING_CUTOVER_PLAN.md Batch 6 — dining.DiningItem/DiningItemRecipeLine
    (outlet_type='cafe') بدل cafe.CafeItem/CafeItemRecipeLine القديمين
    اللي اتحذفوا."""
    from app.modules.core.models import Branch
    from app.modules.dining.models import DiningItem, DiningItemRecipeLine, Outlet
    from app.modules.inventory.models import Product

    branch = db.query(Branch).first()
    if not branch:
        return
    outlet = db.query(Outlet).filter(Outlet.branch_id == branch.id, Outlet.outlet_type == "cafe").first()
    if not outlet:
        return

    prods = {p.sku: p.id for p in db.query(Product).all()}
    items = {i.name: i.id for i in db.query(DiningItem).filter(DiningItem.outlet_id == outlet.id).all()}

    def pid(sku: str) -> int:
        v = prods.get(sku)
        if v is None:
            raise KeyError(f"product SKU not found: {sku}")
        return v

    def iid(name: str) -> int | None:
        return items.get(name)

    D = Decimal
    RECIPES: list[tuple[str, list[tuple[str, Decimal]]]] = [
        # Packaged (1-to-1 stock deduction)
        ("Cola",         [("COLA-C",    D("1"))]),
        ("Sprite",       [("SPRITE-C",  D("1"))]),
        ("Schweppes",    [("SCHWEP-C",  D("1"))]),
        ("Fayrouz",      [("FAYROUZ-C", D("1"))]),
        ("Redbull",      [("REDBULL-C", D("1"))]),
        ("Small Water",  [("WATER-SM",  D("1"))]),
        ("Bearl",        [("BEARL-C",   D("1"))]),
        # House Cocktails
        ("Al Khaima Cocktail", [("MANGO-F", D("0.100")), ("STRAW-F", D("0.080")),
                                ("ORANGE-F", D("0.100")), ("BANANA-F", D("0.080")),
                                ("SUGAR", D("0.020")), ("MILK-FULL", D("0.100"))]),
        ("Hawaiian Cocktail",  [("PINEAP-F", D("0.120")), ("MANGO-F", D("0.100")),
                                ("ORANGE-F", D("0.080")), ("COCONUT-M", D("0.080")),
                                ("SUGAR", D("0.020"))]),
        ("Power Cocktail",     [("BANANA-F", D("0.120")), ("MANGO-F", D("0.100")),
                                ("DATES-F", D("0.040")), ("HONEY", D("0.020")),
                                ("MILK-FULL", D("0.150"))]),
        ("Cup Jack",           [("STRAW-F", D("0.100")), ("GRAPE-F", D("0.100")),
                                ("KIWI-F", D("0.060")), ("SUGAR", D("0.020")),
                                ("MILK-FULL", D("0.100"))]),
        ("Fakhfakhina Ace",    [("ORANGE-F", D("0.150")), ("MANGO-F", D("0.100")),
                                ("PINEAP-F", D("0.080")), ("LEMON", D("0.030")),
                                ("SUGAR", D("0.020"))]),
        ("Africano Cocktail",  [("MANGO-F", D("0.120")), ("PINEAP-F", D("0.100")),
                                ("BANANA-F", D("0.080")), ("COCONUT-M", D("0.080")),
                                ("SUGAR", D("0.020"))]),
        ("Super Viagra",       [("MANGO-F", D("0.100")), ("BANANA-F", D("0.100")),
                                ("STRAW-F", D("0.080")), ("HONEY", D("0.025")),
                                ("MILK-FULL", D("0.120")), ("DATES-F", D("0.040"))]),
        ("Fruit Yogurt",       [("STRAW-F", D("0.080")), ("BANANA-F", D("0.080")),
                                ("YOGURT", D("0.200")), ("HONEY", D("0.020")),
                                ("SUGAR", D("0.015"))]),
        # Fresh Juices
        ("Fresh Orange Juice", [("ORANGE-F", D("0.400")), ("SUGAR", D("0.015"))]),
        ("Mango",            [("MANGO-F",  D("0.200")), ("SUGAR", D("0.020")), ("MILK-FULL", D("0.080"))]),
        ("Strawberry",       [("STRAW-F",  D("0.200")), ("SUGAR", D("0.020")), ("MILK-FULL", D("0.080"))]),
        ("Guava",            [("GUAVA-F",  D("0.220")), ("SUGAR", D("0.020")), ("MILK-FULL", D("0.060"))]),
        ("Cantaloupe",       [("CANT-F",   D("0.300")), ("SUGAR", D("0.020"))]),
        ("Pomegranate",      [("POMG-F",   D("0.250")), ("SUGAR", D("0.015"))]),
        ("Watermelon",       [("WATER-F",  D("0.400")), ("SUGAR", D("0.010"))]),
        ("Kiwi",             [("KIWI-F",   D("0.180")), ("SUGAR", D("0.020")), ("MILK-FULL", D("0.080"))]),
        ("Jujube",           [("APPLE-F",  D("0.250")), ("SUGAR", D("0.020"))]),
        ("Peach Juice",      [("PEACH-F",  D("0.220")), ("SUGAR", D("0.020")), ("MILK-FULL", D("0.060"))]),
        ("Pineapple Juice",  [("PINEAP-F", D("0.200")), ("SUGAR", D("0.020"))]),
        ("Apple Juice with Yogurt", [("APPLE-F", D("0.200")), ("YOGURT", D("0.120")),
                                     ("HONEY", D("0.020"))]),
        ("Red Grape Juice",  [("GRAPE-F",  D("0.250")), ("SUGAR", D("0.020"))]),
        # Mocktails
        ("Fresh Lemon",  [("LEMON", D("0.080")), ("SUGAR", D("0.030")), ("MINT-SYR", D("0.020"))]),
        ("French Lemon", [("LEMON", D("0.080")), ("SUGAR", D("0.030")), ("STRAWB-SYR", D("0.025"))]),
        ("Lemon Mint",   [("LEMON", D("0.080")), ("MINT-SYR", D("0.025")), ("SUGAR", D("0.025"))]),
        ("Mojito Soda",  [("LEMON", D("0.060")), ("MINT-DRY", D("0.005")), ("MINT-SYR", D("0.025")),
                          ("SUGAR", D("0.020")), ("SPRITE-C", D("1"))]),
        ("Mojito Red Bull", [("LEMON", D("0.060")), ("MINT-DRY", D("0.005")),
                             ("MINT-SYR", D("0.025")), ("REDBULL-C", D("1"))]),
        ("Sunrise",  [("ORANGE-F", D("0.150")), ("STRAW-F", D("0.080")),
                      ("STRAWB-SYR", D("0.025")), ("SUGAR", D("0.015"))]),
        ("Sunshine", [("ORANGE-F", D("0.150")), ("MANGO-F", D("0.100")), ("SUGAR", D("0.020"))]),
        # Yogurt
        ("Plain Yogurt",      [("YOGURT", D("0.250")), ("HONEY", D("0.020"))]),
        ("Honey Yogurt",      [("YOGURT", D("0.220")), ("HONEY", D("0.040"))]),
        ("Chocolate Yogurt",  [("YOGURT", D("0.200")), ("CHOC-SYR", D("0.040")), ("SUGAR", D("0.015"))]),
        ("Banana with Yogurt",[("BANANA-F", D("0.120")), ("YOGURT", D("0.180")), ("HONEY", D("0.020"))]),
        ("Dates with Yogurt", [("DATES-F", D("0.040")), ("YOGURT", D("0.200")), ("HONEY", D("0.020"))]),
        ("Avocado",           [("AVOC-F", D("0.150")), ("HONEY", D("0.020")), ("MILK-FULL", D("0.120"))]),
        # Fruit Salads
        ("Fruit Salad Tent",   [("BANANA-F", D("0.060")), ("STRAW-F", D("0.060")),
                                ("MANGO-F", D("0.060")), ("KIWI-F", D("0.040")),
                                ("ORANGE-F", D("0.060")), ("HONEY", D("0.020"))]),
        ("Cinderella Fruit Salad", [("APPLE-F", D("0.060")), ("BANANA-F", D("0.060")),
                                    ("STRAW-F", D("0.060")), ("GRAPE-F", D("0.050")),
                                    ("KIWI-F", D("0.040")), ("HONEY", D("0.020"))]),
        ("Dahab Fruit Salad",  [("MANGO-F", D("0.080")), ("PINEAP-F", D("0.060")),
                                ("CANT-F", D("0.060")), ("WATER-F", D("0.060")),
                                ("HONEY", D("0.020"))]),
        ("Tropical Fruit Salad", [("MANGO-F", D("0.080")), ("PINEAP-F", D("0.080")),
                                  ("KIWI-F", D("0.040")), ("COCONUT-M", D("0.040")),
                                  ("HONEY", D("0.020"))]),
        # Specialty blended
        ("Oreo",  [("MILK-FULL", D("0.150")), ("ICE-CREAM", D("0.080")),
                   ("CHOC-SYR", D("0.030")), ("SUGAR", D("0.020"))]),
        ("Boreo", [("MILK-FULL", D("0.150")), ("ICE-CREAM", D("0.080")),
                   ("CHOC-SYR", D("0.030")), ("CARAML-S", D("0.025"))]),
        # Hot Drinks
        ("Single Espresso",        [("COFFEE-B",   D("0.007"))]),
        ("Double Espresso",        [("COFFEE-B",   D("0.014"))]),
        ("Single Shot Cappuccino", [("COFFEE-B",   D("0.007")), ("MILK-FULL", D("0.120")),
                                    ("SUGAR", D("0.010"))]),
        ("Latte",                  [("COFFEE-B",   D("0.007")), ("MILK-FULL", D("0.200")),
                                    ("SUGAR", D("0.010"))]),
        ("American Coffee",        [("COFFEE-B",   D("0.010")), ("SUGAR", D("0.010"))]),
        ("French Coffee",          [("ESPRESSO-P", D("0.012")), ("MILK-FULL", D("0.100")),
                                    ("CARAML-S", D("0.020"))]),
        ("Hot Chocolate",          [("COCOA-P",    D("0.025")), ("MILK-FULL", D("0.200")),
                                    ("SUGAR", D("0.020"))]),
        ("Nescafe",                [("NESCAFE-P",  D("0.010")), ("MILK-FULL", D("0.150")),
                                    ("SUGAR", D("0.015"))]),
        ("Micato",                 [("NESCAFE-P",  D("0.008")), ("MILK-FULL", D("0.200")),
                                    ("SUGAR", D("0.015"))]),
        ("Turkish Coffee",         [("TURK-COFFE", D("0.012")), ("SUGAR", D("0.010"))]),
        ("Lipton Tea",             [("TEA-BAG",    D("1")),     ("SUGAR", D("0.015"))]),
        ("Tea with Milk",          [("TEA-BAG",    D("1")),     ("MILK-FULL", D("0.100")),
                                    ("SUGAR", D("0.015"))]),
        ("Anise-Hibiscus-Mint",    [("ANISE", D("0.005")), ("HIBISCUS", D("0.005")),
                                    ("MINT-DRY", D("0.003")), ("SUGAR", D("0.015"))]),
    ]

    seeded = 0
    for item_name, lines in RECIPES:
        item_id = iid(item_name)
        if item_id is None:
            continue
        db.query(DiningItemRecipeLine).filter(DiningItemRecipeLine.item_id == item_id).delete()
        for sku, qty in lines:
            try:
                db.add(DiningItemRecipeLine(item_id=item_id, product_id=pid(sku),
                                            quantity_per_unit=qty))
            except KeyError as e:
                print(f"    WARN: {e}")
        seeded += 1

    db.flush()
    print(f"  ✓ Cafe recipes: {seeded} items, "
          f"{sum(len(r[1]) for r in RECIPES)} ingredient lines")
