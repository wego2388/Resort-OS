# حالة المشروع الحالية — El Kheima Beach Resort OS

**آخر تحقق:** 2026-07-30 بعد نشر Timeshare وإصدار Marketing الجديد
**البيئة:** Production — `elkheima.com` / VPS `191.218.161.133`
**قائد التنفيذ والمراجع النهائي:** Codex

هذا الملف يسجل الحقائق الحالية فقط. التاريخ السابق محفوظ في
`docs/archive/2026-07-execution/`.

## 1. المصدر والإصدار

| البند | القيمة المثبتة |
|---|---|
| فرع العمل الوحيد | `claude/CX-02C-frontend-auth-bootstrap` |
| Resort OS source release | `679f76e` |
| Marketing source release | `16f8f2c` من المستودع المستقل |
| remote | فرع العمل يحتوي `679f76e` ثم تحديثات توثيق ما بعد النشر |
| `origin/main` | `598938e` — لم يُغيّر |
| active Resort release | `/opt/resort-os-releases/679f76e` |
| Resort current link | `/opt/resort-os-current -> /opt/resort-os-releases/679f76e` |
| active Marketing release | `/opt/elkheima-marketing-releases/16f8f2c` |
| Marketing current link | `/opt/elkheima-marketing-current -> /opt/elkheima-marketing-releases/16f8f2c` |
| Compose project / override | `resort-os-prod` / `docker-compose.prod.domain.yml` |

أرشيف Resort OS:
`/var/backups/resort-os/source-releases/679f76e.tar.gz`،
SHA-256
`3e8b9a2b88746f93dd578d17dc2f010c0c63e21ccb9a5f82c1c40bff856110a8`.

أرشيف Marketing:
`/var/backups/resort-os/marketing-source-releases/16f8f2c.tar.gz`،
SHA-256
`ba3d8d5c25c8487fb75906ce17ca3ffe8c0df9f0a087c0afefb478c9129cf7a9`.

مجلدا المصدر القديمان `/opt/resort-os` و
`/opt/elkheima-marketing-website` محفوظان كما كانا، وغير مستخدمين كمصدر
للإصدار الفعال ولم يُنظفا أو يُعاد ضبطهما.

## 2. الخدمات الفعالة

- الخدمات التي شملها الإصدار (`backend`, `celery_worker`, `celery_beat`,
  `el_kheima`, `nginx`) تحمل
  `com.docker.compose.project.working_dir=/opt/resort-os-releases/679f76e`.
- `marketing_site` مبني من المصدر المستقل `16f8f2c` عبر
  `/opt/elkheima-marketing-current`.
- Backend image:
  `sha256:7d27ae3a4b7daa38fe878b95c322bd1a7a1f2d5088990aa642163945441d73bc`.
- Celery worker:
  `sha256:371eb2eab1dac5ad18de738a30bd522daa916b412d4e9b4883ba2a148f9e18ea`.
- Celery beat:
  `sha256:df6030ab9d1679f0f16ca655c43d42bd99d16260d3f584bceb7664d4955bd794`.
- El Kheima staff app:
  `sha256:b638351fb3abebea2fa038cb39d26ab3c7632bf71f2e677b0830f27591e8feb1`.
- Marketing image:
  `sha256:277ff191eb630c4313ff728aabfda5e3fbc205c72432e97408b13c03d7358d2e`.
- Nginx:
  `sha256:97d490c12ba55b4946b01546d1c3ed324e8d41ab1c9fcb2a616aa470620e5b46`.
- 8 حاويات Running وكل healthchecks المعرّفة سليمة. الحاويات الثماني
  `RestartCount=0` بعد القطع.
- PostgreSQL وRedis بقيا على volumes والحاويات طويلة العمر ولم يُعاد
  إنشاؤهما أثناء cutover.

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
- النسخة المشفرة خارج الخادم واستعادة 135 جدولًا ما زالتا دليل DR الأساسي.
- `resort-os-backup.timer`, `resort-os-certbot-renew.timer`,
  `resort-os-healthcheck.timer` مثبتة ومفعلة.
- أرشيف الإصدار الحالي:
  `/var/backups/resort-os/source-releases/679f76e.tar.gz`،
  SHA-256
  `3e8b9a2b88746f93dd578d17dc2f010c0c63e21ccb9a5f82c1c40bff856110a8`.
- صور ما قبل `679f76e` محفوظة تحت
  `resort-os-rollback/*:pre-679f76e`، والـmanifest المحمي:
  `/var/backups/resort-os/source-releases/679f76e-rollback-images.txt`.
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

## 9. الحالة المتبقية

| الحزمة | الحالة |
|---|---|
| REL-04 — staff-control-plane deploy | COMPLETE |
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
