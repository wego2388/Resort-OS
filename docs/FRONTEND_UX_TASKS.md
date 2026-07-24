# مهام UX/Frontend — فرع `feat/pin-setup-ui`

> **الحالة:** ✅ المهام الـ 6 منفّذة في الكود — تنتظر إذن Mohamed للـ commit.
> **آخر تحديث:** 2026-07-24
> **الفرع:** `feat/pin-setup-ui` — مبني على `feat/super-admin-panel`
> **آخر commit:** `b5c07a2` (docs handoff)

---

## قبل أي شغل — الـ Checklist الإلزامي

```bash
# 1. تأكد أنك في الفرع الصح
cd /home/wego/projects/resort-os
git status --short --branch
git branch --show-current          # يجب يكون: feat/pin-setup-ui
git rev-parse --short HEAD         # تحقق من آخر commit

# 2. تحقق من البيئة
bash scripts/agent-check.sh

# 3. قبل أي تعديل — type-check وبناء أخضر
cd frontend && pnpm run type-check:all && pnpm run build:all

# 4. بعد كل مهمة — نفس الأمرين
pnpm run type-check:all && pnpm run build:all
```

**قواعد ثابتة:**
- لا `git add .` — stage الملفات المعدّلة بالاسم صراحةً
- لا commit إلا بعد إذن صريح من Mohamed
- لا push إلا بعد إذن صريح من Mohamed
- إذا فشل type-check أو build — لا تكمل، افهم السبب أولاً

---

## ما اتعمل — 5 Commits مكتملة ✅

| Commit | الوصف | الملفات |
|---|---|---|
| `70be38d` | PIN setup UI — SuperAdminView + ProfileView + OperatorSwitchModal i18n | 6 ملفات |
| `53b7d18` | Dark mode gaps + missing i18n key (16 ملف) | 18 ملف |
| `101af3b` | motion-safe:animate-spin + Spinner a11y (17 ملف) | 17 ملف |
| `b8d078b` | Navigation UX — scroll, transitions, 404, document title | 10 ملفات |
| `b5c07a2` | docs: FRONTEND_UX_TASKS agent handoff | 1 ملف (docs فقط) |

---

## المهام — حالة التنفيذ

> **تحديث 2026-07-24:** المهام الـ 6 اتنفّذت في الكود لكن **لم تُضَم لـ commit بعد** — الملفات staged وجاهزة لإذن Mohamed.

---

### ✅ مهمة 1 — `ConfirmDialogContainer` i18n — **منفّذة ✓**

**ما اتعمل:**
- `ConfirmDialogContainer.vue` — props اختيارية (`defaultTitle`, `defaultConfirmText`, `defaultCancelText`)
- `ar.json` + `en.json` — أُضيفت keys `confirmDialog.defaultTitle/defaultConfirm/defaultCancel`
- `App.vue` — بيمرر الترجمات عبر computed تتغير مع اللغة

---

### ✅ مهمة 2 — `ConfirmDialogContainer` accessibility — **منفّذة ✓**

**ما اتعمل:**
- `aria-describedby` مربوط بالـ message paragraph
- `Modal.vue` بتمرر الـ prop للـ dialog element

---

### ✅ مهمة 3 — `size: 100` truncation warning — **منفّذة ✓**

**ما اتعمل:**
- `SuperAdminView`, `HRView`, `CRMView` (3 lists), `HubManagementView` (2 lists) — كلهم بيعرضوا تحذير أصفر لو `total > items.length`
- `ar.json` + `en.json` — keys `common.showingOf` و`common.useSearchToFilter` مضافة

---

### ✅ مهمة 4 — PWA manifest lang — **منفّذة ✓**

**ما اتعمل:**
- `vite.config.ts` — `lang: 'ar-EG'` بدل `'ar'`، `name: 'Resort OS — El Kheima'` (neutral)

---

### ✅ مهمة 5 — `document.title` مع اللغة — **منفّذة ✓**

**ما اتعمل:**
- `router/index.ts` — كل routes تحولت من `meta: { title: 'نص عربي' }` لـ `meta: { titleKey: 'backoffice.nav.X' }`
- `App.vue` بتقرأ `titleKey` وتترجمه مع تغيير اللغة

---

### ✅ مهمة 6 — Back button في `SessionsView` بالأعلى — **منفّذة ✓**

**ما اتعمل:**
- `SessionsView.vue` — زر رجوع (مع SVG arrow) في أعلى الصفحة مباشرة، بجانب `LanguageSwitcher`، مرئي بدون scroll

---

## الملفات المعدّلة — جاهزة للـ Staging (بإذن Mohamed)

```bash
git add \
  frontend/apps/el-kheima/src/App.vue \
  frontend/apps/el-kheima/src/router/index.ts \
  frontend/apps/el-kheima/src/views/account/SessionsView.vue \
  frontend/apps/el-kheima/src/views/admin/CRMView.vue \
  frontend/apps/el-kheima/src/views/admin/HRView.vue \
  frontend/apps/el-kheima/src/views/admin/HubManagementView.vue \
  frontend/apps/el-kheima/src/views/admin/SuperAdminView.vue \
  frontend/apps/el-kheima/vite.config.ts \
  frontend/packages/core/src/i18n/locales/ar.json \
  frontend/packages/core/src/i18n/locales/en.json \
  frontend/packages/ui/src/components/ConfirmDialogContainer.vue \
  frontend/packages/ui/src/components/Modal.vue
```

---

## النواقص والمشاكل المتبقية — مرتبة بالخطورة

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 🔴 خطر فعلي — محتاج قرار

**1. DashboardView — API calls بدون try/catch**

`fetchDailyStats` و`fetchLiveRevenueToday` مش محاطتين بـ try/catch منفصل — لو
`analytics.dailyStats` أو `analytics.revenue` رجعوا error، الـ exception بيطلع
خارج الـ `Promise.allSettled` الموجودة وبيوقع الـ view بصمت.

المتأثر:
```
DashboardView.vue (fetchDailyStats + fetchLiveRevenueToday)
```

**2. beach/services.py — `except Exception: pass` على FolioCharge**

بيع شاطئ محمّل على غرفة ممكن "ينجح" ويتسجّل بدون FolioCharge حقيقي لو الفوليو
مقفول. خطر مالي مباشر — الدفع يحصل بدون تسجيل.

**3. Google Fonts external dependency في production**

```
apps/el-kheima/index.html → fonts.googleapis.com
```
لو الـ VPS مش عنده internet أو Google blocked — الخط مش بيتحمّل وكل الـ app
بيبان بخط system fallback. محتاج self-host أو `font-display: swap` على الأقل.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 🟡 مشاكل متوسطة

**4. KDSView — مفيش loading indicator**

الشاشة بتعمل fetch على mount وبتعمل poll كل 15 ثانية بدون أي visual feedback
للـ initial load. لو الـ kitchen network بطيء — الشاشة فاضية بدون سبب.

**5. OperatorSwitchModal / ShiftPanel — props غير typed**

`ShiftPanel` فيها `defineEmits` بس مفيش `defineProps<{...}>()` typed — TypeScript
ممكن يفوّت errors.

**6. 52 endpoint بدون `response_model`**

أهمهم:
- `GET /beach/live-dashboard` → dashboard data بدون typing
- `POST /beach/transactions/{id}/void` → action بدون confirmed schema
- `GET /beach/eod-report` → PDF/data بدون schema (مقبول للـ binary)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 🟢 تحسينات غير حرجة

**7. `composables/index.ts` مش موجود**

`useSmartBack` مش exported من الـ index — أي view محتاجها بتعمل direct import.

**8. `any` types كثيرة في كبار الـ views**

```
CRMView.vue:       16 × any
TimeshareView.vue: 14 × any
FinanceView.vue:   14 × any
DiningMenuView.vue:13 × any
HRView.vue:        11 × any
```

مش bugs — بس بتضعّف الـ type safety.

**9. Backend: bare `except Exception` في 15 مكان**

معظمها مبرر (swallow notification errors)، لكن الـ FolioCharge في `beach/services.py`
خطر فعلي (بند 2 أعلاه).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## الأولوية المقترحة للخطوة القادمة

| # | المشكلة | الملفات | الخطر |
|---|---|---|---|
| 1 | `beach/services.py` FolioCharge bare except | backend | 🔴 مالي |
| 2 | `DashboardView` fetchDailyStats/fetchLiveRevenue بدون error boundary | frontend | 🔴 UX كسر |
| 3 | Google Fonts external في production | `index.html` | 🟡 reliability |
| 4 | KDSView loading state ناقص | frontend | 🟡 UX |
| 5 | `composables/index.ts` ناقص | frontend | 🟢 DX |
| 6 | 52 endpoint بدون `response_model` | backend | 🟢 type safety |
