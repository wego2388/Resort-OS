# حالة المشروع الحالية — El Kheima Beach Resort OS

**آخر تحقق:** 2026-07-30 بعد DNS cutover ونشر الدومينات
**البيئة:** Production — `elkheima.com` / VPS `191.218.161.133`
**قائد التنفيذ والمراجع النهائي:** Codex

هذا الملف يسجل الحقائق الحالية فقط. التاريخ السابق محفوظ في
`docs/archive/2026-07-execution/`.

## 1. المصدر والإصدار

| البند | القيمة المثبتة |
|---|---|
| فرع العمل الوحيد | `claude/CX-02C-frontend-auth-bootstrap` |
| Resort OS source release | `05ee627` |
| Marketing source release | `e5e122a` من المستودع المستقل |
| remote | فرع العمل يحتوي `05ee627` ثم تحديثات توثيق ما بعد النشر |
| `origin/main` | `598938e` — لم يُغيّر |
| active Resort release | `/opt/resort-os-releases/05ee627` |
| Resort current link | `/opt/resort-os-current -> /opt/resort-os-releases/05ee627` |
| active Marketing release | `/opt/elkheima-marketing-releases/e5e122a` |
| Marketing current link | `/opt/elkheima-marketing-current -> /opt/elkheima-marketing-releases/e5e122a` |
| Compose project / override | `resort-os-prod` / `docker-compose.prod.domain.yml` |

أرشيف Resort OS:
`/var/backups/resort-os/source-releases/05ee627.tar.gz`،
SHA-256
`d8354ec5b48e69a284dc6a6194967ca788f290fe508ba4fd30af0c5bf6946c5b`.

أرشيف Marketing:
`/var/backups/resort-os/marketing-source-releases/e5e122a.tar.gz`،
SHA-256
`357d28e5a4fab05650f19ba0b9f5f82ea6f10e13e29633d47cad388b45e2aaa2`.

مجلدا المصدر القديمان `/opt/resort-os` و
`/opt/elkheima-marketing-website` محفوظان كما كانا، وغير مستخدمين كمصدر
للإصدار الفعال ولم يُنظفا أو يُعاد ضبطهما.

## 2. الخدمات الفعالة

- كل خدمات التطبيق (`backend`, `celery_worker`, `celery_beat`, `el_kheima`,
  `marketing_site`, `nginx`) تحمل
  `com.docker.compose.project.working_dir=/opt/resort-os-releases/05ee627`.
- Backend image:
  `sha256:17f27751b3cc8855c9fc936b281db58a81f80232ab2669b1eadf5190d6d0b4b4`.
- Celery worker:
  `sha256:5b074f225b4ed4dfedb27478f4e55b2738a9510756e0f09b18f8264c36ad6e1b`.
- Celery beat:
  `sha256:033e8413d972c29aed8836818e1b35e282c51a0ff76c67857907d15049071d20`.
- El Kheima staff app:
  `sha256:f6045dd466411eb6bd600910b4c9ef610cd074e685882116fd5f2f8d1e2a73d2`.
- Marketing image:
  `sha256:ceffe9aff37f51cdf3a566d144eedad3acb94ab2665acf59f6fe0c04169cb0db`.
- Nginx:
  `sha256:97d490c12ba55b4946b01546d1c3ed324e8d41ab1c9fcb2a616aa470620e5b46`.
- 8 حاويات Running وكل healthchecks سليمة. خدمات التطبيق كلها
  `RestartCount=0` بعد التوحيد على الإصدار النهائي.
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
- فحص logs النهائي لخدمات backend/worker/beat/staff/marketing/nginx:
  صفر أنماط severe ضمن نافذة الفحص.

## 5. البيانات التجريبية المنشورة

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
`super_admin: total=1, active=1`. لا توجد حسابات موظفين منشأة حتى الآن،
ولم تُعرض أي بيانات اعتماد في التوثيق أو الفحص. إنشاء الحسابات ينتظر
أسماء وبريد وأدوار أشخاص حقيقيين، وفق `docs/STAFF_APP_GUIDE_AR.md`.

## 6. أدلة الجودة

- full backend suite: 2217 tests collected، exit 0، صفر failure.
- production demo seed tests: 9 passed.
- PostgreSQL clean-schema apply + idempotency + safety checks: passed.
- استعادة dump حقيقية واختبار importer عليها ثم تنظيف DB المؤقتة: passed.
- targeted backend security/PMS/public/encryption: 63 passed.
- frontend: 93/93 عبر 13 ملف اختبار.
- frontend type-check وproduction build: passed.
- Marketing `truth`, `type-check`, `build`: passed.
- `agent-check`: passed بعد تغييرات النشر؛ Alembic single head
  `88d1c505a9dc`؛ `git diff --check`: passed.
- دليل الإدارة وتدريب الموظفين العربي محدث، ودليل السوبر أدمن مصحح بحسب
  مسار إنشاء الحسابات و2FA وStep-Up الحالي.

## 7. النسخ والتراجع

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
- النسخة المشفرة خارج الخادم واستعادة 135 جدولًا ما زالتا دليل DR الأساسي.
- `resort-os-backup.timer`, `resort-os-certbot-renew.timer`,
  `resort-os-healthcheck.timer` مثبتة ومفعلة.
- آخر نسخة DB بعد الفحص النهائي:
  `/var/backups/resort-os/resort_os_20260730_043330.dump`،
  SHA-256
  `a31e43e74d777ec41a93ca30a4ec3270b2f1995fb34846b36591498a4e23b72d`؛
  اجتازت `pg_restore --list` داخل PostgreSQL 16 معزول.
- شُغلت خدمتا backup وhealthcheck يدويًا بعد النشر ونجحتا.
- أزيل فقط release staging غير الفعال
  `/opt/resort-os-releases/0b430fb` بعد إثبات عدم وجود symlink أو container
  يشير إليه. أرشيفه القابل للاستعادة ما زال محفوظًا تحت
  `/var/backups/resort-os/source-releases/0b430fb.tar.gz`.

## 8. الحالة المتبقية

| الحزمة | الحالة |
|---|---|
| REL-02 — controlled deploy | COMPLETE |
| DATA-01-DEMO — realistic synthetic dataset | COMPLETE |
| CHAT-01 — chatbot activation/live verification | COMPLETE |
| DNS-01 — domain/TLS cutover | COMPLETE |
| DOC-OPS — management/staff Arabic training guide | COMPLETE |
| ACC-01 — named staff accounts + backup super-admin | PENDING OWNER LIST |
| UAT-01 — device/roles/workflow acceptance | PENDING |
| DATA-02 — approved real master data | PENDING OWNER/OPERATIONS REVIEW |
| OPS-01 — monitoring and burn-in | BASELINE COMPLETE؛ external delivery pending |
| provider snapshot | RECOMMENDED؛ DNS snapshot وoff-server DB موجودان |

لا توجد مشكلة تطبيق أو DNS أو TLS معروفة تستوجب rollback. لا يعني ذلك
اعتماد العمليات أو المالية؛ UAT والبيانات الحقيقية وقرار Go/No-Go تظل
مسؤولية المالك وممثلي التشغيل.
