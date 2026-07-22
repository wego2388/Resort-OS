<script setup lang="ts">
// LeasingView — يغطي فجوة كانت موجودة: الباك إند (app/modules/leasing) عنده
// 9 endpoints حقيقية (عقود إيجار تجاري، دفعات، غرامات تأخير، سجل كاش
// المستأجرين، إيصال PDF) لكن مفيش أي شاشة/route/عنصر قائمة في el-kheima —
// مستحيل أي حد يستخدم الميزة دي فعليًا رغم إنها مبنية بالكامل في الباك إند.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const auth = useAuthStore()
const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatNumber, formatDate } = useStaffFormat()
const branchId = auth.branchId

interface Payment {
  id: number; contract_id: number; due_date: string; amount: number
  penalty: number; paid_amount: number; status: string
  paid_at: string | null; payment_method: string | null
  receipt_number: string | null; year_n: number; notes: string | null
}
interface CashLog {
  id: number; amount: number; activity_type: string
  payment_method: string | null; reference: string | null
  notes: string | null; created_at: string
}
interface Contract {
  id: number; contract_number: string; tenant_name: string; tenant_phone: string | null
  tenant_national_id: string | null; unit_description: string
  start_date: string; end_date: string
  base_rent: number; increase_rate: number; billing_day: number
  grace_months: number; payment_period: string; security_deposit: number
  status: string; notes: string | null
  payments: Payment[]
  days_until_expiry: number
}

const contracts = ref<Contract[]>([])
const loading = ref(false)
const statusFilter = ref<string>('')
const expandedId = ref<number | null>(null)
const cashLogsByContract = ref<Record<number, CashLog[]>>({})

const statusConfig = computed<Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }>>(() => ({
  draft:      { label: t('backoffice.leasing.contractStatus.draft'),  variant: 'neutral' },
  active:     { label: t('backoffice.leasing.contractStatus.active'),    variant: 'success' },
  expired:    { label: t('backoffice.leasing.contractStatus.expired'),  variant: 'warning' },
  terminated: { label: t('backoffice.leasing.contractStatus.terminated'), variant: 'danger' },
}))
const paymentStatusConfig = computed<Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }>>(() => ({
  pending:  { label: t('backoffice.leasing.paymentStatus.pending'),  variant: 'warning' },
  paid:     { label: t('backoffice.leasing.paymentStatus.paid'),  variant: 'success' },
  overdue:  { label: t('backoffice.leasing.paymentStatus.overdue'),  variant: 'danger' },
  partial:  { label: t('backoffice.leasing.paymentStatus.partial'),   variant: 'info' },
}))
const paymentPeriodLabels = computed<Record<string, string>>(() => ({
  monthly: t('backoffice.leasing.paymentPeriod.monthly'), quarterly: t('backoffice.leasing.paymentPeriod.quarterly'),
  biannual: t('backoffice.leasing.paymentPeriod.biannual'), annual: t('backoffice.leasing.paymentPeriod.annual'),
}))
const activityTypeLabels = computed<Record<string, string>>(() => ({
  rent_payment: t('backoffice.leasing.activityType.rentPayment'), penalty: t('backoffice.leasing.activityType.penalty'),
  deposit: t('backoffice.leasing.activityType.deposit'), refund: t('backoffice.leasing.activityType.refund'),
  maintenance: t('backoffice.leasing.activityType.maintenance'), revenue_share: t('backoffice.leasing.activityType.revenueShare'),
  other: t('backoffice.leasing.activityType.other'),
}))

// #28: تنبيه عقود قرب انتهائها — استعلام منفصل عن قائمة العقود الرئيسية
// (اللي ممكن تبقى مفلترة بحالة تانية زي "مسودة") عشان البانر يفضل صحيح
// بصرف النظر عن أي فلتر الحالة المستخدم مختاره حاليًا. الباك إند بيحسب
// days_until_expiry لحظيًا (راجع leasing.services.days_until_expiry).
const expiringSoonContracts = ref<Contract[]>([])
async function loadExpiringSoon() {
  try {
    const { data } = await api.get('/api/v1/leasing/contracts', {
      params: { branch_id: branchId, expiring_within_days: 30 },
    })
    expiringSoonContracts.value = data.items ?? []
  } catch { /* بانر ثانوي — فشله ما يمنعش الشاشة تشتغل */ }
}

async function loadContracts() {
  loading.value = true
  try {
    const params: Record<string, any> = { branch_id: branchId, size: 100 }
    if (statusFilter.value) params.status = statusFilter.value
    const { data } = await api.get('/api/v1/leasing/contracts', { params })
    contracts.value = data.items
  } catch { toast.error(t('backoffice.leasing.msg.loadContractsError')) }
  finally { loading.value = false }
}

async function toggleExpand(contract: Contract) {
  if (expandedId.value === contract.id) { expandedId.value = null; return }
  expandedId.value = contract.id
  if (!cashLogsByContract.value[contract.id]) await loadCashLogs(contract.id)
}

async function loadCashLogs(contractId: number) {
  try {
    const { data } = await api.get(`/api/v1/leasing/contracts/${contractId}/cash-logs`)
    cashLogsByContract.value[contractId] = data
  } catch { toast.error(t('backoffice.leasing.msg.loadCashLogError')) }
}

// ── Create/Edit Contract ──────────────────────────────────────────────
const contractModal = ref({ open: false, editingId: null as number | null })
const contractForm = ref({
  tenant_name: '', tenant_phone: '', tenant_national_id: '', unit_description: '',
  start_date: '', end_date: '', base_rent: '', increase_rate: '0',
  billing_day: '1', grace_months: '0', payment_period: 'monthly',
  security_deposit: '0', notes: '', status: 'draft',
})
const savingContract = ref(false)

function openCreateContract() {
  contractModal.value = { open: true, editingId: null }
  contractForm.value = {
    tenant_name: '', tenant_phone: '', tenant_national_id: '', unit_description: '',
    start_date: '', end_date: '', base_rent: '', increase_rate: '0',
    billing_day: '1', grace_months: '0', payment_period: 'monthly',
    security_deposit: '0', notes: '', status: 'draft',
  }
}

function openEditContract(c: Contract) {
  contractModal.value = { open: true, editingId: c.id }
  contractForm.value = {
    tenant_name: c.tenant_name, tenant_phone: c.tenant_phone ?? '',
    tenant_national_id: c.tenant_national_id ?? '', unit_description: c.unit_description,
    start_date: c.start_date, end_date: c.end_date,
    base_rent: String(c.base_rent), increase_rate: String(c.increase_rate),
    billing_day: String(c.billing_day), grace_months: String(c.grace_months),
    payment_period: c.payment_period, security_deposit: String(c.security_deposit),
    notes: c.notes ?? '', status: c.status,
  }
}

async function saveContract() {
  savingContract.value = true
  try {
    if (contractModal.value.editingId) {
      await api.patch(`/api/v1/leasing/contracts/${contractModal.value.editingId}`, {
        tenant_phone: contractForm.value.tenant_phone || null,
        status: contractForm.value.status,
        notes: contractForm.value.notes || null,
      })
      toast.success(t('backoffice.leasing.msg.contractUpdated'))
    } else {
      await api.post('/api/v1/leasing/contracts', {
        branch_id: branchId,
        tenant_name: contractForm.value.tenant_name,
        tenant_phone: contractForm.value.tenant_phone || null,
        tenant_national_id: contractForm.value.tenant_national_id || null,
        unit_description: contractForm.value.unit_description,
        start_date: contractForm.value.start_date,
        end_date: contractForm.value.end_date,
        base_rent: contractForm.value.base_rent,
        increase_rate: contractForm.value.increase_rate,
        billing_day: parseInt(contractForm.value.billing_day, 10),
        grace_months: parseInt(contractForm.value.grace_months, 10),
        payment_period: contractForm.value.payment_period,
        security_deposit: contractForm.value.security_deposit,
        notes: contractForm.value.notes || null,
      })
      toast.success(t('backoffice.leasing.msg.contractCreated'))
    }
    contractModal.value.open = false
    await loadContracts()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.leasing.msg.saveContractError'))
  } finally {
    savingContract.value = false
  }
}

// ── Pay Payment ────────────────────────────────────────────────────────
const payModal = ref({ open: false, payment: null as Payment | null, contractId: 0 })
const payForm = ref({ paid_amount: '', payment_method: 'cash', receipt_number: '', notes: '' })
const payingInProgress = ref(false)

function openPayModal(contract: Contract, payment: Payment) {
  payModal.value = { open: true, payment, contractId: contract.id }
  payForm.value = {
    paid_amount: String(Number(payment.amount) + Number(payment.penalty)),
    payment_method: 'cash', receipt_number: '', notes: '',
  }
}

async function submitPayment() {
  if (!payModal.value.payment) return
  payingInProgress.value = true
  try {
    await api.post(`/api/v1/leasing/payments/${payModal.value.payment.id}/pay`, {
      paid_amount: payForm.value.paid_amount,
      payment_method: payForm.value.payment_method,
      receipt_number: payForm.value.receipt_number || null,
      notes: payForm.value.notes || null,
    })
    toast.success(t('backoffice.leasing.msg.paymentRecorded'))
    payModal.value.open = false
    await loadContracts()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.leasing.msg.paymentError'))
  } finally {
    payingInProgress.value = false
  }
}

async function downloadReceipt(payment: Payment) {
  try {
    const res = await api.get(`/api/v1/leasing/payments/${payment.id}/receipt`, { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    window.open(url, '_blank')
  } catch {
    toast.error(t('backoffice.leasing.msg.receiptError'))
  }
}

async function applyPenalties(contract: Contract) {
  const ok = await confirm({
    title: t('backoffice.leasing.applyPenaltiesTitle'),
    message: t('backoffice.leasing.confirmApplyPenalties', { name: contract.tenant_name }),
  })
  if (!ok) return
  try {
    const { data } = await api.post(`/api/v1/leasing/contracts/${contract.id}/apply-penalties`)
    toast.success(t('backoffice.leasing.msg.penaltiesApplied', { count: data.updated }))
    await loadContracts()
  } catch { toast.error(t('backoffice.leasing.msg.applyPenaltiesError')) }
}

// ── Cash Log ─────────────────────────────────────────────────────────
const cashLogModal = ref({ open: false, contractId: 0 })
const cashLogForm = ref({ amount: '', activity_type: 'rent_payment', payment_method: '', reference: '', notes: '' })
const savingCashLog = ref(false)

function openCashLogModal(contractId: number) {
  cashLogModal.value = { open: true, contractId }
  cashLogForm.value = { amount: '', activity_type: 'rent_payment', payment_method: '', reference: '', notes: '' }
}

async function saveCashLog() {
  savingCashLog.value = true
  try {
    await api.post(`/api/v1/leasing/contracts/${cashLogModal.value.contractId}/cash-logs`, {
      branch_id: branchId, contract_id: cashLogModal.value.contractId,
      amount: cashLogForm.value.amount, activity_type: cashLogForm.value.activity_type,
      payment_method: cashLogForm.value.payment_method || null,
      reference: cashLogForm.value.reference || null,
      notes: cashLogForm.value.notes || null,
    })
    toast.success(t('backoffice.leasing.msg.cashLogRecorded'))
    cashLogModal.value.open = false
    await loadCashLogs(cashLogModal.value.contractId)
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.leasing.msg.cashLogError'))
  } finally {
    savingCashLog.value = false
  }
}

onMounted(() => { loadContracts(); loadExpiringSoon() })
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.leasing.title') }}</h2>
      <AppButton v-if="auth.hasRole('manager')" size="sm" @click="openCreateContract">+ {{ t('backoffice.leasing.newContract') }}</AppButton>
    </div>

    <!-- #28: عقود قرب انتهائها (خلال 30 يوم) — تنبيه ثابت ظاهر، مش حاجة
         مدير الإيجارات يكتشفها بالصدفة -->
    <div v-if="expiringSoonContracts.length" class="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950/40">
      <p class="mb-2 text-xs font-bold text-amber-800 dark:text-amber-300">⏰ {{ t('backoffice.leasing.expiringSoon', { count: expiringSoonContracts.length }) }}</p>
      <div class="flex flex-wrap gap-2">
        <span v-for="c in expiringSoonContracts" :key="c.id"
          class="rounded-full border border-amber-200 bg-white px-2.5 py-1 text-xs text-amber-700 dark:border-amber-800 dark:bg-surface dark:text-amber-300">
          {{ c.tenant_name }} — {{ c.days_until_expiry === 0 ? t('backoffice.leasing.expiresToday') : t('backoffice.leasing.daysCount', { days: c.days_until_expiry }) }}
        </span>
      </div>
    </div>

    <div class="flex gap-2 mb-4">
      <select v-model="statusFilter" @change="loadContracts" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm">
        <option value="">{{ t('backoffice.leasing.allStatuses') }}</option>
        <option v-for="(cfg, key) in statusConfig" :key="key" :value="key">{{ cfg.label }}</option>
      </select>
    </div>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <div v-else class="space-y-3">
      <AppCard v-for="c in contracts" :key="c.id" padding="none">
        <div class="p-4 cursor-pointer" @click="toggleExpand(c)">
          <div class="flex items-center justify-between">
            <div>
              <div class="flex items-center gap-2 mb-1">
                <span class="font-mono text-xs text-gray-400 dark:text-gray-400">{{ c.contract_number }}</span>
                <span class="font-bold text-gray-900 dark:text-gray-100">{{ c.tenant_name }}</span>
              </div>
              <div class="text-sm text-gray-500 dark:text-gray-400">{{ c.unit_description }}</div>
              <div class="text-xs text-gray-400 dark:text-gray-400 mt-1">
                {{ c.start_date }} → {{ c.end_date }} · {{ paymentPeriodLabels[c.payment_period] }}
              </div>
            </div>
            <div class="flex items-center gap-3">
              <div class="text-end">
                <div class="font-bold text-blue-700 dark:text-blue-300">{{ formatNumber(Number(c.base_rent)) }} {{ t('backoffice.leasing.currency') }}</div>
                <div class="text-[10px] text-gray-400 dark:text-gray-400">{{ t('backoffice.leasing.baseRent') }}</div>
              </div>
              <AppBadge size="sm" :variant="statusConfig[c.status]?.variant ?? 'neutral'">
                {{ statusConfig[c.status]?.label ?? c.status }}
              </AppBadge>
            </div>
          </div>
        </div>

        <div v-if="expandedId === c.id" class="border-t border-stone-100 dark:border-border/50 p-4 bg-stone-50 dark:bg-gray-800/60">
          <div class="flex items-center justify-between mb-3">
            <h4 class="font-bold text-sm text-gray-700 dark:text-gray-300">{{ t('backoffice.leasing.payments') }}</h4>
            <div class="flex gap-2" v-if="auth.hasRole('manager')">
              <AppButton size="sm" variant="secondary" @click="openEditContract(c)">{{ t('backoffice.leasing.editContract') }}</AppButton>
              <AppButton size="sm" variant="secondary" @click="applyPenalties(c)">{{ t('backoffice.leasing.applyPenalties') }}</AppButton>
              <AppButton size="sm" variant="secondary" @click="openCashLogModal(c.id)">+ {{ t('backoffice.leasing.cashMovement') }}</AppButton>
            </div>
          </div>

          <div class="overflow-x-auto mb-4">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-xs text-gray-400 dark:text-gray-400">
                  <th class="text-start py-1">{{ t('backoffice.leasing.column.dueDate') }}</th>
                  <th class="text-start py-1">{{ t('backoffice.leasing.column.amount') }}</th>
                  <th class="text-start py-1">{{ t('backoffice.leasing.column.penalty') }}</th>
                  <th class="text-start py-1">{{ t('backoffice.leasing.column.paid') }}</th>
                  <th class="text-start py-1">{{ t('backoffice.leasing.column.status') }}</th>
                  <th class="text-start py-1">{{ t('backoffice.leasing.column.action') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in c.payments" :key="p.id" class="border-t border-stone-100 dark:border-border/50">
                  <td class="py-2">{{ p.due_date }}</td>
                  <td class="py-2 font-medium">{{ formatNumber(Number(p.amount)) }} {{ t('backoffice.leasing.currency') }}</td>
                  <td class="py-2 text-red-500">{{ formatNumber(Number(p.penalty)) }} {{ t('backoffice.leasing.currency') }}</td>
                  <td class="py-2">{{ formatNumber(Number(p.paid_amount)) }} {{ t('backoffice.leasing.currency') }}</td>
                  <td class="py-2">
                    <AppBadge size="sm" :variant="paymentStatusConfig[p.status]?.variant ?? 'neutral'">
                      {{ paymentStatusConfig[p.status]?.label ?? p.status }}
                    </AppBadge>
                  </td>
                  <td class="py-2">
                    <div class="flex gap-2">
                      <AppButton v-if="p.status !== 'paid'" size="sm" @click="openPayModal(c, p)">{{ t('backoffice.leasing.recordPayment') }}</AppButton>
                      <AppButton v-else size="sm" variant="secondary" @click="downloadReceipt(p)">{{ t('backoffice.leasing.receipt') }}</AppButton>
                    </div>
                  </td>
                </tr>
                <tr v-if="c.payments.length === 0">
                  <td colspan="6" class="py-6 text-center text-gray-400 dark:text-gray-400 text-xs">{{ t('backoffice.leasing.noScheduledPayments') }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <h4 class="font-bold text-sm text-gray-700 dark:text-gray-300 mb-2">{{ t('backoffice.leasing.tenantCashLog') }}</h4>
          <div class="space-y-1">
            <div v-for="log in (cashLogsByContract[c.id] ?? [])" :key="log.id"
              class="flex items-center justify-between text-sm bg-white dark:bg-surface rounded-lg px-3 py-2 border border-stone-100 dark:border-border/50">
              <span>{{ activityTypeLabels[log.activity_type] ?? log.activity_type }}</span>
              <span class="font-bold">{{ formatNumber(Number(log.amount)) }} {{ t('backoffice.leasing.currency') }}</span>
              <span class="text-xs text-gray-400 dark:text-gray-400">{{ formatDate(log.created_at) }}</span>
            </div>
            <EmptyState v-if="(cashLogsByContract[c.id] ?? []).length === 0" icon="💵" :title="t('backoffice.leasing.noCashMovements')" />
          </div>
        </div>
      </AppCard>
      <EmptyState v-if="contracts.length === 0" icon="🏢" :title="t('backoffice.leasing.noLeaseContracts')" />
    </div>

    <!-- Create/Edit Contract Modal -->
    <AppModal :open="contractModal.open" :title="contractModal.editingId ? t('backoffice.leasing.editContractTitle') : t('backoffice.leasing.newContractTitle')" size="lg" @close="contractModal.open = false">
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <template v-if="!contractModal.editingId">
          <input v-model="contractForm.tenant_name" type="text" :placeholder="t('backoffice.leasing.tenantName')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2" />
          <input v-model="contractForm.unit_description" type="text" :placeholder="t('backoffice.leasing.unitDescription')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2" />
          <input v-model="contractForm.tenant_phone" type="text" :placeholder="t('backoffice.leasing.tenantPhone')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="contractForm.tenant_national_id" type="text" :placeholder="t('backoffice.leasing.nationalId')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <div><label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.leasing.startDate') }}</label>
            <input v-model="contractForm.start_date" type="date" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm w-full" /></div>
          <div><label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.leasing.endDate') }}</label>
            <input v-model="contractForm.end_date" type="date" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm w-full" /></div>
          <input v-model="contractForm.base_rent" type="number" step="0.01" :placeholder="t('backoffice.leasing.baseRent')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="contractForm.increase_rate" type="number" step="0.01" :placeholder="t('backoffice.leasing.annualIncreaseRate')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <select v-model="contractForm.payment_period" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
            <option v-for="(label, val) in paymentPeriodLabels" :key="val" :value="val">{{ label }}</option>
          </select>
          <input v-model="contractForm.security_deposit" type="number" step="0.01" :placeholder="t('backoffice.leasing.securityDeposit')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="contractForm.billing_day" type="number" min="1" max="28" :placeholder="t('backoffice.leasing.billingDay')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="contractForm.grace_months" type="number" min="0" :placeholder="t('backoffice.leasing.graceMonths')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        </template>
        <template v-else>
          <input v-model="contractForm.tenant_phone" type="text" :placeholder="t('backoffice.leasing.tenantPhone')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <select v-model="contractForm.status" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
            <option v-for="(cfg, key) in statusConfig" :key="key" :value="key">{{ cfg.label }}</option>
          </select>
        </template>
        <textarea v-model="contractForm.notes" :placeholder="t('backoffice.leasing.notes')" rows="2"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2" />
      </div>
      <template #footer>
        <AppButton :loading="savingContract" @click="saveContract">{{ t('backoffice.leasing.save') }}</AppButton>
      </template>
    </AppModal>

    <!-- Pay Payment Modal -->
    <AppModal :open="payModal.open" :title="t('backoffice.leasing.recordRentPaymentTitle')" size="sm" @close="payModal.open = false">
      <div class="space-y-3">
        <input v-model="payForm.paid_amount" type="number" step="0.01" :placeholder="t('backoffice.leasing.amountPaid')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm w-full" />
        <select v-model="payForm.payment_method" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm w-full">
          <option value="cash">{{ t('backoffice.leasing.paymentMethodCash') }}</option>
          <option value="card">{{ t('backoffice.leasing.paymentMethodCard') }}</option>
          <option value="bank_transfer">{{ t('backoffice.leasing.paymentMethodBankTransfer') }}</option>
          <option value="other">{{ t('backoffice.leasing.paymentMethodOther') }}</option>
        </select>
        <input v-model="payForm.receipt_number" type="text" :placeholder="t('backoffice.leasing.receiptNumberOptional')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm w-full" />
      </div>
      <template #footer>
        <AppButton :loading="payingInProgress" @click="submitPayment">{{ t('backoffice.leasing.confirmPayment') }}</AppButton>
      </template>
    </AppModal>

    <!-- Cash Log Modal -->
    <AppModal :open="cashLogModal.open" :title="t('backoffice.leasing.newCashMovementTitle')" size="sm" @close="cashLogModal.open = false">
      <div class="space-y-3">
        <input v-model="cashLogForm.amount" type="number" step="0.01" :placeholder="t('backoffice.leasing.amount')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm w-full" />
        <select v-model="cashLogForm.activity_type" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm w-full">
          <option v-for="(label, val) in activityTypeLabels" :key="val" :value="val">{{ label }}</option>
        </select>
        <input v-model="cashLogForm.reference" type="text" :placeholder="t('backoffice.leasing.referenceOptional')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm w-full" />
      </div>
      <template #footer>
        <AppButton :loading="savingCashLog" @click="saveCashLog">{{ t('backoffice.leasing.save') }}</AppButton>
      </template>
    </AppModal>
  </div>
</template>
