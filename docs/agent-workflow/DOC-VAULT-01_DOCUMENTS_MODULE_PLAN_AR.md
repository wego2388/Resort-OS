# DOC-VAULT-01 — خزنة الوثائق الرسمية المشفرة

**التاريخ:** 2026-09-12
**الحالة:** COMPLETE / DEPLOYED
**المنفذ:** Codex
**المعتمد:** Mohamed

## النتيجة

تم تنفيذ خزنة واحدة داخل `resort-os` لوثائق المنشأة وملفات الموظفين، مع
فصل كامل بين البيانات الوصفية في PostgreSQL والملفات المشفرة في volume خاص.
اكتمل rollout الإنتاج المرحلي عند release `1d2dc76` بعد recovery sets
وصور rollback متحقق منها؛ الـhead الحي `9f6b1d3e5a70`، والخدمات وفحوصات
الصحة والدخان الحي ناجحة.

## قرارات الأمان النهائية

- لا ملف تحت `/uploads` العامة ولا static URL للمستندات.
- AES-256-GCM بمفتاح مشتق بـHKDF من `FIELD_ENCRYPTION_KEY`، وAAD مرتبط
  بـUUID العام للوثيقة.
- اسم تخزين opaque، واسم الملف الأصلي مشفر في قاعدة البيانات، وSHA-256
  وحجم الملف محفوظان للتحقق قبل إرسال أول byte للعميل.
- PDF/JPEG/PNG/WebP فقط، بحد 20MB قابل للضبط؛ التحقق من magic bytes، MIME،
  الامتداد، EOF للـPDF، وبنية الصور عبر Pillow.
- الكتابة temp + fsync + atomic replace؛ أي فشل DB بعد الكتابة ينظف الملف.
- الفرع مشتق من الجلسة فقط، وكل lookup مقيد بالفرع والنطاق والموظف.
- الحذف منطقي؛ الملف المشفر لا يحذف، والاستعادة لا تتم إلا بعد فك تشفيره
  والتحقق من البصمة.
- كل استجابات المسارات الحساسة `no-store`، والـPWA لا يملك runtime cache
  للـAPI أو للملفات.

## قاعدة البيانات

Migration: `backend/alembic/versions/9f6b1d3e5a70_private_document_vault.py`

### `documents`

- مفتاح داخلي integer + `public_id` UUID غير قابل للتخمين.
- `branch_id` و`employee_id` بقيود `ON DELETE RESTRICT`.
- `scope`: `branch | employee` مع check يفرض وجود الموظف في النطاق الصحيح.
- `visibility`:
  - منشأة: `management | owner_visible`.
  - موظف: `hr_confidential | employee_visible`.
- metadata، تواريخ الإصدار/الانتهاء، MIME والحجم والبصمة.
- version chain عبر `replaces_document_id`, `version_number`, `superseded_at`.
- `uploaded_by`, `deleted_by`, timestamps وsoft delete.
- partial indexes للقوائم النشطة والموظف والانتهاء.

### `document_expiry_notifications`

دفتر idempotency بقاعدة فريدة:
`document_id + expiry_date + threshold_days`، والعتبات `60, 30, 7, -1`.

## الصلاحيات

| النطاق | العرض/التنزيل | الإدارة |
|---|---|---|
| وثائق المنشأة | supervisor/manager/admin/super_admin + `documents.branch:view` | manager/admin/super_admin + `documents.branch:manage` |
| وثائق الموظفين | hr_manager/admin/super_admin + `documents.employee:view` | نفس الأدوار + `documents.employee:manage` |
| مستندات الموظف الذاتية | موظف مرتبط بسجل HR | لا رفع أو تعديل أو حذف |
| تطبيق المالك | owner/super_admin؛ `owner_visible` فقط | لا كتابة |

المحاسب والكاشير والنادل والمدير العام لا يرون مستندات HR السرية. الموظف
لا يرى إلا `employee_visible` المرتبط بسجل HR الخاص بحسابه. كل اختلاف فرع
أو موظف يرجع 404 في lookup الحساس لمنع IDOR disclosure.

اتصال Owner بالإنتاج سيستخدم دوري PostgreSQL حقيقيين بدل fallback العام.
أُصلح سكربت provisioning ليستخدم `format(%L)` و`\gexec` خارج `DO $$`،
ويشترط متغيري السر قبل التنفيذ. اختبار PostgreSQL 16 المعزول مرّ مرتين
متتاليتين وأثبت أن `owner_read_role` يقرأ الوثائق ولا يكتبها، وأن
`owner_metadata_write_role` يحدّث جداول Owner فقط ولا يقرأ `payments`،
وكلاهما لا يملك سوى INSERT المطلوب على `audit_logs`.

## سطح الـAPI المنفذ

### Staff — المنشأة

- `POST /api/v1/documents/branch/upload`
- `GET /api/v1/documents/branch`
- `GET /api/v1/documents/branch/expiring`
- `GET /api/v1/documents/branch/deleted`
- `GET /api/v1/documents/branch/{id}`
- `GET /api/v1/documents/branch/{id}/download`
- `PATCH /api/v1/documents/branch/{id}`
- `DELETE /api/v1/documents/branch/{id}`
- `POST /api/v1/documents/branch/{id}/restore`

### HR والموظف

- رفع/قائمة/تنزيل/تعديل/حذف/استعادة تحت
  `/api/v1/documents/employee/{employee_id}/*`.
- `GET /api/v1/documents/me`
- `GET /api/v1/documents/me/{id}/download`

### Owner

- `GET /api/v1/owner/documents`
- `GET /api/v1/owner/documents/{id}/download`

لا يقبل أي endpoint من هذه المسارات `branch_id` من العميل كمصدر سلطة.

## تجربة المستخدم المنفذة

- Staff: `/admin/documents` للبحث والفلترة والتنبيه والرفع والتنزيل وسلة
  المحذوفات والاستعادة، بأهداف لمس ≥44px.
- HR: تبويب «المستندات» يظهر فقط لـHR/Admin مع اختيار الموظف ورفع/تنزيل/
  حذف/استعادة.
- Employee: `/portal/documents` قراءة وتنزيل فقط مع توضيح الخصوصية.
- Owner: `/documents` قراءة وتنزيل `owner_visible` فقط، وتنقل الهاتف أصبح
  خمس وجهات و«المزيد» للورديات والموظفين والمستندات.
- عربي/إنجليزي في Staff؛ RTL/light/dark/text-scale محفوظة في Owner.

## الانتهاء والتدقيق

- Celery Beat يشغل `documents-expiry-scan` يوميًا 08:00 بتوقيت القاهرة.
- القوائم تعرض المستندات المنتهية والقريبة حتى 60 يومًا؛ دفتر العتبات يمنع
  تكرار نفس event ويتيح توصيل قناة إشعار خارجية لاحقًا دون duplicate.
- Audit يغطي upload/list/view/download/update/delete/restore، لكنه لا يسجل
  العنوان أو الوصف أو اسم الملف أو المحتوى المفكوك.

## النسخ الاحتياطي والاستعادة

- `scripts/backup_db.sh` ينتج recovery set متزامن الاسم:
  DB dump + encrypted document tar + tar checksum + combined manifest.
- `scripts/backup_documents.sh` متاح لاختبار/نسخ الخزنة منفردة.
- `scripts/restore_documents.sh` يتحقق من checksum والمسارات وأنواع entries؛
  الهدف غير الفارغ يحتاج تأكيدًا ويحفظ النسخة السابقة بدل إتلافها.
- `scripts/check_prod_health.sh` يرفض DB backup حديثًا بلا زوج مستندات
  وmanifest متحقق منهما.

## أدلة التحقق المحلية

- Alembic upgrade → downgrade إلى `d2e4f6a8c0b1` → re-upgrade: ناجح.
- `alembic heads`: رأس واحد `9f6b1d3e5a70`.
- Backend: 3049 collected، وصل 100%، exit 0 بعد إضافة Owner Mall Summary
  لنفس مرشح الإصدار.
- Document/owner focused: ناجحة، وتشمل التشفير والتلاعب وMIME/size وIDOR
  والصلاحيات والمالك والحذف/الاستعادة وidempotency.
- Staff: i18n parity 6804/6804، Vitest 111/111، type-check وbuild ناجحان.
- Owner: type-check/build، وPlaywright responsive 13/13 على 320×568،
  390×844، 768×1024، 1024×768، 1280×800.
- backup/restore drill: checksum صحيح وbyte-for-byte comparison ناجح.

## أدلة الإنتاج

1. release immutable حي: `1d2dc766385645ecab1d15c61ebf8510aaf68801`.
2. recovery set قبل الترحيل `20260912_194415`، وقبل rollout بعد الترحيل
   `20260912_195843`، وبعد النشر `20260912_200557`؛ dump/tar/checksums ناجحة.
3. Alembic الحي `9f6b1d3e5a70`، والخدمات التسع Running، والصحية Healthy،
   وRestartCount=0، وhealth gate `16/16`.
4. volume `resort-os-prod_resort_documents` mounted عند
   `/app/private-documents` بصلاحية `0700` ومملوك للمستخدم `resortos`، ولا
   يوجد له mount في Nginx.
5. Owner roles المقيدة متصلة فعليًا من الصورة الحية؛ GET المصادق لملخص
   المول والوثائق نجح، و401 غير المصادق عليه يحمل `no-store`.
6. لا وثائق تشغيل رُفعت لأجل الاختبار؛ `documents=0` ودفتر الانتهاء=0.
