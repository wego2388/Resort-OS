# REL-02 — controlled production deployment

**التاريخ:** 2026-07-29
**المنفذ والمراجع النهائي:** Codex
**النتيجة:** COMPLETE / PASSED
**قرار التشغيل:** IP-only؛ لا DNS أو domain switch

## النتيجة

نُشر source commit `ac7764f` في release immutable:
`/opt/resort-os-releases/ac7764f`. الحاويات المحدثة تعمل من هذا المسار
وباستخدام `docker-compose.prod.yml` مع
`docker-compose.prod.ip-tls.yml`. لم يُبنَ أو يُنظف مجلد Git القديم
`/opt/resort-os`.

## المصدر

- Git branch: `claude/CX-02C-frontend-auth-bootstrap`
- remote head قبل النشر: `ac7764f`
- release archive:
  `/var/backups/resort-os/source-releases/ac7764f.tar.gz`
- archive size: `2,537,412` bytes
- archive SHA-256:
  `17251e23660d7f84d6e89bdb0e2a0b5986ff637f2768a2cbf82589462984d6e6`
- release `.env.prod` نُسخ من البيئة الحالية بصلاحية `0600` ولم تُعرض قيمه.
- عُدّل `MARKETING_SITE_CONTEXT` في نسخة env الخاصة بالـrelease فقط إلى
  المسار المطلق الموجود؛ env القديم لم يُعدّل.

## نقطة التراجع قبل النشر

- DB dump:
  `/opt/resort-os-releases/ac7764f/backups/resort_os_20260729_200809.dump`
- dump size: `539,394` bytes
- rollback image manifest:
  `/var/backups/resort-os/source-releases/ac7764f-rollback-images.txt`

| الخدمة | rollback tag | image ID |
|---|---|---|
| backend | `resort-os-rollback/backend:pre-ac7764f` | `sha256:933cc9a541b6d2cf645d6871cf9c6787720e7d4a9c0d8891fd9f13c3aad2456d` |
| celery worker | `resort-os-rollback/celery-worker:pre-ac7764f` | `sha256:c38acf18bba7cae4ee68fc1d1aa248a97543c3fafd5e63eb77b92e8d8d9864eb` |
| celery beat | `resort-os-rollback/celery-beat:pre-ac7764f` | `sha256:681cbb98f7e8cd3a134bbbf0f3be836ebfa0679a5abde78b96a7b15ec950585c` |
| El Kheima | `resort-os-rollback/el-kheima:pre-ac7764f` | `sha256:3377ad71f95aed76eef9e6e8bf574ab0e8245cafa16b224dd15dcb3f6518b378` |

نقطة DB مشفرة خارج الخادم وrestore drill الكامل موثقان في
`2026-07-29_DR-01_codex_handoff.md`.

## Preflight والترحيل

- `validate_prod_env.py`: passed.
- Compose config بالـIP-TLS override: passed.
- استيراد `app.main` من صورة backend الجديدة: `PREFLIGHT_OK`.
- رأس الكود الجديد: `88d1c505a9dc`.
- قاعدة الإنتاج كانت بالفعل عند `88d1c505a9dc` قبل أمر upgrade.
- `alembic upgrade head`: exit 0؛ لم يحتج تغييرًا إضافيًا.
- `/health` ظل سليمًا بعد خطوة Alembic.

## الصور الفعالة

| الخدمة | image ID | نتيجة الاستبدال |
|---|---|---|
| backend | `sha256:ea9d4fafc52f922a205500da1056f163e2e0d26b377568626af41e18ca438f29` | healthy، restarts=0 |
| celery worker | `sha256:5b074f225b4ed4dfedb27478f4e55b2738a9510756e0f09b18f8264c36ad6e1b` | healthy، restarts=0 |
| celery beat | `sha256:033e8413d972c29aed8836818e1b35e282c51a0ff76c67857907d15049071d20` | healthy، restarts=0 |
| El Kheima | `sha256:b92d5699f9389ecf9aff32eac1efbe357c7e6d02ec3122b4c333eb39c1dd9341` | healthy، restarts=0 |

الترتيب كان backend ثم Celery ثم El Kheima. أُعيد إنشاء Nginx بعد ذلك كي
يعيد حل عناوين الحاويات. PostgreSQL وRedis وmarketing site لم تُستبدل.

## تحقق ما بعد النشر

- 8/8 containers Running.
- `https://191.218.161.133/`: HTTP 200، title=`Resort OS`.
- `https://191.218.161.133:8443/`: HTTP 200، title=`El Kheima Beach`.
- `/health`: app/DB/Redis جميعها `ok`.
- Alembic: `88d1c505a9dc (head)`.
- read-only counts: users=1، branches=1، hub_online_bookings=0.
- لا توجد restore database مؤقتة باقية.
- المنافذ 5436/6381/8005 loopback-only.
- TLS SAN يطابق `191.218.161.133`.
- لا severe runtime logs في backend/Celery/Nginx خلال فحص ما بعد النشر.
- كل container محدث يحمل
  `com.docker.compose.project.working_dir=/opt/resort-os-releases/ac7764f`.

## قرار rollback

لم يُنفذ rollback لأن كل شروط القبول نجحت. إذا لزم rollback تطبيقي، تُعاد
الصور من tags أعلاه ويُعاد إنشاء Nginx. migration الأخيرة توسعة أعمدة فقط
وdowngrade الخاص بها no-op؛ لا تُستعاد DB إلا إذا ثبت فساد بيانات فعلي.

## المتبقي

- OPS-01: burn-in وتنبيهات HTTP/containers/backup/TLS/disk.
- UAT-01: جهاز وهاتف وأدوار ولغات وQR/offline/Night Audit/POS.
- DATA-01: master data معتمدة من المالك والتشغيل والمالية.
- provider snapshot موصى به، لكنه ليس بديلًا عن النسخة المشفرة المختبرة.
- لا domain/DNS ولا Chatbot activation ضمن هذا التسليم.
