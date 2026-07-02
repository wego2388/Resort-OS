<script setup lang="ts">
// KioskLayout — minimal/fullscreen kitchen display wrapper.
// KDS (apps/kds) previously had *no* layout wrapper at all — its router
// mounted views directly at '/'. This gives it a real (if deliberately
// bare) shell for the first time: a thin top strip to switch kitchen/bar
// and log out, then the rest of the viewport is the ticket board — no
// sidebar, no chrome, nothing that competes for attention on a wall-mounted
// display.
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@resort-os/core'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const currentTime = ref('')
function updateClock() {
  currentTime.value = new Date().toLocaleTimeString('ar-EG', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
  })
}
let clockInterval: ReturnType<typeof setInterval> | null = null
onMounted(() => { updateClock(); clockInterval = setInterval(updateClock, 1000) })
onUnmounted(() => { if (clockInterval) clearInterval(clockInterval) })

const navItems = [
  { path: '/kds/kitchen', label: 'المطبخ', icon: '🍳' },
  { path: '/kds/bar', label: 'البار', icon: '🍹' },
]

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-slate-950 text-white flex flex-col" dir="rtl">
    <header class="flex items-center justify-between px-4 py-1.5 bg-slate-900 border-b border-slate-800 flex-shrink-0 text-sm">
      <div class="flex items-center gap-2">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="px-3 py-1 rounded-lg font-bold transition-colors"
          :class="route.path === item.path ? 'bg-blue-700 text-white' : 'text-slate-400 hover:bg-slate-800'"
        >{{ item.icon }} {{ item.label }}</RouterLink>
      </div>
      <div class="flex items-center gap-4">
        <span class="font-mono tabular-nums text-slate-300" dir="ltr">{{ currentTime }}</span>
        <button @click="logout" class="text-red-400 hover:text-red-300 font-medium">خروج</button>
      </div>
    </header>
    <main class="flex-1 overflow-auto">
      <RouterView />
    </main>
  </div>
</template>
