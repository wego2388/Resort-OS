<script setup lang="ts">
// وردايات الكاشير + drill-down كامل (X/Z report + سجل فواتير) — استُخرج من
// FinanceView.vue (تقسيم الملفات الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS, useResortWebSocket } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppButton, AppModal, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface ShiftItem {
  id: number; cashier_id: number; opened_at: string; closed_at?: string | null
  status: string; opening_float: number; expected_cash?: number | null
  counted_cash?: number | null; variance?: number | null
  reconciliation_ok?: boolean | null; reconciliation_warning?: string | null
}
interface ShiftDetailReport {
  total_cash: number; total_card: number; total_credit: number; total_other: number
  total_sales: number; invoice_count: number; voided_count: number; voided_amount: number
  cash_count: { denomination: number; currency: string; quantity: number; subtotal: number; fx_rate: number; egp_equivalent: number }[]
  foreign_currency_summary: { currency: string; total_foreign: number; fx_rate: number; egp_equivalent: number }[]
  counted_cash_egp?: number | null
}
interface ShiftInvoiceItemLine {
  item_id: number; name: string; name_ar: string | null
  category_name: string | null; category_name_ar: string | null
  quantity: number; revenue: number
}
interface ShiftInvoiceLine {
  payment_id: number; folio_id: number | null; guest_name: string; amount: number; method: string
  posted_at: string; is_voided: boolean; items: ShiftInvoiceItemLine[]
}
// Raw API shapes — backend returns Decimal fields as strings
interface RawCashCountLine {
  denomination: unknown; currency: unknown
  quantity: unknown; subtotal: unknown; fx_rate: unknown; egp_equivalent: unknown
}
interface RawFxSummaryLine { currency: unknown; total_foreign: unknown; fx_rate: unknown; egp_equivalent: unknown }
interface RawInvoiceItemLine { revenue: unknown; [key: string]: unknown }
interface RawInvoiceLine { amount: unknown; items?: RawInvoiceItemLine[]; [key: string]: unknown }
interface ShiftWsMessage { type?: string; shift_id?: number; [key: string]: unknown }

const toast = useToast()
const { t } = useI18n()
const { formatDateTime: fmtDateTimeFn } = useStaffFormat()
const branchId = computed(() => props.branchId)

const shifts      = ref<ShiftItem[]>([])
const shiftsTotal = ref(0)
const shiftStatus = ref<'all' | 'open' | 'closed'>('all')
// فلتر "فرق > 0" (S-05)
const shiftVarianceOnly = ref(false)
const loadingShifts = ref(false)

const filteredShifts = computed(() =>
  shiftVarianceOnly.value
    ? shifts.value.filter(s => s.variance != null && Math.abs(s.variance) > 0)
    : shifts.value,
)

const shiftStatusList = computed<{ v: 'all' | 'open' | 'closed'; l: string }[]>(() => [
  { v: 'all',    l: t('backoffice.finance.all') },
  { v: 'open',   l: t('backoffice.finance.shiftOpen') },
  { v: 'closed', l: t('backoffice.finance.shiftClosed') },
])

function parseShift(s: Record<string, unknown>): ShiftItem {
  return {
    ...(s as unknown as ShiftItem),
    opening_float:  s.opening_float  != null ? Number(s.opening_float)  : 0,
    expected_cash:  s.expected_cash  != null ? Number(s.expected_cash)  : null,
    counted_cash:   s.counted_cash   != null ? Number(s.counted_cash)   : null,
    variance:       s.variance       != null ? Number(s.variance)       : null,
  }
}

async function loadShifts() {
  loadingShifts.value = true
  try {
    const params: Record<string, unknown> = { branch_id: branchId.value, page: 1, size: 30 }
    if (shiftStatus.value !== 'all') params.status = shiftStatus.value
    const { data } = await api.get(ENDPOINTS.finance.shifts, { params })
    shifts.value      = (data.items ?? []).map(parseShift)
    shiftsTotal.value = data.total ?? 0
  } catch(e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.loadShiftsError'))
  } finally {
    loadingShifts.value = false
  }
}

// تدرّج لوني حسب حجم الفرق — مش ثنائي (مقبول/مرفوض) زي قبل كده: مطابق تمامًا
// (أخضر) → فرق طبيعي بسيط (كهرماني فاتح) → فرق يستاهل مراجعة مدير (كهرماني
// غامق) → فرق كبير (أحمر، نفس عتبة الرفض في services.close_shift تقريبًا).
function shiftVarianceClass(v?: number | null): string {
  if (v == null) return 'text-gray-400'
  const abs = Math.abs(v)
  if (abs === 0) return 'font-bold text-green-600 dark:text-green-300'
  if (abs <= 50) return 'text-amber-500 font-semibold'
  if (abs <= 200) return 'font-bold text-amber-700 dark:text-amber-300'
  return 'font-bold text-red-600 dark:text-red-300'
}

// ── Drill-down لكل وردية (S-05) — تقرير X/Z كامل + سجل الفواتير، نفس
// endpoints S-04/S-02. مدير+ بيشوف أي وردية من غير أي بوابة PIN إضافية
// (services.list_shift_invoices: acting_user_level>=60 مؤهّل بنفسه). ──────
const detailShift    = ref<ShiftItem | null>(null)
const detailReport   = ref<ShiftDetailReport | null>(null)
const detailInvoices = ref<ShiftInvoiceLine[]>([])
const detailLoading  = ref(false)

async function openShiftDetail(s: ShiftItem) {
  detailShift.value = s
  detailReport.value = null
  detailInvoices.value = []
  detailLoading.value = true
  try {
    const [reportRes, invoicesRes] = await Promise.all([
      api.get(ENDPOINTS.finance.shiftReport(s.id)),
      api.get(ENDPOINTS.finance.shiftInvoices(s.id)),
    ])
    // نحوّل Decimal strings لـ numbers
    const r = reportRes.data
    detailReport.value = {
      ...r,
      total_cash:    Number(r.total_cash    ?? 0),
      total_card:    Number(r.total_card    ?? 0),
      total_credit:  Number(r.total_credit  ?? 0),
      total_other:   Number(r.total_other   ?? 0),
      total_sales:   Number(r.total_sales   ?? 0),
      voided_amount: Number(r.voided_amount ?? 0),
      // cash_count: الـ backend بيرجّع Decimal كـ string — نحوّل كل الحقول العددية
      cash_count: (r.cash_count ?? []).map((line: RawCashCountLine) => ({
        denomination:   Number(line.denomination   ?? 0),
        currency:       String(line.currency ?? 'EGP'),
        quantity:       Number(line.quantity       ?? 0),
        subtotal:       Number(line.subtotal       ?? 0),
        fx_rate:        Number(line.fx_rate        ?? 1),
        egp_equivalent: Number(line.egp_equivalent ?? 0),
      })),
      foreign_currency_summary: (r.foreign_currency_summary ?? []).map((fc: RawFxSummaryLine) => ({
        currency:       String(fc.currency),
        total_foreign:  Number(fc.total_foreign  ?? 0),
        fx_rate:        Number(fc.fx_rate        ?? 1),
        egp_equivalent: Number(fc.egp_equivalent ?? 0),
      })),
      counted_cash_egp: r.counted_cash_egp != null ? Number(r.counted_cash_egp) : null,
    }
    detailInvoices.value = (invoicesRes.data ?? []).map((inv: RawInvoiceLine) => ({
      ...inv,
      amount: Number(inv.amount ?? 0),
      items: (inv.items ?? []).map((it: RawInvoiceItemLine) => ({
        ...it,
        revenue: Number(it.revenue ?? 0),
      })),
    }))
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.loadShiftDetailError'))
  } finally {
    detailLoading.value = false
  }
}
function closeShiftDetail() { detailShift.value = null }

// ── بث لحظي (S-01 live monitoring) — إشارة "دفعة جديدة اترحّلت لوردية X"
// (finance.add_payment/beach.sell_ticket، راجع finance/api/router.py
// shift_manager) — لو الوردية المفتوحة حاليًا في الـ modal هي نفسها، نعيد
// تحميل التقرير/سجل الفواتير تلقائيًا من غير أي polling. مقفول مدير+ من
// الباك إند نفسه (get_websocket_user min_level=60)، متسق مع باقي شاشة
// الحسابات دي كلها.
// CX-02C: computed URL — لو branchId=null مفيش WS يتفتح.
const { onMessage: onShiftWsMessage } = useResortWebSocket(
  computed(() => branchId.value != null ? ENDPOINTS.finance.shiftsWs(branchId.value) : null),
)
onShiftWsMessage((data: unknown) => {
  const msg = data as ShiftWsMessage
  const openShift = detailShift.value
  if (msg?.type === 'shift_sale' && openShift && openShift.id === msg.shift_id) {
    openShiftDetail(openShift)
  }
})

const METHOD_LABEL = computed<Record<string, string>>(() => ({
  cash: `💵 ${t('backoffice.finance.methodCash')}`, card: `💳 ${t('backoffice.finance.methodCard')}`,
  bank_transfer: `🏦 ${t('backoffice.finance.methodBankTransfer')}`,
  credit: `📝 ${t('backoffice.finance.methodCredit')}`, room_charge: `🛏️ ${t('backoffice.finance.methodRoomCharge')}`,
  other: t('backoffice.finance.methodOther'),
}))

onMounted(loadShifts)
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center gap-3 flex-wrap">
      <div class="flex gap-1 bg-stone-100 dark:bg-gray-700 p-1 rounded-xl">
        <button v-for="s in shiftStatusList"
          :key="s.v" @click="shiftStatus = s.v; loadShifts()"
          :class="['px-3 py-1 rounded-lg text-xs font-semibold transition-all', shiftStatus === s.v ? 'bg-white dark:bg-surface shadow-sm text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-400']">
          {{ s.l }}
        </button>
      </div>
      <!-- فلتر "فرق > 0" (S-05) -->
      <button
        @click="shiftVarianceOnly = !shiftVarianceOnly"
        :class="['px-3 py-1 rounded-lg text-xs font-semibold border transition-all',
          shiftVarianceOnly ? 'bg-amber-500 border-amber-500 text-white' : 'bg-white dark:bg-surface border-stone-200 dark:border-border text-gray-500']"
      >⚠️ {{ t('backoffice.finance.varianceOnlyFilter') }}</button>
      <!-- spinner أثناء التحميل -->
      <AppSpinner v-if="loadingShifts" size="sm" />
      <span class="text-xs text-gray-400 dark:text-gray-400">{{ t('backoffice.finance.totalShown', { total: shiftsTotal, shown: filteredShifts.length }) }}</span>
      <button @click="loadShifts()" class="ms-auto px-3 py-1 rounded-lg text-xs font-semibold border border-stone-200 dark:border-border bg-white dark:bg-surface text-gray-500 dark:text-gray-400 hover:bg-stone-50 dark:bg-gray-800/60 transition-all">🔄 {{ t('backoffice.finance.refresh') }}</button>
    </div>
    <div class="overflow-x-auto rounded-xl border border-stone-200 dark:border-border">
      <table class="responsive-card-table w-full min-w-[1100px] text-sm">
        <thead class="bg-stone-50 dark:bg-gray-800/60 text-xs text-gray-500 dark:text-gray-400 uppercase">
          <tr>
            <th class="px-4 py-3 text-start">#</th>
            <th class="px-4 py-3 text-start">{{ t('backoffice.finance.cashier') }}</th>
            <th class="px-4 py-3 text-start">{{ t('backoffice.finance.opened') }}</th>
            <th class="px-4 py-3 text-start">{{ t('backoffice.finance.closed') }}</th>
            <th class="px-4 py-3 text-start">{{ t('backoffice.finance.statusCol') }}</th>
            <th class="px-4 py-3 text-start">{{ t('backoffice.finance.expected') }}</th>
            <th class="px-4 py-3 text-start">{{ t('backoffice.finance.counted') }}</th>
            <th class="px-4 py-3 text-start">{{ t('backoffice.finance.variance') }}</th>
            <th class="px-4 py-3 text-start">PDF</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-stone-100">
          <tr
            v-for="s in filteredShifts" :key="s.id"
            class="hover:bg-stone-50 dark:bg-gray-800/60 transition-colors cursor-pointer"
            @click="openShiftDetail(s)"
          >
            <td data-primary class="px-4 py-3 font-mono text-gray-500 dark:text-gray-400">#{{ s.id }}</td>
            <td :data-label="t('backoffice.finance.cashier')" class="px-4 py-3 font-semibold">{{ s.cashier_id }}</td>
            <td :data-label="t('backoffice.finance.opened')" class="px-4 py-3 text-gray-600 dark:text-gray-400 text-xs">
              {{ fmtDateTimeFn(s.opened_at) }}
            </td>
            <td :data-label="t('backoffice.finance.closed')" class="px-4 py-3 text-gray-500 dark:text-gray-400 text-xs">
              {{ s.closed_at ? fmtDateTimeFn(s.closed_at) : '—' }}
            </td>
            <td :data-label="t('backoffice.finance.statusCol')" class="px-4 py-3">
              <span :class="['px-2 py-0.5 rounded-full text-xs font-bold',
                s.status === 'open'
                  ? 'bg-green-100 text-green-700 dark:bg-green-950/50 dark:text-green-300'
                  : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300']">
                {{ s.status === 'open' ? t('backoffice.finance.shiftOpen') : t('backoffice.finance.shiftClosed') }}
              </span>
              <span v-if="s.reconciliation_warning" class="ms-1 text-red-500 cursor-help"
                :title="s.reconciliation_warning">⚠️</span>
            </td>
            <td :data-label="t('backoffice.finance.expected')" class="px-4 py-3 text-gray-700 dark:text-gray-300">{{ s.expected_cash?.toFixed(2) ?? '—' }}</td>
            <td :data-label="t('backoffice.finance.counted')" class="px-4 py-3 text-gray-700 dark:text-gray-300">{{ s.counted_cash?.toFixed(2) ?? '—' }}</td>
            <td :data-label="t('backoffice.finance.variance')" class="px-4 py-3" :class="shiftVarianceClass(s.variance)">
              {{ s.variance != null ? (s.variance > 0 ? '+' : '') + s.variance.toFixed(2) : '—' }}
            </td>
            <td data-actions class="px-4 py-3">
              <a v-if="s.status === 'closed'"
                :href="ENDPOINTS.finance.shiftReportPdf(s.id)"
                target="_blank"
                @click.stop
                class="text-xs font-semibold text-blue-600 hover:underline dark:text-blue-300">📄 PDF</a>
              <span v-else class="text-gray-300 text-xs">—</span>
            </td>
          </tr>
          <tr v-if="!filteredShifts.length">
            <td data-empty colspan="9" class="px-4 py-12 text-center text-gray-400 dark:text-gray-400">{{ t('backoffice.finance.noShifts') }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Shift drill-down (S-05) — تقرير كامل + سجل فواتير لوردية واحدة -->
    <AppModal :open="!!detailShift" :title="t('backoffice.finance.shiftDetailTitle', { id: detailShift?.id ?? '' })" size="lg" @close="closeShiftDetail">
      <div v-if="detailLoading" class="flex justify-center py-10"><AppSpinner size="lg" /></div>
      <div v-else-if="detailReport" class="space-y-4">

        <!-- KPIs رئيسية -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div class="bg-emerald-50 dark:bg-emerald-900/20 rounded-xl p-3 text-center border border-emerald-100 dark:border-emerald-800/40">
            <div class="text-lg font-black text-emerald-700 dark:text-emerald-400">{{ detailReport.total_sales.toFixed(2) }}</div>
            <div class="text-xs text-emerald-600 dark:text-emerald-500 mt-0.5">{{ t('backoffice.finance.totalSales') }}</div>
          </div>
          <div class="bg-blue-50 dark:bg-blue-900/20 rounded-xl p-3 text-center border border-blue-100 dark:border-blue-800/40">
            <div class="text-lg font-black text-blue-700 dark:text-blue-400">{{ detailReport.total_cash.toFixed(2) }}</div>
            <div class="text-xs text-blue-600 dark:text-blue-500 mt-0.5">{{ t('backoffice.finance.methodCash') }}</div>
          </div>
          <div class="bg-purple-50 dark:bg-purple-900/20 rounded-xl p-3 text-center border border-purple-100 dark:border-purple-800/40">
            <div class="text-lg font-black text-purple-700 dark:text-purple-400">{{ detailReport.total_card.toFixed(2) }}</div>
            <div class="text-xs text-purple-600 dark:text-purple-500 mt-0.5">{{ t('backoffice.finance.methodCard') }}</div>
          </div>
          <div class="rounded-xl p-3 text-center border" :class="shiftVarianceClass(detailShift?.variance).includes('red') ? 'bg-red-50 dark:bg-red-900/20 border-red-100 dark:border-red-800/40' : 'bg-stone-50 dark:bg-gray-800/60 border-stone-200 dark:border-border'">
            <div class="text-lg font-black" :class="shiftVarianceClass(detailShift?.variance)">
              {{ detailShift?.variance != null ? (detailShift.variance > 0 ? '+' : '') + detailShift.variance.toFixed(2) : '—' }}
            </div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ t('backoffice.finance.variance') }}</div>
          </div>
        </div>

        <!-- KPIs إضافية — آجل + أخرى + ملغاة -->
        <div v-if="detailReport.total_credit > 0 || detailReport.total_other > 0 || detailReport.voided_count > 0"
          class="grid grid-cols-3 gap-2">
          <div v-if="detailReport.total_credit > 0" class="bg-stone-50 dark:bg-gray-800/60 rounded-lg p-2.5 text-center border border-stone-200 dark:border-border">
            <div class="text-sm font-bold text-gray-700 dark:text-gray-300">{{ detailReport.total_credit.toFixed(2) }} {{ t('backoffice.finance.egp') }}</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">📝 {{ t('backoffice.finance.methodCredit') }}</div>
          </div>
          <div v-if="detailReport.total_other > 0" class="bg-stone-50 dark:bg-gray-800/60 rounded-lg p-2.5 text-center border border-stone-200 dark:border-border">
            <div class="text-sm font-bold text-gray-700 dark:text-gray-300">{{ detailReport.total_other.toFixed(2) }} {{ t('backoffice.finance.egp') }}</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">🔄 {{ t('backoffice.finance.methodOther') }}</div>
          </div>
          <div v-if="detailReport.voided_count > 0" class="bg-red-50 dark:bg-red-900/20 rounded-lg p-2.5 text-center border border-red-100 dark:border-red-800/40">
            <div class="text-sm font-bold text-red-600 dark:text-red-400">
              {{ detailReport.voided_count }} ({{ detailReport.voided_amount.toFixed(2) }} {{ t('backoffice.finance.egp') }})
            </div>
            <div class="text-xs text-red-500 dark:text-red-400 mt-0.5">❌ {{ t('backoffice.finance.voided') }}</div>
          </div>
        </div>

        <!-- ملخص العملات الأجنبية -->
        <div v-if="detailReport.foreign_currency_summary?.length">
          <h3 class="text-xs font-bold text-gray-400 dark:text-gray-400 uppercase mb-1.5">🌍 {{ t('backoffice.finance.foreignCurrencies') }}</h3>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-1.5 text-xs">
            <div v-for="fc in detailReport.foreign_currency_summary" :key="fc.currency"
              class="bg-amber-50 dark:bg-amber-900/20 rounded-lg px-2 py-1.5 border border-amber-100 dark:border-amber-800/40 flex justify-between">
              <span class="text-gray-600 dark:text-gray-400">
                {{ fc.total_foreign.toFixed(2) }} {{ fc.currency }}
                <span class="text-gray-400 dark:text-gray-400"> × {{ fc.fx_rate }}</span>
              </span>
              <span class="font-semibold text-amber-700 dark:text-amber-400">{{ fc.egp_equivalent.toFixed(2) }} {{ t('backoffice.finance.egp') }}</span>
            </div>
          </div>
          <div v-if="detailReport.counted_cash_egp != null" class="mt-1.5 text-xs text-end text-gray-500 dark:text-gray-400">
            {{ t('backoffice.finance.totalCountedEgp') }} <span class="font-bold text-gray-700 dark:text-gray-300">{{ detailReport.counted_cash_egp.toFixed(2) }} {{ t('backoffice.finance.egp') }}</span>
          </div>
        </div>

        <!-- عدّ الكاش بالفئة -->
        <div v-if="detailReport.cash_count.length">
          <h3 class="text-xs font-bold text-gray-400 dark:text-gray-400 uppercase mb-1.5">{{ t('backoffice.finance.cashCountByDenomination') }}</h3>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-1.5 text-xs">
            <div v-for="(line, i) in detailReport.cash_count" :key="i"
              class="bg-stone-50 dark:bg-gray-800/60 rounded-lg px-2 py-1.5 flex justify-between">
              <span class="text-gray-600 dark:text-gray-400">{{ line.denomination }} {{ line.currency }} × {{ line.quantity }}</span>
              <span class="font-semibold text-gray-800 dark:text-gray-200">{{ line.egp_equivalent.toFixed(2) }} {{ t('backoffice.finance.egp') }}</span>
            </div>
          </div>
        </div>

        <!-- سجل الفواتير -->
        <div>
          <h3 class="text-xs font-bold text-gray-400 dark:text-gray-400 uppercase mb-1.5">
            {{ t('backoffice.finance.invoicesCount', { count: detailInvoices.length }) }}
          </h3>
          <EmptyState v-if="!detailInvoices.length" :title="t('backoffice.finance.noInvoicesInShift')" />
          <div v-else class="divide-y divide-stone-100 dark:divide-border/50 max-h-80 overflow-y-auto">
            <div v-for="inv in detailInvoices" :key="inv.payment_id"
              class="py-2" :class="inv.is_voided && 'opacity-50'">
              <div class="flex items-center justify-between gap-2">
                <div>
                  <span class="text-sm font-semibold text-gray-800 dark:text-gray-200" :class="inv.is_voided && 'line-through'">{{ inv.guest_name }}</span>
                  <span class="text-xs text-gray-400 dark:text-gray-400 ms-2">{{ METHOD_LABEL[inv.method] ?? inv.method }}</span>
                </div>
                <span class="text-sm font-bold" :class="inv.is_voided ? 'text-gray-400 dark:text-gray-400 line-through' : 'text-blue-700 dark:text-blue-400'">{{ inv.amount.toFixed(2) }} {{ t('backoffice.finance.egp') }}</span>
              </div>
              <div v-if="inv.items.length" class="mt-1 ps-2 space-y-0.5">
                <div v-for="item in inv.items" :key="item.item_id" class="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                  <span>{{ item.name_ar || item.name }} × {{ item.quantity }}</span>
                  <span class="font-mono">{{ item.revenue.toFixed(2) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="flex gap-2">
          <a v-if="detailShift?.status === 'closed'"
            :href="ENDPOINTS.finance.shiftReportPdf(detailShift.id)"
            target="_blank"
            class="flex-1">
            <AppButton variant="outline" block>📄 {{ t('backoffice.finance.downloadPdf') }}</AppButton>
          </a>
          <AppButton variant="ghost" :block="detailShift?.status !== 'closed'" @click="closeShiftDetail">{{ t('backoffice.finance.close') }}</AppButton>
        </div>
      </template>
    </AppModal>
  </div>
</template>
