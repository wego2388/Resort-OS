/**
 * Owner PWA — main.ts
 * Boot sequence مطابق لـ el-kheima بدون i18n (الـ owner app عربية فقط)
 * Decision 0004: No cached API data. Dark mode always on.
 */
import { createApp } from 'vue';
import { createPinia } from 'pinia';
import { useAuthStore } from '@resort-os/core';
import router from './router';
import App from './App.vue';
import './assets/main.css';
async function main() {
    const app = createApp(App);
    app.use(createPinia());
    const auth = useAuthStore();
    // T-01: نجدّد access_token من httpOnly cookie عند كل reload
    await auth.initAuth();
    app.use(router);
    app.mount('#app');
}
main();
