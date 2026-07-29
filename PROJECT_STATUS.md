# حالة المشروع الحالية — El Kheima Beach Resort OS

**آخر تحقق:** 2026-07-29 بعد نشر `ac7764f`
**البيئة:** Production IP-only — `191.218.161.133`
**قائد التنفيذ والمراجع النهائي:** Codex

هذا الملف يسجل الحقائق الحالية فقط. السجل المطوّل السابق مؤرشف في
`docs/archive/2026-07-execution/PROJECT_STATUS_HISTORY_THROUGH_2026-07-29.md`.

## 1. المصدر والإصدار

| البند | القيمة المثبتة |
|---|---|
| فرع العمل الوحيد | `claude/CX-02C-frontend-auth-bootstrap` |
| release source commit | `ac7764f` |
| remote | `origin/claude/CX-02C-frontend-auth-bootstrap` عند `ac7764f` |
| `origin/main` | `598938e` — لم يُغيّر |
| release directory | `/opt/resort-os-releases/ac7764f` |
| release archive | `/var/backups/resort-os/source-releases/ac7764f.tar.gz` |
| archive SHA-256 | `17251e23660d7f84d6e89bdb0e2a0b5986ff637f2768a2cbf82589462984d6e6` |
| Compose project | `resort-os-prod` |
| active override | `docker-compose.prod.ip-tls.yml` |

مجلد `/opt/resort-os` القديم ما زال محفوظًا كما كان: Git `0a13c97` مع
تعديلات runtime قديمة. لم يُستخدم `git reset` أو `rsync --delete` ولم يُبنَ
الإصدار الجديد فوقه.

## 2. الصور والخدمات الفعالة

| الخدمة | image ID | الحالة بعد النشر |
|---|---|---|
| backend | `sha256:ea9d4fafc52f922a205500da1056f163e2e0d26b377568626af41e18ca438f29` | healthy، restarts=0 |
| celery_worker | `sha256:5b074f225b4ed4dfedb27478f4e55b2738a9510756e0f09b18f8264c36ad6e1b` | healthy، restarts=0 |
| celery_beat | `sha256:033e8413d972c29aed8836818e1b35e282c51a0ff76c67857907d15049071d20` | healthy، restarts=0 |
| el_kheima | `sha256:b92d5699f9389ecf9aff32eac1efbe357c7e6d02ec3122b4c333eb39c1dd9341` | healthy، restarts=0 |

`db_postgres` و`redis_cache` و`marketing_site` لم تُستبدل. أُعيد إنشاء Nginx
من release الجديد حتى يعيد حل عناوين الحاويات، وهو يعمل بلا restart.

## 3. فحص الإنتاج

- 8 حاويات Running.
- `https://191.218.161.133/` يعيد 200 وعنوان الصفحة `Resort OS`.
- `https://191.218.161.133:8443/` يعيد 200 وعنوان الموقع `El Kheima Beach`.
- `/health` يعيد `status=ok` وDB/Redis كلاهما `ok`.
- Alembic current/head: `88d1c505a9dc`.
- counts المقروءة فقط: `users=1`، `branches=1`،
  `hub_online_bookings=0`.
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

## 4. أدلة الجودة قبل النشر

- full backend suite: exit 0، صفر failure.
- targeted backend security/PMS/public/encryption: 63 passed.
- frontend: 93/93 عبر 13 ملف اختبار.
- frontend type-check: passed.
- production build: passed؛ تحذير chunk-size غير حاجب.
- `agent-check`: passed.
- Alembic single head: `88d1c505a9dc`.
- `git diff --check`: passed.

تحذير الاختبارات الوحيد المعروف هو `SECRET_KEY` الافتراضي داخل بيئة test،
ولا يصف سر الإنتاج.

## 5. النسخ والتراجع

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

الترحيل الأخير توسعة أعمدة فقط، وdowngrade الخاص به no-op آمن؛ rollback
التطبيقي لا يحتاج تصغير الأعمدة.

## 6. الحالة المتبقية

| الحزمة | الحالة |
|---|---|
| REL-02 — controlled deploy | COMPLETE |
| UAT-01 — device/roles/workflow acceptance | PENDING |
| DATA-01 — approved production master data | BLOCKED ON OWNER/OPERATIONS INPUT |
| OPS-01 — monitoring and burn-in | BASELINE COMPLETE؛ external delivery pending |
| DNS/domain cutover | PAUSED BY OWNER — IP-only |
| provider snapshot | RECOMMENDED، ليس مانعًا بعد إثبات off-server restore |

لا توجد مشكلة تقنية معروفة تستوجب rollback الآن. لا يعني ذلك اعتماد
العمليات أو المالية؛ UAT والبيانات الحقيقية وقرار Go/No-Go ما زالت مسؤولية
المالك وممثلي التشغيل.
