<script setup lang="ts">
/**
 * ShiftDashboardView — /pos/shift (wagdy.md بند S-01).
 *
 * الباك إند كان جاهزًا بالكامل من غير أي واجهة تجمّعه في مكان واحد:
 * GET /finance/shifts/{id}/report (ملخص المبيعات، X/Z-Report — نفس بند
 * S-04)، GET /finance/shifts/{id}/invoices (سجل الفواتير، S-02)، وGET
 * /dining/orders?status=... (الطلبات/الطاولات الجارية عبر كل المنافذ).
 * الكاشير كان عنده بس ShiftPanel.vue المدمج في هيدر FieldLayout — عرض
 * مختصر (فتح/قفل بس، من غير أي رقم مبيعات أو رؤية على الطلبات الجارية).
 * الشاشة دي عرض أوسع، مش تكرار لـ ShiftPanel: بتضمّه فعليًا (نفس منطق
 * فتح/قفل الوردية وعدّ الكاش، بدون تكرار الكود) وتضيف حوله ملخص المبيعات
 * اللحظي + الطلبات الجارية عبر كل منافذ الدايننج (DINING_CUTOVER_PLAN.md
 * Batch 6 — كانت restaurant+cafe منفصلين، دلوقتي مصدر واحد مجمّع حسب
 * outlet بدل موديول ثابت، عشان يفضل يشتغل صح لأي outlet_type مستقبلي).
 */
import { ref, computed, onMounted } from 'vue'
import { api, useAuthStore, ENDPOINTS } from '@resort-os/core'
import { AppCard, AppBadge, EmptyState, useToast } from '@resort-os/ui'
import ShiftPanel from '../../components/ShiftPanel.vue'
import InvoiceLogModal from '../../components/InvoiceLogModal.vue'
import CashControlPanel from '../../components/CashControlPanel.vue'

const auth = useAuthStore()
const toast = useToast()
const branchId = computed(() => auth.branchId ?? 1)

interface CurrentShift { id: number; opened_at: string; opening_float: number | string; status: string }
const shift = ref<CurrentShift | null>(null)
const loadingShift = ref(true)

async function fetchShift() {
  loadingShift.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.shiftsCurrent, { params: { branch_id: branchId.value } })
    shift.value = data
    await Promise.all([loadReport(), loadOpenOrders()])
  } catch (e: any) {
    shift.value = null
    if (e?.response?.status !== 404) toast.error('تعذّر تحميل حالة الوردية')
  } finally {
    loadingShift.value = false
  }
}

// ── ملخص المبيعات — نفس تقرير X/Z-Report (S-04)، بيتقرا وسط الوردية من
// غير ما يحتاج قفلها (GET .../report مش محتاج status=closed) ──────────────
interface ShiftReport {
  total_cash: number | string; total_card: number | string; total_credit: number | string
  total_other: number | string; total_sales: number | string
  invoice_count: number; voided_count: number; voided_amount: number | string
  opening_float: number | string
}
const report = ref<ShiftReport | null>(null)
const loadingReport = ref(false)

async function loadReport() {
  if (!shift.value) return
  loadingReport.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.shiftReport(shift.value.id))
    report.value = data
  } catch {
    toast.error('تعذّر تحميل ملخص المبيعات')
  } finally {
    loadingReport.value = false
  }
}

// ── الطلبات الجارية (كل منافذ الدايننج) — DINING_CUTOVER_PLAN.md Batch 6:
// كانت restaurant/cafe نداءين منفصلين على endpoints مختلفة، دلوقتي مصدر
// واحد (/dining/orders) مجمّع حسب outlet_id فعليًا بدل موديول ثابت في
// الكود، عشان يفضل يشتغل صح لأي outlet_type يتضاف مستقبلاً من غير تعديل
// هنا (pagination كامل، status واحد لكل نداء — نفس نمط UnifiedPOSView) ──
interface LiveOrder { id: number; order_number: string; status: string; table_id: number | null; order_type: string; total: number | string; outlet_id: number }
interface Outlet { id: number; name: string; name_ar: string | null }
const outletsById = ref<Record<number, Outlet>>({})
const ordersByOutlet = ref<{ outlet: Outlet; orders: LiveOrder[] }[]>([])
const loadingOrders = ref(false)

async function fetchOutlets(): Promise<void> {
  const { data } = await api.get(ENDPOINTS.dining.outlets, { params: { branch_id: branchId.value, active_only: true } })
  const list: Outlet[] = data?.items ?? data ?? []
  outletsById.value = Object.fromEntries(list.map(o => [o.id, o]))
}

async function fetchAllOpenOrders(): Promise<LiveOrder[]> {
  const fetchStatus = async (status: string): Promise<LiveOrder[]> => {
    const PAGE_SIZE = 100
    const results: LiveOrder[] = []
    let page = 1
    while (true) {
      const res = await api.get(ENDPOINTS.dining.orders, { params: { branch_id: branchId.value, status, page, size: PAGE_SIZE } })
      const items: LiveOrder[] = res.data?.items ?? res.data ?? []
      results.push(...items)
      if (items.length < PAGE_SIZE) break
      page++
    }
    return results
  }
  const [open, inKitchen, served] = await Promise.all([
    fetchStatus('open'), fetchStatus('in_kitchen'), fetchStatus('served'),
  ])
  return [...open, ...inKitchen, ...served]
}

async function loadOpenOrders() {
  loadingOrders.value = true
  try {
    await fetchOutlets()
    const orders = await fetchAllOpenOrders()
    const grouped = new Map<number, LiveOrder[]>()
    for (const o of orders) {
      if (!grouped.has(o.outlet_id)) grouped.set(o.outlet_id, [])
      grouped.get(o.outlet_id)!.push(o)
    }
    ordersByOutlet.value = [...grouped.entries()]
      .map(([outletId, list]) => ({
        outlet: outletsById.value[outletId] ?? { id: outletId, name: `منفذ #${outletId}`, name_ar: null },
        orders: list,
      }))
      .sort((a, b) => a.outlet.id - b.outlet.id)
  } catch {
    toast.error('تعذّر تحميل الطلبات الجارية')
  } finally {
    loadingOrders.value = false
  }
}

const totalOpenOrdersCount = computed(() => ordersByOutlet.value.reduce((sum, g) => sum + g.orders.length, 0))
const openTablesCount = computed(() =>
  new Set(ordersByOutlet.value.flatMap(g => g.orders).filter(o => o.table_id).map(o => `${o.table_id}`)).size,
)

const STATUS_LABEL: Record<string, string> = { open: 'مفتوح', in_kitchen: 'في المطبخ', served: 'اتقدّم' }
const STATUS_VARIANT: Record<string, 'success' | 'warning' | 'info'> = { open: 'info', in_kitchen: 'warning', served: 'success' }

function orderLabel(o: LiveOrder): string {
  return o.table_id ? `طاولة ${o.table_id}` : 'Takeaway'
}

// ── سجل الفواتير (S-02) — بوابة PIN مدير+ داخل InvoiceLogModal نفسها ─────
const showInvoiceLog = ref(false)

function refreshAll() {
  fetchShift()
}

onMounted(fetchShift)
</script>

<template>
  <div class="page-container" dir="rtl">
    <div class="flex items-center justify-between mb-4 gap-2 flex-wrap">
      <h1 class="section-title mb-0">لوحة الوردية</h1>
      <button
        @click="refreshAll"
        class="text-xs text-blue-600 font-semibold hover:text-blue-800 disabled:opacity-50"
        :disabled="loadingShift"
      >🔄 تحديث</button>
    </div>

    <div v-if="loadingShift && !shift" class="flex items-center justify-center py-16">
      <div class="animate-spin w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full" />
    </div>

    <EmptyState
      v-else-if="!shift"
      icon="🔒"
      title="لا توجد وردية مفتوحة"
      description="افتح وردية من الزر أسفل عشان تشوف لوحة التحكم الكاملة"
    />

    <template v-else>
      <!-- التحكم في الوردية (فتح/قفل + عدّ الكاش) — نفس ShiftPanel المستخدم
           في هيدر FieldLayout بالظبط، من غير أي تكرار لمنطق القفل/عدّ الكاش -->
      <AppCard class="mb-4" padding="sm">
        <div class="flex items-center justify-between px-1">
          <span class="text-sm font-bold text-gray-700 dark:text-gray-300">وردية #{{ shift.id }}</span>
          <ShiftPanel @shift-changed="refreshAll" />
        </div>
      </AppCard>

      <!-- ضبط الكاش (Cash Control ledger) — إيداع/سحب/عهدة/تنزيل خزنة/فتح
           درج/تصحيح، كل واحدة محتاجة موافقة PIN مدير+ (راجع CashControlPanel) -->
      <CashControlPanel :shift-id="shift.id" />

      <!-- ملخص المبيعات — X-Report (S-04)، مبني على نفس endpoint التقرير
           بدون قفل الوردية -->
      <AppCard title="ملخص المبيعات (X-Report)" class="mb-4">
        <div v-if="loadingReport" class="text-center text-sm text-gray-400 py-4">جاري التحميل...</div>
        <template v-else-if="report">
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div class="bg-emerald-50 rounded-xl p-3 text-center border border-emerald-100">
              <div class="text-lg font-black text-emerald-700">{{ Number(report.total_sales).toFixed(2) }}</div>
              <div class="text-xs text-emerald-600 mt-0.5">إجمالي المبيعات</div>
            </div>
            <div class="bg-blue-50 rounded-xl p-3 text-center border border-blue-100">
              <div class="text-lg font-black text-blue-700">{{ Number(report.total_cash).toFixed(2) }}</div>
              <div class="text-xs text-blue-600 mt-0.5">كاش</div>
            </div>
            <div class="bg-purple-50 rounded-xl p-3 text-center border border-purple-100">
              <div class="text-lg font-black text-purple-700">{{ Number(report.total_card).toFixed(2) }}</div>
              <div class="text-xs text-purple-600 mt-0.5">كارت</div>
            </div>
            <div class="bg-stone-50 rounded-xl p-3 text-center border border-stone-200 dark:border-border">
              <div class="text-lg font-black text-gray-700 dark:text-gray-300">{{ report.invoice_count }}</div>
              <div class="text-xs text-gray-500 mt-0.5">عدد الفواتير</div>
            </div>
          </div>
          <p v-if="report.voided_count > 0" class="text-xs text-red-500 mt-2">
            ⚠️ {{ report.voided_count }} فاتورة ملغاة بقيمة {{ Number(report.voided_amount).toFixed(2) }} ج
          </p>
          <div class="flex gap-2 mt-3">
            <button
              @click="showInvoiceLog = true"
              class="flex-1 py-2 text-xs font-bold text-blue-700 bg-blue-50 border border-blue-100 rounded-lg hover:bg-blue-100"
            >📋 سجل الفواتير</button>
            <a
              :href="ENDPOINTS.finance.shiftReportPdf(shift.id)"
              target="_blank"
              class="flex-1 py-2 text-xs font-bold text-gray-600 bg-stone-50 border border-stone-200 dark:border-border rounded-lg text-center hover:bg-stone-100"
            >📄 تحميل PDF</a>
          </div>
        </template>
      </AppCard>

      <!-- الطاولات/الطلبات المفتوحة لحظيًا (كل منافذ الدايننج) -->
      <AppCard :title="`الطلبات الجارية (${totalOpenOrdersCount}) — ${openTablesCount} طاولة مفتوحة`">
        <div v-if="loadingOrders" class="text-center text-sm text-gray-400 py-4">جاري التحميل...</div>
        <EmptyState
          v-else-if="totalOpenOrdersCount === 0"
          icon="✅"
          title="مفيش طلبات جارية حاليًا"
        />
        <div v-else class="space-y-4">
          <div v-for="group in ordersByOutlet" :key="group.outlet.id">
            <h3 class="text-xs font-bold text-gray-400 uppercase mb-1.5">{{ group.outlet.name_ar || group.outlet.name }}</h3>
            <div class="divide-y divide-stone-100">
              <div v-for="o in group.orders" :key="o.id" class="py-2 flex items-center justify-between gap-2">
                <div>
                  <span class="text-sm font-semibold text-gray-800 dark:text-gray-200">{{ o.order_number }}</span>
                  <span class="text-xs text-gray-400 mr-2">{{ orderLabel(o) }}</span>
                </div>
                <div class="flex items-center gap-2">
                  <span class="text-sm font-bold text-blue-700">{{ Number(o.total).toFixed(2) }} ج</span>
                  <AppBadge :variant="STATUS_VARIANT[o.status] ?? 'neutral'">{{ STATUS_LABEL[o.status] ?? o.status }}</AppBadge>
                </div>
              </div>
            </div>
          </div>
        </div>
      </AppCard>
    </template>

    <InvoiceLogModal v-if="showInvoiceLog && shift" :shift-id="shift.id" @close="showInvoiceLog = false" />
  </div>
</template>
