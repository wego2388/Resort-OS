import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { useAuthStore, useModulesStore } from '@resort-os/core'
import router from './router'
import App from './App.vue'
import './assets/main.css'

/**
 * Boot sequence: restore session + fetch enabled modules *before* the
 * router's first navigation resolves.
 *
 * `app.use(router)` triggers the router's initial navigation synchronously
 * (it calls `router.push(currentLocation)` internally) — so if we installed
 * the router right after Pinia and let `fetchUser()`/`fetchEnabled()` run
 * concurrently in the background, the very first `beforeEach` guard could
 * evaluate `auth.isAuthenticated`/`modules.isEnabled()` against stale
 * (empty) state and wrongly bounce a logged-in user to /login. Awaiting the
 * boot work *before* `app.use(router)` guarantees the guard's first run
 * already has real state instead of racing it.
 */
async function main() {
  const app = createApp(App)
  app.use(createPinia())

  const auth = useAuthStore()
  const modules = useModulesStore()

  if (auth.token) {
    try {
      await auth.fetchUser()
      await modules.fetchEnabled()
    } catch {
      // token invalid/expired — clear it, the router guard will bounce to /login
      auth.logout()
    }
  }

  app.use(router)
  app.mount('#app')
}

main()
