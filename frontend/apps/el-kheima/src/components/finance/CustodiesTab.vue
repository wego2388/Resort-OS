<script setup lang="ts">
// العهدة (Custody / imprest advance) — استُخرج من FinanceView.vue (تقسيم
// الملفات الكبيرة، 2026-09-07). accounts هنا نسخة محلية مستقلة (نفس نمط
// تكرار الجلب المتبع في باقي التابات المُستخرجة).
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppButton, AppCard, AppBadge, AppModal, AppSpinner, EmptyState, useToast } from '@resort-os/ui'
import StepUpConfirmModal from '../StepUpConfirmModal.vue'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface Account { id: number; code: string; name: string; account_type: string; balance: number }
interface CustodyRow {
  id: number; holder_name: string; purpose: string; amount: number
  disbursed_date: string; status: 'open' | 'settled'
  returned_amount: number; voided_at: string | null
}
interface SettleLineForm { expenseAccountId: number | null; amount: string; description: string }

const toast = useToast()
const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const branchId = computed(() => props.branchId)

const today = new Date().toISOString().slice(0, 10)

const accounts = ref<Account[]>([])
const custodyAssetAccountOptions = computed(() => accounts.value.filter(a => a.account_type === 'asset'))
const expenseAccountOptions = computed(() => accounts.value.filter(a => a.account_type === 'expense'))
async function loadAccounts() {
  if (accounts.value.length) return
  try {
    const res = await api.get(ENDPOINTS.finance.accounts, { params: { branch_id: branchId.value } })
    accounts.value = res.data.accounts ?? res.data.items ?? res.data
  } catch { /* لا يمنع عرض جدول العُهد، بس القوائم المنسدلة في المودالات هتفضل فاضية */ }
}

const custodies = ref<CustodyRow[]>([])
const custodiesTotal = ref(0)
const custodiesPage = ref(1)
const custodiesLoading = ref(false)

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
  loadAccounts()
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

const settleCustodyModal = reactive({
  open: false, saving: false, error: '',
  custodyId: null as number | null, custodyAmount: 0, settlementDate: today,
  lines: [{ expenseAccountId: null, amount: '', description: '' }] as SettleLineForm[],
  returnedAmount: '0',
})
function openSettleCustodyModal(c: CustodyRow) {
  loadAccounts()
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

onMounted(loadCustodies)
</script>

<template>
  <div class="space-y-4">
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
  </div>
</template>
