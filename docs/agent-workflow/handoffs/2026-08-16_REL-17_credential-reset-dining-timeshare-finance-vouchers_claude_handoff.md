# REL-17 — استرداد الدخول + إصلاحات دايننج/تيم شير + سندات محاسبية

**التاريخ:** 2026-08-16
**المنفّذ:** Claude (executive-authority session، متابعة لـREL-16 في نفس اليوم)
**الفرع:** `codex/rel-15-auth-ops-readiness`
**Implementation/Release commit:** `3f44a14a93d3863a8e287ed757da78a4e29d6ca3`

## 1. الدافع

طلبات صريحة من Mohamed خلال جلسة واحدة متصلة:

1. حل قفل حساب المحاسب "يوسف رمضان بخيت" (سبب حقيقي: محاولات باسورد خاطئة
   متكررة) + بناء شاشة/أداة في السوبرادمن تسهّل استرداد أي موظف عادي
   (الأداة الوحيدة الموجودة كانت CLI مقصورة على `super_admin`/`owner`).
2. فحص كاشير الدايننج لمشكلة "مينفعش يضيف أوردر تاني لو الفاتورة مفتوحة"
   + إصلاح أي مشكلة تانية ملاحظة في الكاشير عمومًا.
3. فحص التيم شير: عند تأكيد زيارة، لازم تكون خريطة الغرف موجودة عشان
   الموظف يحدد الزيارة عليها بدل تعيين تلقائي أعمى بالكامل.
4. بعد نقاش عن أنواع السندات المحاسبية المصرية القياسية (سند الصرف/
   القبض/الدفع/الاستلام/المصروفات...): **"انا عايز المحاسب و الحسابات
   يكون حقيقي و كامل 1و 2 و 3و"** — بناء 3 ميزات محاسبية كاملة وحقيقية:
   قيد يدوي، مصروفات مصنّفة، تتبع دفعات الموردين.

## 2. التنفيذ

### 2.1 استرداد بيانات دخول الموظفين

- `backend/app/modules/core/services.py::reset_staff_credentials` —
  يقفل صف المستخدم، يرفض صراحة أي هدف `role in BOOTSTRAP_CREATABLE_ROLES`
  (`super_admin`/`owner` — نفس حدود CLI bootstrap بالظبط)، يولّد باسورد
  مؤقت (`AuthService._new_temporary_password()`) + enrollment token جديد
  لو الدور ضمن `MANDATORY_2FA_ROLES`، يمسح حقول القفل، يحذف
  `TwoFactorRecoveryCode`s + refresh tokens القديمة، يكتب
  `AuditLog(action="reset_staff_credentials")`.
- `POST /users/{user_id}/reset-credentials` — محمي step-up (purpose
  `staff_credentials_reset`)، `get_super_admin_user`.
- زرار جديد في `SuperAdminView.vue` لكل صف موظف (مخفي لصفوف
  super_admin/owner)، بيعيد استخدام مودال نتيجة الـbootstrap الموجود.
- 7 اختبار جديد (`TestResetStaffCredentials`).

### 2.2 كاشير الدايننج — إضافة أصناف لطلب مفتوح

- "وضع الإضافة" جديد في `POSCartPanel.vue` — يعيد استخدام نفس شاشة بناء
  السلة الموجودة (مفيش تكرار لمنطق تصفح المنيو)، بيخفي الخصم/الإرسال/
  الدفع، ويعرض تأكيد/إلغاء بس.
- زرار "➕ إضافة أصناف للفاتورة" جديد في `DiningOrderDetailModal.vue`
  (ظاهر للحالات held/open/in_kitchen/served).
- `UnifiedPOSView.vue` — `sendAppendedItems()` بيستخدم
  `POST /dining/orders/{id}/items` الموجود بالفعل.

### 2.3 التيم شير — خريطة وحدات عند تأكيد الزيارة

- `GET /timeshare/units/availability` جديد (`branch_id`, `unit_type`,
  `check_in`, `check_out`) — يرجع كل الوحدات من النوع ده مع `is_available`.
- `TimeshareUnitPicker.vue` جديد — شبكة وحدات قابلة للاختيار، مربوطة
  في مودالي الموافقة (`approveModal`) والجدولة (`scheduleModal`) في
  `TimeshareView.vue`.
- `services.create_visit` اتعملها rewrite جزئي: عقد وحدة ثابتة يرفض
  اختيار يدوي مخالف (رسالة عربية واضحة)، عقد floating مع اختيار يدوي
  يتحقق من تطابق الفرع/النوع قبل الاستخدام، وعدم الاختيار = نفس السلوك
  القديم (`find_available_unit` التلقائي، بما فيه منطق Family Compound
  المزدوج).
- 11 اختبار جديد (8 service-level + 3 HTTP).

### 2.4 3 سندات محاسبية

**سند القيد اليدوي** — واجهة حقيقية أول مرة لـ`POST /finance/journal-entries`
الموجود من قبل بلا أي مستهلك frontend. تاب جديد في `FinanceView.vue` بميزان
مدين/دائن حي.

**سند المصروفات** — `finance.Expense` (جدول جديد)، `crud.create_expense`/
`list_expenses`، `services.record_expense` (يستدعي
`post_simple_revenue_journal(..., strict=True)` +
`validate_period_open` صراحة — فعل محاسبي يبدأه محاسب بشريًا، مش ترحيل
تلقائي من نقطة بيع فلازم يفشل بوضوح لا يبتلع الخطأ). الفئة = حساب حقيقي
من دليل الحسابات، مفيش enum موازي. `POST/GET /finance/expenses`، تاب
جديد في `FinanceView.vue`.

**سند دفع الموردين** — فجوة محاسبية حقيقية اتكشفت: `receive_purchase_order`
يرحّل Dr.1200(مخزون)/Cr.2200(ذمم دائنة) عند الاستلام من الأساس، لكن مفيش
أي endpoint كان موجود لتسجيل سداد الذمة دي أبدًا. `inventory.SupplierPayment`
(جدول جديد) + `PurchaseOrder.amount_paid`/`payment_status`،
`services.pay_purchase_order` (نفس نمط `strict=True` +
`validate_period_open`) يقفل الذمة (Dr.2200/Cr.حساب التسوية).
`POST /inventory/purchase-orders/{id}/pay` + `GET .../payments`. شاشة
"مستحقات الموردين" جديدة في `InventoryView.vue`.

**Migration** `79d4d53e7109` (down_revision `a7b3f2c8e9d1`) — إضافية
بحتة: `expenses`، `supplier_payments`،
`purchase_orders.amount_paid`/`payment_status`. اتأكدت فعليًا على
Postgres حقيقي (upgrade→verify→downgrade→re-upgrade، قاعدة بيانات
معزولة مؤقتة).

### 2.5 تصحيح ذاتي أثناء العمل — مهم للسجل

أثناء إدراج `Expense` model في `finance/models.py`، انتقل سطر
`submitted_at` بالخطأ من نهاية `ETAInvoice` إلى نهاية `Expense`
الجديد (edit displacement — نتيجة صحيحة نحويًا لكنها كسرت schema
`ETAInvoice` فعليًا). اكتُشف فقط عند تشغيل **مجموعة الاختبارات الكاملة**
(اختبار غير مرتبط، `TestETAInvoiceHTTPFlow`، فشل بـ
`pydantic ValidationError: submitted_at Field required`). تم التحقق من
جذر السبب عبر `git stash` (تأكيد الفشل غير موجود في الأساس النظيف)،
ثم الإصلاح، ثم إعادة تدقيق كل الـdiffs الكبيرة الأخرى بحثًا عن نفس
النمط (لم يوجد أي حالة أخرى)، ثم إعادة تشغيل المجموعة الكاملة
(2947 مجمّعة، صفر فشل).

## 3. البوابات (محليًا، قبل أي نشر)

```
backend  pytest tests/ -q                    → صفر فشل (2947 test collected)
backend  scripts/agent-check.sh               → PASS (alembic heads = 79d4d53e7109)
backend  git diff --check                     → نظيف
frontend pnpm run type-check:all               → نظيف (el-kheima + owner)
frontend validate-i18n.mjs                     → 6445 مفتاح/لغة، صفر ناقص
frontend pnpm --filter el-kheima test:frontend → 106/106 (بعد إصلاح باج
                                                  dark-mode contrast حقيقي
                                                  في تاب المصروفات الجديد)
frontend pnpm --filter el-kheima test:e2e:mock → 8/8
frontend pnpm run build:all                    → نظيف (el-kheima + owner)
```

## 4. سجل النشر على VPS

**Release commit:** `3f44a14a93d3863a8e287ed757da78a4e29d6ca3`
**Release directory:** `/opt/resort-os-releases/3f44a14a93d3863a8e287ed757da78a4e29d6ca3`
**`/opt/resort-os-current`:** تم تحديثه ليشير للإصدار الجديد بعد نجاح النشر.

### 4.1 القراءة قبل النشر

الإصدار الفعال قبل النشر: `43eae4cac3a50feb44308d5482e7ba77cafb74a2`
(REL-16)، كل الـcontainers healthy، صفر unit فاشل خاص بـresort-os
(`wegodivers-healthcheck.service` الفاشل مشروع تاني منفصل)، القرص 54%.

### 4.2 الأرشيف والتحقق

```
SHA-256 (local)  = 37527bb2f43682f2109aa37df0751e2e7cf7730f5296dbc936f05511874a5339
SHA-256 (remote) = 37527bb2f43682f2109aa37df0751e2e7cf7730f5296dbc936f05511874a5339  (مطابق)
```

نُسخ إلى `/var/backups/resort-os/source-releases/3f44a14....tar.gz`، ثم
استُخرج في `/opt/resort-os-releases/3f44a14...` (دليل جديد، لم يُستبدل
أي دليل قائم). `.env.prod` نُسخ من الإصدار النشط الحالي بصلاحية `0600`
بدون عرضه. `MARKETING_SITE_CONTEXT` تأكد أنه يشير لـ
`/opt/elkheima-marketing-current`. `validate_prod_env.py` → PASS.

### 4.3 نقطة الرجوع

Rollback images manifest:
`/var/backups/resort-os/source-releases/3f44a14...-rollback-images.txt`
— 7 صور (`backend`, `celery-worker`, `celery-beat`, `el-kheima`, `owner`,
`nginx`, `marketing-site`) موسومة بـ
`resort-os-rollback/<name>:pre-3f44a14...` مع الـimage IDs الكاملة.

Database backup:
`/opt/resort-os-releases/43eae4c.../backups/resort_os_20260816_162148.dump`
(756K) — تم التحقق منه فعليًا عبر `pg_restore --list` (1557 TOC entries،
1568 سطر) قبل المتابعة.

### 4.4 البناء والفحص المسبق

```
docker compose build --parallel backend el_kheima owner   → نجح
backend run: python -c 'from app.main import app; ...'    → "El Kheima Beach"
backend run: alembic heads                                 → 79d4d53e7109 (head)
```

### 4.5 الترحيل (Migration)

```
docker compose run --rm backend alembic upgrade head
→ Running upgrade a7b3f2c8e9d1 -> 79d4d53e7109,
  Organized expense vouchers + supplier payable settlement
```

تحقق مباشر بعد الترحيل:

```sql
SELECT version_num FROM alembic_version;        → 79d4d53e7109
SELECT to_regclass('public.expenses');            → expenses
SELECT to_regclass('public.supplier_payments');    → supplier_payments
-- purchase_orders.amount_paid / payment_status موجودين
```

### 4.6 الاستبدال المحكوم (بالترتيب)

```
up -d --no-deps backend                          → healthy، RestartCount=0
up -d --no-deps celery_worker celery_beat        → healthy، RestartCount=0
up -d --no-deps el_kheima owner                  → healthy، RestartCount=0
up -d --no-deps --force-recreate nginx           → up، RestartCount=0
```

لم تُعاد PostgreSQL أو Redis في أي خطوة.

### 4.7 قبول ما بعد النشر

- `backend`/`celery_worker`/`celery_beat` الثلاثة على نفس الـimage ID
  (`sha256:249c0bac...`) و`org.opencontainers.image.revision` =
  `3f44a14a93d3863a8e287ed757da78a4e29d6ca3` بالظبط.
- الأربع نطاقات (`elkheima.com`, `www.elkheima.com`, `app.elkheima.com`,
  `owner.elkheima.com`) → `HTTP/2 200`. `app.elkheima.com/health` → ok
  (database/redis ok).
- `docker exec backend alembic current` → `79d4d53e7109 (head)`.
- عدد حقيقي (بدون بيانات تجريبية): `users=24`, `branches=1`.
- `RestartCount=0` على الستة containers كلهم.
- `working_dir` label للـbackend يشير للإصدار الجديد.
- TLS SAN يحتوي الأربع نطاقات بالظبط.
- منافذ Postgres/Redis مربوطة `127.0.0.1` فقط (loopback).
- صفر traceback/critical/fatal/emergency جديد في لوجات
  backend/celery/nginx (المطابقة الوحيدة كانت اسم task
  `notify_critical_work_order` في قائمة تسجيل Celery — إيجابية كاذبة).
- صفر قاعدة بيانات مؤقتة/اختبار متبقية.
- `/opt/resort-os-current` مُحدَّث ليشير للإصدار الجديد.

### 4.8 اختبارات دخان حقيقية (بدون بيانات وهمية)

عبر `https://app.elkheima.com` مباشرة (خارج الـVPS):

```
GET  /api/v1/finance/expenses                          → 401 (مش 404)
POST /api/v1/finance/expenses                            → 401
GET  /api/v1/inventory/purchase-orders/1/payments        → 401
POST /api/v1/users/1/reset-credentials                    → 401
GET  /api/v1/timeshare/units/availability?...             → 401
GET  /api/v1/finance/payment-channels (موجود من قبل)       → 401 (مش متأثر)
```

كل الـendpoints الجديدة مسجّلة وتتطلب مصادقة (401)، مفيش أي 404 —
تأكيد أن الـrouting سليم بدون تنفيذ أي عملية حقيقية على بيانات حقيقية.

### 4.9 بوابة الصحة الرسمية

```
systemctl start resort-os-healthcheck.service
→ RESORT_HEALTHCHECK_OK passes=16
```

### 4.10 تعليمات الرجوع (Rollback)

لو ظهرت مشكلة:

1. اقرأ manifest الصور:
   `/var/backups/resort-os/source-releases/3f44a14...-rollback-images.txt`
2. أعد وسم كل صورة `resort-os-rollback/<name>:pre-3f44a14...` باسمها
   العادي في Compose.
3. أعد إنشاء backend → celery_worker/beat → el_kheima/owner → nginx
   بنفس الترتيب المحكوم.
4. أعد تشغيل كل فحوصات القبول أعلاه.
5. **لا** تسترجع قاعدة البيانات إلا بعد إثبات فساد بيانات فعلي (migration
   إضافية بحتة، `downgrade()` نظيف اتأكد منه محليًا لو احتجته).

## 5. القرار العملياتي المتبقي

- Task #12 (مؤجَّل، غير حرج): ربط حسابات بنكية حقيقية بقنوات التحصيل
  (Visa CIB، محفظة موحّدة) لتفعيل المطابقة البنكية الأوتوماتيكية —
  محتاج تفاصيل حساب بنكي حقيقية من Mohamed. النظام يعمل بشكل طبيعي
  بدونها.

## 6. الخلاصة

كل الأربع طلبات نُفّذت بالكامل، اختُبرت (كل الاختبارات الجديدة +
مجموعة الاختبارات الكاملة صفر فشل)، بُنيت، رُوجعت، اعتُمدت (commit
`3f44a14`)، ونُشرت على الإنتاج مع تحقق كامل post-release. نقطة رجوع
كاملة موثّقة (صور + نسخة قاعدة بيانات) قبل أي تغيير.
