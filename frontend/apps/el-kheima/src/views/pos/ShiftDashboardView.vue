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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { api, useAuthStore, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppBadge, AppButton, AppCard, EmptyState, LoadingState, useToast } from '@resort-os/ui'
import ShiftPanel from '../../components/ShiftPanel.vue'
import InvoiceLogModal from '../../components/InvoiceLogModal.vue'
import CashControlPanel from '../../components/CashControlPanel.vue'

const auth = useAuthStore()
const toast = useToast()
const { t, locale } = useI18n()
const router = useRouter()
const { formatMoney } = useStaffFormat()
// CX-02C: branchId comes from bootstrap (session-scoped, no ?? 1 fallback).
const branchId = computed(() => auth.activeBranchId)

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
    if (e?.response?.status !== 404) toast.error(t('backoffice.shiftDashboard.msg.loadShiftError'))
  } finally {
    loadingShift.value = false
  }
}

// ── ملخص المبيعات — نفس تقرير X/Z-Report (S-04)، بيتقرا وسط الوردية من
// غير ما يحتاج قفلها (GET .../report مش محتاج status=closed) ──────────────
interface ShiftReport {
  // أساسي
  total_cash: number | string; total_card: number | string
  total_credit: number | string; total_other: number | string
  total_sales: number | string; total_room: number | string
  invoice_count: number; voided_count: number; voided_amount: number | string
  opening_float: number | string; expected_cash: number | string
  // مرتجعات
  refunds_total: number | string; refunds_count: number
  // مقارنة بالوردية السابقة
  previous_shift_id: number | null; previous_total_sales: number | string | null
  delta_vs_previous: number | string | null
  // حركات كاش يدوية
  cash_movements_effect: number | string; cash_movements_warning: string | null
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
    toast.error(t('backoffice.shiftDashboard.msg.loadReportError'))
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
        outlet: outletsById.value[outletId] ?? { id: outletId, name: t('backoffice.shiftDashboard.outletHash', { id: outletId }), name_ar: null },
        orders: list,
      }))
      .sort((a, b) => a.outlet.id - b.outlet.id)
  } catch {
    toast.error(t('backoffice.shiftDashboard.msg.loadOrdersError'))
  } finally {
    loadingOrders.value = false
  }
}

const totalOpenOrdersCount = computed(() => ordersByOutlet.value.reduce((sum, g) => sum + g.orders.length, 0))
const openTablesCount = computed(() =>
  new Set(ordersByOutlet.value.flatMap(g => g.orders).filter(o => o.table_id).map(o => `${o.table_id}`)).size,
)

const STATUS_LABEL = computed<Record<string, string>>(() => ({
  open: t('backoffice.shiftDashboard.orderStatus.open'), in_kitchen: t('backoffice.shiftDashboard.orderStatus.inKitchen'),
  served: t('backoffice.shiftDashboard.orderStatus.served'),
}))
const STATUS_VARIANT: Record<string, 'success' | 'warning' | 'info'> = { open: 'info', in_kitchen: 'warning', served: 'success' }

function orderLabel(o: LiveOrder): string {
  return o.table_id ? t('backoffice.shiftDashboard.tableNumber', { number: o.table_id }) : t('backoffice.shiftDashboard.takeaway')
}

function openOrder(orderId: number) {
  router.push({ name: 'pos', query: { order: String(orderId) } })
}

// ── سجل الفواتير (S-02) — بوابة PIN مدير+ داخل InvoiceLogModal نفسها ─────
const showInvoiceLog = ref(false)

// refreshReport: يحدّث الأرقام فقط بدون إعادة تحميل الطلبات الجارية —
// بيتنادى من WS shift_sale وبعد كل عملية في CashControlPanel
async function refreshReport() {
  await loadReport()
}

// ── WebSocket — تحديث تلقائي للـ report عند كل بيعة جديدة ───────────────
let ws: WebSocket | null = null
let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null
let wsScope: string | null = null
let isUnmounted = false
const wsConnected = ref(false)

function disconnectWs() {
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer)
    wsReconnectTimer = null
  }
  if (ws) {
    ws.onclose = null
    ws.close()
    ws = null
  }
  wsScope = null
  wsConnected.value = false
}

function connectWs() {
  if (isUnmounted || !shift.value || !auth.token) {
    disconnectWs()
    return
  }

  const nextScope = `${branchId.value}:${shift.value.id}`
  if (
    ws
    && wsScope === nextScope
    && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)
  ) return

  disconnectWs()
  wsScope = nextScope

  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${window.location.host}${ENDPOINTS.finance.shiftsWs(branchId.value ?? 0)}?token=${auth.token}`
  const socket = new WebSocket(url)
  ws = socket

  socket.onopen = () => {
    if (ws === socket) wsConnected.value = true
  }

  socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      // shift_sale → حدّث الأرقام فقط (مش الطلبات — هي بتتحدث بـ WS خاص بيها)
      if (msg.type === 'shift_sale') refreshReport()
      // shift_closed → وردية اتقفلت خارجيًا (مدير أقفلها) → أعد تحميل الكل
      if (msg.type === 'shift_closed') refreshAll()
    } catch { /* ignore malformed */ }
  }

  socket.onclose = () => {
    if (ws !== socket) return
    ws = null
    wsConnected.value = false
    if (!isUnmounted && shift.value && auth.token) {
      wsReconnectTimer = setTimeout(connectWs, 15_000)
    }
  }
  socket.onerror = () => socket.close()
}

// refreshAll: عند تغيير حالة الوردية (فتح/قفل) — يعيد تحميل كل حاجة،
// ثم يطابق اتصال الـ WS مع الوردية الجديدة. الشاشة قد تبدأ بلا وردية،
// لذلك connectWs مرة واحدة في onMounted لا يكفي عند فتح وردية لاحقًا.
async function refreshAll() {
  await fetchShift()
  connectWs()
}

onUnmounted(() => {
  isUnmounted = true
  disconnectWs()
})

onMounted(async () => {
  await refreshAll()
})
</script>

<template>
  <div class="page-container">
    <div class="flex items-center justify-between mb-4 gap-2 flex-wrap">
      <div class="flex items-center gap-2">
        <h1 class="section-title mb-0">{{ t('backoffice.shiftDashboard.title') }}</h1>
        <!-- مؤشر WS -->
        <span
          v-if="shift"
          :class="wsConnected
            ? 'bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-300'
            : 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'"
          class="text-xs font-bold px-2 py-0.5 rounded-full"
        >{{ wsConnected ? '🟢 ' + t('backoffice.shiftMonitor.live') : '🟡' }}</span>
      </div>
      <AppButton variant="outline" :loading="loadingShift || loadingReport" @click="refreshAll">
        🔄 {{ t('backoffice.shiftDashboard.refresh') }}
      </AppButton>
    </div>

    <LoadingState v-if="loadingShift && !shift" :label="t('backoffice.shiftDashboard.loading')" />

    <EmptyState
      v-else-if="!shift"
      icon="🔒"
      :title="t('backoffice.shiftDashboard.noOpenShift')"
      :subtitle="t('backoffice.shiftDashboard.noOpenShiftHint')"
    />

    <template v-else>
      <!-- التحكم في الوردية (فتح/قفل + عدّ الكاش) — نفس ShiftPanel المستخدم
           في هيدر FieldLayout بالظبط، من غير أي تكرار لمنطق القفل/عدّ الكاش -->
      <AppCard class="mb-4" padding="sm">
        <div class="flex items-center justify-between px-1">
          <span class="text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.shiftDashboard.shiftHash', { id: shift.id }) }}</span>
          <ShiftPanel @shift-changed="refreshAll" />
        </div>
      </AppCard>

      <!-- ضبط الكاش (Cash Control ledger) — إيداع/سحب/عهدة/تنزيل خزنة/فتح
           درج/تصحيح، كل واحدة محتاجة موافقة PIN مدير+ (راجع CashControlPanel) -->
      <CashControlPanel :shift-id="shift.id" />

      <!-- ملخص المبيعات — X-Report (S-04)، مبني على نفس endpoint التقرير
           بدون قفل الوردية -->
      <AppCard :title="t('backoffice.shiftDashboard.salesSummary')" class="mb-4">
        <div v-if="loadingReport" class="text-center text-sm text-gray-400 py-4">{{ t('backoffice.shiftDashboard.loading') }}</div>
        <template v-else-if="report">
          <!-- الصف الأول: إجمالي المبيعات + كاش + كارت + فواتير -->
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div class="rounded-xl border border-emerald-100 bg-emerald-50 p-3 text-center dark:border-emerald-900 dark:bg-emerald-950/30">
              <div class="text-lg font-black text-emerald-700 dark:text-emerald-300">{{ formatMoney(report.total_sales, 'EGP') }}</div>
              <div class="mt-0.5 text-xs text-emerald-600 dark:text-emerald-400">{{ t('backoffice.shiftDashboard.totalSales') }}</div>
            </div>
            <div class="rounded-xl border border-blue-100 bg-blue-50 p-3 text-center dark:border-blue-900 dark:bg-blue-950/30">
              <div class="text-lg font-black text-blue-700 dark:text-blue-300">{{ formatMoney(report.total_cash, 'EGP') }}</div>
              <div class="mt-0.5 text-xs text-blue-600 dark:text-blue-400">{{ t('backoffice.shiftDashboard.cash') }}</div>
            </div>
            <div class="rounded-xl border border-purple-100 bg-purple-50 p-3 text-center dark:border-purple-900 dark:bg-purple-950/30">
              <div class="text-lg font-black text-purple-700 dark:text-purple-300">{{ formatMoney(report.total_card, 'EGP') }}</div>
              <div class="mt-0.5 text-xs text-purple-600 dark:text-purple-400">{{ t('backoffice.shiftDashboard.card') }}</div>
            </div>
            <div class="rounded-xl border border-stone-200 bg-stone-50 p-3 text-center dark:border-border dark:bg-gray-800/60">
              <div class="text-lg font-black text-gray-700 dark:text-gray-300">{{ report.invoice_count }}</div>
              <div class="text-xs text-gray-500 mt-0.5">{{ t('backoffice.shiftDashboard.invoiceCount') }}</div>
            </div>
          </div>

          <!-- الصف الثاني: كاش متوقع + محمّل على غرف + مرتجعات + مقارنة -->
          <div class="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2">
            <!-- الكاش المتوقع في الدرج — الأهم للكاشير -->
            <div class="rounded-lg border border-teal-100 bg-teal-50 p-2.5 text-center dark:border-teal-900 dark:bg-teal-950/30">
              <div class="text-base font-bold text-teal-700 dark:text-teal-300">{{ formatMoney(report.expected_cash, 'EGP') }}</div>
              <div class="text-xs text-teal-600 dark:text-teal-400">{{ t('backoffice.shiftDashboard.expectedCash') }}</div>
            </div>
            <!-- محمّل على غرف (folio) — مش كاش في الدرج -->
            <div v-if="Number(report.total_room) > 0" class="rounded-lg border border-indigo-100 bg-indigo-50 p-2.5 text-center dark:border-indigo-900 dark:bg-indigo-950/30">
              <div class="text-base font-bold text-indigo-700 dark:text-indigo-300">{{ formatMoney(report.total_room, 'EGP') }}</div>
              <div class="text-xs text-indigo-600 dark:text-indigo-400">{{ t('backoffice.shiftDashboard.totalRoom') }}</div>
            </div>
            <!-- مرتجعات -->
            <div v-if="Number(report.refunds_count) > 0" class="rounded-lg border border-red-100 bg-red-50 p-2.5 text-center dark:border-red-900 dark:bg-red-950/30">
              <div class="text-base font-bold text-red-600 dark:text-red-400">-{{ formatMoney(report.refunds_total, 'EGP') }}</div>
              <div class="text-xs text-red-500 dark:text-red-400">{{ t('backoffice.shiftDashboard.refunds', { count: report.refunds_count }) }}</div>
            </div>
            <!-- مقارنة بالوردية السابقة -->
            <div v-if="report.delta_vs_previous != null" class="rounded-lg border border-stone-200 bg-stone-50 p-2.5 text-center dark:border-border dark:bg-gray-800/60">
              <div
                class="text-base font-bold"
                :class="Number(report.delta_vs_previous) >= 0 ? 'text-emerald-600 dark:text-emerald-300' : 'text-red-600 dark:text-red-400'"
              >
                {{ Number(report.delta_vs_previous) >= 0 ? '▲' : '▼' }} {{ formatMoney(Math.abs(Number(report.delta_vs_previous)), 'EGP') }}
              </div>
              <div class="text-xs text-gray-500 dark:text-gray-400">{{ t('backoffice.shiftDashboard.deltaVsPrevious') }}</div>
            </div>
          </div>

          <!-- تحذيرات -->
          <div class="mt-2 space-y-1">
            <p v-if="report.voided_count > 0" class="text-xs text-red-500">
              ⚠️ {{ t('backoffice.shiftDashboard.voidedInvoices', { count: report.voided_count, amount: formatMoney(report.voided_amount, 'EGP') }) }}
            </p>
            <p v-if="report.cash_movements_warning" class="rounded bg-amber-50 px-2 py-1 text-xs text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
              ⚠️ {{ report.cash_movements_warning }}
            </p>
            <p v-if="Number(report.cash_movements_effect) !== 0" class="text-xs text-gray-500">
              {{ t('backoffice.shiftDashboard.cashMovementsEffect', { amount: formatMoney(report.cash_movements_effect, 'EGP') }) }}
            </p>
          </div>

          <div class="flex gap-2 mt-3">
            <button
              @click="showInvoiceLog = true"
              class="min-h-11 flex-1 rounded-xl border border-blue-100 bg-blue-50 px-3 py-2 text-xs font-bold text-blue-700 hover:bg-blue-100 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-300 dark:hover:bg-blue-950/50"
            >📋 {{ t('backoffice.shiftDashboard.invoiceLog') }}</button>
            <a
              :href="ENDPOINTS.finance.shiftReportPdf(shift.id)"
              target="_blank"
              class="inline-flex min-h-11 flex-1 items-center justify-center rounded-xl border border-stone-200 bg-stone-50 px-3 py-2 text-center text-xs font-bold text-gray-600 hover:bg-stone-100 dark:border-border dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
            >📄 {{ t('backoffice.shiftDashboard.downloadPdf') }}</a>
          </div>
        </template>
      </AppCard>

      <!-- الطاولات/الطلبات المفتوحة لحظيًا (كل منافذ الدايننج) -->
      <AppCard :title="t('backoffice.shiftDashboard.liveOrdersTitle', { count: totalOpenOrdersCount, tables: openTablesCount })">
        <div v-if="loadingOrders" class="text-center text-sm text-gray-400 py-4">{{ t('backoffice.shiftDashboard.loading') }}</div>
        <EmptyState
          v-else-if="totalOpenOrdersCount === 0"
          icon="✅"
          :title="t('backoffice.shiftDashboard.noLiveOrders')"
        />
        <div v-else class="space-y-4">
          <div v-for="group in ordersByOutlet" :key="group.outlet.id">
            <h3 class="mb-1.5 text-xs font-bold uppercase text-gray-500 dark:text-gray-400">{{ locale === 'ar' ? (group.outlet.name_ar || group.outlet.name) : group.outlet.name }}</h3>
            <div class="divide-y divide-stone-100 dark:divide-border">
              <div v-for="o in group.orders" :key="o.id" class="py-2 flex items-center justify-between gap-2">
                <div class="flex-1 min-w-0">
                  <span class="text-sm font-semibold text-gray-800 dark:text-gray-200">{{ o.order_number }}</span>
                  <span class="text-xs text-gray-400 ms-2">{{ orderLabel(o) }}</span>
                </div>
                <div class="flex items-center gap-2 flex-shrink-0">
                  <span class="text-sm font-bold text-blue-700 dark:text-blue-300">{{ formatMoney(o.total, 'EGP') }}</span>
                  <AppBadge :variant="STATUS_VARIANT[o.status] ?? 'neutral'">{{ STATUS_LABEL[o.status] ?? o.status }}</AppBadge>
                  <AppButton size="sm" variant="ghost" @click="openOrder(o.id)">{{ t('common.view') }}</AppButton>
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
