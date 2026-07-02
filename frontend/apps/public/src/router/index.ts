import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('../views/HomeView.vue') },
    { path: '/book', component: () => import('../views/BookingView.vue') },
    { path: '/confirmation', component: () => import('../views/ConfirmationView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
