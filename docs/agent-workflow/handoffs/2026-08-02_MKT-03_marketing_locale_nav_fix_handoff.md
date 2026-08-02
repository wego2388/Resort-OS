# MKT-03 — Locale-aware navigation links + View Transitions race fix

**التاريخ:** 2026-08-02
**المالك:** Mohamed
**المنفذ والمراجع النهائي:** Codex
**الحالة:** COMPLETE

## 1. النتيجة

نُشر Marketing release `8dc95d8` على `elkheima.com` من المستودع المستقل
(`elkheima-marketing-website`).

- كل الروابط الداخلية (nav، footer، chatbot، consent، products، اللوجو،
  زر الحجز) بقت تعدّي عبر `useLocalePath()` بدل مسارات خام — التنقل
  بيحافظ على بادئة اللغة الحالية (`/ar`, `/en`, `/ru`, `/it`) بدل ما
  يفقدها. `isActivePath()` بيجرّد بادئة الـlocale قبل المقارنة، فالـ
  active state في الـnav بيشتغل صح على `/ar/rooms` مش بس `/rooms`.
  الـMore dropdown بقى مايكررش الـlinks اللي ظاهرة أصلاً في الـdesktop
  nav (lg+).
- **باج حقيقي اتصلح**: Mohamed بلّغ إن `/ar/contact` (وأي صفحة تانية
  أحيانًا) كانت محتاجة ريفريش يدوي عشان محتواها يظهر بعد تنقل داخل
  الموقع (client-side navigation). السبب الجذري: hook الـView
  Transitions API في `router/index.ts` كان بينادي `next()` (تحديث الصفحة
  في Vue) *قبل* `document.startViewTransition()`، يعني رسم الـDOM
  الحقيقي كان بيحصل برّه الـcallback اللي المفروض يحيط بيه، فبتصادم مع
  لقطة "قبل/بعد" اللي المتصفح بياخدها. اتأكد الباج حيًا (مش تخمين) —
  التنقل عبر قائمة الموبايل على production نفسه طلّع فعليًا
  `InvalidStateError: Transition was aborted because of invalid state`
  في الـconsole.

الملفات المتغيرة: `router/index.ts` (الإصلاح الجذري)،
`composables/useLocalePath.ts` (جديد)، `TheNavbar.vue`, `TheFooter.vue`,
`ChatbotButton.vue`, `ChatbotWindow.vue`, `PublicContactConsent.vue`,
`Products.vue`. لا تغيير Backend أو API أو schema أو بيانات.

## 2. المصدر

- repo: `elkheima-marketing-website`
- branch: `main`
- commit: `8dc95d8` — "fix(i18n): locale-aware nav links + view-transition
  race breaking client-side navigation"
- `origin/main` (GitHub) يطابق الالتزام — تم push مباشرة.
- release: `/opt/elkheima-marketing-releases/8dc95d8`
- current: `/opt/elkheima-marketing-current -> .../8dc95d8`
- archive: `/var/backups/resort-os/marketing-source-releases/8dc95d8.tar.gz`
- archive SHA-256:
  `d390a2aa0a6fc025d323a6e9442330d28092d90ef1d260fb1920410f4a85b40d`

## 3. بوابة الجودة

- `npm run type-check`: passed.
- `npm run build`: passed (نفس تحذير الأداء الموجود من قبل — chunk
  `public-pages` أكبر من 500KB، تحذير غير حاجز).
- تحقّق حي (Playwright، ليس افتراضًا): إعادة إنتاج فعلية للباج قبل
  الإصلاح (خطأ `InvalidStateError` على production عبر التنقل من قائمة
  الموبايل)، ثم تأكيد الإصلاح بعده — 5 محاولات متتالية + تنقل سريع
  متتابع بين 5 صفحات، صفر أخطاء في كل الحالات، والمحتوى (`opacity:1`,
  `.animate-in`) بيظهر فورًا بدون أي تأخير أو ريفريش.
- بعد النشر: نفس اختبار قائمة الموبايل على `elkheima.com` الحقيقي —
  صفر `pageerror`، محتوى ظاهر فورًا.

## 4. نقطة التراجع

- rollback tag: `resort-os-rollback/marketing-site:pre-8dc95d8`
- rollback manifest:
  `/var/backups/resort-os/marketing-source-releases/8dc95d8-rollback-image.txt`
- release السابق `/opt/elkheima-marketing-releases/16f8f2c` لسه محفوظ
  كامل على القرص، غير متحذوف.
- لا migration ولا تغيير DB في هذه الحزمة (frontend فقط) — مفيش نسخة DB
  مخصوصة مطلوبة أو مأخوذة لهذه الحزمة تحديدًا.

## 5. قبول الإنتاج

- `https://elkheima.com`، `https://www.elkheima.com`، `https://elkheima.com/ar/contact`
  المباشر: HTTP 200.
- 8 حاويات Running، `RestartCount=0` لخدمة `marketing_site`.
- severe logs: صفر.

## ملاحظة صغيرة

أثناء التنظيف بعد النشر، حاولت أمسح مجلد release القديم غير المستخدم
`/opt/elkheima-marketing-releases/e5e122a` — اترفضت الأوامر بصلاحيات
الملف (`Permission denied` على كل ملف)، فمفيش أي شيء اتحذف فعليًا. رجعت
عن المحاولة فورًا بدل ما أعيدها بصلاحيات أعلى — الحذف ده مكانش جزء من
المطلوب أصلًا.
