<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'
import StepUpConfirmModal from '../../components/StepUpConfirmModal.vue'
import PinGuardModal from '../../components/PinGuardModal.vue'
import ExchangeRatesTab from '../../components/finance/ExchangeRatesTab.vue'
import AgingReportTab from '../../components/finance/AgingReportTab.vue'
import CostCentersTab from '../../components/finance/CostCentersTab.vue'
import DepreciationTab from '../../components/finance/DepreciationTab.vue'
import BankReconciliationTab from '../../components/finance/BankReconciliationTab.vue'
import ChecksTab from '../../components/finance/ChecksTab.vue'
import PeriodsTab from '../../components/finance/PeriodsTab.vue'
import OverviewTab from '../../components/finance/OverviewTab.vue'
import AccountsTab from '../../components/finance/AccountsTab.vue'
import PaymentChannelsTab from '../../components/finance/PaymentChannelsTab.vue'
import JournalTab from '../../components/finance/JournalTab.vue'
import ShiftsTab from '../../components/finance/ShiftsTab.vue'
import BalanceSheetTab from '../../components/finance/BalanceSheetTab.vue'
import TrialBalanceTab from '../../components/finance/TrialBalanceTab.vue'
import IncomeStatementTab from '../../components/finance/IncomeStatementTab.vue'

const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatNumber, formatDate: fmtDateFn } = useStaffFormat()
const auth = useAuthStore()
// CX-02C: branchId comes from bootstrap (session-scoped, no ?? 1 fallback).
// activeBranchId is null when requires_branch_selection=true — in that case
// API calls carry no branch_id and the server returns 409 BRANCH_CONTEXT_REQUIRED.
const branchId = computed(() => auth.activeBranchId)
const tab = ref<'overview' | 'checks' | 'accounts' | 'cost-centers' | 'balance-sheet' | 'depreciation' | 'bank-reconciliation' | 'shifts' | 'exchange-rates' | 'journal' | 'payment-channels' | 'expenses' | 'custodies' | 'cash-receipts' | 'trial-balance' | 'income-statement' | 'aging' | 'periods'>('overview')
const activeGroupIdx = ref(0)

interface Account { id: number; code: string; name: string; account_type: string; balance: number }
interface BankAccount {
  id: number; bank_name: string; account_name: string; account_number: string
  currency: string; opening_balance: number; is_active: boolean
}
const accounts = ref<Account[]>([])
const loading = ref(false)

// ── Depreciation — استُخرج لـ DepreciationTab.vue (2026-09-07) ───────

// ── Bank Reconciliation — استُخرج لـ BankReconciliationTab.vue
// (2026-09-07). bankAccounts هنا لسه محتفظ بيه لتاب "قنوات التحصيل" تحت —
// نسخة منفصلة عن نسخة الكومبوننت المستخرج عمدًا (نفس نمط تكرار الجلب).
const bankAccounts = ref<BankAccount[]>([])

// ── Payment Channels — استُخرج لـ PaymentChannelsTab.vue (2026-09-07) ─

// ── Cost Centers — استُخرج لـ CostCentersTab.vue (2026-09-07) ─────────
const today = new Date().toISOString().slice(0, 10)
const firstOfMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().slice(0, 10)

// ── الميزانية العمومية، ميزان المراجعة، قائمة الدخل — استُخرجوا لـ
// BalanceSheetTab.vue / TrialBalanceTab.vue / IncomeStatementTab.vue
// (تقسيم الملفات الكبيرة، 2026-09-07).

// ── تقرير أعمار الديون (Aging) — 2026-08-19 ────────────────────────────

// ── الفترات المحاسبية + الإقفال السنوي — استُخرج لـ PeriodsTab.vue
// (2026-09-07) ──────────────────────────────────────────────────────

// ── كشف حساب (ledger drill-down) — استُخرج لـ AccountsTab.vue
// (2026-09-07) ──────────────────────────────────────────────────────

async function loadTab(tabId: typeof tab.value) {
  tab.value = tabId
  if (tabId === 'shifts') { return }
  if (tabId === 'depreciation') { return }
  if (tabId === 'bank-reconciliation') { return }
  if (tabId === 'balance-sheet') { return }
  if (tabId === 'cost-centers') { return }
  if (tabId === 'journal') { return }
  if (tabId === 'payment-channels') { return }
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
  if (tabId === 'checks') { return }
  if (tabId === 'trial-balance') { return }
  if (tabId === 'income-statement') { return }
  if (tabId === 'periods') { return }
  if (tabId === 'overview') { return }
  if (tabId === 'accounts') { return }
}

// ── دفتر اليومية — استُخرج لـ JournalTab.vue (2026-09-07) ─────────────

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
    <OverviewTab v-if="tab === 'overview'" :branch-id="branchId" />

    <!-- Checks -->
    <ChecksTab v-if="tab === 'checks'" :branch-id="branchId" />

    <!-- Accounts -->
    <AccountsTab v-if="tab === 'accounts'" :branch-id="branchId" />

    <!-- Cost Centers -->
    <CostCentersTab v-if="tab === 'cost-centers'" :branch-id="branchId" />

    <!-- Balance Sheet (الميزانية العمومية) -->
    <BalanceSheetTab v-if="tab === 'balance-sheet'" :branch-id="branchId" />

    <!-- Trial Balance -->
    <TrialBalanceTab v-if="tab === 'trial-balance'" :branch-id="branchId" />

    <!-- Income Statement -->
    <IncomeStatementTab v-if="tab === 'income-statement'" :branch-id="branchId" />

    <!-- Aging Report -->
    <AgingReportTab v-if="tab === 'aging'" :branch-id="branchId" />

    <!-- Periods (إقفال شهري + سنوي) -->
    <PeriodsTab v-if="tab === 'periods'" :branch-id="branchId" />

    <!-- Depreciation -->
    <DepreciationTab v-if="tab === 'depreciation'" :branch-id="branchId" />

    <!-- Bank Reconciliation -->
    <BankReconciliationTab v-if="tab === 'bank-reconciliation'" :branch-id="branchId" />

    <!-- Shifts tab -->
    <ShiftsTab v-if="tab === 'shifts'" :branch-id="branchId" />

    <!-- POS-03: شاشة إدارة أسعار الصرف — manager+ فقط -->
    <ExchangeRatesTab v-if="tab === 'exchange-rates'" />

    <!-- دفتر اليومية -->
    <JournalTab v-if="tab === 'journal'" :branch-id="branchId" />

    <!-- Payment Channels -->
    <PaymentChannelsTab v-if="tab === 'payment-channels'" :branch-id="branchId" />

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

  </div>
</template>
