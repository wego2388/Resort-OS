"""
Restaurant recipes part 1: Starters + Sandwiches + Main Course
"""
from decimal import Decimal as D

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
