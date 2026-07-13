<script setup lang="ts">
// FoodCostReportView — تقرير تكلفة الطعام (Food Cost / COGS)
//
// يقارن التكلفة النظرية لكل صنف (وصفة/BOM × كمية مباعة فعليًا — راجع
// RecipesView.vue لإدارة الوصفة نفسها) بالإيراد الفعلي في مدى زمني، عشان
// يكشف الأصناف اللي نسبة تكلفتها أعلى من حد مقبول (منذر/alert) — نفس
// التقرير القياسي في صناعة المطاعم (theoretical vs actual food cost).
//
// Backend: app/modules/dining/api/router.py — GET /dining/outlets/{id}/
// reports/food-cost (مستوى مدير، نفس بوابة تعديل الوصفة نفسها). تابات
// المنافذ ديناميكية من /dining/outlets (DINING_CUTOVER_PLAN.md Batch 6 —
// كانت restaurant/cafe تابين ثابتين، دلوقتي أي عدد منافذ). راجع
// app.resort_os.food_cost_engine للفورمولا الخام.
//
// أصناف بدون وصفة (has_recipe=false) بتتعرض في الجدول لكن تكلفتها "غير
// معروفة" مش صفر — مُستبعدة من الملخص والاتجاه اليومي عمدًا (راجع تعليقات
// services.get_food_cost_report) عشان ما تضخّمش هامش الربح الظاهر بالغلط.
import { ref, computed, onMounted } from 'vue'
import { api, ENDPOINTS } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppInput, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

interface Outlet { id: number; name: string; name_ar: string | null; is_active: boolean }
const outlets = ref<Outlet[]>([])
const activeOutletId = ref<number | null>(null)
function outletLabel(o: Outlet): string { return o.name_ar || o.name }

interface ReportLine {
  item_id: number
  item_name: string
  variant_id: number | null
  has_recipe: boolean
  quantity_sold: number
  revenue: string
  theoretical_unit_cost: string
  theoretical_total_cost: string
  food_cost_pct: string | null
  gross_margin_amount: string
  gross_margin_pct: string | null
  exceeds_threshold: boolean
}
interface TrendPoint {
  date: string
  revenue: string
  theoretical_cost: string
  food_cost_pct: string | null
}
interface Summary {
  branch_id: number
  date_from: string
  date_to: string
  threshold_pct: string
  total_revenue: string
  total_theoretical_cost: string
  food_cost_pct: string | null
  gross_margin_amount: string
  gross_margin_pct: string | null
  items_missing_recipe: number
  items_missing_recipe_revenue: string
}
interface ReportResponse {
  lines: ReportLine[]
  alerts: ReportLine[]
  trend: TrendPoint[]
  summary: Summary
}

const loading = ref(true)
const report = ref<ReportResponse | null>(null)

function isoDate(d: Date) { return d.toISOString().slice(0, 10) }
const today = new Date()
const thirtyDaysAgo = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000)

const dateFrom = ref(isoDate(thirtyDaysAgo))
const dateTo = ref(isoDate(today))
const thresholdPct = ref('30')

function itemName(line: ReportLine) {
  return line.item_name ?? '—'
}
function itemKey(line: ReportLine) {
  return `${line.item_id}-${line.variant_id ?? 0}`
}

async function loadOutlets() {
  try {
    const { data } = await api.get(ENDPOINTS.dining.outlets, { params: { branch_id: branchId, active_only: true } })
    outlets.value = data?.items ?? data ?? []
    activeOutletId.value = outlets.value[0]?.id ?? null
  } catch {
    toast.error('تعذّر تحميل منافذ الدايننج')
  }
}

async function fetchReport() {
  if (activeOutletId.value == null) { report.value = null; return }
  loading.value = true
  try {
    const res = await api.get(ENDPOINTS.dining.foodCostReport(activeOutletId.value), {
      params: {
        date_from: dateFrom.value,
        date_to: dateTo.value,
        threshold_pct: thresholdPct.value || '30',
      },
    })
    report.value = res.data
  } catch {
    toast.error('تعذّر تحميل تقرير تكلفة الطعام — تأكد من المدى الزمني وحاول تاني')
    report.value = null
  } finally {
    loading.value = false
  }
}

function switchOutlet(id: number) {
  if (activeOutletId.value === id) return
  activeOutletId.value = id
  fetchReport()
}

// wagdy.md #16: تصدير Excel — نفس مدى التاريخ/الحد المعروض حاليًا
const exporting = ref(false)
async function exportExcel() {
  if (activeOutletId.value == null) return
  exporting.value = true
  try {
    const res = await api.get(`${ENDPOINTS.dining.foodCostReport(activeOutletId.value)}/export`, {
      params: { date_from: dateFrom.value, date_to: dateTo.value, threshold_pct: thresholdPct.value || '30' },
      responseType: 'blob',
    })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `food-cost-outlet-${activeOutletId.value}-${dateFrom.value}-to-${dateTo.value}.xlsx`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 5000)
  } catch {
    toast.error('تعذّر تصدير التقرير')
  } finally {
    exporting.value = false
  }
}

function money(v: string | number | null | undefined) {
  if (v == null) return '—'
  return Number(v).toLocaleString('ar-EG', { maximumFractionDigits: 2 })
}
function pct(v: string | null | undefined) {
  return v == null ? '—' : `${Number(v).toFixed(1)}%`
}

// أعلى نسبة تكلفة طعام معروفة (لأصناف عندها وصفة) — أساس تطبيع ارتفاع
// أعمدة اتجاه الـ trend (form: بار واحد لكل يوم، محور واحد، لا محورين).
const trendMax = computed(() => {
  if (!report.value) return 0
  const values = report.value.trend
    .map((t) => (t.food_cost_pct != null ? Number(t.food_cost_pct) : 0))
    .concat(Number(report.value.summary.threshold_pct))
  return Math.max(...values, 1)
})

function barHeightPct(point: TrendPoint) {
  if (point.food_cost_pct == null) return 0
  return Math.min(100, (Number(point.food_cost_pct) / trendMax.value) * 100)
}
function barStatus(point: TrendPoint): 'good' | 'critical' | 'muted' {
  if (!report.value || point.food_cost_pct == null) return 'muted'
  return Number(point.food_cost_pct) > Number(report.value.summary.threshold_pct) ? 'critical' : 'good'
}
function shortDay(iso: string) {
  return new Date(iso).toLocaleDateString('ar-EG', { day: 'numeric', month: 'numeric' })
}

onMounted(fetchReport)
</script>

<template>
  <div dir="rtl" class="space-y-5">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-black text-gray-800">تقرير تكلفة الطعام (Food Cost)</h1>
        <p class="text-sm text-gray-500 mt-1">
          التكلفة النظرية (وصفة × كمية مباعة فعليًا) مقابل الإيراد الفعلي — لكشف الأصناف اللي تكلفتها أعلى من المسموح.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <AppButton variant="secondary" size="sm" :disabled="loading || exporting || !report" :loading="exporting" @click="exportExcel">
          📊 تصدير Excel
        </AppButton>
        <AppButton variant="secondary" size="sm" :disabled="loading" @click="fetchReport">تحديث ↻</AppButton>
      </div>
    </div>

    <!-- Module tabs -->
    <div class="flex gap-2">
      <button
        v-for="m in (['restaurant', 'cafe'] as ModuleType[])" :key="m"
        @click="switchModule(m)"
        :class="['px-4 py-2 rounded-xl text-sm font-bold border-2 transition-colors',
                 activeModule === m ? 'border-blue-600 bg-blue-50 text-blue-700' : 'border-stone-200 text-gray-600 hover:border-blue-300']"
      >
        {{ m === 'restaurant' ? '🍽️ المطعم' : '☕ الكافيه' }}
      </button>
    </div>

    <!-- Filters -->
    <AppCard padding="md">
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 items-end">
        <AppInput label="من تاريخ" type="date" v-model="dateFrom" />
        <AppInput label="إلى تاريخ" type="date" v-model="dateTo" />
        <AppInput label="حد الإنذار (%)" type="number" placeholder="30" v-model="thresholdPct" />
        <AppButton variant="primary" :loading="loading" @click="fetchReport">تطبيق</AppButton>
      </div>
    </AppCard>

    <div v-if="loading" class="flex justify-center py-16">
      <AppSpinner size="lg" />
    </div>

    <template v-else-if="report">
      <!-- Summary KPIs -->
      <div class="grid grid-cols-2 md:grid-cols-5 gap-4">
        <AppCard padding="md">
          <div class="text-sm text-gray-500 mb-2">إجمالي الإيراد (مدى محسوب)</div>
          <div class="text-2xl font-black text-gray-900">{{ money(report.summary.total_revenue) }}</div>
          <div class="text-xs text-gray-400 mt-1">جنيه</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 mb-2">التكلفة النظرية</div>
          <div class="text-2xl font-black text-gray-900">{{ money(report.summary.total_theoretical_cost) }}</div>
          <div class="text-xs text-gray-400 mt-1">جنيه</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 mb-2">نسبة تكلفة الطعام</div>
          <div :class="['text-2xl font-black', report.summary.food_cost_pct != null && Number(report.summary.food_cost_pct) > Number(report.summary.threshold_pct) ? 'text-red-600' : 'text-green-700']">
            {{ pct(report.summary.food_cost_pct) }}
          </div>
          <div class="text-xs text-gray-400 mt-1">الحد: {{ report.summary.threshold_pct }}%</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 mb-2">هامش الربح الإجمالي</div>
          <div class="text-2xl font-black text-blue-700">{{ pct(report.summary.gross_margin_pct) }}</div>
          <div class="text-xs text-gray-400 mt-1">{{ money(report.summary.gross_margin_amount) }} جنيه</div>
        </AppCard>
        <AppCard padding="md">
          <div class="text-sm text-gray-500 mb-2">أصناف بدون وصفة</div>
          <div :class="['text-2xl font-black', report.summary.items_missing_recipe > 0 ? 'text-amber-600' : 'text-gray-800']">
            {{ report.summary.items_missing_recipe }}
          </div>
          <div class="text-xs text-gray-400 mt-1">
            {{ report.summary.items_missing_recipe > 0 ? `${money(report.summary.items_missing_recipe_revenue)} ج إيراد مُستبعد من الحساب` : 'كل المبيعات تكلفتها معروفة' }}
          </div>
        </AppCard>
      </div>

      <!-- Alerts -->
      <AppCard :title="`أصناف تخطّت حد الإنذار (${report.alerts.length})`">
        <EmptyState v-if="report.alerts.length === 0" icon="✅" title="مفيش أصناف تخطّت الحد حاليًا" subtitle="كل الأصناف اللي معاها وصفة نسبة تكلفتها تحت المسموح" />
        <div v-else class="flex flex-wrap gap-2">
          <AppBadge v-for="line in report.alerts" :key="itemKey(line)" variant="danger" size="sm">
            {{ itemName(line) }} — {{ pct(line.food_cost_pct) }}
          </AppBadge>
        </div>
      </AppCard>

      <!-- Daily trend -->
      <AppCard title="اتجاه نسبة تكلفة الطعام اليومي">
        <EmptyState v-if="report.trend.every((t) => t.food_cost_pct == null)" icon="📉"
          title="لا توجد بيانات كافية لرسم الاتجاه" subtitle="مفيش مبيعات لأصناف معاها وصفة في المدى ده" />
        <div v-else>
          <div class="flex items-end gap-1 h-32 border-b border-stone-200">
            <div v-for="point in report.trend" :key="point.date" class="flex-1 flex flex-col items-center justify-end h-full group relative"
              :title="`${shortDay(point.date)}: ${pct(point.food_cost_pct)} — إيراد ${money(point.revenue)} ج / تكلفة ${money(point.theoretical_cost)} ج`">
              <div
                :class="['w-full rounded-t transition-all',
                         barStatus(point) === 'critical' ? 'bg-red-500' : barStatus(point) === 'good' ? 'bg-green-500' : 'bg-stone-200']"
                :style="{ height: barStatus(point) === 'muted' ? '2px' : `${Math.max(barHeightPct(point), 2)}%` }"
              />
            </div>
          </div>
          <div class="flex gap-1 mt-1">
            <div v-for="point in report.trend" :key="point.date" class="flex-1 text-center text-[10px] text-gray-400 truncate">
              {{ shortDay(point.date) }}
            </div>
          </div>
          <div class="flex items-center gap-4 mt-3 text-xs text-gray-500">
            <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-sm bg-green-500 inline-block" /> ضمن الحد</span>
            <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-sm bg-red-500 inline-block" /> تخطّى الحد ({{ report.summary.threshold_pct }}%)</span>
            <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-sm bg-stone-200 inline-block" /> بدون مبيعات معروفة التكلفة</span>
          </div>
        </div>
      </AppCard>

      <!-- Full lines table -->
      <AppCard title="تفصيل الأصناف" padding="none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الصنف</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الوصفة</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الكمية المباعة</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الإيراد</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">تكلفة الوحدة</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">التكلفة الإجمالية</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">نسبة تكلفة الطعام</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">هامش الربح</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="line in report.lines" :key="itemKey(line)"
                :class="['border-t border-stone-100 hover:bg-stone-50', line.exceeds_threshold ? 'bg-red-50/60' : '']">
                <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ itemName(line) }}</td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="line.has_recipe ? 'neutral' : 'warning'">
                    {{ line.has_recipe ? 'موجودة' : 'ناقصة' }}
                  </AppBadge>
                </td>
                <td class="px-4 py-3 text-sm text-gray-700">{{ line.quantity_sold }}</td>
                <td class="px-4 py-3 text-sm text-gray-700">{{ money(line.revenue) }}</td>
                <td class="px-4 py-3 text-sm text-gray-500">{{ money(line.theoretical_unit_cost) }}</td>
                <td class="px-4 py-3 text-sm font-bold text-gray-900">{{ money(line.theoretical_total_cost) }}</td>
                <td class="px-4 py-3">
                  <AppBadge v-if="line.food_cost_pct != null" size="sm" :variant="line.exceeds_threshold ? 'danger' : 'success'">
                    {{ pct(line.food_cost_pct) }}
                  </AppBadge>
                  <span v-else class="text-xs text-gray-400">غير معروفة</span>
                </td>
                <td class="px-4 py-3 text-sm text-gray-700">{{ pct(line.gross_margin_pct) }}</td>
              </tr>
              <tr v-if="report.lines.length === 0">
                <td colspan="8" class="px-4 py-8">
                  <EmptyState icon="🍽️" title="لا توجد أصناف" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </template>
  </div>
</template>
