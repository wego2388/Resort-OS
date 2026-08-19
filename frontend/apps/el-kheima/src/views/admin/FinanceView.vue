<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS, useAuthStore, useResortWebSocket } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'
import StepUpConfirmModal from '../../components/StepUpConfirmModal.vue'
import PinGuardModal from '../../components/PinGuardModal.vue'

const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatNumber, formatDate: fmtDateFn, formatDateTime: fmtDateTimeFn } = useStaffFormat()
const auth = useAuthStore()
// CX-02C: branchId comes from bootstrap (session-scoped, no ?? 1 fallback).
// activeBranchId is null when requires_branch_selection=true — in that case
// API calls carry no branch_id and the server returns 409 BRANCH_CONTEXT_REQUIRED.
const branchId = computed(() => auth.activeBranchId)
const tab = ref<'overview' | 'checks' | 'accounts' | 'cost-centers' | 'balance-sheet' | 'depreciation' | 'bank-reconciliation' | 'shifts' | 'exchange-rates' | 'journal' | 'payment-channels' | 'expenses' | 'custodies' | 'cash-receipts' | 'trial-balance' | 'income-statement' | 'aging' | 'periods'>('overview')
const activeGroupIdx = ref(0)

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
// Raw API shapes — backend returns Decimal fields as strings
interface RawCashCountLine {
  denomination: unknown; currency: unknown
  quantity: unknown; subtotal: unknown; fx_rate: unknown; egp_equivalent: unknown
}
interface RawFxSummaryLine { currency: unknown; total_foreign: unknown; fx_rate: unknown; egp_equivalent: unknown }
interface RawInvoiceLine { amount: unknown; [key: string]: unknown }
interface ShiftWsMessage { type?: string; shift_id?: number; [key: string]: unknown }
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
interface PaymentChannel {
  id: number; branch_id: number; code: string; name: string; name_ar: string | null
  method: 'cash' | 'card' | 'wallet'
  gl_account_id: number; gl_account_code: string; gl_account_name: string
  bank_account_id: number | null; bank_account_name: string | null
  is_default: boolean; is_active: boolean; sort_order: number
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
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.runDepreciationError'))
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
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.bankAccountCreateError'))
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

// ── Payment Channels ──────────────────────────────────────────────────
// شاشة إدارة قنوات التحصيل (صندوق/Visa CIB/Vodafone Cash...) — كل قناة
// مربوطة إجباريًا بحساب GL وباختيار حساب بنكي. الصلاحية الحقيقية على
// الـbackend (get_finance_user + assert_branch_access)، الشاشة دي مجرد
// واجهة — مفيش أي منطق تحقق بيزنس هنا (راجع CLAUDE.md §4).
const paymentChannels = ref<PaymentChannel[]>([])
const showChannelForm = ref(false)
const editingChannelId = ref<number | null>(null)
const channelFormError = ref('')
const channelSaving = ref(false)
const channelForm = ref({
  code: '', name: '', name_ar: '', method: 'cash' as 'cash' | 'card' | 'wallet',
  gl_account_id: null as number | null, bank_account_id: null as number | null,
  is_default: false,
})

const glAccountOptions = computed(() => accounts.value.filter(a => a.account_type === 'asset'))

function resetChannelForm() {
  editingChannelId.value = null
  channelFormError.value = ''
  channelForm.value = { code: '', name: '', name_ar: '', method: 'cash', gl_account_id: null, bank_account_id: null, is_default: false }
}

async function loadPaymentChannels() {
  loading.value = true
  try {
    const [channelsRes] = await Promise.all([
      api.get(ENDPOINTS.finance.paymentChannels, { params: { branch_id: branchId.value } }),
      accounts.value.length ? Promise.resolve() : api.get(ENDPOINTS.finance.accounts, { params: { branch_id: branchId.value } }).then(r => { accounts.value = r.data.accounts ?? r.data.items ?? r.data }),
      bankAccounts.value.length ? Promise.resolve() : api.get(ENDPOINTS.finance.bankAccounts, { params: { branch_id: branchId.value } }).then(r => { bankAccounts.value = r.data }),
    ])
    paymentChannels.value = channelsRes.data
  } catch { toast.error(t('backoffice.finance.paymentChannels.loadError')) }
  finally { loading.value = false }
}

function editChannel(channel: PaymentChannel) {
  editingChannelId.value = channel.id
  channelFormError.value = ''
  channelForm.value = {
    code: channel.code, name: channel.name, name_ar: channel.name_ar ?? '',
    method: channel.method, gl_account_id: channel.gl_account_id,
    bank_account_id: channel.bank_account_id, is_default: channel.is_default,
  }
  showChannelForm.value = true
}

async function savePaymentChannel() {
  if (!channelForm.value.code || !channelForm.value.name || !channelForm.value.gl_account_id) {
    channelFormError.value = t('backoffice.finance.paymentChannels.fieldsRequired'); return
  }
  channelSaving.value = true
  channelFormError.value = ''
  try {
    if (editingChannelId.value) {
      await api.patch(ENDPOINTS.finance.paymentChannel(editingChannelId.value), {
        name: channelForm.value.name,
        name_ar: channelForm.value.name_ar || null,
        gl_account_id: channelForm.value.gl_account_id,
        bank_account_id: channelForm.value.bank_account_id,
        clear_bank_account: channelForm.value.bank_account_id == null,
        is_default: channelForm.value.is_default,
      })
      toast.success(t('backoffice.finance.paymentChannels.updated'))
    } else {
      await api.post(ENDPOINTS.finance.paymentChannels, {
        branch_id: branchId.value,
        code: channelForm.value.code,
        name: channelForm.value.name,
        name_ar: channelForm.value.name_ar || null,
        method: channelForm.value.method,
        gl_account_id: channelForm.value.gl_account_id,
        bank_account_id: channelForm.value.bank_account_id,
        is_default: channelForm.value.is_default,
      })
      toast.success(t('backoffice.finance.paymentChannels.created'))
    }
    showChannelForm.value = false
    resetChannelForm()
    await loadPaymentChannels()
  } catch (e: unknown) {
    channelFormError.value = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.paymentChannels.saveError')
  } finally {
    channelSaving.value = false
  }
}

async function toggleChannelActive(channel: PaymentChannel) {
  try {
    await api.patch(ENDPOINTS.finance.paymentChannel(channel.id), { is_active: !channel.is_active })
    toast.success(channel.is_active ? t('backoffice.finance.paymentChannels.disabled') : t('backoffice.finance.paymentChannels.enabled'))
    await loadPaymentChannels()
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.paymentChannels.saveError'))
  }
}

async function setChannelDefault(channel: PaymentChannel) {
  if (channel.is_default) return
  try {
    await api.patch(ENDPOINTS.finance.paymentChannel(channel.id), { is_default: true })
    toast.success(t('backoffice.finance.paymentChannels.defaultSet'))
    await loadPaymentChannels()
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.paymentChannels.saveError'))
  }
}

const paymentChannelMethodLabels = computed<Record<string, string>>(() => ({
  cash: t('backoffice.finance.methodCash'),
  card: t('backoffice.finance.methodCard'),
  wallet: t('backoffice.finance.paymentChannels.methodWallet'),
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
    const toLines = (lines: { amount?: unknown; [k: string]: unknown }[]): BalanceSheetLine[] =>
      (lines ?? []).map((l) => ({ ...l, amount: Number(l.amount) } as BalanceSheetLine))
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
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.loadBalanceSheetError'))
  } finally {
    loading.value = false
  }
}

// نفس نمط HRView.vue's downloadBlobFile بالظبط (blob response + object URL
// + تنزيل تلقائي + revoke بعد 5 ثواني) — مفيش util مشترك للنمط ده جوه
// @resort-os/core/ui حاليًا، فكل شاشة بتكرره محليًا (نفس القرار الموثّق هناك).
function downloadBlobFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}

// ── ميزان المراجعة (Trial Balance) — 2026-08-19 ───────────────────────
interface TrialBalanceLineRow { account_code: string; account_name: string; account_type: string; debit: number; credit: number }
interface TrialBalanceData {
  as_of: string; lines: TrialBalanceLineRow[]
  total_debit: number; total_credit: number; is_balanced: boolean; grouped_by_parent: boolean
}
const tbAsOf = ref(today)
const tbGroupByParent = ref(false)
const tbData = ref<TrialBalanceData | null>(null)
const tbDownloading = ref<'pdf' | 'excel' | null>(null)

async function loadTrialBalance() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.reportsTrialBalance, {
      params: { branch_id: branchId.value, as_of: tbAsOf.value, group_by_parent: tbGroupByParent.value },
    })
    tbData.value = {
      as_of: data.as_of,
      lines: (data.lines ?? []).map((l: Record<string, unknown>) => ({ ...l, debit: Number(l.debit), credit: Number(l.credit) } as TrialBalanceLineRow)),
      total_debit: Number(data.total_debit),
      total_credit: Number(data.total_credit),
      is_balanced: Boolean(data.is_balanced),
      grouped_by_parent: Boolean(data.grouped_by_parent),
    }
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.trialBalance.loadError'))
  } finally {
    loading.value = false
  }
}
async function downloadTrialBalance(fmt: 'pdf' | 'excel') {
  tbDownloading.value = fmt
  try {
    const url = fmt === 'pdf' ? ENDPOINTS.finance.reportsTrialBalancePdf : ENDPOINTS.finance.reportsTrialBalanceExcel
    const res = await api.get(url, {
      params: { branch_id: branchId.value, as_of: tbAsOf.value, group_by_parent: tbGroupByParent.value },
      responseType: 'blob',
    })
    downloadBlobFile(res.data, `trial-balance-${tbAsOf.value}.${fmt === 'pdf' ? 'pdf' : 'xlsx'}`)
  } catch {
    toast.error(t('backoffice.finance.reportDownloadError'))
  } finally {
    tbDownloading.value = null
  }
}

// ── قائمة الدخل التفصيلية (Income Statement) — 2026-08-19 ─────────────
interface IncomeStatementLineRow { account_code: string; account_name: string; amount: number }
interface IncomeStatementData {
  date_from: string; date_to: string
  revenue_lines: IncomeStatementLineRow[]; expense_lines: IncomeStatementLineRow[]
  total_revenue: number; total_expense: number; net_income: number
}
const isDateFrom = ref(firstOfMonth)
const isDateTo = ref(today)
const isData = ref<IncomeStatementData | null>(null)
const isDownloading = ref<'pdf' | 'excel' | null>(null)

async function loadIncomeStatementReport() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.reportsIncomeStatement, {
      params: { branch_id: branchId.value, date_from: isDateFrom.value, date_to: isDateTo.value },
    })
    isData.value = {
      date_from: data.date_from,
      date_to: data.date_to,
      revenue_lines: (data.revenue_lines ?? []).map((l: Record<string, unknown>) => ({ ...l, amount: Number(l.amount) } as IncomeStatementLineRow)),
      expense_lines: (data.expense_lines ?? []).map((l: Record<string, unknown>) => ({ ...l, amount: Number(l.amount) } as IncomeStatementLineRow)),
      total_revenue: Number(data.total_revenue),
      total_expense: Number(data.total_expense),
      net_income: Number(data.net_income),
    }
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.loadIncomeStatementError'))
  } finally {
    loading.value = false
  }
}
async function downloadIncomeStatement(fmt: 'pdf' | 'excel') {
  isDownloading.value = fmt
  try {
    const url = fmt === 'pdf' ? ENDPOINTS.finance.reportsIncomeStatementPdf : ENDPOINTS.finance.reportsIncomeStatementExcel
    const res = await api.get(url, {
      params: { branch_id: branchId.value, date_from: isDateFrom.value, date_to: isDateTo.value },
      responseType: 'blob',
    })
    downloadBlobFile(res.data, `income-statement-${isDateFrom.value}_${isDateTo.value}.${fmt === 'pdf' ? 'pdf' : 'xlsx'}`)
  } catch {
    toast.error(t('backoffice.finance.reportDownloadError'))
  } finally {
    isDownloading.value = null
  }
}

// ── الميزانية العمومية — تصدير PDF/Excel (الشاشة موجودة، التصدير جديد) ─
const bsDownloading = ref<'pdf' | 'excel' | null>(null)
async function downloadBalanceSheet(fmt: 'pdf' | 'excel') {
  bsDownloading.value = fmt
  try {
    const url = fmt === 'pdf' ? ENDPOINTS.finance.reportsBalanceSheetPdf : ENDPOINTS.finance.reportsBalanceSheetExcel
    const res = await api.get(url, { params: { branch_id: branchId.value, as_of: bsAsOf.value }, responseType: 'blob' })
    downloadBlobFile(res.data, `balance-sheet-${bsAsOf.value}.${fmt === 'pdf' ? 'pdf' : 'xlsx'}`)
  } catch {
    toast.error(t('backoffice.finance.reportDownloadError'))
  } finally {
    bsDownloading.value = null
  }
}

// ── تقرير أعمار الديون (Aging) — 2026-08-19 ────────────────────────────
interface AgingBucketRow { label: string; count: number; amount: number }
interface ReceivableAgingRow { folio_id: number; guest_name: string; check_in: string; days_outstanding: number; balance_due: number; bucket: string }
interface PayableAgingRow { source_type: string; source_id: number; reference: string; counterparty: string; due_date: string; days_outstanding: number; remaining: number; bucket: string }
interface AgingData {
  as_of: string
  receivables: ReceivableAgingRow[]; receivables_total: number; receivables_buckets: AgingBucketRow[]
  payables: PayableAgingRow[]; payables_total: number; payables_buckets: AgingBucketRow[]
}
const agingAsOf = ref(today)
const agingData = ref<AgingData | null>(null)

async function loadAging() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.reportsAging, { params: { branch_id: branchId.value, as_of: agingAsOf.value } })
    agingData.value = {
      as_of: data.as_of,
      receivables: (data.receivables ?? []).map((l: Record<string, unknown>) => ({ ...l, balance_due: Number(l.balance_due) } as ReceivableAgingRow)),
      receivables_total: Number(data.receivables_total),
      receivables_buckets: (data.receivables_buckets ?? []).map((b: Record<string, unknown>) => ({ ...b, amount: Number(b.amount) } as AgingBucketRow)),
      payables: (data.payables ?? []).map((l: Record<string, unknown>) => ({ ...l, remaining: Number(l.remaining) } as PayableAgingRow)),
      payables_total: Number(data.payables_total),
      payables_buckets: (data.payables_buckets ?? []).map((b: Record<string, unknown>) => ({ ...b, amount: Number(b.amount) } as AgingBucketRow)),
    }
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.aging.loadError'))
  } finally {
    loading.value = false
  }
}
// تدرّج لوني حسب عمر الدين — بادج أخضر (0-30) → كهرماني (31-60) → برتقالي
// (61-90) → أحمر (90+، متأخر بشكل جدّي يستاهل متابعة فورية).
function agingBucketVariant(bucket: string): 'success' | 'warning' | 'danger' | 'neutral' {
  if (bucket === '0-30') return 'success'
  if (bucket === '31-60') return 'warning'
  if (bucket === '61-90') return 'danger'
  return 'danger'
}

// ── الفترات المحاسبية + الإقفال السنوي (Periods) — 2026-08-19 ─────────
interface PeriodRow { id: number; year: number; month: number; status: string; closed_at: string | null }
const periodsYear = ref(new Date().getFullYear())
const periodsRaw = ref<PeriodRow[]>([])
const periodsLoading = ref(false)
const closingMonthKey = ref<number | null>(null)
const closingYear = ref(false)
const yearCloseResult = ref<{ journal_entry_id: number; net_income: number; closed_at: string } | null>(null)

const periodsGrid = computed(() => {
  return Array.from({ length: 12 }, (_, i) => {
    const month = i + 1
    const row = periodsRaw.value.find(p => p.month === month)
    return { month, status: row?.status ?? 'open', closedAt: row?.closed_at ?? null }
  })
})
const allMonthsClosed = computed(() => periodsGrid.value.every(m => m.status === 'closed' || m.status === 'locked'))
const monthNames = computed(() => Array.from({ length: 12 }, (_, i) =>
  fmtDateFn(new Date(2000, i, 1), { month: 'long' } as Intl.DateTimeFormatOptions)))

async function loadPeriods() {
  periodsLoading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.periods, { params: { branch_id: branchId.value, page: 1, size: 200 } })
    periodsRaw.value = ((data.items ?? []) as PeriodRow[]).filter(p => p.year === periodsYear.value)
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.periods.loadError'))
  } finally {
    periodsLoading.value = false
  }
}
async function closeMonth(month: number) {
  const ok = await confirm({
    message: t('backoffice.finance.periods.confirmCloseMonth', { month: monthNames.value[month - 1], year: periodsYear.value }),
    danger: true,
  })
  if (!ok) return
  closingMonthKey.value = month
  try {
    await api.post(ENDPOINTS.finance.periodClose(periodsYear.value, month), { branch_id: branchId.value })
    toast.success(t('backoffice.finance.periods.closeMonthSuccess'))
    await loadPeriods()
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.periods.closeMonthError'))
  } finally {
    closingMonthKey.value = null
  }
}
async function closeYear() {
  const ok = await confirm({
    message: t('backoffice.finance.periods.confirmCloseYear', { year: periodsYear.value }),
    danger: true, confirmText: t('backoffice.finance.periods.closeYearConfirm'), cancelText: t('backoffice.finance.cancel'),
  })
  if (!ok) return
  closingYear.value = true
  try {
    const { data } = await api.post(ENDPOINTS.finance.closeYear(periodsYear.value), null, { params: { branch_id: branchId.value } })
    yearCloseResult.value = { journal_entry_id: data.journal_entry_id, net_income: Number(data.net_income), closed_at: data.closed_at }
    toast.success(t('backoffice.finance.periods.closeYearSuccess'))
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.periods.closeYearError'))
  } finally {
    closingYear.value = false
  }
}

const checkStatusConfig = computed<Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }>>(() => ({
  received:  { label: t('backoffice.finance.checkReceived'),   variant: 'neutral' },
  deposited: { label: t('backoffice.finance.checkDeposited'),    variant: 'info' },
  cleared:   { label: t('backoffice.finance.checkCleared'),    variant: 'success' },
  bounced:   { label: t('backoffice.finance.checkBounced'),   variant: 'danger' },
}))

// ── كشف حساب — drill-down لكل حساب (2026-08-19، طلب Mohamed) ──────────
interface AccountLedgerLineRow {
  entry_id: number; entry_date: string; reference: string; description: string
  debit: number; credit: number; running_balance: number
}
interface AccountLedgerData {
  account_id: number; account_code: string; account_name: string; account_type: string
  date_from: string; date_to: string
  opening_balance: number; closing_balance: number; total_debit: number; total_credit: number
  lines: AccountLedgerLineRow[]
}
const ledgerModal = reactive({ open: false, loading: false, error: '', account: null as Account | null, dateFrom: firstOfMonth, dateTo: today })
const ledgerData = ref<AccountLedgerData | null>(null)

async function loadAccountLedger() {
  if (!ledgerModal.account) return
  ledgerModal.loading = true
  ledgerModal.error = ''
  try {
    const { data } = await api.get(ENDPOINTS.finance.accountLedger(ledgerModal.account.id), {
      params: { branch_id: branchId.value, date_from: ledgerModal.dateFrom, date_to: ledgerModal.dateTo },
    })
    ledgerData.value = {
      ...data,
      opening_balance: Number(data.opening_balance),
      closing_balance: Number(data.closing_balance),
      total_debit: Number(data.total_debit),
      total_credit: Number(data.total_credit),
      lines: (data.lines ?? []).map((l: Record<string, unknown>) => ({
        ...l, debit: Number(l.debit), credit: Number(l.credit), running_balance: Number(l.running_balance),
      })),
    } as AccountLedgerData
  } catch (e: unknown) {
    ledgerModal.error = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.ledger.loadError')
  } finally {
    ledgerModal.loading = false
  }
}
function openAccountLedger(acc: Account) {
  ledgerModal.account = acc
  ledgerModal.open = true
  ledgerModal.dateFrom = firstOfMonth
  ledgerModal.dateTo = today
  ledgerData.value = null
  loadAccountLedger()
}
function closeAccountLedger() {
  ledgerModal.open = false
  ledgerData.value = null
}

async function loadTab(tabId: typeof tab.value) {
  tab.value = tabId
  if (tabId === 'shifts') { await loadShifts(); return }
  if (tabId === 'depreciation') { await loadDepreciation(); return }
  if (tabId === 'bank-reconciliation') { await loadBankAccounts(); return }
  if (tabId === 'balance-sheet') { await loadBalanceSheet(); return }
  if (tabId === 'exchange-rates') { await loadExchangeRates(); return }
  if (tabId === 'journal') { journalPage.value = 1; await loadJournal(); return }
  if (tabId === 'payment-channels') { await loadPaymentChannels(); return }
  if (tabId === 'expenses') {
    expensesPage.value = 1
    await Promise.all([
      loadExpenses(),
      accounts.value.length ? Promise.resolve() : api.get(ENDPOINTS.finance.accounts, { params: { branch_id: branchId.value } }).then(r => { accounts.value = r.data.accounts ?? r.data.items ?? r.data }),
    ])
    return
  }
  if (tabId === 'custodies') {
    custodiesPage.value = 1
    await Promise.all([
      loadCustodies(),
      accounts.value.length ? Promise.resolve() : api.get(ENDPOINTS.finance.accounts, { params: { branch_id: branchId.value } }).then(r => { accounts.value = r.data.accounts ?? r.data.items ?? r.data }),
    ])
    return
  }
  if (tabId === 'cash-receipts') {
    cashReceiptsPage.value = 1
    await Promise.all([
      loadCashReceipts(),
      accounts.value.length ? Promise.resolve() : api.get(ENDPOINTS.finance.accounts, { params: { branch_id: branchId.value } }).then(r => { accounts.value = r.data.accounts ?? r.data.items ?? r.data }),
    ])
    return
  }
  if (tabId === 'trial-balance') { await loadTrialBalance(); return }
  if (tabId === 'income-statement') { await loadIncomeStatementReport(); return }
  if (tabId === 'aging') { await loadAging(); return }
  if (tabId === 'periods') { yearCloseResult.value = null; await loadPeriods(); return }

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

// ── دفتر اليومية (Journal Entries) ──────────────────────────────────
interface JournalLine { account_id: number; account_code: string; account_name: string; debit: number; credit: number; description: string | null }
interface JournalEntry {
  id: number; entry_date: string; reference: string; description: string
  status: string; source: string | null; created_by: number; currency: string
  lines: JournalLine[]
}
const journalEntries   = ref<JournalEntry[]>([])
const journalTotal     = ref(0)
const journalPage      = ref(1)
const journalDateFrom  = ref(firstOfMonth)
const journalDateTo    = ref(today)
const journalSource    = ref('')
const journalLoading   = ref(false)
const journalExpanded  = ref<number | null>(null)

async function loadJournal() {
  journalLoading.value = true
  try {
    const params: Record<string, unknown> = {
      branch_id: branchId.value,
      date_from: journalDateFrom.value,
      date_to:   journalDateTo.value,
      page: journalPage.value,
      size: 30,
    }
    if (journalSource.value) params.source = journalSource.value
    const { data } = await api.get(ENDPOINTS.finance.journalEntries, { params })
    journalEntries.value = (data.items ?? []).map((e: Record<string, unknown>) => ({
      ...e,
      lines: (e.lines as JournalLine[] ?? []).map((l: JournalLine) => ({
        ...l,
        debit:  Number(l.debit  ?? 0),
        credit: Number(l.credit ?? 0),
      })),
    }))
    journalTotal.value = data.total ?? 0
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.journal.loadError'))
  } finally {
    journalLoading.value = false
  }
}

const SOURCE_LABEL: Record<string, string> = {
  beach:      '🏖️ شاطئ',
  dining:     '🍽️ مطاعم',
  folio:      '🛎️ فوليو',
  payroll:    '💳 رواتب',
  inventory:  '📦 مخزون',
  depreciation: '📉 إهلاك',
  manual:     '✍️ يدوي',
}
function journalSourceLabel(src: string | null): string {
  if (!src) return '—'
  return SOURCE_LABEL[src] ?? src
}
function journalStatusVariant(s: string): 'success' | 'warning' | 'neutral' {
  if (s === 'posted') return 'success'
  if (s === 'draft')  return 'warning'
  return 'neutral'
}
function toggleJournalEntry(id: number) {
  journalExpanded.value = journalExpanded.value === id ? null : id
}

// ── قيد يدوي جديد (2026-08-16) ──────────────────────────────────────────
// POST /finance/journal-entries كان جاهزًا بالكامل في الباك إند (يتحقق من
// توازن مدين=دائن وقفل الفترة المحاسبية) بس مفيش أي شاشة كانت تستخدمه —
// المحاسب معندوش أي طريقة يسجّل بيها تسوية/تصحيح/سند دين أو ائتمان يدوي.
interface NewJournalLine { accountId: number | null; debit: string; credit: string; description: string }
const allAccountOptions = computed(() => accounts.value)
const newJournalModal = reactive({
  open: false, saving: false, error: '',
  entryDate: today, reference: '', description: '',
  lines: [
    { accountId: null, debit: '', credit: '', description: '' },
    { accountId: null, debit: '', credit: '', description: '' },
  ] as NewJournalLine[],
})
function openNewJournalModal() {
  Object.assign(newJournalModal, {
    open: true, saving: false, error: '',
    entryDate: today, reference: '', description: '',
    lines: [
      { accountId: null, debit: '', credit: '', description: '' },
      { accountId: null, debit: '', credit: '', description: '' },
    ],
  })
}
function addJournalLine() {
  newJournalModal.lines.push({ accountId: null, debit: '', credit: '', description: '' })
}
function removeJournalLine(index: number) {
  if (newJournalModal.lines.length <= 2) return
  newJournalModal.lines.splice(index, 1)
}
const newJournalTotalDebit = computed(() =>
  newJournalModal.lines.reduce((sum, l) => sum + (Number(l.debit) || 0), 0))
const newJournalTotalCredit = computed(() =>
  newJournalModal.lines.reduce((sum, l) => sum + (Number(l.credit) || 0), 0))
const newJournalIsBalanced = computed(() =>
  Math.abs(newJournalTotalDebit.value - newJournalTotalCredit.value) < 0.01 && newJournalTotalDebit.value > 0)
async function confirmNewJournalEntry() {
  if (!newJournalModal.reference.trim() || !newJournalModal.description.trim()) {
    newJournalModal.error = t('backoffice.finance.journal.newEntry.validationError')
    return
  }
  if (newJournalModal.lines.some(l => !l.accountId || (!Number(l.debit) && !Number(l.credit)))) {
    newJournalModal.error = t('backoffice.finance.journal.newEntry.lineValidationError')
    return
  }
  if (!newJournalIsBalanced.value) {
    newJournalModal.error = t('backoffice.finance.journal.newEntry.unbalancedError')
    return
  }
  newJournalModal.saving = true
  newJournalModal.error = ''
  try {
    await api.post(ENDPOINTS.finance.journalEntries, {
      branch_id: branchId.value,
      entry_date: newJournalModal.entryDate,
      reference: newJournalModal.reference.trim(),
      description: newJournalModal.description.trim(),
      source: 'manual',
      lines: newJournalModal.lines.map(l => ({
        account_id: l.accountId,
        debit: Number(l.debit) || 0,
        credit: Number(l.credit) || 0,
        description: l.description.trim() || undefined,
      })),
    })
    toast.success(t('backoffice.finance.journal.newEntry.success'))
    newJournalModal.open = false
    journalPage.value = 1
    await loadJournal()
  } catch (e: unknown) {
    newJournalModal.error = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.journal.newEntry.error')
  } finally {
    newJournalModal.saving = false
  }
}

// ── مصروفات (2026-08-16) ────────────────────────────────────────────────
// سند مصروفات حقيقي بفئة (حساب 5xxx) — طلب Mohamed صراحةً بديل القيد
// اليدوي العام.
interface ExpenseRow {
  id: number; expense_date: string; amount: number; description: string
  reference: string | null; expense_account_code: string; expense_account_name: string
  settlement_account_code: string
  payment_status: 'paid' | 'unpaid' | 'partial'; amount_paid: number
  voided_at: string | null
}
const expenses = ref<ExpenseRow[]>([])
const expensesTotal = ref(0)
const expensesPage = ref(1)
const expensesDateFrom = ref(firstOfMonth)
const expensesDateTo = ref(today)
const expensesLoading = ref(false)
const expenseAccountOptions = computed(() => accounts.value.filter(a => a.account_type === 'expense'))
const settlementAccountOptions = computed(() => accounts.value.filter(a => a.account_type === 'asset'))

async function loadExpenses() {
  expensesLoading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.expenses, {
      params: {
        branch_id: branchId.value, date_from: expensesDateFrom.value, date_to: expensesDateTo.value,
        page: expensesPage.value, size: 30,
      },
    })
    expenses.value = (data.items ?? []).map((e: Record<string, unknown>) => ({
      ...e, amount: Number(e.amount), amount_paid: Number(e.amount_paid ?? 0),
    }))
    expensesTotal.value = data.total ?? 0
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.expenses.loadError'))
  } finally {
    expensesLoading.value = false
  }
}

const newExpenseModal = reactive({
  open: false, saving: false, error: '',
  expenseDate: today, expenseAccountId: null as number | null, settlementAccountId: null as number | null,
  amount: '', description: '', reference: '', deferPayment: false,
})
function openNewExpenseModal() {
  Object.assign(newExpenseModal, {
    open: true, saving: false, error: '',
    expenseDate: today, expenseAccountId: null, settlementAccountId: null,
    amount: '', description: '', reference: '', deferPayment: false,
  })
}
// موافقة PIN فوق حد المصروفات (2026-08-19، طلب Mohamed — راجع
// services.record_expense/policy_engine SensitiveAction("record_expense",
// min_approver_level=80)). الفرونت إند ماعندوش قيمة EXPENSE_APPROVAL_
// THRESHOLD خالص (Decimal إعداد سيرفر بس) — فبدل ما يكرر القيمة دي أو
// يخمّنها، بيبعت السند عادي، ولو السيرفر رفضه برسالة "محتاج موافقة مدير
// بالـ PIN" تحديدًا (مش أي 400 تاني) بيفتح PinGuardModal (min-level=80،
// نفس min_approver_level بالظبط) ويعيد المحاولة بـ approver_user_id/pin.
const EXPENSE_APPROVAL_MESSAGE_MARKER = 'موافقة مدير بالـ PIN'
const expensePinGuard = reactive({ open: false, busy: false, error: '' })

async function submitNewExpense(approver?: { approverUserId: number | null; approverPin: string | null }) {
  await api.post(ENDPOINTS.finance.expenses, {
    expense_date: newExpenseModal.expenseDate,
    expense_account_id: newExpenseModal.expenseAccountId,
    settlement_account_id: newExpenseModal.deferPayment ? undefined : newExpenseModal.settlementAccountId,
    amount: Number(newExpenseModal.amount),
    description: newExpenseModal.description.trim(),
    reference: newExpenseModal.reference.trim() || undefined,
    defer_payment: newExpenseModal.deferPayment,
    ...(approver?.approverUserId ? { approver_user_id: approver.approverUserId, approver_pin: approver.approverPin } : {}),
  }, { params: { branch_id: branchId.value } })
  toast.success(t('backoffice.finance.expenses.newExpense.success'))
  newExpenseModal.open = false
  expensesPage.value = 1
  await loadExpenses()
}

async function confirmNewExpense() {
  if (!newExpenseModal.expenseAccountId || (!newExpenseModal.deferPayment && !newExpenseModal.settlementAccountId)) {
    newExpenseModal.error = t('backoffice.finance.expenses.newExpense.accountsRequired')
    return
  }
  if (!Number(newExpenseModal.amount) || Number(newExpenseModal.amount) <= 0) {
    newExpenseModal.error = t('backoffice.finance.expenses.newExpense.amountRequired')
    return
  }
  if (!newExpenseModal.description.trim()) {
    newExpenseModal.error = t('backoffice.finance.expenses.newExpense.descriptionRequired')
    return
  }
  newExpenseModal.saving = true
  newExpenseModal.error = ''
  try {
    await submitNewExpense()
  } catch (e: unknown) {
    const detail = (e as ApiErr)?.response?.data?.detail
    if (typeof detail === 'string' && detail.includes(EXPENSE_APPROVAL_MESSAGE_MARKER)) {
      expensePinGuard.error = ''
      expensePinGuard.open = true
    } else {
      newExpenseModal.error = detail ?? t('backoffice.finance.expenses.newExpense.error')
    }
  } finally {
    newExpenseModal.saving = false
  }
}

async function onExpensePinApproved(payload: { approverUserId: number | null; approverPin: string | null }) {
  expensePinGuard.busy = true
  expensePinGuard.error = ''
  try {
    await submitNewExpense(payload)
    expensePinGuard.open = false
  } catch (e: unknown) {
    expensePinGuard.error = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.expenses.newExpense.error')
  } finally {
    expensePinGuard.busy = false
  }
}

// ── سداد سند مصروفات آجل (2026-08-19) ────────────────────────────────
const payExpenseModal = reactive({
  open: false, saving: false, error: '',
  expenseId: null as number | null, settlementAccountId: null as number | null,
  amount: '', paidAt: today,
})
function openPayExpenseModal(exp: ExpenseRow) {
  Object.assign(payExpenseModal, {
    open: true, saving: false, error: '',
    expenseId: exp.id, settlementAccountId: null,
    amount: String(exp.amount - exp.amount_paid), paidAt: today,
  })
}
async function confirmPayExpense() {
  if (!payExpenseModal.expenseId || !payExpenseModal.settlementAccountId) {
    payExpenseModal.error = t('backoffice.finance.expenses.pay.settlementAccountRequired')
    return
  }
  if (!Number(payExpenseModal.amount) || Number(payExpenseModal.amount) <= 0) {
    payExpenseModal.error = t('backoffice.finance.expenses.newExpense.amountRequired')
    return
  }
  payExpenseModal.saving = true
  payExpenseModal.error = ''
  try {
    await api.post(ENDPOINTS.finance.expensePay(payExpenseModal.expenseId), {
      amount: Number(payExpenseModal.amount),
      settlement_account_id: payExpenseModal.settlementAccountId,
      paid_at: payExpenseModal.paidAt,
    })
    toast.success(t('backoffice.finance.expenses.pay.success'))
    payExpenseModal.open = false
    await loadExpenses()
  } catch (e: unknown) {
    payExpenseModal.error = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.expenses.pay.error')
  } finally {
    payExpenseModal.saving = false
  }
}

// ── إلغاء سند مصروفات (step-up، 2026-08-19) ──────────────────────────
const pendingVoidExpenseId = ref<number | null>(null)
const voidExpenseStepUpError = ref('')
const voidExpenseStepUpBusy = ref(false)
function openVoidExpensePrompt(id: number) {
  pendingVoidExpenseId.value = id
  voidExpenseStepUpError.value = ''
}
function cancelVoidExpensePrompt() {
  pendingVoidExpenseId.value = null
  voidExpenseStepUpError.value = ''
}
async function onVoidExpenseStepUpConfirmed(payload: { stepUpToken: string; reason: string }) {
  if (pendingVoidExpenseId.value === null) return
  voidExpenseStepUpBusy.value = true
  try {
    await api.post(
      ENDPOINTS.finance.expenseVoid(pendingVoidExpenseId.value),
      { reason: payload.reason },
      { headers: { 'X-Step-Up-Token': payload.stepUpToken } },
    )
    toast.success(t('backoffice.finance.expenses.void.success'))
    cancelVoidExpensePrompt()
    await loadExpenses()
  } catch (e: unknown) {
    const code = (e as any)?.response?.data?.detail?.error_code
    voidExpenseStepUpError.value = code === 'STEP_UP_INVALID'
      ? t('backoffice.stepUp.errorGeneric')
      : (e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.expenses.void.error')
  } finally {
    voidExpenseStepUpBusy.value = false
  }
}

// ── العهدة (Custody) — 2026-08-19 ─────────────────────────────────────
interface CustodyRow {
  id: number; holder_name: string; purpose: string; amount: number
  disbursed_date: string; status: 'open' | 'settled'
  returned_amount: number; voided_at: string | null
}
const custodies = ref<CustodyRow[]>([])
const custodiesTotal = ref(0)
const custodiesPage = ref(1)
const custodiesLoading = ref(false)
const custodyAssetAccountOptions = computed(() => accounts.value.filter(a => a.account_type === 'asset'))

async function loadCustodies() {
  custodiesLoading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.custodies, {
      params: { branch_id: branchId.value, page: custodiesPage.value, size: 30 },
    })
    custodies.value = (data.items ?? []).map((c: Record<string, unknown>) => ({
      ...c, amount: Number(c.amount), returned_amount: Number(c.returned_amount ?? 0),
    }))
    custodiesTotal.value = data.total ?? 0
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.custodies.loadError'))
  } finally {
    custodiesLoading.value = false
  }
}

const newCustodyModal = reactive({
  open: false, saving: false, error: '',
  holderName: '', purpose: '', amount: '', disbursedDate: today, sourceAccountId: null as number | null,
})
function openNewCustodyModal() {
  Object.assign(newCustodyModal, {
    open: true, saving: false, error: '',
    holderName: '', purpose: '', amount: '', disbursedDate: today, sourceAccountId: null,
  })
}
async function confirmNewCustody() {
  if (!newCustodyModal.holderName.trim() || !newCustodyModal.purpose.trim()) {
    newCustodyModal.error = t('backoffice.finance.custodies.newCustody.fieldsRequired')
    return
  }
  if (!newCustodyModal.sourceAccountId) {
    newCustodyModal.error = t('backoffice.finance.custodies.newCustody.accountRequired')
    return
  }
  if (!Number(newCustodyModal.amount) || Number(newCustodyModal.amount) <= 0) {
    newCustodyModal.error = t('backoffice.finance.expenses.newExpense.amountRequired')
    return
  }
  newCustodyModal.saving = true
  newCustodyModal.error = ''
  try {
    await api.post(ENDPOINTS.finance.custodies, {
      holder_name: newCustodyModal.holderName.trim(),
      purpose: newCustodyModal.purpose.trim(),
      amount: Number(newCustodyModal.amount),
      disbursed_date: newCustodyModal.disbursedDate,
      source_account_id: newCustodyModal.sourceAccountId,
    }, { params: { branch_id: branchId.value } })
    toast.success(t('backoffice.finance.custodies.newCustody.success'))
    newCustodyModal.open = false
    custodiesPage.value = 1
    await loadCustodies()
  } catch (e: unknown) {
    newCustodyModal.error = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.custodies.newCustody.error')
  } finally {
    newCustodyModal.saving = false
  }
}

interface SettleLineForm { expenseAccountId: number | null; amount: string; description: string }
const settleCustodyModal = reactive({
  open: false, saving: false, error: '',
  custodyId: null as number | null, custodyAmount: 0, settlementDate: today,
  lines: [{ expenseAccountId: null, amount: '', description: '' }] as SettleLineForm[],
  returnedAmount: '0',
})
function openSettleCustodyModal(c: CustodyRow) {
  Object.assign(settleCustodyModal, {
    open: true, saving: false, error: '',
    custodyId: c.id, custodyAmount: c.amount, settlementDate: today,
    lines: [{ expenseAccountId: null, amount: '', description: '' }],
    returnedAmount: '0',
  })
}
function addSettleLine() {
  settleCustodyModal.lines.push({ expenseAccountId: null, amount: '', description: '' })
}
function removeSettleLine(idx: number) {
  settleCustodyModal.lines.splice(idx, 1)
}
const settleCustodyLinesTotal = computed(() =>
  settleCustodyModal.lines.reduce((sum, l) => sum + (Number(l.amount) || 0), 0)
  + (Number(settleCustodyModal.returnedAmount) || 0),
)
async function confirmSettleCustody() {
  if (!settleCustodyModal.custodyId) return
  if (Math.abs(settleCustodyLinesTotal.value - settleCustodyModal.custodyAmount) > 0.01) {
    settleCustodyModal.error = t('backoffice.finance.custodies.settle.mismatchError', {
      total: formatNumber(settleCustodyLinesTotal.value), amount: formatNumber(settleCustodyModal.custodyAmount),
    })
    return
  }
  if (settleCustodyModal.lines.some(l => !l.expenseAccountId || !Number(l.amount) || !l.description.trim())) {
    settleCustodyModal.error = t('backoffice.finance.custodies.settle.linesRequired')
    return
  }
  settleCustodyModal.saving = true
  settleCustodyModal.error = ''
  try {
    await api.post(ENDPOINTS.finance.custodySettle(settleCustodyModal.custodyId), {
      settlement_date: settleCustodyModal.settlementDate,
      lines: settleCustodyModal.lines.map(l => ({
        expense_account_id: l.expenseAccountId, amount: Number(l.amount), description: l.description.trim(),
      })),
      returned_amount: Number(settleCustodyModal.returnedAmount) || 0,
    })
    toast.success(t('backoffice.finance.custodies.settle.success'))
    settleCustodyModal.open = false
    await loadCustodies()
  } catch (e: unknown) {
    settleCustodyModal.error = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.custodies.settle.error')
  } finally {
    settleCustodyModal.saving = false
  }
}

const pendingVoidCustodyId = ref<number | null>(null)
const voidCustodyStepUpError = ref('')
const voidCustodyStepUpBusy = ref(false)
function openVoidCustodyPrompt(id: number) {
  pendingVoidCustodyId.value = id
  voidCustodyStepUpError.value = ''
}
function cancelVoidCustodyPrompt() {
  pendingVoidCustodyId.value = null
  voidCustodyStepUpError.value = ''
}
async function onVoidCustodyStepUpConfirmed(payload: { stepUpToken: string; reason: string }) {
  if (pendingVoidCustodyId.value === null) return
  voidCustodyStepUpBusy.value = true
  try {
    await api.post(
      ENDPOINTS.finance.custodyVoid(pendingVoidCustodyId.value),
      { reason: payload.reason },
      { headers: { 'X-Step-Up-Token': payload.stepUpToken } },
    )
    toast.success(t('backoffice.finance.custodies.void.success'))
    cancelVoidCustodyPrompt()
    await loadCustodies()
  } catch (e: unknown) {
    const code = (e as any)?.response?.data?.detail?.error_code
    voidCustodyStepUpError.value = code === 'STEP_UP_INVALID'
      ? t('backoffice.stepUp.errorGeneric')
      : (e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.custodies.void.error')
  } finally {
    voidCustodyStepUpBusy.value = false
  }
}

// ── إذن قبض عام (Cash Receipt) — 2026-08-19 ───────────────────────────
interface CashReceiptRow {
  id: number; receipt_date: string; amount: number; description: string
  reference: string | null
  destination_account_code: string; destination_account_name: string
  source_account_code: string
  voided_at: string | null
}
const cashReceipts = ref<CashReceiptRow[]>([])
const cashReceiptsTotal = ref(0)
const cashReceiptsPage = ref(1)
const cashReceiptsDateFrom = ref(firstOfMonth)
const cashReceiptsDateTo = ref(today)
const cashReceiptsLoading = ref(false)

async function loadCashReceipts() {
  cashReceiptsLoading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.cashReceipts, {
      params: {
        branch_id: branchId.value, date_from: cashReceiptsDateFrom.value, date_to: cashReceiptsDateTo.value,
        page: cashReceiptsPage.value, size: 30,
      },
    })
    cashReceipts.value = (data.items ?? []).map((r: Record<string, unknown>) => ({ ...r, amount: Number(r.amount) }))
    cashReceiptsTotal.value = data.total ?? 0
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.cashReceipts.loadError'))
  } finally {
    cashReceiptsLoading.value = false
  }
}

const newCashReceiptModal = reactive({
  open: false, saving: false, error: '',
  receiptDate: today, destinationAccountId: null as number | null, sourceAccountId: null as number | null,
  amount: '', description: '', reference: '',
})
function openNewCashReceiptModal() {
  Object.assign(newCashReceiptModal, {
    open: true, saving: false, error: '',
    receiptDate: today, destinationAccountId: null, sourceAccountId: null,
    amount: '', description: '', reference: '',
  })
}
async function confirmNewCashReceipt() {
  if (!newCashReceiptModal.destinationAccountId || !newCashReceiptModal.sourceAccountId) {
    newCashReceiptModal.error = t('backoffice.finance.cashReceipts.newReceipt.accountsRequired')
    return
  }
  if (!Number(newCashReceiptModal.amount) || Number(newCashReceiptModal.amount) <= 0) {
    newCashReceiptModal.error = t('backoffice.finance.expenses.newExpense.amountRequired')
    return
  }
  if (!newCashReceiptModal.description.trim()) {
    newCashReceiptModal.error = t('backoffice.finance.expenses.newExpense.descriptionRequired')
    return
  }
  newCashReceiptModal.saving = true
  newCashReceiptModal.error = ''
  try {
    await api.post(ENDPOINTS.finance.cashReceipts, {
      receipt_date: newCashReceiptModal.receiptDate,
      destination_account_id: newCashReceiptModal.destinationAccountId,
      source_account_id: newCashReceiptModal.sourceAccountId,
      amount: Number(newCashReceiptModal.amount),
      description: newCashReceiptModal.description.trim(),
      reference: newCashReceiptModal.reference.trim() || undefined,
    }, { params: { branch_id: branchId.value } })
    toast.success(t('backoffice.finance.cashReceipts.newReceipt.success'))
    newCashReceiptModal.open = false
    cashReceiptsPage.value = 1
    await loadCashReceipts()
  } catch (e: unknown) {
    newCashReceiptModal.error = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.cashReceipts.newReceipt.error')
  } finally {
    newCashReceiptModal.saving = false
  }
}

const pendingVoidCashReceiptId = ref<number | null>(null)
const voidCashReceiptStepUpError = ref('')
const voidCashReceiptStepUpBusy = ref(false)
function openVoidCashReceiptPrompt(id: number) {
  pendingVoidCashReceiptId.value = id
  voidCashReceiptStepUpError.value = ''
}
function cancelVoidCashReceiptPrompt() {
  pendingVoidCashReceiptId.value = null
  voidCashReceiptStepUpError.value = ''
}
async function onVoidCashReceiptStepUpConfirmed(payload: { stepUpToken: string; reason: string }) {
  if (pendingVoidCashReceiptId.value === null) return
  voidCashReceiptStepUpBusy.value = true
  try {
    await api.post(
      ENDPOINTS.finance.cashReceiptVoid(pendingVoidCashReceiptId.value),
      { reason: payload.reason },
      { headers: { 'X-Step-Up-Token': payload.stepUpToken } },
    )
    toast.success(t('backoffice.finance.cashReceipts.void.success'))
    cancelVoidCashReceiptPrompt()
    await loadCashReceipts()
  } catch (e: unknown) {
    const code = (e as any)?.response?.data?.detail?.error_code
    voidCashReceiptStepUpError.value = code === 'STEP_UP_INVALID'
      ? t('backoffice.stepUp.errorGeneric')
      : (e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.cashReceipts.void.error')
  } finally {
    voidCashReceiptStepUpBusy.value = false
  }
}

onMounted(() => loadTab('overview'))

// تنظيم شاشة المالية (2026-08-19، طلب Mohamed — "متنظمة ومتهيأة للمحاسب
// يقدر يشتغل ببرنامج محاسبي حقيقي") — قايمة مسطّحة من 17 تبويب بقت 4
// مجموعات منطقية زي أي برنامج محاسبة حقيقي: التشغيل اليومي (فيها الورديات
// اللي المحاسب بيراقب بيها الكاشير)، الحسابات والقيود، التقارير المالية،
// الإعدادات المتقدمة.
const tabGroups = computed<{ label: string; tabs: { val: typeof tab.value; label: string }[] }[]>(() => [
  {
    label: t('backoffice.finance.groups.daily'),
    tabs: [
      { val: 'overview',         label: t('backoffice.finance.tabs.overview') },
      { val: 'shifts',           label: t('backoffice.finance.tabs.shifts') },
      { val: 'expenses',         label: t('backoffice.finance.tabs.expenses') },
      { val: 'custodies',        label: t('backoffice.finance.tabs.custodies') },
      { val: 'cash-receipts',    label: t('backoffice.finance.tabs.cashReceipts') },
      { val: 'payment-channels', label: t('backoffice.finance.tabs.paymentChannels') },
    ],
  },
  {
    label: t('backoffice.finance.groups.ledger'),
    tabs: [
      { val: 'accounts',      label: t('backoffice.finance.tabs.accounts') },
      { val: 'journal',       label: t('backoffice.finance.tabs.journal') },
      { val: 'cost-centers',  label: t('backoffice.finance.tabs.costCenters') },
      { val: 'checks',        label: t('backoffice.finance.tabs.checks') },
    ],
  },
  {
    label: t('backoffice.finance.groups.reports'),
    tabs: [
      { val: 'trial-balance',    label: t('backoffice.finance.tabs.trialBalance') },
      { val: 'income-statement', label: t('backoffice.finance.tabs.incomeStatement') },
      { val: 'balance-sheet',    label: t('backoffice.finance.tabs.balanceSheet') },
      { val: 'aging',            label: t('backoffice.finance.tabs.aging') },
    ],
  },
  {
    label: t('backoffice.finance.groups.advanced'),
    tabs: [
      { val: 'periods',             label: t('backoffice.finance.tabs.periods') },
      { val: 'exchange-rates',      label: t('backoffice.finance.tabs.exchangeRates') },
      { val: 'depreciation',        label: t('backoffice.finance.tabs.depreciation') },
      { val: 'bank-reconciliation', label: t('backoffice.finance.tabs.bankReconciliation') },
    ],
  },
])

const shiftStatusList = computed<{ v: 'all' | 'open' | 'closed'; l: string }[]>(() => [
  { v: 'all',    l: t('backoffice.finance.all') },
  { v: 'open',   l: t('backoffice.finance.shiftOpen') },
  { v: 'closed', l: t('backoffice.finance.shiftClosed') },
])

// ── POS-03: أسعار الصرف ───────────────────────────────────────────────
interface ExchangeRateItem {
  id: number
  from_currency: string
  to_currency: string
  rate: string
  effective_date: string
}

const exchangeRates = ref<ExchangeRateItem[]>([])
const fxLoading = ref(false)
const fxError = ref('')
const fxNewFrom = ref('USD')
const fxNewTo = ref('EGP')
const fxNewRate = ref('')
const fxNewDate = ref(new Date().toISOString().slice(0, 10))
const fxSaving = ref(false)

const SUPPORTED_CURRENCIES = ['USD', 'EUR', 'SAR', 'GBP', 'EGP']

async function loadExchangeRates() {
  fxLoading.value = true
  fxError.value = ''
  try {
    // GET /finance/exchange-rates لا يقبل branch_id (أسعار الصرف عالمية مش
    // مربوطة بفرع) ولا limit (بس size، حد أقصى 200) — كانا بيتجاهَلوا بصمت
    // وبيرجّع الـdefault الحالي (page=1/size=50) دايمًا، اللي طابق الغرض هنا
    // بالصدفة بس لسه drift حقيقي عن الـcontract (OPS-DATA-02 §6.3).
    const { data } = await api.get('/finance/exchange-rates', {
      params: { page: 1, size: 100 },
    })
    exchangeRates.value = data.items ?? data ?? []
  } catch {
    fxError.value = t('backoffice.finance.fx.loadError')
  } finally {
    fxLoading.value = false
  }
}

async function saveExchangeRate() {
  if (!fxNewRate.value || !fxNewDate.value) return
  fxSaving.value = true
  try {
    await api.post('/finance/exchange-rates', {
      from_currency: fxNewFrom.value,
      to_currency:   fxNewTo.value,
      rate:          fxNewRate.value,
      effective_date: fxNewDate.value,
    })
    toast.success(t('backoffice.finance.fx.saved'))
    fxNewRate.value = ''
    fxNewDate.value = new Date().toISOString().slice(0, 10)
    await loadExchangeRates()
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.fx.saveError'))
  } finally {
    fxSaving.value = false
  }
}
</script>

<template>
  <div>
    <h2 class="text-2xl font-black text-gray-900 dark:text-gray-100 mb-6">{{ t('backoffice.finance.title') }}</h2>

    <!-- مجموعات رئيسية (2026-08-19) — بديل صف الـ17 تبويب القديم المتناثر،
         نفس أسلوب أي برنامج محاسبة حقيقي (تشغيل يومي / حسابات / تقارير /
         إعدادات متقدمة). -->
    <div class="flex gap-1 bg-stone-50 dark:bg-gray-800/40 p-1 rounded-xl mb-2 w-fit flex-wrap border border-stone-200 dark:border-border/50">
      <button v-for="(group, idx) in tabGroups" :key="group.label"
        @click="activeGroupIdx = idx"
        :class="['px-3 py-1.5 rounded-lg text-xs font-bold transition-all', activeGroupIdx === idx ? 'bg-primary-700 text-white shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:text-gray-300']"
      >{{ group.label }}</button>
    </div>

    <div class="flex gap-1 bg-stone-100 dark:bg-gray-700 p-1 rounded-xl mb-6 w-fit flex-wrap">
      <button v-for="tabDef in tabGroups[activeGroupIdx].tabs"
        :key="tabDef.val" @click="loadTab(tabDef.val)"
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
          <table class="w-full min-w-[760px]">
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
          <table class="w-full min-w-[600px]">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.code') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.accountName') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.type') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.balance') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="acc in accounts" :key="acc.id" class="cursor-pointer border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:hover:bg-gray-800/60" @click="openAccountLedger(acc)">
                <td class="px-4 py-3 font-mono text-sm text-gray-600 dark:text-gray-400">{{ acc.code }}</td>
                <td class="px-4 py-3 text-sm font-medium text-primary-700 dark:text-primary-300 underline decoration-dotted">{{ acc.name }}</td>
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
            <table class="w-full min-w-[600px]">
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
        <div class="flex gap-2 ms-auto">
          <AppButton size="sm" variant="outline" :loading="bsDownloading === 'pdf'" @click="downloadBalanceSheet('pdf')">📄 PDF</AppButton>
          <AppButton size="sm" variant="outline" :loading="bsDownloading === 'excel'" @click="downloadBalanceSheet('excel')">📊 Excel</AppButton>
        </div>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <template v-else-if="bsData">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
          <AppCard padding="none">
            <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.assets') }}</div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[380px]">
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
                <table class="w-full min-w-[380px]">
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
                <table class="w-full min-w-[380px]">
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

    <!-- Trial Balance -->
    <div v-if="tab === 'trial-balance'">
      <div class="flex flex-wrap items-end gap-3 mb-4">
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.asOfDate') }}</label>
          <input v-model="tbAsOf" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
        </div>
        <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300 pb-1.5">
          <input v-model="tbGroupByParent" type="checkbox" class="rounded" />
          {{ t('backoffice.finance.trialBalance.groupByParent') }}
        </label>
        <AppButton size="sm" @click="loadTrialBalance">{{ t('backoffice.finance.apply') }}</AppButton>
        <AppBadge v-if="tbData" size="sm" :variant="tbData.is_balanced ? 'success' : 'danger'">
          {{ tbData.is_balanced ? `✅ ${t('backoffice.finance.balanced')}` : `⚠️ ${t('backoffice.finance.notBalanced')}` }}
        </AppBadge>
        <div class="flex gap-2 ms-auto">
          <AppButton size="sm" variant="outline" :loading="tbDownloading === 'pdf'" @click="downloadTrialBalance('pdf')">📄 PDF</AppButton>
          <AppButton size="sm" variant="outline" :loading="tbDownloading === 'excel'" @click="downloadTrialBalance('excel')">📊 Excel</AppButton>
        </div>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else-if="tbData" padding="none">
        <div class="overflow-x-auto">
          <table class="w-full min-w-[600px]">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.code') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.accountName') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.type') }}</th>
                <th class="px-4 py-3 text-end text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.ledger.debit') }}</th>
                <th class="px-4 py-3 text-end text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.ledger.credit') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="l in tbData.lines" :key="l.account_code" class="border-t border-stone-100 dark:border-border/50">
                <td class="px-4 py-3 font-mono text-sm text-gray-600 dark:text-gray-400">{{ l.account_code }}</td>
                <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">{{ l.account_name }}</td>
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ l.account_type }}</td>
                <td class="px-4 py-3 text-sm text-end font-semibold text-green-600 dark:text-green-300">{{ l.debit ? formatNumber(l.debit) : '—' }}</td>
                <td class="px-4 py-3 text-sm text-end font-semibold text-red-600 dark:text-red-300">{{ l.credit ? formatNumber(l.credit) : '—' }}</td>
              </tr>
              <tr v-if="tbData.lines.length === 0">
                <td colspan="5" class="px-4 py-8"><EmptyState icon="📒" :title="t('backoffice.finance.noAccounts')" /></td>
              </tr>
            </tbody>
            <tfoot v-if="tbData.lines.length">
              <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                <td colspan="3" class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.total') }}</td>
                <td class="px-4 py-3 text-sm text-end font-black text-green-700 dark:text-green-300">{{ formatNumber(tbData.total_debit) }}</td>
                <td class="px-4 py-3 text-sm text-end font-black text-red-700 dark:text-red-300">{{ formatNumber(tbData.total_credit) }}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </AppCard>
      <AppCard v-else padding="lg">
        <EmptyState icon="⚖️" :title="t('backoffice.finance.noBalanceSheetData')" />
      </AppCard>
    </div>

    <!-- Income Statement -->
    <div v-if="tab === 'income-statement'">
      <div class="flex flex-wrap items-end gap-3 mb-4">
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.fromDate') }}</label>
          <input v-model="isDateFrom" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
        </div>
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.toDate') }}</label>
          <input v-model="isDateTo" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
        </div>
        <AppButton size="sm" @click="loadIncomeStatementReport">{{ t('backoffice.finance.apply') }}</AppButton>
        <div class="flex gap-2 ms-auto">
          <AppButton size="sm" variant="outline" :loading="isDownloading === 'pdf'" @click="downloadIncomeStatement('pdf')">📄 PDF</AppButton>
          <AppButton size="sm" variant="outline" :loading="isDownloading === 'excel'" @click="downloadIncomeStatement('excel')">📊 Excel</AppButton>
        </div>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <template v-else-if="isData">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
          <AppCard padding="none">
            <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.revenue') }}</div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[320px]">
                <tbody>
                  <tr v-for="l in isData.revenue_lines" :key="l.account_code" class="border-t border-stone-100 dark:border-border/50">
                    <td class="px-4 py-2 text-xs font-mono text-gray-500 dark:text-gray-400">{{ l.account_code }}</td>
                    <td class="px-4 py-2 text-sm text-gray-900 dark:text-gray-100">{{ l.account_name }}</td>
                    <td class="px-4 py-2 text-sm font-bold text-green-700 dark:text-green-300">{{ formatNumber(l.amount) }} {{ t('backoffice.finance.egp') }}</td>
                  </tr>
                  <tr v-if="isData.revenue_lines.length === 0">
                    <td colspan="3" class="px-4 py-6"><EmptyState icon="💰" :title="t('backoffice.finance.noDataThisPeriod')" /></td>
                  </tr>
                </tbody>
                <tfoot v-if="isData.revenue_lines.length">
                  <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                    <td colspan="2" class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.totalRevenue') }}</td>
                    <td class="px-4 py-3 text-sm font-black text-green-700 dark:text-green-300">{{ formatNumber(isData.total_revenue) }} {{ t('backoffice.finance.egp') }}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </AppCard>

          <AppCard padding="none">
            <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.expense') }}</div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[320px]">
                <tbody>
                  <tr v-for="l in isData.expense_lines" :key="l.account_code" class="border-t border-stone-100 dark:border-border/50">
                    <td class="px-4 py-2 text-xs font-mono text-gray-500 dark:text-gray-400">{{ l.account_code }}</td>
                    <td class="px-4 py-2 text-sm text-gray-900 dark:text-gray-100">{{ l.account_name }}</td>
                    <td class="px-4 py-2 text-sm font-bold text-red-700 dark:text-red-300">{{ formatNumber(l.amount) }} {{ t('backoffice.finance.egp') }}</td>
                  </tr>
                  <tr v-if="isData.expense_lines.length === 0">
                    <td colspan="3" class="px-4 py-6"><EmptyState icon="🧾" :title="t('backoffice.finance.noDataThisPeriod')" /></td>
                  </tr>
                </tbody>
                <tfoot v-if="isData.expense_lines.length">
                  <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                    <td colspan="2" class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.totalExpense') }}</td>
                    <td class="px-4 py-3 text-sm font-black text-red-700 dark:text-red-300">{{ formatNumber(isData.total_expense) }} {{ t('backoffice.finance.egp') }}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </AppCard>
        </div>
        <AppCard padding="md">
          <div class="flex items-center justify-between">
            <span class="font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.netIncome') }}</span>
            <span class="text-lg font-black" :class="isData.net_income >= 0 ? 'text-green-700 dark:text-green-300' : 'text-red-600 dark:text-red-300'">
              {{ formatNumber(isData.net_income) }} {{ t('backoffice.finance.egp') }}
            </span>
          </div>
        </AppCard>
      </template>
      <AppCard v-else padding="lg">
        <EmptyState icon="📉" :title="t('backoffice.finance.noDataThisPeriod')" />
      </AppCard>
    </div>

    <!-- Aging Report -->
    <div v-if="tab === 'aging'">
      <div class="flex flex-wrap items-end gap-3 mb-4">
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.asOfDate') }}</label>
          <input v-model="agingAsOf" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
        </div>
        <AppButton size="sm" @click="loadAging">{{ t('backoffice.finance.apply') }}</AppButton>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <template v-else-if="agingData">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <AppCard padding="none">
            <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 flex items-center justify-between">
              <span class="font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.aging.receivables') }}</span>
              <span class="text-sm font-bold text-green-700 dark:text-green-300">{{ formatNumber(agingData.receivables_total) }} {{ t('backoffice.finance.egp') }}</span>
            </div>
            <div class="flex flex-wrap gap-2 px-4 py-2 border-b border-stone-100 dark:border-border/50">
              <AppBadge v-for="b in agingData.receivables_buckets" :key="b.label" size="sm" :variant="agingBucketVariant(b.label)">
                {{ b.label }} — {{ b.count }} ({{ formatNumber(b.amount) }})
              </AppBadge>
            </div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[420px]">
                <thead class="bg-stone-50 dark:bg-gray-800/60">
                  <tr>
                    <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.aging.guest') }}</th>
                    <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.aging.days') }}</th>
                    <th class="px-3 py-2 text-end text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.aging.balance') }}</th>
                    <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.aging.bucket') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="l in agingData.receivables" :key="l.folio_id" class="border-t border-stone-100 dark:border-border/50">
                    <td class="px-3 py-2 text-sm text-gray-900 dark:text-gray-100">{{ l.guest_name }}</td>
                    <td class="px-3 py-2 text-sm text-gray-600 dark:text-gray-400">{{ l.days_outstanding }}</td>
                    <td class="px-3 py-2 text-sm text-end font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(l.balance_due) }}</td>
                    <td class="px-3 py-2"><AppBadge size="sm" :variant="agingBucketVariant(l.bucket)">{{ l.bucket }}</AppBadge></td>
                  </tr>
                  <tr v-if="agingData.receivables.length === 0">
                    <td colspan="4" class="px-4 py-6"><EmptyState icon="🧾" :title="t('backoffice.finance.aging.noReceivables')" /></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </AppCard>

          <AppCard padding="none">
            <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 flex items-center justify-between">
              <span class="font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.aging.payables') }}</span>
              <span class="text-sm font-bold text-red-700 dark:text-red-300">{{ formatNumber(agingData.payables_total) }} {{ t('backoffice.finance.egp') }}</span>
            </div>
            <div class="flex flex-wrap gap-2 px-4 py-2 border-b border-stone-100 dark:border-border/50">
              <AppBadge v-for="b in agingData.payables_buckets" :key="b.label" size="sm" :variant="agingBucketVariant(b.label)">
                {{ b.label }} — {{ b.count }} ({{ formatNumber(b.amount) }})
              </AppBadge>
            </div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[420px]">
                <thead class="bg-stone-50 dark:bg-gray-800/60">
                  <tr>
                    <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.aging.counterparty') }}</th>
                    <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.aging.days') }}</th>
                    <th class="px-3 py-2 text-end text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.aging.remaining') }}</th>
                    <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.aging.bucket') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="l in agingData.payables" :key="`${l.source_type}-${l.source_id}`" class="border-t border-stone-100 dark:border-border/50">
                    <td class="px-3 py-2 text-sm text-gray-900 dark:text-gray-100">{{ l.counterparty }}</td>
                    <td class="px-3 py-2 text-sm text-gray-600 dark:text-gray-400">{{ l.days_outstanding }}</td>
                    <td class="px-3 py-2 text-sm text-end font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(l.remaining) }}</td>
                    <td class="px-3 py-2"><AppBadge size="sm" :variant="agingBucketVariant(l.bucket)">{{ l.bucket }}</AppBadge></td>
                  </tr>
                  <tr v-if="agingData.payables.length === 0">
                    <td colspan="4" class="px-4 py-6"><EmptyState icon="📦" :title="t('backoffice.finance.aging.noPayables')" /></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </AppCard>
        </div>
      </template>
      <AppCard v-else padding="lg">
        <EmptyState icon="⏳" :title="t('backoffice.finance.noDataThisPeriod')" />
      </AppCard>
    </div>

    <!-- Periods (إقفال شهري + سنوي) -->
    <div v-if="tab === 'periods'">
      <div class="flex flex-wrap items-end gap-3 mb-4">
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.year') }}</label>
          <input v-model.number="periodsYear" type="number" min="2020" max="2100"
            class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm w-28" />
        </div>
        <AppButton size="sm" @click="loadPeriods">{{ t('backoffice.finance.apply') }}</AppButton>
        <AppButton
          v-if="auth.hasRole('admin')"
          size="sm" variant="danger" class="ms-auto"
          :disabled="!allMonthsClosed" :loading="closingYear"
          @click="closeYear"
        >🔒 {{ t('backoffice.finance.periods.closeYear') }}</AppButton>
      </div>

      <p v-if="auth.hasRole('admin') && !allMonthsClosed" class="text-xs text-amber-600 dark:text-amber-400 mb-3">
        {{ t('backoffice.finance.periods.closeYearHint') }}
      </p>

      <AppCard v-if="yearCloseResult" padding="md" class="mb-4 border-2 border-green-500/40">
        <div class="flex items-center gap-2 text-green-700 dark:text-green-300 font-bold mb-1">✅ {{ t('backoffice.finance.periods.closeYearSuccess') }}</div>
        <div class="text-sm text-gray-600 dark:text-gray-300">
          {{ t('backoffice.finance.periods.yearClosedNetIncome') }}: <strong>{{ formatNumber(yearCloseResult.net_income) }} {{ t('backoffice.finance.egp') }}</strong>
          — {{ t('backoffice.finance.ledger.reference') }} #{{ yearCloseResult.journal_entry_id }}
        </div>
      </AppCard>

      <div v-if="periodsLoading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <div v-else class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        <AppCard v-for="m in periodsGrid" :key="m.month" padding="md">
          <div class="flex items-center justify-between mb-2">
            <span class="font-bold text-gray-900 dark:text-gray-100">{{ monthNames[m.month - 1] }}</span>
            <AppBadge size="sm" :variant="m.status === 'open' ? 'warning' : 'success'">
              {{ m.status === 'open' ? t('backoffice.finance.periods.open') : t('backoffice.finance.periods.closed') }}
            </AppBadge>
          </div>
          <AppButton
            v-if="m.status === 'open'"
            size="sm" variant="outline" class="w-full"
            :loading="closingMonthKey === m.month"
            @click="closeMonth(m.month)"
          >{{ t('backoffice.finance.periods.closeMonth') }}</AppButton>
          <p v-else class="text-xs text-gray-400 dark:text-gray-400">{{ fmtDateFn(m.closedAt ?? '') }}</p>
        </AppCard>
      </div>
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
          <table class="w-full min-w-[600px]">
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
            <table class="w-full min-w-[600px]">
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

    <!-- POS-03: شاشة إدارة أسعار الصرف — manager+ فقط -->
    <div v-if="tab === 'exchange-rates'" class="space-y-6">
      <AppCard>
        <h3 class="text-lg font-black text-gray-900 dark:text-gray-100 mb-4">{{ t('backoffice.finance.fx.addTitle') }}</h3>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 items-end">
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.finance.fx.fromCurrency') }}</label>
            <select v-model="fxNewFrom" class="w-full rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm">
              <option v-for="cur in SUPPORTED_CURRENCIES.filter(c => c !== 'EGP')" :key="cur" :value="cur">{{ cur }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.finance.fx.toCurrency') }}</label>
            <select v-model="fxNewTo" class="w-full rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm">
              <option value="EGP">EGP</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.finance.fx.rate') }} (1 {{ fxNewFrom }} = ? EGP)</label>
            <input v-model="fxNewRate" type="number" step="0.01" min="0.01"
              class="w-full rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm font-bold tabular-nums"
              :placeholder="fxNewFrom === 'USD' ? '48.00' : fxNewFrom === 'EUR' ? '52.00' : '0.00'" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.finance.fx.effectiveDate') }}</label>
            <input v-model="fxNewDate" type="date"
              class="w-full rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm" />
          </div>
        </div>
        <div class="mt-4 flex gap-2 items-center">
          <AppButton variant="primary" :loading="fxSaving" :disabled="!fxNewRate || !fxNewDate" @click="saveExchangeRate">
            {{ t('backoffice.finance.fx.save') }}
          </AppButton>
          <p class="text-xs text-gray-500 dark:text-gray-400">{{ t('backoffice.finance.fx.hint') }}</p>
        </div>
      </AppCard>

      <AppCard>
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.fx.historyTitle') }}</h3>
          <AppButton variant="ghost" size="sm" :loading="fxLoading" @click="loadExchangeRates">{{ t('backoffice.finance.refresh') }}</AppButton>
        </div>
        <p v-if="fxError" role="alert" class="text-sm text-danger">{{ fxError }}</p>
        <EmptyState v-else-if="!fxLoading && exchangeRates.length === 0" icon="💱" :title="t('backoffice.finance.fx.empty')" />
        <div v-else class="overflow-x-auto">
          <table class="w-full min-w-[600px] text-sm">
            <thead>
              <tr class="text-start text-gray-500 dark:text-gray-400 border-b border-stone-200 dark:border-border">
                <th class="pb-2 font-semibold text-start">{{ t('backoffice.finance.fx.fromCurrency') }}</th>
                <th class="pb-2 font-semibold text-start">{{ t('backoffice.finance.fx.toCurrency') }}</th>
                <th class="pb-2 font-semibold text-end">{{ t('backoffice.finance.fx.rate') }}</th>
                <th class="pb-2 font-semibold text-start">{{ t('backoffice.finance.fx.effectiveDate') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in exchangeRates" :key="r.id" class="border-b border-stone-100 dark:border-border last:border-0">
                <td class="py-2 font-bold">{{ r.from_currency }}</td>
                <td class="py-2">{{ r.to_currency }}</td>
                <td class="py-2 text-end tabular-nums font-bold">{{ Number(r.rate).toFixed(4) }}</td>
                <td class="py-2 text-gray-500 dark:text-gray-400">{{ r.effective_date }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- دفتر اليومية -->
    <div v-if="tab === 'journal'" class="space-y-4">
      <!-- فلاتر -->
      <AppCard padding="md">
        <div class="flex flex-wrap gap-3 items-end">
          <div>
            <label class="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.finance.dateFrom') }}</label>
            <input v-model="journalDateFrom" type="date"
              class="rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.finance.dateTo') }}</label>
            <input v-model="journalDateTo" type="date"
              class="rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.finance.journal.source') }}</label>
            <select v-model="journalSource"
              class="rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm">
              <option value="">{{ t('backoffice.finance.all') }}</option>
              <option v-for="(label, src) in SOURCE_LABEL" :key="src" :value="src">{{ label }}</option>
            </select>
          </div>
          <AppButton variant="primary" :loading="journalLoading" @click="() => { journalPage = 1; loadJournal() }">
            {{ t('backoffice.finance.refresh') }}
          </AppButton>
          <AppButton variant="outline" class="ms-auto" @click="openNewJournalModal">
            ✍️ {{ t('backoffice.finance.journal.newEntry.btnLabel') }}
          </AppButton>
        </div>
      </AppCard>

      <!-- جدول القيود -->
      <AppCard padding="none">
        <div v-if="journalLoading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
        <EmptyState v-else-if="!journalEntries.length" icon="📒"
          :title="t('backoffice.finance.journal.empty')"
          :description="t('backoffice.finance.journal.emptyHint')" />
        <div v-else>
          <div class="px-4 py-2 border-b border-stone-100 dark:border-border/50 text-xs text-gray-500 dark:text-gray-400">
            {{ t('backoffice.finance.journal.totalEntries', { count: journalTotal }) }}
          </div>
          <div v-for="entry in journalEntries" :key="entry.id"
            class="border-b border-stone-100 dark:border-border/50 last:border-0">
            <!-- رأس القيد — قابل للطي -->
            <button
              class="w-full flex items-center gap-3 px-4 py-3 text-start hover:bg-stone-50 dark:hover:bg-gray-800/40 transition-colors"
              @click="toggleJournalEntry(entry.id)">
              <span class="text-gray-400 text-xs w-4 flex-shrink-0">{{ journalExpanded === entry.id ? '▼' : '▶' }}</span>
              <span class="text-xs text-gray-400 w-24 flex-shrink-0 tabular-nums">{{ entry.entry_date }}</span>
              <span class="font-mono text-xs text-gray-500 dark:text-gray-400 w-28 flex-shrink-0">{{ entry.reference }}</span>
              <span class="flex-1 text-sm text-gray-800 dark:text-gray-200 truncate">{{ entry.description }}</span>
              <span class="text-xs px-2">{{ journalSourceLabel(entry.source) }}</span>
              <AppBadge :variant="journalStatusVariant(entry.status)" size="sm">
                {{ entry.status === 'posted' ? t('backoffice.finance.journal.posted') : t('backoffice.finance.journal.draft') }}
              </AppBadge>
            </button>
            <!-- سطور القيد -->
            <div v-if="journalExpanded === entry.id" class="bg-stone-50 dark:bg-gray-800/30 border-t border-stone-100 dark:border-border/30">
              <table class="w-full text-xs">
                <thead>
                  <tr class="text-gray-500 dark:text-gray-400">
                    <th class="px-6 py-2 text-start font-semibold">{{ t('backoffice.finance.journal.account') }}</th>
                    <th class="px-4 py-2 text-start font-semibold">{{ t('backoffice.finance.journal.description') }}</th>
                    <th class="px-4 py-2 text-end font-semibold">{{ t('backoffice.finance.journal.debit') }}</th>
                    <th class="px-4 py-2 text-end font-semibold">{{ t('backoffice.finance.journal.credit') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="line in entry.lines" :key="line.account_id"
                    class="border-t border-stone-100 dark:border-border/20">
                    <td class="px-6 py-1.5 font-mono">
                      <span class="text-gray-500 dark:text-gray-400">{{ line.account_code }}</span>
                      <span class="mx-1 text-gray-300">|</span>
                      <span class="text-gray-800 dark:text-gray-200">{{ line.account_name }}</span>
                    </td>
                    <td class="px-4 py-1.5 text-gray-500 dark:text-gray-400">{{ line.description ?? '—' }}</td>
                    <td class="px-4 py-1.5 text-end tabular-nums" :class="line.debit > 0 ? 'font-bold text-gray-900 dark:text-gray-100' : 'text-gray-300 dark:text-gray-600'">
                      {{ line.debit > 0 ? formatNumber(line.debit) : '—' }}
                    </td>
                    <td class="px-4 py-1.5 text-end tabular-nums" :class="line.credit > 0 ? 'font-bold text-gray-900 dark:text-gray-100' : 'text-gray-300 dark:text-gray-600'">
                      {{ line.credit > 0 ? formatNumber(line.credit) : '—' }}
                    </td>
                  </tr>
                  <!-- إجمالي القيد -->
                  <tr class="border-t-2 border-stone-200 dark:border-border/50 bg-white dark:bg-gray-800/20 font-bold">
                    <td colspan="2" class="px-6 py-1.5 text-gray-500 dark:text-gray-400">{{ t('backoffice.finance.journal.total') }}</td>
                    <td class="px-4 py-1.5 text-end tabular-nums text-gray-900 dark:text-gray-100">
                      {{ formatNumber(entry.lines.reduce((s, l) => s + l.debit, 0)) }}
                    </td>
                    <td class="px-4 py-1.5 text-end tabular-nums text-gray-900 dark:text-gray-100">
                      {{ formatNumber(entry.lines.reduce((s, l) => s + l.credit, 0)) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <!-- Pagination -->
          <div v-if="journalTotal > 30" class="flex items-center justify-between px-4 py-3 border-t border-stone-100 dark:border-border/50">
            <span class="text-xs text-gray-500 dark:text-gray-400">
              {{ t('backoffice.finance.journal.page', { page: journalPage, total: Math.ceil(journalTotal / 30) }) }}
            </span>
            <div class="flex gap-2">
              <AppButton variant="outline" size="sm" :disabled="journalPage <= 1"
                @click="() => { journalPage--; loadJournal() }">{{ t('backoffice.finance.prev') }}</AppButton>
              <AppButton variant="outline" size="sm" :disabled="journalPage * 30 >= journalTotal"
                @click="() => { journalPage++; loadJournal() }">{{ t('backoffice.finance.next') }}</AppButton>
            </div>
          </div>
        </div>
      </AppCard>
    </div>

    <!-- ══ NEW MANUAL JOURNAL ENTRY MODAL ══ -->
    <AppModal :open="newJournalModal.open" :title="`✍️ ${t('backoffice.finance.journal.newEntry.title')}`"
      size="lg" @close="newJournalModal.open = false">
      <div class="space-y-4">
        <div class="grid grid-cols-2 gap-3">
          <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.journal.newEntry.entryDate') }}
            <input v-model="newJournalModal.entryDate" type="date"
              class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
          </label>
          <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.journal.newEntry.reference') }}
            <input v-model="newJournalModal.reference"
              :placeholder="t('backoffice.finance.journal.newEntry.referencePlaceholder')"
              class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
          </label>
        </div>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.journal.newEntry.description') }}
          <input v-model="newJournalModal.description"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>

        <div class="space-y-2">
          <div class="grid grid-cols-12 gap-2 text-xs font-semibold text-gray-500 dark:text-gray-400 px-1">
            <span class="col-span-5">{{ t('backoffice.finance.journal.account') }}</span>
            <span class="col-span-3">{{ t('backoffice.finance.journal.debit') }}</span>
            <span class="col-span-3">{{ t('backoffice.finance.journal.credit') }}</span>
          </div>
          <div v-for="(line, i) in newJournalModal.lines" :key="i" class="grid grid-cols-12 gap-2 items-center">
            <select v-model.number="line.accountId" class="col-span-5 min-h-[44px] rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-2 py-2 text-sm">
              <option :value="null">{{ t('backoffice.finance.journal.newEntry.selectAccount') }}</option>
              <option v-for="acc in allAccountOptions" :key="acc.id" :value="acc.id">{{ acc.code }} — {{ acc.name }}</option>
            </select>
            <input v-model="line.debit" type="number" min="0" step="0.01" placeholder="0.00"
              class="col-span-3 min-h-[44px] rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-2 py-2 text-sm tabular-nums" />
            <input v-model="line.credit" type="number" min="0" step="0.01" placeholder="0.00"
              class="col-span-3 min-h-[44px] rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-2 py-2 text-sm tabular-nums" />
            <button type="button" class="col-span-1 text-danger disabled:opacity-30" :disabled="newJournalModal.lines.length <= 2"
              @click="removeJournalLine(i)">✕</button>
          </div>
          <button type="button" class="text-sm font-semibold text-primary-700 dark:text-primary-400" @click="addJournalLine">
            + {{ t('backoffice.finance.journal.newEntry.addLine') }}
          </button>
        </div>

        <div class="flex items-center justify-between rounded-xl px-3 py-2 text-sm font-bold"
          :class="newJournalIsBalanced ? 'bg-success/10 text-success' : 'bg-warning/10 text-warning'">
          <span>{{ t('backoffice.finance.journal.newEntry.totalDebit') }}: {{ formatNumber(newJournalTotalDebit) }}</span>
          <span>{{ t('backoffice.finance.journal.newEntry.totalCredit') }}: {{ formatNumber(newJournalTotalCredit) }}</span>
          <span>{{ newJournalIsBalanced ? '✓' : '⚠️' }}</span>
        </div>
        <p v-if="newJournalModal.error" class="text-sm text-red-600 dark:text-red-400">{{ newJournalModal.error }}</p>
      </div>
      <template #footer>
        <div class="flex gap-2">
          <AppButton variant="ghost" class="flex-1" @click="newJournalModal.open = false">{{ t('backoffice.finance.cancel') }}</AppButton>
          <AppButton class="flex-1" :disabled="!newJournalIsBalanced" :loading="newJournalModal.saving" @click="confirmNewJournalEntry">
            {{ t('backoffice.finance.journal.newEntry.confirm') }}
          </AppButton>
        </div>
      </template>
    </AppModal>

    <!-- Payment Channels -->
    <div v-if="tab === 'payment-channels'" class="space-y-4">
      <div class="flex items-center justify-between">
        <p class="text-sm text-gray-500 dark:text-gray-400 max-w-2xl">{{ t('backoffice.finance.paymentChannels.description') }}</p>
        <AppButton size="sm" @click="() => { resetChannelForm(); showChannelForm = true }">
          {{ t('backoffice.finance.paymentChannels.new') }}
        </AppButton>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <div class="overflow-x-auto">
          <table class="w-full min-w-[760px]">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.paymentChannels.name') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.paymentChannels.method') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.paymentChannels.glAccount') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.paymentChannels.bankAccount') }}</th>
                <th class="px-4 py-3 text-center text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.paymentChannels.default') }}</th>
                <th class="px-4 py-3 text-center text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.paymentChannels.status') }}</th>
                <th class="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="ch in paymentChannels" :key="ch.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3">
                  <div class="text-sm font-semibold text-gray-900 dark:text-gray-100">{{ ch.name_ar || ch.name }}</div>
                  <div class="text-xs text-gray-400 dark:text-gray-400 font-mono">{{ ch.code }}</div>
                </td>
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ paymentChannelMethodLabels[ch.method] }}</td>
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                  <span class="font-mono">{{ ch.gl_account_code }}</span> — {{ ch.gl_account_name }}
                </td>
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ ch.bank_account_name ?? '—' }}</td>
                <td class="px-4 py-3 text-center">
                  <button v-if="!ch.is_default" @click="setChannelDefault(ch)"
                    class="text-xs text-blue-600 dark:text-blue-300 hover:underline">
                    {{ t('backoffice.finance.paymentChannels.setDefault') }}
                  </button>
                  <AppBadge v-else variant="success" size="sm">{{ t('backoffice.finance.paymentChannels.default') }}</AppBadge>
                </td>
                <td class="px-4 py-3 text-center">
                  <AppBadge :variant="ch.is_active ? 'success' : 'neutral'" size="sm">
                    {{ ch.is_active ? t('backoffice.finance.paymentChannels.active') : t('backoffice.finance.paymentChannels.inactive') }}
                  </AppBadge>
                </td>
                <td class="px-4 py-3 text-end whitespace-nowrap">
                  <button @click="editChannel(ch)" class="text-xs text-blue-600 dark:text-blue-300 hover:underline me-3">
                    {{ t('backoffice.finance.paymentChannels.edit') }}
                  </button>
                  <button @click="toggleChannelActive(ch)" class="text-xs hover:underline"
                    :class="ch.is_active ? 'text-red-600 dark:text-red-300' : 'text-emerald-600 dark:text-emerald-300'">
                    {{ ch.is_active ? t('backoffice.finance.paymentChannels.disable') : t('backoffice.finance.paymentChannels.enable') }}
                  </button>
                </td>
              </tr>
              <tr v-if="paymentChannels.length === 0">
                <td colspan="7" class="px-4 py-8">
                  <EmptyState icon="💳" :title="t('backoffice.finance.paymentChannels.empty')" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>

      <AppModal :open="showChannelForm"
        :title="editingChannelId ? t('backoffice.finance.paymentChannels.editTitle') : t('backoffice.finance.paymentChannels.newTitle')"
        size="md" @close="showChannelForm = false">
        <div class="space-y-3">
          <p v-if="channelFormError" class="text-sm text-red-600 dark:text-red-300 bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">{{ channelFormError }}</p>

          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.paymentChannels.code') }}</label>
            <input v-model="channelForm.code" :disabled="!!editingChannelId"
              class="w-full rounded-lg border border-stone-200 dark:border-border/50 px-3 py-2 text-sm bg-white dark:bg-surface disabled:opacity-50" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.paymentChannels.nameEn') }}</label>
              <input v-model="channelForm.name" class="w-full rounded-lg border border-stone-200 dark:border-border/50 px-3 py-2 text-sm bg-white dark:bg-surface" />
            </div>
            <div>
              <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.paymentChannels.nameAr') }}</label>
              <input v-model="channelForm.name_ar" class="w-full rounded-lg border border-stone-200 dark:border-border/50 px-3 py-2 text-sm bg-white dark:bg-surface" />
            </div>
          </div>
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.paymentChannels.method') }}</label>
            <select v-model="channelForm.method" :disabled="!!editingChannelId"
              class="w-full rounded-lg border border-stone-200 dark:border-border/50 px-3 py-2 text-sm bg-white dark:bg-surface disabled:opacity-50">
              <option value="cash">{{ t('backoffice.finance.methodCash') }}</option>
              <option value="card">{{ t('backoffice.finance.methodCard') }}</option>
              <option value="wallet">{{ t('backoffice.finance.paymentChannels.methodWallet') }}</option>
            </select>
          </div>
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.paymentChannels.glAccount') }}</label>
            <select v-model.number="channelForm.gl_account_id"
              class="w-full rounded-lg border border-stone-200 dark:border-border/50 px-3 py-2 text-sm bg-white dark:bg-surface">
              <option :value="null">{{ t('backoffice.finance.paymentChannels.selectAccount') }}</option>
              <option v-for="acc in glAccountOptions" :key="acc.id" :value="acc.id">{{ acc.code }} — {{ acc.name }}</option>
            </select>
          </div>
          <div v-if="channelForm.method !== 'cash'">
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.paymentChannels.bankAccount') }}</label>
            <select v-model.number="channelForm.bank_account_id"
              class="w-full rounded-lg border border-stone-200 dark:border-border/50 px-3 py-2 text-sm bg-white dark:bg-surface">
              <option :value="null">{{ t('backoffice.finance.paymentChannels.noBankAccount') }}</option>
              <option v-for="ba in bankAccounts" :key="ba.id" :value="ba.id">{{ ba.bank_name }} — {{ ba.account_name }}</option>
            </select>
          </div>
          <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
            <input type="checkbox" v-model="channelForm.is_default" />
            {{ t('backoffice.finance.paymentChannels.setAsDefault') }}
          </label>

          <div class="flex justify-end gap-2 pt-2">
            <AppButton variant="outline" size="sm" @click="showChannelForm = false">{{ t('backoffice.finance.cancel') }}</AppButton>
            <AppButton size="sm" :disabled="channelSaving" @click="savePaymentChannel">
              {{ channelSaving ? t('backoffice.finance.saving') : t('backoffice.finance.save') }}
            </AppButton>
          </div>
        </div>
      </AppModal>
    </div>

    <!-- Expenses (2026-08-16) -->
    <div v-if="tab === 'expenses'" class="space-y-4">
      <AppCard padding="md">
        <div class="flex flex-wrap gap-3 items-end">
          <div>
            <label class="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.finance.dateFrom') }}</label>
            <input v-model="expensesDateFrom" type="date"
              class="rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.finance.dateTo') }}</label>
            <input v-model="expensesDateTo" type="date"
              class="rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm" />
          </div>
          <AppButton variant="primary" :loading="expensesLoading" @click="() => { expensesPage = 1; loadExpenses() }">
            {{ t('backoffice.finance.refresh') }}
          </AppButton>
          <AppButton variant="outline" class="ms-auto" @click="openNewExpenseModal">
            💸 {{ t('backoffice.finance.expenses.newExpense.btnLabel') }}
          </AppButton>
        </div>
      </AppCard>

      <AppCard padding="none">
        <div v-if="expensesLoading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
        <EmptyState v-else-if="!expenses.length" icon="💸"
          :title="t('backoffice.finance.expenses.empty')" />
        <div v-else class="overflow-x-auto">
          <div class="px-4 py-2 border-b border-stone-100 dark:border-border/50 text-xs text-gray-500 dark:text-gray-400">
            {{ t('backoffice.finance.journal.totalEntries', { count: expensesTotal }) }}
          </div>
          <table class="w-full text-sm">
            <thead>
              <tr class="text-gray-500 dark:text-gray-400 text-xs">
                <th class="px-4 py-2 text-start font-semibold">{{ t('backoffice.finance.date') }}</th>
                <th class="px-4 py-2 text-start font-semibold">{{ t('backoffice.finance.expenses.category') }}</th>
                <th class="px-4 py-2 text-start font-semibold">{{ t('backoffice.finance.journal.description') }}</th>
                <th class="px-4 py-2 text-start font-semibold">{{ t('backoffice.finance.expenses.settlementAccount') }}</th>
                <th class="px-4 py-2 text-end font-semibold">{{ t('backoffice.finance.expenses.amount') }}</th>
                <th class="px-4 py-2 text-start font-semibold">{{ t('backoffice.finance.expenses.status.label') }}</th>
                <th class="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="exp in expenses" :key="exp.id" class="border-t border-stone-100 dark:border-border/20"
                :class="{ 'opacity-50': exp.voided_at }">
                <td class="px-4 py-2 tabular-nums text-gray-500 dark:text-gray-400">{{ exp.expense_date }}</td>
                <td class="px-4 py-2 font-mono text-xs">{{ exp.expense_account_code }} — {{ exp.expense_account_name }}</td>
                <td class="px-4 py-2">{{ exp.description }}<span v-if="exp.reference" class="text-gray-500 dark:text-gray-400"> ({{ exp.reference }})</span></td>
                <td class="px-4 py-2 font-mono text-xs text-gray-500 dark:text-gray-400">{{ exp.settlement_account_code }}</td>
                <td class="px-4 py-2 text-end tabular-nums font-bold">{{ formatNumber(exp.amount) }}</td>
                <td class="px-4 py-2">
                  <AppBadge v-if="exp.voided_at" variant="danger">{{ t('backoffice.finance.expenses.status.voided') }}</AppBadge>
                  <AppBadge v-else-if="exp.payment_status === 'unpaid'" variant="warning">{{ t('backoffice.finance.expenses.status.unpaid') }}</AppBadge>
                  <AppBadge v-else-if="exp.payment_status === 'partial'" variant="warning">{{ t('backoffice.finance.expenses.status.partial') }}</AppBadge>
                  <AppBadge v-else variant="success">{{ t('backoffice.finance.expenses.status.paid') }}</AppBadge>
                </td>
                <td class="px-4 py-2 whitespace-nowrap">
                  <button v-if="!exp.voided_at && exp.payment_status !== 'paid'"
                    class="text-xs font-semibold text-primary-700 dark:text-primary-400 hover:underline me-3"
                    @click="openPayExpenseModal(exp)">
                    {{ t('backoffice.finance.expenses.pay.btnLabel') }}
                  </button>
                  <button v-if="!exp.voided_at && exp.amount_paid === 0"
                    class="text-xs font-semibold text-danger hover:underline"
                    @click="openVoidExpensePrompt(exp.id)">
                    {{ t('backoffice.finance.expenses.void.btnLabel') }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="expensesTotal > 30" class="flex items-center justify-between px-4 py-3 border-t border-stone-100 dark:border-border/50">
            <span class="text-xs text-gray-500 dark:text-gray-400">
              {{ t('backoffice.finance.journal.page', { page: expensesPage, total: Math.ceil(expensesTotal / 30) }) }}
            </span>
            <div class="flex gap-2">
              <AppButton variant="outline" size="sm" :disabled="expensesPage <= 1"
                @click="() => { expensesPage--; loadExpenses() }">{{ t('backoffice.finance.prev') }}</AppButton>
              <AppButton variant="outline" size="sm" :disabled="expensesPage * 30 >= expensesTotal"
                @click="() => { expensesPage++; loadExpenses() }">{{ t('backoffice.finance.next') }}</AppButton>
            </div>
          </div>
        </div>
      </AppCard>
    </div>

    <!-- ══ NEW EXPENSE MODAL ══ -->
    <AppModal :open="newExpenseModal.open" :title="`💸 ${t('backoffice.finance.expenses.newExpense.title')}`"
      size="md" @close="newExpenseModal.open = false">
      <div class="space-y-4">
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.journal.newEntry.entryDate') }}
          <input v-model="newExpenseModal.expenseDate" type="date"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.expenses.category') }}
          <select v-model.number="newExpenseModal.expenseAccountId"
            class="min-h-[44px] w-full mt-1 rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm">
            <option :value="null">{{ t('backoffice.finance.journal.newEntry.selectAccount') }}</option>
            <option v-for="acc in expenseAccountOptions" :key="acc.id" :value="acc.id">{{ acc.code }} — {{ acc.name }}</option>
          </select>
        </label>
        <label class="flex items-center gap-2 text-sm font-bold text-gray-700 dark:text-gray-300">
          <input v-model="newExpenseModal.deferPayment" type="checkbox" class="rounded" />
          {{ t('backoffice.finance.expenses.newExpense.deferPayment') }}
        </label>
        <label v-if="!newExpenseModal.deferPayment" class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.expenses.settlementAccount') }}
          <select v-model.number="newExpenseModal.settlementAccountId"
            class="min-h-[44px] w-full mt-1 rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm">
            <option :value="null">{{ t('backoffice.finance.journal.newEntry.selectAccount') }}</option>
            <option v-for="acc in settlementAccountOptions" :key="acc.id" :value="acc.id">{{ acc.code }} — {{ acc.name }}</option>
          </select>
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.expenses.amount') }}
          <input v-model="newExpenseModal.amount" type="number" min="0" step="0.01"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm tabular-nums" />
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.journal.description') }}
          <input v-model="newExpenseModal.description"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.journal.newEntry.reference') }}
          <input v-model="newExpenseModal.reference"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <p v-if="newExpenseModal.error" class="text-sm text-red-600 dark:text-red-400">{{ newExpenseModal.error }}</p>
      </div>
      <template #footer>
        <div class="flex gap-2">
          <AppButton variant="ghost" class="flex-1" @click="newExpenseModal.open = false">{{ t('backoffice.finance.cancel') }}</AppButton>
          <AppButton class="flex-1" :loading="newExpenseModal.saving" @click="confirmNewExpense">
            {{ t('backoffice.finance.expenses.newExpense.confirm') }}
          </AppButton>
        </div>
      </template>
    </AppModal>

    <PinGuardModal
      v-if="expensePinGuard.open"
      :min-level="80"
      :title="t('backoffice.finance.expenses.newExpense.approvalTitle')"
      :message="t('backoffice.finance.expenses.newExpense.approvalMessage')"
      :loading="expensePinGuard.busy"
      :error-message="expensePinGuard.error"
      @approved="onExpensePinApproved"
      @cancel="expensePinGuard.open = false"
    />

    <!-- ══ PAY EXPENSE MODAL ══ -->
    <AppModal :open="payExpenseModal.open" :title="`💳 ${t('backoffice.finance.expenses.pay.title')}`"
      size="sm" @close="payExpenseModal.open = false">
      <div class="space-y-4">
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.expenses.settlementAccount') }}
          <select v-model.number="payExpenseModal.settlementAccountId"
            class="min-h-[44px] w-full mt-1 rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm">
            <option :value="null">{{ t('backoffice.finance.journal.newEntry.selectAccount') }}</option>
            <option v-for="acc in settlementAccountOptions" :key="acc.id" :value="acc.id">{{ acc.code }} — {{ acc.name }}</option>
          </select>
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.expenses.amount') }}
          <input v-model="payExpenseModal.amount" type="number" min="0" step="0.01"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm tabular-nums" />
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.custodies.disbursedDate') }}
          <input v-model="payExpenseModal.paidAt" type="date"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <p v-if="payExpenseModal.error" class="text-sm text-red-600 dark:text-red-400">{{ payExpenseModal.error }}</p>
      </div>
      <template #footer>
        <div class="flex gap-2">
          <AppButton variant="ghost" class="flex-1" @click="payExpenseModal.open = false">{{ t('backoffice.finance.cancel') }}</AppButton>
          <AppButton class="flex-1" :loading="payExpenseModal.saving" @click="confirmPayExpense">
            {{ t('backoffice.finance.expenses.pay.confirm') }}
          </AppButton>
        </div>
      </template>
    </AppModal>

    <StepUpConfirmModal
      v-if="pendingVoidExpenseId !== null"
      purpose="expense_void"
      :intent="{ expense_id: pendingVoidExpenseId }"
      :description="t('backoffice.finance.expenses.void.stepUpDescription')"
      :loading="voidExpenseStepUpBusy"
      :error-message="voidExpenseStepUpError"
      @confirmed="onVoidExpenseStepUpConfirmed"
      @cancel="cancelVoidExpensePrompt"
    />

    <!-- Custodies / العهدة (2026-08-19) -->
    <div v-if="tab === 'custodies'" class="space-y-4">
      <AppCard padding="md">
        <div class="flex flex-wrap gap-3 items-end">
          <AppButton variant="primary" :loading="custodiesLoading" @click="() => { custodiesPage = 1; loadCustodies() }">
            {{ t('backoffice.finance.refresh') }}
          </AppButton>
          <AppButton variant="outline" class="ms-auto" @click="openNewCustodyModal">
            🧾 {{ t('backoffice.finance.custodies.newCustody.btnLabel') }}
          </AppButton>
        </div>
      </AppCard>

      <AppCard padding="none">
        <div v-if="custodiesLoading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
        <EmptyState v-else-if="!custodies.length" icon="🧾"
          :title="t('backoffice.finance.custodies.empty')" />
        <div v-else class="overflow-x-auto">
          <div class="px-4 py-2 border-b border-stone-100 dark:border-border/50 text-xs text-gray-500 dark:text-gray-400">
            {{ t('backoffice.finance.journal.totalEntries', { count: custodiesTotal }) }}
          </div>
          <table class="w-full text-sm">
            <thead>
              <tr class="text-gray-500 dark:text-gray-400 text-xs">
                <th class="px-4 py-2 text-start font-semibold">{{ t('backoffice.finance.date') }}</th>
                <th class="px-4 py-2 text-start font-semibold">{{ t('backoffice.finance.custodies.holderName') }}</th>
                <th class="px-4 py-2 text-start font-semibold">{{ t('backoffice.finance.custodies.purpose') }}</th>
                <th class="px-4 py-2 text-end font-semibold">{{ t('backoffice.finance.expenses.amount') }}</th>
                <th class="px-4 py-2 text-start font-semibold">{{ t('backoffice.finance.expenses.status.label') }}</th>
                <th class="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in custodies" :key="c.id" class="border-t border-stone-100 dark:border-border/20"
                :class="{ 'opacity-50': c.voided_at }">
                <td class="px-4 py-2 tabular-nums text-gray-500 dark:text-gray-400">{{ c.disbursed_date }}</td>
                <td class="px-4 py-2 font-semibold">{{ c.holder_name }}</td>
                <td class="px-4 py-2">{{ c.purpose }}</td>
                <td class="px-4 py-2 text-end tabular-nums font-bold">{{ formatNumber(c.amount) }}</td>
                <td class="px-4 py-2">
                  <AppBadge v-if="c.voided_at" variant="danger">{{ t('backoffice.finance.expenses.status.voided') }}</AppBadge>
                  <AppBadge v-else-if="c.status === 'settled'" variant="success">{{ t('backoffice.finance.custodies.status.settled') }}</AppBadge>
                  <AppBadge v-else variant="warning">{{ t('backoffice.finance.custodies.status.open') }}</AppBadge>
                </td>
                <td class="px-4 py-2 whitespace-nowrap">
                  <button v-if="!c.voided_at && c.status === 'open'"
                    class="text-xs font-semibold text-primary-700 dark:text-primary-400 hover:underline me-3"
                    @click="openSettleCustodyModal(c)">
                    {{ t('backoffice.finance.custodies.settle.btnLabel') }}
                  </button>
                  <button v-if="!c.voided_at && c.status === 'open'"
                    class="text-xs font-semibold text-danger hover:underline"
                    @click="openVoidCustodyPrompt(c.id)">
                    {{ t('backoffice.finance.custodies.void.btnLabel') }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="custodiesTotal > 30" class="flex items-center justify-between px-4 py-3 border-t border-stone-100 dark:border-border/50">
            <span class="text-xs text-gray-500 dark:text-gray-400">
              {{ t('backoffice.finance.journal.page', { page: custodiesPage, total: Math.ceil(custodiesTotal / 30) }) }}
            </span>
            <div class="flex gap-2">
              <AppButton variant="outline" size="sm" :disabled="custodiesPage <= 1"
                @click="() => { custodiesPage--; loadCustodies() }">{{ t('backoffice.finance.prev') }}</AppButton>
              <AppButton variant="outline" size="sm" :disabled="custodiesPage * 30 >= custodiesTotal"
                @click="() => { custodiesPage++; loadCustodies() }">{{ t('backoffice.finance.next') }}</AppButton>
            </div>
          </div>
        </div>
      </AppCard>
    </div>

    <!-- ══ NEW CUSTODY MODAL ══ -->
    <AppModal :open="newCustodyModal.open" :title="`🧾 ${t('backoffice.finance.custodies.newCustody.title')}`"
      size="md" @close="newCustodyModal.open = false">
      <div class="space-y-4">
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.custodies.holderName') }}
          <input v-model="newCustodyModal.holderName"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.custodies.purpose') }}
          <input v-model="newCustodyModal.purpose"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.custodies.sourceAccount') }}
          <select v-model.number="newCustodyModal.sourceAccountId"
            class="min-h-[44px] w-full mt-1 rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm">
            <option :value="null">{{ t('backoffice.finance.journal.newEntry.selectAccount') }}</option>
            <option v-for="acc in custodyAssetAccountOptions" :key="acc.id" :value="acc.id">{{ acc.code }} — {{ acc.name }}</option>
          </select>
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.expenses.amount') }}
          <input v-model="newCustodyModal.amount" type="number" min="0" step="0.01"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm tabular-nums" />
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.custodies.disbursedDate') }}
          <input v-model="newCustodyModal.disbursedDate" type="date"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <p v-if="newCustodyModal.error" class="text-sm text-red-600 dark:text-red-400">{{ newCustodyModal.error }}</p>
      </div>
      <template #footer>
        <div class="flex gap-2">
          <AppButton variant="ghost" class="flex-1" @click="newCustodyModal.open = false">{{ t('backoffice.finance.cancel') }}</AppButton>
          <AppButton class="flex-1" :loading="newCustodyModal.saving" @click="confirmNewCustody">
            {{ t('backoffice.finance.custodies.newCustody.confirm') }}
          </AppButton>
        </div>
      </template>
    </AppModal>

    <!-- ══ SETTLE CUSTODY MODAL ══ -->
    <AppModal :open="settleCustodyModal.open" :title="`✅ ${t('backoffice.finance.custodies.settle.title')}`"
      size="lg" @close="settleCustodyModal.open = false">
      <div class="space-y-4">
        <p class="text-sm text-gray-600 dark:text-gray-400">
          {{ t('backoffice.finance.custodies.settle.amountHint', { amount: formatNumber(settleCustodyModal.custodyAmount) }) }}
        </p>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.custodies.settle.settlementDate') }}
          <input v-model="settleCustodyModal.settlementDate" type="date"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>

        <div class="space-y-3">
          <div v-for="(line, idx) in settleCustodyModal.lines" :key="idx"
            class="p-3 rounded-xl border border-stone-200 dark:border-border space-y-2">
            <div class="flex items-center justify-between">
              <span class="text-xs font-semibold text-gray-500 dark:text-gray-400">{{ t('backoffice.finance.custodies.settle.lineLabel', { n: idx + 1 }) }}</span>
              <button v-if="settleCustodyModal.lines.length > 1" class="text-xs text-danger hover:underline"
                @click="removeSettleLine(idx)">{{ t('backoffice.finance.custodies.settle.removeLine') }}</button>
            </div>
            <select v-model.number="line.expenseAccountId"
              class="min-h-[44px] w-full rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm">
              <option :value="null">{{ t('backoffice.finance.expenses.category') }}</option>
              <option v-for="acc in expenseAccountOptions" :key="acc.id" :value="acc.id">{{ acc.code }} — {{ acc.name }}</option>
            </select>
            <input v-model="line.amount" type="number" min="0" step="0.01"
              :placeholder="t('backoffice.finance.expenses.amount')"
              class="min-h-[44px] w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm tabular-nums" />
            <input v-model="line.description"
              :placeholder="t('backoffice.finance.journal.description')"
              class="min-h-[44px] w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
          </div>
          <AppButton variant="outline" size="sm" @click="addSettleLine">
            + {{ t('backoffice.finance.custodies.settle.addLine') }}
          </AppButton>
        </div>

        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.custodies.settle.returnedAmount') }}
          <input v-model="settleCustodyModal.returnedAmount" type="number" min="0" step="0.01"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm tabular-nums" />
        </label>

        <p class="text-sm font-semibold" :class="Math.abs(settleCustodyLinesTotal - settleCustodyModal.custodyAmount) > 0.01 ? 'text-danger' : 'text-green-600 dark:text-green-400'">
          {{ t('backoffice.finance.custodies.settle.runningTotal', { total: formatNumber(settleCustodyLinesTotal), amount: formatNumber(settleCustodyModal.custodyAmount) }) }}
        </p>
        <p v-if="settleCustodyModal.error" class="text-sm text-red-600 dark:text-red-400">{{ settleCustodyModal.error }}</p>
      </div>
      <template #footer>
        <div class="flex gap-2">
          <AppButton variant="ghost" class="flex-1" @click="settleCustodyModal.open = false">{{ t('backoffice.finance.cancel') }}</AppButton>
          <AppButton class="flex-1" :loading="settleCustodyModal.saving" @click="confirmSettleCustody">
            {{ t('backoffice.finance.custodies.settle.confirm') }}
          </AppButton>
        </div>
      </template>
    </AppModal>

    <StepUpConfirmModal
      v-if="pendingVoidCustodyId !== null"
      purpose="custody_void"
      :intent="{ custody_id: pendingVoidCustodyId }"
      :description="t('backoffice.finance.custodies.void.stepUpDescription')"
      :loading="voidCustodyStepUpBusy"
      :error-message="voidCustodyStepUpError"
      @confirmed="onVoidCustodyStepUpConfirmed"
      @cancel="cancelVoidCustodyPrompt"
    />

    <!-- Cash Receipts / إذن قبض عام (2026-08-19) -->
    <div v-if="tab === 'cash-receipts'" class="space-y-4">
      <AppCard padding="md">
        <div class="flex flex-wrap gap-3 items-end">
          <div>
            <label class="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.finance.dateFrom') }}</label>
            <input v-model="cashReceiptsDateFrom" type="date"
              class="rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.finance.dateTo') }}</label>
            <input v-model="cashReceiptsDateTo" type="date"
              class="rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm" />
          </div>
          <AppButton variant="primary" :loading="cashReceiptsLoading" @click="() => { cashReceiptsPage = 1; loadCashReceipts() }">
            {{ t('backoffice.finance.refresh') }}
          </AppButton>
          <AppButton variant="outline" class="ms-auto" @click="openNewCashReceiptModal">
            📥 {{ t('backoffice.finance.cashReceipts.newReceipt.btnLabel') }}
          </AppButton>
        </div>
      </AppCard>

      <AppCard padding="none">
        <div v-if="cashReceiptsLoading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
        <EmptyState v-else-if="!cashReceipts.length" icon="📥"
          :title="t('backoffice.finance.cashReceipts.empty')" />
        <div v-else class="overflow-x-auto">
          <div class="px-4 py-2 border-b border-stone-100 dark:border-border/50 text-xs text-gray-500 dark:text-gray-400">
            {{ t('backoffice.finance.journal.totalEntries', { count: cashReceiptsTotal }) }}
          </div>
          <table class="w-full text-sm">
            <thead>
              <tr class="text-gray-500 dark:text-gray-400 text-xs">
                <th class="px-4 py-2 text-start font-semibold">{{ t('backoffice.finance.date') }}</th>
                <th class="px-4 py-2 text-start font-semibold">{{ t('backoffice.finance.cashReceipts.destinationAccount') }}</th>
                <th class="px-4 py-2 text-start font-semibold">{{ t('backoffice.finance.journal.description') }}</th>
                <th class="px-4 py-2 text-start font-semibold">{{ t('backoffice.finance.cashReceipts.sourceAccount') }}</th>
                <th class="px-4 py-2 text-end font-semibold">{{ t('backoffice.finance.expenses.amount') }}</th>
                <th class="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in cashReceipts" :key="r.id" class="border-t border-stone-100 dark:border-border/20"
                :class="{ 'opacity-50': r.voided_at }">
                <td class="px-4 py-2 tabular-nums text-gray-500 dark:text-gray-400">{{ r.receipt_date }}</td>
                <td class="px-4 py-2 font-mono text-xs">{{ r.destination_account_code }} — {{ r.destination_account_name }}</td>
                <td class="px-4 py-2">{{ r.description }}<span v-if="r.reference" class="text-gray-500 dark:text-gray-400"> ({{ r.reference }})</span></td>
                <td class="px-4 py-2 font-mono text-xs text-gray-500 dark:text-gray-400">{{ r.source_account_code }}</td>
                <td class="px-4 py-2 text-end tabular-nums font-bold">{{ formatNumber(r.amount) }}</td>
                <td class="px-4 py-2 whitespace-nowrap">
                  <AppBadge v-if="r.voided_at" variant="danger">{{ t('backoffice.finance.expenses.status.voided') }}</AppBadge>
                  <button v-else class="text-xs font-semibold text-danger hover:underline"
                    @click="openVoidCashReceiptPrompt(r.id)">
                    {{ t('backoffice.finance.cashReceipts.void.btnLabel') }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="cashReceiptsTotal > 30" class="flex items-center justify-between px-4 py-3 border-t border-stone-100 dark:border-border/50">
            <span class="text-xs text-gray-500 dark:text-gray-400">
              {{ t('backoffice.finance.journal.page', { page: cashReceiptsPage, total: Math.ceil(cashReceiptsTotal / 30) }) }}
            </span>
            <div class="flex gap-2">
              <AppButton variant="outline" size="sm" :disabled="cashReceiptsPage <= 1"
                @click="() => { cashReceiptsPage--; loadCashReceipts() }">{{ t('backoffice.finance.prev') }}</AppButton>
              <AppButton variant="outline" size="sm" :disabled="cashReceiptsPage * 30 >= cashReceiptsTotal"
                @click="() => { cashReceiptsPage++; loadCashReceipts() }">{{ t('backoffice.finance.next') }}</AppButton>
            </div>
          </div>
        </div>
      </AppCard>
    </div>

    <!-- ══ NEW CASH RECEIPT MODAL ══ -->
    <AppModal :open="newCashReceiptModal.open" :title="`📥 ${t('backoffice.finance.cashReceipts.newReceipt.title')}`"
      size="md" @close="newCashReceiptModal.open = false">
      <div class="space-y-4">
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.journal.newEntry.entryDate') }}
          <input v-model="newCashReceiptModal.receiptDate" type="date"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.cashReceipts.destinationAccount') }}
          <select v-model.number="newCashReceiptModal.destinationAccountId"
            class="min-h-[44px] w-full mt-1 rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm">
            <option :value="null">{{ t('backoffice.finance.journal.newEntry.selectAccount') }}</option>
            <option v-for="acc in settlementAccountOptions" :key="acc.id" :value="acc.id">{{ acc.code }} — {{ acc.name }}</option>
          </select>
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.cashReceipts.sourceAccount') }}
          <select v-model.number="newCashReceiptModal.sourceAccountId"
            class="min-h-[44px] w-full mt-1 rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm">
            <option :value="null">{{ t('backoffice.finance.journal.newEntry.selectAccount') }}</option>
            <option v-for="acc in accounts" :key="acc.id" :value="acc.id">{{ acc.code }} — {{ acc.name }}</option>
          </select>
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.expenses.amount') }}
          <input v-model="newCashReceiptModal.amount" type="number" min="0" step="0.01"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm tabular-nums" />
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.journal.description') }}
          <input v-model="newCashReceiptModal.description"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.journal.newEntry.reference') }}
          <input v-model="newCashReceiptModal.reference"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <p v-if="newCashReceiptModal.error" class="text-sm text-red-600 dark:text-red-400">{{ newCashReceiptModal.error }}</p>
      </div>
      <template #footer>
        <div class="flex gap-2">
          <AppButton variant="ghost" class="flex-1" @click="newCashReceiptModal.open = false">{{ t('backoffice.finance.cancel') }}</AppButton>
          <AppButton class="flex-1" :loading="newCashReceiptModal.saving" @click="confirmNewCashReceipt">
            {{ t('backoffice.finance.cashReceipts.newReceipt.confirm') }}
          </AppButton>
        </div>
      </template>
    </AppModal>

    <StepUpConfirmModal
      v-if="pendingVoidCashReceiptId !== null"
      purpose="cash_receipt_void"
      :intent="{ receipt_id: pendingVoidCashReceiptId }"
      :description="t('backoffice.finance.cashReceipts.void.stepUpDescription')"
      :loading="voidCashReceiptStepUpBusy"
      :error-message="voidCashReceiptStepUpError"
      @confirmed="onVoidCashReceiptStepUpConfirmed"
      @cancel="cancelVoidCashReceiptPrompt"
    />

    <!-- كشف حساب — drill-down (2026-08-19) -->
    <AppModal :open="ledgerModal.open" :title="ledgerModal.account ? `📒 ${ledgerModal.account.code} — ${ledgerModal.account.name}` : t('backoffice.finance.ledger.title')" size="lg" @close="closeAccountLedger">
      <div class="min-w-[280px]">
        <div class="flex flex-wrap items-end gap-3 mb-4">
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.fromDate') }}</label>
            <input v-model="ledgerModal.dateFrom" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
          </div>
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.toDate') }}</label>
            <input v-model="ledgerModal.dateTo" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
          </div>
          <AppButton size="sm" :loading="ledgerModal.loading" @click="loadAccountLedger">{{ t('backoffice.finance.apply') }}</AppButton>
        </div>

        <div v-if="ledgerModal.loading" class="flex justify-center py-10"><AppSpinner size="lg" /></div>
        <p v-else-if="ledgerModal.error" class="text-sm text-red-600 dark:text-red-400">{{ ledgerModal.error }}</p>
        <template v-else-if="ledgerData">
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
              <div class="text-xs text-gray-400 mb-1">{{ t('backoffice.finance.ledger.opening') }}</div>
              <div class="text-sm font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(ledgerData.opening_balance) }}</div>
            </div>
            <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
              <div class="text-xs text-gray-400 mb-1">{{ t('backoffice.finance.ledger.totalDebit') }}</div>
              <div class="text-sm font-bold text-green-600 dark:text-green-300">{{ formatNumber(ledgerData.total_debit) }}</div>
            </div>
            <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
              <div class="text-xs text-gray-400 mb-1">{{ t('backoffice.finance.ledger.totalCredit') }}</div>
              <div class="text-sm font-bold text-red-600 dark:text-red-300">{{ formatNumber(ledgerData.total_credit) }}</div>
            </div>
            <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
              <div class="text-xs text-gray-400 mb-1">{{ t('backoffice.finance.ledger.closing') }}</div>
              <div class="text-sm font-bold text-primary-700 dark:text-primary-300">{{ formatNumber(ledgerData.closing_balance) }}</div>
            </div>
          </div>
          <div class="overflow-x-auto max-h-[50vh] overflow-y-auto border border-stone-200 dark:border-border rounded-xl">
            <table class="w-full min-w-[600px]">
              <thead class="bg-stone-50 dark:bg-gray-800/60 sticky top-0">
                <tr>
                  <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.date') }}</th>
                  <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.ledger.reference') }}</th>
                  <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.description') }}</th>
                  <th class="px-3 py-2 text-end text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.ledger.debit') }}</th>
                  <th class="px-3 py-2 text-end text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.ledger.credit') }}</th>
                  <th class="px-3 py-2 text-end text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.ledger.runningBalance') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="l in ledgerData.lines" :key="l.entry_id" class="border-t border-stone-100 dark:border-border/50">
                  <td class="px-3 py-2 text-xs text-gray-600 dark:text-gray-400">{{ fmtDateFn(l.entry_date) }}</td>
                  <td class="px-3 py-2 text-xs font-mono text-gray-600 dark:text-gray-400">{{ l.reference }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ l.description }}</td>
                  <td class="px-3 py-2 text-xs text-end font-semibold text-green-600 dark:text-green-300">{{ l.debit ? formatNumber(l.debit) : '—' }}</td>
                  <td class="px-3 py-2 text-xs text-end font-semibold text-red-600 dark:text-red-300">{{ l.credit ? formatNumber(l.credit) : '—' }}</td>
                  <td class="px-3 py-2 text-xs text-end font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(l.running_balance) }}</td>
                </tr>
                <tr v-if="ledgerData.lines.length === 0">
                  <td colspan="6" class="px-4 py-8"><EmptyState icon="📒" :title="t('backoffice.finance.noDataThisPeriod')" /></td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
      <template #footer>
        <AppButton variant="ghost" class="w-full" @click="closeAccountLedger">{{ t('backoffice.finance.close') }}</AppButton>
      </template>
    </AppModal>

  </div>
</template>
