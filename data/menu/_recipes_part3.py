"""
Cafe & Bar recipes: Hot Beverages + Fresh Juices + Mix Juices +
Frappuccino/Iced Coffee + Milkshakes + Mojito + Cold Drinks + Fruit Salad
"""
from decimal import Decimal as D

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

ALL_CAFE = (
    HOT_BEVERAGES
    + FRESH_JUICES
    + MIX_JUICES
    + FRAPPUCCINO
    + MILKSHAKES
    + MOJITO
    + COLD_DRINKS
    + FRUIT_SALAD
)
