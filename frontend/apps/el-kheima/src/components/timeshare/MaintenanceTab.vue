<script setup lang="ts">
// مستحقات الصيانة السنوية لعقود الملكية الجزئية — استُخرج من
// TimeshareView.vue (تقسيم الملفات الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppModal, AppButton, EmptyState, LoadingState, useToast, useConfirm } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface MaintenanceDue {
  id: number; contract_id: number; fee_year: number; due_date: string
  amount: number; paid_amount: number; status: string
  customer_name?: string; customer_phone?: string; room_type?: string
}
type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatDate, formatMoney } = useStaffFormat()
const auth = useAuthStore()
const branchId = computed(() => props.branchId)
const canCollectMaintenance = computed(() => auth.hasPermission('timeshare.maintenance_dues:collect'))

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

const maintenanceDues = ref<MaintenanceDue[]>([])
const maintSummary = ref({ overdue_total: 0, pending_total: 0 })
const maintLoading = ref(false)
const maintStatus = ref('overdue')
const maintSearch = ref('')

async function loadMaintenanceDues() {
  maintLoading.value = true
  try {
    const params: Record<string, string | number | undefined> = { branch_id: branchId.value ?? undefined, limit: 300 }
    if (maintStatus.value) params.status = maintStatus.value
    if (maintSearch.value) params.search = maintSearch.value
    const r = await api.get('/api/v1/timeshare/maintenance-dues', { params })
    maintenanceDues.value = r.data.maintenance_dues ?? []
    maintSummary.value = r.data.summary ?? { overdue_total: 0, pending_total: 0 }
  } catch (e) { toast.error(t('backoffice.timeshare.msg.loadMaintenanceDuesError')) } finally { maintLoading.value = false }
}

// 2026-08-04: التوليد التلقائي (توقيع عقد جديد + 1 يناير سنويًا) بيغطي
// الحالة العادية بالكامل — الزرار ده أداة استرجاع لحالات استثنائية بس.
// نفس endpoint الـCelery task بالظبط، idempotent.
const generatingDues = ref(false)
async function generateMaintenanceDues() {
  const fee_year = new Date().getFullYear()
  const ok = await confirm({
    message: t('backoffice.timeshare.confirmGenerateDues', { year: fee_year }),
    confirmText: t('backoffice.timeshare.yesGenerate'),
  })
  if (!ok) return
  generatingDues.value = true
  try {
    const r = await api.post('/api/v1/timeshare/maintenance-dues/generate', null, {
      params: { branch_id: branchId.value, fee_year },
    })
    toast.success(t('backoffice.timeshare.msg.duesGenerated', { count: r.data.created }))
    await loadMaintenanceDues()
  } catch (e) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.duesGenerateError'))
  } finally { generatingDues.value = false }
}

// ── Maintenance Pay Modal ────────────────────────────────────────────────
const maintPayModal = ref({
  open: false, saving: false, due_id: 0, customer_name: '', due_amount: 0,
  amount: 0, method: 'bank_transfer', receipt_number: '',
})
function openMaintenancePayModal(due: MaintenanceDue) {
  maintPayModal.value = {
    open: true, saving: false, due_id: due.id,
    customer_name: due.customer_name ?? '',
    due_amount: due.amount - due.paid_amount,
    amount: due.amount - due.paid_amount, method: 'bank_transfer', receipt_number: '',
  }
}
async function submitMaintenancePayment() {
  if (!maintPayModal.value.amount || maintPayModal.value.saving) return
  maintPayModal.value.saving = true
  try {
    await api.post(`/api/v1/timeshare/maintenance-dues/${maintPayModal.value.due_id}/pay`, {
      paid_amount: maintPayModal.value.amount, payment_method: maintPayModal.value.method,
      receipt_number: maintPayModal.value.receipt_number || undefined,
    })
    maintPayModal.value.open = false
    toast.success(t('backoffice.timeshare.msg.paymentRecorded'))
    await loadMaintenanceDues()
  } catch (e: unknown) { toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.paymentError')) }
  finally { maintPayModal.value.saving = false }
}

onMounted(loadMaintenanceDues)
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap gap-3">
      <div class="min-h-[44px] inline-flex items-center px-4 py-2 rounded-xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 text-sm font-bold text-red-700 dark:text-red-300">🔴 {{ t('backoffice.timeshare.overdueColon', { amount: fmt(maintSummary.overdue_total) }) }}</div>
      <div class="min-h-[44px] inline-flex items-center px-4 py-2 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 text-sm font-bold text-amber-700 dark:text-amber-300">⏳ {{ t('backoffice.timeshare.pendingColon', { amount: fmt(maintSummary.pending_total) }) }}</div>
    </div>
    <div class="flex flex-wrap gap-3">
      <input v-model="maintSearch" @keyup.enter="loadMaintenanceDues" :placeholder="t('backoffice.timeshare.searchByCustomerName')"
        class="min-h-[44px] flex-1 min-w-48 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2 outline-none" />
      <select v-model="maintStatus" :aria-label="t('backoffice.timeshare.filterByStatus')" @change="loadMaintenanceDues" class="min-h-[44px] bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2">
        <option value="">{{ t('backoffice.timeshare.allStatuses') }}</option><option value="overdue">🔴 {{ t('backoffice.timeshare.payStatus.overdue') }}</option>
        <option value="pending">⏳ {{ t('backoffice.timeshare.payStatus.pending') }}</option><option value="paid">✅ {{ t('backoffice.timeshare.payStatus.paid') }}</option><option value="partial">🔵 {{ t('backoffice.timeshare.payStatus.partial') }}</option>
      </select>
      <button v-if="auth.hasRole('timeshare_admin')" @click="generateMaintenanceDues" :disabled="generatingDues"
        class="min-h-[44px] px-4 py-2 rounded-xl bg-teal-50 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300 text-sm font-bold border border-teal-200 dark:border-teal-800 hover:bg-teal-100 dark:hover:bg-teal-950/60 disabled:opacity-50">
        🛠️ {{ generatingDues ? t('backoffice.timeshare.saving') : t('backoffice.timeshare.generateDues') }}
      </button>
    </div>

    <LoadingState v-if="maintLoading" :label="t('backoffice.timeshare.loadingMaintenanceDues')" />
    <AppCard v-else padding="none">
      <EmptyState v-if="!maintenanceDues.length" icon="🛠️" :title="t('backoffice.timeshare.noResults')" />
      <div v-else class="overflow-x-auto">
      <table class="w-full min-w-[720px] text-sm">
        <thead class="bg-stone-50 dark:bg-gray-800/60"><tr>
          <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.customer') }}</th>
          <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.year') }}</th>
          <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.dueDate') }}</th>
          <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.amount') }}</th>
          <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.status') }}</th>
          <th class="px-4 py-3"></th>
        </tr></thead>
        <tbody class="divide-y divide-stone-100 dark:divide-border">
          <tr v-for="d in maintenanceDues" :key="d.id" :class="d.status === 'overdue' ? 'bg-red-50/50 dark:bg-red-950/20' : ''">
            <td class="px-4 py-3">
              <div class="font-bold text-gray-900 dark:text-gray-100">{{ d.customer_name }}</div>
              <div class="text-xs text-gray-500 dark:text-gray-400">{{ d.customer_phone }}</div>
            </td>
            <td class="px-4 py-3 text-gray-600 dark:text-gray-300">{{ d.fee_year }}</td>
            <td class="px-4 py-3"><span :class="d.status === 'overdue' ? 'text-red-600 dark:text-red-300 font-bold' : 'text-gray-600 dark:text-gray-300'">{{ formatDateValue(d.due_date) }}</span></td>
            <td class="px-4 py-3 font-bold">{{ fmt(d.amount) }}</td>
            <td class="px-4 py-3"><AppBadge size="sm" :variant="payStatusVariant[d.status] ?? 'neutral'">{{ payLabel(d.status) }}</AppBadge></td>
            <td class="px-4 py-3">
              <button v-if="d.status !== 'paid' && canCollectMaintenance" @click="openMaintenancePayModal(d)"
                class="min-h-[44px] px-3 py-2 rounded-xl bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 text-xs font-bold border border-green-200 dark:border-green-800 hover:bg-green-100">💰 {{ t('backoffice.timeshare.pay') }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      </div>
    </AppCard>

    <!-- ══ MAINTENANCE PAY MODAL ══ -->
    <AppModal :open="maintPayModal.open" :title="`🛠️ ${t('backoffice.timeshare.recordMaintenancePayment')}`" size="sm" @close="maintPayModal.open = false">
      <p class="text-sm text-gray-600 dark:text-gray-300 mb-4">{{ maintPayModal.customer_name }}</p>
      <div class="space-y-3">
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.amountPaid') }}</label>
          <input v-model.number="maintPayModal.amount" type="number" min="1" :placeholder="t('backoffice.timeshare.duePlaceholder', { amount: fmt(maintPayModal.due_amount) })"
            class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none focus:border-primary-500" />
        </div>
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.paymentMethod') }}</label>
          <select v-model="maintPayModal.method" class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none">
            <option value="bank_transfer">{{ t('backoffice.timeshare.paymentMethodBankTransfer') }}</option><option value="card">{{ t('backoffice.timeshare.paymentMethodCard') }}</option>
          </select>
        </div>
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.receiptNumberOptional') }}</label>
          <input v-model="maintPayModal.receipt_number" class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none" />
        </div>
      </div>
      <template #footer>
        <div class="flex gap-3">
          <AppButton variant="primary" block :loading="maintPayModal.saving" :disabled="!maintPayModal.amount" @click="submitMaintenancePayment">
            ✅ {{ t('backoffice.timeshare.confirmPayment') }}
          </AppButton>
          <AppButton variant="ghost" @click="maintPayModal.open = false">{{ t('backoffice.timeshare.cancelAction') }}</AppButton>
        </div>
      </template>
    </AppModal>
  </div>
</template>
