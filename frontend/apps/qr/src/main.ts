import { createApp } from 'vue'
import { createPinia } from 'pinia'
import i18n from '@resort-os/core/i18n'
import router from './router'
import App from './App.vue'
import './assets/main.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)
app.mount('#app')
