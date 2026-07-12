import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { useAuthStore, initTheme } from '@resort-os/core'
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
 * Boot sequence: restore session *before* the router's first navigation
 * resolves.
 *
 * `app.use(router)` triggers the router's initial navigation synchronously
 * (it calls `router.push(currentLocation)` internally) — so if we installed
 * the router right after Pinia and let `fetchUser()` run concurrently in the
 * background, the very first `beforeEach` guard could evaluate
 * `auth.isAuthenticated` against stale (empty) state and wrongly bounce a
 * logged-in user to /login. Awaiting the boot work *before* `app.use(router)`
 * guarantees the guard's first run already has real state instead of racing it.
 */
async function main() {
  const app = createApp(App)
  app.use(createPinia())

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
