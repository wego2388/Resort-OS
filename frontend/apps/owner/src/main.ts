/**
 * Owner PWA — main.ts
 * Boot sequence مطابق لـ el-kheima بدون i18n (الـ owner app عربية فقط)
 * Decision 0004: No cached API data. Theme + text-size are now user
 * preferences (2026-08-17, Mohamed's explicit request) — see main.css's
 * top-of-file comment and useTextScale.ts.
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { useAuthStore, initTheme } from '@resort-os/core'
import router from './router'
import App from './App.vue'
import './assets/main.css'
import { initTextScale } from './composables/useTextScale'

// Applies the saved/system theme preference and the saved text-size
// preference to <html> before first paint — must run before app.mount() to
// avoid a flash of the wrong palette/size (same requirement and mechanism
// as el-kheima's main.ts for initTheme()).
initTheme()
initTextScale()

async function main() {
  const app = createApp(App)
  app.use(createPinia())

  const auth = useAuthStore()

  // T-01: نجدّد access_token من httpOnly cookie عند كل reload
  await auth.initAuth()

  app.use(router)
  app.mount('#app')
}

main()
