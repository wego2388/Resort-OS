<script setup lang="ts">
// طلبات الإجازات المعلّقة — استُخرج من HRView.vue (تقسيم الملفات الكبيرة،
// 2026-09-07). employees/leaveTypes هنا نسخ محلية مستقلة (لعرض الأسماء) —
// نفس نمط تكرار الجلب المتبع في تقسيم FinanceView.vue/CRMView.vue.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

interface Employee { id: number; full_name: string }
interface LeaveType { id: number; name: string; name_ar?: string | null }
interface LeaveRequest {
  id: number; employee_id: number; leave_type_id: number
  start_date: string; end_date: string; status: string; days_requested: number
}
type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

const toast = useToast()
const { t } = useI18n()
const { formatDate: fmtDateFn } = useStaffFormat()
const branchId = computed(() => props.branchId)

function formatDate(d?: string | null) {
  if (!d) return '—'
  return fmtDateFn(d)
}
const statusVariant: Record<string, BadgeVariant> = {
  pending: 'warning', approved: 'success', rejected: 'danger',
}
const statusLabels = computed<Record<string, string>>(() => ({
  pending: t('backoffice.hr.status.pending'), approved: t('backoffice.hr.status.approved'), rejected: t('backoffice.hr.status.rejected'),
}))
function statusLabel(s: string) { return statusLabels.value[s] ?? s }

const loading = ref(false)
const employees = ref<Employee[]>([])
const leaveTypes = ref<LeaveType[]>([])
const leaveRequests = ref<LeaveRequest[]>([])

const employeeNameById = computed(() => {
  const m: Record<number, string> = {}
  for (const e of employees.value) m[e.id] = e.full_name
  return m
})
const leaveTypeNameById = computed(() => {
  const m: Record<number, string> = {}
  for (const lt of leaveTypes.value) m[lt.id] = lt.name_ar || lt.name
  return m
})

async function loadEmployeesForNames() {
  if (employees.value.length) return
  try {
    const res = await api.get('/api/v1/hr/employees', { params: { branch_id: branchId.value, size: 100 } })
    employees.value = res.data.employees ?? res.data.items ?? res.data
  } catch { /* غير حرج — الأسماء هتفضل بس بالرقم لو فشل */ }
}
async function fetchLeaveTypes() {
  try {
    const res = await api.get('/api/v1/hr/leave-types', { params: { branch_id: branchId.value } })
    leaveTypes.value = res.data ?? []
  } catch (e) {
    // غير حرج: أسماء أنواع الإجازات مجرد تسمية للعرض، بترجع لرقم النوع لو فشلت
  }
}

async function fetchLeaves() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/hr/leaves', { params: { branch_id: branchId.value, status: 'pending' } })
    leaveRequests.value = res.data.requests ?? res.data.items ?? res.data
    await loadEmployeesForNames()
    if (!leaveTypes.value.length) await fetchLeaveTypes()
  } catch (e) {
    toast.error(t('backoffice.hr.msg.loadLeavesError'))
  } finally { loading.value = false }
}

async function approveLeave(id: number) {
  try {
    await api.patch(`/api/v1/hr/leaves/${id}`, { status: 'approved' })
    leaveRequests.value = leaveRequests.value.filter(l => l.id !== id)
    toast.success(t('backoffice.hr.msg.leaveApproved'))
  } catch (e) {
    toast.error(t('backoffice.hr.msg.leaveApproveError'))
  }
}

async function rejectLeave(id: number) {
  try {
    await api.patch(`/api/v1/hr/leaves/${id}`, { status: 'rejected' })
    leaveRequests.value = leaveRequests.value.filter(l => l.id !== id)
    toast.success(t('backoffice.hr.msg.leaveRejected'))
  } catch (e) {
    toast.error(t('backoffice.hr.msg.leaveRejectError'))
  }
}

onMounted(fetchLeaves)
</script>

<template>
  <div>
    <div v-if="loading" class="flex flex-col items-center justify-center gap-3 py-12">
      <AppSpinner size="md" />
      <span class="text-sm text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.loading') }}</span>
    </div>
    <div v-else-if="!leaveRequests.length">
      <EmptyState icon="🌴" :title="t('backoffice.hr.noPendingLeaves')" />
    </div>
    <div v-else class="space-y-3">
      <AppCard v-for="leave in leaveRequests" :key="leave.id" padding="md">
        <div class="flex items-start justify-between">
          <div>
            <div class="font-bold text-gray-900 dark:text-gray-100">{{ employeeNameById[leave.employee_id] ?? t('backoffice.hr.employeeHash', { id: leave.employee_id }) }}</div>
            <div class="text-sm text-gray-500 dark:text-gray-400">{{ leaveTypeNameById[leave.leave_type_id] ?? t('backoffice.hr.status.leave') }} — {{ t('backoffice.hr.dayCount', { count: leave.days_requested }) }}</div>
            <div class="text-xs text-gray-400 dark:text-gray-400 mt-1">
              {{ formatDate(leave.start_date) }} → {{ formatDate(leave.end_date) }}
            </div>
          </div>
          <div class="flex items-center gap-2">
            <AppButton v-if="leave.status === 'pending'" size="sm" variant="primary" @click="approveLeave(leave.id)">{{ t('backoffice.hr.approve') }}</AppButton>
            <AppButton v-if="leave.status === 'pending'" size="sm" variant="danger" @click="rejectLeave(leave.id)">{{ t('backoffice.hr.reject') }}</AppButton>
            <AppBadge v-else size="sm" :variant="statusVariant[leave.status] ?? 'neutral'">{{ statusLabel(leave.status) }}</AppBadge>
          </div>
        </div>
      </AppCard>
    </div>
  </div>
</template>
