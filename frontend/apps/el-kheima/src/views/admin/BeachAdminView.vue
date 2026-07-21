<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatNumber, formatDate: fmtDateFn, formatTime: fmtTimeFn } = useStaffFormat()
const auth = useAuthStore()
const branchId = auth.branchId
const tab = ref<'summary' | 'transactions' | 'b2b' | 'eod'>('summary')

// ── Interfaces ────────────────────────────────────────────────────────
interface BeachInventory {
  capacity_max: number; capacity_used: number; capacity_pct: number
  available_slots: number; towels_total: number; towels_used: number
  towels_available: number; surge_pct: number; surge_active: boolean
  surge_multiplier: number; adult_price: number; child_price: number
  resident_price: number; towel_price: number
}
interface BeachDailySummary {
  date: string; total_entries: number; total_revenue: number
  b2b_entries: number; b2b_revenue: number
  capacity_pct: number; surge_active: boolean; towels_rented: number
}
interface BeachTransaction {
  id: number; tx_type: string; quantity: number; unit_price: number
  total_amount: number; vat_amount: number; surge_applied: boolean
  tx_date: string; cashier_id: number | null; b2b_contract_id: number | null
  notes: string | null; voided_at: string | null; created_at: string
}
interface B2BContract {
  id: number; hotel_name: string; hotel_name_ar: string | null
  contact_phone: string | null; daily_quota: number; entry_price: number
  towel_price: number; valid_from: string; valid_until: string
  is_active: boolean; credit_limit: number | null; payment_terms_days: number
  last_settled_at: string | null; is_overdue: boolean; created_at: string
}
interface B2BStatus {
  contract_id: number; hotel_name: string; daily_quota: number
  used_today: number; remaining: number; quota_warning: boolean
  is_overdue: boolean; outstanding_balance: number | null
}
interface EodReport {
  date: string; total_entries: number; b2b_entries: number
  individual_entries: number; resident_entries: number
  towels_rented: number; total_revenue: number
  yesterday?: { total_entries: number; total_revenue: number } | null
  last_week?: { total_entries: number; total_revenue: number } | null
}

// ── State ─────────────────────────────────────────────────────────────
const loading = ref(false)
const inventory = ref<BeachInventory | null>(null)
const summary = ref<BeachDailySummary | null>(null)
const transactions = ref<BeachTransaction[]>([])
const txTotal = ref(0)
const txPage = ref(1)
const txDate = ref(new Date().toISOString().slice(0, 10))
const b2bContracts = ref<B2BContract[]>([])
const b2bStatus = ref<B2BStatus[]>([])
const eodReport = ref<EodReport | null>(null)
const eodDate = ref(new Date().toISOString().slice(0, 10))
const eodLoading = ref(false)
const downloadingPdf = ref(false)

// Surge modal
const surgeModal = ref(false)
const surgePct = ref('0')
const savingSurge = ref(false)

// B2B create modal
const b2bModal = ref(false)
const savingB2b = ref(false)
const b2bForm = ref({
  hotel_name: '', hotel_name_ar: '', contact_phone: '',
  daily_quota: '50', entry_price: '', towel_price: '0',
  valid_from: new Date().toISOString().slice(0, 10),
  valid_until: '', credit_limit: '', payment_terms_days: '30',
})

// B2B settle modal
const settleModal = ref(false)
const settlingContract = ref<B2BContract | null>(null)
const settledThrough = ref(new Date().toISOString().slice(0, 10))
const savingSettle = ref(false)

// B2B credit edit modal
const creditModal = ref(false)
const editingCredit = ref<B2BContract | null>(null)
const creditForm = ref({ credit_limit: '', payment_terms_days: '30' })
const savingCredit = ref(false)

// ── Computed ──────────────────────────────────────────────────────────
const capacityColor = computed(() => {
  if (!inventory.value) return 'bg-gray-200'
  const pct = inventory.value.capacity_pct
  if (pct >= 90) return 'bg-red-500'
  if (pct >= 70) return 'bg-amber-500'
  return 'bg-green-500'
})
const capacityTextColor = computed(() => {
  if (!inventory.value) return 'text-gray-600'
  const pct = inventory.value.capacity_pct
  if (pct >= 90) return 'text-red-600'
  if (pct >= 70) return 'text-amber-600'
  return 'text-green-600'
})

// ── Loaders ───────────────────────────────────────────────────────────
async function loadInventory() {
  try {
    const { data } = await api.get(ENDPOINTS.beach.inventory, {
      params: { branch_id: branchId }
    })
    inventory.value = data
    surgePct.value = String(data.surge_pct ?? 0)
  } catch { inventory.value = null }
}

async function loadSummary(date?: string) {
  try {
    const { data } = await api.get(ENDPOINTS.beach.summary, {
      params: { branch_id: branchId, tx_date: date ?? txDate.value }
    })
    summary.value = data
  } catch { summary.value = null }
}

async function loadTransactions() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.beach.transactions, {
      params: { branch_id: branchId, tx_date: txDate.value, page: txPage.value, size: 50 }
    })
    transactions.value = data.items ?? []
    txTotal.value = data.total ?? 0
  } catch { transactions.value = [] }
  finally { loading.value = false }
}

async function loadB2B() {
  loading.value = true
  try {
    const [contractsRes, statusRes] = await Promise.all([
      api.get(ENDPOINTS.beach.b2bContracts, { params: { branch_id: branchId, active_only: false } }),
      api.get(ENDPOINTS.beach.b2bQuotaStatus, { params: { branch_id: branchId } }),
    ])
    b2bContracts.value = contractsRes.data ?? []
    b2bStatus.value = statusRes.data ?? []
  } catch { b2bContracts.value = [] }
  finally { loading.value = false }
}

async function loadEod() {
  eodLoading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.beach.eodReport, {
      params: { branch_id: branchId, report_date: eodDate.value }
    })
    eodReport.value = data
  } catch { eodReport.value = null }
  finally { eodLoading.value = false }
}

async function switchTab(tabId: typeof tab.value) {
  tab.value = tabId
  if (tabId === 'summary') { await Promise.all([loadInventory(), loadSummary()]) }
  else if (tabId === 'transactions') { await loadTransactions() }
  else if (tabId === 'b2b') { await loadB2B() }
  else if (tabId === 'eod') { await loadEod() }
}

// ── Actions ───────────────────────────────────────────────────────────
async function saveSurge() {
  savingSurge.value = true
  try {
    await api.patch(ENDPOINTS.beach.surge, { surge_pct: surgePct.value }, {
      params: { branch_id: branchId }
    })
    toast.success(t('backoffice.beachAdmin.surgeUpdated'))
    surgeModal.value = false
    await loadInventory()
  } catch(e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.beachAdmin.surgeUpdateError'))
  } finally { savingSurge.value = false }
}

async function downloadTicket(txId: number) {
  try {
    const { data } = await api.get(ENDPOINTS.beach.ticket(txId), { responseType: 'blob' })
    const url = URL.createObjectURL(data)
    const a = document.createElement('a'); a.href = url; a.download = `beach-ticket-${txId}.pdf`; a.click()
    setTimeout(() => URL.revokeObjectURL(url), 5000)
  } catch { toast.error(t('backoffice.beachAdmin.ticketDownloadError')) }
}

async function downloadEodPdf() {
  downloadingPdf.value = true
  try {
    const { data } = await api.get(ENDPOINTS.beach.eodReportPdf, {
      params: { branch_id: branchId, report_date: eodDate.value }, responseType: 'blob'
    })
    const url = URL.createObjectURL(data)
    const a = document.createElement('a'); a.href = url; a.download = `beach-eod-${eodDate.value}.pdf`; a.click()
    setTimeout(() => URL.revokeObjectURL(url), 5000)
  } catch { toast.error(t('backoffice.beachAdmin.reportDownloadError')) }
  finally { downloadingPdf.value = false }
}

async function createB2BContract() {
  if (!b2bForm.value.hotel_name || !b2bForm.value.entry_price || !b2bForm.value.valid_until) {
    toast.error(t('backoffice.beachAdmin.b2bFieldsRequired')); return
  }
  savingB2b.value = true
  try {
    await api.post(ENDPOINTS.beach.b2bContracts, {
      branch_id: branchId,
      hotel_name: b2bForm.value.hotel_name,
      hotel_name_ar: b2bForm.value.hotel_name_ar || null,
      contact_phone: b2bForm.value.contact_phone || null,
      daily_quota: parseInt(b2bForm.value.daily_quota),
      entry_price: b2bForm.value.entry_price,
      towel_price: b2bForm.value.towel_price || '0',
      valid_from: b2bForm.value.valid_from,
      valid_until: b2bForm.value.valid_until,
      credit_limit: b2bForm.value.credit_limit || null,
      payment_terms_days: parseInt(b2bForm.value.payment_terms_days),
    })
    toast.success(t('backoffice.beachAdmin.b2bContractCreated'))
    b2bModal.value = false
    b2bForm.value = { hotel_name: '', hotel_name_ar: '', contact_phone: '', daily_quota: '50',
      entry_price: '', towel_price: '0', valid_from: new Date().toISOString().slice(0, 10),
      valid_until: '', credit_limit: '', payment_terms_days: '30' }
    await loadB2B()
  } catch(e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.beachAdmin.b2bContractCreateError'))
  } finally { savingB2b.value = false }
}

function openSettle(c: B2BContract) {
  settlingContract.value = c
  settledThrough.value = new Date().toISOString().slice(0, 10)
  settleModal.value = true
}

async function doSettle() {
  if (!settlingContract.value) return
  savingSettle.value = true
  try {
    await api.post(ENDPOINTS.beach.b2bContractSettle(settlingContract.value.id), {
      settled_through: settledThrough.value
    })
    toast.success(t('backoffice.beachAdmin.settlementDone'))
    settleModal.value = false
    await loadB2B()
  } catch(e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.beachAdmin.settlementError'))
  } finally { savingSettle.value = false }
}

function openCreditEdit(c: B2BContract) {
  editingCredit.value = c
  creditForm.value = {
    credit_limit: c.credit_limit != null ? String(c.credit_limit) : '',
    payment_terms_days: String(c.payment_terms_days),
  }
  creditModal.value = true
}

async function saveCreditEdit() {
  if (!editingCredit.value) return
  savingCredit.value = true
  try {
    await api.patch(ENDPOINTS.beach.b2bContract(editingCredit.value.id), {
      credit_limit: creditForm.value.credit_limit ? Number(creditForm.value.credit_limit) : null,
      payment_terms_days: parseInt(creditForm.value.payment_terms_days),
    })
    toast.success(t('backoffice.beachAdmin.creditUpdated'))
    creditModal.value = false
    await loadB2B()
  } catch(e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.beachAdmin.updateError'))
  } finally { savingCredit.value = false }
}

function fmtMoney(n: number | null | undefined) {
  return formatNumber(n ?? 0, { maximumFractionDigits: 0 })
}
function fmtDate(d?: string | null) {
  if (!d) return '—'
  return fmtDateFn(d)
}
const txTypeLabels = computed<Record<string, string>>(() => ({
  entry: t('backoffice.beachAdmin.txType.entry'), entry_child: t('backoffice.beachAdmin.txType.entryChild'),
  entry_resident: t('backoffice.beachAdmin.txType.entryResident'),
  entry_towel: t('backoffice.beachAdmin.txType.entryTowel'), towel_rent: t('backoffice.beachAdmin.txType.towelRent'),
  towel_return: t('backoffice.beachAdmin.txType.towelReturn'),
}))

onMounted(() => switchTab('summary'))
</script>

<template>
  <div class="space-y-5">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-black text-gray-800 dark:text-gray-200">{{ t('backoffice.beachAdmin.title') }}</h1>
        <p class="text-sm text-gray-500 dark:text-gray-500 mt-1">{{ t('backoffice.beachAdmin.subtitle') }}</p>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 bg-stone-100 dark:bg-gray-700 p-1 rounded-xl w-fit flex-wrap">
      <button v-for="tabDef in [
        { val: 'summary',      label: `📊 ${t('backoffice.beachAdmin.tabs.summary')}` },
        { val: 'transactions', label: `🧾 ${t('backoffice.beachAdmin.tabs.transactions')}` },
        { val: 'b2b',          label: `🤝 ${t('backoffice.beachAdmin.tabs.b2b')}` },
        { val: 'eod',          label: `📋 ${t('backoffice.beachAdmin.tabs.eod')}` },
      ]" :key="tabDef.val" @click="switchTab(tabDef.val as any)"
        :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all',
          tab === tabDef.val ? 'bg-white dark:bg-surface shadow-sm text-gray-900 dark:text-gray-100' : 'text-gray-500 hover:text-gray-700']"
      >{{ tabDef.label }}</button>
    </div>

    <!-- ══ TAB: SUMMARY ══ -->
    <div v-if="tab === 'summary'" class="space-y-4">
      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <template v-else>
        <!-- Capacity Card -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <AppCard padding="md">
            <div class="flex items-center justify-between mb-3">
              <span class="text-sm text-gray-500 dark:text-gray-500">{{ t('backoffice.beachAdmin.currentCapacity') }}</span>
              <AppBadge v-if="inventory?.surge_active" variant="warning">{{ t('backoffice.beachAdmin.surgeActivePct', { pct: inventory?.surge_pct }) }}</AppBadge>
            </div>
            <div :class="['text-3xl font-black', capacityTextColor]">
              {{ inventory?.capacity_used ?? 0 }} / {{ inventory?.capacity_max ?? 0 }}
            </div>
            <div class="mt-3 bg-gray-100 rounded-full h-3">
              <div :class="['h-3 rounded-full transition-all', capacityColor]"
                :style="{ width: (inventory?.capacity_pct ?? 0) + '%' }"></div>
            </div>
            <div class="text-xs text-gray-400 dark:text-gray-500 mt-1">{{ t('backoffice.beachAdmin.availableSlots', { count: inventory?.available_slots ?? 0 }) }}</div>
          </AppCard>

          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-2">{{ t('backoffice.beachAdmin.towels') }}</div>
            <div class="text-2xl font-black text-gray-800 dark:text-gray-200">{{ inventory?.towels_used ?? 0 }} / {{ inventory?.towels_total ?? 0 }}</div>
            <div class="text-xs text-gray-400 dark:text-gray-500 mt-1">{{ t('backoffice.beachAdmin.available', { count: inventory?.towels_available ?? 0 }) }}</div>
          </AppCard>

          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-2">{{ t('backoffice.beachAdmin.basePrices') }}</div>
            <div class="space-y-1 text-sm">
              <div class="flex justify-between"><span class="text-gray-500 dark:text-gray-500">{{ t('backoffice.beachAdmin.adult') }}</span><span class="font-bold">{{ fmtMoney(inventory?.adult_price) }} {{ t('backoffice.beachAdmin.egp') }}</span></div>
              <div class="flex justify-between"><span class="text-gray-500 dark:text-gray-500">{{ t('backoffice.beachAdmin.child') }}</span><span class="font-bold">{{ fmtMoney(inventory?.child_price) }} {{ t('backoffice.beachAdmin.egp') }}</span></div>
              <div class="flex justify-between"><span class="text-gray-500 dark:text-gray-500">{{ t('backoffice.beachAdmin.resident') }}</span><span class="font-bold">{{ fmtMoney(inventory?.resident_price) }} {{ t('backoffice.beachAdmin.egp') }}</span></div>
              <div class="flex justify-between"><span class="text-gray-500 dark:text-gray-500">{{ t('backoffice.beachAdmin.towel') }}</span><span class="font-bold">{{ fmtMoney(inventory?.towel_price) }} {{ t('backoffice.beachAdmin.egp') }}</span></div>
            </div>
          </AppCard>
        </div>
        </template>

        <!-- Summary KPIs -->
        <div v-if="summary" class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.beachAdmin.totalEntries') }}</div>
            <div class="text-2xl font-black text-gray-800 dark:text-gray-200">{{ summary.total_entries }}</div>
          </AppCard>
          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.beachAdmin.totalRevenue') }}</div>
            <div class="text-2xl font-black text-green-600">{{ fmtMoney(summary.total_revenue) }}</div>
            <div class="text-xs text-gray-400 dark:text-gray-500">{{ t('backoffice.beachAdmin.egpWord') }}</div>
          </AppCard>
          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.beachAdmin.b2bEntries') }}</div>
            <div class="text-2xl font-black text-blue-700">{{ summary.b2b_entries }}</div>
            <div class="text-xs text-gray-400 dark:text-gray-500">{{ fmtMoney(summary.b2b_revenue) }} {{ t('backoffice.beachAdmin.egp') }}</div>
          </AppCard>
          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.beachAdmin.towelsRented') }}</div>
            <div class="text-2xl font-black text-gray-800 dark:text-gray-200">{{ summary.towels_rented }}</div>
          </AppCard>
        </div>
        <EmptyState v-else icon="🏖️" :title="t('backoffice.beachAdmin.noDataToday')" />

        <!-- Surge control -->
        <AppCard padding="md">
          <div class="flex items-center justify-between">
            <div>
              <div class="font-semibold text-gray-800 dark:text-gray-200">{{ t('backoffice.beachAdmin.surgeControl') }}</div>
              <div class="text-sm text-gray-500 dark:text-gray-500">{{ t('backoffice.beachAdmin.surgeControlHint') }}</div>
            </div>
            <AppButton variant="outline" size="sm" @click="surgeModal = true">
              {{ inventory?.surge_active ? `✏️ ${t('backoffice.beachAdmin.editSurge')}` : `⚡ ${t('backoffice.beachAdmin.activateSurge')}` }}
            </AppButton>
          </div>
        </AppCard>
    </div>

    <!-- ══ TAB: TRANSACTIONS ══ -->
    <div v-else-if="tab === 'transactions'" class="space-y-4">
      <div class="flex items-center gap-3">
        <input type="date" v-model="txDate" @change="loadTransactions"
          class="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        <span class="text-sm text-gray-500 dark:text-gray-500">{{ t('backoffice.beachAdmin.transactionCount', { count: txTotal }) }}</span>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <EmptyState v-if="!transactions.length" icon="🧾" :title="t('backoffice.beachAdmin.noTransactionsToday')" />
        <div v-else class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.beachAdmin.type') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.beachAdmin.quantity') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.beachAdmin.price') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.beachAdmin.total') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.beachAdmin.time') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.beachAdmin.statusCol') }}</th>
                <th class="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="tx in transactions" :key="tx.id"
                :class="['border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60', tx.voided_at ? 'opacity-50' : '']">
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ txTypeLabels[tx.tx_type] ?? tx.tx_type }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ tx.quantity }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ fmtMoney(tx.unit_price) }} {{ t('backoffice.beachAdmin.egp') }}</td>
                <td class="px-4 py-3 text-sm font-bold text-gray-900 dark:text-gray-100">{{ fmtMoney(tx.total_amount) }} {{ t('backoffice.beachAdmin.egp') }}</td>
                <td class="px-4 py-3 text-xs text-gray-500 dark:text-gray-500">{{ fmtTimeFn(tx.created_at) }}</td>
                <td class="px-4 py-3">
                  <AppBadge v-if="tx.voided_at" variant="danger">{{ t('backoffice.beachAdmin.voided') }}</AppBadge>
                  <AppBadge v-else-if="tx.surge_applied" variant="warning">{{ t('backoffice.beachAdmin.surge') }}</AppBadge>
                  <AppBadge v-else variant="success">{{ t('backoffice.beachAdmin.completed') }}</AppBadge>
                </td>
                <td class="px-4 py-3">
                  <button v-if="!tx.voided_at" @click="downloadTicket(tx.id)"
                    class="text-xs text-blue-600 hover:underline">🖨️ {{ t('backoffice.beachAdmin.ticket') }}</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- ══ TAB: B2B ══ -->
    <div v-else-if="tab === 'b2b'" class="space-y-4">
      <div class="flex items-center justify-between">
        <div class="text-sm text-gray-500 dark:text-gray-500">{{ t('backoffice.beachAdmin.contractCount', { count: b2bContracts.length }) }}</div>
        <AppButton v-if="auth.hasRole('admin')" size="sm" @click="b2bModal = true">{{ t('backoffice.beachAdmin.addContract') }}</AppButton>
      </div>

      <!-- B2B status alerts -->
      <div v-if="b2bStatus.some(s => s.is_overdue || s.quota_warning)" class="space-y-2">
        <div v-for="s in b2bStatus.filter(x => x.is_overdue || x.quota_warning)" :key="s.contract_id"
          :class="['rounded-lg px-4 py-3 text-sm font-semibold',
            s.is_overdue ? 'bg-red-50 text-red-700 border border-red-200' : 'bg-amber-50 text-amber-700 border border-amber-200']">
          {{ s.is_overdue ? t('backoffice.beachAdmin.overduePrefix') : t('backoffice.beachAdmin.lowQuotaPrefix') }} {{ s.hotel_name }}
          {{ t('backoffice.beachAdmin.slotsRemainingToday', { count: s.remaining }) }}
        </div>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <EmptyState v-if="!b2bContracts.length" icon="🤝" :title="t('backoffice.beachAdmin.noB2bContracts')" />
        <div v-else class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.beachAdmin.hotel') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.beachAdmin.dailyQuota') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.beachAdmin.price') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.beachAdmin.creditLimit') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.beachAdmin.paymentTerms') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.beachAdmin.statusCol') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.beachAdmin.validity') }}</th>
                <th class="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in b2bContracts" :key="c.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3">
                  <div class="font-semibold text-sm text-gray-900 dark:text-gray-100">{{ c.hotel_name }}</div>
                  <div v-if="c.hotel_name_ar" class="text-xs text-gray-500 dark:text-gray-500">{{ c.hotel_name_ar }}</div>
                </td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ c.daily_quota }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ fmtMoney(c.entry_price) }} {{ t('backoffice.beachAdmin.egp') }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                  {{ c.credit_limit != null ? `${fmtMoney(c.credit_limit)} ${t('backoffice.beachAdmin.egp')}` : '—' }}
                </td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ t('backoffice.beachAdmin.dayCount', { count: c.payment_terms_days }) }}</td>
                <td class="px-4 py-3">
                  <AppBadge v-if="c.is_overdue" variant="danger">{{ t('backoffice.beachAdmin.overdue') }}</AppBadge>
                  <AppBadge v-else-if="!c.is_active" variant="neutral">{{ t('backoffice.beachAdmin.suspended') }}</AppBadge>
                  <AppBadge v-else variant="success">{{ t('backoffice.beachAdmin.active') }}</AppBadge>
                </td>
                <td class="px-4 py-3 text-xs text-gray-500 dark:text-gray-500">{{ fmtDate(c.valid_from) }} → {{ fmtDate(c.valid_until) }}</td>
                <td class="px-4 py-3">
                  <div class="flex gap-2">
                    <button @click="openCreditEdit(c)" class="text-xs text-blue-600 hover:underline">✏️ {{ t('backoffice.beachAdmin.credit') }}</button>
                    <button @click="openSettle(c)" class="text-xs text-green-600 hover:underline">✅ {{ t('backoffice.beachAdmin.settle') }}</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- ══ TAB: EOD ══ -->
    <div v-else-if="tab === 'eod'" class="space-y-4">
      <div class="flex items-center gap-3">
        <input type="date" v-model="eodDate" @change="loadEod"
          class="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        <AppButton size="sm" variant="outline" :loading="downloadingPdf" @click="downloadEodPdf">
          📄 {{ t('backoffice.beachAdmin.downloadPdf') }}
        </AppButton>
      </div>

      <div v-if="eodLoading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <template v-else-if="eodReport">
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.beachAdmin.totalEntries') }}</div>
            <div class="text-2xl font-black text-gray-800 dark:text-gray-200">{{ eodReport.total_entries }}</div>
            <div v-if="eodReport.yesterday" class="text-xs text-gray-400 dark:text-gray-500 mt-1">
              {{ t('backoffice.beachAdmin.yesterday', { count: eodReport.yesterday.total_entries }) }}
              <span :class="eodReport.total_entries >= eodReport.yesterday.total_entries ? 'text-green-500' : 'text-red-500'">
                {{ eodReport.total_entries >= eodReport.yesterday.total_entries ? '↑' : '↓' }}
              </span>
            </div>
          </AppCard>
          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.beachAdmin.grandTotalRevenue') }}</div>
            <div class="text-2xl font-black text-green-600">{{ fmtMoney(eodReport.total_revenue) }}</div>
            <div v-if="eodReport.yesterday" class="text-xs text-gray-400 dark:text-gray-500 mt-1">
              {{ t('backoffice.beachAdmin.yesterdayRevenue', { amount: fmtMoney(eodReport.yesterday.total_revenue) }) }}
            </div>
          </AppCard>
          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.beachAdmin.b2bEntries') }}</div>
            <div class="text-2xl font-black text-blue-700">{{ eodReport.b2b_entries }}</div>
          </AppCard>
          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.beachAdmin.individualEntries') }}</div>
            <div class="text-2xl font-black text-gray-800 dark:text-gray-200">{{ eodReport.individual_entries }}</div>
            <div class="text-xs text-gray-400 dark:text-gray-500">{{ t('backoffice.beachAdmin.residentCount', { count: eodReport.resident_entries }) }}</div>
          </AppCard>
        </div>

        <!-- Last week comparison -->
        <AppCard v-if="eodReport.last_week" padding="md" :title="t('backoffice.beachAdmin.lastWeekComparison')">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <div class="text-sm text-gray-500 dark:text-gray-500">{{ t('backoffice.beachAdmin.entries') }}</div>
              <div class="flex items-center gap-2">
                <span class="text-xl font-black text-gray-800 dark:text-gray-200">{{ eodReport.total_entries }}</span>
                <span class="text-sm text-gray-400 dark:text-gray-500">vs {{ eodReport.last_week.total_entries }}</span>
                <span :class="eodReport.total_entries >= eodReport.last_week.total_entries ? 'text-green-500 font-bold' : 'text-red-500 font-bold'">
                  {{ eodReport.total_entries >= eodReport.last_week.total_entries ? '▲' : '▼' }}
                </span>
              </div>
            </div>
            <div>
              <div class="text-sm text-gray-500 dark:text-gray-500">{{ t('backoffice.beachAdmin.revenue') }}</div>
              <div class="flex items-center gap-2">
                <span class="text-xl font-black text-gray-800 dark:text-gray-200">{{ fmtMoney(eodReport.total_revenue) }}</span>
                <span class="text-sm text-gray-400 dark:text-gray-500">vs {{ fmtMoney(eodReport.last_week.total_revenue) }}</span>
                <span :class="eodReport.total_revenue >= eodReport.last_week.total_revenue ? 'text-green-500 font-bold' : 'text-red-500 font-bold'">
                  {{ eodReport.total_revenue >= eodReport.last_week.total_revenue ? '▲' : '▼' }}
                </span>
              </div>
            </div>
          </div>
        </AppCard>
      <EmptyState v-else icon="📋" :title="t('backoffice.beachAdmin.noDataToday')" />
      </template>
    </div>

    <!-- ══ MODAL: SURGE ══ -->
    <AppModal :open="surgeModal" @close="surgeModal = false" :title="t('backoffice.beachAdmin.surgeModalTitle')">
      <div class="space-y-4">
        <div>
          <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.beachAdmin.surgePctLabel') }}</label>
          <input v-model="surgePct" type="number" min="0" max="200" step="5"
            class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">{{ t('backoffice.beachAdmin.surgeHint') }}</p>
        </div>
        <div class="flex gap-3 justify-end">
          <AppButton variant="ghost" @click="surgeModal = false">{{ t('backoffice.beachAdmin.cancel') }}</AppButton>
          <AppButton :loading="savingSurge" @click="saveSurge">{{ t('backoffice.beachAdmin.save') }}</AppButton>
        </div>
      </div>
    </AppModal>

    <!-- ══ MODAL: CREATE B2B ══ -->
    <AppModal :open="b2bModal" @close="b2bModal = false" :title="t('backoffice.beachAdmin.newB2bContractTitle')">
      <div class="space-y-3">
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.beachAdmin.hotelNameRequired') }}</label>
            <input v-model="b2bForm.hotel_name" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.beachAdmin.arabicName') }}</label>
            <input v-model="b2bForm.hotel_name_ar" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.beachAdmin.contactNumber') }}</label>
            <input v-model="b2bForm.contact_phone" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.beachAdmin.dailyQuota') }}</label>
            <input v-model="b2bForm.daily_quota" type="number" min="1" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.beachAdmin.entryPriceRequired') }}</label>
            <input v-model="b2bForm.entry_price" type="number" min="0" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.beachAdmin.towelPriceEgp') }}</label>
            <input v-model="b2bForm.towel_price" type="number" min="0" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.beachAdmin.fromDate') }}</label>
            <input v-model="b2bForm.valid_from" type="date" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.beachAdmin.untilDateRequired') }}</label>
            <input v-model="b2bForm.valid_until" type="date" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.beachAdmin.creditLimitEgp') }}</label>
            <input v-model="b2bForm.credit_limit" type="number" min="0" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" :placeholder="t('backoffice.beachAdmin.leaveEmptyUnlimited')" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.beachAdmin.paymentTermsDays') }}</label>
            <input v-model="b2bForm.payment_terms_days" type="number" min="1" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
        </div>
        <div class="flex gap-3 justify-end pt-2">
          <AppButton variant="ghost" @click="b2bModal = false">{{ t('backoffice.beachAdmin.cancel') }}</AppButton>
          <AppButton :loading="savingB2b" @click="createB2BContract">{{ t('backoffice.beachAdmin.createContract') }}</AppButton>
        </div>
      </div>
    </AppModal>

    <!-- ══ MODAL: SETTLE ══ -->
    <AppModal :open="settleModal" @close="settleModal = false" :title="t('backoffice.beachAdmin.settleModalTitle', { name: settlingContract?.hotel_name })">
      <div class="space-y-4">
        <p class="text-sm text-gray-600 dark:text-gray-500">{{ t('backoffice.beachAdmin.settleHint') }}</p>
        <div>
          <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.beachAdmin.settledThroughDate') }}</label>
          <input v-model="settledThrough" type="date" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div class="flex gap-3 justify-end">
          <AppButton variant="ghost" @click="settleModal = false">{{ t('backoffice.beachAdmin.cancel') }}</AppButton>
          <AppButton :loading="savingSettle" @click="doSettle">{{ t('backoffice.beachAdmin.confirmSettle') }}</AppButton>
        </div>
      </div>
    </AppModal>

    <!-- ══ MODAL: CREDIT EDIT ══ -->
    <AppModal :open="creditModal" @close="creditModal = false" :title="t('backoffice.beachAdmin.creditModalTitle', { name: editingCredit?.hotel_name })">
      <div class="space-y-3">
        <div>
          <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.beachAdmin.creditLimitEgp') }}</label>
          <input v-model="creditForm.credit_limit" type="number" min="0"
            class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            :placeholder="t('backoffice.beachAdmin.emptyMeansUnlimited')" />
        </div>
        <div>
          <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.beachAdmin.paymentTermsDays') }}</label>
          <input v-model="creditForm.payment_terms_days" type="number" min="1"
            class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div class="flex gap-3 justify-end">
          <AppButton variant="ghost" @click="creditModal = false">{{ t('backoffice.beachAdmin.cancel') }}</AppButton>
          <AppButton :loading="savingCredit" @click="saveCreditEdit">{{ t('backoffice.beachAdmin.save') }}</AppButton>
        </div>
      </div>
    </AppModal>
  </div>
</template>
