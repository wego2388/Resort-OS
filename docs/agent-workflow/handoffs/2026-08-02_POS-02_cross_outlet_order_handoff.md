# POS-02 — Cross-outlet order support + refund revenue-account fix

**التاريخ:** 2026-08-02
**المالك:** Mohamed
**المنفذ والمراجع النهائي:** Codex
**الحالة:** COMPLETE

## 1. النتيجة

نُشر Resort OS release `ddfbaaa` على `app.elkheima.com` — أول نشر Backend
حقيقي منذ `679f76e` (كل الإصدارات بين الاتنين كانت Frontend-only).

- الكاشير بقى يقدر يضيف صنف من منفذ تاني (مطعم/كافيه) على نفس الفاتورة
  المفتوحة من غير إلغاء الطلب أو فتح فاتورة منفصلة — نفس السلوك الطبيعي
  لطاولة واحدة عندها أكل ومشروبات مع بعض. الطلب الأساسي (`create_order`,
  `add_items_to_order`) كان بيرفض أي صنف من outlet مختلف عن outlet الطلب/
  الطلب المُعلَن — الشرط اتخفّف لـ"نفس الفرع" بس لمسارات الـPOS الداخلية
  (`allow_cross_outlet=True`)، بينما الطلب الذاتي العام للضيف عبر QR فضل
  صارم زي ما كان بالظبط (Gate 1 containment، اختبار الرفض موجود).
- كل صنف بيسجّل `outlet_id` الحقيقي بتاعه (كان دايمًا NULL قبل كده رغم
  إن العمود موجود من زمان، والتسوية المالية مبنية عليه أصلاً).
- **باج حقيقي اتصلح** أثناء الربط: تذكرة المطبخ كانت بتاخد `outlet_id`
  الطلب دايمًا حتى لو الصنف من outlet تاني — دلوقتي كل تذكرة بتتوجّه
  لـoutlet الصنف نفسه (مهم لو أي وقت استُخدمت شاشات KDS مخصّصة لمنفذ واحد).
- **باج محاسبي حقيقي تاني اتصلح** أثناء المراجعة الإضافية: مرتجع صنف بعد
  الدفع كان بيعكس حساب إيراد *المنفذ الأساسي للطلب* بدل حساب إيراد الصنف
  نفسه — لو رجّعت صنف كافيه من طلب أساسه المطعم، القيد العكسي كان بيتقيد
  غلط على "إيرادات المطعم". اتصلح في 3 دوال (`_post_refund_reversals`،
  `_reduce_folio_charge_for_refund`، `_post_order_folio_refund_reversal_journal`)
  بتحويل outlet الصنف المرتجَع نفسه بدل إعادة اشتقاقه من الطلب.

## 2. المراجعة الموسّعة (بطلب Mohamed — فحص شامل للكاشير/الوردية/الإيرادات)

بعد الإصلاحين فوق، اتعمل فحص منهجي لكل المسارات المالية القريبة من
التعديل ده تحديدًا:

- **التحصيل عند الدفع** (`_settle_direct_tender`, `_settle_room_tender`):
  كان مبني صح من قبل (commit سابق `e83020c`) — اتأكد بالكود وبتجربة حية
  فعلية (233.10 كافيه + 327.60 مطعم = 560.70 بالظبط).
- **الوردية والكاش**: صفر ربط بين الشيفت/التحصيل النقدي والـoutlet — كل
  حاجة على مستوى الفرع، آمنة تمامًا من هذا النوع من الباجات.
- **دمج الطلبات (`merge_orders`) وتقسيم الفاتورة (`split_bill`)**: آمنين —
  الدمج بيرفض طلبين بـoutlet أساسي مختلف زي ما كان، والتقسيم بيمرّ عبر
  نفس `settle_order` الصحيح أصلاً.
- **محرك الخصومات**: ثغرة حقيقية بس *نايمة* حاليًا — قاعدة خصم من نوع
  `scope_type="outlet"` بتتقيّم مقابل outlet الطلب الأساسي بس وبتخصم
  subtotal الطلب كله، مش نصيب الـoutlet المطابق فقط. فحصت قاعدة البيانات:
  **صفر قاعدة من النوع ده مفعّلة حاليًا** — مفيش خطر فعلي دلوقتي. مقصود
  عدم إصلاحها كأثر جانبي — محتاجة إعادة تصميم لمحرك الخصم نفسه، مش تعديل
  صغير. **موثّقة هنا كتذكير لأي جلسة قادمة قبل ما حد يفعّل خصم outlet-scoped.**

## 3. المصدر

- repo: `Resort-OS`
- branch: `claude/CX-02C-frontend-auth-bootstrap` (الفرع التشغيلي الوحيد،
  `origin/main` فضل عند `598938e` زي ما هو)
- commits: `9579c2f` (دعم cross-outlet) + `ddfbaaa` (إصلاح مرتجع الإيراد)
- الملفات المتغيّرة: `backend/app/modules/dining/services.py`,
  `backend/app/modules/dining/api/router.py`,
  `backend/tests/test_api/test_dining.py`,
  `frontend/apps/el-kheima/src/components/dining-pos/{POSCartPanel.vue,types.ts}`,
  `frontend/apps/el-kheima/src/views/pos/UnifiedPOSView.vue`,
  `frontend/packages/core/src/i18n/locales/{ar,en}.json`
- release: `/opt/resort-os-releases/ddfbaaa`
- current: `/opt/resort-os-current -> .../ddfbaaa`
- archive: `/var/backups/resort-os/source-releases/ddfbaaa.tar.gz`
- archive SHA-256:
  `8aafedfd109a59e7ed72ea2c4ecc30b248d51af63f09198d0b0cd1629c1390d6`

## 4. بوابة الجودة

- Backend: 2224 اختبار، صفر فشل عدا فشل قديم واحد غير مرتبط ومؤكد
  (`test_timeshare_maintenance.py::test_paying_maintenance_unfreezes_when_no_other_overdue`
  — اتأكد إنه بيفشل بنفس الطريقة على الفرع النضيف قبل أي تعديل من الجلسة دي).
- 5 اختبارات جديدة: cross-outlet initial create، cross-outlet add-items،
  cross-outlet still rejected across branches، kitchen ticket routing
  الصح، **مرتجع cross-outlet بيعكس الحساب الصح** (الأخير اتأكد إنه بيفشل
  فعليًا على الكود قبل الإصلاح، مش مجرد نجاح صوري).
- `alembic heads`: رأس واحد `88d1c505a9dc` — بدون تغيير، صفر migration.
- Frontend: `type-check`, `build`, vitest (95/95), i18n parity كلهم نظاف.
- **تحقّق حي كامل على بيئة تطوير معزولة قبل النشر** (مش تخمين): تسجيل دخول
  كاشير حقيقي، فتح طاولة، إضافة صنف كافيه، تبديل المنفذ للمطعم *بدون* أي
  نافذة تأكيد، إضافة صنف مطعم على نفس الفاتورة، السلة عرضت مجموعتين بعنوان
  لكل منفذ، إرسال للمطبخ (تذكرتان منفصلتان بالتوجيه الصح اتأكدوا من قاعدة
  البيانات مباشرة)، فتح وردية، تحصيل الدفع كاش، **فحص القيود المحاسبية في
  قاعدة البيانات مباشرة**: قيدان منفصلان (233.10 كافيه + 327.60 مطعم =
  560.70 بالظبط).

## 5. نقطة التراجع

- rollback tags: `resort-os-rollback/{backend,celery_worker,celery_beat,el_kheima}:pre-ddfbaaa`
  (الأربعة كانوا على `679f76e` قبل هذا النشر).
- rollback manifest:
  `/var/backups/resort-os/source-releases/ddfbaaa-rollback-images.txt`
- release السابق `/opt/resort-os-releases/a3e8abb` (وقبله `679f76e`) لسه
  محفوظين كاملين على القرص.
- نسخة DB قبل النشر مباشرة (Backend بيتغيّر فعليًا لأول مرة منذ فترة، أخذنا
  نسخة رغم عدم وجود migration):
  `/var/backups/resort-os/database/resort_os_20260802_031105.dump`،
  SHA-256 `7f65646441948e4250b9f141f6d01855e5516794507626eb09d5ebe4d97fd238`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB).

## 6. قبول الإنتاج

- `https://app.elkheima.com` و`/health`: HTTP 200.
- 8 حاويات Running، `RestartCount=0` للأربعة المتغيّرة (backend،
  celery_worker، celery_beat، el_kheima).
- severe logs: صفر.
- تأكيد مباشر إن الكود الجديد فعلاً شغال داخل الحاوية الحية (مش بس
  الصورة اتبنت): `grep allow_cross_outlet` جوه container الـbackend
  الشغالة رجع 3 نتائج.
