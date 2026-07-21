<script setup lang="ts">
// AnalyticsView — لوحة التحليلات الشاملة
//
// يقرأ من endpoints حقيقية في analytics/api/router.py (كلها read-only، get_manager_user):
//   GET /api/v1/analytics/dashboard        ← إيرادات 30 يوم + HR + صيانة + CRM + مخزون + تقييمات
//   GET /api/v1/analytics/occupancy        ← نسبة إشغال PMS للشهر الحالي
//   GET /api/v1/analytics/daily-stats      ← لقطة اليوم (DailyStats model، ممكن تكون فاضية)
//   GET /api/v1/analytics/reviews          ← أحدث تقييمات الضيوف
//   GET /api/v1/analytics/reviews/insights ← GSS score + تفصيل حسب الفئة (نظافة/خدمة/طعام...)
//   GET/POST /api/v1/analytics/utilities   ← قراءات عدادات المرافق (كهرباء/مياه/غاز/ديزل)
//   GET /api/v1/analytics/energy           ← تكلفة كيلوواط/نزيل شهريًا
//
// آخر 3 endpoints (insights/utilities/energy) كانت موجودة بالكامل في الباك
// إند (schema/crud/router + تستات) من غير أي واجهة تستخدمها خالص — نفس فئة
// "الموديل موجود، الواجهة صفر" الموثّقة في CLAUDE.md. اتضافوا هنا كقسمين
// صغيرين (مش شاشة منفصلة) عشان يكتمل الموديول من غير ميزة كبيرة جديدة.
//
// كل الأقسام تُجمّع من modules تانية (restaurant/cafe/pms/beach/hr/...) عبر
// _safe_query في الباك إند — لو module مش مبني، القيمة بترجع null، فكل قسم
// هنا لازم يتعامل مع احتمال null بشكل صريح (مش يفترض وجود بيانات).
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppInput, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const { t } = useI18n()
const { formatNumber, formatDate } = useStaffFormat()
const auth = useAuthStore()
const branchId = auth.branchId

interface Revenue30d {
  restaurant: number
  cafe:       number
  pms:        number
  beach:      number
  total:      number
}
interface DashboardResponse {
  branch_id:   number
  as_of:       string
  revenue_30d: Revenue30d | null
  hr:          { active_employees: number; last_payroll_period: string | null } | null
  maintenance: { open_work_orders: number } | null
  crm:         { total_customers: number } | null
  inventory:   { low_stock_count: number } | null
  reviews:     { count: number; avg_rating: number | null } | null
}
interface OccupancyResponse {
  month: number
  year:  number
  pms:   { nights_audited: number; avg_occupancy_pct: number; total_room_revenue: number } | null
}
interface DailyStatsResponse {
  stat_date:           string
  message?:            string
  occupancy_pct?:      number
  adr?:                number
  revpar?:             number
  room_revenue?:       number
  beach_visitors?:     number
  beach_revenue?:      number
  restaurant_covers?:  number
  restaurant_revenue?: number
  cafe_revenue?:       number
  total_revenue?:      number
}
interface ReviewItem {
  id:             number
  guest_name:     string
  overall_rating: number
  comment:        string | null
  source:         string
  reviewed_at:    string
}
interface ReviewsResponse {
  total:      number
  avg_rating: number
  items:      ReviewItem[]
}
interface CategoryInsight { category: string; avg_rating: number; count: number }
interface ReviewInsightsResponse {
  overall_avg:       number | null
  gss_score:         number | null
  review_count:      number
  category_breakdown: CategoryInsight[]
}
interface UtilityReading {
  id: number; reading_date: string; utility_type: string
  reading_value: string; unit: string; unit_cost: string; total_cost: string
}
interface EnergyKpi {
  period: string
  by_type: Record<string, number>
  total_cost: number
  guest_nights: number
  electricity_cost_per_guest_night: number | null
}

const loading    = ref(true)
const dashboard  = ref<DashboardResponse | null>(null)
const occupancy  = ref<OccupancyResponse | null>(null)
const dailyStats = ref<DailyStatsResponse | null>(null)
const reviews    = ref<ReviewsResponse | null>(null)
const reviewInsights = ref<ReviewInsightsResponse | null>(null)
const utilityReadings = ref<UtilityReading[]>([])
const energyKpi = ref<EnergyKpi | null>(null)
const savingUtility = ref(false)

// ── مقارنة الإيرادات شهر بشهر (R-02) ───────────────────────────────────
interface RevenueCompare {
  period: { from: string; to: string }
  total: number | null
  restaurant: number | null
  cafe: number | null
  pms: number | null
  beach: number | null
}
const revCurrent = ref<RevenueCompare | null>(null)
const revPrevious = ref<RevenueCompare | null>(null)
const revLoading = ref(false)

async function loadRevenueComparison() {
  revLoading.value = true
  try {
    const now = new Date()
    // الشهر الحالي: 1 → آخر يوم
    const thisFrom = new Date(now.getFullYear(), now.getMonth(), 1)
    const thisTo   = new Date(now.getFullYear(), now.getMonth() + 1, 0)
    // الشهر الماضي
    const prevFrom = new Date(now.getFullYear(), now.getMonth() - 1, 1)
    const prevTo   = new Date(now.getFullYear(), now.getMonth(), 0)
    const fmt = (d: Date) => d.toISOString().slice(0, 10)
    const [curRes, prevRes] = await Promise.all([
      api.get(ENDPOINTS.analytics.revenue, { params: { branch_id: branchId, date_from: fmt(thisFrom), date_to: fmt(thisTo) } }),
      api.get(ENDPOINTS.analytics.revenue, { params: { branch_id: branchId, date_from: fmt(prevFrom), date_to: fmt(prevTo) } }),
    ])
    revCurrent.value  = curRes.data
    revPrevious.value = prevRes.data
  } catch { /* صامت — ممكن مفيش بيانات */ }
  finally { revLoading.value = false }
}

function revDiff(cur: number | null, prev: number | null): { pct: string; up: boolean } | null {
  if (!cur || !prev || prev === 0) return null
  const pct = ((cur - prev) / prev) * 100
  return { pct: Math.abs(pct).toFixed(1), up: pct >= 0 }
}

const categoryLabels = computed<Record<string, string>>(() => ({
  cleanliness: t('backoffice.analytics.category.cleanliness'), service: t('backoffice.analytics.category.service'),
  value: t('backoffice.analytics.category.value'), beach: t('backoffice.analytics.category.beach'),
  food: t('backoffice.analytics.category.food'), location: t('backoffice.analytics.category.location'),
}))
const utilityTypeLabels = computed<Record<string, string>>(() => ({
  electricity: t('backoffice.analytics.utilityType.electricity'), water: t('backoffice.analytics.utilityType.water'),
  gas: t('backoffice.analytics.utilityType.gas'), diesel: t('backoffice.analytics.utilityType.diesel'),
}))
const currentPeriod = new Date().toISOString().slice(0, 7)  // YYYY-MM
const utilityForm = reactive({
  utility_type:  'electricity',
  reading_date:  new Date().toISOString().slice(0, 10),
  reading_value: '',
  unit_cost:     '',
})

async function loadDashboard() {
  try {
    const res = await api.get('/api/v1/analytics/dashboard', { params: { branch_id: branchId } })
    dashboard.value = res.data
  } catch {
    toast.error(t('backoffice.analytics.msg.loadDashboardError'))
    dashboard.value = null
  }
}

async function loadOccupancy() {
  try {
    const res = await api.get('/api/v1/analytics/occupancy', { params: { branch_id: branchId } })
    occupancy.value = res.data
  } catch {
    toast.error(t('backoffice.analytics.msg.loadOccupancyError'))
    occupancy.value = null
  }
}

async function loadDailyStats() {
  try {
    const res = await api.get('/api/v1/analytics/daily-stats', { params: { branch_id: branchId } })
    dailyStats.value = res.data
  } catch {
    toast.error(t('backoffice.analytics.msg.loadDailyStatsError'))
    dailyStats.value = null
  }
}

async function loadReviews() {
  try {
    const res = await api.get('/api/v1/analytics/reviews', { params: { branch_id: branchId, size: 5 } })
    reviews.value = res.data
  } catch {
    toast.error(t('backoffice.analytics.msg.loadReviewsError'))
    reviews.value = null
  }
}

async function loadReviewInsights() {
  try {
    const res = await api.get('/api/v1/analytics/reviews/insights', { params: { branch_id: branchId } })
    reviewInsights.value = res.data
  } catch {
    toast.error(t('backoffice.analytics.msg.loadReviewInsightsError'))
    reviewInsights.value = null
  }
}

async function loadUtilities() {
  try {
    const res = await api.get('/api/v1/analytics/utilities', { params: { branch_id: branchId } })
    utilityReadings.value = res.data
  } catch {
    toast.error(t('backoffice.analytics.msg.loadUtilitiesError'))
    utilityReadings.value = []
  }
}

async function loadEnergy() {
  try {
    const res = await api.get('/api/v1/analytics/energy', { params: { branch_id: branchId, period: currentPeriod } })
    energyKpi.value = res.data
  } catch {
    energyKpi.value = null
  }
}

// #18: اتجاه شهري (24 شهر = سنة حالية + سابقة) بدل لقطة شهر واحد بس —
// السنة الحالية (آخر 12 شهر) مقابل نفس الأشهر من السنة اللي فاتت، من نفس
// الرد الواحد (مفيش طلب تاني منفصل للمقارنة).
interface EnergyTrendPoint {
  period: string; by_type: Record<string, number>; total_cost: number
  guest_nights: number; electricity_cost_per_guest_night: number | null
}
const energyTrend = ref<EnergyTrendPoint[]>([])
const exportingEnergyTrend = ref(false)

const thisYearTrend = computed(() => energyTrend.value.slice(12))
const lastYearTrend = computed(() => energyTrend.value.slice(0, 12))
const trendMaxCost = computed(() => Math.max(...energyTrend.value.map(pt => pt.total_cost), 1))
function monthLabelShort(period: string) {
  const [, m] = period.split('-')
  const months = t('backoffice.analytics.monthsShort').split(',')
  return months[Number(m)]
}
// مقارنة سنة بسنة لإجمالي تكلفة آخر 12 شهر مقابل الـ 12 قبلهم
const yoyChangePct = computed(() => {
  const thisYearTotal = thisYearTrend.value.reduce((s, t) => s + t.total_cost, 0)
  const lastYearTotal = lastYearTrend.value.reduce((s, t) => s + t.total_cost, 0)
  if (!lastYearTotal) return null
  return Math.round(((thisYearTotal - lastYearTotal) / lastYearTotal) * 100)
})

async function loadEnergyTrend() {
  try {
    const res = await api.get('/api/v1/analytics/energy/trend', {
      params: { branch_id: branchId, end_period: currentPeriod, months: 24 },
    })
    energyTrend.value = res.data
  } catch {
    energyTrend.value = []
  }
}

async function exportEnergyTrend() {
  exportingEnergyTrend.value = true
  try {
    const res = await api.get('/api/v1/analytics/energy/trend/export', {
      params: { branch_id: branchId, end_period: currentPeriod, months: 24 },
      responseType: 'blob',
    })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `energy-trend-${currentPeriod}.xlsx`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 5000)
  } catch {
    toast.error(t('backoffice.analytics.msg.exportEnergyTrendError'))
  } finally {
    exportingEnergyTrend.value = false
  }
}

async function submitUtilityReading() {
  if (!utilityForm.reading_value || Number(utilityForm.reading_value) <= 0) {
    toast.error(t('backoffice.analytics.msg.enterPositiveReading'))
    return
  }
  savingUtility.value = true
  try {
    await api.post('/api/v1/analytics/utilities', {
      branch_id: branchId,
      reading_date: utilityForm.reading_date,
      utility_type: utilityForm.utility_type,
      reading_value: utilityForm.reading_value,
      unit_cost: utilityForm.unit_cost || '0',
    })
    toast.success(t('backoffice.analytics.msg.readingRecorded'))
    utilityForm.reading_value = ''
    utilityForm.unit_cost = ''
    await Promise.all([loadUtilities(), loadEnergy()])
  } catch {
    toast.error(t('backoffice.analytics.msg.recordReadingError'))
  } finally {
    savingUtility.value = false
  }
}

async function loadAll() {
  loading.value = true
  await Promise.all([
    loadDashboard(), loadOccupancy(), loadDailyStats(), loadReviews(),
    loadReviewInsights(), loadUtilities(), loadEnergy(), loadEnergyTrend(),
    loadRevenueComparison(),
  ])
  loading.value = false
}

function money(n: number | null | undefined) {
  return formatNumber(n ?? 0, { maximumFractionDigits: 0 })
}

function ratingVariant(rating: number): 'success' | 'warning' | 'danger' {
  if (rating >= 4) return 'success'
  if (rating >= 3) return 'warning'
  return 'danger'
}

const reviewSourceLabels = computed<Record<string, string>>(() => ({
  google: t('backoffice.analytics.reviewSource.google'), tripadvisor: 'TripAdvisor',
  internal: t('backoffice.analytics.reviewSource.internal'), facebook: t('backoffice.analytics.reviewSource.facebook'),
}))

onMounted(loadAll)
</script>

<template>
  <div class="space-y-5">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-black text-gray-800 dark:text-gray-200">{{ t('backoffice.analytics.title') }}</h1>
        <p class="text-sm text-gray-500 dark:text-gray-500 mt-1">{{ t('backoffice.analytics.subtitle') }}</p>
      </div>
      <button v-if="!loading" @click="loadAll" class="text-sm font-semibold text-blue-700 hover:underline">
        {{ t('backoffice.analytics.refresh') }} ↻
      </button>
    </div>

    <div v-if="loading" class="flex justify-center py-16">
      <AppSpinner size="lg" />
    </div>

    <template v-else>
      <!-- بطاقات المؤشرات الرئيسية -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <AppCard padding="md">
          <div class="text-sm text-gray-500 dark:text-gray-500 mb-2">{{ t('backoffice.analytics.totalRevenue30d') }}</div>
          <div class="text-2xl font-black text-green-600">{{ money(dashboard?.revenue_30d?.total) }}</div>
          <div class="text-xs text-gray-400 dark:text-gray-500 mt-1">{{ t('backoffice.analytics.currency') }}</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 dark:text-gray-500 mb-2">{{ t('backoffice.analytics.occupancyThisMonth') }}</div>
          <div class="text-2xl font-black text-blue-700">
            {{ occupancy?.pms ? occupancy.pms.avg_occupancy_pct.toFixed(1) + '%' : '—' }}
          </div>
          <div class="text-xs text-gray-400 dark:text-gray-500 mt-1">{{ occupancy?.pms ? t('backoffice.analytics.nightsAudited', { count: occupancy.pms.nights_audited }) : t('backoffice.analytics.noData') }}</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 dark:text-gray-500 mb-2">{{ t('backoffice.analytics.activeEmployees') }}</div>
          <div class="text-2xl font-black text-gray-800 dark:text-gray-200">{{ dashboard?.hr?.active_employees ?? '—' }}</div>
          <div class="text-xs text-gray-400 dark:text-gray-500 mt-1">{{ dashboard?.hr?.last_payroll_period ? t('backoffice.analytics.lastPayroll', { period: dashboard.hr.last_payroll_period }) : t('backoffice.analytics.noPayrollRecord') }}</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 dark:text-gray-500 mb-2">{{ t('backoffice.analytics.openWorkOrders') }}</div>
          <div class="text-2xl font-black text-amber-600">{{ dashboard?.maintenance?.open_work_orders ?? '—' }}</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 dark:text-gray-500 mb-2">{{ t('backoffice.analytics.lowStockItems') }}</div>
          <div class="text-2xl font-black text-red-500">{{ dashboard?.inventory?.low_stock_count ?? '—' }}</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 dark:text-gray-500 mb-2">{{ t('backoffice.analytics.totalCustomers') }}</div>
          <div class="text-2xl font-black text-gray-800 dark:text-gray-200">{{ dashboard?.crm?.total_customers ?? '—' }}</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 dark:text-gray-500 mb-2">{{ t('backoffice.analytics.avgGuestRating') }}</div>
          <div class="text-2xl font-black text-gray-800 dark:text-gray-200">
            {{ dashboard?.reviews?.avg_rating != null ? dashboard.reviews.avg_rating.toFixed(2) : '—' }}
          </div>
          <div class="text-xs text-gray-400 dark:text-gray-500 mt-1">{{ dashboard?.reviews?.count ? t('backoffice.analytics.reviewCount', { count: dashboard.reviews.count }) : t('backoffice.analytics.noReviews') }}</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 dark:text-gray-500 mb-2">{{ t('backoffice.analytics.pmsRevenue30d') }}</div>
          <div class="text-2xl font-black text-gray-800 dark:text-gray-200">{{ money(dashboard?.revenue_30d?.pms) }}</div>
          <div class="text-xs text-gray-400 dark:text-gray-500 mt-1">{{ t('backoffice.analytics.currency') }}</div>
        </AppCard>
      </div>

      <!-- تفصيل الإيرادات -->
      <AppCard :title="t('backoffice.analytics.revenueBreakdown30d')">
        <EmptyState v-if="!dashboard?.revenue_30d" icon="📊" :title="t('backoffice.analytics.noRevenueData')" :subtitle="t('backoffice.analytics.noRevenueDataHint')" />
        <div v-else class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.analytics.column.department') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.analytics.column.revenueCurrency') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr class="border-t border-stone-100 dark:border-border/50">
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ t('backoffice.analytics.dining') }}</td>
                <td class="px-4 py-3 text-sm font-bold text-gray-900 dark:text-gray-100">{{ money(dashboard.revenue_30d.restaurant) }}</td>
              </tr>
              <tr class="border-t border-stone-100 dark:border-border/50">
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ t('backoffice.analytics.cafe') }}</td>
                <td class="px-4 py-3 text-sm font-bold text-gray-900 dark:text-gray-100">{{ money(dashboard.revenue_30d.cafe) }}</td>
              </tr>
              <tr class="border-t border-stone-100 dark:border-border/50">
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ t('backoffice.analytics.pmsRooms') }}</td>
                <td class="px-4 py-3 text-sm font-bold text-gray-900 dark:text-gray-100">{{ money(dashboard.revenue_30d.pms) }}</td>
              </tr>
              <tr class="border-t border-stone-100 dark:border-border/50">
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ t('backoffice.analytics.beach') }}</td>
                <td class="px-4 py-3 text-sm font-bold text-gray-900 dark:text-gray-100">{{ money(dashboard.revenue_30d.beach) }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.analytics.total') }}</td>
                <td class="px-4 py-3 text-sm font-black text-green-700">{{ money(dashboard.revenue_30d.total) }}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </AppCard>

      <!-- مقارنة الإيرادات: هذا الشهر vs الشهر الماضي (R-02) -->
      <AppCard :title="t('backoffice.analytics.revenueComparisonTitle')">
        <div v-if="revLoading" class="flex justify-center py-6"><AppSpinner /></div>
        <div v-else-if="!revCurrent && !revPrevious">
          <EmptyState icon="📈" :title="t('backoffice.analytics.noComparisonData')" />
        </div>
        <div v-else class="space-y-3">
          <!-- فترتا المقارنة -->
          <div class="flex gap-2 text-xs text-gray-400 dark:text-gray-500 mb-2">
            <span class="bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full font-semibold">
              {{ t('backoffice.analytics.thisMonth') }}: {{ revCurrent?.period.from }} → {{ revCurrent?.period.to }}
            </span>
            <span class="bg-stone-100 dark:bg-gray-700 text-gray-600 dark:text-gray-500 px-2 py-0.5 rounded-full font-semibold">
              {{ t('backoffice.analytics.lastMonth') }}: {{ revPrevious?.period.from }} → {{ revPrevious?.period.to }}
            </span>
          </div>

          <!-- صفوف المقارنة -->
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-stone-200 dark:border-border">
                <th class="px-3 py-2 text-start text-xs text-gray-500 dark:text-gray-500 font-semibold">{{ t('backoffice.analytics.column.source') }}</th>
                <th class="px-3 py-2 text-start text-xs text-blue-600 font-semibold">{{ t('backoffice.analytics.thisMonth') }}</th>
                <th class="px-3 py-2 text-start text-xs text-gray-400 dark:text-gray-500 font-semibold">{{ t('backoffice.analytics.lastMonth') }}</th>
                <th class="px-3 py-2 text-start text-xs text-gray-500 dark:text-gray-500 font-semibold">{{ t('backoffice.analytics.change') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in [
                { label: `🍽️ ${t('backoffice.analytics.dining')}`, cur: revCurrent?.restaurant, prev: revPrevious?.restaurant },
                { label: `☕ ${t('backoffice.analytics.cafe')}`, cur: revCurrent?.cafe, prev: revPrevious?.cafe },
                { label: `🛏️ ${t('backoffice.analytics.stay')}`, cur: revCurrent?.pms, prev: revPrevious?.pms },
                { label: `🏖️ ${t('backoffice.analytics.beach')}`, cur: revCurrent?.beach, prev: revPrevious?.beach },
              ]" :key="row.label" class="border-b border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-3 py-2 font-medium text-gray-700 dark:text-gray-300">{{ row.label }}</td>
                <td class="px-3 py-2 font-bold text-blue-700">{{ money(row.cur ?? 0) }} {{ t('backoffice.analytics.currency') }}</td>
                <td class="px-3 py-2 text-gray-500 dark:text-gray-500">{{ money(row.prev ?? 0) }} {{ t('backoffice.analytics.currency') }}</td>
                <td class="px-3 py-2">
                  <span v-if="revDiff(row.cur ?? null, row.prev ?? null)" :class="[
                    'text-xs font-bold px-2 py-0.5 rounded-full',
                    revDiff(row.cur ?? null, row.prev ?? null)!.up ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-600'
                  ]">
                    {{ revDiff(row.cur ?? null, row.prev ?? null)!.up ? '▲' : '▼' }}
                    {{ revDiff(row.cur ?? null, row.prev ?? null)!.pct }}%
                  </span>
                  <span v-else class="text-xs text-gray-400 dark:text-gray-500">—</span>
                </td>
              </tr>
              <tr class="border-t-2 border-stone-300 bg-stone-50 dark:bg-gray-800/60 font-black">
                <td class="px-3 py-2 text-gray-900 dark:text-gray-100">{{ t('backoffice.analytics.total') }}</td>
                <td class="px-3 py-2 text-green-700 text-base">{{ money(revCurrent?.total ?? 0) }} {{ t('backoffice.analytics.currency') }}</td>
                <td class="px-3 py-2 text-gray-500 dark:text-gray-500 text-base">{{ money(revPrevious?.total ?? 0) }} {{ t('backoffice.analytics.currency') }}</td>
                <td class="px-3 py-2">
                  <span v-if="revDiff(revCurrent?.total ?? null, revPrevious?.total ?? null)" :class="[
                    'text-sm font-black px-2 py-0.5 rounded-full',
                    revDiff(revCurrent?.total ?? null, revPrevious?.total ?? null)!.up ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-700'
                  ]">
                    {{ revDiff(revCurrent?.total ?? null, revPrevious?.total ?? null)!.up ? '▲' : '▼' }}
                    {{ revDiff(revCurrent?.total ?? null, revPrevious?.total ?? null)!.pct }}%
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>

      <!-- إحصائيات اليوم -->
      <AppCard :title="t('backoffice.analytics.todayStats')">
        <EmptyState v-if="!dailyStats || dailyStats.message" icon="🗓️" :title="t('backoffice.analytics.noTodayData')" :subtitle="t('backoffice.analytics.noTodayDataHint')" />
        <div v-else class="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">{{ t('backoffice.analytics.occupancyRate') }}</div>
            <div class="text-lg font-black text-blue-700">{{ dailyStats.occupancy_pct?.toFixed(1) }}%</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">ADR</div>
            <div class="text-lg font-black text-gray-800 dark:text-gray-200">{{ money(dailyStats.adr) }}</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">RevPAR</div>
            <div class="text-lg font-black text-gray-800 dark:text-gray-200">{{ money(dailyStats.revpar) }}</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">{{ t('backoffice.analytics.beachVisitors') }}</div>
            <div class="text-lg font-black text-gray-800 dark:text-gray-200">{{ dailyStats.beach_visitors }}</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">{{ t('backoffice.analytics.diningCovers') }}</div>
            <div class="text-lg font-black text-gray-800 dark:text-gray-200">{{ dailyStats.restaurant_covers }}</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">{{ t('backoffice.analytics.roomRevenue') }}</div>
            <div class="text-lg font-black text-gray-800 dark:text-gray-200">{{ money(dailyStats.room_revenue) }}</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">{{ t('backoffice.analytics.beachRevenue') }}</div>
            <div class="text-lg font-black text-gray-800 dark:text-gray-200">{{ money(dailyStats.beach_revenue) }}</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">{{ t('backoffice.analytics.diningRevenue') }}</div>
            <div class="text-lg font-black text-gray-800 dark:text-gray-200">{{ money(dailyStats.restaurant_revenue) }}</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">{{ t('backoffice.analytics.cafeRevenue') }}</div>
            <div class="text-lg font-black text-gray-800 dark:text-gray-200">{{ money(dailyStats.cafe_revenue) }}</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">{{ t('backoffice.analytics.todayTotal') }}</div>
            <div class="text-lg font-black text-green-700">{{ money(dailyStats.total_revenue) }}</div>
          </div>
        </div>
      </AppCard>

      <!-- أحدث تقييمات الضيوف -->
      <AppCard :title="t('backoffice.analytics.latestReviews')">
        <div v-if="reviews && reviews.total > 0" class="flex items-center gap-2 mb-4">
          <AppBadge variant="info">{{ t('backoffice.analytics.publishedReviewCount', { count: reviews.total }) }}</AppBadge>
          <AppBadge :variant="ratingVariant(reviews.avg_rating)">{{ t('backoffice.analytics.avgRatingOf5', { rating: reviews.avg_rating.toFixed(2) }) }}</AppBadge>
        </div>
        <EmptyState v-if="!reviews || reviews.items.length === 0" icon="⭐" :title="t('backoffice.analytics.noPublishedReviews')" />
        <div v-else class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.analytics.column.guest') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.analytics.column.rating') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.analytics.column.comment') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.analytics.column.source') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.analytics.column.date') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in reviews.items" :key="r.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">{{ r.guest_name }}</td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="ratingVariant(r.overall_rating)">{{ r.overall_rating }} / 5</AppBadge>
                </td>
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-500 max-w-xs truncate">{{ r.comment ?? '—' }}</td>
                <td class="px-4 py-3 text-sm text-gray-500 dark:text-gray-500">{{ reviewSourceLabels[r.source] ?? r.source }}</td>
                <td class="px-4 py-3 text-sm text-gray-500 dark:text-gray-500">{{ formatDate(r.reviewed_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>

      <!-- تفصيل التقييمات حسب الفئة (GSS) -->
      <AppCard :title="t('backoffice.analytics.reviewsByCategory')">
        <div v-if="reviewInsights && reviewInsights.gss_score != null" class="flex items-center gap-2 mb-4">
          <AppBadge variant="info">GSS {{ reviewInsights.gss_score.toFixed(2) }} / 5</AppBadge>
          <span class="text-xs text-gray-400 dark:text-gray-500">{{ t('backoffice.analytics.ofPublishedReviews', { count: reviewInsights.review_count }) }}</span>
        </div>
        <EmptyState v-if="!reviewInsights || reviewInsights.category_breakdown.length === 0" icon="📋" :title="t('backoffice.analytics.noCategoryReviews')" />
        <div v-else class="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div v-for="c in reviewInsights.category_breakdown" :key="c.category" class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">{{ categoryLabels[c.category] ?? c.category }}</div>
            <div class="text-lg font-black text-gray-800 dark:text-gray-200">{{ c.avg_rating.toFixed(2) }} / 5</div>
            <div class="w-full bg-gray-200 rounded-full h-1.5 mt-1">
              <div class="bg-blue-600 h-1.5 rounded-full" :style="{ width: (c.avg_rating / 5 * 100) + '%' }" />
            </div>
            <div class="text-xs text-gray-400 dark:text-gray-500 mt-1">{{ t('backoffice.analytics.reviewCount', { count: c.count }) }}</div>
          </div>
        </div>
      </AppCard>

      <!-- عدادات المرافق -->
      <AppCard :title="t('backoffice.analytics.utilitiesTitle')">
        <div class="grid grid-cols-2 md:grid-cols-5 gap-3 items-end mb-5">
          <div class="flex flex-col gap-1">
            <label class="text-sm font-medium text-gray-700 dark:text-gray-300">{{ t('backoffice.analytics.typeLabel') }}</label>
            <select v-model="utilityForm.utility_type" class="w-full px-3 py-2 rounded-lg border border-stone-200 dark:border-border bg-white dark:bg-surface text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500">
              <option value="electricity">{{ t('backoffice.analytics.utilityType.electricity') }}</option>
              <option value="water">{{ t('backoffice.analytics.utilityType.water') }}</option>
              <option value="gas">{{ t('backoffice.analytics.utilityType.gas') }}</option>
              <option value="diesel">{{ t('backoffice.analytics.utilityType.diesel') }}</option>
            </select>
          </div>
          <AppInput :label="t('backoffice.analytics.column.date')" type="date" v-model="utilityForm.reading_date" />
          <AppInput :label="t('backoffice.analytics.consumption')" type="number" placeholder="1500" v-model="utilityForm.reading_value" />
          <AppInput :label="t('backoffice.analytics.unitCostCurrency')" type="number" placeholder="2.5" v-model="utilityForm.unit_cost" />
          <AppButton variant="primary" :loading="savingUtility" @click="submitUtilityReading">{{ t('backoffice.analytics.recordReading') }}</AppButton>
        </div>

        <div v-if="energyKpi" class="flex flex-wrap items-center gap-2 mb-4">
          <AppBadge variant="info">{{ t('backoffice.analytics.totalUtilitiesCostMonth', { amount: money(energyKpi.total_cost) }) }}</AppBadge>
          <AppBadge v-if="energyKpi.electricity_cost_per_guest_night != null" variant="warning">
            {{ t('backoffice.analytics.costPerGuestNight', { amount: energyKpi.electricity_cost_per_guest_night.toFixed(2) }) }}
          </AppBadge>
        </div>

        <!-- #18: اتجاه شهري (سنة حالية + سابقة) + تصدير — بدل لقطة شهر واحد -->
        <div v-if="thisYearTrend.length" class="mb-5 border-t border-stone-100 dark:border-border/50 pt-4">
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-2">
              <p class="text-sm font-bold text-gray-700 dark:text-gray-300">📈 {{ t('backoffice.analytics.utilitiesCostTrend') }}</p>
              <AppBadge v-if="yoyChangePct !== null" :variant="yoyChangePct > 0 ? 'danger' : 'success'">
                {{ yoyChangePct > 0 ? '▲' : '▼' }} {{ t('backoffice.analytics.yoyChange', { pct: Math.abs(yoyChangePct) }) }}
              </AppBadge>
            </div>
            <AppButton variant="secondary" size="sm" :loading="exportingEnergyTrend" @click="exportEnergyTrend">
              📊 {{ t('backoffice.analytics.exportExcel') }}
            </AppButton>
          </div>
          <div class="flex items-end gap-1.5 h-28 bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
            <div v-for="pt in thisYearTrend" :key="pt.period" class="flex-1 flex flex-col items-center justify-end h-full gap-1">
              <div class="w-full bg-blue-500 rounded-t" :style="{ height: `${Math.max(4, (pt.total_cost / trendMaxCost) * 100)}%` }"
                :title="`${pt.period}: ${money(pt.total_cost)} ${t('backoffice.analytics.currency')}`" />
              <span class="text-[9px] text-gray-400 dark:text-gray-500">{{ monthLabelShort(pt.period) }}</span>
            </div>
          </div>
        </div>

        <EmptyState v-if="utilityReadings.length === 0" icon="🔌" :title="t('backoffice.analytics.noReadingsRecorded')" />
        <div v-else class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.analytics.column.date') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.analytics.typeLabel') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.analytics.consumption') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.analytics.totalCost') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in utilityReadings.slice(0, 10)" :key="r.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3 text-sm text-gray-500 dark:text-gray-500">{{ formatDate(r.reading_date) }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ utilityTypeLabels[r.utility_type] ?? r.utility_type }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ r.reading_value }} {{ r.unit }}</td>
                <td class="px-4 py-3 text-sm font-bold text-gray-900 dark:text-gray-100">{{ money(Number(r.total_cost)) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </template>
  </div>
</template>
