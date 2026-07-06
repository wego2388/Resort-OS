import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('../views/HomeView.vue'), meta: { titleKey: 'marketing.nav.home' } },
    { path: '/dining', component: () => import('../views/DiningView.vue'), meta: { titleKey: 'marketing.nav.dining' } },
    { path: '/book', component: () => import('../views/BookingView.vue'), meta: { titleKey: 'marketing.booking.title' } },
    { path: '/confirmation', component: () => import('../views/ConfirmationView.vue'), meta: { titleKey: 'marketing.confirmation.title' } },

    // ── Guest QR flows — دُمجت من apps/qr المستقل سابقاً (2026-07-06) ────
    // كل الروابط دي بتوصل للضيف عن طريق مسح QR على طاولة/شمسية، بدون أي
    // تسجيل دخول — راجع OrderView.vue للتفاصيل.
    { path: '/order/:outlet(restaurant|cafe)/:tableId', component: () => import('../views/OrderView.vue') },
    { path: '/beach/checkin/:reservationId', component: () => import('../views/BeachCheckinView.vue') },
    { path: '/survey/:token', component: () => import('../views/SurveyView.vue') },

    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
