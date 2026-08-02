# حالة المشروع الحالية — El Kheima Beach Resort OS

**آخر تحقق:** 2026-08-02 بعد إصلاح باج في تأكيد الحجوزات الأونلاين (Hub)
**البيئة:** Production — `elkheima.com` / VPS `191.218.161.133`
**قائد التنفيذ والمراجع النهائي:** Codex

هذا الملف يسجل الحقائق الحالية فقط. التاريخ السابق محفوظ في
`docs/archive/2026-07-execution/`.

## 1. المصدر والإصدار

| البند | القيمة المثبتة |
|---|---|
| فرع العمل الوحيد | `claude/CX-02C-frontend-auth-bootstrap` |
| Resort OS source release | `5b02010` |
| Marketing source release | `0b0321f` من المستودع المستقل (`main` يطابق الالتزام) |
| remote | فرع العمل يحتوي `5b02010` (يشمل `9579c2f`، `ddfbaaa`، `4a0a777`، `8597535`، `b1db886`، `0d55717`، `4ca10c1`، `5b02010`) |
| `origin/main` | `598938e` — لم يُغيّر |
| active Resort release | `/opt/resort-os-releases/5b02010` |
| Resort current link | `/opt/resort-os-current -> /opt/resort-os-releases/5b02010` |
| active Marketing release | `/opt/elkheima-marketing-releases/0b0321f` |
| Marketing current link | `/opt/elkheima-marketing-current -> /opt/elkheima-marketing-releases/0b0321f` |
| Compose project / override | `resort-os-prod` / `docker-compose.prod.domain.yml` |

أرشيف Resort OS:
`/var/backups/resort-os/source-releases/5b02010.tar.gz`،
SHA-256
`50538820d9b9e4ef9e3d724e45b09dfca4dfc86e25154a852fab98765900b673`.
(أرشيفات `a3e8abb`، `ddfbaaa`، `4a0a777`، `8597535`، `b1db886`، `0d55717`، `4ca10c1` السابقة ما زالت محفوظة كما هي.)

أرشيف Marketing:
`/var/backups/resort-os/marketing-source-releases/0b0321f.tar.gz`،
SHA-256
`d390a2aa0a6fc025d323a6e9442330d28092d90ef1d260fb1920410f4a85b40d`.
(أرشيف `16f8f2c` السابق ما زال محفوظًا كما هو.)

مجلدا المصدر القديمان `/opt/resort-os` و
`/opt/elkheima-marketing-website` محفوظان كما كانا، وغير مستخدمين كمصدر
للإصدار الفعال ولم يُنظفا أو يُعاد ضبطهما.

## 2. الخدمات الفعالة

- `backend`, `celery_worker`, `celery_beat` بُنوا ونُشروا من `5b02010`
  (موديول Hub: `confirm_booking` كان فيه كود مكرر بعد كتلة if/else بيتنفذ
  دايمًا — يسبب `UnboundLocalError` حقيقي (مبتلوع بصمت) لما مفيش غرف
  متاحة للتأكيد التلقائي، ويتسجّل كـ"فشل" مربك بدل التحذير الصح. الحالة
  النهائية العملية ماتغيّرتش، بس اللوجات كانت مضللة. مكتشف أثناء مراجعة
  ذاتية شاملة طلبها Mohamed). `el_kheima` (frontend) لم يتغيّر في الجولة
  دي، لسه من `b1db886`. صفر migration، Alembic head واحد لم يتغيّر
  `88d1c505a9dc`.
- `marketing_site` مبني من المصدر المستقل `0b0321f` عبر
  `/opt/elkheima-marketing-current`.
- Backend image:
  `sha256:abbd5f245b5e3d84efc2e5c9215f06c08576a465f316e89e26fcf0842655b28a`.
- Celery worker:
  `sha256:c58a764a0c87475db671e8e7d1e9302e8ef1979b9da65f1bf4025a2cee6a2fd6`.
- Celery beat:
  `sha256:9e304ad5e074762707aaab2097a273f31f0aeaba5713ddda7bd95e393da3c1d0`.
- El Kheima staff app (من `b1db886`، غير متغيّر هذه الجولة):
  `sha256:f135b11a4d2d7799afd011934a093eb14ed14921b86bbd807d31582a1082c673`.
- Marketing image:
  `sha256:417bc784605359fdfc9758bffa1445d8eaf959dac740042bd14e3fdc076b3177`.
- Nginx:
  `sha256:97d490c12ba55b4946b01546d1c3ed324e8d41ab1c9fcb2a616aa470620e5b46`.
- 8 حاويات Running وكل healthchecks المعرّفة سليمة. الحاويات الثماني
  `RestartCount=0` بعد القطع.
- PostgreSQL وRedis بقيا على volumes والحاويات طويلة العمر ولم يُعاد
  إنشاؤهما أثناء النشر.

## 3. DNS وTLS والـedge

سجلات Hostinger الفعالة:

| الاسم | النوع | القيمة | TTL |
|---|---|---|---:|
| `@` | A | `191.218.161.133` | 300 |
| `app` | A | `191.218.161.133` | 300 |
| `www` | CNAME | `elkheima.com` | 300 |

- authoritative nameservers:
  `pixel.dns-parking.com` و`byte.dns-parking.com`.
- authoritative DNS و`1.1.1.1` و`8.8.8.8` و`9.9.9.9` أعادوا عنوان
  الـVPS للجذر و`app`.
- Hostinger DNS rollback snapshot: `167902017`، أُنشئ
  `2026-07-30T03:18:09Z`، ويحفظ الحالة السابقة
  `@ A 2.57.91.91` و`www CNAME elkheima.com`.
- لم يُستخدم Reset DNS، ولم يُضف AAAA، ولم تُمس سجلات أخرى.
- شهادة Let's Encrypt ECDSA باسم `elkheima.com` تشمل:
  `elkheima.com`, `www.elkheima.com`, `app.elkheima.com`.
- الشهادة صالحة من `2026-07-30 02:21:35 UTC` حتى
  `2026-10-28 02:21:34 UTC`.
- `certbot renew --dry-run` وdeploy hook لإعادة تحميل Nginx نجحا.
- HSTS canary فعال بقيمة `max-age=604800` دون `includeSubDomains` في
  المرحلة الأولى.
- المنافذ العامة للتطبيق 80 و443 فقط؛ منفذ marketing القديم 8443 أُغلق.

## 4. فحص الإنتاج الخارجي

- `https://elkheima.com/` يعيد 200.
- `https://www.elkheima.com/` يعيد 200.
- `https://app.elkheima.com/` يعيد 200.
- `https://app.elkheima.com/health` يعيد 200 و`status=ok`.
- HTTP على النطاقات الثلاثة يعيد 301 إلى HTTPS الصحيح.
- HTML و`robots.txt` و`sitemap.xml` تحتوي الدومين الرسمي، وصفر مراجع
  للعنوان `191.218.161.133`.
- فحص marketing canary قبل الاستبدال: `/` و`/health` = 200،
  domain refs في 4 ملفات، old-IP refs = 0.
- Backend runtime origins هي الجذر و`www` و`app` فقط، وخريطة Chatbot
  العامة مقصورة على الجذر و`www`.
- Chatbot E2E من الدومين: welcome عربي، إنشاء session، قبول disclosure،
  رد Gemini عربي غير فارغ، وإنهاء session بنجاح.
- `/ar/timeshare` و`/en/timeshare` يعيدان 200. الصفحة تعرض Blue Bay كجهة
  إدارة الملكية الجزئية، وترسل الاستفسار إلى `/api/v1/hub/contact` مع
  consent وidempotency. لا تعرض أسعارًا أو تضمن توفرًا أو شروطًا تعاقدية.
- ترجمات Marketing متطابقة: 2919 مفتاحًا في كل من العربية والإنجليزية
  والروسية والإيطالية، وصور الأنشطة والفعاليات راجعها Codex بصريًا.
- تطبيق الموظفين المنشور يحتوي إصلاح تبديل المنفذ للطلب القائم: وجود
  `pendingOrderId` يغيّر المنيو دون إلغاء الطلب، أما السلة المحلية وحدها
  فتحتفظ بنافذة التأكيد. ملف `UnifiedPOSView` المنشور طابق البناء المحلي
  عند SHA-256
  `0339d0eb7ca8c93a9a9fa081d74e13c6b47a6bc78d9940bfa8b2a024388dea87`.
- فحص logs النهائي لخدمات backend/worker/beat/staff/marketing/nginx:
  صفر أنماط severe ضمن نافذة الفحص.

## 5. مسار الموظفين والحسابات المنشور

- الموارد البشرية (`hr_manager` أو الإدارة) تنشئ سجل الموظف داخل الفرع
  الفعال؛ لا تقبل نقطة الإنشاء `user_id` ولا تسمح للمحاسب بإدارة HR.
- السوبر أدمن يفتح مركز الإدارة الموحد، يختار سجل الموظف، ثم ينشئ حساب
  الدخول ويحدد الدور. Backend يربط الحساب بالموظف ويضيف عضوية الفرع
  الافتراضية الفعالة داخل transaction واحدة.
- إنشاء الحساب محمي بـStep-Up ومسجل في Audit. العزل بين الفروع fail-closed،
  ومسار الربط اليدوي القديم محصور في السوبر أدمن كاستعادة مدققة ولا يمنح
  عضوية فرع.
- صفحات المستخدمين والصلاحيات القديمة تحوّل إلى مركز السوبر أدمن بدل
  ازدواج الشاشات، والقائمة الجانبية منظمة إلى مجموعات تشغيلية مع عرض هاتف
  off-canvas.
- حسابات الموظفين العاديين، ومنها المحاسب، تُنشأ من هذا المسار بعد سجل HR.
  إنشاء `super_admin` احتياطي يبقى bootstrap من الطرفية فقط.

حالة الإنتاج بعد النشر: `users=1`, `active_superadmins=1`, `branches=1`,
`employees=0`, `active_memberships=1`. لم تُنشأ هويات أو كلمات مرور
تجريبية.

## 6. البيانات التجريبية المنشورة

البيانات synthetic وموسومة وليست اعتمادًا ماليًا أو تشغيليًا نهائيًا.
اقتصر التطبيق على الفرع الفعال الوحيد `ELK-001` وبهوية
`super_admin` الفعالة، مع advisory lock وdry-run افتراضي وconfirmation
صريح.

| النطاق | العدد |
|---|---:|
| المخازن / تصنيفات المخزون / المنتجات | 3 / 10 / 114 |
| حركات الرصيد الافتتاحي | 114 |
| الموردون / أوامر الشراء / طلبات الشراء | 6 / 5 / 3 |
| منافذ المطعم / الأصناف / مكونات الوصفات / الطاولات | 2 / 104 / 459 / 12 |
| أنواع الغرف / الغرف / خطط الأسعار | 5 / 52 / 4 |
| الأقسام / الأصول / أوامر الصيانة المغلقة أو الملغاة | 12 / 6 / 3 |
| عملاء CRM / leads / opportunities / campaigns | 4 / 4 / 2 / 1 |
| وحدات timeshare / عقود draft | 12 / 3 |
| عقود lease draft | 3 |
| مواقع beach تجريبية / عقود B2B غير فعالة | 8 / 2 |
| محتوى Hub | 3 صفحات draft + عرض inactive + مقال draft |

لم يضف importer مستخدمين أو كلمات مرور أو sessions أو صلاحيات، ولم يضف
حجوزات أو مدفوعات أو قيود يومية أو رواتب أو dining orders أو beach sales
أو أقساط أو guest alerts. ملفات العد قبل وبعد متطابقة byte-for-byte:

- `/var/backups/resort-os/source-releases/32eb0f8-pre-seed-counts.txt`
- `/var/backups/resort-os/source-releases/32eb0f8-post-seed-safety-counts.txt`

قراءة الإنتاج في آخر فحص أظهرت حسابًا واحدًا فقط:
`super_admin: total=1, active=1`. لا توجد سجلات أو حسابات موظفين حتى
الآن، ولم تُعرض أي بيانات اعتماد في التوثيق أو الفحص. إنشاء الحسابات ينتظر
أسماء وبريد وأدوار أشخاص حقيقيين، وفق `docs/STAFF_APP_GUIDE_AR.md`.

## 7. أدلة الجودة

- full backend suite: 2181 passed و40 skipped من 2221 collected، صفر
  failure.
- production demo seed tests: 9 passed.
- PostgreSQL clean-schema apply + idempotency + safety checks: passed.
- استعادة dump حقيقية واختبار importer عليها ثم تنظيف DB المؤقتة: passed.
- onboarding/HR/auth focused backend: 228 passed و1 skipped؛ وآخر فحص
  أمني بعد تعديل الربط: 31 passed.
- frontend: 95/95 عبر 13 ملف اختبار.
- frontend type-check وproduction build: passed.
- full backend release regression: 2181 passed و40 skipped، صفر failure؛
  Alembic بقي عند head واحد `88d1c505a9dc`.
- Marketing `truth`, `type-check`, `build`: passed.
- `agent-check`: passed بعد تغييرات النشر؛ Alembic single head
  `88d1c505a9dc`؛ `git diff --check`: passed.
- دليل الإدارة وتدريب الموظفين العربي محدث، ودليل السوبر أدمن مصحح بحسب
  مسار إنشاء الحسابات و2FA وStep-Up الحالي.

## 8. النسخ والتراجع

- DNS rollback: Hostinger snapshot `167902017`.
- domain-cutover rollback directory:
  `/var/backups/resort-os-domain-cutover-aed94a0`، mode `0700`.
- يحتوي image manifest، SHA لنسخة DB، ونسخة مشفرة الصلاحيات من إعدادات
  Let's Encrypt السابقة وملفات systemd السابقة.
- Resort base cutover archive:
  `/var/backups/resort-os/source-releases/aed94a0.tar.gz`،
  SHA-256
  `eb404ef2341e6ca10ff658d00dc2846d6daf81cdd5589d98343c4c1e5bccca72`.
- صور ما قبل cutover محفوظة تحت
  `resort-os-rollback/*:pre-domain-aed94a0`.
- صورة Marketing السابقة محفوظة تحت
  `resort-os-rollback/marketing-site:pre-e5e122a`
  (`sha256:014777142d8cae6074b13dfee5493f5e7e08f6901797164104292a1b05121c5b`).
- صورة Marketing السابقة مباشرة لـ`16f8f2c` محفوظة تحت
  `resort-os-rollback/marketing-site:pre-16f8f2c`، والـmanifest:
  `/var/backups/resort-os/marketing-source-releases/16f8f2c-rollback-image.txt`.
- صورة Marketing السابقة مباشرة لـ`0b0321f` محفوظة تحت
  `resort-os-rollback/marketing-site:pre-0b0321f`، والـmanifest:
  `/var/backups/resort-os/marketing-source-releases/0b0321f-rollback-image.txt`.
  release القديم `/opt/elkheima-marketing-releases/16f8f2c` لسه موجود كامل
  على القرص، مش متحذوف. لا migration ولا تغيير DB في هذه الحزمة (frontend
  فقط) فمفيش نسخة DB مخصوصة ليها.
- النسخة المشفرة خارج الخادم واستعادة 135 جدولًا ما زالتا دليل DR الأساسي.
- `resort-os-backup.timer`, `resort-os-certbot-renew.timer`,
  `resort-os-healthcheck.timer` مثبتة ومفعلة.
- أرشيف الإصدار الحالي:
  `/var/backups/resort-os/source-releases/a3e8abb.tar.gz`،
  SHA-256
  `2ff370284727ae57688c4efda9dad22db2729abf45fbbfe3dc276e78d7388bad`.
- صور ما قبل `a3e8abb` محفوظة تحت
  `resort-os-rollback/*:pre-a3e8abb`، والـmanifest المحمي:
  `/var/backups/resort-os/source-releases/a3e8abb-rollback-images.txt`،
  SHA-256
  `f904b6922081b17630814893708e39a543614d8652c2ce974922ec0fbd8f8fec`.
- نسخة DB السابقة مباشرة لنشر إصلاح الـPOS:
  `/var/backups/resort-os/database/resort_os_20260731_210536.dump`،
  SHA-256
  `5dd553f00433f0d7b70e3fcd54518c3c0c1770494efe6c4429dbd2858720aa1d`؛
  اجتازت `pg_restore --list`.
- نسخة DB السابقة مباشرة للقطع:
  `/var/backups/resort-os/database/resort_os_20260730_062529.dump`،
  SHA-256
  `bce5553a9b58d7a930c650c3f8618b7714a9a1db557e067977cc23beec10ab5a`؛
  اجتازت `pg_restore --list`.
- نسخة DB السابقة مباشرة لنشر Marketing:
  `/var/backups/resort-os/database/resort_os_20260730_143944.dump`،
  SHA-256
  `1358f16a526240b447bff98570a93eda9ee8933d8a94580ee5e8ec12c3987e04`؛
  اجتازت `pg_restore --list`.
- شُغلت خدمة healthcheck يدويًا بعد النشر ونجحت
  (`Result=success`, `ExecMainStatus=0`).
- أزيل فقط release staging غير الفعال
  `/opt/resort-os-releases/0b430fb` بعد إثبات عدم وجود symlink أو container
  يشير إليه. أرشيفه القابل للاستعادة ما زال محفوظًا تحت
  `/var/backups/resort-os/source-releases/0b430fb.tar.gz`.
- أرشيف إصدار `ddfbaaa` (دعم الطلب متعدد المنافذ + إصلاح مرتجع الإيراد):
  `/var/backups/resort-os/source-releases/ddfbaaa.tar.gz`،
  SHA-256
  `8aafedfd109a59e7ed72ea2c4ecc30b248d51af63f09198d0b0cd1629c1390d6`.
- صور ما قبل `ddfbaaa` (backend/celery_worker/celery_beat/el_kheima، كلها
  كانت `679f76e`) محفوظة تحت `resort-os-rollback/*:pre-ddfbaaa`، والـmanifest:
  `/var/backups/resort-os/source-releases/ddfbaaa-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `ddfbaaa`:
  `/var/backups/resort-os/database/resort_os_20260802_031105.dump`،
  SHA-256
  `7f65646441948e4250b9f141f6d01855e5516794507626eb09d5ebe4d97fd238`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `4a0a777` (إصلاح ضريبة الدخل في الرواتب، `backend`/
  `celery_worker`/`celery_beat` بس — `el_kheima` من `ddfbaaa` لم يتغيّر):
  `/var/backups/resort-os/source-releases/4a0a777.tar.gz`،
  SHA-256
  `a2638b2a0609cc3931e5e379a28e60823c5886b2213c472419672223227c6405`.
- صور ما قبل `4a0a777` (backend/celery_worker/celery_beat، كانوا `ddfbaaa`)
  محفوظة تحت `resort-os-rollback/*:pre-4a0a777`، والـmanifest:
  `/var/backups/resort-os/source-releases/4a0a777-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `4a0a777`:
  `/var/backups/resort-os/database/resort_os_20260802_034252.dump`،
  SHA-256
  `85f5e5fe300b5f90d49993bc820793e5e5258a2fb37ee35f663efb4784c5f8e7`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `8597535` (إصلاح باج تزامن استرداد نقاط الولاء في CRM،
  `backend`/`celery_worker`/`celery_beat` بس — `el_kheima` من `ddfbaaa`
  لم يتغيّر، صفر migration):
  `/var/backups/resort-os/source-releases/8597535.tar.gz`،
  SHA-256
  `4fcd0da28a3dd6067820315445755be6fcf31beab15114e961e7b5a2c1658320`.
- صور ما قبل `8597535` (backend/celery_worker/celery_beat، كانوا `4a0a777`)
  محفوظة تحت `resort-os-rollback/*:pre-8597535`، والـmanifest:
  `/var/backups/resort-os/source-releases/8597535-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `8597535`:
  `/var/backups/resort-os/database/resort_os_20260802_103152.dump`،
  SHA-256
  `5ecad84360934af560b617c25cdfa53b3730218342e1bce3f5e098b12196ebdc`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `b1db886` (موديول الصيانة: منع إغلاق أمر "مكتمل" عبر PATCH
  العادي + ربط تحرير الأصل بمسار الإلغاء — `backend`/`celery_worker`/
  `celery_beat`/`el_kheima` الأربعة، صفر migration):
  `/var/backups/resort-os/source-releases/b1db886.tar.gz`،
  SHA-256
  `da2bb917b3e7646c5635a4be8fe9edcfc5d80301a477385b93264d17b87cc36a`.
- صور ما قبل `b1db886` (backend/celery_worker/celery_beat/el_kheima، كانوا
  `8597535`/`ddfbaaa` بالترتيب) محفوظة تحت `resort-os-rollback/*:pre-b1db886`،
  والـmanifest: `/var/backups/resort-os/source-releases/b1db886-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `b1db886`:
  `/var/backups/resort-os/database/resort_os_20260802_105621.dump`،
  SHA-256
  `b838604a4db79f02dc099cfc2ef674eab0b6bc34364f2f344c10631cd8ffe472`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `0d55717` (موديول التحليلات: تحقق صارم على مدخلات تقييم
  الضيف العام — `backend`/`celery_worker`/`celery_beat` بس، `el_kheima`
  لم يتغيّر، صفر migration):
  `/var/backups/resort-os/source-releases/0d55717.tar.gz`،
  SHA-256
  `ba9788b147e44c0b19f03edd5541acfb54744d576a89cab71d249fba7ca3fc21`.
- صور ما قبل `0d55717` (backend/celery_worker/celery_beat، كانوا
  `b1db886`) محفوظة تحت `resort-os-rollback/*:pre-0d55717`، والـmanifest:
  `/var/backups/resort-os/source-releases/0d55717-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `0d55717`:
  `/var/backups/resort-os/database/resort_os_20260802_111432.dump`،
  SHA-256
  `c07404cc07489f3cd774938986db269ea5556f657a508ecf1cd4a0090979fa3a`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `4ca10c1` (موديول الإيجارات: تحصيل إيجار على عقد مفسوخ/
  منتهي عبر التسوية الكاش اليومية بقى مرفوض زي التحصيل العادي —
  `backend`/`celery_worker`/`celery_beat` بس، `el_kheima` لم يتغيّر، صفر
  migration):
  `/var/backups/resort-os/source-releases/4ca10c1.tar.gz`،
  SHA-256
  `e6c73575e7020a5676b6233777808211b0979bf55f87be1f986150ac9c945906`.
- صور ما قبل `4ca10c1` (backend/celery_worker/celery_beat، كانوا
  `0d55717`) محفوظة تحت `resort-os-rollback/*:pre-4ca10c1`، والـmanifest:
  `/var/backups/resort-os/source-releases/4ca10c1-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `4ca10c1`:
  `/var/backups/resort-os/database/resort_os_20260802_113200.dump`،
  SHA-256
  `d74442b6b78e52dd721b35b8427f6af0a354ef3e8f49fa61a2021e123418b870`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `5b02010` (موديول Hub: حذف كود مكرر كان بيسبب
  UnboundLocalError صامت في تأكيد الحجوزات الأونلاين — `backend`/
  `celery_worker`/`celery_beat` بس، `el_kheima` لم يتغيّر، صفر migration):
  `/var/backups/resort-os/source-releases/5b02010.tar.gz`،
  SHA-256
  `50538820d9b9e4ef9e3d724e45b09dfca4dfc86e25154a852fab98765900b673`.
- صور ما قبل `5b02010` (backend/celery_worker/celery_beat، كانوا
  `4ca10c1`) محفوظة تحت `resort-os-rollback/*:pre-5b02010`، والـmanifest:
  `/var/backups/resort-os/source-releases/5b02010-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `5b02010`:
  `/var/backups/resort-os/database/resort_os_20260802_115042.dump`،
  SHA-256
  `f2547e1b089c7e9706931536218be92868faf4622f0519e60c6870e364330f91`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).

## 9. الحالة المتبقية

| الحزمة | الحالة |
|---|---|
| REL-04 — staff-control-plane deploy | COMPLETE |
| REL-05 — multi-outlet POS fix deploy | COMPLETE |
| DATA-01-DEMO — realistic synthetic dataset | COMPLETE |
| CHAT-01 — chatbot activation/live verification | COMPLETE |
| DNS-01 — domain/TLS cutover | COMPLETE |
| DOC-OPS — management/staff Arabic training guide | COMPLETE |
| ACC-01 — employee/account workflow | DEPLOYED؛ ACCOUNTS PENDING ROSTER |
| UAT-01 — device/roles/workflow acceptance | PENDING |
| DATA-02 — approved real master data | PENDING OWNER/OPERATIONS REVIEW |
| OPS-01 — monitoring and burn-in | BASELINE COMPLETE؛ external delivery pending |
| provider snapshot | RECOMMENDED؛ DNS snapshot وoff-server DB موجودان |

لا توجد مشكلة تطبيق أو DNS أو TLS معروفة تستوجب rollback. لا يعني ذلك
اعتماد العمليات أو المالية؛ UAT والبيانات الحقيقية وقرار Go/No-Go تظل
مسؤولية المالك وممثلي التشغيل.
