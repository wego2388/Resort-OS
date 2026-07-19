import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { useAuthStore, initTheme } from '@resort-os/core'
import { staffI18n, staffLocale } from '@resort-os/core/i18n/staff'
import router from './router'
import App from './App.vue'
import './assets/main.css'

// Applies the saved/system dark-mode preference to <html class="dark"> before
// first paint — see packages/core/src/composables/useTheme.ts. No screen
// opts into the `.dark` tokens yet (no ThemeToggle is mounted anywhere), so
// this is a visual no-op today beyond making the mechanism real/testable.
initTheme()

/**
 * Boot sequence — order matters:
 *   1. Pinia (stores depend on it)
 *   2. i18n (staff-scoped: ar/en only — see @resort-os/core staffLocale)
 *   3. Auth session (must resolve before router's first beforeEach runs)
 *   4. Router (first navigation fires synchronously on app.use(router))
 *   5. Mount
 *
 * Gate 3A: the staff app installs its OWN i18n instance (`staffI18n`) with an
 * ar/en allow-list and a namespaced storage key — fully independent from the
 * public app's shared singleton. `staffLocale` already resolved and applied
 * `<html lang/dir>` at import time (namespaced key → one-time legacy migration
 * → `ar` fallback), so there is no flash of the wrong direction before Vue
 * hydrates — no `document.body.dir` and no global CSS `direction` rule. After
 * the auth session resolves, the signed-in user's server `preferred_language`
 * becomes the source of truth (kept applied by useStaffLocaleSync in App.vue).
 */
async function main() {
  const app = createApp(App)
  app.use(createPinia())
  app.use(staffI18n)

  const auth = useAuthStore()

  // T-01: access_token مش في localStorage تاني — نجدّده من httpOnly cookie
  // عبر POST /auth/refresh عند كل reload. لو ما فيش cookie صالح (جلسة منتهية
  // أو أول مرة) يرجع false والـ router guard بيودّي /login.
  await auth.initAuth()

  // Reconcile to the signed-in user's saved language before first paint. When
  // signed out, the pre-login namespaced preference already applied at import.
  if (auth.user?.preferred_language) {
    // Authenticated account preference controls this session but must not
    // overwrite the terminal's separate pre-login/login-screen preference.
    await staffLocale.setLocale(auth.user.preferred_language, { persist: false })
  }

  app.use(router)
  app.mount('#app')
}

main()
