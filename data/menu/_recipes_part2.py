"""
Restaurant recipes part 2: Salads + Breakfast + Seafood + Pizza + Pasta
"""
from decimal import Decimal as D

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

ALL_RESTAURANT = (
    STARTERS
    + SANDWICHES
    + MAIN_COURSE
    + SALADS
    + BREAKFAST
    + SEAFOOD
    + PIZZA
    + PASTA
)
