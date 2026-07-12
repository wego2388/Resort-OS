import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { useAuthStore, i18n, getSavedLocale, initTheme } from '@resort-os/core'
import router from './router'
import App from './App.vue'
import './assets/main.css'

// Applies the saved/system dark-mode preference to <html class="dark"> before
// first paint — see packages/core/src/composables/useTheme.ts. No screen
// opts into the `.dark` tokens yet (no ThemeToggle is mounted anywhere), so
// this is a visual no-op today beyond making the mechanism real/testable —
// exactly what "real working dark mode" (Design System Phase 1) requires.
initTheme()

/**
 * Boot sequence — order matters:
 *   1. Pinia (stores depend on it)
 *   2. i18n (locale restored from localStorage before any template renders)
 *   3. Auth session (must resolve before router's first beforeEach runs)
 *   4. Router (first navigation fires synchronously on app.use(router))
 *   5. Mount
 *
 * i18n is installed before the router so route titles and any SSR-style
 * pre-render calls that reference $t() already have a valid locale.
 * getSavedLocale() is called inside createI18n in packages/core/src/i18n/index.ts
 * so the locale is already set — no extra async call needed here.
 */
async function main() {
  const app = createApp(App)
  app.use(createPinia())
  app.use(i18n)

  // Apply dir/lang to <html> immediately from saved locale — avoids a brief
  // flash of RTL→LTR or the wrong lang attribute before Vue hydrates.
  const locale = getSavedLocale()
  document.documentElement.lang = locale
  document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr'
  document.body.dir = locale === 'ar' ? 'rtl' : 'ltr'

  const auth = useAuthStore()

  if (auth.token) {
    try {
      await auth.fetchUser()
    } catch {
      // token invalid/expired — clear it, the router guard will bounce to /login
      auth.logout()
    }
  }

  app.use(router)
  app.mount('#app')
}

main()
