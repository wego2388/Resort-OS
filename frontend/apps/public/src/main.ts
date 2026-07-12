import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { initTheme } from '@resort-os/core'
import i18n from '@resort-os/core/i18n'
import router from './router'
import App from './App.vue'
import { marketingMessages } from './i18n/marketing'
import './assets/main.css'

// See apps/el-kheima/src/main.ts for the full rationale — same Design
// System dark-mode bootstrap, kept in sync between both apps.
initTheme()

// Merge this app's marketing-copy keys (hero/rooms/footer/etc, under the
// `marketing` namespace) into the shared i18n instance for every supported
// locale — see src/i18n/marketing.ts for why this lives here instead of in
// packages/core (keeps qr/el-kheima bundles free of public-site copy).
for (const [locale, messages] of Object.entries(marketingMessages)) {
  i18n.global.mergeLocaleMessage(locale, messages)
}

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)
app.mount('#app')
