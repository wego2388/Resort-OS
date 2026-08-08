# حالة المشروع الحالية — El Kheima Beach Resort OS

**آخر تحديث:** 2026-08-08 — Decision 0005 Personal Credit Account منشور
ومتحقق على الإنتاج بعد موافقة Mohamed.
- **Production:** الإصدار الفعال `/opt/resort-os-releases/1d77e7b`؛ Alembic
  `c9d4e5f6a7b8 (head)`؛ PostgreSQL وRedis وكل الخدمات المتغيرة سليمة.
- **Migration:** PostgreSQL 16 local upgrade/downgrade/upgrade نجحت قبل النشر،
  ثم production upgrade من `f8aa1f0fabba` إلى `c9d4e5f6a7b8` نجح.
- **Credit acceptance:** 21/21 passed؛ Credit + Dining + Beach focused suite:
  242/242 passed؛ el-kheima وowner type-check/build passed؛ Staff frontend 95/95.
- **Full repository gates:** backend 2565 collected وصل 100% بـexit 0 وصفر
  failure؛ agent-check/Alembic/diff-check ناجحة. health/ready والنطاقات الأربعة
  وsystemd healthcheck نجحت بعد النشر، وصفر ERROR/CRITICAL/Traceback.

**السابق:** 2026-08-08 — REL-11: Owner Intelligence Cockpit Phase 1-5 نشر على `owner.elkheima.com` (commit `719a432` + `74959e4` — منشور ✅)
**البيئة:** Production — `elkheima.com` / VPS `191.218.161.133`
**قائد التنفيذ والمراجع النهائي:** Codex

هذا الملف يسجل الحقائق الحالية فقط. التاريخ السابق محفوظ في
`docs/archive/2026-07-execution/`.

## Decision 0005 — حساب آجل شخصي (منشور ✅)

- موديول `credit` كامل: Customer/Employee accounts، limit/status،
  immutable ledger، cash/bank collections، partial sale refunds، exact reversal،
  audit، pagination.
- تصحيح محاسبي للبريف: الذمم الشخصية على `1160`؛ `1200`
  يظل مخزونًا.
- Dining وBeach POS يدعمان حساب عميل أو موظف، limit override
  بـmanager PIN، وatomic posting بقيد محاسبي إلزامي.
- Beach void يعكس المديونية بدل صناعة حركة كاش، وDining item refund يخفض
  مديونية الحساب بنسبة الـtender مع cap وفروق تقريب محسومة.
- Staff App: `/admin/credit-accounts` للفتح/الكشف/التحصيل/الحالة/
  الحد/العكس حسب الصلاحيات.
- Owner App: total/count في NowScreen + read-only receivables detail.
- نُشر implementation commit `dd26a1f`، ثم follow-up `1d77e7b` لإزالة تعريف
  HTTP مكرر لـOwner في Nginx. الإصدار الفعال النهائي `1d77e7b`.
- جداول الحسابات والحركات موجودة وفارغة مبدئيًا (`0 / 0`)؛ الفرع الوحيد لديه
  GL `1160`؛ لم تُنشأ حركة مالية تجريبية على الإنتاج.

### سجل نشر CREDIT-0005

- DB backup verified:
  `/var/backups/resort-os/database/resort_os_20260808_180257.dump`
  (`609846` bytes، SHA-256
  `1bd9d33edebb667eb4d42b53fd2f4040aaeaa9c90a9c69efec61ab6bc616d70d`).
- Rollback images manifest:
  `/var/backups/resort-os/source-releases/dd26a1f-rollback-images.txt`.
- Final exact-source archive:
  `/var/backups/resort-os/source-releases/1d77e7b.tar.gz`، SHA-256
  `1ef3bea7541a2354b712faa6b4d0ec044978093746e501e66b7ff78365506827`.
- build: backend/celery worker/celery beat/el-kheima/owner succeeded؛ الاستبدال
  تم backend → worker/beat → Staff/Owner → Nginx، وكل الحاويات الجديدة
  `running/healthy` و`RestartCount=0` (Nginx running وبدون healthcheck).
- `https://elkheima.com` و`www` و`app` و`owner` رجعت HTTP `200`؛ HTTP Owner
  رجع `301`؛ credit وowner protected probes رجعت `401` بلا توثيق كما يجب.
- `nginx -t` و`resort-os-healthcheck.service` ناجحان، وفحص السجلات الصارم
  بعد النشر صفر alerts.

## 1. المصدر والإصدار

| البند | القيمة المثبتة |
|---|---|
| فرع العمل الوحيد | `claude/CX-02C-frontend-auth-bootstrap` |
| Resort OS source release (منشور) | `1d77e7b` — CREDIT-0005 + Owner Phase 6/7/7a + Nginx cleanup |
| runtime code/config commit | `1d77e7b` — follow-up بعد implementation commit `dd26a1f` |
| Marketing source release | `bc48f09` من المستودع المستقل (`main` يطابق الالتزام، مدفوعة بالكامل) |
| `origin/main` | `598938e` — لم يُغيّر |
| active Resort release | `/opt/resort-os-current -> /opt/resort-os-releases/1d77e7b` |
| active Marketing release | `/opt/elkheima-marketing-releases/bc48f09` |
| Marketing current link | `/opt/elkheima-marketing-current -> /opt/elkheima-marketing-releases/bc48f09` |
| Compose project / override | `resort-os-prod` / `docker-compose.prod.domain.yml` |
| Alembic head (DB) | `c9d4e5f6a7b8` (personal credit accounts — مطبّق ✅) |

## Owner Cockpit Phase 6+7+7a — نشر 8 أغسطس 2026

**ما اتضاف (بدون migration — قراءة فقط):**

**Backend:**
- `owner/schemas.py`: schemas جديدة للـ Phase 6+7+7a (`DaySnapshot`، `NowHistoryResponse`، `SalesPerformanceResponse`، `BeachPerformanceResponse`، `ChannelAnalyticsResponse`، `ExpenseAnalyticsResponse`، `ProcurementAnalyticsResponse`، `ShiftMonitorResponse`، `ExceptionsResponse`)
- `owner/services.py`: `get_sales_performance`، `get_beach_performance`، `get_channel_analytics`، `get_expense_analytics`، `get_procurement_analytics`، `get_shift_monitor`، `get_exceptions`، `get_now_history`
- `owner/api/router.py`: 7 endpoints جديدة (`/owner/sales`، `/owner/beach-performance`، `/owner/channel-analytics`، `/owner/expense-analytics`، `/owner/procurement-analytics`، `/owner/shifts`، `/owner/exceptions`، `/owner/now/history`)

**Frontend:**
- `SalesScreen.vue` — أداء المطعم (ABC + هامش) + الشاطئ (تذاكر بالنوع)
- `ExpensesScreen.vue` — مصروفات كـ % من الإيراد + variance flags + مشتريات الموردين
- `ShiftsScreen.vue` — تنبيهات (critical/attention/watch) + مراقبة الورديات
- `NowScreen.vue` — sparklines حقيقية من `/owner/now/history?days=7`
- `AppShell.vue` — bottom nav من 2 لـ 5 tabs
- `router/index.ts` — 3 routes جديدة (sales/expenses/shifts)
- `public/icon-192.png` + `public/icon-512.png` — PWA icons من الـ logo الأصلي

**التحقق:**
- ✅ 150 owner tests passed
- ✅ TypeScript نظيف
- ✅ Build: 16 entries precached
- ✅ backend: running restarts=0
- ✅ owner: running restarts=0
- ✅ `https://owner.elkheima.com/icon-192.png` → HTTP 200
- ✅ `https://owner.elkheima.com/icon-512.png` → HTTP 200
- ✅ `GET /api/v1/owner/now/history` endpoint موجود في الـ router

## Owner Cockpit — حالة المراحل

| # | المرحلة | الحالة |
|---|---|---|
| 1 | Metric contracts | ✅ مكتمل |
| 2 | Isolation + safety rails | ✅ مكتمل |
| 3 | Aggregation APIs (now/performance) | ✅ مكتمل |
| 4 | Owner PWA (Now + Performance) | ✅ مكتمل |
| 5 | مراجعة الأرقام مع محمد | ✅ مكتمل (2026-08-08) |
| 6 | Sales/Beach/Channel/Expense/Procurement analytics | ✅ مكتمل (2026-08-08) |
| 7 | Shift monitoring + Exceptions engine | ✅ مكتمل (2026-08-08) |
| 7a | PWA polish — icons + sparklines | ✅ مكتمل (2026-08-08) |
| 8 | Security review + production gate | ⏳ التالي |
| ~~9~~ | ~~Unit economics~~ | محذوف بقرار محمد |
| ~~10~~ | ~~Scenario sandbox~~ | محذوف بقرار محمد |

## REL-10 — نشر 7 أغسطس 2026 (commit `427ae82`)

**POS-BEACH-01: فيتشر خريطة الشمسيات + الفنادق في كاشير الدايننج + 5 إصلاحات**

**ما اتنشر:**
- `dining/models.py`: `b2b_contract_id` + `beach_location_id` على `DiningOrder`
- `dining/api/router.py`: `_enrich_order/_enrich_order_list` — `hotel_name` + `beach_location_label` بـ 2 queries، GET `/dining/b2b-contracts`، GET `/dining/reports/hotel-consumption`
- Migration `a3f9c1d2e4b5`: ADD COLUMN b2b_contract_id + beach_location_id + partial unique index
- Frontend: إصلاح `hotel_name` mismatch، cash presets (50-500ج)، i18n beachMap، ShiftDashboard hotel label
- `POSBeachMapWorkspace.vue` + `POSHotelSelector.vue`: components جديدة
- 9 tests جديدة — 2342 backend passed، 95 frontend passed، TypeScript نظيف

**دورة النشر (REL-10، 2026-08-07 ~07:25 Cairo):**
- ✅ نسخة احتياطية: `resort_os_20260807_042156.dump` (588K، 1419 entries — مثبّت)
- ✅ SHA-256 أرشيف مطابق على الطرفين: `4eb5f7f42e38af89e31e1b233ff48821de2cf393a38872cebbe2532e41485bbd`
- ✅ rollback tags: 5 خدمات مؤرشفة كـ `resort-os-rollback/<svc>:pre-427ae82`
- ✅ rollback manifest: `/var/backups/resort-os/source-releases/427ae82-rollback-images.txt`
- ✅ validate_prod_env: passed
- ✅ بناء الصور: backend/celery_worker/celery_beat/el_kheima — Built بنجاح
- ✅ preflight import: `El Kheima Beach`
- ✅ migration `a3f9c1d2e4b5`: applied (`52f4544e50d2 -> a3f9c1d2e4b5`)
- ✅ استبدال تدريجي: backend → celery_worker/beat → el_kheima → nginx
- ✅ health check: `{"status":"ok","database":{"status":"ok"},"redis":{"status":"ok"}}`
- ✅ elkheima.com: HTTP 200 / www.elkheima.com: HTTP 200 / app.elkheima.com: HTTP 200
- ✅ symlink: `/opt/resort-os-current -> /opt/resort-os-releases/427ae82`
- ✅ Alembic current: `a3f9c1d2e4b5 (head)`
- ✅ DB: columns `b2b_contract_id` + `beach_location_id` موجودتين في `dining_orders`
- ✅ RestartCount=0 لكل الحاويات — لوجات نظيفة صفر ERROR/CRITICAL



**dining N+1 batch-load + 41 test جديدة + مراجعة دين تقني**

**ما اتنشر:**
- `dining/services.py`: batch-load في `create_order`, `add_items_to_order`, `sync_offline_order`, `_deduct_inventory_for_order` — صفر N+1 queries داخل الـ loops
- `dining/crud.py`: `get_items_by_ids()`, `get_variants_by_ids()` جديدتين
- `inventory/crud.py`: `get_products_by_ids_any_branch()`, `get_warehouses_by_ids()` جديدتين
- `test_dining_router_coverage.py`: 41 test جديدة (menu CRUD، tables، orders HTTP، kitchen/KDS، public endpoints)
- `docs/audits/TECHNICAL_DEBT_AND_COVERAGE_AUDIT.md`: مراجعة دين تقني شاملة مرتبة بالأولوية
- لا migration جديدة — Alembic head `52f4544e50d2` بدون تغيير
- 2333 pytest passed، type-check نظيف، build نظيف

**دورة النشر (REL-09، 2026-08-06 ~05:25 Cairo):**
- ✅ نسخة احتياطية: `resort_os_20260806_021750.dump` (588K — مثبّت)
- ✅ SHA-256 أرشيف مطابق على الطرفين: `a04aaf6b3d1cffacda5d55645fc4958b1e19f9da5209a1e57a6681f21ca1793c`
- ✅ rollback tags: 5 خدمات مؤرشفة كـ `resort-os-rollback/<svc>:pre-fd105f6`
- ✅ rollback manifest: `/var/backups/resort-os/source-releases/fd105f6-rollback-images.txt`
- ✅ validate_prod_env: passed
- ✅ بناء الصور: backend/celery_worker/celery_beat/el_kheima — Built بنجاح
- ✅ preflight import: `✓ El Kheima Beach`
- ✅ alembic heads: `52f4544e50d2` (head) — لا migration
- ✅ استبدال تدريجي: backend → celery_worker/beat → el_kheima → nginx
- ✅ health check: `{"status":"ok"}` — 8/8 حاويات running/healthy، restarts=0
- ✅ app.elkheima.com: HTTP 200 / elkheima.com: HTTP 200 / www.elkheima.com: HTTP 200
- ✅ symlink: `/opt/resort-os-current -> /opt/resort-os-releases/fd105f6`
- ✅ logs نظيفة — صفر ERROR/CRITICAL

## REL-08 — نشر 5 أغسطس 2026 (commit `7d00917`)

**POS-03 + POS-03b: دعم الدفع بعملات متعددة (مطعم/كافيه + شاطئ)**

**ما اتنشر:**
- `Payment.fx_rate` عمود جديد (migration `52f4544e50d2`) — سعر الصرف وقت الدفع
- المطعم/الكافيه: `OrderStatusUpdate`/`SplitBillPayment` بيقبلوا `payment_currency`/`payment_fx_rate`
- الشاطئ: `BeachSellRequest` يقبل `payment_currency`/`payment_fx_rate` — الفكة دايمًا بالجنيه
- `build_shift_end_report`: `ForeignCurrencySummary` لكل عملة أجنبية (expected/variance)
- `POSPaymentModal.vue` + `BeachPOSView.vue`: اختيار عملة، عرض المطلوب بالأجنبية، الفكة
- `FinanceView.vue`: tab أسعار الصرف (المدير يضيف/يشوف من الواجهة)
- 2292 pytest passed، 95 frontend tests، type-check نظيف، build نظيف

**دورة النشر (REL-08، 2026-08-05 ~17:39 Cairo):**
- ✅ نسخة احتياطية: `resort_os_20260805_172441.dump` (584K، 1419 TOC entries — مثبّت)
- ✅ SHA-256 أرشيف مطابق على الطرفين
- ✅ validate_prod_env: passed
- ✅ rollback tags: 6 خدمات مؤرشفة كـ `resort-os-rollback/<svc>:pre-7d00917...`
- ✅ بناء الصور: backend/celery_worker/celery_beat/el_kheima — Built بنجاح
- ✅ migration `52f4544e50d2`: applied (7b4d81dc08ee → 52f4544e50d2)
- ✅ استبدال تدريجي: backend → celery_worker/beat → el_kheima → nginx
- ✅ health check: `{"status":"ok","database":{"status":"ok"},"redis":{"status":"ok"}}`
- ✅ app.elkheima.com: HTTP 200 / elkheima.com: HTTP 200
- ✅ symlink: `/opt/resort-os-current -> /opt/resort-os-releases/7d00917...`
- ✅ 8/8 حاويات running/healthy

## POS-03b — دعم الدفع بعملات متعددة للشاطئ (commit `f68b232`، 2026-08-05)

قرار Mohamed: الشاطئ يدعم نفس الميزة + الفكة دايمًا بالجنيه.
**منشور على VPS في REL-08 ✅**

**ما اتعمل:**
- `BeachSellRequest` يقبل `payment_currency`/`payment_fx_rate` اختياري مع validator (لو currency≠EGP بدون fx_rate → 422)
- `_sell_ticket_no_commit`: يحفظ currency/fx_rate كـ transient attrs على tx
- `_record_shift_payment`: يمرّر currency/fx_rate لـ `create_direct_payment` — Payment.amount دايمًا EGP-equivalent
- الفكة دايمًا بالجنيه (قرار Mohamed 2026-08-05) — الشاشة تعرض "الفكة = X جنيه"
- `BeachPOSView.vue`: أزرار اختيار عملة (EGP/USD/EUR)، عرض المطلوب بالأجنبية، حقل استلام، الفكة بالجنيه، `fetchFxRates` عند mount
- ترجمات ar/en: 7 مفاتيح `beachPos` جديدة
- 5 تستات جديدة (beach) + 3 schema validation: 2292 passed، صفر failure
- type-check نظيف، build نظيف، agent-check passed، Alembic single head (بدون migration إضافية)

**Gate (POS-03 + POS-03b مع بعض):** 2292 pytest passed، 95 frontend، type-check نظيف، build نظيف.

## POS-03 — دعم الدفع بعملات متعددة للمطعم/الكافيه (commit `e2c31af`، 2026-08-05)

بطلب صريح من Mohamed (بريف `docs/agent-workflow/POS-03_MULTI_CURRENCY_CASHIER_PLAN_AR.md`)
— **غير منشور على VPS بعد، ينتظر قرار Go من Mohamed بعد مراجعة §3.3**.

**ما اتعمل:**
- `Payment.fx_rate` عمود جديد (migration `52f4544e50d2`) — سعر الصرف وقت الدفع
- `create_direct_payment` بيقبل `currency`/`fx_rate` — دفعة كاش بعملة أجنبية تُسجَّل بالمعادل EGP في `amount` والعملة الأصلية في `currency`/`fx_rate`
- `OrderStatusUpdate`/`SplitBillPayment` بيقبلوا `payment_currency`/`payment_fx_rate` (اختياري — لا يكسر أي بيع EGP حالي)
- `build_shift_end_report`: `ForeignCurrencySummary` بيضيف `expected_amount`/`variance` لكل عملة أجنبية — الكاشير يشوف "معدود 70 USD — متوقع 70 USD — فرق 0" بدل رقم جنيه واحد مبلوع
- `POSPaymentModal.vue`: اختيار عملة (EGP/USD/EUR)، عرض المطلوب بالعملة الأجنبية، حقل الاستلام، الفكة، سعر الصرف الحالي مباشر
- `FinanceView.vue`: tab جديد "أسعار الصرف" — المدير يضيف ويشوف الأسعار من الواجهة (بديل Postman)
- 10 تستات جديدة (`test_pos03_multi_currency.py`) — كلها أخضر

**ما ينتظر قرار Mohamed (§3.3 في البريف):**
- الشاطئ محتاج نفس الميزة ولا المطعم/الكافيه بس الأول؟
- الباقي (فكة) بيترجع جنيه دايمًا ولا بنفس العملة؟
- شاشة أسعار الصرف يدوية كافية ولا ربط تلقائي بمصدر خارجي؟
- العملات المدعومة USD/EUR بس ولا نضيف غيرهم؟

**Gate**: 2284 pytest passed، 95 frontend، type-check نظيف، build نظيف، migration تطبّق على prod بـ `alembic upgrade head`

أرشيف Resort OS:
`/var/backups/resort-os/source-releases/5df8191.tar.gz`،
SHA-256 `df209816d2ac9547d42cfc64c45c007a939d7d90f2a586832d30d1fde7e02963`.
(أرشيف `821a718` وما قبله محفوظ كما هو.)

أرشيف سابق (`821a718`):
`/var/backups/resort-os/source-releases/821a718.tar.gz`،
SHA-256
`542cdaa35f7dfb6ae1dd6da68c825d65954da2606a57783ff177c479f35a4411`.
(أرشيفات `5b02010`، `a3e8abb`، `ddfbaaa`، `4a0a777`، `8597535`، `b1db886`، `0d55717`، `4ca10c1` السابقة ما زالت محفوظة كما هي.)

أرشيف Marketing:
`/var/backups/resort-os/marketing-source-releases/79130a6.tar.gz`،
SHA-256 `f8e454beb95a48ac8c72ec8705c36ca50948289f2e690587a9bb629ee4fe5a9f`.
(أرشيفات `1371975`، `16f8f2c`، `0b0321f`، `4fba5b6`، `53bf7a3` السابقة ما زالت محفوظة كما هي.)

مجلدا المصدر القديمان `/opt/resort-os` و
`/opt/elkheima-marketing-website` محفوظان كما كانا، وغير مستخدمين كمصدر
للإصدار الفعال ولم يُنظفا أو يُعاد ضبطهما.

## 2. الخدمات الفعالة

- **2026-08-04 — REL-07: `5df8191` (8 commit فوق `821a718`) + Marketing
  `79130a6` (بتفويض مباشر من Mohamed: "انت القائد للنهاية... اعمل ما
  يلزم")**: `backend`, `celery_worker`, `celery_beat`, `el_kheima` اتبنوا
  ونُشروا من `5df8191`؛ `marketing_site` اتبنى من `79130a6` (المستودع
  المستقل) بنفس الدورة.
  - **فواتير/إيصالات PDF عربية**: 3 باجات متسلسلة اتصلحوا في
    `app/core/kernel/reports.py` — مفيش خط عربي متسجّل خالص (النص العربي
    كان بيترسم بـHelvetica، صفر glyphs عربي)، الخط العربي المتاح مالوش
    حروف لاتينية خالص (تسجيله لوحده كان هيمسح أي كلمة إنجليزية)،
    والتذييل كان بيترسم من غير إعادة تشكيل (`_add_footer` مكنش بينادي
    `_t()`). الحل: `_split_script_runs`/`_draw_mixed` يرسموا كل جزء
    بالخط اللي بيغطّيه فعليًا، + لوجو المنتجع الحقيقي على الإيصال
    الحراري (مكنش موجود خالص)، + تصميم أرقى (فواصل متقطّعة، تفصيل سعر،
    قسم إجمالي واضح). الفونتات/اللوجو اتحطّوا في `app/assets/` عشان
    يتنسخوا فعليًا لصورة الإنتاج (`python:3.11-slim` مفيهوش فونتات نظام).
  - **مدونة حقيقية**: كانت skeleton كامل — endpoint قائمة بس (بدون
    `body`/`cover_image`)، مفيش endpoint لمقال منفرد خالص، صفر مقالات
    مزروعة. اتضاف `GET /hub/blog/posts/{slug}` (404 للمسودات/الناقص،
    بيزوّد `views_count` فعليًا)، `cover_image` بقى متعرّض في القائمة،
    و6 مقالات حقيقية (نص عربي منقول زي ما هو من مشروع
    `elkheima-beach-resort` القديم بطلب صريح من Mohamed) اتزرعوا عبر
    `app.seed._seed_blog_posts` (idempotent upsert بالـslug، نفس نمط
    `_seed_chart_of_accounts` — محتوى حقيقي آمن للتشغيل المباشر على
    الإنتاج، مش بيانات تجريبية).
  - **إصلاح شامل للموقع التسويقي** (`elkheima-marketing-website`، commit
    `79130a6`): حذف `useModulesStore`/`fetchModules` بالكامل (كان بينادي
    `/modules/public` غير موجود خالص في resort-os — نظام تفعيل/تعطيل
    الموديولات اتشال عمدًا من الباك إند، ومفيش أي مستهلك حقيقي لنتيجة
    النداء أصلاً)، وقف نداء `/settings/public` المماثل في
    `useMediaSettings` (نفس القصة — endpoint مش موجود، fallback بصمت).
    إصلاح باج تصميم حقيقي في `Timeshare.vue`/`Booking.vue`: `<SEOHead>`
    كان sibling قبل الـ`<div>` الجذر بدل ما يكون جواه — بيخلّي الكومبوننت
    عنده root عنصرين، وده بالظبط سبب تحذير Vue "renders non-element root
    node that cannot be animated" وخطأ `InvalidStateError` وقت الانتقال
    بين الصفحات اللي Mohamed بعت سكرين شوت بيه. زرار "🏖️ اطلب من مكانك"
    في صفحة الشاطئ العامة كان بيسمح لأي زائر موقع عشوائي يبعت "طلب" وهمي
    (فعليًا رسالة تواصل يدوية بس، بدون أي تحقق حضور فعلي في المنتجع) —
    بقى كارت وصف للخدمة بس، مش نموذج طلب حي.
  - **اكتشاف جانبي أثناء المراجعة**: لقيت 147 ملف تعديل غير محفوظ (commit)
    على `/opt/resort-os` (السيرفر) — راجعتها كلها، اتضح إن 100 منها مجرد
    الفرق الطبيعي بين `main` والفرع التشغيلي (مفيش خطر)، والـ18 الباقية
    (إصلاحات عزل فروع/تعارض دفعات/تشفير PII كانت موثّقة في بريف من وكيل
    اسمه Kiro بتاريخ 29 يوليو) طلعت متعملة لها commit ونشر بالفعل قبل كده
    (إصدار `258c99c`، موجود جوه `821a718`) — يعني مفيش حاجة ضاعت، الفولدر
    ده مجرد نسخة قديمة مش مستخدمة في النشر أصلاً (موثّق في `DEPLOYMENT.md`
    كـ"legacy source snapshot; not a deploy target").
  - **بوابة الجودة**: `agent-check.sh`، pytest كامل (backend)، alembic
    heads (head واحد `7b4d81dc08ee`، صفر migration جديدة هذه الدفعة)،
    `pnpm type-check:all`، `pnpm --filter el-kheima test:frontend`
    (95/95)، `pnpm build:all`، بناء الموقع التسويقي + type-check +
    `validate:truth` — كله أخضر.
  - **النشر**: نسخة احتياطية DB اتاتأكدت (`pg_restore --list`، 1408 TOC
    entry)، rollback tags للـ6 خدمات، استبدال تدريجي (backend → celery →
    el_kheima → nginx، وmarketing_site منفصل)، health check رسمي 14/14،
    تحقق حي فعلي عبر متصفح Playwright على الدومين الحقيقي (صفر console
    errors، صفر 404s، المدونة والفاتورة اشتغلوا صح).

- **2026-08-03 — دفعة `821a718` (23 commit فوق `5b02010`، بتفويض مباشر من
  Mohamed خارج دورة Codex المعتادة)**: `backend`, `celery_worker`,
  `celery_beat`, `el_kheima` اتبنوا ونُشروا كلهم من `821a718`.
  `marketing_site` اتبنى من نفس السياق الحالي (`1371975`، بدون تغيير في
  مصدره) كجزء من أمر البناء الموحّد فقط.
  - **HR/الأدمن**: بحث/فلترة حقيقية للموظفين والمستخدمين، تعديل/تغيير حالة
    الموظف، تحميل الرواتب Excel/PDF وقسائم راتب فردية، ملف موظف موحّد،
    إصلاح IDOR حقيقي في `GET /hr/employees/{id}` (كاشير فرع كان يقدر يقرا
    بيانات موظف فرع تاني)، فك قفل حساب/إعادة ضبط 2FA إداري (step-up)،
    إدارة جلسات مستخدم تاني (عرض/إنهاء، step-up)، فلترة سجل التدقيق بتاريخ
    + اسم فاعل، حذف نظام إشعارات كان مبني بالكامل بدون أي مستهلك خالص.
  - **مالي حقيقي**: `vat_percentage`/`service_charge_percentage` كانا
    بيتقروا من env var بس مهما اتغيّروا في الإعدادات — بقوا فعليًا
    DB-driven في dining/beach/finance الثلاثة.
  - **تايم شير**: إدارة وحدات فعلية (CRUD)، قائمة انتظار حقيقية، تذكيرات
    واتساب (صيانة مستحقة/انتهاء عقد)، نسبة إشغال في اللوحة، بوابة صاحب
    عقد ذاتية كاملة (OTP، تحميل PDF العقد)، تنبيهات واتساب في الاتجاهين
    لطلبات الزيارة وتذاكر الدعم (مكانتش موجودة خالص)، زرار توليد مستحقات
    صيانة يدوي. **باج أمني حقيقي اتصلح قبل النشر مباشرة**: إنتاج فحص fail
    -closed جديد لـ`TIMESHARE_PORTAL_TOKEN_SECRET`/`SURVEY_TOKEN_SECRET`
    (بديل مفتاح فاضي/افتراضي كان ممكن يسمح بتزوير توكن بوابة عميل تايم
    شير بمعرفة الكود العام على GitHub بس). `.env.prod` في هذا الإصدار
    اتضاف له `TIMESHARE_PORTAL_TOKEN_SECRET` حقيقي (32+ حرف عشوائي) أول
    مرة — مكانش موجود قبل كده، الميزة اتبنت بعد آخر نشر.
  - **دايننج**: هوية ضيف + طلب ذاتي عابر للمنافذ + ملاحظات لكل صنف، منيو
    ضيف بـ4 لغات (ar/en/ru/it)، idempotency لطلب الضيف + بث خريطة الطاولات
    الحي، تسالي الكافيه.
  - 4 migrations جديدة (`a7c3f0e9d5b2`، `f1e6c8b4a3d7`، `7e5e126360d5`،
    `7b4d81dc08ee`) — Alembic head واحد `7b4d81dc08ee`، اتأكد `alembic
    upgrade head` شغال نظيف على الإنتاج الحقيقي قبل الاستبدال.
- `marketing_site` بُني ونُشر من `53bf7a3` — جولة مراجعة كاملة لباقي شاشات
  الموقع التسويقي (Rooms/Beach/Restaurant/Activities/Events/Packages/
  Products/FAQ/Home/Contact/Timeshare/booking modal) بعد إغلاق MKT-04،
  لقيت 3 دفعات باجات حقيقية: (١) 7 استمارات تواصل عامة (booking/contact/
  timeshare/spa/room-service/sunbed + usePageBooking المشتركة) كانت بتعيد
  استخدام نفس idempotency key حتى بعد فشل الإرسال — لو رد نجاح ضاع فعليًا
  بعد ما الباك إند كتب الصف (network drop/timeout)، وبعدين الزائر عدّل
  حاجة بسيطة وأعاد الإرسال، كان بيتعلّق للأبد على 409 idempotency_conflict
  من الباك إند من غير أي مخرج غير ريفريش الصفحة — اتصلح بتوليد مفتاح جديد
  عند أي فشل. (٢) تسريب حقيقي من بوابات PUBLIC_TRUTH: "4.2★" (تقييم مفبرك)
  و"12,500 m²" في Beach.vue، 4 إجابات FAQ برقم خصم/عربون صريح، كارت "وفّر
  حتى 30%" في Packages.vue، وبادج سعة "200+ ضيف" في Events.vue — كلهم
  كانوا ظاهرين لأي زائر حقيقي لأنهم راكبين على بوابة عامة (amenities/
  packages) مفعّلة بدل بوابتهم الخاصة (prices/promotions/ratings/
  numericStats، لسه fail-closed). زائد فخين خاملين (تقييم + تصنيف "3 نجوم"
  في Home.vue، وتضارب سعر رومانسي 300ج/$15 حسب اللغة في Rooms.vue) اتأمّنوا
  احتياطيًا قبل ما يتفعّلوا بالغلط لاحقًا. (٣) كاردز Products.vue كانت
  بتستخدم مسارات خام بدل localePath()، عكس باقي الموقع بالكامل. تفاصيل
  كاملة في handoff MKT-05.
- `marketing_site` بُني ونُشر بعد كده من `1371975` (MKT-06) — Mohamed
  رفع screenshot لسكرول أفقي فاضي طويل في `/ar/contact` بس (باقي اللغات
  سليمة). السبب: حقل honeypot مضاد للبوتات كان مخفي بإزاحة فيزيائية ضخمة
  (`-left-[10000px]`) من غير أي عنصر أب positioned يحتوي الـoverflow —
  في LTR المتصفح بيتجاهل السكرول للإحداثيات السالبة بصمت، لكن في RTL
  نقطة بداية السكرول بتتقلب وبتسمح فعليًا بالوصول للمنطقة السالبة دي،
  فعرض الصفحة الفعلي كان بيتوسّع 10000px. اتصلح بـ`sr-only` (تقنية
  Tailwind قياسية، clip-based، صفر إزاحة فيزيائية) — نفس التقنية
  المستخدمة فعلاً في مكان تاني بالموقع. اتفحص باقي الموقع لنفس النمط
  (`-left-[Npx]`/`-right-[Npx]`) — التطابق الوحيد التاني (blob زخرفي في
  CTASection.vue) محاط فعليًا بـ`overflow: hidden` صح، مش نفس الباج.
  اتأكد الإصلاح حيًا: الكود القديم (`10000px`) اختفى تمامًا من الـbundle
  المنشور، و`sr-only` موجود فعليًا.
- Backend image:
  `sha256:abbd5f245b5e3d84efc2e5c9215f06c08576a465f316e89e26fcf0842655b28a`.
- Celery worker:
  `sha256:c58a764a0c87475db671e8e7d1e9302e8ef1979b9da65f1bf4025a2cee6a2fd6`.
- Celery beat:
  `sha256:9e304ad5e074762707aaab2097a273f31f0aeaba5713ddda7bd95e393da3c1d0`.
- El Kheima staff app (من `b1db886`، غير متغيّر هذه الجولة):
  `sha256:f135b11a4d2d7799afd011934a093eb14ed14921b86bbd807d31582a1082c673`.
- Marketing image:
  `sha256:fafe1eb8576b3c2b0c2cd2da3346cbe2bf2eb7d98f26a4619df1d81d707a9ad9`.
- Nginx:
  `sha256:97d490c12ba55b4946b01546d1c3ed324e8d41ab1c9fcb2a616aa470620e5b46`.
- 8 حاويات Running وكل healthchecks المعرّفة سليمة. الحاويات الثماني
  `RestartCount=0` بعد القطع.
- PostgreSQL وRedis بقيا على volumes والحاويات طويلة العمر ولم يُعاد
  إنشاؤهما أثناء النشر.

## 3. DNS وTLS والـedge

سجلات Hostinger الفعالة:

| الاسم | النوع | القيمة | TTL |
|---|---|---|---:|
| `@` | A | `191.218.161.133` | 300 |
| `app` | A | `191.218.161.133` | 300 |
| `www` | CNAME | `elkheima.com` | 300 |

- authoritative nameservers:
  `pixel.dns-parking.com` و`byte.dns-parking.com`.
- authoritative DNS و`1.1.1.1` و`8.8.8.8` و`9.9.9.9` أعادوا عنوان
  الـVPS للجذر و`app`.
- Hostinger DNS rollback snapshot: `167902017`، أُنشئ
  `2026-07-30T03:18:09Z`، ويحفظ الحالة السابقة
  `@ A 2.57.91.91` و`www CNAME elkheima.com`.
- لم يُستخدم Reset DNS، ولم يُضف AAAA، ولم تُمس سجلات أخرى.
- شهادة Let's Encrypt ECDSA باسم `elkheima.com` تشمل:
  `elkheima.com`, `www.elkheima.com`, `app.elkheima.com`.
- الشهادة صالحة من `2026-07-30 02:21:35 UTC` حتى
  `2026-10-28 02:21:34 UTC`.
- `certbot renew --dry-run` وdeploy hook لإعادة تحميل Nginx نجحا.
- HSTS canary فعال بقيمة `max-age=604800` دون `includeSubDomains` في
  المرحلة الأولى.
- المنافذ العامة للتطبيق 80 و443 فقط؛ منفذ marketing القديم 8443 أُغلق.

## 4. فحص الإنتاج الخارجي

- `https://elkheima.com/` يعيد 200.
- `https://www.elkheima.com/` يعيد 200.
- `https://app.elkheima.com/` يعيد 200.
- `https://app.elkheima.com/health` يعيد 200 و`status=ok`.
- HTTP على النطاقات الثلاثة يعيد 301 إلى HTTPS الصحيح.
- HTML و`robots.txt` و`sitemap.xml` تحتوي الدومين الرسمي، وصفر مراجع
  للعنوان `191.218.161.133`.
- فحص marketing canary قبل الاستبدال: `/` و`/health` = 200،
  domain refs في 4 ملفات، old-IP refs = 0.
- Backend runtime origins هي الجذر و`www` و`app` فقط، وخريطة Chatbot
  العامة مقصورة على الجذر و`www`.
- Chatbot E2E من الدومين: welcome عربي، إنشاء session، قبول disclosure،
  رد Gemini عربي غير فارغ، وإنهاء session بنجاح.
- `/ar/timeshare` و`/en/timeshare` يعيدان 200. الصفحة تعرض Blue Bay كجهة
  إدارة الملكية الجزئية، وترسل الاستفسار إلى `/api/v1/hub/contact` مع
  consent وidempotency. لا تعرض أسعارًا أو تضمن توفرًا أو شروطًا تعاقدية.
- ترجمات Marketing متطابقة: 2919 مفتاحًا في كل من العربية والإنجليزية
  والروسية والإيطالية، وصور الأنشطة والفعاليات راجعها Codex بصريًا.
- تطبيق الموظفين المنشور يحتوي إصلاح تبديل المنفذ للطلب القائم: وجود
  `pendingOrderId` يغيّر المنيو دون إلغاء الطلب، أما السلة المحلية وحدها
  فتحتفظ بنافذة التأكيد. ملف `UnifiedPOSView` المنشور طابق البناء المحلي
  عند SHA-256
  `0339d0eb7ca8c93a9a9fa081d74e13c6b47a6bc78d9940bfa8b2a024388dea87`.
- فحص logs النهائي لخدمات backend/worker/beat/staff/marketing/nginx:
  صفر أنماط severe ضمن نافذة الفحص.

## 5. مسار الموظفين والحسابات المنشور

- الموارد البشرية (`hr_manager` أو الإدارة) تنشئ سجل الموظف داخل الفرع
  الفعال؛ لا تقبل نقطة الإنشاء `user_id` ولا تسمح للمحاسب بإدارة HR.
- السوبر أدمن يفتح مركز الإدارة الموحد، يختار سجل الموظف، ثم ينشئ حساب
  الدخول ويحدد الدور. Backend يربط الحساب بالموظف ويضيف عضوية الفرع
  الافتراضية الفعالة داخل transaction واحدة.
- إنشاء الحساب محمي بـStep-Up ومسجل في Audit. العزل بين الفروع fail-closed،
  ومسار الربط اليدوي القديم محصور في السوبر أدمن كاستعادة مدققة ولا يمنح
  عضوية فرع.
- صفحات المستخدمين والصلاحيات القديمة تحوّل إلى مركز السوبر أدمن بدل
  ازدواج الشاشات، والقائمة الجانبية منظمة إلى مجموعات تشغيلية مع عرض هاتف
  off-canvas.
- حسابات الموظفين العاديين، ومنها المحاسب، تُنشأ من هذا المسار بعد سجل HR.
  إنشاء `super_admin` احتياطي يبقى bootstrap من الطرفية فقط.

حالة الإنتاج بعد النشر: `users=1`, `active_superadmins=1`, `branches=1`,
`employees=0`, `active_memberships=1`. لم تُنشأ هويات أو كلمات مرور
تجريبية.

## 6. البيانات التجريبية المنشورة

البيانات synthetic وموسومة وليست اعتمادًا ماليًا أو تشغيليًا نهائيًا.
اقتصر التطبيق على الفرع الفعال الوحيد `ELK-001` وبهوية
`super_admin` الفعالة، مع advisory lock وdry-run افتراضي وconfirmation
صريح.

| النطاق | العدد |
|---|---:|
| المخازن / تصنيفات المخزون / المنتجات | 3 / 10 / 114 |
| حركات الرصيد الافتتاحي | 114 |
| الموردون / أوامر الشراء / طلبات الشراء | 6 / 5 / 3 |
| منافذ المطعم / الأصناف / مكونات الوصفات / الطاولات | 2 / 104 / 459 / 12 |
| أنواع الغرف / الغرف / خطط الأسعار | 5 / 52 / 4 |
| الأقسام / الأصول / أوامر الصيانة المغلقة أو الملغاة | 12 / 6 / 3 |
| عملاء CRM / leads / opportunities / campaigns | 4 / 4 / 2 / 1 |
| وحدات timeshare / عقود draft | 12 / 3 |
| عقود lease draft | 3 |
| مواقع beach تجريبية / عقود B2B غير فعالة | 8 / 2 |
| محتوى Hub | 3 صفحات draft + عرض inactive + مقال draft |

لم يضف importer مستخدمين أو كلمات مرور أو sessions أو صلاحيات، ولم يضف
حجوزات أو مدفوعات أو قيود يومية أو رواتب أو dining orders أو beach sales
أو أقساط أو guest alerts. ملفات العد قبل وبعد متطابقة byte-for-byte:

- `/var/backups/resort-os/source-releases/32eb0f8-pre-seed-counts.txt`
- `/var/backups/resort-os/source-releases/32eb0f8-post-seed-safety-counts.txt`

قراءة الإنتاج في آخر فحص أظهرت حسابًا واحدًا فقط:
`super_admin: total=1, active=1`. لا توجد سجلات أو حسابات موظفين حتى
الآن، ولم تُعرض أي بيانات اعتماد في التوثيق أو الفحص. إنشاء الحسابات ينتظر
أسماء وبريد وأدوار أشخاص حقيقيين، وفق `manual/02-دليل-الموظفين-والتدريب.md`.

## 7. أدلة الجودة

- full backend suite: 2181 passed و40 skipped من 2221 collected، صفر
  failure.
- production demo seed tests: 9 passed.
- PostgreSQL clean-schema apply + idempotency + safety checks: passed.
- استعادة dump حقيقية واختبار importer عليها ثم تنظيف DB المؤقتة: passed.
- onboarding/HR/auth focused backend: 228 passed و1 skipped؛ وآخر فحص
  أمني بعد تعديل الربط: 31 passed.
- frontend: 95/95 عبر 13 ملف اختبار.
- frontend type-check وproduction build: passed.
- full backend release regression: 2181 passed و40 skipped، صفر failure؛
  Alembic بقي عند head واحد `88d1c505a9dc`.
- Marketing `truth`, `type-check`, `build`: passed.
- `agent-check`: passed بعد تغييرات النشر؛ Alembic single head
  `88d1c505a9dc`؛ `git diff --check`: passed.
- دليل الإدارة وتدريب الموظفين العربي محدث، ودليل السوبر أدمن مصحح بحسب
  مسار إنشاء الحسابات و2FA وStep-Up الحالي.

## 7.1 CI مستقل حقيقي (GitHub Actions) — 2026-08-05

مراجعة Codex لـREL-07 كشفت إن الـCI مكنش شغال على الفرع التشغيلي خالص
(الـworkflow كان مقصور على `main`/`release/**` بس)، وإن آخر 7 تشغيلات على
`main` كانت كلها حمراء — بتفويض Mohamed الصريح ("نفّذ CI-01 + TEST-ENV-01 +
DOC-SYNC-01") اتفحصت اللوجات الفعلية (مش تخمين) واتصلحت الأسباب الجذرية:

- Redis غايب كـservice في الـCI (اتصال مرفوض على `localhost:6381` كان
  بيكسر أي تست بينادي Celery `.delay()`، وبيتسرّب لتستات تانية مش متعلقة).
- `pdftotext` (poppler-utils) غير مثبّت — تستات إيصالات الإيجار بتتأكد من
  محتوى PDF الفعلي بيه.
- `DB_PASSWORD` غير معرّف وقت فحص `docker-compose.prod.yml` (compose
  بيرفض المتغيّر الإجباري ده زي الإنتاج الحقيقي بالظبط).
- `backend/.env.prod` (مطلوب كـ`env_file:` في compose نفسه) مش موجود في
  checkout نضيف خالص — لازم ملف فاضي CI-only.
- الفرونت إند كان بيشغّل `test:unit` (بس `vitest run`) بدل `test:frontend`
  الرسمية (بتضيف فحص تطابق مفاتيح i18n عربي/إنجليزي).

**التغييرات**: `.github/workflows/ci.yml` — إضافة الفرع + `workflow_dispatch`،
`redis:7-alpine` service على نفس المنفذ اللي `.env.example` بيتوقعه، تثبيت
`poppler-utils`، قيم CI وهمية ثابتة (≥32 حرف، بدون كلمات ضعيفة) لـ
`SECRET_KEY`/`SURVEY_TOKEN_SECRET`/`TIMESHARE_PORTAL_TOKEN_SECRET`، فحص
Alembic single-head جديد، `touch backend/.env.prod` قبل فحص prod compose،
`DB_PASSWORD` وهمي، `test:frontend` بدل `test:unit`.

**دليل تشغيل حقيقي أخضر بالكامل** (مش تعديل ملف بس — تشغيل فعلي اتأكد منه):

- Resort OS commit `99bab4a`: run
  [30962088781](https://github.com/wego2388/Resort-OS/actions/runs/30962088781)
  — Backend/Frontend/Docker-Config كلهم ✅ (2246 passed، 12 skipped، صفر
  failure).
- Marketing commit `f27aa63`: run
  [30960931242](https://github.com/wego2388/elkheima-marketing-website/actions/runs/30960931242)
  — public-truth + type-check + build ✅.
- **ملاحظة توثيقية مهمة**: تشغيلتين سابقتين على نفس commit تقريبًا (قبل
  `99bab4a`) طلعوا بـ28 فشل — كلهم في تستات مبنية على `date.today()`/
  `business_today()` (فروع، مخزون شاطئ، تكلفة طعام، شيكات...)، والسبب
  اتأكد إنه توقيت التشغيل نفسه عدّى منتصف ليل UTC فعليًا أثناء الـ~5.5
  دقيقة تشغيل التستات (`assert '2026-08-05' == '2026-08-04'` حرفيًا في
  اللوج) — مش regression حقيقي من تعديلات الـCI. اتأكد بإعادة تشغيل بعيد
  عن الحد بدقايق كتير ورجعوا كلهم أخضر بنفس الـcommit بالظبط. **فجوة
  حقيقية منفصلة موثّقة هنا للمستقبل**: التستات دي مش freeze للوقت
  (زي `freezegun`)، فأي تشغيل CI يصادف منتصف الليل UTC حرفيًا معرّض لنفس
  الفلاكينس دي — تحسين مستقبلي محتمل، مش حاجز حاليًا.
- `elkheima-marketing-website` مكانش فيه أي CI خالص قبل كده — workflow
  جديد بالكامل (`f27aa63`)، أول تشغيل حقيقي طلع أخضر مباشرة.

## 8. النسخ والتراجع

- DNS rollback: Hostinger snapshot `167902017`.
- domain-cutover rollback directory:
  `/var/backups/resort-os-domain-cutover-aed94a0`، mode `0700`.
- يحتوي image manifest، SHA لنسخة DB، ونسخة مشفرة الصلاحيات من إعدادات
  Let's Encrypt السابقة وملفات systemd السابقة.
- Resort base cutover archive:
  `/var/backups/resort-os/source-releases/aed94a0.tar.gz`،
  SHA-256
  `eb404ef2341e6ca10ff658d00dc2846d6daf81cdd5589d98343c4c1e5bccca72`.
- صور ما قبل cutover محفوظة تحت
  `resort-os-rollback/*:pre-domain-aed94a0`.
- صورة Marketing السابقة محفوظة تحت
  `resort-os-rollback/marketing-site:pre-e5e122a`
  (`sha256:014777142d8cae6074b13dfee5493f5e7e08f6901797164104292a1b05121c5b`).
- صورة Marketing السابقة مباشرة لـ`16f8f2c` محفوظة تحت
  `resort-os-rollback/marketing-site:pre-16f8f2c`، والـmanifest:
  `/var/backups/resort-os/marketing-source-releases/16f8f2c-rollback-image.txt`.
- صورة Marketing السابقة مباشرة لـ`0b0321f` محفوظة تحت
  `resort-os-rollback/marketing-site:pre-0b0321f`، والـmanifest:
  `/var/backups/resort-os/marketing-source-releases/0b0321f-rollback-image.txt`.
  release القديم `/opt/elkheima-marketing-releases/16f8f2c` لسه موجود كامل
  على القرص، مش متحذوف. لا migration ولا تغيير DB في هذه الحزمة (frontend
  فقط) فمفيش نسخة DB مخصوصة ليها.
- أرشيف إصدار Marketing `4fba5b6` (حدود إدخال استمارة استبيان الضيف):
  `/var/backups/resort-os/marketing-source-releases/4fba5b6.tar.gz`،
  SHA-256
  `81018ef5e29577bfeb40c2a299dd37d12b8cf2433c4946a6798cf7b5e83bf641`.
- صورة Marketing السابقة مباشرة لـ`4fba5b6` محفوظة تحت
  `resort-os-rollback/marketing-site:pre-4fba5b6`، والـmanifest:
  `/var/backups/resort-os/marketing-source-releases/4fba5b6-rollback-image.txt`.
  release القديم `/opt/elkheima-marketing-releases/0b0321f` لسه موجود كامل
  على القرص، مش متحذوف. لا migration ولا تغيير DB في هذه الحزمة برضو.
- أرشيف إصدار Marketing `53bf7a3` (idempotency + بوابات PUBLIC_TRUTH +
  توجيه اللغة عبر باقي شاشات الموقع):
  `/var/backups/resort-os/marketing-source-releases/53bf7a3.tar.gz`،
  SHA-256
  `6e216b8ae15fda2efcda6d16e3819df9b3cbacb7c07a866c70110aec32962f6a`.
- صورة Marketing السابقة مباشرة لـ`53bf7a3` محفوظة تحت
  `resort-os-rollback/marketing-site:pre-53bf7a3`، والـmanifest:
  `/var/backups/resort-os/marketing-source-releases/53bf7a3-rollback-image.txt`.
  release القديم `/opt/elkheima-marketing-releases/4fba5b6` لسه موجود كامل
  على القرص، مش متحذوف. لا migration ولا تغيير DB في هذه الحزمة برضو.
- أرشيف إصدار Marketing `1371975` (MKT-06 — إصلاح سكرول أفقي عربي فقط في
  /contact):
  `/var/backups/resort-os/marketing-source-releases/1371975.tar.gz`،
  SHA-256
  `21fbf305bc06e038464803e1c51703a3b7bcc899e97acfcc35717ac1b061b903`.
- صورة Marketing السابقة مباشرة لـ`1371975` محفوظة تحت
  `resort-os-rollback/marketing-site:pre-1371975`، والـmanifest:
  `/var/backups/resort-os/marketing-source-releases/1371975-rollback-image.txt`.
  release القديم `/opt/elkheima-marketing-releases/53bf7a3` لسه موجود كامل
  على القرص، مش متحذوف. لا migration ولا تغيير DB في هذه الحزمة برضو.
- النسخة المشفرة خارج الخادم واستعادة 135 جدولًا ما زالتا دليل DR الأساسي.
- `resort-os-backup.timer`, `resort-os-certbot-renew.timer`,
  `resort-os-healthcheck.timer` مثبتة ومفعلة.
- أرشيف الإصدار الحالي:
  `/var/backups/resort-os/source-releases/a3e8abb.tar.gz`،
  SHA-256
  `2ff370284727ae57688c4efda9dad22db2729abf45fbbfe3dc276e78d7388bad`.
- صور ما قبل `a3e8abb` محفوظة تحت
  `resort-os-rollback/*:pre-a3e8abb`، والـmanifest المحمي:
  `/var/backups/resort-os/source-releases/a3e8abb-rollback-images.txt`،
  SHA-256
  `f904b6922081b17630814893708e39a543614d8652c2ce974922ec0fbd8f8fec`.
- نسخة DB السابقة مباشرة لنشر إصلاح الـPOS:
  `/var/backups/resort-os/database/resort_os_20260731_210536.dump`،
  SHA-256
  `5dd553f00433f0d7b70e3fcd54518c3c0c1770494efe6c4429dbd2858720aa1d`؛
  اجتازت `pg_restore --list`.
- نسخة DB السابقة مباشرة للقطع:
  `/var/backups/resort-os/database/resort_os_20260730_062529.dump`،
  SHA-256
  `bce5553a9b58d7a930c650c3f8618b7714a9a1db557e067977cc23beec10ab5a`؛
  اجتازت `pg_restore --list`.
- نسخة DB السابقة مباشرة لنشر Marketing:
  `/var/backups/resort-os/database/resort_os_20260730_143944.dump`،
  SHA-256
  `1358f16a526240b447bff98570a93eda9ee8933d8a94580ee5e8ec12c3987e04`؛
  اجتازت `pg_restore --list`.
- شُغلت خدمة healthcheck يدويًا بعد النشر ونجحت
  (`Result=success`, `ExecMainStatus=0`).
- أزيل فقط release staging غير الفعال
  `/opt/resort-os-releases/0b430fb` بعد إثبات عدم وجود symlink أو container
  يشير إليه. أرشيفه القابل للاستعادة ما زال محفوظًا تحت
  `/var/backups/resort-os/source-releases/0b430fb.tar.gz`.
- أرشيف إصدار `ddfbaaa` (دعم الطلب متعدد المنافذ + إصلاح مرتجع الإيراد):
  `/var/backups/resort-os/source-releases/ddfbaaa.tar.gz`،
  SHA-256
  `8aafedfd109a59e7ed72ea2c4ecc30b248d51af63f09198d0b0cd1629c1390d6`.
- صور ما قبل `ddfbaaa` (backend/celery_worker/celery_beat/el_kheima، كلها
  كانت `679f76e`) محفوظة تحت `resort-os-rollback/*:pre-ddfbaaa`، والـmanifest:
  `/var/backups/resort-os/source-releases/ddfbaaa-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `ddfbaaa`:
  `/var/backups/resort-os/database/resort_os_20260802_031105.dump`،
  SHA-256
  `7f65646441948e4250b9f141f6d01855e5516794507626eb09d5ebe4d97fd238`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `4a0a777` (إصلاح ضريبة الدخل في الرواتب، `backend`/
  `celery_worker`/`celery_beat` بس — `el_kheima` من `ddfbaaa` لم يتغيّر):
  `/var/backups/resort-os/source-releases/4a0a777.tar.gz`،
  SHA-256
  `a2638b2a0609cc3931e5e379a28e60823c5886b2213c472419672223227c6405`.
- صور ما قبل `4a0a777` (backend/celery_worker/celery_beat، كانوا `ddfbaaa`)
  محفوظة تحت `resort-os-rollback/*:pre-4a0a777`، والـmanifest:
  `/var/backups/resort-os/source-releases/4a0a777-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `4a0a777`:
  `/var/backups/resort-os/database/resort_os_20260802_034252.dump`،
  SHA-256
  `85f5e5fe300b5f90d49993bc820793e5e5258a2fb37ee35f663efb4784c5f8e7`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `8597535` (إصلاح باج تزامن استرداد نقاط الولاء في CRM،
  `backend`/`celery_worker`/`celery_beat` بس — `el_kheima` من `ddfbaaa`
  لم يتغيّر، صفر migration):
  `/var/backups/resort-os/source-releases/8597535.tar.gz`،
  SHA-256
  `4fcd0da28a3dd6067820315445755be6fcf31beab15114e961e7b5a2c1658320`.
- صور ما قبل `8597535` (backend/celery_worker/celery_beat، كانوا `4a0a777`)
  محفوظة تحت `resort-os-rollback/*:pre-8597535`، والـmanifest:
  `/var/backups/resort-os/source-releases/8597535-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `8597535`:
  `/var/backups/resort-os/database/resort_os_20260802_103152.dump`،
  SHA-256
  `5ecad84360934af560b617c25cdfa53b3730218342e1bce3f5e098b12196ebdc`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `b1db886` (موديول الصيانة: منع إغلاق أمر "مكتمل" عبر PATCH
  العادي + ربط تحرير الأصل بمسار الإلغاء — `backend`/`celery_worker`/
  `celery_beat`/`el_kheima` الأربعة، صفر migration):
  `/var/backups/resort-os/source-releases/b1db886.tar.gz`،
  SHA-256
  `da2bb917b3e7646c5635a4be8fe9edcfc5d80301a477385b93264d17b87cc36a`.
- صور ما قبل `b1db886` (backend/celery_worker/celery_beat/el_kheima، كانوا
  `8597535`/`ddfbaaa` بالترتيب) محفوظة تحت `resort-os-rollback/*:pre-b1db886`،
  والـmanifest: `/var/backups/resort-os/source-releases/b1db886-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `b1db886`:
  `/var/backups/resort-os/database/resort_os_20260802_105621.dump`،
  SHA-256
  `b838604a4db79f02dc099cfc2ef674eab0b6bc34364f2f344c10631cd8ffe472`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `0d55717` (موديول التحليلات: تحقق صارم على مدخلات تقييم
  الضيف العام — `backend`/`celery_worker`/`celery_beat` بس، `el_kheima`
  لم يتغيّر، صفر migration):
  `/var/backups/resort-os/source-releases/0d55717.tar.gz`،
  SHA-256
  `ba9788b147e44c0b19f03edd5541acfb54744d576a89cab71d249fba7ca3fc21`.
- صور ما قبل `0d55717` (backend/celery_worker/celery_beat، كانوا
  `b1db886`) محفوظة تحت `resort-os-rollback/*:pre-0d55717`، والـmanifest:
  `/var/backups/resort-os/source-releases/0d55717-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `0d55717`:
  `/var/backups/resort-os/database/resort_os_20260802_111432.dump`،
  SHA-256
  `c07404cc07489f3cd774938986db269ea5556f657a508ecf1cd4a0090979fa3a`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `4ca10c1` (موديول الإيجارات: تحصيل إيجار على عقد مفسوخ/
  منتهي عبر التسوية الكاش اليومية بقى مرفوض زي التحصيل العادي —
  `backend`/`celery_worker`/`celery_beat` بس، `el_kheima` لم يتغيّر، صفر
  migration):
  `/var/backups/resort-os/source-releases/4ca10c1.tar.gz`،
  SHA-256
  `e6c73575e7020a5676b6233777808211b0979bf55f87be1f986150ac9c945906`.
- صور ما قبل `4ca10c1` (backend/celery_worker/celery_beat، كانوا
  `0d55717`) محفوظة تحت `resort-os-rollback/*:pre-4ca10c1`، والـmanifest:
  `/var/backups/resort-os/source-releases/4ca10c1-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `4ca10c1`:
  `/var/backups/resort-os/database/resort_os_20260802_113200.dump`،
  SHA-256
  `d74442b6b78e52dd721b35b8427f6af0a354ef3e8f49fa61a2021e123418b870`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `5b02010` (موديول Hub: حذف كود مكرر كان بيسبب
  UnboundLocalError صامت في تأكيد الحجوزات الأونلاين — `backend`/
  `celery_worker`/`celery_beat` بس، `el_kheima` لم يتغيّر، صفر migration):
  `/var/backups/resort-os/source-releases/5b02010.tar.gz`،
  SHA-256
  `50538820d9b9e4ef9e3d724e45b09dfca4dfc86e25154a852fab98765900b673`.
- صور ما قبل `5b02010` (backend/celery_worker/celery_beat، كانوا
  `4ca10c1`) محفوظة تحت `resort-os-rollback/*:pre-5b02010`، والـmanifest:
  `/var/backups/resort-os/source-releases/5b02010-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `5b02010`:
  `/var/backups/resort-os/database/resort_os_20260802_115042.dump`،
  SHA-256
  `f2547e1b089c7e9706931536218be92868faf4622f0519e60c6870e364330f91`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `821a718` (23 commit — راجع القسم 2 أعلاه للنطاق الكامل؛
  `backend`/`celery_worker`/`celery_beat`/`el_kheima`/`marketing_site`
  (سياق بدون تغيير مصدر) اتبنوا واتنشروا كلهم، 4 migrations):
  `/var/backups/resort-os/source-releases/821a718.tar.gz`،
  SHA-256
  `542cdaa35f7dfb6ae1dd6da68c825d65954da2606a57783ff177c479f35a4411`.
- صور ما قبل `821a718` (backend/celery_worker/celery_beat/el_kheima/
  marketing_site/nginx، كانوا `5b02010`) محفوظة تحت
  `resort-os-rollback/*:pre-821a718`، والـmanifest:
  `/var/backups/resort-os/source-releases/821a718-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `821a718`:
  `/opt/resort-os-releases/5b02010/backups/resort_os_20260803_232155.dump`،
  SHA-256
  `e9eff9a27f3d81403de4f7589d385a4c5bdaebb141b19d297fe27e8852f1969b`؛
  اجتازت `pg_restore --list` (1373 TOC entries، تحقّق فعلي داخل حاوية
  الـDB نفسها).

## 9. الحالة المتبقية

| الحزمة | الحالة |
|---|---|
| REL-04 — staff-control-plane deploy | COMPLETE |
| REL-05 — multi-outlet POS fix deploy | COMPLETE |
| DATA-01-DEMO — realistic synthetic dataset | COMPLETE |
| CHAT-01 — chatbot activation/live verification | COMPLETE |
| DNS-01 — domain/TLS cutover | COMPLETE |
| DOC-OPS — management/staff Arabic training guide | COMPLETE |
| ACC-01 — employee/account workflow | DEPLOYED؛ ACCOUNTS PENDING ROSTER |
| UAT-01 — device/roles/workflow acceptance | PENDING |
| DATA-02 — approved real master data | PENDING OWNER/OPERATIONS REVIEW |
| OPS-01 — monitoring and burn-in | BASELINE COMPLETE؛ external delivery pending |
| provider snapshot | RECOMMENDED؛ DNS snapshot وoff-server DB موجودان |

لا توجد مشكلة تطبيق أو DNS أو TLS معروفة تستوجب rollback. لا يعني ذلك
اعتماد العمليات أو المالية؛ UAT والبيانات الحقيقية وقرار Go/No-Go تظل
مسؤولية المالك وممثلي التشغيل.
