# Handoff — DOC-VAULT-01 + Owner Mall Summary production release

**التاريخ:** 2026-09-12
**المنفذ والمراجع:** Codex
**الفرع:** `feat/doc-vault-private-storage`
**Release commit:** `1d2dc766385645ecab1d15c61ebf8510aaf68801`
**الحالة:** COMPLETE / DEPLOYED / VERIFIED

## النتيجة الحية

- `/opt/resort-os-current` يشير إلى
  `/opt/resort-os-releases/1d2dc766385645ecab1d15c61ebf8510aaf68801`.
- Alembic الحي: `9f6b1d3e5a70`.
- خزنة الوثائق المشفرة وواجهات Staff/HR/Employee/Owner منشورة.
- Owner `/mall` و`GET /api/v1/owner/mall/summary` منشوران.
- Marketing لم يُبنَ أو يُستبدل؛ بقي عند `e369bb4` كما هو مطلوب.

## الحفظ قبل التغيير

- exact source archive:
  `/var/backups/resort-os/source-releases/resort-os-1d2dc766385645ecab1d15c61ebf8510aaf68801.tar.gz`
- SHA-256 للأرشيف:
  `2164a5c5ed24db204caa6a34c19e574e31beae8424e8dfd9765a07deb9c53ea2`
- rollback image manifest:
  `/var/backups/resort-os/source-releases/1d2dc766385645ecab1d15c61ebf8510aaf68801-rollback-images.txt`
- recovery set قبل migration: `20260912_194415`؛ dump قابل للقراءة بـ
  `pg_restore --list` وزوج الوثائق/checksums متحقق.
- recovery set بعد migration وقبل replacement: `20260912_195843`؛ متحقق.
- recovery set بعد النشر: `20260912_200557`؛ DB dump + encrypted document
  archive + checksum + combined manifest كلها متحققة.

## أمان قاعدة البيانات

- migration `d2e4f6a8c0b1 → 9f6b1d3e5a70` نجحت قبل استبدال الخدمات؛ التغيير
  additive وبقي الإصدار القديم صحيًا أثناء البوابة.
- أصلح `scripts/provision_owner_db_roles.sql` ثم اختُبر مرتين على PostgreSQL
  16 معزول قبل الإنتاج.
- فُعّل `owner_read_role` و`owner_metadata_write_role` بأسرار عشوائية داخل
  `.env.prod` ذي mode `0600`، من دون طباعة الأسرار أو وضعها في process args.
- إثبات least privilege الحي:
  - read: documents SELECT=true، documents INSERT=false، audit INSERT=true.
  - metadata: watchlist UPDATE=true، payments SELECT=false، audit INSERT=true.
- صورة التطبيق المرشحة ثم الحاوية الحية اتصلتا فعليًا بالاسمين المقيدين؛
  لا fallback إلى مستخدم قاعدة البيانات العام.

## الـvolume والنسخ الاحتياطي

- named volume: `resort-os-prod_resort_documents`.
- mount: `/app/private-documents` على Backend فقط، writable للمستخدم
  `resortos`، owner `resortos:resortos`، mode `0700`.
- لا mount للـdocument volume في Nginx ولا static URL له.
- لم نرفع مستند تشغيل تجريبي؛ وقت التسليم `documents=0` و
  `document_expiry_notifications=0`.
- Celery Beat الحي يحمل `documents-expiry-scan` ويشير إلى
  `app.tasks.document_tasks.scan_expiry_notifications`.

## صور الإصدار الحية

- Backend + Celery worker + Celery beat:
  `sha256:9565b7da3f2d61fa472b6c226b64f7644bad1682317ef836b6fdf9183a3f8056`
  وrevision label يطابق release commit.
- Staff: `sha256:c8f39b7a5e9fb2cedf5e95a3f9f0a6b6ee66b868c5f0196d994e78f4e02ac60e`.
- Owner: `sha256:0206061b96b2ea224749884c13a43e9fc0600dea88751956310cda53ca87cf8a`.
- Marketing بقي:
  `sha256:91c8b8092f9bc3c427f01ba6bcf55d43b0e184162c6d5f3bfcf51e286a8340fb`.
- Edge Nginx بقي على الصورة
  `sha256:97d490c12ba55b4946b01546d1c3ed324e8d41ab1c9fcb2a616aa470620e5b46`
  وأعيد إنشاؤه لالتقاط الحاويات الجديدة.

## أدلة التحقق

- محلي قبل الإصدار: Backend 3049 collected ووصل 100% بلا فشل؛ Staff
  111/111؛ i18n 6804/6804؛ Owner responsive 13/13؛ type-check/build ناجحة؛
  Alembic fresh upgrade/downgrade/re-upgrade ناجح؛ backup/restore byte drill
  ناجح؛ `agent-check --quick` ناجح.
- الإنتاج: 9 containers Running، الصحية منها Healthy، RestartCount=0، ولا
  failed systemd units. backup وhealth timers active.
- health service: `Result=success`, `ExecMainStatus=0`, passes=`16`.
- `elkheima.com`, `www.elkheima.com`, `app.elkheima.com`,
  `owner.elkheima.com` كلها HTTPS 200؛ Owner `/mall` و`/documents` 200.
- المسارات الحساسة غير المصادق عليها ترجع 401 وتحمل `Cache-Control:
  no-store`.
- smoke مصادق عبر SuperAdmin موجود وفعال نجح لملخص المول والوثائق: response
  200، لا tenant name/phone/email/national ID، ووحدات/إشغال/خريطة بقيت
  unknown حتى اعتماد master data. وقت الاختبار لا توجد عقود أو وثائق في
  الفرع، فنجحت empty states بلا اختراع أرقام.
- لا Traceback/CRITICAL/ERROR غير متوقع في Backend/Celery/Staff/Owner/Edge.
  التحذير القديم الوحيد هو غياب مفاتيح Sentry وTwilio الخاصة ببوابة
  الملكية الجزئية؛ يحتاج أسرارًا/قرار قناة خارجيًا ولا يعطل هذا الإصدار.
- منافذ PostgreSQL/Redis/Backend بقيت loopback-only عند 5436/6381/8005؛
  القرص مستخدم 13% فقط.

## Rollback

1. استخدم الصور تحت `resort-os-rollback/*:pre-1d2dc766...` والmanifest
   المسجل، وأعد symlink إلى release `76602f0` إذا لزم rollback للكود.
2. اترك migration الإضافية وdocument volume كما هما في rollback العادي؛
   الإصدار السابق متوافق مع الإضافة، وترك ciphertext يحفظ forward recovery.
3. لا downgrade إلى `d2e4f6a8c0b1` إلا بقرار صريح وبعد إثبات عدم وجود وثائق
   جديدة وأخذ recovery set متطابق للـDB والـvolume.
4. recovery set السابق للترحيل `20260912_194415` هو نقطة التعافي الكاملة
   عند الحاجة لرجوع شامل منسق.

## المتبقي خارج الإصدار

تبويب المول نفسه مكتمل ومنشور. المتبقي فقط من MALL-01 هو Unit Registry
والخريطة وStaff CRUD ونسبة الإشغال الحقيقية، وكلها متوقفة عمدًا على ملف
الوحدات وSVG/geometry المعتمدين من Mohamed؛ لا يجوز اشتقاقها من العقود.
