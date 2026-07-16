<script setup lang="ts">
// Dashboard KPIs — was calling `/api/v1/analytics/dashboard/{branchId}` and
// `/api/v1/beach/inventory/{branchId}` (branch id as a *path* segment); neither
// route exists on the backend (real routes take `branch_id` as a *query* param:
// GET /analytics/daily-stats?branch_id=, GET /beach/inventory?branch_id=), so
// both calls always 404'd and every card silently fell back to 0 — an admin
// opening the dashboard for the first time had no way to tell "no data yet"
// apart from "this is broken". Rewired to the real endpoints below.
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, useAuthStore, useResortWebSocket, ENDPOINTS } from '@resort-os/core'
import { StatCard } from '@resort-os/ui'

const auth = useAuthStore()
const branchId = auth.branchId

interface DashboardData {
  today_revenue: number; yesterday_revenue: number
  occupancy_rate: number; beach_sold_today: number
  pending_hk_tasks: number; active_bookings: number
}

const data = ref<DashboardData | null>(null)
const loading = ref(false)
const loadError = ref(false)

// #17: كارت "تنبيهات عاجلة" مجمّع — المدير كان محتاج يفتح 4 شاشات منفصلة
// (مخزون/صيانة/تايم شير/حسابات) عشان يعرف فيه مشكلة. كل رقم هنا بيجي من
// endpoint موجود بالفعل (مفيش منطق عمل جديد، بس تجميع للعرض).
interface UrgentAlerts {
  lowStock: number; overdueMaintenance: number; overdueInstallments: number; bouncedChecks: number
}
const alerts = ref<UrgentAlerts>({ lowStock: 0, overdueMaintenance: 0, overdueInstallments: 0, bouncedChecks: 0 })
const alertsTotal = () => alerts.value.lowStock + alerts.value.overdueMaintenance + alerts.value.overdueInstallments + alerts.value.bouncedChecks

async function fetchUrgentAlerts() {
  const today = isoDate(new Date())
  const [stockRes, maintOpenRes, maintInProgressRes, tsRes, checksRes] = await Promise.allSettled([
    api.get(ENDPOINTS.inventory.products, { params: { branch_id: branchId, low_stock_only: true, size: 1 } }),
    api.get(ENDPOINTS.maintenance.workOrders, { params: { branch_id: branchId, status: 'open', size: 100 } }),
    api.get(ENDPOINTS.maintenance.workOrders, { params: { branch_id: branchId, status: 'in_progress', size: 100 } }),
    api.get(ENDPOINTS.timeshare.csSummary, { params: { branch_id: branchId } }),
    api.get(ENDPOINTS.finance.checks, { params: { branch_id: branchId, status: 'bounced' } }),
  ])

  // أوامر صيانة متأخرة — نفس تعريف notify_overdue_work_orders (scheduled_date
  // < النهاردة، status لسه open/in_progress). الباك إند مالوش فلتر "متأخر"
  // جاهز، فبنفلتر هنا للعرض بس (مفيش قرار عمل، مجرد عدّ).
  const isOverdue = (o: { scheduled_date: string | null }) => !!o.scheduled_date && o.scheduled_date < today
  const openOrders = maintOpenRes.status === 'fulfilled' ? (maintOpenRes.value.data?.items ?? []) : []
  const inProgressOrders = maintInProgressRes.status === 'fulfilled' ? (maintInProgressRes.value.data?.items ?? []) : []
  const overdueMaintenance = [...openOrders, ...inProgressOrders].filter(isOverdue).length

  alerts.value = {
    lowStock: stockRes.status === 'fulfilled' ? (stockRes.value.data?.total ?? 0) : 0,
    overdueMaintenance,
    overdueInstallments: tsRes.status === 'fulfilled' ? (tsRes.value.data?.overdue_contracts_count ?? 0) : 0,
    bouncedChecks: checksRes.status === 'fulfilled' ? (checksRes.value.data?.length ?? 0) : 0,
  }
}

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
    lastUpdatedAt.value = new Date()
    updateLastUpdatedLabel()
  }
}

function revenueChange(current: number, previous: number) {
  if (!previous) return { pct: 0, up: true }
  const pct = Math.round(((current - previous) / previous) * 100)
  return { pct: Math.abs(pct), up: pct >= 0 }
}

// computed trend للـ StatCard — موجب = ↑ أخضر, سالب = ↓ أحمر
const revenueTrend = computed(() => {
  if (!data.value || !data.value.yesterday_revenue) return undefined
  const { pct, up } = revenueChange(data.value.today_revenue, data.value.yesterday_revenue)
  return up ? pct : -pct
})

// #6: إيقاف refresh لما الـ tab في الخلفية — بيوفر API calls غير ضرورية
// ويمنع تحديث البيانات لما المستخدم مش شايف الشاشة
const REFRESH_INTERVAL_MS = 60_000
let refreshTimer: ReturnType<typeof setInterval> | null = null

// آخر تحديث
const lastUpdatedAt = ref<Date | null>(null)
const lastUpdatedLabel = ref('')
let labelTimer: ReturnType<typeof setInterval> | null = null

function updateLastUpdatedLabel() {
  if (!lastUpdatedAt.value) { lastUpdatedLabel.value = ''; return }
  const secs = Math.floor((Date.now() - lastUpdatedAt.value.getTime()) / 1000)
  if (secs < 10) lastUpdatedLabel.value = 'الآن'
  else if (secs < 60) lastUpdatedLabel.value = `منذ ${secs} ثانية`
  else lastUpdatedLabel.value = `منذ ${Math.floor(secs / 60)} دقيقة`
}

// ── WebSocket — تحديثات لحظية للإيرادات عبر قناة KDS ────────────────────
// tickets_updated يُبث عند كل أوردر جديد/دفع — فرصة لإعادة تحميل KPIs
// (الباكند مالوش WS مخصص للـ dashboard — نفس القناة الوحيدة المتاحة هي KDS)
const { onMessage: onKdsMessage } = useResortWebSocket(ENDPOINTS.dining.kdsWs(branchId))
onKdsMessage((data: any) => {
  if (data?.type === 'tickets_updated') {
    fetchDashboard()
  }
})

function handleVisibilityChange() {
  if (document.hidden) {
    if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
  } else {
    // الـ tab رجع visible — نحدّث فوراً ونشغّل الـ interval من جديد
    fetchDashboard()
    fetchUrgentAlerts()
    refreshTimer = setInterval(() => { fetchDashboard(); fetchUrgentAlerts() }, REFRESH_INTERVAL_MS)
  }
}

// ── Analytics sub-cards (HR / Maintenance / CRM / Inventory) ──────────────
interface AnalyticsSummary {
  hr: { active_employees: number; last_payroll_month: string | null } | null
  maintenance: { open_orders: number; critical_orders: number } | null
  crm: { total_customers: number; open_opportunities: number } | null
  inventory: { low_stock_count: number; out_of_stock_count: number } | null
}
const analyticsSummary = ref<AnalyticsSummary>({ hr: null, maintenance: null, crm: null, inventory: null })

async function fetchAnalyticsSummary() {
  const [hrRes, maintRes, crmRes, invRes] = await Promise.allSettled([
    api.get(ENDPOINTS.analytics.hr, { params: { branch_id: branchId } }),
    api.get(ENDPOINTS.analytics.maintenance, { params: { branch_id: branchId } }),
    api.get(ENDPOINTS.analytics.crm, { params: { branch_id: branchId } }),
    api.get(ENDPOINTS.analytics.inventory, { params: { branch_id: branchId } }),
  ])
  analyticsSummary.value = {
    hr:          hrRes.status === 'fulfilled'   ? hrRes.value.data   : null,
    maintenance: maintRes.status === 'fulfilled' ? maintRes.value.data : null,
    crm:         crmRes.status === 'fulfilled'   ? crmRes.value.data   : null,
    inventory:   invRes.status === 'fulfilled'   ? invRes.value.data   : null,
  }
}

// ── Timeshare Upcoming Visits widget ──────────────────────────────────
interface UpcomingVisit {
  id: number; contract_id: number; guest_name: string
  visit_start: string; visit_end: string; unit_name?: string | null; status: string
}
const upcomingVisits = ref<UpcomingVisit[]>([])

async function fetchUpcomingVisits() {
  try {
    const { data } = await api.get(ENDPOINTS.timeshare.upcomingVisits, { params: { branch_id: branchId, size: 5 } })
    upcomingVisits.value = data.items ?? data ?? []
  } catch { /* non-critical widget */ }
}

const todayLabel = new Date().toLocaleDateString('ar-EG', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })

// Quick links
const quickLinks = [  { path: '/admin/hr',        label: 'الموارد البشرية', icon: '👥', color: 'bg-blue-50 border-blue-200 hover:bg-blue-100' },
  { path: '/admin/finance',   label: 'التقارير المالية', icon: '📊', color: 'bg-green-50 border-green-200 hover:bg-green-100' },
  { path: '/admin/inventory', label: 'المخزون',          icon: '📦', color: 'bg-amber-50 border-amber-200 hover:bg-amber-100' },
  { path: '/admin/crm',       label: 'إدارة العملاء',    icon: '🤝', color: 'bg-purple-50 border-purple-200 hover:bg-purple-100' },
  { path: '/admin/analytics', label: 'التحليلات',        icon: '📈', color: 'bg-pink-50 border-pink-200 hover:bg-pink-100' },
  { path: '/admin/dining-menu', label: 'إدارة الدايننج', icon: '🍽️', color: 'bg-cyan-50 border-cyan-200 hover:bg-cyan-100' },
  { path: '/admin/maintenance', label: 'الصيانة',        icon: '🔧', color: 'bg-orange-50 border-orange-200 hover:bg-orange-100' },
  { path: '/admin/settings',  label: 'الإعدادات',        icon: '⚙️', color: 'bg-gray-50 border-gray-200 hover:bg-gray-100' },
]

onMounted(() => {
  fetchDashboard()
  fetchUrgentAlerts()
  fetchAnalyticsSummary()
  fetchUpcomingVisits()
  refreshTimer = setInterval(() => { fetchDashboard(); fetchUrgentAlerts() }, REFRESH_INTERVAL_MS)
  labelTimer = setInterval(updateLastUpdatedLabel, 10_000)
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  if (labelTimer) clearInterval(labelTimer)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>

<template>
  <div dir="rtl">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-2xl font-black text-gray-900 dark:text-gray-100">لوحة التحكم</h2>
        <p class="text-sm text-gray-500 dark:text-gray-500 mt-0.5">{{ todayLabel }}</p>
      </div>
      <div class="flex items-center gap-3">
        <span v-if="lastUpdatedLabel" class="text-xs text-gray-400 dark:text-gray-500">آخر تحديث: {{ lastUpdatedLabel }}</span>
        <button @click="fetchDashboard" :class="[`px-4 py-2 bg-amber-500 text-white rounded-xl font-medium text-sm hover:bg-amber-600 transition-colors`, loading ? `opacity-70` : ``]">
          {{ loading ? 'جاري التحديث...' : '🔄 تحديث' }}
        </button>
      </div>
    </div>

    <div v-if="loadError" class="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm flex items-center justify-between mb-5">
      <span>⚠️ تعذّر تحميل بعض بيانات لوحة التحكم — تأكد من اتصالك وحاول تاني</span>
      <button @click="fetchDashboard" class="font-semibold underline hover:no-underline">إعادة المحاولة</button>
    </div>

    <!-- #17: تنبيهات عاجلة مجمّعة — بديل عن فتح 4 شاشات منفصلة للتأكد من عدم وجود مشاكل -->
    <div v-if="alertsTotal() > 0" class="bg-red-50 border border-red-200 rounded-2xl p-4 mb-6">
      <p class="text-sm font-black text-red-800 mb-3">🚨 تنبيهات عاجلة ({{ alertsTotal() }})</p>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <router-link v-if="alerts.lowStock" to="/admin/inventory"
          class="bg-white dark:bg-surface rounded-xl border border-red-200 px-3 py-2 hover:bg-red-50 transition-colors">
          <div class="text-xs text-gray-500 dark:text-gray-500">📦 مخزون منخفض</div>
          <div class="text-lg font-black text-red-600">{{ alerts.lowStock }}</div>
        </router-link>
        <router-link v-if="alerts.overdueMaintenance" to="/admin/maintenance"
          class="bg-white dark:bg-surface rounded-xl border border-red-200 px-3 py-2 hover:bg-red-50 transition-colors">
          <div class="text-xs text-gray-500 dark:text-gray-500">🔧 صيانة متأخرة</div>
          <div class="text-lg font-black text-red-600">{{ alerts.overdueMaintenance }}</div>
        </router-link>
        <router-link v-if="alerts.overdueInstallments" to="/admin/timeshare"
          class="bg-white dark:bg-surface rounded-xl border border-red-200 px-3 py-2 hover:bg-red-50 transition-colors">
          <div class="text-xs text-gray-500 dark:text-gray-500">🏨 أقساط متأخرة</div>
          <div class="text-lg font-black text-red-600">{{ alerts.overdueInstallments }}</div>
        </router-link>
        <router-link v-if="alerts.bouncedChecks" to="/admin/finance"
          class="bg-white dark:bg-surface rounded-xl border border-red-200 px-3 py-2 hover:bg-red-50 transition-colors">
          <div class="text-xs text-gray-500 dark:text-gray-500">🏦 شيكات مرتجعة</div>
          <div class="text-lg font-black text-red-600">{{ alerts.bouncedChecks }}</div>
        </router-link>
      </div>
    </div>

    <!-- KPI Cards -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <StatCard
        label="إيراد اليوم"
        :value="loading ? '...' : (data?.today_revenue ?? 0).toLocaleString('ar-EG') + ' ج'"
        icon="currency"
        variant="success"
        :trend="revenueTrend"
        trend-label="مقارنة بالأمس"
        :loading="loading"
      />

      <!-- Occupancy — يحتفظ بالـ progress bar اليدوي داخل slot لأن StatCard مافيهاش progress bar -->
      <div class="bg-white dark:bg-surface rounded-xl border border-stone-200 dark:border-border shadow-elevation-1 p-5">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <p class="text-sm text-muted font-medium">إشغال الأوضة</p>
            <div v-if="loading" class="h-8 w-24 mt-2 rounded bg-background animate-pulse" />
            <p v-else class="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-1 tabular-nums">
              {{ data?.occupancy_rate ?? 0 }}<span class="text-base font-normal text-muted">%</span>
            </p>
            <div class="mt-2">
              <div class="w-full bg-gray-200 rounded-full h-1.5">
                <div class="bg-primary-600 h-1.5 rounded-full transition-all" :style="{ width: (data?.occupancy_rate ?? 0) + '%' }" />
              </div>
            </div>
            <p class="text-xs text-muted mt-1">{{ data?.active_bookings ?? 0 }} حجز نشط</p>
          </div>
          <div class="w-11 h-11 rounded-lg flex items-center justify-center shrink-0 bg-primary-50 text-primary-700 text-lg">🏨</div>
        </div>
      </div>

      <StatCard
        label="الشاطئ اليوم"
        :value="loading ? '...' : (data?.beach_sold_today ?? 0)"
        icon="cart"
        variant="warning"
        trend-label="تذكرة مباعة"
        :loading="loading"
      />

      <StatCard
        label="مهام التنظيف"
        :value="loading ? '...' : (data?.pending_hk_tasks ?? 0)"
        icon="clipboard"
        :variant="(data?.pending_hk_tasks ?? 0) > 10 ? 'warning' : 'neutral'"
        trend-label="مهمة معلقة"
        :loading="loading"
      />
    </div>

    <!-- Analytics Sub-cards: HR / Maintenance / CRM / Inventory -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">

      <!-- HR -->
      <router-link to="/admin/hr" class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border p-4 shadow-sm hover:shadow-md transition-shadow">
        <div class="flex items-center gap-2 mb-2">
          <div class="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center text-base">👥</div>
          <span class="text-xs font-semibold text-gray-500 dark:text-gray-500">الموارد البشرية</span>
        </div>
        <div v-if="analyticsSummary.hr">
          <div class="text-2xl font-black text-gray-900 dark:text-gray-100">{{ analyticsSummary.hr.active_employees }}</div>
          <div class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">موظف نشط</div>
          <div v-if="analyticsSummary.hr.last_payroll_month" class="text-xs text-blue-600 mt-1">
            آخر رواتب: {{ analyticsSummary.hr.last_payroll_month }}
          </div>
        </div>
        <div v-else class="text-xs text-gray-300 mt-2">— لا بيانات</div>
      </router-link>

      <!-- Maintenance -->
      <router-link to="/admin/maintenance" class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border p-4 shadow-sm hover:shadow-md transition-shadow">
        <div class="flex items-center gap-2 mb-2">
          <div class="w-8 h-8 bg-orange-100 rounded-lg flex items-center justify-center text-base">🔧</div>
          <span class="text-xs font-semibold text-gray-500 dark:text-gray-500">الصيانة</span>
        </div>
        <div v-if="analyticsSummary.maintenance">
          <div class="text-2xl font-black"
            :class="analyticsSummary.maintenance.critical_orders > 0 ? 'text-red-600' : 'text-gray-900 dark:text-gray-100'">
            {{ analyticsSummary.maintenance.open_orders }}
          </div>
          <div class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">أمر مفتوح</div>
          <div v-if="analyticsSummary.maintenance.critical_orders > 0" class="text-xs text-red-500 font-bold mt-1">
            {{ analyticsSummary.maintenance.critical_orders }} حرج 🔴
          </div>
        </div>
        <div v-else class="text-xs text-gray-300 mt-2">— لا بيانات</div>
      </router-link>

      <!-- CRM -->
      <router-link to="/admin/crm" class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border p-4 shadow-sm hover:shadow-md transition-shadow">
        <div class="flex items-center gap-2 mb-2">
          <div class="w-8 h-8 bg-purple-100 rounded-lg flex items-center justify-center text-base">🤝</div>
          <span class="text-xs font-semibold text-gray-500 dark:text-gray-500">إدارة العملاء</span>
        </div>
        <div v-if="analyticsSummary.crm">
          <div class="text-2xl font-black text-gray-900 dark:text-gray-100">{{ analyticsSummary.crm.total_customers }}</div>
          <div class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">عميل مسجّل</div>
          <div v-if="analyticsSummary.crm.open_opportunities > 0" class="text-xs text-purple-600 mt-1">
            {{ analyticsSummary.crm.open_opportunities }} فرصة مفتوحة
          </div>
        </div>
        <div v-else class="text-xs text-gray-300 mt-2">— لا بيانات</div>
      </router-link>

      <!-- Inventory -->
      <router-link to="/admin/inventory" class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border p-4 shadow-sm hover:shadow-md transition-shadow">
        <div class="flex items-center gap-2 mb-2">
          <div class="w-8 h-8 bg-amber-100 rounded-lg flex items-center justify-center text-base">📦</div>
          <span class="text-xs font-semibold text-gray-500 dark:text-gray-500">المخزون</span>
        </div>
        <div v-if="analyticsSummary.inventory">
          <div class="text-2xl font-black"
            :class="analyticsSummary.inventory.out_of_stock_count > 0 ? 'text-red-600' : analyticsSummary.inventory.low_stock_count > 0 ? 'text-amber-600' : 'text-green-600'">
            {{ analyticsSummary.inventory.low_stock_count + analyticsSummary.inventory.out_of_stock_count }}
          </div>
          <div class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">صنف يحتاج طلباً</div>
          <div v-if="analyticsSummary.inventory.out_of_stock_count > 0" class="text-xs text-red-500 font-bold mt-1">
            {{ analyticsSummary.inventory.out_of_stock_count }} نفذ تماماً 🔴
          </div>
        </div>
        <div v-else class="text-xs text-gray-300 mt-2">— لا بيانات</div>
      </router-link>

    </div>

    <!-- Timeshare Upcoming Visits -->
    <div v-if="upcomingVisits.length" class="mb-6">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-bold text-gray-700 dark:text-gray-300">🏨 زيارات التايم شير القادمة</h3>
        <router-link to="/admin/timeshare" class="text-xs text-primary-700 hover:underline">عرض الكل</router-link>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <div v-for="v in upcomingVisits" :key="v.id"
          class="bg-white dark:bg-surface border border-stone-200 dark:border-border rounded-xl p-3 flex items-start gap-3 shadow-sm">
          <div class="w-9 h-9 bg-primary-100 rounded-xl flex items-center justify-center text-primary-700 font-black text-sm shrink-0">
            {{ new Date(v.visit_start).getDate() }}
          </div>
          <div class="min-w-0">
            <div class="font-semibold text-gray-900 dark:text-gray-100 text-sm truncate">{{ v.guest_name }}</div>
            <div class="text-xs text-gray-500 dark:text-gray-500 mt-0.5">
              {{ new Date(v.visit_start).toLocaleDateString('ar-EG', { month: 'short', day: 'numeric' }) }}
              →
              {{ new Date(v.visit_end).toLocaleDateString('ar-EG', { month: 'short', day: 'numeric' }) }}
            </div>
            <div v-if="v.unit_name" class="text-xs text-primary-600 mt-0.5">{{ v.unit_name }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Quick links -->
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
      <router-link v-for="link in quickLinks" :key="link.path" :to="link.path"
        :class="[`flex items-center gap-3 p-4 rounded-xl border-2 transition-colors`, link.color]"
      >
        <span class="text-2xl">{{ link.icon }}</span>
        <span class="font-semibold text-gray-800 dark:text-gray-200">{{ link.label }}</span>
      </router-link>
    </div>
  </div>
</template>
