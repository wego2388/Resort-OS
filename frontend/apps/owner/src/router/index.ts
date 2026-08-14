/**
 * owner app router — Decision 0004 §Isolation model item 2.
 *
 * كل route محمية بـ requiredRoles: ['owner', 'super_admin'].
 * Fail-closed: أي role آخر → /login.
 * super_admin يعدي دائماً (Decision 0003 invariant #1).
 */
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@resort-os/core'

const ALLOWED_ROLES = new Set(['owner', 'super_admin'])

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      component: () => import('../views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/2fa-setup',
      component: () => import('../views/TwoFactorSetupView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/change-temporary-password',
      component: () => import('../views/ForcePasswordChangeView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/',
      component: () => import('../views/AppShell.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          redirect: '/now',
        },
        {
          path: 'now',
          name: 'now',
          component: () => import('../views/NowScreen.vue'),
          meta: { requiresAuth: true, title: 'الآن' },
        },
        {
          path: 'performance',
          name: 'performance',
          component: () => import('../views/PerformanceScreen.vue'),
          meta: { requiresAuth: true, title: 'الأداء' },
        },
        {
          path: 'sales',
          name: 'sales',
          component: () => import('../views/SalesScreen.vue'),
          meta: { requiresAuth: true, title: 'المبيعات' },
        },
        {
          path: 'expenses',
          name: 'expenses',
          component: () => import('../views/ExpensesScreen.vue'),
          meta: { requiresAuth: true, title: 'المصروفات' },
        },
        {
          path: 'shifts',
          name: 'shifts',
          component: () => import('../views/ShiftsScreen.vue'),
          meta: { requiresAuth: true, title: 'الورديات' },
        },
        {
          path: 'hr',
          name: 'hr',
          component: () => import('../views/HRScreen.vue'),
          meta: { requiresAuth: true, title: 'الموظفين' },
        },
      ],
    },
    // fallback
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (!auth.isAuthenticated || !auth.user) {
    if (to.meta.public) return true
    return '/login'
  }

  // تحقق Role — fail-closed: فقط owner أو super_admin
  if (!ALLOWED_ROLES.has(auth.role)) {
    if (to.path === '/login') return true
    return '/login'
  }

  // Temporary credentials must be replaced before any other route.
  if (auth.needsPasswordChange && to.path !== '/change-temporary-password') {
    return '/change-temporary-password'
  }

  // Mandatory 2FA comes after the temporary password has been replaced.
  if (!auth.needsPasswordChange && auth.needsTwoFactorSetup && to.path !== '/2fa-setup') {
    return '/2fa-setup'
  }

  if (to.path === '/login') return '/'
  if (to.path === '/change-temporary-password' && !auth.needsPasswordChange) {
    return auth.needsTwoFactorSetup ? '/2fa-setup' : '/'
  }
  if (to.path === '/2fa-setup' && !auth.needsTwoFactorSetup) return '/'

  return true
})

export default router
