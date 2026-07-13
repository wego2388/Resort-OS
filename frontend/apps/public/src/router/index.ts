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
    // DINING_CUTOVER_PLAN.md Batch 6 (2026-07-13): كان المسار
    // `/order/:outlet(restaurant|cafe)/:tableId` (النوع في الـ URL نفسه) —
    // بعد توحيد restaurant/cafe في dining (outlet_type نص مفتوح، مش بس
    // النوعين دول)، الـ QR بيشاور مباشرة على رقم المنفذ (outlet_id) الحقيقي
    // بدل نوعه. ⚠️ يعني أي QR مطبوع قديم بقى غير صالح — لازم إعادة طباعة
    // كل QR الطاولات عبر admin/QRGeneratorView.vue الجديدة.
    { path: '/order/:outletId(\\d+)/:tableId(\\d+)', component: () => import('../views/OrderView.vue') },
    { path: '/beach/checkin/:reservationId', component: () => import('../views/BeachCheckinView.vue') },
    { path: '/survey/:token', component: () => import('../views/SurveyView.vue') },

    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
