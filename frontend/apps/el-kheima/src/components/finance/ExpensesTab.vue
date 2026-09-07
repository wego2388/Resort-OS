<script setup lang="ts">
// سند مصروفات بفئة (حساب 5xxx) — استُخرج من FinanceView.vue (تقسيم
// الملفات الكبيرة، 2026-09-07). accounts هنا نسخة محلية مستقلة (نفس نمط
// تكرار الجلب المتبع في باقي التابات المُستخرجة).
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppButton, AppCard, AppBadge, AppModal, AppSpinner, EmptyState, useToast } from '@resort-os/ui'
import PinGuardModal from '../PinGuardModal.vue'
import StepUpConfirmModal from '../StepUpConfirmModal.vue'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface Account { id: number; code: string; name: string; account_type: string; balance: number }
interface ExpenseRow {
  id: number; expense_date: string; amount: number; description: string
  reference: string | null; expense_account_code: string; expense_account_name: string
  settlement_account_code: string
  payment_status: 'paid' | 'unpaid' | 'partial'; amount_paid: number
  voided_at: string | null
}

const toast = useToast()
const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const branchId = computed(() => props.branchId)

const today = new Date().toISOString().slice(0, 10)
const firstOfMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().slice(0, 10)

const accounts = ref<Account[]>([])
const expenseAccountOptions = computed(() => accounts.value.filter(a => a.account_type === 'expense'))
const settlementAccountOptions = computed(() => accounts.value.filter(a => a.account_type === 'asset'))
async function loadAccounts() {
  if (accounts.value.length) return
  try {
    const res = await api.get(ENDPOINTS.finance.accounts, { params: { branch_id: branchId.value } })
    accounts.value = res.data.accounts ?? res.data.items ?? res.data
  } catch { /* لا يمنع عرض جدول المصروفات، بس القوائم المنسدلة في المودالات هتفضل فاضية */ }
}

const expenses = ref<ExpenseRow[]>([])
const expensesTotal = ref(0)
const expensesPage = ref(1)
const expensesDateFrom = ref(firstOfMonth)
const expensesDateTo = ref(today)
const expensesLoading = ref(false)

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
  loadAccounts()
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
  loadAccounts()
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

onMounted(loadExpenses)
</script>

<template>
  <div class="space-y-4">
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
  </div>
</template>
