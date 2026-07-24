<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS, useAuthStore, useResortWebSocket } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatNumber, formatDate: fmtDateFn, formatDateTime: fmtDateTimeFn } = useStaffFormat()
const auth = useAuthStore()
const branchId = computed(() => auth.branchId ?? 1)
const tab = ref<'overview' | 'checks' | 'accounts' | 'cost-centers' | 'balance-sheet' | 'depreciation' | 'bank-reconciliation' | 'shifts'>('overview')

interface Check { id: number; check_number: string; amount: number; drawer_name: string; due_date: string; status: string; bank_name: string }
interface Account { id: number; code: string; name: string; account_type: string; balance: number }
interface CostCenterLine { code: string; name: string; revenue: number; expense: number; net: number; source: 'ledger' | 'direct' }
interface BalanceSheetLine { account_code: string; account_name: string; amount: number }
interface BalanceSheetData {
  as_of: string
  asset_lines: BalanceSheetLine[]; liability_lines: BalanceSheetLine[]; equity_lines: BalanceSheetLine[]
  retained_earnings: number
  total_assets: number; total_liabilities: number; total_equity: number; total_liabilities_and_equity: number
  is_balanced: boolean
}
interface DepreciationEntry { id: number; asset_id: number; year: number; month: number; amount: number; accumulated_after: number }
interface Asset { id: number; code: string; name: string }
interface ShiftItem {
  id: number; cashier_id: number; opened_at: string; closed_at?: string | null
  status: string; opening_float: number; expected_cash?: number | null
  counted_cash?: number | null; variance?: number | null
  reconciliation_ok?: boolean | null; reconciliation_warning?: string | null
}
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

function parseShift(s: any): ShiftItem {
  return {
    ...s,
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
  } catch(e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.finance.loadShiftsError'))
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
interface ShiftDetailReport {
  total_cash: number; total_card: number; total_credit: number; total_other: number
  total_sales: number; invoice_count: number; voided_count: number; voided_amount: number
  cash_count: { denomination: number; currency: string; quantity: number; subtotal: number; fx_rate: number; egp_equivalent: number }[]
  foreign_currency_summary: { currency: string; total_foreign: number; fx_rate: number; egp_equivalent: number }[]
  counted_cash_egp?: number | null
}
interface ShiftInvoiceLine {
  payment_id: number; folio_id: number | null; guest_name: string; amount: number; method: string
  posted_at: string; is_voided: boolean
}
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
      cash_count: (r.cash_count ?? []).map((line: any) => ({
        denomination:   Number(line.denomination   ?? 0),
        currency:       line.currency ?? 'EGP',
        quantity:       Number(line.quantity       ?? 0),
        subtotal:       Number(line.subtotal       ?? 0),
        fx_rate:        Number(line.fx_rate        ?? 1),
        egp_equivalent: Number(line.egp_equivalent ?? 0),
      })),
      foreign_currency_summary: (r.foreign_currency_summary ?? []).map((fc: any) => ({
        currency:       fc.currency,
        total_foreign:  Number(fc.total_foreign  ?? 0),
        fx_rate:        Number(fc.fx_rate        ?? 1),
        egp_equivalent: Number(fc.egp_equivalent ?? 0),
      })),
      counted_cash_egp: r.counted_cash_egp != null ? Number(r.counted_cash_egp) : null,
    }
    detailInvoices.value = (invoicesRes.data ?? []).map((inv: any) => ({
      ...inv,
      amount: Number(inv.amount ?? 0),
    }))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.finance.loadShiftDetailError'))
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
const { onMessage: onShiftWsMessage } = useResortWebSocket(ENDPOINTS.finance.shiftsWs(branchId.value))
onShiftWsMessage((data: any) => {
  const openShift = detailShift.value
  if (data?.type === 'shift_sale' && openShift && openShift.id === data.shift_id) {
    openShiftDetail(openShift)
  }
})

const METHOD_LABEL = computed<Record<string, string>>(() => ({
  cash: `💵 ${t('backoffice.finance.methodCash')}`, card: `💳 ${t('backoffice.finance.methodCard')}`,
  bank_transfer: `🏦 ${t('backoffice.finance.methodBankTransfer')}`,
  credit: `📝 ${t('backoffice.finance.methodCredit')}`, room_charge: `🛏️ ${t('backoffice.finance.methodRoomCharge')}`,
  other: t('backoffice.finance.methodOther'),
}))
interface BankAccount {
  id: number; bank_name: string; account_name: string; account_number: string
  currency: string; opening_balance: number; is_active: boolean
}
interface StatementLine {
  id: number; line_date: string; description: string; amount: number
  status: string; external_reference?: string | null
}
interface ReconciliationSummary {
  opening_balance: number; book_balance: number; statement_balance: number
  difference: number; is_reconciled: boolean
  unmatched_statement_lines: number; unmatched_payments_count: number
}

const checks = ref<Check[]>([])
const accounts = ref<Account[]>([])
const financeData = ref<{ total_revenue: number; total_expense: number; net_income: number } | null>(null)
const loading = ref(false)

// ── Depreciation ─────────────────────────────────────────────────────
const depreciationEntries = ref<DepreciationEntry[]>([])
const assetsById = ref<Record<number, string>>({})
const depYear = ref(new Date().getFullYear())
const depMonth = ref(new Date().getMonth() + 1)
const runningDepreciation = ref(false)
const lastRunResult = ref<{ total_amount: number; entries_count: number; skipped: string[] } | null>(null)

async function loadDepreciation() {
  loading.value = true
  try {
    const [entriesRes, assetsRes] = await Promise.all([
      api.get(ENDPOINTS.finance.depreciationEntries, { params: { branch_id: branchId.value, size: 100 } }),
      api.get(ENDPOINTS.maintenance.assets, { params: { branch_id: branchId.value, size: 100 } }),
    ])
    depreciationEntries.value = entriesRes.data.items ?? []
    const map: Record<number, string> = {}
    for (const a of (assetsRes.data.items ?? []) as Asset[]) map[a.id] = a.name
    assetsById.value = map
  } catch { toast.error(t('backoffice.finance.loadDepreciationError')) }
  finally { loading.value = false }
}

async function runDepreciation() {
  runningDepreciation.value = true
  lastRunResult.value = null
  try {
    const { data } = await api.post(ENDPOINTS.finance.depreciationRun, {
      branch_id: branchId.value, year: depYear.value, month: depMonth.value,
    })
    lastRunResult.value = {
      total_amount: Number(data.total_amount),
      entries_count: data.entries.length,
      skipped: data.skipped_assets,
    }
    toast.success(t('backoffice.finance.depreciationPostedToast', { count: data.entries.length, amount: formatNumber(Number(data.total_amount)) }))
    await loadDepreciation()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.finance.runDepreciationError'))
  } finally {
    runningDepreciation.value = false
  }
}

// ── Bank Reconciliation ──────────────────────────────────────────────
const bankAccounts = ref<BankAccount[]>([])
const selectedBankAccountId = ref<number | null>(null)
const statementLines = ref<StatementLine[]>([])
const reconciliationSummary = ref<ReconciliationSummary | null>(null)
const showBankAccountForm = ref(false)
const bankAccountForm = ref({ bank_name: '', account_name: '', account_number: '', opening_balance: '0' })
const matchingInProgress = ref(false)

async function loadBankAccounts() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.bankAccounts, { params: { branch_id: branchId.value } })
    bankAccounts.value = data
    if (!selectedBankAccountId.value && data.length) {
      selectedBankAccountId.value = data[0].id
      await loadStatementLinesAndSummary()
    }
  } catch { toast.error(t('backoffice.finance.loadBankAccountsError')) }
  finally { loading.value = false }
}

async function loadStatementLinesAndSummary() {
  if (!selectedBankAccountId.value) return
  try {
    const [linesRes, summaryRes] = await Promise.all([
      api.get(ENDPOINTS.finance.bankAccountStatementLines(selectedBankAccountId.value), {
        params: { size: 100 },
      }),
      api.get(ENDPOINTS.finance.bankAccountReconciliationSummary(selectedBankAccountId.value), {
        params: { as_of: new Date().toISOString().slice(0, 10) },
      }),
    ])
    statementLines.value = linesRes.data.items ?? []
    reconciliationSummary.value = summaryRes.data
  } catch { toast.error(t('backoffice.finance.loadReconciliationError')) }
}

async function createBankAccount() {
  if (!bankAccountForm.value.bank_name || !bankAccountForm.value.account_number) {
    toast.error(t('backoffice.finance.bankAccountFieldsRequired')); return
  }
  try {
    await api.post(ENDPOINTS.finance.bankAccounts, {
      branch_id: branchId.value,
      bank_name: bankAccountForm.value.bank_name,
      account_name: bankAccountForm.value.account_name || bankAccountForm.value.bank_name,
      account_number: bankAccountForm.value.account_number,
      opening_balance: bankAccountForm.value.opening_balance,
    })
    toast.success(t('backoffice.finance.bankAccountCreated'))
    showBankAccountForm.value = false
    bankAccountForm.value = { bank_name: '', account_name: '', account_number: '', opening_balance: '0' }
    await loadBankAccounts()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.finance.bankAccountCreateError'))
  }
}

async function runAutoMatch() {
  if (!selectedBankAccountId.value) return
  matchingInProgress.value = true
  try {
    const { data } = await api.post(
      ENDPOINTS.finance.bankAccountAutoMatch(selectedBankAccountId.value),
    )
    toast.success(t('backoffice.finance.autoMatchedToast', { count: data.matched_count }))
    await loadStatementLinesAndSummary()
  } catch { toast.error(t('backoffice.finance.autoMatchError')) }
  finally { matchingInProgress.value = false }
}

const statementLineStatusConfig = computed<Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }>>(() => ({
  unmatched: { label: t('backoffice.finance.stmtUnmatched'), variant: 'warning' },
  matched:   { label: t('backoffice.finance.stmtMatched'),     variant: 'success' },
  ignored:   { label: t('backoffice.finance.stmtIgnored'),    variant: 'neutral' },
}))

// ── Cost Centers ─────────────────────────────────────────────────────
const today = new Date().toISOString().slice(0, 10)
const firstOfMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().slice(0, 10)
const ccDateFrom = ref(firstOfMonth)
const ccDateTo = ref(today)
const ccLines = ref<CostCenterLine[]>([])
const ccTotalRevenue = ref(0)
const ccTotalExpense = ref(0)
const ccTotalNet = ref(0)

async function loadCostCenters() {
  loading.value = true
  try {
    const res = await api.get(ENDPOINTS.finance.costCenterReport, {
      params: { branch_id: branchId.value, date_from: ccDateFrom.value, date_to: ccDateTo.value },
    })
    ccLines.value = res.data.lines ?? []
    ccTotalRevenue.value = res.data.total_revenue ?? 0
    ccTotalExpense.value = res.data.total_expense ?? 0
    ccTotalNet.value = res.data.total_net ?? 0
  } catch { toast.error(t('backoffice.finance.loadCostCentersError')) }
  finally { loading.value = false }
}

// ── Balance Sheet (الميزانية العمومية) ────────────────────────────────
// Assets = Liabilities + Equity + Retained Earnings — من نفس مصدر بيانات
// ميزان المراجعة/قائمة الدخل (أرصدة journal_lines الفعلية لكل حساب حتى
// as_of)، مش حساب موازٍ منفصل. راجع finance.services.get_balance_sheet.
const bsAsOf = ref(today)
const bsData = ref<BalanceSheetData | null>(null)

async function loadBalanceSheet() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.reportsBalanceSheet, {
      params: { branch_id: branchId.value, as_of: bsAsOf.value },
    })
    const toLines = (lines: any[]): BalanceSheetLine[] =>
      (lines ?? []).map((l: any) => ({ ...l, amount: Number(l.amount) }))
    bsData.value = {
      as_of: data.as_of,
      asset_lines: toLines(data.asset_lines),
      liability_lines: toLines(data.liability_lines),
      equity_lines: toLines(data.equity_lines),
      retained_earnings: Number(data.retained_earnings),
      total_assets: Number(data.total_assets),
      total_liabilities: Number(data.total_liabilities),
      total_equity: Number(data.total_equity),
      total_liabilities_and_equity: Number(data.total_liabilities_and_equity),
      is_balanced: Boolean(data.is_balanced),
    }
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.finance.loadBalanceSheetError'))
  } finally {
    loading.value = false
  }
}

const checkStatusConfig = computed<Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }>>(() => ({
  received:  { label: t('backoffice.finance.checkReceived'),   variant: 'neutral' },
  deposited: { label: t('backoffice.finance.checkDeposited'),    variant: 'info' },
  cleared:   { label: t('backoffice.finance.checkCleared'),    variant: 'success' },
  bounced:   { label: t('backoffice.finance.checkBounced'),   variant: 'danger' },
}))

async function loadTab(tabId: typeof tab.value) {
  tab.value = tabId
  if (tabId === 'shifts') { await loadShifts(); return }
  if (tabId === 'depreciation') { await loadDepreciation(); return }
  if (tabId === 'bank-reconciliation') { await loadBankAccounts(); return }
  if (tabId === 'balance-sheet') { await loadBalanceSheet(); return }

  loading.value = true
  try {
    if (tabId === 'overview') {
      const res = await api.get(ENDPOINTS.finance.reportsIncomeStatement, {
        params: { branch_id: branchId.value, date_from: firstOfMonth, date_to: today },
      })
      financeData.value = {
        total_revenue: Number(res.data.total_revenue),
        total_expense: Number(res.data.total_expense),
        net_income: Number(res.data.net_income),
      }
    } else if (tabId === 'checks') {
      const res = await api.get(ENDPOINTS.finance.checks, { params: { branch_id: branchId.value } })
      checks.value = res.data.checks ?? res.data.items ?? res.data
    } else if (tabId === 'accounts') {
      const res = await api.get(ENDPOINTS.finance.accounts, { params: { branch_id: branchId.value } })
      accounts.value = res.data.accounts ?? res.data.items ?? res.data
    } else if (tabId === 'cost-centers') {
      await loadCostCenters()
    }
  } catch {
    const messages: Record<'overview' | 'checks' | 'accounts' | 'cost-centers', string> = {
      overview: t('backoffice.finance.loadIncomeStatementError'),
      checks: t('backoffice.finance.loadChecksError'),
      accounts: t('backoffice.finance.loadAccountsError'),
      'cost-centers': t('backoffice.finance.loadCostCentersError'),
    }
    toast.error(messages[tabId as 'overview' | 'checks' | 'accounts' | 'cost-centers'])
  } finally { loading.value = false }
}

async function advanceCheck(check: Check) {
  const flow: Record<string, string> = { received: 'deposited', deposited: 'cleared' }
  const next = flow[check.status]
  if (!next) return
  try {
    await api.patch(ENDPOINTS.finance.checkStatus(check.id), { to_status: next })
    check.status = next
  } catch { toast.error(t('backoffice.finance.updateCheckStatusError')) }
}

// كانت الشاشة بتعرض بس مسار "إيداع → تحصيل" — مفيش أي زرار لتسجيل شيك
// مرتجع (bounced) رغم إن الحالة والـ endpoint موجودين بالكامل في الباك إند
// (راجع CHECK_STATUS_TRANSITIONS في finance/services.py). في الواقع نسبة لا
// يُستهان بها من الشيكات بترتد فعليًا (رصيد غير كافٍ) — فجوة UI صغيرة على
// ميزة موجودة، مش ميزة جديدة.
async function markCheckBounced(check: Check) {
  const ok = await confirm({
    message: t('backoffice.finance.confirmBounceMessage', { number: check.check_number, amount: formatNumber(check.amount) }),
    danger: true, confirmText: t('backoffice.finance.confirmBounceYes'), cancelText: t('backoffice.finance.confirmBounceNo'),
  })
  if (!ok) return
  try {
    await api.patch(ENDPOINTS.finance.checkStatus(check.id), {
      to_status: 'bounced', notes: t('backoffice.finance.bouncedNoteDefault'),
    })
    check.status = 'bounced'
    toast.success(t('backoffice.finance.checkMarkedBounced'))
  } catch { toast.error(t('backoffice.finance.updateCheckStatusError')) }
}

onMounted(() => loadTab('overview'))
</script>

<template>
  <div>
    <h2 class="text-2xl font-black text-gray-900 dark:text-gray-100 mb-6">{{ t('backoffice.finance.title') }}</h2>

    <div class="flex gap-1 bg-stone-100 dark:bg-gray-700 p-1 rounded-xl mb-6 w-fit flex-wrap">
      <button v-for="tabDef in [
        { val: 'overview', label: t('backoffice.finance.tabs.overview') },
        { val: 'checks', label: t('backoffice.finance.tabs.checks') },
        { val: 'accounts', label: t('backoffice.finance.tabs.accounts') },
        { val: 'cost-centers', label: t('backoffice.finance.tabs.costCenters') },
        { val: 'balance-sheet', label: t('backoffice.finance.tabs.balanceSheet') },
        { val: 'depreciation', label: t('backoffice.finance.tabs.depreciation') },
        { val: 'bank-reconciliation', label: t('backoffice.finance.tabs.bankReconciliation') },
        { val: 'shifts', label: t('backoffice.finance.tabs.shifts') },
      ]"
        :key="tabDef.val" @click="loadTab(tabDef.val as any)"
        :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all', tab === tabDef.val ? 'bg-white dark:bg-surface shadow-sm text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:text-gray-300']"
      >{{ tabDef.label }}</button>
    </div>

    <!-- Overview -->
    <div v-if="tab === 'overview'">
      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <div v-else-if="financeData" class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <AppCard padding="lg" class="text-center">
          <div class="text-sm text-gray-500 dark:text-gray-400 mb-2">{{ t('backoffice.finance.totalRevenue') }}</div>
          <div class="text-3xl font-black text-green-600 dark:text-green-300">{{ formatNumber(financeData.total_revenue) }}</div>
          <div class="text-xs text-gray-400 dark:text-gray-400 mt-1">{{ t('backoffice.finance.egpWord') }}</div>
        </AppCard>
        <AppCard padding="lg" class="text-center">
          <div class="text-sm text-gray-500 dark:text-gray-400 mb-2">{{ t('backoffice.finance.totalExpense') }}</div>
          <div class="text-3xl font-black text-red-500">{{ formatNumber(financeData.total_expense) }}</div>
          <div class="text-xs text-gray-400 dark:text-gray-400 mt-1">{{ t('backoffice.finance.egpWord') }}</div>
        </AppCard>
        <AppCard padding="lg" class="text-center">
          <div class="text-sm text-gray-500 dark:text-gray-400 mb-2">{{ t('backoffice.finance.netIncome') }}</div>
          <div :class="['text-3xl font-black', financeData.net_income >= 0 ? 'text-blue-700 dark:text-blue-300' : 'text-red-500 dark:text-red-300']">
            {{ formatNumber(financeData.net_income) }}
          </div>
          <div class="text-xs text-gray-400 dark:text-gray-400 mt-1">{{ t('backoffice.finance.egpWord') }}</div>
        </AppCard>
      </div>
      <AppCard v-else padding="lg">
        <EmptyState icon="📊" :title="t('backoffice.finance.noFinancialData')" />
      </AppCard>
    </div>

    <!-- Checks -->
    <div v-if="tab === 'checks'">
      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.checkNumber') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.drawer') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.amount') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.dueDate') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.statusCol') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.action') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="check in checks" :key="check.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3 font-mono text-sm text-gray-900 dark:text-gray-100">{{ check.check_number }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ check.drawer_name }}</td>
                <td class="px-4 py-3 text-sm font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(check.amount) }} {{ t('backoffice.finance.egp') }}</td>
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ fmtDateFn(check.due_date) }}</td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="checkStatusConfig[check.status]?.variant ?? 'neutral'">
                    {{ checkStatusConfig[check.status]?.label ?? check.status }}
                  </AppBadge>
                </td>
                <td class="px-4 py-3">
                  <div v-if="check.status === 'received' || check.status === 'deposited'" class="flex gap-2">
                    <AppButton size="sm" @click="advanceCheck(check)">
                      {{ check.status === 'received' ? t('backoffice.finance.deposit') : t('backoffice.finance.collect') }}
                    </AppButton>
                    <AppButton size="sm" variant="danger" @click="markCheckBounced(check)">
                      {{ t('backoffice.finance.bounced') }}
                    </AppButton>
                  </div>
                </td>
              </tr>
              <tr v-if="checks.length === 0">
                <td colspan="6" class="px-4 py-8">
                  <EmptyState icon="🏦" :title="t('backoffice.finance.noChecks')" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- Accounts -->
    <div v-if="tab === 'accounts'">
      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.code') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.accountName') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.type') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.balance') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="acc in accounts" :key="acc.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3 font-mono text-sm text-gray-600 dark:text-gray-400">{{ acc.code }}</td>
                <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">{{ acc.name }}</td>
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ acc.account_type }}</td>
                <td class="px-4 py-3 text-sm font-bold" :class="acc.balance >= 0 ? 'text-green-600 dark:text-green-300' : 'text-red-500 dark:text-red-300'">
                  {{ formatNumber(acc.balance) }} {{ t('backoffice.finance.egp') }}
                </td>
              </tr>
              <tr v-if="accounts.length === 0">
                <td colspan="4" class="px-4 py-8">
                  <EmptyState icon="📒" :title="t('backoffice.finance.noAccounts')" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- Cost Centers -->
    <div v-if="tab === 'cost-centers'">
      <div class="flex flex-wrap items-end gap-3 mb-4">
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.fromDate') }}</label>
          <input v-model="ccDateFrom" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
        </div>
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.toDate') }}</label>
          <input v-model="ccDateTo" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
        </div>
        <AppButton size="sm" @click="loadCostCenters">{{ t('backoffice.finance.apply') }}</AppButton>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <template v-else>
        <AppCard padding="none" class="mb-4">
          <div class="overflow-x-auto">
            <table class="w-full">
              <thead class="bg-stone-50 dark:bg-gray-800/60">
                <tr>
                  <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.costCenter') }}</th>
                  <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.revenue') }}</th>
                  <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.expense') }}</th>
                  <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.net') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="line in ccLines" :key="line.code" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                  <td class="px-4 py-3 text-sm font-bold text-gray-900 dark:text-gray-100">{{ line.name }}</td>
                  <td class="px-4 py-3 text-sm font-bold text-green-600 dark:text-green-300">{{ formatNumber(line.revenue) }} {{ t('backoffice.finance.egp') }}</td>
                  <td class="px-4 py-3 text-sm font-bold text-red-600 dark:text-red-300">{{ formatNumber(line.expense) }} {{ t('backoffice.finance.egp') }}</td>
                  <td class="px-4 py-3 text-sm font-bold" :class="line.net >= 0 ? 'text-gray-900 dark:text-gray-100' : 'text-red-700'">
                    {{ formatNumber(line.net) }} {{ t('backoffice.finance.egp') }}
                  </td>
                </tr>
                <tr v-if="ccLines.length === 0">
                  <td colspan="4" class="px-4 py-8">
                    <EmptyState icon="📈" :title="t('backoffice.finance.noDataThisPeriod')" />
                  </td>
                </tr>
              </tbody>
              <tfoot v-if="ccLines.length">
                <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                  <td class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.total') }}</td>
                  <td class="px-4 py-3 text-sm font-black text-green-700 dark:text-green-300">{{ formatNumber(ccTotalRevenue) }} {{ t('backoffice.finance.egp') }}</td>
                  <td class="px-4 py-3 text-sm font-black text-red-700 dark:text-red-300">{{ formatNumber(ccTotalExpense) }} {{ t('backoffice.finance.egp') }}</td>
                  <td class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ formatNumber(ccTotalNet) }} {{ t('backoffice.finance.egp') }}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </AppCard>
        <p class="text-[11px] text-gray-400 dark:text-gray-400">
          {{ t('backoffice.finance.costCenterHint') }}
        </p>
      </template>
    </div>

    <!-- Balance Sheet (الميزانية العمومية) -->
    <div v-if="tab === 'balance-sheet'">
      <div class="flex flex-wrap items-end gap-3 mb-4">
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.asOfDate') }}</label>
          <input v-model="bsAsOf" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
        </div>
        <AppButton size="sm" @click="loadBalanceSheet">{{ t('backoffice.finance.apply') }}</AppButton>
        <AppBadge v-if="bsData" size="sm" :variant="bsData.is_balanced ? 'success' : 'danger'">
          {{ bsData.is_balanced ? `✅ ${t('backoffice.finance.balanced')}` : `⚠️ ${t('backoffice.finance.notBalanced')}` }}
        </AppBadge>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <template v-else-if="bsData">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
          <AppCard padding="none">
            <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.assets') }}</div>
            <div class="overflow-x-auto">
              <table class="w-full">
                <tbody>
                  <tr v-for="l in bsData.asset_lines" :key="l.account_code" class="border-t border-stone-100 dark:border-border/50">
                    <td class="px-4 py-2 text-xs font-mono text-gray-500 dark:text-gray-400">{{ l.account_code }}</td>
                    <td class="px-4 py-2 text-sm text-gray-900 dark:text-gray-100">{{ l.account_name }}</td>
                    <td class="px-4 py-2 text-sm font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(l.amount) }} {{ t('backoffice.finance.egp') }}</td>
                  </tr>
                  <tr v-if="bsData.asset_lines.length === 0">
                    <td colspan="3" class="px-4 py-6"><EmptyState icon="🏦" :title="t('backoffice.finance.noAssetsToDate')" /></td>
                  </tr>
                </tbody>
                <tfoot v-if="bsData.asset_lines.length">
                  <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                    <td colspan="2" class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.totalAssets') }}</td>
                    <td class="px-4 py-3 text-sm font-black text-green-700 dark:text-green-300">{{ formatNumber(bsData.total_assets) }} {{ t('backoffice.finance.egp') }}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </AppCard>

          <div class="space-y-4">
            <AppCard padding="none">
              <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.liabilities') }}</div>
              <div class="overflow-x-auto">
                <table class="w-full">
                  <tbody>
                    <tr v-for="l in bsData.liability_lines" :key="l.account_code" class="border-t border-stone-100 dark:border-border/50">
                      <td class="px-4 py-2 text-xs font-mono text-gray-500 dark:text-gray-400">{{ l.account_code }}</td>
                      <td class="px-4 py-2 text-sm text-gray-900 dark:text-gray-100">{{ l.account_name }}</td>
                      <td class="px-4 py-2 text-sm font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(l.amount) }} {{ t('backoffice.finance.egp') }}</td>
                    </tr>
                    <tr v-if="bsData.liability_lines.length === 0">
                      <td colspan="3" class="px-4 py-6"><EmptyState icon="📋" :title="t('backoffice.finance.noLiabilitiesToDate')" /></td>
                    </tr>
                  </tbody>
                  <tfoot v-if="bsData.liability_lines.length">
                    <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                      <td colspan="2" class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.totalLiabilities') }}</td>
                      <td class="px-4 py-3 text-sm font-black text-red-700 dark:text-red-300">{{ formatNumber(bsData.total_liabilities) }} {{ t('backoffice.finance.egp') }}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </AppCard>

            <AppCard padding="none">
              <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.equity') }}</div>
              <div class="overflow-x-auto">
                <table class="w-full">
                  <tbody>
                    <tr v-for="l in bsData.equity_lines" :key="l.account_code" class="border-t border-stone-100 dark:border-border/50">
                      <td class="px-4 py-2 text-xs font-mono text-gray-500 dark:text-gray-400">{{ l.account_code }}</td>
                      <td class="px-4 py-2 text-sm text-gray-900 dark:text-gray-100">{{ l.account_name }}</td>
                      <td class="px-4 py-2 text-sm font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(l.amount) }} {{ t('backoffice.finance.egp') }}</td>
                    </tr>
                    <tr class="border-t border-stone-100 dark:border-border/50">
                      <td colspan="2" class="px-4 py-2 text-sm text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.retainedEarnings') }}</td>
                      <td class="px-4 py-2 text-sm font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(bsData.retained_earnings) }} {{ t('backoffice.finance.egp') }}</td>
                    </tr>
                  </tbody>
                  <tfoot>
                    <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                      <td colspan="2" class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.totalLiabilitiesAndEquity') }}</td>
                      <td class="px-4 py-3 text-sm font-black text-blue-700 dark:text-blue-300">{{ formatNumber(bsData.total_liabilities_and_equity) }} {{ t('backoffice.finance.egp') }}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </AppCard>
          </div>
        </div>
        <p class="text-[11px] text-gray-400 dark:text-gray-400">
          {{ t('backoffice.finance.balanceSheetHint') }}
        </p>
      </template>
      <AppCard v-else padding="lg">
        <EmptyState icon="⚖️" :title="t('backoffice.finance.noBalanceSheetData')" />
      </AppCard>
    </div>

    <!-- Depreciation -->
    <div v-if="tab === 'depreciation'">
      <AppCard class="mb-4">
        <div class="flex flex-wrap items-end gap-3">
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.year') }}</label>
            <input v-model.number="depYear" type="number" min="2020" max="2100"
              class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm w-28" />
          </div>
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.month') }}</label>
            <input v-model.number="depMonth" type="number" min="1" max="12"
              class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm w-20" />
          </div>
          <AppButton size="sm" :loading="runningDepreciation" @click="runDepreciation">
            {{ t('backoffice.finance.runDepreciationCycle') }}
          </AppButton>
        </div>
        <div v-if="lastRunResult" class="mt-3 text-sm">
          <p class="font-semibold text-green-700 dark:text-green-300">
            {{ t('backoffice.finance.depreciationRunSummary', { count: lastRunResult.entries_count, amount: formatNumber(lastRunResult.total_amount) }) }}
          </p>
          <p v-if="lastRunResult.skipped.length" class="text-gray-400 dark:text-gray-400 text-xs mt-1">
            {{ t('backoffice.finance.skippedList', { names: lastRunResult.skipped.join('، ') }) }}
          </p>
        </div>
      </AppCard>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.asset') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.month') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.depreciationAmount') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.accumulatedAfter') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="e in depreciationEntries" :key="e.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">{{ assetsById[e.asset_id] ?? t('backoffice.finance.assetHash', { id: e.asset_id }) }}</td>
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ e.month }}/{{ e.year }}</td>
                <td class="px-4 py-3 text-sm font-bold text-red-500">{{ formatNumber(Number(e.amount)) }} {{ t('backoffice.finance.egp') }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ formatNumber(Number(e.accumulated_after)) }} {{ t('backoffice.finance.egp') }}</td>
              </tr>
              <tr v-if="depreciationEntries.length === 0">
                <td colspan="4" class="px-4 py-8">
                  <EmptyState icon="📉" :title="t('backoffice.finance.noDepreciationEntries')" :subtitle="t('backoffice.finance.noDepreciationEntriesHint')" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- Bank Reconciliation -->
    <div v-if="tab === 'bank-reconciliation'">
      <div class="flex justify-between items-center mb-4">
        <select v-if="bankAccounts.length" v-model.number="selectedBankAccountId" @change="loadStatementLinesAndSummary"
          class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm">
          <option v-for="ba in bankAccounts" :key="ba.id" :value="ba.id">
            {{ ba.bank_name }} — {{ ba.account_number }}
          </option>
        </select>
        <span v-else />
        <AppButton size="sm" @click="showBankAccountForm = !showBankAccountForm">
          {{ showBankAccountForm ? t('backoffice.finance.cancel') : t('backoffice.finance.newBankAccount') }}
        </AppButton>
      </div>

      <AppCard v-if="showBankAccountForm" class="mb-4">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input v-model="bankAccountForm.bank_name" type="text" :placeholder="t('backoffice.finance.bankName')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="bankAccountForm.account_name" type="text" :placeholder="t('backoffice.finance.accountNameOptional')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="bankAccountForm.account_number" type="text" :placeholder="t('backoffice.finance.accountNumber')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="bankAccountForm.opening_balance" type="number" step="0.01" :placeholder="t('backoffice.finance.openingBalance')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        </div>
        <AppButton class="mt-3" size="sm" @click="createBankAccount">{{ t('backoffice.finance.saveAccount') }}</AppButton>
      </AppCard>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <EmptyState v-else-if="bankAccounts.length === 0" icon="🏦" :title="t('backoffice.finance.noBankAccountsYet')" />
      <template v-else>
        <div v-if="reconciliationSummary" class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <AppCard padding="md" class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.bookBalance') }}</div>
            <div class="text-lg font-black text-gray-900 dark:text-gray-100">{{ formatNumber(reconciliationSummary.book_balance) }}</div>
          </AppCard>
          <AppCard padding="md" class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.statementBalance') }}</div>
            <div class="text-lg font-black text-gray-900 dark:text-gray-100">{{ formatNumber(reconciliationSummary.statement_balance) }}</div>
          </AppCard>
          <AppCard padding="md" class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.difference') }}</div>
            <div :class="['text-lg font-black', reconciliationSummary.is_reconciled ? 'text-green-600 dark:text-green-300' : 'text-amber-600 dark:text-amber-300']">
              {{ formatNumber(reconciliationSummary.difference) }}
            </div>
          </AppCard>
          <AppCard padding="md" class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.statusLabel') }}</div>
            <AppBadge :variant="reconciliationSummary.is_reconciled ? 'success' : 'warning'">
              {{ reconciliationSummary.is_reconciled ? `${t('backoffice.finance.reconciled')} ✓` : t('backoffice.finance.notReconciled') }}
            </AppBadge>
          </AppCard>
        </div>

        <div class="flex justify-end mb-3">
          <AppButton size="sm" :loading="matchingInProgress" @click="runAutoMatch">
            {{ t('backoffice.finance.autoMatchConservative') }}
          </AppButton>
        </div>

        <AppCard padding="none">
          <div class="overflow-x-auto">
            <table class="w-full">
              <thead class="bg-stone-50 dark:bg-gray-800/60">
                <tr>
                  <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.date') }}</th>
                  <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.description') }}</th>
                  <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.amount') }}</th>
                  <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.statusCol') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="line in statementLines" :key="line.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                  <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ line.line_date }}</td>
                  <td class="px-4 py-3 text-sm text-gray-900 dark:text-gray-100">{{ line.description }}</td>
                  <td class="px-4 py-3 text-sm font-bold" :class="line.amount >= 0 ? 'text-green-600 dark:text-green-300' : 'text-red-500 dark:text-red-300'">
                    {{ formatNumber(Number(line.amount)) }}
                  </td>
                  <td class="px-4 py-3">
                    <AppBadge size="sm" :variant="statementLineStatusConfig[line.status]?.variant ?? 'neutral'">
                      {{ statementLineStatusConfig[line.status]?.label ?? line.status }}
                    </AppBadge>
                  </td>
                </tr>
                <tr v-if="statementLines.length === 0">
                  <td colspan="4" class="px-4 py-8">
                    <EmptyState icon="📄" :title="t('backoffice.finance.noStatementLines')" />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </AppCard>
      </template>
    </div>

    <!-- Shifts tab -->
    <div v-if="tab === 'shifts'" class="space-y-4">
      <div class="flex items-center gap-3 flex-wrap">
        <div class="flex gap-1 bg-stone-100 dark:bg-gray-700 p-1 rounded-xl">
          <button v-for="s in [
            { v: 'all', l: t('backoffice.finance.all') },
            { v: 'open', l: t('backoffice.finance.shiftOpen') },
            { v: 'closed', l: t('backoffice.finance.shiftClosed') },
          ]"
            :key="s.v" @click="shiftStatus = s.v as any; loadShifts()"
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
        <table class="w-full text-sm">
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
              <td class="px-4 py-3 font-mono text-gray-500 dark:text-gray-400">#{{ s.id }}</td>
              <td class="px-4 py-3 font-semibold">{{ s.cashier_id }}</td>
              <td class="px-4 py-3 text-gray-600 dark:text-gray-400 text-xs">
                {{ fmtDateTimeFn(s.opened_at) }}
              </td>
              <td class="px-4 py-3 text-gray-500 dark:text-gray-400 text-xs">
                {{ s.closed_at ? fmtDateTimeFn(s.closed_at) : '—' }}
              </td>
              <td class="px-4 py-3">
                <span :class="['px-2 py-0.5 rounded-full text-xs font-bold',
                  s.status === 'open'
                    ? 'bg-green-100 text-green-700 dark:bg-green-950/50 dark:text-green-300'
                    : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300']">
                  {{ s.status === 'open' ? t('backoffice.finance.shiftOpen') : t('backoffice.finance.shiftClosed') }}
                </span>
                <span v-if="s.reconciliation_warning" class="ms-1 text-red-500 cursor-help"
                  :title="s.reconciliation_warning">⚠️</span>
              </td>
              <td class="px-4 py-3 text-gray-700 dark:text-gray-300">{{ s.expected_cash?.toFixed(2) ?? '—' }}</td>
              <td class="px-4 py-3 text-gray-700 dark:text-gray-300">{{ s.counted_cash?.toFixed(2) ?? '—' }}</td>
              <td class="px-4 py-3" :class="shiftVarianceClass(s.variance)">
                {{ s.variance != null ? (s.variance > 0 ? '+' : '') + s.variance.toFixed(2) : '—' }}
              </td>
              <td class="px-4 py-3">
                <a v-if="s.status === 'closed'"
                  :href="ENDPOINTS.finance.shiftReportPdf(s.id)"
                  target="_blank"
                  @click.stop
                  class="text-xs font-semibold text-blue-600 hover:underline dark:text-blue-300">📄 PDF</a>
                <span v-else class="text-gray-300 text-xs">—</span>
              </td>
            </tr>
            <tr v-if="!filteredShifts.length">
              <td colspan="9" class="px-4 py-12 text-center text-gray-400 dark:text-gray-400">{{ t('backoffice.finance.noShifts') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
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
          <div v-else class="divide-y divide-stone-100 dark:divide-border/50 max-h-64 overflow-y-auto">
            <div v-for="inv in detailInvoices" :key="inv.payment_id"
              class="py-2 flex items-center justify-between gap-2" :class="inv.is_voided && 'opacity-50'">
              <div>
                <span class="text-sm font-semibold text-gray-800 dark:text-gray-200" :class="inv.is_voided && 'line-through'">{{ inv.guest_name }}</span>
                <span class="text-xs text-gray-400 dark:text-gray-400 ms-2">{{ METHOD_LABEL[inv.method] ?? inv.method }}</span>
              </div>
              <span class="text-sm font-bold" :class="inv.is_voided ? 'text-gray-400 dark:text-gray-400 line-through' : 'text-blue-700 dark:text-blue-400'">{{ inv.amount.toFixed(2) }} {{ t('backoffice.finance.egp') }}</span>
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
