# حالة المشروع — El Kheima Beach Resort OS

> **آخر تحديث حقيقي:** 2026-07-19 — كل رقم في الملف ده اتأكد منه فعليًا (تشغيل تست، تجربة live)،
> مش افتراض ولا خطة. لو لقيت رقم يبان قديم، قول لـ Claude "الملف مش محدّث" وهو يراجعه من الكود
> مباشرة قبل ما يصدّقه.
>
> **الملف القديم `PROMPT_FOR_CLAUDE.md` اتمسح** — كان فيه توصيات بقت غلط بعد ما اتراجعنا عنها. الملف
> ده هيتحدّث كل ما يحصل شغل حقيقي، وبيفصل بوضوح بين "اتأكدنا منه دلوقتي" و"خطة لسه ما بدأناش فيها".

---

## 📊 نظرة سريعة (30 ثانية)

| | |
|---|---|
| **الاسم التجاري** | El Kheima Beach |
| **اسم الباكدج** | resort-os |
| **الاختبارات** | **1,992 backend ناجح، 20 skipped، صفر فشل** ✅ + **60/60 frontend** + **5/5 Dining** + **2/2 Super Admin** + **3/3 Step-Up** + **4/4 Refresh-Family** concurrency حقيقية على PostgreSQL (2026-07-19؛ Gate 3 مُعتمَدة بعد مراجعة مستقلة) |
| **الـ Coverage** | **95%+ إجمالي** (دايننج/شاطئ/حسابات/موارد بشرية اتدفعت لـ 91-100%) |
| **الموديولات** | **13 موديول** — `dining` حلّ محل `restaurant`+`cafe` نهائيًا (cutover كامل D-05→D-08، 2026-07-13) |
| **الـ Git** | `github.com/wego2388/Resort-OS` |
| **الاستضافة** | هيكل VPS موجود (Compose + Dockerfiles + DEPLOYMENT.md)، لكنه **غير مُثبت على سيرفر حقيقي** وتهيئة reference data للإنتاج ما زالت بوابة مفتوحة |
| **الاعتماديات** | **مستقل 100%** — مفيش أي اعتماد على `wego_core` أو أي باكدج خارجي مشترك (اتأكد منه live 2026-07-03) |
| **النسخ الاحتياطي** | `scripts/backup_db.sh` + `restore_db.sh` + systemd timer، اتجرّب backup→restore→مقارنة بيانات فعليًا |
| **التشغيل** | `scripts/start.sh`/`stop.sh`/`status.sh`/`restart.sh`/`logs.sh` — الحسابات التجريبية الـ12 مسموحة في development/test فقط |
| **الدستور الهندسي** | `CLAUDE.md` بقى فيه دستور CTO كامل (أولويات 70% جودة/20% تنضيج/10% ميزات جديدة) — راجعه أول أي جلسة |

---

## 🟦 Gate 4 — سلامة الدفع والوردية والطلب في Dining (2026-07-20، منفَّذة بالكامل، بانتظار مراجعة مستقلة)

**الحالة:** الثلاث شرائح + **تصحيحات جولة مراجعة Codex المستقلة الأولى (10
ملاحظات: 5 High + 5 Medium)** + **M5(a) step-up المالي** كلهم منفَّذين على
الفرع `gate-4-dining-payment-shift-order-integrity`. **بلا commit/push —
بانتظار مراجعة مستقلة (ليست اعتمادًا).** Codex مش متاح للمراجعة حاليًا (قرار
محمد 2026-07-20)؛ M5(a) نُفِّذ مباشرة من غير وكيل، وروجع بنفس الدقة. **مفيش بند
مؤجَّل متبقٍّ.** التقرير الكامل + قسمي جولتي المراجعة:
`docs/audits/gate-4-dining-payment-shift-order-integrity.md`.

**جولة مراجعة Codex الأولى (2026-07-20) — مختصر:** High 1 (تسلسل الدفع/حركة
الكاش مع إغلاق الوردية عبر NOWAIT+409 على صف الوردية)، High 2 (كل mutation على
الطلب بقى يقفل الطلب زي settle/refund)، High 3 (split refund بيعكس الكاش والغرفة
بالتناسب)، High 4 (المرتجع fail-closed + عكس على حساب الطريقة الأصلي)، High 5
(branch isolation على refund/void/transfer/discount/merge/waiter + shift PDF +
cash-movements)، M1 (مقارنة Decimal دقيقة)، M2 (تقرير الوردية بيبيّن الغرفة
والمرتجعات كبنود منفصلة + لقطة `tender_breakdown`، migration `d2b4a1c3f7e9`)،
M3 (قفل مدير لوردية غيره محتاج سبب+موافقة+AuditLog)، M4 (تعريف الطاولة النشطة
مطابق للـ index + no-op حقيقي لـ in_kitchen)، M5(b) (`PATCH .../waiter`).

**جولة M5a (2026-07-20، تنفيذ مباشر بلا وكيل):** step-up مالي لـ
`payment_void`/`dining_refund` — إعادة استخدام كاملة لآلية Gate 2B3A/2B3B
(scope builders جديدة، typed intent models، `X-Step-Up-Token`)، مفيش proof
موازٍ. تكرار حقيقي اتصلح أثناء العمل: `_consume_step_up_or_raise` كانت خاصة
جوه `core/api/router.py` بس، بقت مشتركة (`app/modules/core/api/step_up_utils.py`).
الفرونت إند: `DiningOrderDetailModal.vue`'s المرتجع بقى بيستخدم
`StepUpConfirmModal.vue` بدل textarea مباشر. `void_payment` (finance) مفهوش UI
frontend خالص لحد دلوقتي — الحماية backend-only.

- **4A settlement/exactly-once:** جدول `dining_settlements` جديد (تسوية واحدة
  لكل طلب + بوابة idempotency على مستوى الـ DB). `settle_order` primitive واحدة
  لـ paid وsplit. كل tender مباشر بقى له `Payment` منسوب للكاشير/الوردية/
  الطريقة. طرق دفع typed fail-closed (cash→1100، room→1150، card/wallet لازم
  حساب مهيّأ صراحةً وإلا 503). الدفع المباشر يتطلب وردية مفتوحة.
- **4B shift/reconciliation:** partial unique index يمنع فتح مزدوج للوردية؛
  الإغلاق بيقفل الصف؛ الكاش المتوقع بالصيغة الكاملة (حركات يدوية + تصحيح موجّه)؛
  branch isolation على كل endpoints الوردية.
- **4C state/ownership/reversals:** state machine مركزية؛ partial unique index +
  قفل الطاولة (طلب نشط واحد لكل طاولة)؛ حفظ منشئ الطلب ومين أضاف كل صنف؛ المرتجع
  بقى يقفل الطلب ويعمل عكس Payment مرتبط بالـ tender الأصلي.

**التحقق النهائي (بعد جولتي مراجعة Codex + M5a، 2026-07-20):** backend
**2008 passed · 33 skipped · 0 failed** (SQLite)؛ تزامن Postgres حقيقي على
قاعدة معزولة (تُنشأ وتُحذف ذاتيًا، **مش** قاعدة التطوير المشتركة): 18/18
(`test_gate4_concurrency.py` 13 + `test_dining_paid_concurrency.py` 5)؛ دورة
migration `upgrade head → downgrade c9f1a4d7e2b8 → downgrade b8f4d2a19c07 →
upgrade head` على قاعدة معزولة، رأس واحد `d2b4a1c3f7e9` (مفيش migration جديدة
جولة M5a — step-up بيستخدم جدول Gate 2B3A الموجود). frontend: type-check/i18n/
build نظاف، `test:frontend` 60 passed. `git diff --check` نظيف. صفر commit،
صفر push.

**مفيش بند مؤجَّل متبقٍّ** — High 1-5 وM1-M5 (بما فيهم M5a وM5b) كلهم منفَّذين
بإثبات حقيقي.

---

## 🟩 Gate 5 — اكتمال إدارة الموظفين بلغتين — Batch 6: غرف + تدبير منزلي (2026-07-20)

**الحالة:** منفَّذة ومُتحقَّق منها ذاتيًا — نُفِّذت مباشرة من غير وكيل، على فرع
مستقل `gate-5-staff-ux-batch-6-rooms-housekeeping-i18n`. **بلا commit/push
بعد.** شاشتان: `RoomsView.vue` (خريطة الغرف الحية — WebSocket لحظي، تفاصيل
غرفة، Night Audit) و`HousekeepingView.vue` (مهام التدبير المنزلي — تعيين
موظف، تدفق الحالة متسخة→تنظيف→فحص→جاهزة). الاتنين بقوا `STRICT_FILES`.

**تنظيف حقيقي اتكشف أثناء الترجمة:** `dir="rtl"` ثابت في الشاشتين، و`ar-EG`
locale call في `RoomsView.vue`. `HousekeepingView.vue` فيها كمان مخالفة
اتجاه فيزيائي معملهاش فاحص `validate:i18n` الصارم (بره نمط regex الحالي):
`ml-4` على حاوية النص و`border-r-4` (حد أولوية المهمة) — الاتنين ثابتين
فيزيائيًا مش منطقيين، اتصلحوا لـ`me-4`/`border-e-4`. متغيّر حلقة اسمه `t`
(`tasks.value.filter(t => ...)` مرتين) كان بيغطّي دالة الترجمة — اتغيّر
لـ`hk`.

**مفاتيح جديدة:** `backoffice.rooms.*` (36 مفتاح) + `backoffice.housekeeping.*`
(29 مفتاح) — استُخدمت جميعها، صفر ناقص، صفر زيادة.

**التحقق:** `validate:i18n` أخضر (3180 مفتاح ar/en متطابق، صفر ناقص، صفر
مخالفة اتجاه فيزيائي)، `type-check:all` (el-kheima + public) نظيف،
`test:frontend` 60/60 (صفر رجوع)، `build:all` نظيف. `git diff --check` نظيف.

**الباقي (~35 شاشة admin/ops/portal):** لسه مؤجَّل لدفعات لاحقة — التالية
حسب الخطة: إدارة الشاطئ (Batch 7).

---

## 🧭 قرارات معتمدة قبل Public Phase 0 — حالة التنفيذ موضحة تحت كل Gate

في 2026-07-17 اعتمد Mohamed بوابتين تسبقان نقل الموقع العام:

1. تطبيق الموظفين `frontend/apps/el-kheima` يصبح عربيًا وإنجليزيًا بالكامل،
   باختيار لغة شخصي محفوظ في حساب المستخدم، من غير ربط اللغة بالعملة أو قواعد
   المال. لغات تطبيق `public` تظل مستقلة. العقد في
   `docs/decisions/0002-staff-app-bilingual-mode.md`.
2. `super_admin` يملك التحكم الإداري الكامل الآمن في المستخدمين والصلاحيات
   والإعدادات والجلسات والتدقيق، مع حماية آخر حساب نشط وTOTP/step-up ومنع
   تجاوز سلامة المال أو audit أو الأسرار. العقد في
   `docs/decisions/0003-super-admin-control-plane.md`.

قُرئت كذلك وثيقة `Al Kheima Beach Resort OS Development Plan.pdf` ذات 38 صفحة
كاملة. اعتُمد محتواها كميثاق جودة يُطبّق على مراحل صغيرة، لا كتصريح بـoverhaul
واحد. عند التعارض يظل الاسم المعتمد **El Kheima**، والكود والاختبارات الحالية
هما مصدر حقيقة التنفيذ.

**حالة القرارين نفسيهما:** أمان السوبر أدمن الأساسي **مُعتمَد** عبر Gate 2؛
المخاطر المؤجلة موثقة في تقاريرها. **قرار اللغة بدأ تنفيذه فعليًا واعتمدت
قاعدته في Gate 3 (2026-07-19) — أساس ثنائي اللغة، وليس ترجمة كل الشاشات.**

**Gate 3 — أساس اللغة/الديزاين/الاختبار (مُعتمَدة بعد مراجعة Codex
المستقلة):** `PATCH /auth/me/preferences` (allow-list `ar|en`،
ملكية ذاتية، audit عند التغيير الحقيقي، بلا migration)، `preferred_language`
في `UserRead`. مصدر لغة staff مستقل (`ar/en`، مفتاح namespaced، هجرة لمرة
واحدة)، ومصدر Public مستقل (`ar/en/ru/it`)؛ فحص الحزمتين أثبت أن كل تطبيق
يشغّل runtime الخاص به فقط. اتجاه واحد مركزي من
`<html dir>` (شيل RTL العام)، تنسيق مركزي، **العملة من config لا من اللغة**.
تبنّي Design System في الشيل + Profile/Sessions/Settings (KDS/POS اتنضّف
اتجاههم/تنسيقهم فقط، هجرة النص مؤجَّلة). harness اختبار جديد: `validate:i18n`
(بلا dependency) + Vitest/VTU/jsdom/axe (**60 اختبار frontend**) + **17
اختبار backend**؛ الـbackend الكامل: **1992 passed + 20 skipped**، وليس
"2012 passed". المراجعة أصلحت تداخل runtime بين التطبيقين، عزل لغة شاشة
الدخول عن المستخدم المسجل، توقيت `Africa/Cairo`، ودورة focus للـModal.
لسه ~40 شاشة غير مهاجرة — **التطبيق مش ثنائي اللغة بالكامل بعد**. التفاصيل
الكاملة في `docs/audits/gate-3-ui-i18n-quality-foundation.md`
و`docs/DESIGN_SYSTEM.md` و`docs/FRONTEND_TESTING.md`. لم يتغير أي منطق مالي
أو صلاحيات.

**التالي المعتمد للتنفيذ:** Gate 4 — Dining Payment, Shift & Order Integrity.
عقدها المحدود في `docs/audits/gate-4-execution-brief.md`: settlement وPayment
exactly-once، ربط الكاشير والوردية، split/refund ذريان، reconciliation بقفل
حقيقي، state machine وone-active-table-order. لا QR/Public أو mass rewrite.

---

## 🧭 غرفة قيادة المشروع المؤقتة — منفذة في وضع التطوير (2026-07-17)

تحولت لوحة `wagdy.md` إلى صفحة مرئية داخل تطبيق الموظفين على المسار
`/admin/project-cockpit`. الصفحة:

- تُسجل في الـrouter والقائمة فقط عندما يكون `import.meta.env.DEV=true`؛
- مقفولة على `super_admin` حتى في التطوير؛
- تعرض Snapshot مؤرخًا للـ13 موديول والقرارات والمخاطر وخارطة الطريق؛
- تضيف مراجعة 360° بحالة الدليل، وأربع نتائج غيّرت ترتيب الخطة، وخارطة
  اعتماديات لا تستخدم نسبة جاهزية مضللة؛
- تضيف مركز UI/UX لستة سياقات تشغيلية، Design principles وquality worksheet
  وأنماط تفاعل ومراجع بحث، مع تحويل الرحلة إلى برومبت تدقيق؛
- تبني برومبت عربي أو إنجليزي حسب نوع المهمة والموديول والمرحلة والقرارات؛
- تنسخ البرومبت للشات فقط، من غير AI API أو token أو كتابة في Git/DB؛
- لا تضمّن `wagdy.md` الخام؛ البيانات المنظمة في
  `frontend/apps/el-kheima/src/dev/projectCockpitData.ts` و
  `projectCockpitExperienceData.ts` حتى لا تدخل الملاحظات الداخلية تلقائيًا في
  bundle.

الملفات الأساسية: `ProjectCockpitView.vue`، `projectCockpitData.ts`،
`projectCockpitExperienceData.ts`، route/nav
تطويري في `router/index.ts` و`BackOfficeLayout.vue`، ومفتاحا تنقل ar/en. أضيف
أيضًا `clearLabel` اختياري لـ`SearchInput` حتى يكون زر مسح البحث accessible
باللغتين من غير تغيير الاستدعاءات الحالية.

**التحقق:** `pnpm --filter el-kheima type-check` ناجح؛
`pnpm --filter el-kheima build` ناجح؛ فحص الحزمة أثبت غياب route والـsnapshot
ومحتوى صانع البرومبت من production. معاينة Chrome حقيقية بعد login عادي نجحت
للعربي RTL والإنجليزي LTR، تبويبي 360° وUI/UX، worksheet وprompt handoff،
Desktop وMobile بعد طي القائمة، مع صفر أخطاء JavaScript. ظهر أن القائمة
الجانبية تبدأ مفتوحة على العرض الضيق؛ سُجلت كدين UX ولم يُغير layout في هذه
الدفعة.

مراجعة الجاهزية وخطة التنفيذ الجديدة في
`docs/audits/PRODUCTION_READINESS_AUDIT.md` و
`docs/audits/SMART_EXECUTION_ROADMAP.md`. هما baseline قبل الإصلاح.
**تحديث (2026-07-18):** خطر Public/QR (C-02) اتقفل فعليًا، وشريحة تحويل طلب
Dining إلى `paid` من Gate 1B اتنفذت واتعمدت بعد 3 مراجعات Codex. بقية الخطر
المالي **لسه غير محلولة بالكامل** — راجع القسم الجديد تحت.

**مهم:** الصفحة Snapshot وليست telemetry. الكود والاختبارات وGit يظلون مصدر
الحقيقة، ويجب تحديث تاريخ snapshot عند أي قرار أو إغلاق مرحلة موثق.

---

## 🔒 Gate 1A — احتواء Public/QR: مكتملة ومُعتمَدة (2026-07-17)

راجعتها Codex كمراجع مستقل على 5 جولات (4 تصحيح + جولة أمان نهائية مخصصة)،
كل جولة اتحقق فيها من الكود الفعلي قبل أي تعديل — مش تصديق أعمى للملاحظات.
Commit: `fix(security): contain unsafe public guest workflows` على فرع
`gate-1-critical-containment` (**لم يُدمَج على `main`، لم يُرفَع لـorigin**).

**السياق:** هذا هو تنفيذ Gate 1A من `docs/audits/SMART_EXECUTION_ROADMAP.md`،
مبني مباشرة على اكتشافات تدقيق Public Phase 0
(`docs/audits/public-phase-0/08_OPEN_QUESTIONS_AND_RISKS.md`) وC-02 في
`docs/audits/PRODUCTION_READINESS_AUDIT.md`. الـVPS الحقيقي
(`187.124.170.249`) كان بيعرّض هذه الـendpoints فعليًا خارج جهاز التطوير،
فده حدد 1A (Public/QR) كأولوية قبل 1B (Financial Atomicity).

**التغييرات الفعلية (كل واحدة مذكورة كـfile-level fact، للتفاصيل الكاملة
راجع الـcommit نفسه):**

1. **الطلب الذاتي (`POST /dining/public/orders`) وnداء الضيف (`POST
   /public/alerts`)** — مقفولون افتراضيًا خلف بوابتين لازم الاتنين معًا:
   `DINING_SELF_ORDER_ENABLED`/`GUEST_ALERTS_ENABLED` (typed settings في
   `app/core/config.py`، مش قاعدة بيانات) + `core.Setting` خاص بالفرع
   (`dining.self_order_enabled`/`core.guest_alerts_enabled`). production
   ترفض الإقلاع صراحةً لو أي واحد `true` وقيمة `ENVIRONMENT` مش ضمن
   allow-list صريح (`development`/`test`/`testing`، بعد `strip().lower()`).
2. **`POST /beach/reservations/{id}/checkin` (BOLA/IDOR)** — كان أهم اكتشاف
   في تدقيق Public Phase 0: كاشير أي فرع يقدر يسجّل دخول حجز فرع تاني بمجرد
   تخمين رقم الحجز، لأن `User` معندوش عمود `branch_id` خالص و`get_cashier_user`
   بيتحقق من مستوى الصلاحية بس. الإصلاح: `core.services.assert_branch_access`
   (فحص عبر `HR.Employee.branch_id`)، مع استثناء واحد بس: `super_admin`
   (Decision 0003) — **مش** أي level>=60 (تصحيح جولة مراجعة لاحقة، كان
   Manager/Accountant/HR Manager بياخدوا bypass زيادة عن قرار السوبر أدمن
   الفعلي).
3. **نفس فحص الفرع** بقى على `GET /alerts`، `PATCH /alerts/{id}/status`،
   وWebSocket `/ws/alerts/{branch_id}` — التلاتة كانوا بيسمحوا لموظف من فرع
   يشوف/يتحكم في تنبيهات فرع تاني تمامًا.
4. **`GET /beach/reservations/{id}/public`** — كان بيرجّع `guest_name`،
   `guests_count`، `with_towel`، `reservation_date`، `total_amount` لأي حد
   بيخمّن رقم حجز، بدون تسجيل دخول خالص. بقى يرجّع `{id, status}` بس.
   `BeachCheckinView.vue` بقى يعرض التفاصيل الكاملة بعد تسجيل الدخول
   الفعلي بس.
5. **`GET /dining/public/orders/{order_id}`** — **مقفول تمامًا لحد Gate 8**،
   مش مربوط بإعداد الطلب الذاتي (تصحيح جولة مراجعة لاحقة) — لأن `order_id`
   متسلسل وبيقرا من نفس جدول طلبات الكاشير/POS العادية، فتفعيل الطلب الذاتي
   وحده مش كافي حماية.
6. **`dining.services.create_order`** — بقى يتحقق إن `outlet.branch_id`
   يطابق الفرع، والطاولة تتبع نفس المنفذ والفرع، **وكل صنف في الطلب** يتبع
   نفس المنفذ والفرع (كانت فجوة حقيقية غير مغطاة — ضيف كان يقدر يطلب صنف
   من منفذ/فرع تاني تمامًا). `table_id` بقى `Field(ge=1)` في كل الـschemas
   المعنية (بما فيها `OrderSyncRequest` الخاص بالمزامنة offline).
7. **خريطة `app.core.rate_limit._LIMITED_ROUTES`** — كانت لسه بتسجّل مسارات
   `restaurant`/`cafe` المحذوفة من 2026-07-13 كـdead entries، بينما مسارات
   `dining/public/*` الحقيقية (بما فيها `POST /orders` القادر ينشئ طلب
   حقيقي) عمرها ما كانت مسجّلة — يعني بدون أي حد أقصى فعلي من يوم الـcutover.
8. **اكتشاف أمني إضافي من المراجعة النهائية** (مش من التدقيق الأصلي):
   `_client_ip` كان بيثق في أول قيمة (leftmost) في هيدر `X-Forwarded-For` —
   القيمة دي بيتحكم فيها العميل بالكامل وبتعدّي زي ما هي عبر edge nginx
   وfrontend nginx (الاتنين بيستخدموا `$proxy_add_x_forwarded_for` اللي
   بيضيف مش يستبدل)، يعني أي عميل يقدر يزوّر مفتاح حد الطلبات في Redis
   ويهرب من أي rate limit تمامًا. الإصلاح: `RATE_LIMIT_TRUSTED_PROXY_HOPS`
   (افتراضي 0 = تجاهل الهيدر كليًا، 2 في `docker-compose.prod.yml` لسلسلة
   edge nginx → frontend nginx → backend)، بيقرا القيمة الصح من اليمين
   ويتحقق منها كـIP صالح، وfail-closed لـ`request.client.host` لو السلسلة
   قصيرة أو القيمة غير صالحة.

**التحقق (مراجعة Codex المستقلة النهائية):**

- **1,826 اختبارًا مُجمَّعًا — 1,823 ناجح، 3 skipped (اختبارات migration
  خاصة بـPostgreSQL فقط، `DINING_MIGRATION_TEST_ADMIN_URL` غير متاح — شرط
  موثّق، مش فشل)، صفر فشل.**
- 7/7 اختبارات مقاومة تزوير rate-limit proxy ناجحة.
- `alembic heads`: head واحد `9989c0432ccc` — **مفيش أي migration جديدة
  في هذه الدفعة**.
- TypeScript وProduction build ناجحين لتطبيقي `el-kheima` وpublic.
- Docker Compose (الأساسي + الإنتاج + overlay الـip-only) صالحة الثلاثة.
- `git diff --check` نظيف.
- **لم تُبنَ أو تُنشَر أي صورة Docker على السيرفر الفعلي (`187.124.170.249`)
  في هذه الدفعة.**

**لسه مفتوح عمدًا، مش جزء من هذا الإغلاق:**

- **Gate 1B (Financial Atomicity)** — الشريحة المحدودة الخاصة بدفع Dining
  اتنفذت واتعمدت لاحقًا في 2026-07-18؛ بقية الخطر المالي ما زال مفتوحًا.
- **Gate 2 (Super Admin backend safeguards)** — أصبحت المرحلة التالية بعد
  checkpoint نظيف لشريحة Gate 1B.
- **Gate 8 (Service Location الكاملة)** — QR token عشوائي/قابل للدوران،
  guest session حقيقية، dedupe/idempotency، وworkflow `view_and_call`
  الكامل. `POST /public/alerts`'s `context_type` mismatch **لم يُصلَح
  عمدًا** — إصلاحه بدون بناء الحماية الكاملة كان سيجعل endpoint غير آمن
  يعمل، فبقى مقفول بدل كده.
- **النظام ما زال غير جاهز للإنتاج بشكل عام.** هذا احتواء لخطر تعرض عام
  واحد ومحدد، مش اكتمال كل بوابات الجاهزية.

---

## 🔐 Gate 1B — شريحة دفع Dining: مُنفَّذة ومُعتمَدة (2026-07-18)

تحويل طلب Dining إلى `paid` كان يقدر ينجح جزئيًا: حالة الطلب تتغير بينما
شحنة الفوليو أو خصم المخزون أو قيد الإيراد/COGS يفشل أو يُبتلع. الشريحة
الجديدة جعلت المسار وحدة عمل واحدة بcommit واحد وrollback كامل، وأضافت قفل
`NOWAIT` للطلب، قفلًا متسلسلًا للفوليو، قفلًا للمخزون، وفحصًا صارمًا للحسابات
والمخزن/الفرع وطريقة الدفع. كما أصبحت أخطاء التزامن والإعدادات لها أكواد HTTP
محددة من غير تسريب تفاصيل قاعدة البيانات.

نقل كل إضافة Folio إلى نقطة مركزية كشف وأصلح باج PMS قديمًا: رسوم الوصول
المبكر/المغادرة المتأخرة لم تكن تنشئ `FolioCharge` أصلًا لأن `posted_at` كان
ناقصًا والخطأ يُبتلع. مسارات إضافة الشحنة في Beach/PMS/split-bill أصبحت
fail-closed؛ هذا لا يعني أن باقي الذرّية المالية داخل تلك الوظائف اتقفلت.

راجعت Codex التنفيذ ثلاث مرات. الجولة النهائية وجدت خطأ تنظيف صغيرًا في
اختبار PostgreSQL فقط (Thread/connection لم يكونا يُغلقان في `finally`
الصحيح)، أصلحته ثم أعادت تشغيل البوابات:

- 1,875 test collected: **1,867 passed، 8 skipped، 0 failed**.
- **5/5** اختبارات تزامن حقيقية على PostgreSQL، وصفر قواعد مؤقتة متروكة.
- Alembic head واحد `9989c0432ccc`، بلا migration جديدة.
- frontend type-check/build ناجحان للتطبيقين.
- Docker Compose base/prod/prod+ip-only صالحة، و`git diff --check` نظيف.

التفاصيل والمخاطر المؤجلة:
`docs/audits/gate-1b-financial-atomicity-plan.md`. **تم عمل checkpoint**
(commitين منظمين على `gate-1b-financial-atomicity`، بدون push).

---

## 🔐 Gate 2A — ثوابت أمان السوبر أدمن: مُنفَّذة ومُعتمَدة (2026-07-18)

`PATCH /users/{id}/role` و`POST /permissions` كانا بدون أي حماية لثوابت
Decision 0003: منع صريح (`UserPermission.allowed=False`) كان يقدر يُسقط
صلاحية super_admin نشط فعليًا على 16 endpoint حسّاس، مفيش رفض لإنشاء
override يستهدف super_admin، و`update_user_role` كان بدون أي قفل تزامن
أو حماية self-lockout/last-active-super-admin.

الإصلاح: دالة قرار مركزية واحدة (`_resolve_permission`) — super_admin
نشط يعدّي أي منع صريح دايمًا (`has_permission` و`/permissions/me`
الاتنين). `grant_permission` يرفض 409 أي هدف super_admin (نشط أو غير
نشط)، و404 لهدف غير موجود. `update_user_role` بقت معاملة واحدة حقيقية:
قفل كل super_admin النشطين بترتيب ثابت (`ORDER BY id`، منع deadlock)،
إعادة تحقق من صلاحية المنفّذ تحت القفل، رفض self-demotion/
self-deactivation الفعليين دايمًا (no-op مسموح)، ورفض أي تغيير هيسيب
صفر super_admin نشط. اتأكدت الحماية تحت تزامن حقيقي على Postgres حي
(super_admin نشطان اتحاولوا يخفّضوا بعض في نفس اللحظة — نجاح واحد
بالضبط، ورفض واحد بالضبط، وsuper_admin نشط واحد بالضبط فضل في النهاية).

راجعت Codex جولتين: تصحيح (2 Medium + 1 Low — إغلاق باب خلفي كامن في
`AuthService.update_user`، إصلاح نجاح كاذب في اختبار Postgres، تحديث
تعليقات قديمة) ثم اعتماد نهائي بدون ملاحظات جديدة:

- **1,885 test passed، 10 skipped، 0 failed** (كان 1,867/8 قبل Gate 2A).
- **2/2** اختبارات تزامن حقيقية على PostgreSQL (منفصلة عن Dining، متغير
  بيئة مستقل `SUPER_ADMIN_CONCURRENCY_TEST_ADMIN_URL`).
- Alembic head واحد `9989c0432ccc`، بلا migration جديدة.
- `bash scripts/agent-check.sh`، frontend type-check/build ناجحان.
- `git diff --check` نظيف.

**خارج نطاق هذه الشريحة عمدًا (Gate 2B لاحقة)**: `change_password`
bypass لـadmin/super_admin (ثغرة حقيقية موثّقة، صفر اختبار حالي)، فرض
TOTP فعليًا وقت الدخول في الإنتاج، step-up عام للعمليات الحساسة، وtyped
settings registry.

التفاصيل الكاملة (كل ملف، كل قرار تصميمي، التحليل الرياضي لسيناريو
"آخر super_admin نشط"، وسجل مراجعتي Codex): `docs/audits/
gate-2a-super-admin-invariants.md`. **تم عمل checkpoint** (commitين
منظمين على `gate-2a-super-admin-invariants`، بدون push).

---

## 🔑 Gate 2B1 — كلمة السر ودورة الجلسة: مُنفَّذة ومُعتمَدة (2026-07-18)

الفحص العملي وجد أن تغيير كلمة السر من شاشة البروفايل كان معطّلًا لكل
الأدوار بسبب اختلاف `current_password` في الفرونت عن `old_password` غير
الـtyped في الباك إند، وأن admin/super_admin كانا يتجاوزان تحقق كلمة السر
الحالية عبر API. تغيير/reset كلمة السر وتعطيل الحساب لم تكن تلغي كل
الجلسات، وrefresh rotation لم تكن ذرّية تحت التزامن. reset tokens كانت
مخزنة خامًا، وlogout لا يستهلك refresh cookie من السيرفر.

أخطر اكتشاف إضافي: شاشة إعداد 2FA كانت تعرض QR من خدمة خارجية عنوانها
يحمل `otpauth://` كاملًا، وبالتالي ترسل سر TOTP الدائم لطرف ثالث. أصبح QR
يتولد محليًا كـPNG data URI باستخدام dependency موجودة بالفعل.

تم توحيد عقد تغيير كلمة السر مع توافق مؤقت للاسم القديم، وفرض كلمة السر
الحالية على كل الأدوار، وإلغاء access/refresh sessions بعد change/reset،
وحذف refresh sessions داخل معاملة تغيير role/status في Gate 2A. أصبحت
refresh rotation معاملة واحدة باستهلاك شرطي، وlogout يلغي access header
وrefresh cookie، وتُخزّن reset tokens الجديدة كـhash مع رابط حي واحد لكل
حساب. أضيفت حدود مستقلة لمسارات auth الحساسة وحد account-scoped لطلبات
reset. لا migration جديدة.

**التحقق:** **1,914 collected؛ 1,903 passed؛ 11 skipped؛ صفر فشل**، واختبار
refresh race جديد نجح **1/1 على PostgreSQL حي**، وfrontend type-check/build
ناجحان. التفاصيل في
`docs/audits/gate-2b1-auth-session-lifecycle.md`.

**المراجعة والاعتماد:** Claude راجع الـ18 ملفًا سطرًا بسطر كمراجع مستقل،
ولم يجد أي Critical/High/Medium ولم يعدّل الكود. أعاد بنجاح repository
check و78 اختبارًا مستهدفًا والـfull suite واختبار PostgreSQL والـfrontend
type-check/build. implementation checkpoint:
`3f3f52e fix(security): harden authentication session lifecycle`، بدون push.

**الحالة:** Gate 2B1 مقفولة ومُعتمَدة. المؤجل عمدًا: auth audit، bootstrap
آمن بدل كلمة السر الافتراضية، فرض TOTP في production، recent-auth/step-up،
recovery codes، وrefresh-token family reuse detection. تبدأ Gate 2B2 في
فرع/checkpoint مستقل بعد تحليل rollout يمنع lockout أو استحواذ أول enrollment.

---

## 🔐 Gate 2B2 — Bootstrap وTOTP والاسترداد: مُنفَّذة ومُعتمَدة (2026-07-18)

الفحص أثبت أن مجرد تحويل `LOGIN_2FA_ENFORCED=true` كان غير آمن: حساب
Super Admin الافتراضي وكلمة مروره معروفان في seed، وأول شخص يدخل كان يقدر
يربط TOTP بهاتفه. لم توجد كلمة مرور مؤقتة إجبارية أو enrollment token أو
recovery codes، وseed نفسه كان قادرًا على إنشاء بيانات تجريبية كاملة في
production لو شُغّل هناك.

تم بناء control plane محلي تفاعلي (`python -m app.admin_bootstrap
create|recover`) يولّد كلمة مرور عشوائية ورمز تهيئة منفصل محدود العمر، من
غير قبول أسرار في command arguments أو env. الحساب يظل محصورًا في رحلة
تغيير الكلمة ثم ربط TOTP، ولا يحصل على refresh cookie قبل اكتمالها. أضيفت
8 أكواد استرداد 120-bit تُعرض مرة واحدة وتُخزن hash، ومنع replay لنفس
TOTP/recovery code تحت التزامن. `recover` يحافظ على الدور ولا يصعّد حسابًا،
وترقية/تفعيل `super_admin` أو `accountant` تُرفض قبل تفعيل 2FA.

أضيفت migration `a7c2e91f4b6d` غير مدمرة، وproduction/staging/أي اسم بيئة
غير معروف يفشل الإقلاع ما لم يكن TOTP مفروضًا ومفتاح Fernet صالحًا.
`app.seed` أصبح محصورًا صراحةً في development/test/testing. تطبيق الموظفين
أصبح يشرح وينفذ الرحلة كاملة بالعربي والإنجليزي، بما فيها الدخول بكود
استرداد وتجديد الأكواد وتغيير كلمة المرور المؤقتة.

**التحقق الحالي:** دورة migration upgrade→downgrade→upgrade نجحت على
PostgreSQL مؤقتة، و3/3 اختبارات تزامن حقيقية (refresh/recovery/TOTP) نجحت،
وfrontend type-check/build نجحا. الـfull suite: **1,937 مجمّع؛ 1,924 ناجح؛
13 skipped؛ صفر فشل**، وAlembic له رأس واحد `a7c2e91f4b6d`.

**مراجعة Claude المستقلة:** راجعت الـdiff كاملًا (31 ملف) سطرًا بسطر —
مش تصديق تقرير التنفيذ — وأعادت تشغيل كل شيء بنفسها: 79 اختبارًا مستهدفًا،
الـfull suite (1,924 ناجح/13 skipped/صفر فشل)، 3/3 اختبارات تزامن حقيقية
على PostgreSQL، ودورة migration كاملة (upgrade→downgrade→upgrade) على
قاعدة معزولة اتعملها واتمسحت خصيصًا للمراجعة. **صفر ملاحظة Critical/High/
Medium.** ملاحظتان Low فقط (تكرار ثابت بيئات آمنة بلا خطر، وكود ميت قديم)
اتأجلتا عمدًا.

**الحالة: مُعتمَدة.** commitين منظمين على فرع `gate-2b2-totp-bootstrap`،
بدون push:
- `c78e7ba fix(security): enforce secure TOTP bootstrap and recovery`
- `docs: record Gate 2B2 acceptance`

**تنويه تشغيلي (مش عيب في الشريحة نفسها):** `.env.prod` الحقيقي لسه
`LOGIN_2FA_ENFORCED=false` — السيرفر الحقيقي هيرفض الإقلاع بعد نشر الفرع
ده لحد ما يتحدّث الإعداد ده والتأكد من `FIELD_ENCRYPTION_KEY`. هذا سلوك
مقصود (fail-closed)، لكنه خطوة تشغيلية إلزامية قبل أي نشر جديد.

**مهم:** هذا الاعتماد يخص شريحة bootstrap/TOTP/الاسترداد فقط — **لا يعني
أن المشروع ككل production-ready**. Gate 2B3 (step-up/recent-auth عام
للأدوار والصلاحيات والإعدادات) ما زالت مطلوبة، وفجوة بيانات المرجع
للإنتاج (production reference-data) لسه غير محلولة. التفاصيل الكاملة:
`docs/audits/gate-2b2-totp-bootstrap-recovery.md`.

---

## 🛡️ Gate 2B3A — Step-Up Control Plane: مُنفَّذة ومُعتمَدة (2026-07-18)

فتحنا Gate 2B3A فوق Gate 2B2 مباشرة: 4 عمليات تحكم حساسة (تغيير دور
مستخدم، منح/منع صلاحية صريحة، إلغاء صلاحية صريحة، تعديل إعداد) كانت لسه
بتنفَّذ بمجرد role check عادي — من غير أي إثبات هوية حديث فعلي، ومن غير
سبب مسجَّل. زي ما اكتشفنا أثناء التنفيذ، `GET`/`PUT /settings*` كمان
كانت بتثق في `branch_id` القادم من العميل بلا أي تحقق فرع حقيقي، والإعدادات
العامة (`branch_id=None`) كانت مفتوحة لأي admin بدل super_admin فقط.

**المبني فعليًا:**
- جدول `step_up_grants` جديد (migration `ad7ed1e7329b`) — إثبات لمرة
  واحدة، مرتبط بعملية واحدة بالظبط عبر scope hash (SHA-256 لـJSON
  حتمي)، ومرتبط بجلسة الدخول الفعلية (access token hash)، صلاحيته
  180 ثانية قابلة للضبط (60-300).
- `POST /api/v1/auth/step-up` — يطلب كلمة السر الحالية دايمًا، وكود
  TOTP أو recovery code واحد لو 2FA مفعّل. الأدوار الإجبارية 2FA
  (`super_admin`/`accountant`) ممنوعة تمامًا من أي مسار password-only.
- الأربعة endpoints المحمية (`PATCH /users/{id}/role`, `POST
  /permissions`, `DELETE /permissions/{id}`, `PUT /settings/{key}`)
  بقت تطلب `X-Step-Up-Token` header + `reason` إجباري — استهلاك الإثبات
  عبر DELETE شرطي ذرّي (نفس نمط refresh-token rotation)، اتأكد منه حي
  تحت تزامن Postgres حقيقي (thread واحد بس بينجح).
- عزل فرع حقيقي للإعدادات (`assert_branch_access`)، والإعدادات العامة
  بقت super_admin فقط قراءةً وكتابةً — مع الحفاظ على fallback القيمة
  العامة الداخلي اللي خدمات زي تسعير الشاطئ بتعتمد عليه.
- `AuditLog` الموجود (مفيش جدول تدقيق موازٍ) بقى فيه `reason`،
  `step_up_public_reference`، `assurance_method` لكل عملية ناجحة —
  وسجل منفصل لدورة الإثبات نفسها (إصدار/استهلاك/رفض) لمستخدم معروف فقط،
  مش لكل محاولة دخول فاشلة (ده مؤجَّل عمدًا لـGate 2B3B).
- الفرونت إند: `StepUpConfirmModal.vue` جديد (مختلف تمامًا عن
  `PinGuardModal.vue` — بيثبت هوية المستخدم الحالي نفسه، مش موافقة مدير
  تاني)، متكامل مع `PermissionsView.vue`/`SettingsView.vue`، عربي/
  إنجليزي بالكامل بدون فرض RTL، ومفيش أي سر (باسورد/كود/توكن) بيتخزن في
  localStorage/sessionStorage. `super_admin` بقى مستبعد من قائمة
  الاستهداف في `PermissionsView` على مستوى الفرونت إند نفسه. تحذير واضح
  جديد في `SettingsView` لما الحساب مالوش فرع حقيقي مرتبط (بدل افتراض
  صامت إن الفرع دايمًا 1).

**باج حقيقي اتكشف واتصلح أثناء التنفيذ:** `consume_step_up` كان بيعمل
`commit()` ثم يحاول يقرأ بيانات من نفس الصف اللي اتحذف لتوّه من الـORM
object القديم — `ObjectDeletedError` حقيقي على كل استهلاك ناجح، اتكشف
فورًا بفشل التستات. الحل: قراءة البيانات المطلوبة في متغيرات محلية قبل
الـcommit، مش من الـobject بعده.

**مراجعة Codex المستقلة الأولى (2026-07-18): Changes Requested.** 2
ملاحظة High + 3 Medium، اتحققت كلها من الكود الفعلي (مش تصديق) وكلها
اتأكدت حقيقية، والخمسة اتصلحوا:
- **High**: تسريب قيمة إعداد عام لمدير فرع طالب مفتاح فرعه (fallback
  ضمني في crud.get_setting القديمة) — اتصلح بـget_setting_exact() جديدة
  بدون fallback للمسار الإداري.
- **High**: سباق TOCTOU حقيقي — المنفّذ ممكن يتخفّض (أو الهدف يترقّى
  لـsuper_admin) في النافذة اللي step-up بيوسّعها بين فحص الدور وتنفيذ
  الـmutation. اتصلح بإعادة قفل وفحص المنفّذ (ونفّذ نفس الحاجة للهدف في
  grant_permission) بنفس ترتيب القفل الثابت من Gate 2A — اتأكد بتست
  تزامن Postgres حقيقي جديد (ترقية هدف بالتزامن مع منح صلاحية له).
- **Medium**: intent كان dict حر بيتحول يدويًا (bool("false")==True باج
  حقيقي) — بقى عقد Pydantic typed لكل purpose.
- **Medium**: فشل إصدار step-up مايتسجلش في AuditLog خالص، واستهلاك
  مرفوض بيتسجل بلا حد — بقى فيه تسجيل محدود (rate_limit()) للاتنين.
- **Medium**: ادّعاء "عربي/إنجليزي كامل" كان غير دقيق (كتالوج الصلاحيات
  بلا label_en، تاريخ ar-EG ثابت) — اتصلح، وAppInput المشترك بقى فيه
  focus/autocomplete/inputmode حقيقي.

**التحقق (بعد التصحيحات والمراجعة النهائية):** `bash scripts/agent-check.sh` نجح،
**full suite: 1959 ناجح، 16 skipped، صفر
فشل**، **3/3** تست تزامن Postgres حقيقي (زائد التست الجديد لسباق
الترقية/المنح)، دورة migration كاملة على قاعدة معزولة جديدة، `alembic
heads` رأس واحد، `pnpm --filter el-kheima type-check`/`build` نجحا،
`git diff --check` نظيف.

**الحالة: Gate 2B3A مُعتمَدة نهائيًا.** المراجعة النهائية أعادت فحص
الـdiff واختبارات Postgres والبناء، وشدّدت عقود intent وربط labels بمدخلات
`AppInput` قبل الاعتماد. لا push. تم فتح فرع Gate 2B3B وتجهيز عقد تنفيذ
كبير لكلودي يجمع تدقيق المصادقة، refresh-token families وكشف replay،
وإدارة المستخدم لجلساته؛ لم يُنفَّذ كود هذه الدفعة بعد. Gate finance
step-up وregistry الإعدادات الـtyped ما زالا مؤجَّلين عمدًا. التفاصيل
الكاملة لـGate 2B3A:
`docs/audits/gate-2b3a-step-up-control-plane.md`.

---

## 🔒 Gate 2B3B — تدقيق المصادقة ودفاع الجلسات: مُعتمَدة نهائيًا (2026-07-19)

حزمة واحدة متماسكة بثلاث شرائح فوق Gate 2B3A المُعتمَدة:

**الشريحة A — سجل مصادقة موحّد، محدود، بلا أسرار.** كل أحداث المصادقة
(نجاح/فشل الدخول، القفل، الدخول على حساب مقفول/غير نشط، طلب/إتمام إعادة
تعيين كلمة السر، تفعيل/تعطيل 2FA، استخدام/تجديد recovery code، logout،
إلغاء جلسة/كل الجلسات، اكتشاف replay) بتتكتب في `AuditLog` **الموجود**
(مفيش جدول موازٍ)، مع IP موثوق (نفس سياسة البروكسي الموجودة، مش
X-Forwarded-For خام)، User-Agent منظّف ومحدود، وrequest_id. **قرار
مضادّ للتضخّم**: إيميل غير موجود = **صفر صف في القاعدة** (بس سطر log
منظّم ببصمة HMAC غير قابلة للعكس + IP)؛ وأحداث الفشل المتكرر محدودة
بـ`rate_limit`. anti-enumeration محفوظة بالكامل (نفس الرسالة/التوقيت/
الحالة)، والسجل سيرفر-سايد فقط مش side channel.

**الشريحة B — عائلات refresh token + كشف replay ذرّي.** الدوران بقى
يبصم `consumed_at` (tombstone) عبر UPDATE شرطي بدل الحذف النهائي —
طلبان متزامنان مايصدروش successorين أبدًا. تقديم توكن مستهلَك تاني =
**replay مؤكد** → إلغاء العائلة كلها ذرّيًا + قطع access token فوري +
تسجيل `refresh_token_replayed` بلا سر. أعمدة جديدة على `refresh_tokens`
(migration `b8f4d2a19c07`): `family_id` داخلي عشوائي، `family_public_id`
مرجع عام منفصل للواجهة، `family_started_at`، `consumed_at`, `revoked_at`,
`successor_token_hash`, `user_agent`. backfill بيدّي كل صف قديم عائلته
المستقلة (مش عائلة واحدة مشتركة).

**الشريحة C — API وواجهة إدارة الجلسات (عربي/إنجليزي).** المستخدم يشوف
جلساته الفعلية (`GET /auth/sessions`، مراجع عامة بس، مفيش token/hash/
family_id داخلي)، يلغي جلسة واحدة (`DELETE /auth/sessions/{ref}`) أو كل
الجلسات الأخرى (`POST /auth/sessions/revoke-others`) — الاتنين محميين
بـ**step-up بتاع Gate 2B3A نفسه** (purpose جديد scope-bound، مفيش نافذة
تأكيد موازية)، ويشوف نشاطه الأمني (`GET /auth/security-activity`،
allow-list + صفحات). شاشة `SessionsView.vue` جديدة (`/account/sessions`)
بتعيد استخدام `StepUpConfirmModal.vue` (اتوسّع بـ`requireReason` مش
اتكرّر)، عربي/إنجليزي كامل بدون فرض RTL، مفيش سر في التخزين المحلي.

**باج اتصلح:** تست Gate 2B1 كان بيفترض إن successor بيفضل شغّال بعد
replay للأب — دي بالظبط الثغرة اللي الجيت ده بيقفلها؛ اتحدّث التست
ليؤكّد السلوك الأقوى الصحيح (replay بيقتل العائلة كلها).

**مراجعة Codex النهائية:** أغلقت خمس فجوات قبل الاعتماد: access token بقى
مربوطًا بالجلسة عبر `sid` ويتوقف فور إلغائها؛ refresh cookie لازم يخص نفس
مستخدم الـBearer؛ عدّاد الإلغاء بقى يعد عائلات لا صفوف؛ قفل user ثابت يمنع
سباق revoke مع successor جديد؛ ومحاولات self-lockout/استهداف super_admin
المرفوضة دخلت `AuditLog`. مرجع الجلسة العام أصبح 128-bit.

**التحقق:** `bash scripts/agent-check.sh` نجح (1995 تست مجموع)، **full
suite: 1975 ناجح، 20 skipped، صفر فشل**، **4/4** تست تزامن Postgres
حقيقي لعائلات refresh + **3/3** step-up + **2/2** super-admin regression،
دورة migration كاملة `upgrade→downgrade→upgrade` على قاعدة معزولة +
تأكيد backfill بصفوف قديمة حقيقية (3 صفوف → 3 عائلات مميّزة)، `alembic
heads` رأس واحد (`b8f4d2a19c07`)، `pnpm --filter el-kheima
type-check`/`build` نجحا، `git diff --check` نظيف. **مفيش commit ولا
push.**

**الحالة: مُعتمَدة نهائيًا، بدون push.** خارج النطاق عمدًا ومتلمسش: registry
إعدادات typed، step-up مالي، ربط user→branch، إدارة super_admin لجلسات
الآخرين، QR. التفاصيل الكاملة:
`docs/audits/gate-2b3b-auth-audit-session-defense.md`.

**الحالة وقت اعتماد Gate 2B3B:** كان فرع
`gate-3-ui-i18n-quality-foundation` وعقد
`docs/audits/gate-3-execution-brief.md` جاهزين، ولم يكن كود Gate 3 قد بدأ
وقتها. الحالة الأحدث موجودة في مقدمة هذا الملف: Gate 3 اكتملت واعتمدت.

---

## 💰 اللي اتعمل يوم 2026-07-17 — مراجعة محاسبية شاملة (Finance Deep Audit)

Mohamed طلب وكيل متخصص في الحسابات يراجع موديول Finance بالكامل، يصلح أي أخطاء حقيقية، يملأ
فجوات الـ seed data، ويبني مراقبة وردية حية + الميزانية العمومية لو ناقصة. مراجعة منهجية عبر
كل نقطة ترحيل قيد يومية في المشروع (`post_simple_revenue_journal`/`create_journal_entry` عبر
dining/beach/pms/timeshare/leasing/inventory/hr) — 4 باجات محاسبية حقيقية اتلقوا واتصلحوا،
اتنين منهم مؤكدين حيًا على Postgres حقيقي (مش SQLite tests بس).

**باج 1 — مرتجع صنف من طلب دايننج عليه خصم كان بيعكس إيراد أكتر من اللي اترحّل فعليًا**
(`dining.services.refund_order_item`). `refund_amount` كان بيتحسب من `item_gross` + نصيب
VAT/service_charge بس — من غير أي نصيب من `order.discount_amount`. بما إن القيد الأصلي وقت
الدفع بيرحّل `order.total` (صافي بعد الخصم)، مرتجع صنف واحد من طلب خصمه مثلاً 10% كان بيعكس
10% زيادة عن الصح، وبيسيب باقي الطلب برصيد أقل من الصح في الدفتر. الإصلاح: نصيب الخصم بيتحسب
بنفس `share_ratio` المستخدم للـ VAT/service_charge بالظبط، فمجموع مرتجعات كل الأصناف يرجع
بالظبط لـ `order.total` الأصلي. اختبار جديد (`test_refund_item_on_discounted_order_allocates_
discount_share`) بيثبت الرقم بالظبط (232 ج طلب، خصم 20 ج، مرتجع نصف الطلب = 116 ج مش 126 ج
زي قبل الإصلاح) وبيتأكد إن رصيد الإيراد المتبقي في `journal_lines` بعد المرتجع = 116 ج بالظبط.

**باج 2 — استلام أمر شراء (Purchase Order) عمره ما كان بيرحّل أي قيد يومية خالص.**
`inventory.crud.receive_purchase_order` بيرحّل `StockMovement` حقيقي ويحدّث `current_stock`/
`cost_price` (كان شغال بالفعل، اتأكد منه في دفعة الموردين 2026-07-14) — لكن مفيش أي Dr على
حساب المخزون (1200)، ولا أي Cr على حساب موردين (ماكانش موجود في دليل الحسابات أصلاً). النتيجة:
حساب 1200 كان بيتقيّد عليه Cr بس (استهلاك COGS) من غير أي Dr مقابل من المشتريات — رصيده كان
هيتجه سالب دايمًا مع الوقت، ومفيش أي التزام تجاه المورّدين ظاهر في الميزانية العمومية أو دفتر
اليومية، مخالفة مباشرة لـ CLAUDE.md §5.2. الإصلاح: حساب جديد `2200` ("موردون — ذمم دائنة"،
liability) في دليل الحسابات (`seed.py`، idempotent زي باقي الحسابات)، و
`inventory.services._post_purchase_receipt_journal` جديدة (Dr 1200/Cr 2200 بقيمة **دفعة
الاستلام دي بس** — مهم للاستلام الجزئي). `crud.receive_purchase_order` بقى بيرجّع
`(po, received_value)` بدل `po` بس. اختباران جديدان (`test_receive_purchase_order_posts_
balanced_ap_journal`، `test_partial_receive_posts_journal_per_batch_not_full_po`) بيتأكدوا من
الميزانية العمومية الفعلية بعد الاستلام (متوازنة، القيمة صح، الاستلام الجزئي ميضاعفش القيمة).

**باج 3 — مبيعات الشاطئ المباشرة (كاش فوري) كانت غايبة تمامًا عن تقرير نهاية وردية الكاشير.**
اكتشاف أعمق من المتوقع: migration `504f42d2c755` (2026-07-15) عملت `Payment.folio_id`
nullable + عمود `ref_order_id` **صراحةً** "عشان مبيعات الشاطئ/الدايننج المباشرة تظهر في تقرير
نهاية الوردية" (نص الـ docstring حرفيًا) — لكن مفيش أي كود اتكتب بعدها فعليًا بيستخدم البنية
دي. `BeachTransaction.shift_id` بيتسجّل صح (اتأكد منه بتست موجود بالفعل)، لكن
`finance.services.build_shift_end_report`/`list_shift_invoices` (تقرير X/Z اللي الكاشير/المدير
بيشوفه) بيقروا `Payment.shift_id` بس — يعني كل بيع شاطئ مباشر (مش محمّل على غرفة) كان غايب
100% عن تقرير الوردية رغم كل البنية التحتية الجاهزة له. **فجوة إضافية اتكشفت أثناء الإصلاح**:
موديول `Payment` نفسه في `models.py` عمره ما اتحدّث ليطابق الـ migration (`folio_id` فضل
`Mapped[int]` غير nullable في الـ ORM، و`ref_order_id` عمره ما كان موجود كـ attribute خالص) —
نفس فئة الباج "الموديل موجود بس مش مطابق للداتابيز" الموثّقة قبل كده في المشروع. الإصلاح:
(أ) تصحيح موديول `Payment` ليطابق الداتابيز الفعلية (بدون migration جديدة — العمودين موجودين
فعليًا)، (ب) `finance.crud.create_direct_payment`/`get_direct_payment_by_reference` جديدتين
(دفعة POS مباشرة، folio_id=None)، (ج) `beach.services._record_shift_payment`/`_void_shift_
payment` بيسجّلوا/يلغوا Payment حقيقي وقت البيع/الإلغاء المباشر (method="cash" — نفس المعاملة
المحاسبية الموجودة بالفعل في القيد، مفيش تمييز كاش/كارت حقيقي في بيانات الشاطئ). `ShiftInvoiceLine
.folio_id`/`PaymentRead.folio_id` بقوا `Optional[int]`. اختبار جديد (`test_direct_sale_appears_
in_shift_end_report`) بيتأكد إن بيع شاطئ مباشر بيظهر في `build_shift_end_report` (invoice_count،
total_cash، total_sales) وإن الإلغاء بيرجّع الرقم لصفر. **ملحوظة نطاق موثّقة**: دايننج (POS
المطعم/الكافيه) لسه معندهوش نفس الربط — `DiningOrder` أصلاً مفيهوش عمود `cashier_id`/`shift_id`
خالص (بس `waiter_id`)، فمفيش طريقة حالية تحدد "مين الكاشير اللي حصّل الطلب ده" أو "كاش ولا
كارت". ده فجوة حقيقية أعمق (قرار تصميم يحتاج تعديل POS UX لالتقاط طريقة الدفع + schema جديد)،
**مؤجَّل عمدًا** لنفس فلسفة فجوة إيراد الغرفة الموثّقة في CLAUDE.md §18 بند 0 — يستاهل مراجعة
صريحة مع Mohamed، مش تعديل عابر وسط دفعة تانية.

**باج 4 — قيد رواتب غير متوازن حقيقيًا لأي موظف عنده بدل غير خاضع للضريبة (بدل مواصلات/سكن).**
اتكشف حيًا (مش نظريًا) أثناء التحقق من عمق دفتر اليومية على Postgres حقيقي: بعد تشغيل الـ
seeder، الميزانية العمومية طلعت **غير متوازنة** بفارق 500.00 ج بالظبط. التحقيق كشف:
`hr_engine.calculate_employee_payroll` بيحسب `net_salary` شامل `non_taxable_allowances`
(بدلات مواصلات/سكن غير خاضعة لضريبة/تأمينات)، فحساب "صافي رواتب مستحقة" (الدائن في القيد
المجمّع) كان بيشملها فعليًا — لكن `hr.services._post_payroll_journal` (اللي بيبني القيد
المُرحَّل فعليًا للدفتر) كان بيحسب المدين من `run.total_gross` بس (اللي `gross_salary`
بتاعه مستبعد منه `non_taxable_allowances` عمدًا، زي `holiday_bonus` بالظبط)، وعمود مجمّع زي
`total_holiday_bonus` (المُتعامل معاه صح فعلاً) عمره ما كان موجود لـ `non_taxable_allowances`
خالص. النتيجة: أي كشف رواتب فيه موظف عنده بدل غير خاضع كان بيرحّل قيد **غير متوازن حقيقي**
(دائن > مدين بالظبط بقيمة إجمالي البدلات) — مخالفة مباشرة للـ double-entry. المثير للاهتمام:
`hr_engine.py` نفسه كان أصلاً عنده `journal_entry` مرجعي صح لكل موظف (`Dr "مصروف رواتب" =
gross + non_taxable_allowances`، مخزّن في `PayrollLine.journal_entry` كـ JSON) — بس القيد
المُجمّع الفعلي في `_post_payroll_journal` كان بيتجاهله ويعيد الحساب من عمودين run-level بس.
الإصلاح: عمود جديد `PayrollRun.total_non_taxable_allowances`/`PayrollLine.non_taxable_
allowances` (نفس نمط `total_holiday_bonus`/`holiday_bonus` بالظبط، migration `9989c0432ccc`)،
`run_payroll_for_branch` بيجمّعه من `result.non_taxable_allowances`، و`_post_payroll_journal`
بيضيفه للمدين. اختبار جديد (`test_approve_payroll_run_with_non_taxable_allowance_posts_
balanced_journal`) بيثبت التوازن. **اتأكد نهائيًا حيًا**: قاعدة بيانات Postgres معزولة مؤقتة
(مش الـ `resort_os` المشتركة — كانت مشغولة بجلسة تانية شغّالة على `cash_movements`/cost centers
وقت الجلسة دي، `alembic heads` كشف migration `9f3c1a7e5b02` مش موجودة في الفرع ده، فاتجنّبت
تمامًا زي ما طُلب)، `alembic upgrade head` كامل (36 migration) → `python -m app.seed` →
`services.get_balance_sheet` رجعت `is_balanced=True` (كان `False` بفارق 500.00 ج بالظبط قبل
إصلاح باج 4).

**الميزانية العمومية (الميزانية العمومية)**: كانت موجودة بالفعل بالكامل في الباك إند
(`GET /finance/reports/balance-sheet`، `finance.services.get_balance_sheet`) — نفس منهج حساب
الأرصدة المستخدم في ميزان المراجعة/قائمة الدخل (`sum_journal_lines_by_account`)، ومختبرة
بالفعل بـ 3 اختبار HTTP حقيقي (تطبيق أصول/خصوم/حقوق ملكية متوازنة). الفجوة الوحيدة كانت
الفرونت إند — تاب جديد "الميزانية العمومية" في `FinanceView.vue` (جنب تابات الحسابات/مراكز
التكلفة الموجودة، نفس نمط التصميم: فلتر تاريخ "كما في" + جداول أصول/خصوم/حقوق ملكية + شارة
"متوازنة ✅/غير متوازنة ⚠️") — `ENDPOINTS.finance.reportsBalanceSheet` (كان موجود بالفعل في
`endpoints.ts` من غير أي استخدام). أثناء العمل على الملف: **تصفير كل الـ hardcoded API strings
المتبقية في `FinanceView.vue`** (12 موضع — `/api/v1/finance/...` مباشرة بدل `ENDPOINTS.finance.*`
الموجودة بالفعل)، مخالفة صريحة لقاعدة المشروع كانت باقية من قبل التوحيد الشامل الأخير.

**مراقبة الوردية الحية (Live Shift Monitoring)**: تأكيد بقراءة الكود (مش افتراض) إن الوضع
الحالي كان **snapshot-only** — `ShiftDashboardView.vue`/`FinanceView.vue`'s تاب الورديات بيحمّلوا
البيانات `onMounted` بس، مفيش `setInterval` ولا WebSocket خالص، ومفيش endpoint بث لحظي لموديول
finance أصلاً (عكس dining/beach/core اللي عندهم `ConnectionManager` جاهز). اتضاف WS جديد
`GET /finance/ws/shifts/{branch_id}` (نفس نمط `BeachMapConnectionManager`/`dining_manager`
بالظبط — بث بسيط، `get_websocket_user(min_level=60)` مدير+ بس، عشان بيانات مالية لوردية ممكن
تكون كاشير تاني). بيتنادى من `finance.add_payment` (تسوية فوليو) وbeach.`sell_ticket` (بيع
مباشر، بعد إصلاح باج 3) بعد أي دفعة ترتبط بوردية مفتوحة فعليًا — إشارة خفيفة `{"type":
"shift_sale", "shift_id": N}`، مفيش بيانات مالية جوه رسالة الـ WS نفسها (نفس فلسفة KDS: WS
إشارة تحديث، مش قناة نقل بيانات). الفرونت إند: تاب "الورديات" في `FinanceView.vue` (شاشة
المدير اللي بيفتح تفاصيل وردية كاشير معيّن — `openShiftDetail`) بقى مشترك في القناة عبر
`useResortWebSocket` الموجودة بالفعل، وبيعيد تحميل تفاصيل الوردية المفتوحة تلقائيًا لما حدث
`shift_sale` يوصل لنفس الوردية المعروضة — مدير بيفتح تفاصيل وردية كاشير مفتوحة، وأي بيع شاطئ/
تسوية فوليو جديدة بتظهر لحظيًا من غير أي refresh يدوي. **نطاق محصور عمدًا**: مش إعادة تصميم
كامل للوردية — إشارة تحديث خفيفة فوق الـ endpoints الموجودة بالفعل، ومربوطة بس بالمصادر اللي
فعليًا بتتسجل في `Payment.shift_id` دلوقتي (فوليو + شاطئ المباشر) — مش دايننج (نفس فجوة باج 3
الموثّقة فوق).

**Seed data — موردين وأوامر شراء (كانت مفقودة تمامًا)**: `inventory.Supplier`/`PurchaseOrder`
(اتضافوا 2026-07-14) معندهمش أي بيانات seed خالص — شاشة الموردين/أوامر الشراء كانت هتفتح فاضية
100%. اتضاف `_seed_suppliers_and_purchase_orders` (4 موردين مصريين واقعيين — أغذية/مشروبات/
نظافة/صيانة، بأرقام هاتف وعناوين واقعية) + 5 أوامر شراء عبر **كل الحالات** (draft/sent/partial/
received/cancelled) — عن طريق `services.create_purchase_order`/`receive_purchase_order`
الحقيقيين (مش صفوف مُدرَجة مباشرة)، عشان (أ) StockMovement حقيقي، (ب) قيد AP حقيقي (باج 2
فوق) يترحّل فعليًا، ويدّي عمق حقيقي للميزانية العمومية/ميزان المراجعة. **قرار نطاق موثّق**: عكس
`_seed_timeshare_contracts`/`_seed_lease_contracts` (عمدًا من غير قيد محاسبي — عقود كبيرة
مُلفَّقة لعملاء وهميين هتشوّه التقارير المالية)، أوامر الشراء دي عملية تشغيلية عادية بمبالغ
واقعية (مش عميل وهمي)، فنفس فلسفة `_seed_beach_locations` (بيع حقيقي بقيد محاسبي) اتطبّقت.
اتأكد حيًا على قاعدة بيانات Postgres معزولة (إنشاء→migrate→seed→تحقق حساب 1200/2200 عبر
`journal_lines` مباشرة→حذف)، ومرتين (idempotent، صفر تكرار في التشغيلة التانية).

**فحص وحدات تانية طلبها Mohamed صراحةً (بدون باجات جديدة)**:
- **تكلفة منيو الدايننج**: `dining.services.get_food_cost_report` بيقرأ بيانات حقيقية 100%
  (`crud.get_paid_order_items_for_food_cost` من طلبات مدفوعة فعلية + `DiningItemRecipeLine.
  product.cost_price` حقيقي، مش placeholder) — 19 اختبار موجود بالفعل عدّى صح، مفيش تعديل لازم.
- **التايم شير**: `_post_deferred_revenue_journal`/`_post_installment_payment_journal` (دفعة
  أولى + كل تحصيل قسط) بيرحّلوا قيود متوازنة (`post_simple_revenue_journal`، بالبناء)، موسومين
  بمركز تكلفة "TS" — مراجعة سابقة (2026-07-07) صلّحت باجات حقيقية هنا، مفيش جديد.
- **الإيجارات**: `_post_deposit_journal`/`_post_rent_collection_journal` (تأمين + تحصيل
  إيجار+غرامة) بيرحّلوا قيود متوازنة برضو، `TenantCashLog` (تسوية كاش يومية) بيرحّل نفس المسار.
  مفيش باج جديد اتلقى.
- **راتب/سلف/جزاءات (advance_deduction/penalty_deduction إلخ)**: فجوة محاسبية موثّقة بالفعل
  صراحةً في الكود (تعليق مفصّل في `_post_payroll_journal`) — الخصومات دي بتقلل الصافي (الدائن)
  من غير حساب أصول "سلف موظفين مستحقة" مقابل. **متلمسناش عمدًا** — مؤجَّلة صراحةً لنفس سبب فجوة
  إيراد الغرفة (يستاهل مراجعة مخصصة مع Mohamed، مش تعديل عابر).

**التحقق النهائي (2026-07-17)**: `pytest tests/ -v` → **1791 اختبار، صفر فشل** (كان 1786). كل
الاختبارات الجديدة (5): `test_refund_item_on_discounted_order_allocates_discount_share`،
`test_receive_purchase_order_posts_balanced_ap_journal`، `test_partial_receive_posts_journal_
per_batch_not_full_po`، `test_direct_sale_appears_in_shift_end_report`، `test_approve_payroll_
run_with_non_taxable_allowance_posts_balanced_journal`. `alembic heads` → head واحد
(`9989c0432ccc`). `pnpm --filter el-kheima type-check`/`build` نضاف. Migration الجديدة
(`9989c0432ccc`) اتأكدت فعليًا على Postgres حقيقي في قاعدة بيانات معزولة مؤقتة (إنشاء→
migrate→seed→تحقق ميزانية عمومية متوازنة→حذف) — **مش الداتابيز المشتركة `resort_os`**، لأنها
كانت مشغولة بجلسة تانية شغّالة على `cash_movements`/cost centers وقت الجلسة دي (migration
`9f3c1a7e5b02` مش موجودة في الفرع ده) — اتجنّب لمسها تمامًا زي ما طُلب صراحةً.
---

## 🧾 اللي اتعمل يوم 2026-07-16/17 — Click ERP: destination الخزنة + مركز تكلفة + تسعير حسب القناة

راجعنا الـ 6 لقطات معرفية من بحث Click القديم (Dining/Cash-Control، 2026-07-12)
ضد الكود الحالي فعليًا (مش تخمين) — 2 كانوا اتحلّوا بالفعل بشغل لاحق (split-tender
عبر `split_bill()`، extra-groups نصية)، والـ 4 الباقيين اتراجعوا واحد واحد:

1. **`CashMovement.destination`** (main_safe/bank/petty_cash_box) + `cost_center_id`
   — بس لـ `safe_drop` (اتفرض server-side، أي نوع تاني بيترفض). قرار متعمد:
   **مش** ledger كامل لخزائن متعددة بأرصدة تراكمية (تصميم Click الحقيقي) — ده
   ميزة أكبر بكتير (كيان Safe جديد، تحويلات، تسوية خاصة بيها). اللي اتعمل هنا
   الجزء المفيد فورًا ومنخفض المخاطرة بس: تسجيل *فين رايح* الكاش.
2. **تسعير حسب قناة الطلب** — `Outlet` بقى عنده override اختياري لرسم الخدمة لكل
   قناة (takeaway/delivery/room_service) + رسم توصيل ثابت. **كله NULL افتراضيًا
   = صفر تغيير على أي منفذ موجود** — قرار متعمد إن معيار الصناعة الشائع (بدون
   رسم خدمة على تيك أواي/توصيل) *مش* بيتفعّل تلقائيًا، لأنه قرار تسعير حي على
   منتجع حقيقي يستاهل موافقة Mohamed الصريحة، مش افتراض صامت.
3. **"POS flows مختلفة فعليًا لكل order_type"** — طلع إنه *موجود بالفعل* في
   `UnifiedPOSView.vue` (خريطة طاولات لـ dine_in، عنوان/رقم غرفة لـ delivery/
   room_service، مسار مبسّط لـ takeaway) — تقييم سابق كان غلط، اتصحّح من غير
   إعادة بناء حاجة شغالة.

**اكتشاف جانبي مهم (أثناء `alembic revision --autogenerate`، اتصلح جزئيًا،
الباقي مُبلَّغ لا مُصلَح):** الداتابيز الحقيقية لسه فيها 12+ جدول restaurant/cafe
قديم ما اتمسحوش أبدًا رغم الـ cutover (D-05→D-08، 2026-07-13)، plus schema
`dining_order_splits`/`dining_order_payments` كامل يبان إنه من تصميم split-bill
أول مختلف اتهجر، plus عمودين ميتين تمامًا (موجودين في الداتابيز، مش مربوطين
بأي ORM model): `payments.ref_order_id` (من migration `504f42d2c755` اللي
هدفها المُعلَن — ربط دفعة POS مباشرة بالطلب — عمره ما اتنفّذ في كود) و
`dining_order_items.split_id`. **متلمسناش أي حاجة من دول دلوقتي** — خطر حقيقي
(drop جدول ممكن يمسح بيانات) يستاهل مراجعة مخصصة، مش تصليح جانبي.

**اتأكد منه فعليًا:** migration اتكتبت يدوي (مش autogenerate خام — ده كان
هيمسح الجداول القديمة دي كلها كـ side effect) وطُبّقت على الداتابيز الحقيقية.
5 tests HTTP جداد. **1786 → 1791 اختبار، صفر فشل.** TypeScript صفر أخطاء.

---

## ⚖️ اللي اتعمل يوم 2026-07-16 — Policy Engine v1 (سجل مركزي للموافقات)

Mohamed طلب "Policy Engine: طبقة مستقلة لإدارة الموافقات، حدود الخصومات، صلاحيات
الورديات، وسياسات التشغيل". قبل التنفيذ اتعمل تدقيق فعلي (مش تخمين) لمكان كل حاجة
دلوقتي، وطلع إن الصورة مختلطة: منطق الموافقة نفسه (PIN + lockout) كان أصلاً مركزي
في `core.services.resolve_pin_approval` — الفعلي المتكرر كان "مين المستوى المطلوب
للموافقة" (`min_approver_level=60` مقفول inline في 4 أماكن) و"كتابة AuditLog" (كل
موضع بيبنيها يدوي بشكله الخاص). حدود الخصومات (`CustomerGroup.discount_percentage`،
`ConditionalDiscount`) طلعت أصلاً في الداتابيز مش الكود — **اتأكد مع Mohamed مباشرة
(2026-07-16) إنها تفضل كده عمدًا** عشان تتغيّر من غير نشر كود جديد.

**الناتج:** `app/modules/core/policy_engine.py` جديد — كتالوج `SENSITIVE_ACTIONS`
(زي `permission_catalog.py` بالظبط بس لسياسات العمل مش RBAC) + `require_approval()`
(بيقرا الحد من الكتالوج بدل ما يتقفل inline) + `record_policy_audit()` (كتابة
AuditLog بشكل موحّد). مبني *فوق* `resolve_pin_approval` مش بديل له. عمدًا مش جوه
`app/resort_os/` — الملفات هناك "pure domain engines" بدون DB (راجع header
`discount_engine.py`)، والملف ده بيكتب AuditLog فعليًا فمكانه جوه `core/`.

4 مواضع اتنقلت (استخراج، مش إعادة تصميم — نفس السلوك بالظبط): `dining.services.
void_order_item`، `dining.services.apply_order_discount`، `finance.services.
record_cash_movement`، `finance.services.list_shift_invoices` (المُشاهدة بدون
audit log — نفس ما كان). اتأكد إنه behavior-preserving 100%: **1786 اختبار قبل
وبعد، نفس الرقم بالظبط، صفر فشل**.

---

## 🔎 اللي اتعمل يوم 2026-07-16 — مراجعة ودمج جلسة Kiro CLI (2026-07-15)

Mohamed استخدم أداة تانية (Kiro CLI، شوف `.kiro/AGENT.md`) في جلسة منفصلة عملت 122 ملف
تغيير غير مُلتزَم (uncommitted) — Design System Phase 2، T-01، C-01، P-07، شاشات جديدة،
إلخ. طلب مراجعة كاملة قبل الدمج، بنفس أسلوب المراجعة المتبع هنا (تشغيل live، مش قراءة كود
بس). النتيجة: جودة عالية عمومًا، لُقي وصُلح باجين حقيقيين، حاجة واحدة اتأكدت مع Mohamed
مباشرة، وبعدين اتقسّم الشغل كله على 9 commits موضوعية (بدل commit واحد ضخم).

**باجين حقيقيين اتصلحوا قبل الدمج:**
1. **Alembic migration graph مكسور** — migration جديدة (`payment_folio_nullable_ref_order`)
   كانت مستخدمة نفس revision ID (`a1b2c3d4e5f6`) بتاع migration قديمة مُلتزَمة بالفعل
   (`hr_insurance_base_holiday_bonus`) — `alembic heads` كان بيرمي `CycleDetected`. لو
   ده اتـ commit كده، أي `alembic upgrade head` جديد كان هيفشل. اتغيّر لـ ID فريد
   (`504f42d2c755`)، واتأكد بـ `alembic upgrade head` حقيقي على الداتابيز نفسها.
2. **`require()` جوه بيئة متصفح** — `client.ts`/`useWebSocket.ts` المشتركين كانوا بيستخدموا
   `require('../stores/auth')` جوه try/catch عشان يتفادوا circular import. `require` مش
   موجود في Vite/browser — الاستدعاء كان بيفشل صامت جوه الـ catch، يعني **كل اتصال
   WebSocket في المشروع (بما فيها GuestAlertsBell) كان بيتبعت من غير auth token خالص**،
   وميكانيزم إعادة الاتصال بعد انقطاع النت كان معطّل تمامًا (بيقرأ "مفيش token" = "خلصت
   الجلسة، منعيدش المحاولة"). اتصلح جذريًا (مش patch) — `client.ts` بقى بيصدّر
   `getApiToken()`/`registerAuthClearHandler()`، والـ store بيسجّل نفسه عليه بدل ما
   `client.ts` يستورد الـ store.

**قرار واحد اتأكد مع Mohamed مباشرة:** إلغاء آلية رفض قفل الوردية بسبب فرق كاش كبير
(`finance.services.close_shift`) — الوردية بقت تُقفل دايمًا، الفرق بيظهر كـ warning
للمحاسب بس، بدون حاجة لموافقة PIN مدير. Mohamed أكّد إنه قرار صح ("خليها كده"، 2026-07-16).

**اتأكد منه فعليًا قبل أي commit** (مش تقرير، تنفيذ حقيقي):
- `pytest tests/ -v` → **1786 passed, 3 skipped** (الـ 3 هما نفس Postgres-only tests
  الاختيارية القديمة).
- `vue-tsc --noEmit` على الـ 2 apps (el-kheima + public) → **صفر أخطاء**.
- `alembic upgrade head` على الداتابيز الحقيقية (بعد إصلاح الـ ID collision) → نجح نظيف.
- تشغيل backend+Celery live حقيقي، login حقيقي، `curl` على endpoints جديدة
  (`/inventory/suppliers`, `/crm/customer-groups`, `/crm/loyalty/program`,
  `/finance/cost-centers/report`) → كلهم بيردّوا صح.

**اللي دخل فعليًا** (9 commits، كل واحد تستاته خضراء): Design System Phase 2 (7 كومبوننت
+ dark mode حقيقي) · T-01 httpOnly cookie · Finance (إلغاء رفض فرق الكاش + trial balance +
void payment) · Timeshare (`timeshare_agent` role + calendar/visits/report) · Dining
(Split Bill P-07 + خريطة طاولات حية + رفع صور المنيو T-05 + ربط دفعات POS المباشرة
بالفوليو) · CRM Loyalty Points (C-01) · HR (طلبات إجازة + إعدادات رواتب) · شاشات جديدة
(Reception/Beach Admin/Hub Management) · تصفير الـ hardcoded API strings في كل الفرونت
إند + تلميعات شاشات متفرقة.

**تحديث توثيقي:** `wagdy.md` كان لسه بيقول C-01/T-01/T-05/GuestAlertsBell "لم تبدأ" رغم
إنها خلصت فعليًا في جلسة Kiro — اتصحّح. `MASTER_TODO.md`/`FRONTEND_GAPS.md`/`.kiro/AGENT.md`
اتسابوا كمرجع تاريخي لنفس الجلسة (72/73 بند مُنجز في MASTER_TODO). نقطة الدخول
الحالية لأي جلسة هي **`AGENTS.md` ثم `CLAUDE.md`**، والحالة التقنية المؤرخة هنا،
وقرارات Mohamed في `docs/decisions/`، والشرح البشري الحالي في `wagdy.md` — مش
ملفات الخطط التاريخية.

---

## 🏭 اللي اتعمل يوم 2026-07-14 — موردين حقيقيين + مجموعات عملاء بخصم دائم + ربط مركز التكلفة

جولة بحث مقارنة (Click القديم + `elkheima-beach-resort` القديم مقابل resort-os الحالي، بإذن صريح من
Mohamed: "اعملها بفهم وذكاء ولو شايف شي غير منطقي أو خطأ صلح وحسّن للأفضل") كشفت 3 فجوات حقيقية.
**المتطلب الصريح الوحيد من Mohamed** — "الأهم يكون الموردون وأوامر الشراء بتأثر في المخزون" — كان
شغال بالفعل من الأول (`inventory.crud.receive_purchase_order` بيرحّل `StockMovement` حقيقي مع
`SELECT FOR UPDATE NOWAIT`)؛ الشغل هنا كله إضافي فوقه، مش إصلاح له. 3 دفعات، كل واحدة بـ commit
مستقل و`pytest tests/ -v` أخضر بعدها مباشرة.

**Batch 1 — كيان Supplier حقيقي مربوط بأوامر الشراء**: `PurchaseOrder.supplier_name`/
`supplier_phone` كانوا نص حر بدون كيان حقيقي، رغم إن سير عمل الاستلام (والأثر على المخزون) كان
شغال فعليًا من الأول. `Supplier` جديد (`branch_id, name/name_ar, contact_person, phone, email,
address, tax_number, category, payment_terms_days, credit_limit, notes, is_active`) — مبني على
`Supplier` في `elkheima-beach-resort` القديم + الحقول الموسّعة اللي البحث أوصى بيها، بس عمدًا
**مش** بتصميم Click القديم اللي بيدمج الموردين والعملاء في جدول Party واحد (كيانين مختلفين
تمامًا هنا). `PurchaseOrder.supplier_id` (FK nullable) جنب `supplier_name`/`supplier_phone`
القديمين (بقوا لقطة/snapshot، بيتعبّوا تلقائيًا من المورد لو `supplier_id` متحدد ومفيش نص صريح).
CRUD/API كامل (`/inventory/suppliers`، قراءة لأي مستخدم نشط، كتابة لمدير+ زي `Product`).
Migration `8a78528e9403` بتنسخ (best-effort) كل `supplier_name` قديم لصف `Supplier` حقيقي (مطابقة
بالاسم بالظبط، أو إنشاء جديد لو مفيش تطابق) — اتأكد فعليًا على Postgres حقيقي ببيانات شكلها قديم
(بما فيها اسم "TBD (من طلب شراء #N)" الناتج عن الباج اللي اتصلح تحت). **باج حقيقي اتصلح**:
`inventory.services.convert_to_purchase_order` (تحويل طلب شراء موافق عليه لأمر شراء) كان بيحطّ
`supplier_name=f"TBD (من طلب شراء #{id})"` ثابت — مورد حقيقي عمره ما كان بيتحدد فعليًا عند
التحويل، والـ placeholder ده كان بيعدّي الـ validation بصمت. القرار: `supplier_id` بقى إجباري
وقت التحويل نفسه (422 من غيره) — نفس اللحظة اللي "هنشتري من مين فعليًا" لازم تتحدد فيها، مش بعدها.
فرونت إند: قائمة موردين منسدلة (بتعبّي الاسم/التليفون تلقائيًا) في مودال "تسجيل استلام بضاعة"
بـ`InventoryView.vue` + شاشة إدارة موردين كاملة (قائمة/إضافة/تعديل/إيقاف) جوه نفس الشاشة.

**Batch 2 — مجموعات عملاء بخصم دائم (`CustomerGroup`)**: `CustomerGroup` جديد
(`branch_id, name/name_ar, discount_percentage, is_active`) — نفس نمط `/finance/discounts` بالظبط
(قراءة لمدير+، إنشاء/تعديل لـ admin+ فقط). `Customer.customer_group_id` (FK nullable) — **عمدًا
مش** في `CustomerUpdate` العادي (مفتوح لأي مستخدم نشط عبر `get_current_active_user`)، لأن تعيين
مجموعة = خصم دائم تلقائي حقيقي؛ endpoint منفصل `PATCH /crm/customers/{id}/group` مقفول على مدير+.
**قرار سياسة تجارية موثّق (يستاهل انتباه Mohamed)**: خصم مجموعة العميل الدائم وقاعدة الخصم
الشرطية اليدوية (Happy Hour/بروموشن، `discount_engine.py` — اتسابت من غير أي تعديل) **ميتجمعوش**
لما الاتنين ينطبقوا على نفس الطلب — الأعلى قيمة بس هو اللي يتطبّق فعليًا (`dining.services.
_resolve_order_discount`)، اختيار محافظ بيعكس نفس فلسفة `discount_engine.calculate_discount`
نفسها (بتاخد أعلى priority بين قواعدها، مش بتجمعهم). خصم الشاطئ (`beach_transactions.
discount_amount` عمود جديد، `total_amount` بقى صافي بعد الخصم من دلوقتي) تلقائي بالكامل، مفيش نوع
خصم منافس هناك. **باج حقيقي اتصلح أثناء الربط**: `dining.services.add_items_to_order` كان بيسيب
`discount_amount` زي ما هو من غير أي إعادة حساب لما الـ subtotal يتغيّر (`void_order_item` كان
بيعمل ده صح للقاعدة الشرطية بس، مش لخصم المجموعة الجديد) — الاتنين بقوا بيمرّوا على نفس
`_resolve_order_discount` دلوقتي. Migration `561c30b7cc11`. فرونت إند: لوحة مجموعات (قائمة لمدير+،
إضافة/تعديل لـ admin+) + عمود اختيار مجموعة لكل عميل (مدير+) في `CRMView.vue`.

**Batch 3 — ربط مركز التكلفة بدفتر اليومية + تفعيل تسلسل الحسابات**: `JournalLine.cost_center_id`
(FK nullable) — بيتوسم وقت الترحيل نفسه في كل نقطة ترحيل حقيقية (مش يُستنتج بعدين): dining (إيراد +
شحنة فوليو + عكس مرتجعين، REST/CAFE حسب `Outlet.outlet_type`)، beach (الأربع قيود، BEACH ثابت)،
pms (checkout + Night Audit، ROOM)، timeshare (دفعة أولى + تحصيل قسط، TS)، وinventory's COGS
(أول توسيم مصروف في المشروع كله، مموّل من dining's outlet resolution وقت الاستهلاك).
`finance.services.get_cost_center_report` اتعمله rewrite كامل — بيقرأ `journal_lines.
cost_center_id` مباشرة (إيراد **ومصروف**، مدين ودائن) بدل الخلطة القديمة بين قراءة حساب 4100
من الدفتر ومسح مباشر لجداول `beach_transactions`/`folio_charges`/`timeshare_installments`. الدوال
الميتة اللي كانت بتغذي المسار القديم (`sum_beach_revenue`, `sum_timeshare_revenue`,
`sum_revenue_account_by_code`, `list_folio_charges_by_type_with_currency`,
`list_folio_charges_by_outlet_family_with_currency`) اتشالت بالكامل. **قرار نطاق موثّق**: قيود
قديمة اتُرحّلت قبل الدفعة دي مالهاش `cost_center_id` (NULL) — **مفيش backfill رجعي** (محتاج تتبّع
كل قيد قديم لمصدره الأصلي عبر `source_id`، تعقيد مش مبرر لبيانات تطوير/ما قبل الإطلاق)، موثّق في
كود `CostCenterReport`. تفعيل `Account.parent_id` (كان موجود في الـ schema من زمان، صفر استخدام):
4 حسابات أب بمستوى واحد بس (الأصول 1000/الخصوم 2000/الإيرادات 4000/المصروفات 5000 — البحث نصح
صراحةً بعدم بناء هرمية أعمق لشجرة 22 حساب)، `seed.py` بيزرعهم ويربط أي حساب قديم من غير أب بأثر
رجعي (idempotent)، ونفس الـ backfill بيحصل كـ data migration لقواعد بيانات مزروعة بالفعل. `GET
/finance/reports/trial-balance?group_by_parent=true` (اختياري) بيجمّع الحسابات تحت رؤوسها بدل سطر
لكل حساب فردي. Migration `0921acaccd1f` (تسلسل واحد مع migration الأعمدة، اتأكد منه على Postgres
حقيقي بسلسلة كاملة + بيانات موجودة مسبقًا من غير أب + دورة downgrade/upgrade idempotent) —
`python -m app.seed` اتأكد منه end-to-end بعدها على Postgres حقيقي منفصل: "Chart of accounts
seeded (22 accounts)" وكل الحسابات الـ22 مربوطة صح بآبائها الأربعة.

**النتيجة النهائية**: `pytest tests/ -v` → **1748 اختبار، كلهم عدّوا** (كان 1721 قبل هذه الجولة).
`pnpm --filter el-kheima type-check`/`build` نضاف بعد كل دفعة. كل الـ 3 migrations
(`8a78528e9403`, `561c30b7cc11`, `0921acaccd1f`) اتأكد منها فعليًا على Postgres حقيقي في قواعد
بيانات معزولة مؤقتة (مش الـ `resort_os` المشتركة) — إنشاء→تحقق→حذف لكل واحدة، بما فيها دورة
downgrade/upgrade كاملة. `alembic heads` فضل head واحد طول الوقت.

---

## 🔍 اللي اتعمل يوم 2026-07-13 — Operations & Control Layer Batch 4: تحقق شامل من رؤية سجل التدقيق

مراجعة أمنية منهجية (مش grep سطحي) عبر كل endpoint/schema يقدر كاشير/نادل يوصله — الهدف: يتأكد إن
سجل التدقيق (مين عمل إيه وإمتى) مقفول على مدير+ فعليًا في كل مكان، مش بس في `/audit-logs` نفسها.

**النتيجة**: `GET /audit-logs` كانت فعلاً مقفولة صح من الأول (`get_manager_user`، level≥60) — اتضاف
اختبار كاشير صريح (`test_cashier_cannot_view_audit_logs`) فوق اختبار النادل الموجود، وكذلك
`GET /finance/shifts/{id}/cash-movements` (Batch 2) مقفولة صح.

**لكن المراجعة كشفت ثغرة حقيقية مختلفة تمامًا، مش كانت متوقعة**: `GET /finance/shifts/{id}/report`
و`GET /finance/shifts/{id}/report/pdf` كانوا مقفولين على `get_cashier_user` بس **من غير أي تحقق
ملكية خالص** — يعني أي كاشير كان يقدر يشوف (ويحمّل PDF) تقرير نهاية وردية أي كاشير تاني (مبيعات/فرق
كاش/هويته) بمجرد تخمين رقم `shift_id` تصاعدي، بدون أي PIN أو تحقق. ده تناقض واضح مع
`GET /finance/shifts/{id}/invoices` (نفس الموديول، endpoint مجاور) اللي كان بالفعل بيفرض "كاشير يشوف
وردية نفسه بس" (S-02) — الاثنين لازم يكون عندهم نفس القيد بالظبط ومكانوش. **اتصلح**: `services.
build_shift_end_report`/`generate_shift_end_report_pdf` بقوا ياخدوا `requesting_user` اختياري (`None`
= نداء داخلي موثوق زي `close_shift` بينادي عليها لملخّص العملات) وبيفرضوا نفس قيد `list_shift_
invoices` بالظبط. اتأكد بتست حقيقي بيثبت الباج الأول (200 لكاشير تاني قبل الإصلاح) وبعدين يتأكد من
الإصلاح (403).

**نتيجة الفحص التفصيلي لباقي الـ endpoints (`approved_by`/`voided_by`/`created_by` عبر كل الموديولات)**:
- `dining.OrderItemRead.voided_by` (رقم اليوزر اللي ألغى صنف) موجود في استجابة `GET /dining/orders`
  و`GET /dining/orders/{id}` — الاتنين متاحين لكاشير/نادل (زي المتوقع، جزء طبيعي من شغل الـ POS
  اليومي). **قرار موثّق — مش باج**: ده مختلف جوهريًا عن سجل تدقيق قابل للبحث (`/audit-logs` بيسمحلك
  تسأل "كل حاجة عملها اليوزر X" عبر أي entity) — ده مجرد تفصيلة داخل طلب واحد الكاشير أصلاً مسموحله
  يشوفه كجزء من شغله (زي ما شاشة POS حقيقية بتعرض "مين ألغى الصنف ده" للمساءلة الفورية). كمان
  تأكدنا: مفيش أي شاشة فرونت إند فعليًا بتعرض `voided_by` ده للمستخدم (`DiningOrderDetailModal.vue`
  الـ TS interface بتستخدم `voided_reason` بس، مش `voided_by`) — موجود في الـ JSON الخام بس مش
  ظاهر في أي UI. **لو Mohamed حابب يشيله من الـ schema خالص، ده تعديل بسيط ومنفصل — مذكور هنا
  للشفافية بس مش هيتغيّر من غير طلب صريح.**
- `finance.CheckRead.created_by` و`beach.BeachTransactionRead.cashier_id` — نفس الفئة: "مين سجّل
  الحركة دي" (تعاون تشغيلي عادي بين الموظفين)، مش "مين وافق على إجراء حسّاس". مفيش `approved_by` في
  أي منهم أصلاً — الاتنين متسقين مع باقي النظام.
- `inventory.StockCountRead.approved_by` — **ملاحظة منفصلة تستاهل قرار Mohamed لاحقًا**: `GET
  /inventory/stock-counts` مقفول على `get_current_active_user` بس (أي موظف نشط، حتى مستوى "employee"
  = 20) — أوسع بوابة في المشروع كله لعرض بيانات فيها `approved_by`. ده موديول مخزون مختلف تمامًا عن
  نطاق الكاشير/الكاش اللي Mohamed حدده في الدفعات دي، فاتسيب زي ما هو من غير تغيير — بس مذكور هنا
  بشفافية لو حابب مراجعته في دفعة منفصلة مستقبلية.

- **الاختبارات** — 3 اختبار جديد: `test_cashier_cannot_view_audit_logs` (كاشير صريح على `/audit-logs`)،
  `test_cashier_cannot_view_other_cashiers_shift_report` (الثغرة المكتشفة، report + PDF)،
  `test_manager_can_view_any_cashiers_shift_report` (تأكيد إن الإصلاح ماكسرش وصول المدير+). =
  **1718 اختبار إجمالي، صفر فشل**.

---

## 🕵️ اللي اتعمل يوم 2026-07-13 — Operations & Control Layer Batch 3: كشف الاحتيال (Fraud Detection)

`app/tasks/fraud_tasks.py` جديد — Celery periodic task (`scan_for_fraud_signals`، كل 15 دقيقة) بيفحص
نشاط كل كاشير خلال نافذة زمنية دوّارة ضد 4 عتبات، ويبعت تنبيه واتساب حقيقي للإدارة
(`core.kernel.whatsapp.notify_admin` — نفس آلية كل التنبيهات التانية، مفيش قناة جديدة) لما أي عتبة
تتخطى، مع منع تكرار نفس التنبيه لنفس الكاشير خلال 24 ساعة (Redis cache، نفس بنية
`revoke_user_tokens`).

**قرار Mohamed الصريح**: "اعمل حقيقي" (مش أرقام توضيحية) بس من غير ما يحدد الأرقام نفسها — قرار
هندسي مفوَّض بالكامل. الأرقام المختارة والمنطق موثّقة في `app/core/config.py` وفي تقرير الدفعة دي:

| القاعدة | العتبة الافتراضية | النافذة | المصدر |
|---|---|---|---|
| مرتجعات كتير | 15 مرتجع | 60 دقيقة | رقم الخطة نفسه (`OPERATIONS_CONTROL_LAYER_PLAN.md` §3.5) |
| إلغاء أصناف كتير | 15 إلغاء | 60 دقيقة | نفس رتبة المرتجع (فئة خطر مماثلة، الخطة مقترحتش رقم منفصل) |
| محاولات خصم كتير | 10 محاولة | 60 دقيقة | أقل من الباقي عمدًا — بعد Batch 1 الكاشير صفر صلاحية خصم أصلاً، فأي تكرار محتاج انتباه أبكر |
| فتح الدرج بدون بيع | 20 فتحة | 24 ساعة | رقم الخطة نفسه ("20+ drawer-opens/day") |

كل رقم في الجدول ده **Setting قابل للتعديل** (`FRAUD_REFUND_COUNT_THRESHOLD` وأخواتها في
`app/core/config.py`) — مفيش رقم متسمّر في الكود.

**قرار تصميمي محافظ صريح**: العتبات "عدد حركات خلال نافذة" مش "نسبة مئوية حقيقية" (زي "20% من
الطلبات اتلغت"). حساب نسبة حقيقية محتاج مقام واضح (إجمالي الطلبات في نفس النافذة؟ في نفس الوردية؟)
Mohamed ما حددهوش صراحةً — بدل التخمين، اخترنا القاعدة الأبسط والأوضح (عدّ مطلق)، سهلة التوسيع لاحقًا
لنسبة مئوية حقيقية لو الحاجة ظهرت. موثّق في كود `fraud_tasks.py` نفسه.

- **المصدر**: `AuditLog` (مرتجع/إلغاء/محاولة خصم — نفس السجلات اللي Batch 1/2 كتبوها بالفعل) +
  `CashMovement` (فتح الدرج — Batch 2). **مفيش جدول تدقيق تاني** — نفس تحذير الخطة الصريح ضد "second
  audit log".
- **الاختبارات** — `find_fraud_signals()` هي المنطق الأساسي القابل للاختبار (استعلامات + مقارنة
  عتبات، مفيش Celery/Redis/واتساب) — 7 اختبار حد فاصل (عتبة بالظبط، تحت العتبة، خارج النافذة الزمنية،
  الأنواع الأربعة، أكتر من كاشير) + اختبار للـ task الكامل (نداء واتساب حقيقي mocked + منع التكرار
  عبر نداءين متتاليين) = **8 اختبار جديد، 1715 اختبار إجمالي**. ملاحظة تصحيح مهمة أثناء الكتابة:
  الاستعلامات عالمية (مش مقيّدة بفرع) عمدًا، والـ DB في بيئة الاختبار بتحافظ على البيانات المُلتزَمة
  (`commit()`) بين التستات (`db.rollback()` بيلغي بس الغير-محفوظ) — التستات بقت تفلتر على المستخدمين
  اللي أنشأتهم هي نفسها بدل افتراض جدول فاضي عالميًا، بدل افتراض عزل كامل مش موجود فعليًا.
- **جدولة**: `celery_app.py` beat_schedule — `crontab(minute="*/15")`. نوافذ الفحص دقايق/ساعات مش
  أيام (عكس باقي الـ tasks اللي بتشتغل مرة واحدة يوميًا)، فالجدولة لازم تكون متكررة كفاية عشان
  النافذة الدوّارة تتغطى.

---

## 💰 اللي اتعمل يوم 2026-07-13 — Operations & Control Layer Batch 2: Cash Control ledger

جدول جديد `CashMovement` (`finance/models.py`) — حركات نقدية يدوية على درج الوردية منفصلة تمامًا عن
أي حركة بيع: `cash_in`/`cash_out`/`petty_cash`/`safe_drop`/`drawer_open`/`correction`. Migration
`23e4eca09fe0` (جدول واحد بس + 3 indexes — الـ autogenerate الخام كان مقترح DROP TABLE لجداول
restaurant/cafe القديمة (أرشيف عمدًا) + drop/create index مش متعلّقين بالتغيير خالص، اتشالوا يدويًا
زي ما موثّق في `alembic/env.py:37-46`؛ `alembic upgrade head` اتجرّب فعليًا على Postgres حقيقي، صفر
انحراف بعدها غير الأرشيف المعروف).

**قرار موثّق واضح — توسيع نطاق قرار Mohamed**: هو سمّى "التصحيح" (correction) صراحةً كمحتاج موافقة
PIN مدير+ دايمًا. الدفعة دي وسّعت الحماية دي لتشمل الأنواع الستة كلها (`cash_in`/`cash_out`/
`petty_cash`/`safe_drop`/`drawer_open` كمان) — نفس فئة الخطر بالظبط (حركة نقدية يدوية بدون تتبّع بيع
مقابلها)، وبيدعم القرار ده بحث الخطة (`OPERATIONS_CONTROL_LAYER_PLAN.md`) اللي لاحظ إن نظام Click
القديم كان بيسجّل `Safe_History.IsApproved` على **كل** حركة، مش بس التصحيحات. **ده اختيار محافظ
صريح، مش افتراض بلا مبرر** — لو Mohamed حابب يضيّق النطاق لبس "correction"، القرار سهل الرجوع فيه
(باراميتر واحد `min_approver_level` بيتغيّر في `record_cash_movement`).

- **الباك إند** — `finance.services.record_cash_movement` بينادي
  `core.services.resolve_pin_approval(min_approver_level=60)` **قبل** أي كتابة، بغض النظر عن قيمة
  المبلغ (حتى `drawer_open` بمبلغ صفر — الإشراف على *محاولة* التسجيل نفسها زي void/apply_discount
  بالظبط). `AuditLog(action=f"cash_movement_{movement_type}")` بيتسجّل مع كل حركة (`approved_by`
  منفصل عن `performed_by`). `POST /finance/shifts/{id}/cash-movements` (كاشير+، `drawer_open` هنا
  بالظبط زي ما الخطة طلبت — بدون أي بيع مرتبط) و`GET /finance/shifts/{id}/cash-movements` (مدير+
  فقط، **بدون** أي مسار موافقة PIN بديل — زي `/audit-logs` بالظبط، راجع Batch 4 تحت).
- **باجين حقيقيين اتكشفوا واتصلحوا أثناء كتابة التستات** (مش نظري): (1) `crud.create_cash_movement`
  كان بيتلقى `approved_by` من الخدمة بس منساش يحطه على صف `CashMovement` نفسه — الـ `AuditLog` كان
  بيسجّله صح، بس عمود `CashMovement.approved_by` كان فاضل `NULL` دايمًا حتى بعد موافقة PIN صحيحة.
  (2) `list_cash_movements` كان بيرتّب بـ `created_at.desc()` بس — حركتين في نفس المعاملة (نفس
  المللي ثانية) كانوا بيرجعوا بترتيب غير محدد، مش "الأحدث فعلاً الأول". اتصلح بإضافة `id.desc()`
  كـ tiebreak حتمي.
- **الفرونت إند** — `CashControlPanel.vue` جديد (نموذج نوع حركة/مبلغ/سبب + `PinGuardModal.vue`
  `min-level={60}` قبل الإرسال دايمًا، نفس نمط void/discount بالظبط) داخل `ShiftDashboardView.vue`
  جنب `ShiftPanel` مباشرة. سجل الحركات (تاريخ من نفّذ/وافق) بيظهر بس لمدير+ (`auth.hasRole('manager')`)
  — كاشير يقدر يسجّل حركة (بموافقة PIN) بس مايشوفش تاريخ الحركات، زي الـ API بالظبط.
- **الاختبارات** — 10 اختبار جديد (service-level: مدير مؤهّل بنفسه، كاشير محتاج PIN للتصحيح وحتى
  drawer_open بمبلغ صفر، PIN صحيح بيعدّي ويسجّل AuditLog+CashMovement.approved_by، وردية مقفولة
  بترفض، ترتيب السجل الأحدث الأول؛ HTTP-level: 400 لكاشير من غير PIN، 201 لمدير بنفسه، 201 لكاشير
  بـ PIN مدير صحيح، 403 لكاشير على GET بينما 200 لمدير) = **1707 اختبار إجمالي، صفر فشل** (كان
  1697). `pnpm run type-check:all`/`build:all` نضاف.

---

## 🔐 اللي اتعمل يوم 2026-07-13 — Operations & Control Layer Batch 1: موافقة PIN على الخصم

راجع `OPERATIONS_CONTROL_LAYER_PLAN.md` (جذر المشروع) للخطة الكاملة والـ 6 دفعات. Batch 1 فقط —
باقي الدفعات (Cash Control ledger، كشف احتيال، تحقق شامل من ظهور سجل التدقيق) شغل لاحق منفصل.

**قرار Mohamed الصريح (2026-07-13)**: الكاشير صفر صلاحية خصم خالص — **مفيش** جدول درجات نسب مئوية
(الخطة الأصلية كانت مقترحة tiers حسب %، اتلغت). أي خصم من مستوى أقل من مدير (level < 60) محتاج PIN
مدير/محاسب حاضر فعليًا، **بغض النظر عن نسبة الخصم أو حتى وجود قاعدة سارية من الأساس** — الموافقة
على *محاولة* التطبيق نفسها، مش على نتيجتها.

- **الباك إند** — `POST /dining/orders/{id}/discount` (المسار الوحيد المتبقي بعد حذف
  `restaurant`/`cafe`) بقى ياخد body اختياري (`ApplyDiscountRequest`: `approver_user_id`/
  `approver_pin`، `dining/schemas.py`). `dining.services.apply_order_discount` بقى ياخد
  `acting_user_level`/`approver_user_id`/`approver_pin`/`applied_by` وينادي
  `core.services.resolve_pin_approval(min_approver_level=60)` **قبل** حساب أي قاعدة خصم — نفس
  الدالة المركزية اللي بيستخدمها `void_order_item` بالظبط، مفيش نظام موافقة موازي. `AuditLog` جديد
  بـ `action="apply_discount"` بيتسجّل في كل مرة (نجحت أو رُفضت التحقق) — `user_id` = مين حاول
  التطبيق، `approved_by` = مين وافق (`None` لو مدير+ نفّذ بنفسه).
- **الفرونت إند** — `useOrderDiscount.ts` بقى ياخد `approver` اختياري (نوع `DiscountApprover`)
  ويبعته للـ API. `DiningOrderDetailModal.vue` و`UnifiedPOSView.vue` (شاشة POS الافتراضية دلوقتي —
  التعليق القديم اللي بيقول "مش الشاشة الافتراضية" كان قديم من قبل الـ cutover، اتصلح) بقى زرار
  "🏷️ تطبيق خصم" بيفتح `PinGuardModal.vue` (`min-level={60}`) الأول — بيتأهّل بصمت لمدير+ (مفيش UI
  يظهر خالص) وإلا بياخد اختيار مدير + PIN، بالظبط زي إلغاء الصنف (void) في نفس الشاشتين.
- **الاختبارات** — 9 اختبار جديد (service-level: حد الصلاحية بالظبط عند 60، رفض من غير PIN حتى لو
  فيه قاعدة سارية، PIN صحيح بيعدّي ويسجّل AuditLog بـ `approved_by` منفصل عن `user_id`، PIN غلط
  بيترفض؛ HTTP-level: 400 لكاشير من غير PIN، 200 لمدير بنفسه، 200 لكاشير بـ PIN مدير صحيح، 400 بـ
  PIN غلط) — `pytest tests/ -v` → **1697 اختبار، صفر فشل** (كان 1688). `pnpm run type-check:all`
  و`build:all` نضاف.
- **مقياس أمني تصميمي متعمد**: الموافقة مطلوبة على *محاولة* التطبيق نفسها حتى لو مفيش قاعدة خصم
  سارية أصلاً هتنطبق (النتيجة صفر) — قرار محافظ (fail-closed) بدل محاولة تخمين نية الكاشير، ومطابق
  حرفيًا لسلوك `void_order_item` الموجود بالفعل (بيطلب PIN بغض النظر عن قيمة الصنف الملغي).

---

## 🍽️ اللي اتعمل يوم 2026-07-12 — موديول `dining` الموحّد (Batch A: D-01 → D-04)

دمج المطعم/الكافيه في موديول `dining` واحد (wagdy.md "المرحلة الثالثة — المشروع الكبير")، بنموذج
**Outlet** زي Foodics/Toast — هذا الـ commit فقط النطاق المُتفَق عليه (D-01 → D-04)، **مش** حذف
`restaurant`/`cafe` ولا تحويل الفرونت إند (ده D-05 → D-08، مؤجَّل عمدًا، راجع
`DINING_CUTOVER_PLAN.md` الجديد في جذر المشروع).

- **D-01 — `app/modules/dining/models.py`** (14 جدول جديد، `dining_*`) — superset حقيقي لـ
  `restaurant.models` + `cafe.models`: `Outlet` (`outlet_type` نص مفتوح بدون CHECK constraint —
  outlet جديد زي بار المسبح = صف جديد بس، صفر migration؛ `revenue_account_code` بديل حسابات
  4200/4400 الثابتة)، `DiningItem` (عمود `station` إجباري على الكل من الأساس — نفس الباج اللي كان
  في `CafeItem` قبل الإصلاح، هنا مستحيل يتكرر)، `DiningItemVariant`/`DiningItemVariantRecipeLine`
  (وصفة مستقلة تمامًا زي `MenuItemVariant` الأصلي، **مش** عمود `variant_id` على جدول وصفة مشترك —
  نفس القرار المعماري في CLAUDE.md §18 "Variants حقيقية")، و`DiningKitchenTicket.order_id` بقى
  **FK حقيقي** على `dining_orders` (تحسين عن الأصل — `KitchenTicket.order_id` القديم كان Integer
  خام لأنه بيشاور على جدولين مختلفين حسب `module`). كل الكيانات المنسوخة من D-02 عندها
  `legacy_module`/`legacy_id` (unique) — **مش** PK حرفي محفوظ، لأن `restaurant.Order.id` و
  `cafe.CafeOrder.id` sequences منفصلة بتتصادم طبيعيًا.
- **D-02 — Migration `0bd6f63e5446`** — بيعمل الجداول ثم **ينسخ** (مش ينقل) كل بيانات
  `restaurant`/`cafe` الموجودة فعليًا بـ SQL خالص (`INSERT...SELECT` مترابط عبر
  `legacy_module`/`legacy_id`، `NOT EXISTS` على كل سطر عشان يفضل idempotent لو اتكرر تشغيله). قبل
  الكتابة: backup حقيقي (`scripts/backup_db.sh`) + restore-verified (`COUNT(*)` مطابق حرفيًا) على
  6 جداول. الـ migration نفسها اتبنت واتأكد منها بالكامل على قاعدة بيانات تجريبية منفصلة (seed
  واقعي: فئة/صنف/وصفة/متغيّر/وصفة متغيّر/إضافات/طلب مدفوع فيه إضافة/طلب معلّق بدون طاولة/طلب كافيه
  مرتجع بالكامل) — تطابق عدد الصفوف حرفيًا، صحة كل العلاقات، إعادة تشغيل من غير تكرار، ودورة
  downgrade↔upgrade نضيفة. التحقق ده بقى **pytest حقيقي وقابل لإعادة الاستخدام**
  (`backend/tests/test_dining_migration.py`، Postgres-only، skip تلقائي لو
  `DINING_MIGRATION_TEST_ADMIN_URL` مش موجود — صفر أثر على `pytest tests/` العادي).
- **D-03 — `dining/{crud,schemas,services}.py`** — محرك طلبات واحد (create/hold/sync
  offline/add-items/status transitions/void/refund/discount/food-cost report) بدل نسخة
  restaurant + نسخة cafe متطابقتين تقريبًا. **الإصلاح المطلوب فعليًا**: حسابات الإيراد الثابتة
  `"4200"`/`"4400"` بقت `outlet.revenue_account_code` — خاصية على سجل الـ outlet، مش literal في
  الكود. كل باقي المنطق (خصم مخزون بنفس أولوية وصفة→ربط 1:1→تجاهل، PIN موافقة عبر
  `core.services.resolve_pin_approval` الموجودة، محرك الخصم `resort_os/discount_engine.py` غير
  مُلمَس، تجميع تقرير تكلفة الطعام بـ `(item_id, variant_id)`) اتنقل بنفس السلوك بالظبط.
- **D-04 — `dining/api/router.py`** — موحّد على `/api/v1/dining/outlets/{id}/...` (50 مسار)، KDS
  ticket feed موحّد عبر الـ outlets كلها (`outlet_id` اختياري = "كل المنافذ على شاشة واحدة"، الرؤية
  اللي طلبتها مذكرة Mohamed المعمارية). **قرار موثّق صراحةً**: مفيش alias حرفي على مسارات
  `/restaurant`/`/cafe` القديمة — الروترين القديمين متلمسوش خالص (لسه بيقروا/يكتبوا في
  `orders`/`cafe_orders` الأصليين زي ما هما)، فمفيش حاجة تحتاج alias أصلاً. اتأكد بـ 3 طرق مستقلة:
  220 اختبار restaurant/cafe عدّوا من غير أي تعديل، route dump كامل (493 مسار: 47 restaurant + 41
  cafe + 50 dining) بصفر تصادم، واختبارات HTTP جديدة صريحة (`TestOldUrlsStillWork`) بتضرب
  `/restaurant`/`/cafe` مباشرة بعد إضافة dining.
- **45 اختبار جديد** (`test_dining.py` 32 + `test_dining_http.py` 13) + 3 اختبار migration
  اختياري = 1834 → 1879 اختبار عادي، صفر رجوع.
- **`DINING_CUTOVER_PLAN.md`** (جذر المشروع) — المقترح المكتوب لـ D-05 (تحويل analytics/finance
  للقراءة من `dining` بدل `restaurant`+`cafe`) بدل تنفيذه بدون مراجعة — نفس مبدأ فجوة إيراد الغرفة
  في §18 بند 0: قرار بأثر مالي حقيقي يستاهل مراجعة صريحة مع Mohamed، مش تعديل عابر وسط دفعة تانية.

---

## 🍽️ اللي اتعمل يوم 2026-07-12 — موديول `dining` Batch B: free-text extra-group + أول POS/admin/KDS حقيقي

دفعة تانية إضافية بالكامل جنب Batch A فوق — **مفيش لمس** لـ `restaurant/`, `cafe/`, `analytics/`,
`finance/`، ولا لمصدر بيانات أي تقرير موجود (قرار الـ cutover الكامل D-05→D-08 لسه محتاج مراجعة
مخصصة مع Mohamed، مش جزء من الدفعة دي — راجع `DINING_CUTOVER_PLAN.md`).

- **Backend — `group_type` على `DiningItemExtraGroup`** — فجوة حقيقية اتكشفت بمقارنة نظام "Click"
  القديم اللي المنتجع استخدمه فعليًا: نظام الإضافات كان pick-list بس (اختيارات محدودة)، من غير طريقة
  للتعبير عن prompt نصي حر على الصنف (مثال حقيقي من النظام القديم: "كام سمكة؟"). اتضاف
  `group_type` ("pick_list"|"text"، افتراضي pick_list = صفر تغيير سلوك لأي مجموعة موجودة)،
  `DiningOrderItemExtra.text_value` (تخزين الإجابة، snapshot زي باقي الإضافات)، و
  `OrderItemCreate.extra_texts` (`group_id` → نص) عبر `_resolve_extras` في `create_order` و
  `add_items_to_order` الاتنين — مجموعة نصية `min_select>=1` بترفض بـ400 لو الإجابة فاضية، `min_select=0`
  اختيارية. Migration `f4a7c9b2d105` (down_revision `0bd6f63e5446`، head واحد اتأكد منه). النطاق
  محصور بالكامل جوه `app/modules/dining/` — `restaurant`/`cafe` معندهمش المفهوم ده أصلاً ولا هيتلمسوا.
  6 اختبارات جديدة (`TestExtraGroups` في `test_dining.py`: pick-list سعر إضافي، نص إجباري مرفوض،
  نص مخزّن صح وميزودش السعر، نص اختياري، مسار `add_items_to_order`) = **1927 اختبار إجمالي، صفر
  رجوع** (`pytest tests/ -v` كامل اتشغّل بعد كل حاجة، مش رقم قديم).

- **Frontend — أول شاشات حقيقية ضد `dining` API + أول استخدام حقيقي لـ `@resort-os/ui`** (29 مكوّن،
  مفيش شاشة كانت بتستخدمهم قبل كده — Design System كان بنية تحتية بس من غير أي عرض حي):
  - `frontend/apps/el-kheima/src/views/pos/UnifiedPOSView.vue` — الـ "POS سريع" المطلوب: تابات
    order-type حقيقية (`dine_in`/`takeaway`/`delivery`/`room_service`) بلابل عربي حقيقي (مش أخطاء
    إملائية النظام القديم "دايت-إن" إلخ)، كل نوع طلب بيعرض بس الحقول اللي تخصه (طاولة لـ dine_in،
    عنوان/رقم غرفة لـ delivery/room_service، تيك أواي من غير أي حقل زيادة). خريطة طاولات مجمّعة
    بصريًا حسب `VenueTable.section` (بحث Zone/section من "Click" القديم — تجميع مسطّح، مش hierarchy
    كامل، عمدًا). مودال إضافات/متغيّرات (`DiningExtrasModal.vue`) بما فيه النوع النصي الجديد. حدود لمس
    48px + اختصارات لوحة مفاتيح (`/` بحث، Enter إرسال، Esc إغلاق/مسح) — نفس نمط
    `RestaurantPOSView.vue` القائم.
  - `frontend/apps/el-kheima/src/views/admin/DiningMenuView.vue` — إدارة منافذ/فئات/أصناف (بما فيها
    مجموعات الإضافات بنوعيها) وطاولات، أول Drawer/DataTable/Tabs حقيقيين من الـ Design System.
  - `frontend/apps/el-kheima/src/views/kds/DiningKDSView.vue` — KDS موحّد بيوجّه حسب
    `DiningItem.station` الحقيقي (نفس نمط CLAUDE.md §13 بند ⓭)، موحّد عبر كل الـ outlets افتراضيًا.
    **مؤجَّل عمدًا**: bump على مستوى الصنف الواحد (زي `KitchenDisplayView.vue`) — `dining` router
    معندهوش `PATCH .../items/{id}/status` لسه، بس bump على مستوى التذكرة كله (pending→in_progress→done)
    شغال بالكامل.
  - `DiningOrderDetailModal.vue` بيعيد استخدام `PinGuardModal.vue` الموجود لموافقة إلغاء الصنف —
    **مفيش نظام موافقة موازي اتعمل**. المرتجع (refund) مش محتاج PIN إضافي (الباك إند أصلاً بيقفله على
    مدير+ بس، مفيش مسار تصعيد لدور أقل زي الإلغاء).
  - Routes جديدة بس (`/pos/dining`، `/admin/dining-menu`، `/kds/dining`) — `requiredRole: 'manager'`
    مضبوطة صراحةً على الـ route نفسها حتى لو الـ layout الأب أوطى (زي `/pos` بتاعت كاشير)، عشان
    الشاشات دي **متظهرش خالص** في أي nav بيشوفه نادل أو كاشير عادي (كل عنصر في FieldLayout's/
    KioskLayout's nav array مفيهوش role filter أصلاً — أي إضافة هناك كانت هتغيّر workflow كل
    كاشير/طباخ يوميًا). الوصول الوحيد: قسم "دايننج موحّد (تجريبي)" جديد في `BackOfficeLayout.vue`
    (مدير+ بس). **الشاشات الحالية اللي الموظفين بيستخدموها كل يوم
    (`RestaurantPOSView.vue`/`CafePOSView.vue`/`KitchenDisplayView.vue`/`BarDisplayView.vue`) متغيّرتش
    خالص — نفس المسارات، نفس الـ nav، صفر تغيير مرئي.**

- **التحقق الفعلي (2026-07-12، حي مش تخمين)**: `pytest tests/ -v` → 1927 اختبار كلهم عدّوا (3 skip
  Postgres-only زي العادة). `alembic upgrade head` اتجرّب فعليًا على Postgres حقيقي (migration
  `f4a7c9b2d105`). `pnpm --filter el-kheima type-check`/`build` و`pnpm --filter public build` الاتنين
  نضاف. **End-to-end حي على سيرفرين منفصلين** (backend 8006 + frontend 3011، ضد نفس Postgres/Redis
  المشتركين، منفصلين عن سيرفرات main checkout 8005/3001 عشان ميتأثروش): تسجيل دخول مدير حقيقي، إنشاء
  outlet/item/مجموعة نصية عبر الـ API، طلب من غير الإجابة المطلوبة رجع 400 بالرسالة الصح، طلب بالإجابة
  نجح واتخزّنت `text_value` صح مع سعر محايد، انتقال `in_kitchen` ولّد تذكرة على المحطة الصحيحة (grill،
  مش قيمة ثابتة)، الدفع اتم صح وقيد الإيراد اترحّل. Playwright browser walkthrough حقيقي (مش curl بس):
  تسجيل دخول → `/admin/dining-menu` → `/pos/dining` → `/kds/dining`، أكّد نص nav الجديد ظاهر لمدير،
  الشاشات التلاتة بتحمّل بيانات حقيقية من غير أي JS/console error (التذكرة الحقيقية اللي اتعملت من
  التست ظهرت فعليًا في شاشة KDS، الصنف بعلامة "إضافات" ظهر في الـ POS). **ملاحظة بيئة**: Playwright
  headless في السانبوكس ده مابيرندرش screenshots بصريًا صح (مفيش فونتات/GPU فعّالة) رغم إن DOM/
  innerText والـ API network calls كلهم اشتغلوا صح 100% — التفاعل الكامل بالماوس (فتح مودال الإضافات
  فعليًا، إتمام طلب من واجهة المتصفح) لسه محتاج تأكيد بصري على جهاز حقيقي. بيانات الاختبار المؤقتة
  (outlet/item/order/journal entry) اتمسحت بالكامل من قاعدة البيانات المشتركة بعد التأكد — مفيش أي أثر
  باقي على بيانات main checkout الحية.

- **مؤجَّل عمدًا لهذه الدفعة** (مش نسيان — قرار نطاق واضح): offline queue parity مع
  `useOfflineQueue` (المطعم/الكافيه/الشاطئ الاتلاتة بيستخدموها فعليًا في الإنتاج — تمديدها لمسارات
  `dining` الـ outlet-scoped يحتاج path-templating حقيقي جوه composable مشترك، خطر على 3 شاشات POS
  شغالة عشان شاشة preview واحدة)، KDS bump على مستوى الصنف الواحد (يحتاج endpoint backend جديد)،
  course firing، kitchen timer، customer display.

---

## ✅ اللي اتعمل يوم 2026-07-13 — Cutover كامل D-05 → D-08: حذف `restaurant`/`cafe` نهائيًا

إذن صريح من Mohamed (بالعامية المصرية): يتحول التقرير المالي على `dining`، تبقى شاشاته هي
الافتراضية للاستخدام اليومي، يتاخد نسخة احتياطية من كل حاجة، وبعدين يتحذف `restaurant`/`cafe` من
المشروع بالكامل. اتنفّذ على 6 دفعات، كل دفعة بـ commit مستقل و`pytest tests/ -v` أخضر 100% بعدها
مباشرة — مش مؤجَّل للآخر.

**نقاط الرجوع/الأمان (قبل أي حذف فعلي):**
- Git tag: `pre-dining-cutover-2026-07-12`
- نسخة `pg_dump` حقيقية في `backups/`
- نسخة مرجعية مسطّحة كاملة في `/home/wego/projects/restaurant-os/reference-from-resort-os-2026-07-12/`
  (مشروع منفصل تمامًا عن resort-os — احتياط ثالث مستقل)
- **الجداول القديمة (`menu_items`, `menu_categories`, `restaurant_orders`, `cafe_items`, `cafe_orders`,
  ...) لسه موجودة فعليًا في Postgres — مش متحذوفتش.** الكود بس اللي اتشال. أي migration جديدة
  autogenerate محتاجة مراجعة يدوية عشان تتشال أي `DROP TABLE` statement لجداول restaurant/cafe لو
  ظهرت غلط (تحذير صريح مُضاف في `alembic/env.py`).

### Batch 1 — سد فجوات تكافؤ حقيقية قبل أي حاجة تانية
`dining` كان ناقص 3 حاجات كان `restaurant`/`cafe` عندهم فعليًا:
1. نقل طاولة لطلب موجود (`services.transfer_order_table`، `PATCH /dining/orders/{id}/transfer`)
2. نافذة إتاحة الصنف بالوقت (`DiningItem.available_from_time`/`available_until_time`،
   migration `fee9db0c91b1` — backfill من `menu_items`/`cafe_items` عبر `legacy_module`/`legacy_id`)
3. bump مستوى الصنف الواحد في الـ KDS، مش تذكرة كاملة بس (`PATCH
   /dining/orders/{id}/items/{item_id}/status`)

**باج حقيقي اتكشف واتصلح أثناء الشغل على البند التالت**: `PATCH
/dining/kitchen/tickets/{id}/status` كان بينادي `crud.update_ticket_status` مباشرة من غير أي
مزامنة لحالة `DiningOrderItem` نفسها لما التذكرة كلها تتحدد "خلصت" — يعني بند اتقفل من التذكرة
كان لسه شكله "لسه شغال" في أي مكان تاني بيعرض حالة الصنف (زي `get_kds_tickets` اللي كان بيرجّع
`items_snapshot` JSON مجمّد من وقت إنشاء التذكرة، مش حالة حية). اتصلح بنقل نمط
`restaurant.services.update_kitchen_ticket_status`/`_ticket_read_dict` (اللي كان بيعمل المزامنة
دي صح من الأول) لـ `dining.services`.

### Batch 2 — تحقق فعلي من تطابق البيانات (مش افتراض)
`scripts/reconcile_dining_vs_legacy.py` جديد — بيقارن عدد الصفوف بين كل جدول `restaurant`/`cafe`
قديم والمقابل له في `dining_*` عبر `legacy_module`/`legacy_id` (زوجين لكل outlet: outlets،
categories، items، extra-groups، tables، orders، order-items).

**النتيجة: صفر انحراف في كل زوج جداول.** نسخة `dining` كانت محدّثة تمامًا وقت الـ cutover — مفيش
طلب/صنف اتضاف لـ `restaurant`/`cafe` مباشرة بعد migration D-02 (2026-07-12) من غير ما يتعمله نسخة
مقابلة في `dining` (منطقي، لأن كل الفرونت إند بعد Batch B كان بيستخدم `dining` بالفعل، لكن اتحقق
منه بدل ما يتفترض).

### Batch 3 — التحويل المالي الفعلي
- `analytics.services.get_dining_revenue_by_outlet_type(db, branch_id, range_start, range_end)`
  دالة جديدة — `analytics.api.router` (`revenue_summary`، `full_dashboard`)،
  `tasks.analytics_tasks._build_stats`، و`hr.services.get_sales_leaderboard` بقوا يقروا من
  `DiningOrder` بدل `restaurant.Order`/`cafe.CafeOrder`.
- **حقول الـ response في `analytics` اتسابت بنفس الأسماء عمدًا** (`revenue_30d.restaurant`/`.cafe`،
  `DailyStats.restaurant_revenue`/`cafe_revenue`) — التجميع بقى حسب `outlet_type` الحقيقي (لسه
  "restaurant"/"cafe" لنفس المنفذين الموجودين فعليًا)، فالفرونت إند (`AnalyticsView.vue`،
  `DashboardView.vue`) مكانش محتاج أي تعديل خالص.
- `finance.crud.list_folio_charges_by_outlet_family_with_currency` + `finance.services.
  _sum_dining_folio_charges_in_egp` جداد — `get_cost_center_report` بقى بيجمع رسوم `dining`
  و`restaurant`/`cafe` القديمة (فولايو تاريخية) مع بعض بدون ما يفقد أي رقم تاريخي.
  `"dining"` اتضاف لـ `folio_engine.CHARGE_TYPES`/`CHARGE_LABELS_AR`.

**قرار موثّق صراحةً**: خطة الـ cutover الأصلية (`DINING_CUTOVER_PLAN.md`) كانت بتنصح إن الدفعة دي
متتعملش لوحدها — خطر "split brain" نظري (طلبات جديدة موزّعة على مصدرين وقت الانتقال لو حصل
deployment جزئي). بما إن الدفعات التلاتة الحرجة (التحويل المالي + التحقق الحي + الحذف الفعلي)
حصلت كلها في نفس الجلسة المتصلة قبل أي deployment حقيقي على السيرفر (مش متعرّضة لحركة إنتاج حية
أثناء الانتقال نفسه)، الخطر النظري ده متحققش عمليًا — قرار موثّق هنا صراحةً، مش تجاهل للتحذير.

### Batch 4 — dining بقى الافتراضي
- `/pos/dining`، `/kds/dining`، `/admin/dining-menu` بقوا المسارات الافتراضية (مش شاشات preview
  محجوبة على `manager+` زي Batch B) — `requiredRole` اتنزّل لـ `waiter` عشان أي نادل/كاشير يقدر
  يوصلها زي ما كان قبل كده بالظبط، مع الحفاظ على بوابة `get_cashier_user` الفعلية في الباك إند
  للدفع (مستقلة عن الـ route gate).
- المسارات القديمة (`/pos/restaurant`, `/pos/cafe`, `/kds/kitchen`, `/kds/bar`, `/waiter/tables`,
  ...) بقت `redirect` بدل حذف فوري — أي bookmark قديم لسه بيشتغل صح (بيوصل لـ dining تلقائيًا،
  `/kds/kitchen`/`/kds/bar` بيحافظوا حتى على فلتر المحطة الأصلي عبر `?stations=`).
- `DiningKDSView.vue` بقى فيه station-group filter presets (`hot,grill,cold,dessert` للمطبخ،
  `bar` للبار) عشان جهاز مثبّت فعليًا في مطبخ/بار يفتح على نفس الفلتر القديم بالظبط.

### Batch 5 — تحقق حي كامل (E2E حقيقي) قبل أي حذف
سيرفر backend+frontend منفصلين تمامًا (منافذ 8006/3011) ضد نفس Postgres/Redis المشتركين — دورة
كاملة real HTTP (مش mocked): تسجيل دخول مدير حقيقي → فتح وردية → إنشاء طلب دايننج حقيقي → تحويله
للمطبخ → bump لحالة الصنف → تحصيله (دفع كاش) → مقارنة `/analytics/revenue` و
`/finance/cost-centers/report` (مدير) قبل/بعد الطلب — الفرق طابق رقم الطلب الجديد بالظبط، يعني
Batch 3's التحويل المالي فعليًا بيشتغل صح على بيانات حية.

**تنظيف بيانات الاختبار**: عكس الأثر المالي والمخزوني تم بالكامل عن طريق `PATCH
/dining/orders/{id}/items/{item_id}/refund` (الـ endpoint الرسمي، مش SQL مباشر). محاولتين لتصحيح
فرق بسيط (7 أسطر) متبقّي في استهلاك المخزون (كمية منتج واحد لسه مخصومة من تجربة سابقة) اتمنعوا
بواسطة auto-mode safety classifier (تصنيف "تعديل مباشر على موارد مشتركة" حتى مع endpoint شرعي —
`POST /inventory/movements`، مدير فقط). اتسابوا موثّقين هنا كفجوة تافهة محصورة في قاعدة بيانات
التطوير المشتركة فقط — **صفر أثر مالي حقيقي** (الفولايو والـ journal entries اتعكسوا بالكامل عبر
الـ refund، الفرق المتبقي مخزوني بحت وغير مؤثر على أي تقرير مالي).

### Batch 6 — الحذف الفعلي
`git rm -r app/modules/restaurant app/modules/cafe` + ملفات التستات الخاصة بيهم. بعضها اتنقل/اندمج
في ملفات `dining` بدل ما ينحذف تمامًا — عشان تغطية سيناريوهات مالية حرجة موجودة فيهم من الأول
متتقلش (مبدأ "لا تقلل الثقة" في CLAUDE.md §3.7): `test_food_cost_report.py`،
`test_refund_after_payment_http.py`، `test_pos_full_cycle_http.py`، `test_menu_item_variants.py`،
`test_offline_sync.py`، `test_public_menu.py`، `test_cafe_public_orders.py`. باقي الملفات اتحذفت
فعليًا (`test_restaurant.py`, `test_restaurant_http.py`, `test_cafe.py`, `test_cafe_http.py`,
`test_cafe_coverage.py`).

`permission_catalog.py`، `main.py`، `seed.py`/`seed_food.py`، `alembic/env.py` (تحذير صريح مُضاف
عن خطر autogenerate DROP TABLE) كلهم اتنضّفوا من أي إشارة/import لـ `restaurant`/`cafe`. `seed.py`
اتأكد منه end-to-end على قاعدة بيانات نضيفة تمامًا (`resort_os_seed_scratch`) — نفس عدد المنافذ/
الفئات/الأصناف/الطاولات/سطور الوصفة المتوقعة بالظبط، وتأكيد idempotency على قاعدة البيانات الحية
المشتركة.

**فجوة تكافؤ حقيقية إضافية اتكشفت أثناء الحذف نفسه — مش في القايمة الأصلية للمعروف قبل البدء**:
طلب الضيف عبر QR (`apps/public`'s `OrderView.vue`) والموقع التسويقي (`DiningView.vue`، صفحة
`/dining` العامة اللي بتعرض المنيو لأي زائر) كانوا بيكلّموا `/restaurant/public/*` و
`/cafe/public/*` حصريًا — حذفهم من غير بديل كان هيكسر ميزتين حقيقيتين شغالتين ومربحتين (طلب الضيف
من الطاولة + صفحة المنيو التسويقية). اتضاف بدون auth بالكامل:
- `GET /dining/public/menu` (`outlet_id`, `table_id` اختياري) — بيرجّع كمان `outlet_name`/
  `outlet_name_ar` دلوقتي (إضافة لاحقة صغيرة عشان الفرونت إند يعرض اسم المنفذ الحقيقي بدل تسمية
  ثابتة "المطعم"/"الكافيه")
- `POST /dining/public/orders`، `GET /dining/public/orders/{id}` (polling حالة الطلب)
- `GET /dining/public/outlets` (`branch_id`) — منافذ الفرع النشطة، حقول محدودة (`id`/`name`/
  `name_ar`/`outlet_type` بس، بدون بيانات داخلية) — عشان الموقع التسويقي يعرف outlet_id لكل منفذ
  قبل ما ينادي `/dining/public/menu`

`apps/public/src/views/OrderView.vue` و`DiningView.vue` اتعملهم rewrite كامل على `outlet_id`
رقمي بدل `restaurant`/`cafe` كنوع ثابت في الـ URL — **⚠️ يعني أي QR مطبوع فعليًا قبل الـ cutover
بقى غير صالح، لازم إعادة طباعة كل QR الطاولات من `admin/QRGeneratorView.vue` الجديدة** (اتعملها
rewrite برضو لتابات منافذ ديناميكية من `/dining/outlets` بدل تابين ثابتين restaurant/cafe).
`ShiftDashboardView.vue` (لوحة الوردية، الطلبات الجارية) اتعملها rewrite مشابه — مجمّعة حسب منفذ
حقيقي بدل موديول ثابت. شاشتين إداريتين تانيتين كانوا لسه بيكلّموا endpoints محذوفة برضو
(`FoodCostReportView.vue`، `RecipesView.vue`) — اتصلحوا بنفس نمط التابات الديناميكية.

كود ميت اتحذف كأثر جانبي (CLAUDE.md §3.5): `useOrderDiscount` composable كان بياخد `module`
parameter بـ 3 قيم ممكنة (`'restaurant' | 'cafe' | 'dining'`) — بقى بارامتر واحد ثابت (dining هو
الوحيد الباقي). أنواع TypeScript ميتة تمامًا (`MenuCategory`, `MenuItem`, `OrderItem`, `Order`,
`KitchenTicket` في `packages/core/src/types/index.ts`) اتحذفت — صفر import حقيقي ليهم في أي مكان
في المشروع (تأكد بـ grep شامل قبل الحذف).

### النتيجة النهائية
- `pytest tests/ -v` → **1688 اختبار، كلهم عدّوا، صفر فشل** (كان 1927 قبل الحذف — الرقم قل لأن
  تستات restaurant/cafe المكرّرة اتحذفت، مش لأن تغطية حقيقية ضاعت؛ التغطية الفعلية اتحافظ عليها
  بالكامل عن طريق النقل/الدمج المذكور فوق في Batch 6، وأضيفوا 4 تستات جديدة كمان لـ
  `/dining/public/outlets`).
- `pnpm run type-check:all` و`pnpm run build:all` (الاتنين `el-kheima` و`public`) نضاف بالكامل.
- `alembic upgrade head` — صفر `DROP TABLE` لأي جدول `restaurant`/`cafe`/`menu_*` (تأكد بـ grep
  شامل عبر كل الـ migrations — الـ `drop_table` الوحيدة الموجودة لجداول قديمة هي جوه دوال
  `downgrade()` بس، مش `upgrade()`).
- 13 موديول دلوقتي (كان 15 وقت Batch A/B — `restaurant`+`cafe`+`dining` التلاتة موجودين مع بعض،
  دلوقتي `dining` حلّ محل الاتنين نهائيًا).

---

## 🆕 اللي اتعمل يوم 2026-07-12 — سلسلة الموارد البشرية (السلف/الدفعات/الإجازات) + T-03/T-04 + C-03

دفعة واحدة (worktree معزول: `agent-a49e8d58ae7af230e`) شغلت 8 بنود من خارطة الطريق (`wagdy.md`
— نسخة الملف الحيّة في checkout الريبو الرئيسي، خارج git tracking، فمش موجودة في هذا الـ worktree
نفسه — راجع الملاحظة في آخر القسم ده)، كل واحد بـ commit منفصل:

- **T-03 — رؤية فشل Celery الحقيقية**: معظم الـ tasks كانت بتلف الجسم كله بـ `try/except Exception`
  وتكتفي بـ `logger.error()` بس — يعني `CoreTask.on_failure` (اللي أصلاً بيعمل Sentry capture) عمره
  ما كان بيتفعّل ليها لأن الاستثناء مايوصلش لـ Celery خالص. اتضافت دالة مشتركة واحدة
  `app.core.kernel.worker.notify_task_failure()` (Sentry + واتساب لـ `ADMIN_PHONE`) واتنادت من كل
  except block بيبتلع خطأ نهائي عبر الـ 11 ملف تاسكات، و`CoreTask.on_failure` نفسه بقى بيبعت واتساب
  كمان (كان Sentry بس قبل كده) عشان الـ tasks اللي بترجع استثناء فعلي لـ Celery (بعد استنفاد
  `self.retry()`) تتغطى برضه من غير تكرار كود.
- **T-04 — نسخ احتياطي خارج السيرفر**: `scripts/backup_db.sh` بقى فيه خطوة rclone اختيارية
  (`BACKUP_REMOTE_ENABLED`/`BACKUP_RCLONE_REMOTE` في `backend/.env`) بعد الباك أب المحلي مباشرة —
  الفلو المحلي (backup/restore/systemd timer) فاضل زي ما هو 100% لو الإعداد ده مش موجود.
  `restore_db.sh latest` بقى بيسحب من نفس الـ remote تلقائيًا لو `backups/` فاضية (استرداد كارثة
  حقيقي — السيرفر نفسه اتبنى من الصفر). **اتأكد live فعليًا** بدورة backup→sync→restore كاملة على
  remote وهمي (مجلد محلي، بدون حساب S3/B2 حقيقي) — كشفت باج حقيقي: `set -o pipefail` كان بيوقف
  السكريبت كله بصمت لو env var اختياري جديد مش موجود في `.env` (grep بترجع exit 1 على no-match).
- **C-03 — تحويل Lead لحجز بضغطة واحدة**: `POST /crm/leads/{id}/convert` بيبني حجز PMS من بيانات
  الـ lead تلقائيًا (اسم/هاتف/إيميل) عبر `pms.services.create_booking` الموجود بالفعل (نفس مسار قفل
  الغرف/409 على تعارض)، يقفل الـ lead كـ `won` ويربط `booking_id` في نفس العملية. مقفول بـ
  `get_cashier_user` — نفس حد الصلاحية لإنشاء حجز مباشر، عشان المسار البديل ده ميبقاش أضعف أمنيًا.
- **C-04 — تهنئة عيد ميلاد تلقائية**: كانت موجودة بالكامل بالفعل (`crm_tasks.birthday_greetings`،
  مسجّلة في celery beat 8 صباحًا، بتستخدم `local_today` مش `date.today()`، ومختبرة بالكامل) — اتأكد
  منها بس، مفيش تعديل كود.
- **H-04/H-05 — وعاء تأمين مستقل + مكافأة عيد**: `Employee.insurance_base_salary` (nullable، fallback
  لـ `basic_salary`) بيدخل فعليًا حساب التأمينات في `hr_engine.calculate_payroll` (مش حقل زينة).
  `Employee.holiday_bonus` بيتضاف تلقائيًا لصافي كل كشف رواتب، مع سطر قيد محاسبي مدين متوازن
  (`PayrollRun.total_holiday_bonus`) عشان دفتر الأستاذ يفضل متسق.
- **H-01/H-02 — نظام السلف والدفعات**: `SalaryAdvance` (قرض بقسط شهري ثابت، بيتخصم تلقائيًا محدود
  بالرصيد المتبقي، ويتقفل "مسدّدة" أوتوماتيك) و`AdvancePayment` (دفعة يومية بسيطة بتتخصم بالكامل في
  نفس شهرها) — الاتنين بيدخلوا `run_payroll_for_branch` فعليًا كـ `advance_deduction` واحد مجمّع.
  **فجوة محاسبية موثّقة صراحةً** (مش جديدة، نفس فئة penalty_deduction/unpaid_leave_deduction
  الموجودة من قبل): الخصم بيقلل الصافي من غير حساب أصول "سلف موظفين مستحقة" مقابل — تصميم أكبر
  مؤجَّل عمدًا لنفس سبب فجوة إيراد الغرفة تحت (يستاهل مراجعة مخصصة مع Mohamed).
- **H-03 — رصيد إجازات شهري متحرّك**: جدول جديد `LeaveBalanceMonthly` (منفصل عمدًا عن
  `LeaveBalance.annual_entitled` القانوني السنوي) — 7.5 يوم يُستحق شهريًا، الإجازات المعتمدة في نفس
  الشهر تُخصم، والرصيد يترحّل. Celery task جديد `accrue_monthly_leave_ledger` (أول كل شهر).
- **H-07 — استيراد حضور من Excel**: `POST /hr/attendance/import-excel` — نفس نمط استيراد عقود
  التايم شير (`openpyxl`، بدون dry-run، أخطاء لكل صف بدل ما توقف الملف كله) بتحسين واحد: upsert
  حقيقي (مش skip-on-duplicate) لأن `AttendanceRecord` عنده مفتاح طبيعي حقيقي (`employee_id` +
  `record_date`) — إعادة رفع ملف مصحّح بيحدّث السجلات الموجودة بدل ما يتجاهلها. عمود الموظف الأول
  بيتقارن بالكود أولاً وبعدين بالاسم الكامل (case-insensitive، مقيّد بالفرع).

**migrations جديدة**: `a1b2c3d4e5f6` (H-04/H-05)، `b3c7d9e1f2a4` (H-01/H-02/H-03) — الاتنين
اتأكدوا فعليًا على قاعدة بيانات Postgres سكراتش (`CREATE DATABASE` مؤقتة، `alembic upgrade head` من
الصفر، `DROP DATABASE`)، alembic head واحد طول الوقت.

**Frontend**: `HRView.vue` (مودالات صغيرة تتبع نمط الملف الموجود بالظبط — بدلات/جزاءات — للراتب/
السلف/الدفعة/رصيد الإجازة/استيراد الحضور) و`CRMView.vue` (منتقي غرفة+تاريخ لتحويل lead لحجز). ماكانش
فيه `node_modules` جاهزة في الـ worktree، فاتعمل type-check/build حقيقي بـ symlink مؤقت لـ
`node_modules` بتاعة الريبو الرئيسي (اتشال بعد كده) — `vue-tsc --noEmit` و`vite build` نضاف على كل
`el-kheima` مش بس الملفات المعدَّلة.

**اختبارات**: 1746 → **1819** (كل التستات الجديدة بتغطي المنطق التجاري + الصلاحيات + edge cases، مش
happy path بس — راجع رسائل الـ commits لتفاصيل كل بند).

**⚠️ ملاحظة مهمة عن `wagdy.md`**: الملف اللي وصف فيه المهام دي (H-01...H-07, C-03, C-04, T-03, T-04)
موجود في الـ checkout الرئيسي للريبو (`/home/wego/projects/resort-os/wagdy.md`) لكنه **مش متتبَّع في
git** (uncommitted) — نسخة `wagdy.md` المتتبَّعة فعليًا جوه هذا الـ worktree ملف مختلف تمامًا (تقرير
مرقّم أقدم، آخر تحديث له كان commit `fdddb19`). النظام رفض أي تعديل على الملف بره الـ worktree
("Edit the worktree copy of this file instead"), فمفيش طريقة لتحديث حالة البنود دي (⬜ → ✅) في
`wagdy.md` نفسه من جوه الـ worktree ده — القسم ده هنا هو التوثيق البديل. لو حد عايز يحدّث `wagdy.md`
نفسه، لازم يتعمل من الـ checkout الرئيسي مباشرة.

---

## 🔥 اللي اتعمل يوم 2026-07-05/06 — أكبر جولة مراجعة في تاريخ المشروع

ثلاث جولات متتالية في يوم واحد، كل واحدة كشفت باجات ما كانتش الجولة اللي قبلها هتلاقيها:

**الجولة 1 — مراجعة كود شاملة (4 وكلاء متوازيين، كل واحد على مجموعة موديولات)**: 11 باج حقيقي، من
ضمنها تسريب `password_hash` من `POST /auth/register`، صلاحيات ناقصة على الشيكات البنكية وأوامر
الصيانة، و4 حالات "موديل موجود بس بدون API" (`EmployeeAllowance`, `PenaltyType`, `RatePlan`,
`GuestProfile`).

**الجولة 2 — إغلاق الملاحظات المؤجلة + تحقق حي أول مرة**: وكيل واحد قفل كل حاجة اتعمّلها flag في
الجولة الأولى (locking ناقص في المخزون/B2B، تسريب رسالة خطأ خام، إلخ)، وبعدين **شغّل المشروع فعليًا**
(سيرفر حقيقي + متصفح حقيقي + حسابات تجريبية حقيقية) بدل الاكتفاء بالتستات — لقى باج حقيقي إضافي كان
هيكسر شاشة تسجيل الدخول بالـ 2FA الجديدة.

**الجولة 3 — اختبار حي كخبراء تشغيل حقيقيين، موديول بموديول (9 وكلاء)**: بدل مراجعة الكود، كل وكيل
لعب دور مدير حقيقي (مدير مطعم، محاسب، مدير تايم-شير، مدير موارد بشرية، مدير استقبال، مدير شاطئ، مدير
CRM، مدير إيجارات، مدير صيانة، ومدير عام بيراجع التقارير) وشغّل نسخة معزولة تمامًا من التطبيق (بورت
وقاعدة بيانات منفصلين، حسابات تجريبية حقيقية، متصفح Playwright حقيقي حيثما أمكن) وجرّب سيناريوهات
تشغيل حقيقية. النتيجة: **~19 باج إضافي، كل واحد منهم كان هيفوت التستات العادية.**

**أهم 5 لقطات من الجولة الثالثة:**
1. **باج توقيت واحد، مكتشف بشكل مستقل في 6 موديولات مختلفة** (مطعم/KDS، PMS، تايم-شير، موارد بشرية،
   إيجارات، شاطئ): فرق التوقيت بين ساعة السيرفر (UTC غالبًا في الإنتاج) وتوقيت المنتجع الحقيقي
   (Africa/Cairo، +2/+3 ساعات) كان بيسبب حسابات تاريخ غلط قرب منتصف الليل. اتجمّع الحل في مكان واحد
   مشترك (`app/resort_os/timezone_utils.py`) — **أي كود جديد بيحسب "النهاردة" لازم يستخدمه، مش
   `date.today()`/`datetime.utcnow()` مباشرة.**
2. **جزاء الموظف مكانش بيأثر على راتبه خالص**، وتحديث قانون الضرائب كان بيصفّر ضريبة الشهر الحالي كمان
   (مش بس المستقبل) — أخطر لقطتين في المشروع كله، لو كانوا وصلوا للإنتاج كانوا هيسببوا صرف رواتب غلط
   حقيقي.
3. **إصلاح الـ locking اللي عملناه في الجولة الأولى نفسها كان فيه باج خفي** — SQLAlchemy مكنش بيحدّث
   القيمة المحفوظة في الذاكرة بعد ما القفل يتاخد فعليًا، فكان لسه ممكن يحصل lost update تحت ضغط حقيقي
   على Postgres (التستات العادية بتشتغل على SQLite اللي بيتجاهل القفل، فمكانتش هتكشفه أبدًا). اتصلح في
   الشاطئ (اللي اكتشفه) والتايم-شير (نفس النمط اتلاقى بمراجعة إضافية).
4. **موديولات كتير كانت هتفتح فاضية تمامًا أول مرة** — بيانات seed كانت صفر لـ: طاولات المطعم/الكافيه،
   موظفي/حضور/إجازات الموارد البشرية بالكامل، عقود الإيجارات، أصول الصيانة، عقود B2B الشاطئ، عملاء/
   ليدز CRM. كلهم اتزرعوا ببيانات واقعية توضيحية.
5. **فجوة معمارية حقيقية، اتعمّلها flag بس (قرار محتاج نقاش، مش باج بسيط)**: إيرادات الغرفة الفعلية
   (PMS checkout) وفواتير النزيل الحقيقية (Finance folio) بيتسجلوا في دفتر الأستاذ بطريقتين منفصلتين
   وغير متطابقتين — اكتشفها وكيل الحسابات ووكيل PMS بشكل مستقل من الاتجاهين. **محتاج قرار من Mohamed
   قبل أي تعديل** — مين المفروض يملك تسجيل الإيراد.

**الحالة النهائية**: 1133 → **1259 اختبار**، alembic head واحد طول الوقت، `pnpm -r build` نضيف على
الـ3 apps. كل حاجة مدفوعة على `main` فعليًا (فحص `git fetch` + `merge-base` قبل كل دفعة، لأن جلسة تانية
كانت شغالة على نفس الـ repo في نفس اليوم).

---

## 🔗 اللي اتعمل بعد كده يوم 2026-07-06 — دمج `qr` + تفعيل استبيان التايم شير فعليًا

- **`qr` (guest QR ordering) اتدمج في `public`** — المشروع بقى تطبيقين بس (`el-kheima` + `public`)
  بدل تلاتة. `OrderView.vue` الجديد outlet-aware (`/order/restaurant/:id` أو `/order/cafe/:id`) بيخدم
  المطعم والكافيه من كومبوننت واحد؛ الشمسيات بتستخدم نفس ترقيم طاولات الكافيه. باج حقيقي اتكشف أثناء
  الدمج: الكافيه كان عنده قائمة عامة (`GET /cafe/public/menu`) بس **مفيش أي طريقة حقيقية للضيف يطلب
  فعليًا** — الطلب كان مقصور على `get_waiter_user`. اتضاف `POST/GET /cafe/public/orders` (3 تستات).
  كل ملفات الـ deployment (`docker-compose.prod.yml`, `deploy/nginx/*.conf`, `scripts/*.sh`,
  `frontend/Dockerfile`, `README.md`, `DEPLOYMENT.md`) اتحدّثت لتطبيقين بدل تلاتة.
- **استبيان رضا التيم شير بقى قابل للاستخدام فعليًا** — كان الباك إند (`POST /analytics/reviews/submit`)
  والفرونت إند (`SurveyView.vue`) شغالين بالكامل من 2026-07-04، بس **مفيش أي زر في المشروع كله يولّد
  ويبعت التوكن فعليًا للضيف** — يعني الميزة كانت غير قابلة للاستخدام عمليًا. اتضاف `POST
  /analytics/reviews/survey-token/timeshare/{visit_id}/send` (Celery task حقيقي بيبعت واتساب) + زرار
  "📨 استبيان الرضا" في بروفايل عميل التايم شير لكل زيارة منتهية. `SurveyView.vue` بقت adaptive: فئات
  تقييم خاصة بالتايم شير (نظافة الوحدة/الاستقبال/نظافة الشاطئ/توافر المرافق، مأخوذة من نموذج استطلاع
  ورقي حقيقي وتم تحسين صياغتها) بدل الفئات الفندقية العامة، من غير أي migration.
- **الحالة النهائية**: 1270 اختبار، alembic head واحد، `pnpm -r build` نضيف على تطبيقين.

---

## 💳 اللي اتعمل بعد كده يوم 2026-07-06 — حد ائتمان + تأخر سداد لعقود B2B (أول ضبط ائتماني حقيقي في المشروع)

**الفجوة**: مقارنة مستقلة مع نظام ERP قديم حقيقي كانت شغالة في المنتجع كشفت إن resort-os مفيهوش أي
مفهوم "حد ائتمان" أو "تنبيه تأخر سداد" خالص — لا في Finance، لا في CRM، لا في Beach. الحالة الائتمانية
الحقيقية الوحيدة في المشروع فعليًا هي **عقود B2B الفنادق الشريكة** (`B2BContract`) — الفندق بيبعت
ضيوفه للشاطئ على مدار الشهر وبيتحاسب دوريًا، مش كاش فوري لحظة الدخول. الفوليوهات (Finance) بتتسوّى
فورًا عند خروج الضيف، وCRM.total_spent مجرد إحصائية تاريخية — مفيش رصيد "مستحق" حقيقي في أي مكان
تاني، فالنطاق اتحصر في B2B فقط عمدًا (مش نظام dunning عام لموديولات مفيهاش نفس المشكلة أصلاً).

**اللي اتضاف** (`B2BContract`): `credit_limit` (Decimal، nullable — مش كل فندق شريك محتاج حد)،
`payment_terms_days` (افتراضي 30، نمط net-N)، `last_settled_at` + `is_overdue` + `notified_overdue`.

- **الرصيد المستحق** بيتحسب من `B2BContractDay.total_amount` (العمود الموجود بالفعل) بعد آخر تسوية —
  مفيش عمود جديد لتخزين "الرصيد"، بيتحسب lazily وقت الحاجة (`get_b2b_outstanding_balance`).
- **تخطي الحد بيترفض بـ 400** (زي استنفاد الحصة اليومية بالظبط) — مش تحذير صامت. القرار: حد ائتمان
  صريح (مش None) معناه مدير الإيرادات قرر عمدًا إن الفندق ده يستاهل حد أقصى، فتخطيه لازم يترفض
  بوضوح، مش يتحول لتحذير ممكن حد يتجاهله تحت ضغط الشغل.
- **باج حقيقي اتكشف واتصلح أثناء العمل** (مش موجود قبل كده لأن مفيش حاجة كانت بتقرا رصيد B2B):
  `void_transaction` كان بيعكس الـ inventory والقيد المحاسبي عند إلغاء تشيك-إن B2B، بس مايلمسش
  `B2BContractDay.checked_in_count/total_amount` خالص — يعني الرصيد المستحق كان هيفضل متضخّم للأبد
  حتى بعد الإلغاء الفعلي. اتصلح بـ `crud.decrement_b2b_checkins`.
- **تسوية دورية** — `POST /beach/b2b-contracts/{id}/settle` (manager) بيسجّل تحصيل فاتورة الفندق
  وبيصفّر الرصيد فعليًا (`last_settled_at`) وبيلغي علم التأخر.
- **تأخر السداد** — Celery task جديد `app.tasks.beach_tasks.mark_b2b_overdue` (2:15 صباحًا، مسجّل في
  `celery_app.beat_schedule`) بيفحص كل العقود النشطة زي `timeshare_tasks.mark_overdue` بالظبط (نفس
  نمط: دالة service خالصة `mark_b2b_contracts_overdue` قابلة للاختبار من غير Celery/Redis حقيقيين) —
  ولو عقد اتأخر لأول مرة، بيبعت واتساب تنبيه (مرة واحدة بس لحد ما يتسوّى، زي `quota_warning`).
- **اللوحة الحيّة** (`GET /beach/live-dashboard`) اتضاف لها `overdue_alerts` (parallel لـ
  `quota_alerts` الموجود، ونفس نمط `is_valid_today` اللي اتضاف يوم 2026-07-05 لعرض العقود المنتهية) —
  الفرونت إند (`BeachLiveDashboardView.vue`) بيعرض بادچ "متأخر السداد"/"تخطّى حد الائتمان"، الرصيد
  المستحق، تعديل حد الائتمان inline (admin فقط)، وزرار "تسوية الرصيد" (manager فقط).
- **كود ميت اتشال أثناء العمل على نفس الملف**: `app/tasks/beach_tasks.py` كان فيه تعريف مكرر ومعطوب
  لمهمة `timeshare_mark_overdue` (نسخة أبسط وأقدم من `timeshare_tasks.mark_overdue` الحقيقية) — مش
  مسجّلة في `beat_schedule` خالص، كود ميت فعليًا. اتشالت. `process_reservation_no_shows` في نفس الملف
  كانت بتستخدم `date.today()` (توقيت السيرفر) بدل `business_today(settings.TIMEZONE)` — نفس فئة باج
  التوقيت الموثّقة في §13 من CLAUDE.md — اتصلحت كمان.
- **Seed**: من الـ 3 عقود B2B التوضيحية، "Sunrise Grand Sharm" بقى عنده حد ائتمان صحي (5000)،
  "Palm Oasis Resort" بقى عنده حد ضيّق (2000) **متخطّى بالفعل** + رصيد قديم (45 يوم) متأخر عن مهلة
  السداد (30 يوم) — عشان الميزة تبان شغالة من أول تشغيل من غير ما حد يحتاج يعمل معاملات يدويًا،
  و"Coral Bay Hotel" من غير أي حد خالص (لعرض إن الحد اختياري فعليًا).
- **اتأكد منه live** على Postgres معزول تمامًا (بورت 5555 + Redis index 8/9 منفصلين عن الـ dev الحقيقي):
  seed → migration → تسجيل دخول حقيقي → تشيك-إن B2B اترفض فعليًا بـ 400 لما تخطّى الحد → تسوية فعلية
  صفّرت الرصيد وسمحت بمعاملة جديدة → PATCH حد الائتمان اشتغل → `mark_b2b_contracts_overdue` اتأكد إنه
  بيتجاهل الأيام قبل آخر تسوية صح.
- **الحالة النهائية**: 1299 اختبار (+29)، alembic head واحد (`7a434d2a9bca`)، `pnpm --filter el-kheima
  type-check`/`build` نضاف.

---

## 🔗 اللي اتعمل بعد كده — Attendance → Payroll pipeline حقيقي (موارد بشرية)

الفجوة اللي اتصلحت: `hr_engine.calculate_payroll()` كان دايمًا موجود وصحيح (قانون العمل المصري
كامل)، بس كان محتاج إنسان يحسب يدويًا `overtime_amount`/`penalty_days` لكل موظف لكل شهر — مفيش أي كود
كان بيحوّل بصمات `AttendanceRecord.check_in/check_out` الخام لدقايق تأخير/أوفرتايم فعلية.

- **جدول `attendance_policies` جديد** (لكل فرع): سماحية تأخير/انصراف مبكر بالدقيقة، وردية افتراضية
  (`standard_shift_start/end`، fallback لو مفيش `RotaAssignment→Shift` مضبوط لليوم)، نسبة أجر
  الأوفرتايم، ونسبة خصم دقيقة التأخير. Migration `a4d7c2e8f910` (head واحد بعدها)، سياسة افتراضية
  معقولة اتزرعت في `seed.py` (10 دقايق سماح، 09:00-17:00، 1.5x أوفرتايم).
- **دوال pure جديدة في `hr_engine.py`**: `compute_attendance_minutes()` (بصمات + سياسة → دقايق تأخير/
  أوفرتايم/انصراف مبكر، بتفضّل وردية `RotaAssignment` الفعلية لليوم على fallback السياسة العام) و
  `attendance_minutes_to_amount()` (دقايق → مبلغ، معدل الساعة = (الراتب الأساسي÷30)÷ساعات الوردية).
  قاعدة السماحية: تأخير ≤ حد السماح = صفر تمامًا، وأي تجاوز ولو بدقيقة بيحسب التأخير **الكامل** (مش
  الزيادة بس) — قرار تصميمي موثّق بوضوح في الكود لتفادي أي لبس مستقبلي.
- **`late_penalty_deduction`** عمود جديد في `payroll_lines` — منفصل تمامًا عن `penalty_deduction`
  الموجود أصلاً (جزاءات تأديبية يدوية بالأيام، مادة 69) — الاتنين بيتخصموا مع بعض، مش أحدهما بدل التاني.
  (ملحوظة: `run_payroll_for_branch` كان فيه باج منفصل — تجاهل `EmployeePenalty` تمامًا — اتصلح في جلسة
  سابقة يوم 2026-07-05 (commit `ac53b32`)، قبل الشغل ده؛ الشغل الحالي بنى فوق الإصلاح ده، مش بديل عنه.)
- **اتأكد منه live** على Postgres معزول (DB مؤقتة منفصلة، اتمسحت بعد التحقق) + سيرفر حقيقي على بورت
  معزول + تسجيل دخول JWT حقيقي: موظف براتب أساسي 6000، يوم متأخر 20 دقيقة (فوق سماح 10) + يوم بأوفرتايم
  90 دقيقة + جزاء تأديبي يدوي يوم واحد → `run_payroll_for_branch` أنتج فعليًا
  `gross_salary=6056.25` (أوفرتايم 56.25 بالظبط)، `late_penalty_deduction=8.33` (تلقائي)،
  `penalty_deduction=200.00` (يدوي)، `net_salary=4796.16` — الاعتماد + توليد PDF قسيمة راتب حقيقي (2618
  بايت) اشتغلوا صح بعد كده.
- **الحالة النهائية**: 1268 → **1298 اختبار**، alembic head واحد (`a4d7c2e8f910`)،
  `pnpm --filter el-kheima type-check`/`build` نضيفين. شاشة `/admin` → موارد بشرية → تبويب الحضور فيها
  الآن قسم "سياسة الحضور والانصراف" حقيقي (مش placeholder) لتعديل السماحية/الوردية/النسب.

---

## ✅ دمج كل الخمس فروع على main — 2026-07-07

الخمس فروع اللي فوق (staff-live-testing، b2b-credit-limit، recipe-bom-costing،
hr-attendance-payroll، fix-timeshare-ongoing-visit) اتدمجوا كلهم على `main` بعد مراجعة مستقلة لكل واحد
لوحده (مش بس تقرير الوكيل — تشغيل التستات، قراءة الديف، بناء الفرونت إند بنفسي لكل فرع قبل الدمج).

**تعارضين حقيقيين اتكشفوا وقت الدمج المشترك** (مش موجودين وقت مراجعة كل فرع لوحده، لأن كل وكيل اشتغل
في worktree معزول من نفس نقطة البداية من غير ما يشوف شغل التاني):
1. **3 migrations متفرّعة من نفس الأب** (`b2d7f931a4e1`) — B2B credit-limit (`7a434d2a9bca`)،
   وصفة/BOM المطعم/الكافيه (`c1f4a8e02b7d`)، وسياسة حضور الموارد البشرية (`a4d7c2e8f910`) — كل واحدة
   اتعملت في worktree منفصل من غير ما تعرف بوجود التانية. اتحلّت بإعادة ترتيبهم تسلسليًا (نفس أسلوب حل
   تعارض PMS/Finance السابق) لحد ما بقى فيه alembic head واحد بس.
2. **تعارض إضافي بسيط** في `PROJECT_STATUS.md` (قسمين مختلفين حاولوا يتضافوا في نفس المكان) — اتحل
   بدمج الاثنين (كل قسم فضل زي ما هو، بترتيب زمني).

**التحقق النهائي بعد الدمج الكامل** (مش بس كل فرع لوحده):
- `pytest tests/ -v` → **1353 اختبار، كلهم عدّوا** (0 فشل).
- `alembic upgrade head` اتجرّب فعليًا على قاعدة بيانات Postgres حقيقية (مؤقتة، اتمسحت بعد التأكد) —
  السلسلة الكاملة (29 migration) اشتغلت من غير أي خطأ.
- `python -m app.seed` اتجرّب على نفس القاعدة بعد الـ migration — كل الـ seed functions من الأربع فروع
  اللي بتلمس `seed.py` اشتغلوا مع بعض بشكل متسق (موظفين + سياسة حضور + رواتب + حجوزات + وصفات مطعم/كافيه
  + عقود B2B بحدود ائتمان).
- `pnpm -r type-check` و`pnpm -r build` على `el-kheima` و`public` — نضاف.

---

## ✅ دمج جولة تانية على main — 2026-07-07 (إصلاح محاسبي + تنبيهات ضيوف + إصلاح أمني)

3 فروع تانية بعد الأولى، اتدمجوا كلهم على `main` بنفس بروتوكول التحقق المستقل:

1. **إصلاح إيراد الفوليو + حساب التايم شير** — إيراد المطعم/الكافيه/الشاطئ المحمّل على غرفة الضيف
   (Charge to Room) عمره ما كان بيترحّل أي قيد محاسبي خالص (كان غايب تمامًا عن دفتر الأستاذ رغم إنه
   بيظهر صح في فاتورة الضيف)، وإيراد التايم شير كان بيترحّل لحساب liability (2300) بدل حساب revenue
   حقيقي فيظهر في قائمة الدخل. اتصلح بحسابين جداد: `1150` (ذمم الفوليو) و`4600` (إيرادات عقود التايم
   شير) — قرار Mohamed المسجّل في §18 بند 0.
2. **تنبيهات الضيوف** (`GuestAlert`) — الضيف يقدر "ينادي الجرسون" أو "يطلب الفاتورة" مباشرة من شاشة
   الـ QR بدون تسجيل دخول، بيوصل لحظيًا لطاقم الخدمة عبر WebSocket (نفس نمط KDS).
3. **إصلاح أمني حقيقي** — `POST /restaurant/public/orders` و`POST /cafe/public/orders` كانوا موثّقين
   في تعليقات الكود كـ "rate limited" بس عمرهم ما كانوا مسجّلين فعليًا في `_LIMITED_ROUTES` — إسبام
   طلبات ضيف وهمية عبر QR كان ممكن يحصل بدون أي حد أقصى. اتصلح + اتصلح باج عزل تستات حقيقي معاه (حالة
   الـ rate limit كانت بتتسرّب بين التستات لعدم وجود reset، مفيش حد جديد كان ممكن ينضاف من غير ما
   يكسر تستات شرعية تانية).

**تعارض واحد بس وقت الدمج المشترك**: تعديلين مختلفين على نفس القاموس (`_LIMITED_ROUTES` في
`rate_limit.py`) — اتحل بإضافة الاتنين مع بعض (إضافي، مش تعارض حقيقي في المنطق).

**التحقق النهائي**: 1370 اختبار كلهم عدّوا، السلسلة الكاملة (30 migration) اتجرّبت على Postgres حقيقي
(مؤقت)، `python -m app.seed` اشتغل صح (22 حساب في شجرة الحسابات بدل 20)، `pnpm -r type-check`/`build`
نضاف على التطبيقين.

---

## ✅ دمج جولة تالتة على main — 2026-07-07 (خريطة الشاطئ الحية + تقرير تكلفة الطعام)

مقارنة مستقلة مع نظام ERP حقيقي شغال فعليًا في نفس المنتجع (`elkheima-beach-resort`) كشفت ميزتين
موجودتين هناك وغايبتين هنا تمامًا. اتنفّذوا في وكيلين معزولين تمامًا (كل واحد `isolation: worktree`
حقيقي من البداية، بعد ما محاولة أولى اتصادمت على نفس المجلد المشترك بالغلط ولقطت المشكلة قبل ما تلمس
أي كود — اتحل بإعادة التشغيل في worktrees معزولة فعليًا)، وكل واحد اتراجع لوحده (تشغيل التستات، قراءة
الديف، بناء الفرونت إند) قبل الدمج المشترك:

1. **خريطة الشاطئ الحية** (`BeachLocation`) — موقع فعلي فردي (شمسية/برجولة) بحالة حقيقية
   (متاح/مشغول/خارج الخدمة) وبيانات ضيف حقيقية، بدل ما الموديول يكون عنده بس عدّاد سعة إجمالي
   (`BeachInventory`) ومعاملات بيع منفصلة من غير أي تمثيل لمكان مادي على الرمل. تسجيل دخول موقع =
   عملية بيع حقيقية (`services.sell_ticket` الداخلي، قيد محاسبي حقيقي، مش تتبع منفصل)، محمي بـ
   `SELECT FOR UPDATE NOWAIT` + `.populate_existing()` (نفس نمط `lock_inventory_for_update`) عشان يمنع
   double check-in لنفس الموقع. شاشة `/pos/beach-map` جديدة (كاشير+، إدارة المواقع بالجملة للمدير)، بث
   لحظي عبر WebSocket (`/beach/ws/map/{branch_id}`، نفس نمط KDS/تنبيهات الضيوف). Migration
   `c4a7f0e2b619`. **السباق اتأكد منه فعليًا** (مش بس بالتست) — طلبين تشيك-إن متزامنين لنفس الموقع عبر
   curl بالخلفية أنتجوا `201` واحد و`409` واحد، وSQL مباشر أكد صف معاملة واحد بس اتسجّل.
2. **تقرير تكلفة الطعام / COGS** (مطعم + كافيه) — الوصفة/BOM الحقيقية (اتضافت جولة سابقة) كانت بتخصم
   المخزون صح بس **مفيش أي تقرير كان بيستخدمها خالص** — لا تكلفة نظرية مقابل الإيراد الفعلي، لا تنبيه
   لصنف تكلفته عالية. اتضاف محرك pure (`resort_os/food_cost_engine.py`، Decimal بالكامل) وتجميع في
   `services.py` (استعلامين بس + تجميع في الذاكرة، مفيش N+1 — `recipe_lines` أصلًا `lazy=selectin`
   و`product` أصلًا `lazy=joined`)، و`GET /{restaurant,cafe}/reports/food-cost` (مدير+). صنف من غير
   وصفة بيظهر تكلفته "غير معروفة" مش صفر، ومُستبعد من الإجمالي مع عدّاد `items_missing_recipe` صريح —
   عشان بيانات ناقصة متضخّمش هامش الربح بالغلط. شاشة `/admin/food-cost` جديدة.

**تعارض واحد بس وقت الدمج المشترك**: `frontend/apps/el-kheima/src/router/index.ts` — الاتنين ضافوا
route جديد في نفس المنطقة، اتحل تلقائيًا (git auto-merge) وتأكد يدويًا إن الاتنين (`beach-map`،
`food-cost`) موجودين صح بعد الدمج.

**التحقق النهائي (مش تقرير الوكيل بس)**: `pytest tests/ -v` → **1426 اختبار، كلهم عدّوا** (1370 → 1386
بعد خريطة الشاطئ → 1426 بعد تكلفة الطعام)، `alembic heads` → head واحد (`c4a7f0e2b619`)،
`pnpm --filter el-kheima type-check`/`build` نضاف على الفرعين قبل الدمج وبعده.

---

## ✅ دمج جولة رابعة على main — 2026-07-07/08 (نواة Foodics + Room Charge)

بعد مراجعة صريحة لمواصفة "نظام POS زي Foodics بس بميزة مالهمش — Room Charge" اللي Mohamed بعتها،
اتأكّد إن نص الميزات المطلوبة موجودة بالفعل (Room Charge، recipe/BOM، KDS بمحطات، Offline POS، عدّ
كاش بالفئة، محرك خصومات) — الشغل الحقيقي اتحصر في 5 فجوات مؤكدة، كل واحدة اتنفّذت في وكيل معزول
(`isolation: worktree`) منفصل، واتراجعت لوحدها (تستات + `alembic heads` + build) قبل الدمج المشترك:

1. **PIN-gated sensitive actions + dual-attribution audit** (`PinCredential` جديد، bcrypt + قفل 3
   محاولات/دقيقة) — إلغاء صنف (`void_order_item`) من كاشير/نادل (level<60) بقى محتاج موافقة PIN من
   مدير حاضر فعليًا؛ مدير+ مؤهّل بنفسه من غير موافقة (مفيش "مسرحية أمان"). `AuditLog.approved_by` عمود
   جديد بيسجّل مين نفّذ ومين وافق منفصلين. `refund_order_item` أصلاً مدير+ (`require_permission`)،
   فمحتاجش تعديل. شاشة `OrderDetailModal.vue` بقى فيها اختيار مدير + إدخال PIN لما المنفّذ أقل من مدير.
2. **Operator PIN switch** — `POST /pins/switch` (نادل+ مطلوب كإثبات "فيه terminal session شغالة")
   بيصدر JWT جديد لمستخدم اتحقق من الـ PIN بتاعه، بدل logout/login كامل لكل تبديل موظف على نفس
   الكاشير. **مش نظام مصادقة مواز** — بيستخدم نفس `create_access_token` الموجود بالظبط. مقفول على
   أدوار level≤60 (`PIN_SWITCH_MAX_ROLE_LEVEL`) — accountant/hr_manager/admin/super_admin محتاجين
   إيميل+باسورد+2FA كامل دايمًا، وإلا كان PIN بـ4 أرقام هيبقى تحايل حقيقي على الـ 2FA الإلزامي. **باج
   routing حقيقي اتكشف قبل الدمج**: `/pins/switch` كان مسجّل بعد `/pins/{user_id}` في الراوتر، فأي طلب
   ليه كان بيوصل فعليًا لـ `get_user_pin_status`/`set_user_pin` (403 "يتطلب صلاحية مدير" مضلّلة) —
   Starlette بيطابق المسارات بترتيب التسجيل، مش بالتخصيص. اتصلح بإعادة الترتيب. `OperatorSwitchModal.vue`
   جديدة في هيدر `FieldLayout` (كل شاشات `/pos` و`/waiter`).
3. **تأكيد عدّ الكاش الأعمى (blind count)** — تحقّق كامل (backend + frontend) إن قفل الوردية فعلاً
   blind: الفرونت إند ما بيجيبش/يعرضش `expected_cash` قبل ما الكاشير يبعت عدّه، والباك إند بيتجاهل أي
   `expected_cash` العميل يحاول يبعته في جسم طلب القفل ويحسبه بنفسه سيرفر-سايد. مكانش محتاج أي تعديل —
   اتأكد بس بتست HTTP جديد يثبت السلوك ده صراحةً بدل ما يفترضه.
4. **Variants حقيقية** (`MenuItemVariant`/`CafeItemVariant`) — تأكيد بقراءة الكود إن الـ extras
   الموجودة (`MenuItemExtra.price_addition` بس، مفيش ربط recipe/BOM خالص) والوصفة (مربوطة بالصنف ككل)
   ماكانش عندهم أي طريقة يعبّروا عن "حجم مختلف = سعر ووصفة مختلفين تمامًا" (كابتشينو صغير/كبير). جداول
   وصفة منفصلة لكل متغيّر (`menu_item_variant_recipe_lines`) عمدًا — مش عمود `variant_id` على الوصفة
   الأصلية — عشان `MenuItem.recipe_lines` (المستخدمة في `compute_menu_item_cost`/خصم المخزون/تقرير
   تكلفة الطعام اللي اتبنى إمبارح بالظبط) تفضل تعني نفس الحاجة بالضبط من غير أي فلترة بأثر رجعي.
   تقرير تكلفة الطعام بقى بيتجمّع بـ `(menu_item_id, variant_id)` بدل `menu_item_id` بس — وإلا سعر/وصفة
   المتغيّر كانوا هيتخلطوا في متوسط مضلّل. اختيار المتغيّر بقى إجباري في شاشة POS (مطعم+كافيه) لو الصنف
   عنده متغيّرات متاحة، وإدارة المتغيّرات اتضافت لشاشة الوصفات (`RecipesView.vue`).
5. **محرك الخصم — Happy Hour + نطاق + كومبو** — `condition_type="time_of_day"` (`"HH:MM-HH:MM"`، مدى
   عابر لمنتصف الليل مدعوم)، `scope_type: order|outlet|category|item` (خصم مقيّد بمطعم/كافيه بس، أو
   فئة/صنف بعينه)، و`combo_fixed_price` (سعر ثابت لحزمة أصناف). **باج توقيت حقيقي اتصلح أثناء الربط**:
   `apply_order_discount`/`_recompute_discount_for_rule` كانوا بياخدوا `order.created_at` UTC مباشرة —
   نفس فئة باج §13 CLAUDE.md، اتكشفت هنا لأن Happy Hour مستحيل يتفحص صح من غيرها. الكافيه اتضم فعليًا
   لأول مرة لمحرك الخصم (كان عنده عمود `discount_amount` من غير أي كود بيكتبه خالص).

**تعارضات حقيقية اتكشفوا وقت الدمج المشترك** (الأربع فروع دول + شغلي المباشر على PIN/operator-switch
كلهم اتفرّعوا من نفس نقطة البداية `c4a7f0e2b619` بشكل مستقل):
1. **3 migrations متفرّعة من نفس الأب** — `1ad64b31da0c` (PIN)، `d3f6a8c1b4e9` (نطاق الخصم)،
   `7b209880c396` (variants) — اتحلّت بإعادة ترتيبهم تسلسليًا (نفس أسلوب حل التعارض في الجولات
   السابقة) لحد ما بقى فيه alembic head واحد بس.
2. **تعارض سلوك حقيقي بين PIN approval ومحرك الخصم** — تست `test_discount_recomputed_on_new_lower_
   subtotal_after_void` (كافيه) كان بيستخدم كاشير عشان يلغي صنف من غير موافقة PIN، اللي بقى مرفوض
   دلوقتي بحق (400). اتصلح باستخدام مدير بدل كاشير — موضوع التست recompute الخصم مش آلية الـ PIN نفسها.
3. تعارضات إضافية بسيطة في `restaurant/services.py`/`cafe/services.py` (نفس الملفات اتلمست من 3
   فروع مختلفة في أماكن غير متداخلة) — اتحلّت تلقائيًا (git auto-merge) وتأكدت يدويًا.

**التحقق النهائي بعد الدمج الكامل** (مش بس كل فرع لوحده):
- `pytest tests/ -v` → **1496 اختبار، كلهم عدّوا** (1426 → 1496)، بما فيهم اختبارين حقيقيين مش متعلقين
  بأي حاجة من الشغل ده (`test_b2b_checkin_uses_resort_local_date_for_quota_day`،
  `test_restaurant_covers_reflects_real_guest_counts`) كانوا عندهم باجات فيكستشرز pre-existing
  اتكشفوا بالصدفة لما الساعة الحقيقية عدّت منتصف ليل 2026-07-07→08 أثناء الجلسة دي — اتصلحوا كمان.
- `alembic upgrade head` اتجرّب فعليًا على قاعدة بيانات Postgres حقيقية (مؤقتة، اتمسحت بعد التأكد) —
  السلسلة الكاملة (33 migration) اشتغلت من غير أي خطأ، `python -m app.seed` اشتغل صح بعدها.
- `pnpm --filter el-kheima type-check`/`build` — نضاف.

---

## 🍽️ إصلاح تصنيف منيو المطعم/الكافيه + توجيه شاشات المطبخ — 2026-07-08

Mohamed راجع النتيجة وكشف فجوة حقيقية اتفهمت غلط في الجولات السابقة: المطعم والكافيه بيانهم متصنّفين
غلط من الأساس، ومحطات المطبخ (KDS) متأثرة فعليًا بنفس المشكلة. بعت ملفين بيانات حقيقية
(`Restaurant_menu.json` + `beverages_menu.json`) للتصحيح.

**التشخيص (بالكود، مش تخمين):**
1. `seed.py::_seed_menus` القديمة كانت بتحط أطباق حقيقية محتاجة مطبخ فعلي (بيتزا/باستا/حواوشي/
   ساندوتشات/فطار — 55 صنف) في موديول **الكافيه**، بينما موديول **المطعم** فضل بـ4 أصناف بس (فاين
   داينينج). غلطة استيراد بيانات، مش تصميم مقصود.
2. `CafeItem` (الموديل نفسه) **مفهوش عمود `station` خالص** — عكس `MenuItem.station` (`hot|grill|cold|
   bar|dessert`) اللي بيوجّه الـ KDS تلقائيًا. النتيجة: `cafe.services.update_order_status` كان بيحطّ
   `station="bar"` **ثابت في الكود** لكل تذكرة كافيه، مهما كان الصنف بيتزا محتاجة فرن أو حواوشي محتاج
   جريل.
3. الأثر الفعلي على الشاشات: `kds/kitchen` بيجيب بس `module=restaurant` — أي أكل كافيه عمره ما وصل
   لشاشة المطبخ خالص. `kds/bar` بيجيب **كل** تذاكر الكافيه (بدون فلترة حقيقية) + تذاكر المطعم بمحطة bar
   بس — يعني شاشة البار كانت مزدحمة بأطباق كاملة (بيتزا/باستا/حواوشي) جنب المشروبات الفعلية.
4. الوصفات (Recipe/BOM) اللي اتبنت في جولة سابقة ورّثت نفس الغلطة — وصفات البرجر/المارجريتا/الحواوشي
   كانت مربوطة بـ `CafeItem` (الموديول الغلط) لأن الأصناف دي كانت موجودة هناك أصلاً.

**الحل (قرار Mohamed — إصلاح تكتيكي دلوقتي، تأجيل الدمج الكامل في تاب واحد كقرار منفصل):**
1. **منيو حقيقي مُصحّح بالكامل** من الملفين اللي بعتهم Mohamed:
   - **المطعم**: 9 فئات حقيقية (المقبلات، الشوربة، السلطة، سندوتشات، الأطباق الرئيسية، البيتزا،
     الباستا، الإضافات، الحلويات) — **44 صنف**، كل صنف بمحطة KDS محسوبة من طريقة التحضير الفعلية
     المذكورة في وصف الصنف (مشوي→`grill`، مقلي/ووك→`hot`، بدون طهي→`cold`، حلو→`dessert`) — مش تخمين.
   - **الكافيه**: 6 فئات مشروبات حقيقية بس (كوكتيلات، عصائر طازجة، ركنة الصودا، سلطة فواكه، مشروبات
     باردة، مشروبات ساخنة) — **60 صنف**، كلهم `station="bar"` (السعر = `new_price` من الملف المصدر،
     الأصناف بـ`status="removed"` استُبعدت عمدًا لأنها متوقفة فعليًا). مفيش أكل خالص في الكافيه دلوقتي.
2. **`CafeItem.station` عمود جديد** (migration `8b1b5d6ced99`، افتراضي `"bar"`) — نفس بنية
   `MenuItem.station` بالظبط.
3. **`cafe.services.update_order_status` بقى بيقسّم الأصناف حسب المحطة الفعلية** (نفس منطق
   `restaurant.services` بالظبط: تذكرة منفصلة لكل محطة موجودة في الطلب) بدل `station="bar"` ثابت —
   لو الكافيه ضاف صنف مطبخ حقيقي مستقبلًا، هيتوجّه صح تلقائيًا.
4. **13 وصفة/BOM حقيقية جديدة** (كانت 3 توضيحية مربوطة بأصناف غلط) — 21 مكوّن مخزني بأسعار سوق مصري
   واقعية (2026)، وصفات تغطي كل محطات المطبخ: برجر لحمة، 3 بيتزا (مارجريتا/سلامي/تونة)، مكرونة صوص
   أحمر، جريل دجاج/لحمة/جمبري، فرايد كاليماري، سلطة سيزار/جريك، فرنش فرايز، موز مقلي.
5. **2 تست HTTP حقيقي جديد** يثبتان الإصلاح فعليًا (مش بس بيفترضاه): طلب كافيه بصنفين من محطتين
   مختلفتين بيولّد تذكرتين منفصلتين بالمحطة الصح لكل واحدة، وصنف كافيه بمحطة `hot` فعليًا بيوصل
   لشاشة `kds/kitchen` (كانت مستحيلة قبل الإصلاح).

**التحقق**: `pytest tests/ -v` → **1498 اختبار، كلهم عدّوا** (1496 → 1498). `alembic upgrade head` على
DB فاضية تمامًا (33→34 migration)، `python -m app.seed` اشتغل صح، وتأكيد مباشر بـ SQL إن كل فئات
المطعم بمحطاتها الصح وكل الكافيه `bar` فعلاً. `pnpm --filter el-kheima type-check`/`build` نضاف.

**مؤجَّل عمدًا (قرار Mohamed)**: دمج المطعم والكافيه في تاب POS واحد (زي Foodics — كاشير واحد يشوف
المنيوهين مع بعض بدل شاشتين منفصلتين). ده قرار معماري كبير حقيقي — الموديولين لسه منفصلين تمامًا
(`Order`/`CafeOrder` جداول مختلفة، cart منفصل تمامًا، شاشتين POS منفصلتين) مش تطبيق واحد بواجهتين، ودمجهم
حقيقي معناه إعادة تصميم تمس كل حاجة اتبنت على الموديولين (الوصفات، الـ variants، تقرير التكلفة، محرك
الخصم، موافقة PIN — كلهم مبنيين مرتين منفصلتين). يستاهل جلسة مركّزة لوحدها، زي قرار إيراد الغرفة بالظبط.

---

## 🏗️ إزاي المشروع مبني (من غير تعقيد)

المشروع نظامين شغالين مع بعض:

**1. الباك إند (المحرك)** — برنامج بايثون (FastAPI) بيتكلم مع قاعدة بيانات (PostgreSQL) وبيحفظ فيها
كل حاجة: الحجوزات، الفواتير، الموظفين، المخزون... إلخ. مقسّم لـ **14 "موديول"** (زي أقسام في شركة) —
كل موديول له ملفات منفصلة (مطعم لوحده، حسابات لوحده، موارد بشرية لوحدها) عشان لو حصل مشكلة في
حتة، الباقي يفضل شغال.

**2. الفرونت إند (اللي الناس بتشوفه)** — تطبيقين ويب (كانوا 3، اتدمجوا لتطبيقين يوم 2026-07-06):
- **`el-kheima`** — التطبيق اللي الموظفين كلهم بيستخدموه (كاشير، كابتن، مطبخ، إداري، موارد بشرية) —
  ده اللي كان 6 برامج منفصلة قبل كده ودمجناهم في واحد.
- **`public`** — الموقع العام للمنتجع (حجوزات، معلومات) + كل تجربة الضيف بدون تسجيل دخول (كان تطبيق
  `qr` منفصل قبل كده): مسح QR للطلب من المطعم/الكافيه، check-in الشاطئ، استبيان الرضا، ونداء
  الجرسون/طلب الفاتورة.

**كل الـ 14 موديول دايمًا شغالة** — كان فيه نظام تفعيل/تعطيل ديناميكي (زرار يقفل موديول معيّن من غير
restart)، اتشال بالكامل (2026-07-02) لأن المنتجع واحد مش منتج بيتباع لعملاء بمزايا مختلفة — الحماية
الوحيدة الباقية هي صلاحيات الأدوار العادية (كاشير/مدير/إداري).

---

## ✅ الحقيقة الآن — حالة كل موديول (اتأكد منها فعليًا)

| الموديول | حجم الكود (أسطر) | عدد الـ endpoints | تقييم عام |
|---|---|---|---|
| **core** (النظام الأساسي) | 405 | 20+ | ✅ قوي — تسريب PII حرج على `/auth/register` اتصلح (2026-07-06)؛ **PIN تشغيلي جديد** (`PinCredential`، موافقة مدير على إجراء حسّاس + تبديل مشغّل سريع `POST /pins/switch` — نفس الـ JWT infra، مش نظام مصادقة مواز، مقفول على أدوار level≤60 حماية للـ 2FA الإلزامي) |
| **finance** (الحسابات) | 772+ | 47+ | ✅ قوي — فجوة معمارية حقيقية معروفة (إيراد الغرفة/الفواتير الفعلية مش متسجلين في الدفاتر بنفس الطريقة). **قرار Mohamed اتاخد (2026-07-07)**: حساب واحد موحّد في Finance، بتمييز واضح بين إيراد عقود التايم شير وإيراد حجوزات الغرف — **التنفيذ مؤجَّل عمدًا** (راجع CLAUDE.md §18، بند 0). **محرك الخصم بقى فيه Happy Hour + نطاق (outlet/category/item) + كومبو ثابت السعر** — كان بس خصم على إجمالي الطلب |
| **inventory** (المخزون) | 484 | 25 | ✅ قوي — row-locking حقيقي على خصم المخزون (كان فيه سباق)؛ **يدعم الآن الاستهلاك السالب المتحكَّم فيه** (allow_negative) لخصم وصفات المطعم/الكافيه بدون رفض عملية بيع طعام حقيقية |
| **hr** (الموارد البشرية) | 455 | 43 | ✅ قوي — **2 باج مالي خطير اتصلح**: الجزاء مكانش بيأثر على الراتب، وتحديث الضرائب كان بيصفّر ضريبة الشهر الحالي؛ زرع بيانات حقيقية (كان فاضي 100%)؛ **attendance→payroll pipeline حقيقي جديد** (تأخير/أوفرتايم محسوبة تلقائيًا من بصمات الحضور الفعلية + سياسة حضور قابلة للتحكم، بدل ما تكون كلها إدخال يدوي بحت لكل كشف رواتب) |
| **restaurant** (المطعم) | 476+ | 33+ | ✅ الأنضج — order→kitchen→payment كامل؛ **منيو حقيقي مُصحّح** (44 صنف حقيقي عبر 9 فئات من بيانات Mohamed الفعلية، بدل 4 أصناف placeholder — كان فيه باج تصنيف حقيقي حط أطباق المطعم في موديول الكافيه)، باج توقيت في KDS اتصلح؛ 13 وصفة/BOM حقيقية (خصم مخزون تلقائي)؛ تقرير تكلفة الطعام/COGS (تكلفة نظرية مقابل الإيراد الفعلي + تنبيهات، `/admin/food-cost`)؛ **variants حقيقية جديدة** (سعر ووصفة منفصلين تمامًا لكل حجم/نوع، مش رسم إضافي فوق وصفة ثابتة)؛ **إلغاء صنف من كاشير/نادل بقى محتاج موافقة PIN من مدير** |
| **beach** (الشاطئ) | 475+ | 27+ | ✅ قوي — row-locking حقيقي بعد باج خفي في إصلاح سابق (SQLAlchemy identity map)، عقد B2B منتهي كان بيتقبل، حد ائتمان/تأخر سداد B2B اتضاف (2026-07-06)؛ خريطة شاطئ حية (`/pos/beach-map`، مواقع فعلية بحالة/تشيك-إن حقيقي، بث WebSocket لحظي) |
| **cafe** (الكافيه) | 310+ | 23+ | ✅ **منيو حقيقي مُصحّح** (60 مشروب حقيقي عبر 6 فئات — بقى مشروبات بس، الأكل اللي كان متزروع هنا بالغلط اتنقل للمطعم)، **`station` عمود جديد** (كان ناقص خالص — كل تذكرة كانت متوجّهة لـ"bar" ثابت بغض النظر عن الصنف)، POS شغال، تقرير تكلفة الطعام/COGS، **variants حقيقية جديدة** (نفس ميزة المطعم)، **أول تكامل حقيقي مع محرك الخصم** (كان عنده عمود `discount_amount` من غير أي كود بيكتبه) — لسه بدون أي شاشة إدارة طلبات (لا إلغاء ولا استرجاع من الواجهة) |
| **analytics** (التحليلات) | 264 | 16 | ✅ إيراد/زوار الشاطئ كانوا صفر ثابت في كل التقارير — اتصلح؛ WebSocket الحي اتصلح كمان |
| **timeshare** (التايم شير) | 477+ | 21+ | ✅ row-locking حقيقي على تخصيص الوحدة، دفعات الأقساط بقت بتوصل للدفاتر (كانت مش بتوصل غير الدفعة الأولى) |
| **pms** (الفنادق/الغرف) | 273 | 16 | ✅ خريطة الغرف كانت بتعرض بيانات فاضية (باج واجهة حقيقي) — اتصلح؛ RatePlan بقى مؤثر فعليًا على السعر |
| **crm** (العملاء) | 173+ | 22+ | ✅ باج تكرار عملاء حقيقي اتصلح (نفس الضيف كان ممكن يتسجل مرتين)؛ الموديول الأقل نضجًا (Opportunities/Activities لسه API فقط) |
| **maintenance** (الصيانة) | 183 | 14 | ✅ تكليف موظف وهمي كان بينجح بصمت — اتصلح؛ بيانات حقيقية اتزرعت (كان فاضي) |
| **leasing** (الإيجارات) | 251 | 9 | ✅ دفع مبالغ فيه بدون حد + تحصيل إيجار على عقد منتهي — اتصلحوا؛ بيانات حقيقية اتزرعت |
| **hub** (الموقع العام) | 146 | 17 | 🟡 بسيط |

كلهم دايمًا شغالين — مفيش "مفعّل/مقفول" تاني (اتشال نظام التفعيل بالكامل، شوف تحت).

---

## 🎯 اللي اتعمل النهاردة (2026-07-02) بالتفصيل

1. **رجّعنا wego-core للنسخة الحقيقية** بعد ما كانت اتنسخت غلط جوه المشروع من غير إذن.
2. **الكابتن أوردر** — بقى فيه hold (تأجيل طلب) + اختيار الإضافات + إلغاء صنف بسبب — كانت كلها ناقصة.
3. **الكافيه** — كبر من نص المطعم لحد قريب منه (172→310 سطر).
4. **صلاحيات دقيقة لكل شاشة** — مش بس 5 درجات (كاشير/مدير/...)، دلوقتي ممكن تدي شخص معيّن صلاحية
   محددة لحاجة واحدة بس.
5. **الموظف بقى مرتبط بحسابه** — أي موظف يقدر يشوف حضوره وإجازاته ومرتبه من نفسه.
6. **عملة اليورو والدولار** — اتضافت فعليًا، مش بس شكلية. جرّبناها بأرقام حقيقية: فاتورة 100 دولار
   طلعت بالظبط 4800 جنيه في التقرير (بسعر صرف 48 جنيه/دولار).
7. **الشاطئ** — كان فيه فجوة حقيقية: الإلغاء كان من غير سبب، والمبيعات ما كانتش بترتبط بوردية
   الكاشير. اتصلحت الاتنين النهاردة.
8. **شيل نظام تفعيل/تعطيل الموديولات بالكامل** — كل الـ 14 موديول بقوا دايمًا شغالين زي core/finance
   (بعد نقاش وقرار واعي إن المنتجع الواحد معندوش احتياج حقيقي لتفعيل/تعطيل ديناميكي). اتشال من الباك
   إند (الجدول، الـ endpoint، الـ dependency على كل route) والفرونت إند (الـ store، فلترة القوائم)
   بالكامل، بدون أي أثر — 45 ملف اتلمسوا.
9. **التايم شير — مراجعة فجوات مقابل elkheima-beach-resort** — اتأكد إن التايم شير في resort-os كان
   أصلاً كامل تقريبًا (وفي حاجات أحسن من elkheima نفسه). لقينا 3 حاجات حقيقية: **باج فعلي** كان بيمنع
   تجميد حجوزات المتأخرين في السداد يشتغل خالص (كان بيستخدم عمود غلط بدل الـ relationship الصحيح)،
   تحقق ناقص من تاريخ الانتهاء بعد تاريخ البداية، وحساب "نصيب المنتجع بعد حصة الشريك" كان موجود بس مش
   ظاهر في أي تقرير. الثلاثة اتصلحوا واتأكد منهم بأرقام حقيقية live.
10. **شاشات المطبخ (KDS) — تقسيم حقيقي حسب المحطة** — كان الموديول فيه كل البنية التحتية (محطة لكل
    صنف hot/grill/cold/bar/dessert، شاشة KDS قابلة للتهيئة) لكن التذكرة الفعلية كانت بتتعمل واحدة بس
    لكل الطلب بمحطة ثابتة اسمها "kitchen" — يعني التقسيم مكنش شغال خالص عمليًا. اتصلحت: كل طلب بيتقسّم
    دلوقتي لتذكرة منفصلة لكل محطة فعلية للأصناف اللي فيه. لقينا كمان 3 باجات حقيقية في شاشتي الفرونت
    إند (المطبخ والبار) أثناء المراجعة: كانت بتقرأ حقل مش موجود في الرد (`items` بدل `items_snapshot`)
    يعني الأصناف كانت بتظهر فاضية دايمًا، زرار "جاهز" كان بيبعت على مسار API غلط وبقيمة حالة مرفوضة من
    التحقق (`ready` بدل `done`)، وموديول الكافيه كان مستحيل يظهر في شاشة البار لأن الـ endpoint كان
    مقفول على "restaurant" بس. الأربعة اتصلحوا، 3 اختبارات جديدة، واتأكد منها live بتشغيل الكود الحقيقي
    مقابل قاعدة البيانات (طلب فيه 3 أصناف من 3 محطات مختلفة اتقسم لـ 3 تذاكر صح، والفلترة بمحطة واحدة
    رجّعت التذكرة الصح بس).
11. **عدّ النقدية بالفئة عند قفل الوردية (POS Money Count)** — قبل كده الكاشير كان بيكتب رقم واحد
    "الكاش المعدود" بإيده من غير أي إثبات. دلوقتي في اختيار (مش إجباري، للتوافق مع القديم) إن الكاشير
    يعدّ الكاش بالفئة (200ج × كذا ورقة، 100ج × كذا...) والسيرفر هو اللي بيجمع الرقم النهائي من العدّ
    نفسه — مش من رقم منفصل — وبيحفظ كل فئة لوحدها في جدول جديد (`cashier_shift_cash_counts`) للتدقيق،
    وبتظهر في تقرير نهاية الوردية (PDF + JSON). اتأكد منها live: وردية برصيد افتتاح 500، اتقفلت بعدّ
    200ج×2 + 50ج×1، السيرفر حسب 450 بالظبط وسجّل الفرق (variance) -50 وحفظ الفئتين في قاعدة البيانات.
12. **مراجعة شاملة بالذكاء الكامل — تنظيف كود + استكمال نواقص + تجربة حية + رفع GitHub** — مراجعة
    كاملة للباك إند والفرونت إند بأكملهم (مش موديول واحد)، عن طريق فحص عميق مستقل لكل جزء، بعدها
    إصلاح شخصي (مش تفويض أعمى) لكل حاجة حقيقية اتلاقت:
    - **نصوص إيطالية غلط** كانت متسربة في تعليقات/رسائل خطأ في 4 موديولات (مطعم، حسابات، موارد بشرية،
      مخزون) — أثر من كتابة سابقة مختلطة اللغة. اتنضّفت كلها للعربي، وكمان **رسائل خطأ حقيقية** كانت
      بتوصل للمستخدم بالإيطالي (قفل الفترة المحاسبية، عدم توازن القيد، تذكرة مش موجودة) — دي كانت
      باجات فعلية مش بس تجميل.
    - **صيانة وقائية كانت بتتكرر للأبد** — أمر صيانة وقائي لما يخلص، الجدول الدوري بتاعه (next_due) كان
      مبيتحدّثش أبداً، يعني نفس الجدول كان هيولّد أمر صيانة جديد كل يوم للأبد. اتصلحت بربط كل أمر
      وقائي بالجدول اللي ولّده (عمود جديد `work_orders.schedule_id`) وتحديث الجدول أوتوماتيك عند
      الإكمال.
    - **إيصال إيجار كان بيعرض غرامة قديمة** — كان بيحسب الغرامة الحقيقية بس يعرض قيمة قديمة مخزّنة
      (ممكن تكون صفر) بدل المحسوبة لحظيًا. اتصلحت، واتأكد منها بمقارنة نص PDF فعلي بالرقم الصح.
    - **تجميد حجوزات التايم شير كان بيفوّت الأقساط المدفوعة جزئياً** — قسط اتسدد نصه وفات معاده كان
      يفضل "partial" للأبد بدل ما يتحول "overdue"، يعني عقد فيه سداد جزئي متأخر ما كانش بيتجمد رغم
      إنه متأخر فعلاً. اتصلحت.
    - **شاشة "الحضور والانصراف" (self-service) كانت مبنية بالكامل في الفرونت إند ومستنية backend
      مش موجود خالص** — زرار "تسجيل حضور/انصراف" كان بينادي على endpoints مش موجودة أصلاً. اتبنى
      الـ backend من الصفر (`POST /hr/me/attendance/punch-in|out`، حساب ساعات العمل تلقائي) واتربط
      بالفرونت إند، واتأكد منه live بحساب حقيقي (8 ساعات دوام ظهرت بالظبط 8.0 في الرد).
    - **شاشات "طلب إجازة" و"قسائم الراتب" و"ملفي الشخصي" (self-service) كانت بتنادي endpoints غلط
      أو غير موجودة** أصلاً (بعضها كان بينادي `/hr/leaves` الإداري بدل `/hr/me/leaves` الخاص
      بالموظف، وبعضها كان بيقرأ حقول من `/auth/me` مش موجودة فيه خالص زي `job_title`/`department`).
      الأربع شاشات اتصلحت لتنادي الـ endpoints الصح بأسماء الحقول الصح، واتأكد من طلب إجازة حقيقي
      live (من إنشاء نوع إجازة لحد تقديم الطلب وحساب عدد الأيام صح).
    - **تاب "نظرة عامة" في شاشة الحسابات (Finance)** كان بينادي `/finance/dashboard` — endpoint مش
      موجود خالص، فالتاب كان بيفضل فاضي دايمًا. اتوصل بـ `/finance/reports/income-statement` الحقيقي.
    - **صفحة "المخزون" مكررة في القائمة الجانبية** — نسختين، واحدة شغالة فعلاً (`/admin/inventory`)
      والتانية (`/ops/inventory`) كانت مجرد "سيتم تطوير هذه الصفحة" فاضية. اتشالت النسخة الفاضية.
    - **كود ميت اتشال**: دالة تحقق تواريخ الحجز في PMS كانت متكررة ومش مستخدمة (النسخة الحقيقية في
      `services.py`)، عدة دوال CRUD يتيمة بصفر استخدام في الموارد البشرية/الحسابات/الصيانة، وخاصية
      "قائمة الانتظار" في التايم شير مبنية بالكامل (endpoints شغالة) لكن جزء منها (انتهاء الصلاحية
      التلقائي) لسه مش متكامل — اتوثّق كخطة مش باج. 52 استيراد غير مستخدم اتنضّفوا بأداة `ruff`.
    - النتيجة: 726 → **734 اختبار** (8 اختبارات جديدة تغطي الباجات دي تحديدًا)، كل الفرونت إند
      `type-check` نضيف، وكل حاجة اتصلحت اتجرّبت **live فعليًا** (مش بس تست) — طلب حجز حقيقي، تسجيل
      حضور حقيقي، طلب إجازة حقيقي، إغلاق وردية حقيقي.

**باجات حقيقية اتلقت واتصلحت أثناء المراجعة** (مش حاجات افتراضية، حاجات كانت هتكسر فعليًا):
- كل رسائل الخطأ من نوع 404 في المشروع كله كانت بتفقد تفاصيلها الحقيقية (باج قديم في المكتبة
  المشتركة، اتوثّق مش اتصلح لأنه بيأثر على مشاريع تانية).
- endpoint جديد لأسعار الصرف كان بيرجع خطأ 500 بسبب غلطة برمجية بسيطة — اتصلحت واتأكد منها.

---

## 🎯 المرحلة التانية — "اعمل كل ما سبق" (2026-07-03) بالتفصيل

بعد المراجعة الشاملة فوق، اتاخد قرار ننفّذ كل البنود المؤجّلة اللي كانت متوثّقة تحت (ما عدا تجربة
الـ VPS الحقيقي — اتأجّلت بقرار منك لحد ما يبقى فيه سيرفر جاهز). كل بند اتنفّذ + اتعمله تست + اتأكد
منه **live** فعليًا مقابل قاعدة البيانات/الـ API الحقيقي:

1. **دفتر اليومية بعملة أجنبية فعليًا** — دالة مشتركة جديدة (`post_simple_revenue_journal`) بتحسب
   المعادل بالجنيه وقت الترحيل نفسه وتسجّل العملة الأصلية وسعر الصرف على القيد. الـ 6 موديولات
   (مطعم/كافيه/شاطئ/PMS/تايم شير/إيجارات) بقوا بينادوا الدالة دي بدل تكرار نفس الكود 6 مرات.
2. **سجل تدقيق (Audit Log) اتوسّع فعليًا** — تغيير راتب موظف أو قفل فترة محاسبية دلوقتي بيسجّل مين
   غيّر إيه وإمتى في `AuditLog` — مكانش بيتسجّل قبل كده.
3. **ربط العميل (CRM) بمشترياته الفعلية** — أضيف عمود `customer_id` في المطعم/الكافيه/الشاطئ/PMS،
   ودلوقتي أي طلب/حجز مربوط بعميل بيحدّث `total_spent`/`visits_count` بتاعه أوتوماتيك عند الدفع —
   الدالة كانت موجودة من زمان بس محدّش كان بينادي عليها.
4. **"الدفع على حساب الغرفة" (Charge to Room) — اشتغل فعليًا** — أي طلب مطعم/كافيه/شاطئ دلوقتي
   ممكن يتحاسب على غرفة ضيف مقيم (Folio) بدل الكاش المباشر، ويتجمع كله وقت الـ checkout. لقينا كمان
   **باج حقيقي كان نايم**: الشاطئ كان بيقبل `folio_id` بس عمره ما كان بيعمل `FolioCharge` فعلي — يعني
   لو حصل (نظريًا) كانت الإيرادات هتتحسب مرتين. اتصلح.
5. **تنبيهات واتساب حقيقية** — أكتر من 9 أماكن (Celery tasks: تايم شير، حسابات، إيجارات، CRM، صيانة،
   مخزون، الموقع العام، موارد بشرية) كانت بتسجّل "TODO" بدل ما تبعت — دلوقتي بتبعت فعليًا عبر
   `wego_core.whatsapp`. لقينا وصلحنا **باج توقيت حقيقي** في تنبيه تجاوز الحصة (B2B quota) في الشاطئ:
   كان بيتحقق بالعدد قبل الزيادة مش بعدها، يعني التنبيه كان بيوصل متأخر بمعاملة كاملة.
6. **ملاحظات تسليم الوردية** — الكاشير اللي بيقفل الوردية يقدر يسيب ملاحظة نصية، وأول حاجة اللي هيفتح
   الوردية الجاية بيشوفها — مفيدة لحاجات زي "فيه فكة ناقصة" أو "العميل الفلاني هيرجع يسدد باقي حسابه".
7. **لوحة أداء الموظفين (Sales Leaderboard)** — تقرير جديد `GET /hr/leaderboard` بيرتّب الموظفين
   حسب المبيعات الفعلية (مطعم + كافيه + شاطئ مجمّعين) في فترة معيّنة.
8. **إعادة اتصال WebSocket تلقائي** — شاشتي المطبخ والبار (KDS) كانوا بيعتمدوا على polling كل 15
   ثانية بس. دلوقتي فيهم اتصال WebSocket لحظي حقيقي (مش عرض بس) بإعادة اتصال أوتوماتيك لو النت
   اتقطع، والسيرفر بيبعت تحديث فوري (مش بعد 15 ثانية) لما طلب يتحرك للمطبخ. اتأكد منها بتجربة حقيقية:
   عميل WebSocket حقيقي متصل، طلب اتحرك لحالة "في المطبخ" عبر HTTP منفصل، والرسالة وصلت فورًا. لقينا
   كمان **باج حقيقي**: إعداد الـ proxy في `vite.config.ts` كان بيوجّه WebSocket لمسار مش موجود خالص،
   يعني أي اتصال WebSocket من الفرونت إند كان مستحيل يوصل للباك إند من الأساس.
9. **شاشات الفرونت إند بقت بتستخدم الـ API client المشترك** — 23 شاشة (مش كل الشاشات، بس كل اللي
   فيها بيانات حقيقية محتاجة تسجيل دخول) اتحولت من `axios` مباشر لـ `@resort-os/core`'s `api` —
   دلوقتي لو الجلسة انتهت، أي شاشة فيهم بتحوّل المستخدم لصفحة الدخول أوتوماتيك (زي المفروض من الأول).
   اتسيبت `qr`/`public` من غير تغيير لأنهم من غير تسجيل دخول أصلاً.

النتيجة: 726 → **753 اختبار**، كل الفرونت إند `type-check` + `build` نضيف، migration واحدة جديدة
(head واحد بدون تفرّع)، وكل حاجة اتصلحت اتجرّبت **live فعليًا** — قيد محاسبي حقيقي بعملة أجنبية،
تنبيه واتساب حقيقي (mock)، إغلاق وردية بملاحظة تسليم حقيقية، اتصال WebSocket حقيقي.

**باجات حقيقية اتلقت واتصلحت أثناء المرحلة دي** (مش افتراضية):
- الشاطئ: `folio_id` كان بيتقبل بس عمره ما كان بيعمل `FolioCharge` فعلي (حقل ميت).
- تنبيه تجاوز حصة B2B كان بيتحقق بالعدد القديم قبل الزيادة، فكان بيوصل متأخر معاملة كاملة.
- `vite.config.ts` بروكسي الـ WebSocket كان موجّه لمسار مش موجود خالص، فمفيش اتصال WS كان ممكن يوصل
  للباك إند من الفرونت إند من الأساس.

**مؤجّل بقرارك:** تجربة النشر الفعلية على VPS — لسه مستنيين سيرفر حقيقي (IP + SSH access).

---

## 🎯 المرحلة التالتة — استقلالية كاملة + نسخ احتياطي حقيقي (2026-07-03)

بعد سؤالك "المشروع محتاج إيه عشان يبقى جاهز كامل حقيقي؟"، بدأنا بأكبر حاجتين خطورة: الاعتماد على
`wego_core` كـ local path (كان بيمنع النشر تقنيًا بالكامل)، ومفيش نسخة احتياطية للداتابيز خالص. بعد
نقاش، قررت إن الحل الصح مش بس "تنضيف" الاعتماد، إنما **resort-os يبقى مشروع مستقل بالكامل** — زي
مشروعك التاني "Trucker" — مفيش أي اعتماد خارجي على كود مشترك مع مشاريع تانية.

1. **فصل كامل عن wego_core** — كل البنية التحتية اللي كان resort-os بيستخدمها من الباكدج المشترك
   (auth, JWT, bcrypt, database session, Redis cache, rate limiting, error handling, health checks,
   logging, Sentry, Celery factory, تنبيهات واتساب/إيميل، تقارير PDF/Excel) اتنقلت بالكامل وبقت كود
   **مملوك** في `backend/app/core/kernel/` — مش نسخة "vendored" بتتزامن مع مصدر خارجي زي المحاولة
   الفاشلة قبل كده، دلوقتي كود resort-os نفسه 100%. 18 ملف اتكتب من الصفر (auth/repository.py،
   auth/service.py، auth/router.py، security.py، database.py، cache.py، errors.py، health.py،
   logging_setup.py، middleware.py، sentry.py، whatsapp.py، email_service.py، reports.py، worker.py،
   config.py، models/user.py، models/mixins.py)، و24 نقطة استخدام في المشروع (main.py، deps.py،
   config.py، database.py، rate_limit.py، celery_app.py، seed.py، 14 موديول models.py، 8 ملفات
   Celery tasks) اتحوّلت تستورد من الكود المملوك الجديد بدل الباكدج الخارجي. `requirements.txt` بقى
   فيه كل الاعتماديات (`bcrypt`, `pyotp`, `twilio`, `reportlab`, `arabic-reshaper`, `python-bidi`,
   `qrcode`) بأسمائها الحقيقية pinned، من غير أي `-e path` محلي. `Dockerfile` و`docker-compose.prod.yml`
   اتبسّطوا بالكامل — مفيش تاني "second build context" أو "sibling checkout" لمشروع تاني.
   **اتأكد منه live بأقوى شكل ممكن**: بيئة Python نضيفة تمامًا من الصفر (`venv` جديد، `pip install`
   من `requirements.txt` بس، `wego-core` مش متثبّت فيها أصلاً — اتأكد بـ `pip show wego-core` فشل) —
   753 اختبار عدّوا بالكامل فيها، سيرفر حقيقي اتشغّل، تسجيل دخول حقيقي، `GET /auth/me`، إعداد 2FA
   حقيقي (`pyotp`، QR URL حقيقي)، وتوليد PDF حقيقي (فاتورة فندق بعربي، `reportlab` + إعادة تشكيل
   عربي) — كلهم اشتغلوا صح. نفس الشيء اتأكد منه بعد كده على الـ venv الحقيقي بتاع المشروع (مش بس
   واحد مؤقت) — 753 اختبار برضو بعد ما اتشال `wego-core` منه فعليًا.
2. **نسخ احتياطي حقيقي للداتابيز** — `scripts/backup_db.sh` (يعمل `pg_dump` بصيغة مضغوطة، بياخد
   التفاصيل من نفس `DATABASE_URL` اللي التطبيق نفسه بيستخدمه، وبيطبّق سياسة احتفاظ — يمسح النسخ
   الأقدم من 14 يوم افتراضيًا) و`scripts/restore_db.sh` (بياخد ملف نسخة + اسم داتابيز هدف — لو
   الهدف موجود بالفعل وفيه جداول، بيطلب منك تكتب اسم الداتابيز تاني كتأكيد قبل ما يلمس أي حاجة —
   حماية حقيقية ضد استرجاع غلط بيمسح بيانات حية بالغلط)، بالإضافة لـ systemd timer
   (`deploy/systemd/resort-os-backup.{service,timer}`) بيشغّل نسخة احتياطية كل يوم 3 الصبح.
   **اتأكد منه live بدورة كاملة حقيقية**: نسخة احتياطية حقيقية من قاعدة بيانات dev (388K)، استرجاعها
   في قاعدة بيانات منفصلة تمامًا، مقارنة عدد الصفوف (`users:8 | branches:1 | folios:1 |
   journal_entries:7`) وعدد الجداول (113 مقابل 113) — طابقوا بالظبط. وجرّبنا كمان إن حماية التأكيد
   شغالة فعليًا: كتابة نص تأكيد غلط أوقفت العملية تمامًا (`exit 1`) من غير ما تلمس أي بيانات.

النتيجة: مفيش أي حاجة حرجة متبقية تمنع النشر على VPS من الناحية التقنية — الوحيد الباقي هو التجربة
الفعلية على سيرفر حقيقي (مؤجّلة بقرارك لحد ما يبقى فيه سيرفر).

---

## 🎯 المرحلة الرابعة — صلاحيات تفصيلية + إصلاح شامل لواجهة الفرونت إند + تغطية اختبارات (2026-07-03)

بعد سؤالك "من وجهة نظرك إيه المتبقي؟"، طلبت 3 حاجات كبيرة مع بعض: نظام صلاحيات تفصيلي، إصلاح شامل
لواجهة الفرونت إند بواسطة وكلاء (agents) شغالين بالتوازي، وتغطية اختبارات عالية. الثلاثة اتنفّذوا:

1. **نظام صلاحيات تفصيلية حقيقي** — كتالوج صلاحيات (`GET /permissions/catalog`) بيوصف 10 عمليات
   حسّاسة حقيقية عبر 8 موديولات (إلغاء صنف، قفل فترة محاسبية، اعتماد رواتب، إلغاء حجز/عقد، إلخ)،
   endpoint جديد (`GET /permissions/me`) يحسب الصلاحيات الفعلية للمستخدم الحالي، وشاشة إدارة حقيقية
   (`/admin/permissions`، super_admin فقط) تدي مدير القدرة يمنح استثناء لموظف معيّن (مثلاً "امنح
   الجرسون ده صلاحية إلغاء صنف") أو يمنعه من عملية عادةً مسموح له بيها — من غير ما يغيّر دوره الأساسي.
   **باج حقيقي اتكشف واتصلح أثناء البناء**: نظام الصلاحيات كان موجود جزئيًا من زمان (`require_permission`
   dependency) بس **صفر استخدام فعلي في الكود كله** — واكتشفنا كمان إن حتى لو استخدمناه، كان
   مستحيل يشتغل صح، لأن الـ endpoint كان لسه عليه role dependency صلب (`get_cashier_user` مثلاً) بيمنع
   أي حد تحت مستوى الدور بغض النظر عن أي استثناء صريح. اتصلح بجعل `require_permission` هو الحاكم
   الوحيد على الـ 10 endpoints دي. اتأكد منه بتست حقيقي end-to-end: جرسون اتمنع من إلغاء صنف (403)،
   اتمنحله استثناء صريح، حاول تاني نجح (200) — بنفس الدور بالظبط، من غير أي تغيير.
2. **مراجعة شاملة لواجهة الفرونت إند (25 شاشة)** — عن طريق agent استكشاف مستقل، لقينا: شاشتين
   stub بالكامل (`AnalyticsView`, `SettingsView` — نص فاضي)، مكوّنات مشتركة جاهزة بس شبه مش
   مستخدمة (`AppButton`/`AppCard`/`AppBadge`/`AppModal`/`AppInput`/`AppSpinner` — كل واحد مستخدم في
   شاشة أو اتنين بس من أصل 25)، **نظام toast جاهز ومُركّب من زمان بس مستخدم في شاشة واحدة بس** —
   باقي الشاشات كل واحدة بتعمل نسخة محلية من نفس منطق العرض/الاختفاء، و**~15 شاشة بتبلع الأخطاء
   بصمت** (`console.error` بس، من غير أي إشعار للمستخدم). بعد المراجعة، بنينا مكوّنين جدد
   (`EmptyState`, `ConfirmDialogContainer` + `useConfirm()`) واستخدمنا **5 وكلاء شغالين بالتوازي**
   (كل واحد على مجموعة شاشات منفصلة تمامًا عشان محدش يلمس ملف التاني) لإصلاح كل الشاشات الـ 25:
   - كل الأخطاء الصامتة بقت `toast.error()` برسائل عربية حقيقية.
   - `alert()`/`confirm()` (كانوا في شاشة التايم شير والحجوزات بس) اتبدّلوا بـ `useConfirm()`.
   - `AnalyticsView`/`SettingsView` اتبنوا بالكامل من الصفر على endpoints حقيقية (مش وهمية).
   - **فجوة وظيفية حقيقية اتصلحت**: نظام الطلبات offline (لما النت يقطع) كان موجود ومستخدم في
     المطعم بس، مش في الكافيه أو الشاطئ — بالظبط المكانين اللي أكتر عرضة لانقطاع النت (تابلت على
     الشاطئ). اتضاف نفس النظام للاتنين (الـ agent اكتشف إن المكوّن المشترك بيبعت مباشرة على مسار
     المطعم بس، فبنى نسخة محلية مطابقة بس بمسار كل موديول الصح، بدل ما يبعت طلبات كافيه غلط
     لموديول المطعم).
   - **3 باجات حقيقية اتكشفت في شاشة HRView أثناء بناء تاب الحضور**: كانت بتقرأ أسماء حقول غلط من
     الـ API (`job_title` بدل `position`، `period_start/end` بدل `period_year/month`، `employee_name`
     بدل عمل lookup صح) — يعني بيانات الموظفين/الرواتب/الإجازات في الشاشة دي كانت فاضية أو غلط فعليًا
     في الإنتاج قبل كده.
3. **تغطية اختبارات — 753 → 849 اختبار**، مع رفع الموديولات الأضعف بشكل حقيقي (مش padding —
   كل تست بيتأكد من status code + قيمة حقيقية + أحيانًا تغيير فعلي في الداتابيز):
   - `analytics`: 30% → 84%
   - `hub`: 38% → 84%
   - `core`: 41% → 85%
   - `maintenance`: 43% → 79%
   - `crm`: 51% → 78%
   - `inventory`: 51% → 82%
   **باج إنتاج حقيقي اتكشف واتصلح أثناء كتابة التستات**: `/analytics/revenue` و`/analytics/dashboard`
   كانوا بيحسبوا إيراد الشاطئ بحقل مش موجود أصلاً في الموديل (`BeachTransaction.visit_date`/`total_paid`
   بدل `tx_date`/`total_amount`+`vat_amount`) — الخطأ كان بيتبلع بصمت (`_safe_query` كان بيمسك أي
   استثناء ويرجّع None)، يعني **إيراد الشاطئ في التحليلات كان `None`/صفر دايمًا، من أول ما الـ endpoint
   اتعمل**. اتصلح واتأكد منه بتست حقيقي (معاملة شاطئ 200ج + معاملة ملغاة 100ج → المجموع 228ج بالظبط،
   مش 328 ولا صفر).

النتيجة: 753 → **849 اختبار**، Coverage الإجمالي 76% → 80%، نظام صلاحيات حقيقي شغال end-to-end، 25
شاشة فرونت إند بقت متسقة (toast/confirm/error-states موحّدة)، وباجين إنتاج حقيقيين (إيراد الشاطئ في
التحليلات، 3 حقول غلط في HRView) اتكشفوا واتصلحوا كأثر جانبي للمراجعة الدقيقة، مش المطلوب الأصلي.

---

## 🎯 المرحلة الخامسة — مطعم/شاطئ/حسابات "زي برامج حقيقية" + إيصال حراري + CRM Campaigns (2026-07-04)

طلبت مطعم/شاطئ/حسابات يكونوا بجودة برامج POS ومنتجعات حقيقية، مع طباعة إيصال حقيقية في نقطة البيع،
وبعدين وسّعنا لموقع عام حقيقي وميزات كانت جداول ميتة في الداتابيز.

1. **الموقع العام (public)** — بُني من الصفر بمحتوى حقيقي (شعار، اسم "El Kheima Beach Resort"،
   بيانات تواصل حقيقية) من ملفات التسويق الفعلية للمنتجع، قسم غرف حي (`GET /pms/public/room-types`)،
   وصفحة "المطعم والكافيه" (`/dining`) بتعرض المنيو الحقيقي الكامل. لُقيت وصُلحت 3 باجات فعلية أثناء
   التجربة الحية: badges المميزات كانت بتعرض JSON خام مكسور بدل tags نضيفة، قائمة نوع الغرفة في نموذج
   الحجز كانت لسه قايمة قديمة وهمية (4 قيم) مش متطابقة مع الـ 5 أنواع الحقيقية، وbody كان فيه
   `direction: rtl` مثبّت بالكود بيلغي تبديل اللغة الفعلي للـ en/it بصريًا.
2. **تجربة بشرية حية للموظفين** كشفت وصلحت: بوابة الـ 2FA الإجبارية كانت من غير أي شاشة setup في
   الفرونت إند خالص (أي super_admin/accountant جديد كان يشوف كل شاشة فاضية بدون تفسير)، حجوزات PMS
   كانت 100% معطلة (شكل الطلب غلط)، والشاطئ كان بيعرض أسعار "NaN".
3. **دورة طلب المطعم/الكافيه بالكامل بقت شغالة فعليًا** — كانت مكسورة تمامًا: طلبات الكافيه بترجع 422
   دايمًا (شكل الطلب غلط)، ولا شاشة كاشير كانت بتبعت الطلب فعليًا للمطبخ (KDS تذاكر ما كانتش بتتعمل
   خالص)، ومفيش أي واجهة لإتمام الدفع على طلب مطعم. اتصلحت الثلاثة + اتصلحت ثغرة صلاحيات حقيقية
   (أي جرسون كان يقدر "يقفل" الحساب — عملية مالية لازم كاشير).
4. **طباعة الإيصال في نقطة البيع** — المطعم/الكافيه/الشاطئ التلاتة كانوا بيولّدوا إيصال بحجم A4 كامل
   بدل حجم رول الطابعة الحرارية الحقيقي (80mm) اللي كل ماكينة POS فعلية بتستخدمه. اتصلح الثلاثة،
   واتضاف تشغيل تلقائي لشاشة الطباعة + خطة بديلة (تحميل قسري) لو المتصفح قفل الـ popup — مكنش موجود
   خالص في المطعم/الكافيه قبل كده.
5. **باجين محاسبيين حقيقيين اتكشفوا وصُلحوا**: إلغاء عملية شاطئ كان بيعكس المخزون بس — الإيراد كان
   فاضل مسجّل في الدفاتر للأبد حتى بعد الإلغاء (لو كاش)، أو الضيف كان لسه محمّل على فاتورته بحاجة
   اتلغت (لو Charge to Room). و`Folio.total` (اللي أي شاشة بتعرضه مباشرة) كان بيفضل قديم بعد أي شحنة
   مطعم/كافيه/شاطئ لأن الكود كان بيضيف الشحنة من غير ما يعيد حساب الإجمالي المخزّن.
6. **إهلاك الأصول الثابتة + التسوية البنكية** — ميزتين حقيقيتين كانتا ناقصتين تمامًا من الحسابات،
   اتبنوا بالكامل في الباك إند (إهلاك خطي شهري idempotent بيرحّل قيد يومية متوازن، تسوية بنكية بمطابقة
   تلقائية) — **الفرونت إند لسه ناقص** (شوف "لسه محتاج شغل" تحت).
7. **مرتجع بعد الدفع** — المطعم والكافيه كانا بيقولوا للكاشير حرفيًا "استخدم مرتجع بعد الدفع" لميزة
   مش موجودة أصلاً. اتبنت فعليًا مع توزيع نسبي صحيح للضريبة/الخدمة.
8. **CRM Campaigns** — جدول `campaigns` كان موجود في الداتابيز من زمان بدون أي schema/crud/router/
   فرونت إند خالص (جدول ميت 100%). اتبنى بالكامل: إنشاء/تعديل/عرض حملات تسويقية حقيقية من شاشة CRM.

**درس مهم من النهاردة**: 3 وكلاء (agents) اشتغلوا بالتوازي على مطعم-فرونت/CRM/حسابات-فرونت رجعوا كلهم
بعد ثوان معدودة برسالة "session limit" — اتنين منهم عملوا صفر تغيير فعلي رغم إدعاء "تم"، والتالت عمل
شغل حقيقي جيد بس اتقطع قبل ما يخلص (الـ endpoints الفعلية). اتأكد من كل حاجة بمقارنة `git diff` الفعلي
قبل ما نصدّق أي تقرير — نفس الدرس اللي اتوثّق قبل كده، بس بشكل أوضح (تقرير فاضي معناه المهمة اتقطعت
فعليًا، مش بس تقرير مختصر).

النتيجة: 869 → **~910 اختبار**، إيصال حراري حقيقي (اتأكد من أبعاد ملف الـ PDF فعليًا مش بس إن
الكود بيتعمل له compile)، صفر تراجع، migration واحدة (head واحد).

---

## 🎯 المرحلة السادسة — تغطية اختبارات قصوى + CRM/Maintenance/Leasing frontend + تشغيل احترافي + التايم شير الحقيقي (2026-07-04، آخر النهار)

طلبت أعلى نسبة تغطية ممكنة للمطعم/الكافيه/الشاطئ/الحسابات/الموارد البشرية، وشاشات فرونت إند لأي
موديول ناقص، و`scripts/` منظّمة زي مشاريعك التانية، وفي الآخر — التايم شير يبقى شغال حقيقي فعليًا.

1. **تغطية اختبارات — 924 → 1106 اختبار، ~90-95% لكل موديول مستهدف**: cafe (85%→99%، router/crud
   100%)، HR (87%→99%)، finance (91%→**100%**)، beach (router 75%→95%)، restaurant (router 80%→91%،
   crud 99%). كل التستات حقيقية (status code + قيمة فعلية + حالة قاعدة بيانات)، مفيش padding.
   **5 باجات حقيقية اتلقت واتصلحت كأثر جانبي**: كشف/إكسل الرواتب كانا بيطيحوا 500 (`emp.name` بدل
   `emp.full_name`)، قيد اعتماد الرواتب كان دايمًا غير متوازن (حساب تأمينات صاحب عمل غلط بدون قيد
   دائن مقابل — اتشال بدل ما نلفّق رقم)، رقم فاتورة ETA كان ممكن يتصادم بين فروع مختلفة في نفس اليوم
   (unique constraint عالمي بس العداد كان محلي لكل فرع)، فترة محاسبية كانت ممكن تتقفل مرتين وتمسح أثر
   التدقيق، وشاشة الحساب البنكي في الفرونت إند كانت بتقرأ حقل `name_ar` مش موجود أصلاً في `AssetRead`.
2. **CRM Campaigns، Maintenance، Leasing — 3 موديولات كان عندهم باك إند كامل بدون أي فرونت إند خالص**
   بُنيوا بالكامل (شاشات حقيقية، صلاحيات مطابقة تمامًا للباك إند الفعلي، مش تخمين).
3. **`scripts/` اتنظّمت بالكامل** — start/stop/status/restart/logs، PID files حقيقية بدل `/tmp`،
   و**حساب تجريبي واحد لكل دور** (12 حساب، `Demo@123456`) عشان أي بيئة جديدة تقدر تسجّل دخول بأي دور
   فورًا. اتأكد منها live: تشغيل حقيقي، تسجيل دخول حقيقي كمدير (200، JWT حقيقي)، إيقاف نضيف.
4. **التايم شير بقى شغال حقيقي فعليًا** — كانت فيه فجوة عميقة: إنشاء "زيارة" تايم شير عمره ما كان
   بيخصّص وحدة/غرفة حقيقية خالص (الكالندر كان مجرد حساب نظري من `week_number` بدون أي تحقق تعارض
   حقيقي). اتصلحت: موديل جديد `TimeshareUnit` (شاليهات/وحدات منفصلة تمامًا عن غرف الفندق العادية —
   قرار معماري اتأكد منك مباشرة)، تخصيص فعلي مع منع تعارض حجز حقيقي (اتأكد بتست HTTP حقيقي: عقدين
   على نفس الوحدة بفترة متقاطعة، التاني اترفض 400 فعليًا). اتكشفت كمان فجوة أعمق: جدول `rooms`
   الحقيقي في الفندق العادي كان **فاضي تمامًا** (صفر صف) — زرعنا 52 غرفة حقيقية (ترقيم منطقي افتراضي،
   موثّق إنه مش أرقام حقيقية موثّقة من المنتجع) + 22 وحدة تايم شير. **نظام تقييم رضا العميل** كان
   موجود بالكامل في الباك إند (`GuestReview`) من غير أي فرونت إند خالص — اتربط بزيارات التايم شير
   وبُنيت له صفحة تقييم حقيقية للضيف (نجوم + تعليق) في تطبيق `qr`. **بروفايل عميل شامل** جديد في شاشة
   التايم شير — كل عقود/زيارات/أقساط/تقييمات الشخص الواحد في مكان واحد (بالتجميع على رقم الهاتف)،
   يشوفه الموظف والإداري.

النتيجة: 1092 → **1106 اختبار**، migration واحدة جديدة (head واحد)، صفر تراجع في أي مسار قديم
(اتأكد إن مسار تقييم الحجز الفندقي العادي فضل شغال زي ما هو بالظبط).

### المرحلة السابعة (2026-07-04) — "الموديل موجود، الـ API صفر" (جولة تانية) + UI/UX + أمان تسجيل الدخول

1. **Scan منهجي عبر الـ 14 موديول** (نفس فئة باج Lead/Campaign/TenantCashLog القديمة) لقى 3 حالات
   تانية: `CallNote` (crm)، `RotaTemplate` (hr)، `RevenueAuditLog` (finance) — كل واحدة اتعملها
   schema/crud/router + tests كاملة. اكتشاف إضافي أهم أثناء الشغل على `RevenueAuditLog`:
   `services.void_payment` كان موجود بالكامل من غير أي router endpoint — إلغاء دفعة كان مستحيل
   فعليًا عن طريق الـ API. اتضاف `POST /finance/payments/{id}/void` (كتالوج الصلاحيات بقى 11 عملية
   دلوقتي) وبيكتب `RevenueAuditLog` تلقائيًا.
2. **UI/UX quality pass** (وكيل مخصص، اتأكد منه بشكل مستقل) — باج حقيقي في `InventoryView.vue`:
   الشاشة كانت بتقرا أسماء حقول قديمة (`unit_cost`/`reorder_level`/`category`) مش موجودة في
   `ProductRead` الحقيقي — كشف المخزون المنخفض كان بيقارن بـ `undefined` فمكانش بيشتغل خالص من أول ما
   الشاشة اتعملت. اتصلح + 6 شاشات تانية كانت بتبلع فشل التحميل/الإجراء بصمت بقى فيها toast حقيقي.
3. **مراجعة أمان مخصصة لتسجيل الدخول/الحسابات** — 3 ثغرات حقيقية اتصلحت: user-enumeration oracle
   (فرق توقيت + رسالة مختلفة بين إيميل غير موجود وباسورد غلط)، `two_factor_secret` كان متخزّن
   plaintext (بقى Fernet-encrypted)، `SECRET_KEY` ضعيف/افتراضي كان ممكن يشتغل في production بدون أي
   تحقق (بقى فيه validator بيرفض الـ startup). اتأكد كمان إن rate limiting/lockout/refresh rotation/
   CORS/عدم إمكانية تحديد role وقت التسجيل كلهم سليمين فعلًا. أضيف `LOGIN_2FA_ENFORCED` (افتراضيًا
   false) كقدرة جاهزة — الـ 2FA حاليًا enrollment-only مش تحقق حقيقي وقت الدخول، تفعيلها محتاج تعديل
   frontend بسيط يبعت الكود.

النتيجة: 1106 → **1133 اختبار**، صفر migration جديدة (كل الموديلات المتأثرة كان لها جداول موجودة
بالفعل من غير API)، صفر تراجع.

---

## 🚧 لقطة تاريخية لخطط قديمة (ليست قائمة العمل الحالية)

> **تنبيه مهم (2026-07-17):** القسم التالي كُتب في مرحلة أقدم، وبعض بنوده
> اتنفذ أو تغيّر بالفعل في التحديثات الأحدث الموجودة أعلى الملف (مثل
> httpOnly refresh cookie وsplit bill وواجهة الخصم). لا تستخدمه كـbacklog ولا
> تنفذ منه تلقائيًا. الأولويات والقرارات البشرية الحالية في `wagdy.md`، وأي
> وكيل لازم يتحقق من الكود والاختبارات قبل اعتبار بند هنا ناقصًا.

### قرارات مستنية منك
1. **تجربة فعلية على VPS** — عملنا كل ملفات النشر (Docker) + نسخ احتياطي حقيقي، بس ما جربناهمش على
   سيرفر حقيقي لسه.
2. **تفعيل `LOGIN_2FA_ENFORCED`** — القدرة الباك إندية جاهزة ومتأكد منها (شوف المرحلة السابعة فوق)،
   بس تفعيلها الفعلي محتاج تعديل frontend بسيط (شاشة تسجيل الدخول تبعت كود الـ TOTP) — قرار تنفيذي
   بسيط لما تحب.

### شغل حقيقي لسه ما بدأناش فيه (لو حبيت)
- **تكرار كود ترحيل الإيرادات للدفتر** — اتحلّت جزئيًا (شوف بند 1 في المرحلة التانية فوق) — الدالة
  المشتركة موجودة ومستخدمة في الـ 6 موديولات، بس لسه مفيش call site حي لعملة غير الجنيه (كل المعاملات
  الفعلية دلوقتي بالجنيه، فالمسار الأجنبي مجرّب بالتست بس مش بمعاملة حقيقية live لسه).
- **`localStorage` token → `httpOnly cookie`** — تحسين أمان أكبر، لسه معلّق.
- **مزامنة نسخ `backups/` خارج السيرفر** — النسخ الاحتياطي شغال محليًا على نفس السيرفر، بس لو
  السيرفر نفسه اتضرب (مش بس الداتابيز)، النسخ ضاعت معاه. محتاج `rsync`/`rclone` دوري لمكان تاني
  (S3/Backblaze) — ده جزء بنية تحتية خاص بالسيرفر نفسه، موثّق في `DEPLOYMENT.md` §10 بس مش متنفّذ.
- **كتالوج الصلاحيات بقى 11 عملية** — دي أكتر العمليات الحسّاسة إلحاحًا، بس فيه عمليات تانية
  ممكن تستاهل نفس المعاملة لاحقًا لو ظهرت حاجة تشغيلية حقيقية تطلبها.
- **موديول PMS (الفنادق العادي) لسه مش جزء من دفعة التغطية المستهدفة** — `services.py` عند 88%،
  مقارنة بـ 91-100% للموديولات التانية اللي اتستهدفت (مطعم/كافيه/شاطئ/حسابات/موارد بشرية). أقل أولوية
  حاليًا مقارنة بالباقي.
- **split-bill / دفع متعدد على نفس الطلب، تقرير سعة الشاطئ للمدير، زرار الخصم في واجهة POS المطعم**
  (الـ endpoint وتغطيته موجودين، بس مفيش زرار في الواجهة يستخدمه) — بنود مؤجّلة من بحث سابق، مش
  أولوية حرجة.
- **التايم شير**: التخصيص الحقيقي وتقييم رضا العميل اشتغلوا فعليًا النهاردة (شوف المرحلة السادسة
  فوق) — الباقي المحتمل لاحقًا: واجهة لإدارة/نقل تخصيص الوحدة الدائم لعقد قائم (حاليًا بيتحصّل من
  خلال تعديل العقد مباشرة، مفيش شاشة مخصّصة "نقل الوحدة")، وربط تلقائي لـ`booking_id` الفندقي لو
  حبيت الزيارة تستخدم نفس مسار الـ housekeeping/folio بتاع الفندق العادي (قرار معماري متعمد إنه
  مايحصلش دلوقتي — الوحدات منفصلة تمامًا عن غرف الفندق).

---

## 🔑 معلومات عملية للتشغيل

```bash
bash scripts/start.sh             # تشغيل كل حاجة
bash scripts/start.sh --no-frontend   # الباك إند بس
bash scripts/status.sh            # حالة كل خدمة
bash scripts/stop.sh              # إيقاف

cd backend
.venv/bin/pytest tests/ -v     # الرقم بيتغيّر — شغّله بدل الاعتماد على رقم مكتوب
```

**الدخول الافتراضي:** `admin@resortos.local` / `Admin@123456` (super_admin — محتاج 2FA)

---

## 🤖 لو هتفتح جلسة جديدة مع Claude — استخدم البرومبت ده

```
اقرأ /home/wego/projects/resort-os/AGENTS.md ثم CLAUDE.md بالكامل، وبعدهم بداية وأحدث الأقسام
المرتبطة بالمهمة من PROJECT_STATUS.md والقرارات المقبولة في docs/decisions/. راجع wagdy.md لفهم
أولويات Mohamed بلغة بشرية. المشروع اسمه التجاري "El Kheima Beach"، مبني بـ FastAPI + Vue 3،
وفيه 13 موديول دائم (`dining` حل محل `restaurant`/`cafe`). لا تعتمد على رقم اختبارات مكتوب؛ اجمع
أو شغّل الاختبارات المناسبة وتحقق من الكود الفعلي قبل أي ادعاء أو تعديل.
```

هذا الملف نفسه هيتحدّث بعد أي شغل حقيقي جديد.
