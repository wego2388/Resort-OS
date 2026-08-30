# REL-24 — إصلاح 11 finding متبقية من مراجعة Codex (H-01 → M-04)

## السياق

استكمال مباشر لـ `2026-08-30_REL-23_codex-review-C01-finance-branch-isolation_claude_handoff.md`
— بعد ما Mohamed وافق على الدفعة 1 (C-01) ونفّذتها، وافق على "كمل بالدفعة 2"
ثم طلب صراحةً إكمال كل الدفعات المتبقية من غير توقف ("اعمل المهام كلها لا
تتوقف"). هذا الملف يوثّق الدفعات 2-5 كاملة (11 finding: H-01 حتى M-04).

كل finding اتنفّذ بنفس المنهج: قراءة الكود الفعلي قبل التعديل، إصلاح
مستهدف، اختبار انحدار جديد يثبت الإصلاح (مش سيناريو وهمي)، `pytest`
للموديول المتأثر أخضر، ثم `pytest tests/ -v` كامل في الآخر.

## H-06 — إلغاء حجز PMS وهو الضيف لسه نازل (checked_in)

**الملف**: `backend/app/modules/pms/services.py::cancel_booking`

الحارس كان denylist (يرفض `checked_out`/`cancelled` بس) بدل allowlist —
حجز `checked_in` (ضيف نازل فعليًا، عنده Folio مفتوح) كان يقدر يتلغي
بمسار الإلغاء العادي، فترجع الغرفة `available` وهي لسه فيها ضيف مقيم
(حجز مزدوج حقيقي)، والفوليو يفضل مفتوح بلا تسوية. الحارس بقى allowlist
صريح: `confirmed`/`no_show` بس. حجز `checked_in` لازم يمر بـ`checkout_booking`.

**اختبار جديد**: `test_cannot_cancel_checked_in_booking` (test_pms.py).

## H-04 — تسوية عقود B2B الشاطئ (atomicity + حد أعلى)

**الملفات**: `backend/app/modules/beach/crud.py`, `services.py`

3 باجات:
1. العقد كان بيتقرا من غير قفل — تسويتان متزامنتان ممكن الاتنين يرحّلوا
   قيد تحصيل. أُضيف `crud.lock_b2b_contract_for_update` (نفس نمط
   `lock_contract_day_for_update`)، بيتقفل الأول في `settle_b2b_contract`.
2. `get_b2b_outstanding_balance` مفيهاش حد أعلى (`through`) — تسوية بتاريخ
   معيّن كانت بتجمع شهور مستقبلية كمان. أُضيف param `through` اختياري.
3. القيد كان بيترحّل عبر `post_journal_entry` (commit داخلي) قبل تحديث
   `last_settled_at` بـcommit منفصل — فشل بينهم كان يسيب قيد بلا علامة
   تسوية. دلوقتي القيد بيتبني بـ`finance_crud.create_journal_entry` (flush
   بس) وcommit واحد بس في الآخر.

كمان: رفض `settled_through` في المستقبل.

**اختبارات جديدة** (test_beach.py): `test_settle_through_date_does_not_
sweep_future_months`, `test_settle_rejects_future_date`,
`test_settle_twice_in_a_row_posts_journal_only_once`.

## H-05 — ترتيب الأقفال في تحصيل/إلغاء عقود الملكية الجزئية

**الملف**: `backend/app/modules/timeshare/services.py::pay_installment`, `pay_maintenance_due`

كانت تقفل القسط/المستحق الأول ثم تقرا العقد من غير قفل — عكس
`cancel_contract` (بتقفل العقد الأول). ترتيب أقفال غير ثابت بين المسارين
= سباق حقيقي ممكن. الاتنين بقوا يقفلوا العقد الأول دايمًا (نفس ترتيب
`cancel_contract`)، عبر lookup غير مقفول لمعرفة `contract_id` الأول.

لا يوجد Postgres حقيقي متاح لاختبار تزامن synthetic ذو معنى في السلوك
السابق — الإصلاح اتأكد سلوكيًا عبر مجموعة اختبارات timeshare الكاملة
(77 اختبار) اللي فضلت خضراء بعد التغيير، بما فيها كل سيناريوهات pay/
cancel الموجودة.

## H-03 — استلام أمر شراء (قفل + تجميع تكرار الصنف)

**الملفات**: `backend/app/modules/inventory/crud.py`, `services.py`

1. أمر الشراء كان بيتقرا من غير قفل. أُضيف `crud.lock_purchase_order_
   for_update`.
2. كل سطر استلام كان بيتحقق لوحده من `remaining` (نفس القيمة القديمة) —
   طلب فيه سطرين بنفس `item_id` (60+60 لصنف متبقيه 100) كان كل سطر يعدّي
   بمفرده. دلوقتي الكميات بتتجمّع بـ`item_id` قبل أي تحقق.

**اختبار جديد**: `test_duplicate_item_id_in_same_request_is_aggregated_
not_bypassed` (test_inventory.py).

## H-01 — فجوات عزل فرع متبقية في HR

**الملف**: `backend/app/modules/hr/api/router.py`

أُضيف `assert_branch_access` لـ: `list_departments`/`create_department`،
`list_shifts`/`create_shift`، `get_attendance_policy`/`upsert_attendance_
policy`، `create_penalty_type`، `create_rota_template`/`get_rota_template`،
`get_rota` (قائمة الجدول)، `create_leave_type`، `create_leave_request`،
`create_swap_request`. (`list_penalty_types`/`list_leave_types` مقصودين
مفتوحين — بيانات مرجعية لأي مستخدم، زي `list_leave_types` من REL-22).

**اختبار جديد**: `test_cross_branch_manager_cannot_list_or_create_
departments` (تمثيلي للدفعة، test_hr_http.py).

## H-02 — Analytics بيثق في branch_id من غير فحص فرع

**الملف**: `backend/app/modules/analytics/api/router.py`

كل endpoint تقريبًا (`revenue`, `occupancy`, `hr`, `maintenance`, `crm`,
`inventory`, `daily-stats`, `utilities` GET/POST, `energy`, `energy/trend`
+export, `reviews` list/insights, `dashboard`) كان على `get_manager_user`
بس (دور، مش فرع). أُضيف helper مشترك `_assert_analytics_branch` وطُبّق
على كل الـendpoints دي. كمان `survey-token`/`survey-token/timeshare`/
`.../send` كانت بتتحقق من تناسق المورد (booking.branch_id == branch_id)
بس مش من إن الفاعل نفسه له وصول لهذا الفرع — أُضيف الفحص الناقص.

**اختبار جديد**: `test_cross_branch_manager_cannot_view_revenue` (تمثيلي).

## H-07 — وعاء التأمين الاجتماعي + توازن قيد الرواتب

**الملفات**: `backend/app/modules/hr/schemas.py` (لا تعديل فعلي — التحقق
في services)، `services.py`، `api/router.py`

1. `insurance_base_salary > basic_salary` كان يعدّي من غير أي رفض —
   ينتج `employee_si` أكبر من المستحق فعليًا. أُضيف `_validate_insurance_
   base_salary` في `create_employee`/`update_employee` (بيقارن بالقيمة
   الفعلية الحالية للموظف عند partial update).
2. أثناء التحقق، اكتُشفت فجوة أعمق: `_post_payroll_journal` كانت بتنادي
   `finance_crud.create_journal_entry` مباشرة (بدون فحص توازن) بدل
   `finance_services.post_journal_entry` — القيد المجمّع مش متوازن
   بالبناء الرياضي زي `post_simple_revenue_journal` (مبني من أعمدة
   run-level منفصلة)، فحافة زي وعاء تأمين منفوخ كانت تقدر تكسر التوازن
   بصمت. بقى بينادي `post_journal_entry` (بترفض بـValueError واضح).
3. أثر جانبي: `PATCH /hr/employees/{id}` كان بيترجم **كل** ValueError
   من `update_employee` لـ404 "غير موجود" — حتى أخطاء تحقق حقيقية. اتفصل
   لـ404 (موظف مش موجود) و400 (أي فشل تحقق تاني).

**اختبارات جديدة**: `test_create_employee_rejects_insurance_base_above_
basic_salary`, `test_update_employee_rejects_lowering_basic_salary_below_
existing_insurance_base` (test_hr_http.py)، `test_approve_payroll_run_
rejects_unbalanced_journal_from_bad_insurance_base` (test_hr.py — بيحاكي
INSERT مباشر يتخطى فحص الـservice، عشان يمثّل بيانات قديمة فاسدة).

## M-01 — عقود ملكية جزئية ملغاة في تقارير التحصيل

**الملف**: `backend/app/modules/timeshare/crud.py`

`installments_summary`, `maintenance_dues_summary`, `overall_collection`
كانت من غير استبعاد `TimeshareContract.status == "cancelled"` (بعكس
`stats_by_partner`/`stats_by_room_type` اللي بيستبعدوا فعلاً). REL-22
منعت بس أقساط عقد ملغي من "التحول" لـoverdue لأول مرة بعد الإلغاء —
قسط كان overdue بالفعل قبل الإلغاء فضل محسوب للأبد.

**اختبار جديد**: `test_cancelled_contract_excluded_from_collection_
reports` (test_timeshare.py).

## M-02 — إدارة PIN بلا فحص فرع/مستوى نسبي

**الملفات**: `backend/app/modules/core/services.py`, `api/router.py`

أي مدير كان يقدر يقرا/يعيد ضبط PIN أي `user_id` بدون تحقق من وجوده،
فرعه، أو مستواه. أُضيفت `assert_can_manage_target_pin(db, actor, target_
user_id, action_desc)`: نفس الفرع النشط للفاعل (عبر `UserBranchMembership`)
+ target أدنى من الفاعل صراحةً (يمنع peers/higher)، مطبّقة حتى على
super_admin. مُوصّلة لـ`GET/POST /pins/{user_id}`.

**مؤجَّل عمدًا** (خارج نطاق هذا الإصلاح): Codex ذكر كمان إن
`resolve_pin_approval` (المستخدمة في void/refund/discount عبر موديولات
كتير) مالهاش branch context — تغيير أعمق وأوسع الأثر، محتاج مراجعة
منفصلة قبل التنفيذ.

**اختبارات جديدة** (test_core_http.py): أصلحت `test_manager_can_set_
another_users_pin` (كانت بتستخدم headers بلا فرع)، أضفت
`test_cross_branch_manager_cannot_set_pin`,
`test_manager_cannot_set_pin_for_peer_or_higher_level`.

## M-03 — استبيان الرضا (survey token) قابل للتكرار بلا حد

**الملفات**: `backend/app/modules/analytics/models.py`, `services.py`,
`api/router.py`، `backend/app/core/rate_limit.py`،
migration `6449668eb81a_guest_review_replay_guard.py`

Survey token صالح 7 أيام بلا أي تتبع "تم استهلاكه" — نفس اللينك كان
يتبعت عدد غير محدود من المرات. الحل: partial unique index على
`guest_reviews.booking_id`/`timeshare_visit_id` (WHERE NOT NULL) — أقصى
تقييم واحد لكل مرجع. `submit_review` بيمسك `IntegrityError` ويرفعها
كـ`ValueError` واضح، والراوتر بيترجمها لـ409. كمان أُضيف rate limit
(`public`, 20/60s) على `POST /analytics/reviews/submit` (كان بدون أي حد
خالص قبل كده).

المigration اتأكدت فعليًا على Postgres حقيقي (upgrade→downgrade→upgrade،
راجع details في هذا الـhandoff نفسه وقت التنفيذ) — الفهرس اتفحص مباشرة
عبر `pg_indexes`. نفس الـIndex معرّف كمان في `GuestReview.__table_args__`
عشان تستات الوحدة (SQLite `create_all`) تفحص السلوك.

**اختبار جديد**: `test_submit_review_rejects_replayed_survey_token`
(test_analytics_http.py).

## M-04 — شاشة أسعار الصرف بتنادي مسار API غلط

**الملف**: `frontend/apps/el-kheima/src/views/admin/FinanceView.vue`

`loadExchangeRates`/`saveExchangeRate` كانا بينادوا `/finance/exchange-
rates` مباشرة (ناقص بادئة `/api/v1`) بدل `ENDPOINTS.finance.exchangeRates`
— axios baseURL فاضي، وnginx بيوجّه `/api/` بس، فالمسار الناقص كان بيقع
في SPA fallback (HTML بدل JSON) — الشاشة معطّلة تمامًا في الإنتاج رغم
نجاح build/type-check. اتصلح باستخدام `ENDPOINTS.finance.exchangeRates`
زي باقي الاستدعاءات في نفس الملف.

**تحقق**: `pnpm --filter el-kheima type-check` نظيف، `pnpm --filter
el-kheima test:frontend` (بيشمل `validate-i18n.mjs` + vitest) — 106/106.

## التحقق الإجمالي

- `pytest tests/ -v` كامل — أخضر (اتأكد بعد كل finding على حدة، ثم مرة
  أخيرة شاملة).
- Migration جديدة واحدة (`6449668eb81a`) — اتأكدت upgrade/downgrade/
  upgrade على Postgres حقيقي (راجع M-03 فوق).
- الفرونت إند: type-check + i18n + vitest نظاف بالكامل.
- 16 اختبار انحدار جديد + عدد من الاختبارات الموجودة اتصلحت (fixtures
  headers بلا سياق فرع بقت تستخدم helpers الفرع الصحيحة، نفس نمط REL-23).

## Deploy

**لسه مطلوب — خطوة منفصلة، مش جزء من الدفعة دي.** الكود commit فقط
(محلي، بدون push).
