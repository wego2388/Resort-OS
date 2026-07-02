<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@resort-os/core'

const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

interface DashboardData {
  today_revenue: number; yesterday_revenue: number
  occupancy_rate: number; beach_sold_today: number
  restaurant_covers_today: number; pending_hk_tasks: number
  monthly_revenue: number; active_bookings: number
}

const data = ref<DashboardData | null>(null)
const loading = ref(false)
const today = new Date().toISOString().split('T')[0]

async function fetchDashboard() {
  loading.value = true
  try {
    const res = await api.get(`/api/v1/analytics/dashboard/${branchId}`, { params: { date: today } })
    data.value = res.data
  } catch {
    try {
      const [beachRes, bookingsRes] = await Promise.allSettled([
        api.get(`/api/v1/beach/inventory/${branchId}`),
        api.get('/api/v1/pms/bookings', { params: { branch_id: branchId, status: 'checked_in', limit: 5 } }),
      ])
      data.value = {
        today_revenue: 0, yesterday_revenue: 0,
        occupancy_rate: 0,
        beach_sold_today: beachRes.status === 'fulfilled' ? beachRes.value.data.adult_sold ?? 0 : 0,
        restaurant_covers_today: 0,
        pending_hk_tasks: 0, monthly_revenue: 0,
        active_bookings: bookingsRes.status === 'fulfilled'
          ? (bookingsRes.value.data.total ?? bookingsRes.value.data.items?.length ?? 0)
          : 0,
      }
    } catch { /* ignore */ }
  } finally {
    loading.value = false
  }
}

function revenueChange(current: number, previous: number) {
  if (!previous) return { pct: 0, up: true }
  const pct = Math.round(((current - previous) / previous) * 100)
  return { pct: Math.abs(pct), up: pct >= 0 }
}

onMounted(fetchDashboard)
</script>

<template>
  <div dir="rtl">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-2xl font-black text-gray-900">لوحة التحكم</h2>
        <p class="text-sm text-gray-500 mt-0.5">{{ new Date().toLocaleDateString('ar-EG', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) }}</p>
      </div>
      <button @click="fetchDashboard" :class="['px-4 py-2 bg-amber-500 text-white rounded-xl font-medium text-sm hover:bg-amber-600 transition-colors', loading ? 'opacity-70' : '']">
        {{ loading ? 'جاري التحديث...' : '🔄 تحديث' }}
      </button>
    </div>

    <!-- KPI Cards -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <!-- Revenue Today -->
      <div class="bg-white rounded-2xl border border-stone-200 p-5 shadow-sm">
        <div class="flex items-center gap-3 mb-3">
          <div class="w-10 h-10 bg-green-100 rounded-xl flex items-center justify-center text-lg">💰</div>
          <span class="text-sm font-medium text-gray-500">إيراد اليوم</span>
        </div>
        <div class="text-3xl font-black text-gray-900">
          {{ loading ? '...' : (data?.today_revenue ?? 0).toLocaleString('ar-EG') }}
        </div>
        <div class="text-xs text-gray-400 mt-1">جنيه مصري</div>
        <div v-if="data && data.yesterday_revenue" class="flex items-center gap-1 mt-2 text-xs">
          <span :class="revenueChange(data.today_revenue, data.yesterday_revenue).up ? 'text-green-600' : 'text-red-500'">
            {{ revenueChange(data.today_revenue, data.yesterday_revenue).up ? '↑' : '↓' }}
            {{ revenueChange(data.today_revenue, data.yesterday_revenue).pct }}%
          </span>
          <span class="text-gray-400">مقارنة بالأمس</span>
        </div>
      </div>

      <!-- Occupancy -->
      <div class="bg-white rounded-2xl border border-stone-200 p-5 shadow-sm">
        <div class="flex items-center gap-3 mb-3">
          <div class="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center text-lg">🏨</div>
          <span class="text-sm font-medium text-gray-500">إشغال الأوضة</span>
        </div>
        <div class="text-3xl font-black text-gray-900">{{ loading ? '...' : (data?.occupancy_rate ?? 0) }}<span class="text-base font-normal text-gray-400">%</span></div>
        <div class="mt-2">
          <div class="w-full bg-gray-200 rounded-full h-1.5">
            <div class="bg-blue-600 h-1.5 rounded-full transition-all" :style="{ width: (data?.occupancy_rate ?? 0) + '%' }"/>
          </div>
        </div>
        <div class="text-xs text-gray-400 mt-1">{{ data?.active_bookings ?? 0 }} حجز نشط</div>
      </div>

      <!-- Beach -->
      <div class="bg-white rounded-2xl border border-stone-200 p-5 shadow-sm">
        <div class="flex items-center gap-3 mb-3">
          <div class="w-10 h-10 bg-amber-100 rounded-xl flex items-center justify-center text-lg">🏖️</div>
          <span class="text-sm font-medium text-gray-500">الشاطئ اليوم</span>
        </div>
        <div class="text-3xl font-black text-gray-900">{{ loading ? '...' : (data?.beach_sold_today ?? 0) }}</div>
        <div class="text-xs text-gray-400 mt-1">تذكرة مباعة</div>
      </div>

      <!-- HK Tasks -->
      <div class="bg-white rounded-2xl border border-stone-200 p-5 shadow-sm">
        <div class="flex items-center gap-3 mb-3">
          <div class="w-10 h-10 bg-purple-100 rounded-xl flex items-center justify-center text-lg">🧹</div>
          <span class="text-sm font-medium text-gray-500">مهام التنظيف</span>
        </div>
        <div class="text-3xl font-black text-gray-900">{{ loading ? '...' : (data?.pending_hk_tasks ?? 0) }}</div>
        <div class="text-xs text-gray-400 mt-1">مهمة معلقة</div>
      </div>
    </div>

    <!-- Quick links -->
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
      <router-link v-for="link in [
        { path: '/admin/hr',        label: 'الموارد البشرية', icon: '👥', color: 'bg-blue-50 border-blue-200 hover:bg-blue-100' },
        { path: '/admin/finance',   label: 'التقارير المالية', icon: '📊', color: 'bg-green-50 border-green-200 hover:bg-green-100' },
        { path: '/admin/inventory', label: 'المخزون',          icon: '📦', color: 'bg-amber-50 border-amber-200 hover:bg-amber-100' },
        { path: '/admin/crm',       label: 'إدارة العملاء',    icon: '🤝', color: 'bg-purple-50 border-purple-200 hover:bg-purple-100' },
        { path: '/admin/analytics', label: 'التحليلات',        icon: '📈', color: 'bg-pink-50 border-pink-200 hover:bg-pink-100' },
        { path: '/admin/settings',  label: 'الإعدادات',        icon: '⚙️', color: 'bg-gray-50 border-gray-200 hover:bg-gray-100' },
      ]" :key="link.path" :to="link.path"
        :class="['flex items-center gap-3 p-4 rounded-xl border-2 transition-colors', link.color]"
      >
        <span class="text-2xl">{{ link.icon }}</span>
        <span class="font-semibold text-gray-800">{{ link.label }}</span>
      </router-link>
    </div>
  </div>
</template>
