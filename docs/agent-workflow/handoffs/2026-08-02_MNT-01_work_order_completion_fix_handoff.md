# MNT-01 — Work order completion bypass + asset-release-on-cancel fix

**التاريخ:** 2026-08-02
**المالك:** Mohamed
**المنفذ والمراجع النهائي:** Codex
**الحالة:** COMPLETE

## 1. الخلفية

بعد إغلاق CRM-01، تابعت جولة المراجعة الذاتية الحرة اللي طلبها Mohamed
("دور في CRM وMaintenance Analytics Leasing") — الميديول التالي هو
الصيانة (Maintenance). الميديول ده كان اتعمله فحص/إصلاح جزئي قبل كده
(2026-07-28، توثيق branch isolation وتحقق assigned_to وتصحيح خصم قطع
الغيار من المخزون)، لكن أثناء مراجعة `services.update_work_order` تحديدًا
لقيت باجين حقيقيين مركّبين في نفس مسار إنهاء/إلغاء أمر الصيانة.

## 2. النتيجة

`PATCH /maintenance/work-orders/{id}` (الشاشة العادية للتعديل، صلاحية
`get_employee_user` — مستوى موظف 20) كان بيقبل `status="completed"`
مباشرة من غير أي فحص. المسار المخصص `POST .../complete` محتاج مدير+
(مستوى 60) ويشغّل كود `complete_work_order()` اللي بيعمل 3 حاجات مهمة:
يسجّل `completed_at`، يحرر الأصل المرتبط من `under_maintenance` لو مفيش
أوامر صيانة مفتوحة تانية عليه، ويقدّم `next_due` لجدول الصيانة الوقائية
لو الأمر ده جاي من جدول دوري (وإلا `generate_preventive_work_orders`
هيفضل يعمل أمر جديد لنفس الجدول كل يوم للأبد). أي waiter (مستوى 20) كان
يقدر يستخدم PATCH العادي "يقفل" أمر صيانة حرج بضغطة واحدة، من غير أي من
الآثار التلاتة دي — الأمر يفضل شكليًا "مكتمل" بس، والأصل يفضل تحت
الصيانة، والجدول الوقائي يفضل مستحق للأبد.

**اتأكد الباج بتجربة حية**: waiter رجع 200 مع `status="completed"`،
و`completed_at` فضل `null`.

أثناء بناء الإصلاح، اتكشف باج تاني مرتبط بنفس السبب الجذري: منطق تحرير
الأصل (`open_count` check) كان جوه `complete_work_order()` بس — أمر صيانة
critical لو اتلغى (`cancelled`، حالة نهائية تانية مسموحة عبر PATCH العادي
أصلًا) بدل ما يتقفل، الأصل كان يفضل `under_maintenance` للأبد من غير أي
مسار تاني يعيد فحص الأوامر المفتوحة.

## 3. الإصلاح

- `services.update_work_order` بقى يرفض `data.status == "completed"`
  صراحةً برسالة توجّه لـ`/complete` — بغض النظر عن هوية المستخدم (حتى
  مدير مؤهّل أصلًا لـ`/complete` لازم يمر بالمسار المخصص، مش الاختصار).
- `_release_asset_if_no_open_orders(db, asset_id)` دالة مشتركة جديدة
  (استُخرجت من نفس منطق `complete_work_order`)، دلوقتي مستخدمة من
  الاتنين: `complete_work_order` و`update_work_order` (لما الانتقال يكون
  لـ`cancelled`).
- الفرونت إند (`MaintenanceView.vue`): dropdown تعديل أمر الصيانة كان فيه
  "مكتمل" كخيار قابل للاختيار عبر PATCH العادي — هيرجع 400 دايمًا بعد
  الإصلاح، فاتفلتر (`editableWoStatusConfig`، computed جديد بيستبعد
  `completed` من `woStatusConfig`). زرار "✅ إنهاء" المخصص
  (`completeWorkOrder`, بينادي `/complete` الصح) كان موجود بالفعل ومتأثرش.

## 4. المصدر

- repo: `Resort-OS`
- branch: `claude/CX-02C-frontend-auth-bootstrap`
- commit: `b1db886`
- الملفات المتغيّرة: `backend/app/modules/maintenance/services.py`,
  `backend/tests/test_api/test_maintenance_http.py`,
  `frontend/apps/el-kheima/src/views/admin/MaintenanceView.vue`

## 5. بوابة الجودة

- تستان جديدان في `test_maintenance_http.py`:
  - `test_generic_patch_cannot_bypass_complete_endpoint`: يثبت الباج حيًا
    قبل الإصلاح (waiter نجح فعليًا بـ200 وcompleted_at فاضي)، وبعد الإصلاح
    بيتأكد إن PATCH بـstatus=completed يرفض 400 لوايتر ولمدير الاتنين،
    وإن أمر الصيانة يفضل مفتوح فعليًا (status != completed، completed_at
    لسه None) بعد الرفض.
  - `test_cancelling_last_open_order_releases_asset`: يتأكد إن إلغاء آخر
    أمر صيانة مفتوح على أصل under_maintenance بيحرره لـoperational، زي
    الإكمال بالظبط.
- `pytest tests/test_api/test_maintenance_http.py -v`: 22 passed (كانوا
  21 قبل التستين الجداد).
- `pytest tests/ -k maintenance`: 84 passed (نفس الفشل القديم غير المرتبط
  في timeshare مش من نطاق ده).
- Backend الكامل: `pytest tests/ -v` → 2186 passed, 1 failed, 42 skipped.
  الفشل الوحيد هو نفس الفشل القديم الموثّق سابقًا
  (`test_paying_maintenance_unfreezes_when_no_other_overdue`).
- `alembic heads`: رأس واحد `88d1c505a9dc` — صفر migration (منطق service
  layer + فرونت إند بس، مفيش تغيير schema).
- `pnpm --filter el-kheima type-check`: نضاف.
- تحقّق مباشر داخل الحاوية الحية بعد النشر: `inspect.getsource` على
  `update_work_order` أكد وجود رسالة الرفض ووجود نداء
  `_release_asset_if_no_open_orders` مع `cancelled`.

## 6. النشر

- نسخة DB قبل النشر مباشرة:
  `/var/backups/resort-os/database/resort_os_20260802_105621.dump`،
  SHA-256
  `b838604a4db79f02dc099cfc2ef674eab0b6bc34364f2f344c10631cd8ffe472`؛
  اجتازت `pg_restore --list`.
- rollback tags: `resort-os-rollback/{backend,celery_worker,celery_beat,el_kheima}:pre-b1db886`،
  manifest: `/var/backups/resort-os/source-releases/b1db886-rollback-images.txt`.
- release: `/opt/resort-os-releases/b1db886`، current symlink محدّث.
- archive: `/var/backups/resort-os/source-releases/b1db886.tar.gz`،
  SHA-256 `da2bb917b3e7646c5635a4be8fe9edcfc5d80301a477385b93264d17b87cc36a`.
- الأربعة (`backend`, `celery_worker`, `celery_beat`, `el_kheima`) اتبنوا
  واتنشروا — أول مرة `el_kheima` يتغيّر منذ `ddfbaaa` (تغيير فرونت إند
  حقيقي هنا: dropdown الصيانة).
- 8 حاويات Running، `RestartCount=0` للأربعة المتغيّرة، صفر severe logs.
- `https://app.elkheima.com/` → 200، `/health` → `status: ok`.

## 7. ملاحظة

نفس فئة الباج ("طريقة تانية للإنهاء بتتخطى الآثار الجانبية") ظهرت قبل كده
في المشروع (زي `void_order_item`/`apply_discount` اللي ليهم بوابة PIN
مخصصة بدل تعديل عادي) — الحل هنا بنفس الفلسفة: طريقة واحدة رسمية بس
للانتقال الحسّاس، والتعديل العادي بيرفضه صراحةً بدل ما يسمح بيه بصمت.
لا backfill رجعي لأوامر صيانة "مكتملة" شكليًا من قبل الإصلاح (لو موجودة)
— نفس سياسة المشروع الثابتة لعدم تعديل بيانات تاريخية بأثر رجعي.
