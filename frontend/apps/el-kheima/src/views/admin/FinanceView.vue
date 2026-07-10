<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const toast = useToast()
const { confirm } = useConfirm()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')
const tab = ref<'overview' | 'checks' | 'accounts' | 'cost-centers' | 'depreciation' | 'bank-reconciliation' | 'shifts'>('overview')

interface Check { id: number; check_number: string; amount: number; drawer_name: string; due_date: string; status: string; bank_name: string }
interface Account { id: number; code: string; name: string; account_type: string; balance: number }
interface CostCenterLine { code: string; name: string; revenue: number; source: 'ledger' | 'direct' }
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

async function loadShifts() {
  try {
    const params: Record<string, unknown> = { branch_id: branchId, page: 1, size: 30 }
    if (shiftStatus.value !== 'all') params.status = shiftStatus.value
    const { data } = await api.get('/api/v1/finance/shifts', { params })
    shifts.value      = data.items ?? []
    shiftsTotal.value = data.total ?? 0
  } catch(e) { console.error(e) }
}

function shiftVarianceClass(v?: number | null) {
  if (v == null) return 'text-gray-400'
  if (Math.abs(v) <= 50) return 'text-green-600 font-bold'
  return v > 0 ? 'text-blue-600 font-bold' : 'text-red-600 font-bold'
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
      api.get('/api/v1/finance/depreciation/entries', { params: { branch_id: branchId, size: 100 } }),
      api.get('/api/v1/maintenance/assets', { params: { branch_id: branchId, size: 200 } }),
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
    const { data } = await api.post('/api/v1/finance/depreciation/run', {
      branch_id: branchId, year: depYear.value, month: depMonth.value,
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
    const { data } = await api.get('/api/v1/finance/bank-accounts', { params: { branch_id: branchId } })
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
      api.get(`/api/v1/finance/bank-accounts/${selectedBankAccountId.value}/statement-lines`, {
        params: { size: 100 },
      }),
      api.get(`/api/v1/finance/bank-accounts/${selectedBankAccountId.value}/reconciliation-summary`, {
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
    await api.post('/api/v1/finance/bank-accounts', {
      branch_id: branchId,
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
      `/api/v1/finance/bank-accounts/${selectedBankAccountId.value}/statement-lines/auto-match`,
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
const ccTotal = ref(0)

async function loadCostCenters() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/finance/cost-centers/report', {
      params: { branch_id: branchId, date_from: ccDateFrom.value, date_to: ccDateTo.value },
    })
    ccLines.value = res.data.lines ?? []
    ccTotal.value = res.data.total_revenue ?? 0
  } catch { toast.error('تعذّر تحميل مراكز التكلفة — حاول تاني') }
  finally { loading.value = false }
}

const checkStatusConfig: Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }> = {
  received:  { label: 'مستلم',   variant: 'neutral' },
  deposited: { label: 'مودع',    variant: 'info' },
  cleared:   { label: 'محصل',    variant: 'success' },
  bounced:   { label: 'مرتجع',   variant: 'danger' },
}

async function loadTab(t: typeof tab.value) {
  tab.value = t
  if (t === 'shifts') await loadShifts()
  if (t === 'depreciation') { await loadDepreciation(); return }
  if (t === 'bank-reconciliation') { await loadBankAccounts(); return }

  loading.value = true
  try {
    if (t === 'overview') {
      const res = await api.get('/api/v1/finance/reports/income-statement', {
        params: { branch_id: branchId, date_from: firstOfMonth, date_to: today },
      })
      financeData.value = {
        total_revenue: Number(res.data.total_revenue),
        total_expense: Number(res.data.total_expense),
        net_income: Number(res.data.net_income),
      }
    } else if (t === 'checks') {
      const res = await api.get('/api/v1/finance/checks', { params: { branch_id: branchId } })
      checks.value = res.data.checks ?? res.data.items ?? res.data
    } else if (t === 'accounts') {
      const res = await api.get('/api/v1/finance/accounts', { params: { branch_id: branchId } })
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
    await api.patch(`/api/v1/finance/checks/${check.id}/status`, { to_status: next })
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
    await api.patch(`/api/v1/finance/checks/${check.id}/status`, {
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
    <h2 class="text-2xl font-black text-gray-900 mb-6">المالية</h2>

    <div class="flex gap-1 bg-stone-100 p-1 rounded-xl mb-6 w-fit">
      <button v-for="t in [{ val: 'overview', label: 'نظرة عامة' }, { val: 'checks', label: 'الشيكات' }, { val: 'accounts', label: 'الحسابات' }, { val: 'cost-centers', label: 'مراكز التكلفة' }, { val: 'depreciation', label: 'إهلاك الأصول' }, { val: 'bank-reconciliation', label: 'التسوية البنكية' }, { val: 'shifts', label: 'الورديات' }]"
        :key="t.val" @click="loadTab(t.val as any)"
        :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all', tab === t.val ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700']"
      >{{ t.label }}</button>
    </div>

    <!-- Overview -->
    <div v-if="tab === 'overview'">
      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <div v-else-if="financeData" class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <AppCard padding="lg" class="text-center">
          <div class="text-sm text-gray-500 mb-2">إجمالي الإيرادات</div>
          <div class="text-3xl font-black text-green-600">{{ financeData.total_revenue.toLocaleString('ar-EG') }}</div>
          <div class="text-xs text-gray-400 mt-1">جنيه</div>
        </AppCard>
        <AppCard padding="lg" class="text-center">
          <div class="text-sm text-gray-500 mb-2">إجمالي المصروفات</div>
          <div class="text-3xl font-black text-red-500">{{ financeData.total_expense.toLocaleString('ar-EG') }}</div>
          <div class="text-xs text-gray-400 mt-1">جنيه</div>
        </AppCard>
        <AppCard padding="lg" class="text-center">
          <div class="text-sm text-gray-500 mb-2">صافي الربح</div>
          <div :class="['text-3xl font-black', financeData.net_income >= 0 ? 'text-blue-700' : 'text-red-500']">
            {{ financeData.net_income.toLocaleString('ar-EG') }}
          </div>
          <div class="text-xs text-gray-400 mt-1">جنيه</div>
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
            <thead class="bg-stone-50">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">رقم الشيك</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الساحب</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">المبلغ</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">تاريخ الاستحقاق</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الحالة</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">إجراء</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="check in checks" :key="check.id" class="border-t border-stone-100 hover:bg-stone-50">
                <td class="px-4 py-3 font-mono text-sm text-gray-900">{{ check.check_number }}</td>
                <td class="px-4 py-3 text-sm text-gray-700">{{ check.drawer_name }}</td>
                <td class="px-4 py-3 text-sm font-bold text-gray-900">{{ check.amount.toLocaleString('ar-EG') }} ج</td>
                <td class="px-4 py-3 text-sm text-gray-600">{{ new Date(check.due_date).toLocaleDateString('ar-EG') }}</td>
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
            <thead class="bg-stone-50">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الكود</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">اسم الحساب</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">النوع</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الرصيد</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="acc in accounts" :key="acc.id" class="border-t border-stone-100 hover:bg-stone-50">
                <td class="px-4 py-3 font-mono text-sm text-gray-600">{{ acc.code }}</td>
                <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ acc.name }}</td>
                <td class="px-4 py-3 text-sm text-gray-600">{{ acc.account_type }}</td>
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
          <label class="block text-xs text-gray-400 mb-1">من تاريخ</label>
          <input v-model="ccDateFrom" type="date" class="border border-stone-200 rounded-lg px-3 py-1.5 text-sm" />
        </div>
        <div>
          <label class="block text-xs text-gray-400 mb-1">إلى تاريخ</label>
          <input v-model="ccDateTo" type="date" class="border border-stone-200 rounded-lg px-3 py-1.5 text-sm" />
        </div>
        <AppButton size="sm" @click="loadCostCenters">تطبيق</AppButton>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <template v-else>
        <AppCard padding="none" class="mb-4">
          <div class="overflow-x-auto">
            <table class="w-full">
              <thead class="bg-stone-50">
                <tr>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">مركز التكلفة</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الإيراد</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">المصدر</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="line in ccLines" :key="line.code" class="border-t border-stone-100 hover:bg-stone-50">
                  <td class="px-4 py-3 text-sm font-bold text-gray-900">{{ line.name }}</td>
                  <td class="px-4 py-3 text-sm font-bold text-green-600">{{ line.revenue.toLocaleString('ar-EG') }} ج</td>
                  <td class="px-4 py-3">
                    <span :class="['px-2 py-0.5 rounded-full text-[10px] font-bold',
                                   line.source === 'ledger' ? 'bg-blue-100 text-blue-700' : 'bg-amber-100 text-amber-700']">
                      {{ line.source === 'ledger' ? 'دفتر اليومية' : 'مباشر' }}
                    </span>
                  </td>
                </tr>
                <tr v-if="ccLines.length === 0">
                  <td colspan="3" class="px-4 py-8">
                    <EmptyState icon="📈" title="لا توجد بيانات في هذه الفترة" />
                  </td>
                </tr>
              </tbody>
              <tfoot v-if="ccLines.length">
                <tr class="border-t-2 border-stone-200 bg-stone-50">
                  <td class="px-4 py-3 text-sm font-black text-gray-900">الإجمالي</td>
                  <td class="px-4 py-3 text-sm font-black text-gray-900">{{ ccTotal.toLocaleString('ar-EG') }} ج</td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </div>
        </AppCard>
        <p class="text-[11px] text-gray-400">
          "دفتر اليومية" = محسوب من القيود المحاسبية الفعلية. "مباشر" = محسوب من جداول العمليات
          لأن الموديول ده لسه ميرحّلش لدفتر اليومية.
        </p>
      </template>
    </div>

    <!-- Depreciation -->
    <div v-if="tab === 'depreciation'">
      <AppCard class="mb-4">
        <div class="flex flex-wrap items-end gap-3">
          <div>
            <label class="block text-xs text-gray-400 mb-1">السنة</label>
            <input v-model.number="depYear" type="number" min="2020" max="2100"
              class="border border-stone-200 rounded-lg px-3 py-1.5 text-sm w-28" />
          </div>
          <div>
            <label class="block text-xs text-gray-400 mb-1">الشهر</label>
            <input v-model.number="depMonth" type="number" min="1" max="12"
              class="border border-stone-200 rounded-lg px-3 py-1.5 text-sm w-20" />
          </div>
          <AppButton size="sm" :loading="runningDepreciation" @click="runDepreciation">
            شغّل دورة الإهلاك
          </AppButton>
        </div>
        <div v-if="lastRunResult" class="mt-3 text-sm">
          <p class="text-green-700 font-semibold">
            ترحّل إهلاك {{ lastRunResult.entries_count }} أصل — إجمالي {{ lastRunResult.total_amount.toLocaleString('ar-EG') }} ج
          </p>
          <p v-if="lastRunResult.skipped.length" class="text-gray-400 text-xs mt-1">
            اتخطّى: {{ lastRunResult.skipped.join('، ') }}
          </p>
        </div>
      </AppCard>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الأصل</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الشهر</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">قيمة الإهلاك</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">مجمّع الإهلاك بعدها</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="e in depreciationEntries" :key="e.id" class="border-t border-stone-100 hover:bg-stone-50">
                <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ assetsById[e.asset_id] ?? `أصل #${e.asset_id}` }}</td>
                <td class="px-4 py-3 text-sm text-gray-600">{{ e.month }}/{{ e.year }}</td>
                <td class="px-4 py-3 text-sm font-bold text-red-500">{{ Number(e.amount).toLocaleString('ar-EG') }} ج</td>
                <td class="px-4 py-3 text-sm text-gray-700">{{ Number(e.accumulated_after).toLocaleString('ar-EG') }} ج</td>
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
          class="border border-stone-200 rounded-lg px-3 py-1.5 text-sm">
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
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="bankAccountForm.account_name" type="text" placeholder="اسم الحساب (اختياري)"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="bankAccountForm.account_number" type="text" placeholder="رقم الحساب"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="bankAccountForm.opening_balance" type="number" step="0.01" placeholder="الرصيد الافتتاحي"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
        </div>
        <AppButton class="mt-3" size="sm" @click="createBankAccount">حفظ الحساب</AppButton>
      </AppCard>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <EmptyState v-else-if="bankAccounts.length === 0" icon="🏦" title="لا توجد حسابات بنكية بعد" />
      <template v-else>
        <div v-if="reconciliationSummary" class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <AppCard padding="md" class="text-center">
            <div class="text-xs text-gray-400 mb-1">رصيد الدفاتر</div>
            <div class="text-lg font-black text-gray-900">{{ reconciliationSummary.book_balance.toLocaleString('ar-EG') }}</div>
          </AppCard>
          <AppCard padding="md" class="text-center">
            <div class="text-xs text-gray-400 mb-1">رصيد كشف الحساب</div>
            <div class="text-lg font-black text-gray-900">{{ reconciliationSummary.statement_balance.toLocaleString('ar-EG') }}</div>
          </AppCard>
          <AppCard padding="md" class="text-center">
            <div class="text-xs text-gray-400 mb-1">الفرق</div>
            <div :class="['text-lg font-black', reconciliationSummary.is_reconciled ? 'text-green-600' : 'text-amber-600']">
              {{ reconciliationSummary.difference.toLocaleString('ar-EG') }}
            </div>
          </AppCard>
          <AppCard padding="md" class="text-center">
            <div class="text-xs text-gray-400 mb-1">الحالة</div>
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
              <thead class="bg-stone-50">
                <tr>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">التاريخ</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الوصف</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">المبلغ</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الحالة</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="line in statementLines" :key="line.id" class="border-t border-stone-100 hover:bg-stone-50">
                  <td class="px-4 py-3 text-sm text-gray-600">{{ line.line_date }}</td>
                  <td class="px-4 py-3 text-sm text-gray-900">{{ line.description }}</td>
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
        <div class="flex gap-1 bg-stone-100 p-1 rounded-xl">
          <button v-for="s in [{ v: 'all', l: 'الكل' }, { v: 'open', l: 'مفتوحة' }, { v: 'closed', l: 'مقفولة' }]"
            :key="s.v" @click="shiftStatus = s.v as any; loadShifts()"
            :class="['px-3 py-1 rounded-lg text-xs font-semibold transition-all', shiftStatus === s.v ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500']">
            {{ s.l }}
          </button>
        </div>
        <span class="text-xs text-gray-400">إجمالي: {{ shiftsTotal }}</span>
      </div>
      <div class="overflow-x-auto rounded-xl border border-stone-200">
        <table class="w-full text-sm">
          <thead class="bg-stone-50 text-xs text-gray-500 uppercase">
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
            <tr v-for="s in shifts" :key="s.id" class="hover:bg-stone-50 transition-colors">
              <td class="px-4 py-3 font-mono text-gray-500">#{{ s.id }}</td>
              <td class="px-4 py-3 font-semibold">{{ s.cashier_id }}</td>
              <td class="px-4 py-3 text-gray-600 text-xs">
                {{ new Date(s.opened_at).toLocaleString('ar-EG', { dateStyle: 'short', timeStyle: 'short' }) }}
              </td>
              <td class="px-4 py-3 text-gray-500 text-xs">
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
              <td class="px-4 py-3 text-gray-700">{{ s.expected_cash?.toFixed(2) ?? '—' }}</td>
              <td class="px-4 py-3 text-gray-700">{{ s.counted_cash?.toFixed(2) ?? '—' }}</td>
              <td class="px-4 py-3" :class="shiftVarianceClass(s.variance)">
                {{ s.variance != null ? (s.variance > 0 ? '+' : '') + s.variance.toFixed(2) : '—' }}
              </td>
              <td class="px-4 py-3">
                <a v-if="s.status === 'closed'"
                  :href="`/api/v1/finance/shifts/${s.id}/report/pdf`"
                  target="_blank"
                  class="text-xs text-blue-600 hover:underline font-semibold">📄 PDF</a>
                <span v-else class="text-gray-300 text-xs">—</span>
              </td>
            </tr>
            <tr v-if="!shifts.length">
              <td colspan="9" class="px-4 py-12 text-center text-gray-400">لا توجد ورديات</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

  </div>
</template>
