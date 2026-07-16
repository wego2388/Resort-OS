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
import { useI18n } from 'vue-i18n'
import ShiftPanel from '../components/ShiftPanel.vue'
import GuestAlertsBell from '../components/GuestAlertsBell.vue'
import OperatorSwitchModal from '../components/OperatorSwitchModal.vue'
import LanguageSwitcher from '../components/LanguageSwitcher.vue'
import { ThemeToggle } from '@resort-os/ui'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const { t, locale } = useI18n()
const { isOnline, pendingCount } = useOfflineQueue()

const showOperatorSwitch = ref(false)

const branchName = computed(() => `${t('backoffice.layout.branch')} ${auth.branchId}`)

const currentTime = ref('')
function updateClock() {
  // Clock locale follows UI locale — Arabic gets Arabic-Indic numerals, others get Latin
  currentTime.value = new Date().toLocaleTimeString(
    locale.value === 'ar' ? 'ar-EG' : 'en-GB',
    { hour: '2-digit', minute: '2-digit', hour12: locale.value === 'ar' },
  )
}
let clockInterval: ReturnType<typeof setInterval> | null = null
onMounted(() => { updateClock(); clockInterval = setInterval(updateClock, 1000) })
onUnmounted(() => { if (clockInterval) clearInterval(clockInterval) })

// DINING_CUTOVER_PLAN.md Batch 4 — role-based بدل path-based
const isWaiter = computed(() => auth.role === 'waiter')

const allNavItems = computed(() => [
  { path: '/pos/beach',     label: t('backoffice.nav.beachPos'),  icon: '🏖️', minRole: 'cashier' },
  { path: '/pos/beach-map', label: t('backoffice.nav.beachMap'),  icon: '🗺️', minRole: 'cashier' },
  { path: '/pos/dining',    label: t('backoffice.nav.diningPos'), icon: '🍽️', minRole: 'waiter' },
  { path: '/pos/shift',     label: t('backoffice.nav.shift'),     icon: '🧾', minRole: 'cashier' },
])

const navItems = computed(() => allNavItems.value.filter(item => auth.hasRole(item.minRole)))

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <!--
    POS dark theme — warm dark navy (#1E2530) بيقلل إرهاق العين للكاشير
    اللي بيشتغل 8+ ساعات على الشاشة في الشمس.
    CSS vars محدّدة هنا تنتقل تلقائياً لكل الـ POS views عبر CSS inheritance.
  -->
  <div
    class="min-h-screen flex flex-col"
    :dir="locale === 'ar' ? 'rtl' : 'ltr'"
    style="
      background: #1E2530;
      --pos-bg: #1E2530;
      --pos-surface: #252D3A;
      --pos-surface-2: #2E3748;
      --pos-border: #374151;
      --pos-text: #F9FAFB;
      --pos-text-muted: #9CA3AF;
      --pos-accent: #C9963C;
      --pos-accent-bg: rgba(201,150,60,0.15);
      --pos-success: #10B981;
      --pos-danger: #F87171;
    "
  >
    <!-- ── Header ── -->
    <header style="background:#252D3A; border-bottom:1px solid #374151;" class="flex-shrink-0 shadow-elevation-2">
      <div class="flex items-center justify-between px-4 py-2.5">

        <!-- Logo + title -->
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 shadow-elevation-1"
            style="background:#C9963C;">
            <span class="text-white text-xs font-black">{{ isWaiter ? '🧑🍳' : 'POS' }}</span>
          </div>
          <div>
            <div class="font-bold text-sm leading-tight" style="color:#F9FAFB;">
              {{ isWaiter ? t('backoffice.layout.orderTaker') : t('backoffice.layout.pos') }}
            </div>
            <div class="text-xs leading-tight" style="color:#9CA3AF;">{{ branchName }}</div>
          </div>
        </div>

        <!-- Actions -->
        <div class="flex items-center gap-3">
          <!-- Shift panel — كاشير+ فقط -->
          <ShiftPanel v-if="auth.hasRole('cashier')" />

          <!-- Guest alerts bell -->
          <GuestAlertsBell />

          <!-- Connectivity dot -->
          <div class="flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full"
              :class="isOnline ? 'bg-[#10B981]' : 'bg-amber-500 animate-pulse'" />
            <span v-if="pendingCount > 0"
              class="text-xs font-bold px-1.5 py-0.5 rounded-full"
              style="color:#FBBF24; background:rgba(120,80,0,0.3);">
              {{ pendingCount }}
            </span>
          </div>

          <!-- Clock — gold لجذب الانتباه -->
          <div class="text-sm font-mono font-bold tabular-nums px-3 py-1 rounded-lg border"
            style="color:#C9963C; background:#2E3748; border-color:#374151;"
            dir="ltr">
            {{ currentTime }}
          </div>

          <!-- User info -->
          <button
            @click="showOperatorSwitch = true"
            class="hidden sm:flex flex-col items-end rounded-lg px-1.5 py-0.5 transition-colors"
            style="hover:background:#2E3748;"
          >
            <span class="text-sm font-medium" style="color:#F9FAFB;">{{ auth.user?.full_name }}</span>
            <span class="text-xs" style="color:#C9963C;">{{ auth.role }}</span>
          </button>

          <LanguageSwitcher variant="compact" />
          <ThemeToggle />

          <button
            @click="logout"
            class="text-sm font-medium px-2 py-1 rounded transition-colors"
            style="color:#F87171;"
          >{{ t('backoffice.layout.logout') }}</button>
        </div>
      </div>

      <OperatorSwitchModal v-if="showOperatorSwitch" @close="showOperatorSwitch = false" />

      <!-- ── Nav tabs ── -->
      <nav v-if="navItems.length" class="flex overflow-x-auto"
        style="border-top:1px solid #374151;">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-semibold transition-colors min-w-[80px]"
          :style="route.path === item.path
            ? 'background:#C9963C; color:#FFFFFF;'
            : 'color:#9CA3AF;'"
        >
          <span>{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
    </header>

    <!-- ── Content ── -->
    <main class="flex-1 overflow-auto">
      <RouterView />
    </main>

  </div>
</template>
