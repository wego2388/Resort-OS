# مراجعة الجاهزية الشاملة 360° — خط أساس قبل التنفيذ

**التاريخ:** 2026-07-17  
**المستودع:** `/home/wego/projects/resort-os`  
**الفرع وقت المراجعة:** `chore/agent-workflow-foundation`  
**HEAD وقت اللقطة:** `b26a2e3`  
**نوع المراجعة:** فحص قراءة وتحليل قبل مراحل التطوير — وليس شهادة جاهزية إنتاج.

## لماذا أُنشئت هذه المراجعة؟

الهدف هو منع بدء أي مرحلة اعتمادًا على انطباع عام أو رقم تقدّم وهمي. هذه
الوثيقة تفصل بين:

- أساس تم إثباته بأمر أو كود؛
- خطر ظاهر مباشرة في الكود؛
- مجال يحتاج تدقيقًا متخصصًا قبل تغييره؛
- أمر لا يمكن إثباته محليًا، مثل تشغيل VPS حقيقي أو جودة شبكة الشاطئ.

لم تُنفَّذ إصلاحات المنتج أثناء هذه المراجعة. المخاطر أدناه ستتحول إلى مهام
صغيرة لها Root Cause ومعايير قبول واختبارات مستقلة قبل أي تعديل.

## صورة النظام الحالية

- **Backend:** FastAPI + SQLAlchemy + Alembic، في Modular Monolith يضم 13
  موديولًا مسجلًا: Core، Finance، Inventory، HR، Dining، PMS، Timeshare،
  Beach، Maintenance، CRM، Analytics، Hub، Leasing.
- **Data and jobs:** PostgreSQL، Redis، Celery worker وbeat.
- **Frontend:** Vue 3 + TypeScript + Pinia + Vue Router + Tailwind، داخل
  monorepo يضم تطبيق الموظفين `el-kheima`، الموقع العام `public`، وحزم
  `core` و`ui` مشتركة.
- **Dining:** هو المصدر النشط الموحد؛ مجلدا Restaurant/Cafe المتبقيان لا
  يحتويان source Python نشطًا، وإنما بقايا cache/directories تحتاج تنظيفًا
  آمنًا في مهمة hygiene منفصلة.
- **الحجم التقريبي:** 150 ملف Python داخل التطبيق، 83 ملف اختبار Backend،
  38 شاشة موظفين، 7 شاشات عامة، و43 مكوّن UI مشترك.

## نقاط قوة مثبتة

1. Alembic له head واحد (`9989c0432ccc`) والقاعدة المحلية عند نفس الـhead.
2. PostgreSQL وRedis يعملان محليًا، و`/health` و`/health/ready` أعادا HTTP 200.
3. توجد طبقات مركزية للأخطاء الآمنة، request correlation، security headers،
   rate limiting، logging، وSentry اختياري.
4. access token محفوظ في الذاكرة، والـrefresh token في httpOnly cookie؛ لا
   يُحفظ access token في `localStorage`.
5. الفحص الموجه لم يجد أعمدة أموال ORM مبنية على `Float`، ووجد استخدامًا
   واسعًا لـ`Numeric`/`Decimal`.
6. يوجد AuditLog موحد ومفهرس، وطبقة permission matrix، واختبارات Backend
   واسعة. ملف coverage المحفوظ يسجل 85.3% line coverage بتاريخ 2026-07-09؛
   هذا سجل تاريخي وليس قياسًا جديدًا.
7. توجد scripts للنسخ والاستعادة، وDocker dev/prod health checks، لكن الدليل
   المحلي لا يساوي إثبات VPS حقيقي في البيئة الحالية.
8. `pnpm audit --prod` لم يجد ثغرات معروفة في اعتماديات Frontend الحالية،
   و`pip check` لم يجد اعتماديات Python مكسورة.

## المخاطر الحرجة

### C-01 — بعض العمليات المالية Fail-open وليست ذرّية

يوجد نمط يسمح بإتمام العملية التشغيلية رغم فشل الأثر المالي المرتبط بها:

- `backend/app/modules/finance/services.py:837`: الدالة
  `post_simple_revenue_journal` تبتلع كل الأخطاء وتستدعي CRUD مباشرة، فتتجاوز
  فحص قفل الفترة الموجود في `post_journal_entry`.
- `backend/app/modules/hr/services.py:541`: اعتماد Payroll يمكن أن يُحفظ رغم
  فشل إنشاء القيد (`except Exception: pass`).
- `backend/app/modules/dining/services.py:685` و`:1037`: يمكن إتمام الدفع مع
  فشل إضافة Folio charge.
- `backend/app/modules/beach/services.py:293`: يمكن إتمام بيع الشاطئ مع فشل
  Folio charge/القيد.
- `backend/app/modules/inventory/services.py:235`: يمكن استهلاك المخزون مع فشل
  قيد COGS.

**الأثر:** دفتر الأستاذ، الفوليو، المخزون، والعملية التشغيلية قد تختلف من دون
إنذار يعطل المعاملة أو سجل reconciliation مضمون. هذا خطر صحة بيانات وليس
مجرد تحسين logging.

**بوابة الإصلاح:** تحديد سياسة واضحة لكل أثر (ذرّي إلزامي أو outbox/retry مع
حالة reconciliation)، ثم failure-injection tests على PostgreSQL قبل تعديل
السلوك. لا يجوز استبدال `pass` برفع عشوائي بعد حدوث writes من دون تصميم
rollback/idempotency.

### C-02 — حدود الثقة العامة للـQR والطلب الذاتي لا تطابق القرار المعتمد

- `backend/app/modules/dining/api/router.py:910`: المنيو العام يثق في
  `outlet_id` و`table_id` أرقامًا متسلسلة من العميل.
- `backend/app/modules/dining/api/router.py:940`: الطلب الذاتي العام متاح
  مباشرة، رغم أن القرار المعتمد هو `view_and_call` وأن self-ordering يجب أن
  يكون مغلقًا افتراضيًا.
- `backend/app/modules/dining/api/router.py:977`: حالة الطلب العام تُقرأ عبر
  `order_id` متسلسل بلا session/token عام.
- `backend/app/core/schemas.py:242`: GuestAlert يثق في `branch_id` و
  `context_id` المرسلين من العميل، ولا يشتق السياق من QR token موثوق.
- `backend/app/core/rate_limit.py:47`: خريطة limiter ما زالت تسجل مسارات
  Restaurant/Cafe القديمة، ولا تسجل مسارات Dining العامة الجديدة.
- لا توجد حماية duplicate unresolved request أو idempotency للضغط المتكرر.

**الأثر:** تخمين مواقع/طلبات، إنشاء طلب في سياق غير موثوق، spam، وكسر قاعدة
أن نداء الضيف لا ينشئ أثرًا مطبخيًا أو ماليًا. عدم وجود QR مطبوع يقلل التعرض
الميداني الآن، لكنه لا يصلح حدود الثقة البرمجية.

**بوابة الإصلاح:** أول خطوة في أي بيئة متاحة للعامة هي حصر/تعطيل self-order
خلف setting آمن افتراضيًا، ثم Service Location + token عشوائي/قابل للدوران +
guest session + dedupe/rate limit. إذا ثبت أن النظام محلي فقط، تظل البوابة
مطلوبة قبل أي نشر أو طباعة QR.

**✅ حالة الإغلاق (Gate 1A، 2026-07-17 — النتائج فوق سجل تاريخي، مش مُعاد
كتابته):** الخطوة الأولى (حصر/تعطيل) اكتملت ومراجَعة من Codex على 5 جولات
مستقلة. الطلب الذاتي وguest alerts مقفولون افتراضيًا خلف بوابتين معًا (typed
deployment switch + branch-scoped setting)، `GET
/dining/public/orders/{order_id}` مقفول تمامًا بدل الاعتماد على إعداد واحد،
outlet_id/table_id/item_id بقوا يتحققوا فعليًا من الانتماء لنفس الفرع/المنفذ،
خريطة rate limiting بقت تغطي مسارات Dining الحقيقية، وrate-limit key بقى
مقاومًا لتزوير `X-Forwarded-For` (كان اكتُشف في المراجعة الأمنية النهائية، مش
جزء من C-02 الأصلي). التفاصيل الكاملة والملفات المتأثرة في commit
`fix(security): contain unsafe public guest workflows`.

**لسه مفتوح عمدًا (Gate 8، مش جزء من هذا الإغلاق):** Service Location
الحقيقية، QR token عشوائي/قابل للدوران، guest session، dedupe/idempotency
لطلبات الخدمة، وworkflow `view_and_call` الكامل. **النظام ما زال غير جاهز
للإنتاج بشكل عام** — Gate 1A أغلق خطر تعرض عام واحد محدد، ولا يعني اكتمال
باقي البوابات (C-01 فشل مالي fail-open لسه مفتوح بالكامل — Gate 1B، Super
Admin لسه Gate 2، إلخ).

## مخاطر مرتفعة

| الرمز | المجال | الدليل الحالي | البوابة المطلوبة |
|---|---|---|---|
| H-01 | Super Admin | explicit deny يمكن أن يعطل super_admin، ويمكن تعديل دوره/نشاطه أو منحه override بلا حماية آخر حساب نشط أو self-lockout | سياسة server-side، lock/transaction، TOTP وstep-up، واختبارات تصعيد وتزامن |
| H-02 | Dining finance | لا يوجد بعد عقد Payment متكامل يثبت cashier/shift/method/idempotency وظهور البيع مرة واحدة | نموذج Payment وtransaction boundary واختبارات reconciliation قبل QR/payment |
| H-03 | English/RTL | 42 ملفًا يفرض `dir="rtl"`، و42 ملفًا يستخدم اتجاهات CSS physical، و37 من 38 شاشة موظفين تحتوي نصًا عربيًا مباشرًا | locale واحد محفوظ للمستخدم، `dir` على document root، logical CSS، واختبارات مفاتيح/متصفح |
| H-04 | Frontend quality | لا توجد scripts أو tests خاصة بـlint/component/a11y/E2E؛ الموجود build وtype-check فقط | اختيار minimal toolchain وعدم إضافة أدوات متداخلة، ثم smoke/a11y للرحلات الحرجة |
| H-05 | Deployment | Compose وhealth checks موجودة، لكن لا يوجد إثبات داخل هذه الجلسة لـVPS/TLS/migrations/restore/monitoring | staging/VPS runbook وdeployment + rollback + backup/restore drill موثق |
| H-06 | Order concurrency | منع أكثر من order نشط للموقع يعتمد على منطق التطبيق ولا توجد بعد قاعدة/lock مثبتة للـService Location العامة | invariant DB أو lock مناسب واختبار تزامن PostgreSQL |

## مخاطر متوسطة وحاجة لتدقيق موجه

- **API contracts:** error middleware آمن، لكن الأشكال غير موحدة بالكامل،
  و`request_id` لا يظهر في كل body. `analytics/services.py:83` يرفع
  `HTTPException` من service layer، ما يخلط النقل بالمنطق.
- **Typed settings:** الإعدادات الحالية key/value نصية عامة؛ مركز تحكم
  Super Admin يحتاج registry بالأنواع، validation، الحساسية، scope، audit،
  وقابلية الرجوع.
- **Uploads:** صور Dining تتحقق من MIME الذي يرسله العميل والحجم فقط؛ تحتاج
  signature decoding، إزالة metadata، storage policy، وحذف/استبدال آمن.
- **Auditability:** AuditLog أساس جيد، لكن يجب عمل coverage matrix لكل فعل
  حساس، وتحديد retention/immutability/export policy، وعدم اعتبار best-effort
  audit كافيًا للمال أو الصلاحيات.
- **Pagination and query performance:** توجد pagination في مسارات عديدة، لكن
  يلزم inventory فعلي لكل list endpoint، وEXPLAIN/query-count للرحلات الحرجة
  بدل تحسينات حدسية.
- **Time:** توجد utility لتوقيت المنتجع، لكن بقايا `datetime.utcnow()` و
  `date.today()` تحتاج تصنيفًا حسب معنى الحقل؛ ليست كلها أخطاء.
- **Privacy:** بيانات الضيف العامة قليلة حاليًا، لكن guest-session analytics
  المستقبلية تحتاج minimization وretention قبل التنفيذ.

## مصفوفة المراجعة 360°

| العدسة | الحالة | ما نعرفه الآن | ما لا يجوز افتراضه |
|---|---|---|---|
| Architecture | أساس جيد + دين تقني | Modular Monolith وDining موحد | أن كل service خالٍ من transport/CRUD coupling |
| Database & migrations | مثبت محليًا | head واحد والقاعدة current | سلامة كل FK/index/cascade من دون مراجعة model-by-model |
| Finance & accounting | خطر حرج | قيود متوازنة في المسار المركزي، مع fail-open call sites | تطابق ledger/folio/shift لكل مسار فشل |
| Authorization | خطر مرتفع | backend dependencies وpermission matrix موجودان | isolation كامل لكل branch/outlet أو حماية super_admin |
| Public security | خطر حرج | endpoints عامة وrate limiter مركزي | أن client-supplied IDs موثوقة أو أن QR غير قابل للتخمين |
| API consistency | يحتاج تدقيق | OpenAPI وerror middleware موجودان | contract موحد لكل 13 موديولًا |
| Auditability | أساس موجود | AuditLog مركزي ومفهرس | تغطية كل فعل حساس أو عدم قابلية التعديل إداريًا |
| Backend reliability | مختلط | health/jobs/transactions موجودة | أن broad exception handlers كلها best-effort آمنة |
| Frontend architecture | أساس جيد | core/ui مشتركة وtyped build | خلو الشاشات من duplicate state أو `any` غير الآمن |
| Design system | أساس موجود | tokens و43 مكوّنًا مشتركًا | توحيد استعمالها في كل شاشة |
| UI/UX | يحتاج baseline | سياقات POS/KDS/Admin/Public معروفة | اجتياز رحلة حقيقية في ضوء الشمس/اللمس/الشبكة الضعيفة |
| Accessibility | يحتاج proof | focus/reduced-motion primitives موجودة | WCAG 2.2 AA من دون automated + keyboard + screen-reader audit |
| Localization | خطر مرتفع | vue-i18n وswitch موجودان | English/RTL/LTR كاملا التجربة |
| Testing | Backend قوي/Frontend فجوة | 1,799 اختبار Backend يُجمع حاليًا | أن collection يعني pass، أو أن UI regressions مغطاة |
| Performance | يحتاج قياس | pagination/cache وبعض lazy routes | Core Web Vitals أو query budgets من دون قياس p75/EXPLAIN |
| Realtime/offline | يحتاج failure tests | WebSocket وoffline queue primitives موجودة | fallback/dedupe/recovery في شبكة الشاطئ |
| Observability | أساس موجود | structured logs، request ID، Sentry اختياري | alerts/SLO/runbooks وتطابق الأخطاء مع request ID |
| Deployment/DR | محلي مثبت جزئيًا | Compose config وbackup scripts | VPS/TLS/offsite restore/rollback في البيئة الفعلية |
| Dependencies | فحص جزئي | Frontend audit نظيف وPython dependency graph متماسك | CVE audit Python؛ `pip-audit` غير مثبت |
| CI & developer experience | فجوة | agent baseline script ووثائق تشغيل | بوابة CI مستضافة؛ لا يوجد workflow داخل `.github` |

## أدلة وأوامر هذه اللقطة

| الأمر/الفحص | النتيجة |
|---|---|
| `bash scripts/agent-check.sh` | نجح: الأدوات، Alembic head، جمع 1,799 اختبارًا، Compose dev/prod، و`git diff --check` |
| `alembic heads` / `alembic current` | كلاهما `9989c0432ccc` |
| `/health` و`/health/ready` | HTTP 200 محليًا؛ PostgreSQL وRedis جاهزان |
| `docker compose ps` | PostgreSQL وRedis healthy، وخدمات Backend/Celery/Frontend تعمل محليًا |
| `pnpm audit --prod` | لا توجد ثغرات معروفة في advisory database المستخدمة وقت الفحص |
| `pip check` | لا توجد متطلبات Python مكسورة |
| Python security audit | لم يُشغّل؛ `pip-audit`/`bandit` غير مثبتين أو مهيئين |
| Frontend automated tests/a11y/E2E | غير موجودة في scripts الحالية |
| Real VPS / production restore drill | لم يُشغّل في هذه الجلسة؛ يحتاج بيئة وصلاحية منفصلة |

## أدلة إغلاق Gate 1A (2026-07-17 — إضافة، مش تعديل للقطة الأصلية فوق)

مراجعة مستقلة نهائية من Codex (5 جولات: 4 تصحيح + جولة أمان) اعتمدت الإغلاق:

| الفحص | النتيجة |
|---|---|
| اختبارات الباك إند الكاملة | **1,826 اختبارًا مُجمَّعًا — 1,823 ناجح، 3 skipped (PostgreSQL-only migration tests، `DINING_MIGRATION_TEST_ADMIN_URL` غير متاح)، صفر فشل** |
| اختبارات مقاومة تزوير rate-limit proxy | 7/7 ناجحة |
| `alembic heads` | head واحد: `9989c0432ccc` — لا migration جديدة |
| TypeScript (`type-check:all`) | ناجح للتطبيقين |
| Production build (`build:all`) | ناجح للتطبيقين، مع تحذيرات bundle/i18n غير حاجبة موجودة من قبل |
| Docker Compose (base + prod + prod+ip-only overlay) | نجحت الثلاثة |
| `git diff --check` | نظيف |
| نشر VPS حقيقي | **لم يحدث** — لم تُبنَ أو تُنشَر أي صورة Docker على السيرفر الفعلي في هذه الدفعة |

## القرار قبل التنفيذ

لا نعلن النظام production-ready — Gate 1A أغلق خطر تعرّض عام محدد فقط. نبدأ من
[`SMART_EXECUTION_ROADMAP.md`](./SMART_EXECUTION_ROADMAP.md)، ونختار في كل مرة
أصغر مرحلة تعالج أعلى خطر مثبت بعد التحقق من تعرض البيئة واعتمادياتها. Gate 1B
(Financial Atomicity — C-01 فوق) هي التالية ولم تبدأ. أي نتيجة جديدة تغيّر
ترتيب المخاطر تُحدّث هذه الوثيقة و`wagdy.md` قبل التنفيذ.
