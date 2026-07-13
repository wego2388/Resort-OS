<script setup lang="ts">
// KioskLayout — minimal/fullscreen kitchen display wrapper.
// KDS (apps/kds) previously had *no* layout wrapper at all — its router
// mounted views directly at '/'. This gives it a real (if deliberately
// bare) shell: a thin top strip (clock + logout) then the rest of the
// viewport is the ticket board — no sidebar, no chrome, nothing that
// competes for attention on a wall-mounted display.
//
// DINING_CUTOVER_PLAN.md Batch 4 — the kitchen/bar page-level nav tabs that
// used to live here (routing between separate /kds/kitchen and /kds/bar
// pages) were removed: there is now a single unified /kds/dining screen,
// and station filtering (all/kitchen-group/bar-group/single station) lives
// as in-page tabs on DiningKDSView.vue itself — a second, redundant nav
// layer here would just be confusing (both old tabs would lead to the same
// page now that /kds/kitchen and /kds/bar are redirects).
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@resort-os/core'

const router = useRouter()
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

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-slate-950 text-white flex flex-col" dir="rtl">
    <header class="flex items-center justify-end px-4 py-1.5 bg-slate-900 border-b border-slate-800 flex-shrink-0 text-sm">
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
