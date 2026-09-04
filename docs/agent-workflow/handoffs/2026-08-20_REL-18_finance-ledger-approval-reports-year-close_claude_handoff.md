# REL-18 — كشف حساب، حد موافقة المصروفات، تصدير التقارير المالية، تقرير أعمار الديون، الإقفال السنوي

**التاريخ:** 2026-08-20
**المنفّذ:** Claude (نفس الجلسة، متابعة لدفعة المحاسبة الأولى في REL-17)
**الفرع:** `codex/rel-15-auth-ops-readiness`
**Implementation/Release commit:** `9504ae3d5e9a263757c618b2d36b48db94d8c3f7`
(يشمل commit سابق `19820d6ceee8172bc400a87fc52bfb356ed9fc7a` + إصلاح تباين لوني بسيط)

## 1. الدافع

بعد دفعة "المحاسب" الأولى (REL-17: العهدة/إذن القبض/المصروف الآجل)، سأل
Mohamed: "هل ناقص المحاسب اي حاجه في المحاسبه تخص شغله لم تظكر او مش معمول
بيها؟" — بعد فحص شامل تم اختيار 5 فجوات حقيقية وطلب تنفيذها: (1) كشف حساب
لكل حساب، (2) حد موافقة على المصروفات، (3) تصدير PDF/Excel للتقارير
المالية، (4) تقرير أعمار الديون (Aging)، (7) الإقفال السنوي. بعدها طلب
Mohamed صراحةً تنظيم شاشة `FinanceView.vue` في مجموعات منطقية "زي برنامج
محاسبي حقيقي" مع الحفاظ على وضوح مراقبة الكاشير/الورديات.

## 2. التنفيذ

**Backend (إضافي بحت، migration واحدة جديدة):**
- `GET /finance/accounts/{account_id}/ledger` — كشف حساب برصيد متحرك
  (opening/closing balance، مدين/دائن لكل قيد) خلال مدى تاريخي.
- حد موافقة المصروفات: `EXPENSE_APPROVAL_THRESHOLD` (إعداد جديد، افتراضي
  5000 جنيه) — مبلغ السند لو تخطاه، `policy_engine.require_approval`
  (نفس نمط إلغاء الصنف/الخصم) بيطلب PIN مدير+ (`min_approver_level=80`،
  أعلى عمدًا من `min_role_level=60` بتاع تسجيل مصروف عادي، عشان الحد
  يبقى فاعل فعليًا مش no-op — راجع تفاصيل الحساب في تعليق الكود).
- `GET /finance/reports/{trial-balance,income-statement,balance-sheet}/{pdf,excel}`
  — 6 endpoints تصدير جديدة، بنفس نمط `ReportBuilder` المستخدم في تقارير
  الورديات/كشوف الرواتب.
- `GET /finance/reports/aging` — تقرير أعمار الديون: فوليوهات مفتوحة
  (مستحقة لنا) + أوامر شراء/مصروفات آجلة غير مسددة (مستحقة علينا)، مبوّبة
  0-30/31-60/61-90/90+ يوم.
- `POST /finance/periods/{year}/close-year` (`min_role_level=80`) — إقفال
  سنة محاسبية: يرحّل صافي الربح/الخسارة لحساب الأرباح المرحّلة (3200)
  ويسجّل الإقفال في جدول `accounting_year_closes` الجديد. يستدعي
  `crud.create_journal_entry` مباشرة (مش `post_journal_entry`) عشان يتجاوز
  `validate_period_open`'s قفل شهر ديسمبر (لازم يكون مقفول أصلاً كشرط
  مسبق للإقفال السنوي).
- Migration `a63858c55efa` — جدول `accounting_year_closes` فقط (branch_id,
  year, journal_entry_id, net_income, closed_by, closed_at).
- تغطية اختبارات كاملة لكل الميزات الخمسة (تفاصيل التصحيحات الحقيقية أثناء
  الكتابة موثّقة في `PROJECT_STATUS.md`).

**Frontend (`FinanceView.vue`):**
- إعادة تنظيم كاملة لتابات الشاشة الـ18 في 4 مجموعات منطقية: العمليات
  اليومية (نظرة عامة/الورديات/المصروفات/العهد/أذون القبض/قنوات التحصيل)،
  الحسابات والدفتر (الحسابات/دفتر اليومية/مراكز التكلفة/الشيكات)، التقارير
  المالية (ميزان المراجعة/قائمة الدخل/الميزانية/أعمار الديون)، إعدادات
  متقدمة (الفترات/أسعار الصرف/الإهلاك/التسوية البنكية) — شريط تابات
  بمستويين (مجموعة ثم تاب فرعي).
- كشف حساب: صفوف جدول الحسابات بقت قابلة للضغط، بتفتح modal بمدى تاريخي
  قابل للتعديل، رصيد افتتاحي/ختامي، وجدول قيود برصيد متحرك.
- تدفق موافقة PIN لسند المصروفات: بيتبعت عادي، ولو رفضه السيرفر برسالة
  "محتاج موافقة مدير بالـ PIN" تحديدًا، بيفتح `PinGuardModal`
  (`min-level=80`) ويعيد المحاولة بـ`approver_user_id`/`approver_pin` —
  مفيش تكرار لقيمة الحد نفسها في الفرونت إند.
- 3 تابات جديدة (ميزان المراجعة، أعمار الديون، الفترات) + زراير تحميل
  PDF/Excel على ميزان المراجعة/قائمة الدخل/الميزانية العمومية (نمط
  `downloadBlobFile` الموجود في `HRView.vue`).
- تاب الفترات: شبكة 12 شهر (حالة مفتوح/مقفول تتولّد من غياب/وجود صف
  `AccountingPeriod`، مش endpoint منفصل)، زرار إقفال شهر لكل شهر، وزرار
  "إقفال السنة المالية" (يظهر لمدير+ فقط، مقفول بـ`auth.hasRole('admin')`
  في الواجهة زي ما الباك إند يفرضه).
- i18n كامل عربي/إنجليزي (48 مفتاح جديد، `groups.*`/`tabs.*`/`ledger.*`/
  `trialBalance.*`/`aging.*`/`periods.*`).

**إصلاح جانبي أثناء التحقق**: `test:frontend`'s حارس التباين اللوني
(`themeContrast.spec.ts`) كشف `dark:text-gray-500` حقيقي في تاب الفترات
(تسمية تاريخ الإقفال) — اتصلح لـ`dark:text-gray-400` زي باقي النصوص
الثانوية في نفس الملف (commit منفصل `9504ae3`).

## 3. التحقق

```
backend  pytest tests/ -v (كامل، مش -q — البيئة دي بتخفي سطر النتيجة مع -q)
                                           → 2965 passed, 68 skipped, صفر فشل
backend  scripts/agent-check.sh           → PASS (alembic heads = a63858c55efa)
frontend type-check:all                   → نظيف (el-kheima + owner)
frontend test:frontend (i18n + vitest)    → 106/106 (بعد إصلاح التباين)
frontend test:e2e:mock (el-kheima)        → 8/8
frontend test:e2e (owner)                 → 12/12
frontend test:e2e (el-kheima، حي ضد dev server) → 74/74 (RTL/responsive)
frontend build:all                        → نظيف
```

**تحقق تفاعلي حي حقيقي** (Playwright ضد dev server حقيقي، تسجيل دخول
`manager@resortos.local`): شريط المجموعات بيتنقل صح، ميزان المراجعة
بيعرض بيانات حقيقية + زراير PDF/Excel، قائمة الدخل بتعرض الإيراد/المصروف
وصافي الربح، تقرير أعمار الديون بيعرض فوليوهات/موردين حقيقيين ببادجات
عمرية ملوّنة، تاب الفترات بيعرض شبكة الـ12 شهر (زرار "إقفال السنة" مختفي
صح لمستخدم مدير مش أدمن)، الضغط على صف حساب بيفتح كشف الحساب فعليًا. تحميل
PDF حقيقي عبر curl مباشر (`trial-balance/pdf`) رجّع ملف PDF حقيقي 260KB.
اختبار مباشر لحد موافقة المصروفات عبر API (منسوخ فوق الحد كـ manager) رجّع
بالظبط رسالة الرفض المتوقعة (400، "الإجراء ده محتاج موافقة مدير بالـ PIN").

## 4. سجل النشر على VPS

**Release commit:** `9504ae3d5e9a263757c618b2d36b48db94d8c3f7`
**النطاق**: backend (endpoint جديدة + migration واحدة) + `el_kheima`
frontend. `backend`/`celery_worker`/`celery_beat`/`el_kheima`/`nginx`
اتبنوا واتستبدلوا؛ `owner`/`marketing_site` اتبنى `owner` أيضًا (جزء من
build --parallel القياسي) بس محتواه متغيّرش فعليًا هذه الدفعة.

- SHA-256 مطابق (local ↔ remote):
  `111a6b4e9a3227d32263b0d308f4279fa9a74f95f9c50ea96424fc26a99c34f5`
- `.env.prod` بصلاحية `0600`، `validate_prod_env.py` → PASS.
- Rollback manifest: `backend`/`celery-worker`/`celery-beat`/`el-kheima`/
  `owner`/`marketing-site`/`nginx` — 7 صور موسومة
  `resort-os-rollback/<name>:pre-9504ae3...`
  (`/var/backups/resort-os/source-releases/9504ae3...-rollback-images.txt`).
- نسخة قاعدة بيانات جديدة قبل النشر (1638 TOC entry، اتحقق منها
  بـ`pg_restore --list` عبر `docker cp` + مسار ملف مباشر).
- Preflight: `python -c 'from app.main import app'` → "El Kheima Beach"،
  `alembic heads` → `a63858c55efa` (مطابق للمتوقع، مؤكَّد قبل الاستبدال).
- Migration فعلية على قاعدة بيانات الإنتاج الحقيقية:
  `alembic upgrade head` → `e58e17b2593d -> a63858c55efa, accounting year close`
  (جدول إضافي بحت، صفر أثر على جداول موجودة).
- استبدال محكوم بالترتيب: `backend` → `celery_worker`+`celery_beat` →
  `el_kheima`+`owner` → `nginx` (force-recreate) — كل مرحلة `healthy`
  فورًا، `RestartCount=0` للثلاثة (backend/worker/beat).
- تحقق: image ID/revision متطابق تمامًا للثلاثة (backend/worker/beat) =
  commit الجديد بالظبط.
- الـ4 نطاقات العامة (`elkheima.com`, `www.elkheima.com`,
  `app.elkheima.com`, `owner.elkheima.com`) → `200` من خارج الـVPS،
  `/health` → `{"status":"ok", database: ok, redis: ok}`.
- شهادة TLS SAN تغطي الأربعة نطاقات.
- Endpoints جديدة عبر `https://app.elkheima.com` مباشرة (trial-balance،
  aging، account-ledger، close-year) → `401` (مش `404`) — تسجيل صح، محمي
  بمصادقة صح.
- صفر traceback/critical/fatal/emergency جديد في لوجات
  backend/celery/nginx.
- منافذ Postgres/Redis (5436/6381) لسه loopback-only (`127.0.0.1`) بس.
- Health gate الرسمي: `RESORT_HEALTHCHECK_OK passes=16`.
- `/opt/resort-os-current` مُحدَّث للإصدار الجديد.

## 5. مؤجَّل عمدًا برّه نطاق REL-18

باج حقيقي منفصل اتكشف أثناء مراجعة كود كاشير الشاطئ/الدايننج (بطلب صريح
من Mohamed أثناء تجربته الحية لكاشير الدايننج والشاطئ، مش جزء من دفعة
المحاسبة دي): مسار البيع الجزئي/أوفلاين في `BeachPOSView.vue`
(`completeSale()`) ممكن يبيع نفس الصنف مرتين لو صنف تاني في نفس السلة
فشل بعد ما صنف نجح (مفيش idempotency key لكل صنف على المسار ده، عكس
المسار الأونلاين الذري). قيد الإصلاح في نفس الجلسة، منفصل تمامًا عن
النشر ده.

## 6. الخلاصة

الميزات الخمسة اللي طلبها Mohamed صراحةً (كشف حساب، حد موافقة، تصدير
تقارير، أعمار ديون، إقفال سنوي) + إعادة تنظيم شاشة المحاسبة بالكامل
"زي برنامج محاسبي حقيقي" (طلب Mohamed الصريح) اتنفّذوا، اتاختبروا، واتنشروا
على الإنتاج الحقيقي بنجاح كامل. صفر تراجع (2965 اختبار backend، 200+
اختبار frontend، صفر خطأ في لوجات الإنتاج).
