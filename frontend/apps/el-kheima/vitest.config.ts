import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// Vitest config kept separate from vite.config.ts on purpose: the app's Vite
// config wires VitePWA (service worker, manifest) which is irrelevant and
// noisy under jsdom. Here we only need the Vue SFC compiler, the `@` alias,
// and a jsdom DOM so components that read/write document.documentElement
// (direction/lang) and localStorage behave like the browser.
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': resolve(__dirname, 'src') },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.{test,spec}.ts'],
    setupFiles: ['src/__tests__/setup.ts'],
    // jsdom leaves a real localStorage + documentElement between tests; the
    // setup file resets them so migration/direction tests never leak state.
    restoreMocks: true,
  },
})
