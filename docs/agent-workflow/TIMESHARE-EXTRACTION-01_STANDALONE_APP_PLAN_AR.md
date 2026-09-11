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

## 3. البنية المستهدفة — قرار محمد النهائي (2026-09-11): داخل `wego-platform`، مش مستودع Python جديد

⚠️ **تعديل على القرار الأصلي:** أول نسخة من الخطة دي اقترحت مستودع Python/FastAPI
مستقل جديد (`~/projects/timeshare-os`، راجع §4 القديم تحت) بنفس معمارية `resort-os`
تمامًا. محمد راجع القرار وحدّد الاتجاه الصح صراحةً:

> "خليه يعمل المشروع مجاور شرم تو جو ويستغل خواص الموبايل ويكون مشروع مستقل مثل الباقي"

يعني: **التيم شير منتج جديد داخل `/home/wego/wego-platform`** (مش مستودع منفصل بره
المنظومة دي) — بنفس نمط `Wego Divers`/`Sharm Divers Club` و`Wego Travel Marketplace`/
`Sharm To Go` الموجودين فعلاً هناك، وباستخدام قدرات الموبايل الحقيقية (KMP/Compose
Multiplatform) اللي المنصة دي مبنية عليها أصلاً — مش تطبيق ويب متنكّر كموبايل.

### 3.1 نموذج التركيب في `wego-platform` (من `README.md`/`ENGINEERING_CONSTITUTION.md`)

```
Wego Product (products/<product>/) + Client Configuration (clients/<client-id>/)
                    = Isolated Client Deployment
```

| الطبقة | المسار | الدور |
|---|---|---|
| قدرات مشتركة بين كل المنتجات | `platform/` (kernel/identity/security/events) | Kotlin/Spring، بنية تحتية عامة فقط — بدون منطق عمل صناعي |
| **المنتج الجديد** | `products/timeshare/` (مقترح) | Kotlin/Spring، Modular Monolith (`domain`/`application`/`infrastructure`/`api`)، PostgreSQL+Flyway+jOOQ، `BigDecimal` للأموال، عقد OpenAPI |
| **إعداد عميل الخيمة** | `clients/el-kheima-timeshare/` (مقترح) | `client.manifest.json` بيشاور على `product.id = "wego-timeshare"`، توقيت القاهرة، عملة EGP، `deploymentIsolation: ISOLATED_INSTANCE` — بنفس نمط `clients/sharm-to-go/client.manifest.json` بالظبط |
| واجهة الإدارة (موظفي التيم شير) | `web/apps/el-kheima-timeshare-erp/` (مقترح، Nuxt) | نفس نمط `sharm-to-go-erp` — لوحة الموظفين/العقود/الأقساط |
| **تطبيق موبايل حقيقي لمالكي الملكية الجزئية** | امتداد لـ `mobile/apps/customer` (KMP) + `mobile/apps/customer-android` | زيارات، أسابيع، خدمة عملاء، تسجيل دخول (OTP/بيومتري)، إشعارات push حقيقية — مش نسخة من بوابة الويب الحالية `TimeshareOwnerPortalView.vue`، بناء أصلي يستغل قدرات الجهاز |
| (اختياري) واجهة موبايل لموظفي التيم شير | `mobile/apps/ops` | لو فيه حاجة تستحق تطبيق موبايل للموظفين (مثلاً تأكيد استلام وحدة أثناء الجولة) — قرار لاحق بعد ما النواة تثبت |

### 3.2 قواعد إلزامية من `docs/ENGINEERING_CONSTITUTION.md` (بند 1، 3، 4، 6) — لـ Codex

- منطق التيم شير كله في `products/timeshare/` — **ممنوع** يتحط جوه `platform/` (ده للقدرات العامة بس) أو يتفرّع خصيصى لعميل الخيمة جوه المنتج نفسه (التخصيص بيبقى في `clients/el-kheima-timeshare/` بس، عبر إعداد/نقاط امتداد صريحة، مش فرع كود).
- `domain` layer نضيف من Spring/HTTP/jOOQ generated records — نفس القاعدة المطبّقة في `products/divers`.
- الأموال `BigDecimal`/`NUMERIC` دايمًا — مطابق تمامًا لقاعدة `Decimal` في `resort-os`، نفس المبدأ بلغة تانية.
- Flyway هو مسار الـ migration الوحيد (مش Alembic — ده كان افتراض غلط في النسخة الأولى من الخطة، مبني على افتراض إن المشروع هيكون Python).
- عقد OpenAPI إصدار (versioned) بين الـ backend والعميلين (web + mobile) — مطابق لبند 6 من الدستور.

---

## 4. حالة الـ scaffold — تصحيح المسار

**الـ scaffold القديم في `~/projects/timeshare-os` (commit `9eb0e46`, Python/FastAPI) أصبح
متجاوَزًا (superseded) بقرار محمد في §3 — سيبته موجود كمرجع فقط، لا تُكمل عليه.**
كان فيه: نسخة من `resort-os/backend/app/core/kernel`، موديول `timeshare` كامل، و
`modules/core/models.py` — مفيد كمرجع لمنطق العمل الأصلي (قواعد الأسابيع، حسابات
الصيانة، تدفق OTP بوابة المالك) وقت بناء النسخة الحقيقية جوه `wego-platform`، لكن
مش نقطة بداية تنفيذية بعد النهاردة.

**نقطة البداية الحقيقية لـ Codex الآن:** `/home/wego/wego-platform`، بمراجعة
`docs/ENGINEERING_CONSTITUTION.md`، `docs/architecture/BOUNDARIES.md`، وبنية
`products/divers/` و`clients/sharm-to-go/` كمرجع نمطي مباشر قبل إنشاء أي ملف.

---

## 5. خطة التنفيذ بالمراحل

كل مرحلة **مستقلة وقابلة للتراجع** ومنتهية ببوابة تحقق واضحة. لا تنتقل لمرحلة قبل ما اللي قبلها يعدي بواباته. المراحل هنا موصوفة على مستوى الهدف/الـ DoD — التفاصيل الحرفية (أسماء ملفات jOOQ، إعداد Flyway، إلخ) تتبع قواعد `wego-platform` نفسها زي أي منتج تاني فيه (`products/divers` مرجع مباشر)، مش تفاصيل Python المذكورة في مسودة الخطة الأولى (اتشالت — راجع §4).

### المرحلة 1 — سقالة المنتج الجديد `products/timeshare/`
**الهدف:** موديول Kotlin/Spring فاضي (Modular Monolith، `domain`/`application`/`infrastructure`/`api`) بيتبني وبيمرّ بالـ quality gates الأساسية، ومسجّل في `foundry/catalog/modules.json`.

- أنشئ `products/timeshare/` بنفس بنية `products/divers/` (package `com.wego.timeshare`).
- `platform/kernel/identity` + `platform/kernel/security` للمصادقة/الصلاحيات — **زي أي منتج تاني، مش نسخة جديدة**.
- أنشئ `clients/el-kheima-timeshare/client.manifest.json` (على نمط `clients/sharm-to-go/client.manifest.json` بالظبط: `product.id: "wego-timeshare"`, `timezone: Africa/Cairo`, `currency: EGP`, `deploymentIsolation: ISOLATED_INSTANCE`).
- **بوابة التحقق:** أوامر البناء/الفحص القياسية للمنتج (زي `:products:divers:check` بالظبط بس لـ timeshare) تعدي، وFoundry manifest validation ينجح.

### المرحلة 2 — منطق العمل الأساسي (Domain) — منقول من `resort-os` كمرجع منطقي، مبني من الصفر بـ Kotlin
**الهدف:** ترجمة قواعد العمل الحقيقية الموجودة فعليًا في `resort-os/backend/app/modules/timeshare/` (مش إعادة اختراعها) إلى `domain` layer نضيف.

- العقود، الأقساط، الوحدات (`TimeshareUnit`/`TimeshareUnitPair` — **افصلهم عن أي مفهوم غرفة فندق من الأساس**، مطابقةً لقرار العزل الموجود فعلاً في `resort-os`، راجع §2.1)، الزيارات.
- **دفتر حسابات خاص بالمنتج نفسه**: Account/JournalEntry/JournalLine داخل `products/timeshare/` (أو جدول عام جوه `platform/` لو فيه بالفعل مفهوم محاسبي مشترك بين منتجات `wego-platform` — Codex أدرى ببنية `platform/` الحالية من هذه الخطة؛ المهم: **صفر اتصال بقاعدة بيانات `resort-os`**).
- Flyway migrations لجداول المنتج الجديد.
- **بوابة التحقق:** إنشاء عقد → تحصيل قسط → قيد محاسبي متوازن حقيقي في قاعدة بيانات `timeshare`'s الخاصة بيها — بتست تكامل حقيقي (PostgreSQL فعلي، مش mock)، بنفس روح بند 8 من `ENGINEERING_CONSTITUTION.md`.

### المرحلة 3 — عقد الـ API (OpenAPI) + واجهة الإدارة (Web)
- عقد OpenAPI موثَّق ومُصدَّر (versioned) — بند 6 من الدستور.
- `web/apps/el-kheima-timeshare-erp/` (Nuxt، على نمط `sharm-to-go-erp`): لوحة موظفي التيم شير — عقود/أقساط/وحدات/زيارات، منقولة منطقيًا من `TimeshareView.vue` وتبويباتها الحالية في `resort-os` (مرجع UX بس، مش كود يُنسخ حرفيًا).

### المرحلة 4 — تطبيق الموبايل الحقيقي لمالكي الملكية الجزئية
**الهدف الصريح من محمد:** "يستغل خواص الموبايل" — يعني مش بوابة ويب ملفوفة، تطبيق حقيقي.

- امتداد `mobile/apps/customer` (KMP) بتجربة عميل التيم شير: تسجيل دخول (OTP اللي موجود فعلاً في `resort-os/timeshare/_services/owner_portal.py` كمرجع منطقي، أو بيومتري لو متاح)، عرض الزيارات/الأسابيع المستحقة، طلب زيارة، تذاكر خدمة عملاء، **إشعارات push حقيقية** (تأكيد/رفض الزيارة، رد على تذكرة دعم) — بدائل حقيقية لواتساب OTP الحالي في `resort-os` (اللي كان أفضل بديل متاح وقتها لمنتج مش عنده تطبيق موبايل).
- تأكد من `mobile/apps/customer-android` بيبني (`./gradlew :mobile:apps:customer-android:assembleDebug`) وتجربة iOS بتتحقق على الأقل بالـ klib compile (`compileKotlinIosSimulatorArm64`) زي باقي المنتجات.
- قرار مؤجَّل بعد ما النواة تثبت: هل موظفي التيم شير محتاجين `mobile/apps/ops` كمان، ولا واجهة الويب (المرحلة 3) كافية لهم؟

### المرحلة 5 — إكمال نواقص `TIMESHARE-01` (داخل `products/timeshare/` الجديد)
- نفّذ الباقي من `TIMESHARE-01_FULL_PLAN_AR.md` (قواعد مواسم الذروة، جدول المواسم، ملف العميل الكامل، إلخ) — **هنا، مش جوه resort-os**، وبقواعد `wego-platform` (Flyway/jOOQ) مش الوصف القديم بلغة Alembic/SQLAlchemy الموجود في الملف الأصلي (المنطق التجاري صحيح ومرجعي، التفاصيل التقنية فيه لمشروع resort-os القديم بس).

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

- **اتبع `docs/ENGINEERING_CONSTITUTION.md` و`docs/architecture/BOUNDARIES.md` بالكامل** في `wego-platform` — نفس مستوى الالتزام اللي `resort-os` عنده بـ`CLAUDE.md`.
- **مرحلة 1-5 لا تلمس `resort-os` إطلاقًا** — كل الشغل الفعلي في `wego-platform`، حتى المرحلة 6.
- كل مرحلة = execution packet مستقل (بند 2 من الدستور) + بوابة تحقق فعلية (مش افتراض) قبل الانتقال للي بعدها.
- لو ظهر ترابط حقيقي إضافي متوقّعش موجود جوه أي منطق بيتنقل من `resort-os` كمرجع (مثلاً اعتماد على موديول resort-os تاني غير المذكورين في §2)، **وثّقه واسأل قبل ما تخترع حل**.
- بيانات حقيقية للعملاء (لو ظهرت لاحقًا) = PII، تصنيف وتشفير حسب بند 5 من `ENGINEERING_CONSTITUTION.md` — `customer_national_id` كان مُشفّر (`EncryptedString`) في `resort-os` الأصلي، حافظ على نفس مستوى الحماية.
- مراجعة عدائية مستقلة إلزامية (بند 2) على: المصادقة/الصلاحيات، الترحيل المحاسبي، عزل بيانات العميل (`clients/el-kheima-timeshare` مقابل أي عميل تاني مستقبلي على نفس المنتج) — قبل أي commit.

---

## 7. قرارات مفتوحة لمحمد (تأكيد بس، مش عائق للبدء)

1. **اسم المنتج/العميل:** `products/timeshare` + `clients/el-kheima-timeshare` (مقترح، بنفس نمط `wego-travel-marketplace`/`sharm-to-go`). لو عايز أسماء تجارية مختلفة قولها.
2. **العملة:** هل عمليات التيم شير كلها بالجنيه المصري فقط؟ لو أيوه، منطق تحويل العملة (`convert_to_egp` المرجعي من `resort-os`) ممكن يتحذف تمامًا بدل ما يتنقل.
3. **الموبايل للموظفين:** هل موظفي التيم شير محتاجين تطبيق موبايل خاص بيهم (`mobile/apps/ops`) كمان، ولا واجهة الويب (المرحلة 3) كافية ليهم؟ (سؤال المستخدم النهائي = تطبيق الموبايل اتحدد إنه لمالكي الملكية الجزئية أولاً — راجع §5 المرحلة 4).

---

## 8. مؤشر النجاح النهائي (Definition of Done للخطة كاملة)

- [ ] `products/timeshare` + `clients/el-kheima-timeshare` + web ERP + تطبيق الموبايل يشتغلوا مستقلين بالكامل، بقاعدة بياناتهم وحساباتهم الخاصة، داخل `wego-platform`.
- [ ] `resort-os` بعد المرحلة 6: صفر كود/جدول نشط خاص بالتيم شير، `pytest` أخضر 100%، الحجز/PMS يعمل بلا أي تغيير سلوكي ملحوظ.
- [ ] لا أي قيد محاسبي جديد لعقود/أقساط/صيانة ملكية جزئية يظهر في دفتر يومية `resort-os` من تاريخ القطع فصاعدًا.
- [ ] APK حقيقي لتطبيق الموبايل بيبني (`assembleDebug` على الأقل) ومالك ملكية جزئية يقدر فعليًا يسجّل دخول ويشوف زياراته منه.
- [ ] تطبيق موبايل التيم شير (زيارات/أسابيع/خدمة عملاء) — مرحلة لاحقة منفصلة، بعد ثبات الـ backend الجديد.
