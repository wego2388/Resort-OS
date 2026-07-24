# مهام UX/Frontend — فرع `feat/pin-setup-ui`

> **الحالة:** قيد التنفيذ — 4 commits مكتملة، المهام أدناه جاهزة للتنفيذ المتسلسل.
> **آخر تحديث:** 2026-07-24
> **الفرع:** `feat/pin-setup-ui` — مبني على `feat/super-admin-panel`
> **Base commit (نقطة البداية):** `b8d078b`

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

## ما اتعمل — 4 Commits مكتملة ✅

| Commit | الوصف | الملفات |
|---|---|---|
| `70be38d` | PIN setup UI — SuperAdminView + ProfileView + OperatorSwitchModal i18n | 6 ملفات |
| `53b7d18` | Dark mode gaps + missing i18n key (16 ملف) | 18 ملف |
| `101af3b` | motion-safe:animate-spin + Spinner a11y (17 ملف) | 17 ملف |
| `b8d078b` | Navigation UX — scroll, transitions, 404, document title | 10 ملفات |

---

## المهام الجاهزة للتنفيذ — مرتبة بالأولوية

---

### ✅ مهمة 1 — `ConfirmDialogContainer` i18n (عالي الأولوية)

**المشكلة:**
`packages/ui/src/components/ConfirmDialogContainer.vue` فيها نصوص fallback
hardcoded عربي (`'تأكيد'` و`'إلغاء'`). لو المستخدم شغّل English، الـ dialog
بيظهر بالعربي — مكسور مع i18n.

**الدليل:**
```
packages/ui/src/components/ConfirmDialogContainer.vue:11
  title ?? 'تأكيد'
  cancelText ?? 'إلغاء'
  confirmText ?? 'تأكيد'
```

**الحل المطلوب:**
- `ConfirmDialogContainer` تستخدم `useI18n` للـ fallbacks
- إضافة keys في `ar.json` و`en.json`:
  ```json
  "confirmDialog": {
    "defaultTitle": "تأكيد",
    "defaultConfirm": "تأكيد",
    "defaultCancel": "إلغاء"
  }
  ```
- نظراً لأن `ConfirmDialogContainer` في `packages/ui` (مش في `el-kheima`)،
  تحقق أولاً إن `vue-i18n` متاح في `packages/ui/package.json`

**الملفات المتوقعة:**
- `packages/ui/src/components/ConfirmDialogContainer.vue`
- `packages/core/src/i18n/locales/ar.json`
- `packages/core/src/i18n/locales/en.json`

**القبول:**
- المستخدم English: الـ dialog fallback يعرض "Confirm" و"Cancel"
- المستخدم Arabic: يعرض "تأكيد" و"إلغاء"
- type-check ✓ build ✓

---

### ✅ مهمة 2 — `ConfirmDialogContainer` accessibility (عالي الأولوية)

**المشكلة:**
الـ modal مفيهاش `aria-describedby` — screen readers مش بتقرأ الـ message تلقائيًا.

**الدليل:**
```
packages/ui/src/components/ConfirmDialogContainer.vue:11-20
  <AppModal> → الـ message paragraph مش مرتبط بالـ dialog
```

**الحل المطلوب:**
- إضافة `id="confirm-dialog-desc"` على الـ `<p>` اللي فيها الـ message
- تمرير `aria-describedby="confirm-dialog-desc"` للـ `AppModal`
- تحقق إن `AppModal` بتمرر `aria-describedby` للـ dialog element الداخلي

**الملفات المتوقعة:**
- `packages/ui/src/components/ConfirmDialogContainer.vue`
- `packages/ui/src/components/Modal.vue` (إذا احتاجت تعديل)

**القبول:**
- `aria-describedby` موجود ومربوط صح
- type-check ✓ build ✓

---

### ✅ مهمة 3 — إصلاح `size: 100` truncation warning (متوسط الأولوية)

**المشكلة:**
كثير من الـ views بتجيب البيانات بـ `size: 100` أو `size: 200` ثابتة. لو
الـ total أكبر — المستخدم مش بيعرف. مثال: SuperAdminView بتجيب 100 مستخدم بس.

**الدليل:**
```
SuperAdminView.vue:83   params: { page: 1, size: 100 }
SuperAdminView.vue:231  params: { page: 1, size: 200 }
HRView.vue:139          params: { size: 100 }
CRMView.vue:310,320,329 params: { size: 100 }
HubManagementView.vue:119,130 params: { size: 100 }
```

**الحل المطلوب:**
- في كل مكان بيرجع `PaginatedResponse`، تحقق من `total` في الـ response
- لو `total > items.length`، اعرض رسالة تحذيرية بسيطة:
  `"يعرض {n} من أصل {total} — استخدم البحث لتصفية النتائج"`
- مش محتاج pagination كاملة — مجرد warning واضح

**الـ views المتأثرة:**
- `SuperAdminView.vue` (users list + perms users)
- `HRView.vue` (employees)
- `CRMView.vue` (opportunities, activities, campaigns)
- `HubManagementView.vue` (offers, pages)

**i18n keys:**
```json
"common": {
  "showingOf": "يعرض {shown} من أصل {total}",
  "useSearchToFilter": "استخدم البحث لتصفية النتائج"
}
```

**القبول:**
- لو total > items.length → رسالة تحذيرية تظهر تحت الـ list
- لو total <= items.length → لا رسالة
- type-check ✓ build ✓

---

### ✅ مهمة 4 — PWA manifest lang ديناميكي (منخفض الأولوية)

**المشكلة:**
```
apps/el-kheima/vite.config.ts
  manifest: { lang: 'ar', dir: 'rtl' }   ← ثابتة
```
لو المستخدم English، اسم الـ PWA المثبّت وصفحة البداية فاضلين عربي.

**الحل المطلوب:**
- إضافة `shortcuts` array في الـ manifest للـ PWA — بيوفر quick actions من home screen
- مش ممكن تغيير `lang` ديناميكيًا في manifest (ده limitation في PWA spec)
- الـ workaround العملي: إضافة `name_localized` بالـ translations المتاحة
- الحل البسيط: تغيير `name` من `'Resort OS'` لـ `'Resort OS — El Kheima'` (اسم neutral)
- إضافة `lang: 'ar-EG'` بدل `'ar'` (أكثر دقة)

**الملفات المتوقعة:**
- `apps/el-kheima/vite.config.ts`

**القبول:**
- `pnpm build:all` ✓ (بدون errors)

---

### ✅ مهمة 5 — `document.title` مع اللغة (منخفض الأولوية)

**المشكلة:**
`App.vue` بتستخدم `route.meta.title` الـ static العربي حتى لو المستخدم شغّل
English. المهمة دي تحتاج نقل كل الـ static titles لـ titleKey.

**الدليل:**
```
router/index.ts:
  { path: 'hr', meta: { title: 'الموارد البشرية' } }  ← hardcoded عربي
  { path: 'finance', meta: { title: 'المالية' } }      ← hardcoded عربي
```

**الحل المطلوب:**
- إضافة i18n keys `backoffice.nav.*` لكل الـ route titles (موجودة أصلاً في ar.json/en.json!)
- تحويل كل `meta: { title: '...' }` لـ `meta: { titleKey: 'backoffice.nav.X' }`
- فحص إن كل الـ nav keys موجودة بالفعل في الـ locales

**الملفات المتوقعة:**
- `apps/el-kheima/src/router/index.ts`

**i18n keys موجودة بالفعل:**
```
backoffice.nav.hr, backoffice.nav.finance, backoffice.nav.dashboard
backoffice.nav.analytics, backoffice.nav.crm, backoffice.nav.maintenance
... إلخ (موجودة في ar.json/en.json)
```

**القبول:**
- Browser tab بيعرض الاسم بالإنجليزي لو المستخدم EN
- type-check ✓

---

### ✅ مهمة 6 — `useSmartBack` في `SessionsView` — back button بالأعلى (تحسين بسيط)

**المشكلة:**
`SessionsView` (`/account/sessions`) هي standalone page (خارج BackOfficeLayout)
والزر "رجوع" موجود في أسفل الصفحة — المستخدم لازم يسكرول للأسفل يلاقيه.

**الحل المطلوب:**
- نقل/إضافة زر رجوع واضح في أعلى الصفحة (topbar أو header القسم)
- نفس الـ `useSmartBack('/portal/profile')` الموجودة

**الملفات المتوقعة:**
- `apps/el-kheima/src/views/account/SessionsView.vue`

**القبول:**
- زر "← رجوع" ظاهر في أعلى الصفحة بدون سكرول
- type-check ✓

---

## طريقة الشغل الصحيحة — خطوة بخطوة

### 1. ابدأ المهمة

```bash
cd /home/wego/projects/resort-os
git status --short --branch
# تأكد: feat/pin-setup-ui
git rev-parse --short HEAD
```

### 2. اقرأ الملفات المتأثرة أولاً

قبل أي تعديل، اقرأ:
- الملف المستهدف كاملاً
- الملفات المرتبطة (أي composable أو component بيستخدمه)
- الـ i18n keys الموجودة في `ar.json` و`en.json`

### 3. نفّذ التعديل

- عدّل الملفات بدقة (بدون تغيير غير مطلوب)
- الـ i18n: دايمًا ar.json و en.json معًا
- Dark mode: كل `bg-white` لازم `dark:bg-surface`، كل `text-gray-900` لازم `dark:text-gray-100`

### 4. تحقق

```bash
cd /home/wego/projects/resort-os/frontend
pnpm run type-check:all
pnpm run build:all
```

كلاهما لازم يخرجوا `Done` بدون errors قبل ما تكمّل.

### 5. فحص i18n

```bash
cd /home/wego/projects/resort-os/frontend
python3 << 'EOF'
import re, os, json

used = set()
for dirpath, _, files in os.walk('apps/el-kheima/src'):
    for fn in files:
        if not (fn.endswith('.vue') or fn.endswith('.ts')): continue
        with open(os.path.join(dirpath, fn)) as f:
            content = f.read()
        used.update(re.findall(r"t\('(backoffice\.[^']+)'\)", content))

def flatten(d, prefix=''):
    r = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict): r.update(flatten(v, key))
        else: r[key] = v
    return r

with open('packages/core/src/i18n/locales/ar.json') as f:
    flat = flatten(json.load(f))

missing = [k for k in sorted(used) if '*' not in k and k not in flat]
print(f"Missing keys: {len(missing)}")
for k in missing: print(f"  {k}")
EOF
```

نتيجة متوقعة: `Missing keys: 0`

### 6. Stage وأبلّغ

```bash
git diff --check
git status --short
# stage الملفات المعدّلة بالاسم:
git add frontend/path/to/file1 frontend/path/to/file2
```

**لا تعمل commit — بلّغ Mohamed بالنتائج وانتظر الإذن.**

---

## Template للـ Handoff Report

بعد كل مهمة، أرسل للـ owner:

```
## مهمة [رقم] — [اسمها] ✅

**الملفات المعدّلة:**
- `path/to/file1` — وصف التغيير
- `path/to/file2` — وصف التغيير

**التحقق:**
- pnpm type-check:all: ✅ Done
- pnpm build:all: ✅ Done
- i18n check: ✅ 0 missing keys
- ar/en symmetry: ✅ متطابقين

**التغييرات:**
- [ما اتغير فعلاً وليه]

**ما اتأجّل ومبررات:**
- [أي شيء مش في scope هذه المهمة]

**مخاطر متبقية:**
- [أي حاجة لازم Mohamed يعرفها]

**الملفات جاهزة للـ staging:**
git add [الملفات]
```

---

## طريقة الـ Push الآمنة (بإذن Mohamed فقط)

```bash
# 1. تأكد إن كل المهام المتفق عليها اتنفذت واتـ commit
git log --oneline feat/pin-setup-ui | head -10

# 2. تحقق إن مفيش worktree conflicts
git worktree list

# 3. fetch أولاً وشوف الفرق
git fetch origin
git log --left-right --oneline HEAD...origin/feat/pin-setup-ui 2>/dev/null || echo "فرع جديد"

# 4. Push
git push -u origin feat/pin-setup-ui

# 5. على الـ VPS (مفيش migrations جديدة في هذا الفرع)
# bash scripts/deploy.sh
```

**تحذير deploy:** الفرع ده frontend-only — مفيش migrations. `deploy.sh` بيعمل
`alembic upgrade head` تلقائيًا وهو safe لأنه idempotent لو مفيش migrations جديدة.

---

## Context سريع للـ Agent الجديد

```
المشروع:   El Kheima Beach Resort OS
Stack:     FastAPI + PostgreSQL + Vue 3 + TypeScript + pnpm monorepo
Frontend:  frontend/apps/el-kheima (staff app, port 3001)
i18n:      packages/core/src/i18n/locales/{ar,en}.json
UI:        packages/ui/src/components/
Router:    apps/el-kheima/src/router/index.ts
Layouts:   BackOfficeLayout, FieldLayout, KioskLayout
AGENTS.md: قواعد كل الـ agents — اقرأه أولاً
CLAUDE.md: الميثاق الهندسي الكامل — اقرأه بعد AGENTS.md
wagdy.md:  الحالة الحالية للمشروع بالعربي
```

**أهم القواعد:**

1. اقرأ AGENTS.md و CLAUDE.md قبل أي شيء
2. Frontend-only: لا تلمس الـ backend
3. كل تغيير i18n → ar.json وen.json معًا
4. Dark mode: كل class ضوئي لازم dark counterpart
5. بعد كل تعديل: `pnpm type-check:all && pnpm build:all`
6. لا commit — بلّغ Mohamed وانتظر الإذن
