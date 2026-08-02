# MKT-03 — Locale-aware navigation links + View Transitions race fix

**التاريخ:** 2026-08-02
**المالك:** Mohamed
**المنفذ والمراجع النهائي:** Codex
**الحالة:** COMPLETE (جولتان — الجولة الأولى كانت غير كاملة، Mohamed لقط
الفجوة حيًا وأثبتها بالدليل)

## 1. النتيجة النهائية

Marketing release `0b0321f` منشور على `elkheima.com` — النسخة الكاملة بعد
جولتين:

**الجولة 1 (`8dc95d8`)**: كل روابط الـchrome المشتركة (nav، footer،
chatbot widget، consent، products index، اللوجو، زر الحجز) بقت تعدّي عبر
`useLocalePath()` بدل مسارات خام. `isActivePath()` بيجرّد بادئة الـlocale
قبل المقارنة. الـMore dropdown بقى مايكررش الـlinks الظاهرة في الـdesktop
nav. كمان اتصلح باج حقيقي في `router/index.ts`: hook الـView Transitions
API كان بينادي `next()` *قبل* `document.startViewTransition()` بدل جواه —
رسم الـDOM الحقيقي كان بيحصل برّه الـcallback اللي المفروض يحيط بيه،
فبيتصادم مع لقطة "قبل/بعد" اللي المتصفح بياخدها. اتأكد حيًا (`InvalidStateError:
Transition was aborted because of invalid state` عبر قائمة الموبايل على
production نفسه) قبل الإصلاح، وصفر أخطاء بعده.

**الجولة 2 (`0b0321f`) — الأهم**: بعد نشر الجولة 1، Mohamed اختبر بنفسه
مباشرة على `elkheima.com` ولقط باج حقيقي تاني لسه موجود: من `/ar/rooms`،
الضغط على زر "تواصل مع الفريق" كان بيودّي لـ`/contact` (من غير بادئة
`/ar`) بدل `/ar/contact`. السبب: `PublicAvailabilityNotice.vue` (component
مشترك يظهر في 9 صفحات — Rooms, Beach, Restaurant, Activities, Events,
Packages, About وغيرها) كان لسه فيه `to="/contact"` خام، فات على الجولة 1
لأنها غطّت الـchrome المشترك بس مش كل الروابط الداخلية في محتوى الصفحات.

**تحقيق منهجي بعد الاكتشاف** (`grep` شامل على كل `to="/...`،
`router.push`, `router.replace`, `$router.push` في المشروع كله) كشف إن
الفجوة كانت أوسع بكتير — عشرات الروابط الخام في كل صفحات `apps/public/*`
تقريبًا (Home.vue لوحدها فيها 9). كل واحدة منها اتصلحت — التفاصيل الكاملة
تحت §2.

**تشخيص خاطئ اتصحّح أثناء الطريق، يستاهل التسجيل**: قبل ما نلاقي السبب
الحقيقي، جربنا نفسر الأعراض (صفحة فاضية) كـ browser extensions (Privacy
Badger, Web Developer, إلخ) ظاهرة في DevTools بتاع Mohamed — ده كان
ملاحظة حقيقية (الإضافات دي فعلاً كانت شغالة) بس مش السبب الجذري. Mohamed
كرر التجربة بخطوات دقيقة (من صفحة معينة، بضغطة معينة، مع تأكيد إن back
ثم forward بيصلح الحالة) وده اللي كشف الـcomponent المشترك الناقص.

## 2. المصدر

- repo: `elkheima-marketing-website`
- branch: `main`
- الجولة 1: commit `8dc95d8` — "fix(i18n): locale-aware nav links +
  view-transition race breaking client-side navigation"
- الجولة 2: commit `0b0321f` — "fix(i18n): complete locale-aware routing
  on remaining in-page links" — 17 ملف: `PublicAvailabilityNotice.vue`
  (الأصل المُبلَّغ)، `Home.vue` (9 روابط + `goToBooking()`)، `Rooms.vue`,
  `Beach.vue`, `Restaurant.vue`, `Activities.vue`, `Events.vue`,
  `Packages.vue`, `Privacy.vue`, `Terms.vue`, `Blog.vue`, `BlogPost.vue`
  (بما فيها `router.replace`)، `NotFound.vue`, `HomeGallerySlider.vue`,
  `CookieConsent.vue`, `MobileQuickBar.vue`, `ChatbotMessage.vue` (route
  actions من ردود الشات بوت — untrusted بالفعل، `isSafeInternalRoute`
  موجودة، أضيف `localePath()` فوقها).
  **متعمدًا متلمسناش**: `stores/app.ts` و`useLanguageSelector.ts` —
  الاتنين بيبنوا الـroute بالاسم/params مباشرة (مش path خام) وده الصح
  أصلاً لمنطق تبديل اللغة نفسه.
- `origin/main` (GitHub) يطابق كل التزام — push مباشر في الحالتين.
- release نهائي: `/opt/elkheima-marketing-releases/0b0321f`
- current: `/opt/elkheima-marketing-current -> .../0b0321f`
- archive: `/var/backups/resort-os/marketing-source-releases/0b0321f.tar.gz`
- archive SHA-256:
  `6ab52916cd615663571538181a4fee0ba884d3711479393b8246d061d257142f`

## 3. بوابة الجودة

- `npm run type-check`: passed (الجولتين).
- `npm run build`: passed (نفس تحذير الأداء الموجود من قبل — chunk
  `public-pages` أكبر من 500KB، تحذير غير حاجز).
- تحقّق شامل (`grep`) بعد الجولة 2 أكّد صفر `to="/..."` خام متبقي في أي
  `.vue`/`.ts`، وصفر `router.push`/`router.replace`/`$router.push` بمسار
  خام غير معدّي بـ`localePath()`.
- تحقّق حي (Playwright، ليس افتراضًا) في الجولتين: إعادة إنتاج الباج
  الفعلي قبل كل إصلاح، ثم تأكيد الإصلاح بعده على production نفسه —
  السيناريو المحدد اللي بلّغه Mohamed (Rooms → زر "تواصل مع الفريق" →
  Contact) اتعاد بالظبط: `href` قبل الإصلاح `/contact`، بعده `/ar/contact`،
  والمحتوى بيظهر فورًا (1054+ حرف، navbar/hero موجودين، صفر console
  errors). فحص إضافي عبر 3 صفحات تانية (Rooms→Restaurant،
  Activities→Packages، Beach→Contact) أكّد كل الروابط بادئتها صح.

## 4. نقطة التراجع

- rollback tags: `resort-os-rollback/marketing-site:pre-8dc95d8` (الجولة
  1) و`resort-os-rollback/marketing-site:pre-0b0321f` (الجولة 2، الحالي).
- rollback manifest:
  `/var/backups/resort-os/marketing-source-releases/0b0321f-rollback-image.txt`
- releases السابقة (`16f8f2c`, `8dc95d8`) لسه محفوظة كاملة على القرص،
  غير متحذوفة.
- لا migration ولا تغيير DB في أي من الجولتين (frontend فقط).

## 5. قبول الإنتاج

- `https://elkheima.com`، `https://www.elkheima.com`،
  `https://elkheima.com/ar/contact` المباشر: HTTP 200.
- 8 حاويات Running، `RestartCount=0` لخدمة `marketing_site`.
- severe logs: صفر.

## ملاحظة صغيرة (من الجولة 1، تُركت للسجل)

أثناء التنظيف بعد نشر الجولة 1، حاولت أمسح مجلد release قديم غير مستخدم
(`/opt/elkheima-marketing-releases/e5e122a`) — اترفضت الأوامر بصلاحيات
الملف (`Permission denied` على كل ملف)، فمفيش أي شيء اتحذف فعليًا. رجعت
عن المحاولة فورًا — الحذف ده مكانش جزء من المطلوب أصلًا.

## الدرس المسجَّل

فحص "الروابط المشتركة" (nav/footer/chatbot) وحده مش كافي لضمان
locale-awareness كاملة في تطبيق فيه عشرات صفحات محتوى — لازم `grep`
شامل على كل أنماط التنقل (`to=`, `router.push`, `router.replace`,
`$router.push`) في المشروع كله، مش بس الملفات "المتوقع" إنها فيها
navigation.
