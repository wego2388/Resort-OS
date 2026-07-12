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
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@resort-os/core'
import { useI18n } from 'vue-i18n'
import GuestAlertsBell from '../components/GuestAlertsBell.vue'
import LanguageSwitcher from '../components/LanguageSwitcher.vue'

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
      { path: '/admin/menu',         label: t('backoffice.nav.restaurantMenu'), icon: '🍽️',  requiredRole: 'manager' },
      { path: '/admin/tables',       label: t('backoffice.nav.tablesManagement'),icon: '🪑', requiredRole: 'manager' },
      { path: '/admin/inventory',    label: t('backoffice.nav.inventory'),      icon: '📦',  requiredRole: 'manager' },
      { path: '/admin/recipes',      label: t('backoffice.nav.recipes'),        icon: '🧾',  requiredRole: 'manager' },
      { path: '/admin/food-cost',    label: t('backoffice.nav.foodCost'),       icon: '📉',  requiredRole: 'manager' },
      { path: '/admin/crm',          label: t('backoffice.nav.crm'),            icon: '🤝',  requiredRole: 'manager' },
      { path: '/admin/maintenance',  label: t('backoffice.nav.maintenance'),    icon: '🔧',  requiredRole: 'supervisor' },
      { path: '/admin/leasing',      label: t('backoffice.nav.leasing'),        icon: '🏢',  requiredRole: 'supervisor' },
    ],
  },
  {
    label: t('backoffice.nav.cafe'),
    items: [
      { path: '/admin/cafe-menu',  label: t('backoffice.nav.cafeMenu'),  icon: '☕', requiredRole: 'manager' },
      { path: '/admin/cafe-sales', label: t('backoffice.nav.cafeSales'), icon: '📊', requiredRole: 'manager' },
      { path: '/admin/qr',         label: t('backoffice.nav.qrCodes'),   icon: '📱', requiredRole: 'manager' },
    ],
  },
  {
    // Unified dining module (Batch B, additive — DINING_CUTOVER_PLAN.md).
    // manager+ only, deliberately: every /pos/* item a waiter/cashier sees
    // in FieldLayout has zero role filter, so putting the preview screens
    // there would change every cashier's daily nav. Gating discovery to
    // this manager-only section keeps their workflow untouched while still
    // giving Mohamed/managers a real way to reach all three preview
    // screens (menu admin, unified POS, unified KDS) for review.
    label: t('backoffice.nav.diningPreview'),
    items: [
      { path: '/admin/dining-menu', label: t('backoffice.nav.diningMenu'), icon: '🍽️', requiredRole: 'manager' },
      { path: '/pos/dining',        label: t('backoffice.nav.diningPos'),  icon: '🧾', requiredRole: 'manager' },
      { path: '/kds/dining',        label: t('backoffice.nav.diningKds'), icon: '👨‍🍳', requiredRole: 'manager' },
    ],
  },
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

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-stone-50 flex" :dir="locale === 'ar' ? 'rtl' : 'ltr'">
    <!-- Sidebar -->
    <aside :class="['bg-slate-900 text-white flex-shrink-0 flex flex-col transition-all duration-300', sidebarOpen ? 'w-60' : 'w-16']">
      <!-- Logo -->
      <div class="flex items-center gap-3 px-4 py-5 border-b border-slate-700">
        <div class="w-9 h-9 bg-amber-500 rounded-xl flex items-center justify-center flex-shrink-0">
          <span class="text-white font-black text-sm">RO</span>
        </div>
        <div v-if="sidebarOpen" class="overflow-hidden">
          <div class="font-bold text-sm text-white">Resort OS</div>
          <div class="text-xs text-slate-400 truncate">{{ t('backoffice.layout.branch') }} {{ auth.branchId }}</div>
        </div>
      </div>

      <!-- Navigation -->
      <nav class="flex-1 py-4 overflow-y-auto">
        <div v-for="section in navSections" :key="section.label" class="mb-4">
          <div v-if="sidebarOpen" class="px-4 py-1 text-xs font-semibold text-slate-500 uppercase tracking-wider">
            {{ section.label }}
          </div>
          <router-link
            v-for="item in section.items" :key="item.path"
            :to="item.path"
            :class="[
              'flex items-center gap-3 px-4 py-2.5 text-sm font-medium transition-colors rounded-lg mx-2 my-0.5',
              isActive(item.path)
                ? 'bg-amber-500 text-white'
                : 'text-slate-300 hover:bg-slate-800 hover:text-white'
            ]"
          >
            <span class="text-lg flex-shrink-0">{{ item.icon }}</span>
            <span v-if="sidebarOpen" class="truncate">{{ item.label }}</span>
          </router-link>
        </div>
      </nav>

      <!-- User + Logout -->
      <div class="border-t border-slate-700 p-4">
        <div v-if="sidebarOpen" class="flex items-center gap-3 mb-3">
          <div class="w-8 h-8 bg-slate-600 rounded-full flex items-center justify-center text-sm font-bold">
            {{ (auth.user?.full_name ?? '?').charAt(0) }}
          </div>
          <div class="overflow-hidden">
            <div class="text-sm font-medium text-white truncate">{{ auth.user?.full_name }}</div>
            <div class="text-xs text-slate-400">{{ auth.role }}</div>
          </div>
        </div>
        <button @click="logout"
          :class="['w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-red-400 hover:bg-red-900/30 transition-colors', !sidebarOpen && 'justify-center']"
        >
          <span>🚪</span>
          <span v-if="sidebarOpen">{{ t('backoffice.layout.logout') }}</span>
        </button>
      </div>
    </aside>

    <!-- Main -->
    <div class="flex-1 flex flex-col min-w-0">
      <!-- Topbar -->
      <header class="bg-white border-b border-stone-200 px-6 py-3 flex items-center justify-between flex-shrink-0">
        <div class="flex items-center gap-4">
          <button @click="toggleSidebar"
            class="p-1.5 rounded-lg hover:bg-gray-100 text-gray-600 transition-colors">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
            </svg>
          </button>
          <div>
            <nav v-if="breadcrumb" class="flex items-center gap-1.5 text-[11px] text-gray-400 mb-0.5">
              <span>{{ breadcrumb.section }}</span>
              <span>/</span>
              <span class="text-gray-500 font-medium">{{ breadcrumb.page }}</span>
            </nav>
            <h1 class="font-bold text-gray-900 text-base">{{ route.meta.title ?? 'Resort OS' }}</h1>
          </div>
        </div>
        <div class="flex items-center gap-3 text-sm text-gray-600">
          <!-- تنبيهات الضيوف (نادِ الجرسون / هات الفاتورة) — كانت ظاهرة بس في
               FieldLayout (نادل/كاشير)، يعني مدير/مشرف/محاسب قاعدين في
               BackOfficeLayout عمرهم ما كانوا بيشوفوا نداء ضيف خالص لو النادل
               مشغول. نفس المكوّن بالظبط (لا تكرار منطق). -->
          <GuestAlertsBell />
          <LanguageSwitcher variant="compact" />
          <span>{{ new Date().toLocaleDateString(locale === 'ar' ? 'ar-EG' : 'en-GB', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) }}</span>
        </div>
      </header>

      <!-- Content -->
      <main class="flex-1 overflow-auto p-6">
        <RouterView />
      </main>
    </div>
  </div>
</template>
