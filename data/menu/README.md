# El Kheima Beach — data/menu/README.md
# مجلد البيانات المصدرية (خام) للمنيو الجديد

## ⚠️ حالة هذا المجلد (2026-08-03)

الملفات هنا هي **المصدر الخام بس** (البيانات المستخرجة من صور المنيو +
مسودة أولى للسكريبتات). راجعتها Claude ولقى 3 مشاكل حقيقية كانت هتمنعها
تشتغل خالص أو هتمسح بيانات حقيقية شغالة (تفاصيل كاملة في
`MENU_UPDATE_REPORT_2026.md` وفي محادثة المراجعة) — **النسخ المُصلَّحة
والمُختبَرة فعليًا هي مصدر الحقيقة دلوقتي، مش الملفات في المجلد ده**:

| الملف الأصلي هنا | النسخة المُصلَّحة (شغّلها من هنا) |
|---|---|
| `seed_menu_2026.py` | `backend/app/seed_menu_2026.py` |
| `seed_recipes_2026.py` | `backend/app/seed_recipes_2026.py` |
| `migration_add_i18n_columns.py` | `backend/alembic/versions/a7c3f0e9d5b2_add_dining_i18n_and_sort_order.py` (اتطبّقت بالفعل) |
| `menu_i18n_structure.json` | `backend/app/seed_data/menu_i18n_2026.json` (نفس المحتوى، بدون تغيير) |
| `CHATBOT_KNOWLEDGE_BASE_PATCH.json` | **متجاهَل تمامًا** — `03_chatbot/CHATBOT_KNOWLEDGE_BASE.json` مش موجود في resort-os خالص؛ شات بوت المشروع بيقرأ المنيو من الداتابيز مباشرة (`app/modules/chat/`)، مش من ملف JSON ثابت. الخطوة دي غالبًا متبقية من مشروع تاني قديم. |

اتأكد فعليًا (مش افتراض) على قاعدة بيانات نظيفة معزولة: migration
upgrade/downgrade round-trip، `update_menu_2026`+`apply_translations`+
`seed_recipes_2026` الثلاثة مع بعض، صفر SKU/item مفقود (83/83 كود مكوّن
اتحل، 124/124 صنف اتربط بوصفة)، الأصناف الخمسة اللي بيتشاركوا اسم مع
المنيو القديم (Margherita/Salami/Tuna Pizza، Caesar/Greek Salad) لسه
عندهم وصفة حقيقية بعد التحديث (مش فاضية)، ونسب تكلفة الطعام المحسوبة
واقعية (6–31%، متوافقة مع المدى المستهدف). راجع `git log` على
`backend/app/seed_menu_2026.py`/`seed_recipes_2026.py` للتفاصيل الكاملة.

---

## محتوى المجلد

### بيانات المصدر (مستخرجة من الصور)
| الملف | الوصف |
|-------|--------|
| `RESTAURANT_MENU_NEW.json` | منيو المطعم كامل — JSON منظم |
| `CAFE_BAR_MENU_NEW.json` | منيو الكافيه والبار — JSON منظم |
| `MENU_COMPLETE_2026.csv` | الكل في ملف CSV موحد |
| `MENU_COMPLETE_2026.md` | عرض بشري مقروء للمنيو الكامل |
| `MENU_UPDATE_REPORT_2026.md` | تقرير الفروق عن المنيو القديم |

### ملفات مرجعية (المسودة الأصلية — راجع الجدول فوق للنسخة المُصلَّحة الفعلية)
| الملف | الوصف |
|-------|--------|
| `seed_menu_2026.py` | مسودة أولى — فيها باج حقيقي (عمودين مش موجودين)، مُصلَّحة في `backend/app/` |
| `seed_recipes_2026.py` | مسودة أولى — فيها syntax error حقيقي + SKUs غير متطابقة مع المخزون، مُصلَّحة في `backend/app/` |
| `migration_add_i18n_columns.py` | مسودة أولى — ناقصة `sort_order` + معندهاش تعديل `models.py` مقابل |
| `menu_i18n_structure.json` | **صحيحة 100%، اتنسخت بدون تعديل** — 124/124 صنف/فئة مترجمين روسي+إيطالي |
| `CHATBOT_KNOWLEDGE_BASE_PATCH.json` | غير قابلة للتطبيق على resort-os — راجع الجدول فوق |
| `_recipes_part1.py` / `_recipes_part2.py` / `_recipes_part3.py` | نفس بيانات `seed_recipes_2026.py` الأصلي مقسّمة لقراءة أسهل بس — مدموجة بالفعل في النسخة المُصلَّحة |

---

## كيفية التطبيق (النسخة القديمة تحت — للسياق التاريخي بس، اتبع الجدول فوق فعليًا)

### الخطوة 1 — تحديث بيانات المنيو فقط (بدون i18n)
```bash
# انسخ seed_menu_2026.py للمشروع
cp data/menu/seed_menu_2026.py backend/app/seed_menu_2026.py
# شغّل السكريبت
cd backend && .venv/bin/python -c "
from app.seed_menu_2026 import update_menu_2026
from app.core.database import SessionLocal
db = SessionLocal()
update_menu_2026(db)
db.commit()
db.close()
"
```

### الخطوة 2 — إضافة حقول اللغات الجديدة (Migration)
```bash
# انسخ الـ migration
cp data/menu/migration_add_i18n_columns.py backend/alembic/versions/
cd backend && .venv/bin/alembic upgrade head
```

### الخطوة 3 — ملء الترجمات (جاهزة ✅)
`menu_i18n_structure.json` مكتمل بالترجمات الروسية والإيطالية لكل الأصناف.
شغّل `apply_translations` من `seed_menu_2026.py` مباشرة بعد migration.

### الخطوة 4 — وصفات BOM (اختياري)
```bash
cp data/menu/seed_recipes_2026.py backend/app/seed_recipes_2026.py
cd backend && .venv/bin/python -c "
from app.seed_recipes_2026 import seed_recipes_2026
from app.core.database import SessionLocal
db = SessionLocal()
seed_recipes_2026(db)
db.commit()
db.close()
"
```

### الخطوة 5 — تحديث الـ Chatbot Knowledge Base
```bash
# ادمج CHATBOT_KNOWLEDGE_BASE_PATCH.json في
# 03_chatbot/CHATBOT_KNOWLEDGE_BASE.json
# استبدل أقسام dining بالكامل ببيانات الـ patch
```

---

## الوضع الحالي في resort-os (مرجع)

```
dining_items: name (en) + name_ar (ar) — موجودان
dining_items: name_ru / name_it — غير موجودان (يحتاجان migration)

PublicMenuItemRead: يرجع name + name_ar فقط
  → لإضافة name_ru/name_it: يحتاج تعديل schemas.py + router.py
```

## حالة الترجمات

| اللغة | الحالة |
|-------|--------|
| English (name) | ✅ موجود في DB |
| Arabic (name_ar) | ✅ موجود في DB |
| Russian (name_ru) | ✅ مكتمل في menu_i18n_structure.json — ينتظر migration |
| Italian (name_it) | ✅ مكتمل في menu_i18n_structure.json — ينتظر migration |

## ملاحظات مهمة

- **seed_menu_2026.py** يعمل بـ `upsert` (UPDATE لو موجود، INSERT لو جديد)
  — آمن على production database مع orders تاريخية.
- الأصناف القديمة في seed.py تختلف عن المنيو الجديد (أسعار + أصناف).
  الـ script يعمل `match by name` ويضيف flag `is_available=False`
  للأصناف اللي اتحذفت من المنيو الجديد بدل حذفها hard.
- الترقيم في المنيو الجديد (1-56 للمطعم) مذكور في `sort_order`
  عشان يظهر بنفس الترتيب في الـ POS والـ KDS.
