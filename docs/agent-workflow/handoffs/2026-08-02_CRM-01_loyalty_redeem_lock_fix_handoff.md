# CRM-01 — Loyalty redeem row-lock fix

**التاريخ:** 2026-08-02
**المالك:** Mohamed
**المنفذ والمراجع النهائي:** Codex
**الحالة:** COMPLETE

## 1. الخلفية

بعد إغلاق POS-02 وHR-01، طلب Mohamed صراحةً مراجعة ذاتية شاملة إضافية —
"لو انت لاحظ اي مشاكل في الكافيه والوردية والتحاصيل والإيرادات والحسابات
والسيناريو في الكاشير بالكامل افحص وشوف بطريقتك"، ثم بعدها طلب تحديدًا
التجوّل في CRM وModule تانية بحرية كاملة ("اختار انت المكان أو الموديول
أو الخدمة"). اخترت مراجعة موديول CRM كنقطة بداية، ولقيت باج تزامن حقيقي
في مسار استرداد نقاط الولاء (loyalty points redeem) — نفس فئة الباج
المتكررة في المشروع (مخزون/شاطئ/ملكية جزئية، راجع CLAUDE.md §13 بند ⓫)،
هنا أول مرة تُكتشف في CRM.

## 2. النتيجة

`crm.services.redeem_loyalty_points` كان بيقرا رصيد نقاط العميل عبر
`crud.get_loyalty_account_by_customer` — استعلام عادي بدون أي قفل صف.
طلبين استرداد متزامنين لنفس العميل (سيناريو تشغيلي واقعي: نفس العميل
عنده فاتورتين مفتوحتين في نفس اللحظة — مثلاً طاولة مطعم وطلب شاطئ، وكل
كاشير بيحاول يسترد نقاط على فاتورته) كل واحد فيهم بيقرا نفس الرصيد
القديم قبل ما التاني يعمل commit. النتيجتين بيتقبلوا الاتنين، وبيتخصم
نصيب واحد بس فعليًا من الرصيد في قاعدة البيانات (lost update classic) —
يعني خصم مالي مزدوج حقيقي (خصم على فاتورتين) بينما دفتر النقاط نفسه
بيوريه استرداد واحد بس، من غير أي خطأ ظاهر لأي طرف وقت التنفيذ.

**التستات الموجودة ماكانتش هتلقط الباج ده أبدًا** — موديول CRM مالوش أي
تغطية اختبار للـloyalty قبل كده خالص (صفر تست على `redeem_loyalty_points`
من الأساس)، وحتى لو كان فيه، الاختبار العادي بيشتغل على SQLite
اللي بتتجاهل `with_for_update()` بالكامل — لازم Postgres حقيقي لإثبات
تزامن صفوف فعلي.

## 3. الإصلاح

`crud.get_loyalty_account_by_customer_for_update(db, branch_id,
customer_id)` جديد — نفس الاستعلام بس مع `.with_for_update(nowait=True)`.
`services.redeem_loyalty_points` بقى يستخدمها، ولو القفل فشل (صف مقفول
فعليًا من معاملة تانية) بيمسك `OperationalError`، يتأكد إنه فعلاً
"lock not available" (`is_lock_not_available`)، يعمل `db.rollback()`،
ويرمي `LoyaltyConcurrencyError` جديد — الراوتر (`api/router.py`) بيترجمها
لـ409 برسالة عربية واضحة بدل ما ينتظر أو ينجح غلط. نفس نمط
`InventoryConcurrencyError`/`BeachConcurrencyError` بالظبط، حرفيًا.

## 4. المصدر

- repo: `Resort-OS`
- branch: `claude/CX-02C-frontend-auth-bootstrap`
- commit: `8597535`
- الملفات المتغيّرة: `backend/app/modules/crm/crud.py`,
  `backend/app/modules/crm/services.py`,
  `backend/app/modules/crm/api/router.py`,
  `backend/tests/test_crm_loyalty_concurrency.py` (جديد)

## 5. بوابة الجودة

- تست Postgres-only جديد (`tests/test_crm_loyalty_concurrency.py`،
  SQLite بتتجاهل `with_for_update` تمامًا فمينفعش يثبت قفل حقيقي) —
  تستين:
  1. قفل يدوي في thread منفصل (`crud.get_loyalty_account_by_customer_for_update`
     مباشرة) يفضل ماسك الصف، ومحاولة استرداد حقيقية عبر
     `services.redeem_loyalty_points` في نفس اللحظة لازم ترفض فورًا
     بـ`LoyaltyConcurrencyError` (409) — مش تنتظر ولا تنجح. بعد ما القفل
     يتحرر، استرداد حقيقي تاني لازم ينجح صح (`new_balance == 20`).
  2. معاملتين حقيقيتين متسابقتين فعليًا (`threading.Barrier(2)`، مش
     thread واحد ماسك قفل يدوي) — الاتنين بيحاولوا يستردوا 80 نقطة من
     رصيد 100 في نفس اللحظة، لازم واحد بس ينجح والرصيد النهائي يبقى 20
     بالظبط (مفيش lost update)، اتأكد من قراءة fresh session منفصلة بعد
     كده.
- **اتأكد الإصلاح فعليًا بيلقط الباج، مش نجاح صوري**: بعد التأكد إن
  التستين عدّوا حيًا ضد Postgres حقيقي مع الإصلاح، اترجع `crud.py`
  و`services.py` مؤقتًا لحالتهم قبل الإصلاح (`git stash`) وأُعيد تشغيل
  نفس التستات — التست الأول فشل بـ`AttributeError` (الدالة المقفولة مش
  موجودة أصلًا، متوقع تمامًا)، والتست التاني كشف تعامل ضعيف في كود
  الاختبار نفسه مع استثناء غير متوقع جوه thread (كان بيمسك بس
  `(LoyaltyConcurrencyError, ValueError)` فاستثناء `AttributeError` غير
  متوقع كان بيسبب crash صامت للـthread من غير ما يظهر في نتيجة التست) —
  اتحسّن الـ`except` clause ليمسك أي `Exception` صريح ويسجله كنتيجة
  "rejected" بدل ما يختفي. بعد كده اترجع الإصلاح (`git stash pop`)
  وأُعيد التشغيل — **2 passed** تاني، للسبب الصح هذه المرة.
- `pytest tests/ -k "crm or loyalty"`: 103 passed, 2 skipped (تستات
  Postgres-only بتتخطى بدون `CRM_LOYALTY_CONCURRENCY_TEST_ADMIN_URL`،
  زي المتوقع تمامًا).
- Backend الكامل: `pytest tests/ -v` → 2185 passed, 1 failed, 42 skipped.
  الفشل الوحيد هو نفس الفشل القديم غير المرتبط الموثّق سابقًا في handoff
  HR-01 (`test_paying_maintenance_unfreezes_when_no_other_overdue`).
- `alembic heads`: رأس واحد `88d1c505a9dc` — صفر migration (استعلام
  جديد بس، مفيش تغيير schema، `LoyaltyAccount` موجود بالفعل).
- تحقّق مباشر داخل الحاوية الحية بعد النشر: `hasattr(crud,
  'get_loyalty_account_by_customer_for_update')` و`hasattr(services,
  'LoyaltyConcurrencyError')` رجعوا `True` الاتنين.

## 6. النشر

- نسخة DB قبل النشر مباشرة:
  `/var/backups/resort-os/database/resort_os_20260802_103152.dump`،
  SHA-256
  `5ecad84360934af560b617c25cdfa53b3730218342e1bce3f5e098b12196ebdc`؛
  اجتازت `pg_restore --list`.
- rollback tags: `resort-os-rollback/{backend,celery_worker,celery_beat}:pre-8597535`
  (كانوا `4a0a777`)، manifest:
  `/var/backups/resort-os/source-releases/8597535-rollback-images.txt`.
- release: `/opt/resort-os-releases/8597535`، current symlink محدّث.
- archive: `/var/backups/resort-os/source-releases/8597535.tar.gz`،
  SHA-256 `4fcd0da28a3dd6067820315445755be6fcf31beab15114e961e7b5a2c1658320`.
- `backend`, `celery_worker`, `celery_beat` بس اتبنوا واتنشروا — `el_kheima`
  (frontend) من `ddfbaaa` زي ما هو، مالوش تغيير في الجولة دي.
- 8 حاويات Running، `RestartCount=0` للثلاثة المتغيّرة، صفر severe logs.
- `https://app.elkheima.com/` → 200، `/health` → `status: ok` (DB وRedis
  الاتنين `ok`).

## 7. ملاحظة

المبلغ المتأثر لكل حالة استرداد فعلي متزامن كان هيبقى صغير نسبيًا (قيمة
نقاط استرداد واحدة فقط)، لكن الباج كان **نظامي** بمعنى إنه بيحصل مع أي
تزامن حقيقي، مش حالة نادرة جدًا — سيناريو "نفس العميل عنده فاتورتين
مفتوحتين في نفس اللحظة" وارد تشغيليًا (طاولة مطعم + طلب شاطئ، أو كاشيرين
مختلفين). لا backfill رجعي لاستردادات سابقة — نفس سياسة المشروع الثابتة
(إصلاح يسري على أي معاملة جديدة من دلوقتي بس، مطابق لقرارات مشابهة سابقة
زي إصلاح دليل الحسابات الفارغ 2026-07-27 وإصلاح شرائح الضريبة 2026-08-02).
