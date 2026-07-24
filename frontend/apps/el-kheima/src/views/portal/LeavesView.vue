<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS , useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const { t } = useI18n()
const { formatDate } = useStaffFormat()
const auth = useAuthStore()
const branchId = auth.branchId

interface Leave {
  id: number; leave_type_id: number; start_date: string; end_date: string
  days_requested: number; status: string; reason?: string
}
interface LeaveType { id: number; name: string; name_ar?: string }

const leaves = ref<Leave[]>([])
const leaveTypes = ref<LeaveType[]>([])
const loading = ref(false)
const showModal = ref(false)
const submitting = ref(false)
const successMsg = ref('')
const errorMsg = ref('')
const form = ref({ leave_type_id: null as number | null, start_date: '', end_date: '', reason: '' })

const leaveTypeLabel = computed(() => (id: number) => {
  const lt = leaveTypes.value.find(x => x.id === id)
  return lt ? (lt.name_ar || lt.name) : t('backoffice.leaves.typeHash', { id })
})

const statusColors: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300',
  approved: 'bg-green-100 text-green-700 dark:bg-green-950/50 dark:text-green-300',
  rejected: 'bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300',
}
const statusLabels = computed<Record<string, string>>(() => ({
  pending: t('backoffice.leaves.status.pending'), approved: t('backoffice.leaves.status.approved'), rejected: t('backoffice.leaves.status.rejected'),
}))

function calcDays() {
  if (!form.value.start_date || !form.value.end_date) return 0
  const diff = new Date(form.value.end_date).getTime() - new Date(form.value.start_date).getTime()
  return Math.max(0, Math.round(diff / 86400000) + 1)
}

async function fetchLeaveTypes() {
  try {
    const res = await api.get(ENDPOINTS.hr.leaveTypes, { params: { branch_id: branchId } })
    leaveTypes.value = res.data
    if (leaveTypes.value.length && form.value.leave_type_id === null) {
      form.value.leave_type_id = leaveTypes.value[0].id
    }
  } catch(e) {
    toast.error(t('backoffice.leaves.msg.loadTypesError'))
  }
}

async function fetchLeaves() {
  loading.value = true
  try {
    const res = await api.get(ENDPOINTS.hr_extra.meLeaves)
    leaves.value = res.data.items ?? []
  } catch(e) {
    toast.error(t('backoffice.leaves.msg.loadLeavesError'))
  } finally { loading.value = false }
}

async function requestLeave() {
  if (!form.value.start_date || !form.value.end_date || !form.value.leave_type_id) {
    errorMsg.value = t('backoffice.leaves.msg.fieldsRequired'); return
  }
  submitting.value = true; errorMsg.value = ''
  try {
    await api.post(ENDPOINTS.hr_extra.meLeaveRequest, {
      leave_type_id: form.value.leave_type_id,
      start_date: form.value.start_date,
      end_date: form.value.end_date,
      reason: form.value.reason || null,
    })
    showModal.value = false
    form.value = { leave_type_id: leaveTypes.value[0]?.id ?? null, start_date: '', end_date: '', reason: '' }
    successMsg.value = t('backoffice.leaves.msg.requestSubmitted')
    setTimeout(() => successMsg.value = '', 4000)
    await fetchLeaves()
  } catch(e: any) {
    errorMsg.value = e?.response?.data?.detail ?? t('backoffice.leaves.msg.submitError')
  } finally { submitting.value = false }
}

onMounted(() => { fetchLeaveTypes(); fetchLeaves() })
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <h2 class="font-bold text-gray-900 dark:text-gray-100 text-lg">{{ t('backoffice.leaves.title') }}</h2>
      <button @click="showModal = true"
        class="px-4 py-2 bg-blue-700 text-white rounded-xl text-sm font-bold hover:bg-blue-800 transition-colors">
        + {{ t('backoffice.leaves.requestLeave') }}
      </button>
    </div>

    <div v-if="successMsg" class="rounded-xl bg-green-100 px-4 py-3 text-sm font-medium text-green-700 dark:bg-green-950/50 dark:text-green-300">{{ successMsg }}</div>

    <div v-if="loading" class="flex flex-col items-center justify-center py-12 text-gray-400 dark:text-gray-400 gap-3">
      <AppSpinner size="lg" />
      <p>{{ t('backoffice.leaves.loading') }}</p>
    </div>
    <div v-else class="space-y-3">
      <div v-for="leave in leaves" :key="leave.id"
        class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border p-4 shadow-sm">
        <div class="flex items-start justify-between">
          <div>
            <div class="font-semibold text-gray-900 dark:text-gray-100">{{ leaveTypeLabel(leave.leave_type_id) }}</div>
            <div class="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
              {{ formatDate(leave.start_date) }}
              ←
              {{ formatDate(leave.end_date) }}
            </div>
            <div class="text-xs text-gray-400 dark:text-gray-400 mt-0.5">{{ t('backoffice.leaves.daysCount', { count: leave.days_requested }) }}</div>
            <div v-if="leave.reason" class="text-xs text-gray-500 dark:text-gray-400 mt-1.5 italic border-e-2 border-stone-200 dark:border-border pe-2">{{ leave.reason }}</div>
          </div>
          <span :class="['flex-shrink-0 rounded-full px-2.5 py-1 text-xs font-medium', statusColors[leave.status] ?? 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400']">
            {{ statusLabels[leave.status] ?? leave.status }}
          </span>
        </div>
      </div>

      <div v-if="leaves.length === 0" class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border">
        <EmptyState icon="🌴" :title="t('backoffice.leaves.noLeaveRequests')" :subtitle="t('backoffice.leaves.noLeaveRequestsHint')" />
      </div>
    </div>

    <!-- Request modal -->
    <Teleport to="body">
      <div v-if="showModal" class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" @click.self="showModal = false">
        <div class="bg-white dark:bg-surface rounded-2xl p-6 w-full max-w-sm shadow-2xl">
          <div class="flex items-center justify-between mb-5">
            <h3 class="font-bold text-gray-900 dark:text-gray-100 text-lg">{{ t('backoffice.leaves.newRequestTitle') }}</h3>
            <button @click="showModal = false" class="text-gray-400 dark:text-gray-400 hover:text-gray-600 text-2xl leading-none">×</button>
          </div>
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.leaves.leaveType') }}</label>
              <select v-model="form.leave_type_id"
                class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option v-for="lt in leaveTypes" :key="lt.id" :value="lt.id">{{ lt.name_ar || lt.name }}</option>
              </select>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.leaves.from') }}</label>
                <input v-model="form.start_date" type="date"
                  class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.leaves.to') }}</label>
                <input v-model="form.end_date" type="date"
                  class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
              </div>
            </div>
            <div v-if="calcDays() > 0" class="rounded-lg bg-blue-50 py-2 text-center text-sm font-medium text-blue-700 dark:bg-blue-950/40 dark:text-blue-300">
              {{ t('backoffice.leaves.daysCount', { count: calcDays() }) }}
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.leaves.reasonOptional') }}</label>
              <textarea v-model="form.reason" rows="2" :placeholder="t('backoffice.leaves.reasonPlaceholder')"
                class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none text-sm"/>
            </div>
            <div v-if="errorMsg" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-300">{{ errorMsg }}</div>
          </div>
          <div class="flex gap-2 mt-5">
            <button @click="showModal = false" class="flex-1 rounded-xl border-2 border-stone-200 py-2.5 text-sm font-semibold text-gray-600 hover:bg-gray-50 dark:bg-surface-2 dark:border-border dark:text-gray-400 dark:hover:bg-gray-800">{{ t('backoffice.leaves.cancel') }}</button>
            <button @click="requestLeave" :disabled="submitting"
              class="flex-1 py-2.5 bg-blue-700 text-white rounded-xl text-sm font-bold hover:bg-blue-800 disabled:opacity-50">
              {{ submitting ? t('backoffice.leaves.submitting') : t('backoffice.leaves.submitRequest') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
