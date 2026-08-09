# OPS-DATA-02 — موجز تنفيذ إصلاح الواجهات وتسعير الإقامة وتشغيل بيانات يوليو 2026

> هذا هو ملف التسليم التنفيذي إلى Claude Code. يضم مراجعة الشاشات المؤرخة
> 2026-08-09، قرار أسعار الإقامة، خطة التايم شير غير المنفذة، وتصميم شهر
> تشغيلي كامل مترابط محاسبيًا. لا تُنفذ أجزاء منه انتقائيًا بما يخلق أرقامًا
> تشغيلية بلا قيود أو قيودًا بلا مستندات مصدر.

## 1. التحكم والحالة

- **الحالة:** معتمد من Mohamed في 2026-08-10 للتنفيذ أولًا على Local ثم على
  قاعدة الـVPS الحالية باعتبارها بيئة Trial تحت مسؤوليته. لا يبدأ VPS قبل
  نجاح Local كاملًا، backup قابل للاستعادة، dry-run ومطابقة fingerprint الهدف.
- **المالك:** Mohamed.
- **مهندس التنفيذ:** Claude Code.
- **المراجع المستقل:** Codex.
- **تاريخ إعداد الموجز:** 2026-08-10.
- **الفترة التشغيلية المطلوبة:** 2026-07-01 حتى 2026-07-31 بتوقيت
  `Africa/Cairo`.
- **ترتيب البيئات المعتمد:** Local → تقرير تحقق → VPS backup/restore drill →
  VPS dry-run → apply → validate. لا يوجد تطبيق متوازٍ على البيئتين.
- **مستودع Resort OS:** `/home/wego/projects/resort-os`.
- **مستودع الموقع:** `/home/wego/projects/elkheima-marketing-website`.
- **HEAD الذي تمت عليه المراجعة:** `4edcb598b93a65bc2ce2cd4349442399c1c5bb27`.
- **الفرع وقت المراجعة:** `claude/CX-02C-frontend-auth-bootstrap`.
- **حالة الـworktree:** غير نظيف وبه تعديلات قائمة في PMS/Timeshare وواجهات
  العمليات، بالإضافة إلى migration وملف خطة غير متتبعين. هذه التغييرات تخص
  عملًا قائمًا ولا يجوز حذفها أو الكتابة فوقها أو افتراض اكتمالها.

### نقطة توقف أولى إلزامية

قبل أول تعديل كود:

1. اقرأ `AGENTS.md` و`CLAUDE.md` و`wagdy.md` و`PROJECT_STATUS.md` وهذا الملف
   و`TIMESHARE-01_FULL_PLAN_AR.md` كاملين.
2. اعرض `git status --short --branch` و`git diff --stat` وراجع كل diff متداخل.
3. لا تستخدم `git reset --hard` أو `git checkout --` أو stash/حذف لعمل موجود.
4. ثبّت base commit/worktree للحزمة. لو تغييرات التايم شير الحالية غير مفهومة،
   توقف واطلب من Mohamed تحديد هل هي عمل جارٍ يجب استكماله أم تسليمه أولًا.
5. نفذ الحزم كـcommits صغيرة قابلة للمراجعة. تفويض Mohamed يشمل التنفيذ
   والتطبيق على Local وVPS، لكنه لا يلغي قواعد branch/push/deploy الموجودة في
   `AGENTS.md` ولا يسمح بالكتابة فوق عمل قائم غير مفهوم.

## 2. نتيجة المنتج المطلوبة

عند الإغلاق يجب أن يكون الآتي صحيحًا:

1. أخطاء الشاشات والـAPI والتجاوب المذكورة في §6 محلولة باختبارات regression.
2. سعر الإقامة له مصدر حقيقة واحد في PMS ويظهر متطابقًا في Staff App والموقع
   وطلبات الحجز الخارجية، مع snapshot للسعر وقت الطلب/الحجز.
3. خطة التايم شير الحالية منفذة بعد التصحيحات في §8، لا حرفيًا قبل مراجعتها.
4. توجد أداة idempotent ومحكومة تنشئ تاريخًا تشغيليًا صناعيًا كاملًا لشهر
   يوليو 2026 عبر الموديولات، لا مجرد rows منفصلة.
5. العمليات التشغيلية هي التي تنشئ القيود كلما يوجد لها مسار حقيقي، ودفتر
   الأستاذ متزن وقابل للمطابقة مع PMS/POS/Beach/Leasing/Timeshare/Inventory/HR.
6. لا تُرسل أي رسائل أو فواتير ضريبية أو مدفوعات فعلية إلى خدمات خارجية أثناء
   توليد السيناريو.
7. يمكن إثبات مصدر كل صف صناعي ونسخة dataset، ومنع إعادة التشغيل المكرر،
   واستعادة بيئة التدريب أو عكس الأثر بطريقة موثقة.
8. توجد أداة آمنة لتصفير بيانات الـTrial وإعادة بناء قاعدة نظيفة عند الطلب،
   مع backup وهدف صريح وحمايات تمنع تشغيلها على قاعدة خاطئة.

## 3. القرارات المؤكدة وإعدادات الـTrial

### قرارات Mohamed المؤكدة

- إنشاء بيانات تشغيلية كاملة للشهر السابق، والمقصود هنا يوليو 2026 كاملًا.
- أسعار الإقامة الرقمية المطلوبة:

| الفئة التجارية | السعة | السعر المطلوب |
|---|---:|---:|
| Studio | 2 | 2,500 EGP/ليلة |
| Chalet | 4 | 3,500 EGP/ليلة |
| Family Compound: Chalet + Family Studio | 6 | 4,500 EGP/ليلة |

- عرض الأسعار على الموقع وربطها بالحجوزات الداخلية والخارجية.
- إضافة مركز غوص مستأجر، Water Sports مستأجر، Massage/Spa، ومحلات لبيع
  مستلزمات البحر ضمن الإيجارات.
- إدخال سيناريوهات تايم شير وزيارات وأقساط وصيانة استرشادًا بملف Excel.
- تكوين أصول وحسابات ودفتر أستاذ لشهر يبدو فيه المشروع عاملًا فعليًا.
- التطبيق المعتمد على Local ثم VPS Trial، مع إمكانية تصفير آمنة وإعادة البدء.
- الأسعار لا تشمل VAT أو رسم الخدمة، ولا يوجد إفطار ضمن أي سعر.
- قيم الإيجارات والأصول والأرصدة والرواتب تكون صناعية واقعية يحددها هذا
  الموجز؛ لا ننتظر أرقامًا حقيقية من المحاسب لهذه النسخة التجريبية.
- نستخدم من Excel الأنماط والقيم اللازمة فقط، دون نقل أسماء أو أرقام شخصية.

### قرارات تشغيلية محسومة لهذه النسخة

- المبالغ أعلاه سعر الوحدة/الباقة لليلة واحدة بالجنيه المصري، وليست سعر الفرد.
- كل وحدة `S` تبقى Studio مستقلًا بسعة 2. عرض 6 أفراد ليس نوع غرفة وهميًا؛
  هو باقة ذرية من Chalet `A` + Family Studio `S` لهما نفس الرقم.
- الأزواج التجريبية المعتمدة بعد تحقق importer من وجود الوحدتين هي:
  `102A+102S`, `111A+111S`, `122A+122S`, `123A+123S`, `124A+124S`.
- السعر يسري من 2026-07-01 بلا تاريخ نهاية (`effective_to=NULL`) ويظل السعر
  المنشور الحالي بعد يوليو حتى إنشاء version جديدة؛ لا seasonal override الآن.
- السعر المنشور يقال عنه صراحة: «غير شامل 14% ضريبة قيمة مضافة و12% رسم
  خدمة — بدون إفطار». النسب effective-dated وقابلة للتعديل من إعداد الفرع.
- بيانات الشهر صناعية وليست مطالبة بأنها معاملات قانونية أو ضريبية حقيقية.
- أسماء وهواتف وإيميلات عملاء ملف Excel لا تُنسخ إلى dataset. تستخدم أسماء
  صناعية وأرقامًا محجوبة ونطاق `.invalid`؛ لا يوجد احتياج تشغيلي لنقل PII.

### ملف التسعير والضريبة التجريبي

- إعدادات المشروع الحالية في `backend/app/core/config.py` و
  `backend/.env.example` هي VAT `14%` وخدمة `12%`، وتُزرع كنسخة
  `EG-TRIAL-2026-07-v1` لا كأرقام مبعثرة في الخدمات.
- لهذه النسخة فقط: كل من VAT والخدمة يُحسب على السعر الأساسي بصورة مستقلة،
  ثم `total = base + vat + service`، بما يطابق سلوك النظام الحالي. لا يتم
  احتساب VAT مركبًا فوق رسم الخدمة قبل قرار محاسب موثق.

| العرض | الأساسي | VAT 14% | خدمة 12% | الإجمالي/ليلة |
|---|---:|---:|---:|---:|
| Studio 2P | 2,500.00 | 350.00 | 300.00 | 3,150.00 |
| Chalet 4P | 3,500.00 | 490.00 | 420.00 | 4,410.00 |
| Family Compound 6P | 4,500.00 | 630.00 | 540.00 | 5,670.00 |

- لا breakfast line ولا meal-plan ضمن quote. أي طعام طلب Dining منفصل.
- سعر الليلة يطبق على الحجز النقدي/direct/online. زيارة مالك Timeshare داخل
  حقه التعاقدي تحجز نفس مخزون 2/4/6 ولا تُحصّل منه سعر ليلة جديدًا؛ الأقساط
  والصيانة شيء مستقل. Hospitality/rental خارج الحق فقط يأخذ quote وسياسة
  رسوم موثقة بدل خلط سعر الإقامة بقيمة عقد التايم شير.
- المصدر القانوني العام للـVAT هو قانون 67/2016 وتعديلاته في
  [بوابة قوانين VAT الرسمية لمصلحة الضرائب](https://www.eta.gov.eg/ar/content/qwanyn-aldrybt-ly-alqymt-almdaft)؛
  أما 12% هنا فهو إعداد الخدمة الحالي وقرار تجريبي، لا فتوى قانونية.
- لا ETA invoice/e-receipt حقيقي من dataset. قبل استخدام النظام لإقرار ضريبي
  فعلي، يراجع المحاسب tax basis والإعفاءات والتسجيل ويصدر نسخة profile جديدة.

## 4. الأدلة ومصادر الحقيقة

### 4.1 ملف محاسبة التايم شير

- **المصدر:** `/home/wego/Downloads/محاسبة تايم شير .xlsx`.
- **SHA-256:**
  `251ee5e22223f30b2a923d21b552e627c2b230a36bf7511f821e21aaaa206066`.
- **الحجم:** 220,611 bytes.
- **عدد الأوراق:** 21 ورقة: `37`–`52` وخمس أوراق تجميع/تصنيف.

الملف أرشيف قديم غير مكتمل، وفيه قوالب وصفوف إجماليات وصيغ وبيانات مكررة؛
ليس price list حديثًا ولا يجوز استيراده row-for-row. البيانات التاريخية
القابلة للاستخدام كأنماط هي:

| السعة التاريخية | القيم المرصودة بعد استبعاد الإجماليات |
|---|---|
| `2R` | 45,000؛ 50,000؛ 70,000 EGP |
| `4R` | 70,000؛ 73,500؛ 100,000 EGP |
| `6R` | 140,000 EGP |

تفاصيل مهمة للمستورد:

- ورقة `أقل من 5000` تحتوي 16 عقدًا/سجلًا فعليًا في الصفوف 4–19، ثم صف
  إجمالي في 180 لا يُعامل كعقد.
- التوزيع الفعلي فيها: ثمانية `2R`، خمسة `4R`، ثلاثة `6R`.
- توجد أرقام عقود غير رقمية مثل `بدون عقد` و`ب عقد+ب كمبيالة`.
- تنسيقات التواريخ مختلطة بين Date cells ونصوص `/` و`\`.
- ورقة `الكنسل` تحتوي نموذج إلغاء ودفعًا جزئيًا يصلح كسيناريو، لا كسجل جاهز.
- بعض السجلات مكررة بين أوراق المصدر والتجميع.
- القيم أعلاه تاريخية لعقود 2022–2024، ولا تُعلن كسعر بيع عقد جديد في 2026.

### 4.2 الواقع الحالي في الكود

- المخزون الحقيقي المعتمد: 14 وحدة، 8 Chalet و6 Studio، والأسعار والسعات
  ما زالت `NULL` عمدًا في `backend/app/real_room_inventory.py`.
- PMS يسعر الحجز من `RoomType.base_rate` أو `RatePlan` ويخزن السعر الفعلي
  في `BookingRoom.daily_rate`.
- الموقع يعرض فئتي Chalet/Studio ثابتتين بلا أسعار، و
  `PUBLIC_TRUTH.publish.prices=false` في مستودع الموقع.
- نموذج الغرف في الموقع يرسل حاليًا Contact Request، لا ينشئ
  `HubOnlineBooking` ولا PMS booking.
- `POST /hub/online-bookings` الحالي يحتاج مستخدمًا مسجلًا، يخزن بيانات الحجز
  الحساسة بشكل يحتاج مراجعة، ولا يحفظ quote واضحًا؛ و`confirm_booking` يمكن
  أن يؤكد Hub request حتى لو لم تُنشأ غرفة في PMS.
- `backend/app/production_demo_seed.py` مقصود به master/demo catalogs فقط
  ويمنع الحجوزات والمدفوعات والقيود. لا توسّع عقده؛ أنشئ importer مستقلًا.

## 5. ثوابت السلامة والمالية

1. كل الأموال `Decimal` ومخزنة `Numeric`؛ ممنوع `float` في الحساب أو JSON
   المرجعي المالي.
2. لا تُنشأ قيود إيراد يدويًا إذا كان نفس الإيراد يمكن إنشاؤه من checkout أو
   settlement أو collection حقيقي.
3. كل Journal Entry متزن، وكل سطر له cost center عندما يكون النشاط معلومًا.
4. لا حذف أو تعديل لقيد posted؛ التصحيح بقيد reversal مرتبط بالأصل.
5. كل source event له مفتاح idempotency/reference يمنع ترحيل القيد مرتين.
6. لا يُسجل عقد إيجار أو Timeshare أو Booking بسعر صفر/`NULL`.
7. الحجز الخارجي لا يصبح `confirmed` إلا إذا حُجزت غرفة PMS فعلًا في نفس
   العملية؛ غياب المخزون ينتج `409/awaiting_inventory` لا تأكيدًا وهميًا.
8. السعر الظاهر للضيف والسعر المحفوظ في الطلب والسعر في `BookingRoom` يجب
   أن يتطابقوا، أو يُسجل override بصلاحية وسبب وAudit.
9. فترة يوليو تظل `open` أثناء الاستيراد والمراجعة، ولا تُغلق تلقائيًا.
10. البيانات الصناعية لا تنشئ اتصالات خارجية: لا Paymob charge، لا ETA، لا
    WhatsApp/SMS/Email، ولا CRM marketing consent افتراضي.
11. لا `date.today()` أو `datetime.utcnow()` لتحديد تاريخ الحدث الصناعي؛ كل
    event يأخذ وقتًا صريحًا بتوقيت القاهرة ويحفظ UTC بطريقة صحيحة.
12. لا PII حقيقية من Excel في fixtures أو logs أو commits.
13. أي bug يظهر أثناء seed لا يُغطى بـSQL patch أو تجاهل validation: أنشئ
    regression test، أصلح service/source posting، ثم أعد السيناريو من بدايته.

## 6. الحزمة UX-API-01 — إصلاح المشاكل المكتشفة في الصور

هذه الحزمة تسبق إدخال البيانات حتى لا تتحول البيانات الصحيحة إلى قوائم ناقصة
أو أصفار كاذبة.

### 6.1 المستخدمون والصلاحيات

- Backend `/users` يقبل `size<=100` بينما النسخة المنشورة أرسلت `size=200`.
- التغيير المحلي إلى `100` workaround فقط وليس إغلاقًا للمهمة.
- نفذ pagination/server search في المستخدمين، قائمة الصلاحيات، واختيار الموظف.
- افصل `overallTotal` عن إجمالي نتيجة البحث.
- وفر endpoint aggregate للإحصائيات، أو اجلب كل الصفحات صراحةً.
- لا تعتمد أول 100 لتحديد عدد active super admins أو أسماء منفذي Audit.
- لا تضع tab في `tabsLoaded` قبل نجاح الطلب؛ أضف Retry وراقب `route.query.tab`.

**قبول:** المستخدم 101 و500 يمكن إيجادهما وإدارة صلاحياتهما، وإحصاءات الرأس
لا تتغير عند البحث، ولا يوجد `422` في Network.

### 6.2 رسائل الموقع

- غيّر شاشة الموظف من `GET /hub/contact` غير الصحيح إلى
  `GET /hub/contact-forms`.
- طابق `ContactFormListItem` (`full_name`, `public_reference`, `status`,
  `crm_sync_status`, `marketing_consent`...).
- لا تستخدم `is_read` الوهمي. إما تحذف unread UI أو تضيف `reviewed_at/read_at`
  وmutation وAudit حقيقيين.
- لا تحول الخطأ إلى قائمة فارغة.

**قبول:** رسالة ضيف صناعية تظهر للموظف بكل حالتها، وفشل API يظهر Error+Retry.

### 6.3 Reception وRecipes وعقود query parameters

- Reception يستخدم `limit` و`check_in_date` بينما PMS يقبل
  `page/size/check_in_from/check_in_to`.
- اجلب checked-in bookings بكل الصفحات، واجلب حجوزات اليوم بمدى اليوم الصحيح.
- Recipes يستخدم `limit:200` لـInventory، فيحصل فعليًا على أول 20 فقط؛ نفذ
  pagination أو server search.
- نظف `FinanceView` من `limit/branch_id` غير المدعومين في exchange rates حتى
  لا يستمر contract drift ولو كان default الحالي يخفيه.
- أضف contract tests تمنع query غير موجودة في OpenAPI؛ الأفضل client typed
  مولّدًا أو schemas مشتركة بدل `Record<string, unknown>` الحر.

### 6.4 HR self-service والتوجيه

- `/hr/me/*` يعيد 404 عمدًا للحساب غير المرتبط بـEmployee؛ لا تحوله إلى `[]`.
- أضف `employee_self_service_available` أو `employee_id` إلى bootstrap/auth.
- اخف روابط HR الذاتية للحساب غير الموظف واعرض Not Applicable واضحًا.
- أضف `timeshare_admin/timeshare_agent` إلى `homeRouteFor`.
- لا تجعل permission fallback أو Sessions Back يذهب دائمًا إلى
  `/portal/profile`؛ استخدم home آمن حسب الدور.
- أزل `admin` من روابط Timeshare في Sidebar لأن Backend يعزل الموديول، أو غيّر
  السياسة كلها بقرار مالك صريح؛ لا تترك Nav وRoute وBackend متعارضين.

### 6.5 Dashboard والأصفار الكاذبة

- `Promise.allSettled` الحالي يحول فشل كل API إلى صفر ولا يفعّل `loadError`.
- لكل widget حالة `loading/success/empty/error`؛ الفشل يعرض `—` وRetry، لا صفرًا.
- لا تطلب CS Timeshare لدور غير مخوّل ثم تعتبر 403 = لا توجد متأخرات.
- `lastUpdated` يعكس آخر نجاح، لا مجرد انتهاء المحاولة.

### 6.6 Settings وSessions والـConsole

- استخدم `auth.branchId`/allowed branches بدل `auth.user?.branch_id` للتحذير.
- ادمج Quick Links الثلاثة التي تتحول كلها إلى `/admin/dining-menu`.
- حلل User-Agent إلى Browser/OS مفهوم، واستخدم `<bdi dir="ltr">` للنص الخام
  وIP والمعرفات في RTL.
- أضف favicon حقيقيًا من assets الموجودة.
- لا تضف `/finance/shift_report` compatibility endpoint. أعد الإنتاج بعد مسح
  Network وحدد Initiator؛ المسار الحالي الصحيح `/finance/shifts/{id}/report`.
- `content.js: Feature is disabled` يُستبعد إذا ثبت أنه Browser Extension.

### 6.7 التجاوب وإتاحة الاستخدام

- Topbar: `min-w-0` وtruncate وتجميع الأدوات الثانوية على 320–430px.
- Drawer: عرض أقصى `min(18rem, calc(100vw - 1rem))`، `100dvh`، body scroll
  lock، focus trap، focus return، وdialog semantics.
- Dashboard/Settings: عمود واحد على xs ثم عمودان من `sm`.
- Permission rows وSessions modal تتحول إلى column/wrap على xs.
- Hub tabs قابلة للتمرير الأفقي.
- الجداول: mobile cards أو scroller مقصود مع action column قابل للوصول؛ ممنوع
  document-level horizontal overflow.

**مصفوفة الاختبار:** `320,360,390,430,768,1024,1280,1440,1920` مع
`568,667,844,1024` ارتفاعًا، Arabic RTL وEnglish LTR، portrait/landscape،
Zoom 200%، وأحجام بيانات `0,1,20,100,101,500`.

أضف Playwright visual/functional suite؛ الـ95 frontend tests الحالية ليست
Browser/viewport tests ولا تثبت التجاوب.

## 7. الحزمة ROOM-PRICE-01 — مصدر حقيقة سعر الإقامة

### 7.1 نموذج PMS وبيانات الغرف

أنشئ أداة بيانات مستقلة، dry-run افتراضيًا، مثل:

`backend/app/approved_room_pricing.py`

ويكون عقدها:

- branch code صريح، actor super_admin صريح، advisory lock، dataset version،
  confirmation phrase، Audit marker، before/after snapshot.
- تتحقق من وجود الوحدات الـ14 المعتمدة قبل التعديل.
- تنشئ/تحدث نوعين فعليين للغرف:
  - `Studio 2P`: `max_occupancy=2`, `base_rate=2500.00`.
  - `Chalet 4P`: `max_occupancy=4`, `base_rate=3500.00`.
- تنشئ منتجًا/باقة قابلة للحجز `Family Compound 6P` بسعر `4500.00`، لا
  `RoomType` ثالثًا؛ كل occurrence يشير إلى زوج الوحدات في §3.
- Availability للباقة هي تقاطع إتاحة الوحدتين، والتأكيد يقفلهما ويحجزهما في
  transaction واحدة. فشل قفل أي منهما يلغي الكل ويرجع `409`.
- check-in/out/cancel/no-show يحدّث الوحدتين، بينما guest folio وquote واحدان.
- يمنع النظام بيع أي وحدة منفردة في نفس التواريخ بعد حجز الباقة والعكس.
- لأغراض تحليلات الوحدة فقط يوزع صافي `4500` بنسبة السعرين المستقلين:
  `2625` للشاليه و`1875` للاستوديو؛ الضيف والدفتر يرون إيراد باقة واحدًا
  بإجمالي `4500` قبل الضريبة والخدمة، ولا ينشأ إيراد مزدوج.
- لا تغيّر تاريخ `BookingRoom.daily_rate` لحجوزات قديمة عند تعديل السعر.
- إذا كانت هناك حجوزات مرتبطة بنوع سيتغير، استخدم migration/update محافظًا
  للـFK ولا تحذف type مستخدمًا.
- لا تنشئ seasonal RatePlan ما دام السعر الأساسي ثابتًا. أضف الخطط فقط عند
  وجود قرار موسم موثق.

### 7.2 API العام والسعر المنشور

- اجعل public availability/catalog endpoint يرجع الغرف والباقات بمعرف عام
  ثابت، الاسم المترجم، السعة، السعر الأساسي، VAT، الخدمة، الإجمالي، العملة،
  `price_unit=night`، `effective_from`، `includes_breakfast=false`.
- الفرع العام يجب أن يُحسم server-side من resort/site config؛ لا تثق في
  `branch_id=1` من العميل كحد أمني مستقبلي.
- لا تقلب `PUBLIC_TRUTH.publish.prices=true` عالميًا؛ هذا قد ينشر أسعار Beach
  وPackages غير معتمدة. أضف gate مخصصًا `roomPrices` أو registry facts مؤرخًا.
- الموقع في `/home/wego/projects/elkheima-marketing-website` يجلب الأنواع
  من API بدل array Chalet/Studio الثابتة، ويعرض:
  - السعر بالجنيه/ليلة.
  - السعة.
  - حالة تعذر تحميل السعر بدل رقم قديم مخبأ.
  - Arabic/English/Russian/Italian بنفس القيمة، لا تحويلات أو أرقام متعارضة.
- أضف Schema.org Offer بالقيمة الأساسية، `priceCurrency=EGP`، ووصف صريح أن
  VAT 14% والخدمة 12% غير شاملين وأن الإفطار غير متاح؛ لا تجعل structured
  data توحي بسعر نهائي مختلف عن النص المرئي.

### 7.3 الحجز الخارجي الحقيقي

لا تجعل الموقع يرسل حجز الغرفة إلى Contact Form بعد هذه الحزمة. صمم contract
عامًا آمنًا لـOnline Booking:

- endpoint عام محدد للفرع من إعداد السيرفر، rate-limited وidempotent، مع
  honeypot/abuse controls وservice-contact disclosure.
- تشفير اسم/هاتف/إيميل الحجز في السكون أو توثيق بديل privacy-safe.
- `room_type_id`, check-in/out, adults, children، وعدد الليالي.
- quote snapshot: `nightly_rate`, `nights`, `subtotal`, taxes/service إن وجدت،
  `total`, `currency`, `quoted_at`, `rate_plan_id/effective_version`، ومع الباقة
  `bundle_id` وsnapshot للوحدتين دون كشف IDs داخلية غير لازمة للعميل.
- الحالة الأولية `pending`; التأكيد يتم transactionally مع حجز غرفة متاحة.
- إذا لا توجد غرفة: يبقى request `pending/awaiting_inventory` وتعود رسالة
  واضحة؛ ممنوع `confirmed` بلا `pms_booking_id`.
- عند التأكيد، `Booking.source=online` والسعر المحفوظ يطابق quote، مع Audit.
- أي staff override للسعر يحتاج صلاحية وreason وRevenueAuditLog.

**اختبارات إلزامية:** quote drift، تغير السعر بعد الطلب، double confirmation،
double-booking متزامن، retry بنفس idempotency key، room unavailable، branch
tampering، over-capacity، تشفير PII، حجز/إلغاء الباقة الذري، وتعارض الباقة مع
حجز منفرد على أي وحدة من الزوج.

## 8. الحزمة TIMESHARE-01R — دمج وتصحيح الخطة الحالية

المرجع غير المنفذ هو:
`docs/agent-workflow/TIMESHARE-01_FULL_PLAN_AR.md`.

تُضم كل نتائجه الوظيفية: أسبوع السبت، السعة، المستفيد والهواتف، التواريخ
البديلة، قواعد/مواسم الذروة، الصيانة، ملف العميل، الزيارات والبوابة؛ لكن
التعديلات الآتية ناسخة لأي نص متعارض فيه:

1. **إثبات الموافقة:** `terms_accepted` و`booking_rules_accepted` لا يكفيان
   كحقول request مؤقتة. خزّن version/hash و`accepted_at` وactor/request id
   وسجّل Audit. أي نص جديد له version جديد ولا يعيد كتابة تاريخ القديم.
2. **Backfill السعة:** لا تضف `unit_capacity default=2` لكل العقود القديمة.
   أضفها nullable أولًا، استنتج فقط من `2R/4R/6R` الموثق، اصدر تقرير unknown،
   راجع، ثم أضف Check Constraint `IN (2,4,6)` وNOT NULL عند اكتمال backfill.
3. **أسعار الصيانة:** لا hard-code سنة 2026 ثم تعدل contracts يدويًا سنويًا.
   أضف جدول قواعد effective-dated/versioned حسب contract-date tier والسعة
   والسنة، واحفظ fee snapshot في كل due. قواعد 2026 من الخطة تزرع كنسخة أولى.
4. **مواسم الذروة:** `created_by` يكون nullable إذا FK `SET NULL`. لا حذف
   لموسم استُخدم في قرار؛ استخدم inactive/archive واحفظ snapshot على الطلب.
5. **تعريف المتتالي:** ألغِ افتراض فجوة 30 يومًا. سياسة الـTrial المختارة هي:
   العقد الذي استخدم أسبوعًا داخل موسم `peak_kind=official_holiday` في سنة
   موسم لا يحصل على official holiday في السنة التالية مباشرة؛ يمكنه التقديم
   مجددًا بعد سنة فاصلة. الصيف/الموسم العادي لا يُعامل كعيد. اجعل
   `holiday_cooldown_years=1` إعدادًا versioned، واحفظ rule snapshot على
   القرار حتى يمكن لمحمد تغييره دون إعادة تفسير التاريخ.
6. **عدم العد المزدوج:** الطلب approved والزيارة الناتجة عنه حدث واحد؛ تقرير
   peak usage لا يحسبهما مرتين. اربط visit بـrequest أو ضع dedup key واضحًا.
7. **حدود السنة:** اختبر ISO week 1/52/53 والسبت الذي يعبر سنة ميلادية، ولا
   تعيد تفسير زيارات تاريخية بصمت عند تغيير بداية الأسبوع.
8. **السنوات التاريخية:** لا تقيد `season_year >= 2026` إذا كنا سنعرض زيارات
   يوليو أو سجلات أقدم.
9. **ترتيب المراحل:** ملف العميل الذي يعرض peak usage يعتمد على peak models
   وقواعدها؛ ليس مستقلًا بالكامل عن المرحلتين 3/4 كما تقول الخطة القديمة.
10. **Privacy:** لا تستخدم أسماء/هواتف ملف Excel في tests أو demo. أنشئ
    fixtures صناعية تمثل الأنماط والقيم فقط.
11. **مخزون 6R:** عقد/طلب بسعة 6 يحجز Family Compound pair من §3 ذريًا مثل
    الحجز العادي، لكنه لا يسجل daily room revenue إذا كانت الزيارة entitlement
    مسددة بالعقد. خزّن `entitlement_visit=true` وbundle allocation للتشغيل
    والإشغال، وافصل أي hospitality/extra fees في folio مستقل واضح.

### سيناريوهات التايم شير في يوليو

أنشئ 12 عقدًا صناعيًا موزعة على `2R/4R/6R`، بتواريخ تعاقد تاريخية وقيم ضمن
النطاقات المرصودة، وليس باعتبارها سعر 2026:

- عقود مسددة بانتظام، عقد بقسط partial، عقد overdue، وعقد cancelled.
- دفعات أولى وأقساط يوليو ودفعة صيانة، وكلها تولد قيودًا بمراجع فريدة.
- ست زيارات completed خلال يوليو موزعة على السعات.
- طلب approved تحول إلى visit، طلب rejected بسبب عدم الإتاحة، طلب frozen
  بسبب متأخرات، وwaitlist واحد.
- زيارة عيد تنجح، وطلب عيد في السنة التالية يفشل بقاعدة التتابع، وطلب موسم
  صيفي لا يفشل بسبب قاعدة العيد مع بقائه خاضعًا لحد أسبوع الذروة السنوي.
- عدم تداخل وحدة Timeshare أو تجاوز السعة.

## 9. الحزمة HIST-01 — محرك تاريخ تشغيلي لشهر يوليو

### 9.1 لا توسع production_demo_seed

أنشئ CLI مستقلًا مثل:

`python -m app.operational_history_seed --branch-code ELK-001 --period 2026-07`

الخصائص المطلوبة:

- dry-run افتراضي، و`--apply` يحتاج confirmation phrase يتضمن branch/period/version.
- Local يحتاج confirmation عادي. VPS Trial يحتاج flag إضافيًا، fingerprint
  مطابقًا، backup وrestore drill ناجحًا؛ لا تعتمد فقط على `ENVIRONMENT` لأن
  اسم البيئة التقني قد يكون `production` رغم كون البيانات تجريبية حاليًا.
- dataset version وSHA للmanifest، advisory lock، actor، Audit marker.
- فحص preconditions: الفرع، الحسابات، الغرف، الأسعار، المينيو، المخزون،
  الممثلون، الفترة المحاسبية، وعدم وجود نفس marker.
- منع rerun حتى بعد crash باستخدام import batch/checkpoints.
- `--dry-run` يعرض counts والمبالغ المتوقعة والمخاطر بلا commit.
- `--validate-only` يعيد المطابقات على dataset مطبق.
- لا يطبع PII أو secrets.

### 9.2 الزمن التاريخي

المسارات الحالية تستخدم مزيجًا من `business_today/local_today/datetime.utcnow`
وDB defaults، لذلك استدعاؤها اليوم سيضع قيود يوليو في أغسطس. قبل التوليد:

- أدخل Clock داخليًا قابلًا للحقن للمسارات التي يستخدمها السيناريو، مع default
  يظل الوقت الحقيقي.
- `event_at` داخلي وليس query عامًا يسمح للمستخدم العادي بالـbackdate.
- journal `entry_date`، shift opened/closed، payments، orders، attendance،
  work orders وAudit timestamps تعكس وقت السيناريو المتفق عليه.
- DB `created_at/updated_at` للأطفال والسجلات التابعة لا تبقى بتاريخ التطبيق.
- اختبر التحويل بين Cairo وUTC خاصة 00:00 وورديات ما بعد منتصف الليل.

لا تستخدم monkeypatch مؤقتًا أو تحديث SQL شامل بعد الإنشاء. الأفضل فصل
business operation عن commit وإتاحة `commit=False/event_at` داخليًا، ثم تجعل
CLI هو مالك Unit of Work/checkpoint.

### 9.3 Manifest والرجوع

- سجل import batch: version، period، branch، status، actor، checksum، counts،
  totals، started/completed، وأي failure.
- سجل/manifest لكل source reference أو row صنعه المستورد.
- في Local وVPS Trial، rollback المفضل restore لنسخة DB المأخوذة قبل apply.
- حتى لو اسم بيئة VPS هو `production` تقنيًا، لا hard-delete قيود posted أو
  مدفوعات من التطبيق العادي؛ reset الكامل يتم باستبدال قاعدة Trial كاملة من
  baseline/backup، لا بكسر قواعد المحاسبة سجلًا بسجل.
- أي row تم تعديله يدويًا بعد الاستيراد يمنع rollback الآلي.

### 9.4 RESET-01 — التصفير وإعادة البداية النظيفة

أنشئ أداة إدارة واحدة موثقة، مثل:

```bash
./scripts/resort-data backup        --target local|vps
./scripts/resort-data seed-july     --target local|vps --dry-run
./scripts/resort-data validate      --target local|vps --period 2026-07
./scripts/resort-data reset-dataset --target local|vps --version july-2026-v1 --dry-run
./scripts/resort-data rebuild-trial --target local|vps --dry-run
```

العقد الإلزامي:

- كل الأوامر dry-run افتراضيًا، وتقرأ الاتصال من secret/env موجود ولا تقبل
  DB URL أو password كـCLI argument أو تطبعه في logs.
- قبل `--apply` تعرض host/database/schema، instance UUID، branch، migration
  head، row counts، آخر backup وSHA له. تأخذ confirmation phrase يضم هذه
  القيم؛ `local` و`vps` ليسا مجرد labels قابلين للتبديل.
- `reset-dataset` يفحص manifest: إذا وصل dataset إلى posted journals أو
  settled payments فطريق الرجوع هو restore للـpre-apply backup، لا حذف rows.
  يسمح بالحذف المحدد فقط لbatch فاشل قبل posting، بترتيب FK موثق، ويرفض إذا
  عُدّل أي صف أو ارتبط ببيانات ليست من نفس dataset.
- `rebuild-trial` عملية مختلفة ومدمرة: backup جديد → اختبار سلامته → إنشاء DB
  بديلة/نظيفة → Alembic upgrade → master catalogs → bootstrap admin → pricing
  → July seed → validation → switch ذري. لا `DROP/TRUNCATE` لقاعدة غير مؤكدة.
- احتفظ بآخر 3 backups مشفرة على الأقل مع retention واضح، واختبر restore على
  اسم قاعدة مؤقت قبل أول VPS apply. لا يكفي نجاح أمر `pg_dump`.
- default يحافظ على migration history/configuration/bootstrap path ولا يعيد
  استخدام كلمات مرور demo. بيانات الدخول الأولية تأتي من secret أو one-time
  reset flow، ولا تُكتب في manifest.
- بعد تحول الـVPS من Trial إلى تشغيل قانوني حقيقي، يعطّل `rebuild-trial`
  افتراضيًا ولا يعمل إلا بموافقة جديدة مستقلة ونافذة صيانة.
- اختبارات shell/integration تغطي target mismatch، backup failure، partial
  failure، retry، altered row، wrong confirmation، واستعادة ناجحة end-to-end.

## 10. Manifest البيانات التشغيلية المطلوبة

الأعداد التالية fixtures ثابتة قابلة للمراجعة، وليست random بلا seed.

### 10.1 الموظفون والأدوار — Local/VPS Trial فقط حتى اعتماد roster حقيقي

- 14 موظفًا صناعيًا: مدير، محاسب، HR، 2 استقبال، 2 كاشير، 2 مطبخ/كافيه،
  2 خدمة، 2 Housekeeping، 1 صيانة.
- Accounts لازمة لتشغيل السيناريو فقط، ببريد `.invalid` وكلمات مرور عشوائية
  غير مطبوعة وحسابات غير قابلة للدخول خارج بيئة التدريب.
- حضور يوليو، يوم إجازة approved، تأخير، overtime، وغياب مبرر.
- Payroll run واحد لـ2026-07 مع payslips وقيود رواتب/التزامات متزنة.
- الرواتب الأساسية الصناعية الشهرية:

| الوظيفة | العدد | راتب الفرد | الإجمالي |
|---|---:|---:|---:|
| Resort Manager | 1 | 28,000 | 28,000 |
| Accountant | 1 | 18,000 | 18,000 |
| HR | 1 | 15,000 | 15,000 |
| Reception | 2 | 13,000 | 26,000 |
| Cashier | 2 | 11,000 | 22,000 |
| Kitchen/Cafe | 2 | 12,000 | 24,000 |
| Service | 2 | 9,000 | 18,000 |
| Housekeeping | 2 | 8,500 | 17,000 |
| Maintenance | 1 | 13,000 | 13,000 |
| **الإجمالي الأساسي** | **14** |  | **181,000** |

- أضف `12,600` overtime/allowances موزعة من attendance، فيكون gross قبل
  الاستقطاعات `193,600`. لا hard-code صافي الرواتب أو التأمينات: مررها عبر
  Payroll engine ونسخة tax/social-insurance effective-dated. النظام الحالي
  يزرع شرائح 2024؛ لا تُعرض كحساب قانوني 2026 قبل تحديثها، ويمكن وسم run
  `synthetic_non_filing=true` في الـTrial.
- في التشغيل القانوني الحقيقي لا تُنشأ هويات صناعية؛ يلزم roster معتمد.

### 10.2 PMS والحجوزات

- 38 حجزًا موزعة: direct/online/phone/B2B.
- fixture صريح: 70 Studio nights منفردة + 75 Chalet nights منفردة + 25
  Family Compound nights. الباقة تستهلك 50 physical unit-nights، فيكون
  الإشغال `195 / (14 × 31) = 44.93%`، وصافي room revenue قبل VAT/service:
  `70×2500 + 75×3500 + 25×4500 = 550,000 EGP`.
- VAT الغرف `77,000` والخدمة `66,000` وإجمالي فواتير الإقامة `693,000` قبل
  extras/discounts/refunds. تحفظ الأرقام من line items لا كقيد إجمالي مزيف.
- completed/checked-out، إلغاءات، no-show، وstay يعبر نهاية الشهر.
- حالتا early check-in/late checkout برسوم، وحجز multi-room واحد.
- 31 Night Audit logs؛ يوم بلا إشغال ويوم مرتفع الإشغال.
- Housekeeping checkout clean/inspection، وغرفة maintenance تمنع الحجز.
- كل `total_rate = Σ BookingRoom.total + approved extras`.

### 10.3 Hub والحجز الخارجي وCRM

- 12 طلبًا من website/WhatsApp/Instagram، منها confirmed→PMS وcancelled
  وpending/awaiting inventory.
- Contact forms بموافقة خدمة إلزامية؛ marketing consent false افتراضيًا،
  وعينتان true مع version لإثبات مسار CRM فقط.
- Customers/Leads/Opportunities مرتبطة بالحجوزات دون duplication بالهاتف.
- لا رسائل أو حملات خارجية فعلية.

### 10.4 POS والمطعم والكافيه والشاطئ والورديات

- ورديتان يوميًا بحد مستهدف 62 وردية مغلقة، مع فتح/إغلاق وتقارير end-of-shift.
- 4–8 Dining orders في اليوم موزعة Restaurant/Cafe، و3–5 Beach transactions
  في أيام النشاط؛ لا تُنشأ صفوف مجمعة بلا items.
- مستهدف fixture قبل الضريبة والخدمة: Restaurant `165,000`، Cafe `120,000`،
  Beach `132,000`. Dining/Cafe dine-in يستخدمان 14% VAT +12% service؛
  takeaway/delivery بلا service عند ضبط channel override، وBeach يستخدم VAT
  فقط. القيم النهائية تُحسب من الأصناف الفعلية وقد تقل بالخصومات/المرتجعات؛
  manifest يطبع gross/refunds/net لكل منفذ.
- طرق الدفع المستهدفة: 55% cash، 30% card، 10% room folio، 5% personal credit.
- cash safe drops، petty cash، drawer open، وفرقين صغيرين موثقين بموافقة،
  وبقية الورديات variance=0.
- void قبل التسوية، refund بعد التسوية، discount مع approval، split tender،
  order على الغرفة، B2B beach check-in، وBeach EOD.
- الوصفات تخصم مخزونًا وCOGS؛ لا إيراد بلا Payment/folio charge مقابل.

### 10.5 الإيجارات والمستأجرون

استخدم عقودًا صناعية نشطة من 2026-06-01 إلى 2027-05-31، الاستحقاق يوم 1،
grace حتى يوم 10، ثم غرامة 2% مرة واحدة. القيم الواقعية المعتمدة للـTrial:

| العقد | النشاط | الإيجار الشهري | التأمين | سيناريو يوليو |
|---|---|---:|---:|---|
| `HIST-LSE-DIVE-01` | مركز غوص | 45,000 | 90,000 | تحويل بنكي 1 يوليو |
| `HIST-LSE-WATER-01` | Water Sports | 35,000 | 70,000 | تحويل بنكي 4 يوليو |
| `HIST-LSE-SPA-01` | Massage/Spa | 25,000 | 50,000 | 15,000 بنك +10,000 نقدي |
| `HIST-LSE-SHOP-01` | مستلزمات بحر | 18,000 | 36,000 | 18,000 +360 غرامة يوم 15 |
| `HIST-LSE-SHOP-02` | مستلزمات/بقالة شاطئ | 15,000 | 30,000 | overdue في 31 يوليو |
| **الإجمالي** |  | **138,000** | **276,000** | محصل `123,360`؛ AR=`15,000` |

التأمينات مستلمة قبل 2026-06-30 وتظهر التزامًا `2150` لا إيرادًا. عقود
الإيجار تحمل tax code مستقلًا؛ لا يضيف importer VAT افتراضيًا لأن إيجار
الوحدات غير السكنية له معالجة تحتاج مطابقة شكل العقد/الترخيص، بينما يظل
الإيراد ظاهرًا ومعلّمًا `tax_review_required` في تقرير الـTrial.

قبل seed أصلح المحاسبة الحالية للإيجار:

- لا تسجل security deposit كـCash بمجرد توقيع العقد؛ سجله عند receipt حقيقي.
- accrue الإيجار في due date: Dr tenant receivable / Cr rent revenue.
- عند التحصيل فقط: Dr cash/bank/card clearing / Cr tenant receivable.
- لا تستخدم `1100` لكل طرق الدفع.
- اجعل مراجع accrual/receipt منفصلة وidempotent.
- أضف cost center `LEASE` واظهر aging للمستأجرين.

معدات المستأجرين لا تُسجل أصولًا للمنتجع إلا إذا العقد يثبت ملكية المنتجع.

### 10.6 المخزون والمشتريات والصيانة

- رصيد افتتاحي `420,000`: Food/Beverage `140,000`، Housekeeping `80,000`،
  Maintenance `120,000`، Beach/Retail supplies `80,000`.
- خمسة Purchase Orders بإجمالي `160,000`، استلام كامل وجزئي، Supplier AP،
  issue للمطبخ/Housekeeping/الصيانة، low stock وreorder.
- استهلاك/COGS يوليو المستهدف `185,000` من recipe/issue lines، فيكون closing
  valuation المتوقع `395,000` قبل أي stock adjustment. أي فرق يحتاج counted
  adjustment موثق، ولا stock سالب.
- 10 Work Orders: preventive، corrective، pending parts، completed، cancelled.
- تخصيص قطع من Inventory واختبار تحرير الأصل بعد الإكمال/الإلغاء.

### 10.7 الأصول الثابتة — قيم صناعية معتمدة للـTrial

الإهلاك straight-line، salvage صفر في fixture، monthly convention، ولا إهلاك
للأرض. opening accumulated محسوب حتى 2026-06-30:

| المجموعة | العدد | التكلفة | بدء الاستخدام | العمر | Opening accum. |
|---|---:|---:|---|---:|---:|
| أرض المنتجع | 1 | 6,000,000 | 2023-01-01 | بلا إهلاك | 0 |
| مباني وتحسينات المنتجع | 1 group | 9,500,000 | 2023-01-01 | 25 سنة | 1,330,000.00 |
| Pool/Landscape works | 1 group | 1,200,000 | 2023-01-01 | 10 سنوات | 420,000.00 |
| مولد كهرباء | 1 | 450,000 | 2024-01-01 | 10 سنوات | 112,500.00 |
| مضخات مياه | 2 | 150,000 | 2024-01-01 | 5 سنوات | 75,000.00 |
| تكييفات الوحدات | 14 | 420,000 | 2024-01-01 | 5 سنوات | 210,000.00 |
| مطبخ وتبريد | 1 group | 350,000 | 2024-07-01 | 7 سنوات | 100,000.00 |
| معدات كافيه | 1 group | 180,000 | 2025-01-01 | 5 سنوات | 54,000.00 |
| أثاث الوحدات | 14 packages | 630,000 | 2024-07-01 | 7 سنوات | 180,000.00 |
| أثاث المطعم | 1 group | 250,000 | 2024-07-01 | 7 سنوات | 71,428.57 |
| IT/POS/CCTV | 1 group | 180,000 | 2025-01-01 | 4 سنوات | 67,500.00 |
| معدات شاطئ مملوكة للمنتجع | 1 group | 220,000 | 2025-04-01 | 4 سنوات | 68,750.00 |
| Laundry/Housekeeping | 1 group | 140,000 | 2025-01-01 | 5 سنوات | 42,000.00 |
| **الإجمالي** |  | **19,670,000** |  |  | **2,731,178.57** |

كل أصل له code/location/purchase date/cost/salvage/useful life/depreciation
start، ويشغّل July depreciation مرة واحدة idempotently. لا تجعل grouped asset
بديلًا لأصل فردي إذا الصيانة تحتاج تتبع serial مستقلًا.

إهلاك يوليو المتوقع من الجدول `83,226.19 EGP`؛ الخدمة تحسبه من سجل كل أصل
وتعالج قرش rounding على آخر أصل، ولا تنشئ قيدًا إجماليًا دون asset entries.

### 10.8 التايم شير

نفذ manifest §8: 12 عقدًا صناعيًا، installments/maintenance/visits/requests/
waitlist، مع نطاقات القيم التاريخية من Excel، دون نسخ أي اسم أو رقم حقيقي.

- قيم العقود: أربع `2R` بقيم `45k/50k/50k/70k`، خمس `4R` بقيم
  `70k/73.5k/100k/100k/100k`، وثلاث `6R` بقيمة `140k` لكل عقد.
- opening installment receivable لجميع العقود `320,000`، ودفعات يوليو
  `142,000` موزعة bank/cash مع partial/overdue/cancelled scenario.
- maintenance receipts يوليو `10,000` وفق جدول rule snapshots، ولا تخلطها
  بإيراد بيع العقد. إجمالي Timeshare cash-in في الشهر `152,000`.
- القيم cashflow targets؛ recognition كإيراد/التزام يتبع السياسة التي تثبتها
  خدمات Timeshare ولا يُفرض بأن كل تحصيل إيراد فوري.

### 10.9 مصروفات يوليو التشغيلية غير المخزون والرواتب

| البند | القيمة |
|---|---:|
| كهرباء | 85,000 |
| مياه | 18,000 |
| إنترنت واتصالات | 7,500 |
| أمن خارجي | 30,000 |
| Cleaning/Laundry خارجي | 16,000 |
| صيانة وخدمات فنية | 24,000 |
| تسويق | 20,000 |
| مخلفات ومكافحة آفات | 8,500 |
| Bank/Card fees | 9,500 |
| تأمينات/Prepaids amortization | 10,000 |
| **الإجمالي** | **228,500** |

أنشئ فواتير موردين، accruals ومدفوعات موزعة خلال الشهر بدل قيد واحد. أضف
فاتورة واردة متأخرة في أغسطس تخص يوليو لتثبت accrual/reversal، ومصروفًا مدفوعًا
مقدمًا لا يُحمّل كاملًا على يوليو.

### 10.10 مظروف Owner Dashboard المتوقع

هذه أرقام تحقق من الـmanifest وليست KPI مخزنة يدويًا:

- Physical occupancy: `44.93%`، وroom base revenue `550,000`.
- Restaurant + Cafe base sales قبل refunds/discounts: `285,000`.
- Beach base sales: `132,000`.
- Rent accrual `138,000` + penalty `360`، وtenant AR closing `15,000`.
- Timeshare cash-in `152,000` مع فصل receipts عن recognized revenue.
- Payroll basic `181,000`، gross قبل الاستقطاعات `193,600`.
- Inventory opening/purchases/consumption/closing:
  `420,000 + 160,000 - 185,000 = 395,000`.
- July depreciation `83,226.19`، والمصروفات التشغيلية في §10.9 `228,500`.

يعرض الـOwner القيم مع مقارنة أسبوعية ومصادر drill-down وbadge واضح
`Synthetic Trial Data · July 2026`؛ ممنوع إظهارها كأرقام فعلية أو إخفاء أصلها.

## 11. الحزمة GL-01 — دليل الحسابات ودفتر الأستاذ وإقفال الشهر

### 11.1 توسيع دليل الحسابات

الدليل الحالي لا يكفي لرصيد افتتاحي وأصول وتسويات كاملة. أضف على الأقل بعد
مراجعة المحاسب:

- Equity parent `3000`، رأس مال/Opening Balance Equity.
- Card وOnline/Paymob clearing منفصلين عن Cash.
- Fixed assets cost accounts حسب الفئة، ومجمعات إهلاك مقابلة.
- VAT output/service charge payable إذا الأسعار غير شاملة أو النظام يفصلها.
- Accrued expenses/customer advances إن استخدمت.
- مصروفات كهرباء/مياه/إنترنت/صيانة/نظافة/Laundry/Marketing/Bank fees.
- cost centers: `LEASE`, `MAINT`, `ADMIN` بالإضافة إلى الموجودين.

لا تستخدم حساب Equity كـplug غير موثق في كل تشغيل. قيد الافتتاح واحد مؤرخ
2026-06-30 ومرفق بmanifest يبين كل رصيد ومصدره؛ قيم التشغيل القانوني الحقيقي
تأتي من المحاسب، أما fixture الـTrial فيحسبها ويطبعها قبل apply.

الأكواد المقترحة غير المتعارضة بعد discovery: `1120 Card Clearing`,
`1130 Online Clearing`, `1170 Timeshare AR`, `1210 Prepaids`, `1500 Land`,
`1510 Buildings`, `1515 Pool/Landscape`, `1520 Equipment`, `1530 Furniture`,
`1540 IT`, `1590+ Accumulated Depreciation`, `2160 VAT Payable`,
`2165 Service Charge Payable`,
`2170 Guest Advances`, `2180 Accrued Expenses`, `2310 Timeshare Contract
Liability`, `3000 Equity`, `3100 Capital`, `3200 Retained Earnings`. افشل
migration/seed لو code موجود بمعنى آخر؛ لا تعيد تسميته بصمت.

### 11.2 FIN-TAX-01 — إصلاح فصل VAT والخدمة عن الإيراد

الفحص كشف أن المسارات الحالية في `dining/services.py` و`beach/services.py`
ترحّل في حالات direct/folio/credit **الإجمالي شامل VAT/service كله** إلى حساب
الإيراد؛ لذلك الربح وVAT payable غير صحيحين. كذلك بعض `post_simple_revenue_journal`
وNight Audit تبتلع فشل القيد وتكمل العملية. ممنوع seed قبل إصلاح ذلك.

أنشئ posting primitive ذريًا وstrict مثل `post_taxed_sale_journal` ينتج:

```text
Dr Cash/Bank/Card Clearing/Wallet Clearing/Folio AR = gross collected/owed
    Cr Net Revenue                                      = base - discount
    Cr VAT Payable 2160                                = vat_amount
    Cr Service Charge Payable 2165                     = service_charge
```

- Cash=`1100`، Bank=`1110`، Card Clearing=`1120`، Wallet/Online=`1130`،
  Room Folio=`1150`. لا mapping للكارت إلى البنك أو الصندوق مباشرة.
- يدعم splits حسب outlet/cost center مع توزيع rounding على آخر line، ويحفظ
  tax profile version وbasis في source snapshot.
- Dining يرحّل عند settlement، Beach عند البيع/check-in، والغرف يوميًا في
  Night Audit: base room revenue + VAT + service إلى Folio AR؛ checkout يحصّل
  AR فقط ولا يعيد تسجيل الإيراد.
- discount يقلل الأساس وفق policy، والvoid/refund يعكس نفس سطور الأصل ونسبها
  لا `Dr Revenue` بإجمالي gross.
- rent يستخدم tax code `RENTAL_REVIEW` بلا VAT في Trial، وTimeshare يتبع
  recognition policy الخاصة به؛ ممنوع تمريرهما آليًا على tax profile الغرف.
- كل posting strict، يحترم accounting-period lock، لا يعمل commit داخليًا،
  وله unique source/idempotency key. فشل القيد يفشل العملية المالية كلها.
- اختبر direct/folio/credit/split tender/refund/void/card settlement وNight
  Audit retry، ثم طابق مجموع `2160/2165` مع tax/service detail reports.

### 11.3 قيد الافتتاح الصناعي في 2026-06-30

| الحساب | مدين | دائن |
|---|---:|---:|
| Cash + drawers `1100` | 150,000.00 | 0 |
| Bank `1110` | 950,000.00 | 0 |
| Guest folio AR `1150` | 85,000.00 | 0 |
| Timeshare installment AR `1170` | 320,000.00 | 0 |
| Inventory `1200` | 420,000.00 | 0 |
| Prepaids `1210` | 75,000.00 | 0 |
| Fixed assets gross `1500–1540` | 19,670,000.00 | 0 |
| Accumulated depreciation `1590+` | 0 | 2,731,178.57 |
| Supplier AP `2200` | 0 | 230,000.00 |
| VAT payable `2160` | 0 | 95,000.00 |
| Guest advances `2170` | 0 | 140,000.00 |
| Tenant deposits `2150` | 0 | 276,000.00 |
| Timeshare contract/maintenance liability `2310` | 0 | 360,000.00 |
| Accrued utilities `2180` | 0 | 45,000.00 |
| Capital `3100` | 0 | 17,500,000.00 |
| Retained earnings `3200` | 0 | 292,821.43 |
| **الإجمالي** | **21,670,000.00** | **21,670,000.00** |

صافي الأصول `18,938,821.43` = التزامات `1,146,000.00` + حقوق ملكية
`17,792,821.43`. خزّن source breakdown للأصول والمخزون والذمم؛ لا يكفي وصف
`Opening balance` عام. هذا القيد صناعي للـTrial، وليس إقرارًا بملكية أو تقييم
حقيقي للمنتجع.

### 11.4 ترتيب يوليو المحاسبي

1. قيد افتتاح 2026-06-30.
2. عمليات يوليو من المصادر التشغيلية.
3. accrual الإيجارات والموردين والرواتب والمرافق.
4. تسويات cash/card/bank وtenant receivables وguest folios.
5. Inventory valuation وCOGS reconciliation.
6. إهلاك يوليو من Asset service.
7. مراجعة trial balance/P&L/balance sheet/cost centers/cash flow.
8. الفترة تظل open حتى اعتماد Mohamed/المحاسب؛ الإغلاق خطوة منفصلة.

### 11.5 مطابقات يجب أن تساوي صفر فرق

- مجموع debit = مجموع credit لكل قيد وللفترة.
- Room revenue ledger = Night Audit room revenue بعد استبعاد/شرح الفروق.
- Dining/Beach revenue = settlements ناقص refunds/void reversals.
- VAT payable = مجموع tax snapshots ناقص VAT reversals، وService payable =
  مجموع service snapshots ناقص reversals؛ لا يدخل أي منهما صافي الإيراد.
- Cash account = opening cash + cash receipts ± cash movements - safe drops.
- Card clearing = card payments - bank settlements.
- Folio receivable = charges - checkout settlements.
- Tenant AR = accruals + penalties - receipts.
- Timeshare cash/AR movement = receipts/installments ledger؛ أما recognized
  contract/maintenance revenue وcontract liability movement فيطابقان policy
  snapshots ولا يُفترض أن كل دفعة إيراد فوري.
- Inventory GL = valuation، وCOGS = recipe/issue costs.
- Asset accumulated depreciation = مجموع AssetDepreciationEntry.
- Payroll expense/liabilities = PayrollRun lines والجورنال.

أي فرق يظهر كفشل importer/validation، لا warning مطبوع ثم نجاح.

## 12. ترتيب التنفيذ المقترح

| الترتيب | الحزمة | شرط البدء | شرط الإغلاق |
|---:|---|---|---|
| 0 | Discovery/worktree freeze | هذا الملف | diff map + base واضح |
| 1 | UX-API-01 | لا يوجد | tests + Playwright + صفر 4xx غير متوقع |
| 2 | GL accounts + FIN-TAX-01 | discovery + profile §3 | strict split postings + tests |
| 3 | ROOM-PRICE-01 backend | الأزواج + FIN-TAX | price importer + bundle/PMS tests |
| 4 | HUB-BOOK-01 + Marketing | Backend pricing | public quote→Hub→PMS E2E |
| 5 | TIMESHARE-01R | مراجعة diff والخطة | migrations/rules/profile/tests |
| 6 | Leasing/Assets/Payroll/Inventory GL | قيم §10–11 | source postings + reconciliations |
| 7 | HIST-01 + RESET-01 | كل ما سبق | deterministic dry-run + restore test |
| 8 | Local apply | Local backup + dry-run | validation report كامل |
| 9 | Local UAT | بيانات Local مطبقة | role/RTL/mobile/finance sign-off |
| 10 | VPS Trial apply | Local أخضر + VPS restore drill | backup+apply+validation evidence |
| 11 | VPS UAT | VPS dataset مطبق | Owner/roles/mobile/finance sign-off |

لا تنفذ المراحل كلها في commit واحد. كل migration أو تغيير عقد API أو importer
له commit ومراجعة منفصلان.

## 13. الملفات المتوقعة — تقدير بعد discovery

### Resort OS

- `backend/app/modules/pms/{models,schemas,services,crud,api/router}.py`
- `backend/app/modules/hub/{models,schemas,services,crud,api/router}.py`
- `backend/app/modules/timeshare/*`
- `backend/app/modules/leasing/*`
- `backend/app/modules/finance/*`
- `backend/app/resort_os/timezone_utils.py` أو clock module جديد.
- `backend/app/approved_room_pricing.py`.
- `backend/app/operational_history_seed.py` وملفات manifest/factories صغيرة.
- manifest versioned ثابت مثل `backend/app/scenarios/july_2026_v1.{json,yaml}`
  بلا secrets أو PII، مع schema validator.
- `scripts/resort-data` وطبقة backup/fingerprint/reset/rebuild من §9.4.
- Alembic migrations مراجعة يدويًا وبـsingle head.
- اختبارات API/domain/concurrency/importer/reconciliation/reset/restore.
- ملفات Frontend المذكورة في UX-API-01 وPlaywright config/tests.

### Marketing website

- `src/apps/public/Rooms.vue`.
- `src/config/publicTruth.ts` وconfig/API client مناسب.
- `src/composables/booking/usePageBooking.ts` أو composable خاص بالحجز الحقيقي.
- i18n locales الأربعة واختبارات parity/public truth.
- اختبارات build وE2E للحجز والسعر والتجاوب.

## 14. معايير القبول النهائية

1. العروض الثلاثة وأسعارها تظهر متطابقة في DB/API/Staff/Website/quote/PMS؛
   Family Compound يحجز وحدتين فعليتين ولا يظهر كغرفة واحدة مزيفة.
2. لا يوجد Booking خارجي confirmed بلا PMS booking وغرفة محجوزة.
3. لا 422 users، لا 405 contact، ولا قوائم/أصفار صامتة عند فشل API.
4. Reception “وصول اليوم” يساوي استعلام backend الصحيح حتى مع أكثر من 100.
5. مستخدم 101/500 ومنتج 101 قابلان للبحث والاستخدام.
6. الروابط حسب role/capability لا تقود إلى HR 404 أو Timeshare 403.
7. كل viewport في §6.7 بلا document overflow أو controls مقطوعة.
8. إعادة تشغيل room pricing/history/Timeshare rules لا تكرر صفًا أو قيدًا.
9. July dataset يطابق counts/scenarios في §10 ويغطي حالات النجاح والفشل.
10. كل مطابقات §11.5 بصفر فرق وTrial Balance متزن، ولا VAT/service داخل صافي
    الإيراد.
11. لا outbound integrations ولا PII حقيقية ولا secrets في diff/logs.
12. Alembic head واحد، upgrade/downgrade أو rollback موثق، والاختبارات كاملة.
13. backup→reset/rebuild→restore مُثبت على قاعدة مؤقتة، وtarget mismatch يفشل.

## 15. خطة التحقق

Claude يسجل الأوامر والنتائج الفعلية، ولا يكتب “passed” من الذاكرة:

```bash
bash scripts/agent-check.sh
pnpm --filter el-kheima test:frontend
pnpm run type-check:all
pnpm run build:all
cd backend
.venv/bin/pytest tests/ -q
.venv/bin/alembic heads
cd ..
git diff --check
```

استخدم أوامر المشروع الصحيحة إذا اختلفت paths بعد discovery. أضف:

- Targeted tests لكل حزمة قبل full suite.
- Concurrency tests للحجز/التأكيد/التحصيل/الوردية/idempotency.
- Import dry-run مرتين، apply مرة، apply ثانية no-op، ثم validate-only.
- SQL/report snapshots لـcounts والمبالغ والمطابقات دون PII.
- Playwright على اللغتين والمقاسات.
- Marketing: `npm test` إن وجد، `npm run build` و`check-public-truth`.

## 16. ما هو خارج النطاق أو ممنوع

- إرسال ETA e-invoices حقيقية أو Paymob charges أو WhatsApp/SMS/Email.
- نسخ أسماء/هواتف/عقود Excel الحقيقية إلى Git أو demo.
- اختلاق سعر بيع Timeshare جديد من القيم التاريخية.
- اختلاق ملكية معدات المستأجرين للمنتجع.
- إغلاق يوليو محاسبيًا أو التطبيق خارج Local/VPS Trial المعتمدين.
- توسيع `app.seed` أو إزالة حمايات `production_demo_seed`.
- إصلاح أخطاء الواجهة بإخفاء Console أو catch صامت.
- إضافة `/finance/shift_report` قبل تحديد caller الحقيقي.

## 17. تسليم Claude المطلوب

لكل حزمة:

- ملخص diff والملفات.
- migrations وتأثير existing data والرجوع.
- اختبارات بالأوامر والأعداد.
- sample dry-run JSON بلا PII.
- reconciliation report للفترة.
- Screenshots responsive عربية/إنجليزية.
- مخاطر متبقية وقرارات المالك التي استُخدمت.
- تقريران منفصلان لـLocal وVPS يتضمنان DB fingerprint ونسخة dataset دون secrets.
- لا يعلن المهمة مكتملة قبل إثبات reset/restore وOwner dashboard على VPS.

## 18. سجل قرارات Mohamed — محسوم في 2026-08-10

1. التطبيق على Local ثم VPS الحالي، والـVPS تحت التجربة وعلى مسؤولية Mohamed.
2. يلزم توفير تصفير وإعادة بداية نظيفة مستقبلًا؛ تنفذها RESET-01 بحماياتها.
3. عرض 6 أفراد = Chalet + Family Studio، ونستخدم الأزواج ذات الرقم نفسه في §3.
4. الأسعار لليلة، غير شاملة الضريبة والخدمة، ولا يوجد إفطار.
5. القيم المالية صناعية واقعية يحددها الموجز؛ اعتمدت قيم §§10–11.
6. يستخدم Excel كمصدر أنماط وقيم فقط؛ لا حاجة إلى PII حقيقية لنجاح السيناريو.
7. سياسة «لا أعياد متتالية» للـTrial هي سنة فاصلة بين official-holiday uses
   كما في §8، وليست فجوة 30 يومًا، وتظل rule versioned قابلة للتغيير.

لا توجد إجابة تجارية معلقة تمنع البدء. أي تغيير لاحق في النسب القانونية أو
الأرصدة الحقيقية يصدر كنسخة إعداد/dataset جديدة، ولا يعيد كتابة يوليو بصمت.

## 19. Stop conditions

يتوقف Claude ويطلب قرارًا إذا:

- لا يمكن تمييز تغييرات worktree الحالية من المهمة الجديدة.
- أي زوج Family في §3 غير موجود/نشط في نفس الفرع أو ليس قابلًا للحجز معًا.
- قاعدة Local/VPS تحتوي معاملات يوليو غير معلّمة ستختلط بالـdataset.
- VPS fingerprint غير مطابق، أو backup/restore proof فشل، أو المساحة غير كافية.
- إعداد VAT/service الفعلي يختلف عن profile §3 ولم يُنشأ version/quote واضح.
- تنفيذ قاعدة Timeshare سيغير عقود/زيارات قائمة دون backfill report.
- خدمة خارجية أو PII حقيقية أو إقفال فترة محاسبية أصبح مطلوبًا.
- اتضح أن الـVPS خرج من حالة Trial وبدأ معاملات قانونية حقيقية قبل التطبيق.
