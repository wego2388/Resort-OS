# MALL-01 — إدارة المول التجاري داخل Leasing

**التاريخ:** 2026-09-12
**الحالة:** OWNER SUMMARY DEPLOYED / UNIT DATA GATE
**المنفذ:** Codex
**المعتمد:** Mohamed

## القرار

المول توسعة للـbounded context الحالي `leasing`، وليس موديول عقود أو مالية
جديدًا. التنفيذ البرمجي المؤثر على schema أو البيانات يبدأ بعد اعتماد سجل
الوحدات والخريطة الفعليين؛ لا seed تخميني ولا `branch_id=1` ولا اعتبار
الممرات والخدمات وحدات قابلة للتأجير.

## بوابة البيانات المطلوبة

ملف معتمد يحتوي لكل وحدة:

| الحقل | مطلوب | ملاحظة |
|---|---:|---|
| `branch_code` | نعم | كود ثابت، لا ID رقمي مفترض |
| `unit_code` | نعم | فريد داخل الفرع |
| `name_ar` | نعم | اسم العرض |
| `floor` | نعم | قيمة معيارية معتمدة |
| `unit_type` | نعم | shop/restaurant/office/kiosk/outdoor/other |
| `area_sqm` | نعم | Decimal موجب |
| `is_leasable` | نعم | false للممر/الخدمة/WC ونحوها |
| `physical_status` | نعم | ready/maintenance/blocked/inactive |
| `map_shape` | للخريطة | polygon/rect بإحداثيات معتمدة |
| `notes` | اختياري | بلا بيانات مستأجر شخصية |

يلزم أيضًا ملف/SVG مصدر معتمد يطابق الأكواد، وتحديد صريح للوحدات الأربع
المؤجرة حاليًا إن كانت هذه المعلومة ما زالت صحيحة. أي أرقام مستخرجة من PDF
أو أمثلة سابقة تظل مرشحة فقط حتى يوقع Mohamed على السجل.

## التصميم بعد فتح البوابة

### قاعدة البيانات

- `mall_units`: branch-scoped، وunique (`branch_id`, `unit_code`).
- الحالة المادية مستقلة عن occupancy المشتق من العقود.
- إضافة `mall_unit_id` nullable إلى `lease_contracts` مع
  `ON DELETE RESTRICT`، والإبقاء على `unit_description` كـhistorical snapshot.
- منع تداخل عقدين فعالين للوحدة نفسها على مستوى DB، مع row lock ومعاملة
  واحدة في service.
- الوحدة المرتبطة بتاريخ عقد لا تحذف؛ تعطّل بعد validation.
- migration مستقلة مبنية من Alembic head الحي وقت التنفيذ، وليس من رقم
  ثابت داخل هذه الخطة.

### الـAPI

- Staff CRUD للوحدات تحت `/api/v1/leasing/mall/units` بصلاحيات leasing.
- map/status endpoint يعيد semantic state بلا ألوان وبلا PII.
- statistics تفصل:
  - total/leasable/occupied/vacant/maintenance.
  - contracted rent.
  - accrued rent.
  - collected cash.
  - overdue receivables.
- Owner endpoints مستقلة `/api/v1/owner/mall/*`، branch من الجلسة وread-only.

## المنفذ قبل فتح البوابة — بدون تغيير schema أو بيانات

- `GET /api/v1/owner/mall/summary` وواجهة Owner `/mall` منفذان فوق
  `lease_contracts`, `lease_payments`, `payments`, `tenant_cash_logs` الحالية.
- الأرقام مفصولة semantic: مجدول، متحقق، متحصل، ومتأخر؛ التأمين وباقي حركات
  المستأجر لا تدخل رقم الإيجار المتحصل.
- قائمة PII-free للعقود الحالية تستخدم `unit_description` كـhistorical
  contract snapshot، ولا تدعي أنها Unit Registry.
- total/occupied/vacant/occupancy/map لا تُستنتج من العقود؛ ترجع unknown/null
  حتى اعتماد السجل الحقيقي.
- Backend 3/3 للمسار الجديد، Owner responsive E2E 13/13، والبناء ناجح.
- ملخص المول منشور عند Resort `1d2dc76`؛ smoke مصادق رجع 200 بلا tenant
  PII وبقيت occupancy/map unknown كما تفرض بوابة البيانات.

### الواجهة

- Staff dashboard + map + list fallback + unit detail/history.
- الخريطة keyboard/touch، pinch/zoom، focus واضح، ولا تعتمد على اللون وحده.
- اختبار Lenovo landscape/portrait، وشاشات Owner 320/390/768/1024/1280.
- لا اسم/هاتف/بيانات مستأجر على الخريطة أو Owner DTO.

## الاستيراد

- dry-run أولًا مع counts/errors/checksum.
- idempotency على branch code + unit code.
- transaction كاملة؛ أي كود مكرر/فرع مجهول/shape غير صالح يفشل المجموعة.
- لا إنشاء عقود أو دفعات من ملف الوحدات.
- تقرير reconciliation بعد الاستيراد يطابق السجل المعتمد حرفيًا.

## Definition of Done

- [ ] سجل الوحدات والخريطة معتمدان.
- [ ] schema/migration وقيود التداخل ناجحة تحت concurrent tests.
- [ ] importer dry-run/apply/idempotency/reconciliation ناجح.
- [ ] Staff map + list fallback + responsive/a11y ناجحة.
- [ ] مؤشرات financial semantics متصالحة مع Leasing/GL.
- [x] Owner read-only summary/UI بلا PII وبلا إشغال مخمّن.
- [ ] full regression + backup/rollback + immutable production release.

## الحالة الحالية

لا يوجد مانع تقني. ملخص المول للمالك منفذ ومنشور على الإنتاج. المانع
الوحيد الآمن لباقي MALL-01 هو master data المعتمدة اللازمة لـschema والوحدات
والخريطة ونسبة الإشغال الحقيقية.
