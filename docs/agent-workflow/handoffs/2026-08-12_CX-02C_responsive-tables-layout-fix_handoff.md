# Handoff — CX-02C: إصلاح تجاوب الجداول والـ Layout
**التاريخ:** 2026-08-12
**الـ Branch:** `claude/CX-02C-frontend-auth-bootstrap`
**آخر commit:** `79b910d`
**الحالة:** مُنشور على الإنتاج ✅ (`app.elkheima.com` — HTTP 200)

---

## المشكلة التي اكتُشفت

بدأت من صورة للـ Super Admin Panel — عمود "إجراء" كان مش ظاهر على شاشة التابلت/موبايل.
بعد تحليل أعمق اتضح إن:

1. **كل جداول التطبيق** (15 ملف، 32 جدول) كانت بدون `min-width` جوا `overflow-x-auto` — الجداول بتتضغط وتخفي الأعمدة الأخيرة بدل ما تعمل scroll أفقي.
2. **أعمدة الإجراءات** في بعض الجداول بدون `whitespace-nowrap` — الأزرار بتتكسر لسطرين.
3. **Email في جدول المستخدمين** بدون `dir="ltr"` — بيتعرض معكوس في الـ RTL.
4. **TimeshareView** — `AppModal` بيستخدم `v-model:open` بدون `@close` handler صريح.
5. **على الكمبيوتر الكبير** — المحتوى بيتمدد لكامل عرض الشاشة (1600px+) بدون حد أقصى، فالجداول تبدو "مفرودة" ومش مريحة بصرياً.

---

## التغييرات المنفذة — 4 Commits

### `74312cc` — SuperAdmin users table
```
frontend/apps/el-kheima/src/views/admin/SuperAdminView.vue
- table: w-full → w-full min-w-[860px]
- th#actions: أضيف min-w-[220px]
```

### `c7dbf42` — كل الجداول (15 ملف)
أضفنا `min-w` مناسب لعدد الأعمدة على كل `<table>` جوا `overflow-x-auto`:

| الملف | الجداول | min-w المضاف |
|---|---|---|
| FinanceView.vue | 6 جداول | 600px – 1100px |
| HRView.vue | 3 جداول | 600px – 900px |
| BeachAdminView.vue | 2 جداول | 860px – 1000px |
| InventoryView.vue | 2 جداول | 700px – 960px |
| HubManagementView.vue | 3 جداول | 700px – 800px |
| MaintenanceView.vue | 1 جدول | 900px |
| RecipesView.vue | 1 جدول | 900px |
| LeasingView.vue | 1 جدول | 800px |
| CreditAccountsView.vue | 1 جدول | 700px |
| EInvoiceView.vue | 1 جدول | 700px |
| AnalyticsView.vue | 2 جداول | 600px – 700px |
| SettingsView.vue | 1 جدول | 600px |
| SuperAdminView.vue | 1 جدول (permissions) | 800px |
| FoodCostReportView.vue | 1 جدول | 960px |
| ShiftMonitorView.vue | 1 جدول | 900px |

**المبدأ:** 4 cols→600px / 5→700px / 6→800px / 7→900px / 8→960-1000px / 9+→1100px

### `f423f6f` — UX fixes
```
BeachAdminView.vue      → whitespace-nowrap على td الإجراءات (B2B contracts)
HRView.vue             → whitespace-nowrap على td الإجراءات (employees)
HubManagementView.vue  → whitespace-nowrap على td الإجراءات (bookings/pages/blog)
SuperAdminView.vue     → dir="ltr" + break-all على email في td
TimeshareView.vue      → @close="scheduleModal.open = false" على AppModal
```

### `79b910d` — Layout max-width (الأهم للكمبيوتر)
```
frontend/apps/el-kheima/src/layouts/BackOfficeLayout.vue

التغيير: أضفنا wrapper div حول RouterView:
<div class="mx-auto w-full max-w-[1400px]">
  <RouterView ... />
</div>
```
يؤثر على **كل صفحات** `admin/*` + `ops/*` + `portal/*` — على الشاشات الكبيرة المحتوى مقيّد بـ 1400px ومتمركز.

---

## نقاط مهمة للعمل معها

### الـ Branch والـ Deploy
- الـ branch الحالي: `claude/CX-02C-frontend-auth-bootstrap`
- **الـ VPS يشتغل بـ `sync-deploy`** مش `git pull` — يعني الملفات بتتنقل بـ rsync مباشرة بصرف النظر عن الـ branch
- لنشر أي تغيير frontend: `bash scripts/sync-deploy.sh resort-os el_kheima`
- لنشر backend: `bash scripts/sync-deploy.sh resort-os backend,celery_worker,celery_beat`

### هيكل المشروع المهم
```
backend/                    FastAPI + Python 3.11
  app/modules/              13 موديول (core/finance/hr/dining/pms/...)
  app/core/kernel/          auth/JWT/middleware/errors/health
  alembic/versions/         migrations

frontend/apps/el-kheima/    Vue 3 + Vite + TailwindCSS — تطبيق الموظفين
  src/layouts/
    BackOfficeLayout.vue    ← الـ Layout الرئيسي (sidebar + topbar + main)
    FieldLayout.vue         ← للـ POS/KDS
  src/views/admin/          شاشات الإدارة
  src/views/ops/            الاستقبال/الحجوزات/الغرف
  src/views/pos/            POS
frontend/apps/owner/        لوحة المالك (owner.elkheima.com)
frontend/packages/core/     API client + Pinia stores + i18n
frontend/packages/ui/       مكونات مشتركة (AppModal/AppCard/AppButton...)
```

### تعليمات قبل أي تغيير (من AGENTS.md)
1. `git status --short --branch` — تأكد من الـ branch
2. `bash scripts/agent-check.sh` — baseline سريع
3. بعد التغيير: `pnpm --filter el-kheima run type-check` ثم `pnpm --filter el-kheima run test:frontend`
4. Tests يجب تعدي 103/103 قبل الـ deploy

### مشاكل اكتُشفت ولم تُصلح (اختياري لاحقاً)
- `float` في بعض response schemas في `analytics/dining/finance` — مش في الـ DB models (محمية بـ Decimal) لكن في الـ JSON responses
- `e: any` في TypeScript — 128 حالة معظمها `catch (e: any)` مقبولة

---

## الحالة الحالية للإنتاج
- الإصدار الفعال على VPS: commit `79b910d` (frontend) + `8fbda3c` (backend — لم يتغير)
- `app.elkheima.com` — HTTP 200 ✅
- كل الخدمات `healthy` ✅
- لا migrations جديدة — Alembic head: `d1e2f3a4b5c6`
