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
import { ref, reactive, onMounted } from 'vue'
import { api } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppInput, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

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

const categoryLabels: Record<string, string> = {
  cleanliness: 'النظافة', service: 'الخدمة', value: 'القيمة مقابل السعر',
  beach: 'الشاطئ', food: 'الطعام', location: 'الموقع',
}
const utilityTypeLabels: Record<string, string> = {
  electricity: 'كهرباء', water: 'مياه', gas: 'غاز', diesel: 'ديزل',
}
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
    toast.error('تعذّر تحميل لوحة المؤشرات العامة — تأكد من اتصالك وحاول تاني')
    dashboard.value = null
  }
}

async function loadOccupancy() {
  try {
    const res = await api.get('/api/v1/analytics/occupancy', { params: { branch_id: branchId } })
    occupancy.value = res.data
  } catch {
    toast.error('تعذّر تحميل نسبة الإشغال — تأكد من اتصالك وحاول تاني')
    occupancy.value = null
  }
}

async function loadDailyStats() {
  try {
    const res = await api.get('/api/v1/analytics/daily-stats', { params: { branch_id: branchId } })
    dailyStats.value = res.data
  } catch {
    toast.error('تعذّر تحميل إحصائيات اليوم — تأكد من اتصالك وحاول تاني')
    dailyStats.value = null
  }
}

async function loadReviews() {
  try {
    const res = await api.get('/api/v1/analytics/reviews', { params: { branch_id: branchId, size: 5 } })
    reviews.value = res.data
  } catch {
    toast.error('تعذّر تحميل تقييمات الضيوف — تأكد من اتصالك وحاول تاني')
    reviews.value = null
  }
}

async function loadReviewInsights() {
  try {
    const res = await api.get('/api/v1/analytics/reviews/insights', { params: { branch_id: branchId } })
    reviewInsights.value = res.data
  } catch {
    toast.error('تعذّر تحميل تفصيل التقييمات حسب الفئة')
    reviewInsights.value = null
  }
}

async function loadUtilities() {
  try {
    const res = await api.get('/api/v1/analytics/utilities', { params: { branch_id: branchId } })
    utilityReadings.value = res.data
  } catch {
    toast.error('تعذّر تحميل قراءات المرافق')
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

async function submitUtilityReading() {
  if (!utilityForm.reading_value || Number(utilityForm.reading_value) <= 0) {
    toast.error('اكتب قيمة استهلاك أكبر من صفر')
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
    toast.success('اتسجّلت قراءة المرفق')
    utilityForm.reading_value = ''
    utilityForm.unit_cost = ''
    await Promise.all([loadUtilities(), loadEnergy()])
  } catch {
    toast.error('تعذّر تسجيل القراءة — تأكد من البيانات وحاول تاني')
  } finally {
    savingUtility.value = false
  }
}

async function loadAll() {
  loading.value = true
  await Promise.all([
    loadDashboard(), loadOccupancy(), loadDailyStats(), loadReviews(),
    loadReviewInsights(), loadUtilities(), loadEnergy(),
  ])
  loading.value = false
}

function money(n: number | null | undefined) {
  return (n ?? 0).toLocaleString('ar-EG', { maximumFractionDigits: 0 })
}

function ratingVariant(rating: number): 'success' | 'warning' | 'danger' {
  if (rating >= 4) return 'success'
  if (rating >= 3) return 'warning'
  return 'danger'
}

const reviewSourceLabels: Record<string, string> = {
  google: 'جوجل', tripadvisor: 'TripAdvisor', internal: 'استبيان داخلي', facebook: 'فيسبوك',
}

onMounted(loadAll)
</script>

<template>
  <div dir="rtl" class="space-y-5">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-black text-gray-800">التقارير والتحليلات</h1>
        <p class="text-sm text-gray-500 mt-1">نظرة عامة على أداء المنتجع — آخر 30 يوم وأحدث المؤشرات</p>
      </div>
      <button v-if="!loading" @click="loadAll" class="text-sm font-semibold text-blue-700 hover:underline">
        تحديث ↻
      </button>
    </div>

    <div v-if="loading" class="flex justify-center py-16">
      <AppSpinner size="lg" />
    </div>

    <template v-else>
      <!-- بطاقات المؤشرات الرئيسية -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <AppCard padding="md">
          <div class="text-sm text-gray-500 mb-2">إجمالي الإيرادات (30 يوم)</div>
          <div class="text-2xl font-black text-green-600">{{ money(dashboard?.revenue_30d?.total) }}</div>
          <div class="text-xs text-gray-400 mt-1">جنيه</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 mb-2">نسبة الإشغال (الشهر الحالي)</div>
          <div class="text-2xl font-black text-blue-700">
            {{ occupancy?.pms ? occupancy.pms.avg_occupancy_pct.toFixed(1) + '%' : '—' }}
          </div>
          <div class="text-xs text-gray-400 mt-1">{{ occupancy?.pms ? `${occupancy.pms.nights_audited} ليلة مدقّقة` : 'لا توجد بيانات' }}</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 mb-2">الموظفون النشطون</div>
          <div class="text-2xl font-black text-gray-800">{{ dashboard?.hr?.active_employees ?? '—' }}</div>
          <div class="text-xs text-gray-400 mt-1">{{ dashboard?.hr?.last_payroll_period ? `آخر رواتب: ${dashboard.hr.last_payroll_period}` : 'لا يوجد سجل رواتب' }}</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 mb-2">أوامر صيانة مفتوحة</div>
          <div class="text-2xl font-black text-amber-600">{{ dashboard?.maintenance?.open_work_orders ?? '—' }}</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 mb-2">أصناف منخفضة المخزون</div>
          <div class="text-2xl font-black text-red-500">{{ dashboard?.inventory?.low_stock_count ?? '—' }}</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 mb-2">إجمالي العملاء</div>
          <div class="text-2xl font-black text-gray-800">{{ dashboard?.crm?.total_customers ?? '—' }}</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 mb-2">متوسط تقييم الضيوف</div>
          <div class="text-2xl font-black text-gray-800">
            {{ dashboard?.reviews?.avg_rating != null ? dashboard.reviews.avg_rating.toFixed(2) : '—' }}
          </div>
          <div class="text-xs text-gray-400 mt-1">{{ dashboard?.reviews?.count ? `${dashboard.reviews.count} تقييم` : 'لا توجد تقييمات' }}</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 mb-2">إيراد الفنادق (30 يوم)</div>
          <div class="text-2xl font-black text-gray-800">{{ money(dashboard?.revenue_30d?.pms) }}</div>
          <div class="text-xs text-gray-400 mt-1">جنيه</div>
        </AppCard>
      </div>

      <!-- تفصيل الإيرادات -->
      <AppCard title="تفصيل الإيرادات — آخر 30 يوم">
        <EmptyState v-if="!dashboard?.revenue_30d" icon="📊" title="لا تتوفر بيانات إيرادات" subtitle="موديولات الإيرادات (مطعم/كافيه/فنادق/شاطئ) غير متاحة حاليًا" />
        <div v-else class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">القسم</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الإيراد (جنيه)</th>
              </tr>
            </thead>
            <tbody>
              <tr class="border-t border-stone-100">
                <td class="px-4 py-3 text-sm text-gray-700">المطعم</td>
                <td class="px-4 py-3 text-sm font-bold text-gray-900">{{ money(dashboard.revenue_30d.restaurant) }}</td>
              </tr>
              <tr class="border-t border-stone-100">
                <td class="px-4 py-3 text-sm text-gray-700">الكافيه</td>
                <td class="px-4 py-3 text-sm font-bold text-gray-900">{{ money(dashboard.revenue_30d.cafe) }}</td>
              </tr>
              <tr class="border-t border-stone-100">
                <td class="px-4 py-3 text-sm text-gray-700">الفنادق (PMS)</td>
                <td class="px-4 py-3 text-sm font-bold text-gray-900">{{ money(dashboard.revenue_30d.pms) }}</td>
              </tr>
              <tr class="border-t border-stone-100">
                <td class="px-4 py-3 text-sm text-gray-700">الشاطئ</td>
                <td class="px-4 py-3 text-sm font-bold text-gray-900">{{ money(dashboard.revenue_30d.beach) }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="border-t-2 border-stone-200 bg-stone-50">
                <td class="px-4 py-3 text-sm font-black text-gray-900">الإجمالي</td>
                <td class="px-4 py-3 text-sm font-black text-green-700">{{ money(dashboard.revenue_30d.total) }}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </AppCard>

      <!-- إحصائيات اليوم -->
      <AppCard title="إحصائيات اليوم">
        <EmptyState v-if="!dailyStats || dailyStats.message" icon="🗓️" title="لا توجد بيانات لهذا اليوم" subtitle="لسه ما اتسجّلش إحصائيات (DailyStats) لليوم الحالي" />
        <div v-else class="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div class="text-center">
            <div class="text-xs text-gray-400 mb-1">نسبة الإشغال</div>
            <div class="text-lg font-black text-blue-700">{{ dailyStats.occupancy_pct?.toFixed(1) }}%</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 mb-1">ADR</div>
            <div class="text-lg font-black text-gray-800">{{ money(dailyStats.adr) }}</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 mb-1">RevPAR</div>
            <div class="text-lg font-black text-gray-800">{{ money(dailyStats.revpar) }}</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 mb-1">زوار الشاطئ</div>
            <div class="text-lg font-black text-gray-800">{{ dailyStats.beach_visitors }}</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 mb-1">عدد كفوفر المطعم</div>
            <div class="text-lg font-black text-gray-800">{{ dailyStats.restaurant_covers }}</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 mb-1">إيراد الغرف</div>
            <div class="text-lg font-black text-gray-800">{{ money(dailyStats.room_revenue) }}</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 mb-1">إيراد الشاطئ</div>
            <div class="text-lg font-black text-gray-800">{{ money(dailyStats.beach_revenue) }}</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 mb-1">إيراد المطعم</div>
            <div class="text-lg font-black text-gray-800">{{ money(dailyStats.restaurant_revenue) }}</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 mb-1">إيراد الكافيه</div>
            <div class="text-lg font-black text-gray-800">{{ money(dailyStats.cafe_revenue) }}</div>
          </div>
          <div class="text-center">
            <div class="text-xs text-gray-400 mb-1">إجمالي اليوم</div>
            <div class="text-lg font-black text-green-700">{{ money(dailyStats.total_revenue) }}</div>
          </div>
        </div>
      </AppCard>

      <!-- أحدث تقييمات الضيوف -->
      <AppCard title="أحدث تقييمات الضيوف">
        <div v-if="reviews && reviews.total > 0" class="flex items-center gap-2 mb-4">
          <AppBadge variant="info">{{ reviews.total }} تقييم منشور</AppBadge>
          <AppBadge :variant="ratingVariant(reviews.avg_rating)">متوسط {{ reviews.avg_rating.toFixed(2) }} / 5</AppBadge>
        </div>
        <EmptyState v-if="!reviews || reviews.items.length === 0" icon="⭐" title="لا توجد تقييمات منشورة بعد" />
        <div v-else class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الضيف</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">التقييم</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">التعليق</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">المصدر</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">التاريخ</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in reviews.items" :key="r.id" class="border-t border-stone-100 hover:bg-stone-50">
                <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ r.guest_name }}</td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="ratingVariant(r.overall_rating)">{{ r.overall_rating }} / 5</AppBadge>
                </td>
                <td class="px-4 py-3 text-sm text-gray-600 max-w-xs truncate">{{ r.comment ?? '—' }}</td>
                <td class="px-4 py-3 text-sm text-gray-500">{{ reviewSourceLabels[r.source] ?? r.source }}</td>
                <td class="px-4 py-3 text-sm text-gray-500">{{ new Date(r.reviewed_at).toLocaleDateString('ar-EG') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>

      <!-- تفصيل التقييمات حسب الفئة (GSS) -->
      <AppCard title="تفصيل تقييمات الضيوف حسب الفئة">
        <div v-if="reviewInsights && reviewInsights.gss_score != null" class="flex items-center gap-2 mb-4">
          <AppBadge variant="info">GSS {{ reviewInsights.gss_score.toFixed(2) }} / 5</AppBadge>
          <span class="text-xs text-gray-400">من {{ reviewInsights.review_count }} تقييم منشور</span>
        </div>
        <EmptyState v-if="!reviewInsights || reviewInsights.category_breakdown.length === 0" icon="📋" title="لا توجد تقييمات مفصّلة حسب الفئة بعد" />
        <div v-else class="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div v-for="c in reviewInsights.category_breakdown" :key="c.category" class="text-center">
            <div class="text-xs text-gray-400 mb-1">{{ categoryLabels[c.category] ?? c.category }}</div>
            <div class="text-lg font-black text-gray-800">{{ c.avg_rating.toFixed(2) }} / 5</div>
            <div class="w-full bg-gray-200 rounded-full h-1.5 mt-1">
              <div class="bg-blue-600 h-1.5 rounded-full" :style="{ width: (c.avg_rating / 5 * 100) + '%' }" />
            </div>
            <div class="text-xs text-gray-400 mt-1">{{ c.count }} تقييم</div>
          </div>
        </div>
      </AppCard>

      <!-- عدادات المرافق -->
      <AppCard title="عدادات المرافق (كهرباء / مياه / غاز / ديزل)">
        <div class="grid grid-cols-2 md:grid-cols-5 gap-3 items-end mb-5">
          <div class="flex flex-col gap-1">
            <label class="text-sm font-medium text-gray-700">النوع</label>
            <select v-model="utilityForm.utility_type" class="w-full px-3 py-2 rounded-lg border border-stone-200 bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500">
              <option value="electricity">كهرباء</option>
              <option value="water">مياه</option>
              <option value="gas">غاز</option>
              <option value="diesel">ديزل</option>
            </select>
          </div>
          <AppInput label="التاريخ" type="date" v-model="utilityForm.reading_date" />
          <AppInput label="الاستهلاك" type="number" placeholder="مثال: 1500" v-model="utilityForm.reading_value" />
          <AppInput label="تكلفة الوحدة (جنيه)" type="number" placeholder="مثال: 2.5" v-model="utilityForm.unit_cost" />
          <AppButton variant="primary" :loading="savingUtility" @click="submitUtilityReading">تسجيل القراءة</AppButton>
        </div>

        <div v-if="energyKpi" class="flex flex-wrap items-center gap-2 mb-4">
          <AppBadge variant="info">إجمالي تكلفة المرافق هذا الشهر: {{ money(energyKpi.total_cost) }} جنيه</AppBadge>
          <AppBadge v-if="energyKpi.electricity_cost_per_guest_night != null" variant="warning">
            {{ energyKpi.electricity_cost_per_guest_night.toFixed(2) }} جنيه / ليلة إشغال (كهرباء)
          </AppBadge>
        </div>

        <EmptyState v-if="utilityReadings.length === 0" icon="🔌" title="لا توجد قراءات مسجّلة بعد" />
        <div v-else class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">التاريخ</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">النوع</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الاستهلاك</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">التكلفة الإجمالية</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in utilityReadings.slice(0, 10)" :key="r.id" class="border-t border-stone-100 hover:bg-stone-50">
                <td class="px-4 py-3 text-sm text-gray-500">{{ new Date(r.reading_date).toLocaleDateString('ar-EG') }}</td>
                <td class="px-4 py-3 text-sm text-gray-700">{{ utilityTypeLabels[r.utility_type] ?? r.utility_type }}</td>
                <td class="px-4 py-3 text-sm text-gray-700">{{ r.reading_value }} {{ r.unit }}</td>
                <td class="px-4 py-3 text-sm font-bold text-gray-900">{{ money(Number(r.total_cost)) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </template>
  </div>
</template>
