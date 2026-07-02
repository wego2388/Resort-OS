import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('../views/QRLandingView.vue') },
    { path: '/table/:tableId', component: () => import('../views/TableMenuView.vue') },
    { path: '/order/:orderId/confirm', component: () => import('../views/OrderConfirmView.vue') },
    { path: '/beach/checkin/:reservationId', component: () => import('../views/BeachCheckinView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
