# SEC-01 → SEC-12 — إصلاح 11 finding من جولة مراجعة Codex الثانية

## السياق

Mohamed حوّلّي بنود Codex Review round 2 (Core branch/audit permissions،
Dining/PIN branch isolation، backup/health timers، dependency audit،
providers/التنبيهات، password 72-byte، upload limits، وثائق VPS القديم)،
وطلب تحقق شخصي بقراءة الكود الفعلي قبل أي خطة. وزّعت التحقق على 4 وكلاء
معزولين متوازيين (قراءة فقط، صفر تعديل)، جمّعت النتائج في خطة مرتّبة
Critical→High→Medium، وبعد موافقته الصريحة ("نفذها كلها و رقم 2 سيبها
للاخر") نفّذت كل البنود عدا رقم 2 (قناة التنبيهات — مؤجّلة عمدًا لآخر
الدفعة، تفاصيلها في handoff منفصل).

**لم يُلمس**: أي كود deploy فعلي على containers الإنتاج، وأي من ملفات
الـworktree المعلّقة غير المرتبطة (docker-compose.yml, owner frontend
files, scripts/start.sh, xlsx template, docs/UAT_PERSONAL_GUIDE.md) —
هذه بقيت زي ما هي بالظبط، مش جزء من commit الدفعة دي.

## SEC-01 — تسريب سجل التدقيق عبر الفروع (Critical)

**الملف**: `backend/app/modules/core/api/router.py::list_audit_logs`

`branch_id` كان اختياري بدون أي فرض — أي مدير (مش super_admin بس) يقدر
يشوف سجل تدقيق كل الفروع بحذف الفلتر. أُعيد استخدام
`_require_branch_or_global_read` الموجود أصلاً في نفس الملف (Gate 2B3A،
كان بيحمي إعدادات الفرع فقط) — `branch_id` فاضي = عرض عام لـsuper_admin
بس، محدد = لازم يطابق فرع الجلسة عبر `assert_branch_access`. 5 اختبار
جديد.

## SEC-06 — إنشاء طلبات Dining عبر الفروع (High، اتوسّع نطاقه فعليًا)

**الملفات**: `dining/api/router.py`

الخطة الأصلية غطّت مسارات الإنشاء الأربعة بس (`create_order`,
`hold_order`, `list_held_orders`, `sync_offline_order`) — نادل فرع A كان
يقدر ينشئ/يعلّق/يزامن طلبات على منفذ فرع B بمجرد تخمين `outlet_id`.
اتضاف `_assert_outlet_branch` (نفس نمط `_assert_order_branch` الموجود)
وطُبِّق على الأربعة. **فحص إضافي أثناء التنفيذ اكتشف نطاق أوسع بكتير**:
كل endpoints إدارة المنيو/المنافذ/الطاولات (`update_outlet`,
`create/update/delete_category`, `create/update/delete_item`, صور
الأصناف، extra-groups، recipe-lines، variants، الطاولات) **كمان من غير
أي تحقق فرع خالص** — ده **مش** ضمن SEC-06 المعتمد، اتسجّل كـfinding
منفصل في القسم الأخير تحت "لسه محتاج قرار Mohamed" بدل ما يتنفّذ بدون
إذن. تصحيح fixture ripple كبير: كل تست عبر 6 ملفات كان بيستخدم
`waiter_headers`/`manager_headers` العالمية (بلا عضوية فرع) لإنشاء طلبات
— اتحوّلوا لمستخدمين معزولين مربوطين بالفرع الصح، نفس نمط REL-23/24. 3
اختبار جديد.

## SEC-07 — `resolve_pin_approval` بدون تحقق فرع خالص (High)

**الملفات**: `core/services.py`, `core/policy_engine.py`, و7 call sites
عبر `credit/finance/dining`.

المعتمِد كان بيتحقق دوره وPIN بس — مدير فرع A كان يقدر PIN بتاعه يوافق
على إلغاء/خصم/حركة كاش/قفل وردية في فرع B. `target_branch_id` بقى
باراميتر إجباري في `resolve_pin_approval` و`policy_engine.require_approval`،
بيتحقق عبر `_can_enter_branch` (نفس فحص `pin_switch_login`). **باج ثاني
اتكشف بالـpyright بعد أول تعديل**: `finance.services.close_shift` عندها
نداء مباشر لـ`resolve_pin_approval` (مش عبر `policy_engine`) كان
هينسى منه لولا الفحص — كل الـ7 call sites اتأكدت يدويًا. ripple على
تستات كتير كانت بتستخدم "manager@test.local" المشترك (fixture عالمي) —
لقيت إن ربط نفس اليوزر المشترك بفروع مختلفة في تستات مختلفة بيصطدم بقيد
`UNIQUE(user_id)` على `user_branch_memberships` (مستخدم واحد = عضوية فرع
واحدة بس) — اتصلح بمدراء معزولين جداد بدل إعادة استخدام اليوزر المشترك.
1 اختبار جديد (branch mismatch)، ~6 تستات موجودة اتصلحت.

## SEC-08 — IP سيرفر قديم في سكربتات وظيفية (High)

3 سكربتات (`vps-create-admin.sh`, `vps-recover-admin.sh`,
`vps-init-first-branch.sh`) كانت بتفحص شهادة على مسار IP قديم
(`191.218.161.133`) عشان تقرر تستخدم أي docker-compose override — دلوقتي
بتفحص شهادة `elkheima.com` الحقيقية (domain-based، الوضع الفعلي حاليًا)
مع fallback لـ`ip-only` لو مفيش شهادة أصلاً (bootstrap أول مرة).
`check_prod_health.sh` نفس المنطق. `resort-os-healthcheck.service`:
حذف `RESORT_PUBLIC_IP=191.218.161.133` المفلطة (باقي المتغيرات فعليًا
بتتخطاها بـoverride صريح، فكانت dead value مضلّلة).

## SEC-09 — bcrypt 72-byte crash (High)

**الملف**: `core/kernel/security.py::validate_password_strength`،
`core/kernel/auth/service.py::update_user`

`bcrypt.hashpw` بترمي `ValueError` غير معالجة لأي باسورد أطول من 72
بايت — باسورد عربي حقيقي (~40 حرف) بيتخطاها بسهولة (UTF-8، حرفين لكل
حرف عربي)، يعني 500 قبيح لأي موظف بيكتب باسورد بالعربي. فحص طول البايت
اتضاف كأول فحص في `validate_password_strength` (البوابة المستخدمة في كل
مسارات كلمة المرور تقريبًا). مسار واحد إضافي (`AuthService.update_user`)
كان بيتخطى البوابة دي تمامًا — اتضاف الفحص هناك كمان (دفاع إضافي، مفيش
caller مؤكد له حاليًا لكن نفس البوابة أفضل من ثغرة صامتة). 5 اختبار جديد.

## SEC-10 — حدود رفع الملفات في استيراد Excel (Medium)

**الملفات**: `hr/api/router.py`, `timeshare/api/router.py`

الفحص الأصلي كان بيقول "مفيش حد حجم خالص" — **تصحيح بعد القراءة
الفعلية**: فيه أصلاً حد 5 ميجا (zip bomb protection) على مستوى
`services.py`، بس بعد قراءة الملف كامل في الذاكرة ومن غير أي فحص نوع
محتوى. اتضاف فحص `content-type` + امتداد `.xlsx` قبل القراءة (نفس نمط
`dining.upload_item_image` الموجود)، فبيرفض ملف غلط برسالة واضحة قبل ما
يوصل لـopenpyxl خالص. 4 اختبار جديد.

## SEC-11 — مراجع IP قديم في وثائق حية (Medium)

`DEPLOYMENT.md` (المرجع الرئيسي، host + SSH alias)، `docs/README.md`،
`wagdy.md`، `.kiro/AGENT.md`، `EL_KHEIMA_EXECUTION_BOARD.md` (جدول "حالة
الإنتاج المثبتة"). **متلمسش عمدًا**: `PROJECT_STATUS.md` وhandoffs
مؤرَّخة — دي سجلات تاريخية لحظة-بلحظة (زي `git log`)، تعديلها بأثر رجعي
بيزوّر التاريخ لا يصححه؛ `docs/DNS_CUTOVER_NAMECHEAP_GUIDE.md` كان
بالفعل صحيحًا (بيوثّق الانتقال القديم→الجديد عمدًا).

## SEC-04/SEC-05 — تحديث الاعتماديات (Critical/High)

- **python-jose 3.3.0 → 3.5.0**: يقفل CVE-2024-33663 (Critical،
  algorithm confusion في تحقق JWT) — نفس المكتبة المستخدمة لكل طلب
  مصادَق.
- **fastapi 0.115.6 → 0.122.0 + starlette 0.41.3 → 0.50.0**: قفل زي
  الـRange-header ReDoS الحقيقي (DoS غير مصادَق) وقفل معظم الـ9 CVE
  الأصلية. **قرار نطاق موثّق**: 5 CVE متبقية (Host-header URL confusion،
  HTTPEndpoint raw dispatch، Windows UNC SSRF) بتحتاج starlette 1.x +
  قفزة fastapi أكبر بكتير (0.135+) — قرأت وصف كل CVE، ولا واحدة منهم
  مستغَلّة فعليًا في هذا المشروع تحديدًا (JWT+role checks مش
  request.url، FastAPI routers مش raw HTTPEndpoint، Linux مش Windows).
  توسيع القفزة لـ1.x قرار أكبر يستاهل مراجعة منفصلة، مش جزء من الدفعة دي.
- **cryptography 44.0.0 → 50.0.1**: يقفل 8 CVE (مستخدمة أساسًا لـFernet
  تشفير PII).
- **python-multipart 0.0.12 → 0.0.32**: يقفل 7 CVE.
- **ecdsa 0.19.2**: مفيش fix متاح (المشروع نفسه معلن "خارج النطاق"،
  Minerva timing attack على التوقيع). **تقييم مخاطر**: transitive
  dependency لـ`python-jose[cryptography]`/`sendgrid` بس — هذا المشروع
  بيستخدم HMAC (JWT عادي بـSECRET_KEY) مش ECDSA signing فعليًا، فالثغرة
  دي (بتسرّب مفتاح خاص وقت التوقيع بـECDSA) مش قابلة للاستغلال هنا
  عمليًا. اتسيبت كما هي، موثّقة.

**تحقق كامل**: `pip-audit` بعد التحديث يأكّد صفر CVE على جوز/كريبتوجرافي/
مالتيبارت. `pytest tests/ -v` (الكامل، 2000+ اختبار) عدّى صفر فشل قبل
وبعد كل التغييرات دي، بما فيها 4 دفعات كاملة منفصلة على مراحل مختلفة من
التنفيذ.

## SEC-02/SEC-03 — تفعيل backup/health timers على السيرفر (High/Critical)

كانوا موثّقين في الريبو (`deploy/systemd/resort-os-{backup,healthcheck}.
{service,timer}`) بس **غير مثبّتين خالص** على السيرفر الجديد (نفس فجوة
certbot المكتشفة يوم 2026-08-30) — آخر نسخة احتياطية حقيقية كانت من
25 أغسطس (6 أيام قديمة وقت الاكتشاف).

- **Backup**: ثبّت + فعّل الـtimer (يومي 03:00). **اتأكد حي مش نظري**:
  شغّلت الـservice يدويًا (نجح، 844K dump)، عملت restore drill حقيقي
  (قاعدة بيانات معزولة `resort_os_restore_drill`، مسحتها بعد التأكد) —
  `users=26`/`branches=1` طابقوا الإنتاج بالظبط.
- **Health check**: ثبّت + فعّل الـtimer (كل 5 دقايق). اتأكد: 16/16 فحص
  عدّى (backend/db/redis health، 4 نطاقات HTTPS، 9 containers، backup
  حديث، TLS صالح، مساحة قرص).

## SEC-12 — بوابة التحقق النهائية

- `pytest tests/ -v` (الكامل، backend) — **صفر فشل**، شغّالة بعد كل
  التغييرات (branch isolation + PIN approval + bcrypt + uploads +
  الاعتماديات المحدّثة كلهم مع بعض).
- **Postgres-only concurrency tests** (16 ملف، `DINING_CONCURRENCY_TEST_
  ADMIN_URL` وما شابه، بتتجاهل افتراضيًا بدون Postgres حقيقي): 56 عدّوا،
  2 skip، **9 فشلوا — كلهم مؤكَّدين pre-existing** (`git blame`/`git diff`
  يثبت إنهم مش من تغييراتي اليوم): `pay_payment()` في leasing ناقصها
  `collected_by` (باراميتر أُضيف يوم 2026-08-11 والتست نفسه ما اتحدّثش)،
  `test_fresh_chain_reaches_privacy_head` بترجع revision قديم ثابت في
  الكود (`c4d8e2f6a901`) بينما الـhead الحقيقي اتحرّك قدام كتير من وقتها،
  و`FinancialConfigurationError`/`OpenCashierShiftRequiredError` في
  تستات تانية بتوحي بـfixture drift مشابه. **دين تقني حقيقي، بس مش جزء
  من الدفعة المعتمدة دي — محتاج قرار منفصل من Mohamed** (تفصيل كامل تحت).
- Frontend: `type-check:all` نظيف، `build:all` (الاتنين el-kheima
  وowner) نظيف، `test:frontend` 106/106 عدّوا.
- **`pnpm audit` جديد (مرة أولى، كان برّه نطاق التحقق الأصلي)**: 14 CVE
  (1 حرج، 10 عالي، 3 متوسط) — **كلهم في أدوات البناء/التطوير بس**
  (vite/esbuild/vitest/eslint/workbox-build)، صفر منهم في كود بيتنشر
  فعليًا للمتصفح. خطر عملي منخفض جدًا (سيرفر إنتاج بيقدّم ملفات static
  مبنية، مفيش dev server ولا Vitest UI متعرّضين للإنترنت). محتاج قرار
  منفصل مستقبلي، مش جزء من الدفعة دي.

## SEC-13 — قناة التنبيهات fail-open (Critical، نُفِّذت آخر الدفعة بطلب Mohamed الصريح)

**الملفات**: `core/kernel/whatsapp.py`, `core/kernel/worker.py`,
`core/kernel/auth/router.py`, `main.py`

3 نقاط صمت حقيقية اتصلحت (الجزء اللي ممكن يتنفذ بدون بيانات اعتماد
حقيقية — الجزء التاني، ربط مزوّد حقيقي فعليًا، لسه مطلوب من Mohamed،
تفاصيله تحت):

1. **`send_whatsapp_message`**: كانت بترجع `True` حتى لو Twilio مش مُعدّة
   خالص — أي caller (فحص احتيال، فشل مهمة Celery، تنبيه تأخر سداد) كان
   بيصدّق إن التنبيه اتبعت فعليًا. دلوقتي: `True` بس في development/test
   (نفس السلوك القديم عمدًا، مفيش داعي لإعداد Twilio محليًا)، `False` +
   ERROR واضح في أي بيئة تانية (الإنتاج تحديدًا).
2. **`_try_whatsapp_notify`/`_try_sentry_capture`** (في `worker.py`، القلب
   المشترك لكل تنبيهات فشل المهام): كانوا بيتجاهلوا نتيجة
   `notify_admin`/`capture_exception` تمامًا — لو القناة رجعت
   `False`/`None` (مش استثناء)، الفشل ده كان يختفي بصمت فوق فشل المهمة
   الأصلي نفسه (صمت مزدوج). دلوقتي بيسجّلوا WARNING واضح.
3. **`password_reset_request`** (auth router): `send_password_reset_email`
   بترجع `False` (مش استثناء) لو SendGrid غير مُعدّة — الـ`except
   Exception` القديم مكانش بيمسك الحالة دي خالص، يعني كل طلب استرجاع
   باسورد كان بيفشل بصمت تمامًا من غير أي أثر في اللوج. دلوقتي بيتسجّل
   WARNING (الاستجابة العامة للمستخدم فضلت زي ما هي بالظبط — enumeration-
   safe، مفيش تسريب).
4. **تحذير موحّد وقت الإقلاع** (`main.py::_warn_if_alert_channels_
   unconfigured`، جديدة): سطر ERROR واحد واضح في لوجات الإقلاع، بس في
   production/staging، بيسرد بالاسم أي قناة (Sentry/WhatsApp/ADMIN_PHONE/
   Email) لسه مش مُعدّة — بدل ما الفجوة تتكشف وقت حادثة حقيقية. تحذير بس،
   مش فشل إقلاع (بيانات الاعتماد الحقيقية قرار Mohamed منفصل).

**اتأكد حي**: نداءات مباشرة لـ`send_whatsapp_message`/`_warn_if_alert_
channels_unconfigured` أثبتت السلوك بالظبط (production→False+ERROR،
dev→True، سطر تحذير واحد واضح بيسرد كل القنوات الفاضية). 9 اختبار جديد
(`test_kernel_whatsapp.py` جديد كامل، إضافات في `test_kernel_worker.py`
و`test_auth_session_security.py`).

### 🔴 لسه مطلوب من Mohamed تحديدًا (مش حاجة أقدر أعملها بنفسي)

القناة نفسها لسه ميتة في الإنتاج — الكود بقى يبلّغ عن الصمت ده بوضوح،
لكن ده مش حل، ده تشخيص. عشان التنبيهات تشتغل فعليًا محتاج منك:

1. **WhatsApp**: إما حساب Twilio حقيقي (`TWILIO_ACCOUNT_SID`,
   `TWILIO_AUTH_TOKEN`, رقم WhatsApp Business مفعّل)، أو Meta Cloud API
   مباشرة (`WHATSAPP_PHONE_ID`, `WHATSAPP_ACCESS_TOKEN`) — أي مسار منهم.
2. **`ADMIN_PHONE`**: رقمك (أو رقم مين تحب يستلم تنبيهات الاحتيال/فشل
   المهام) بصيغة دولية (`+201...`).
3. **Sentry**: حساب مجاني على sentry.io، `SENTRY_DSN` بتاعه.
4. **SendGrid** (لاسترجاع كلمة المرور): `SENDGRID_API_KEY` +
   `SENDGRID_FROM_EMAIL` (إيميل مُتحقَّق في SendGrid).

بمجرد ما تجهّزهم، أحطهم في `.env.prod` على السيرفر وأعمل restart
لـcontainer الـbackend — مفيش أي تعديل كود إضافي مطلوب، القيم دي بس.

## لسه محتاج قرار Mohamed (مؤجَّل عمدًا، برّه نطاق الدفعة المعتمدة)

1. **فجوة branch isolation أوسع في dining menu-management** — اتكشفت
   أثناء SEC-06 (`update_outlet`, category/item/table CRUD, صور، extra-
   groups، recipe-lines، variants — كلهم من غير تحقق فرع). مش ضمن الـ13
   بند المعتمدين، محتاجة موافقة صريحة قبل التنفيذ.
2. **9 اختبار Postgres-only فاشل (pre-existing، من 2026-08-11 وقبلها)**
   — `pay_payment()` بدون `collected_by`، alembic-head test بمرجع قديم
   ثابت، وfixture drift في تستات تانية. دين تقني حقيقي غير مرتبط
   بالدفعة دي.
3. **14 CVE في أدوات البناء الأمامية** (dev-tooling بس، صفر تعرّض
   إنتاجي حقيقي) — يستاهل ترقية منفصلة مخطط لها، مش عاجلة.
4. **starlette 5 CVE متبقية** (تحتاج starlette 1.x + fastapi 0.135+) —
   قفزة أكبر بكتير من دفعة اليوم، غير مستغَلّة فعليًا في هذا المشروع
   تحديدًا لكن يستاهل مراجعة مخصوصة مستقبلًا.
