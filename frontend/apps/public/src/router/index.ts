import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  // Batch 2 fix (2026-07-21): the header's "Rooms" nav link is `#rooms`
  // (Home's own in-page anchor) — with no scrollBehavior, clicking it from
  // any page other than Home was a dead no-op (no element with that id
  // exists there). Cross-page hash navigation now scrolls to the target
  // once the destination page has mounted; same-page hash clicks keep
  // working via the browser's native anchor behavior.
  scrollBehavior(to) {
    if (to.hash) return { el: to.hash, behavior: 'smooth' }
    return { top: 0 }
  },
  routes: [
    { path: '/', component: () => import('../views/HomeView.vue'), meta: { titleKey: 'marketing.nav.home', descriptionKey: 'marketing.seo.home' } },
    { path: '/dining', component: () => import('../views/DiningView.vue'), meta: { titleKey: 'marketing.nav.dining', descriptionKey: 'marketing.seo.dining' } },
    { path: '/book', component: () => import('../views/BookingView.vue'), meta: { titleKey: 'marketing.booking.title', descriptionKey: 'marketing.seo.booking' } },
    { path: '/confirmation', component: () => import('../views/ConfirmationView.vue'), meta: { titleKey: 'marketing.confirmation.title', descriptionKey: 'marketing.seo.confirmation', noindex: true } },

    // ── Batch 2 (Public Phase 0 migration, 2026-07-21) — didn't exist at
    // all before this batch (only the 4 routes above did).
    { path: '/about', component: () => import('../views/AboutView.vue'), meta: { titleKey: 'marketing.nav.about', descriptionKey: 'marketing.seo.about' } },
    { path: '/contact', component: () => import('../views/ContactView.vue'), meta: { titleKey: 'marketing.pages.contact.title', descriptionKey: 'marketing.seo.contact' } },
    { path: '/faq', component: () => import('../views/FaqView.vue'), meta: { titleKey: 'marketing.pages.faq.title', descriptionKey: 'marketing.seo.faq' } },
    { path: '/privacy', component: () => import('../views/PrivacyView.vue'), meta: { titleKey: 'marketing.pages.privacy.title', descriptionKey: 'marketing.seo.privacy' } },
    { path: '/terms', component: () => import('../views/TermsView.vue'), meta: { titleKey: 'marketing.pages.terms.title', descriptionKey: 'marketing.seo.terms' } },

    // ── Batch 3 (Public Phase 0 migration, 2026-07-21) — Beach and Packages
    // ship with real, sourced content; Events and Gallery ship as page
    // shells with a "content pending" notice (no verified event-package
    // detail or real resort photography in this repo — see each view's
    // header comment).
    { path: '/beach', component: () => import('../views/BeachView.vue'), meta: { titleKey: 'marketing.nav.beach', descriptionKey: 'marketing.seo.beach' } },
    { path: '/packages', component: () => import('../views/PackagesView.vue'), meta: { titleKey: 'marketing.nav.packages', descriptionKey: 'marketing.seo.packages' } },
    { path: '/events', component: () => import('../views/EventsView.vue'), meta: { titleKey: 'marketing.nav.events', descriptionKey: 'marketing.seo.events' } },
    { path: '/gallery', component: () => import('../views/GalleryView.vue'), meta: { titleKey: 'marketing.nav.gallery', descriptionKey: 'marketing.seo.gallery' } },

    // ── Guest QR flows — دُمجت من apps/qr المستقل سابقاً (2026-07-06) ────
    // كل الروابط دي بتوصل للضيف عن طريق مسح QR على طاولة/شمسية، بدون أي
    // تسجيل دخول — راجع OrderView.vue للتفاصيل.
    // Gate 8: `/s/:token` is the only guest-service route. Branch, table,
    // and the allowed outlets are derived server-side and never appear in
    // the printed URL.
    //
    // الثلاثة دول noindex عمدًا (Batch 1، 2026-07-21) — صفحات وظيفية
    // بتتوصل بيها بس عبر مسح QR/رابط توكن شخصي، صفر قيمة SEO مستقلة، ومفيش
    // داعي تظهر في نتائج البحث.
    { path: '/s/:token', component: () => import('../views/OrderView.vue'), meta: { titleKey: 'marketing.pageTitles.order', descriptionKey: 'marketing.seo.order', noindex: true } },
    { path: '/beach/checkin/:reservationId', component: () => import('../views/BeachCheckinView.vue'), meta: { titleKey: 'marketing.pageTitles.beachCheckin', descriptionKey: 'marketing.seo.beachCheckin', noindex: true } },
    { path: '/survey/:token', component: () => import('../views/SurveyView.vue'), meta: { titleKey: 'marketing.pageTitles.survey', descriptionKey: 'marketing.seo.survey', noindex: true } },

    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
