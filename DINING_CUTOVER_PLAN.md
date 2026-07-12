# خطة الانتقال (Cutover) — دمج المطعم/الكافيه إلى Dining الموحّد

> **الحالة:** تخطيط فقط — لا شيء في هذا الملف مُنفَّذ. راجع wagdy.md "المرحلة الثالثة — المشروع
> الكبير (Dining Module Merge)" للمواصفة الكاملة (D-01 → D-08).
>
> **المُنفَّذ فعليًا (Batch A، D-01 → D-04):** موديول `app/modules/dining/` كامل ومستقل —
> models/schemas/crud/services/router — جنب `restaurant`/`cafe` مش بدلهم. الموديولين القديمين
> لسه المصدر الوحيد للحقيقة (source of truth) لكل عملية بيع حقيقية، ولسه هما اللي الفرونت إند
> بيكلّمهم فعليًا. تفاصيل التحقق الكاملة (تست، migration، إلخ) في نهاية هذا الملف.
>
> **غير المُنفَّذ عمدًا:** D-05 (تحويل analytics/finance لقراءة `dining` بدل `restaurant`+`cafe`)،
> D-06/D-07 (فرونت إند)، D-08 (حذف الموديولين القديمين). هذا الملف هو المقترح المكتوب لـ D-05
> تحديدًا — القرار النهائي يحتاج مراجعة صريحة مع Mohamed قبل التنفيذ، بالظبط زي فجوة إيراد الغرفة
> الموثّقة في CLAUDE.md §18 بند 0.

---

## (أ) هل الـ "aliases" في D-04 لازم تبقى مسار الكتابة الوحيد فورًا؟

**لأ، مش دلوقتي — وده قرار متعمد، مش تأجيل كسول.**

### إيه اللي اتعمل فعليًا في D-04

`dining/api/router.py` **مالوش أي alias حرفي** لمسارات `/restaurant/...` أو `/cafe/...`
القديمة. الروترين القديمين (`restaurant.api.router`, `cafe.api.router`) **متلمسوش خالص** — لسه
مسجّلين في `app/main.py` بنفس الترتيب، لسه بيقروا/يكتبوا في `orders`/`cafe_orders`/`menu_items`/
`cafe_items`/إلخ زي ما هما بالظبط. الموديول الجديد `dining` بيعيش على prefix منفصل تمامًا
(`/api/v1/dining/...`) وبيكتب في جداول جديدة تمامًا (`dining_orders`/`dining_items`/إلخ).

يعني "الـ alias" اللي طلبه الـ spec الأصلي (wagdy.md D-04: *"Add temporary path aliases so every
existing `/restaurant/...` and `/cafe/...` URL keeps working exactly as before"*) **محقّق تلقائيًا
من غير أي كود إضافي** — مفيش حاجة اتشالت أو اتلمست، فمفيش حاجة تحتاج "alias" ليها أصلاً. اتأكد من
ده عمليًا (مش افتراض):

1. **220 اختبار restaurant/cafe الموجودين عدّوا 100% من غير أي تعديل عليهم** (`test_restaurant.py`،
   `test_restaurant_http.py`، `test_cafe.py`، `test_cafe_http.py`، `test_cafe_coverage.py`،
   `test_cafe_public_orders.py`) — قبل وبعد إضافة D-01 → D-04 كاملين.
2. **route dump كامل للتطبيق بعد تسجيل كل الموديولات** يورّي 493 مسار (47 restaurant + 41 cafe +
   50 dining)، **صفر تصادم (method, path)** في أي مكان.
3. **HTTP-level tests جديدة صريحة** (`tests/test_api/test_dining_http.py::TestOldUrlsStillWork`)
   بتنادي `/api/v1/restaurant/menu/items` و`/api/v1/cafe/items` مباشرة بعد إضافة dining وبتتأكد
   إنهم لسه شغالين + إن صنف اتضاف عبر `/dining` **ميظهرش** في القوائم القديمة (عزل كامل، مش
   تسريب بيانات بين الموديولين).

### ليه مش عملت alias حرفي (proxy القديم → dining) بدل كده

الـ spec نفسه بيديك خيارين: *"proxy to the same underlying dining service functions, or keep the
old routers mounted and pointed at the new services"*. الخيار التاني ده (خلّي الروترات القديمة
تكتب في جداول dining بدل جداولها هي) **هو بالظبط D-05** (analytics/finance cutover) بس من زاوية
تانية — لو الروتر القديم بدأ يكتب في `dining_orders` بدل `orders`، بقى `dining` هو مصدر الحقيقة
الحقيقي من غير ما تكون finance/analytics عارفة تقرا منه لسه. ده split-brain حرفي: طلب مطعم جديد
موجود في `dining_orders` بس، بينما كل تقرير مالي/تحليلي في المشروع (finance folio reconciliation،
`analytics/revenue`، `restaurant/reports/food-cost`) لسه بيستعلم `orders`/`order_items` القديمة —
هيفضل يرجّع صفر أو بيانات ناقصة من غير أي تحذير. هذا بالظبط نوع القرار اللي wagdy.md نفسه طلب
يتوقف قبله ("Where to stop") وده نفس مبدأ فجوة إيراد الغرفة الموثّقة في CLAUDE.md §18 بند 0 —
قرار معماري بأثر مالي حقيقي، يستاهل وقت مخصص ومراجعة صريحة، مش تعديل عابر وسط دفعة تانية.

**الخلاصة**: أبقى الروترين القديمين كما هما بالضبط لحد ما القرار تحت (ب) يتاخد فعليًا وينفَّذ
بالكامل (D-05 → D-08 مع بعض، مش D-05 لوحدها) — مش نص طريق فيه جدولين بيتحدّثوا في نفس اللحظة.

---

## (ب) إيه اللي analytics/finance محتاجين يتغيّروا فيه (D-05، لو ومتى)

### الوضع الحالي (بعد Batch A)
```
الكتابة الحقيقية:  restaurant/cafe routers → orders/cafe_orders (+ جداولهم الفرعية)
القراءة المالية:   finance (folio charges)، analytics (revenue/dashboard)،
                    restaurant/cafe food-cost reports
                    ↑ كل ده بيستعلم orders/cafe_orders مباشرة، مش dining_orders
dining tables:      نسخة (snapshot وقت D-02) + أي بيانات تُنشأ عبر /api/v1/dining مباشرة
                    (مفيش حاليًا — الفرونت إند لسه بيكلّم /restaurant و/cafe بس)
```

### المطلوب فعليًا في D-05 (لو اتاخد القرار)

1. **قرار المصدر الوحيد للحقيقة أولاً، قبل أي كود.** التصميم الصح (المتوافق مع نية الدمج) هو إن
   `dining_orders`/`dining_items`/إلخ يبقوا هما المصدر الوحيد، و`restaurant`/`cafe` routers
   يتحوّلوا هما نفسهم لـ **delegate** لـ `dining.services` (بدل ما يكون عندهم منطق مستقل) — يعني
   طلب جاي على `/restaurant/orders` بيتحوّل جوّه لـ `dining.services.create_order(outlet_id=<outlet
   المطعم بتاع الفرع>, ...)` ويرجّع نتيجة بشكل `OrderRead` القديم (restaurant schema) عشان
   الفرونت إند القديم (لسه ما اتحدّثش، D-06/D-07) يفضل شغال من غير تغيير. هذا التسلسل (routers
   القديمة تتحول لـ thin adapters فوق dining services) **لازم يحصل في نفس الدفعة اللي فيها
   analytics/finance بيتحوّلوا للقراءة من dining** — مش قبلها بخطوة، وإلا split-brain فورًا.

2. **`app/modules/finance/services.py`** — `update_order_status`/الكودات المكافئة اللي بتنشئ
   `FolioCharge(charge_type="restaurant"/"cafe")` لازم تبقى `charge_type="dining"` (المسار الجديد
   `dining.services.update_order_status` أصلاً بيستخدم `charge_type="dining"` من دلوقتي — راجع D-03
   commit). أي كود finance بيفلتر على `charge_type IN ("restaurant", "cafe")` (لو موجود) لازم
   يتحدّث ليشمل `"dining"` كمان أثناء فترة انتقالية، أو الأنضف: **migration بيانات** تحوّل كل
   `FolioCharge.charge_type` القديمة من `"restaurant"`/`"cafe"` لـ `"dining"` كخطوة D-08 (بعد ما
   الفرونت إند بالكامل بقى بيكلّم `/dining`).

3. **`app/modules/analytics/services.py`** (`get_revenue`/`get_dashboard`/أي دالة بتستعلم `Order`/
   `CafeOrder` مباشرة) — تتحول لتستعلم `DiningOrder` بدل الاتنين، مفلترة بـ `Outlet.outlet_type`
   لو محتاجة تفرّق (مثلاً "إيراد المطعم" مقابل "إيراد الكافيه" في نفس الشاشة). ده تبسيط حقيقي —
   استعلام واحد بدل استعلامين + دمج يدوي، وبيفتح تلقائيًا لأي outlet جديد (بار مسبح) من غير أي
   كود إضافي في التحليلات (نفس وعد الدمج الأساسي).

4. **`restaurant/services.get_food_cost_report`/`cafe/services.get_food_cost_report`** — تتحول
   لـ thin wrappers فوق `dining.services.get_food_cost_report(outlet_id=<outlet بتاعهم>)` (نفس
   فكرة #1) بدل تكرار المنطق. `dining.services.get_food_cost_report` أصلاً موجود وبيدعم فلترة
   بـ outlet_id اختياريًا — جاهز لده من دلوقتي.

5. **جدول تتبّع أثناء الانتقال**: لحد ما D-08 يحصل (حذف الموديولين القديمين فعليًا)، أي طلب جديد
   بيتعمل عبر `/restaurant` أو `/cafe` (بعد تحويلهم لـ delegate في الخطوة #1) لازم يظهر في
   `dining_orders` **بـ `legacy_module`/`legacy_id` = NULL** (مش نسخة من D-02 — طلب جديد كليًا،
   لا يوجد له نظير قديم). أي كود D-08 بيتحقق من نجاح الانتقال لازم يفرّق بين الصفوف دي (طلبات
   حقيقية بعد الـ cutover) والصفوف المنسوخة من D-02 (`legacy_module` IS NOT NULL) — العمود ده
   أصلاً مصمّم ليدعم التمييز ده.

### التوصية الأساسية

**لا تنفّذ D-05 لوحدها.** نفّذ D-05 + تحويل `restaurant`/`cafe` routers لـ delegates (الخطوة #1
فوق) **في نفس الدفعة**، واعتبر D-06/D-07 (الفرونت إند الموحّد) الخطوة اللي بعدها مباشرة — مش
دفعة منفصلة بفاصل زمني طويل. الفترة ما بين "الروترات القديمة بقت delegates" و"الفرونت إند بقى
بيكلّم `/dining` مباشرة" هي أضعف نقطة (لسه فيه طبقتين API لنفس البيانات)، وكل ما الفترة دي أقصر
كل ما المخاطرة أقل.

---

## (ج) خطة اختبار واقعية لإثبات عدم كسر أي تقرير/شاشة حية أثناء الانتقال

### قبل البدء في D-05 فعليًا
1. **Backup حقيقي + restore-verified** (نفس نمط D-02 بالظبط — `scripts/backup_db.sh` ثم
   `scripts/restore_db.sh latest <scratch-db>` ثم مقارنة `COUNT(*)` صف بصف على الجداول المتأثرة).
2. **Snapshot الأرقام المالية الحالية** قبل أي تغيير — `GET /analytics/revenue`،
   `GET /analytics/dashboard`، trial balance (`GET /finance/reports/trial-balance`)، ووفّرهم
   كملف مرجعي (JSON). أي انحراف عن الأرقام دي بعد الـ cutover (غير مبرَّر بمعاملات حقيقية جديدة
   حصلت في نفس الفترة) = باج، مش "تحسين".

### أثناء D-05 (على بيئة test/staging، مش production مباشرة)
3. **موازاة القراءة (Shadow read) قبل التبديل الفعلي** — قبل ما `analytics`/`finance` يتحولوا
   رسميًا، شغّل الاستعلام الجديد (`dining_orders`) **جنب** القديم (`orders`+`cafe_orders`) لنفس
   المدى الزمني، وقارن الناتج برمجيًا (نفس فكرة `test_dining_migration.py`'s row-count parity، بس
   على مستوى aggregate مش raw rows). أي فرق غير متوقع يوقف الانتقال قبل ما يوصل لأي مستخدم حقيقي.
4. **إعادة تشغيل نفس سيناريو D-02's migration verification test** (`tests/test_dining_migration.py`)
   بعد أي طلب جديد اتعمل فعليًا عبر `/restaurant`/`/cafe` (بعد التحويل لـ delegates) — تأكيد إن
   الطلب الجديد ده وصل لـ `dining_orders` بـ `legacy_module IS NULL` صح، وإن كل الحسابات (folio
   charge، journal entry، خصم مخزون) حصلت بالظبط زي قبل D-05 (نفس مبالغ، نفس حسابات).
5. **اختبارات HTTP-level جديدة على `restaurant`/`cafe` القديمين بعد تحويلهم لـ delegates** —
   الاختبارات الموجودة بالفعل (`test_restaurant_http.py`, `test_cafe_http.py`, ...) لازم **تفضل
   عادية بالكامل من غير أي تعديل** (نفس مبدأ §3.7 من CLAUDE.md: تعديل بيكسر تست موجود من غير
   تحديثه مرفوض) — لو أي واحد منهم احتاج تعديل عشان delegates الجداد يعدّوا، ده معناه سلوك
   الـ endpoint اتغيّر فعليًا للمستخدم، مش مجرد تفصيل تنفيذ داخلي، ولازم يتراجع.

### بعد التبديل (production، دفعة صغيرة أولاً)
6. **مقارنة يوم كامل حقيقي** — شفت إيراد يوم واحد فعلي (كل الطلبات، كل الـ outlets) محسوب بطريقتين
   مستقلتين: (أ) `GET /dining/reports/food-cost`/`GET /analytics/revenue` الجديد، (ب) استعلام SQL
   مباشر على `orders`+`cafe_orders` القديمة لنفس اليوم (نفس الاستعلام اللي كان بيشتغل قبل D-05).
   لازم يتطابقوا لآخر قرش.
7. **Z-report/X-report يوم القفل** — قفل وردية حقيقي بعد الـ cutover، ومقارنة الرقم النهائي (كاش +
   كارت + محمّل على الغرفة) مع اللي كان بيطلع قبل الدمج لنفس نمط اليوم (نفس عدد الطلبات تقريبًا).
8. **مراقبة `items_missing_recipe`/`items_missing_recipe_revenue`** في تقرير تكلفة الطعام الموحّد
   لمدة أسبوع بعد الـ cutover — أي قفزة مفاجئة في العدد دي معناها صنف/متغيّر مش بيتربط صح بالوصفة
   بعد التحويل (باج ربط، مش مجرد بيانات ناقصة قديمة).

---

## ملحق — التحقق الفعلي اللي حصل فعليًا في Batch A (D-01 → D-04)

هذا القسم توثيق لما اتعمل بالفعل (مش خطة)، مرجع لأي حد يراجع القرار فوق:

- **Backup حقيقي قبل D-02**: `scripts/backup_db.sh` على قاعدة البيانات الفعلية، ثم
  `scripts/restore_db.sh latest <scratch>` وتأكيد `COUNT(*)` مطابق حرفيًا عبر 6 جداول
  (`branches`, `users`, `orders`, `cafe_orders`, `menu_items`, `cafe_items`).
- **D-02 migration اتبنيت واتأكد منها على قاعدة بيانات تجريبية منفصلة تمامًا** (مش القاعدة
  المشتركة الحيّة — worktree تاني كان شغال عليها بالتوازي وقت التنفيذ، فالاختبار اتعمل بمعزل
  تام عنه): seed بيانات مطعم+كافيه واقعية (فئة → صنف → وصفة → متغيّر → وصفة متغيّر، مجموعة
  إضافات + إضافة، طاولة، طلب مدفوع فيه إضافة، طلب معلّق (held) من غير طاولة، طلب كافيه مرتجع
  بالكامل)، تشغيل الـ migration، والتأكد من: تطابق عدد الصفوف حرفيًا بين كل جدول قديم ونظيره
  الجديد، صحة كل العلاقات (طلب → طاولة outlet-scoped، صنف طلب → صنف + متغيّر، وصفة متغيّر →
  المنتج الصح)، إعادة تشغيل الـ copy function من غير تكرار أي صف (idempotent)، ودورة
  downgrade → upgrade نضيفة.
- **الاختبار ده بقى pytest حقيقي وقابل لإعادة الاستخدام**: `backend/tests/test_dining_migration.py`
  — Postgres-only (skip تلقائي لو `DINING_MIGRATION_TEST_ADMIN_URL` مش موجود، صفر أثر على
  `pytest tests/` العادي)، بيعيد نفس السيناريو اللي اتعمل يدويًا: seed → migrate → تحقق من
  تطابق الصفوف + العلاقات + idempotency + downgrade/upgrade. اتشغّل فعليًا ضد Postgres حقيقي
  و3/3 عدّوا.
- **`pytest tests/ -v`**: 1834 اختبار (الرقم قبل Batch A) → 1879 بعد إضافة 45 اختبار dining
  جديد (32 service-level + 13 HTTP-level) — **كلهم عدّوا، صفر رجوع في أي تست restaurant/cafe
  موجود**.
- **`alembic heads`**: head واحد (`0bd6f63e5446`) قبل وبعد.
- **Route-level proof إن `/restaurant` و`/cafe` لسه شغالين بالظبط**: 493 مسار مسجّل بعد إضافة
  dining (47 restaurant + 41 cafe + 50 dining)، صفر تصادم `(method, path)`.
