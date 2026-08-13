# Handoff — CX-02G: إصلاح login freeze + WebSocket branchId=null
**التاريخ:** 2026-08-12
**الـ Branch:** `claude/CX-02C-frontend-auth-bootstrap`
**آخر commit:** `fe0c160`
**الحالة:** مُنشور على الإنتاج ✅ (`app.elkheima.com` — HTTP 200، el_kheima healthy)

---

## المشاكل التي اكتُشفت وأُصلحت

### 🔴 1. Login freeze للكاشير بعد تغيير الباسورد
**الملف:** `LoginView.vue`

**السبب الحقيقي:** بعد `auth.login()` ينجح وبيعمل `fetchBootstrap()` داخلياً، الـ `router.push('/')` كان بيتنفذ synchronously في نفس الـ microtask. الـ Vue reactivity queue لم تُفرَّغ بعد، فالـ router guard كان يقرأ `auth.branchId = null` (القيمة القديمة قبل `_applyBootstrap`) ويوجّه الكاشير لـ `/select-branch` بدل `/pos/beach`.

المستخدم كان يشوف الصفحة "مجمّدة" لأن الـ navigation كان بيحصل في الخلفية وهو لسه على `/login`.

**الإصلاح:** إضافة `await nextTick()` بعد `auth.login()` وقبل `router.push()` — يضمن flush الـ reactive state الكامل قبل تقييم الـ guard.

---

### �ارنج 2. BranchSelectionView: لا auto-select للفرع الوحيد
**الملف:** `BranchSelectionView.vue`

الكاشير/الموظف الجديد كان يُعرض عليه شاشة اختيار فرع رغم أن له فرع واحد بالظبط — خطوة إضافية غير ضرورية.

**الإصلاح:** `onMounted` بيعمل auto-select لو `auth.branches.length === 1`.

---

### 🔴 3. useResortWebSocket: لا يقبل URL reactive
**الملف:** `packages/core/src/composables/useWebSocket.ts`

الـ composable كان يقبل `string` ثابت فقط — يُبنى مرة واحدة في setup time. لو `branchId=null` في تلك اللحظة، كان يبني URL بـ `/ws/alerts/0` أو `ws/kds/0` ويفتح اتصال فاشل.

**الإصلاح:** أُعيدت كتابة الـ composable ليقبل `MaybeRefOrGetter<string | null | undefined>`:
- `null/undefined/''` → لا يفتح أي اتصال، يُغلق الموجود
- تغيير القيمة → يُغلق القديم ويفتح جديد تلقائياً (reactive watch)
- `_closeSocket()` نظيفة: تُلغي handlers، reconnect timer، والـ WebSocket نفسه

---

### 🟡 4. 8 components: branchId ?? 0 أو string ثابت في setup time
**الملفات:**
- `GuestAlertsBell.vue` — `alertsWs(branchId ?? 0)` → 4+ WS failures في الكونسول
- `DiningKDSView.vue` — `kdsWs(branchId ?? 0)`
- `DashboardView.vue` — `kdsWs(branchId ?? 0)`
- `UnifiedPOSView.vue` — `tablesWs(branchId ?? 0)`
- `BeachMapView.vue` — URL ثابت بـ `branchId.value != null ? ... : ''`
- `RoomsView.vue` — URL ثابت بـ `branchId.value`
- `FinanceView.vue` — `shiftsWs(branchId ?? 0)`
- `POSBeachMapWorkspace.vue` — `mapWs(props.branchId ?? '')`

**الإصلاح:** كلهم حُوّلوا لـ `computed(() => branchId.value != null ? ENDPOINTS.xxx(branchId.value) : null)` — يستفيد من الـ composable الجديد.

---

### 🟡 5. GuestAlertsBell: polling toast عند كل فشل
**الملف:** `GuestAlertsBell.vue`

`fetchAlerts()` كانت تعمل `toast.error()` لو فشل الـ polling — يظهر toast كل 20 ثانية للـ super_admin قبل اختيار فرع.

**الإصلاح:** فشل الـ polling صامت — هو fallback وليس مصدر حرج.

---

## الفحوصات

```bash
pnpm --filter el-kheima run type-check  # ✅ نظيف
pnpm --filter el-kheima run test:frontend  # ✅ 103/103
pytest tests/ -p no:randomly  # ✅ 2748 passed, 68 skipped, 0 failed
bash scripts/sync-deploy.sh resort-os el_kheima  # ✅ healthy
```

---

## الحالة الحالية للإنتاج
- commit: `fe0c160` ✅
- `app.elkheima.com` — HTTP 200 ✅
- `el_kheima` container: Up, healthy ✅
- لا migrations — Alembic head: `d1e2f3a4b5c6` (بدون تغيير)
- backend/celery لم يتغيرا

---

## ملاحظة للجلسة القادمة
التغييرات دي تحل freeze الكاشير بعد تغيير الباسورد وتنظف الكونسول من WS errors. لو ظهر أي مشكلة في WS على شاشة معينة، الـ composable الجديد يدعم `.status` ref لعرض حالة الاتصال للمستخدم.
