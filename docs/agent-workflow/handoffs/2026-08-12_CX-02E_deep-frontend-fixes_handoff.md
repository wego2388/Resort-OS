# Handoff — CX-02E: إصلاحات عميقة في الفرونت اند
**التاريخ:** 2026-08-12
**الـ Branch:** `claude/CX-02C-frontend-auth-bootstrap`
**آخر commit:** `1e14a3f`
**الحالة:** مُنشور على الإنتاج ✅ (`app.elkheima.com` — HTTP 200)

---

## المشاكل التي اكتُشفت وأُصلحت

### 1. KioskLayout + DiningKDSView — نفس مشكلة BackOfficeLayout
**الملفات:** `layouts/KioskLayout.vue` + `views/kds/DiningKDSView.vue`

`KioskLayout` كان `min-h-screen` + `overflow-auto` — نفس المشكلة اللي كانت في BackOfficeLayout. شاشة الـ KDS المثبتة على الحيط مكانتش بتتقفل في الشاشة.

`DiningKDSView` كان عنده `min-h-screen` داخله كمان — double expansion داخل layout مقفول.

**الإصلاح:**
- `KioskLayout`: `min-h-screen` → `h-screen overflow-hidden`، `main overflow-auto` → `overflow-y-auto min-h-0`
- `DiningKDSView`: `min-h-screen` → `h-full` (يملأ الـ parent المقفول)

---

### 2. BackOfficeLayout sidebar — `height: 100vh` → `height: 100%`
**الملف:** `layouts/BackOfficeLayout.vue`

الـ `sticky` sidebar كان `height: 100vh` — بعد تغيير الـ root لـ `h-screen overflow-hidden`، الـ `100%` أصح لأنه يملأ الـ parent المقفول بدون تجاوز.

---

### 3. DashboardView — setInterval يتضاعف عند تبديل التابات
**الملف:** `views/admin/DashboardView.vue`

`handleVisibilityChange` كان بيشغّل `setInterval` جديد لما الـ tab يرجع visible بدون ما يتأكد من مسح الـ timer القديم أولاً. بعد فتح وإغلاق التابات عدة مرات، الـ API calls بتتضاعف (memory leak + extra load).

**الإصلاح:** إضافة `clearInterval` قبل إنشاء الـ timer الجديد.

---

### 4. DataTable (packages/ui) — بدون min-w
**الملف:** `packages/ui/src/components/DataTable.vue`

`DataTable` المستخدمة في `DiningMenuView` كانت بتتضغط على الموبايل.

**الإصلاح:** إضافة `tableMinWidth` computed بناءً على عدد الأعمدة:
`4→500px / 5→600px / 6→700px / 7→800px / 8→900px / 9+→1000px`

---

### 5. RoomsView + LeavesView — Custom modals بدون accessibility
**الملفات:** `views/ops/RoomsView.vue` + `views/portal/LeavesView.vue`

Modal panels داخل Teleport بدون `role="dialog"` / `aria-modal` / `aria-labelledby` — screen readers مكانتش بتعرف تتعامل معاهم.

**الإصلاح:** إضافة `role="dialog" aria-modal="true" aria-labelledby` على الـ panel، `id` على الـ heading، `aria-label` على زر الإغلاق.

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
- الإصدار الفعال: commit `1e14a3f` (frontend) + `8fbda3c` (backend — لم يتغير)
- `app.elkheima.com` — HTTP 200 ✅
- كل الخدمات `healthy` ✅
- لا migrations — Alembic head: `d1e2f3a4b5c6`
