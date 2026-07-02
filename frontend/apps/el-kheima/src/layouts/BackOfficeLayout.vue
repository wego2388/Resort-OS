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

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const sidebarOpen = ref(true)

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

const allSections: NavSection[] = [
  {
    label: 'العمليات',
    items: [
      { path: '/ops/rooms', label: 'الغرف', icon: '🛏️' },
      { path: '/ops/bookings', label: 'الحجوزات', icon: '📋' },
      { path: '/ops/housekeeping', label: 'التنظيف', icon: '🧹' },
    ],
  },
  {
    label: 'الرئيسية',
    items: [
      { path: '/admin/dashboard', label: 'لوحة التحكم', icon: '📊', requiredRole: 'manager' },
      { path: '/admin/analytics', label: 'التحليلات', icon: '📈', requiredRole: 'manager' },
    ],
  },
  {
    label: 'الإدارة',
    items: [
      { path: '/admin/hr', label: 'الموارد البشرية', icon: '👥', requiredRole: 'manager' },
      { path: '/admin/finance', label: 'المالية', icon: '💰', requiredRole: 'manager' },
      { path: '/admin/e-invoice', label: 'الفاتورة الإلكترونية', icon: '🧾', requiredRole: 'manager' },
      { path: '/admin/timeshare', label: 'التايم شير', icon: '🏨', requiredRole: 'manager' },
      { path: '/admin/sales', label: 'لوحة المبيعات', icon: '📞', requiredRole: 'manager' },
      { path: '/admin/beach-live', label: 'لوحة الشاطئ الحيّة', icon: '🏖️', requiredRole: 'manager' },
      { path: '/admin/inventory', label: 'المخزون', icon: '📦', requiredRole: 'manager' },
      { path: '/admin/crm', label: 'إدارة العملاء', icon: '🤝', requiredRole: 'manager' },
    ],
  },
  {
    label: 'الإعدادات',
    items: [
      { path: '/admin/settings', label: 'الإعدادات', icon: '⚙️', requiredRole: 'admin' },
    ],
  },
  {
    label: 'بوابة الموظفين',
    items: [
      { path: '/portal/attendance', label: 'الحضور والانصراف', icon: '⏰' },
      { path: '/portal/leaves', label: 'طلبات الإجازة', icon: '🌴' },
      { path: '/portal/payroll', label: 'الرواتب', icon: '💳' },
      { path: '/portal/profile', label: 'ملفي الشخصي', icon: '👤' },
    ],
  },
]

const navSections = computed(() =>
  allSections
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

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-stone-50 flex" dir="rtl">
    <!-- Sidebar -->
    <aside :class="['bg-slate-900 text-white flex-shrink-0 flex flex-col transition-all duration-300', sidebarOpen ? 'w-60' : 'w-16']">
      <!-- Logo -->
      <div class="flex items-center gap-3 px-4 py-5 border-b border-slate-700">
        <div class="w-9 h-9 bg-amber-500 rounded-xl flex items-center justify-center flex-shrink-0">
          <span class="text-white font-black text-sm">RO</span>
        </div>
        <div v-if="sidebarOpen" class="overflow-hidden">
          <div class="font-bold text-sm text-white">Resort OS</div>
          <div class="text-xs text-slate-400 truncate">فرع {{ auth.branchId }}</div>
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
          <span v-if="sidebarOpen">تسجيل الخروج</span>
        </button>
      </div>
    </aside>

    <!-- Main -->
    <div class="flex-1 flex flex-col min-w-0">
      <!-- Topbar -->
      <header class="bg-white border-b border-stone-200 px-6 py-3 flex items-center justify-between flex-shrink-0">
        <div class="flex items-center gap-4">
          <button @click="sidebarOpen = !sidebarOpen"
            class="p-1.5 rounded-lg hover:bg-gray-100 text-gray-600 transition-colors">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
            </svg>
          </button>
          <h1 class="font-bold text-gray-900 text-base">{{ route.meta.title ?? 'Resort OS' }}</h1>
        </div>
        <div class="flex items-center gap-3 text-sm text-gray-600">
          <span>{{ new Date().toLocaleDateString('ar-EG', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) }}</span>
        </div>
      </header>

      <!-- Content -->
      <main class="flex-1 overflow-auto p-6">
        <RouterView />
      </main>
    </div>
  </div>
</template>
