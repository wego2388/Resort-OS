# REL-23 — إصلاح C-01: عزل الفروع في Finance (نتيجة مراجعة Codex المستقلة)

## السياق

Codex أنهى `CODEX-REVIEW-01` (مراجعة مستقلة قبل التشغيل الحقيقي، طلبها
Mohamed صراحةً بعد REL-22) ولقى finding واحد **Critical** (C-01) و7
**High** و4 **Medium** — راجع
`docs/agent-workflow/CODEX-REVIEW-01_pre-launch-critical-path-review_AR.md`
للطلب الأصلي، ونتيجة Codex الكاملة موثّقة في محادثة الجلسة (مش ملف
منفصل — Mohamed لصقها مباشرة).

Claude تحقق شخصيًا من كل الـ12 finding بقراءة الكود الفعلي (file:line)
قبل أي تنفيذ — **11 من 12 اتأكدوا مباشرة بدليل من الكود، وواحد (M-01)
قوي الاحتمال ومتّسق مع نطاق REL-22 المعروف بدون قراءة إضافية مخصصة**.
عرض خطة تنفيذ مرتبة بـ5 دفعات على Mohamed، وهو وافق صراحةً على البدء
بالدفعة 1 (C-01) بس — "ابدأ بالدفعة 1، اتفقنا".

**ملاحظة مهمة اكتُشفت أثناء التحقق**: فجوة C-01 كانت أوسع بكتير مما
وصفه Codex نفسه — عمليًا كل endpoints الكتابة (POST/PATCH) وكل التقارير
المالية الرئيسية (ميزان مراجعة/قائمة دخل/ميزانية/أعمار ديون + نسخ
PDF/Excel) كانت من غير أي فحص عزل فرع خالص، مش بس الأمثلة المحددة اللي
Codex ذكرها.

## المشكلة (C-01)

`assert_branch_access(db, user, target_branch_id, action_desc)`
(`app/modules/core/services.py`) هي الآلية المعتمدة في المشروع لعزل
الفروع — لكنها كانت مطبّقة يدويًا endpoint-بـendpoint، وده فشل مرتين
قبل كده (REL-22 على HR/Finance لسه سايب فجوات). النتيجة: أي مستخدم
Finance (محاسب/مدير) كان يقدر:
- يرحّل قيد يومية (`POST /finance/journal-entries`) لفرع تاني بمجرد
  تمرير `branch_id` مختلف.
- يقرا قيد يومية فرع تاني بـID (`GET /finance/journal-entries/{id}`).
- يسحب تقرير أرباح وخسائر/ميزانية عمومية/ميزان مراجعة **كامل** لأي فرع
  تاني (كل endpoints `/finance/reports/*` بما فيها PDF/Excel).
- يفتح فوليو، يسجّل مصروف/عهدة/إذن قبض/شيك/حساب بنكي، يقفل فترة أو سنة
  محاسبية، ينشئ حساب أو مركز تكلفة — كل ده لفرع تاني.
- حتى مع صلاحية الفرع الصحيح، يستخدم `account_id`/`cost_center_id`
  **من فرع تاني تمامًا** جوه القيد نفسه — بيلوّث أرصدة الفرعين مع بعض
  (فجوة تكامل بيانات، مش بس صلاحيات).

## الإصلاح

### 1. فحص عزل فرع على مستوى الـrouter (~30 endpoint)

كل endpoint كان ناقص، اتضاف له `core_services.assert_branch_access(...)`
(أو fetch المورد أولًا ثم فحص `resource.branch_id` لو الـendpoint شغال
بـID مش بـbranch_id مباشر) — بنفس النمط المعتمد بالفعل في هذا الملف
(`_assert_folio_branch`, `_assert_shift_branch`). اتضاف كمان 3 helper
جداد بنفس النمط: `_assert_report_branch` (10 endpoints تقارير)،
`_assert_bank_account_branch` (6 endpoints حسابات بنكية/كشوف حساب).

**الملفات**: `backend/app/modules/finance/api/router.py` (كل التعديلات).

**قائمة الـendpoints المُصلَحة** (بالترتيب في الملف):
`POST /finance/folios`, `GET /finance/folios/report/export`,
`POST /finance/accounts`, `POST /finance/journal-entries`,
`GET /finance/journal-entries/{id}`, `POST /finance/expenses`,
`POST /finance/custodies`, `POST /finance/cash-receipts`,
`GET /finance/revenue-audit-logs`,
`POST /finance/periods/{y}/{m}/close`,
`POST /finance/periods/{year}/close-year`,
`POST /finance/checks`, `PATCH /finance/checks/{id}/status`,
`POST /finance/cost-centers`, `GET /finance/cost-centers/report`,
`PATCH/DELETE /finance/discounts/{id}`,
كل 10 `GET /finance/reports/*` (+PDF/Excel)،
`POST /finance/eta/invoices`, `GET /finance/eta/invoices/{id}`,
`POST /finance/depreciation/run`, `POST /finance/bank-accounts`,
`PATCH /finance/bank-accounts/{id}`, وكل الـ5 endpoints بتاعة
statement-lines/reconciliation.

### 2. فحص ملكية الحساب/مركز التكلفة على مستوى الـservice (تكامل بيانات)

`backend/app/modules/finance/services.py::post_journal_entry` — قبل
إنشاء القيد، كل سطر بيتحقق إن `account_id` (وlo موجود `cost_center_id`)
فعليًا بيتبعوا نفس `data.branch_id`، وإلا `ValueError` → 400. اتأكّد
إن الاستدعاءات الداخلية (`post_simple_revenue_journal` في نفس الملف،
`beach.services.settle_b2b_contract`, `app/hist_gl_opening_balance.py`)
كلها بتبني حساباتها بـ`get_account_by_code(branch_id, code)` — آمنة
بالبناء، مش متأثرة بالفحص الجديد.

### 3. اختبارات انحدار جديدة

- `tests/test_api/test_finance_http.py`: 5 اختبارات جديدة —
  cross-branch لـpost/get journal entry، رفض حساب من فرع تاني، رفض
  مركز تكلفة من فرع تاني، cross-branch لتقرير ميزان المراجعة (تمثيلي
  لكل الـ10 تقارير)، cross-branch لإنشاء مركز تكلفة.
- `tests/test_api/test_finance_depreciation_and_reconciliation_http.py`:
  اختبار جديد cross-branch للحسابات البنكية (تمثيلي للـ6 endpoints).
- `super_admin_headers_for_branch(branch)` helper جديد — `super_admin_
  headers` العادية (fixture مشتركة) عمدًا من غير `bid` claim
  (`_link_shared_users_to_branch` بتستثنيها صراحةً)، فأي endpoint بقى
  بيفرض عزل فرع محتاج توكن بـ`bid` صريح حتى لسوبر أدمن — نفس مبدأ
  `assert_branch_access`'s docstring ("Even super-admin must select a
  live active context first").

### 4. إصلاح 3 اختبارات موجودة كسرت (سلوك صحيح جديد، مش تراجع)

- `test_finance_depreciation_and_reconciliation_http.py`: 13 test كانت
  بتستخدم `manager_headers` (fixture عالمية بلا عضوية فرع) — بقت
  تستخدم `manager_headers_for_branch(db, branch)` الموجودة بالفعل في
  نفس الملف من REL-22.
- `test_finance_http.py`: 3 tests كانت بتستخدم `super_admin_headers`
  العادية لعمليات بقت تفرض عزل فرع (`close_period`/`close-year`،
  `update/delete_discount`، `create_cost_center`) — بقت تستخدم
  `super_admin_headers_for_branch(branch)` الجديدة.

## التحقق

- `pytest tests/ -v` → **أخضر بالكامل، صفر فشل** (اتأكّد بعد كل تعديل
  وبعد التنفيذ الكامل، مرتين).
- كل الاختبارات الجديدة اتأكّد إنها فعلاً بتثبت الإصلاح (مش false
  positive) — راجعت كل finding بقراءة الكود الفعلي أولاً قبل كتابة أي
  test، مش نسخ سيناريو من تقرير Codex على الفاضي.
- الفرونت إند متلمسش خالص — كل النداءات الموجودة بالفعل بتبعت
  `branch_id` المستخدم النشط نفسه، فمفيش أي كسر متوقّع (اتأكّد بمراجعة
  الكود، مش تشغيل حي — الدفعة دي backend-only).

## اللي لسه معلّق (بموافقة Mohamed المسبقة، دفعات لاحقة)

الدفعات 2-5 من خطة الـ12 finding (H-01 → H-07, M-01 → M-04) لسه معلّقة
لحد ما Mohamed يوافق يبدأ فيها — راجع الرد اللي اتبعت له بعد التحقق من
مراجعة Codex للتفاصيل الكاملة لكل finding.

## Deploy

**لسه مطلوب — خطوة منفصلة، مش جزء من الدفعة دي.** الكود commit فقط.
