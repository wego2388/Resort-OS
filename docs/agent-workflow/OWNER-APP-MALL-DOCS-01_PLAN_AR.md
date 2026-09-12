# OWNER-APP-MALL-DOCS-01 — تطبيق المالك: الوثائق والمول

**التاريخ:** 2026-09-12
**الحالة:** DOCS + MALL SUMMARY DEPLOYED / UNIT MAP DATA GATE
**المنفذ:** Codex
**المعتمد:** Mohamed

## قواعد ثابتة

- المالك read-only للوثائق والمول في المرحلة الأولى.
- كل البيانات تحت `/api/v1/owner/*` عبر `get_owner_reader` وOwnerReadDb.
- الفرع مشتق من الجلسة؛ لا `branch_id` يرسله العميل كمصدر سلطة.
- لا PII للضيف أو الموظف، ولا وثائق HR، ولا رفع/تعديل/حذف.
- الملفات والـAPI لا تدخل runtime Service Worker cache، والاستجابات `no-store`.
- لا عبارة «كل شيء سليم» عند غياب البيانات أو requirement matrix؛ نعرض
  «لا توجد بيانات مسجلة» أو حالة غير محددة.

## الجزء المنفذ: الوثائق

- `GET /api/v1/owner/documents`
- `GET /api/v1/owner/documents/{id}/download`
- projection محصور في `scope=branch` و`visibility=owner_visible` والفرع
  النشط وغير المحذوف وغير المستبدل.
- تنزيل authenticated blob بعد AES-GCM/SHA/size verification، مع headers
  `no-store`, `nosniff`, `CSP sandbox` واسم آمن.
- شاشة `/documents`: بحث، تنبيه انتهاء، بطاقات متجاوبة، حجم/تاريخ، تنزيل
  بلمسة 48px، empty/error/loading states.
- تنقل الهاتف أصبح خمس وجهات فقط:
  `الآن | الأداء | المبيعات | المصروفات | المزيد`.
- «المزيد» يجمع الورديات والموظفين والمول والمستندات. شاشات التابلت/desktop تعرض
  نفس الخمس كـside rail، ولا يوجد شريط أفقي مزدحم.
- responsive Playwright ناجح على 320/390/768/1024/1280، وtype-check/build
  ناجحان.

## الجزء المنفذ: ملخص المول

- `GET /api/v1/owner/mall/summary` يشتق الفرع من الجلسة ويستخدم
  `OwnerReadDb` و`Cache-Control: no-store`.
- شاشة `/mall` داخل «المزيد» تعرض المجدول حتى اليوم، والإيراد المتحقق،
  والمتحصل الفعلي، والمتأخرات، وعدد العقود والنشط والقريب من الانتهاء.
- التحصيل من `payments`: `leasing_rent` زائد `leasing_cash_log` لنوعي
  `rent_payment/revenue_share` فقط؛ التأمين والصيانة والغرامة والرد ليست
  «إيجارًا متحصلًا».
- بطاقات العقود تعرض رقم العقد ووصف الوحدة التعاقدي والحالة والتواريخ
  والمجدول/المسدد/المستحق؛ لا tenant name/phone/national ID.
- branch isolation واختبار PII/مصادر الأرقام/empty state/role gate ناجحة.
- Owner Playwright أصبح 13/13 ويغطي الشاشة نفسها وكل المقاسات المعتمدة.

## الجزء المتبقي: سجل الوحدات والخريطة

حتى فتح MALL-01 data gate تبقى `registered_unit_count`, `occupied_unit_count`,
`vacant_unit_count`, `occupancy_pct` بقيمة `null` و`map_available=false`؛
عقد الإيجار يثبت وجود عقد ولا يثبت عدد الوحدات الشاغرة. بعد اعتماد الوحدات:

- `/api/v1/owner/mall/map`
- `/api/v1/owner/mall/units`
- `/api/v1/owner/mall/units/{id}`
- خريطة semantic مع list fallback وkeyboard/pinch/zoom، وهندسة الخيمة تبقى
  feature data مستقلة عن component العرض العام.
- unit detail بلا tenant phone/email أو أي PII.

## Definition of Done

### الوثائق

- [x] Owner API مصفى وعابر لـOwner isolation tests.
- [x] OwnerRead role provisioning محدث للجدول الجديد.
- [x] no-store وتنزيل آمن وعدم إظهار وثائق الموظفين.
- [x] 5 + More وتنفيذ responsive/light/dark/text-scale-compatible.
- [x] build و13/13 responsive E2E تشمل المول.
- [x] immutable production release وlive smoke.

### المول

- [x] Owner Mall summary مالي متصالح مع Leasing/Payments وبلا PII.
- [x] `/mall` responsive/a11y states وbranch/role/empty tests.
- [ ] MALL-01 unit/map data gate معتمد.
- [ ] Mall map/unit list/detail بعد إنشاء Unit Registry.
- [x] production deployment بعد backup وrollback.

## ملاحظة الإصدار

جزء الوثائق وMall Summary منشوران معًا عند Resort `1d2dc76` بعد backup
وrollback وhealth/live smoke ناجحة. Unit Registry والخريطة فقط ينتظران
البيانات المعتمدة؛ الواجهة تصرح بأن هذه القيم غير متاحة بدل عرض أرقام
مصطنعة.
