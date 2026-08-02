# HUB-01 — confirm_booking dead-code UnboundLocalError fix

**التاريخ:** 2026-08-02
**المالك:** Mohamed
**المنفذ والمراجع النهائي:** Codex
**الحالة:** COMPLETE

## 1. الخلفية

بعد إغلاق قائمة الموديولات الأربعة اللي حددها Mohamed صراحةً (CRM-01،
MNT-01، ANL-01، LSE-01)، تابعت الجولة على باقي الموديولات حسب تعليمة
Mohamed التالية ("كمل علي باقي الميديول"). راجعت الشاطئ (Beach) أولًا —
اتأكد سليم تمامًا (كان اتعمله إصلاحات محاسبية/تزامن مكثفة قبل كده على 4
جولات منفصلة: 2026-07-04، 07-06، 07-07، 07-28). بعدين راجعت موديول Hub
(المنصة الرقمية — موقع + حجوزات أونلاين) ولقيت باج كود حقيقي في
`confirm_booking`.

## 2. النتيجة

`confirm_booking` (تأكيد حجز أونلاين وارد من الموقع — لو الطلب عنده
تواريخ إقامة ونوع غرفة، بينشئ حجز PMS تلقائيًا) كان فيه سطرين مكررين
(`pms_booking_id = pms_b.id` + `logger.info`) بعد كتلة `if not
available: ... else: ...` مباشرة، بنفس مستوى إزاحة الـ`if` — يعني
بيتنفذوا **دايمًا** بغض النظر عن الفرع اللي اتنفذ فعليًا في الـif/else.

لما فيه غرف متاحة (فرع `else`): السطرين المكررين بيعيدوا نفس العمل
(redundant، مش خطأ، بس log spam).

لما **مفيش** غرف متاحة (فرع `if not available`، اللي المفروض — حسب
التوثيق الرسمي للدالة نفسها — يسجّل تحذير واضح ويكمل عادي بدون PMS):
المتغيّر `pms_b` أصلًا **مالوش قيمة** في الفرع ده، فالسطر المكرر بيرمي
`UnboundLocalError` حقيقي. الاستثناء ده كان بيتبلع بصمت في `except
Exception:` الأوسع المحيط بكل الكتلة، ويتسجّل في اللوجات كـ`logger.error`
كامل بـ`exc_info=True` — عنوانه "فشل إنشاء PMS booking... يحتاج إنشاء
يدوي" — بدل التحذير الواضح "لا توجد غرف متاحة" اللي كان المفروض يظهر.

**الأثر العملي**: الحجز نفسه كان بيتأكد صح (status=confirmed،
pms_booking_id=None) في الحالتين — مفيش أي كسر وظيفي ظاهر للمستخدم. لكن
أي مراجعة لوجات مستقبلية (تشخيص مشكلة، تدقيق) كانت هتشوف "خطأ" و
traceback مربك تمامًا لسيناريو عادي جدًا ومتوقع (نفاد الغرف)، بدل تحذير
تشغيلي واضح.

## 3. الإصلاح

حذف السطرين المكررين بعد كتلة `if/else` — النسخة الوحيدة الصحيحة (جوه
فرع `else`، بعد إنشاء `pms_b` فعليًا في `pms_create(...)`) هي اللي فضلت
لوحدها.

## 4. المصدر

- repo: `Resort-OS`
- branch: `claude/CX-02C-frontend-auth-bootstrap`
- commit: `5b02010`
- الملفات المتغيّرة: `backend/app/modules/hub/services.py`,
  `backend/tests/test_api/test_hub.py`

## 5. بوابة الجودة

- تست جديد
  `test_confirm_booking_with_no_available_rooms_logs_clean_warning_not_error`
  بيستخدم `caplog` (مش بس فحص الحالة النهائية — الحالة النهائية
  status/pms_booking_id كانت بتطلع صح غلطًا في الحالتين لأن الاستثناء
  كان بيتبلع بصمت) عشان يتأكد: (أ) التحذير "لا توجد غرف متاحة" موجود
  فعليًا في اللوج، (ب) صفر أي سجل بمستوى ERROR أو أعلى.
- **اتأكد الإصلاح فعليًا بيلقط الباج**: `git stash` مؤقت للملف وإعادة
  تشغيل التست قبل الإصلاح — فشل فعليًا بـ`AssertionError` يوضح سجل ERROR
  حقيقي بمحتوى `UnboundLocalError: cannot access local variable 'pms_b'
  where it is not associated with a value` في الـtraceback الملتقط. بعد
  استرجاع الإصلاح، التست عدّى للسبب الصح.
- `pytest tests/test_api/test_hub.py -v`: 19 passed.
- Backend الكامل: `pytest tests/ -v` → 2195 passed, 1 failed, 42 skipped.
  الفشل الوحيد هو نفس الفشل القديم غير المرتبط الموثّق سابقًا.
- `alembic heads`: رأس واحد `88d1c505a9dc` — صفر migration.
- تحقّق مباشر داخل الحاوية الحية بعد النشر: عدد تكرارات
  `"pms_booking_id = pms_b.id"` في مصدر `confirm_booking` = 1 (كانت 2).

## 6. النشر

- نسخة DB قبل النشر مباشرة:
  `/var/backups/resort-os/database/resort_os_20260802_115042.dump`،
  SHA-256
  `f2547e1b089c7e9706931536218be92868faf4622f0519e60c6870e364330f91`؛
  اجتازت `pg_restore --list`.
- rollback tags: `resort-os-rollback/{backend,celery_worker,celery_beat}:pre-5b02010`
  (كانوا `4ca10c1`)، manifest:
  `/var/backups/resort-os/source-releases/5b02010-rollback-images.txt`.
- release: `/opt/resort-os-releases/5b02010`، current symlink محدّث.
- archive: `/var/backups/resort-os/source-releases/5b02010.tar.gz`،
  SHA-256 `50538820d9b9e4ef9e3d724e45b09dfca4dfc86e25154a852fab98765900b673`.
- `backend`, `celery_worker`, `celery_beat` بس اتبنوا واتنشروا — `el_kheima`
  (frontend) من `b1db886` زي ما هو، مالوش تغيير في الجولة دي.
- 8 حاويات Running، `RestartCount=0` للثلاثة المتغيّرة، صفر severe logs.
- `https://app.elkheima.com/` → 200، `/health` → `status: ok`.

## 7. ملاحظة

الموديولات المتبقية من قائمة "باقي الموديولات": `core`، `chat` (كان
اتعمله تحصين مخصص CL-01 قبل كده، جولة خفيفة كافية). بعد كده، حسب تعليمة
Mohamed: "كمل اخيرا علي الويب سايت" — مراجعة `elkheima-marketing-website`
(مستودع منفصل).
