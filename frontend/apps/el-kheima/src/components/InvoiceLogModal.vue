<script setup lang="ts">
/**
 * InvoiceLogModal — سجل فواتير الوردية الحالية (wagdy.md بند S-02).
 *
 * الباك إند (GET /finance/shifts/{id}/invoices، services.list_shift_invoices)
 * بيفرض قيدين: (1) كاشير يشوف وردية نفسه بس — أي وردية غيره PermissionError
 * →403، (2) حتى وردية نفسه محتاجة موافقة PIN مدير+ قبل ما التفاصيل تتعرض —
 * بيانات مالية تفصيلية حسّاسة. البوابة التانية دي هي PinGuardModal (S-03).
 */
import { ref } from 'vue'
import { api, ENDPOINTS } from '@resort-os/core'
import { AppModal, AppSpinner, EmptyState } from '@resort-os/ui'
import PinGuardModal from './PinGuardModal.vue'

const props = defineProps<{ shiftId: number }>()
const emit = defineEmits<{ close: [] }>()

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
    loadError.value = e?.response?.data?.detail ?? 'تعذّر تحميل سجل الفواتير'
  } finally {
    loading.value = false
  }
}

function onGuardApproved(payload: { approverUserId: number | null; approverPin: string | null }) {
  fetchInvoices(payload.approverUserId, payload.approverPin)
}

const METHOD_LABEL: Record<string, string> = {
  cash: '💵 كاش',
  card: '💳 كارت',
  bank_transfer: '🏦 تحويل بنكي',
  credit: '📝 آجل',
  room_charge: '🛏️ حساب الغرفة',
  other: 'أخرى',
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <!-- بوابة موافقة PIN — أول ما الشاشة تفتح، قبل أي بيانات مالية تتعرض -->
  <PinGuardModal
    v-if="showPinGuard"
    :min-level="60"
    title="سجل فواتير الوردية"
    message="عرض تفاصيل فواتير الوردية يحتاج موافقة مدير بالـ PIN"
    :loading="loading"
    :error-message="loadError"
    @approved="onGuardApproved"
    @cancel="emit('close')"
  />

  <AppModal v-else :open="true" title="سجل فواتير الوردية" size="md" @close="emit('close')">
    <div dir="rtl" class="space-y-2">
      <div v-if="loading" class="flex items-center justify-center py-10"><AppSpinner /></div>
      <EmptyState v-else-if="!invoices.length" title="مفيش فواتير في الوردية دي لحد دلوقتي" />
      <div v-else class="divide-y divide-stone-100 max-h-96 overflow-y-auto">
        <div
          v-for="inv in invoices"
          :key="inv.payment_id"
          class="py-2.5 flex items-center justify-between gap-2"
          :class="inv.is_voided && 'opacity-50'"
        >
          <div>
            <div class="text-sm font-semibold text-gray-900" :class="inv.is_voided && 'line-through'">
              {{ inv.guest_name }}
            </div>
            <div class="text-xs text-gray-400">
              {{ METHOD_LABEL[inv.method] ?? inv.method }} — {{ fmtTime(inv.posted_at) }}
            </div>
            <div v-if="inv.is_voided" class="text-xs text-red-500">ملغاة</div>
          </div>
          <div class="text-sm font-bold" :class="inv.is_voided ? 'text-gray-400 line-through' : 'text-blue-700'">
            {{ inv.amount }} ج
          </div>
        </div>
      </div>
    </div>
    <template #footer>
      <button
        @click="emit('close')"
        class="w-full py-2 text-sm font-semibold text-gray-600 border border-stone-200 rounded-lg"
      >إغلاق</button>
    </template>
  </AppModal>
</template>
