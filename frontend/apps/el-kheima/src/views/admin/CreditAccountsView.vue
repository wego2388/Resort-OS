<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppBadge, AppButton, AppCard, AppInput, AppModal, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

interface CreditAccount {
  id: number
  holder_type: 'customer' | 'employee'
  customer_id: number | null
  employee_id: number | null
  holder_name: string
  credit_limit: string
  current_balance: string
  available_credit: string | null
  status: 'active' | 'suspended' | 'closed'
  notes: string | null
  updated_at: string
}

interface CreditTransaction {
  id: number
  txn_type: 'charge' | 'payment' | 'refund' | 'reversal'
  amount: string
  balance_delta: string
  payment_method: string | null
  ref_order_id: number | null
  ref_beach_tx_id: number | null
  reversed_txn_id: number | null
  notes: string | null
  recorded_by_name: string
  journal_entry_id: number
  created_at: string
}

interface Statement {
  account: CreditAccount
  transactions: CreditTransaction[]
  total_charges: string
  total_payments: string
  total_refunds: string
  net_movement: string
}

const { t } = useI18n()
const toast = useToast()
const auth = useAuthStore()
const { formatMoney, formatDateTime } = useStaffFormat()
const accounts = ref<CreditAccount[]>([])
const total = ref(0)
const page = ref(1)
const size = 30
const loading = ref(false)
const statusFilter = ref('')
const holderFilter = ref('')
const selected = ref<CreditAccount | null>(null)
const statement = ref<Statement | null>(null)
const detailLoading = ref(false)

const showOpen = ref(false)
const openBusy = ref(false)
const openForm = ref({ holder_type: 'customer', holder_id: '', credit_limit: '0', notes: '' })
const showPayment = ref(false)
const paymentBusy = ref(false)
const paymentForm = ref({ amount: '', payment_method: 'cash', notes: '' })
const showLimit = ref(false)
const limitBusy = ref(false)
const limitForm = ref({ credit_limit: '', notes: '' })
const showReverse = ref(false)
const reverseBusy = ref(false)
const reverseForm = ref({ transaction_id: 0, notes: '' })

const canManage = computed(() => ['manager', 'admin', 'super_admin'].includes(auth.role))
const canChangeLimit = computed(() => ['admin', 'super_admin'].includes(auth.role))

function apiError(error: any): string {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  return detail?.message ?? t('backoffice.credit.errors.generic')
}

async function loadAccounts() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.credit.accounts, {
      params: {
        page: page.value,
        size,
        account_status: statusFilter.value || undefined,
        holder_type: holderFilter.value || undefined,
      },
    })
    accounts.value = data.items ?? []
    total.value = data.total ?? 0
  } catch (error) {
    toast.error(apiError(error))
  } finally {
    loading.value = false
  }
}

async function openDetail(account: CreditAccount) {
  selected.value = account
  statement.value = null
  detailLoading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.credit.statement(account.id))
    statement.value = data
    selected.value = data.account
  } catch (error) {
    toast.error(apiError(error))
  } finally {
    detailLoading.value = false
  }
}

async function createAccount() {
  const holderId = Number(openForm.value.holder_id)
  if (!holderId) return toast.error(t('backoffice.credit.errors.holderRequired'))
  openBusy.value = true
  try {
    await api.post(ENDPOINTS.credit.accounts, {
      holder_type: openForm.value.holder_type,
      holder_id: holderId,
      credit_limit: openForm.value.credit_limit || '0',
      notes: openForm.value.notes || null,
    })
    toast.success(t('backoffice.credit.messages.opened'))
    showOpen.value = false
    openForm.value = { holder_type: 'customer', holder_id: '', credit_limit: '0', notes: '' }
    await loadAccounts()
  } catch (error) {
    toast.error(apiError(error))
  } finally {
    openBusy.value = false
  }
}

async function recordPayment() {
  if (!selected.value || Number(paymentForm.value.amount) <= 0) return
  paymentBusy.value = true
  try {
    await api.post(ENDPOINTS.credit.payment(selected.value.id), {
      amount: paymentForm.value.amount,
      payment_method: paymentForm.value.payment_method,
      notes: paymentForm.value.notes || null,
    }, { headers: { 'Idempotency-Key': crypto.randomUUID() } })
    toast.success(t('backoffice.credit.messages.paymentRecorded'))
    showPayment.value = false
    paymentForm.value = { amount: '', payment_method: 'cash', notes: '' }
    await Promise.all([loadAccounts(), openDetail(selected.value)])
  } catch (error) {
    toast.error(apiError(error))
  } finally {
    paymentBusy.value = false
  }
}

async function changeStatus(status: CreditAccount['status']) {
  if (!selected.value) return
  try {
    const { data } = await api.patch(ENDPOINTS.credit.status(selected.value.id), { status })
    selected.value = data
    toast.success(t('backoffice.credit.messages.statusUpdated'))
    await loadAccounts()
  } catch (error) {
    toast.error(apiError(error))
  }
}

function openLimit() {
  if (!selected.value) return
  limitForm.value = { credit_limit: selected.value.credit_limit, notes: '' }
  showLimit.value = true
}

async function changeLimit() {
  if (!selected.value) return
  limitBusy.value = true
  try {
    const { data } = await api.patch(ENDPOINTS.credit.limit(selected.value.id), {
      credit_limit: limitForm.value.credit_limit,
      notes: limitForm.value.notes || null,
    })
    selected.value = data
    showLimit.value = false
    toast.success(t('backoffice.credit.messages.limitUpdated'))
    await loadAccounts()
  } catch (error) {
    toast.error(apiError(error))
  } finally {
    limitBusy.value = false
  }
}

function requestReverse(transaction: CreditTransaction) {
  reverseForm.value = { transaction_id: transaction.id, notes: '' }
  showReverse.value = true
}

async function reverseTransaction() {
  if (!selected.value || reverseForm.value.notes.trim().length < 5) return
  reverseBusy.value = true
  try {
    await api.post(ENDPOINTS.credit.reverse(selected.value.id), {
      original_txn_id: reverseForm.value.transaction_id,
      notes: reverseForm.value.notes.trim(),
    })
    showReverse.value = false
    toast.success(t('backoffice.credit.messages.reversed'))
    await Promise.all([loadAccounts(), openDetail(selected.value)])
  } catch (error) {
    toast.error(apiError(error))
  } finally {
    reverseBusy.value = false
  }
}

function statusVariant(status: string): 'success' | 'warning' | 'neutral' {
  return status === 'active' ? 'success' : status === 'suspended' ? 'warning' : 'neutral'
}

onMounted(loadAccounts)
</script>

<template>
  <div class="p-4 sm:p-6 space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.credit.title') }}</h1>
        <p class="text-sm text-gray-500 dark:text-gray-400">{{ t('backoffice.credit.subtitle') }}</p>
      </div>
      <AppButton v-if="canManage" @click="showOpen = true">{{ t('backoffice.credit.openAccount') }}</AppButton>
    </div>

    <AppCard>
      <div class="grid sm:grid-cols-2 gap-3 mb-4">
        <select v-model="statusFilter" class="rounded-xl border border-stone-200 bg-white px-3 py-2 dark:border-border dark:bg-surface" @change="page = 1; loadAccounts()">
          <option value="">{{ t('backoffice.credit.allStatuses') }}</option>
          <option value="active">{{ t('backoffice.credit.status.active') }}</option>
          <option value="suspended">{{ t('backoffice.credit.status.suspended') }}</option>
          <option value="closed">{{ t('backoffice.credit.status.closed') }}</option>
        </select>
        <select v-model="holderFilter" class="rounded-xl border border-stone-200 bg-white px-3 py-2 dark:border-border dark:bg-surface" @change="page = 1; loadAccounts()">
          <option value="">{{ t('backoffice.credit.allHolders') }}</option>
          <option value="customer">{{ t('backoffice.credit.holder.customer') }}</option>
          <option value="employee">{{ t('backoffice.credit.holder.employee') }}</option>
        </select>
      </div>
      <div v-if="loading" class="py-12 text-center"><AppSpinner /></div>
      <EmptyState v-else-if="accounts.length === 0" icon="📒" :title="t('backoffice.credit.empty')" />
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="text-start text-gray-500"><tr>
            <th class="p-3 text-start">{{ t('backoffice.credit.holderName') }}</th>
            <th class="p-3 text-start">{{ t('backoffice.credit.balance') }}</th>
            <th class="p-3 text-start">{{ t('backoffice.credit.limit') }}</th>
            <th class="p-3 text-start">{{ t('backoffice.credit.statusLabel') }}</th>
            <th class="p-3"></th>
          </tr></thead>
          <tbody>
            <tr v-for="account in accounts" :key="account.id" class="border-t border-stone-100 dark:border-border">
              <td class="p-3 font-bold">{{ account.holder_name }} <span class="text-xs text-gray-400">#{{ account.id }}</span></td>
              <td class="p-3 font-black tabular-nums">{{ formatMoney(account.current_balance, 'EGP') }}</td>
              <td class="p-3 tabular-nums">{{ Number(account.credit_limit) === 0 ? t('backoffice.credit.unlimited') : formatMoney(account.credit_limit, 'EGP') }}</td>
              <td class="p-3"><AppBadge :variant="statusVariant(account.status)">{{ t(`backoffice.credit.status.${account.status}`) }}</AppBadge></td>
              <td class="p-3 text-end"><AppButton size="sm" variant="outline" @click="openDetail(account)">{{ t('backoffice.credit.statement') }}</AppButton></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="total > size" class="mt-4 flex items-center justify-between">
        <AppButton size="sm" variant="outline" :disabled="page === 1" @click="page--; loadAccounts()">{{ t('backoffice.credit.previous') }}</AppButton>
        <span class="text-sm text-gray-500">{{ page }} / {{ Math.ceil(total / size) }}</span>
        <AppButton size="sm" variant="outline" :disabled="page * size >= total" @click="page++; loadAccounts()">{{ t('backoffice.credit.next') }}</AppButton>
      </div>
    </AppCard>

    <AppModal :open="selected !== null" :title="selected?.holder_name ?? ''" size="xl" @close="selected = null; statement = null">
      <div v-if="selected" class="space-y-4">
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div class="rounded-xl bg-amber-50 p-3 dark:bg-amber-950/30"><div class="text-xs text-gray-500">{{ t('backoffice.credit.balance') }}</div><div class="font-black">{{ formatMoney(selected.current_balance, 'EGP') }}</div></div>
          <div class="rounded-xl bg-gray-50 p-3 dark:bg-gray-800"><div class="text-xs text-gray-500">{{ t('backoffice.credit.limit') }}</div><div class="font-black">{{ Number(selected.credit_limit) === 0 ? t('backoffice.credit.unlimited') : formatMoney(selected.credit_limit, 'EGP') }}</div></div>
          <div class="rounded-xl bg-gray-50 p-3 dark:bg-gray-800"><div class="text-xs text-gray-500">{{ t('backoffice.credit.available') }}</div><div class="font-black">{{ selected.available_credit === null ? '∞' : formatMoney(selected.available_credit, 'EGP') }}</div></div>
          <div class="rounded-xl bg-gray-50 p-3 dark:bg-gray-800"><div class="text-xs text-gray-500">{{ t('backoffice.credit.statusLabel') }}</div><AppBadge :variant="statusVariant(selected.status)">{{ t(`backoffice.credit.status.${selected.status}`) }}</AppBadge></div>
        </div>
        <div class="flex flex-wrap gap-2">
          <AppButton v-if="selected.status !== 'closed'" @click="showPayment = true">{{ t('backoffice.credit.recordPayment') }}</AppButton>
          <AppButton v-if="canManage && selected.status !== 'active'" variant="outline" @click="changeStatus('active')">{{ t('backoffice.credit.activate') }}</AppButton>
          <AppButton v-if="canManage && selected.status === 'active'" variant="outline" @click="changeStatus('suspended')">{{ t('backoffice.credit.suspend') }}</AppButton>
          <AppButton v-if="canManage && selected.status !== 'closed'" variant="outline" @click="changeStatus('closed')">{{ t('backoffice.credit.close') }}</AppButton>
          <AppButton v-if="canChangeLimit" variant="outline" @click="openLimit">{{ t('backoffice.credit.changeLimit') }}</AppButton>
        </div>
        <div v-if="detailLoading" class="py-10 text-center"><AppSpinner /></div>
        <EmptyState v-else-if="!statement?.transactions.length" icon="🧾" :title="t('backoffice.credit.noTransactions')" />
        <div v-else class="max-h-[45vh] overflow-auto">
          <table class="w-full text-sm"><tbody>
            <tr v-for="txn in statement?.transactions.slice().reverse()" :key="txn.id" class="border-b border-stone-100 dark:border-border">
              <td class="py-3"><div class="font-bold">{{ t(`backoffice.credit.txn.${txn.txn_type}`) }} #{{ txn.id }}</div><div class="text-xs text-gray-400">{{ formatDateTime(txn.created_at) }} · {{ txn.recorded_by_name }} · JE #{{ txn.journal_entry_id }}</div></td>
              <td class="py-3 text-end font-black tabular-nums" :class="Number(txn.balance_delta) > 0 ? 'text-amber-700' : 'text-emerald-700'">{{ Number(txn.balance_delta) > 0 ? '+' : '' }}{{ formatMoney(txn.balance_delta, 'EGP') }}</td>
              <td class="py-3 text-end"><AppButton v-if="canManage && (txn.txn_type === 'charge' || txn.txn_type === 'payment')" size="sm" variant="ghost" @click="requestReverse(txn)">{{ t('backoffice.credit.reverse') }}</AppButton></td>
            </tr>
          </tbody></table>
        </div>
      </div>
    </AppModal>

    <AppModal :open="showOpen" :title="t('backoffice.credit.openAccount')" size="sm" @close="showOpen = false">
      <div class="space-y-3">
        <select v-model="openForm.holder_type" class="w-full rounded-xl border border-stone-200 px-3 py-2 dark:border-border dark:bg-surface"><option value="customer">{{ t('backoffice.credit.holder.customer') }}</option><option value="employee">{{ t('backoffice.credit.holder.employee') }}</option></select>
        <AppInput v-model="openForm.holder_id" type="number" :label="t('backoffice.credit.holderId')" />
        <AppInput v-model="openForm.credit_limit" type="number" :label="t('backoffice.credit.limit')" />
        <AppInput v-model="openForm.notes" :label="t('backoffice.credit.notes')" />
      </div><template #footer><AppButton :loading="openBusy" @click="createAccount">{{ t('backoffice.credit.save') }}</AppButton></template>
    </AppModal>

    <AppModal :open="showPayment" :title="t('backoffice.credit.recordPayment')" size="sm" @close="showPayment = false">
      <div class="space-y-3"><AppInput v-model="paymentForm.amount" type="number" :label="t('backoffice.credit.amount')" /><select v-model="paymentForm.payment_method" class="w-full rounded-xl border border-stone-200 px-3 py-2 dark:border-border dark:bg-surface"><option value="cash">{{ t('backoffice.credit.payment.cash') }}</option><option value="bank">{{ t('backoffice.credit.payment.bank') }}</option></select><AppInput v-model="paymentForm.notes" :label="t('backoffice.credit.notes')" /></div>
      <template #footer><AppButton :loading="paymentBusy" @click="recordPayment">{{ t('backoffice.credit.collect') }}</AppButton></template>
    </AppModal>

    <AppModal :open="showLimit" :title="t('backoffice.credit.changeLimit')" size="sm" @close="showLimit = false"><div class="space-y-3"><AppInput v-model="limitForm.credit_limit" type="number" :label="t('backoffice.credit.limit')" /><AppInput v-model="limitForm.notes" :label="t('backoffice.credit.notes')" /></div><template #footer><AppButton :loading="limitBusy" @click="changeLimit">{{ t('backoffice.credit.save') }}</AppButton></template></AppModal>
    <AppModal :open="showReverse" :title="t('backoffice.credit.reverse')" size="sm" @close="showReverse = false"><AppInput v-model="reverseForm.notes" :label="t('backoffice.credit.reversalReason')" /><template #footer><AppButton :loading="reverseBusy" @click="reverseTransaction">{{ t('backoffice.credit.confirmReverse') }}</AppButton></template></AppModal>
  </div>
</template>
