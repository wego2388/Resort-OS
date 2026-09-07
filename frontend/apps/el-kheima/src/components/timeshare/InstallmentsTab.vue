<script setup lang="ts">
// أقساط عقود الملكية الجزئية — استُخرج من TimeshareView.vue (تقسيم الملفات
// الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppModal, EmptyState, LoadingState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface Installment {
  id: number; contract_id: number; installment_no: number; due_date: string
  amount: number; paid_amount: number; status: string
  customer_name?: string; customer_phone?: string; room_type?: string
}
type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

const toast = useToast()
const { t } = useI18n()
const { formatDate, formatMoney } = useStaffFormat()
const auth = useAuthStore()
const branchId = computed(() => props.branchId)
const canCollectInstallments = computed(() => auth.hasPermission('timeshare.installments:collect'))

const fmt = (v: number | string | null | undefined) => formatMoney(v, 'EGP')
const formatDateValue = (d?: string) => {
  if (!d) return '—'
  try { return formatDate(d, { day: 'numeric', month: 'short', year: 'numeric' }) }
  catch { return d }
}
const payStatusVariant: Record<string, BadgeVariant> = {
  paid: 'success', pending: 'warning', overdue: 'danger', partial: 'info',
}
function payLabel(s: string) {
  const icons: Record<string, string> = { paid: '✅', pending: '⏳', overdue: '🔴', partial: '🔵' }
  const labels: Record<string, string> = {
    paid: t('backoffice.timeshare.payStatus.paid'), pending: t('backoffice.timeshare.payStatus.pending'),
    overdue: t('backoffice.timeshare.payStatus.overdue'), partial: t('backoffice.timeshare.payStatus.partial'),
  }
  return labels[s] ? `${icons[s]} ${labels[s]}` : s
}

const installments = ref<Installment[]>([])
const installSummary = ref({ overdue_total: 0, pending_total: 0 })
const installLoading = ref(false)
const installStatus = ref('overdue')
const installMonth = ref('')
const installSearch = ref('')

async function loadInstallments() {
  installLoading.value = true
  try {
    const params: Record<string, string | number | undefined> = { branch_id: branchId.value ?? undefined, limit: 300 }
    if (installStatus.value) params.status = installStatus.value
    if (installMonth.value) params.month = installMonth.value
    if (installSearch.value) params.search = installSearch.value
    const r = await api.get('/api/v1/timeshare/installments', { params })
    installments.value = r.data.installments ?? []
    installSummary.value = r.data.summary ?? { overdue_total: 0, pending_total: 0 }
  } catch (e) { toast.error(t('backoffice.timeshare.msg.loadInstallmentsError')) } finally { installLoading.value = false }
}

// ── Pay Modal ────────────────────────────────────────────────────────────
const payModal = ref({
  open: false, saving: false, inst_id: 0, customer_name: '', due_amount: 0,
  amount: 0, method: 'bank_transfer', receipt_number: '',
})
function openPayModal(inst: Installment) {
  payModal.value = {
    open: true, saving: false, inst_id: inst.id,
    customer_name: inst.customer_name ?? '',
    due_amount: inst.amount - inst.paid_amount,
    amount: inst.amount - inst.paid_amount, method: 'bank_transfer', receipt_number: '',
  }
}
async function submitPayment() {
  if (!payModal.value.amount || payModal.value.saving) return
  payModal.value.saving = true
  try {
    await api.post(`/api/v1/timeshare/installments/${payModal.value.inst_id}/pay`, {
      paid_amount: payModal.value.amount, payment_method: payModal.value.method,
      receipt_number: payModal.value.receipt_number || undefined,
    })
    payModal.value.open = false
    toast.success(t('backoffice.timeshare.msg.paymentRecorded'))
    await loadInstallments()
  } catch (e: unknown) { toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.paymentError')) }
  finally { payModal.value.saving = false }
}

// تقارير جاهزة بدون زرار تحميل — نفس نمط SalesDashboardView.vue's exportExcel
// بالظبط (blob → object URL → <a download>). بيستخدم installMonth (الفلتر
// الموجود بالفعل هنا) — لو فاضي، الشهر الحالي.
const exportingMonthly = ref(false)
async function downloadMonthlyReport() {
  const month = installMonth.value || new Date().toISOString().slice(0, 7)
  exportingMonthly.value = true
  try {
    const res = await api.get('/api/v1/timeshare/installments/monthly-report', {
      params: { branch_id: branchId.value, month },
      responseType: 'blob',
    })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `timeshare-collection-${month}.xlsx`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 5000)
  } catch { toast.error(t('backoffice.timeshare.msg.reportError')) } finally { exportingMonthly.value = false }
}

onMounted(loadInstallments)
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap gap-3">
      <div class="min-h-[44px] inline-flex items-center px-4 py-2 rounded-xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 text-sm font-bold text-red-700 dark:text-red-300">🔴 {{ t('backoffice.timeshare.overdueColon', { amount: fmt(installSummary.overdue_total) }) }}</div>
      <div class="min-h-[44px] inline-flex items-center px-4 py-2 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 text-sm font-bold text-amber-700 dark:text-amber-300">⏳ {{ t('backoffice.timeshare.pendingColon', { amount: fmt(installSummary.pending_total) }) }}</div>
    </div>
    <div class="flex flex-wrap gap-3">
      <input v-model="installSearch" @keyup.enter="loadInstallments" :placeholder="t('backoffice.timeshare.searchByCustomerName')"
        class="min-h-[44px] flex-1 min-w-48 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2 outline-none" />
      <select v-model="installStatus" :aria-label="t('backoffice.timeshare.filterByStatus')" @change="loadInstallments" class="min-h-[44px] bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2">
        <option value="">{{ t('backoffice.timeshare.allStatuses') }}</option><option value="overdue">🔴 {{ t('backoffice.timeshare.payStatus.overdue') }}</option>
        <option value="pending">⏳ {{ t('backoffice.timeshare.payStatus.pending') }}</option><option value="paid">✅ {{ t('backoffice.timeshare.payStatus.paid') }}</option><option value="partial">🔵 {{ t('backoffice.timeshare.payStatus.partial') }}</option>
      </select>
      <input v-model="installMonth" :aria-label="t('backoffice.timeshare.filterByMonth')" @change="loadInstallments" type="month" class="min-h-[44px] bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2" />
      <button v-if="auth.hasRole('timeshare_admin')" @click="downloadMonthlyReport" :disabled="exportingMonthly"
        class="min-h-[44px] px-4 py-2 rounded-xl bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 text-sm font-bold border border-emerald-200 dark:border-emerald-800 hover:bg-emerald-100 disabled:opacity-50">
        📊 {{ exportingMonthly ? t('backoffice.timeshare.saving') : t('backoffice.timeshare.downloadMonthlyReport') }}
      </button>
    </div>

    <LoadingState v-if="installLoading" :label="t('backoffice.timeshare.loadingInstallments')" />
    <AppCard v-else padding="none">
      <EmptyState v-if="!installments.length" icon="💰" :title="t('backoffice.timeshare.noResults')" />
      <div v-else class="overflow-x-auto">
      <table class="w-full min-w-[720px] text-sm">
        <thead class="bg-stone-50 dark:bg-gray-800/60"><tr>
          <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.customer') }}</th>
          <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.dueDate') }}</th>
          <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.amount') }}</th>
          <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.status') }}</th>
          <th class="px-4 py-3"></th>
        </tr></thead>
        <tbody class="divide-y divide-stone-100 dark:divide-border">
          <tr v-for="p in installments" :key="p.id" :class="p.status === 'overdue' ? 'bg-red-50/50 dark:bg-red-950/20' : ''">
            <td class="px-4 py-3">
              <div class="font-bold text-gray-900 dark:text-gray-100">{{ p.customer_name }}</div>
              <div class="text-xs text-gray-500 dark:text-gray-400">{{ p.customer_phone }}</div>
            </td>
            <td class="px-4 py-3"><span :class="p.status === 'overdue' ? 'text-red-600 dark:text-red-300 font-bold' : 'text-gray-600 dark:text-gray-300'">{{ formatDateValue(p.due_date) }}</span></td>
            <td class="px-4 py-3 font-bold">{{ fmt(p.amount) }}</td>
            <td class="px-4 py-3"><AppBadge size="sm" :variant="payStatusVariant[p.status] ?? 'neutral'">{{ payLabel(p.status) }}</AppBadge></td>
            <td class="px-4 py-3">
              <button v-if="p.status !== 'paid' && canCollectInstallments" @click="openPayModal(p)"
                class="min-h-[44px] px-3 py-2 rounded-xl bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 text-xs font-bold border border-green-200 dark:border-green-800 hover:bg-green-100">💰 {{ t('backoffice.timeshare.pay') }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      </div>
    </AppCard>

    <!-- ══ PAY MODAL ══ -->
    <AppModal :open="payModal.open" :title="`💰 ${t('backoffice.timeshare.recordPayment')}`" size="sm" @close="payModal.open = false">
      <p class="text-sm text-gray-600 dark:text-gray-300 mb-4">{{ payModal.customer_name }}</p>
      <div class="space-y-3">
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.amountPaid') }}</label>
          <input v-model.number="payModal.amount" type="number" min="1" :placeholder="t('backoffice.timeshare.duePlaceholder', { amount: fmt(payModal.due_amount) })"
            class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none focus:border-primary-500" />
        </div>
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.paymentMethod') }}</label>
          <select v-model="payModal.method" class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none">
            <option value="bank_transfer">{{ t('backoffice.timeshare.paymentMethodBankTransfer') }}</option><option value="card">{{ t('backoffice.timeshare.paymentMethodCard') }}</option>
          </select>
        </div>
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.receiptNumberOptional') }}</label>
          <input v-model="payModal.receipt_number" class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none" />
        </div>
      </div>
      <template #footer>
        <div class="flex gap-3">
          <AppButton variant="primary" block :loading="payModal.saving" :disabled="!payModal.amount" @click="submitPayment">
            ✅ {{ t('backoffice.timeshare.confirmPayment') }}
          </AppButton>
          <AppButton variant="ghost" @click="payModal.open = false">{{ t('backoffice.timeshare.cancelAction') }}</AppButton>
        </div>
      </template>
    </AppModal>
  </div>
</template>
