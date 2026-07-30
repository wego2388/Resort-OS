# الخطة التنفيذية النهائية الحية — El Kheima Resort OS

**آخر تحديث مثبت:** 2026-07-30 بعد نشر Timeshare وإصدار Marketing الجديد
**المالك:** Mohamed
**قائد التنفيذ والمراجع النهائي:** Codex
**الحالة:** النشر والبيانات وChatbot وDNS ومسار الحسابات مكتملة؛ الحسابات
الحقيقية وUAT قبل Go/No-Go

## 1. القرارات السارية

1. الخيمة تعمل بفرع تشغيلي واحد فقط؛ لا Branch Switcher ظاهر.
2. عضوية الفرع والصلاحيات والطابور غير المتصل تظل fail-closed.
3. الموقع الرسمي هو `https://elkheima.com` و`www`، وتطبيق الموظفين هو
   `https://app.elkheima.com`.
4. DNS cutover أُجيز صراحةً في 30 يوليو 2026 واكتمل. أي تعديل DNS جديد
   يحتاج نطاقًا واضحًا ونقطة تراجع؛ لا Reset DNS ولا AAAA دون IPv6 فعلي.
5. مصدر الإنتاج Resort OS هو release immutable `679f76e`، ومصدر الموقع
   التسويقي المستقل هو `16f8f2c`.
6. لا `git pull` أو reset أو تنظيف أو rebuild فوق مجلدات المصدر القديمة.
7. لا أسرار في Git أو logs أو handoffs؛ أسرار Compose تُشتق في الذاكرة.
8. البيانات synthetic لا تُضاف إلا عبر importer المحكوم
   `production_demo_seed`؛ البيانات الحقيقية تحتاج اعتماد المالك والتشغيل.
9. كل نشر يحتاج backup وrollback وhealth evidence وsource digest.
10. أي تعليمات تحت `docs/archive/` تاريخية وممنوع تنفيذها.
11. `scripts/wait-dns-then-switch.sh` ملف مستخدم خارج التشغيل؛ لا يُعدّل
    أو يُشغّل.

## 2. خط الأساس المثبت

### الكود

- branch: `claude/CX-02C-frontend-auth-bootstrap`.
- Resort source release: `679f76e`، مدفوع على فرع العمل.
- Marketing source release: `16f8f2c`، مدفوع على `main` في مستودعه المستقل.
- `origin/main` في Resort OS بقي عند `598938e`.
- Alembic single head: `88d1c505a9dc`.
- full backend: 2181 passed و40 skipped من 2221 collected، صفر failure.
- onboarding/HR/auth focused backend: 228 passed و1 skipped؛ frontend:
  95/95.
- Resort `agent-check` وtype-check/build وdiff-check: ناجحة.
- Marketing truth/type-check/build: ناجحة.

### الإنتاج

- SSH بالمفتاح كمستخدم `resortos` مع sudo وDocker.
- root login وpassword auth مغلقان؛ UFW وFail2ban والـloopback bindings
  لم تُضعف.
- `/opt/resort-os-current -> /opt/resort-os-releases/679f76e`.
- `/opt/elkheima-marketing-current ->
  /opt/elkheima-marketing-releases/16f8f2c`.
- Backend وCelery وتطبيق الموظفين والـedge تستخدم release `679f76e`.
  Marketing يستخدم مصدره المستقل `16f8f2c`.
- الحاويات الثماني `restarts=0`، وكل healthchecks المعرّفة سليمة.
- 8 حاويات تعمل؛ الخدمات ذات healthcheck سليمة.
- PostgreSQL وRedis لم يُعاد إنشاؤهما أثناء النشر.
- المنافذ العامة 80/443؛ 8443 القديم غير منشور.
- backup/health/certbot timers مثبتة ومفعلة.
- البيانات التجريبية الواقعية منشورة، وChatbot اجتاز E2E من الدومين.
- DNS العام والنطاقات الثلاثة وTLS وHTTP redirects اجتازت الفحص.

## 3. حالة البوابات

| Gate | الحالة | شرط الإغلاق |
|---|---|---|
| Gate 0 — baseline | COMPLETE | الأدلة الحالية خضراء |
| Gate 1 — auth/permissions/branch | DEPLOYED — UAT PENDING | قبول الأدوار على جهاز فعلي |
| Gate 2 — QR/PWA/public | PARTIAL | device UAT والعقد العام النهائي |
| Gate 3 — chat/consent/truth | ACTIVE + LIVE VERIFIED | مراجعة دورية للحقائق والـprovider |
| Gate 4 — content/SEO | TECHNICAL COMPLETE | اعتماد بيانات المالك الحقيقية |
| Gate 5A — synthetic demo data | COMPLETE | importer idempotent + safety counts |
| Gate 5B — real master data | PENDING REVIEW | اعتماد التشغيل والمالية |
| Gate 6 — VPS hardening | COMPLETE + VERIFIED | مراجعة دورية فقط |
| Gate 7 — deploy/backup/monitoring | BASELINE COMPLETE | external alert channel وburn-in |
| Gate 8 — TLS/domain | COMPLETE | تجديد ومراقبة دوريان |
| Gate 9 — cutover | COMPLETE | مراقبة + UAT تشغيلي |
| Gate 10 — operating/training docs | COMPLETE | إعادة مراجعة عند تغير workflow أو role |

## 4. الحزم المنتهية

### P0-01 — حفظ ومصالحة exact source

**الحالة:** COMPLETE

- حُفظ manifest وGit bundle وbinary patch وuntracked tar وDocker metadata
  للمصدر القديم قبل النشر.
- أُعيد تركيب المصدر byte-for-byte وثبت عدم وجود source مجهول.
- مجلدا المصدر القديمان على VPS محفوظان وغير مستخدمين كمصدر للنشر.

### P0-02 — نقطة تراجع خارج الخادم

**الحالة:** COMPLETE

- نسخة DB مشفرة خارج VPS مع SHA مطابق.
- restore معزول كامل نجح إلى 135 جدولًا ثم نُظفت قاعدة الاختبار.
- local daily backup مستمر؛ provider snapshot الدوري تحسين دفاعي متبقٍ.

### P0-03 — الكود والبيانات التجريبية

**الحالة:** COMPLETE

- frontend auth/bootstrap/permissions/route gates وsingle-branch UX مكتملة.
- importer الإنتاجي dry-run افتراضي، confirmation حرفي، advisory lock،
  marker، وidempotency.
- نُشرت بيانات المخزون والموردين والمطعم والغرف والصيانة وCRM وtimeshare
  وlease وbeach وHub دون مستخدمين أو حجوزات أو مدفوعات أو رواتب تجريبية.
- safety counts قبل/بعد متطابقة، وsecond apply أعاد `added={}`.

### P0-04 — النشر وChatbot

**الحالة:** COMPLETE

- نُشرت الخدمات تدريجيًا من releases immutable مع DB backup وrollback tags.
- Chatbot فعال، وخريطة المواقع العامة مقصورة على الجذر و`www`.
- E2E حي: welcome + session + disclosure + رد Gemini عربي + end.

### P0-05 — DNS وTLS

**الحالة:** COMPLETE — 2026-07-30

- حُفظت صور التطبيق وDB وإعدادات الشهادة السابقة قبل التغيير.
- أضيف edge للدومينات مع HSTS canary وإعادة تحميل آمنة.
- تغير `A @` و`A app` فقط إلى `191.218.161.133`، وبقي
  `www CNAME -> elkheima.com`.
- Hostinger snapshot `167902017` يحفظ حالة DNS السابقة.
- شهادة SAN صالحة حتى `2026-10-28 02:21:34 UTC`، وتجديد dry-run ناجح.
- authoritative DNS وثلاثة public resolvers أعادوا عنوان VPS.
- الجذر و`www` و`app` = 200، وHTTP→HTTPS صحيح.
- أزيلت مراجع IP القديمة من Marketing bundle وSEO files.
- خدمات Resort التي شملها القطع موحدة على `679f76e`؛ Marketing source
  عند `16f8f2c`.

### P0-06 — دليل الإدارة وتدريب الموظفين

**الحالة:** COMPLETE

- `docs/STAFF_APP_GUIDE_AR.md` هو المرجع العربي لتدريب الأقسام: الدخول
  والحسابات والأدوار والصلاحيات، PMS وDining وBeach، المالية والتكلفة،
  المخزون والموردون، HR، التايم شير، CRM وخدمة العملاء والصيانة.
- يتضمن فصل المسؤوليات، قوائم فتح/إغلاق اليوم، معالجة المشاكل، سيناريوهات
  UAT، ونموذج اعتماد الموظف.
- `docs/SUPER_ADMIN_GUIDE_AR.md` هو المرجع الأمني المكمل لإدارة الحسابات
  و2FA وStep-Up والطوارئ.

### P0-07 — مسار الموظفين ومركز السوبر أدمن

**الحالة:** DEPLOYED — ACCOUNTS PENDING ROSTER

- HR ينشئ سجل الموظف في الفرع الفعال ولا يستطيع تمرير `user_id` أو إنشاء
  حساب دخول ضمنيًا.
- السوبر أدمن يختار الموظف من مركز موحد، يحدد الدور، ثم ينشئ الحساب تحت
  Step-Up. الخدمة تربط الحساب بسجل HR وتضيف عضوية الفرع الافتراضية وتكتب
  Audit داخل العملية نفسها.
- المحاسب وبقية الموظفين حسابات عادية من الواجهة بعد إنشاء سجل HR. حساب
  `super_admin` احتياطي فقط هو الذي يُنشأ من الطرفية عبر bootstrap موثق.
- عزل الفروع fail-closed. الربط اليدوي القديم أصبح استعادة للسوبر أدمن فقط
  ولا يقبل حسابًا بلا عضوية فعالة في الفرع نفسه.
- شاشتا المستخدمين والصلاحيات القديمتان تحولان إلى مركز الإدارة الموحد،
  والقائمة الجانبية منظمة حسب مجالات العمل مع تحسين الهاتف.
- إنتاجيًا ما زالت الحالة الآمنة: مستخدم واحد `super_admin`، فرع واحد،
  عضوية فعالة واحدة، وصفر سجلات/حسابات موظفين.

### P0-08 — UAT وGo/No-Go

**الحالة:** PENDING

- جهاز وهاتف حقيقيان، عربي/إنجليزي، QR، انقطاع شبكة، logout/login.
- استقبال/غرف/housekeeping/night audit/POS/guest alerts حسب الأدوار.
- مراجعة بيانات العرض واستبدال المطلوب ببيانات master معتمدة.
- فترة burn-in مع توصيل alerts لقناة خارجية.
- اعتماد ممثل التشغيل والمالية والمالك، ثم قرار Go/No-Go مؤرخ.

### P0-09 — Timeshare وMarketing multilingual

**الحالة:** COMPLETE — 2026-07-30

- صفحة `/timeshare` منشورة بأربع لغات وترسل الطلب إلى عقد
  `/api/v1/hub/contact` الآمن مع consent وidempotency.
- Blue Bay موثقة على الصفحة كجهة إدارة الملكية الجزئية وفق نموذج الحجز
  الداخلي الذي قدمه المالك.
- لا أسعار منشورة؛ `publicTruth.publish.prices=false` لم يتغير.
- وعود الملكية والتوريث والتوفر والرد خلال 24 ساعة أزيلت من النسخة العامة؛
  الفريق يؤكد التكلفة والتوفر والشروط بعد الاستفسار.
- exact location section يبقى خلف `publicTruth.publish.exactLocation=false`.
- ترجمات العربية والإنجليزية والروسية والإيطالية متطابقة عند 2919 مفتاحًا.
- Marketing release `16f8f2c` نُشر بعد build canary وDB backup وrollback
  image، واجتاز الدومين والـhealth gate.

## 5. العمل الحالي بالترتيب

### P1-UAT

1. اعتماد roster الحسابات: الاسم والبريد والدور والمدير. ينشئ HR سجل
   الموظف أولًا، ثم ينشئ السوبر أدمن حسابه من الواجهة. إنشاء
   `super_admin` احتياطي يتم عبر bootstrap التقني فقط بعد تسمية مالكه.
2. توزيع `docs/STAFF_APP_GUIDE_AR.md` على رؤساء الأقسام وتنفيذ مصفوفة
   device/role/language/workflow وسيناريوهات الاعتماد الموجودة فيه.
3. تسجيل defects مع severity وowner ونتيجة retest.
4. اختبار QR والطباعة والعمل عند انقطاع الشبكة.

### P1-DATA

1. مراجعة synthetic data بواسطة التشغيل والمالية.
2. إعداد ملفات master data الحقيقية، ثم dry-run وvalidation.
3. تطبيق دفعات صغيرة مع audit وrollback لكل دفعة.

### P1-OPS

1. اختيار قناة خارجية لتنبيهات health gate.
2. مراقبة DNS/TLS/HTTP/containers/backup/disk خلال burn-in.
3. إنشاء provider snapshot دوري إن كان متاحًا، دون اعتباره بديلًا لنسخة DB.

## 6. قواعد التراجع

- DNS rollback يستخدم snapshot `167902017` فقط بعد إثبات عطل يستوجب الرجوع.
- application rollback يستخدم وسوم `resort-os-rollback/*` المسجلة للحزمة.
- لا restore لقاعدة البيانات عند rollback تطبيقي متوافق.
- لا حذف schema أو تصغير أعمدة encryption.
- لا `git reset --hard` أو تنظيف مجلدات المصدر كوسيلة rollback.
- بعد أي rollback تُعاد اختبارات DNS وTLS وHTTP وDB وRedis والحاويات
  والسجلات.

## 7. الأدلة الحالية

- حالة المشروع: `PROJECT_STATUS.md`
- ملخص المالك: `wagdy.md`
- لوحة التنفيذ: `docs/agent-workflow/EL_KHEIMA_EXECUTION_BOARD.md`
- تسليم النشر والـDNS:
  `docs/agent-workflow/handoffs/2026-07-30_DNS-01_codex_handoff.md`
- تسليم مسار الموظفين والإصدار الحالي:
  `docs/agent-workflow/handoffs/2026-07-30_ACC-01_REL-04_codex_handoff.md`
- تسليم Marketing وTimeshare:
  `docs/agent-workflow/handoffs/2026-07-30_MKT-02_codex_handoff.md`
- تسليم البيانات وChatbot:
  `docs/agent-workflow/handoffs/2026-07-30_DATA-01_CHAT-01_codex_handoff.md`
- التاريخ القديم: `docs/archive/2026-07-execution/`
