<script setup lang="ts">
// FieldLayout — lightweight, mobile/tablet-first header for on-floor use.
// Covers /pos/* (cashier terminals) and /waiter/* (order-taking on the floor).
// Adapted from apps/pos's AppLayout.vue, merged with apps/waiter's
// connectivity indicator (useOfflineQueue) since both apps queue orders
// offline via the same composable.
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@resort-os/core'
import { useOfflineQueue } from '@resort-os/core/composables'
import ShiftPanel from '../components/ShiftPanel.vue'
import GuestAlertsBell from '../components/GuestAlertsBell.vue'
import OperatorSwitchModal from '../components/OperatorSwitchModal.vue'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const { isOnline, pendingCount } = useOfflineQueue()

const showOperatorSwitch = ref(false)

const branchName = computed(() => `فرع ${auth.branchId}`)

const currentTime = ref('')
function updateClock() {
  currentTime.value = new Date().toLocaleTimeString('ar-EG', {
    hour: '2-digit', minute: '2-digit', hour12: true,
  })
}
let clockInterval: ReturnType<typeof setInterval> | null = null
onMounted(() => { updateClock(); clockInterval = setInterval(updateClock, 1000) })
onUnmounted(() => { if (clockInterval) clearInterval(clockInterval) })

const isWaiter = computed(() => route.path.startsWith('/waiter'))

const allNavItems = [
  { path: '/pos/beach', label: 'الشاطئ', icon: '🏖️' },
  { path: '/pos/beach-map', label: 'خريطة الشاطئ', icon: '🗺️' },
  { path: '/pos/restaurant', label: 'المطعم', icon: '🍽️' },
  { path: '/pos/cafe', label: 'الكافيه', icon: '☕' },
  { path: '/waiter/tables', label: 'الطاولات', icon: '🧑‍🍳' },
]

// Nav is scoped to the active section (pos vs waiter).
const navItems = computed(() =>
  allNavItems.filter((item) => item.path.startsWith(isWaiter.value ? '/waiter' : '/pos')),
)

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-resort-bg flex flex-col" dir="rtl">

    <header class="bg-white border-b border-resort-border shadow-sm flex-shrink-0">
      <div class="flex items-center justify-between px-4 py-2.5">

        <div class="flex items-center gap-3">
          <div class="w-8 h-8 bg-blue-700 rounded-lg flex items-center justify-center flex-shrink-0">
            <span class="text-white text-xs font-black">{{ isWaiter ? '🧑‍🍳' : 'POS' }}</span>
          </div>
          <div>
            <div class="font-bold text-gray-900 text-sm leading-tight">{{ isWaiter ? 'أوردر تيكر' : 'نقطة البيع' }}</div>
            <div class="text-xs text-gray-400 leading-tight">{{ branchName }}</div>
          </div>
        </div>

        <div class="flex items-center gap-4">
          <!-- Cashier shift open/close + cash count — POS section only.
               راجع components/ShiftPanel.vue للسبب الكامل: الباك إند كان
               عنده دورة وردية كاملة من غير أي واجهة تستخدمها. -->
          <ShiftPanel v-if="!isWaiter && auth.hasRole('cashier')" />

          <!-- تنبيهات الضيوف (نادِ الجرسون / هات الفاتورة) — ظاهرة لأي حد
               بيشتغل على الأرض (نادل أو كاشير)، مش بس النادل. -->
          <GuestAlertsBell />

          <!-- Connectivity dot (offline order queue) -->
          <div class="flex items-center gap-1.5" :title="isOnline ? 'متصل' : 'غير متصل'">
            <span class="w-2 h-2 rounded-full" :class="isOnline ? 'bg-green-500' : 'bg-amber-500 animate-pulse'" />
            <span v-if="pendingCount > 0" class="text-xs font-bold text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded-full">
              {{ pendingCount }}
            </span>
          </div>

          <div class="text-sm font-mono font-semibold text-gray-700 bg-gray-100 px-3 py-1 rounded-lg tabular-nums" dir="ltr">
            {{ currentTime }}
          </div>

          <button
            @click="showOperatorSwitch = true"
            class="hidden sm:flex flex-col items-end hover:bg-gray-50 rounded-lg px-1.5 py-0.5 transition-colors"
            title="تبديل المشغّل"
          >
            <span class="text-sm font-medium text-gray-700">{{ auth.user?.full_name }}</span>
            <span class="text-xs text-blue-600">{{ auth.role }} · تبديل ↔</span>
          </button>

          <button
            @click="logout"
            class="text-sm text-red-600 hover:text-red-700 font-medium px-2 py-1 rounded hover:bg-red-50 transition-colors"
          >خروج</button>
        </div>
      </div>

      <OperatorSwitchModal v-if="showOperatorSwitch" @close="showOperatorSwitch = false" />

      <nav v-if="navItems.length" class="flex border-t border-resort-border overflow-x-auto">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-medium transition-colors"
          :class="route.path === item.path
            ? 'bg-blue-700 text-white'
            : 'text-gray-600 hover:bg-gray-50'"
        >
          <span>{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
    </header>

    <main class="flex-1 overflow-auto">
      <RouterView />
    </main>

  </div>
</template>
