# Handoff — CX-02D: إصلاح overflow-y-auto والجداول المتبقية
**التاريخ:** 2026-08-12
**الـ Branch:** `claude/CX-02C-frontend-auth-bootstrap`
**آخر commit:** `601c6b4`
**الحالة:** مُنشور على الإنتاج ✅ (`app.elkheima.com` — HTTP 200)

---

## المشكلة الجذرية (اكتُشفت من صور المستخدم)

على الكمبيوتر الكبير، المستخدم مش قادر يعمل scroll أفقي على جدول "الحسابات الحالية" في Super Admin Panel — رغم إن `overflow-x-auto` موجودة على الجدول.

**السبب:** `BackOfficeLayout.vue` عنده `overflow-auto` على الـ `<main>` — ده بياكل الـ `overflow-x-auto` الداخلي لـ **كل** الجداول في **كل** الصفحات على الشاشات الكبيرة.

---

## التغييرات — commit `601c6b4`

### `BackOfficeLayout.vue`
```
overflow-auto → overflow-y-auto على <main>
```
كان الـ `overflow-auto` بيمنع الـ scroll الأفقي الداخلي من الشغل على الكمبيوتر. التغيير لـ `overflow-y-auto` بيحافظ على الـ vertical scroll بس بيسمح للـ overflow الأفقي الداخلي يشتغل صح.
**يؤثر على كل صفحات** `admin/*` + `ops/*` + `portal/*`.

### `AnalyticsView.vue`
- جدول تفصيل الإيرادات (سطر 414): أضيف `min-w-[360px]`
- جدول مقارنة الإيرادات (سطر 467): أُضيف `overflow-x-auto` wrapper + `min-w-[480px]`

### `CRMView.vue`
- جدول العملاء (سطر 922): أُضيف `overflow-x-auto` wrapper + `min-w-[560px]`
- جدول الضيوف (سطر 1112): أُضيف `overflow-x-auto` wrapper + `min-w-[500px]`

### `FinanceView.vue` — Balance Sheet
- جدول Assets/Liabilities/Equity (3 أعمدة بسيطة): أضيف `min-w-[380px]` لكل منهم

### `BeachLiveDashboardView.vue`
- جدول ملخص المعاملات: أُضيف `overflow-x-auto` wrapper + `min-w-[320px]`

---

## الفحوصات

```bash
pnpm --filter el-kheima run type-check  # ✅ نظيف
pnpm --filter el-kheima run test:frontend  # ✅ 103/103
bash scripts/sync-deploy.sh resort-os el_kheima  # ✅ healthy
curl https://app.elkheima.com/admin/super-admin  # ✅ HTTP 200
```

---

## الحالة الحالية للإنتاج
- الإصدار الفعال: commit `601c6b4` (frontend) + `8fbda3c` (backend — لم يتغير)
- `app.elkheima.com` — HTTP 200 ✅
- كل الخدمات `healthy` ✅
- لا migrations — Alembic head: `d1e2f3a4b5c6`

---

## ما يظل مقبولاً (قرار مقصود)
- `BookingsView.vue` table: محمي بـ `hidden md:block` — يظهر فقط على md+ ✅
- `MaintenanceView.vue` table (سطر 580): جدول القطع 3 أعمدة صغيرة داخل card ضيقة — مقبول بدون wrapper
- `FinanceView.vue` tables الفرعية في Income Statement: جداول inline داخل rows موجودة في context محدود — مقبولة
