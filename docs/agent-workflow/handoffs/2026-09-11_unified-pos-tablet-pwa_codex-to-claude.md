# Handoff إلى Claude — Unified POS Tablet PWA + QR Guest Orders

**التاريخ:** 2026-09-11  
**المنفذ/المراجع:** Codex  
**الفرع المحلي:** `feat/tablet-unified-pos-pwa` فوق `5a6036c`  
**الحالة:** تغييرات محلية مختبرة؛ لا commit ولا push ولا deploy.

## المطلوب من Claude

راجع التنفيذ كمراجع مستقل، لا تعِد اقتراح ما هو منفذ، وركّز على أي regression
في صلاحيات waiter/cashier، Redis pub/sub lifecycle، PWA installability، أو
تجربة 8.7 بوصة. القرارات الثلاثة في آخر الملف تحتاج Mohamed، لا افتراضًا.

## ما قُرئ وحُفظ قبل التعديل

- `AGENTS.md` و`CLAUDE.md` و`PROJECT_STATUS.md` و`wagdy.md` و`docs/README.md`.
- `docs/decisions/0001-qr-guest-service-mode.md` و`docs/DESIGN_SYSTEM.md`.
- قرار `dining` bounded context واحد وشاشة `UnifiedPOSView.vue` واحدة
  للكاشير والويتر؛ لا restaurant/cafe ولا شاشة waiter موازية.
- تحسينات REL-20 محفوظة: `beginNewOrder()` يفتح المنيو بلا إجبار طاولة،
  حذف/تصفير صنف يحتاج confirmation، menu/tables cache وتحديث reconnect،
  والكروت موحّدة بصريًا.

## Findings حقيقية قبل التنفيذ

1. إعداد PWA كان `standalone` مبدئيًا لكن باسم Resort OS عام، بأيقونة POS
   نصية فقط، بلا maskable/Apple icon أو orientation/start URL خاص بالـPOS أو
   install affordance واضح.
2. واجهة الطلبات النشطة ظاهرة للنادل، لكن `GET /dining/orders` كان
   cashier-only ولا يفحص `branch_id` المطلوب صراحة؛ النادل يحصل 403.
3. قاعدة البيانات تفرق طلب QR عبر `guest_session_id`، لكن `OrderRead` وجدول
   الطاولات لا يرسلان source للواجهة؛ وحدث WebSocket كان table update مبهمًا.
4. `DiningOrderDetailModal` منع إضافة أصناف عن النادل لأنه ربط الزر خطأً
   بصلاحية الخصم cashier، رغم أن endpoint نفسه waiter+.
5. طلب QR يولد `waiter_id=None` بلا آلية ذاتية لتحديد مَن استلمه؛ نقل النادل
   الحالي manager-only ليس مناسبًا للاستلام الأول.
6. الأخطر: `backend/Dockerfile` يشغل Uvicorn `--workers 4`، بينما Dining
   WebSocket manager كان process-local. HTTP POST والتابلت قد يقعان على
   workerين مختلفين، فيضيع التنبيه الحي.
7. “split bill” الحالي split tender فقط (وسائل دفع)، لا تقسيم line items أو
   شيكات منفصلة؛ تغيير المعنى ضمنيًا سيكسر accounting/refund semantics.

## التنفيذ

### PWA/Tablet

- `vite.config.ts`: manifest باسم El Kheima POS، `display:standalone`،
  `start_url:/pos/dining?source=pwa`، scope/id/lang/dir، `orientation:any`،
  shortcuts، any + maskable icons، Workbox navigation fallback مع منع `/api`.
- `index.html`: viewport safe areas، theme/application/Apple standalone meta.
- `PWAInstallButton.vue`: يمسك `beforeinstallprompt`، يظهر فقط عند أهلية
  Chromium، يختفي في standalone وبعد التثبيت؛ له unit test وi18n.
- أيقونات جديدة: `pwa-icon-192.png`، `pwa-icon-512.png`،
  `pwa-icon-maskable-512.png`، `apple-touch-icon.png`. صُنعت بأداة ImageGen
  المدمجة من هوية الخيمة/النخلة/الموج، بلا نص، ثم صُقلت maskable بخلفية
  full-bleed ومنطقة آمنة. الأصلان محفوظان خارج repo في:
  `/home/wego/.codex/generated_images/01a08e50-33e0-72e1-95e8-321ca3242516/`.
- touch/layout: command bar 48px، categories 56px، frequent 72px، product
  feedback/haptics، mobile cart 60px + safe area، overscroll containment،
  logical RTL offsets، low-height landscape layout. اختُبر 1340×800،
  894×533، 533×894.

### QR guest order end-to-end

- `DiningOrder.source` property (`guest_qr|staff`) بلا كشف `guest_session_id`.
- `OrderRead.source` و`DiningTableRead.active_order_source`، مع frontend types.
- `create_guest_order` يبث `guest_order_created` ويضم فقط id/number/type/
  staff location/items count/total. لا token ولا public reference.
- فحص idempotency قبل service يمنع إعادة بث/جرس عند replay لنفس المفتاح.
- `UnifiedPOSView`: صوت مشترك عبر `useAlertSound` + vibration + toast + بانر
  amber `aria-live=assertive` يفتح الطلب بنقرة؛ reload للطاولات والطلبات.
- active orders/table cards: guest badge/ring/filter وحالة “يحتاج مراجعة”.

### تفاعل الأدوار

- list orders أصبح `get_waiter_user` مع `assert_branch_access` صريح؛ الدفع
  ما زال cashier-only server-side وUI.
- `canAddItems` waiter+ بدل ربطه خطأً بـcashier discount permission.
- `claim_order_waiter`: row lock، يسمح unassigned→current waiter، idempotent
  لنفسه، يرفض طلب زميل أو order مقفول. endpoint branch-isolated، يعيد
  waiter name ويبث تحديثًا لكل الأجهزة. manager transfer flow لم يتغير.
- waiter name/unassigned ownership يظهر في القائمة والتفاصيل.
- الكاشير لديه زر split tender مباشر يقلل نقرة ويفتح payment modal على split؛
  النادل لا يرى settlement controls.

### WebSocket متعدد العمال

- `app/core/kernel/realtime.py`: generic `DistributedWebSocketManager`.
  sockets تبقى محلية، events تمر عبر Redis pub/sub لكل worker، listener يعيد
  الاتصال بتدرج، handshake bounded، وفشل Redis يرجع local fan-out. البيانات
  في DB تبقى source of truth.
- Dining KDS/table channels تستخدمه بدل manager المحلي.
- اختبار مستقل ينشئ managerين (كأنهما workerان) فوق FakeRedis ويثبت وصول
  الحدث للاثنين، واختبار local fallback.

## أدلة التحقق

- `bash scripts/agent-check.sh` قبل التعديل: PASS.
- Backend: `.venv/bin/pytest tests/ -q` → 100% بلا فشل؛ 3017 collected.
- Dining/QR/role suites الموسعة + claim/replay tests: PASS.
- Ruff على كود backend المتغير: PASS.
- Frontend `vue-tsc --noEmit`: PASS.
- i18n: ar/en parity، 6675 key لكل لغة: PASS.
- Vitest بدون الحارس غير المتعلق: 104/104 PASS؛ اختبار PWA install منفرد PASS.
- Playwright mock responsive: 14/14 PASS، ويتضمن device geometry، live
  multisensory event، cashier split، وwaiter permission boundary.
- Production build: PASS؛ ولّد `dist/sw.js` و`manifest.webmanifest`.
- المانع الوحيد في suite الفرونت الكامل: `themeContrast.spec.ts` يشير فقط
  إلى `src/components/hr/RotaTab.vue` غير المعدّل والمطابق للـbase؛ ليس من
  هذه الدفعة. لم يتم توسيع النطاق لإصلاح HR.

## قرارات تحتاج Mohamed

1. **Split حقيقي:** هل المطلوب split tender الحالي، أم checks مستقلة؟ لو
   مستقلة: التقسيم بالمقعد، بالصنف، أم كمية جزئية من السطر؟ هذا يغير domain
   model والترحيل والمرتجعات وKDS، فلا يُفترض.
2. **Orientation:** أبقينا `any` لأن جهاز الكاشير المثبت landscape وجهاز
   الويتر المحمول portrait كلاهما لنفس التطبيق. لو المطلوب قفل landscape
   للكاشير فقط، الأنسب MDM/device profile أو runtime role-specific lock، لا
   manifest lock عالمي.
3. **Cold-start offline auth:** الـPWA وأوامر POS الحالية تتحمل الانقطاع بعد
   فتح الجلسة، لكن فتح التطبيق من إغلاق كامل يحتاج الشبكة لتجديد refresh
   session. offline PIN/credential cache قرار أمني مستقل ولا ينبغي إضافته
   ضمن تحسين واجهة بلا موافقة.

## لا تخلط بين “منفذ” و“منشور”

الفرع المحلي dirty عمدًا بهذه الحزمة. لا يوجد commit hash جديد، ولا migration،
ولا تغيير بيانات، ولا VPS operation. أي نشر يحتاج runbook/backup/rollback/
health evidence منفصلة.
