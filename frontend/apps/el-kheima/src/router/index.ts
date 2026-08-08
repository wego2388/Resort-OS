import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore, type PermissionKey } from '@resort-os/core'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    requiresBranch?: boolean
    // Minimum role required, checked against the numeric ROLE_LEVELS map in
    // @resort-os/core's useAuthStore (mirrors backend app/core/deps.py).
    requiredRole?: string
    // Exact-role allow-list — overrides requiredRole when present. Needed
    // for modules isolated from the general role hierarchy (timeshare,
    // 2026-08-03): a level-based requiredRole can't express "only
    // timeshare_admin/timeshare_agent, not any manager" — timeshare_admin
    // (level 55) would satisfy a plain 'manager' (60) check as false but a
    // lower 'cashier' (40) check as true, while timeshare_agent (level 25)
    // sits below every other operational role. super_admin always passes
    // regardless (mirrors backend Decision 0003 invariant #1).
    requiredRoles?: string[]
    // Server-evaluated permissions from /auth/bootstrap. Arrays require every
    // listed permission; unknown values fail closed in the auth store.
    requiredPermission?: PermissionKey | PermissionKey[]
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
  { path: '/forgot-password', name: 'forgot-password', component: () => import('../views/account/ForgotPasswordView.vue'), meta: { titleKey: 'backoffice.forgotPassword.title' } },
  { path: '/reset-password', name: 'reset-password', component: () => import('../views/account/ResetPasswordView.vue'), meta: { titleKey: 'backoffice.resetPassword.title' } },

  {
    path: '/change-temporary-password',
    name: 'change-temporary-password',
    component: () => import('../views/account/ForcePasswordChangeView.vue'),
    meta: { requiresAuth: true },
  },

  {
    path: '/select-branch',
    name: 'select-branch',
    component: () => import('../views/account/BranchSelectionView.vue'),
    meta: { requiresAuth: true, titleKey: 'backoffice.layout.chooseBranchTitle' },
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
    meta: { requiresAuth: true, titleKey: 'account.sessions.navLink' },
  },

  // ── /pos — FieldLayout (lightweight, tablet/phone, on-floor cashier use) ──
  {
    path: '/pos',
    component: () => import('../layouts/FieldLayout.vue'),
    meta: { requiresAuth: true, requiresBranch: true, requiredRole: 'cashier' },
    children: [
      { path: '', redirect: '/pos/beach' },
      { path: 'beach', name: 'pos-beach', component: () => import('../views/pos/BeachPOSView.vue'), meta: { titleKey: 'backoffice.nav.beachPos' } },
      { path: 'beach-map', name: 'pos-beach-map', component: () => import('../views/pos/BeachMapView.vue'), meta: { titleKey: 'backoffice.nav.beachMap' } },
      // DINING_CUTOVER_PLAN.md Batch 4 — dining هو الـ POS الافتراضي دلوقتي
      // (مش manager-only preview بقى). requiredRole مخفّض لـ 'waiter' هنا
      // عشان يفوّت بوابة الأب (cashier) — نادل يقدر ياخد طلبات ويبعتها
      // للمطبخ، لكن مش يقفل الحساب (paid يتطلب get_cashier_user في الباك
      // إند نفسه، مستقل تمامًا عن الـ route gate ده). الروترات القديمة
      // (restaurant/cafe) اتسابت كـ redirect بدل حذف فوري — مفيش رابط حي
      // بيوصلها تاني، لكن أي bookmark قديم لسه بيشتغل صح.
      { path: 'dining', name: 'pos-dining', component: () => import('../views/pos/UnifiedPOSView.vue'), meta: { requiredRole: 'waiter', titleKey: 'backoffice.nav.diningPos' } },
      { path: 'restaurant', redirect: '/pos/dining' },
      { path: 'cafe', redirect: '/pos/dining' },
      { path: 'shift', name: 'pos-shift', component: () => import('../views/pos/ShiftDashboardView.vue'), meta: { titleKey: 'backoffice.nav.shift' } },
      { path: 'shift-monitor', name: 'pos-shift-monitor', component: () => import('../views/pos/ShiftMonitorView.vue'), meta: { requiredRole: 'manager', titleKey: 'backoffice.nav.shiftMonitor' } },
    ],
  },

  // ── /kds — KioskLayout (fullscreen, distraction-free kitchen display) ──
  {
    path: '/kds',
    component: () => import('../layouts/KioskLayout.vue'),
    meta: { requiresAuth: true, requiresBranch: true, requiredRole: 'waiter' },
    children: [
      { path: '', redirect: '/kds/dining' },
      // DINING_CUTOVER_PLAN.md Batch 4 — شاشة موحّدة واحدة بدل station-specific
      // منفصلة (kitchen/bar/cafe) — بتغطي كل المحطات بتابات فلترة داخلية
      // (راجع DiningKDSView.vue's STATIONS)، نفس رؤية "نفس المطبخ لكل الـ
      // outlets" الموثّقة في dining.models.DiningKDSScreen. requiredRole
      // بيرث من الأب (waiter، level 30) — نفس مستوى kitchen/chef بالظبط.
      { path: 'dining',  name: 'kds-dining',  component: () => import('../views/kds/DiningKDSView.vue'), meta: { titleKey: 'backoffice.nav.diningKds' } },
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
    meta: { requiresAuth: true, requiresBranch: true },
    children: [
      { path: '', redirect: '/ops/reception' },
      { path: 'reception', name: 'ops-reception', component: () => import('../views/ops/ReceptionView.vue'), meta: {
        titleKey: 'backoffice.nav.reception',
        requiredPermission: ['pms.rooms:view', 'pms.bookings:view', 'pms.housekeeping:view'],
      } },
      { path: 'rooms', name: 'ops-rooms', component: () => import('../views/ops/RoomsView.vue'), meta: {
        titleKey: 'backoffice.nav.rooms', requiredPermission: 'pms.rooms:view',
      } },
      { path: 'bookings', name: 'ops-bookings', component: () => import('../views/ops/BookingsView.vue'), meta: {
        titleKey: 'backoffice.nav.bookings', requiredPermission: 'pms.bookings:view',
      } },
      { path: 'housekeeping', name: 'ops-housekeeping', component: () => import('../views/ops/HousekeepingView.vue'), meta: {
        titleKey: 'backoffice.nav.housekeeping', requiredPermission: 'pms.housekeeping:view',
      } },
    ],
  },

  // ── /admin — BackOfficeLayout (sidebar + grouped nav) ──
  {
    path: '/admin',
    component: () => import('../layouts/BackOfficeLayout.vue'),
    // requiredRole: 'manager' كان level-based (≥60) — كان يسمح لـ hr_manager
    // (level 70) و accountant (level 70) بالدخول على /admin بدون قيد، ثم
    // الـ child guard يمنعهم من الصفحات الفردية. لكن لو child ما عنده
    // requiredRoles (مثل /admin/dining-menu أو /admin/hub) كانوا يشوفوها.
    // requiredRoles allow-list صريح يضمن إن بس الأدوار المصرح بها تدخل
    // /admin أصلاً، بغض النظر عن level.
    meta: { requiresAuth: true, requiresBranch: true, requiredRoles: ['manager', 'accountant', 'hr_manager', 'supervisor', 'timeshare_admin', 'timeshare_agent', 'admin', 'super_admin'] },
    children: [
      // كل دور بيكون له landing page مختلفة — homeRouteFor بيحدد الصحيحة
      // بدل redirect ثابت لـ /admin/dashboard اللي بعدين guard يرده.
      { path: '', redirect: () => homeRouteFor(useAuthStore().role) },
      { path: 'dashboard', name: 'admin-dashboard', component: () => import('../views/admin/DashboardView.vue'), meta: { requiredRoles: ['manager', 'admin', 'super_admin'], titleKey: 'backoffice.nav.dashboard' } },
      { path: 'analytics', name: 'admin-analytics', component: () => import('../views/admin/AnalyticsView.vue'), meta: { requiredRoles: ['manager', 'admin', 'super_admin'], titleKey: 'backoffice.nav.analytics' } },
      { path: 'hr', name: 'admin-hr', component: () => import('../views/admin/HRView.vue'), meta: { requiredRoles: ['manager', 'hr_manager', 'admin', 'super_admin'], titleKey: 'backoffice.nav.hr' } },
      { path: 'finance', name: 'admin-finance', component: () => import('../views/admin/FinanceView.vue'), meta: { requiredRoles: ['manager', 'accountant', 'admin', 'super_admin'], titleKey: 'backoffice.nav.finance' } },
      { path: 'credit-accounts', name: 'admin-credit-accounts', component: () => import('../views/admin/CreditAccountsView.vue'), meta: {
        requiredRoles: ['manager', 'accountant', 'admin'],
        requiredPermission: 'credit.accounts:view',
        titleKey: 'backoffice.nav.creditAccounts',
      } },
      // ⚠️ requiredRole كان 'supervisor' (level 50) — أعلى من الصلاحية اللي
      // الباك إند بيمنحها فعليًا لتسجيل تحصيل قسط (get_cashier_user، level 40،
      // اتصلحت اليوم من get_current_active_user). يعني الكاشير المفروض يقدر
      // يحصّل الأقساط كان أصلاً ميقدرش يوصل للشاشة دي خالص — بيتحول تلقائيًا
      // لصفحته الرئيسية لو حاول يدخل /admin/timeshare مباشرة. باقي إجراءات
      // المدير (إلغاء عقد، تعليق، استيراد Excel) محمية أصلاً بـ
      // auth.hasRole('manager') داخل الشاشة نفسها، فتخفيض البوابة هنا آمن.
      // requiredRoles (2026-08-03): وحدة التايم شير بقت معزولة تمامًا عن
      // هرمية الأدوار العامة (طلب Mohamed — راجع app.core.deps.
      // get_timeshare_user). requiredRole القديم (level-based) كان بيسمح
      // لأي مدير/كاشير عام يدخل الشاشة يشوفها فاضية وتطلعله 403 على كل
      // نداء API — requiredRoles allow-list صريح بديل بدل ما يعتمد على مستوى.
      { path: 'timeshare', name: 'admin-timeshare', component: () => import('../views/admin/TimeshareView.vue'), meta: { requiredRoles: ['timeshare_admin', 'timeshare_agent'], titleKey: 'backoffice.nav.timeshare' } },
      { path: 'sales', name: 'admin-sales', component: () => import('../views/admin/SalesDashboardView.vue'), meta: { requiredRoles: ['timeshare_admin', 'timeshare_agent'], titleKey: 'backoffice.nav.sales' } },
      { path: 'beach-live', name: 'admin-beach-live', component: () => import('../views/admin/BeachLiveDashboardView.vue'), meta: { requiredRoles: ['manager', 'supervisor', 'admin', 'super_admin'], titleKey: 'backoffice.nav.beachLive' } },
      { path: 'beach-admin', name: 'admin-beach-admin', component: () => import('../views/admin/BeachAdminView.vue'), meta: { requiredRoles: ['manager', 'supervisor', 'admin', 'super_admin'], titleKey: 'backoffice.nav.beachAdmin' } },
      { path: 'e-invoice', name: 'admin-e-invoice', component: () => import('../views/admin/EInvoiceView.vue'), meta: { requiredRoles: ['manager', 'accountant', 'admin', 'super_admin'], titleKey: 'backoffice.nav.eInvoice' } },
      { path: 'inventory', name: 'admin-inventory', component: () => import('../views/admin/InventoryView.vue'), meta: { requiredRoles: ['manager', 'supervisor', 'admin', 'super_admin'], titleKey: 'backoffice.nav.inventory' } },
      { path: 'recipes', name: 'admin-recipes', component: () => import('../views/admin/RecipesView.vue'), meta: { requiredRoles: ['manager', 'supervisor', 'admin', 'super_admin'], titleKey: 'backoffice.nav.recipes' } },
      { path: 'food-cost', name: 'admin-food-cost', component: () => import('../views/admin/FoodCostReportView.vue'), meta: { requiredRoles: ['manager', 'supervisor', 'admin', 'super_admin'], titleKey: 'backoffice.nav.foodCost' } },
      { path: 'crm', name: 'admin-crm', component: () => import('../views/admin/CRMView.vue'), meta: { requiredRoles: ['manager', 'admin', 'super_admin'], titleKey: 'backoffice.nav.crm' } },
      { path: 'maintenance', name: 'admin-maintenance', component: () => import('../views/admin/MaintenanceView.vue'), meta: { requiredRoles: ['manager', 'supervisor', 'admin', 'super_admin'], titleKey: 'backoffice.nav.maintenance' } },
      { path: 'leasing', name: 'admin-leasing', component: () => import('../views/admin/LeasingView.vue'), meta: { requiredRoles: ['manager', 'supervisor', 'admin', 'super_admin'], titleKey: 'backoffice.nav.leasing' } },
      { path: 'settings',    name: 'admin-settings',    component: () => import('../views/admin/SettingsView.vue'),    meta: { requiredRole: 'admin', titleKey: 'backoffice.nav.settings' } },
      { path: 'qr',          name: 'admin-qr',          component: () => import('../views/admin/QRGeneratorView.vue'),        meta: { titleKey: 'backoffice.nav.qrCodes' } },
      // DINING_CUTOVER_PLAN.md Batch 4 — dining-menu هو الافتراضي دلوقتي،
      // بيغطي منافذ/فئات/أصناف/مجموعات إضافات/طاولات المطعم والكافيه معًا
      // (راجع DiningMenuView.vue). menu/cafe-menu/tables القدام باقيين كـ
      // redirect — cafe-sales (تقرير مبيعات cafe.reports/sales) اتحول لـ
      // /admin/analytics لحد ما يتعمل شاشة تقرير مبيعات dining مخصصة (فجوة
      // موثّقة، راجع تقرير الـ cutover).
      { path: 'dining-menu', name: 'admin-dining-menu', component: () => import('../views/admin/DiningMenuView.vue'),        meta: { titleKey: 'backoffice.nav.diningMenu' } },
      { path: 'menu',        redirect: '/admin/dining-menu' },
      { path: 'cafe-menu',   redirect: '/admin/dining-menu' },
      { path: 'tables',      redirect: '/admin/dining-menu' },
      { path: 'cafe-sales',  redirect: '/admin/analytics' },
      // Legacy bookmarks stay valid, but user/account/permission management
      // now has one authoritative screen instead of three diverging copies.
      { path: 'permissions', name: 'admin-permissions', redirect: to => ({
        path: '/admin/super-admin', query: { ...to.query, tab: 'permissions' },
      }), meta: { requiredRole: 'super_admin', titleKey: 'backoffice.permissions.title' } },
      { path: 'users', name: 'admin-users', redirect: to => ({
        path: '/admin/super-admin', query: { ...to.query, tab: 'users' },
      }), meta: { requiredRole: 'super_admin', titleKey: 'backoffice.accounts.title' } },
      { path: 'super-admin', name: 'admin-super-admin', component: () => import('../views/admin/SuperAdminView.vue'), meta: { requiredRole: 'super_admin', titleKey: 'backoffice.superAdmin.title' } },
      { path: 'hub', name: 'admin-hub', component: () => import('../views/admin/HubManagementView.vue'), meta: { titleKey: 'backoffice.hub.title' } },
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
      { path: 'attendance', name: 'portal-attendance', component: () => import('../views/portal/AttendanceView.vue'), meta: { titleKey: 'backoffice.nav.attendance' } },
      { path: 'leaves', name: 'portal-leaves', component: () => import('../views/portal/LeavesView.vue'), meta: { titleKey: 'backoffice.nav.leaves' } },
      { path: 'payroll', name: 'portal-payroll', component: () => import('../views/portal/PayrollView.vue'), meta: { titleKey: 'backoffice.nav.payroll' } },
      { path: 'profile', name: 'portal-profile', component: () => import('../views/portal/ProfileView.vue'), meta: { titleKey: 'backoffice.nav.profile' } },
    ],
  },

  {
    path: '/',
    redirect: () => homeRouteFor(useAuthStore().role),
  },
  { path: '/:pathMatch(.*)*', component: () => import('../views/account/NotFoundView.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, _from, savedPosition) {
    // الـ savedPosition موجود لما المستخدم يضغط back/forward في المتصفح
    // — يرجع لنفس المكان اللي كان فيه (سلوك المتصفح الطبيعي).
    // لو مفيش saved position، نبدأ من الأعلى دايمًا عند التنقل لصفحة جديدة.
    if (savedPosition) return savedPosition
    if (to.hash) return { el: to.hash, behavior: 'smooth' }
    return { top: 0, behavior: 'smooth' }
  },
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

  // 4. Branch gate — operational screens never mount with a guessed/default
  // branch. The selector itself and account recovery screens stay reachable.
  if (auth.isAuthenticated && to.meta.requiresBranch && auth.branchId == null) {
    return '/select-branch'
  }

  // 5. Role gate — redirect to the user's own home, not a raw 403 page.
  // requiredRoles (exact allow-list) takes priority over requiredRole
  // (level threshold) when both are present in the merged meta — see the
  // RouteMeta.requiredRoles doc comment above for why isolated modules
  // need this instead of a level check.
  if (to.meta.requiredRoles) {
    if (!to.meta.requiredRoles.includes(auth.role) && !auth.hasRole('super_admin')) {
      return homeRouteFor(auth.role)
    }
  } else if (to.meta.requiredRole && !auth.hasRole(to.meta.requiredRole)) {
    return homeRouteFor(auth.role)
  }

  // 6. Fine-grained permission gate. /portal/profile is the safe destination
  // for a valid employee whose branch role has no access to the requested UI.
  const requirements = to.meta.requiredPermission
    ? (Array.isArray(to.meta.requiredPermission) ? to.meta.requiredPermission : [to.meta.requiredPermission])
    : []
  if (requirements.some((permission) => !auth.hasPermission(permission))) {
    return '/portal/profile'
  }

  return true
})

export default router
