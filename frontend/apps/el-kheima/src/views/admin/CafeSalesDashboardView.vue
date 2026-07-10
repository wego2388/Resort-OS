<script setup lang="ts">
/**
 * CafeSalesDashboardView — تقرير مبيعات الكافيه اليومي/الأسبوعي
 * مدير+ فقط
 */
import { ref, onMounted } from 'vue'
import { api, useAuthStore } from '@resort-os/core'

const branchId  = parseInt(localStorage.getItem('branch_id') ?? '1')
const authStore = useAuthStore()

interface DailyEntry  { orders: number; revenue: number }
interface TopItem     { name: string; qty: number; revenue: number }
interface PayMethod   { orders: number; total: number }
interface SalesReport {
  total_orders: number; total_revenue: number
  total_vat: number; total_discount: number; avg_order_value: number
  payment_breakdown: Record<string, PayMethod>
  top_items: TopItem[]
  daily: Record<string, DailyEntry>
}

const loading   = ref(false)
const loadError = ref(false)
const report    = ref<SalesReport | null>(null)

const today   = new Date().toISOString().slice(0, 10)
const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10)
const dateFrom = ref(weekAgo)
const dateTo   = ref(today)

const fmt = (v: number) =>
  `${v.toLocaleString('ar-EG', { maximumFractionDigits: 0 })} ج`
const fmtDate = (d: string) => {
  try { return new Date(d).toLocaleDateString('ar-EG', { day: 'numeric', month: 'short' }) }
  catch { return d }
}
const PAYMENT_LABELS: Record<string, string> = {
  cash: 'كاش 💵', card: 'كارت 💳', wallet: 'محفظة 📱', room: 'غرفة 🏨',
}

function maxRevenue(): number {
  if (!report.value) return 1
  return Math.max(...Object.values(report.value.daily).map(d => d.revenue), 1)
}

async function load() {
  loading.value = true; loadError.value = false
  try {
    const { data } = await api.get('/api/v1/cafe/reports/sales', {
      params: { branch_id: branchId, date_from: dateFrom.value, date_to: dateTo.value },
    })
    report.value = data
  } catch { loadError.value = true }
  finally { loading.value = false }
}

// #7: metadata في الـ CSV — فرع + تاريخ التصدير + اسم المستخدم
function exportCsv() {
  if (!report.value) return

  const r         = report.value
  const exportedAt = new Date().toLocaleString('ar-EG')
  const exportedBy = authStore.user?.full_name || authStore.user?.username || '—'
  const rows: string[][] = []

  // ── metadata ──
  rows.push(['# تقرير مبيعات الكافيه'])
  rows.push(['تاريخ التصدير', exportedAt])
  rows.push(['صدّره', exportedBy])
  rows.push(['الفرع', String(branchId)])
  rows.push(['الفترة', `${dateFrom.value} → ${dateTo.value}`])
  rows.push([])
  rows.push(['إجمالي الإيرادات', r.total_revenue.toFixed(2)])
  rows.push(['عدد الطلبات', String(r.total_orders)])
  rows.push(['متوسط قيمة الطلب', r.avg_order_value.toFixed(2)])
  rows.push(['إجمالي الضريبة', r.total_vat.toFixed(2)])
  rows.push(['إجمالي الخصم', r.total_discount.toFixed(2)])
  rows.push([])

  // ── طرق الدفع ──
  rows.push(['# طرق الدفع'])
  rows.push(['الطريقة', 'عدد الطلبات', 'الإجمالي'])
  for (const [method, pm] of Object.entries(r.payment_breakdown)) {
    rows.push([PAYMENT_LABELS[method] ?? method, String(pm.orders), pm.total.toFixed(2)])
  }
  rows.push([])

  // ── أكثر الأصناف مبيعًا ──
  rows.push(['# أكثر الأصناف مبيعًا'])
  rows.push(['الصنف', 'الكمية', 'الإيراد'])
  for (const item of r.top_items) {
    rows.push([item.name, String(item.qty), item.revenue.toFixed(2)])
  }
  rows.push([])

  // ── التفاصيل اليومية ──
  rows.push(['# التفاصيل اليومية'])
  rows.push(['التاريخ', 'عدد الطلبات', 'الإيراد'])
  for (const [date, entry] of Object.entries(r.daily).sort()) {
    rows.push([date, String(entry.orders), entry.revenue.toFixed(2)])
  }

  // BOM لدعم العربية في Excel
  const bom = '\uFEFF'
  const csv = bom + rows.map(r => r.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\r\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = `cafe-sales-${dateFrom.value}-to-${dateTo.value}.csv`
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}

onMounted(load)
</script>

<template>
  <div dir="rtl" class="p-6 max-w-5xl mx-auto">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6 flex-wrap gap-3">
      <div>
        <h1 class="text-xl font-black text-gray-900">☕ تقرير مبيعات الكافيه</h1>
        <p class="text-xs text-gray-400 mt-1">إجماليات المبيعات · أكثر الأصناف · تحليل طرق الدفع</p>
      </div>
      <div class="flex items-center gap-2 flex-wrap">
        <input v-model="dateFrom" type="date"
          class="border border-stone-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500" />
        <span class="text-gray-400">←</span>
        <input v-model="dateTo" type="date"
          class="border border-stone-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500" />
        <button @click="load"
          class="px-4 py-2 bg-amber-600 text-white rounded-lg font-bold text-sm hover:bg-amber-700 transition-colors">
          🔍 عرض
        </button>
        <!-- #25: export CSV -->
        <button
          v-if="report"
          @click="exportCsv"
          class="px-4 py-2 bg-green-600 text-white rounded-lg font-bold text-sm hover:bg-green-700 transition-colors"
          title="تصدير التقرير كـ CSV (يفتح في Excel)"
        >📥 CSV</button>
      </div>
    </div>

    <div v-if="loading" class="flex justify-center py-20">
      <div class="animate-spin w-8 h-8 border-4 border-amber-600 border-t-transparent rounded-full" />
    </div>

    <div v-else-if="loadError" class="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm flex items-center justify-between">
      <span>⚠️ تعذّر تحميل التقرير</span>
      <button @click="load" class="font-semibold underline">إعادة المحاولة</button>
    </div>

    <template v-else-if="report">
      <!-- KPI Cards -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <div class="bg-white rounded-2xl border border-amber-200 p-4 shadow-sm">
          <p class="text-[10px] text-gray-400 font-bold uppercase tracking-wide mb-2">إجمالي الإيرادات</p>
          <p class="text-2xl font-black text-amber-600">{{ fmt(report.total_revenue) }}</p>
        </div>
        <div class="bg-white rounded-2xl border border-blue-200 p-4 shadow-sm">
          <p class="text-[10px] text-gray-400 font-bold uppercase tracking-wide mb-2">عدد الطلبات</p>
          <p class="text-2xl font-black text-blue-600">{{ report.total_orders }}</p>
        </div>
        <div class="bg-white rounded-2xl border border-green-200 p-4 shadow-sm">
          <p class="text-[10px] text-gray-400 font-bold uppercase tracking-wide mb-2">متوسط الطلب</p>
          <p class="text-2xl font-black text-green-600">{{ fmt(report.avg_order_value) }}</p>
        </div>
        <div class="bg-white rounded-2xl border border-purple-200 p-4 shadow-sm">
          <p class="text-[10px] text-gray-400 font-bold uppercase tracking-wide mb-2">إجمالي الضريبة</p>
          <p class="text-2xl font-black text-purple-600">{{ fmt(report.total_vat) }}</p>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-6">
        <!-- Daily chart -->
        <div class="bg-white rounded-2xl border border-stone-200 p-5 shadow-sm">
          <h2 class="font-bold text-gray-900 mb-4">📅 الإيرادات اليومية</h2>
          <div v-if="Object.keys(report.daily).length === 0" class="text-center text-gray-400 py-8">
            لا توجد بيانات
          </div>
          <div v-else class="space-y-2">
            <div v-for="(entry, day) in report.daily" :key="day" class="flex items-center gap-3">
              <span class="text-xs text-gray-500 w-14 flex-shrink-0">{{ fmtDate(day) }}</span>
              <div class="flex-1 bg-stone-100 rounded-full h-5 overflow-hidden">
                <div class="h-full bg-amber-400 rounded-full transition-all"
                  :style="{ width: `${(entry.revenue / maxRevenue()) * 100}%` }" />
              </div>
              <span class="text-xs font-bold text-amber-700 w-20 text-right flex-shrink-0">{{ fmt(entry.revenue) }}</span>
              <span class="text-xs text-gray-400 w-10 text-right flex-shrink-0">{{ entry.orders }}✓</span>
            </div>
          </div>
        </div>

        <!-- Payment breakdown -->
        <div class="bg-white rounded-2xl border border-stone-200 p-5 shadow-sm">
          <h2 class="font-bold text-gray-900 mb-4">💳 طرق الدفع</h2>
          <div v-if="Object.keys(report.payment_breakdown).length === 0" class="text-center text-gray-400 py-8">لا توجد بيانات</div>
          <div v-else class="space-y-3">
            <div v-for="(info, method) in report.payment_breakdown" :key="method"
              class="flex items-center justify-between bg-stone-50 rounded-xl p-3">
              <div>
                <div class="font-bold text-gray-900 text-sm">{{ PAYMENT_LABELS[method] ?? method }}</div>
                <div class="text-xs text-gray-500">{{ info.orders }} طلب</div>
              </div>
              <div class="font-black text-amber-700 text-lg">{{ fmt(info.total) }}</div>
            </div>
          </div>
          <div v-if="report.total_discount > 0" class="mt-3 pt-3 border-t border-stone-200 flex justify-between text-sm">
            <span class="text-gray-500">إجمالي الخصومات</span>
            <span class="font-bold text-green-600">−{{ fmt(report.total_discount) }}</span>
          </div>
        </div>
      </div>

      <!-- Top Items -->
      <div class="bg-white rounded-2xl border border-stone-200 p-5 shadow-sm">
        <h2 class="font-bold text-gray-900 mb-4">🏆 أكثر الأصناف مبيعاً</h2>
        <div v-if="report.top_items.length === 0" class="text-center text-gray-400 py-8">لا توجد بيانات</div>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-xs text-gray-400 border-b border-stone-100">
                <th class="text-right pb-2 font-bold">#</th>
                <th class="text-right pb-2 font-bold pr-3">الصنف</th>
                <th class="text-right pb-2 font-bold">الكمية</th>
                <th class="text-right pb-2 font-bold">الإيراد</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, idx) in report.top_items" :key="item.name"
                class="border-b border-stone-50 hover:bg-amber-50 transition-colors">
                <td class="py-2.5 text-gray-400 font-bold">{{ idx + 1 }}</td>
                <td class="py-2.5 pr-3 font-semibold text-gray-900">{{ item.name }}</td>
                <td class="py-2.5">
                  <span class="bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-bold text-xs">
                    {{ item.qty }} قطعة
                  </span>
                </td>
                <td class="py-2.5 font-black text-amber-700">{{ fmt(item.revenue) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
