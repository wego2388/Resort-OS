import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('../views/HomeView.vue'), meta: { titleKey: 'marketing.nav.home', descriptionKey: 'marketing.seo.home' } },
    { path: '/dining', component: () => import('../views/DiningView.vue'), meta: { titleKey: 'marketing.nav.dining', descriptionKey: 'marketing.seo.dining' } },
    { path: '/book', component: () => import('../views/BookingView.vue'), meta: { titleKey: 'marketing.booking.title', descriptionKey: 'marketing.seo.booking' } },
    { path: '/confirmation', component: () => import('../views/ConfirmationView.vue'), meta: { titleKey: 'marketing.confirmation.title', descriptionKey: 'marketing.seo.confirmation', noindex: true } },

    // ── Guest QR flows — دُمجت من apps/qr المستقل سابقاً (2026-07-06) ────
    // كل الروابط دي بتوصل للضيف عن طريق مسح QR على طاولة/شمسية، بدون أي
    // تسجيل دخول — راجع OrderView.vue للتفاصيل.
    // DINING_CUTOVER_PLAN.md Batch 6 (2026-07-13): كان المسار
    // `/order/:outlet(restaurant|cafe)/:tableId` (النوع في الـ URL نفسه) —
    // بعد توحيد restaurant/cafe في dining (outlet_type نص مفتوح، مش بس
    // النوعين دول)، الـ QR بيشاور مباشرة على رقم المنفذ (outlet_id) الحقيقي
    // بدل نوعه. ⚠️ يعني أي QR مطبوع قديم بقى غير صالح — لازم إعادة طباعة
    // كل QR الطاولات عبر admin/QRGeneratorView.vue الجديدة.
    //
    // الثلاثة دول noindex عمدًا (Batch 1، 2026-07-21) — صفحات وظيفية
    // بتتوصل بيها بس عبر مسح QR/رابط توكن شخصي، صفر قيمة SEO مستقلة، ومفيش
    // داعي تظهر في نتائج البحث.
    { path: '/order/:outletId(\\d+)/:tableId(\\d+)', component: () => import('../views/OrderView.vue'), meta: { titleKey: 'marketing.pageTitles.order', descriptionKey: 'marketing.seo.order', noindex: true } },
    { path: '/beach/checkin/:reservationId', component: () => import('../views/BeachCheckinView.vue'), meta: { titleKey: 'marketing.pageTitles.beachCheckin', descriptionKey: 'marketing.seo.beachCheckin', noindex: true } },
    { path: '/survey/:token', component: () => import('../views/SurveyView.vue'), meta: { titleKey: 'marketing.pageTitles.survey', descriptionKey: 'marketing.seo.survey', noindex: true } },

    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
