<script setup lang="ts">
/**
 * InvoiceLogModal — سجل فواتير الوردية الحالية (wagdy.md بند S-02).
 *
 * الباك إند (GET /finance/shifts/{id}/invoices، services.list_shift_invoices)
 * بيفرض قيدين: (1) كاشير يشوف وردية نفسه بس — أي وردية غيره PermissionError
 * →403، (2) حتى وردية نفسه محتاجة موافقة PIN مدير+ قبل ما التفاصيل تتعرض —
 * بيانات مالية تفصيلية حسّاسة. البوابة التانية دي هي PinGuardModal (S-03).
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppButton, AppModal, AppSpinner, EmptyState } from '@resort-os/ui'
import PinGuardModal from './PinGuardModal.vue'

const props = defineProps<{ shiftId: number }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
const { formatMoney, formatTime } = useStaffFormat()

interface InvoiceLine {
  payment_id: number
  folio_id: number
  guest_name: string
  amount: number | string
  method: string
  reference: string | null
  posted_at: string
  is_voided: boolean
  voided_at: string | null
}

const showPinGuard = ref(true)
const loading = ref(false)
const loadError = ref('')
const invoices = ref<InvoiceLine[]>([])

async function fetchInvoices(approverUserId: number | null, approverPin: string | null) {
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await api.get(ENDPOINTS.finance.shiftInvoices(props.shiftId), {
      params: approverUserId ? { approver_user_id: approverUserId, approver_pin: approverPin } : {},
    })
    invoices.value = data
    showPinGuard.value = false
  } catch (e: any) {
    // showPinGuard يفضل true — المستخدم يقدر يصحح الـ PIN ويحاول تاني
    loadError.value = e?.response?.data?.detail ?? t('backoffice.shiftDashboard.invoiceDetail.loadFailed')
  } finally {
    loading.value = false
  }
}

function onGuardApproved(payload: { approverUserId: number | null; approverPin: string | null }) {
  fetchInvoices(payload.approverUserId, payload.approverPin)
}

const methodLabel = computed<Record<string, string>>(() => ({
  cash: `💵 ${t('backoffice.shiftDashboard.invoiceDetail.methods.cash')}`,
  card: `💳 ${t('backoffice.shiftDashboard.invoiceDetail.methods.card')}`,
  bank_transfer: `🏦 ${t('backoffice.shiftDashboard.invoiceDetail.methods.bankTransfer')}`,
  credit: `📝 ${t('backoffice.shiftDashboard.invoiceDetail.methods.credit')}`,
  room: `🛏️ ${t('backoffice.shiftDashboard.invoiceDetail.methods.roomCharge')}`,
  room_charge: `🛏️ ${t('backoffice.shiftDashboard.invoiceDetail.methods.roomCharge')}`,
  other: t('backoffice.shiftDashboard.invoiceDetail.methods.other'),
}))

function fmtTime(iso: string): string {
  return formatTime(iso)
}
</script>

<template>
  <!-- بوابة موافقة PIN — أول ما الشاشة تفتح، قبل أي بيانات مالية تتعرض -->
  <PinGuardModal
    v-if="showPinGuard"
    :min-level="60"
    :title="t('backoffice.shiftDashboard.invoiceLog')"
    :message="t('backoffice.shiftDashboard.invoiceDetail.approvalMessage')"
    :loading="loading"
    :error-message="loadError"
    @approved="onGuardApproved"
    @cancel="emit('close')"
  />

  <AppModal v-else :open="true" :title="t('backoffice.shiftDashboard.invoiceLog')" size="md" @close="emit('close')">
    <div class="space-y-2">
      <div v-if="loading" class="flex items-center justify-center py-10"><AppSpinner /></div>
      <EmptyState v-else-if="!invoices.length" :title="t('backoffice.shiftDashboard.invoiceDetail.empty')" />
      <div v-else class="max-h-96 divide-y divide-stone-100 overflow-y-auto dark:divide-border">
        <div
          v-for="inv in invoices"
          :key="inv.payment_id"
          class="py-2.5 flex items-center justify-between gap-2"
          :class="inv.is_voided && 'opacity-50'"
        >
          <div>
            <div class="text-sm font-semibold text-gray-900 dark:text-gray-100" :class="inv.is_voided && 'line-through'">
              {{ inv.guest_name }}
            </div>
            <div class="text-xs text-gray-400">
              {{ methodLabel[inv.method] ?? inv.method }} — {{ fmtTime(inv.posted_at) }}
            </div>
            <div v-if="inv.is_voided" class="text-xs text-red-500 dark:text-red-300">{{ t('backoffice.shiftDashboard.invoiceDetail.voided') }}</div>
          </div>
          <div class="text-sm font-bold" :class="inv.is_voided ? 'text-gray-400 line-through' : 'text-blue-700 dark:text-blue-300'">
            {{ formatMoney(inv.amount, 'EGP') }}
          </div>
        </div>
      </div>
    </div>
    <template #footer>
      <AppButton variant="outline" block @click="emit('close')">
        {{ t('backoffice.shiftDashboard.invoiceDetail.close') }}
      </AppButton>
    </template>
  </AppModal>
</template>
