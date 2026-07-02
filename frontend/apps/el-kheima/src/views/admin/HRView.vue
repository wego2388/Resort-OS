<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'

const h = { Authorization: `Bearer ${localStorage.getItem('access_token')}` }
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')
const tab = ref<'employees' | 'attendance' | 'payroll' | 'leaves'>('employees')

interface Employee {
  id: number; full_name: string; job_title: string; department: string
  hire_date: string; base_salary: number; status: string; phone?: string
}
interface PayrollRun { id: number; period_start: string; period_end: string; status: string; total_net: number; employee_count: number }
interface LeaveRequest { id: number; employee_name: string; leave_type: string; start_date: string; end_date: string; status: string; days: number }

const employees = ref<Employee[]>([])
const payrollRuns = ref<PayrollRun[]>([])
const leaveRequests = ref<LeaveRequest[]>([])
const loading = ref(false)

async function fetchEmployees() {
  loading.value = true
  try {
    const res = await axios.get('/api/v1/hr/employees', { headers: h, params: { branch_id: branchId } })
    employees.value = res.data.employees ?? res.data.items ?? res.data
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

async function fetchPayroll() {
  loading.value = true
  try {
    const res = await axios.get('/api/v1/hr/payroll/runs', { headers: h, params: { branch_id: branchId } })
    payrollRuns.value = res.data.runs ?? res.data.items ?? res.data
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

async function fetchLeaves() {
  loading.value = true
  try {
    const res = await axios.get('/api/v1/hr/leaves', { headers: h, params: { branch_id: branchId, status: 'pending' } })
    leaveRequests.value = res.data.requests ?? res.data.items ?? res.data
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

async function loadTab(t: typeof tab.value) {
  tab.value = t
  if (t === 'employees') await fetchEmployees()
  if (t === 'payroll') await fetchPayroll()
  if (t === 'leaves') await fetchLeaves()
}

async function approveLeave(id: number) {
  try {
    await axios.patch(`/api/v1/hr/leaves/${id}`, { status: 'approved' }, { headers: h })
    leaveRequests.value = leaveRequests.value.filter(l => l.id !== id)
  } catch (e) { console.error(e) }
}

async function rejectLeave(id: number) {
  try {
    await axios.patch(`/api/v1/hr/leaves/${id}`, { status: 'rejected' }, { headers: h })
    leaveRequests.value = leaveRequests.value.filter(l => l.id !== id)
  } catch (e) { console.error(e) }
}

const statusColors: Record<string, string> = {
  active: 'bg-green-100 text-green-700',
  inactive: 'bg-gray-100 text-gray-600',
  terminated: 'bg-red-100 text-red-700',
  pending: 'bg-amber-100 text-amber-700',
  approved: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
  processing: 'bg-blue-100 text-blue-700',
  paid: 'bg-green-100 text-green-700',
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
      <div v-if="loading" class="text-center py-12 text-gray-400">جاري التحميل...</div>
      <div v-else class="bg-white rounded-2xl border border-stone-200 overflow-hidden shadow-sm">
        <div class="px-5 py-4 border-b border-stone-100 flex items-center justify-between">
          <span class="font-bold text-gray-900">الموظفون ({{ employees.length }})</span>
        </div>
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
                <td class="px-4 py-3 text-sm text-gray-700">{{ emp.job_title }}</td>
                <td class="px-4 py-3 text-sm text-gray-700">{{ emp.department }}</td>
                <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ emp.base_salary.toLocaleString('ar-EG') }} ج</td>
                <td class="px-4 py-3">
                  <span :class="['px-2 py-1 rounded-full text-xs font-medium', statusColors[emp.status] ?? 'bg-gray-100 text-gray-600']">
                    {{ emp.status === 'active' ? 'نشط' : emp.status === 'inactive' ? 'غير نشط' : emp.status }}
                  </span>
                </td>
              </tr>
              <tr v-if="employees.length === 0">
                <td colspan="5" class="px-4 py-12 text-center text-gray-400">لا يوجد موظفون</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Payroll Tab -->
    <div v-if="tab === 'payroll'">
      <div v-if="loading" class="text-center py-12 text-gray-400">جاري التحميل...</div>
      <div v-else class="space-y-3">
        <div v-for="run in payrollRuns" :key="run.id"
          class="bg-white rounded-2xl border border-stone-200 p-5 shadow-sm flex items-center justify-between"
        >
          <div>
            <div class="font-bold text-gray-900">
              {{ new Date(run.period_start).toLocaleDateString('ar-EG', { month: 'long', year: 'numeric' }) }}
            </div>
            <div class="text-sm text-gray-500 mt-0.5">{{ run.employee_count }} موظف</div>
          </div>
          <div class="text-left">
            <div class="text-xl font-black text-gray-900">{{ run.total_net.toLocaleString('ar-EG') }} ج</div>
            <span :class="['px-2 py-0.5 rounded-full text-xs font-medium', statusColors[run.status] ?? 'bg-gray-100 text-gray-600']">
              {{ run.status === 'paid' ? 'مصروف' : run.status === 'processing' ? 'قيد المعالجة' : run.status }}
            </span>
          </div>
        </div>
        <div v-if="payrollRuns.length === 0" class="text-center py-12 text-gray-400">لا توجد دفعات رواتب</div>
      </div>
    </div>

    <!-- Leaves Tab -->
    <div v-if="tab === 'leaves'">
      <div v-if="loading" class="text-center py-12 text-gray-400">جاري التحميل...</div>
      <div v-else class="space-y-3">
        <div v-for="leave in leaveRequests" :key="leave.id"
          class="bg-white rounded-2xl border border-stone-200 p-5 shadow-sm"
        >
          <div class="flex items-start justify-between">
            <div>
              <div class="font-bold text-gray-900">{{ leave.employee_name }}</div>
              <div class="text-sm text-gray-500">{{ leave.leave_type }} — {{ leave.days }} أيام</div>
              <div class="text-xs text-gray-400 mt-1">
                {{ new Date(leave.start_date).toLocaleDateString('ar-EG') }} → {{ new Date(leave.end_date).toLocaleDateString('ar-EG') }}
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button v-if="leave.status === 'pending'" @click="approveLeave(leave.id)"
                class="px-3 py-1.5 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700">موافقة</button>
              <button v-if="leave.status === 'pending'" @click="rejectLeave(leave.id)"
                class="px-3 py-1.5 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700">رفض</button>
              <span v-else :class="['px-2 py-1 rounded-full text-xs font-medium', statusColors[leave.status] ?? 'bg-gray-100 text-gray-600']">
                {{ leave.status === 'approved' ? 'معتمدة' : 'مرفوضة' }}
              </span>
            </div>
          </div>
        </div>
        <div v-if="leaveRequests.length === 0" class="text-center py-12 text-gray-400">لا توجد طلبات إجازات معلقة</div>
      </div>
    </div>

    <!-- Attendance Tab -->
    <div v-if="tab === 'attendance'" class="bg-white rounded-2xl border border-stone-200 p-8 text-center text-gray-400">
      <div class="text-4xl mb-3">⏰</div>
      <p class="font-medium text-gray-600 mb-2">سجلات الحضور</p>
      <p class="text-sm">سيتم تطوير هذا القسم قريباً — يعتمد على نظام البصمة</p>
    </div>
  </div>
</template>
