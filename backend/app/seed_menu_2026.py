"""
app/seed_menu_2026.py
────────────────────────────────────────────────────────────────────────
منيو المطعم/الكافيه 2026 (11 صورة حقيقية، راجع data/menu/MENU_UPDATE_
REPORT_2026.md) — مستقل عن app/seed.py (dev/test فقط)، آمن يتشغّل على
production مباشرة.

⚠️ نسخة مُصلَّحة (2026-08-03) من data/menu/seed_menu_2026.py الأصلية —
كانت بتحاول تكتب في DiningItem.sort_order/description_ar اللي ماكانوش
موجودين خالص على الموديل (مش بس الداتابيز)، فكانت هتقع بـTypeError فورًا
على أول صنف جديد (راجع migration a7c3f0e9d5b2 اللي ضافت الأعمدة دي
فعليًا في الموديل والداتابيز مع بعض). نفس المشكلة اتصلحت هنا +
تكرار _upsert_item اتشال (كان معرّف ومش مستخدم، الحلقات كانت بتكرر نفس
منطقه يدويًا) + الفئات القديمة اللي مش في المنيو الجديد بقت تتقفل
(is_active=False) بدل ما تفضل معلّقة فاضية للأبد.

يعمل upsert آمن:
  - DiningItem موجود بنفس الاسم في نفس الـ outlet  → UPDATE
  - DiningItem غير موجود                            → INSERT جديد
  - صنف في الـ database لكن مش في المنيو الجديد     → is_available=False (لا حذف)
  - نفس المنطق على DiningCategory (is_active بدل is_available)

الاستخدام:
    from app.seed_menu_2026 import update_menu_2026
    from app.core.database import SessionLocal
    db = SessionLocal()
    update_menu_2026(db)
    db.commit()
"""
from __future__ import annotations

from decimal import Decimal
from sqlalchemy.orm import Session


# ─── Public entry point ───────────────────────────────────────────────────────

def update_menu_2026(db: Session) -> None:
    """نقطة الدخول الرئيسية — استدعِها بعد نسخ الملف لـ backend/app/."""
    print("▶ update_menu_2026: starting...")
    _update_restaurant_menu(db)
    _update_cafe_menu(db)
    db.flush()
    print("✓ update_menu_2026: done. Call db.commit() to persist.")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_outlet(db: Session, outlet_type: str):
    from app.modules.dining.models import Outlet
    from app.modules.core.models import Branch
    branch = db.query(Branch).first()
    if not branch:
        raise RuntimeError("No branch found — run main seed first.")
    outlet = db.query(Outlet).filter(
        Outlet.branch_id == branch.id,
        Outlet.outlet_type == outlet_type,
    ).first()
    if not outlet:
        raise RuntimeError(
            f"Outlet type='{outlet_type}' not found — run main seed first."
        )
    return branch, outlet


def _upsert_category(db: Session, branch_id: int, outlet_id: int,
                     name_en: str, name_ar: str, sort_order: int) -> int:
    """GET or CREATE — returns category id."""
    from app.modules.dining.models import DiningCategory
    cat = db.query(DiningCategory).filter(
        DiningCategory.outlet_id == outlet_id,
        DiningCategory.name == name_en,
    ).first()
    if cat:
        cat.name_ar    = name_ar
        cat.sort_order = sort_order
        cat.is_active  = True
        return cat.id
    cat = DiningCategory(
        branch_id=branch_id, outlet_id=outlet_id,
        name=name_en, name_ar=name_ar, sort_order=sort_order, is_active=True,
    )
    db.add(cat)
    db.flush()
    return cat.id


def _upsert_item(db: Session, *, branch_id: int, outlet_id: int,
                 category_id: int, name_en: str, name_ar: str,
                 price: Decimal, station: str, sort_order: int,
                 description: str | None = None,
                 description_ar: str | None = None) -> None:
    from app.modules.dining.models import DiningItem
    item = db.query(DiningItem).filter(
        DiningItem.outlet_id == outlet_id,
        DiningItem.name == name_en,
    ).first()
    if item:
        item.price        = price
        item.name_ar      = name_ar
        item.category_id  = category_id
        item.station      = station
        item.sort_order   = sort_order
        item.is_available = True
        if description:
            item.description    = description
        if description_ar:
            item.description_ar = description_ar
    else:
        item = DiningItem(
            branch_id=branch_id, outlet_id=outlet_id,
            category_id=category_id, name=name_en, name_ar=name_ar,
            price=price, station=station, sort_order=sort_order,
            is_available=True,
            description=description, description_ar=description_ar,
        )
        db.add(item)


def _deactivate_removed_items(db: Session, outlet_id: int, active_names: set[str]) -> int:
    """أصناف في الـ DB لكن مش في المنيو الجديد → is_available=False (لا حذف —
    قد تكون مرتبطة بطلبات/وصفات تاريخية حقيقية)."""
    from app.modules.dining.models import DiningItem
    items = db.query(DiningItem).filter(DiningItem.outlet_id == outlet_id).all()
    count = 0
    for item in items:
        if item.name not in active_names:
            item.is_available = False
            count += 1
    return count


def _deactivate_removed_categories(db: Session, outlet_id: int, active_names: set[str]) -> int:
    """فئات في الـ DB لكن مش في المنيو الجديد → is_active=False. بدون ده
    كانت الفئات القديمة (زي "Salad"/"Main Dish" اللي حلّ محلها "Salads"/
    "Main Course" بأسماء إنجليزية مختلفة) هتفضل ظاهرة فاضية للأبد في شاشات
    الإدارة جنب الفئات الجديدة."""
    from app.modules.dining.models import DiningCategory
    cats = db.query(DiningCategory).filter(DiningCategory.outlet_id == outlet_id).all()
    count = 0
    for cat in cats:
        if cat.name not in active_names:
            cat.is_active = False
            count += 1
    return count


# ─── Restaurant 2026 ──────────────────────────────────────────────────────────

def _update_restaurant_menu(db: Session) -> None:
    D = Decimal
    branch, outlet = _get_outlet(db, "restaurant")

    # ── Categories (name_en, name_ar, sort_order) ─────────────────────────
    CATEGORIES = [
        ("Starters",    "المقبلات",             0),
        ("Sandwiches",  "الساندوتشات",          1),
        ("Main Course", "الأطباق الرئيسية",     2),
        ("Salads",      "السلطات",              3),
        ("Breakfast",   "الإفطار",              4),
        ("Seafood",     "المأكولات البحرية",    5),
        ("Pizza",       "البيتزا",              6),
        ("Pasta",       "الباستا",              7),
    ]
    cat_map: dict[str, int] = {}
    for name_en, name_ar, sort in CATEGORIES:
        cat_map[name_en] = _upsert_category(
            db, branch.id, outlet.id, name_en, name_ar, sort
        )
    _deactivate_removed_categories(db, outlet.id, {c[0] for c in CATEGORIES})

    # ── Items (sort_id, cat_en, name_en, name_ar, price, station, desc_en, desc_ar) ──
    # sort_id = رقم الصنف في المنيو الحقيقي (1-56) — يُخزّن في sort_order
    ITEMS: list[tuple] = [
        # — Starters —
        (1,  "Starters", "Spicy Potato",
         "بطاطس حارة", D("110"), "hot",
         "Potato cubes mixed with spices and coriander.",
         "مكعبات بطاطس متبلة بالبهارات والكزبرة."),

        (2,  "Starters", "Chicken Wings",
         "أجنحة دجاج", D("190"), "hot",
         "8 pieces crispy chicken wings.",
         "8 قطع أجنحة دجاج مقرمشة."),

        (3,  "Starters", "Bruschetta",
         "بروشيتا", D("90"), "cold",
         "2 pieces. Bread topped with tomatoes, garlic and oregano.",
         "2 قطعة. خبز محمص مع الطماطم والثوم والأوريجانو."),

        (4,  "Starters", "Chips",
         "بطاطس مقلية", D("80"), "hot",
         "Crispy fried potato chips.",
         "بطاطس مقلية مقرمشة."),

        # — Sandwiches —
        (5,  "Sandwiches", "Shish Tawook Sandwich",
         "ساندوتش شيش طاووق", D("260"), "grill",
         "Grilled marinated chicken breast, lettuce, cheese, garlic sauce and pickles.",
         "صدر دجاج مشوي متبل مع خس، صوص الثوم، ومخلل."),

        (6,  "Sandwiches", "Chicken Shawarma Sandwich",
         "ساندوتش شاورما دجاج", D("260"), "grill",
         "Marinated chicken with lettuce, tomato, pickles and garlic sauce.",
         "شاورما دجاج متبلة مع خس، طماطم، مخلل، وصوص الثوم."),

        (7,  "Sandwiches", "Kofta Sandwich",
         "ساندوتش كفتة", D("260"), "grill",
         "Grilled minced kofta, tomato, onion, pickles and sesame sauce.",
         "كفتة مشوية مع طماطم، بصل، مخلل، وصوص السمسم."),

        (8,  "Sandwiches", "Fajita Sandwich",
         "ساندوتش فاهيتا", D("260"), "grill",
         "Grilled sliced chicken, coloured pepper, onion, pickles, mayo and cheese.",
         "شرائح دجاج مشوية مع فلفل ألوان، بصل، مخلل، مايونيز، وجبنة."),

        (9,  "Sandwiches", "Chicken Crispy Sandwich",
         "ساندوتش دجاج كريسبي", D("260"), "hot",
         "Fried crispy chicken, lettuce, tomato and mayo sauce.",
         "دجاج كريسبي مقرمش مع خس، طماطم، ومايونيز."),

        (10, "Sandwiches", "Mexican Sandwich",
         "ساندوتش مكسيكان", D("260"), "grill",
         "Chicken breast with coloured pepper and onion.",
         "صدر دجاج مع فلفل ألوان وبصل."),

        (11, "Sandwiches", "Crystal Sandwich",
         "ساندوتش كريستال", D("260"), "hot",
         "Chicken breast, french fries, lettuce, pickles and garlic sauce.",
         "صدر دجاج، بطاطس مقلية، خس، مخلل، وصوص الثوم."),

        # — Main Course —
        (12, "Main Course", "Grilled Chicken Breast",
         "صدر دجاج مشوي", D("330"), "grill",
         "Grilled chicken breast with grilled vegetables.",
         "صدر دجاج مشوي مع خضار مشوية."),

        (13, "Main Course", "Chicken Breast with Mushroom Sauce",
         "صدر دجاج بصوص المشروم", D("330"), "hot",
         "Chicken breast with mushroom cream sauce.",
         "صدر دجاج بصوص المشروم الكريمي."),

        (14, "Main Course", "Grilled Whole Chicken",
         "دجاجة مشوية كاملة", D("420"), "grill",
         "Full grilled whole chicken, served with salad and chips or rice.",
         "دجاجة مشوية كاملة مع سلطة وأرز أو بطاطس."),

        (15, "Main Course", "Grilled Half Chicken",
         "نصف دجاجة مشوية", D("280"), "grill",
         "Grilled half chicken, served with salad and chips or rice.",
         "نصف دجاجة مشوية مع سلطة وأرز أو بطاطس."),

        (16, "Main Course", "Escalope Panne & Chips",
         "إسكالوب بانيه مع بطاطس مقلية", D("340"), "hot",
         "Escalope panne served with chips.",
         "إسكالوب بانيه مع بطاطس مقلية."),

        (17, "Main Course", "Chicken Crispy & Chips",
         "دجاج كريسبي مع بطاطس مقلية", D("290"), "hot",
         "Crispy fried chicken served with chips.",
         "دجاج كريسبي مع بطاطس مقلية."),

        (18, "Main Course", "Chicken Nuggets & Chips",
         "ناجتس دجاج مع بطاطس مقلية", D("190"), "hot",
         "8 pieces chicken nuggets served with chips.",
         "8 قطع ناجتس دجاج مع بطاطس مقلية."),

        (19, "Main Course", "Cheese Burger & Chips",
         "تشيز برجر مع بطاطس مقلية", D("250"), "grill",
         "Cheese burger served with chips.",
         "تشيز برجر مع بطاطس مقلية."),

        (20, "Main Course", "Beef Burger & Chips",
         "بيف برجر مع بطاطس مقلية", D("230"), "grill",
         "Beef burger served with chips.",
         "بيف برجر مع بطاطس مقلية."),

        (21, "Main Course", "Chicken Burger & Chips",
         "تشيكن برجر مع بطاطس مقلية", D("230"), "grill",
         "Chicken burger served with chips.",
         "تشيكن برجر مع بطاطس مقلية."),

        (22, "Main Course", "Shish Tawook Platter",
         "طبق شيش طاووق", D("320"), "grill",
         "Shish tawook platter with salad and chips or rice.",
         "طبق شيش طاووق مع سلطة وأرز أو بطاطس."),

        (23, "Main Course", "Peri-Peri Shish Tawook",
         "شيش طاووق بيري بيري", D("330"), "grill",
         "Peri-peri marinated shish tawook platter.",
         "طبق شيش طاووق بيري بيري مع سلطة وأرز أو بطاطس."),

        (24, "Main Course", "Kofta Platter",
         "طبق كفتة", D("320"), "grill",
         "Kofta platter with salad and chips or rice.",
         "طبق كفتة مع سلطة وأرز أو بطاطس."),

        (25, "Main Course", "Chicken Shawarma Platter",
         "طبق شاورما دجاج", D("320"), "grill",
         "Chicken shawarma platter with salad and chips or rice.",
         "طبق شاورما دجاج مع سلطة وأرز أو بطاطس."),

        (26, "Main Course", "Mixed Grill Platter",
         "طبق مشويات مشكلة", D("350"), "grill",
         "Mixed grill platter with salad and chips or rice.",
         "طبق مشويات مشكلة مع سلطة وأرز أو بطاطس."),

        # — Salads —
        (27, "Salads", "Caesar Salad",
         "سلطة سيزر", D("190"), "cold",
         "Grilled chicken, lettuce, tomato, crispy bread, parmesan and Caesar sauce.",
         "دجاج مشوي، خس، طماطم، خبز مقرمش، جبن بارميزان، وصوص سيزر."),

        (28, "Salads", "Greek Salad",
         "سلطة يونانية", D("180"), "cold",
         "Feta cheese, lettuce, tomato, paprika, cucumber, onion and olive.",
         "جبنة فيتا، خس، طماطم، فلفل ألوان، خيار، بصل، وزيتون."),

        (29, "Salads", "Tuna Salad",
         "سلطة تونة", D("200"), "cold",
         "Tuna, lettuce, carrot, tomato, sweet corn, olive, onion with vinegar and lemon sauce.",
         "تونة، خس، جزر، طماطم، ذرة حلوة، زيتون، بصل، مع صوص الليمون والخل."),

        (30, "Salads", "Crystal Salad",
         "سلطة كريستال", D("200"), "cold",
         "Grilled chicken breast, lettuce, tomato, rocca, white cheese, olive, cucumber and crystal special sauce.",
         "صدر دجاج مشوي، خس، طماطم، جرجير، جبنة بيضاء، زيتون، خيار، وصوص كريستال الخاص."),

        (31, "Salads", "Fit Salad",
         "سلطة دايت", D("200"), "cold",
         "Iceberg lettuce, rocca, tomatoes, white cheese, cucumber, parsley, boiled egg and olive oil.",
         "خس آيسبيرج، جرجير، طماطم، جبنة بيضاء، خيار، بقدونس، بيض مسلوق، وزيت زيتون."),

        (32, "Salads", "Tabbouleh",
         "تبولة", D("150"), "cold",
         "Parsley, mint, tomato, onion, lemon juice and olive oil.",
         "بقدونس، نعناع، طماطم، بصل، عصير ليمون، وزيت زيتون."),

        (33, "Salads", "Fattoush",
         "فتوش", D("150"), "cold",
         "Cucumber, tomato, lettuce, mint, lemon juice, olive oil, sumac and crispy bread.",
         "خيار، طماطم، خس، نعناع، عصير ليمون، زيت زيتون، سماق، وخبز مقرمش."),

        (34, "Salads", "Mediterranean Salad",
         "سلطة البحر المتوسط", D("120"), "cold",
         "Cucumber, tomato, lettuce, lemon juice and olive oil.",
         "خيار، طماطم، خس، عصير ليمون، وزيت زيتون."),

        # — Breakfast (till 12 PM) —
        (35, "Breakfast", "Scrambled Eggs",
         "بيض مخفوق", D("140"), "hot",
         "Scrambled eggs, lettuce, tomatoes and cucumber with 2 toasts. (Till 12 PM)",
         "بيض مخفوق مع خس، طماطم، خيار، و2 توست. (حتى 12 ظهراً)"),

        (36, "Breakfast", "Fried Eggs with Cheese",
         "بيض مقلي بالجبن", D("140"), "hot",
         "Fried eggs, cheese, lettuce and tomatoes with 2 crunchy toasts. (Till 12 PM)",
         "بيض مقلي مع جبنة، خس، طماطم، و2 توست مقرمش. (حتى 12 ظهراً)"),

        (37, "Breakfast", "Omelette",
         "أومليت", D("140"), "hot",
         "Eggs omelette with cucumber, tomatoes and 2 toasts. (Till 12 PM)",
         "بيض أومليت مع خيار، طماطم، و2 توست. (حتى 12 ظهراً)"),

        (38, "Breakfast", "Omelette with Vegetables",
         "أومليت بالخضار", D("140"), "hot",
         "Vegetable omelette with cucumber, tomatoes, butter and 2 toasts. (Till 12 PM)",
         "بيض أومليت بالخضار مع خيار، طماطم، زبدة، و2 توست. (حتى 12 ظهراً)"),

        # — Seafood —
        (39, "Seafood", "Calamari",
         "كاليماري", D("360"), "hot",
         "Calamari — fried or grilled.",
         "كاليماري (مقلي أو مشوي)."),

        (40, "Seafood", "Shrimps",
         "جمبري", D("420"), "hot",
         "Shrimps — fried or grilled.",
         "جمبري (مقلي أو مشوي)."),

        (41, "Seafood", "Shrimps with Calamari",
         "جمبري مع كاليماري", D("490"), "hot",
         "Shrimps with calamari — fried or grilled.",
         "جمبري مع كاليماري (مقلي أو مشوي)."),

        (42, "Seafood", "Fish & Chips",
         "سمك مع بطاطس مقلية", D("320"), "hot",
         "Fish with chips.",
         "سمك مع بطاطس مقلية."),

        # — Pizza —
        (43, "Pizza", "Salami Pizza",
         "بيتزا سلامي", D("280"), "hot",
         "Beef salami, mozzarella and tomato sauce.",
         "سلامي بقري، جبنة موزاريلا، وصوص الطماطم."),

        (44, "Pizza", "Margherita Pizza",
         "بيتزا مارجريتا", D("240"), "hot",
         "Mozzarella, tomato sauce and garnish with basil.",
         "جبنة موزاريلا، صوص الطماطم، ومزينة بالريحان."),

        (45, "Pizza", "Four Cheese Pizza",
         "بيتزا أربع أنواع جبن", D("280"), "hot",
         "Mozzarella, gorgonzola, scamorza and mixed cheddar.",
         "موزاريلا، جورجونزولا، سكامورزا، وشيدر مشكل."),

        (46, "Pizza", "Chicken Pizza",
         "بيتزا دجاج", D("310"), "hot",
         "Chicken, tomato sauce and mozzarella.",
         "دجاج، صوص الطماطم، وجبنة موزاريلا."),

        (47, "Pizza", "Tuna Pizza",
         "بيتزا تونة", D("290"), "hot",
         "Mozzarella, red onion, tuna and black olives.",
         "جبنة موزاريلا، بصل أحمر، تونة، وزيتون أسود."),

        (48, "Pizza", "Vegetariana Pizza",
         "بيتزا خضار", D("260"), "hot",
         "Tomato sauce, mozzarella and grilled vegetables.",
         "صوص الطماطم، جبنة موزاريلا، وخضار مشوية."),

        (49, "Pizza", "Frutti Di Mare Pizza",
         "بيتزا فروتي دي ماري", D("360"), "hot",
         "Mixed seafood, oregano, mozzarella and tomato sauce.",
         "مأكولات بحرية مشكلة، أوريجانو، جبنة موزاريلا، وصوص الطماطم."),

        (50, "Pizza", "Shrimps Pizza",
         "بيتزا جمبري", D("330"), "hot",
         "Shrimps, oregano, mozzarella and tomato sauce.",
         "جمبري، أوريجانو، جبنة موزاريلا، وصوص الطماطم."),

        # — Pasta —
        (51, "Pasta", "Chicken Pasta",
         "باستا دجاج", D("190"), "hot",
         "Chicken and mushroom with tomato sauce.",
         "دجاج ومشروم مع صوص الطماطم."),

        (52, "Pasta", "Bolognese Pasta",
         "باستا بولونيز", D("190"), "hot",
         "Minced meat, tomato sauce, cheese and basil.",
         "لحم مفروم، صوص الطماطم، جبنة، وريحان."),

        (53, "Pasta", "Arrabiata Pasta",
         "باستا أرابياتا", D("160"), "hot",
         "Spaghetti or penne with spicy tomato sauce.",
         "اسباجيتي أو بيني مع صوص الطماطم الحار."),

        (54, "Pasta", "Loro Rosso Pasta",
         "باستا لورو روسو", D("190"), "hot",
         "Grilled chicken, Loro Rosso sauce, spaghetti or penne.",
         "دجاج مشوي مع صوص لورو روسو، اسباجيتي أو بيني."),

        (55, "Pasta", "Quattro Formaggi Pasta",
         "باستا كواترو فورماجي", D("190"), "hot",
         "Four cheese with cheese sauce.",
         "أربع أنواع جبنة مع صوص الجبنة."),

        (56, "Pasta", "Shrimp Pasta",
         "باستا جمبري", D("260"), "hot",
         "Shrimp, celery, red onion, lemon juice, salt and pepper.",
         "جمبري، كرفس، بصل أحمر، عصير ليمون، ملح، وفلفل."),
    ]

    active_names: set[str] = set()
    inserted = updated = 0

    from app.modules.dining.models import DiningItem
    existing = {
        i.name: i for i in db.query(DiningItem).filter(
            DiningItem.outlet_id == outlet.id
        ).all()
    }

    for sort_order, cat_en, name_en, name_ar, price, station, desc_en, desc_ar in ITEMS:
        active_names.add(name_en)
        updated += name_en in existing
        inserted += name_en not in existing
        _upsert_item(
            db, branch_id=branch.id, outlet_id=outlet.id,
            category_id=cat_map[cat_en], name_en=name_en, name_ar=name_ar,
            price=price, station=station, sort_order=sort_order,
            description=desc_en, description_ar=desc_ar,
        )

    deactivated = _deactivate_removed_items(db, outlet.id, active_names)
    db.flush()
    print(
        f"  ✓ Restaurant menu 2026: {inserted} inserted, "
        f"{updated} updated, {deactivated} deactivated"
    )


# ─── Cafe & Bar 2026 ──────────────────────────────────────────────────────────

def _update_cafe_menu(db: Session) -> None:
    D = Decimal
    branch, outlet = _get_outlet(db, "cafe")

    CATEGORIES = [
        ("Hot Beverages",             "المشروبات الساخنة",       0),
        ("Fresh Juices",              "العصائر الطازجة",         1),
        ("Mix Juices",                "العصائر المخلطة",         2),
        ("Frappuccino & Iced Coffee", "فرابتشينو وآيس كوفي",    3),
        ("Milkshakes",                "الميلك شيك",              4),
        ("Mojito",                    "موهيتو",                  5),
        ("Cold Drinks",               "المشروبات الباردة",       6),
        ("Fruit Salad",               "فروت سلاط",               7),
    ]
    cat_map: dict[str, int] = {}
    for name_en, name_ar, sort in CATEGORIES:
        cat_map[name_en] = _upsert_category(
            db, branch.id, outlet.id, name_en, name_ar, sort
        )
    _deactivate_removed_categories(db, outlet.id, {c[0] for c in CATEGORIES})

    ITEMS: list[tuple] = [
        (1,  "Hot Beverages", "Espresso Single",              "إسبريسو سنجل",                  D("65")),
        (2,  "Hot Beverages", "Espresso Double",              "إسبريسو دبل",                   D("75")),
        (3,  "Hot Beverages", "Cappuccino",                   "كابتشينو",                      D("110")),
        (4,  "Hot Beverages", "Latte",                        "لاتيه",                         D("115")),
        (5,  "Hot Beverages", "Macchiato",                    "ماكياتو",                       D("80")),
        (6,  "Hot Beverages", "Nescafe with Milk",            "نسكافيه بالحليب",               D("110")),
        (7,  "Hot Beverages", "Nescafe Classic",              "نسكافيه كلاسيك",                D("80")),
        (8,  "Hot Beverages", "Americano",                    "أمريكانو",                      D("110")),
        (9,  "Hot Beverages", "Hot Chocolate",                "هوت شوكليت",                    D("120")),
        (10, "Hot Beverages", "Hot Cider",                    "هوت سيدر",                      D("100")),
        (11, "Hot Beverages", "Turkish Coffee",               "قهوة تركي",                     D("60")),
        (12, "Hot Beverages", "French Coffee",                "قهوة فرنساوي",                  D("70")),
        (13, "Hot Beverages", "Tea Anise Mint Hibiscus",      "شاي / ينسون / نعناع / كركديه",  D("70")),
        (14, "Hot Beverages", "Milk Tea",                     "شاي بالحليب",                   D("90")),
        (15, "Fresh Juices",  "Mango Juice",                  "مانجو",                         D("130")),
        (16, "Fresh Juices",  "Strawberry Juice",             "فراولة",                        D("130")),
        (17, "Fresh Juices",  "Guava Juice",                  "جوافة",                         D("130")),
        (18, "Fresh Juices",  "Cantaloupe Juice",             "كنتالوب / شمام",                D("130")),
        (19, "Fresh Juices",  "Pomegranate Juice",            "رمان",                          D("130")),
        (20, "Fresh Juices",  "Orange Juice",                 "برتقال",                        D("130")),
        (21, "Fresh Juices",  "Watermelon Juice",             "بطيخ",                          D("150")),
        (22, "Fresh Juices",  "Kiwi Juice",                   "كيوي",                          D("150")),
        (23, "Fresh Juices",  "Lemon Juice",                  "ليمون",                         D("100")),
        (24, "Fresh Juices",  "Lemon Mint",                   "ليمون بالنعناع",                D("120")),
        (25, "Fresh Juices",  "Apple Juice",                  "تفاح",                          D("150")),
        (26, "Fresh Juices",  "Pineapple Juice",              "أناناس",                        D("130")),
        (27, "Fresh Juices",  "Peach Juice",                  "خوخ",                           D("130")),
        (28, "Fresh Juices",  "Avocado Juice",                "أفوكادو",                       D("150")),
        (29, "Fresh Juices",  "Avocado Honey Nuts",           "أفوكادو بالعسل والمكسرات",      D("150")),
        (30, "Fresh Juices",  "Dates Juice",                  "تمر",                           D("130")),
        (31, "Mix Juices",    "Pina Colada Mix",              "بينا كولادا",                   D("150")),
        (32, "Mix Juices",    "Mango Kiwi Mix",               "مانجو كيوي",                    D("150")),
        (33, "Mix Juices",    "Mango Plum Mix",               "مانجو بلز",                     D("150")),
        (34, "Mix Juices",    "Mango Strawberry Mix",         "مانجو فراولة",                  D("150")),
        (35, "Mix Juices",    "Mango Cantaloupe Mix",         "مانجو كنتالوب",                 D("150")),
        (36, "Mix Juices",    "Kiwi Cantaloupe Mix",          "كيوي كنتالوب",                  D("150")),
        (37, "Mix Juices",    "Kiwi Pineapple Mix",           "كيوي أناناس",                   D("150")),
        (38, "Mix Juices",    "Mango Banana Mix",             "مانجو موز",                     D("150")),
        (39, "Mix Juices",    "Strawberry Banana Mix",        "فراولة موز",                    D("150")),
        (40, "Mix Juices",    "Khayma Mix",                   "الخيمة ميكس",                   D("150")),
        (41, "Frappuccino & Iced Coffee", "Frappuccino Classic",  "فرابتشينو كلاسيك",  D("150")),
        (42, "Frappuccino & Iced Coffee", "Frappuccino Vanilla",  "فرابتشينو فانيليا", D("150")),
        (43, "Frappuccino & Iced Coffee", "Frappuccino Hazelnut", "فرابتشينو بندق",    D("150")),
        (44, "Frappuccino & Iced Coffee", "Iced Coffee",          "آيس كوفي",          D("150")),
        (45, "Frappuccino & Iced Coffee", "Iced Latte",           "آيس لاتيه",         D("150")),
        (46, "Frappuccino & Iced Coffee", "Spanish Latte",        "سبانيش لاتيه",      D("150")),
        (47, "Milkshakes",    "Vanilla Milkshake",            "فانيليا",                       D("150")),
        (48, "Milkshakes",    "Chocolate Milkshake",          "شوكولاتة",                      D("150")),
        (49, "Milkshakes",    "Caramel Milkshake",            "كراميل",                        D("150")),
        (50, "Milkshakes",    "Oreo Milkshake",               "أوريو",                         D("150")),
        (51, "Milkshakes",    "Tonkeys Milkshake",            "تونكيز",                        D("150")),
        (52, "Milkshakes",    "Berries Milkshake",            "توت مشكل",                      D("150")),
        (53, "Milkshakes",    "Mango Milkshake",              "مانجو ميلك شيك",                D("150")),
        (54, "Milkshakes",    "Strawberry Milkshake",         "فراولة ميلك شيك",               D("150")),
        (55, "Mojito",        "Mojito Classic",               "موهيتو كلاسيك",                 D("110")),
        (56, "Mojito",        "Mojito Soda",                  "موهيتو صودا",                   D("115")),
        (57, "Mojito",        "Mojito Sunshine",              "موهيتو صن شاين",                D("115")),
        (58, "Mojito",        "Mojito Red Bull Special",      "مهيتو ريدبول اسبيشال",          D("150")),
        (59, "Cold Drinks",   "Cola Fanta Sprite",            "كولا / فانتا / سبرايت",         D("65")),
        (60, "Cold Drinks",   "Fayrouz",                      "فيروز",                         D("70")),
        (61, "Cold Drinks",   "Barrel",                       "بريل",                          D("70")),
        (62, "Cold Drinks",   "Red Bull",                     "ريد بول",                       D("110")),
        (63, "Cold Drinks",   "Water Small",                  "مياه صغيرة",                    D("25")),
        (64, "Cold Drinks",   "Water Large",                  "مياه كبيرة",                    D("35")),
        (65, "Fruit Salad",   "Fruit Salad Small",            "فروت سلاط صغير",                D("120")),
        (66, "Fruit Salad",   "Fruit Salad Large",            "فروت سلاط كبير",                D("200")),
        (67, "Fruit Salad",   "Watermelon Plate Small",       "طبق بطيخ صغير",                 D("120")),
        (68, "Fruit Salad",   "Watermelon Plate Large",       "طبق بطيخ كبير",                 D("200")),
    ]

    active_names: set[str] = set()
    inserted = updated = 0

    from app.modules.dining.models import DiningItem
    existing = {
        i.name: i for i in db.query(DiningItem).filter(
            DiningItem.outlet_id == outlet.id
        ).all()
    }

    for sort_order, cat_en, name_en, name_ar, price in ITEMS:
        active_names.add(name_en)
        updated += name_en in existing
        inserted += name_en not in existing
        _upsert_item(
            db, branch_id=branch.id, outlet_id=outlet.id,
            category_id=cat_map[cat_en], name_en=name_en, name_ar=name_ar,
            price=price, station="bar", sort_order=sort_order,
        )

    deactivated = _deactivate_removed_items(db, outlet.id, active_names)
    db.flush()
    print(
        f"  ✓ Cafe & Bar menu 2026: {inserted} inserted, "
        f"{updated} updated, {deactivated} deactivated"
    )


# ─── Apply translations (Step 3 — after migration + filling i18n JSON) ───────

def apply_translations(db: Session, json_path: str | None = None) -> None:
    """
    كل الترجمات جاهزة فعلاً (روسي + إيطالي كاملين لـ124 صنف/فئة، راجع
    data/menu/menu_i18n_structure.json's _meta) — الدالة دي بس بتكتبهم في
    الداتابيز بعد الـmigration (a7c3f0e9d5b2).

    Usage:
        from app.seed_menu_2026 import apply_translations
        from app.core.database import SessionLocal
        db = SessionLocal()
        apply_translations(db)
        db.commit()
        db.close()
    """
    import json
    from pathlib import Path
    from app.modules.dining.models import DiningCategory, DiningItem

    if json_path is None:
        json_path = str(Path(__file__).parent / "seed_data" / "menu_i18n_2026.json")

    if not Path(json_path).exists():
        raise FileNotFoundError(f"i18n file not found: {json_path}")

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    updated_cats = updated_items = skipped = 0

    for section_key in ("restaurant", "cafe"):
        section = data.get(section_key, {})

        # Categories
        for cat_def in section.get("categories", []):
            name_ru = cat_def.get("name_ru", "").strip()
            name_it = cat_def.get("name_it", "").strip()
            if not name_ru and not name_it:
                skipped += 1
                continue
            rows = db.query(DiningCategory).filter(
                DiningCategory.name == cat_def["name"]
            ).all()
            for row in rows:
                if name_ru:
                    row.name_ru = name_ru
                if name_it:
                    row.name_it = name_it
                updated_cats += 1

        # Items
        for item_def in section.get("items", []):
            name_ru = item_def.get("name_ru", "").strip()
            name_it = item_def.get("name_it", "").strip()
            if not name_ru and not name_it:
                skipped += 1
                continue
            rows = db.query(DiningItem).filter(
                DiningItem.name == item_def["name"]
            ).all()
            for row in rows:
                if name_ru:
                    row.name_ru = name_ru
                if name_it:
                    row.name_it = name_it
                updated_items += 1

    db.flush()
    print(
        f"  ✓ Translations applied: {updated_cats} categories, "
        f"{updated_items} items, {skipped} skipped (empty)"
    )
