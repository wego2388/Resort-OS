import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@resort-os/core'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    // Minimum role required, checked against the numeric ROLE_LEVELS map in
    // @resort-os/core's useAuthStore (mirrors backend app/core/deps.py).
    requiredRole?: string
    title?: string
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
      return '/waiter/tables'
    case 'chef':
    case 'kitchen':
      return '/kds/kitchen'
    case 'cashier':
    case 'receptionist':
      return '/pos/beach'
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
  { path: '/login', component: () => import('@resort-os/ui').then((m) => ({ default: m.LoginView })) },

  // ── /pos — FieldLayout (lightweight, tablet/phone, on-floor cashier use) ──
  {
    path: '/pos',
    component: () => import('../layouts/FieldLayout.vue'),
    meta: { requiresAuth: true, requiredRole: 'cashier' },
    children: [
      { path: '', redirect: '/pos/beach' },
      { path: 'beach', name: 'pos-beach', component: () => import('../views/pos/BeachPOSView.vue') },
      { path: 'restaurant', name: 'pos-restaurant', component: () => import('../views/pos/RestaurantPOSView.vue') },
      { path: 'cafe', name: 'pos-cafe', component: () => import('../views/pos/CafePOSView.vue') },
    ],
  },

  // ── /kds — KioskLayout (fullscreen, distraction-free kitchen display) ──
  {
    path: '/kds',
    component: () => import('../layouts/KioskLayout.vue'),
    meta: { requiresAuth: true, requiredRole: 'waiter' },
    children: [
      { path: '', redirect: '/kds/kitchen' },
      { path: 'kitchen', name: 'kds-kitchen', component: () => import('../views/kds/KitchenDisplayView.vue') },
      { path: 'bar', name: 'kds-bar', component: () => import('../views/kds/BarDisplayView.vue') },
    ],
  },

  // ── /ops — BackOfficeLayout (sidebar + grouped nav) ──
  {
    path: '/ops',
    component: () => import('../layouts/BackOfficeLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/ops/rooms' },
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
      { path: 'timeshare', name: 'admin-timeshare', component: () => import('../views/admin/TimeshareView.vue'), meta: { title: 'التايم شير' } },
      { path: 'sales', name: 'admin-sales', component: () => import('../views/admin/SalesDashboardView.vue'), meta: { title: 'لوحة المبيعات' } },
      { path: 'beach-live', name: 'admin-beach-live', component: () => import('../views/admin/BeachLiveDashboardView.vue'), meta: { title: 'لوحة الشاطئ الحيّة' } },
      { path: 'e-invoice', name: 'admin-e-invoice', component: () => import('../views/admin/EInvoiceView.vue'), meta: { title: 'الفاتورة الإلكترونية' } },
      { path: 'inventory', name: 'admin-inventory', component: () => import('../views/admin/InventoryView.vue'), meta: { title: 'المخزون' } },
      { path: 'crm', name: 'admin-crm', component: () => import('../views/admin/CRMView.vue'), meta: { title: 'إدارة العملاء' } },
      { path: 'settings', name: 'admin-settings', component: () => import('../views/admin/SettingsView.vue'), meta: { requiredRole: 'admin', title: 'الإعدادات' } },
      { path: 'permissions', name: 'admin-permissions', component: () => import('../views/admin/PermissionsView.vue'), meta: { requiredRole: 'super_admin', title: 'الصلاحيات' } },
    ],
  },

  // ── /waiter — FieldLayout (lightweight header, on-floor order-taking) ──
  {
    path: '/waiter',
    component: () => import('../layouts/FieldLayout.vue'),
    meta: { requiresAuth: true, requiredRole: 'waiter' },
    children: [
      { path: '', redirect: '/waiter/tables' },
      { path: 'tables', name: 'waiter-tables', component: () => import('../views/waiter/TablesView.vue') },
      { path: 'order/:tableId', name: 'waiter-order-table', component: () => import('../views/waiter/OrderView.vue'), props: true },
      { path: 'order', name: 'waiter-order', component: () => import('../views/waiter/OrderView.vue') }, // takeaway (no table)
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

  // 2. Role gate — redirect to the user's own home, not a raw 403 page.
  if (to.meta.requiredRole && !auth.hasRole(to.meta.requiredRole)) {
    return homeRouteFor(auth.role)
  }

  return true
})

export default router
