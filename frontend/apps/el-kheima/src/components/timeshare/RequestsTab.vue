<script setup lang="ts">
// طلبات زيارة العملاء (بوابة العميل العامة) — استُخرج من TimeshareView.vue
// (تقسيم الملفات الكبيرة، 2026-09-07).
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppModal, EmptyState, LoadingState, useToast } from '@resort-os/ui'
import TimeshareUnitPicker from '../TimeshareUnitPicker.vue'

const props = defineProps<{ branchId: number | null }>()
const emit = defineEmits<{ changed: [] }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface VisitRequestItem {
  id: number; contract_id: number; preferred_start: string; preferred_end: string
  notes: string | null; status: string; rejection_reason: string | null
  customer_name?: string; customer_phone?: string; contract_number?: string
  room_type?: string | null; contract_unit_id?: number | null; unit_capacity?: number | null
}

const toast = useToast()
const { t } = useI18n()
const { formatDate } = useStaffFormat()
const auth = useAuthStore()
const branchId = computed(() => props.branchId)

function formatDateValue(d?: string) {
  if (!d) return '—'
  try { return formatDate(d, { day: 'numeric', month: 'short', year: 'numeric' }) }
  catch { return d }
}

const visitRequests = ref<VisitRequestItem[]>([])
const requestsLoading = ref(false)
const requestsStatus = ref('pending')

async function loadVisitRequests() {
  requestsLoading.value = true
  try {
    const r = await api.get('/api/v1/timeshare/visit-requests', { params: { branch_id: branchId.value, status: requestsStatus.value || undefined } })
    visitRequests.value = r.data
  } catch { toast.error(t('backoffice.timeshare.msg.loadRequestsError')) } finally { requestsLoading.value = false }
}

const approveModal = ref({
  open: false, request: null as VisitRequestItem | null, check_in: '', check_out: '', saving: false, error: '',
  unitId: null as number | null,
})
const rejectModal = ref({ open: false, request: null as VisitRequestItem | null, reason: '', saving: false, error: '' })

function openApproveModal(r: VisitRequestItem) {
  approveModal.value = {
    open: true, request: r, check_in: r.preferred_start, check_out: r.preferred_end, saving: false, error: '',
    unitId: null,
  }
}
watch(() => [approveModal.value.check_in, approveModal.value.check_out], () => { approveModal.value.unitId = null })
async function confirmApprove() {
  if (!approveModal.value.request) return
  approveModal.value.saving = true
  approveModal.value.error = ''
  try {
    await api.post(`/api/v1/timeshare/visit-requests/${approveModal.value.request.id}/approve`, {
      check_in: approveModal.value.check_in, check_out: approveModal.value.check_out,
      unit_id: approveModal.value.unitId ?? undefined,
    })
    toast.success(t('backoffice.timeshare.msg.requestApproved'))
    approveModal.value.open = false
    await loadVisitRequests()
    emit('changed')
  } catch (e) {
    approveModal.value.error = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.requestApproveError')
  } finally { approveModal.value.saving = false }
}

function openRejectModal(r: VisitRequestItem) {
  rejectModal.value = { open: true, request: r, reason: '', saving: false, error: '' }
}
async function confirmReject() {
  if (!rejectModal.value.request) return
  if (rejectModal.value.reason.trim().length < 3) { rejectModal.value.error = t('backoffice.timeshare.reasonTooShort'); return }
  rejectModal.value.saving = true
  rejectModal.value.error = ''
  try {
    await api.post(`/api/v1/timeshare/visit-requests/${rejectModal.value.request.id}/reject`, { reason: rejectModal.value.reason.trim() })
    toast.success(t('backoffice.timeshare.msg.requestRejected'))
    rejectModal.value.open = false
    await loadVisitRequests()
    emit('changed')
  } catch (e) {
    rejectModal.value.error = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.requestRejectError')
  } finally { rejectModal.value.saving = false }
}

onMounted(loadVisitRequests)
</script>

<template>
  <div class="space-y-4">
    <select v-model="requestsStatus" @change="loadVisitRequests" class="min-h-[44px] bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2">
      <option value="pending">⏳ {{ t('backoffice.timeshare.requestStatus.pending') }}</option>
      <option value="approved">✅ {{ t('backoffice.timeshare.requestStatus.approved') }}</option>
      <option value="rejected">❌ {{ t('backoffice.timeshare.requestStatus.rejected') }}</option>
      <option value="">{{ t('backoffice.timeshare.allStatuses') }}</option>
    </select>

    <LoadingState v-if="requestsLoading" :label="t('backoffice.timeshare.loadingRequests')" />
    <AppCard v-else padding="none">
      <EmptyState v-if="!visitRequests.length" icon="📝" :title="t('backoffice.timeshare.noResults')" />
      <div v-else class="divide-y divide-stone-100 dark:divide-border">
        <div v-for="r in visitRequests" :key="r.id" class="p-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div class="font-bold text-gray-900 dark:text-gray-100">{{ r.customer_name }} — {{ r.contract_number }}</div>
            <div class="text-sm text-gray-600 dark:text-gray-300">{{ formatDateValue(r.preferred_start) }} → {{ formatDateValue(r.preferred_end) }}</div>
            <div v-if="r.notes" class="text-xs text-gray-500 dark:text-gray-400 mt-1">💬 {{ r.notes }}</div>
            <div v-if="r.rejection_reason" class="text-xs text-red-600 dark:text-red-300 mt-1">✋ {{ r.rejection_reason }}</div>
          </div>
          <div class="flex items-center gap-2">
            <AppBadge size="sm" :variant="r.status === 'pending' ? 'warning' : r.status === 'approved' ? 'success' : 'neutral'">{{ t(`backoffice.timeshare.requestStatus.${r.status}`) }}</AppBadge>
            <template v-if="r.status === 'pending' && auth.hasRole('timeshare_admin')">
              <button @click="openApproveModal(r)" class="min-h-[44px] px-3 py-2 rounded-xl bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 text-xs font-bold border border-green-200 dark:border-green-800 hover:bg-green-100">✅ {{ t('backoffice.timeshare.approve') }}</button>
              <button @click="openRejectModal(r)" class="min-h-[44px] px-3 py-2 rounded-xl bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300 text-xs font-bold border border-red-200 dark:border-red-800 hover:bg-red-100">❌ {{ t('backoffice.timeshare.reject') }}</button>
            </template>
          </div>
        </div>
      </div>
    </AppCard>

    <!-- ══ APPROVE VISIT REQUEST MODAL ══ -->
    <AppModal :open="approveModal.open" :title="`✅ ${t('backoffice.timeshare.approveRequestTitle')}`" size="sm" @close="approveModal.open = false">
      <div v-if="approveModal.request" class="space-y-3">
        <p class="text-sm text-gray-600 dark:text-gray-300">{{ approveModal.request.customer_name }} — {{ approveModal.request.contract_number }}</p>
        <p class="text-xs text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.approveRequestHint') }}</p>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.timeshare.scheduleVisit.checkIn') }}
          <input v-model="approveModal.check_in" type="date" class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.timeshare.scheduleVisit.checkOut') }}
          <input v-model="approveModal.check_out" type="date" class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <TimeshareUnitPicker
          v-model="approveModal.unitId"
          :branch-id="branchId"
          :unit-type="approveModal.request.room_type ?? ''"
          :check-in="approveModal.check_in"
          :check-out="approveModal.check_out"
          :contract-unit-id="approveModal.request.contract_unit_id ?? null"
          :unit-capacity="approveModal.request.unit_capacity ?? null"
        />
        <p v-if="approveModal.error" class="text-sm text-red-600 dark:text-red-400">{{ approveModal.error }}</p>
        <AppButton class="w-full min-h-[44px]" :disabled="approveModal.saving" @click="confirmApprove">{{ approveModal.saving ? t('backoffice.timeshare.saving') : t('backoffice.timeshare.confirmApprove') }}</AppButton>
      </div>
    </AppModal>

    <!-- ══ REJECT VISIT REQUEST MODAL ══ -->
    <AppModal :open="rejectModal.open" :title="`❌ ${t('backoffice.timeshare.rejectRequestTitle')}`" size="sm" @close="rejectModal.open = false">
      <div v-if="rejectModal.request" class="space-y-3">
        <p class="text-sm text-gray-600 dark:text-gray-300">{{ rejectModal.request.customer_name }} — {{ rejectModal.request.contract_number }}</p>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.timeshare.rejectionReason') }}
          <textarea v-model="rejectModal.reason" rows="3" class="w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm resize-none" />
        </label>
        <p v-if="rejectModal.error" class="text-sm text-red-600 dark:text-red-400">{{ rejectModal.error }}</p>
        <AppButton variant="danger" class="w-full min-h-[44px]" :disabled="rejectModal.saving" @click="confirmReject">{{ rejectModal.saving ? t('backoffice.timeshare.saving') : t('backoffice.timeshare.confirmReject') }}</AppButton>
      </div>
    </AppModal>
  </div>
</template>
