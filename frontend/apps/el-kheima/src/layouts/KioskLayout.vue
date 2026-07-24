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
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'

const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()
const { formatTime } = useStaffFormat()

const currentTime = ref('')
function updateClock() {
  // Central locale-aware formatter (tabular Latin digits for a legible
  // wall-mounted clock in either language).
  currentTime.value = formatTime(new Date(), {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
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
  <!-- Direction inherited from <html dir> (central staff locale controller). -->
  <div class="min-h-screen bg-slate-950 text-white flex flex-col">
    <header class="flex items-center justify-end px-4 py-1.5 bg-slate-900 border-b border-slate-800 flex-shrink-0 text-sm">
      <div class="flex items-center gap-4">
        <!-- dir="ltr": a clock is a fixed HH:MM:SS numeric token, not directional text. -->
        <span class="font-mono tabular-nums text-slate-300" dir="ltr">{{ currentTime }}</span>
        <button @click="logout" class="text-red-400 hover:text-red-300 font-medium">{{ t('backoffice.layout.logout') }}</button>
      </div>
    </header>
    <main class="flex-1 overflow-auto">
      <RouterView v-slot="{ Component, route: r }">
        <Transition name="page" mode="out-in" :duration="{ enter: 160, leave: 80 }">
          <component :is="Component" :key="r.fullPath" />
        </Transition>
      </RouterView>
    </main>
  </div>
</template>

<style scoped>
@media (prefers-reduced-motion: no-preference) {
  .page-enter-active { transition: opacity 160ms ease; }
  .page-leave-active { transition: opacity 80ms ease; }
  .page-enter-from   { opacity: 0; }
  .page-leave-to     { opacity: 0; }
}
</style>
