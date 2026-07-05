import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import { resolve } from 'path'

export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon-192.png', 'icon-512.png'],
      manifest: {
        name: 'Resort OS',
        short_name: 'Resort OS',
        description: 'نظام إدارة المنتجع المتكامل — نقطة البيع، المطبخ، العمليات، الإدارة، الجرسون، بوابة الموظفين',
        theme_color: '#0B4F8A',
        background_color: '#F9F7F4',
        display: 'standalone',
        start_url: '/',
        scope: '/',
        dir: 'rtl',
        lang: 'ar',
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
        ],
      },
      workbox: {
        // Combined caching rules from the 4 former apps that carried VitePWA
        // (pos/kds/ops/waiter) — admin/portal have no bespoke rules but having
        // the SW installed for them doesn't hurt (app-shell caching only).
        // POST requests (orders) are queued offline via useOfflineQueue()
        // (IndexedDB), not via workbox — these rules only cache GET data so
        // screens still render something if the tab is reopened offline.
        runtimeCaching: [
          {
            // pos: menu/tables/inventory for restaurant, cafe, beach
            urlPattern: /\/api\/v1\/(restaurant|cafe|beach)\/(menu|tables|inventory)/,
            method: 'GET',
            handler: 'NetworkFirst',
            options: {
              cacheName: 'pos-menu-cache',
              networkTimeoutSeconds: 3,
              expiration: { maxEntries: 100, maxAgeSeconds: 86_400 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            // waiter: menu/tables (order-taking on the floor)
            urlPattern: /\/api\/v1\/restaurant\/(menu|tables)/,
            method: 'GET',
            handler: 'NetworkFirst',
            options: {
              cacheName: 'waiter-menu-cache',
              networkTimeoutSeconds: 3,
              expiration: { maxEntries: 100, maxAgeSeconds: 86_400 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            // kds: kitchen/bar ticket screens (WebSocket carries live updates;
            // this is just a GET fallback so the screen isn't blank on reopen)
            urlPattern: /\/api\/v1\/restaurant\/(kds|kitchen)/,
            method: 'GET',
            handler: 'NetworkFirst',
            options: {
              cacheName: 'kds-cache',
              networkTimeoutSeconds: 3,
              expiration: { maxEntries: 50, maxAgeSeconds: 3_600 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            // ops: broad back-office reads (rooms/bookings/housekeeping/inventory)
            urlPattern: /\/api\/v1\/(pms|inventory)\/.*/,
            method: 'GET',
            handler: 'NetworkFirst',
            options: {
              cacheName: 'ops-api-cache',
              networkTimeoutSeconds: 3,
              expiration: { maxEntries: 100, maxAgeSeconds: 3_600 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: { '@': resolve(__dirname, 'src') },
  },
  server: {
    proxy: {
      // ws: true هنا مهم — الـ WebSocket الحقيقي (KDS) مسجّل تحت نفس مسار
      // /api/v1/... زي أي endpoint تاني، مش تحت /ws منفصل. الإعداد القديم
      // (/ws بروكسي لمسار مختلف تمامًا عن مسار الـ backend الحقيقي) كان
      // معناه إن أي اتصال WebSocket من الفرونت إند مستحيل يوصل للباك إند خالص.
      // VITE_API_PROXY_TARGET لو محتاج تشغّل نسخة باك إند تانية على بورت
      // مختلف (بيئة اختبار منفصلة عن السيرفر الرئيسي، بدون ما تلمس القيمة
      // الافتراضية اللي باقي المطورين/الجلسات معتمدين عليها).
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8005',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
