# TIMESHARE-EXTRACTION-01 — فصل موديول الملكية الجزئية إلى مشروع مستقل

**تاريخ الإعداد:** 2026-09-11
**المالك:** Mohamed
**قائد التنفيذ المكلَّف:** Codex (بتكليف Mohamed صراحةً — "عايز كوديكس هو اللي ينفذ المهام دي بذكاء وفهم واحترافية")
**مُعِدّ الخطة:** Claude (بحث معماري + scaffold أولي — راجع §6)
**الحالة:** خطة معتمدة للتنفيذ، لسه محدّش لمس `resort-os` بالحذف — كل الشغل الفعلي لسه في مشروع جديد منفصل بالكامل.

---

## 0. القرار الأصلي (كلام Mohamed حرفيًا، للمرجعية)

> "في قرار بفكر اخده بخصوص التيم شير الملكية الجزئية و اخلي بس الغرف و الحجز
> و الاستقبال زي ما هو انما التيم شير افكر فيه أبليكيشن لوحده مثل الأونر و
> يبقى المشروع خاص بنفسه"

> "لا [العميل الحالي] حاليًا لا يستخدمها. افصلها واعمل خطة تنفيذية عاقلة لأن
> الموضوع حساس، وحيبقي الحجز PMS متناسق مع الموقع والغرف بالدقة، والحسابات
> هتكون فقط عند ريزورت طبيعي كأنه بيحصل [أنه لا يحصّل] العقود الملكية الجزئية
> ولا ياخد المقدم والأقساط والصيانة. ولما حعمل أبليكيشن التيم شير للموبايل
> يكون فيه خواص الزيارات والأسابيع وخدمة العملاء وإلخ."

**استخلاص المتطلبات الثلاثة الصريحة:**
1. `resort-os` يفضل زي ما هو للغرف/الحجز/الاستقبال (PMS) — **بلا أي تغيير سلوكي**.
2. التيم شير يبقى **مشروع مستقل بالكامل** (كود، قاعدة بيانات، نشر) — مش موديول جوه `resort-os`.
3. دفتر حسابات `resort-os` يبقى **كأنه منتجع عادي 100%** — صفر أثر مالي لعقود/أقساط/صيانة الملكية الجزئية فيه.
4. مستقبلًا: تطبيق موبايل مخصوص للتيم شير (زيارات + أسابيع + خدمة عملاء).

---

## 1. علاقة هذه الخطة بـ `TIMESHARE-01_FULL_PLAN_AR.md`

يوجد ملف سابق (`docs/agent-workflow/TIMESHARE-01_FULL_PLAN_AR.md`، 2026-08-09) بيغطي **نضج منطق العمل** داخل موديول التيم شير (قواعد مواسم الذروة، حقول العقد الناقصة، ملف العميل الكامل، إلخ) — جزء كبير من مرحلتَيه 1-2 (`unit_capacity`, `beneficiary_name`, `customer_phone_work/home`, `mailing_address`) **منفَّذ بالفعل فعليًا** (تأكدت بقراءة `timeshare/models.py` الحالي).

**القرار:** الخطة دي (`TIMESHARE-EXTRACTION-01`) هي الأسبق تنفيذًا — فصل المشروع أولاً. أي بند لسه متبقي من `TIMESHARE-01` (قواعد الذروة، ملف العميل، إلخ) **يُنفَّذ داخل المشروع الجديد `timeshare-os` بعد الفصل**، مش داخل `resort-os`. لا تبدأ أي بند من `TIMESHARE-01` جوه `resort-os` من دلوقتي.

---

## 2. حقائق معمارية مؤكَّدة بقراءة الكود الفعلي (مش افتراض)

هذا القسم هو سبب كون الفصل **أسهل وأقل خطورة مما يبدو** — تأكدت من كل نقطة بقراءة الكود مباشرة قبل كتابة الخطة:

### 2.1 الخبر الكويس: التيم شير معزول عن PMS أصلاً
- `TimeshareUnit` (`backend/app/modules/timeshare/models.py:271-280`) **منفصل تمامًا** عن `pms.Room` — قرار معماري متعمد موثّق في الكود نفسه بتاريخ 2026-07-04 ("بعد سؤال صاحب المنتجع مباشرة... لا تُوحَّد مع room_types/rooms الفندق").
- `timeshare._services.visits.create_visit` **لا يحجز غرفة PMS ولا يرحّل إيراد غرف** — التعليق في `models.py:255-259` صريح: "create_visit عمرها ما كانت بترحّل إيراد غرف أصلًا (بتخصّص وحدة ملكية جزئية بس، مش حجز PMS)".
- `TimeshareVisit.booking_id` (FK اختياري لـ `bookings.id`) موجود بس **للربط المرجعي الاختياري فقط** (مثلاً لو المالك حجز ليالي إضافية مدفوعة عبر PMS العادي) — مش مسار إلزامي، ومفيش أي كود بيبني عليه اعتماد حقيقي.

**الأثر العملي:** المتطلب الأول لمحمد ("PMS يفضل متزامن مع الغرف بالدقة") **متحقق أصلاً من قبل حتى ما نبدأ** — مفيش خطر نكسره أثناء الفصل لأنه أصلاً مفيش ترابط حقيقي نقطعه.

### 2.2 نقطة الترابط الحقيقية الوحيدة: الترحيل المالي
التيم شير بيرحّل فعليًا 3 قيود محاسبية في دفتر يومية `resort-os` (`finance.JournalEntry`/`Account`) عبر `finance._services.posting.post_simple_revenue_journal`:

| الملف | السطر | العملية | حساب مدين | حساب دائن |
|---|---|---|---|---|
| `timeshare/_services/contracts.py` | 138-148 | مقدم العقد | نقدية/بنك حسب طريقة الدفع | **4600** (إيراد بيع ملكية جزئية) |
| `timeshare/_services/contracts.py` | 306-313 | استرداد | **4600** | نقدية/بنك حسب طريقة الاسترداد |
| `timeshare/_services/installments.py` | 175-186 | تحصيل قسط | نقدية/بنك | **4600** |
| `timeshare/_services/maintenance.py` | 118-129 | تحصيل صيانة | نقدية/بنك | **4650** (إيراد صيانة، منفصل عمدًا عن 4600) |

هذه هي **النقطة الوحيدة** اللي لازم تتقطع فعليًا عشان يتحقق متطلب محمد التالت ("الحسابات زي ريزورت عادي"). كل حاجة تانية (تصنيف CRM، مراكز التكلفة، مراجعات الضيوف) روابط اختيارية/نصّية سهلة الفك — راجع §2.3.

### 2.3 روابط تانية (اختيارية، سهلة الفك — للتوثيق بس)
- `crm.models`/`crm.schemas`: قيمة نصية `"timeshare"` جوه `product_type`/`interest` enum — تصنيف بيانات بس، مفيش FK حقيقي.
- `finance._services.cost_centers`: التيم شير واحد من عدة مستهلكين لآلية وسم `cost_center_id` العامة — مجرد استدعاء بيتوقف.
- `analytics.models.GuestReview.timeshare_visit_id`: FK اختياري (nullable، mutually-exclusive مع `booking_id`) لربط مراجعة رضا بزيارة تيم شير — نظام استبيان مشترك.
- `core.deps`: أدوار `timeshare_admin` (level=55) و`timeshare_agent` (level=25) **معزولة بالفعل** عن باقي الأدوار (`get_timeshare_user`/`get_timeshare_admin_user` بمطابقة اسم الدور مباشرة، مش عتبة مستوى؛ `auth/service.py:73` بيستثنيهم صراحة من وراثة الأدوار العادية). هذا العزل الموجود فعليًا هو تقريبًا نفس شكل نظام صلاحيات مستقل — ميزة، مش عيب، للفصل.
- `core.config`: `SURVEY_TOKEN_SECRET` مشترك بين `analytics.services.create_survey_token` و`timeshare.services` — أداة توقيع عامة، سهلة التكرار في المشروع الجديد بمفتاح خاص بيه.
- بوابة المالك (`timeshare/_services/owner_portal.py`): OTP عبر واتساب بتستخدم `core.kernel.whatsapp.send_whatsapp_message` + `core.cache.rate_limit` — أدوات بنية تحتية عامة (`core/kernel/`)، مش خاصة بـ `resort-os`.

---

## 3. البنية المستهدفة لمشروع `timeshare-os`

مشروع مستقل بالكامل، بنفس قناعات `resort-os` المعمارية (نفس الدستور: `crud→services→router`، Pydantic v2، SQLAlchemy 2.0، Vue 3 + Pinia لاحقًا):

```
~/projects/timeshare-os/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── kernel/          ← منقول بالكامل من resort-os (auth/security/db/cache/
│   │   │   │                       whatsapp/errors/health/logging/middleware/sentry)
│   │   │   ├── config.py, database.py, deps.py, encryption.py, rate_limit.py
│   │   ├── modules/
│   │   │   ├── core/             ← Branch/User-adjacent فقط (models.py منقول، بدون
│   │   │   │                        CRM/HR/Inventory وغيره من resort-os)
│   │   │   ├── finance/          ← جديد، مصغّر: Account/JournalEntry/JournalLine/
│   │   │   │                        CostCenter + post_simple_revenue_journal فقط —
│   │   │   │                        دفتر حسابات خاص بمشروع التيم شير وحده
│   │   │   └── timeshare/        ← منقول بالكامل (models/schemas/crud/services/api)
│   │   ├── main.py, celery_app.py, seed.py
│   │   └── resort_os/            ← أي pure-domain helpers مشتركة (timezone_utils، إلخ)
│   ├── alembic/
│   └── requirements.txt
├── frontend/
│   └── apps/timeshare-admin/     ← لوحة موظفي التيم شير (منقولة من TimeshareView.vue
│                                     تبويباتها + TimeshareUnitPicker.vue)
│   └── (بوابة المالك العامة + لاحقًا: تطبيق الموبايل)
```

**قرارات تصميم موثّقة:**
- `core/kernel/` يُنسَخ لا يُشارَك — نفس فلسفة استقلال `resort-os` عن `wego_core` (راجع `CLAUDE.md §14`): كل مشروع يملك بنيته التحتية، صفر اعتماد بيني وقت التشغيل.
- دفتر حسابات مستقل تمامًا (Account/JournalEntry/JournalLine خاصين بـ `timeshare-os`) — **مش اتصال بقاعدة بيانات `resort-os` من بعيد**. هذا هو التنفيذ الحرفي لمتطلب محمد الثالث.
- قاعدة بيانات Postgres منفصلة تمامًا (اسم جديد، مش schema جوه نفس قاعدة `resort-os`).

---

## 4. الحالة الحالية للـ scaffold (منجز بالفعل — نقطة بداية Codex)

تم فعليًا (commit `9eb0e46` في `~/projects/timeshare-os`، git مستقل، **لم يُلمس أي شيء في `resort-os`**):
- إنشاء المستودع + `.gitignore`
- نسخ `app/core/kernel/` كامل من `resort-os`
- نسخ `app/modules/timeshare/` كامل (models/schemas/crud/services/_services/api)
- نسخ `app/modules/core/models.py` فقط (Branch وما يتبعه — بدون crud/services/schemas الخاصة بـ resort-os)
- نسخ `app/resort_os/` (pure helpers، منها `timezone_utils` و`image_processing` — الأخير غير مستخدم من التيم شير، يمكن حذفه)

**لم يتم بعد (أول مهام Codex):** ربط كل ده ببعضه (imports مكسورة حاليًا)، بناء دفتر الحسابات المصغّر، قاعدة بيانات فعلية، أول migration، تشغيل حقيقي للسيرفر.

---

## 5. خطة التنفيذ بالمراحل

كل مرحلة **مستقلة وقابلة للتراجع** ومنتهية ببوابة تحقق واضحة. لا تنتقل لمرحلة قبل ما اللي قبلها يعدي بواباته.

### المرحلة 1 — إصلاح الاستيرادات المكسورة + تشغيل أولي
**الهدف:** `timeshare-os/backend` يشتغل كسيرفر FastAPI فاضي (بدون finance حقيقي بعد) ضد قاعدة بيانات جديدة.

- تنقية `app/core/deps.py` المنسوخ: يفضل بس الأدوار ذات الصلة (`timeshare_admin`, `timeshare_agent`, `super_admin` كحد أدنى للـ bootstrap) — احذف مراجع الأدوار التانية (`cashier`, `waiter`, إلخ) من `ROLE_LEVELS`.
- `app/main.py` مصغّر: `build_auth_router()` + `build_health_router()` + `timeshare.api.router` بس (بدون الحلقة اللي بتحاول تسجّل 16 موديول).
- `app/modules/core/`: أضف `schemas.py` (بس `PaginatedResponse` وما يحتاجه `timeshare` فعليًا — راجع `timeshare/api/router.py:91`) و`services.py` مصغّر (بس الدوال اللي `timeshare/api/router.py` بينادها فعليًا من `core_services`، مثل `provision_timeshare_agent`-adjacent).
- قاعدة بيانات Postgres جديدة (`timeshare_os`، docker أو container منفصل) + `alembic init` + migration أولى (autogenerate من الموديلات المنقولة).
- **بوابة التحقق:** `uvicorn app.main:app` يشتغل، `/health` يرجع 200، `alembic upgrade head` ينجح بدون أخطاء.

### المرحلة 2 — دفتر الحسابات المصغّر الخاص بالمشروع
**الهدف:** التيم شير يرحّل قيوده في حساباته هو، صفر اتصال بـ `resort-os`.

- `app/modules/finance/models.py` جديد: `Account`, `JournalEntry`, `JournalLine`, `CostCenter` فقط (منقولة/مبسّطة من `resort-os/backend/app/modules/finance/models.py:314-458` و`447-458`) — **بدون** `Payment`/`CashierShift`/`Folio`/`Check`/`BankAccount`/`AccountingPeriod` وغيرها (مش محتاجينهم).
- `app/modules/finance/_services/posting.py`: انسخ `post_simple_revenue_journal` (من `resort-os/backend/app/modules/finance/_services/posting.py:67` فصاعدًا) + `_exceptions.FinancialConfigurationError` + الجزء المحتاج من `cost_centers.py` (`ensure_default_cost_centers`, `DEFAULT_COST_CENTERS` — أو تبسيطه لمركز تكلفة واحد `TS` بس) + `exchange_rates.convert_to_egp` (أو تبسيطه لو كل عمليات التيم شير بالجنيه فقط — قرار يحتاج تأكيد من محمد، راجع §7).
- Seed أولي لدليل حسابات صغير: 4600، 4650، + حسابات نقدية/بنك حسب طرق الدفع الفعلية المستخدمة في `contracts.py`/`installments.py`/`maintenance.py` (`_PAYMENT_METHOD_DEBIT_ACCOUNT` map — انسخها كما هي).
- **بوابة التحقق:** استدعاء `post_simple_revenue_journal` حي (من تست أو سكريبت) ينشئ قيد متوازن فعلي في قاعدة بيانات `timeshare-os` الجديدة.

### المرحلة 3 — اختبارات + تحقق شامل
- انقل ملفات التست ذات الصلة بالتيم شير من `resort-os/backend/tests/` (ابحث بـ `grep -rl timeshare tests/`) وعدّلها لتشتغل ضد المشروع الجديد.
- `pytest tests/ -v` أخضر 100% في `timeshare-os`.
- تدفق حي كامل: تسجيل دخول `timeshare_admin` → إنشاء عقد → تحصيل قسط → التأكد من القيد المحاسبي في `timeshare-os`'s DB → لا أي أثر في `resort-os`'s DB.

### المرحلة 4 — الفرونت إند
- انقل `frontend/apps/el-kheima/src/views/admin/TimeshareView.vue` وتبويباتها، `TimeshareUnitPicker.vue`، `views/public/TimeshareOwnerPortalView.vue` إلى تطبيق Vue مستقل جديد جوه `timeshare-os/frontend/`.
- أعد استخدام `@resort-os/ui`/`@resort-os/core` كـ **مرجع نمط بصري بس** (انسخ المكوّنات المحتاجة، متعملش دependency حيّة بين المشروعين — نفس فلسفة استقلال الـ backend).

### المرحلة 5 — إكمال نواقص `TIMESHARE-01` (داخل المشروع الجديد)
- نفّذ الباقي من `TIMESHARE-01_FULL_PLAN_AR.md` (قواعد مواسم الذروة، جدول `timeshare_peak_seasons`، ملف العميل الكامل، إلخ) — **هنا، مش جوه resort-os**.

### المرحلة 6 — القطع النهائي من `resort-os` (آخر خطوة، بعد إثبات المشروع الجديد شغال 100%)
⚠️ **لا تنفّذ هذه المرحلة إلا بعد إثبات حي كامل للمراحل 1-4 وموافقة صريحة من محمد.**
- احذف `backend/app/modules/timeshare/` بالكامل من `resort-os` (models/schemas/crud/services/api).
- احذف `_MODULE_KEYS` entry الخاص بـ `"timeshare"` في `app/main.py`.
- احذف أدوار `timeshare_admin`/`timeshare_agent` من `ROLE_LEVELS` (`core/deps.py`) و`useAuthStore.ts` (الفرونت إند) وأي مدخل `timeshare.*` في `permission_catalog.py`.
- احذف شاشات الفرونت إند (`TimeshareView.vue`, `TimeshareUnitPicker.vue`, `TimeshareOwnerPortalView.vue`) وروابطها من الـ router والـ nav.
- **الجداول نفسها (`timeshare_*`) تُترَك في قاعدة بيانات `resort-os` كأرشيف/safety-net — بلا حذف DROP TABLE** — بنفس القرار المتبع بالظبط مع جداول `restaurant`/`cafe` القديمة (`CLAUDE.md §18`، Batch 6). أضف تعليق تحذيري في `alembic/env.py` بنفس النمط.
- شغّل `scripts/reconcile_dining_vs_legacy.py`-style سكريبت تحقق بسيط (أو يدوي) يتأكد إن آخر نسخة بيانات `timeshare_*` في `resort-os` (لو فيه أي بيانات تجريبية) اتنسخت فعليًا لـ `timeshare-os` قبل القطع، احتياطًا فقط — العميل الحالي مش مستخدم الموديول أصلًا فالمخاطرة نظريًا صفر.
- **بوابة التحقق:** `pytest tests/ -v` في `resort-os` أخضر 100% بعد الحذف (تستات التيم شير هتتشال معاه)، `alembic upgrade head` سليم، `pnpm build` للفرونت إند سليم، تصفّح حي يتأكد إن مفيش أي رابط ميت لشاشات التيم شير المحذوفة.

---

## 6. قواعد إلزامية أثناء التنفيذ (لـ Codex)

- **اتبع نفس دستور `resort-os` بالكامل** (`CLAUDE.md`) في المشروع الجديد — نفس طبقات crud/services/router، نفس قواعد الأموال (`Decimal` لا `float`)، نفس معايير الاختبار.
- **مرحلة 1-5 لا تلمس `resort-os` إطلاقًا** — كل الشغل في `~/projects/timeshare-os` فقط، حتى المرحلة 6.
- كل مرحلة = commit مستقل + بوابة تحقق فعلية (مش افتراض) قبل الانتقال للي بعدها — نفس فلسفة "دفعات صغيرة آمنة" (`CLAUDE.md §7`).
- لو ظهر ترابط حقيقي إضافي متوقّعش موجود جوه أي دالة بتتنقل (مثلاً استيراد من موديول resort-os تاني غير المذكورين في §2)، **وثّقه واسأل قبل ما تخترع حل** — مايتفترضش حل تلقائي لترابط جديد غير موثّق هنا.
- بيانات حقيقية للعملاء (لو ظهرت لاحقًا) = PII، لازم `EncryptedString` بنفس نمط `resort-os` (`customer_national_id` بالفعل مُشفّر في الموديل المنقول — حافظ عليه).

---

## 7. قرارات مفتوحة لمحمد (تأكيد بس، مش عائق للبدء)

الافتراضات التالية موضوعة كـ defaults معقولة ومُنفَّذة جزئيًا بالفعل (المسمى والمكان) — لو عايز تغييرها قول:

1. **اسم/مكان المشروع:** `~/projects/timeshare-os` (تم إنشاؤه بالفعل). لو عايز اسم تجاري مختلف (زي "El Kheima Owners" أو غيره) قوله وهيتغير بسهولة (لسه بداية).
2. **العملة:** هل عمليات التيم شير كلها بالجنيه المصري فقط؟ لو أيوه، دفتر الحسابات المصغّر (المرحلة 2) ممكن يتبسّط بحذف تحويل العملة (`convert_to_egp`) تمامًا بدل نسخه.
3. **تطبيق الموبايل (المرحلة 5+):** ستاك التطبيق — Flutter (زي WegoDivers وWatersportsOS الحاليين في نفس البيئة) ولا حاجة تانية؟

---

## 8. مؤشر النجاح النهائي (Definition of Done للخطة كاملة)

- [ ] `timeshare-os` backend + frontend يشتغلوا مستقلين بالكامل، بقاعدة بياناتهم وحساباتهم الخاصة.
- [ ] `resort-os` بعد المرحلة 6: صفر كود/جدول نشط خاص بالتيم شير، `pytest` أخضر 100%، الحجز/PMS يعمل بلا أي تغيير سلوكي ملحوظ.
- [ ] لا أي قيد محاسبي جديد لعقود/أقساط/صيانة ملكية جزئية يظهر في دفتر يومية `resort-os` من تاريخ القطع فصاعدًا.
- [ ] تطبيق موبايل التيم شير (زيارات/أسابيع/خدمة عملاء) — مرحلة لاحقة منفصلة، بعد ثبات الـ backend الجديد.
