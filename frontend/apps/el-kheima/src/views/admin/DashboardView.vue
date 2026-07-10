<script setup lang="ts">
// Dashboard KPIs — was calling `/api/v1/analytics/dashboard/{branchId}` and
// `/api/v1/beach/inventory/{branchId}` (branch id as a *path* segment); neither
// route exists on the backend (real routes take `branch_id` as a *query* param:
// GET /analytics/daily-stats?branch_id=, GET /beach/inventory?branch_id=), so
// both calls always 404'd and every card silently fell back to 0 — an admin
// opening the dashboard for the first time had no way to tell "no data yet"
// apart from "this is broken". Rewired to the real endpoints below.
import { ref, onMounted, onUnmounted } from 'vue'
import { api, ENDPOINTS } from '@resort-os/core'

const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

interface DashboardData {
  today_revenue: number; yesterday_revenue: number
  occupancy_rate: number; beach_sold_today: number
  pending_hk_tasks: number; active_bookings: number
}

const data = ref<DashboardData | null>(null)
const loading = ref(false)
const loadError = ref(false)

function isoDate(d: Date) {
  return d.toISOString().split('T')[0]
}

async function fetchDailyStats(stat_date: string) {
  const { data } = await api.get(ENDPOINTS.analytics.dailyStats, { params: { branch_id: branchId, stat_date } })
  // DailyStats is a nightly-computed snapshot — if today's row hasn't been
  // built yet the endpoint returns `{stat_date, message}` with no numeric
  // fields at all (see AnalyticsView.vue for the same contract).
  if (data.message) return null
  return data as {
    occupancy_pct: number; beach_visitors: number
    restaurant_covers: number; total_revenue: number
  }
}

// ⚠️ باج حقيقي (اتصلح 2026-07-05، اتلقى أثناء اختبار حي): "إيراد اليوم" كان
// دايمًا صفر خلال ساعات الشغل الفعلية — DailyStats بتتولّد مرة واحدة بس كل
// يوم الساعة 1 صباحًا (وقتها بتحسب "أمس" مش "النهاردة")، يعني الصف بتاع
// النهاردة عمره ما بيكون موجود قبل الساعة 1 بليل بكرة. النتيجة: مدير بيفتح
// اللوحة ظهرًا يشوف "إيراد اليوم = 0" رغم مبيعات حقيقية شغالة قدامه. الحل:
// لو مفيش صف DailyStats للنهاردة، نستخدم /analytics/revenue (بيحسب لحظيًا
// من جداول المطعم/الكافيه/الشاطئ/الفندق نفسها، مش من لقطة مخزّنة).
async function fetchLiveRevenueToday() {
  const today = isoDate(new Date())
  const { data } = await api.get(ENDPOINTS.analytics.revenue, {
    params: { branch_id: branchId, date_from: today, date_to: today },
  })
  return {
    total_revenue: Number(data?.total ?? 0),
    beach_visitors: Number(data?.beach?.visits ?? 0),
  }
}

async function fetchDashboard() {
  loading.value = true
  loadError.value = false
  try {
    const yesterday = new Date(); yesterday.setDate(yesterday.getDate() - 1)

    const [todayRes, yesterdayRes, bookingsRes, hkRes, liveRevenueRes] = await Promise.allSettled([
      fetchDailyStats(isoDate(new Date())),
      fetchDailyStats(isoDate(yesterday)),
      api.get(ENDPOINTS.pms.bookings, { params: { branch_id: branchId, status: 'checked_in', page: 1, size: 1 } }),
      api.get(ENDPOINTS.pms.housekeeping, { params: { branch_id: branchId, status: 'pending' } }),
      fetchLiveRevenueToday(),
    ])

    const todayStats = todayRes.status === 'fulfilled' ? todayRes.value : null
    const yesterdayStats = yesterdayRes.status === 'fulfilled' ? yesterdayRes.value : null
    const liveRevenue = liveRevenueRes.status === 'fulfilled' ? liveRevenueRes.value : null

    data.value = {
      // todayStats (nightly snapshot) wins once it exists (it also carries
      // occupancy_pct, which the live fallback below can't compute); until
      // then, fall back to the live query so "today" isn't just always 0.
      today_revenue: todayStats?.total_revenue ?? liveRevenue?.total_revenue ?? 0,
      yesterday_revenue: yesterdayStats?.total_revenue ?? 0,
      occupancy_rate: todayStats?.occupancy_pct ?? 0,
      beach_sold_today: todayStats?.beach_visitors ?? liveRevenue?.beach_visitors ?? 0,
      active_bookings: bookingsRes.status === 'fulfilled' ? (bookingsRes.value.data.total ?? 0) : 0,
      pending_hk_tasks: hkRes.status === 'fulfilled' ? (hkRes.value.data?.length ?? 0) : 0,
    }
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

function revenueChange(current: number, previous: number) {
  if (!previous) return { pct: 0, up: true }
  const pct = Math.round(((current - previous) / previous) * 100)
  return { pct: Math.abs(pct), up: pct >= 0 }
}

// #6: إيقاف refresh لما الـ tab في الخلفية — بيوفر API calls غير ضرورية
// ويمنع تحديث البيانات لما المستخدم مش شايف الشاشة
const REFRESH_INTERVAL_MS = 60_000
let refreshTimer: ReturnType<typeof setInterval> | null = null

function handleVisibilityChange() {
  if (document.hidden) {
    if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
  } else {
    // الـ tab رجع visible — نحدّث فوراً ونشغّل الـ interval من جديد
    fetchDashboard()
    refreshTimer = setInterval(fetchDashboard, REFRESH_INTERVAL_MS)
  }
}

onMounted(() => {
  fetchDashboard()
  refreshTimer = setInterval(fetchDashboard, REFRESH_INTERVAL_MS)
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
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

    <div v-if="loadError" class="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm flex items-center justify-between mb-5">
      <span>⚠️ تعذّر تحميل بعض بيانات لوحة التحكم — تأكد من اتصالك وحاول تاني</span>
      <button @click="fetchDashboard" class="font-semibold underline hover:no-underline">إعادة المحاولة</button>
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
        { path: '/admin/cafe-sales', label: 'مبيعات الكافيه',  icon: '☕', color: 'bg-cyan-50 border-cyan-200 hover:bg-cyan-100' },
        { path: '/admin/tables',    label: 'إدارة الطاولات',   icon: '🪑', color: 'bg-orange-50 border-orange-200 hover:bg-orange-100' },
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
