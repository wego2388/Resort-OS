# خارطة طريق Resort OS — المهام الكاملة
> آخر تحديث: 2026-07-11
> الأولوية مبنية على أثر تشغيلي حقيقي — مش رأي، مش تخمين.
> **مراجعة تحقق (2026-07-11)**: كل بند اتراجع فعليًا ضد الكود (مش قراءة سطحية) — P-02/R-03 كانوا
> ✅ خلصوا بالفعل، S-02/S-03/T-02 اتصححت ملاحظاتهم التقنية. الباقي اتأكد إنه دقيق.

---

## كيف تقرأ هذا الملف

كل مهمة فيها:
- **الحالة** — ⬜ لم تبدأ | 🔄 جارية | ✅ مكتملة
- **الحجم** — S (ساعات) | M (يوم–يومين) | L (أسبوع) | XL (أسبوعين+)
- **المخاطرة** — 🟢 منخفضة | 🟡 متوسطة | 🔴 عالية (داتا إنتاج)
- **ملاحظة تقنية** — backend موجود / frontend ناقص / جديد كامل

---

## المرحلة الأولى — عاجل ويومي 🔥
> هذه المهام تؤثر على التشغيل اليومي الحالي. ابدأ بها.

### 1.1 نظام الوردية الكامل (Shift System)

| #    | المهمة                                                                                                                | الحالة         | الحجم | المخاطرة | ملاحظة                                                                                                                                                                                                             |
| ---- | --------------------------------------------------------------------------------------------------------------------- | -------------- | ----- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| S-01 | **ShiftDashboard** — صفحة `/pos/shift` تعرض: ملخص المبيعات، الطاولات المفتوحة live، الطلبات الجارية، زرار قفل الوردية | ✅ (2026-07-11) | M     | 🟢        | تم                                                                                                                                                                                                                 |
| S-02 | **InvoiceLogModal** — سجل فواتير الوردية الحالية، مرئي للكاشير فقط (لا يرى ورديات غيره)                               | ✅ (2026-07-11) | S     | 🟢        | تم — `GET /finance/shifts/{id}/invoices` جديد + `list_shift_payments_with_folio` (joinedload، بدون N+1)                                                                                                            |
| S-03 | **PinGuardModal** — كومبوننت PIN قابل للإعادة (min_level كـ prop) يُستخدم لفتح سجل الفواتير بكود محاسب/مدير            | ✅ (2026-07-11) | S     | 🟢        | تم — استُخرج من `OrderDetailModal.vue`، بقى مُستخدم في S-02 وS-06 كمان                                                                                                                                               |
| S-04 | **X-Report** — تقرير مبيعات لحظي وسط الوردية بدون قفلها (`GET /finance/shifts/{id}/report` موجود)                     | ✅ (2026-07-11) | S     | 🟢        | تم                                                                                                                                                                                                                 |
| S-05 | **ShiftDetail في FinanceView** — drill-down لكل وردية (فواتير + عدّ الكاش)، فلتر "فرق > 0"، ألوان variance             | ✅ (2026-07-11) | S     | 🟢        | تم                                                                                                                                                                                                                 |
| S-06 | **PIN guard على قفل الوردية بفرق كبير** — بدل رفض 400 تلقائي، يسمح للمدير يتخطى بكوده                                 | ✅ (2026-07-11) | M     | 🟡        | تم — `force_close`+PIN عبر `resolve_pin_approval`، يسجّل `AuditLog(action="close_shift_variance_override")`. باج حقيقي اتصلح أثناء الشغل: `AuditLogRead` ماكانش بيعرض عمود `approved_by` رغم إنه موجود ومتعبّى فعليًا |

**ما يحتاجه backend في S-06 فقط:**
```
finance/api/router.py  → query param: force_close=true + pin_user_id
finance/services.py    → تحقق PIN قبل تخطي threshold
finance/schemas.py     → ShiftInvoiceLine بسيط
```

---

### 1.2 ميزات POS اليومية الناقصة

| #    | المهمة                                                                                       | الحالة         | الحجم | المخاطرة | ملاحظة                                                                                                                                                                |
| ---- | -------------------------------------------------------------------------------------------- | -------------- | ----- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P-01 | **Table Transfer** — نقل طلب من طاولة لأخرى (ضيوف اتحركوا)                                   | ✅ (2026-07-12) | M     | 🟡        | تم — `PATCH /restaurant/orders/{id}/transfer` + "نقل لطاولة" في OrderDetailModal.vue                                                                                  |
| P-02 | **Discount Button في POS** — زرار خصم مباشر في شاشة الكاشير (بدون فتح OrderDetailModal)      | ✅ (2026-07-11) | S     | 🟢        | تم — `applyDiscountToCart()` في RestaurantPOSView.vue وCafePOSView.vue                                                                                                |
| P-03 | **Item Availability Schedule** — صنف يشتغل في أوقات محددة (إفطار 7-11، غداء 12-4، عشاء 7-11) | ✅ (2026-07-12) | M     | 🟡        | تم — `available_from_time`/`available_until_time` على MenuItem وCafeItem، بيدعم نطاق عابر لمنتصف الليل                                                              |
| P-04 | **Night Audit Frontend** — زرار تشغيل night audit اليومي للاستقبال                           | ✅ (2026-07-11) | S     | 🟢        | تم — زرار + مودال نتيجة في RoomsView.vue. ⚠️ تصحيح: الزرار بيبان لـ admin+ بس مش الاستقبال (`run_night_audit` محتاج get_admin_user، مش get_manager_user، في الباك إند) |
| P-05 | **Kitchen Item Bump** — تأكيد صنف بصنف من شاشة KDS (بدل تأكيد الـ ticket كلها)               | ✅ (2026-07-12) | M     | 🟡        | تم — `PATCH /restaurant/orders/{order_id}/items/{item_id}/status`، KitchenTicket بقى مشتق مش snapshot مجمّد                                                          |
| P-06 | **Rate Plans Frontend** — شاشة إدارة خطط الأسعار الموسمية/العروض                             | ✅ (2026-07-12) | M     | 🟢        | تم — `PATCH /pms/rate-plans/{id}` (تعديل + تعطيل)                                                                                                                     |

---

### 1.3 تحسينات أمان عاجلة

| #    | المهمة                                                                                    | الحالة               | الحجم | المخاطرة | ملاحظة                                                                                                                          |
| ---- | ----------------------------------------------------------------------------------------- | -------------------- | ----- | -------- | ------------------------------------------------------------------------------------------------------------------------------- |
| A-01 | **WebSocket Authentication** — الـ KDS/tables/beach WebSocket بدون auth حالياً             | ✅ (2026-07-11)       | S     | 🟡        | تم — `get_websocket_user()` موحّد لكل الـ 6 قنوات (KDS/tables/pms rooms/beach/alerts/analytics)، `?token=` من useResortWebSocket |
| A-02 | **Inventory Low-Stock Alert** — Celery task يبعت واتساب للمدير لما مخزون يوصل للحد الأدنى | ✅ (تأكيد 2026-07-11) | S     | 🟢        | كان موجود بالفعل — `inventory_tasks.check_low_stock` مسجّل في celery beat (7 صباحًا يوميًا)، مختبر بالكامل                         |

---

## المرحلة الثانية — مهم ويُضاف قريباً 📈

### 2.1 ميزات POS متقدمة

| #    | المهمة                                                               | الحالة         | الحجم | المخاطرة | ملاحظة                                                                                                                         |
| ---- | -------------------------------------------------------------------- | -------------- | ----- | -------- | ------------------------------------------------------------------------------------------------------------------------------ |
| P-07 | **Split Bill** — تقسيم الفاتورة على أكثر من شخص                      | ⬜              | L     | 🟡        | Backend + Frontend جديدين                                                                                                      |
| P-08 | **Merge Tables** — دمج طاولتين في أوردر واحد                         | ⬜              | M     | 🟡        | Backend: `POST /restaurant/orders/{id}/merge`                                                                                  |
| P-09 | **Table Reservation (مطعم)** — حجز طاولة مسبقاً (مختلف عن حجز الغرفة) | ⬜              | L     | 🟡        | Backend: جدول `restaurant_reservations` جديد                                                                                   |
| P-10 | **Course Firing** — إرسال المطبخ بالمراحل (مقبّلات أولاً، ثم رئيسية)   | ⬜              | M     | 🟡        | Backend: `course_number` على OrderItem + `fire_course` endpoint                                                                |
| P-11 | **Sales Leaderboard Frontend** — عرض ترتيب الموظفين حسب المبيعات     | ✅ (2026-07-11) | S     | 🟢        | تم — تاب "🏆 لوحة الأداء" جديد في HRView.vue، ميداليات لأول 3، فلتر مدى تاريخ                                                   |
| P-12 | **Housekeeping Assignment** — تعيين موظف على task تنظيف من الفرونت   | ✅ (2026-07-11) | S     | 🟢        | تم — ⚠️ تصحيح: `assigned_to` ماكانش في `HousekeepingTaskStatusUpdate` أصلاً، اتضاف للـ schema+service+router كمان مش frontend بس |

---

### 2.2 CRM وولاء العملاء

| #    | المهمة                                                                                    | الحالة | الحجم | المخاطرة | ملاحظة                                         |
| ---- | ----------------------------------------------------------------------------------------- | ------ | ----- | -------- | ---------------------------------------------- |
| C-01 | **Loyalty Points** — نقاط تراكمية للعملاء (X نقطة لكل جنيه، صرف كخصم)                     | ⬜      | L     | 🟡        | Backend: `customer.points` + endpoints صرف/كسب |
| C-02 | **Voucher / Gift Card** — كوبون بكود يعطي خصم أو رصيد ثابت (مختلف عن ConditionalDiscount) | ⬜      | L     | 🟡        | Backend: جدول `vouchers` جديد                  |
| C-03 | **Lead → Booking Conversion** — تحويل lead لحجز مباشرة بزرار واحد                         | ✅ (2026-07-12) | S     | 🟢        | تم — `POST /crm/leads/{id}/convert` بيبني حجز حقيقي عبر `pms.services.create_booking`        |
| C-04 | **Birthday/Anniversary Automation** — تنبيه واتساب تلقائي في مناسبات العملاء              | ✅ (تأكيد 2026-07-12) | S     | 🟢        | كان موجود بالفعل ومختبر بالكامل — لا تغيير محتاج        |

---

### 2.3 تقارير وتحليلات

| #    | المهمة                                                                                     | الحالة              | الحجم | المخاطرة | ملاحظة                                                                                              |
| ---- | ------------------------------------------------------------------------------------------ | ------------------- | ----- | -------- | --------------------------------------------------------------------------------------------------- |
| R-01 | **Real-time Analytics WebSocket** — لوحة تحليلات تتحدّث لحظياً (مبيعات الساعة، أكثر الأصناف) | ⬜                   | L     | 🟡        | Backend: WebSocket على `/ws/analytics/kpis` موجود — frontend ناقص                                   |
| R-02 | **Revenue Comparison** — مقارنة مع نفس اليوم الأسبوع الماضي / الشهر الماضي                 | 🔄 جزئي (2026-07-11) | S     | 🟢        | تريند الطاقة عنده YoY كامل (`/analytics/energy/trend`) — نفس الفكرة لسه ناقصة لتقرير المبيعات العام |
| R-03 | **Energy/Utilities Report** — تقرير تكلفة الكهرباء/المياه لكل ضيف بشكل واضح                | ✅ (2026-07-11)      | S     | 🟢        | تم — AnalyticsView.vue فيه KPI + ترند 24 شهر + تصدير Excel                                          |

---

## المرحلة الثالثة — المشروع الكبير (Dining Module Merge) 🏗️
> هذه مهمة معمارية كبيرة. لا تبدأ قبل إتمام المرحلتين الأولى والثانية.

### الهدف
دمج `restaurant` + `cafe` في موديول `dining` واحد بنموذج **Outlet** (نفس Foodics).

```
Outlet (restaurant | cafe | bar | buffet | ...)
  ├── VenueTable   ← دمج dining_tables + cafe_tables
  ├── MenuItem     ← دمج menu_items + cafe_items
  ├── MenuCategory ← دمج menu_categories + cafe_categories
  └── Order        ← دمج orders + cafe_orders
```

**ما يكسبه الدمج:**
- صنف واحد يُباع من المطعم والكافيه معاً
- إضافة outlet جديد (بار، بوفيه) = صفر كود جديد
- تقارير موحدة بدون `_safe_query` مكرر
- API نظيف: `/api/v1/dining/outlets/{id}/orders` بدل `/restaurant` و `/cafe` منفصلين

### الخطوات — بالترتيب الإجباري

| #    | المرحلة                                                                                     | الحجم | المخاطرة | شرط البدء   |
| ---- | ------------------------------------------------------------------------------------------- | ----- | -------- | ----------- |
| D-01 | **Models** — إنشاء `app/modules/dining/models.py` بدون لمس أي كود قائم                      | M     | 🟢        | لا يوجد     |
| D-02 | **Migration** — إنشاء الجداول الجديدة + نقل البيانات + pg_dump قبلها                        | M     | 🔴        | backup كامل |
| D-03 | **CRUD + Schemas + Services** — موحّد، `outlet.revenue_account_code` بدل hardcoded 4200/4400 | L     | 🟡        | D-01 + D-02 |
| D-04 | **Router الموحد** — `/api/v1/dining/outlets/{id}/...` + aliases مؤقتة للـ paths القديمة     | L     | 🟡        | D-03        |
| D-05 | **تحديث analytics + finance** — استيراد من `dining.models` بدل `restaurant` + `cafe`        | S     | 🟢        | D-04        |
| D-06 | **Frontend Endpoints** — إضافة `dining.*` في `endpoints.ts`                                 | S     | 🟢        | D-04        |
| D-07 | **Frontend Views** — `UnifiedPOSView.vue` + `DiningMenuView.vue` (outlet selector)          | L     | 🟡        | D-06        |
| D-08 | **Tests + Cleanup** — حذف الموديولات القديمة بعد التحقق الكامل                              | L     | 🟡        | D-07        |

**قبل D-02 لازم:**
1. `pg_dump` كامل
2. تشغيل D-01 + D-02 على بيئة test أولاً والتحقق من عدد الصفوف
3. الـ aliases في D-04 تفضل حتى يتأكد الـ frontend كله شغال

**حجم الأثر:**
- 16 جدول → 8
- ~4,219 سطر tests لازم تتحدث
- 6 frontend views لازم تتحدث

---

## المرحلة الرابعة — تحسينات بنية تقنية 🔧
> مهمة لكن مش عاجلة. تُنفَّذ بعد استقرار التشغيل.

| #    | المهمة                                                                        | الحالة | الحجم | المخاطرة | ملاحظة                                                                                                                                                                                                                                        |
| ---- | ----------------------------------------------------------------------------- | ------ | ----- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| T-01 | **localStorage → httpOnly Cookie**                                            | ⬜      | L     | 🔴        | أمان — يحتاج تغيير auth flow كامل                                                                                                                                                                                                             |
| T-02 | **Order Number Race Condition** — `COUNT` بدون row-level lock تحت تزامن حقيقي | ⬜      | S     | 🟡        | ⚠️ تصحيح: `order_number` عنده `unique=True` في الداتابيز، فمش هيتولّد رقم مكرر فعليًا — اللي هيحصل إن الطلب المتزامن التاني هيفشل بـ 500 غير مُتحكّم فيه (IntegrityError) بدل ما ياخد رقم صحيح. نفس الخطورة، الحل: `SELECT FOR UPDATE` أو sequence |
| T-03 | **Celery Tasks Error Visibility** — معظم tasks بتبلع الاستثناءات بصمت         | ✅ (2026-07-12) | S     | 🟢        | تم — `notify_task_failure()` (Sentry+WhatsApp) متوصّلة في كل الـ 11 ملف `app/tasks/*.py` + `CoreTask.on_failure`                                                                                                                                                                                     |
| T-04 | **Backup خارج السيرفر** — النسخ الاحتياطي محلي فقط                            | ✅ (2026-07-12) | S     | 🟢        | تم — rclone sync اختياري في `backup_db.sh` + fallback في `restore_db.sh`، اتأكد منه حي end-to-end                                                                                                                                                                                           |
| T-05 | **Menu Item Image Upload** — رفع صور مباشرة بدل URL فقط                       | ⬜      | M     | 🟢        | Backend: S3/local storage endpoint                                                                                                                                                                                                            |
| T-06 | **Multi-Branch Menu Copy** — نسخ قائمة فرع لفرع آخر                           | ⬜      | S     | 🟢        | Backend: `POST /dining/outlets/{id}/copy`                                                                                                                                                                                                     |

---

## ملخص سريع — الترتيب المقترح للبدء

```
الأسبوع 1–2:  S-01, S-02, S-03, S-04 (نظام الوردية)
الأسبوع 3:    P-01, P-02, A-01, A-02 (POS + أمان)
الأسبوع 4:    P-03, P-04, P-05, S-05 (ميزات POS متبقية)
الشهر 2:      H-01, H-02, H-03, H-04 (الموارد البشرية — السلف والدفعات والإجازات)
الشهر 2:      P-07, C-01, C-02 (split bill + loyalty)
الشهر 3+:     D-01 → D-08 (dining merge — المشروع الكبير)
```

---

## المرحلة الخامسة — الموارد البشرية: ما كشفته كشوف المرتبات الحقيقية 📋
> مبنية على تحليل ملفات Excel الفعلية (يناير 2026): 48 موظف، 235,500 ج رواتب أساسية، 60,066 ج سلف شهرية (26% من المستحق).
> النظام الحالي يحسب الرواتب لكنه لا يغطي دورة حياة المرتب الكاملة كما يعمل المنتجع فعلاً.

### ما كشفته الملفات — الفجوات الحقيقية

**كيف يصرف المنتجع المرتبات حالياً (4 ملفات Excel):**
- `مرتبات شهر يناير.xlsx` — كشف المرتب الرئيسي (راتب + أوفرتايم + تأمينات + سلف + صافي)
- `دفعات المرتبات.xlsx` — سجل الدفعات اليومية (موظف بياخد دفعات على مدار الشهر)
- `Attendance.xlsx` — حضور يوم بيوم (p=حاضر، v=إجازة، u=غياب)
- `بار الخيمه.xlsm` — إيرادات البار يومياً (شاطئ + مشروبات + طعام + شيشة)

| #    | المهمة                                                                                                    | الحالة | الحجم | المخاطرة | لماذا؟                                                            |
| ---- | --------------------------------------------------------------------------------------------------------- | ------ | ----- | -------- | ----------------------------------------------------------------- |
| H-01 | **نظام السلف** `salary_advances` — سجل السلفة، المبلغ، تاريخ الصرف، وحدة الخصم الشهرية، الرصيد المتبقي    | ✅ (2026-07-12) | M     | 🟡        | تم — `SalaryAdvance` model + API كامل، مخصوم أوتوماتيك جوه `run_payroll_for_branch`      |
| H-02 | **الدفعات الجزئية** `advance_payments` — الموظف بياخد دفعات خلال الشهر تُخصم من المرتب النهائي             | ✅ (2026-07-12) | M     | 🟡        | تم — `AdvancePayment` model + API، نفس مسار الخصم بتاع H-01        |
| H-03 | **رصيد الإجازات التراكمي** `leave_balance` — 7.5 يوم/شهر يُضاف، ويُخصم المستهلك، ويُحسب الرصيد المتبقي شهرياً | ✅ (2026-07-12) | M     | 🟡        | تم — `LeaveBalanceMonthly` model + API  |
| H-04 | **وعاء التأمين المستقل** `insurance_base_salary` — حقل منفصل على الموظف (مختلف عن الراتب الأساسي)         | ✅ (2026-07-12) | S     | 🟢        | تم — عمود `Employee.insurance_base_salary`، مُستخدم فعليًا في حساب التأمين بدل الراتب الأساسي |
| H-05 | **مكافأة الأعياد** `holiday_bonus` — مبلغ مكافأة الأعياد الرسمية لكل موظف                                 | ✅ (2026-07-12) | S     | 🟢        | تم — عمود `Employee.holiday_bonus`، مُضاف فعليًا لصافي المرتب في `hr_engine`                   |
| H-06 | **كشف مرتبات قابل للطباعة** — تقرير PDF بنفس شكل Excel الحالي (اسم، أيام، راتب، خصومات، صافي)             | ⬜      | M     | 🟢        | النظام عنده PDF قسيمة راتب للموظف — لكن مفيش كشف جماعي للمحاسب    |
| H-07 | **استيراد الحضور من Excel** — رفع ملف Attendance وتحويله لـ `AttendanceRecord` تلقائياً                    | ✅ (2026-07-12) | M     | 🟢        | تم — `POST /hr/attendance/import-excel`، upsert حقيقي مش skip-on-duplicate                     |

### الأرقام المرجعية (يناير 2026)

| البند                   | المبلغ          |
| ----------------------- | --------------- |
| إجمالي رواتب أساسية     | 235,500 ج       |
| إجمالي أوفرتايم         | 24,500 ج        |
| إجمالي مستحق            | 226,117 ج       |
| إجمالي تأمين حصة العامل | 5,115 ج         |
| إجمالي السلف المخصومة   | 60,066 ج        |
| صافي للصرف              | 160,936 ج       |
| عدد الموظفين            | 48              |
| الوظائف                 | 25 وظيفة مختلفة |

### الوظائف الموجودة في المنتجع (للمرجعية عند إضافة موظفين)
```
إدارة:    مدير عام، مدير مالي، مدير حسابات، محاسب (×2)، سوبر فايزر، كاشير (×2)
خدمة:    ويتر (×2)، مضيف، بارمان (×3)
مطبخ:    شيف (×2)، مساعد شيف، طباخ
أمن:     أمن (×2)، أمن الشاطئ، منقذ
صيانة:   نجار، سباك، كهربائي، صيانة
تنظيف:   هاوس (×5)، هاوس العماره، مشرف العماره
زراعة:   زراعه
```

---

## مرجع سريع — Backend الجاهز بدون Frontend

هذه endpoints شغالة 100% لكن لا يوجد واجهة تستخدمها:

| Endpoint                             | الميزة                            |
| ------------------------------------ | --------------------------------- |
| `POST /pms/night-audit/run`          | Night Audit اليومي                |
| `GET/POST /pms/rate-plans`           | خطط الأسعار الموسمية              |
| `GET /hr/leaderboard`                | ترتيب الموظفين حسب المبيعات       |
| `GET /finance/shifts/{id}/report`    | تقرير وردية كامل (X + Z Report)   |
| `GET /analytics/energy`              | تقرير استهلاك الطاقة              |
| `GET /analytics/energy/trend`        | ترند الطاقة                       |
| `PATCH /pms/housekeeping/tasks/{id}` | تعيين موظف على task (assigned_to) |
| `GET /analytics/reviews/insights`    | تحليل تقييمات الضيوف              |
| `WS /ws/analytics/kpis/{branch_id}`  | KPIs لحظية                        |







المهمة الرئيسية

أنت مسؤول عن إعادة بناء Frontend بالكامل ليصل إلى مستوى عالمي من حيث UI وUX وسهولة الاستخدام والأداء، مع الحفاظ على جميع وظائف النظام الحالية وعدم كسر أي API أو Business Logic أو Permissions.

قواعد أساسية

قبل أي تعديل يجب الالتزام بهذه القواعد:

لا تضف أي Business Logic داخل Vue Components.
لا تكرر أي Component.
كل شيء يبنى فوق Design System موحد.
كل شاشة يجب أن تخدم مهمة واحدة فقط.
كل تعديل يجب أن يحسن سرعة الموظف.
لا تضف Features جديدة إلا إذا كانت ضرورية لتجربة المستخدم.
لا تكسر أي API.
لا تكسر أي Route.
لا تغير أي Permission.
لا تغير أي Database Model.
جميع التحسينات Frontend فقط إلا إذا كان Backend يحتاج Endpoint صغير لتحسين UX.
أي Endpoint جديد يجب أن يكون Generic وليس خاصاً بشاشة واحدة.
المرحلة الأولى
بناء Design System احترافي

هذه المرحلة إجبارية.

يجب إنشاء Design System كامل.

Typography

توحيد

Font Sizes
Font Weights
Line Heights
Letter Spacing
Colors

إنشاء Color Tokens

Primary

Secondary

Success

Warning

Danger

Info

Surface

Border

Muted

Background

Dark

Light

بدون ألوان عشوائية.

Radius

توحيد جميع

Buttons

Cards

Dialogs

Inputs

Dropdowns

Tables

Shadows

Shadow System موحد.

Spacing

اعتماد نظام

4

8

12

16

20

24

32

40

48

64

فقط.

Icons

توحيد جميع الأيقونات.

Elevation

إنشاء مستويات واضحة.

Animations

Motion System موحد.

Focus Ring

كل عنصر قابل للوصول بلوحة المفاتيح.

Dark Mode

إصلاح كامل.

Responsive Tokens

Desktop

Tablet

POS

Mobile

المرحلة الثانية
إنشاء مكتبة Components

إعادة كتابة جميع الـ Components لتصبح قابلة لإعادة الاستخدام.

مثل

Button

IconButton

Dropdown

Combobox

Select

Autocomplete

Search

Input

Textarea

Money Input

Phone Input

Date Picker

Time Picker

Card

Stat Card

Empty State

Error State

Loading State

Skeleton

Badge

Avatar

Timeline

Toast

Notification

Modal

Drawer

Wizard

Tabs

Accordion

Command Palette

Data Table

Virtual Table

Status Badge

Permission Badge

Role Badge

Progress

Charts Wrapper

Filters

Paginator

Floating Action Button

Confirm Dialog

المرحلة الثالثة
إعادة تصميم Navigation بالكامل

Sidebar

Topbar

Breadcrumb

Recent Pages

Pinned Pages

Favorites

Global Search

Quick Actions

Command Palette

آخر الصفحات

History

Notifications

Tasks

بدون أي ازدحام.

المرحلة الرابعة
إعادة تصميم جميع Workflows

هذه أهم مرحلة.

لا يعاد تصميم الصفحات.

بل يعاد تصميم طريقة العمل.

Reception

Check In

Check Out

Room Change

Guest Search

Payments

Folio

Invoices

كل Workflow يجب أن ينتهي بأقل عدد ضغطات.

Dining (Restaurant + Cafe)

بما أنك دمجتهما داخل

app/modules/dining

فيجب أن يصبح قريباً من Foodics.

المطلوب:

POS سريع.

Table View.

Takeaway.

Delivery.

Room Charge.

Split Bill.

Merge Tables.

Transfer Order.

Course Management.

Kitchen Notes.

Modifiers.

Variants.

Discounts.

Refund.

Void.

Kitchen Display.

Offline Queue.

Cash Drawer.

Shift.

Blind Count.

Tips.

Kitchen Timer.

Fire Course.

Recall Order.

Reopen Order.

Duplicate Order.

Customer Display.

Order Status.

Realtime Updates.

Hotkeys.

Touch Friendly.

Beach

خريطة مباشرة.

سحب وإفلات.

Check In.

Check Out.

Umbrella Status.

Live Capacity.

B2B.

Walk In.

Room Charge.

Quick Sell.

Housekeeping

Room Cards

Filters

Drag Drop

Today's Tasks

Priority

Maintenance

Lost & Found

Maintenance

Kanban

Calendar

Priority

Technician

Assets

Photos

Parts

Timeline

HR

Attendance

Payroll

Leave

Loans

Penalties

Documents

Employee Profile

Finance

Journal

Payments

Receipts

Cash Flow

Shift Closing

Reports

Approval Workflow

المرحلة الخامسة
سرعة الاستخدام

كل العمليات اليومية يجب أن تكون

Click Count Optimized.

الهدف

أقل عدد ضغطات.

المرحلة السادسة
Keyboard UX

كل الشاشة تعمل بالكامل بالكيبورد.

Hotkeys

Tab Order

Focus

Shortcuts

Escape

Enter

Search

المرحلة السابعة
Touch UX

جميع الأزرار

Touch Friendly.

48px minimum.

المرحلة الثامنة
Performance

تقليل

Re-render

Large DOM

Bundle Size

Network Calls

Memory

Lazy Loading

Route Splitting

Image Optimization

Virtualization

Memoization

Caching

المرحلة التاسعة
Tables

كل الجداول يجب أن تدعم

Search

Column Picker

Resize

Sorting

Filtering

Grouping

Export

Saved Views

Pagination

Virtual Scroll

Sticky Header

Sticky Columns

Keyboard Navigation

المرحلة العاشرة
Forms

كل Forms يجب أن تحتوي على

Autosave (عند الحاجة)

Inline Validation

Error Recovery

Undo

Draft

Required Indicators

Clear Errors

Loading

Submit Protection

المرحلة الحادية عشرة
Empty States

عدم وجود أي صفحة فارغة.

كل Empty State يجب أن يساعد المستخدم.

المرحلة الثانية عشرة
Loading UX

Skeleton

Progress

Optimistic UI

Streaming

Background Refresh

المرحلة الثالثة عشرة
Notifications

Realtime.

Grouped.

Priority.

Action Buttons.

المرحلة الرابعة عشرة
Accessibility

WCAG AA.

Keyboard.

ARIA.

Contrast.

Focus.

Screen Reader.

المرحلة الخامسة عشرة
Testing

لكل شاشة جديدة:

Component Tests.
Integration Tests.
Playwright End-to-End Tests للسيناريوهات الحرجة (فتح وردية، إنشاء طلب، إغلاق فاتورة، Check-in، Check-out، وغيرها).
اختبارات Hotkeys.
اختبارات Responsive.
اختبارات Touch.
المرحلة السادسة عشرة
Frontend Code Quality

يجب مراجعة المشروع بالكامل لإزالة:

Components مكررة.
CSS مكرر.
Props غير مستخدمة.
Composables غير مستخدمة.
Stores متضخمة.
Imports غير مستخدمة.
Magic Numbers.
Inline Styles.
Inline Colors.
Inline Strings.
Dead Code.
أي منطق يمكن تبسيطه أو توحيده.
Definition of Done

لا تعتبر أي مرحلة مكتملة إلا إذا تحققت جميع الشروط التالية:

لا يوجد كود مكرر.
جميع الشاشات تستخدم Design System الموحد.
جميع المكونات قابلة لإعادة الاستخدام.
كل Workflow أسرع من السابق.
لا يوجد أي كسر في الـ API أو الـ Backend.
جميع الأدوار (Cashier، Waiter، Reception، Manager، Accountant، HR، Housekeeping...) ترى واجهات مخصصة لاحتياجاتها فقط.
الأداء أفضل من الإصدار السابق (وقت التحميل، سرعة التفاعل، وحجم الحزمة).
جميع الاختبارات تمر بنجاح.
تم توثيق أي تغيير يؤثر على تجربة الاستخدام.
ملاحظة معمارية أخيرة

بما أنك دمجت Restaurant وCafe في app/modules/dining، أنصح أن ينعكس هذا الدمج أيضًا على الواجهة بالكامل. لا تجعل هناك شاشتين منفصلتين إلا إذا اختلفت طبيعة التشغيل فعلًا. الأفضل أن تبني Dining Platform واحدة، تعمل بالمفهوم نفسه الذي تتبعه Foodics وToast:

نفس محرك الطلبات.
نفس شاشة POS.
نفس إدارة الطاولات.
نفس المطبخ (KDS).
نفس الفواتير والخصومات والمدفوعات.
والاختلافات (مطعم، كافيه، بار، Beach Service) تكون Configuration أو Outlet Type وليس نسخًا مختلفة من الواجهة أو الكود.

هذا سيقلل حجم الكود، ويرفع قابلية الصيانة، ويجعل إضافة أي Outlet جديد في المستقبل (مثل Pool Bar أو Rooftop Restaurant) تتم دون إعادة بناء النظام.









معظم مشاريع الـ ERP تركز على الشاشات، بينما الأنظمة الاحترافية تركز على من يحق له فعل ماذا، ومتى، وبأي شروط، ومن وافق على العملية، وهل يمكن مراجعتها لاحقًا.

أنا سأضيف طبقة كاملة اسمها:

Operations & Control Layer

وليس مجرد Permissions.

أولاً: نظام الصلاحيات (Permissions)

لا تعتمد على Role فقط.

بدلاً من:

Cashier

Manager

Admin

اجعل النظام يعتمد على:

Role

+

Permission

+

Outlet

+

Branch

+

Shift

+

Approval Level

مثال:

كاشير المطعم

لا يستطيع:

فتح كاش الكافيه.
رؤية تقارير الإدارة.
تعديل أسعار الأصناف.
حذف فاتورة.

لكن يستطيع:

إنشاء طلب.
استلام الدفع.
طباعة الفاتورة.
Approval Levels

هذه موجودة في الأنظمة الكبيرة.

مثلاً:

خصم أقل من 5%

↓

الكاشير يوافق.

خصم 10%

↓

Supervisor

خصم 20%

↓

Manager

خصم 40%

↓

General Manager

أكثر من ذلك

↓

Owner فقط.

Officer Approval

لا أريد كلمة

Manager Password

بل

Officer Approval

مثلاً

Discount

↓

Officer PIN

↓

Reason

↓

Audit


ويتم تسجيل:

Who Requested

Who Approved

Time

Reason

Old Price

New Price
Void

إلغاء الطلب.

يجب أن يحتوي على:

سبب.

PIN.

Audit.

قبل وبعد.

Refund

الاسترجاع.

يحتاج:

سبب.

PIN.

رقم المرجع.

المبلغ.

طريقة الدفع.

Discount Engine

لا تجعل الخصم مجرد رقم.

أنشئ محرك خصومات.

أنواع الخصومات:

Percentage

10%

Fixed

100 EGP

Employee Discount

VIP Discount

Birthday

Coupon

Promotion

Happy Hour

Corporate

Hotel Guest

Room Charge Discount

Manager Manual

Comp Meal

Staff Meal

Influencer

Marketing Campaign

Loyalty Points

Voucher

Gift Card

قواعد الخصم

لا يسمح:

Multiple Discounts


إلا إذا كانت السياسة تسمح.

كل خصم له:

Maximum

Minimum

Expiration

Outlet

Time

Employee

Approval

Officer PIN

أي عملية حساسة:

Delete

Refund

Void

Discount

Price Override

Open Drawer

Cancel Payment

Cash Adjustment

Shift Close

Transfer Bill

Split Payment

Manual Price

تحتاج

Officer PIN.

Price Override

الكاشير لا يغير السعر مباشرة.

يضغط:

Override Price

↓

Officer PIN

↓

Reason

↓

Audit

Open Drawer

فتح درج الكاش.

حتى بدون بيع.

يسجل:

الوقت.

السبب.

الموظف.

الكاميرا.

Shift Management

فتح الوردية.

إغلاقها.

Suspend.

Resume.

Transfer.

Emergency Close.

Recount.

Blind Count.

Safe Drop.

Cash Pickup.

Float.

Cash Control

كل حركة نقدية تسجل.

Cash In

Cash Out

Petty Cash

Safe Drop

Drawer Open

Correction

Kitchen Control

من يغير حالة الطلب؟

Waiter

↓

لا.

Chef فقط.

من يعيد الطلب؟

Manager.

من يلغي الطبخة؟

Chef Approval.

Table Control

Transfer Table

Merge

Split

Move

Reopen

Cancel

كل واحدة لها Permission.

Customer Control

لا يسمح بحذف العميل.

Soft Delete فقط.

Loyalty

من يضيف نقاط؟

من يعدلها؟

من يحذفها؟

Room Charge

الكاشير لا يستطيع:

Charge لأي غرفة.

إلا إذا:

الغرفة Occupied.

الضيف مفعل.

يوجد Credit.

الصلاحية موجودة.

Offline Mode

من يسمح بإغلاق فاتورة Offline؟

ليس أي كاشير.

Reports

كل تقرير له صلاحية مستقلة.

Sales

Profit

Cash

Inventory

Payroll

VIP

Discount

Audit

Kitchen

Audit Log

أسجل كل شيء.

حتى:

Login

Logout

Discount

Refund

Delete

Price Change

PIN

Approval

Role Change

Permission Change

Device Management

أربط الجهاز.

POS-01

POS-02

Beach POS

Restaurant POS


كل جهاز له:

آخر مستخدم.

آخر Shift.

آخر Login.

IP.

MAC.

Version.

Session Management

لا يسمح:

بنفس الكاشير

يفتح

3 أجهزة.

Fraud Detection

مثلاً

إذا الكاشير عمل:

15 Refund

في ساعة.

↓

تنبيه.

20 Drawer Open

↓

تنبيه.

خصومات كثيرة

↓

تنبيه.

Void مرتفع

↓

تنبيه.

Restaurant KPIs

لكل موظف:

عدد الفواتير.

متوسط الفاتورة.

عدد الخصومات.

عدد الإلغاءات.

عدد الاسترجاع.

سرعة الخدمة.

متوسط تجهيز الطلب.

إجمالي المبيعات.

نسبة الأخطاء.

Kitchen KPIs

متوسط التحضير.

الأطباق المتأخرة.

الأطباق الملغاة.

الأطباق المعادة.

Cashier KPIs

Average Ticket

Void Rate

Refund Rate

Discount Rate

Cash Difference

Shift Accuracy

Orders/Hour

Manager Dashboard

يرى مباشرة:

🚨 الخصومات اليوم.

🚨 Refund.

🚨 Void.

🚨 Drawer Open.

🚨 Shift Difference.

🚨 Offline Sales.

🚨 Failed Payments.

🚨 Slow Kitchen.

🚨 Complaints.

أهم نصيحة معمارية

لا تجعل كلمة Role هي التي تتحكم في كل شيء.

صمم النظام بهذه المعادلة:

User
   ↓
Role
   ↓
Permission Set
   ↓
Branch
   ↓
Outlet
   ↓
Shift
   ↓
Device
   ↓
Approval Level
   ↓
Business Rules

بهذا الشكل يمكنك تشغيل نفس النظام في مطعم واحد، أو منتجع كامل، أو سلسلة فروع، دون الحاجة إلى تغيير المعمارية.

نقطة أخيرة

إذا كنت تبني مشروعًا يستهدف مستوى Foodics أو Toast، فأنا أنصح بإضافة Policy Engine مستقل عن نظام الصلاحيات. هذا المحرك لا يحدد من يستطيع تنفيذ العملية فقط، بل متى وتحت أي شروط يسمح بها.

أمثلة على ذلك:

منع الخصومات بعد إغلاق الوردية.
منع الـ Refund بعد مرور 24 ساعة إلا بموافقة مدير.
منع فتح درج الكاش أكثر من عدد معين بدون سبب.
منع الـ Room Charge إذا تجاوز العميل حد الائتمان.
منع تعديل الطلب بعد بدء تحضيره في المطبخ إلا بصلاحية أعلى.

هذا المستوى من التحكم هو ما يميز أنظمة الـ POS الاحترافية عن الأنظمة التي تعتمد فقط على الأدوار والصلاحيات.



رقم 1

نسبه الموافقه علي الخصم  الرقم السري يكون المحاسب و المدير
و الكاشير ليس لديه صلاحيه و لازم لو حيعمل خصم  لازم يدخل الرقم السري

و نسبه الاحتيال اعمل حقيقي و المهم عندي  المحاسب و المدير يكون مراقب شغل الكاشير  بالاخص السجل  و الكاشير مش شايف السجل بتاعه

في تصحيح الكاش المدير و المحاسب اللي معاهم pin
 و الماسح الضوعي انا حطبع من جديد و اجرب عليه لا تقلق  رقم 2


  و شغل الديزاين لما تخلص المهم  اعمله بي مزاج و فهم و احترافيه مناسبه للبرنامج   رقم 3
 لو عندك اي استفسارات قولي عليها
