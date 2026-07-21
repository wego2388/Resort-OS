# خارطة التنفيذ الذكية المعتمدة على المخاطر والاعتماديات

**الحالة:** خارطة حية؛ Gate 1A وشريحة Dining-paid من Gate 1B وGate 2 وGate 3
مُعتمَدة. Gate 4 منفَّذة بالكامل ومُتحقَّق منها ذاتيًا (2026-07-20)، بانتظار
مراجعة مستقلة قبل الاعتماد. Gate 5 Batch 6 (غرف+تدبير منزلي) منفَّذة
ومُتحقَّق منها ذاتيًا (2026-07-20) — الباقي (~35 شاشة) دفعات لاحقة.
**المصدر:** مراجعة 360° بتاريخ 2026-07-17 + القرارات الموجودة في
`docs/decisions/` + `wagdy.md`.

## لوحة التنفيذ الحالية

| المرحلة | الحالة الآن | المسؤول التنفيذي | المخرج الذي نراجعه قبل الانتقال |
|---|---|---|---|
| Gate 0: baseline وCockpit | **مكتملة** | Codex/ChatGPT | audit + roadmap + UI/UX cockpit + checks |
| Public Phase 0 المرجعية | **مكتملة** (راجعتها Codex على 4 جولات) | Claude | `docs/audits/public-phase-0/` — route/state/assets/content/API/Keep-Adapt-Remove evidence |
| Gate 1A: احتواء Public/QR | **مكتملة (2026-07-17)** — راجع `docs/audits/PRODUCTION_READINESS_AUDIT.md`'s قسم الإغلاق | Claude | commit `fix(security): contain unsafe public guest workflows` — أصغر diff آمن + regression/failure tests، اعتمدتها Codex |
| Gate 1B: Financial Atomicity | **شريحة Dining-paid مكتملة ومُعتمَدة (2026-07-18)**؛ بقية call sites لاحقة | Claude | اجتازت failure/concurrency/full-suite gates؛ لا commit/push بعد |
| Gate 2: Super Admin safeguards | **مكتملة ومُعتمَدة (2A→2B3B)** | Claude/Codex | server-side policy/concurrency/session/audit tests |
| Gate 3: i18n/design/test foundation | **مكتملة ومُعتمَدة (2026-07-19)** | Claude/Codex | bilingual shell + reference screens + quality harness |
| Gate 4: Dining financial integrity | **منفَّذة بالكامل ومُتحقَّق منها ذاتيًا (2026-07-20) — Codex راجعت جولة أولى، كل الملاحظات + step-up المالي اتصلحوا، بانتظار مراجعة مستقلة تالية** | Claude | settlement/idempotency/shift-lock/one-active-order + 18/18 Postgres concurrency؛ لا commit/push بعد؛ مفيش بند مؤجَّل متبقٍّ |
| Gate 5: Staff UX batches | **Batch 6 (غرف+تدبير منزلي) منفَّذة ومُتحقَّق منها ذاتيًا (2026-07-20)** — الباقي (~35 شاشة) لسه لاحق | Claude | دفعات صغيرة ثنائية اللغة قابلة للاختبار |
| Gate 7: Public migration batches | مغلقة على Gates 2 و3 واعتماد Phase 0 | Claude | visual/API diff لكل batch بلا legacy backend |
| Gate 8: QR + Guest Service | مغلقة على Gates 1A و3 و4 و7 | Claude | scan-to-call-to-payment E2E evidence |
| Gate 9: production evidence | مغلقة حتى تحديد release scope | الفريق | CI/staging/security/restore/rollback evidence |

كل ناتج يمر على **Codex كمراجع مستقل** في نفس مساحة الـdiff، ثم يعيد Claude
فحص الملاحظات الصحيحة وإصلاحها، ثم يقرر Mohamed القبول والـcommit. الاستثناء
الوحيد للتوازي الآن هو Public Phase 0 لأنها توثيق وأدلة فقط، وعقدها التفصيلي:

`docs/agent-workflow/PUBLIC_PHASE_0_CLAUDE_HANDOFF.md`

قاعدة WIP: لا توجد مرحلتان تغيران كود المنتج في الوقت نفسه، ولا يبدأ رقم جديد
لمجرد أن السابق «قريب من الانتهاء»؛ يجب اجتياز بوابة الخروج بالأدلة أولًا.

## الفكرة

لن ننفذ قائمة طويلة بترتيب ثابت ثم نكتشف أن أساسها غير صحيح. اختيار المرحلة
التالية يتم وفق خمس أسئلة، من دون «درجة صحة» أو نسبة مئوية مضللة:

1. ما شدة الأثر لو ظل الخطر موجودًا؟
2. هل هو معرض الآن لمستخدم/شبكة/بيانات حقيقية؟
3. ما المراحل التي تعتمد عليه؟
4. هل الدليل مؤكد من الكود/اختبار أم مجرد فرضية تحتاج audit؟
5. هل الإصلاح قابل للرجوع، وهل يمكن تنفيذه في diff صغير واختباره؟

الحالات المستخدمة فقط: **مثبت**، **خطر مثبت**، **يحتاج تدقيقًا**،
**جاهز للتخطيط**، **مغلق باعتمادية**، و**ممنوع بلا قرار مالك المنتج**.

## بوابة الاستعداد لكل مهمة

قبل لمس الكود في أي مرحلة:

1. قراءة `AGENTS.md` و`CLAUDE.md` و`wagdy.md` والقرار المرتبط كاملًا.
2. `git status` وتسجيل branch/HEAD وحماية عمل المستخدم غير المسجل.
3. baseline موجّه للمسار ثم إعادة إنتاج المشكلة أو إثبات الفجوة.
4. Root Cause، حدود واضحة، ملفات متوقعة، migration impact، ومعايير قبول.
5. عرض الخطة على Mohamed والتوقف إذا كان نوع المهمة `plan`.
6. تنفيذ **مرحلة واحدة فقط**.
7. targeted tests ثم full relevant checks ثم `git diff --check`.
8. مراجعة مستقلة للـdiff: security، authorization، transactions، races،
   accounting، compatibility، UX/RTL/a11y.
9. إصلاح الملاحظات الصحيحة فقط، تحديث الأدلة و`wagdy.md`، ثم موافقة المالك.
10. لا commit أو push قبل المراجعة والموافقة الصريحة.

## ترتيب البوابات

### Gate 0 — خط الأساس ومركز القرار

**الحالة:** قيد الإكمال في مهمة Cockpit الحالية.  
**الناتج:** مراجعة 360°، معيار UI/UX، خارطة اعتماديات، وصانع تعليمات لا ينفذ
مباشرة.  
**الخروج:** type-check/build/browser review، وتطابق Cockpit مع `wagdy.md`.

### Gate 1 — احتواء الأخطار الحرجة

Gate 1 له مساران؛ endpoints عامة فعليًا على VPS حقيقي (`187.124.170.249`)
جعلت 1A الأول:

- **1A — Public/QR containment: ✅ مكتملة (2026-07-17).** إغلاق self-order
  وguest alerts افتراضيًا خلف بوابتين معًا (typed deployment switch +
  branch-scoped setting)، branch-scoped authorization حقيقي على beach
  check-in وGuest Alert REST/WebSocket، إغلاق تام لـ`GET
  /dining/public/orders/{id}` لحد Gate 8، تحقق outlet/table/item الكامل في
  `create_order`، تصحيح خريطة rate limiting، وrate-limit key مقاوم لتزوير
  `X-Forwarded-For`. راجعتها Codex على 5 جولات مستقلة (4 تصحيح + جولة أمان
  نهائية)، commit: `fix(security): contain unsafe public guest workflows`.
  Service Location الكاملة/QR token/guest session **لسه Gate 8**، مش جزء
  من الإغلاق ده.
- **1B — Financial atomicity contract: أول شريحة مكتملة ومُعتمَدة.** تم
  تصنيف call sites واختيار تحويل طلب Dining إلى `paid` كأعلى مسار محدود؛
  أصبح commit واحدًا fail-closed مع أقفال طلب/فوليو/مخزون واختبارات فشل
  وتزامن حقيقية. التفاصيل والأدلة في
  `docs/audits/gate-1b-financial-atomicity-plan.md`. بقية call sites المالية
  ما زالت backlog صريحًا، لا تُعتبر مغلقة ضمن هذا الاعتماد.

**اعتماديات الخروج:** الشريحة المطلوبة لفتح Gate 2 اجتازت المراجعة؛ يلزم
checkpoint/commit مستقل ونظيف قبل أي تعديل Gate 2. لا مرحلة مالية أو QR أو
Public migration تعتبر بقية Gate 1B مكتملة، وكل rollback يظل واضحًا ولا
migration مدمرة.

### Gate 2 — أمان مركز التحكم

**النطاق:** Super Admin backend safeguards.  
**الحالة:** مكتملة ومُعتمَدة عبر Gate 2A و2B1 و2B2 و2B3A و2B3B.
**يعتمد على:** Gate 1A مكتملة ✅ وشريحة Gate 1B المطلوبة اتعمدت ✅.
**الناتج:** حماية آخر super_admin نشط، self-demotion/deactivation، explicit
deny policy، منع privilege escalation، invalidation للجلسات، TOTP login-time،
step-up للأفعال الحساسة، وتدقيق.  
**الخروج:** اختبارات server-side وتزامن، ولا تعتمد الحماية على الواجهة.

### Gate 3 — الأساسات المشتركة للواجهة

**3A — i18n runtime:** preferred language موحد وآمن، catalog policy، `dir`
على root، Intl للوقت/الرقم، واستقلال اللغة عن العملة.  
**3B — Design-system adoption baseline:** tokens ومكونات وأنماط تشغيلية،
keyboard/focus/error/loading/empty/offline contracts، ومنع نسخ Button/Table/
Modal جديدة.  
**3C — Frontend quality harness:** minimal lint/component/a11y/smoke checks
بعد تبرير الأدوات، لا stack متداخل.

**يعتمد على:** Gate 2 قبل واجهات التحكم الحساسة.  
**الحالة:** مكتملة ومُعتمَدة بعد مراجعة مستقلة؛ backend **1992 passed + 20
skipped**، frontend **60/60**، وبناء Staff/Public وفصل حزمتي locale ناجح.
**الخروج:** shell واحد صحيح عربي RTL وإنجليزي LTR، وشاشة مرجعية لكل POS،
KDS، Admin، Public قبل الهجرة على دفعات. الترجمة الكاملة لبقية الشاشات تظل
Gate 5 ولا تدخل ضمن ادعاء الاعتماد هنا.

### Gate 4 — سلامة Dining المالية والتشغيلية

**النطاق:** Payment، cashier shift، method، idempotency، reconciliation،
void/refund/discount approvals، order ownership، one-active-order invariant.  
**يعتمد على:** Gate 1B، وسياسات Gate 2 للأفعال الحساسة.  
**الحالة:** **منفَّذة بالكامل ومُتحقَّق منها ذاتيًا (2026-07-20)، بلا
commit/push.** الثلاث شرائح اتنفّذت: 4A settlement/idempotency/Payment
attribution/typed-method-fail-closed، 4B open-shift invariant + close lock +
expected-cash formula + branch isolation، 4C state machine + one-active-order
+ actor attribution + refund lock/reversal. جولة مراجعة Codex مستقلة أولى
(2026-07-20) لقت 5 High + 5 Medium (منها فساد بيانات حقيقي مثبَت على
PostgreSQL معزولة) — كلهم اتصلحوا بإثبات حقيقي، بما فيهم step-up المالي
لـ payment_void/dining_refund (كان الوحيد المؤجَّل، نُفِّذ لاحقًا مباشرة من
غير وكيل لما Codex بقى غير متاح). **مفيش بند مؤجَّل متبقٍّ.**
**عقد التنفيذ:** `docs/audits/gate-4-execution-brief.md` — ثلاث شرائح مترابطة:
settlement/payment، shift/reconciliation، ثم state/ownership/reversals. تقرير
التنفيذ: `docs/audits/gate-4-dining-payment-shift-order-integrity.md`.
**الخروج:** كل بيع يظهر مرة واحدة فقط في Payment والوردية والفوليو والدفتر،
وتنجح concurrency/failure tests على PostgreSQL.

### Gate 5 — اكتمال إدارة الموظفين بلغتين

**النطاق:** Shell ثم POS/KDS ثم إدارة/Super Admin ثم بقية الشاشات على batches
صغيرة.  
**يعتمد على:** Gate 3، وGate 4 للشاشات المالية.  
**الخروج:** keyboard + responsive + Arabic RTL + English LTR + print، ولا
missing keys أو strings حرجة hard-coded.

**Batch 1 — POS + KDS (2026-07-20)، منفَّذة ومُتحقَّق منها ذاتيًا، فرع
`gate-5-staff-ux-batch-1-pos-kds-i18n`:** الشاشتين المرجعيتين اللي كانتا
"direction-normalized بس" من Gate 3 (`UnifiedPOSView.vue`، `DiningKDSView.vue`)
اتترجموا بالكامل — كل نص hard-coded (83 مفتاح POS + 25 مفتاح KDS) بقى عبر
`t()` تحت `backoffice.pos.*`/`backoffice.kds.*`، والاتنين اتترقّوا من
`DIRECTION_CLEAN_FILES` لـ`STRICT_FILES` في `validate-i18n.mjs`. KDS بيعيد
استخدام `backoffice.pos.orderTypes`/`tableLabel`/`elapsedUnits` بدل تكرار
نفس التصنيف تحت namespace تاني.

**Batch 2 — لوحات الإدارة الرئيسية (2026-07-20)، منفَّذة ومُتحقَّق منها ذاتيًا،
فرع `gate-5-staff-ux-batch-2-admin-i18n`:** `PermissionsView.vue` (ترقية بلا
تعديل كود — كانت مترجمة بالفعل)، `DashboardView.vue`، `SalesDashboardView.vue`،
`BeachLiveDashboardView.vue`. الثلاثة الأخيرة كان فيها `dir="rtl"` ثابت و
`ar-EG` locale calls (مخالفات Gate 3 ما كانتش اتكشفت) — اتصلحت مع الترجمة.

**Batch 3 — CRM (2026-07-20)، منفَّذة ومُتحقَّق منها ذاتيًا، فرع
`gate-5-staff-ux-batch-3-crm-i18n`:** `CRMView.vue` (7 تابات + مودالين)، أكبر
شاشة اتترجمت لحد دلوقتي. نفس فئة مخالفات Gate 3 (`dir="rtl"` ثابت، `ar-EG`
locale calls، physical CSS `text-right`/`mr-2`) اتكشفت واتصلحت، زائد تعارض
اسم `t` مع دالة الترجمة في مكانين (function parameter + loop variable).

**Batch 4 — HR (2026-07-20)، منفَّذة ومُتحقَّق منها ذاتيًا، فرع
`gate-5-staff-ux-batch-4-hr-i18n`:** `HRView.vue` (5 تابات + 6 مودالات).
نفس فئة مخالفات Gate 3 (`dir="rtl"` ثابت، `ar-EG` locale calls، physical
CSS `text-right`/`mr-2`/`text-left`/`file:ml-3`) اتكشفت واتصلحت، زائد تعارض
اسم `t` مع دالة الترجمة في 3 مواضع مختلفة.

**Batch 5 — استقبال + حجوزات (2026-07-20)، منفَّذة ومُتحقَّق منها ذاتيًا،
فرع `gate-5-staff-ux-batch-5-reception-bookings-i18n`:** `ReceptionView.vue`
و`BookingsView.vue`. نفس فئة مخالفات Gate 3 (`dir="rtl"` ثابت، `ar-EG`
locale calls، physical CSS `text-right`/`mr-1`) اتكشفت واتصلحت.

**Batch 6 — غرف + تدبير منزلي (2026-07-20)، منفَّذة ومُتحقَّق منها ذاتيًا،
فرع `gate-5-staff-ux-batch-6-rooms-housekeeping-i18n`:** `RoomsView.vue`
و`HousekeepingView.vue`. نفس فئة مخالفات Gate 3 (`dir="rtl"` ثابت، `ar-EG`)
زائد مخالفة اتجاه فيزيائي بره نطاق فاحص `validate:i18n` الحالي (`ml-4`/
`border-r-4`) اتكشفت واتصلحت يدويًا.

### Gate 6 — Public Phase 0 فقط — مسموح أن يبدأ الآن

**النطاق:** لا نقل كود بعد. نجمد مرجع المشروع القديم والحالي: routes، Desktop
وMobile screenshots، assets/fonts، content، API calls، حالات loading/error/
empty، ثم Keep/Adapt/Remove.  
**يعتمد على:** Gate 0، قرار brand `El Kheima`، وموافقة Mohamed الحالية. يمكن
تشغيله بالتوازي لأنه قراءة وتوثيق ولا يغير المنتج.  
**الخروج:** migration map ومصفوفة API compatibility يوافق عليهما Mohamed.

### Gate 7 — نقل الموقع العام تدريجيًا

**النطاق:** Shell/theme أولًا، ثم صفحات قليلة متجانسة في كل batch، مع إبقاء
Backend الحالي المصدر الوحيد للحقيقة.  
**يعتمد على:** Gate 6 **وكذلك Gates 2 و3**؛ السماح بجمع مرجع Phase 0 لا يفتح
باب نقل الكود قبل أمان الإدارة وأساس اللغة والتصميم.  
**الخروج لكل batch:** visual comparison، responsive/a11y، budget للأصول،
type-check/build/smoke، ولا نسخ backend أو بيانات legacy.

### Gate 8 — QR Menu وGuest Service

**النطاق:** Service Location عام، QR token آمن وقابل للدوران، guest session،
view_and_call، dedupe/cooldown، state machine، assignment، realtime مع polling
fallback، cashier monitoring، وaudit. self-order يظل مغلقًا افتراضيًا.  
**يعتمد على:** Gates 1A و3 و4 وواجهة Public المناسبة من Gate 7.  
**الخروج:** اختبار من scan إلى call/acknowledge/order/payment/close، مع
Arabic/English، mobile، slow/offline recovery، وعدم وجود أثر مطبخي أو مالي من
النداء وحده.

### Gate 9 — Production evidence

**النطاق:** CI، dependency/security audit، query/performance budgets، logs and
alerts، migration rehearsal، staging/VPS، TLS، health/readiness، backup/offsite
restore، rollback، smoke runbooks.  
**يعتمد على:** اكتمال الرحلات المطلوب إصدارها، لا اكتمال كل أفكار المنتج.  
**الخروج:** تقرير إصدار بأدلة فعلية؛ وحده يسمح بعبارة production-ready للنطاق
الذي تم اختباره.

## مسارات الاعتماد المختصرة

```text
Gate 0 baseline ───────────────────────────────> Gate 6 Public reference (read-only)
  ├─> Gate 1A public containment ───────────────────────┐
  └─> Gate 1B financial atomicity ─> Gate 4 Dining ────┤
                              Gate 2 Super Admin        │
                                   └─> Gate 3 UI/i18n ─┼─> Gate 5 staff UI
Gate 2 + Gate 3 + approved Gate 6 reference ────────────────> Gate 7 migration
Gate 1A + Gate 3 + Gate 4 + Gate 7 ─────────────────────────> Gate 8 QR
validated release scope ────────────────────────────────────> Gate 9 production evidence
```

## عقد جودة UI/UX داخل كل مرحلة

أي شاشة تتغير يجب أن تثبت، بحسب سياقها:

- المهمة الأساسية واضحة وأسرع إجراء متكرر لا يختبئ؛
- الصلاحية الحقيقية من السيرفر مع Access Denied مفهوم؛
- loading/empty/error/offline/success states؛
- منع duplicate submit واستعادة آمنة بعد الخطأ؛
- keyboard، focus، labels، status announcements، contrast، reduced motion؛
- عربي RTL وإنجليزي LTR مع logical CSS، ومال/تواريخ بصيغة صحيحة؛
- Desktop/Touch/Tablet/Mobile حسب المستخدم الفعلي؛
- أداء مقاس لا حدسي، خصوصًا POS وQR؛
- audit/reason/approval للأفعال الحساسة؛
- screenshot أو test أو command يثبت النتيجة، لا علامة checklist فقط.

## شروط التوقف الإجباري

نتوقف ونطلب قرارًا إذا كان التنفيذ يحتاج: حذف بيانات غير قابل للرجوع، تغيير
قاعدة عمل مالية لا يمكن استنتاجها، production secret، كسر QR مطبوع، إعادة
تفسير أثر محاسبي، أو تعديل migration مطبقة. الغموض العادي يُحل بأكثر افتراض
آمن وقابل للرجوع مع توثيقه.
