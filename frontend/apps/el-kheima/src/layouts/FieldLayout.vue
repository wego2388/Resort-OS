<script setup lang="ts">
// FieldLayout — lightweight, mobile/tablet-first header for on-floor use.
// Covers /pos/* (cashier terminals) and /waiter/* (order-taking on the floor).
// Adapted from apps/pos's AppLayout.vue, merged with apps/waiter's
// connectivity indicator (useOfflineQueue) since both apps queue orders
// offline via the same composable.
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
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
const { t } = useI18n()
const { formatTime } = useStaffFormat()
const { isOnline, pendingCount } = useOfflineQueue()

const showOperatorSwitch = ref(false)

const branchName = computed(() => auth.branchId ? `${t('backoffice.layout.branch')} ${auth.branchId}` : t('backoffice.layout.branch'))

const currentTime = ref('')
function updateClock() {
  // Locale-aware time via the central formatter (tabular Latin digits for an
  // unambiguous, column-stable operational clock in both languages).
  currentTime.value = formatTime(new Date())
}
let clockInterval: ReturnType<typeof setInterval> | null = null
onMounted(() => { updateClock(); clockInterval = setInterval(updateClock, 1000) })
onUnmounted(() => { if (clockInterval) clearInterval(clockInterval) })

// DINING_CUTOVER_PLAN.md Batch 4 — role-based بدل path-based
const isWaiter = computed(() => auth.role === 'waiter')

// 2026-08-11: باج UX حقيقي رفعه Mohamed (سكرين شوت من /pos/dining) — سكرول
// المنيو كان بيسحب الصفحة كلها معاه (بما فيها سلة/إتمام البيع)، لأن الشل هنا
// كان min-h-screen (بينمو من غير سقف) والـ<main> overflow-auto من غير min-h-0
// — يعني أي شاشة ابنة (POS المطعم/الشاطئ) مبنية أصلاً بمنطقة سكرول داخلية
// خاصة بيها (قايمة أصناف تتسكرول، سلة/checkout ثابتة) كانت بتفقد الاحتواء ده
// لأن الأب كان بيدّعي السكرول لنفسه بدل ما يسيبه للابن. راجع scrollMode في
// router/index.ts — الشاشات المبنية بمنطقة سكرول داخلية (pos-beach/pos-dining)
// بس هي اللي محتاجة الاحتواء ده؛ خريطة الشاطئ ولوحات الورديات مبنية على سكرول
// صفحة عادي فباقية على الافتراضي.
const mainScrollClass = computed(() =>
  route.meta.scrollMode === 'contained' ? 'overflow-hidden' : 'overflow-auto',
)

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
  <!-- Direction is inherited from <html dir> (set centrally by the staff
       locale controller) — no per-component dir override. -->
  <div class="field-shell flex h-dvh flex-col overflow-hidden">
    <!-- ── Header ── -->
    <header class="flex-shrink-0 border-b border-stone-200 bg-white shadow-elevation-2 dark:border-gray-700 dark:bg-[#252D3A]">
      <div class="flex min-h-16 items-center justify-between gap-2 px-3 py-2 sm:px-4">

        <!-- Logo + title -->
        <div class="flex items-center gap-3">
          <div class="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-gold-DEFAULT shadow-elevation-1">
            <span class="text-white text-xs font-black">{{ isWaiter ? '🧑🍳' : 'POS' }}</span>
          </div>
          <div>
            <div class="text-sm font-bold leading-tight text-gray-900 dark:text-gray-50">
              {{ isWaiter ? t('backoffice.layout.orderTaker') : t('backoffice.layout.pos') }}
            </div>
            <div class="text-xs leading-tight text-gray-500 dark:text-gray-400">{{ branchName }}</div>
          </div>
        </div>

        <!-- Actions -->
        <div class="flex items-center gap-1 sm:gap-2">
          <!-- Shift panel — كاشير+ فقط -->
          <ShiftPanel v-if="auth.hasRole('cashier')" />

          <!-- Guest alerts bell -->
          <GuestAlertsBell />

          <!-- Connectivity dot -->
          <div class="flex items-center gap-1.5">
            <span class="h-2.5 w-2.5 rounded-full"
              :class="isOnline ? 'bg-[#10B981]' : 'bg-amber-500 animate-pulse'" />
            <span v-if="pendingCount > 0"
              class="rounded-full bg-amber-100 px-1.5 py-0.5 text-xs font-bold text-amber-800 dark:bg-amber-950/60 dark:text-amber-300">
              {{ pendingCount }}
            </span>
          </div>

          <!-- Clock — gold لجذب الانتباه -->
          <div class="hidden min-h-11 items-center rounded-xl border border-stone-200 bg-stone-50 px-3 font-mono text-sm font-bold tabular-nums text-amber-700 dark:border-gray-600 dark:bg-[#2E3748] dark:text-amber-300 md:flex"
            dir="ltr">
            {{ currentTime }}
          </div>

          <!-- User info -->
          <button
            @click="showOperatorSwitch = true"
            type="button"
            class="hidden min-h-11 flex-col items-end justify-center rounded-xl px-2 transition-colors hover:bg-stone-100 dark:hover:bg-[#2E3748] sm:flex"
          >
            <span class="text-sm font-medium text-gray-900 dark:text-gray-50">{{ auth.user?.full_name }}</span>
            <span class="text-xs text-amber-700 dark:text-amber-300">{{ auth.role }}</span>
          </button>

          <LanguageSwitcher variant="compact" />
          <ThemeToggle
            :light-label="t('backoffice.layout.switchLight')"
            :dark-label="t('backoffice.layout.switchDark')"
          />

          <button
            @click="logout"
            class="min-h-11 rounded-xl px-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-950/40"
          >{{ t('backoffice.layout.logout') }}</button>
        </div>
      </div>

      <OperatorSwitchModal v-if="showOperatorSwitch" @close="showOperatorSwitch = false" />

      <!-- ── Nav tabs ── -->
      <nav v-if="navItems.length" class="flex overflow-x-auto border-t border-stone-200 dark:border-gray-700">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="flex min-h-11 min-w-[96px] flex-1 items-center justify-center gap-2 px-3 py-2.5 text-sm font-semibold transition-colors"
          :class="route.path === item.path
            ? 'bg-gold-DEFAULT text-white'
            : 'text-gray-600 hover:bg-stone-100 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-[#2E3748] dark:hover:text-white'"
        >
          <span>{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
    </header>

    <!-- ── Content ── -->
    <main :class="['flex-1 min-h-0', mainScrollClass]">
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
  .page-enter-active { transition: opacity 160ms ease, transform 160ms ease; }
  .page-leave-active { transition: opacity 80ms ease, transform 80ms ease; }
  .page-enter-from   { opacity: 0; transform: translateY(6px); }
  .page-leave-to     { opacity: 0; transform: translateY(-4px); }
}
</style>

<!--
  ⚠️ باج حقيقي اتكشف حي (2026-07-27، فحص تباين الوضع الداكن بمتصفح حقيقي):
  نفس فئة الباج الموثّقة في Drawer.vue تحت — `:global(.dark) .field-shell`
  كان جوه <style scoped> فوق، فـVue's scoped-CSS compiler فقد جزء
  `.field-shell` بالكامل من الـ selector وطلع الناتج المُصرَّف حرفيًا
  `.dark { background: #1e2530; ... }` (بدون أي تقييد بـ.field-shell خالص).
  يعني `.field-shell` في الوضع الداكن فضلت عالقة على خلفيتها الفاتحة
  الافتراضية (#f8fafc) للأبد — أي شاشة جوه FieldLayout من غير خلفية خاصة بيها
  (زي ShiftDashboardView وقت "لا توجد وردية مفتوحة") كانت بتوّرث الخلفية
  الفاتحة العالقة دي، فالنص الأبيض/الفاتح المُعدّ للوضع الداكن (زي
  .section-title's dark:text-gray-100) كان بيترسم على خلفية فاتحة تقريبًا
  بنفس درجته — تباين شبه معدوم، نص غير مقروء عمليًا. الإصلاح: نقل قاعدتي
  .field-shell (الفاتحة والداكنة) لـ<style> غير scoped منفصل، بعيد عن الباج
  ده تمامًا — زي Drawer.vue بالظبط.
-->
<style>
.field-shell {
  background: #f8fafc;
  --pos-bg: #f8fafc;
  --pos-surface: #ffffff;
  --pos-surface-2: #f1f5f9;
  --pos-border: #e2e8f0;
  --pos-text: #111827;
  --pos-text-muted: #64748b;
  --pos-accent: #a86f18;
  --pos-accent-bg: rgb(201 150 60 / 12%);
  --pos-success: #047857;
  --pos-danger: #dc2626;
}

.dark .field-shell {
  background: #1e2530;
  --pos-bg: #1e2530;
  --pos-surface: #252d3a;
  --pos-surface-2: #2e3748;
  --pos-border: #4b5563;
  --pos-text: #f9fafb;
  --pos-text-muted: #cbd5e1;
  --pos-accent: #d7aa5b;
  --pos-accent-bg: rgb(201 150 60 / 15%);
  --pos-success: #34d399;
  --pos-danger: #fca5a5;
}
</style>
