# MASTER TODO — Resort OS Frontend
> **تاريخ الفحص:** 2026-07-15 | **المنهجية:** قراءة مباشرة لكل ملف فرونت إند
> **القاعدة:** كل مهمة تُنجز مرة واحدة فقط — مرتبة بحيث كل مهمة تبني على السابقة
> **التقدّم:** ✅ منجز | 🔄 جاري | ⬜ لم يبدأ

---

## 🏗️ المرحلة 0 — أساسيات يجب أن تسبق أي شيء

> هذه المهام تؤثر على كل شاشة. أنجزها أولاً حتى لا تُعيد العمل لاحقاً.

### 0-A: Dark Mode — تفعيل حقيقي في الـ Layout
**الملف:** `frontend/apps/el-kheima/src/layouts/BackOfficeLayout.vue`
**المشكلة:** الـ sidebar والـ topbar مبنيان بـ `style=""` hard-coded hex colors — الـ dark mode لن يُرى أبداً حتى لو فُعِّل.
**المطلوب:**
- [x] استبدل `style="background:#111827"` بـ `class="bg-gray-900 dark:bg-gray-950"`
- [x] استبدل `style="background:#C9963C"` بـ `class="bg-gold-DEFAULT"`
- [x] استبدل `style="color:#6B7280"` بـ `class="text-gray-500 dark:text-gray-400"`
- [x] استبدل `style="color:#F87171"` بـ `class="text-red-400"`
- [x] استبدل hard-coded `border rgba(255,255,255,0.08)` بـ `border-white/10`
- [x] الـ active nav item: `style="background:#C9963C; color:#fff"` → `class="bg-gold-DEFAULT text-white"`
- [x] الـ inactive nav item: `style="color:#D1D5DB"` → `class="text-gray-300"`
- [x] Topbar: أضف `dark:bg-gray-900 dark:border-gray-700`
- [x] Main area: أضف `dark:bg-gray-950`
- [x] أضف `<ThemeToggle />` في الـ topbar بجنب `<LanguageSwitcher />`

### 0-B: Dark Mode — Card + inputClasses
- [x] `Card.vue`: `bg-white` → `bg-white dark:bg-surface` + border + title dark variants
- [x] `inputClasses.ts`: error state أضف `dark:bg-red-900/20` + border → `dark:border-border`
- [x] Scrollbar: `background: #C9963C` → `background: rgb(var(--color-secondary))` (في base.css)
- [x] `.section-title` أضف `dark:text-gray-100`
- [x] `.data-table th/td` أضف dark variants

### 0-C: نقل CSS المشترك لمكان واحد
- [x] أنشئ `frontend/packages/ui/src/styles/base.css`
- [x] انقل `@layer components` من كلا الـ `main.css` للملف الجديد
- [x] `el-kheima/main.css` → `@import '@resort-os/ui/src/styles/base.css'`
- [x] `public/main.css` → `@import '@resort-os/ui/src/styles/base.css'`

---

## 🍽️ المرحلة 1 — POS الطاولات والمطعم (أعلى أولوية تشغيلية)

> هذه هي قلب الطلب — "أحسن من خريطة الشاطئ وذكية"

### 1-A: Backend — إضافة بيانات الطاولة النشطة في API Response
**الملف:** `backend/app/modules/dining/api/router.py` + `schemas.py`
**المطلوب:** `GET /dining/outlets/{id}/tables` يُرجع لكل طاولة:
```python
active_order_id: int | None
active_order_number: str | None
active_order_total: float | None
active_covers: int | None
occupied_since: datetime | None  # وقت أول أوردر على الطاولة
order_status: str | None  # open / in_kitchen / served
```
- [x] أضف هذه الحقول لـ `VenueTableRead` schema
- [x] في `crud.get_tables()`: JOIN مع `DiningOrder` لجلب الأوردر النشط (status IN ['open','in_kitchen','served'])

### 1-B: Frontend — خريطة الطاولات الذكية (الجزء الأكبر)
**الملف:** `frontend/apps/el-kheima/src/views/pos/UnifiedPOSView.vue`
**المطلوب:**

**أولاً — تحديث Interface:**
- [x] أضف للـ `VenueTable` interface: `active_order_id`, `active_order_number`, `active_order_total`, `active_covers`, `occupied_since`, `order_status`

**ثانياً — Summary Bar للطاولات (فوق الخريطة):**
- [x] أضف `computed` يحسب: إجمالي / فاضي / مشغول / في انتظار الدفع (served) / محجوز
- [x] أضف bar بصري: `🟢 فاضي: 8 | 🔴 مشغول: 12 | 🟠 انتظار دفع: 3 | 🔵 محجوز: 1`

**ثالثاً — بطاقة الطاولة الجديدة (بدل الزر الصغير):**
```
الحجم الجديد: min-w-[110px] min-h-[90px]
الألوان:
  available  → bg-green-50  border-green-400
  occupied   → bg-red-50    border-red-400    ring-2 ring-red-200
  served     → bg-amber-50  border-amber-400  (انتظار الدفع)
  reserved   → bg-blue-50   border-blue-400
  out_of_service → bg-gray-100 border-gray-300 opacity-50

المحتوى:
  السطر 1: رقم الطاولة (كبير + bold)
  السطر 2: 👥 {active_covers} ضيوف (لو مشغولة)
  السطر 3: 💰 {active_order_total} ج (لو مشغولة)
  السطر 4: ⏱️ {وقت منذ occupied_since} (لو مشغولة)
  السطر 5: حالة نصية ملونة صغيرة
```
- [x] نفّذ البطاقة الجديدة

**رابعاً — Tap على طاولة مشغولة:**
- [x] بدل `selectedTableId = t.id`، لو `t.status === 'occupied' && t.active_order_id` → افتح `DiningOrderDetailModal` بـ `t.active_order_id`
- [x] لو `t.status === 'served' && t.active_order_id` → نفس الشيء (الأوردر محتاج دفع)
- [x] لو `t.status === 'available'` → اختر الطاولة لأوردر جديد (كما هو الآن)

**خامساً — فلتر الطلبات الجارية بالطاولة:**
- [x] في modal "الطلبات الجارية": لو طاولة محددة، أضف زر "طاولة {رقم} فقط" للفلترة

### 1-C: WebSocket للطاولات (تحديثات لحظية)
**الملفات:**
- `backend/app/modules/dining/api/router.py` (WS endpoint جديد أو تعديل موجود)
- `frontend/apps/el-kheima/src/views/pos/UnifiedPOSView.vue`

**المطلوب:**
- [x] الباك إند: عند تغيير حالة أي طاولة (أوردر جديد/إغلاق/دفع) → broadcast `{"type": "tables_updated"}` على WS
- [x] الفرونت إند: `useResortWebSocket` للاستماع لـ `tables_updated` → `loadOutletData()` (إعادة تحميل الطاولات)
- [x] أضف indicator صغير في الـ UI يُظهر حالة الاتصال (مثل KDS)

### 1-D: رقم الطاولة في KDS
**الملف:** `frontend/apps/el-kheima/src/views/kds/DiningKDSView.vue`
**المطلوب:**
- [x] أضف `table_number: string | null` و `order_type: string` لـ `Ticket` interface
- [x] في الباك إند `DiningKitchenTicket` response: أضف `table_number` و `order_type`
- [x] في بطاقة KDS: أضف `طاولة {table_number}` أو `{order_type_label}` تحت رقم الأوردر
- [x] أضف `outlet_name` صغيرة في الكورنر العلوي للتذكرة (لو أكثر من منفذ)

### 1-E: ملاحظات الأوردر في KDS
**الملف:** `frontend/apps/el-kheima/src/views/kds/DiningKDSView.vue`
**المطلوب:**
- [x] أضف `order_notes: string | null` لـ `Ticket` interface
- [x] في الباك إند response: أضف `notes` من `DiningOrder.notes`
- [x] في بطاقة KDS: لو `order_notes` موجودة → `⚠️ ملاحظة: {order_notes}` بلون أصفر تحت header التذكرة

---

## 🔐 المرحلة 2 — أمان وثبات (لا يظهر للمستخدم لكن حيوي)

### 2-A: T-01 — localStorage → httpOnly Cookie
**الملف:** `frontend/packages/core/src/stores/auth.ts`
**المشكلة:** JWT token في localStorage = قابل للسرقة بأي XSS
**المطلوب:**
- [x] راجع `auth.ts` واستبدل `localStorage.getItem('access_token')` بالاعتماد على cookie من الـ backend
- [x] تأكد أن `initAuth()` يستخدم `POST /auth/refresh` بدل قراءة token من localStorage
- [x] في `backend/app/core/deps.py` + auth router: تأكد `httponly=True, samesite='lax'` على الـ cookie

### 2-B: branch_id من auth store بدل localStorage
**المشكلة:** كل ملف في المشروع يكرر `parseInt(localStorage.getItem('branch_id') ?? '1')` — هذا غير موثوق
**المطلوب:**
- [x] في `packages/core/src/stores/auth.ts`: أضف `branchId` كـ computed من الـ user payload
- [x] ابحث عن كل `localStorage.getItem('branch_id')` في المشروع واستبدلها بـ `auth.branchId`
- [x] الملفات المتأثرة: كل الـ views (20+ ملف)

---

## 📊 المرحلة 3 — تكميل الشاشات الناقصة

### 3-A: Dashboard — Real-time Analytics WebSocket (R-01)
**الملف:** `frontend/apps/el-kheima/src/views/admin/DashboardView.vue`
**المشكلة:** الباك إند عنده WS endpoint جاهز — الفرونت مش بيستخدمه، الـ KPIs ثابتة حتى الـ refresh
**المطلوب:**
- [x] أضف `useResortWebSocket` للـ dashboard
- [x] عند وصول event → أعد تحميل `fetchDailyStats`
- [x] أضف مؤشر "آخر تحديث: قبل X ثانية"

### 3-B: Loyalty Points C-01
**الملفات:** جديدة
**المطلوب:**
- [x] تأكد وجود backend endpoints في `app/modules/crm` لـ loyalty points (راجع wagdy.md C-01)
- [x] أضف tab "نقاط الولاء" في `CRMView.vue`
- [x] عرض نقاط العميل + سجل النقاط + استرداد النقاط
- [x] في `UnifiedPOSView.vue`: زرار "استرداد نقاط" في الـ cart sidebar

### 3-C: Merge Tables P-08
**الملفات:**
- `backend/app/modules/dining/api/router.py`
- `frontend/apps/el-kheima/src/views/pos/UnifiedPOSView.vue`

**المطلوب:**
- [x] تأكد وجود `POST /dining/orders/{id}/merge` endpoint في الباك إند
- [x] في `DiningOrderDetailModal.vue`: أضف زرار "دمج مع طاولة" (يظهر فقط لـ waiter+ على أوردر `dine_in`)
- [x] Modal صغير: اختر الطاولة الهدف → تأكيد → API call

### 3-D: AnalyticsView — Revenue Comparison R-02
**الملف:** `frontend/apps/el-kheima/src/views/admin/AnalyticsView.vue`
**المشكلة:** tab "الإيرادات" موجود لكن المقارنة (هذا الشهر vs الشهر الماضي) ناقصة
**المطلوب:**
- [x] أضف مقارنة شهر بشهر في tab "الإيرادات"
- [x] استخدم `ChartWrapper` مع نوع `line` لعرض الاتجاه

---

## 🎨 المرحلة 4 — اللمسة الأخيرة والتنظيم

### 4-A: ThemeToggle في كل الـ Layouts
**الملفات:**
- `frontend/apps/el-kheima/src/layouts/BackOfficeLayout.vue` ← الأهم (بعد 0-A)
- `frontend/apps/el-kheima/src/layouts/FieldLayout.vue`
- `frontend/apps/el-kheima/src/layouts/KioskLayout.vue`

**المطلوب:**
- [x] BackOfficeLayout: أضف `<ThemeToggle />` في topbar (بعد إنجاز 0-A)
- [x] FieldLayout: أضف `<ThemeToggle />` لو مناسب
- [x] KioskLayout: KDS screen — تفضل داكنة دائماً (intentional)، لا تضف toggle

### 4-B: console.error → toast.error في الشاشات
**الملفات:** `HRView.vue`, `TimeshareView.vue`, `CRMView.vue`
**المطلوب:**
- [x] `HRView.vue`: ابحث عن كل `console.error` (17 مكان) واستبدلها بـ `toast.error(...)` مع رسالة مفيدة
- [x] `TimeshareView.vue`: نفس الشيء (5 مكان)
- [x] `CRMView.vue`: نفس الشيء
- [x] `BookingsView.vue`, `HousekeepingView.vue`, `RoomsView.vue`: نفس الشيء
- [x] `FinanceView.vue`, `LeavesView.vue`, `AttendanceView.vue`, `ProfileView.vue`, `PayrollView.vue`: نفس الشيء
- [x] `BeachMapView.vue`, `BeachPOSView.vue`, `GuestAlertsBell.vue`: نفس الشيء

### 4-C: LoginView — Dark Mode Support
**الملف:** `frontend/apps/el-kheima/src/views/account/LoginView.vue`
**المطلوب:**
- [x] الـ login page استخدمت `LoginView.vue` من `packages/ui/src/views/LoginView.vue`
- [x] تأكد أن `LoginView.vue` في الـ package يدعم dark mode (`dark:bg-background dark:text-gray-100`)

### 4-D: Menu Item Image Upload (T-05)
**الملفات:**
- `backend/app/modules/dining/api/router.py`
- `frontend/apps/el-kheima/src/views/admin/DiningMenuView.vue`

**المطلوب:**
- [x] الباك إند: `POST /dining/items/{id}/image` endpoint (file upload)
- [x] الفرونت إند: أضف زرار "رفع صورة" في Drawer تعديل الصنف
- [x] في `filteredItems` grid في POS: اعرض الصورة لو موجودة

### 4-E: تنظيف Color System
**المطلوب (تدريجي، لا تكسر الموجود):**
- [ ] في أي كود جديد: استخدم فقط `bg-primary-*` / `bg-secondary` / `bg-danger` إلخ — لا hex مباشر
- [x] `public/tailwind.config.js`: `brand.*` colors مستخدمة في HomeView, BookingView, DiningView, SiteHeader, SiteFooter, ConfirmationView, LanguageSelector (57 مكان) — لا تُحذف

---

## 📋 جدول الأولويات السريعة

| الأولوية | المهمة | الملف | الجهد | لماذا الآن |
|----------|--------|-------|-------|------------|
| **1** | 1-A: Backend tables API | dining/api + schemas | S | أساس كل مهام الطاولات |
| **2** | 1-B: خريطة الطاولات الذكية | UnifiedPOSView | L | الطلب الرئيسي — أهم مهمة |
| **3** | 1-D: رقم الطاولة في KDS | DiningKDSView + backend | S | يوم عمل واحد، أثر كبير |
| **4** | 0-A: Dark Mode Layout | BackOfficeLayout | M | يجب قبل ThemeToggle |
| **5** | 0-B: Dark Mode Components | Card + inputClasses | S | يكمل 0-A |
| **6** | 4-A: ThemeToggle تركيب | BackOfficeLayout | XS | بعد 0-A فقط |
| **7** | 1-C: WebSocket للطاولات | UnifiedPOSView + backend | M | بعد 1-B |
| **8** | 1-E: ملاحظات أوردر في KDS | DiningKDSView | S | بسيطة، أثر تشغيلي |
| **9** | 2-B: branch_id من auth | auth.ts + كل الـ views | M | تنظيف مهم |
| **10** | 4-B: console.error | HR/Timeshare/CRM views | S | production readiness |
| **11** | 2-A: httpOnly Cookie | auth.ts + backend | L | أمان، لكن محتاج وقت |
| **12** | 3-A: Analytics WS | DashboardView | M | الباك إند جاهز |
| **13** | 3-C: Merge Tables | POS + backend | M | يومي في المطاعم |
| **14** | 3-B: Loyalty Points | CRM + POS | L | أثر تجاري عالي |
| **15** | 4-D: Menu Item Images | DiningMenu + backend | M | تحسين UX |
| **16** | 0-C: نقل CSS مشترك | main.css files | S | تنظيم |
| **17** | 3-D: Revenue Comparison | AnalyticsView | M | BI |
| **18** | 4-E: Color System | جميع الملفات | L | تدريجي |

---

## 📌 ملاحظات حرجة

### مهام مترابطة — اتبع هذا الترتيب صارماً:
```
1-A (backend API) → 1-B (frontend tables map) → 1-C (websocket)
0-A (layout dark mode) → 0-B (components) → 4-A (ThemeToggle)
2-B (branch_id refactor) → تعديل كل الـ views
```

### المهام المستقلة (يمكن تنفيذها بأي ترتيب):
- 1-D, 1-E (KDS) — مستقلة تماماً
- 4-B (console.error cleanup) — مستقلة
- 0-C (CSS merge) — مستقلة

### لا تبدأ هذه المهام قبل أسلافها:
- `4-A` (ThemeToggle) تتطلب `0-A` (Layout classes) أولاً — وإلا الـ toggle يشتغل لكن لا شيء يتغير بصرياً
- `3-B` (Loyalty Points) تتطلب مراجعة backend أولاً — تأكد من وجود model قبل الفرونت
- `3-C` (Merge Tables) تتطلب تأكيد backend endpoint قبل الـ UI
