import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('../views/HomeView.vue'), meta: { titleKey: 'marketing.nav.home' } },
    { path: '/dining', component: () => import('../views/DiningView.vue'), meta: { titleKey: 'marketing.nav.dining' } },
    { path: '/book', component: () => import('../views/BookingView.vue'), meta: { titleKey: 'marketing.booking.title' } },
    { path: '/confirmation', component: () => import('../views/ConfirmationView.vue'), meta: { titleKey: 'marketing.confirmation.title' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
