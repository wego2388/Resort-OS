# مهام UX/Frontend — فرع `feat/pin-setup-ui`

> **الحالة:** ✅ المهام الـ 6 + إصلاحات إضافية منفّذة في الكود — تنتظر إذن Mohamed للـ commit.
> **آخر تحديث:** 2026-07-24
> **الفرع:** `feat/pin-setup-ui` — مبني على `feat/super-admin-panel`
> **آخر commit:** `ada3168`

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
# المهام الـ 6 الأصلية (commit ada3168 — مدفوعة للـ VPS بالفعل)
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

# الإصلاحات الإضافية (جلسة 2026-07-24 — لم تُدمج بعد)
git add \
  frontend/apps/el-kheima/index.html \
  frontend/apps/el-kheima/src/composables/index.ts \
  frontend/apps/el-kheima/src/components/OperatorSwitchModal.vue \
  frontend/apps/el-kheima/src/views/admin/SuperAdminView.vue \
  frontend/apps/el-kheima/src/views/kds/DiningKDSView.vue
```

---

## النواقص والمشاكل المتبقية — مرتبة بالخطورة

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### ✅ مُصلَحة في جلسة 2026-07-24

**beach/services.py — FolioCharge bare except** — ✅ مُصلَح بالفعل في الكود الحالي
(الـ `except Exception: pass` اتبدّل بـ `except Exception: db.rollback(); raise`
في commit سابق — الفجوة محلولة).

**DashboardView — error boundary** — ✅ `fetchDailyStats` و`fetchLiveRevenueToday`
بيشتغلوا داخل `Promise.allSettled` مع `.status === 'fulfilled'` checks، والـ outer
`try/catch` في `fetchDashboard` موجود ويعرض `loadError` banner للمستخدم.

**Google Fonts — font-display** — ✅ `display=swap` مضمّن في الـ URL (كان موجود
في public، أُضيف تعليق توضيحي لـ el-kheima). الـ `system-ui` fallback موجود
في `tailwind.config.js`. TODO Gate 9: self-host Cairo كـ woff2.

**KDSView — loading indicator** — ✅ أُضيف `initialLoading` ref + skeleton cards
(6 بطاقات animate-pulse) تظهر فقط على الـ initial fetch وتختفي بعده.

**composables/index.ts** — ✅ أُنشئ الملف ويصدّر `useSmartBack` و`useStaffLocaleSync`.

**OperatorSwitchModal + SuperAdminView — dark mode contrast** — ✅ أُصلح:
- `dark:text-gray-500` → `dark:text-gray-300/400` في الملفين
- Pale surfaces بدون dark variants في SuperAdminView (red, amber, blue) أُصلحت
- **70/70 frontend tests pass** بعد الإصلاح

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 🟡 مشاكل متوسطة متبقية

**1. OperatorSwitchModal / ShiftPanel — props غير typed**

`ShiftPanel` فيها `defineEmits` بس مفيش `defineProps<{...}>()` typed — TypeScript
ممكن يفوّت errors.

**2. 52 endpoint بدون `response_model`**

أهمهم:
- `GET /beach/live-dashboard` → dashboard data بدون typing
- `POST /beach/transactions/{id}/void` → action بدون confirmed schema
- `GET /beach/eod-report` → PDF/data بدون schema (مقبول للـ binary)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 🟢 تحسينات غير حرجة

**3. `any` types كثيرة في كبار الـ views**

```
CRMView.vue:       16 × any
TimeshareView.vue: 14 × any
FinanceView.vue:   14 × any
DiningMenuView.vue:13 × any
HRView.vue:        11 × any
```

مش bugs — بس بتضعّف الـ type safety.

**4. Backend: bare `except Exception: pass` في ~14 مكان متبقي**

معظمها مبرر (swallow notification errors مثل WhatsApp/SMS) — مش خطر مالي.
FolioCharge اتصلح بالفعل (↑).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## الأولوية المقترحة للخطوة القادمة

| # | المشكلة | الملفات | الخطر |
|---|---|---|---|
| 1 | ShiftPanel props غير typed | frontend | 🟡 type safety |
| 2 | 52 endpoint بدون `response_model` | backend | 🟢 type safety |
| 3 | Google Fonts self-host (Gate 9) | `index.html` + `/public/fonts/` | 🟢 reliability |
| 4 | `any` types في CRM/Finance/HR/Timeshare | frontend | 🟢 DX |

## ملخص ما اتعمل

### commit ada3168 (مدفوع للـ VPS ✅)
المهام الـ 6 الأصلية:
- ConfirmDialog i18n + a11y
- Truncation warning في 7 قوائم
- PWA manifest lang → ar-EG
- document.title مع اللغة
- Back button في SessionsView

### جلسة 2026-07-24 — إصلاحات إضافية (staged، تنتظر commit)
- `index.html` — تعليق font-display توضيحي
- `composables/index.ts` — ملف جديد يصدّر useSmartBack + useStaffLocaleSync
- `OperatorSwitchModal.vue` — إصلاح dark:text-gray-500 → dark:text-gray-300
- `SuperAdminView.vue` — إصلاح dark:text-gray-500 + pale surfaces بدون dark variants
- `DiningKDSView.vue` — إضافة initialLoading skeleton للـ initial fetch
- **النتيجة:** 70/70 frontend tests ✅ | type-check ✅ | build ✅ | agent-check ✅
