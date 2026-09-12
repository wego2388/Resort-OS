# Handoff — POS Tablet/PWA Closure + Post-payment QR Rating

**التاريخ:** 2026-09-12
**المنفذ والمراجع:** Codex
**الحالة:** تغييرات محلية مختبرة؛ لا commit ولا push ولا deploy.

## أماكن العمل

1. Resort OS: `/home/wego/projects/resort-os`
   branch: `feat/tablet-unified-pos-pwa`، base HEAD: `068e6e6`.
2. Marketing guest UI: `/home/wego/projects/elkheima-marketing-guest-review`
   branch: `feat/guest-review-after-payment`، base HEAD: `7275e51`.

لا تخلط هذه التغييرات مع worktree الملكية الجزئية
`/home/wego/projects/resort-os-fractional-owner`.

## النتيجة التشغيلية

### 1. تقييم الضيف بعد الدفع

- `GET /dining/public/orders/{public_reference}` ما زال يتطلب
  `X-Guest-Session` ويعيد الآن أيضًا `review_submitted` و`review_rating`
  و`google_review_url` عند الاستحقاق.
- `POST /dining/public/orders/{public_reference}/review` يقبل `{rating:
  1..5, comment?}` فقط إذا كان الطلب `paid` ويخص نفس جلسة الضيف. لا يثق
  باسم/فرع من العميل؛ يأخذهما من الجلسة والطلب.
- التقييم واحد لكل جلسة QR، وليس لكل ضغطة أو لكل طلب فرعي. migration
  `d2e4f6a8c0b1` أضافت `dining_order_id` و`guest_session_id` إلى
  `guest_reviews` مع FKs وpartial unique indexes. retry متزامن أو refresh
  يرجع السجل الأصلي ولا يغيّر النجوم المثبتة.
- كل تقييم يُحفظ داخليًا في Analytics بالمصدر `dining_qr`. تقييم 1–2
  ينشئ CRM complaint بالطريق الحالي. رابط Google لا يرجع إلا إذا كانت
  القيمة المثبتة 4 أو 5:
  `https://g.page/r/CelR6rfY5VCeEAI/review`.
- المسار الديناميكي العام عليه rate limit فعلي 20/60 ثانية، مع اختبار HTTP
  يثبت أن الطلب 21 يرجع 429.

### 2. تجربة QR العامة

- مكوّن `PaidOrderRating.vue` مشترك بين `QrOrder.vue` و`DigitalHub.vue`:
  5 أزرار لمس 48px، تعليق اختياري، feedback واضح، «بعد قليل» مع زر عائم
  لإعادة الفتح، واستعادة شاشة الشكر بعد refresh لو ضاع رد الشبكة.
- polling كان يتوقف خطأ عند `served` في `QrOrder`، وكان Digital Hub يتابع
  آخر طلب فقط ويتوقف عند حالات لا يرسلها Backend (`completed`). الآن
  يستمران حتى `paid/cancelled/refunded`، والـHub يحفظ كل طلبات الجلسة
  ويتابعها كلها.
- `HubCart` يعرض الحالات الحقيقية (`open/in_kitchen/served/paid/...`)،
  رقم الطلب بدل المرجع العشوائي حين يتوفر، وله زر إغلاق واضح وأزرار كمية
  40px بدل 28px.
- النصوص مكتملة بالعربية والإنجليزية والروسية والإيطالية. رابط Google
  القديم في `chatbotPlatforms.ts` استُبدل بالرابط المعتمد.

### 3. الكاشير/الويتر على Lenovo وPWA

- `GET /pins/operators` waiter+ يعيد فقط waiter/cashier/supervisor/manager
  النشطين أصحاب عضوية نشطة في الفرع الحالي وPIN، ويستبعد المستخدم الحالي.
  مودال التبديل لم يعد يعتمد endpoint cashier-only.
- حارس المسودة يغطي route leave وlogout وoperator switch، وأصبح يغطي أيضًا
  PWA app update. زر «تحديث الآن» لا يستطيع reload وإسقاط سلة غير مرسلة.
- logout ينتظر `auth.logout()` بدل تشغيل router push متوازٍ، وتبديل المشغل
  لا ينسب draft قديمًا للمستخدم الجديد.
- أزرار إغلاق الـModal، العملات، التقسيم، refresh/credit lookup والتحصيل
  صارت 44px على الأقل حيث تستخدم في POS. أضيف منع text selection غير
  المقصود وmomentum scrolling لمناطق POS اللمسية.
- Playwright يقيس نافذة التحصيل داخل viewport وأهداف اللمس في Lenovo
  894×533 أفقي و800×1280 رأسي، بالإضافة إلى 1340×800 و533×894 الموجودة.

## الملفات الأساسية

### Resort OS

- `backend/alembic/versions/d2e4f6a8c0b1_add_dining_order_guest_reviews.py`
- `backend/app/modules/analytics/models.py`
- `backend/app/modules/analytics/services.py`
- `backend/app/modules/dining/api/router.py`
- `backend/app/modules/dining/schemas.py`
- `backend/app/core/rate_limit.py`
- `backend/tests/test_api/test_public_menu.py`
- `backend/tests/test_api/test_auth_security_http.py`
- `backend/app/modules/core/_services/pins.py`
- `backend/app/modules/core/api/router.py`
- `frontend/apps/el-kheima/src/composables/operationalDraftGuard.ts`
- `frontend/apps/el-kheima/src/views/pos/UnifiedPOSView.vue`
- `frontend/apps/el-kheima/src/layouts/FieldLayout.vue`
- `frontend/apps/el-kheima/src/components/OperatorSwitchModal.vue`
- `frontend/apps/el-kheima/src/components/PWAUpdateBanner.vue`
- `frontend/apps/el-kheima/src/components/dining-pos/POSActiveOrdersWorkspace.vue`
- `frontend/apps/el-kheima/src/components/dining-pos/POSPaymentModal.vue`
- `frontend/apps/el-kheima/src/components/dining-pos/POSCartPanel.vue`
- `frontend/packages/ui/src/components/Modal.vue`
- `frontend/apps/el-kheima/e2e/mock-responsive.spec.ts`
- `frontend/apps/el-kheima/src/__tests__/components/PWAUpdateBanner.spec.ts`
- `frontend/packages/core/src/api/endpoints.ts`
- `frontend/packages/core/src/i18n/locales/{ar,en}.json`
- `frontend/apps/el-kheima/package.json` + `frontend/pnpm-lock.yaml`

### Marketing

- `src/components/guest/PaidOrderRating.vue`
- `src/apps/ops/QrOrder.vue`
- `src/apps/public/DigitalHub.vue`
- `src/components/hub/HubCart.vue`
- `src/i18n/locales/{ar,en,ru,it}.json`
- `src/data/chatbotPlatforms.ts`
- `package-lock.json` (`nanoid` transitive safe patch).

## أدلة التحقق

- Alembic head: `d2e4f6a8c0b1`.
- disposable PostgreSQL upgrade/downgrade chain: **3/3 PASS**.
- `test_public_menu.py + test_analytics_http.py +
  test_analytics_endpoints_http.py`: **80/80 PASS**.
- rate-limit tests الجديدة/المرتبطة: **3/3 PASS**.
- Backend الكامل: **3035 collected**، وصل 100% بـexit 0 دون أي failure.
- Staff frontend: type-check PASS؛ i18n **6705/6705**؛ Vitest
  **108/108 PASS**؛ production build PASS (1172 modules، `sw.js` وmanifest).
- Staff Playwright mock responsive: **19/19 PASS**.
- Marketing: public-truth PASS؛ type-check PASS؛ production build PASS؛
  `npm audit --omit=dev` = **0 vulnerabilities**.
- `git diff --check`: PASS بعد آخر تحديث توثيق قبل إنشاء release commit.

رسائل WebSocket proxy `ECONNREFUSED 127.0.0.1:8005` أثناء mock E2E متوقعة:
الاختبار يمّوك REST والـWebSocket المطلوب، ولا يشغّل Backend حقيقيًا؛ كل
الرحلات اجتازت.

## ما لم يحدث وما يلزم قبل الإنتاج

- لا commit/push/deploy ولا migration على قاعدة الإنتاج.
- حالة Gate العامة لم تتغير، لذلك لم يُعدّل Final Execution Plan.
- يلزم device UAT على تابلت فعلي، وتجربة `served → paid → rating` من QR
  طاولة وغرفة وبأكثر من لغة، ثم تفويض منفصل لدمج/نشر المستودعين مع backup
  وrollback وhealth evidence.
