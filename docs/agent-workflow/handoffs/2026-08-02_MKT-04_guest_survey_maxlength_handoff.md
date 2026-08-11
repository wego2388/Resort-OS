# MKT-04 — Marketing site: guest survey form maxlength guards

**التاريخ:** 2026-08-02
**المالك:** Mohamed
**المنفذ والمراجع النهائي:** Codex
**الحالة:** COMPLETE

## 1. الخلفية

بعد ما اتقفلت جولة مراجعة موديولات resort-os الذاتية بالكامل (CRM-01،
MNT-01، ANL-01، LSE-01، ثم HUB-01 وفحص Beach/Core/Chat)، انتقلت للموقع
التسويقي (`elkheima-marketing-website`، مستودع منفصل) حسب تعليمة Mohamed
الأخيرة صراحةً: "كمل اخيرا علي الويب سايت و معاك وقتك برحتك".

أول حاجة راجعتها كانت التزام صريح اتسجّل في handoff ANL-01 (نفس اليوم):
استبيان تقييم الضيف في resort-os backend (`POST /analytics/reviews/
submit`) بقى يفرض حدود صارمة على المدخلات (schema جديد بدل dict خام) —
وكان مذكور صراحةً إن الفرونت إند المستهلك الحقيقي (`GuestSurvey.vue`)
عايش في المستودع المنفصل ده، ولازم يتراجع شكل الطلب وقت جولة الموقع.

## 2. النتيجة

شكل الطلب نفسه (`guest_name`/`overall_rating`/`comment`/`categories`)
كان مطابق تمامًا للـschema الجديد — مفيش أي كسر وظيفي. لكن أثناء
المراجعة اتكشف إن `GuestSurvey.vue` مالوش أي حد أقصى (`maxlength`) على
أي حقل نصي حر خالص:

- استمارة الملكية الجزئية: حقلين تعليق منفصلين (`highlightText` — "أكتر حاجة
  عجبتك" — و`comment` — "اقتراحات") بيتجمّعوا في حقل `comment` واحد قبل
  الإرسال.
- استمارة الفندق العادي: `comment` واحد بس.

الـschema الجديد في resort-os بيفرض `comment <= 2000` حرف و`guest_name
<= 200` حرف. لو ضيف كتب نص طويل جدًا بشكل غير عادي (خصوصًا في التايم
شير، لأن الحقلين بيتجمّعوا) كان ممكن يتعدّى الحد ويترفض بـ422 بدل ما
يتقبل — سيناريو نادر جدًا عمليًا (استبيان ضيف مش عادة نص طويل)، بس
موجود نظريًا وسهل الوقاية منه.

## 3. الإصلاح

اتضاف `maxlength` لكل حقل نصي حر في `GuestSurvey.vue`، متوافق مع حدود
الباك إند الفعلية:
- حقول الاسم (`guestName`/`highlightText` في الفرع غير-ملكية جزئية، بيتحوّلوا
  لـ`guest_name`): `maxlength="200"`.
- حقلي الملكية الجزئية المدموجين (`highlightText`/`comment`): `maxlength="800"`
  لكل واحد — بعد الدمج بالـlabels القصيرة، أقصى طول ممكن يفضل بأمان تحت
  حد الـ2000 حرف.
- حقل الفندق العادي (`comment`): `maxlength="2000"` مباشرة.

إضافة client-side بحتة، صفر تغيير منطقي — الاستخدام العادي كان أصلًا
بعيد جدًا عن الحدود دي، الهدف الوحيد منع dead-end نادر لضيف بيكتب رأي
طويل بشكل استثنائي.

## 4. المصدر

- repo: `elkheima-marketing-website` (منفصل عن resort-os)
- branch: `main` (git flow عادي، مش single-operational-branch زي resort-os)
- commit: `4fba5b6`
- الملف المتغيّر: `src/apps/ops/GuestSurvey.vue`

## 5. بوابة الجودة

- `npm run validate` (public-truth check + `vue-tsc --noEmit` + `vite
  build`) — الكل نضاف، صفر تحذير جديد.
- مراجعة موازية للشات بوت (`useChatbot.ts`، `ChatbotMessage.vue`) —
  تأكيد إن تحصين CL-01R (escaping حقيقي عبر `textContent`، مش regex،
  قبل تركيب markdown tags؛ صفر lead-capture صامت؛ إشعار خصوصية قبل أول
  turn) لسه سليم ومطبّق صح.
- مراجعة استمارة التواصل العامة (`src/api/publicContact.ts`) — idempotency
  key حقيقي عبر `crypto.randomUUID()`، تتبّع نسخة الموافقة (service/
  marketing consent versioned)، حقل honeypot (`website`) — متطابق تمامًا
  مع `hub.ContactForm` في الباك إند (idempotency_key_hash، consent
  versioning). صفر مشكلة.

## 6. النشر

- release: `/opt/elkheima-marketing-releases/4fba5b6`، current symlink
  محدّث (`MARKETING_SITE_CONTEXT` عبر الـsymlink، مش المسار الشقيق
  الثابت).
- archive: `/var/backups/resort-os/marketing-source-releases/4fba5b6.tar.gz`،
  SHA-256 `81018ef5e29577bfeb40c2a299dd37d12b8cf2433c4946a6798cf7b5e83bf641`.
- rollback tag: `resort-os-rollback/marketing-site:pre-4fba5b6`، manifest:
  `/var/backups/resort-os/marketing-source-releases/4fba5b6-rollback-image.txt`.
  release القديم `/opt/elkheima-marketing-releases/0b0321f` لسه موجود
  كامل، مش متحذوف.
- `marketing_site` بس اتبنى واتنشر — `backend`/`celery_worker`/
  `celery_beat`/`el_kheima` متلمسوش، مالوش migration ولا تغيير DB (frontend
  فقط، نفس نمط MKT-02/MKT-03 قبل كده).
- `sudo docker ps` أكد `RestartCount=0`، صفر error/emerg في اللوجات.
- `https://elkheima.com/` → 200، `https://www.elkheima.com/` → 200.

## 7. ملاحظة — إغلاق جولة "دور في المشروع بالكامل"

هذا يقفل السلسلة الكاملة اللي بدأت بطلب Mohamed الأصلي ("افحص وشوف
بطريقتك... لو وجدت أخطاء صلّحها") ومرّت بـ: POS-02، HR-01، CRM-01،
MNT-01، ANL-01، LSE-01، HUB-01، وأخيرًا MKT-04 — 7 باجات حقيقية اتكشفت
واتصلحت واتنشرت بأدلة backup/rollback/health كاملة لكل واحدة، زائد
مراجعات مؤكِّدة (بدون باج) لـFinance/Inventory/PMS/Timeshare/Beach/
Core/Chat. باقي الجولة الحرة على الموقع التسويقي (شاشات تانية غير
الاستبيان/الشات بوت/التواصل) لو Mohamed حابب استمرار أعمق، لكن النطاق
الصريح المطلوب ("كمل اخيرا علي الويب سايت") اتغطى.
