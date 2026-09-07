<script setup lang="ts">
// إذن قبض عام (Cash Receipt) — استُخرج من FinanceView.vue (تقسيم الملفات
// الكبيرة، 2026-09-07). accounts هنا نسخة محلية مستقلة (نفس نمط تكرار
// الجلب المتبع في باقي التابات المُستخرجة).
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppButton, AppCard, AppBadge, AppModal, AppSpinner, EmptyState, useToast } from '@resort-os/ui'
import StepUpConfirmModal from '../StepUpConfirmModal.vue'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface Account { id: number; code: string; name: string; account_type: string; balance: number }
interface CashReceiptRow {
  id: number; receipt_date: string; amount: number; description: string
  reference: string | null
  destination_account_code: string; destination_account_name: string
  source_account_code: string
  voided_at: string | null
}

const toast = useToast()
const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const branchId = computed(() => props.branchId)

const today = new Date().toISOString().slice(0, 10)
const firstOfMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().slice(0, 10)

const accounts = ref<Account[]>([])
const settlementAccountOptions = computed(() => accounts.value.filter(a => a.account_type === 'asset'))
async function loadAccounts() {
  if (accounts.value.length) return
  try {
    const res = await api.get(ENDPOINTS.finance.accounts, { params: { branch_id: branchId.value } })
    accounts.value = res.data.accounts ?? res.data.items ?? res.data
  } catch { /* لا يمنع عرض جدول إذونات القبض، بس القوائم المنسدلة هتفضل فاضية */ }
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
  loadAccounts()
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

onMounted(loadCashReceipts)
</script>

<template>
  <div class="space-y-4">
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
