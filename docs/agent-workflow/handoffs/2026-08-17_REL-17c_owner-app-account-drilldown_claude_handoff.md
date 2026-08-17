# REL-17c — الضغط على كارت الإيراد/المصروف يفتح تفصيل من الحسابات

**التاريخ:** 2026-08-17
**المنفّذ:** Claude (نفس الجلسة، متابعة لـREL-17b)
**الفرع:** `codex/rel-15-auth-ops-readiness`
**Implementation/Release commit:** `b162bbed78a0d169c13b59f92d9fa9c1cae75b4a`

## 1. الدافع

Mohamed جرّب تطبيق المالك (بعد REL-17b) وطلب: "لما يضغط على كارت زي دول
يشوف تفاصيل أكتر... حاول تاخد التفاصيل من الحسابات وتشوفها بطريقة كويسة
وذكية."

## 2. التنفيذ

- جانب **المصروف** كان عنده البنية التحتية دي بالفعل ("Phase 8" drill-down
  — `ExpensesScreen.vue` بتاعت المصروفات/المشتريات) لكن مالهاش أي اختبار
  خالص، ومش موصول بكروت "الآن"/"الأداء" الرئيسية.
- جانب **الإيراد** ملوش أي endpoint تفصيل بالحساب خالص.

**Backend (إضافي بحت، مفيش migration):**
- `RevenueBreakdownResponse`/`RevenueLineResponse` + `RevenueDetailResponse`/
  `RevenueJournalLine` — نظير schemas المصروف بالحرف.
- `get_revenue_breakdown()` — غلاف رفيع فوق
  `finance.get_income_statement`'s الموجودة أصلاً `revenue_lines` (محسوبة
  من قبل، لكن مفيش حد كان بيقراها) — صفر حساب جديد، نفس مصدر الحقيقة
  المستخدم لأي رقم مالي أساسي تاني (Decision 0004).
- `get_revenue_detail()` — نظير `get_expense_detail()` على جانب الدائن
  (الإيراد يزيد بالدائن، المصروف بالمدين).
- `GET /owner/revenue-breakdown`، `GET /owner/revenue-detail` — نفس نمط
  `get_owner_reader`/`no-store`/تسجيل تدقيق عند drill-down.
- 9 اختبار جديد (كان صفر تغطية لعائلة الـdrill-down دي كلها، بما فيها
  `expense-detail` الموجودة من قبل): تطابق مع income statement، فلترة
  قيود اليومية صح، pagination، عزل الفرع، رفض غير المالك.

**Frontend:**
- `MetricCard.vue` — prop جديد `clickable` — بيتحول لـ`<button>` حقيقي
  بمؤشر "‹" بدل `<div>` ثابت.
- `PeriodComparisonCard.vue` — صفوف الإيراد/المصروف بقت أزرار بتصدر
  `click-revenue`/`click-expense`.
- `useAccountBreakdownDrilldown()` — composable مشترك جديد (مستويين فوق
  `useDetailSheet`: قائمة حسابات → قيود اليومية داخل حساب منها، مع زرار
  رجوع) — نفس الكود مستخدم في `NowScreen` (الفترة = اليوم) و
  `PerformanceScreen` (الفترة = أي تاب نشط).
- `NowScreen`: كارتي "إيراد اليوم"/"مصروفات اليوم" بيفتحوا الـdrilldown
  دلوقتي؛ "كاش الأدراج" بيودّي لشاشة `/shifts` (تفاصيله الحقيقية هناك
  أصلاً، مش مفهوم قيد يومية).
- `PerformanceScreen`: صفوف الإيراد/المصروف بتفتح تفصيل الفترة النشطة
  فعليًا (اليوم/الأسبوع/الشهر) من `PeriodSnapshot.date_from/date_to`.

## 3. التحقق

```
backend  pytest tests/ -q                → صفر فشل (2956 مجمّعة)
backend  scripts/agent-check.sh           → PASS (alembic heads = 79d4d53e7109، بدون تغيير)
frontend type-check:all                   → نظيف (el-kheima + owner)
frontend build (owner)                    → نظيف
frontend test:e2e (owner، 12 اختبار)      → 12/12 (320-1280px، صفر تراجع تخطيط)
```

**تحقق تفاعلي حي حقيقي** (Playwright، ضغطات فعلية، مش build ناجح بس):
ضغط كارت "إيراد اليوم" → نافذة تفصيل بالحساب فتحت ببيانات حقيقية (إيراد
الغرف/المطعم) → ضغط حساب → نافذة قيود اليومية الفعلية فتحت (رقمين حجز
حقيقيين) → زرار "رجوع" رجّع لقائمة الحسابات → إغلاق النافذة اشتغل → صفر
overflow أفقي طول التسلسل كله.

## 4. سجل النشر على VPS

**Release commit:** `b162bbed78a0d169c13b59f92d9fa9c1cae75b4a`
**النطاق**: backend (endpoints جديدة، مفيش migration) + owner frontend.
`backend`/`celery_worker`/`celery_beat`/`owner` الأربعة اتبنوا واتستبدلوا؛
`el_kheima`/`nginx`/`marketing_site` متلمسوش.

- SHA-256 مطابق (local ↔ remote):
  `99bacc576491dc298170f0102c5da3e91361d65e7fddfe299ae05d53b3f29973`
- `.env.prod` بصلاحية `0600`، `validate_prod_env.py` → PASS.
- Rollback manifest: `backend`/`celery-worker`/`celery-beat`/`owner` —
  4 صور موسومة `resort-os-rollback/<name>:pre-b162bbe...`.
- نسخة قاعدة بيانات جديدة قبل النشر (1587 TOC entry، اتحقق منها
  بـ`pg_restore --list`) — رغم عدم وجود migration، لأن كود backend نفسه
  اتغيّر.
- Preflight: `python -c 'from app.main import app'` → "El Kheima Beach"،
  `alembic heads` → `79d4d53e7109` (بدون تغيير، مؤكَّد قبل الاستبدال).
- استبدال محكوم: `backend` → `celery_worker`+`celery_beat` → `owner` —
  الأربعة healthy فورًا، `RestartCount=0`.
- تحقق: image ID/revision متطابق للثلاثة (backend/worker/beat) =
  commit الجديد بالظبط؛ الـbundle المنشور فعليًا لـ`owner`
  (`NowScreen-Ck6P5cYw.js`, `PerformanceScreen-6vF0y1oz.js`) نفس hash
  الـbuild المحلي بالظبط.
- Endpoints جديدة عبر `https://app.elkheima.com` مباشرة: `401` (مش
  `404`) — تسجيل صح، محمي بمصادقة صح.
- صفر خطأ جديد في لوجات backend/owner/nginx.
- Health gate الرسمي: `RESORT_HEALTHCHECK_OK passes=16`.
- `/opt/resort-os-current` مُحدَّث للإصدار الجديد.

## 5. الخلاصة

طلب Mohamed المحدد ("الضغط على كارت زي دول يوريني تفاصيل أكتر من
الحسابات") اتنفّذ بالكامل على كارتي الإيراد والمصروف الرئيسيين في شاشتي
"الآن" و"الأداء"، بمستويين حقيقيين (حساب → قيد يومية فعلي)، من نفس مصدر
الحقيقة المحاسبي المستخدم في كل مكان تاني بالتطبيق — مش رقم متخيّل أو
تقريبي. تم النشر والتحقق الكامل على الإنتاج.
