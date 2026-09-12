# Handoff — DOC-VAULT-01 + Owner Mall Summary ready for release

**التاريخ:** 2026-09-12
**المنفذ والمراجع:** Codex
**الفرع:** `feat/doc-vault-private-storage`
**نقطة البداية:** `efd55a7`
**حالة الإنتاج وقت التسليم:** لم تتغير؛ Resort `76602f0`، Marketing
`e369bb4`، Alembic `d2e4f6a8c0b1`.

**تحديث rollout في اليوم نفسه:** recovery set وصور rollback وبناء الصور
نجحت، وطُبقت migration فأصبح Alembic الحي `9f6b1d3e5a70` مع بقاء الخدمات
القديمة صحية لحين الاستبدال. أصلح Codex سكربت أدوار Owner المقيدة قبل
التفعيل؛ الاختبار المعزول على PostgreSQL 16 مرّ مرتين متتاليتين وأثبت
least privilege المطلوب.

## النتيجة

مرشح الإصدار يحتوي خزنة وثائق كاملة للمنشأة والموظفين، وOwner projection
محدودة، ونسخة تعافي مزدوجة للـDB والملفات. كما يحتوي تبويب Owner حقيقيًا
للمول يعرض حقائق Leasing/Payments الحالية من دون انتظار Unit Registry ومن
دون اختراع إشغال أو تسريب بيانات مستأجر.

## DOC-VAULT-01

- private Docker volume عند `/app/private-documents`، غير مخدوم من Nginx
  ولا داخل `/uploads`.
- AES-GCM لكل ملف مع HKDF، اسم تخزين opaque، SHA-256/size verification،
  وفحص magic/MIME/extension/PDF EOF/Pillow قبل الحفظ.
- `documents` و`document_expiry_notifications` مع branch scope، UUID عام،
  version chain، soft delete/restore، وقيود DB تمنع الحالات غير الصحيحة.
- صلاحيات دقيقة منفصلة لوثائق المنشأة وHR، مع employee self-service
  `employee_visible` فقط وOwner `branch + owner_visible` فقط.
- Staff: `/admin/documents`، HR employee documents، `/portal/documents`.
- Owner: `/documents` قراءة وتنزيل فقط، authenticated verified streaming،
  وheaders `no-store`, `nosniff`, `CSP sandbox`.
- Celery expiry scan يوميًا 08:00 القاهرة، ledger idempotent عند 60/30/7/0.
- migration: `9f6b1d3e5a70_private_document_vault.py`.

## Owner Mall Summary

- endpoint: `GET /api/v1/owner/mall/summary`، branch من الجلسة،
  `OwnerReadDb`، و`Cache-Control: no-store`.
- screen: `/mall` داخل «المزيد»؛ تنقل الهاتف/التابلت يظل خمس وجهات رئيسية.
- الأرقام الحالية: scheduled rent حتى اليوم، accrued rent، collected rent،
  overdue receivables، contract counts/expiry، وPII-free contract cards.
- collected rent يأخذ `leasing_rent` وdirect `rent_payment/revenue_share`
  فقط؛ لا يخلط deposit/penalty/maintenance/refund بالإيجار المتحصل.
- لا tenant name/phone/national ID في schema أو response.
- `registered/occupied/vacant/occupancy` تظل `null` و`map_available=false`
  حتى اعتماد Unit Registry والخريطة؛ وصف الوحدة المعروض historical snapshot
  من العقد وليس سجل وحدات.

## Backup / Restore

- `scripts/backup_documents.sh`: tar للـciphertext فقط، checksum وmanifest،
  وصلاحيات خاصة.
- `scripts/backup_db.sh`: recovery set واحد DB dump + document archive +
  checksumين + combined manifest، مع retention/offsite sync للزوج.
- `scripts/restore_documents.sh`: checksum/manifest verification، استخراج
  آمن في staging، استبدال ذري، وrollback للدليل السابق عند الخطأ.
- `scripts/check_prod_health.sh`: يرفض آخر DB backup إذا لم يكن له زوج وثائق
  حديث ومتحقق منه.
- drill فعلي نجح: DB dump + document archive + manifest، ثم restore في دليل
  منفصل وbyte comparison مطابق، ووضع الملف المستعاد `0600`.

## Evidence

- Backend full: **3049 collected، 100%، exit 0**.
- Document + Owner Mall focused HTTP/security tests: ناجحة.
- Alembic: head واحد `9f6b1d3e5a70`؛ fresh PostgreSQL
  upgrade → head، downgrade → `d2e4f6a8c0b1`، re-upgrade → head ناجحة.
- Staff: i18n **6804/6804**، Vitest **111/111**، type-check/build ناجحان.
- Owner: type-check/build ناجحان، Playwright responsive **13/13** على
  320/390/768/1024/1280؛ اختبار `/mall` يتحقق من data-gate والـoverflow.
- `scripts/agent-check.sh --quick`: ناجح؛ **3049** test collected، Alembic
  head واحد، development/production Compose config وgit diff check ناجحة.
- `scripts/provision_owner_db_roles.sql`: اختبار isolated + idempotent
  ناجح؛ read role: documents SELECT=true/INSERT=false/audit INSERT=true؛
  metadata role: watchlist UPDATE=true/payments SELECT=false/audit
  INSERT=true. الأسرار مررت عبر stdin ولم تظهر في process arguments.

## Release checklist

1. راجع `git diff --check` و`scripts/agent-check.sh` ثم أنشئ commit صريحًا
   وادفع نفس الفرع؛ لا تنشر working tree غير مثبتة.
2. اتبع `DEPLOYMENT.md` immutable release فقط؛ احفظ exact pre-deploy source،
   rollback image IDs، وDB backup متحققًا منه.
3. أنشئ document volume وراجع ownership/permissions؛ لا تجعله public.
4. من مرشح الإصدار أنشئ recovery set pre-migration يشمل DB والـdocument
   vault الفارغ/الحالي، ثم نفذ `alembic upgrade 9f6b1d3e5a70`.
5. أعد تزويد Owner DB roles بعد migration ليأخذ `SELECT documents`، ثم
   rollout تدريجي Backend → Celery → Staff → Owner → edge عند الحاجة.
6. شغّل health/log/restart/HTTPS gates، ثم live smoke مصادق عليه للقائمة
   والتنزيل و`/owner/mall/summary` فقط؛ لا ترفع مستند تشغيل حقيقي كاختبار.
7. شغّل backup جديدًا بعد النشر وتحقق من الزوج والmanifest، ثم وثّق release
   SHA والصور وDB head والدليل الحي في production handoff.

## Rollback

- كود/صور: أعد symlink والصور المحفوظة لنقطة الإصدار السابقة بالتدرج.
- DB: `alembic downgrade d2e4f6a8c0b1` فقط إذا لم تُنشأ وثائق حقيقية بعد
  الإصدار. إذا أُنشئت وثائق، حافظ أولًا على recovery set للـDB والـciphertext
  المتطابقين ولا تفصل أحدهما عن الآخر.
- لا تحذف document volume أثناء rollback؛ بقاؤه آمن وغير public ويحفظ
  إمكانية forward recovery.

## المتبقي خارج هذا الإصدار

MALL-01 Unit Registry والخريطة وStaff CRUD ومنع تداخل عقود الوحدات ينتظرون
السجل والخريطة المعتمدين فقط. تبويب Owner Mall Summary نفسه منفذ ومختبر ولا
ينبغي حجبه بسبب data gate الخاصة بالوحدات.
