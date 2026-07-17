<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, ENDPOINTS, useAuthStore, useResortWebSocket } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const toast = useToast()
const { confirm } = useConfirm()
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
    toast.error(e?.response?.data?.detail ?? 'تعذّر تحميل الورديات')
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
  if (abs === 0) return 'text-green-600 font-bold'
  if (abs <= 50) return 'text-amber-500 font-semibold'
  if (abs <= 200) return 'text-amber-700 font-bold'
  return 'text-red-600 font-bold'
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
    toast.error(e?.response?.data?.detail ?? 'تعذّر تحميل تفاصيل الوردية')
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

const METHOD_LABEL: Record<string, string> = {
  cash: '💵 كاش', card: '💳 كارت', bank_transfer: '🏦 تحويل بنكي',
  credit: '📝 آجل', room_charge: '🛏️ حساب الغرفة', other: 'أخرى',
}
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
  } catch { toast.error('تعذّر تحميل بيانات الإهلاك — حاول تاني') }
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
    toast.success(`تم ترحيل إهلاك ${data.entries.length} أصل بإجمالي ${Number(data.total_amount).toLocaleString('ar-EG')} ج`)
    await loadDepreciation()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تشغيل دورة الإهلاك')
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
  } catch { toast.error('تعذّر تحميل الحسابات البنكية — حاول تاني') }
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
  } catch { toast.error('تعذّر تحميل بيانات التسوية — حاول تاني') }
}

async function createBankAccount() {
  if (!bankAccountForm.value.bank_name || !bankAccountForm.value.account_number) {
    toast.error('املأ اسم البنك ورقم الحساب'); return
  }
  try {
    await api.post(ENDPOINTS.finance.bankAccounts, {
      branch_id: branchId.value,
      bank_name: bankAccountForm.value.bank_name,
      account_name: bankAccountForm.value.account_name || bankAccountForm.value.bank_name,
      account_number: bankAccountForm.value.account_number,
      opening_balance: bankAccountForm.value.opening_balance,
    })
    toast.success('تم إنشاء الحساب البنكي')
    showBankAccountForm.value = false
    bankAccountForm.value = { bank_name: '', account_name: '', account_number: '', opening_balance: '0' }
    await loadBankAccounts()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر إنشاء الحساب البنكي')
  }
}

async function runAutoMatch() {
  if (!selectedBankAccountId.value) return
  matchingInProgress.value = true
  try {
    const { data } = await api.post(
      ENDPOINTS.finance.bankAccountAutoMatch(selectedBankAccountId.value),
    )
    toast.success(`اتطابق ${data.matched_count} سطر تلقائيًا`)
    await loadStatementLinesAndSummary()
  } catch { toast.error('تعذّر تشغيل المطابقة التلقائية') }
  finally { matchingInProgress.value = false }
}

const statementLineStatusConfig: Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }> = {
  unmatched: { label: 'غير مطابق', variant: 'warning' },
  matched:   { label: 'مطابق',     variant: 'success' },
  ignored:   { label: 'متجاهل',    variant: 'neutral' },
}

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
  } catch { toast.error('تعذّر تحميل مراكز التكلفة — حاول تاني') }
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
    toast.error(e?.response?.data?.detail ?? 'تعذّر تحميل الميزانية العمومية')
  } finally {
    loading.value = false
  }
}

const checkStatusConfig: Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }> = {
  received:  { label: 'مستلم',   variant: 'neutral' },
  deposited: { label: 'مودع',    variant: 'info' },
  cleared:   { label: 'محصل',    variant: 'success' },
  bounced:   { label: 'مرتجع',   variant: 'danger' },
}

async function loadTab(t: typeof tab.value) {
  tab.value = t
  if (t === 'shifts') { await loadShifts(); return }
  if (t === 'depreciation') { await loadDepreciation(); return }
  if (t === 'bank-reconciliation') { await loadBankAccounts(); return }
  if (t === 'balance-sheet') { await loadBalanceSheet(); return }

  loading.value = true
  try {
    if (t === 'overview') {
      const res = await api.get(ENDPOINTS.finance.reportsIncomeStatement, {
        params: { branch_id: branchId.value, date_from: firstOfMonth, date_to: today },
      })
      financeData.value = {
        total_revenue: Number(res.data.total_revenue),
        total_expense: Number(res.data.total_expense),
        net_income: Number(res.data.net_income),
      }
    } else if (t === 'checks') {
      const res = await api.get(ENDPOINTS.finance.checks, { params: { branch_id: branchId.value } })
      checks.value = res.data.checks ?? res.data.items ?? res.data
    } else if (t === 'accounts') {
      const res = await api.get(ENDPOINTS.finance.accounts, { params: { branch_id: branchId.value } })
      accounts.value = res.data.accounts ?? res.data.items ?? res.data
    } else if (t === 'cost-centers') {
      await loadCostCenters()
    }
  } catch {
    const messages: Record<'overview' | 'checks' | 'accounts' | 'cost-centers', string> = {
      overview: 'تعذّر تحميل قائمة الدخل — حاول تاني',
      checks: 'تعذّر تحميل الشيكات — حاول تاني',
      accounts: 'تعذّر تحميل الحسابات — حاول تاني',
      'cost-centers': 'تعذّر تحميل مراكز التكلفة — حاول تاني',
    }
    toast.error(messages[t as 'overview' | 'checks' | 'accounts' | 'cost-centers'])
  } finally { loading.value = false }
}

async function advanceCheck(check: Check) {
  const flow: Record<string, string> = { received: 'deposited', deposited: 'cleared' }
  const next = flow[check.status]
  if (!next) return
  try {
    await api.patch(ENDPOINTS.finance.checkStatus(check.id), { to_status: next })
    check.status = next
  } catch { toast.error('تعذّر تحديث حالة الشيك — حاول تاني') }
}

// كانت الشاشة بتعرض بس مسار "إيداع → تحصيل" — مفيش أي زرار لتسجيل شيك
// مرتجع (bounced) رغم إن الحالة والـ endpoint موجودين بالكامل في الباك إند
// (راجع CHECK_STATUS_TRANSITIONS في finance/services.py). في الواقع نسبة لا
// يُستهان بها من الشيكات بترتد فعليًا (رصيد غير كافٍ) — فجوة UI صغيرة على
// ميزة موجودة، مش ميزة جديدة.
async function markCheckBounced(check: Check) {
  const ok = await confirm({
    message: `تأكيد ارتداد الشيك رقم "${check.check_number}" (${check.amount.toLocaleString('ar-EG')} ج)؟ لا يمكن التراجع عن هذا الإجراء.`,
    danger: true, confirmText: 'نعم، الشيك مرتجع', cancelText: 'تراجع',
  })
  if (!ok) return
  try {
    await api.patch(ENDPOINTS.finance.checkStatus(check.id), {
      to_status: 'bounced', notes: 'رصيد غير كافٍ — سُجّل من شاشة الحسابات',
    })
    check.status = 'bounced'
    toast.success('تم تسجيل الشيك كمرتجع')
  } catch { toast.error('تعذّر تحديث حالة الشيك — حاول تاني') }
}

onMounted(() => loadTab('overview'))
</script>

<template>
  <div dir="rtl">
    <h2 class="text-2xl font-black text-gray-900 dark:text-gray-100 mb-6">المالية</h2>

    <div class="flex gap-1 bg-stone-100 dark:bg-gray-700 p-1 rounded-xl mb-6 w-fit">
      <button v-for="t in [{ val: 'overview', label: 'نظرة عامة' }, { val: 'checks', label: 'الشيكات' }, { val: 'accounts', label: 'الحسابات' }, { val: 'cost-centers', label: 'مراكز التكلفة' }, { val: 'balance-sheet', label: 'الميزانية العمومية' }, { val: 'depreciation', label: 'إهلاك الأصول' }, { val: 'bank-reconciliation', label: 'التسوية البنكية' }, { val: 'shifts', label: 'الورديات' }]"
        :key="t.val" @click="loadTab(t.val as any)"
        :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all', tab === t.val ? 'bg-white dark:bg-surface shadow-sm text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-500 hover:text-gray-700 dark:text-gray-300']"
      >{{ t.label }}</button>
    </div>

    <!-- Overview -->
    <div v-if="tab === 'overview'">
      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <div v-else-if="financeData" class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <AppCard padding="lg" class="text-center">
          <div class="text-sm text-gray-500 dark:text-gray-500 mb-2">إجمالي الإيرادات</div>
          <div class="text-3xl font-black text-green-600">{{ financeData.total_revenue.toLocaleString('ar-EG') }}</div>
          <div class="text-xs text-gray-400 dark:text-gray-500 mt-1">جنيه</div>
        </AppCard>
        <AppCard padding="lg" class="text-center">
          <div class="text-sm text-gray-500 dark:text-gray-500 mb-2">إجمالي المصروفات</div>
          <div class="text-3xl font-black text-red-500">{{ financeData.total_expense.toLocaleString('ar-EG') }}</div>
          <div class="text-xs text-gray-400 dark:text-gray-500 mt-1">جنيه</div>
        </AppCard>
        <AppCard padding="lg" class="text-center">
          <div class="text-sm text-gray-500 dark:text-gray-500 mb-2">صافي الربح</div>
          <div :class="['text-3xl font-black', financeData.net_income >= 0 ? 'text-blue-700' : 'text-red-500']">
            {{ financeData.net_income.toLocaleString('ar-EG') }}
          </div>
          <div class="text-xs text-gray-400 dark:text-gray-500 mt-1">جنيه</div>
        </AppCard>
      </div>
      <AppCard v-else padding="lg">
        <EmptyState icon="📊" title="لا تتوفر بيانات مالية حالياً" />
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
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">رقم الشيك</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الساحب</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">المبلغ</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">تاريخ الاستحقاق</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الحالة</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">إجراء</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="check in checks" :key="check.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3 font-mono text-sm text-gray-900 dark:text-gray-100">{{ check.check_number }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ check.drawer_name }}</td>
                <td class="px-4 py-3 text-sm font-bold text-gray-900 dark:text-gray-100">{{ check.amount.toLocaleString('ar-EG') }} ج</td>
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-500">{{ new Date(check.due_date).toLocaleDateString('ar-EG') }}</td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="checkStatusConfig[check.status]?.variant ?? 'neutral'">
                    {{ checkStatusConfig[check.status]?.label ?? check.status }}
                  </AppBadge>
                </td>
                <td class="px-4 py-3">
                  <div v-if="check.status === 'received' || check.status === 'deposited'" class="flex gap-2">
                    <AppButton size="sm" @click="advanceCheck(check)">
                      {{ check.status === 'received' ? 'إيداع' : 'تحصيل' }}
                    </AppButton>
                    <AppButton size="sm" variant="danger" @click="markCheckBounced(check)">
                      مرتجع
                    </AppButton>
                  </div>
                </td>
              </tr>
              <tr v-if="checks.length === 0">
                <td colspan="6" class="px-4 py-8">
                  <EmptyState icon="🏦" title="لا توجد شيكات" />
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
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الكود</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">اسم الحساب</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">النوع</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الرصيد</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="acc in accounts" :key="acc.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3 font-mono text-sm text-gray-600 dark:text-gray-500">{{ acc.code }}</td>
                <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">{{ acc.name }}</td>
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-500">{{ acc.account_type }}</td>
                <td class="px-4 py-3 text-sm font-bold" :class="acc.balance >= 0 ? 'text-green-600' : 'text-red-500'">
                  {{ acc.balance.toLocaleString('ar-EG') }} ج
                </td>
              </tr>
              <tr v-if="accounts.length === 0">
                <td colspan="4" class="px-4 py-8">
                  <EmptyState icon="📒" title="لا توجد حسابات" />
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
          <label class="block text-xs text-gray-400 dark:text-gray-500 mb-1">من تاريخ</label>
          <input v-model="ccDateFrom" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
        </div>
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-500 mb-1">إلى تاريخ</label>
          <input v-model="ccDateTo" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
        </div>
        <AppButton size="sm" @click="loadCostCenters">تطبيق</AppButton>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <template v-else>
        <AppCard padding="none" class="mb-4">
          <div class="overflow-x-auto">
            <table class="w-full">
              <thead class="bg-stone-50 dark:bg-gray-800/60">
                <tr>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">مركز التكلفة</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الإيراد</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">المصروف</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الصافي</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="line in ccLines" :key="line.code" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                  <td class="px-4 py-3 text-sm font-bold text-gray-900 dark:text-gray-100">{{ line.name }}</td>
                  <td class="px-4 py-3 text-sm font-bold text-green-600">{{ line.revenue.toLocaleString('ar-EG') }} ج</td>
                  <td class="px-4 py-3 text-sm font-bold text-red-600">{{ line.expense.toLocaleString('ar-EG') }} ج</td>
                  <td class="px-4 py-3 text-sm font-bold" :class="line.net >= 0 ? 'text-gray-900 dark:text-gray-100' : 'text-red-700'">
                    {{ line.net.toLocaleString('ar-EG') }} ج
                  </td>
                </tr>
                <tr v-if="ccLines.length === 0">
                  <td colspan="4" class="px-4 py-8">
                    <EmptyState icon="📈" title="لا توجد بيانات في هذه الفترة" />
                  </td>
                </tr>
              </tbody>
              <tfoot v-if="ccLines.length">
                <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                  <td class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">الإجمالي</td>
                  <td class="px-4 py-3 text-sm font-black text-green-700">{{ ccTotalRevenue.toLocaleString('ar-EG') }} ج</td>
                  <td class="px-4 py-3 text-sm font-black text-red-700">{{ ccTotalExpense.toLocaleString('ar-EG') }} ج</td>
                  <td class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ ccTotalNet.toLocaleString('ar-EG') }} ج</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </AppCard>
        <p class="text-[11px] text-gray-400 dark:text-gray-500">
          الأرقام محسوبة من القيود المحاسبية الفعلية (journal_lines) الموسومة بمركز التكلفة وقت
          الترحيل — الإيراد والمصروف (تكلفة البضاعة المباعة) الاتنين، مش الإيراد بس. قيود اتُرحّلت
          قبل هذا التحديث مالهاش وسم مركز تكلفة، فمش هتظهر هنا.
        </p>
      </template>
    </div>

    <!-- Balance Sheet (الميزانية العمومية) -->
    <div v-if="tab === 'balance-sheet'">
      <div class="flex flex-wrap items-end gap-3 mb-4">
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-500 mb-1">كما في تاريخ</label>
          <input v-model="bsAsOf" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
        </div>
        <AppButton size="sm" @click="loadBalanceSheet">تطبيق</AppButton>
        <AppBadge v-if="bsData" size="sm" :variant="bsData.is_balanced ? 'success' : 'danger'">
          {{ bsData.is_balanced ? '✅ متوازنة (الأصول = الخصوم + حقوق الملكية)' : '⚠️ غير متوازنة — راجع القيود' }}
        </AppBadge>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <template v-else-if="bsData">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
          <AppCard padding="none">
            <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 font-bold text-gray-900 dark:text-gray-100">الأصول</div>
            <div class="overflow-x-auto">
              <table class="w-full">
                <tbody>
                  <tr v-for="l in bsData.asset_lines" :key="l.account_code" class="border-t border-stone-100 dark:border-border/50">
                    <td class="px-4 py-2 text-xs font-mono text-gray-500 dark:text-gray-500">{{ l.account_code }}</td>
                    <td class="px-4 py-2 text-sm text-gray-900 dark:text-gray-100">{{ l.account_name }}</td>
                    <td class="px-4 py-2 text-sm font-bold text-gray-900 dark:text-gray-100">{{ l.amount.toLocaleString('ar-EG') }} ج</td>
                  </tr>
                  <tr v-if="bsData.asset_lines.length === 0">
                    <td colspan="3" class="px-4 py-6"><EmptyState icon="🏦" title="لا توجد أصول مسجّلة حتى هذا التاريخ" /></td>
                  </tr>
                </tbody>
                <tfoot v-if="bsData.asset_lines.length">
                  <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                    <td colspan="2" class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">إجمالي الأصول</td>
                    <td class="px-4 py-3 text-sm font-black text-green-700">{{ bsData.total_assets.toLocaleString('ar-EG') }} ج</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </AppCard>

          <div class="space-y-4">
            <AppCard padding="none">
              <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 font-bold text-gray-900 dark:text-gray-100">الخصوم</div>
              <div class="overflow-x-auto">
                <table class="w-full">
                  <tbody>
                    <tr v-for="l in bsData.liability_lines" :key="l.account_code" class="border-t border-stone-100 dark:border-border/50">
                      <td class="px-4 py-2 text-xs font-mono text-gray-500 dark:text-gray-500">{{ l.account_code }}</td>
                      <td class="px-4 py-2 text-sm text-gray-900 dark:text-gray-100">{{ l.account_name }}</td>
                      <td class="px-4 py-2 text-sm font-bold text-gray-900 dark:text-gray-100">{{ l.amount.toLocaleString('ar-EG') }} ج</td>
                    </tr>
                    <tr v-if="bsData.liability_lines.length === 0">
                      <td colspan="3" class="px-4 py-6"><EmptyState icon="📋" title="لا توجد خصوم مسجّلة حتى هذا التاريخ" /></td>
                    </tr>
                  </tbody>
                  <tfoot v-if="bsData.liability_lines.length">
                    <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                      <td colspan="2" class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">إجمالي الخصوم</td>
                      <td class="px-4 py-3 text-sm font-black text-red-700">{{ bsData.total_liabilities.toLocaleString('ar-EG') }} ج</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </AppCard>

            <AppCard padding="none">
              <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 font-bold text-gray-900 dark:text-gray-100">حقوق الملكية</div>
              <div class="overflow-x-auto">
                <table class="w-full">
                  <tbody>
                    <tr v-for="l in bsData.equity_lines" :key="l.account_code" class="border-t border-stone-100 dark:border-border/50">
                      <td class="px-4 py-2 text-xs font-mono text-gray-500 dark:text-gray-500">{{ l.account_code }}</td>
                      <td class="px-4 py-2 text-sm text-gray-900 dark:text-gray-100">{{ l.account_name }}</td>
                      <td class="px-4 py-2 text-sm font-bold text-gray-900 dark:text-gray-100">{{ l.amount.toLocaleString('ar-EG') }} ج</td>
                    </tr>
                    <tr class="border-t border-stone-100 dark:border-border/50">
                      <td colspan="2" class="px-4 py-2 text-sm text-gray-700 dark:text-gray-300">أرباح محتجزة (صافي الإيراد − المصروف تراكميًا)</td>
                      <td class="px-4 py-2 text-sm font-bold text-gray-900 dark:text-gray-100">{{ bsData.retained_earnings.toLocaleString('ar-EG') }} ج</td>
                    </tr>
                  </tbody>
                  <tfoot>
                    <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                      <td colspan="2" class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">إجمالي الخصوم + حقوق الملكية</td>
                      <td class="px-4 py-3 text-sm font-black text-blue-700">{{ bsData.total_liabilities_and_equity.toLocaleString('ar-EG') }} ج</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </AppCard>
          </div>
        </div>
        <p class="text-[11px] text-gray-400 dark:text-gray-500">
          الأرقام محسوبة من أرصدة القيود المحاسبية الفعلية (journal_lines) لكل حساب حتى تاريخ "كما في"
          — نفس مصدر بيانات الحسابات ومراكز التكلفة، مش حساب موازٍ منفصل. الأرباح المحتجزة = صافي
          الإيرادات ناقص المصروفات تراكميًا (المشروع مفيهوش قيد إقفال سنوي فعلي لسه).
        </p>
      </template>
      <AppCard v-else padding="lg">
        <EmptyState icon="⚖️" title="لا تتوفر بيانات ميزانية عمومية" />
      </AppCard>
    </div>

    <!-- Depreciation -->
    <div v-if="tab === 'depreciation'">
      <AppCard class="mb-4">
        <div class="flex flex-wrap items-end gap-3">
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-500 mb-1">السنة</label>
            <input v-model.number="depYear" type="number" min="2020" max="2100"
              class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm w-28" />
          </div>
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-500 mb-1">الشهر</label>
            <input v-model.number="depMonth" type="number" min="1" max="12"
              class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm w-20" />
          </div>
          <AppButton size="sm" :loading="runningDepreciation" @click="runDepreciation">
            شغّل دورة الإهلاك
          </AppButton>
        </div>
        <div v-if="lastRunResult" class="mt-3 text-sm">
          <p class="text-green-700 font-semibold">
            ترحّل إهلاك {{ lastRunResult.entries_count }} أصل — إجمالي {{ lastRunResult.total_amount.toLocaleString('ar-EG') }} ج
          </p>
          <p v-if="lastRunResult.skipped.length" class="text-gray-400 dark:text-gray-500 text-xs mt-1">
            اتخطّى: {{ lastRunResult.skipped.join('، ') }}
          </p>
        </div>
      </AppCard>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الأصل</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الشهر</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">قيمة الإهلاك</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">مجمّع الإهلاك بعدها</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="e in depreciationEntries" :key="e.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">{{ assetsById[e.asset_id] ?? `أصل #${e.asset_id}` }}</td>
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-500">{{ e.month }}/{{ e.year }}</td>
                <td class="px-4 py-3 text-sm font-bold text-red-500">{{ Number(e.amount).toLocaleString('ar-EG') }} ج</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ Number(e.accumulated_after).toLocaleString('ar-EG') }} ج</td>
              </tr>
              <tr v-if="depreciationEntries.length === 0">
                <td colspan="4" class="px-4 py-8">
                  <EmptyState icon="📉" title="لا توجد قيود إهلاك بعد" subtitle="شغّل دورة الإهلاك أعلاه لأول مرة" />
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
          {{ showBankAccountForm ? 'إلغاء' : '+ حساب بنكي جديد' }}
        </AppButton>
      </div>

      <AppCard v-if="showBankAccountForm" class="mb-4">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input v-model="bankAccountForm.bank_name" type="text" placeholder="اسم البنك"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="bankAccountForm.account_name" type="text" placeholder="اسم الحساب (اختياري)"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="bankAccountForm.account_number" type="text" placeholder="رقم الحساب"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="bankAccountForm.opening_balance" type="number" step="0.01" placeholder="الرصيد الافتتاحي"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        </div>
        <AppButton class="mt-3" size="sm" @click="createBankAccount">حفظ الحساب</AppButton>
      </AppCard>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <EmptyState v-else-if="bankAccounts.length === 0" icon="🏦" title="لا توجد حسابات بنكية بعد" />
      <template v-else>
        <div v-if="reconciliationSummary" class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <AppCard padding="md" class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">رصيد الدفاتر</div>
            <div class="text-lg font-black text-gray-900 dark:text-gray-100">{{ reconciliationSummary.book_balance.toLocaleString('ar-EG') }}</div>
          </AppCard>
          <AppCard padding="md" class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">رصيد كشف الحساب</div>
            <div class="text-lg font-black text-gray-900 dark:text-gray-100">{{ reconciliationSummary.statement_balance.toLocaleString('ar-EG') }}</div>
          </AppCard>
          <AppCard padding="md" class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">الفرق</div>
            <div :class="['text-lg font-black', reconciliationSummary.is_reconciled ? 'text-green-600' : 'text-amber-600']">
              {{ reconciliationSummary.difference.toLocaleString('ar-EG') }}
            </div>
          </AppCard>
          <AppCard padding="md" class="text-center">
            <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">الحالة</div>
            <AppBadge :variant="reconciliationSummary.is_reconciled ? 'success' : 'warning'">
              {{ reconciliationSummary.is_reconciled ? 'متطابقة ✓' : 'غير متطابقة' }}
            </AppBadge>
          </AppCard>
        </div>

        <div class="flex justify-end mb-3">
          <AppButton size="sm" :loading="matchingInProgress" @click="runAutoMatch">
            مطابقة تلقائية محافظة
          </AppButton>
        </div>

        <AppCard padding="none">
          <div class="overflow-x-auto">
            <table class="w-full">
              <thead class="bg-stone-50 dark:bg-gray-800/60">
                <tr>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">التاريخ</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الوصف</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">المبلغ</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الحالة</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="line in statementLines" :key="line.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                  <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-500">{{ line.line_date }}</td>
                  <td class="px-4 py-3 text-sm text-gray-900 dark:text-gray-100">{{ line.description }}</td>
                  <td class="px-4 py-3 text-sm font-bold" :class="line.amount >= 0 ? 'text-green-600' : 'text-red-500'">
                    {{ Number(line.amount).toLocaleString('ar-EG') }}
                  </td>
                  <td class="px-4 py-3">
                    <AppBadge size="sm" :variant="statementLineStatusConfig[line.status]?.variant ?? 'neutral'">
                      {{ statementLineStatusConfig[line.status]?.label ?? line.status }}
                    </AppBadge>
                  </td>
                </tr>
                <tr v-if="statementLines.length === 0">
                  <td colspan="4" class="px-4 py-8">
                    <EmptyState icon="📄" title="لا توجد سطور كشف حساب" />
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
          <button v-for="s in [{ v: 'all', l: 'الكل' }, { v: 'open', l: 'مفتوحة' }, { v: 'closed', l: 'مقفولة' }]"
            :key="s.v" @click="shiftStatus = s.v as any; loadShifts()"
            :class="['px-3 py-1 rounded-lg text-xs font-semibold transition-all', shiftStatus === s.v ? 'bg-white dark:bg-surface shadow-sm text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-500']">
            {{ s.l }}
          </button>
        </div>
        <!-- فلتر "فرق > 0" (S-05) -->
        <button
          @click="shiftVarianceOnly = !shiftVarianceOnly"
          :class="['px-3 py-1 rounded-lg text-xs font-semibold border transition-all',
            shiftVarianceOnly ? 'bg-amber-500 border-amber-500 text-white' : 'bg-white dark:bg-surface border-stone-200 dark:border-border text-gray-500']"
        >⚠️ فرق &gt; 0 فقط</button>
        <!-- spinner أثناء التحميل -->
        <AppSpinner v-if="loadingShifts" size="sm" />
        <span class="text-xs text-gray-400 dark:text-gray-500">إجمالي: {{ shiftsTotal }} — معروض: {{ filteredShifts.length }}</span>
        <button @click="loadShifts()" class="ms-auto px-3 py-1 rounded-lg text-xs font-semibold border border-stone-200 dark:border-border bg-white dark:bg-surface text-gray-500 dark:text-gray-500 hover:bg-stone-50 dark:bg-gray-800/60 transition-all">🔄 تحديث</button>
      </div>
      <div class="overflow-x-auto rounded-xl border border-stone-200 dark:border-border">
        <table class="w-full text-sm">
          <thead class="bg-stone-50 dark:bg-gray-800/60 text-xs text-gray-500 dark:text-gray-500 uppercase">
            <tr>
              <th class="px-4 py-3 text-right">#</th>
              <th class="px-4 py-3 text-right">كاشير</th>
              <th class="px-4 py-3 text-right">فُتحت</th>
              <th class="px-4 py-3 text-right">أُغلقت</th>
              <th class="px-4 py-3 text-right">الحالة</th>
              <th class="px-4 py-3 text-right">متوقع</th>
              <th class="px-4 py-3 text-right">معدود</th>
              <th class="px-4 py-3 text-right">الفرق</th>
              <th class="px-4 py-3 text-right">PDF</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-stone-100">
            <tr
              v-for="s in filteredShifts" :key="s.id"
              class="hover:bg-stone-50 dark:bg-gray-800/60 transition-colors cursor-pointer"
              @click="openShiftDetail(s)"
            >
              <td class="px-4 py-3 font-mono text-gray-500 dark:text-gray-500">#{{ s.id }}</td>
              <td class="px-4 py-3 font-semibold">{{ s.cashier_id }}</td>
              <td class="px-4 py-3 text-gray-600 dark:text-gray-500 text-xs">
                {{ new Date(s.opened_at).toLocaleString('ar-EG', { dateStyle: 'short', timeStyle: 'short' }) }}
              </td>
              <td class="px-4 py-3 text-gray-500 dark:text-gray-500 text-xs">
                {{ s.closed_at ? new Date(s.closed_at).toLocaleString('ar-EG', { dateStyle: 'short', timeStyle: 'short' }) : '—' }}
              </td>
              <td class="px-4 py-3">
                <span :class="['px-2 py-0.5 rounded-full text-xs font-bold',
                  s.status === 'open' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600']">
                  {{ s.status === 'open' ? 'مفتوحة' : 'مقفولة' }}
                </span>
                <span v-if="s.reconciliation_warning" class="mr-1 text-red-500 cursor-help"
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
                  class="text-xs text-blue-600 hover:underline font-semibold">📄 PDF</a>
                <span v-else class="text-gray-300 text-xs">—</span>
              </td>
            </tr>
            <tr v-if="!filteredShifts.length">
              <td colspan="9" class="px-4 py-12 text-center text-gray-400 dark:text-gray-500">لا توجد ورديات</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Shift drill-down (S-05) — تقرير كامل + سجل فواتير لوردية واحدة -->
    <AppModal :open="!!detailShift" :title="`تفاصيل وردية #${detailShift?.id ?? ''}`" size="lg" @close="closeShiftDetail">
      <div v-if="detailLoading" class="flex justify-center py-10"><AppSpinner size="lg" /></div>
      <div v-else-if="detailReport" dir="rtl" class="space-y-4">

        <!-- KPIs رئيسية -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div class="bg-emerald-50 dark:bg-emerald-900/20 rounded-xl p-3 text-center border border-emerald-100 dark:border-emerald-800/40">
            <div class="text-lg font-black text-emerald-700 dark:text-emerald-400">{{ detailReport.total_sales.toFixed(2) }}</div>
            <div class="text-xs text-emerald-600 dark:text-emerald-500 mt-0.5">إجمالي المبيعات</div>
          </div>
          <div class="bg-blue-50 dark:bg-blue-900/20 rounded-xl p-3 text-center border border-blue-100 dark:border-blue-800/40">
            <div class="text-lg font-black text-blue-700 dark:text-blue-400">{{ detailReport.total_cash.toFixed(2) }}</div>
            <div class="text-xs text-blue-600 dark:text-blue-500 mt-0.5">كاش</div>
          </div>
          <div class="bg-purple-50 dark:bg-purple-900/20 rounded-xl p-3 text-center border border-purple-100 dark:border-purple-800/40">
            <div class="text-lg font-black text-purple-700 dark:text-purple-400">{{ detailReport.total_card.toFixed(2) }}</div>
            <div class="text-xs text-purple-600 dark:text-purple-500 mt-0.5">كارت</div>
          </div>
          <div class="rounded-xl p-3 text-center border" :class="shiftVarianceClass(detailShift?.variance).includes('red') ? 'bg-red-50 dark:bg-red-900/20 border-red-100 dark:border-red-800/40' : 'bg-stone-50 dark:bg-gray-800/60 border-stone-200 dark:border-border'">
            <div class="text-lg font-black" :class="shiftVarianceClass(detailShift?.variance)">
              {{ detailShift?.variance != null ? (detailShift.variance > 0 ? '+' : '') + detailShift.variance.toFixed(2) : '—' }}
            </div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">الفرق</div>
          </div>
        </div>

        <!-- KPIs إضافية — آجل + أخرى + ملغاة -->
        <div v-if="detailReport.total_credit > 0 || detailReport.total_other > 0 || detailReport.voided_count > 0"
          class="grid grid-cols-3 gap-2">
          <div v-if="detailReport.total_credit > 0" class="bg-stone-50 dark:bg-gray-800/60 rounded-lg p-2.5 text-center border border-stone-200 dark:border-border">
            <div class="text-sm font-bold text-gray-700 dark:text-gray-300">{{ detailReport.total_credit.toFixed(2) }} ج</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">📝 آجل</div>
          </div>
          <div v-if="detailReport.total_other > 0" class="bg-stone-50 dark:bg-gray-800/60 rounded-lg p-2.5 text-center border border-stone-200 dark:border-border">
            <div class="text-sm font-bold text-gray-700 dark:text-gray-300">{{ detailReport.total_other.toFixed(2) }} ج</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">🔄 أخرى</div>
          </div>
          <div v-if="detailReport.voided_count > 0" class="bg-red-50 dark:bg-red-900/20 rounded-lg p-2.5 text-center border border-red-100 dark:border-red-800/40">
            <div class="text-sm font-bold text-red-600 dark:text-red-400">
              {{ detailReport.voided_count }} ({{ detailReport.voided_amount.toFixed(2) }} ج)
            </div>
            <div class="text-xs text-red-500 dark:text-red-400 mt-0.5">❌ ملغاة</div>
          </div>
        </div>

        <!-- ملخص العملات الأجنبية -->
        <div v-if="detailReport.foreign_currency_summary?.length">
          <h3 class="text-xs font-bold text-gray-400 dark:text-gray-500 uppercase mb-1.5">🌍 عملات أجنبية</h3>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-1.5 text-xs">
            <div v-for="fc in detailReport.foreign_currency_summary" :key="fc.currency"
              class="bg-amber-50 dark:bg-amber-900/20 rounded-lg px-2 py-1.5 border border-amber-100 dark:border-amber-800/40 flex justify-between">
              <span class="text-gray-600 dark:text-gray-400">
                {{ fc.total_foreign.toFixed(2) }} {{ fc.currency }}
                <span class="text-gray-400 dark:text-gray-500"> × {{ fc.fx_rate }}</span>
              </span>
              <span class="font-semibold text-amber-700 dark:text-amber-400">{{ fc.egp_equivalent.toFixed(2) }} ج</span>
            </div>
          </div>
          <div v-if="detailReport.counted_cash_egp != null" class="mt-1.5 text-xs text-end text-gray-500 dark:text-gray-400">
            إجمالي العدّ بالجنيه: <span class="font-bold text-gray-700 dark:text-gray-300">{{ detailReport.counted_cash_egp.toFixed(2) }} ج</span>
          </div>
        </div>

        <!-- عدّ الكاش بالفئة -->
        <div v-if="detailReport.cash_count.length">
          <h3 class="text-xs font-bold text-gray-400 dark:text-gray-500 uppercase mb-1.5">عدّ الكاش بالفئة</h3>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-1.5 text-xs">
            <div v-for="(line, i) in detailReport.cash_count" :key="i"
              class="bg-stone-50 dark:bg-gray-800/60 rounded-lg px-2 py-1.5 flex justify-between">
              <span class="text-gray-600 dark:text-gray-400">{{ line.denomination }} {{ line.currency }} × {{ line.quantity }}</span>
              <span class="font-semibold text-gray-800 dark:text-gray-200">{{ line.egp_equivalent.toFixed(2) }} ج</span>
            </div>
          </div>
        </div>

        <!-- سجل الفواتير -->
        <div>
          <h3 class="text-xs font-bold text-gray-400 dark:text-gray-500 uppercase mb-1.5">
            الفواتير ({{ detailInvoices.length }})
          </h3>
          <EmptyState v-if="!detailInvoices.length" title="مفيش فواتير في الوردية دي" />
          <div v-else class="divide-y divide-stone-100 dark:divide-border/50 max-h-64 overflow-y-auto">
            <div v-for="inv in detailInvoices" :key="inv.payment_id"
              class="py-2 flex items-center justify-between gap-2" :class="inv.is_voided && 'opacity-50'">
              <div>
                <span class="text-sm font-semibold text-gray-800 dark:text-gray-200" :class="inv.is_voided && 'line-through'">{{ inv.guest_name }}</span>
                <span class="text-xs text-gray-400 dark:text-gray-500 mr-2">{{ METHOD_LABEL[inv.method] ?? inv.method }}</span>
              </div>
              <span class="text-sm font-bold" :class="inv.is_voided ? 'text-gray-400 dark:text-gray-500 line-through' : 'text-blue-700 dark:text-blue-400'">{{ inv.amount.toFixed(2) }} ج</span>
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
            <AppButton variant="outline" block>📄 تحميل PDF</AppButton>
          </a>
          <AppButton variant="ghost" :block="detailShift?.status !== 'closed'" @click="closeShiftDetail">إغلاق</AppButton>
        </div>
      </template>
    </AppModal>

  </div>
</template>
