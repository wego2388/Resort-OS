# MKT-05 — Marketing site: remaining pages (idempotency, PUBLIC_TRUTH gate leaks, locale routing)

**التاريخ:** 2026-08-02
**المالك:** Mohamed
**المنفذ والمراجع النهائي:** Codex
**الحالة:** COMPLETE

## 1. الخلفية

بعد MKT-04، طلب Mohamed صراحةً: "كمل شوف باقي شاشات الويب سايت كمان" —
استكمال جولة المراجعة الحرة على باقي صفحات `elkheima-marketing-website`
(كانت المراجعة السابقة اقتصرت على الشات بوت واستمارة التواصل العامة
واستبيان الضيف). راجعت Rooms/Beach/Restaurant/Activities/Events/
Packages/Products/FAQ/Home/Contact/Timeshare/Booking modal + i18n
locales الأربعة.

## 2. النتيجة والإصلاح — 3 دفعات

### دفعة 1 — Idempotency key ماكانش بيتجدد عند الفشل (7 ملفات)

كل استمارة تواصل عامة في الموقع (`Booking.vue`, `Contact.vue`,
`Timeshare.vue`, `usePageBooking.ts` — المشتركة بين Beach/Events/
Packages/Restaurant/Activities/Rooms —, `HubSpaSection.vue`,
`HubRoomServices.vue`, `SunbedOrderModal.vue`) بتولّد idempotency key
واحد وترجّعه بس بعد **نجاح** الإرسال. الباك إند (`hub.ContactForm` في
resort-os) بيقارن `payload_hash` مع نفس المفتاح — لو مختلف بيرفض بـ409
("Idempotency-Key was already used with different contact data.")،
مش يعيد نفس النتيجة القديمة بصمت. لو رد النجاح ضاع فعليًا (انقطاع شبكة/
timeout بعد ما الباك إند كتب الصف)، والزائر ظن إنه فشل وعدّل حاجة بسيطة
(غلطة إملائية في الرقم) وأعاد الإرسال — كان بيتعلّق على نفس الـ409 للأبد،
من غير أي مخرج غير ريفريش الصفحة كاملة.

**الإصلاح**: توليد مفتاح جديد داخل كل `catch` block كمان، مش بس بعد
النجاح. أسوأ سيناريو دلوقتي: صف طلب تواصل مكرر نادر (لو فعلاً حصل تكرار
حقيقي) — أفضل بكتير من زائر عالق تمامًا.

### دفعة 2 — تسريبات حقيقية من بوابات PUBLIC_TRUTH (4 ملفات + i18n)

الموقع عنده نظام حوكمة صارم (`scripts/check-public-truth.mjs` +
`src/config/publicTruth.ts`) بيمنع ادعاءات حساسة (أسعار/تقييمات/
إحصائيات رقمية/ندرة...) من الظهور من غير موافقة صريحة مسجّلة ومؤرخة —
لكن الـvalidator بيتحقق من إن البوابات نفسها مضبوطة صح، مش إن كل محتوى
معروض فعليًا بيحترمها. لقيت 4 حالات حقيقية كانت **ظاهرة على الإنتاج
الحي دلوقتي** لأنها راكبة على بوابة عامة تانية مفعّلة (`amenities`/
`packages`) بدل بوابتها الخاصة (`ratings`/`prices`/`promotions`/
`numericStats`، لسه fail-closed كلهم):

1. **`Beach.vue`**: "4.2★" (تقييم مفبرك تمامًا — كل تقييم تاني في الموقع
   `Home.vue`/`About.vue` بيحترم بوابة `ratings` بدقة، دي كانت الاستثناء
   الوحيد) و"12,500 m²" — الاتنين تحت `amenities` بس.
2. **`FAQ.vue`**: 4 من 12 سؤال بيردوا برقم خصم/عربون صريح (عربون 30%،
   خصم حجز مبكر/جماعي 10-25%، سعة "حتى 200 ضيف") — تحت `amenities` بس.
   اتحل بإضافة حقل `gate` لكل سؤال حساس في ملفات i18n الأربعة (`en`/`ar`/
   `ru`/`it`)، وفلترة في `FAQ.vue` حسب البوابة المناسبة — اتأكد إن كل فئة
   سؤال لسه فيها سؤال ظاهر واحد على الأقل بعد الفلترة (مفيش فئة فاضية).
3. **`Packages.vue`**: كارت "وفّر حتى 30%" تحت `packages` بس — عكس نفس
   الادعاء المشابه في `Activities.vue` اللي بيحترم `promotions` صح.
4. **`Events.vue`**: بادج "سعة القاعة: 200+ ضيف" تحت `amenities` بس.

زائد فخين **خاملين** (لسه مش ظاهرين، بس محتاجين تصحيح احتياطي قبل ما
يظهروا بالغلط لو بوابة تانية اتفعّلت مستقبلًا من غير مراجعة منفصلة):
- **`Home.vue`**: تقييم "4.2 (1,919 مراجعة)" وبادج "تصنيف 3 نجوم" كانوا
  متضمّنين جوه قسم `exactLocation` (لسه false) من غير بوابتهم الخاصة —
  دلوقتي كل واحد مربوط بالاتنين معًا.
- **`Rooms.vue`**: `rooms.from_15`/`rooms.from_10` بيردوا سعر مختلف
  فعليًا حسب اللغة (300/200 جنيه بالعربي مقابل $15/$10 بالإنجليزي/
  الروسي/الإيطالي — مش ترجمة لنفس الحقيقة، رقمين متضاربين). القسم ده
  محاط بـ`promotions` (لسه false) فمش ظاهر دلوقتي — **مالمستش الأرقام
  نفسها عمدًا** (قرار سعر حقيقي محتاج معرفة Mohamed، مش تخمين وكيل)،
  وأضفت تحذير واضح في الكود يمنع أي تفعيل غير مقصود قبل حل التضارب.

### دفعة 3 — رابط داخلي خام في Products.vue

كاردز الأقسام الستة كانت بتستخدم مسارات خام (`/rooms`، `/beach`...) بدل
`localePath('/rooms')`، عكس زرار الـCTA تحت مباشرة وباقي الموقع بالكامل.
مسار خام لسه بيتطابق (بادئة اللغة اختيارية في الراوتر)، لكن بيخلي حارس
اللغة العام يعيد التوجيه للغة المحفوظة/الافتراضية بدل اللي الزائر
متصفح بيها فعليًا — زائر روسي أو إيطالي بيدوس كارت "الغرف" كان ممكن
يترمي فجأة للعربي أو الإنجليزي.

## 3. المصدر

- repo: `elkheima-marketing-website` (منفصل)
- branch: `main`
- commits: `5c8ad84` (idempotency)، `c5319f6` (PUBLIC_TRUTH gates)،
  `53bf7a3` (Products.vue routing)
- الملفات: `Booking.vue`, `Contact.vue`, `Timeshare.vue`,
  `usePageBooking.ts`, `HubSpaSection.vue`, `HubRoomServices.vue`,
  `SunbedOrderModal.vue`, `Beach.vue`, `FAQ.vue`, `Packages.vue`,
  `Events.vue`, `Home.vue`, `Rooms.vue`, `Products.vue`,
  `src/i18n/locales/{ar,en,ru,it}.json`

## 4. بوابة الجودة

- `npm run validate` (public-truth check + `vue-tsc --noEmit` + `vite
  build`) نضاف بعد كل دفعة من الثلاث.
- تحقّق منطقي يدوي: كل فئة سؤال في `FAQ.vue` (booking/beach/rooms/
  events/payment) لسه فيها سؤال ظاهر واحد على الأقل بعد فلترة الـ`gate`
  (صفر فئة بتطلع فاضية بعد الفلترة).
- استخدام subagent مستقل (Explore) لمسح باقي الصفحات (Activities/Gallery/
  Blog/BlogPost/باقي About.vue) — رجّع نتائج راجعتها وتأكدت منها بنفسي
  قبل التنفيذ (قرأت الكود الفعلي لكل finding، مش اعتماد أعمى على تقرير
  الوكيل)، ثم طبّقت الإصلاحات المؤكدة بنفسي.

## 5. النشر

- release: `/opt/elkheima-marketing-releases/53bf7a3`، current symlink
  محدّث.
- archive: `/var/backups/resort-os/marketing-source-releases/53bf7a3.tar.gz`،
  SHA-256 `6e216b8ae15fda2efcda6d16e3819df9b3cbacb7c07a866c70110aec32962f6a`.
- rollback tag: `resort-os-rollback/marketing-site:pre-53bf7a3`، manifest:
  `/var/backups/resort-os/marketing-source-releases/53bf7a3-rollback-image.txt`.
  release القديم `/opt/elkheima-marketing-releases/4fba5b6` لسه موجود
  كامل، مش متحذوف.
- `marketing_site` بس اتبنى واتنشر — resort-os (backend/frontend) متلمسش
  خالص، مفيش migration ولا تغيير DB.
- `sudo docker ps` أكد `RestartCount=0`، صفر error/emerg في اللوجات.
- `https://elkheima.com/`، `/faq`، `/beach` → 200 كلهم،
  `https://www.elkheima.com/` → 200.
- ملاحظة عملية أثناء النشر: انقطاع SSH مؤقت لثواني (connection timed
  out) في منتصف خطوة tagging، اتحل بإعادة المحاولة العادية — الاتصال رجع
  فورًا، مفيش أي أثر على البيانات أو الحاويات.

## 6. ملاحظة — قرار Mohamed مطلوب

`rooms.from_15`/`rooms.from_10` (سعر عشا رومانسي/رياضات مائية) لسه
متضاربين بين اللغات في الكود (300/200 جنيه عربي مقابل $15/$10 باقي
اللغات) — القسم ده معطّل حاليًا (`promotions` لسه false) فمفيش أثر على
الإنتاج، لكن محتاج قرارك بالسعر الصح الحقيقي قبل ما يتفعّل القسم ده أي
وقت مستقبلًا.
