# Handoff — Cashier/Waiter Smart Polish

**التاريخ:** 2026-09-11
**المنفذ والمراجع:** Codex
**المستودع:** `/home/wego/projects/resort-os`
**الفرع:** `feat/tablet-unified-pos-pwa`
**HEAD قبل الدفعة:** `068e6e6`
**الحالة:** تغييرات محلية مختبرة؛ لا commit ولا push ولا deploy.

## النتيجة

أُغلقت أربع فجوات يومية في شاشة `UnifiedPOSView` المشتركة للكاشير والويتر
من دون إنشاء شاشة موازية أو تغيير صلاحيات الـBackend:

1. **حماية draft من الضياع:** مغادرة route والسلة فيها أصناف تفتح confirmation
   واضحًا. اختيار المغادرة يمسح draft ويلغي الطلب المرحلي على السيرفر أولًا؛
   فشل الإلغاء يمنع التنقل. reload/إغلاق المتصفح يمر عبر `beforeunload`.
   logout لا يُحبس بعد أن تكون الجلسة مُسحت.
2. **عداد كمية صحيح:** badge «طلب جديد» وزر السلة المحمول يجمعان
   `line.quantity` بدل `cart.length`؛ سطر واحد بكمية 2 يعرض 2.
3. **فرز تشغيل ذكي:** `POSActiveOrdersWorkspace` يستقبل هوية المستخدم وقدرته
   على التحصيل. «الأولوية الآن» تشمل QR مفتوحًا بلا نادل للجميع، `served`
   للكاشير، وأي طلب عمره 45 دقيقة للجميع. «طلباتي» يعتمد `waiter_id`، والقائمة
   ترتب الأولوية ثم طلبات المستخدم ثم الأقدم. بانر قابل للضغط يشرح الأولوية
   بصياغة مختلفة للكاشير والويتر، وكارت الأولوية يحمل badge واضحًا.
4. **خصوصية cache الأوفلاين:** المفاتيح أصبحت
   `pos:dining:cache:v2:{userId}:...`. عند mount تُحذف مفاتيح v1 التي يمكن أن
   تحتوي هوية ضيف. نسخة الطاولات المحفوظة تصفّر
   `active_order_guest_name/phone`، بينما العرض online لا يفقد البيانات.

أُضيف `workbox-window` إلى `apps/el-kheima` كاعتماد مباشر. كان موجودًا في
الـlock/virtual store كـpeer عابر فقط، لذلك فشل production build من worktree
نظيف في resolve الاستيراد الافتراضي لـ`vite-plugin-pwa`. بعد الإضافة صار
الربط قابلًا لإعادة الإنتاج ونجح build.

## الملفات المتغيرة

- `frontend/apps/el-kheima/src/views/pos/UnifiedPOSView.vue`
- `frontend/apps/el-kheima/src/components/dining-pos/POSActiveOrdersWorkspace.vue`
- `frontend/apps/el-kheima/e2e/mock-responsive.spec.ts`
- `frontend/apps/el-kheima/package.json`
- `frontend/pnpm-lock.yaml`
- `frontend/packages/core/src/i18n/locales/ar.json`
- `frontend/packages/core/src/i18n/locales/en.json`
- `wagdy.md`
- `PROJECT_STATUS.md`
- `docs/agent-workflow/EL_KHEIMA_EXECUTION_BOARD.md`
- هذا الملف.

## أدلة التحقق

- `pnpm --filter el-kheima type-check` — PASS.
- `pnpm --filter el-kheima test:frontend` — 17 files، **108/108 PASS**.
- i18n validation — العربية/الإنجليزية **6696 key لكل لغة**، صفر نقص أو
  placeholder.
- `pnpm --filter el-kheima test:e2e:mock` — **16/16 PASS**، ويشمل:
  - landscape الفعلي والمنطقي وportrait للتابلت؛
  - حدود صلاحيات cashier/waiter؛
  - priority/mine filters والبانر role-aware؛
  - كمية 2 في السلة؛
  - منع المغادرة ثم السماح بها بعد تأكيد صريح؛
  - إزالة cache القديم، user-scoped key، وعدم حفظ اسم/هاتف الضيف.
- `VITE_PUBLIC_SITE_URL=https://elkheima.com pnpm --filter el-kheima build`
  — PASS؛ 1171 module، وُلد `dist/sw.js` و`manifest.webmanifest`.
- `git diff --check` — PASS قبل التوثيق، ويعاد ضمن الإغلاق النهائي.

رسائل `ECONNREFUSED 127.0.0.1:8005` في سجل mock E2E تخص WebSocket proxy
غير المموك في اختبار layout؛ الاختبارات تموّك REST وبعضها يمّوك WebSocket
نفسه، والـ16 كلها اجتازت. ليست فشلًا في التنفيذ.

## حدود وتكملة التشغيل

- لا Backend أو Alembic migration أو بيانات تغيرت.
- لم يتغير معنى split tender إلى split checks؛ ما زال قرار منتج مستقلًا.
- لم يتغير orientation العام؛ التطبيق يخدم cashier landscape وwaiter
  portrait.
- لا ادعاء نشر: يلزم device UAT على جهاز التشغيل الحقيقي ثم تفويض منفصل
  للـcommit/push/deploy مع backup/rollback/health evidence.
- حزمة fractional-owner والوصفات/المخزون موجودة في worktree منفصل؛ لا تخلط
  تغييراتها بهذه الدفعة عند المراجعة أو الدمج.
