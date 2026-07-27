# CL-02A + CL-02D — Codex handoff

**التاريخ:** 2026-07-26  
**الحالة:** `READY_FOR_REVIEW` للجزأين CL-02A وCL-02D فقط.  
**بوابة النشر العامة:** ما زالت `NO-GO` حتى إغلاق CL-02B (public contact/CRM/PII) وCL-02C (consent/analytics) واعتماد بيانات الحقيقة.  
**المشروع المنفذ عليه:** `/home/wego/projects/elkheima-marketing-website`  
**التسليم:** لا commit، لا push، لا deploy.

## 1. النطاق وحدود الملكية

نُفذ:

- CL-02A: truth containment للمحتوى العام غير المعتمد.
- CL-02D: dependency/typecheck runner، security headers/CSP داخل container، retirement للـservice worker القديم، وإصلاح/تنظيف الأصول الواضحة.

استُبعد عمدًا:

- `src/components/chatbot/**`
- `src/composables/booking/useChatbot*.ts`
- منطق `src/api/client.ts` و`src/apps/public/DigitalHub.vue`
- `Contact.vue` وعقد contact/CRM/PII والـbackend الخاص به
- منطق cookie consent وGA/GTM/Meta

التغييرات الموجودة في الملفات المستبعدة تخص أعمال agents أخرى ولم ألمسها أو أنسبها لهذا packet.

## 2. ما تم تنفيذه

### أ. Truth containment fail-closed

- أُضيف سجل مركزي في `src/config/publicTruth.ts`.
- كل الفئات غير المعتمدة تبدأ `false`: amenities، exact location، history، numeric stats، packages، prices، promotions، ratings، scarcity، وstructured business data.
- أُضيف `PublicAvailabilityNotice.vue` بنص واضح: الأسعار والتوفر والخدمات النهائية تؤكد مع الفريق قبل الطلب.
- عُطلت الأقسام غير الموثقة في:
  - Home
  - About
  - Beach
  - Activities
  - Rooms
  - Events
  - Packages
  - Restaurant
  - FAQ
- عُدلت عناوين ووصف SEO والـhero copy والـProducts copy إلى صياغة محافظة لا تعد بسعر أو توفر أو amenity.
- أصلح default title/description/keywords وOpen Graph في `index.html`.
- أُزيل TripAdvisor tracker من `index.html`.

لا يجب تحويل أي gate إلى `true` إلا بعد وجود سجل حقيقة مع source/owner/approval/date/validity في مسار استيراد البيانات المعتمد.

### ب. إزالة claims الوهمية

أزيلت مكونات العرض نهائيًا بعد إزالة mounts/imports:

- `AbandonmentRecovery.vue`
- `HotDealsBar.vue`
- `UrgencyTimer.vue`
- `SmartExitModal.vue`
- `TripAdvisorWidget.vue`
- `LocalBusinessSchema.vue`

وأزيلت public artifacts غير الصالحة للإنتاج:

- `public/schema.json`
- `public/google-business-profile.json`
- `public/dark-mode-test.html`

بالتالي لم يعد `SAVE10`/`DIRECT10` أو countdown/scarcity/fake review/schema جزءًا من مسار الموقع.

### ج. Service worker

- استبدل `public/sw.js` القديم retirement worker صغير.
- النسخة الجديدة تحذف caches وقاعدة `elkheima-offline` القديمة، ثم تلغي تسجيل نفسها وتعيد تحميل clients.
- أزيلت منها queues التي كانت تخزن bearer tokens، gate sales sync، API caches القديمة، push navigation، ووعد offline sync غير القابل للتنفيذ.
- لا يوجد تسجيل service worker جديد في التطبيق.

### د. Dependencies وtypecheck

- أزيلت `@vueuse/head` وdirect `unhead`.
- وُحدت head API على `@unhead/vue` و`@unhead/vue/client`.
- ثُبتت الإصدارات:
  - `@unhead/vue@3.2.3`
  - `vite@6.4.3`
  - `vue-tsc@3.3.8`
- أضيف Vite client types وأصلحت أخطاء typecheck المكتشفة في:
  - `LanguageSelector.vue`
  - `common/Toast.vue`
  - `stores/menuStore.ts`
  - `composables/seo/useSchema.ts`
- أضيفت scripts:
  - `validate:truth`
  - `type-check`
  - `audit:prod`
  - `validate`

### هـ. Headers/CSP

أضيفت إلى `nginx.spa.conf` على HTML/static responses:

- enforced Content-Security-Policy
- `frame-ancestors 'none'`
- `object-src 'none'`
- `base-uri 'self'`
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy`
- COOP وCORP
- `client_max_body_size 1m`

الـallowlist تشمل فقط المصادر المستخدمة حاليًا للموقع/الخطوط/analytics وUnsplash/Open-Meteo. HSTS متروك عمدًا للـTLS edge الخارجي بعد تثبيت كل subdomains.

### و. الأصول والحجم

- أصلحت مرجعي `/images/rooms/beach-view-01.webp` المكسورين إلى `room-09.webp`.
- استبدلت خلفية Unsplash في Beach بأصل محلي.
- أزيلت locale backup files التي كانت تتحول إلى chunks بلا داعٍ.
- أزيلت صور public كبيرة/قديمة غير referenced، ومنها `public/images/logo.png` بحجم 1.8 MiB.
- حجم `public/` الحالي: `44.42 MiB`.
- static reference scan يغطي 181 ملف source ويمر بلا مرجع `/images` أو `/icons` مفقود.

## 3. Validation evidence

| الفحص | النتيجة |
|---|---|
| `npm run validate:truth` | PASS |
| `npm run type-check` | PASS |
| `npm run build` | PASS — Vite 6.4.3، 2040 modules |
| `npm audit --omit=dev` | PASS — 0 vulnerabilities |
| `npm audit` | PASS — 0 vulnerabilities |
| `git diff --check` | PASS |
| static public asset scan | PASS — 181 source files |
| `nginx:1.27-alpine nginx -t` | PASS |
| runtime `curl -I` على `/` وSPA fallback وstatic asset | PASS؛ headers ظاهرة على الثلاثة |
| headless Chrome smoke | PASS على `/`, `/beach`, `/activities`, `/rooms`, `/events`, `/packages`, `/restaurant`, `/faq`, `/products` |

ملاحظة build غير حاجبة: `ar.json` مستورد static وdynamic معًا، لذلك لا ينتقل إلى chunk منفصل. بقية backup locale chunks أزيلت.

## 4. Findings/قيود متبقية

1. **CL-02B وCL-02C ما زالا بوابتي نشر High.** هذا packet لم يغير PII/CRM أو analytics consent.
2. exact address/coordinates/domain aliases/email/social profiles لا تزال تحتاج اعتماد مالك موحد قبل تفعيل schema أو map claims.
3. المحتوى غير المعتمد ما زال موجودًا داخل بعض templates/i18n خلف gates مغلقة كي لا يتحول هذا packet إلى إعادة تصميم ضخمة؛ validator يمنع فتح الفئات بالخطأ. بعد وصول بيانات معتمدة، الأفضل استبداله بمحتوى مولد من registry/DB ثم حذف النصوص القديمة.
4. CSP داخل container ليست بديلًا عن headers على Hostinger TLS edge. يجب إعادة `curl -I` من الإنترنت بعد النشر التجريبي.
5. لم يتم UAT لخدمات API الحية لأن CL-02B/C وbranch bootstrap ما زالت تعمل في packets أخرى.

## 5. خطوات المراجع

1. راجع diff مع استبعاد ملفات agents الأخرى المذكورة في قسم الملكية.
2. شغّل:

```bash
cd /home/wego/projects/elkheima-marketing-website
npm ci --ignore-scripts
npm run validate
npm audit
docker run --rm \
  -v "$PWD/nginx.spa.conf:/etc/nginx/conf.d/default.conf:ro" \
  -v "$PWD/dist:/usr/share/nginx/html:ro" \
  nginx:1.27-alpine nginx -t
```

3. لا تُقبل CL-02 بالكامل ولا يبدأ public deploy قبل دمج ومراجعة CL-02B وCL-02C وtruth data approval.
