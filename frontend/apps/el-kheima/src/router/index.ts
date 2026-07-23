import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@resort-os/core'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    // Minimum role required, checked against the numeric ROLE_LEVELS map in
    // @resort-os/core's useAuthStore (mirrors backend app/core/deps.py).
    requiredRole?: string
    title?: string
    titleKey?: string
  }
}

/**
 * Role-based landing route — replaces the old hardcoded `redirect: '/xxx'`
 * each former app had. Picks the first screen that role actually uses day to
 * day, matching the plan's owner-approved mapping:
 *   cashier/receptionist → POS, kitchen/bar staff → KDS, waiter → floor view,
 *   manager/admin (+finance/HR/supervisor roles) → back-office dashboard,
 *   HR/employee-level roles → self-service portal.
 */
export function homeRouteFor(role: string): string {
  switch (role) {
    case 'waiter':
      // DINING_CUTOVER_PLAN.md Batch 4 — UnifiedPOSView بديل TablesView/
      // OrderView (كانوا restaurant-only بالكامل، بدون أي إصدار dining).
      return '/pos/dining'
    case 'chef':
    case 'kitchen':
      return '/kds/dining'
    case 'cashier':
      return '/pos/beach'
    case 'receptionist':
      return '/ops/reception'
    case 'manager':
    case 'admin':
    case 'super_admin':
    case 'accountant':
      return '/admin/dashboard'
    case 'hr_manager':
      // hr_manager clears the same manager-level (60+) threshold as
      // accountant per backend ROLE_LEVELS — lands on their own module
      // instead of the generic dashboard.
      return '/admin/hr'
    case 'supervisor':
      // Level 50 — below the manager (60) threshold most /admin/* routes
      // require server-side, but above cashier — front-desk/ops oversight.
      return '/ops/rooms'
    case 'employee':
    case 'customer':
    case 'guest':
      return '/portal/attendance'
    default:
      // Unknown/least-privileged role — self-service portal is the safest
      // default (no back-office/financial data visible there).
      return '/portal/attendance'
  }
}

const routes: RouteRecordRaw[] = [
  { path: '/login', component: () => import('../views/account/LoginView.vue') },

  // Standalone (no layout, no auth) — reached from the "نسيت كلمة السر؟" link
  // on /login, or (for /reset-password) from the email link the backend sends
  // (app/core/kernel/email_service.py::send_password_reset_email). Both call
  // the existing app/core/kernel/auth/router.py password-reset endpoints —
  // no backend changes needed for either.
  { path: '/forgot-password', name: 'forgot-password', component: () => import('../views/account/ForgotPasswordView.vue') },
  { path: '/reset-password', name: 'reset-password', component: () => import('../views/account/ResetPasswordView.vue') },

  {
    path: '/change-temporary-password',
    name: 'change-temporary-password',
    component: () => import('../views/account/ForcePasswordChangeView.vue'),
    meta: { requiresAuth: true },
  },

  // Standalone (no layout) — same tier as /login. Reached either by force
  // (router guard below, for MANDATORY_2FA_ROLES with two_factor_enabled=false)
  // or voluntarily by any authenticated user who wants to turn 2FA on/off.
  {
    path: '/2fa-setup',
    name: '2fa-setup',
    component: () => import('../views/account/TwoFactorSetupView.vue'),
    meta: { requiresAuth: true },
  },

  // Gate 2B3B — session & security self-service, available to any authenticated
  // user (mirrors /2fa-setup: standalone, no back-office chrome). Lists the
  // user's own active sessions (revoke one / revoke all others via step-up) and
  // their recent security activity.
  {
    path: '/account/sessions',
    name: 'account-sessions',
    component: () => import('../views/account/SessionsView.vue'),
    meta: { requiresAuth: true },
  },

  // ── /pos — FieldLayout (lightweight, tablet/phone, on-floor cashier use) ──
  {
    path: '/pos',
    component: () => import('../layouts/FieldLayout.vue'),
    meta: { requiresAuth: true, requiredRole: 'cashier' },
    children: [
      { path: '', redirect: '/pos/beach' },
      { path: 'beach', name: 'pos-beach', component: () => import('../views/pos/BeachPOSView.vue') },
      { path: 'beach-map', name: 'pos-beach-map', component: () => import('../views/pos/BeachMapView.vue') },
      // DINING_CUTOVER_PLAN.md Batch 4 — dining هو الـ POS الافتراضي دلوقتي
      // (مش manager-only preview بقى). requiredRole مخفّض لـ 'waiter' هنا
      // عشان يفوّت بوابة الأب (cashier) — نادل يقدر ياخد طلبات ويبعتها
      // للمطبخ، لكن مش يقفل الحساب (paid يتطلب get_cashier_user في الباك
      // إند نفسه، مستقل تمامًا عن الـ route gate ده). الروترات القديمة
      // (restaurant/cafe) اتسابت كـ redirect بدل حذف فوري — مفيش رابط حي
      // بيوصلها تاني، لكن أي bookmark قديم لسه بيشتغل صح.
      { path: 'dining', name: 'pos-dining', component: () => import('../views/pos/UnifiedPOSView.vue'), meta: { requiredRole: 'waiter' } },
      { path: 'restaurant', redirect: '/pos/dining' },
      { path: 'cafe', redirect: '/pos/dining' },
      { path: 'shift', name: 'pos-shift', component: () => import('../views/pos/ShiftDashboardView.vue') },
    ],
  },

  // ── /kds — KioskLayout (fullscreen, distraction-free kitchen display) ──
  {
    path: '/kds',
    component: () => import('../layouts/KioskLayout.vue'),
    meta: { requiresAuth: true, requiredRole: 'waiter' },
    children: [
      { path: '', redirect: '/kds/dining' },
      // DINING_CUTOVER_PLAN.md Batch 4 — شاشة موحّدة واحدة بدل station-specific
      // منفصلة (kitchen/bar/cafe) — بتغطي كل المحطات بتابات فلترة داخلية
      // (راجع DiningKDSView.vue's STATIONS)، نفس رؤية "نفس المطبخ لكل الـ
      // outlets" الموثّقة في dining.models.DiningKDSScreen. requiredRole
      // بيرث من الأب (waiter، level 30) — نفس مستوى kitchen/chef بالظبط.
      { path: 'dining',  name: 'kds-dining',  component: () => import('../views/kds/DiningKDSView.vue') },
      // ?stations=... يخلي جهاز مثبّت فعليًا في المطبخ/البار يفتح على
      // فلتره الأصلي بالظبط (راجع DiningKDSView.vue's initialStationFilter)
      // بدل ما يفضل يبدأ بـ "كل المحطات" كل مرة.
      { path: 'kitchen', redirect: () => ({ path: '/kds/dining', query: { stations: 'hot,grill,cold,dessert' } }) },
      { path: 'bar',     redirect: () => ({ path: '/kds/dining', query: { stations: 'bar' } }) },
      { path: 'cafe',    redirect: () => ({ path: '/kds/dining', query: { stations: 'bar' } }) },
    ],
  },

  // ── /ops — BackOfficeLayout (sidebar + grouped nav) ──
  {
    path: '/ops',
    component: () => import('../layouts/BackOfficeLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/ops/reception' },
      { path: 'reception', name: 'ops-reception', component: () => import('../views/ops/ReceptionView.vue'), meta: { title: 'الاستقبال' } },
      { path: 'rooms', name: 'ops-rooms', component: () => import('../views/ops/RoomsView.vue'), meta: { title: 'الغرف' } },
      { path: 'bookings', name: 'ops-bookings', component: () => import('../views/ops/BookingsView.vue'), meta: { title: 'الحجوزات' } },
      { path: 'housekeeping', name: 'ops-housekeeping', component: () => import('../views/ops/HousekeepingView.vue'), meta: { title: 'التنظيف' } },
    ],
  },

  // ── /admin — BackOfficeLayout (sidebar + grouped nav) ──
  {
    path: '/admin',
    component: () => import('../layouts/BackOfficeLayout.vue'),
    meta: { requiresAuth: true, requiredRole: 'manager' },
    children: [
      { path: '', redirect: '/admin/dashboard' },
      { path: 'dashboard', name: 'admin-dashboard', component: () => import('../views/admin/DashboardView.vue'), meta: { title: 'لوحة التحكم' } },
      { path: 'analytics', name: 'admin-analytics', component: () => import('../views/admin/AnalyticsView.vue'), meta: { title: 'التحليلات' } },
      { path: 'hr', name: 'admin-hr', component: () => import('../views/admin/HRView.vue'), meta: { title: 'الموارد البشرية' } },
      { path: 'finance', name: 'admin-finance', component: () => import('../views/admin/FinanceView.vue'), meta: { title: 'المالية' } },
      // ⚠️ requiredRole كان 'supervisor' (level 50) — أعلى من الصلاحية اللي
      // الباك إند بيمنحها فعليًا لتسجيل تحصيل قسط (get_cashier_user، level 40،
      // اتصلحت اليوم من get_current_active_user). يعني الكاشير المفروض يقدر
      // يحصّل الأقساط كان أصلاً ميقدرش يوصل للشاشة دي خالص — بيتحول تلقائيًا
      // لصفحته الرئيسية لو حاول يدخل /admin/timeshare مباشرة. باقي إجراءات
      // المدير (إلغاء عقد، تعليق، استيراد Excel) محمية أصلاً بـ
      // auth.hasRole('manager') داخل الشاشة نفسها، فتخفيض البوابة هنا آمن.
      { path: 'timeshare', name: 'admin-timeshare', component: () => import('../views/admin/TimeshareView.vue'), meta: { requiredRole: 'cashier', title: 'التايم شير' } },
      { path: 'sales', name: 'admin-sales', component: () => import('../views/admin/SalesDashboardView.vue'), meta: { title: 'لوحة المبيعات' } },
      { path: 'beach-live', name: 'admin-beach-live', component: () => import('../views/admin/BeachLiveDashboardView.vue'), meta: { title: 'لوحة الشاطئ الحيّة' } },
      { path: 'beach-admin', name: 'admin-beach-admin', component: () => import('../views/admin/BeachAdminView.vue'), meta: { title: 'إدارة الشاطئ' } },
      { path: 'e-invoice', name: 'admin-e-invoice', component: () => import('../views/admin/EInvoiceView.vue'), meta: { title: 'الفاتورة الإلكترونية' } },
      { path: 'inventory', name: 'admin-inventory', component: () => import('../views/admin/InventoryView.vue'), meta: { title: 'المخزون' } },
      { path: 'recipes', name: 'admin-recipes', component: () => import('../views/admin/RecipesView.vue'), meta: { title: 'وصفات الأصناف' } },
      { path: 'food-cost', name: 'admin-food-cost', component: () => import('../views/admin/FoodCostReportView.vue'), meta: { title: 'تكلفة الطعام' } },
      { path: 'crm', name: 'admin-crm', component: () => import('../views/admin/CRMView.vue'), meta: { title: 'إدارة العملاء' } },
      { path: 'maintenance', name: 'admin-maintenance', component: () => import('../views/admin/MaintenanceView.vue'), meta: { requiredRole: 'supervisor', title: 'الصيانة' } },
      { path: 'leasing', name: 'admin-leasing', component: () => import('../views/admin/LeasingView.vue'), meta: { requiredRole: 'supervisor', title: 'الإيجارات' } },
      { path: 'settings',    name: 'admin-settings',    component: () => import('../views/admin/SettingsView.vue'),    meta: { requiredRole: 'admin', title: 'الإعدادات' } },
      { path: 'qr',          name: 'admin-qr',          component: () => import('../views/admin/QRGeneratorView.vue'),        meta: { title: 'QR Codes' } },
      // DINING_CUTOVER_PLAN.md Batch 4 — dining-menu هو الافتراضي دلوقتي،
      // بيغطي منافذ/فئات/أصناف/مجموعات إضافات/طاولات المطعم والكافيه معًا
      // (راجع DiningMenuView.vue). menu/cafe-menu/tables القدام باقيين كـ
      // redirect — cafe-sales (تقرير مبيعات cafe.reports/sales) اتحول لـ
      // /admin/analytics لحد ما يتعمل شاشة تقرير مبيعات dining مخصصة (فجوة
      // موثّقة، راجع تقرير الـ cutover).
      { path: 'dining-menu', name: 'admin-dining-menu', component: () => import('../views/admin/DiningMenuView.vue'),        meta: { title: 'إدارة الدايننج' } },
      { path: 'menu',        redirect: '/admin/dining-menu' },
      { path: 'cafe-menu',   redirect: '/admin/dining-menu' },
      { path: 'tables',      redirect: '/admin/dining-menu' },
      { path: 'cafe-sales',  redirect: '/admin/analytics' },
      { path: 'permissions', name: 'admin-permissions', component: () => import('../views/admin/PermissionsView.vue'),  meta: { requiredRole: 'super_admin', title: 'الصلاحيات' } },
      { path: 'super-admin', name: 'admin-super-admin', component: () => import('../views/admin/SuperAdminView.vue'), meta: { requiredRole: 'super_admin', title: 'لوحة تحكم Super Admin' } },
      { path: 'hub', name: 'admin-hub', component: () => import('../views/admin/HubManagementView.vue'), meta: { title: 'الموقع والحجوزات الأونلاين' } },
      // Mohamed's temporary project control room. The route is compiled into
      // development only and remains role-gated even there. Production builds
      // contain neither the route nor its lazy-loaded snapshot chunk.
      ...(import.meta.env.DEV ? [{
        path: 'project-cockpit',
        name: 'dev-project-cockpit',
        component: () => import('../views/dev/ProjectCockpitView.vue'),
        meta: {
          requiredRole: 'super_admin',
          titleKey: 'backoffice.nav.projectCockpit',
        },
      }] : []),
    ],
  },

  // ── /waiter — DINING_CUTOVER_PLAN.md Batch 4: TablesView/OrderView/
  // TablesMapView كانوا restaurant-only بالكامل (كل استدعاء API فيهم على
  // /api/v1/restaurant/...، بدون أي outlet-awareness) من غير أي إصدار
  // dining مقابل. UnifiedPOSView بيغطي نفس المهمة (dine_in بخريطة طاولات
  // حقيقية مجمّعة بالقسم) على الـ API الموحّد — redirect بدل إعادة كتابة
  // 3 شاشات لنفس القدرة المتاحة فعليًا في /pos/dining.
  {
    path: '/waiter',
    children: [
      { path: '', redirect: '/pos/dining' },
      { path: 'tables', redirect: '/pos/dining' },
      { path: 'tables-map', redirect: '/pos/dining' },
      { path: 'order/:tableId', redirect: '/pos/dining' },
      { path: 'order', redirect: '/pos/dining' },
    ],
  },

  // ── /portal — BackOfficeLayout (sidebar + grouped nav, employee self-service) ──
  {
    path: '/portal',
    component: () => import('../layouts/BackOfficeLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/portal/attendance' },
      { path: 'attendance', name: 'portal-attendance', component: () => import('../views/portal/AttendanceView.vue'), meta: { title: 'الحضور والانصراف' } },
      { path: 'leaves', name: 'portal-leaves', component: () => import('../views/portal/LeavesView.vue'), meta: { title: 'طلبات الإجازة' } },
      { path: 'payroll', name: 'portal-payroll', component: () => import('../views/portal/PayrollView.vue'), meta: { title: 'الرواتب' } },
      { path: 'profile', name: 'portal-profile', component: () => import('../views/portal/ProfileView.vue'), meta: { title: 'ملفي الشخصي' } },
    ],
  },

  {
    path: '/',
    redirect: () => homeRouteFor(useAuthStore().role),
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()

  // 1. Auth gate
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return '/login'
  }

  // Already logged in and heading to /login — send to their home instead.
  if (to.path === '/login' && auth.isAuthenticated) {
    return homeRouteFor(auth.role)
  }

  // 2. Temporary/bootstrap credentials may only reach the dedicated password
  // replacement screen. This mirrors get_current_active_user server-side.
  if (
    auth.isAuthenticated
    && auth.needsPasswordChange
    && to.path !== '/change-temporary-password'
  ) {
    return '/change-temporary-password'
  }

  // 3. Mandatory 2FA gate — mirrors backend app/core/deps.py's
  // MANDATORY_2FA_ROLES check. Without this, a super_admin/accountant who
  // hasn't finished 2FA setup lands on their normal home route and every
  // API call there silently 403s (dashboards render all-zero, lists render
  // empty) with no indication why. Force them to /2fa-setup first.
  if (
    auth.isAuthenticated
    && !auth.needsPasswordChange
    && auth.needsTwoFactorSetup
    && to.path !== '/2fa-setup'
  ) {
    return '/2fa-setup'
  }

  // 4. Role gate — redirect to the user's own home, not a raw 403 page.
  if (to.meta.requiredRole && !auth.hasRole(to.meta.requiredRole)) {
    return homeRouteFor(auth.role)
  }

  return true
})

export default router
