/**
 * owner app router — Decision 0004 §Isolation model item 2.
 *
 * كل route محمية بـ requiredRoles: ['owner', 'super_admin'].
 * Fail-closed: أي role آخر → /login.
 * super_admin يعدي دائماً (Decision 0003 invariant #1).
 */
import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '@resort-os/core';
const ALLOWED_ROLES = new Set(['owner', 'super_admin']);
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
            meta: { public: true },
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
            ],
        },
        // fallback
        { path: '/:pathMatch(.*)*', redirect: '/' },
    ],
});
router.beforeEach(async (to) => {
    const auth = useAuthStore();
    // routes عامة — لا تحقق
    if (to.meta.public) {
        // لو متسجّل دخول بالفعل → الرئيسية
        if (auth.isAuthenticated && ALLOWED_ROLES.has(auth.role)) {
            return '/';
        }
        return true;
    }
    // غير متسجّل → /login
    if (!auth.isAuthenticated || !auth.user) {
        return '/login';
    }
    // 2FA مطلوب → /2fa-setup
    if (auth.needsTwoFactorSetup) {
        return '/2fa-setup';
    }
    // تحقق Role — fail-closed: فقط owner أو super_admin
    if (!ALLOWED_ROLES.has(auth.role)) {
        return '/login';
    }
    return true;
});
export default router;
