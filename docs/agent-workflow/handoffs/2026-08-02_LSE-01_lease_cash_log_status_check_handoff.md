# LSE-01 — Lease cash-log rent collection blocked on terminated/expired contract

**التاريخ:** 2026-08-02
**المالك:** Mohamed
**المنفذ والمراجع النهائي:** Codex
**الحالة:** COMPLETE

## 1. الخلفية

بعد إغلاق ANL-01، أكملت جولة المراجعة الذاتية الحرة اللي طلبها Mohamed
("دور في CRM وMaintenance Analytics Leasing") بآخر ميديول في القائمة —
الإيجارات (Leasing). الموديول ده كان اتعمله فحص/إصلاح جزئي سابق
(2026-07-28، قفل صف الدفعة، سقف مبلغ التحصيل، فحص حالة العقد في
`pay_payment`) — أثناء مراجعة `services.py` بالكامل مقارنةً `pay_payment`
بـ`record_cash_log` (المسار المواز)، لقيت فحص حالة العقد مكانش متسق بين
الاتنين.

## 2. النتيجة

`pay_payment` (تحصيل الدفعة الشهرية العادية من جدول العقد) بيرفض بوضوح
لو `contract.status` كان `terminated` أو `expired`. لكن `record_cash_log`
(التسوية الكاش اليومية — مستخدمة عمليًا مع مستأجرين زي مراكز الغوص/واتر
سبورت اللي بيسووا حساباتهم يوميًا بره دورة الاستحقاق الشهرية العادية)
بترحّل **بالظبط نفس قيدي المحاسبة** (`_post_rent_collection_journal`:
Dr.1100/Cr.1260 ثم Dr.1260/Cr.4500) لما `activity_type` يكون
`rent_payment` أو `revenue_share` — من غير أي فحص لحالة العقد خالص.

يعني: عقد إيجار اتفسخ فعليًا (Mohamed أنهى العلاقة مع المستأجر) كان لسه
ممكن مدير يسجّل عليه "تحصيل إيجار" حقيقي عبر شاشة التسوية الكاش، والقيد
المحاسبي يترحّل بصمت كإيراد إيجار حقيقي لعقد مفروض يكون مقفول تمامًا.

## 3. الإصلاح

`record_cash_log` بقى يفحص حالة العقد **قبل** أي كتابة، لكن **مقصور
على `rent_payment`/`revenue_share` بس** — مش كل `activity_type` — عشان
الأنواع التانية (`deposit`/`refund`/`penalty`/`maintenance`/`other`)
مسموحة عمدًا حتى بعد الفسخ/الانتهاء: رد تأمين للمستأجر أو تسوية غرامة
نهائية سيناريو تشغيلي طبيعي تمامًا بعد إقفال العقد، عكس تحصيل إيراد
إيجار جديد على عقد مفروض يكون خلص.

## 4. المصدر

- repo: `Resort-OS`
- branch: `claude/CX-02C-frontend-auth-bootstrap`
- commit: `4ca10c1`
- الملفات المتغيّرة: `backend/app/modules/leasing/services.py`,
  `backend/tests/test_api/test_leasing_http.py`

## 5. بوابة الجودة

- 3 اختبارات جديدة في `TestLeasingCashLog`:
  - `test_rent_payment_cash_log_rejected_on_terminated_contract`
  - `test_rent_payment_cash_log_rejected_on_expired_contract`
  - `test_deposit_refund_cash_log_still_allowed_on_terminated_contract`
    (يتأكد إن الحظر مش شامل كل الأنواع بالغلط)
- **اتأكد الإصلاح فعليًا بيلقط الباج**: `git stash` مؤقت لـ`services.py`
  وإعادة تشغيل التستين الأولين قبل الإصلاح — الاتنين فشلوا فعليًا
  (`201` بدل `400` المتوقع)، مؤكدين إن الباج حقيقي مش نظري. بعد
  `git stash pop` وإعادة الإصلاح، كل التستات عدّت للسبب الصح.
- `pytest tests/test_api/test_leasing_http.py -v`: 30 passed.
- Backend الكامل: `pytest tests/ -v` → 2194 passed, 1 failed, 42 skipped.
  الفشل الوحيد هو نفس الفشل القديم غير المرتبط الموثّق سابقًا.
- `alembic heads`: رأس واحد `88d1c505a9dc` — صفر migration (فحص منطقي بس).
- تحقّق مباشر داخل الحاوية الحية بعد النشر: `inspect.getsource` على
  `record_cash_log` أكد وجود رسائل الرفض "مفسوخ"/"منتهي".

## 6. النشر

- نسخة DB قبل النشر مباشرة:
  `/var/backups/resort-os/database/resort_os_20260802_113200.dump`،
  SHA-256
  `d74442b6b78e52dd721b35b8427f6af0a354ef3e8f49fa61a2021e123418b870`؛
  اجتازت `pg_restore --list`.
- rollback tags: `resort-os-rollback/{backend,celery_worker,celery_beat}:pre-4ca10c1`
  (كانوا `0d55717`)، manifest:
  `/var/backups/resort-os/source-releases/4ca10c1-rollback-images.txt`.
- release: `/opt/resort-os-releases/4ca10c1`، current symlink محدّث.
- archive: `/var/backups/resort-os/source-releases/4ca10c1.tar.gz`،
  SHA-256 `e6c73575e7020a5676b6233777808211b0979bf55f87be1f986150ac9c945906`.
- `backend`, `celery_worker`, `celery_beat` بس اتبنوا واتنشروا — `el_kheima`
  (frontend) من `b1db886` زي ما هو، مالوش تغيير في الجولة دي.
- 8 حاويات Running، `RestartCount=0` للثلاثة المتغيّرة، صفر severe logs.
- `https://app.elkheima.com/` → 200، `/health` → `status: ok`.

## 7. ملاحظة — إغلاق دورة CRM/Maintenance/Analytics/Leasing

هذا هو آخر موديول من القائمة اللي حددها Mohamed صراحةً ("دور في CRM
وMaintenance Analytics Leasing"). الأربعة اتقفلوا بنفس الترتيب والدرجة
من الصرامة: CRM-01 (8597535)، MNT-01 (b1db886)، ANL-01 (0d55717)،
LSE-01 (4ca10c1) — كل واحد منهم باج حقيقي مكتشف بالمراجعة، مش تخمين،
مع فحص/تست يثبت الباج قبل الإصلاح لما كان ده ممكن (CRM/MNT/LSE)، ونشر
كامل بأدلة backup/rollback/health. الخطوة التالية حسب تعليمات Mohamed:
استكمال باقي الموديولات المتبقية، ثم أخيرًا الموقع التسويقي
(`elkheima-marketing-website`).
