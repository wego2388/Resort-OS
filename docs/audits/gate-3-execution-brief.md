# Gate 3 — Staff UI, i18n, Design-System & Quality Foundation

**الحالة:** جاهزة للتنفيذ على الفرع
`gate-3-ui-i18n-quality-foundation` فوق checkpoint Gate 2B3B المُعتمَد.

**طريقة العمل:** Claude ينفّذ الحزمة كاملة بثلاث شرائح داخلية مترابطة،
ويتحقق بعد كل شريحة، ثم يشغّل البوابة الكاملة ويتوقف بلا commit أو push حتى
يراجع Codex الناتج مرة واحدة في النهاية. لا يتوقف بعد baseline أو الخطة إلا
لو ظهر blocker حقيقي من قواعد المشروع.

## لماذا Gate 3 الآن؟

Gate 2 أغلقت أساس الهوية والسوبر أدمن والجلسات. نقل الموقع العام، توحيد
شاشات الموظفين، وتجربة QR لاحقًا كلها تعتمد على runtime لغة واتجاه موثوق،
Design System قابل للتبنّي، واختبارات frontend تكشف كسر RTL/keyboard/catalog
قبل الانتشار على عشرات الشاشات.

الوضع الحالي مفيد لكنه متعارض:

- `User.preferred_language` موجود، لكنه غير ظاهر أو قابل للتحديث عبر عقد
  `/auth/me` كامل وآمن.
- singleton الـi18n المشترك يعرض `ar/en/ru/it` لكل التطبيقات ويكتب ثلاث
  مفاتيح localStorage قديمة؛ قرار الموظفين يسمح `ar/en` فقط، بينما Public
  يجب أن يحتفظ بلغاته الأربع.
- `main.css` يفرض `direction: rtl` على `body` رغم أن runtime يغيّر root dir.
- `LanguageSwitcher` يعرض أربع لغات ولا يحفظ تفضيل الموظف في السيرفر.
- عشرات الصفحات فيها نص عربي، `dir="rtl"` و`ar-EG` hard-coded؛ لا نصلحها
  كلها في mass rewrite داخل هذه البوابة.
- Design System غني نسبيًا (`@resort-os/ui` + tokens/components) لكنه غير
  متبنّى باتساق، ولا توجد وثيقة استخدام أو catalog داخلي قابل للصيانة.
- frontend لديه type-check/build فقط؛ لا catalog validation أو component/
  accessibility/smoke harness.

## قبل التعديل

اقرأ بالكامل:

- `CLAUDE.md`, `AGENTS.md`, `wagdy.md`, `PROJECT_STATUS.md`.
- `docs/decisions/0002-staff-app-bilingual-mode.md`.
- `docs/audits/SMART_EXECUTION_ROADMAP.md`، قسم Gate 3.
- تقارير Gate 2B3A و2B3B حتى لا تُكسر شاشات step-up/session الجديدة.
- `frontend/packages/core/src/i18n/` واستخدامه في Staff وPublic.
- `frontend/apps/el-kheima/src/{main.ts,App.vue,assets/main.css}` وكل layouts.
- `LanguageSwitcher`, auth store/types/API، `/auth/me` backend contract.
- `frontend/packages/ui` كاملًا: tokens، preset، exports، components، focus.
- package scripts/lockfile وأي testing/lint tooling موجود فعلًا.

شغّل baseline قابل للتكرار واحفظه في التقرير:

- عدد ملفات Staff Vue/TS القابلة للوصول.
- hard-coded user copy، `dir=`, `ar-EG/en-US`, physical left/right classes
  في shell والشاشات المرجعية.
- catalog key parity، القيم الفارغة/placeholder-like، missing runtime keys.
- المكونات المكررة مقابل `@resort-os/ui`.
- type-check/build الحاليان لكل من `el-kheima` و`public`.

اكتب baseline/tool output في ملف أو script، لا أرقامًا يدوية يصعب تحديثها.

## الشريحة 3A — Staff-only bilingual runtime & saved preference

### Backend contract

استخدم عمود `User.preferred_language` الموجود؛ لا تنشئ جدول تفضيلات موازٍ.

المطلوب:

- أضف `preferred_language` إلى current-user DTO/types الفعلية.
- endpoint self-service واضح مثل `PATCH /auth/me/preferences` أو ما يلائم
  routing الحالي؛ لا يقبل target user id أصلًا.
- allow-list سيرفرية **`ar|en` فقط** لتطبيق الموظفين.
- المستخدم العادي يحدّث تفضيله هو فقط؛ لا permission إدارية مطلوبة.
- normalize للقيم القديمة/null بأكثر افتراض آمن وقابل للرجوع، مع اختبار.
- audit مختصر عند التغيير الفعلي، بدون ضوضاء عند no-op.
- unsupported values، mass assignment وحقول إضافية تُرفض باختبارات HTTP.
- لا migration إلا إذا أثبت فحص البيانات/القيود أنها لازمة وآمنة؛ لا تعدّل
  migration قديمة.

### Separate app locale policies

افصل **سياسة اللغة** لكل تطبيق مع إعادة استخدام الرسائل المشتركة:

- Staff `el-kheima`: `ar`, `en` فقط.
- Public: يحتفظ بـ`ar`, `en`, `ru`, `it` وسياسته المستقلة.
- لا singleton API واحد يفرض نفس allow-list أو storage key على التطبيقين.
- فضّل factory/controller صغيرًا واضحًا داخل core، أو app-scoped instances،
  بدل نسخ نظام i18n كامل في كل app.

### One source of truth and storage migration

- pre-login Staff preference له مفتاح واحد namespaced، مثل
  `resort-os:staff:locale`.
- نفّذ one-time migration موثقة من المفاتيح القديمة
  (`locale`, `kheima_lang`, `app_language`) ثم توقف عن كتابتها/قراءتها إلى
  الأبد في Staff.
- Public يستخدم مفتاحًا namespaced مستقلًا ولا يتأثر بتسجيل موظف.
- بعد login/refresh/PIN switch، backend `preferred_language` هو source of
  truth ويُطبَّق فورًا؛ لا يرث الموظف لغة حساب الموظف السابق على terminal.
- تغيير الموظف للغة: احفظ السيرفر أولًا أو تعامل مع failure بوضوح؛ لا تظهر
  نجاحًا دائمًا بينما backend رفض.
- logout يعيد التطبيق إلى pre-login policy بصورة حتمية ومختبرة.

### Root direction and formatting

- مصدر واحد يضبط `<html lang>` و`<html dir>`؛ لا تفرض `body.dir` في أكثر من
  مكان ولا CSS global `direction: rtl`.
- Arabic = RTL، English = LTR، بدون reload.
- typography مناسبة للغتين: Arabic rendering مريح، وEnglish لا يُجبر بلا
  داعٍ على خط عربي؛ استخدم fonts الموجودة/system fallbacks فقط.
- utilities مركزية لـdate/time/number/money تستخدم locale الحالي وtimezone
  الموثوق. `formatMoney(value, currency)` يأخذ العملة من trusted config/
  caller صراحة؛ **ممنوع اشتقاق العملة من اللغة**.
- لا تترجم business data أو أسماء المنتجات/الأشخاص كأنها catalog keys.
- backend error codes تُحوّل لرسائل catalog مع fallback آمن؛ لا تعرض stack/
  path/raw internal detail.

### 3A tests

- backend ownership/allow-list/no-op/audit/mass-assignment tests.
- pre-login migration، login reconciliation، refresh، logout، PIN switch،
  second-user-on-shared-terminal tests.
- root `lang/dir` يتغير reactive بلا reload.
- currency/value لا يتغيران عند تبديل `ar↔en`؛ التنسيق فقط يتغير.
- Public ما زال يعرض اللغات الأربع ويبني بنجاح.

## الشريحة 3B — Design-system adoption baseline

هذه ليست إعادة تصميم كل المشروع وليست صفحة showcase تجميلية فقط. استخدم
الموجود أولًا، وسد فجواته، ثم أثبت التبنّي في شاشات تشغيل حقيقية محدودة.

### Tokens and primitives

راجع ووسّع فقط عند الحاجة:

- semantic colors: background/surface/text/border/primary/success/warning/
  danger/info/focus.
- typography Arabic/English، numeric/tabular styles.
- spacing، radii، shadows، z-index، motion، input heights، table density،
  icon sizes، touch targets (44px minimum where applicable).
- logical direction utilities/patterns (`inline-start/end`) بدل physical
  left/right عندما يكون الاتجاه مهمًا.
- print variables/patterns للفاتورة والتقارير عند الحاجة المرجعية.

لا تضف dark-mode scope جديدًا. حافظ على الموجود إن كان يعمل، لكن light mode
والوضوح التشغيلي هما الأولوية.

### Component contracts

استخدم/صحح `@resort-os/ui` بدل إنشاء نسخ جديدة من Button/Input/Modal/Table/
Toast/Loading/Empty/Error. لكل primitive يتغير:

- focus/keyboard/disabled/loading/error states.
- ARIA/label association وfocus return/trap للمودال.
- RTL/LTR وresponsive behavior.
- reduced motion.
- API صغير typed ومتوافق قدر الإمكان.

### Real reference adoption

نفّذ baseline في نطاق واقعي، لا كل الشاشات:

1. **Shell/Auth/Account:** Login + BackOffice/Field/Kiosk shell + Profile/
   Sessions/Language control.
2. **Admin reference:** Sessions أو Settings/Permissions بحسب الأقل مخاطرة؛
   يجب أن يثبت forms/tables/loading/error/step-up في الاتجاهين.
3. **KDS reference:** `DiningKDSView` بالكامل أو رحلة bounded مكتملة منه،
   مع status/age/empty/offline ووضوح شاشة المطبخ.
4. **POS reference:** shell والـcritical order summary/actions في
   `UnifiedPOSView` فقط، دون تغيير منطق المال أو الطلب؛ touch/keyboard/totals
   تظل واضحة في RTL/LTR.

لا تترجم بقية 50+ شاشة في هذه الدفعة. أنشئ inventory/ratchet واضحًا للدفعات
التالية، ولا تقل "التطبيق كامل ثنائي اللغة" بسبب الشاشات المرجعية.

### Internal catalog

أضف dev-only UI catalog صغيرًا داخل التطبيق إذا كان صيانته معقولة، يستخدم
المكونات الحقيقية ويعرض:

- tokens والtypography والحالات الأساسية.
- AR/EN وRTL/LTR toggle محلي للمعاينة لا يغير business preference.
- form/table/modal/loading/empty/error/status/touch examples.

لا تضف Storybook في هذه المرحلة؛ البنية الحالية لا تبرر stack مستقلًا.
الcatalog لا يُعد بديلًا من تبنّي المكونات في الشاشات المرجعية.

وثّق النظام في `docs/DESIGN_SYSTEM.md`: brand principles، tokens، typography،
layout، components، forms، tables، statuses، feedback، confirmation، loading/
empty/error، RTL، accessibility، POS/KDS patterns، do/don't.

## الشريحة 3C — Minimal frontend quality harness

ابدأ بأقل أدوات تحقق تخدم المخاطر الفعلية. لا تدخل stackين للغرض نفسه.

### Dependency-free gates first

أنشئ scripts قابلة للتشغيل في CI/local لفحص:

- Staff `ar/en` key parity.
- Public locale policy لم تتراجع.
- empty/TODO/TBD/raw-key/placeholder-like values؛ إذا كان الدين القديم كبيرًا
  استخدم baseline allow-list مفسرة + ratchet يمنع الزيادة، لا تجاهلًا عامًا.
- missing runtime keys في الشاشات المرجعية.
- منع `dir="rtl"`, hard-coded locale وphysical-direction regressions داخل
  **النطاق المهاجر**، مع inventory منفصل للدين غير المهاجر.
- عدم عودة مفاتيح localStorage القديمة في Staff.

### Component/accessibility/smoke tests

لا توجد حاليًا test stack للفرونت. الخيار الافتراضي الموصى به إن أثبت الفحص
عدم وجود بديل قائم:

- Vitest + Vue Test Utils + jsdom للمكونات.
- axe-core مباشرة لاختبارات a11y المركزة، بدون wrapper stack زائد.

برّر كل dependency في التقرير وثبّت نسخًا متوافقة مع Vue/Vite الحاليين.
لا تضف Playwright أو Storybook أو Jest في نفس الدفعة.

الحد الأدنى للاختبارات:

- locale controller/storage migration/server reconciliation.
- LanguageSwitcher keyboard/failure/loading behavior.
- root lang/dir and formatting utilities.
- shared modal/input/button/table focus and accessible-name basics.
- reference Shell/Admin/KDS/POS components render in `ar/rtl` and `en/ltr`
  without missing keys or axe critical violations.
- smoke route/navigation/auth guards للroutes المرجعية.

أضف scripts واضحة مثل `validate:i18n`, `test:unit`, `test:a11y`,
`test:frontend` أو أسماء متسقة مع repo. لا تقل إن browser E2E كامل موجود إن
كان الاختبار jsdom/component فقط.

## UI/UX acceptance contract

في كل شاشة مرجعية:

- المهمة الأساسية واضحة، primary action واحد، destructive منفصل.
- loading/empty/error/offline/success حقيقية.
- منع duplicate submit واسترجاع آمن بعد الخطأ.
- keyboard logical order، focus visible/return، labels/status announcements.
- desktop admin + POS desktop/touch + tablet widths المقصودة.
- لا color-only statuses، ولا نص صغير/contrast ضعيف.
- Arabic outdoor/operational readability وEnglish LTR بلا انعكاس خاطئ.
- totals لا تختفي تحت fold في POS reference.
- لا تغيير business logic أو صلاحيات backend بسبب refactor العرض.

## ما هو خارج النطاق

- ترجمة كل Staff routes دفعة واحدة.
- نقل أو إعادة تصميم صفحات Public القديمة.
- تغيير public locale list أو محتواه؛ فقط منع regression وبناءه.
- Dining payment/shift/accounting business rules (Gate 4).
- typed settings control center الكامل.
- QR/Guest Service/Service Location.
- Dark-mode redesign.
- Storybook/Playwright/full visual-regression system.
- تعديل generated files يدويًا أو إضافة dependencies بلا تبرير.

## Required validation

اكتشف الأوامر الفعلية وأضف scripts الجديدة إلى بوابة واضحة. الحد الأدنى:

```bash
bash scripts/agent-check.sh
cd backend
.venv/bin/pytest <preferred-language/current-user targeted tests> -v
.venv/bin/pytest tests/ -v
.venv/bin/alembic heads
cd ../frontend
pnpm --filter el-kheima validate:i18n
pnpm --filter el-kheima type-check
pnpm --filter el-kheima test:frontend
pnpm --filter el-kheima build
pnpm --filter public type-check
pnpm --filter public build
cd ..
git diff --check
git status --short --branch
```

إن كانت أسماء scripts النهائية مختلفة، اذكرها بوضوح وشغّل المقابل الفعلي.

اعمل browser walkthrough أو screenshots لـAR/RTL وEN/LTR على الشاشات
المرجعية إن كانت بيئة التنفيذ تدعمه؛ إن لم تدعمه، اكتب "not run" وسببًا
صريحًا بدل ادعاء visual verification.

## Deliverables

حدّث بعد نجاح التحقق فقط:

- `docs/audits/gate-3-ui-i18n-quality-foundation.md` كتقرير تنفيذي.
- `docs/DESIGN_SYSTEM.md`.
- `docs/FRONTEND_TESTING.md` أو دمج واضح في وثيقة اختبار موجودة إن وُجدت.
- baseline/ratchet artifact قابل للتحديث، لا أرقام في prose فقط.
- `PROJECT_STATUS.md`, `wagdy.md`, SMART roadmap وProject Cockpit.
- Decision 0002 بالحالة المنفذة بدقة، دون ادعاء ترجمة التطبيق كله.

تقرير Claude النهائي يفصل: baseline، architecture، backend contract، storage
migration، locale/public separation، reference screens، design tokens/
components، dependencies المضافة ولماذا، test matrix، كل command/result،
الدين المتبقي والملفات المتغيرة.

**توقف بعدها بلا commit وبلا push وبلا بدء Gate 4 أو Public migration.**
