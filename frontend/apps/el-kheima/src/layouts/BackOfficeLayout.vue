<script setup lang="ts">
// BackOfficeLayout — collapsible sidebar + grouped nav + topbar.
// Adapted from apps/admin's AppLayout.vue (the most complete of the 6 —
// collapsible sidebar, grouped nav, topbar) and reused for /ops/*, /admin/*
// and /portal/* — the three former apps that were all "back office chrome"
// stylistically, just with different nav sections.
//
// Nav items are filtered through useAuthStore().hasRole() — a user never
// sees a link for a section their role doesn't have, instead of finding out
// via a 403 after clicking through.
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@resort-os/core'
import { useI18n } from 'vue-i18n'
import GuestAlertsBell from '../components/GuestAlertsBell.vue'
import LanguageSwitcher from '../components/LanguageSwitcher.vue'
import { CommandPalette, ThemeToggle } from '@resort-os/ui'
import type { CommandItem } from '@resort-os/ui'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const { t, locale } = useI18n()

// #23: حفظ حالة الـ sidebar في localStorage — بيتذكر اختيار المستخدم بين الجلسات
const SIDEBAR_KEY = 'resort-os-sidebar-open'
const sidebarOpen = ref(localStorage.getItem(SIDEBAR_KEY) !== 'false')

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
  localStorage.setItem(SIDEBAR_KEY, String(sidebarOpen.value))
}

interface NavItem {
  path: string
  label: string
  icon: string
  requiredRole?: string
}
interface NavSection {
  label: string
  items: NavItem[]
}

const allSections = computed<NavSection[]>(() => [
  {
    label: t('backoffice.nav.operations'),
    items: [
      { path: '/ops/reception',   label: 'الاستقبال',                    icon: '🛎️' },
      { path: '/ops/rooms',       label: t('backoffice.nav.rooms'),       icon: '🛏️' },
      { path: '/ops/bookings',    label: t('backoffice.nav.bookings'),    icon: '📋' },
      { path: '/ops/housekeeping',label: t('backoffice.nav.housekeeping'),icon: '🧹' },
    ],
  },
  {
    label: t('backoffice.nav.main'),
    items: [
      { path: '/admin/dashboard', label: t('backoffice.nav.dashboard'), icon: '📊', requiredRole: 'manager' },
      { path: '/admin/analytics', label: t('backoffice.nav.analytics'), icon: '📈', requiredRole: 'manager' },
    ],
  },
  {
    label: t('backoffice.nav.management'),
    items: [
      { path: '/admin/hr',           label: t('backoffice.nav.hr'),             icon: '👥',  requiredRole: 'manager' },
      { path: '/admin/finance',      label: t('backoffice.nav.finance'),        icon: '💰',  requiredRole: 'manager' },
      { path: '/admin/e-invoice',    label: t('backoffice.nav.eInvoice'),       icon: '🧾',  requiredRole: 'manager' },
      { path: '/admin/timeshare',    label: t('backoffice.nav.timeshare'),      icon: '🏨',  requiredRole: 'cashier' },
      { path: '/admin/sales',        label: t('backoffice.nav.sales'),          icon: '📞',  requiredRole: 'manager' },
      { path: '/admin/beach-live',   label: t('backoffice.nav.beachLive'),      icon: '🏖️',  requiredRole: 'manager' },
      { path: '/admin/beach-admin',  label: t('backoffice.nav.beachAdmin'),     icon: '🏄',  requiredRole: 'manager' },
      { path: '/admin/inventory',    label: t('backoffice.nav.inventory'),      icon: '📦',  requiredRole: 'manager' },
      { path: '/admin/recipes',      label: t('backoffice.nav.recipes'),        icon: '🧾',  requiredRole: 'manager' },
      { path: '/admin/food-cost',    label: t('backoffice.nav.foodCost'),       icon: '📉',  requiredRole: 'manager' },
      { path: '/admin/crm',          label: t('backoffice.nav.crm'),            icon: '🤝',  requiredRole: 'manager' },
      { path: '/admin/maintenance',  label: t('backoffice.nav.maintenance'),    icon: '🔧',  requiredRole: 'supervisor' },
      { path: '/admin/leasing',      label: t('backoffice.nav.leasing'),        icon: '🏢',  requiredRole: 'supervisor' },
    ],
  },
  {
    // DINING_CUTOVER_PLAN.md Batch 4 — dining بقى الافتراضي الحقيقي دلوقتي
    // (مش manager-only preview) — بس القسم نفسه فضل manager+ لأنه إدارة/
    // إشراف (منيو، تقارير)، مش استخدام يومي. النادل/الكاشير بيوصلوا
    // /pos/dining و/kds/dining من FieldLayout/KioskLayout مباشرة، مش من هنا.
    label: t('backoffice.nav.dining'),
    items: [
      { path: '/admin/dining-menu', label: t('backoffice.nav.diningMenu'), icon: '🍽️', requiredRole: 'manager' },
      { path: '/pos/dining',        label: t('backoffice.nav.diningPos'),  icon: '🧾', requiredRole: 'manager' },
      { path: '/kds/dining',        label: t('backoffice.nav.diningKds'), icon: '👨‍🍳', requiredRole: 'manager' },
      { path: '/admin/qr',          label: t('backoffice.nav.qrCodes'),   icon: '📱', requiredRole: 'manager' },
    ],
  },
  {
    label: t('backoffice.nav.hubSection'),
    items: [
      { path: '/admin/hub', label: t('backoffice.nav.hubManagement'), icon: '🌐', requiredRole: 'manager' },
    ],
  },
  ...(import.meta.env.DEV ? [{
    label: t('backoffice.nav.development'),
    items: [
      {
        path: '/admin/project-cockpit',
        label: t('backoffice.nav.projectCockpit'),
        icon: '🧭',
        requiredRole: 'super_admin',
      },
    ],
  }] : []),
  {
    label: t('backoffice.nav.settings'),
    items: [
      { path: '/admin/settings',    label: t('backoffice.nav.settings'),    icon: '⚙️', requiredRole: 'admin' },
      { path: '/admin/permissions', label: t('backoffice.nav.permissions'), icon: '🔐', requiredRole: 'super_admin' },
    ],
  },
  {
    label: t('backoffice.nav.portalSection'),
    items: [
      { path: '/portal/attendance', label: t('backoffice.nav.attendance'), icon: '⏰' },
      { path: '/portal/leaves',     label: t('backoffice.nav.leaves'),     icon: '🌴' },
      { path: '/portal/payroll',    label: t('backoffice.nav.payroll'),    icon: '💳' },
      { path: '/portal/profile',    label: t('backoffice.nav.profile'),    icon: '👤' },
      // Gate 2B3B — session & security self-service, reachable by any signed-in user.
      { path: '/account/sessions',  label: t('account.sessions.navLink'),  icon: '🔒' },
    ],
  },
])

const navSections = computed(() =>
  allSections.value
    .map((section) => ({
      ...section,
      items: section.items.filter(
        (item) => !item.requiredRole || auth.hasRole(item.requiredRole),
      ),
    }))
    .filter((section) => section.items.length > 0),
)

function isActive(path: string) {
  return route.path === path || route.path.startsWith(path + '/')
}

// #21/#29: breadcrumb (قسم ← صفحة) في التوببار — ثابت وظاهر بصرف النظر عن
// حالة الـ sidebar (مفتوح/مقفول/على شاشة صغيرة)، بيحل المشكلتين مع بعض:
// المدير كان تايه في البنية (#21)، وعلى تابلت لما الـ sidebar يتقفل لأيقونات
// بس مفيش أي مؤشر تاني لمكانه الحالي (#29). بيتبني من allSections نفسها
// (نفس مصدر الـ nav) — مفيش مصدر تاني منفصل يتزامن معاه بالغلط.
const breadcrumb = computed(() => {
  for (const section of allSections.value) {
    const item = section.items.find((i) => isActive(i.path))
    if (item) return { section: section.label, page: item.label }
  }
  return null
})

const pageTitle = computed(() => (
  route.meta.titleKey ? t(route.meta.titleKey) : (route.meta.title ?? 'Resort OS')
))

function logout() {
  auth.logout()
  router.push('/login')
}

// ── CommandPalette ────────────────────────────────────────────────────────
const showCommandPalette = ref(false)

// بناء الـ commands من الـ nav items الظاهرة للمستخدم الحالي
const commandItems = computed<CommandItem[]>(() => {
  const items: CommandItem[] = []
  for (const section of navSections.value) {
    for (const item of section.items) {
      items.push({
        id: item.path,
        label: item.label,
        sublabel: section.label,
        category: section.label,
        action: () => router.push(item.path),
      })
    }
  }
  return items
})

function handleGlobalKey(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault()
    showCommandPalette.value = !showCommandPalette.value
  }
}

onMounted(() => document.addEventListener('keydown', handleGlobalKey))
onBeforeUnmount(() => document.removeEventListener('keydown', handleGlobalKey))
</script>

<template>
  <div class="min-h-screen bg-stone-50 dark:bg-gray-950 flex" :dir="locale === 'ar' ? 'rtl' : 'ltr'">

    <!-- ── Sidebar ── -->
    <aside
      :class="['flex-shrink-0 flex flex-col transition-all duration-300 bg-gray-900 dark:bg-gray-950', sidebarOpen ? 'w-60' : 'w-16']"
    >
      <!-- Logo -->
      <div class="flex items-center gap-3 px-4 py-5 border-b border-white/10">
        <div class="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 bg-gold-DEFAULT">
          <span class="text-white font-black text-sm">RO</span>
        </div>
        <div v-if="sidebarOpen" class="overflow-hidden">
          <div class="font-bold text-sm text-white">Resort OS</div>
          <div class="text-xs truncate text-gray-500">
            {{ t('backoffice.layout.branch') }} {{ auth.branchId }}
          </div>
        </div>
      </div>

      <!-- Nav -->
      <nav class="flex-1 py-4 overflow-y-auto">
        <div v-for="section in navSections" :key="section.label" class="mb-4">
          <div v-if="sidebarOpen"
            class="px-4 py-1 text-[10px] font-bold uppercase tracking-widest text-gray-400">
            {{ section.label }}
          </div>
          <router-link
            v-for="item in section.items" :key="item.path"
            :to="item.path"
            :title="!sidebarOpen ? item.label : undefined"
            :class="[
              'flex items-center gap-3 px-4 py-2.5 text-sm font-medium transition-colors rounded-lg mx-2 my-0.5',
              !sidebarOpen && 'justify-center',
              isActive(item.path)
                ? 'bg-gold-DEFAULT text-white'
                : 'text-gray-300 hover:text-white hover:bg-white/10',
            ]"
          >
            <span class="text-base flex-shrink-0">{{ item.icon }}</span>
            <span v-if="sidebarOpen" class="truncate">{{ item.label }}</span>
          </router-link>
        </div>
      </nav>

      <!-- User + Logout -->
      <div class="p-4 border-t border-white/10">
        <div v-if="sidebarOpen" class="flex items-center gap-3 mb-3">
          <div class="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold bg-gray-700 text-gray-100">
            {{ (auth.user?.full_name ?? '?').charAt(0) }}
          </div>
          <div class="overflow-hidden">
            <div class="text-sm font-medium text-white truncate">{{ auth.user?.full_name }}</div>
            <div class="text-xs text-gray-500">{{ auth.role }}</div>
          </div>
        </div>
        <button @click="logout"
          :class="['w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors text-red-400 hover:bg-red-400/10', !sidebarOpen && 'justify-center']"
        >
          <span>🚪</span>
          <span v-if="sidebarOpen">{{ t('backoffice.layout.logout') }}</span>
        </button>
      </div>
    </aside>

    <!-- ── Main ── -->
    <div class="flex-1 flex flex-col min-w-0">

      <!-- Topbar -->
      <header class="bg-white dark:bg-gray-900 border-b border-stone-200 dark:border-gray-700 px-6 py-3 flex items-center justify-between flex-shrink-0">
        <div class="flex items-center gap-4">
          <button @click="toggleSidebar"
            class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400 transition-colors">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
            </svg>
          </button>
          <div>
            <nav v-if="breadcrumb" class="flex items-center gap-1.5 text-[11px] text-gray-400 dark:text-gray-500 mb-0.5">
              <span>{{ breadcrumb.section }}</span>
              <span>/</span>
              <span class="text-gray-500 dark:text-gray-400 font-medium">{{ breadcrumb.page }}</span>
            </nav>
            <h1 class="font-bold text-gray-900 dark:text-gray-100 text-base">{{ pageTitle }}</h1>
          </div>
        </div>

        <div class="flex items-center gap-3 text-sm text-gray-600 dark:text-gray-400">
          <!-- Ctrl+K search trigger -->
          <button
            type="button"
            class="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg border border-stone-200 dark:border-gray-700 bg-stone-50 dark:bg-gray-800 text-sm text-muted hover:bg-stone-100 dark:hover:bg-gray-700 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
            @click="showCommandPalette = true"
          >
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
            </svg>
            <span>بحث سريع</span>
            <kbd class="flex items-center gap-0.5 text-[10px] font-semibold bg-white dark:bg-gray-700 border border-stone-300 dark:border-gray-600 rounded px-1 py-0.5">
              <span>⌘</span><span>K</span>
            </kbd>
          </button>
          <GuestAlertsBell />
          <ThemeToggle />
          <LanguageSwitcher variant="compact" />
          <span class="hidden lg:block text-xs text-gray-500 dark:text-gray-500">
            {{ new Date().toLocaleDateString(locale === 'ar' ? 'ar-EG' : 'en-GB') }}
          </span>
        </div>
      </header>

      <!-- Content -->
      <main class="flex-1 overflow-auto p-6 bg-stone-50 dark:bg-gray-950">
        <RouterView />
      </main>
    </div>
  </div>

  <!-- CommandPalette -->
  <CommandPalette
    :open="showCommandPalette"
    :items="commandItems"
    placeholder="ابحث في الصفحات والإجراءات..."
    @close="showCommandPalette = false"
  />
</template>
