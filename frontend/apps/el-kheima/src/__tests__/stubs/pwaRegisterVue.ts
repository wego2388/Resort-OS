// Test-only stand-in for the 'virtual:pwa-register/vue' module VitePWA
// registers in a real build (excluded from vitest.config.ts — see its
// comment). Any spec exercising a component that imports the real virtual
// module overrides this via vi.mock('virtual:pwa-register/vue', ...).
import { ref } from 'vue'

export function useRegisterSW() {
  return {
    needRefresh: ref(false),
    offlineReady: ref(false),
    updateServiceWorker: async () => {},
  }
}
