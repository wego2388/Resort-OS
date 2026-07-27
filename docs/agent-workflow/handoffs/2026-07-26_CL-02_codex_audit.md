# CL-02 — تدقيق Codex لموقع El Kheima Marketing خارج الشات

**التاريخ:** 2026-07-26  
**الحالة:** `CHANGES_REQUIRED` — الموقع **غير جاهز للنشر أو UAT العام** قبل إغلاق بنود `[High]`.  
**نوع العمل:** تدقيق read-only؛ لم يُعدّل أي كود في المشروع التسويقي، ولم يحدث commit/push/deploy.  
**المشروع المدقَّق:** `/home/wego/projects/elkheima-marketing-website`  
**المشروع المرجعي للـ backend/database:** `/home/wego/projects/resort-os`

## 1. النطاق والملكية

شمل التدقيق الأمن الطبيعي، الوعود التسويقية والـ leads، عقود الـ API، auth/tokens، XSS/URLs، headers/CSP، dependencies، build/typecheck، SEO/structured data، accessibility، performance، وصدق المحتوى.

استُبعدت عمدًا ملفات CL-01R/الشات التي كانت متغيرة وقت التدقيق:

- `src/api/client.ts`
- `src/apps/public/DigitalHub.vue`
- `src/components/chatbot/**`
- `src/components/hub/HubConcierge.vue`
- `src/composables/booking/useChatbot.ts`

لم تُنسب أي finding إلى تعديلات CL-01R داخل هذه الملفات، ولا يجوز أن تتضمن packets أدناه تعديلها قبل تحرير ملكيتها رسميًا.

حالة marketing worktree وقت التدقيق:

```text
 M src/api/client.ts
 M src/apps/public/DigitalHub.vue
 M src/components/chatbot/ChatbotMessage.vue
 D src/components/hub/HubConcierge.vue
 M src/composables/booking/useChatbot.ts
```

## 2. نتيجة التنفيذ والـ validation

| الفحص | النتيجة | الملاحظة |
|---|---|---|
| `npm run build` | PASS | Vite 5.4.21، عدد 2036 module |
| `npm run type-check` | FAIL | `vue-tsc@1.8.27` يتعطل قبل فحص كود المشروع مع TypeScript 5.9.3 |
| `npm audit --omit=dev --json` | FAIL | 3 production vulnerabilities: 2 Low + 1 Moderate في سلسلة `@vueuse/head -> unhead` |
| `npm audit --json` | FAIL | 10 إجماليًا: 4 High + 4 Moderate + 2 Low؛ تشمل Vite/vue-tsc وسلسلة Unhead |
| `docker run ... nginx:1.27-alpine nginx -t` | PASS | syntax ملف `nginx.spa.conf` صالح |
| JSON parse | PASS | `schema.json` و`google-business-profile.json` و`manifest.json` JSON صالح؛ الصلاحية النحوية لا تعني صحة الحقائق |
| static asset reference scan | FAIL | مرجعان مكسوران لنفس الملف غير الموجود: `/images/rooms/beach-view-01.webp` |
| secret-pattern scan | PASS | لم يظهر secret فعلي في الملفات المدققة |
| `git diff --check` | PASS | لا توجد whitespace errors في التغييرات المرئية |
| automated tests | غير موجودة | لا توجد Vitest/Playwright/Cypress/axe tests للموقع |

تفاصيل build المهمة:

- `public-pages`: ‏460.25 kB raw / 129.67 kB gzip.
- `vendor-vue`: ‏151.87 / 56.36 kB.
- CSS الرئيسي: ‏109.59 / 19.41 kB.
- تُشحن locale backup chunks إضافية، منها `ru-backup` بحجم 74.90 / 31.33 kB.
- `public/` يقارب 49 MB، منه `public/images/` يقارب 47 MB و257 ملفًا.
- أكبر أصل: `public/images/logo.png` بحجم 1.8 MiB، ثم `room-24.webp` بحجم يقارب 1 MiB.

## 3. Findings — [High]

> `[High]` هنا تعني **أولوية/بوابة نشر**، وليست بالضرورة CVSS High.

### CL02-H01 — عروض وندرة وكوبونات غير متصلة بأي مصدر حقيقة

**الدليل**

- `src/components/AbandonmentRecovery.vue:8-14,27,35-55`: كوبون `SAVE10` وخصم 10% hardcoded.
- `src/App.vue:34-35,63-65`: يعرض الكوبون على صفحات الحجز/الغرف/الباقات وغيرها.
- `src/components/HotDealsBar.vue:28-38,52-60`: التعليق نفسه يقر بأن المحتوى ثابت وغير متصل بمصدر حي، ثم يعرض خصم 20%، 1,900 ضيف، ترقية ولاء، “3 أماكن فقط”، ليلة ثالثة مجانية، ونظام نقاط.
- `src/apps/public/Home.vue:93`: الشريط منشور في الصفحة الرئيسية.
- `src/components/UrgencyTimer.vue:6-42,56-83`: خصم 25%، 3 غرف فقط، “الأكثر حجزًا اليوم”، ومؤقت 24 ساعة يعيد تشغيل نفسه.
- `src/apps/public/Packages.vue:178-188`: المؤقت منشور فعليًا.
- `src/components/SmartExitModal.vue:22-57,80-109`: يحتوي `DIRECT10` وbest-rate/free-upgrade/free-drink؛ غير mounted حاليًا لكنه كود تضليلي جاهز لإعادة الاستخدام.
- مسار الحجز الحالي يرسل inquiry إلى `/api/v1/hub/contact` ولا يقرأ أو يتحقق من coupon أصلًا.
- `backend/app/modules/hub/api/router.py:85-125`: عروض `/hub/offers` الحالية staff-authenticated وليست public contract.

**الأثر**

وعود سعرية/توافر/ولاء يمكن للضيف الاعتماد عليها دون إمكانية تنفيذها أو إثباتها. هذا خطر ثقة، نزاع مالي، وسمعة قبل أن يكون مجرد UI.

**الإجراء الإلزامي**

1. إخفاء/حذف كل claim غير معتمد فورًا.
2. لا يعاد أي خصم/ندرة/تقييم إلا من public read-only contract مبني على سجل approved له `valid_from`, `valid_until`, `status`, currency، وشروط واضحة.
3. لا يظهر coupon قبل وجود validation حقيقي داخل مسار الحجز/الاستفسار المعتمد.
4. إن لم يعتمد المالك العرض كتابةً، القيمة الآمنة هي عدم عرضه.

**قبول**

- لا تظهر في production strings مثل `SAVE10`, `DIRECT10`, `Only 3`, `25% off`, `20% off` من fallback.
- contract test يثبت أن العرض المنتهي/غير النشط لا يظهر.
- UAT يربط كل claim ظاهر بسجل DB أو ملف حقيقة approved موثق المصدر والتاريخ.

### CL02-H02 — GA/GTM/Meta تعمل قبل موافقة الزائر

**الدليل**

- `src/main.ts:19-36`: تهيئة GA وGTM وFacebook Pixel أثناء bootstrap مباشرة إذا وُجدت env IDs.
- `src/composables/seo/useGoogleAnalytics.ts:13-36`: تحميل Google script وإرسال page view تلقائيًا.
- `src/composables/seo/useGoogleTagManager.ts:6-36`: تحميل GTM script/iframe.
- `src/composables/seo/useFacebookPixel.ts:6-35`: تحميل `fbevents.js` وإرسال `PageView`.
- `src/components/CookieConsent.vue:40-60`: البانر يظهر لاحقًا؛ decline يسجل localStorage فقط ولا يمنع التحميل ولا يرسل denied/revoke.
- `src/router/index.ts:40-53`: يستمر في إرسال page views متى وجدت globals.
- `src/i18n/locales/en.json:3278-3296` و`ar.json:3278-3296`: سياسة الخصوصية تقول استخدام analytics وpromotional offers، لكن لا توجد آلية unsubscribe/revoke أو مدد احتفاظ/أطراف مفصلة.

**الأثر**

يحدث اتصال بطرف ثالث ومعالجة tracking قبل الاختيار؛ زر الرفض لا يحقق ما يفهمه الزائر منه.

**الإجراء الإلزامي**

- default consent = denied قبل تحميل أي script غير ضروري.
- لا تُنشأ globals ولا third-party requests إلا بعد `accepted`.
- decline/revoke يوقف الإرسال اللاحق ويُحدّث consent لدى providers.
- consent record versioned مع timestamp وفئات منفصلة عند الحاجة.
- routes التشغيلية ذات token/QR لا تُتبع افتراضيًا.
- تحديث Privacy بنطاق البيانات، الأغراض، الأطراف، المدة، الحقوق، وطريقة سحب الموافقة.

**قبول**

- Playwright network assertion: صفر طلبات إلى Google/Meta/TripAdvisor tracker قبل الموافقة وبعد decline.
- بعد accept فقط تظهر الطلبات المصرح بها.
- يوجد زر دائم لإعادة فتح الإعدادات وسحب الموافقة.

### CL02-H03 — public contact intake غير typed ويحوّل PII إلى CRM Lead بصمت

**الدليل**

- frontend يرسل إلى `/api/v1/hub/contact` من:
  - `src/apps/public/Booking.vue:101-116`
  - `src/composables/booking/usePageBooking.ts:78-139`
  - `src/apps/public/Contact.vue:181-223`
  - `src/components/SunbedOrderModal.vue:136-156`
  - `src/components/hub/HubSpaSection.vue:70-90`
  - `src/components/hub/HubRoomServices.vue:108-124`
- `backend/app/modules/hub/api/router.py:183-224`: يقبل `data: dict` بدل schema، يستخدم مفاتيح إجبارية مباشرة قد تنتج 500، يثق في `branch_id` القادم أو `1`، ثم ينشئ CRM Lead تلقائيًا.
- نفس المسار يبتلع أي exception أثناء إنشاء lead دون logging/audit واضح.
- يوجد IP rate limit حقيقي 30/60s في `backend/app/core/rate_limit.py:139,162-181`، وهذه نقطة إيجابية، لكنه لا يعوض schema/branch/abuse controls ولا يمنع 30 lead في الدقيقة.
- `backend/app/modules/hub/models.py:133-148` و`backend/app/modules/crm/models.py:147-169`: الهاتف والبريد مخزنان plaintext دون retention fields أو marketing-consent provenance.
- النماذج لا تعرض disclosure صريحًا بأن الاستفسار سيُحفظ في CRM، ولا تفصل service-contact عن marketing consent.

**الأثر**

branch injection، payloads كبيرة/غير صالحة، أخطاء 500، spam/lead pollution، تخزين PII بلا lifecycle واضح، وتحويل غرض “تواصل معي بخصوص طلبي” إلى lead تسويقي غير شفاف.

**الإجراء الإلزامي**

- `ContactFormCreate` typed schema بحدود أطوال وصيغ وتطبيع phone/email، ورفض unknown fields.
- branch/site server-derived من public site context؛ ممنوع `branch_id ?? 1` أو قبول branch arbitrary من browser.
- idempotency key + honeypot وطبقة anti-abuse قابلة للرفع دون إضرار المستخدم الحقيقي، مع trusted proxy hops مضبوطة في VPS.
- فصل موافقة التواصل اللازم لتنفيذ الطلب عن موافقة marketing الاختيارية.
- إنشاء lead فقط وفق قاعدة معلنة ومسجلة معها `source`, `purpose`, consent/version/timestamp.
- تشفير PII at rest أو قرار risk موثق مع DB access controls، retention، purge job، وحق حذف.
- logging آمن لا يسجل payload/PII كاملًا، ولا `except Exception: pass`.

**قبول**

- API tests لـ missing/oversized/malformed/unknown fields، branch spoof، rate limit، idempotency، وCRM failure.
- request ناقص يرجع 422 structured، لا 500.
- لا يستطيع العميل اختيار فرع آخر.
- توجد اختبارات retention/purge وconsent provenance.

### CL02-H04 — structured data وحقائق النشاط والأسعار متناقضة أو غير موثقة

**الدليل الداخلي**

- `src/components/LocalBusinessSchema.vue:11-41`: domain مختلف `alkhayma.com`، عنوان Naama Bay، coordinates وأسعار 3000–7000 غير موثقة.
- `LocalBusinessSchema.vue:67-87`: `starRating=4.5`، aggregate 4.7/156، ومراجعة باسم Sarah Johnson وتاريخ/نص غير موثقين.
- `LocalBusinessSchema.vue:101-120`: ReserveAction وحيوانات/تدخين/مواعيد غير مربوطة بمصدر.
- `src/apps/public/Home.vue:598-605,637-642,695-710,786-805`: تقييمات 4.0 و9.0 و4.2، 1,919 reviews، 37K visitors، و3-Star في نفس الصفحة.
- `public/schema.json:9-48,111-123`: #1 of 8، 5-star، تقييمان متضاربان داخل نفس object بسبب duplicate `aggregateRating`، أعداد مراجعات 487/250، 120 غرفة، placeholder phone، وpets=true.
- `public/schema.json:50-109,126-171,232-255,305-369`: spa/pool/fitness/shuttle/PADI/kids club/weddings/restaurant ratings/FAQ وعرض Event بسعر نصي؛ كلها بلا سجل اعتماد.
- `public/google-business-profile.json:1-10,32-111,113-203`: ملف خطة تسويق/محتوى aspirational منشور كـ public asset وفيه infinity pool/spa/all-inclusive/pets/shuttle وغيرها.
- `src/config/constants.ts:5-13`، `src/blocks/layout/TheFooter.vue:86-90`، و`src/apps/public/Privacy.vue:31-35`: domains/emails/social identities مختلفة.
- `index.html:28` يعرض دخول 100/150 وغرفًا من 300، بينما `src/config/constants.ts:16-22` و`backend/app/modules/beach/services.py:126,139-142` يستخدمان 200/250.
- الموقع يعرض coordinates `27.8625,34.2915` في `Home.vue:755,822` و`About.vue:150,160`، بينما schema يستخدم `27.915752,34.329869`.
- ملفات structured data تشير إلى Naama Bay بينما `constants.ts:6-8` يقول Sharm El Maya/Old Market.

**لقطة تحقق خارجية بتاريخ التدقيق**

- [TripAdvisor listing](https://www.tripadvisor.com/Hotel_Review-g297555-d3854106-Reviews-El_Kheima_Beach_Resort-Sharm_El_Sheikh_South_Sinai_Red_Sea_and_Sinai.html) ظهر بنتيجة 4.7/5 و109 reviews.
- [Booking.com listing](https://www.booking.com/hotel/eg/el-kheima-beach-resort.en-gb.html) ظهر بنتيجة 8.6 و29 reviews، وتختلف الأرقام حسب locale/time؛ وهذا يثبت أن hardcoding سيتقادم.
- [Google Travel listing](https://www.google.co.il/travel/hotels/entity/ChgI6aOpv4u7uaieARoLL2cvMXRoenIxc2IQAQ) ظهر 3-star و4.2 وحوالي 1,960 reviews.

هذه الروابط verification snapshot وليست تصريحًا للنسخ الآلي أو مصدرًا دائمًا؛ الاعتماد النهائي يجب أن يأتي من المالك والحسابات الرسمية.

**الأثر**

معلومات مضللة للزائر ومحركات البحث، rich-result/manual-action risk، وارتباك DNS/brand قبل الإطلاق.

**الإجراء الإلزامي**

- إنشاء truth registry واحد مع: `field`, `value`, `locale`, `source`, `approved_by`, `approved_at`, `valid_from/to`, `status`.
- تحديد domain/email/location/coordinates/star classification/amenities/prices/policies نهائيًا قبل DNS.
- حذف `public/google-business-profile.json` من public build؛ هو artifact تخطيط لا asset إنتاج.
- حذف `public/schema.json` غير المستخدم أو توليده فقط من truth registry.
- منع self-authored reviews وaggregate ratings ما لم تكن مطابقة لمصدر طرف ثالث وسياساته.
- `starRating` يمثل التصنيف الفندقي، لا متوسط المراجعات.

**قبول**

- لا يوجد claim ظاهر أو JSON-LD بلا source/approval.
- Schema Validator/Rich Results يمر دون invented reviews أو URLs مكسورة.
- domain/contact/location موحد في code، sitemap، OG، schema، البريد، والـ DNS.

### CL02-H05 — Service Worker/Offline Orders عقد قديم يمكنه إعطاء نجاح زائف

**الدليل**

- لا توجد أي `serviceWorker.register(...)` في `src/` أو `index.html`، رغم شحن `public/sw.js` وmanifest وPWA banner. تسجيل قديم على origin قد يظل مسيطرًا عند مستخدم سابق.
- `src/composables/pwa/useOfflineOrders.ts:31-47`: يخزن payload وtoken في IndexedDB، و`offline_ref` مبني على `Math.random`.
- `public/sw.js:55-75`: يرسل إلى `/api/orders/location`، وهو ليس contract الطلب العام الحالي.
- contract الحقيقي هو `/api/v1/dining/public/orders` ويستخدم guest session/schema مختلفة؛ لذلك queue الحالي لا يستطيع التسليم الصحيح.
- `public/sw.js:77-109`: يحمل gate staff sales flow وBearer token داخل SW عام.
- `public/sw.js:112-159`: caches لمسارات قديمة `/api/products`, `/api/gate/*`, `/api/categories`.
- `public/sw.js:180-188`: يقبل أي payload/token من controlled same-origin client دون schema validation.
- `public/sw.js:207-215`: يتنقل إلى URL قادم من push payload دون same-origin path allowlist.

**الأثر**

الزائر قد يظن أن الطلب حُفظ وسيرسل تلقائيًا بينما لن يصل، مع بقايا staff/offline token surface على origin عام.

**الإجراء الإلزامي**

الاختيار الآمن قبل الإطلاق هو **retire** للـ SW والـ offline-order promise:

1. شحن retirement worker يحذف caches/IndexedDB القديمة ثم unregister controlled workers.
2. حذف gate sales/API caches من الموقع العام.
3. إخفاء أي UI يعد بالمزامنة حتى يوجد contract idempotent، schema-versioned، واختبارات offline حقيقية.
4. إن أعيد بناء PWA لاحقًا: guest capability scoped، expiry، encryption threat model، `crypto.randomUUID`, same-origin notification targets، وqueue state ظاهر (`pending/failed/synced`) لا نجاح افتراضي.

**قبول**

- browser لديه SW v7 قديم ثم يفتح النسخة الجديدة: يُحذف التحكم والكاش والـ DB القديم بأمان.
- لا يوجد staff Bearer token في public IndexedDB/SW.
- لا يظهر “سيتم الإرسال” دون E2E offline→online test يثبت وصول الطلب مرة واحدة فقط.

### CL02-H06 — headers/CSP غير موجودة على response الإنتاج

**الدليل**

- `nginx.spa.conf:14-75`: proxy/cache/gzip فقط؛ لا توجد CSP، `frame-ancestors`/X-Frame-Options، HSTS، Referrer-Policy، Permissions-Policy، أو X-Content-Type-Options.
- `index.html:7-9`: meta referrer/nosniff/Permissions-Policy ليست بديلًا موثوقًا عن response headers، وبعض هذه السياسات لا تعمل من meta كما يتوقع الكود.
- `index.html:30-38`: 3 Google Fonts stylesheets وTripAdvisor external script يجب حصرها أو إزالتها قبل CSP.
- `nginx.spa.conf:31-41`: `/api/` proxy بلا `client_max_body_size` محلي؛ يجب أن تكون الحدود معلنة في edge/app أيضًا.

**الأثر**

غياب defense-in-depth ضد framing/content injection/MIME confusion وتسريب capabilities، مع صعوبة تفعيل CSP لاحقًا بسبب third-party surface الحالي.

**الإجراء الإلزامي**

- وضع headers في Hostinger edge النهائي، مع نسخة دفاعية في container nginx.
- CSP تبدأ Report-Only، تجمع violations، ثم enforce. قلل external scripts قبل كتابة allowlist.
- HSTS على TLS edge فقط وبعد ثبوت كل subdomains؛ لا يضاف عشوائيًا داخل HTTP container.
- تقييد body/timeouts وWebSocket paths حسب contracts الفعلية.

**قبول**

- `curl -I` من الإنترنت يثبت headers على HTML وstatic وAPI errors.
- CSP enforced بلا `unsafe-eval`، وأي `unsafe-inline` مؤقت له ticket/expiry.
- securityheaders.com أو بديله يصل للهدف المتفق عليه، مع regression test للheaders.

### CL02-H07 — dependency gate وtype gate مكسوران

**الدليل**

- `package.json:12-21`: يوجد `@vueuse/head` و`@unhead/vue` و`unhead` معًا.
- production audit: سلسلة Unhead تحوي URI sanitization/XSS bypass advisories.
- full audit: 4 High و4 Moderate و2 Low؛ منها Vite high/dev-server وvue-tsc toolchain.
- `package.json:29-31`: TypeScript يسمح بـ5.x بينما `vue-tsc@1.8.27` قديم؛ resolved TS 5.9.3 يجعل `vue-tsc` ينهار:

```text
Search string not found: "/supportedTSExtensions = .*(?=;)/"
Node.js v20.20.0
```

**الأثر**

لا يوجد ضمان type safety أصلًا، وproduction head library ضمن advisories مرتبطة بـ XSS/URI scheme.

**الإجراء الإلزامي**

- توحيد head stack على dependency واحدة مدعومة، وإزالة legacy duplicate.
- ترقية Vue/Vite/vue-tsc/TypeScript كمجموعة توافق، لا `npm audit fix --force` عمياء.
- تثبيت runtime/toolchain versions وقرار update cadence.
- بعد إصلاح runner يجب إصلاح **كل** type errors؛ PASS build وحده غير كافٍ.

**قبول**

- `npm ci && npm run type-check && npm run build` كلها PASS من clone نظيف.
- `npm audit --omit=dev` = صفر High/Moderate، وأي استثناء أقل له risk acceptance وتاريخ انتهاء.
- لا توجد حزمتا head متنافستان.

## 4. Findings — [Medium]

### CL02-M01 — SEO للـ SPA لا ينتج صفحات قابلة للمشاركة/الفهرسة بدقة

- `nginx.spa.conf:65-69` يرجع `index.html` نفسه لكل route؛ bots التي لا تنفذ JS ترى title/description الصفحة الرئيسية.
- `src/composables/seo/useSEO.ts:17` يقرأ `VITE_APP_URL` بينما `Dockerfile:27-33` يمرر `VITE_SITE_URL`.
- `useSEO.ts:20,32,61`: عند غياب `url` يصبح canonical و`og:url` للصفحة الرئيسية.
- كل استخدامات `<SEOHead>` المدققة لا تمرر `url`؛ أي صفحة داخلية تصبح canonical للـ home.
- `SEOHead.vue:5-16` يدعم locale `ar|en` فقط، بينما router يدعم ar/en/ru/it.
- `src/router/routes/public.routes.ts:3-13`: routes متعددة اللغات، لكن `public/sitemap.xml:14-97` لا يضع alternates للصفحات الداخلية.
- `public/sitemap.xml:50-61` يفهرس `/hub` و`/menu`، و`public/sitemap-enhanced.xml:86-113` يحتوي `/spa`, `/diving`, `/offers` غير الموجودة.
- لا توجد noindex policy لمسارات capability tokens: `/s/:token`, `/survey/:token`, `/hub/:token`.

**المطلوب:** prerender/SSR للصفحات التسويقية الثابتة، canonical/hreflang من route+locale، sitemap واحدة مولدة من route manifest، وnoindex/no-store للـ QR/token routes.

### CL02-M02 — عقود API ميتة وbranch 1 وغياب public site bootstrap

- `src/stores/modulesStore.ts:5-43` و`src/App.vue:59-60`: نداء `/modules/public` غير موجود، ثم fallback يفعّل modules افتراضية.
- `src/composables/ui/useMediaSettings.ts:19-34,57-60`: نداء `/settings/public` غير موجود ويفشل بصمت، ويمكن تكراره لأن `loaded` لا يصبح true عند الفشل.
- `src/api/menu.ts:3-8` و`src/api/rooms.ts:4-27`: dead admin-like wrappers بمسارات double `/api` وغير مناسبة للموقع العام.
- `src/apps/public/Blog.vue:184` و`BlogPost.vue:179`: `branch_id: 1`.
- يوجد public room-types contract حقيقي في `backend/app/modules/pms/api/router.py:152-170`، لكن `Rooms.vue:29-50,318-357` يعرض أربع فئات ثابتة ولا يستخدمه.
- `Rooms.vue:318-323` يقول إن public room types غير موجودة، بينما backend يحتويها؛ documentation/code drift.

**المطلوب:** يعتمد التنفيذ على CX-02C active branch/site bootstrap، ثم public contract واحد typed/versioned للهوية والمحتوى والغرف/الأسعار. ممنوع fallback إلى فرع 1. لا يجب كشف room-level occupancy؛ يكفي catalog وسعر/availability aggregate مع `as_of` وcurrency/policy.

### CL02-M03 — الحجز inquiry لكن UI/الشروط قد توحي بعقد مالي غير موجود

- `Booking.vue:63-74` يوضح في comment أنه inquiry، وهذه نقطة صحيحة، والنص الظاهر يجب أن يبقى واضحًا.
- `PageBookingModal.vue:57-73` يعرض “Total” و“Confirm” من أسعار frontend ثابتة رغم أن backend يستقبل رسالة contact فقط.
- `usePageBooking.ts:38` و`Booking.vue:92` و`Rooms.vue:343`: `new Date().toISOString()` يستخدم UTC وقد يعطي min date خطأ قرب منتصف الليل في Cairo.
- `usePageBooking.ts:115-116` يرسل check-in/out دون validation صريح أن checkout > checkin.
- `src/i18n/locales/en.json:3299-3320` و`ar.json:3299-3320`: عربون 30%، VAT 14%، refunds، وقواعد مسؤولية منشورة بلا policy source معتمد.
- `Rooms.vue:134-151,178-195` يعرض “special offer” وأسعار “from” غير مربوطة بمصدر.

**المطلوب:** إما inquiry بلا total/confirmation claims، أو عقد booking/quote حقيقي يحدد quote expiry/currency/tax. استخدم business timezone server-side، وراجع Terms قانونيًا وعمليًا قبل النشر.

### CL02-M04 — accessibility gaps في gallery/modals

- `src/apps/public/Gallery.vue:70-101`: cards عبارة عن `div @click` بلا keyboard/role/tabindex.
- `Gallery.vue:114-165`: lightbox بلا `role=dialog`, `aria-modal`, focus trap, Escape، أو return focus، وأزرار icon فقط بلا labels.
- `src/blocks/sections/HomeGallerySlider.vue:62-68,96-120`: navigation/fullscreen buttons ناقصة aria labels/dialog focus management.
- `src/components/shared/PageBookingModal.vue:2-79`: modal بلا dialog semantics/focus trap/Escape/return focus.
- توجد نقاط إيجابية في `src/assets/main.css:243,285,1096`: reduced-motion وfocus-visible أساسهما موجود.

**المطلوب:** shared accessible dialog primitive، keyboard grid interactions، localized accessible names، وفحص axe + keyboard + screen reader smoke.

### CL02-M05 — performance وassets

- `vite.config.ts:37-46` يجمع كل `/apps/public/` في chunk واحد `public-pages`، فيلغي فائدة route lazy imports عمليًا.
- `public/` يقارب 49 MB؛ صور عديدة 500–1000 kB وشعار PNG 1.8 MiB.
- `src/apps/public/Home.vue:174` و`Rooms.vue:268` يشيران إلى `/images/rooms/beach-view-01.webp` غير الموجود.
- `index.html:30-35`: ثلاثة Google Font stylesheets render-blocking.
- backup locale chunks تُبنى رغم عدم الحاجة الظاهرة لها.
- صور كثيرة بلا dimensions/srcset/sizes، ما يرفع LCP/CLS/data usage.

**المطلوب:** إزالة manual mega-chunk، image pipeline AVIF/WebP responsive، budgets، self-host/subset fonts، حذف assets/locale backups غير المستخدمة، وتصحيح المرجعين المكسورين.

### CL02-M06 — auth/token/security code ميت يعطي ثقة زائفة

- `src/stores/settingsStore.ts:94-109`: dead branch يقرأ `auth_token` من localStorage ويرسل staff settings من موقع لا يملك login.
- `src/utils/security.ts:16-22,119-126,128-179,233-295`: client SQL escaping، URL validator يقبل أي scheme، CSRF token self-generated في localStorage بـ`Math.random` وليس مربوطًا بالسيرفر، regex sanitizer، وCSP helper لا يضيف CSP.
- لا توجد استخدامات حية لهذه helpers خارج الملف في النطاق المدقق، لكن وجودها يشجع إعادة استخدامها كضمان أمني غير حقيقي.
- generic auth/refresh logic داخل `src/api/client.ts` يحتاج تدقيقًا بعد تحرير CL-01R؛ لم يُفحص أو يُسند في هذا التقرير.

**المطلوب:** حذف dead auth/security abstractions أو استبدالها بعقود server-backed. URL allowlists يجب أن تقيد `https/http` أو same-origin حسب السياق.

### CL02-M07 — هوية ومحتوى متعدد اللغات غير متسقين

- الاسم يتغير بين `El Kheima`, `Al Khayma`, و`Al Kheima`.
- البريد يتغير بين `info@alkhaymaresort.com` و`Elkhima.beach@gmail.com`، بينما listing خارجي آخر يستخدم domain مختلف.
- بعض أقسام الخدمات/hub hardcoded بالعربية داخل موقع يدعم أربع لغات.
- وصف Italian restaurant/spa/all-inclusive/24/7 وكل غرفة بإطلالة بحرية موجود بلا content approval registry.

**المطلوب:** content inventory كامل لكل locale، مع منع fallback الذي يحول claim غير معتمد إلى نص “حقيقي”. النص غير المعتمد يُخفى، لا يُخترع.

## 5. Findings — [Low]

### CL02-L01 — روابط `_blank` بلا `rel`

أمثلة: `Booking.vue:17`, `BlogPost.vue:43-52`, `TripAdvisorWidget.vue:31`, `CTASection.vue:17`. المتصفحات الحديثة توفر implicit noopener غالبًا، لكن القاعدة الموحدة يجب أن تضيف `rel="noopener noreferrer"` وتختبر external-link component.

### CL02-L02 — لا توجد اختبارات frontend

لا توجد unit/component/E2E/accessibility suites. يلزم حد أدنى:

- contract tests للمحتوى والـ API.
- Playwright smoke لأربع locales وأهم routes.
- consent/network tests.
- axe على home/rooms/booking/gallery/privacy.
- link/image/structured-data checks في CI.

### CL02-L03 — artifacts تطويرية داخل public

`public/dark-mode-test.html` وملفات SEO/business-plan العامة تحتاج inventory. لا يُشحن أي artifact ليس runtime asset مقصودًا.

### CL02-L04 — missing external-link consistency وdead wrappers

توجد re-export wrappers مكررة تحت `src/composables/` و`src/composables/seo|ui|pwa/`. ليست مشكلة إنتاج بذاتها، لكنها تزيد فرص تعديل نسخة غير المستخدمة؛ تُنظف بعد type gate.

## 6. مصدر الحقيقة المطلوب قبل “تكملة بيانات حقيقية”

لا ينبغي لـ Codex اختراع بيانات نشاط حقيقية. المطلوب إنشاء registry مع ثلاث حالات فقط:

1. `approved`: يظهر في الموقع ويمكن نشره.
2. `unverified`: يبقى مخفيًا.
3. `expired`: لا يظهر حتى إعادة اعتماد.

الحقول التي تحتاج قرار المالك قبل الإطلاق:

- الاسم التجاري الإنجليزي/العربي والدومين النهائي.
- البريد والهاتف وWhatsApp والحسابات الرسمية.
- العنوان وGoogle CID والـ coordinates.
- التصنيف الفندقي الرسمي.
- أنواع الغرف، السعة، الصور، السعر الأساسي، الضرائب، وسياسة التغير.
- مواعيد الوصول/المغادرة والتشغيل.
- كل amenity: pool/spa/fitness/shuttle/diving/pets/kids club/Wi-Fi/parking/room service.
- أسعار دخول الشاطئ/VIP والباقات/الأنشطة/السبا.
- refund/deposit/tax/cancellation policies.
- العروض: الشروط، الكود، السقف، الصلاحية، المخزون.
- التقييمات وأعداد المراجعات ومصدرها و`as_of`.

Public response المقترح بعد CX-02C:

```json
{
  "schema_version": 1,
  "site": {
    "slug": "el-kheima",
    "branch_id": 123,
    "brand": {},
    "contacts": {},
    "location": {},
    "policies": {}
  },
  "room_types": [],
  "offers": [],
  "content_version": "2026-07-26T00:00:00Z",
  "as_of": "2026-07-26T00:00:00Z"
}
```

`branch_id` في الرد للتعريف فقط؛ mutations لا تثق فيه من browser بل تربط الموقع بالفرع server-side.

## 7. Packetization تنفيذية بلا تداخل مع الشات

### CL-02A — Truth containment وإزالة الوعود الكاذبة `[High]`

**ملكية حصرية**

- `src/components/{AbandonmentRecovery,HotDealsBar,UrgencyTimer,SmartExitModal,LocalBusinessSchema}.vue`
- `src/apps/public/{Home,Packages,Rooms,Beach,Activities,Events,Restaurant,Products,About,FAQ}.vue`
- `src/config/constants.ts`
- `public/{schema.json,google-business-profile.json}`
- content keys ذات الصلة في `src/i18n/locales/*.json`

**التسليم:** إخفاء كل claim غير approved، truth inventory، لا fake countdown/coupon/review.

### CL-02B — Public contact/CRM/PII contract `[High]`

**ملكية حصرية**

- `resort-os/backend/app/modules/hub/{schemas.py,models.py}`
- `resort-os/backend/app/modules/hub/api/router.py`
- CRM fields/migration الضرورية فقط
- backend tests الجديدة
- `src/apps/public/{Booking,Contact}.vue`
- `src/composables/booking/usePageBooking.ts`
- `src/components/shared/PageBookingModal.vue`
- contact submitters خارج DigitalHub/chat بعد حصرها

**اعتماد:** CX-02C active branch/site mapping.  
**التسليم:** typed/idempotent/consented intake، no branch 1، retention/audit.

### CL-02C — Consent/privacy/analytics `[High]`

**ملكية حصرية**

- `src/main.ts`
- `src/router/index.ts`
- `src/components/CookieConsent.vue`
- `src/composables/seo/use{GoogleAnalytics,GoogleTagManager,FacebookPixel}.ts`
- wrappers المباشرة المقابلة
- `src/apps/public/Privacy.vue`
- privacy/cookie locale keys

**التسليم:** no third-party requests before consent، revoke، QR no-tracking، updated privacy.

### CL-02D — Headers/dependencies/type gate `[High]`

**ملكية حصرية**

- `nginx.spa.conf`
- `Dockerfile`
- `package.json`, `package-lock.json`
- `vite.config.ts`, `tsconfig*.json`
- CI files الجديدة

**التسليم:** headers/CSP staged، head dependency موحدة، audit/type/build clean.

### CL-02E — PWA retirement `[High]`

**ملكية حصرية**

- `public/sw.js`
- `public/manifest.json`
- `public/offline.html`
- `src/composables/pwa/useOfflineOrders.ts`
- `src/composables/useOfflineOrders.ts`
- `src/components/PWAInstallBanner.vue`

إذا احتاج retirement hook تعديل `src/main.ts` ينفذ **بعد CL-02C** في نفس lane/owner. لا يُعدل `DigitalHub.vue` حتى ACCEPTED لـ CL-01R وتحرير الملكية.

### CL-02F — SEO/prerender/routes `[Medium]`

**ملكية حصرية**

- `src/components/SEOHead.vue`
- `src/composables/seo/{useSEO,useSchema}.ts`
- `src/router/routes/public.routes.ts`
- `index.html`
- `public/{robots.txt,sitemap.xml,sitemap-enhanced.xml}`
- prerender config/tests

**اعتماد:** CL-02A لاعتماد الحقائق، وCL-02D لاختيار CSP/build stack.

### CL-02G — Public data contract وربط الغرف/الأسعار `[Medium]`

**ملكية حصرية**

- public site/bootstrap backend files الجديدة المتفق عليها
- `src/stores/{modulesStore,settingsStore,menuStore}.ts`
- `src/composables/ui/useMediaSettings.ts`
- `src/api/{menu,rooms}.ts`
- `src/apps/public/{Blog,BlogPost,Rooms}.vue` بعد تحريرها من CL-02A
- `src/App.vue`

**اعتماد:** CX-02C ثم CL-02A/CL-02B.  
**التسليم:** إزالة dead calls وbranch 1، typed site context، غرفة/سعر/offer من DB مع `as_of`.

### CL-02H — Accessibility/performance/regression suite `[Medium/Low]`

**ملكية حصرية**

- `src/apps/public/Gallery.vue`
- `src/blocks/sections/HomeGallerySlider.vue`
- shared modal/dialog primitives بعد تحرير `PageBookingModal.vue` من CL-02B
- image/font assets
- frontend test files

**التسليم:** WCAG keyboard/dialog fixes، image/bundle budgets، E2E/axe.

## 8. ترتيب متوازٍ آمن

```text
Lane A: CL-02A ───────────────> CL-02F
Lane B: CX-02C -> CL-02B ─────> CL-02G
Lane C: CL-02C ───────────────> CL-02E
Lane D: CL-02D ───────────────> CL-02H
```

قواعد الدمج:

- لا يبدأ packet في ملف يملكه packet آخر لم يُسلَّم.
- `Rooms.vue` يحرره CL-02A أولًا ثم CL-02G.
- `PageBookingModal.vue` يحرره CL-02B ثم CL-02H.
- `main.ts` يحرره CL-02C ثم retirement hook في CL-02E.
- `index.html` يملكه CL-02F؛ headers/CSP في CL-02D يجب أن يبنى allowlist بالتنسيق دون تعديل نفس الملف.
- لا packet يلمس ملفات CL-01R المستبعدة قبل handoff جديد صريح.

## 9. بوابات Go/No-Go الخاصة بالموقع

### Gate M1 — Truth

- صفر fake coupon/countdown/scarcity/review.
- كل سعر/سياسة/amenity ظاهر approved وله source و`as_of`.
- domain/contact/location موحد.

### Gate M2 — Security/privacy

- headers/CSP من الإنترنت PASS.
- consent network tests PASS.
- production audit بلا High/Moderate غير مقبول.
- public contact abuse/validation/branch/PII tests PASS.
- SW v7 retired ولا token في public offline storage.

### Gate M3 — Contract/data

- لا `/modules/public` أو `/settings/public` dead calls.
- لا `branch_id: 1`.
- room/price/offer contract typed ويطابق DB seed المعتمد.
- inquiry لا يدعي confirmation/payment/availability.

### Gate M4 — Quality

- `npm ci`, typecheck, build, tests PASS في CI.
- أربع locales smoke PASS.
- لا broken internal route/image/link.
- axe لا يحتوي critical/serious على الصفحات الأساسية.
- performance budgets متفق عليها وتُفحص آليًا.

### Gate M5 — UAT قبل DNS

- UAT على staging domain منفصل.
- اختبار mobile/desktop، Arabic RTL وEN/RU/IT، slow network، consent، contact flow، وإخفاق backend.
- موافقة مالك المحتوى على truth registry ولقطات الصفحات.

## 10. أوامر إعادة التحقق

```bash
cd /home/wego/projects/elkheima-marketing-website
npm ci
npm run type-check
npm run build
npm audit --omit=dev
npm audit
git diff --check
docker run --rm \
  -v "$PWD/nginx.spa.conf:/etc/nginx/conf.d/default.conf:ro" \
  nginx:1.27-alpine nginx -t
```

بعد وجود staging:

```bash
curl -fsSI https://STAGING_DOMAIN/
curl -fsSI https://STAGING_DOMAIN/ar/rooms
curl -fsSI https://STAGING_DOMAIN/s/INVALID_TOKEN
```

ثم تشغيل Playwright/axe/contract tests الجديدة، وفحص network قبل/بعد consent، واختبار upgrade من SW v7 بمتصفح profile قديم.

## 11. الخلاصة

الـ build ينجح، لكن هذا لا يجعل الموقع قابلًا للنشر: توجد سبع بوابات `[High]` تخص صدق العروض والبيانات، الموافقة والتتبع، PII/CRM، structured data، PWA القديم، headers، وسلسلة dependencies/typecheck. الأولوية الصحيحة هي containment للوعود غير الموثقة ثم إصلاح consent/contact/security gates بالتوازي، وبعد CX-02C يتم توحيد public site/branch contract وربط الغرف والأسعار ببيانات معتمدة. لا يُنصح بتوجيه DNS العام قبل إغلاق Gates M1–M4.
