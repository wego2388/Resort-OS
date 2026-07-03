<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')
const tab = ref<'employees' | 'attendance' | 'payroll' | 'leaves'>('employees')

interface Employee {
  id: number; full_name: string; position: string; department?: string
  hire_date: string; basic_salary: number; status: string; phone?: string
}
interface PayrollRun {
  id: number; period_year: number; period_month: number; status: string
  total_net: number; total_gross: number
}
interface LeaveRequest {
  id: number; employee_id: number; leave_type_id: number
  start_date: string; end_date: string; status: string; days_requested: number
}
interface LeaveType { id: number; name: string; name_ar?: string | null }
interface AttendanceRecord {
  id: number; employee_id: number; record_date: string
  check_in: string | null; check_out: string | null; status: string
  hours_worked: number | null
}

const employees = ref<Employee[]>([])
const payrollRuns = ref<PayrollRun[]>([])
const leaveRequests = ref<LeaveRequest[]>([])
const leaveTypes = ref<LeaveType[]>([])
const attendanceRecords = ref<AttendanceRecord[]>([])
const loading = ref(false)
const attendanceLoading = ref(false)

const today = new Date()
const attendanceDateFrom = ref(new Date(today.getFullYear(), today.getMonth(), 1).toISOString().slice(0, 10))
const attendanceDateTo = ref(today.toISOString().slice(0, 10))

const employeeNameById = computed(() => {
  const m: Record<number, string> = {}
  for (const e of employees.value) m[e.id] = e.full_name
  return m
})
const leaveTypeNameById = computed(() => {
  const m: Record<number, string> = {}
  for (const t of leaveTypes.value) m[t.id] = t.name_ar || t.name
  return m
})

async function fetchEmployees() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/hr/employees', { params: { branch_id: branchId, size: 100 } })
    employees.value = res.data.employees ?? res.data.items ?? res.data
  } catch (e) {
    console.error(e)
    toast.error('فشل تحميل بيانات الموظفين')
  } finally { loading.value = false }
}

async function fetchLeaveTypes() {
  try {
    const res = await api.get('/api/v1/hr/leave-types', { params: { branch_id: branchId } })
    leaveTypes.value = res.data ?? []
  } catch (e) {
    // غير حرج: أسماء أنواع الإجازات مجرد تسمية للعرض، بترجع لرقم النوع لو فشلت
    console.error(e)
  }
}

async function fetchPayroll() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/hr/payroll/runs', { params: { branch_id: branchId } })
    payrollRuns.value = res.data.runs ?? res.data.items ?? res.data
  } catch (e) {
    console.error(e)
    toast.error('فشل تحميل بيانات الرواتب')
  } finally { loading.value = false }
}

async function fetchLeaves() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/hr/leaves', { params: { branch_id: branchId, status: 'pending' } })
    leaveRequests.value = res.data.requests ?? res.data.items ?? res.data
    if (!employees.value.length) await fetchEmployees()
    if (!leaveTypes.value.length) await fetchLeaveTypes()
  } catch (e) {
    console.error(e)
    toast.error('فشل تحميل طلبات الإجازات')
  } finally { loading.value = false }
}

async function fetchAttendance() {
  attendanceLoading.value = true
  try {
    const res = await api.get('/api/v1/hr/attendance', {
      params: {
        branch_id: branchId,
        date_from: attendanceDateFrom.value,
        date_to: attendanceDateTo.value,
        size: 200,
      },
    })
    attendanceRecords.value = res.data.items ?? res.data
    if (!employees.value.length) await fetchEmployees()
  } catch (e) {
    console.error(e)
    toast.error('فشل تحميل سجلات الحضور')
  } finally { attendanceLoading.value = false }
}

async function loadTab(t: typeof tab.value) {
  tab.value = t
  if (t === 'employees') await fetchEmployees()
  if (t === 'payroll') await fetchPayroll()
  if (t === 'leaves') await fetchLeaves()
  if (t === 'attendance') await fetchAttendance()
}

async function approveLeave(id: number) {
  try {
    await api.patch(`/api/v1/hr/leaves/${id}`, { status: 'approved' })
    leaveRequests.value = leaveRequests.value.filter(l => l.id !== id)
    toast.success('تم اعتماد الإجازة')
  } catch (e) {
    console.error(e)
    toast.error('فشل في اعتماد الإجازة')
  }
}

async function rejectLeave(id: number) {
  try {
    await api.patch(`/api/v1/hr/leaves/${id}`, { status: 'rejected' })
    leaveRequests.value = leaveRequests.value.filter(l => l.id !== id)
    toast.success('تم رفض الإجازة')
  } catch (e) {
    console.error(e)
    toast.error('فشل في رفض الإجازة')
  }
}

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'
const statusVariant: Record<string, BadgeVariant> = {
  active: 'success', inactive: 'neutral', terminated: 'danger', on_leave: 'warning',
  pending: 'warning', approved: 'success', rejected: 'danger',
  processing: 'info', paid: 'success', draft: 'neutral',
  present: 'success', absent: 'danger', late: 'warning', leave: 'info', holiday: 'neutral',
}
const statusLabels: Record<string, string> = {
  active: 'نشط', inactive: 'غير نشط', terminated: 'منتهي الخدمة', on_leave: 'إجازة',
  pending: 'معلق', approved: 'معتمدة', rejected: 'مرفوضة',
  processing: 'قيد المعالجة', paid: 'مصروف', draft: 'مسودة',
  present: 'حاضر', absent: 'غائب', late: 'متأخر', leave: 'إجازة', holiday: 'عطلة',
}
function statusLabel(s: string) { return statusLabels[s] ?? s }

function formatDate(d?: string | null) {
  if (!d) return '—'
  try { return new Date(d).toLocaleDateString('ar-EG') } catch { return d }
}
function formatTime(d?: string | null) {
  if (!d) return '—'
  try { return new Date(d).toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' }) } catch { return d }
}
function monthLabel(year: number, month: number) {
  try { return new Date(year, month - 1, 1).toLocaleDateString('ar-EG', { month: 'long', year: 'numeric' }) }
  catch { return `${month}/${year}` }
}

onMounted(fetchEmployees)
</script>

<template>
  <div dir="rtl">
    <h2 class="text-2xl font-black text-gray-900 mb-6">الموارد البشرية</h2>

    <!-- Tabs -->
    <div class="flex gap-1 bg-stone-100 p-1 rounded-xl mb-6 w-fit">
      <button v-for="t in [
        { val: 'employees',  label: 'الموظفون' },
        { val: 'attendance', label: 'الحضور' },
        { val: 'payroll',    label: 'الرواتب' },
        { val: 'leaves',     label: 'الإجازات' },
      ]" :key="t.val"
        @click="loadTab(t.val as any)"
        :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all', tab === t.val ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700']"
      >{{ t.label }}</button>
    </div>

    <!-- Employees Tab -->
    <div v-if="tab === 'employees'">
      <div v-if="loading" class="flex flex-col items-center justify-center gap-3 py-12">
        <AppSpinner size="md" />
        <span class="text-sm text-gray-400">جاري التحميل...</span>
      </div>
      <AppCard v-else :title="`الموظفون (${employees.length})`" padding="none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الاسم</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الوظيفة</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">القسم</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الراتب</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الحالة</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="emp in employees" :key="emp.id" class="border-t border-stone-100 hover:bg-stone-50">
                <td class="px-4 py-3">
                  <div class="flex items-center gap-3">
                    <div class="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center text-blue-700 font-bold text-sm">
                      {{ emp.full_name.charAt(0) }}
                    </div>
                    <div>
                      <div class="font-semibold text-gray-900 text-sm">{{ emp.full_name }}</div>
                      <div v-if="emp.phone" class="text-xs text-gray-400">{{ emp.phone }}</div>
                    </div>
                  </div>
                </td>
                <td class="px-4 py-3 text-sm text-gray-700">{{ emp.position }}</td>
                <td class="px-4 py-3 text-sm text-gray-700">{{ emp.department ?? '—' }}</td>
                <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ (emp.basic_salary ?? 0).toLocaleString('ar-EG') }} ج</td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="statusVariant[emp.status] ?? 'neutral'">{{ statusLabel(emp.status) }}</AppBadge>
                </td>
              </tr>
              <tr v-if="employees.length === 0">
                <td colspan="5" class="px-4 py-12 text-center text-gray-400">لا يوجد موظفون</td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- Payroll Tab -->
    <div v-if="tab === 'payroll'">
      <div v-if="loading" class="flex flex-col items-center justify-center gap-3 py-12">
        <AppSpinner size="md" />
        <span class="text-sm text-gray-400">جاري التحميل...</span>
      </div>
      <div v-else-if="!payrollRuns.length">
        <EmptyState icon="💰" title="لا توجد دفعات رواتب" />
      </div>
      <div v-else class="space-y-3">
        <AppCard v-for="run in payrollRuns" :key="run.id" padding="md">
          <div class="flex items-center justify-between">
            <div>
              <div class="font-bold text-gray-900">{{ monthLabel(run.period_year, run.period_month) }}</div>
              <div class="text-sm text-gray-500 mt-0.5">إجمالي قبل الاستقطاعات: {{ (run.total_gross ?? 0).toLocaleString('ar-EG') }} ج</div>
            </div>
            <div class="text-left">
              <div class="text-xl font-black text-gray-900">{{ (run.total_net ?? 0).toLocaleString('ar-EG') }} ج</div>
              <AppBadge size="sm" :variant="statusVariant[run.status] ?? 'neutral'">{{ statusLabel(run.status) }}</AppBadge>
            </div>
          </div>
        </AppCard>
      </div>
    </div>

    <!-- Leaves Tab -->
    <div v-if="tab === 'leaves'">
      <div v-if="loading" class="flex flex-col items-center justify-center gap-3 py-12">
        <AppSpinner size="md" />
        <span class="text-sm text-gray-400">جاري التحميل...</span>
      </div>
      <div v-else-if="!leaveRequests.length">
        <EmptyState icon="🌴" title="لا توجد طلبات إجازات معلقة" />
      </div>
      <div v-else class="space-y-3">
        <AppCard v-for="leave in leaveRequests" :key="leave.id" padding="md">
          <div class="flex items-start justify-between">
            <div>
              <div class="font-bold text-gray-900">{{ employeeNameById[leave.employee_id] ?? `موظف #${leave.employee_id}` }}</div>
              <div class="text-sm text-gray-500">{{ leaveTypeNameById[leave.leave_type_id] ?? 'إجازة' }} — {{ leave.days_requested }} أيام</div>
              <div class="text-xs text-gray-400 mt-1">
                {{ formatDate(leave.start_date) }} → {{ formatDate(leave.end_date) }}
              </div>
            </div>
            <div class="flex items-center gap-2">
              <AppButton v-if="leave.status === 'pending'" size="sm" variant="primary" @click="approveLeave(leave.id)">موافقة</AppButton>
              <AppButton v-if="leave.status === 'pending'" size="sm" variant="danger" @click="rejectLeave(leave.id)">رفض</AppButton>
              <AppBadge v-else size="sm" :variant="statusVariant[leave.status] ?? 'neutral'">{{ statusLabel(leave.status) }}</AppBadge>
            </div>
          </div>
        </AppCard>
      </div>
    </div>

    <!-- Attendance Tab -->
    <div v-if="tab === 'attendance'" class="space-y-4">
      <div class="flex flex-wrap items-center gap-3">
        <label class="text-xs font-semibold text-gray-500">من</label>
        <input v-model="attendanceDateFrom" @change="fetchAttendance" type="date"
          class="bg-white border border-stone-200 text-gray-700 text-xs rounded-xl px-3 py-2 outline-none focus:border-primary-500" />
        <label class="text-xs font-semibold text-gray-500">إلى</label>
        <input v-model="attendanceDateTo" @change="fetchAttendance" type="date"
          class="bg-white border border-stone-200 text-gray-700 text-xs rounded-xl px-3 py-2 outline-none focus:border-primary-500" />
      </div>

      <div v-if="attendanceLoading" class="flex flex-col items-center justify-center gap-3 py-12">
        <AppSpinner size="md" />
        <span class="text-sm text-gray-400">جاري التحميل...</span>
      </div>
      <EmptyState v-else-if="!attendanceRecords.length" icon="⏰" title="لا توجد سجلات حضور"
        subtitle="لم يتم تسجيل أي حضور خلال الفترة المحددة" />
      <AppCard v-else padding="none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الموظف</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">التاريخ</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الحضور</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الانصراف</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">ساعات العمل</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الحالة</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="rec in attendanceRecords" :key="rec.id" class="border-t border-stone-100 hover:bg-stone-50">
                <td class="px-4 py-3 text-sm font-semibold text-gray-900">
                  {{ employeeNameById[rec.employee_id] ?? `موظف #${rec.employee_id}` }}
                </td>
                <td class="px-4 py-3 text-sm text-gray-700">{{ formatDate(rec.record_date) }}</td>
                <td class="px-4 py-3 text-sm text-gray-700">{{ formatTime(rec.check_in) }}</td>
                <td class="px-4 py-3 text-sm text-gray-700">{{ formatTime(rec.check_out) }}</td>
                <td class="px-4 py-3 text-sm text-gray-700">{{ rec.hours_worked != null ? rec.hours_worked.toFixed(2) : '—' }}</td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="statusVariant[rec.status] ?? 'neutral'">{{ statusLabel(rec.status) }}</AppBadge>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>
  </div>
</template>
