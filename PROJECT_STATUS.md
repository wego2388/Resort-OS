# حالة المشروع الحالية — El Kheima Beach Resort OS

**آخر تحقق:** 2026-07-30 بعد نشر `32eb0f8` وزرع البيانات واختبار Chatbot
**البيئة:** Production IP-only — `191.218.161.133`
**قائد التنفيذ والمراجع النهائي:** Codex

هذا الملف يسجل الحقائق الحالية فقط. السجل المطوّل السابق مؤرشف في
`docs/archive/2026-07-execution/PROJECT_STATUS_HISTORY_THROUGH_2026-07-29.md`.

## 1. المصدر والإصدار

| البند | القيمة المثبتة |
|---|---|
| فرع العمل الوحيد | `claude/CX-02C-frontend-auth-bootstrap` |
| release source commit | Backend data release `32eb0f8` فوق baseline `ac7764f` |
| remote | `origin/claude/CX-02C-frontend-auth-bootstrap` عند `32eb0f8` |
| `origin/main` | `598938e` — لم يُغيّر |
| active Backend release directory | `/opt/resort-os-releases/32eb0f8` |
| release archive | `/var/backups/resort-os/source-releases/32eb0f8.tar.gz` |
| archive SHA-256 | `a1ba17a840afe15191451e21a3a08ee604147cb6b5722c582ed0f891e88c16e3` |
| Compose project | `resort-os-prod` |
| active override | `docker-compose.prod.ip-tls.yml` |

مجلد `/opt/resort-os` القديم ما زال محفوظًا كما كان: Git `0a13c97` مع
تعديلات runtime قديمة. لم يُستخدم `git reset` أو `rsync --delete` ولم يُبنَ
الإصدار الجديد فوقه.

## 2. الصور والخدمات الفعالة

| الخدمة | image ID | الحالة بعد النشر |
|---|---|---|
| backend | `sha256:17f27751b3cc8855c9fc936b281db58a81f80232ab2669b1eadf5190d6d0b4b4` | healthy، restarts=0 |
| celery_worker | `sha256:5b074f225b4ed4dfedb27478f4e55b2738a9510756e0f09b18f8264c36ad6e1b` | healthy، restarts=0 |
| celery_beat | `sha256:033e8413d972c29aed8836818e1b35e282c51a0ff76c67857907d15049071d20` | healthy، restarts=0 |
| el_kheima | `sha256:b92d5699f9389ecf9aff32eac1efbe357c7e6d02ec3122b4c333eb39c1dd9341` | healthy، restarts=0 |

حزمة `32eb0f8` غيّرت Backend فقط. بقيت صور Celery وEl Kheima وmarketing
وPostgreSQL وRedis كما هي لأن لا سلوك background أو schema تغير. أُعيد
تشغيل El Kheima وmarketing وNginx بالصور نفسها لإعادة حل Backend الجديد.

## 3. فحص الإنتاج

- 8 حاويات Running.
- `https://191.218.161.133/` يعيد 200 وعنوان الصفحة `Resort OS`.
- `https://191.218.161.133:8443/` يعيد 200 وعنوان الموقع `El Kheima Beach`.
- `/health` يعيد `status=ok` وDB/Redis كلاهما `ok`.
- Alembic current/head: `88d1c505a9dc`.
- importer marker: `synthetic_demo_dataset_seeded`، الإصدار
  `2026-07-30.1`، مرة واحدة فقط.
- إعادة تشغيل importer بالـconfirmation الصحيح أعادت `added={}`.
- لا توجد قاعدة restore مؤقتة باقية.
- لا `Traceback` أو `CRITICAL` أو `FATAL` أو Nginx emergency/alert في فحص
  السجلات بعد النشر.
- `resort-os-healthcheck.timer` enabled/active كل 5 دقائق؛ الفحص اليدوي
  عبر systemd نجح بـ14/14، وأول trigger تلقائي نجح
  `2026-07-29 20:45:55 UTC`؛ يغطي health وHTTPS والحاويات والنسخ وTLS والمساحة.
- PostgreSQL `5436` وRedis `6381` وBackend `8005` مربوطة بالـloopback؛
  المنافذ العامة هي SSH و80 و443 و8443.
- شهادة TLS تحمل SAN للـIP `191.218.161.133` وتنتهي
  `2026-08-02 09:59:28 UTC`. `certbot renew --dry-run` نجح والمؤقت يعمل كل
  12 ساعة.
- Chatbot E2E حي: إنشاء session، قبول AI disclosure، سؤال عربي تجريبي،
  رد Gemini، وإنهاء session؛ staff وmarketing وhealth جميعها 200/ok.

## 4. البيانات التجريبية المنشورة

البيانات synthetic وموسومة بوضوح وليست اعتمادًا ماليًا أو تشغيليًا نهائيًا.
اقتصر التطبيق على الفرع الفعال الوحيد `ELK-001` وبهوية
`super_admin` الفعالة، مع advisory lock وdry-run افتراضي وconfirmation
صريح للتطبيق.

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
أو أقساط timeshare/lease أو guest alerts أو notifications أو public
bookings. ملفات العد قبل وبعد متطابقة byte-for-byte:
`/var/backups/resort-os/source-releases/32eb0f8-pre-seed-counts.txt` و
`/var/backups/resort-os/source-releases/32eb0f8-post-seed-safety-counts.txt`.

## 5. أدلة الجودة

- full backend suite: 2217 tests collected، exit 0، صفر failure.
- production demo seed tests: 9 passed.
- PostgreSQL clean-schema apply + idempotency + safety checks: passed.
- استعادة dump الإنتاج الحقيقي في DB مؤقتة ثم apply/idempotency وعدم تغير
  المدفوعات وbeach transactions: passed؛ حُذفت DB وتأكد غيابها.
- targeted backend security/PMS/public/encryption: 63 passed.
- frontend: 93/93 عبر 13 ملف اختبار.
- frontend type-check: passed.
- production build: passed؛ تحذير chunk-size غير حاجب.
- `agent-check`: passed.
- Alembic single head: `88d1c505a9dc`.
- `git diff --check`: passed.

تحذير الاختبارات الوحيد المعروف هو `SECRET_KEY` الافتراضي داخل بيئة test،
ولا يصف سر الإنتاج.

## 6. النسخ والتراجع

- fresh pre-deploy dump:
  `/opt/resort-os-releases/ac7764f/backups/resort_os_20260729_200809.dump`.
- rollback image tags محفوظة تحت `resort-os-rollback/*:pre-ac7764f`.
- rollback image IDs موثقة في
  `/var/backups/resort-os/source-releases/ac7764f-rollback-images.txt`.
- exact old production source archive:
  `/var/backups/resort-os/source-snapshots/20260729T194312Z.tar.gz`.
- نسخة المصدر خارج الخادم:
  `/home/wego/backups/resort-os/production-source/20260729T194312Z.tar.gz`
  بالـSHA-256
  `71b7bb408b2e0be822d4f2e212fa26c37f32f8761b770d0585efd37e76ed50b3`.
- DB off-server مشفرة AES-256، وفكها كـstream طابق dump المصدر.
- isolated restore نجح إلى 135 جدولًا ثم حُذفت قاعدة الاختبار وتأكد غيابها.
- fresh pre-demo dump:
  `/opt/resort-os-releases/32eb0f8/backups/resort_os_20260729_233436.dump`.
- dump SHA-256:
  `dd7499b025bbd46ccdbd9b8544531b129a0be035e49f46c90483b75ee4f1b3ff`.
- نسخته المشفرة خارج الخادم:
  `/home/wego/backups/resort-os/database/resort_os_20260729_233436.dump.gpg`.
- Backend rollback:
  `resort-os-rollback/backend:pre-32eb0f8` =
  `sha256:ea9d4fafc52f922a205500da1056f163e2e0d26b377568626af41e18ca438f29`.

الترحيل الأخير توسعة أعمدة فقط، وdowngrade الخاص به no-op آمن؛ rollback
التطبيقي لا يحتاج تصغير الأعمدة.

## 7. DNS

مراجعة 30 يوليو كانت read-only ولم تغيّر أي سجل:

- `elkheima.com A = 2.57.91.91`؛ لا يزال عنوان الاستضافة القديمة.
- `www CNAME = elkheima.com` ولذلك يصل إلى العنوان القديم نفسه.
- لا AAAA ولا CAA وقت الفحص.
- لا MX أو TXT/DMARC/DKIM ظاهرة وقت الفحص؛ لا توجد خدمة بريد DNS مهيأة.
- nameservers: `pixel.dns-parking.com` و`byte.dns-parking.com`.
- عنوان VPS الحالي `191.218.161.133` غير موجود في سجلات الـdomain.
- HTTP على النطاقين يعيد 200 من المضيف القديم، لكن HTTPS على
  `elkheima.com` و`www.elkheima.com` يفشل حاليًا بـTLS internal alert.

أي cutover لاحق يحتاج: `A @ -> 191.218.161.133` مع إبقاء
`www CNAME -> elkheima.com`، ثم إصدار شهادة domain وتجهيز Nginx وإضافة
سجلات البريد فقط إن كانت الخدمة مطلوبة. لا يُستخدم Reset DNS ولا يُضاف
AAAA قبل IPv6 فعلي.

## 8. الحالة المتبقية

| الحزمة | الحالة |
|---|---|
| REL-02 — controlled deploy | COMPLETE |
| DATA-01-DEMO — realistic synthetic dataset | COMPLETE |
| CHAT-01 — chatbot activation/live verification | COMPLETE |
| UAT-01 — device/roles/workflow acceptance | PENDING |
| DATA-02 — approved real master data | PENDING OWNER/OPERATIONS REVIEW |
| OPS-01 — monitoring and burn-in | BASELINE COMPLETE؛ external delivery pending |
| DNS/domain cutover | REVIEWED, NOT CHANGED — still old host |
| provider snapshot | RECOMMENDED، ليس مانعًا بعد إثبات off-server restore |

لا توجد مشكلة تقنية معروفة تستوجب rollback الآن. لا يعني ذلك اعتماد
العمليات أو المالية؛ UAT والبيانات الحقيقية وقرار Go/No-Go ما زالت مسؤولية
المالك وممثلي التشغيل.
