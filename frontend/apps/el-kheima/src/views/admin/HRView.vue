<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, parseApiTimestamp, useAuthStore } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppSpinner, AppModal, AppInput, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const auth = useAuthStore()
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

interface Allowance {
  id: number; employee_id: number; name: string; amount: number
  is_taxable: boolean; is_pensionable: boolean; is_active: boolean
}
interface PenaltyType { id: number; name: string; name_ar?: string | null; penalty_days: number }
interface AttendancePolicy {
  late_grace_minutes: number | string; early_leave_grace_minutes: number | string
  standard_shift_start: string; standard_shift_end: string
  overtime_rate_multiplier: number | string; late_penalty_rate_multiplier: number | string
  is_active: boolean
}

const employees = ref<Employee[]>([])
const payrollRuns = ref<PayrollRun[]>([])
const leaveRequests = ref<LeaveRequest[]>([])
const leaveTypes = ref<LeaveType[]>([])
const attendanceRecords = ref<AttendanceRecord[]>([])
const loading = ref(false)
const attendanceLoading = ref(false)

// toISOString() بترجّع تاريخ UTC مش التاريخ المحلي (توقيت القاهرة) — بالقرب
// من منتصف الليل المحلي كانت بترجع يوم مختلف عن اليوم الحقيقي. نفس فئة باج
// AttendanceView.vue (راجع localDateStr هناك).
function localDateStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const today = new Date()
const attendanceDateFrom = ref(localDateStr(new Date(today.getFullYear(), today.getMonth(), 1)))
const attendanceDateTo = ref(localDateStr(today))

// سياسة الحضور — سماحية تأخير/انصراف مبكر، الوردية الافتراضية، نسب أوفرتايم/
// خصم تأخير — بتغذّي الحساب التلقائي في تشغيل الرواتب (backend: hr_engine.
// compute_attendance_minutes). مفيش سياسة محفوظة بعد = صفر تلقائي، مش عطل.
const DEFAULT_POLICY: AttendancePolicy = {
  late_grace_minutes: 10, early_leave_grace_minutes: 10,
  standard_shift_start: '09:00', standard_shift_end: '17:00',
  overtime_rate_multiplier: '1.50', late_penalty_rate_multiplier: '1.00',
  is_active: true,
}
const attendancePolicy = ref<AttendancePolicy>({ ...DEFAULT_POLICY })
const policyConfigured = ref(false)
const policyLoading = ref(false)
const policySaving = ref(false)

async function fetchAttendancePolicy() {
  policyLoading.value = true
  try {
    const res = await api.get('/api/v1/hr/attendance-policy', { params: { branch_id: branchId } })
    attendancePolicy.value = res.data
    policyConfigured.value = true
  } catch (e: any) {
    if (e?.response?.status === 404) {
      attendancePolicy.value = { ...DEFAULT_POLICY }
      policyConfigured.value = false
    } else {
      console.error(e)
      toast.error('فشل تحميل سياسة الحضور')
    }
  } finally { policyLoading.value = false }
}

async function saveAttendancePolicy() {
  policySaving.value = true
  try {
    const res = await api.put('/api/v1/hr/attendance-policy', attendancePolicy.value, { params: { branch_id: branchId } })
    attendancePolicy.value = res.data
    policyConfigured.value = true
    toast.success('تم حفظ سياسة الحضور')
  } catch (e) {
    console.error(e)
    toast.error('فشل حفظ سياسة الحضور')
  } finally { policySaving.value = false }
}

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
  await fetchAttendancePolicy()
}

// ── Allowances / Penalties — نموذج بسيط لـ endpoints اليوم دي (كانت
// EmployeeAllowance/PenaltyType موجودين بالكامل في الباك إند من غير أي شاشة
// تستخدمهم — نفس فئة الباج الموثّقة في CLAUDE.md). فورم صغير جوه مودال بدل
// شاشة منفصلة كاملة، لأن العملية نفسها بسيطة (إضافة سطر واحد لموظف واحد).
const allowanceModalEmployee = ref<Employee | null>(null)
const employeeAllowances = ref<Allowance[]>([])
const allowancesLoading = ref(false)
const allowanceForm = ref({ name: '', amount: 0, is_taxable: true, is_pensionable: false })
const savingAllowance = ref(false)

const penaltyModalEmployee = ref<Employee | null>(null)
const penaltyTypes = ref<PenaltyType[]>([])
const penaltyForm = ref({ penalty_type_id: null as number | null, penalty_days: 1, reason: '' })
const savingPenalty = ref(false)

async function openAllowanceModal(emp: Employee) {
  allowanceModalEmployee.value = emp
  allowanceForm.value = { name: '', amount: 0, is_taxable: true, is_pensionable: false }
  allowancesLoading.value = true
  try {
    const res = await api.get(`/api/v1/hr/employees/${emp.id}/allowances`, { params: { active_only: true } })
    employeeAllowances.value = res.data ?? []
  } catch (e) {
    console.error(e)
    toast.error('فشل تحميل بدلات الموظف')
  } finally { allowancesLoading.value = false }
}

async function submitAllowance() {
  if (!allowanceModalEmployee.value) return
  // AppInput لا يطبّق مودفاير .number تلقائيًا (component مبني بـ defineProps
  // عادي مش defineModel) — القيمة اللي بترجع ممكن تكون string، فلازم تحويل
  // صريح هنا قبل أي مقارنة رقمية أو إرسال للباك إند.
  const amount = Number(allowanceForm.value.amount)
  if (!allowanceForm.value.name.trim() || !(amount > 0)) {
    toast.error('اسم البدل والمبلغ (أكبر من صفر) مطلوبان')
    return
  }
  savingAllowance.value = true
  try {
    const empId = allowanceModalEmployee.value.id
    const { data } = await api.post(`/api/v1/hr/employees/${empId}/allowances`, {
      employee_id: empId, ...allowanceForm.value, amount,
    })
    employeeAllowances.value = [...employeeAllowances.value, data]
    allowanceForm.value = { name: '', amount: 0, is_taxable: true, is_pensionable: false }
    toast.success('تمت إضافة البدل — سيدخل في حساب الراتب القادم')
  } catch (e: any) {
    console.error(e)
    toast.error(e?.response?.data?.detail ?? 'فشل حفظ البدل')
  } finally { savingAllowance.value = false }
}

async function openPenaltyModal(emp: Employee) {
  penaltyModalEmployee.value = emp
  penaltyForm.value = { penalty_type_id: null, penalty_days: 1, reason: '' }
  try {
    const res = await api.get('/api/v1/hr/penalty-types', { params: { branch_id: branchId } })
    penaltyTypes.value = res.data ?? []
  } catch (e) {
    console.error(e)
    toast.error('فشل تحميل أنواع الجزاءات')
  }
}

function onPenaltyTypeChange() {
  const t = penaltyTypes.value.find(pt => pt.id === penaltyForm.value.penalty_type_id)
  if (t) penaltyForm.value.penalty_days = t.penalty_days
}

async function submitPenalty() {
  if (!penaltyModalEmployee.value) return
  const penaltyDays = Number(penaltyForm.value.penalty_days)
  if (!penaltyForm.value.reason.trim() || !(penaltyDays > 0)) {
    toast.error('السبب وعدد الأيام (أكبر من صفر) مطلوبان')
    return
  }
  savingPenalty.value = true
  try {
    const empId = penaltyModalEmployee.value.id
    await api.post('/api/v1/hr/penalties', {
      employee_id: empId, branch_id: branchId,
      penalty_type_id: penaltyForm.value.penalty_type_id,
      penalty_date: localDateStr(new Date()),
      penalty_days: penaltyDays,
      reason: penaltyForm.value.reason,
      applied_by: auth.user?.id,
    })
    toast.success('تم تسجيل الجزاء')
    penaltyModalEmployee.value = null
  } catch (e: any) {
    console.error(e)
    toast.error(e?.response?.data?.detail ?? 'فشل حفظ الجزاء')
  } finally { savingPenalty.value = false }
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
  // check_in/check_out من الباك إند naive UTC (بدون "Z") — لازم parseApiTimestamp
  // مش new Date() الخام، وإلا وقت الحضور المعروض للمدير يبقى مزاح بفرق توقيت
  // القاهرة عن UTC (نفس فئة باج الـ KDS الموثّقة في @resort-os/core/utils/dates).
  try { return parseApiTimestamp(d).toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' }) } catch { return d }
}
function monthLabel(year: number, month: number) {
  try { return new Date(year, month - 1, 1).toLocaleDateString('ar-EG', { month: 'long', year: 'numeric' }) }
  catch { return `${month}/${year}` }
}

// ── #8: تصحيح سجل حضور يدويًا (موظف نسي يبصم انصراف، وقت خطأ...) ──────
// <input type="datetime-local"> بيشتغل بتوقيت المتصفح المحلي بدون أي معلومة
// timezone — لازم تحويل صريح للـ UTC الخام (naive) اللي الباك إند مخزّنه،
// نفس منطق parseApiTimestamp بالظبط لكن بالعكس.
const editingAttendance = ref<AttendanceRecord | null>(null)
const editForm = ref<{ check_in: string; check_out: string; status: string; notes: string }>({
  check_in: '', check_out: '', status: '', notes: '',
})
const savingAttendanceEdit = ref(false)

function toDatetimeLocalInput(iso: string | null): string {
  if (!iso) return ''
  const d = parseApiTimestamp(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
function fromDatetimeLocalInput(value: string): string | null {
  if (!value) return null
  return new Date(value).toISOString().replace('Z', '')
}

function openEditAttendance(rec: AttendanceRecord) {
  editingAttendance.value = rec
  editForm.value = {
    check_in:  toDatetimeLocalInput(rec.check_in),
    check_out: toDatetimeLocalInput(rec.check_out),
    status:    rec.status,
    notes:     '',
  }
}

async function saveAttendanceEdit() {
  if (!editingAttendance.value) return
  savingAttendanceEdit.value = true
  try {
    await api.patch(`/api/v1/hr/attendance/${editingAttendance.value.id}`, {
      check_in:  fromDatetimeLocalInput(editForm.value.check_in),
      check_out: fromDatetimeLocalInput(editForm.value.check_out),
      status:    editForm.value.status,
      notes:     editForm.value.notes || undefined,
    })
    toast.success('تم تصحيح سجل الحضور')
    editingAttendance.value = null
    await fetchAttendance()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر حفظ التصحيح')
  } finally {
    savingAttendanceEdit.value = false
  }
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
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">إجراءات</th>
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
                <td class="px-4 py-3">
                  <div class="flex items-center gap-2">
                    <button @click="openAllowanceModal(emp)" class="text-xs font-semibold text-blue-600 hover:text-blue-800">+ بدل</button>
                    <button @click="openPenaltyModal(emp)" class="text-xs font-semibold text-red-600 hover:text-red-800">+ جزاء</button>
                  </div>
                </td>
              </tr>
              <tr v-if="employees.length === 0">
                <td colspan="6" class="px-4 py-12 text-center text-gray-400">لا يوجد موظفون</td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- Allowance Modal -->
    <AppModal :open="!!allowanceModalEmployee" :title="`بدلات — ${allowanceModalEmployee?.full_name ?? ''}`"
      @close="allowanceModalEmployee = null">
      <div class="space-y-4">
        <div v-if="allowancesLoading" class="text-center py-4 text-sm text-gray-400">جاري التحميل...</div>
        <div v-else-if="employeeAllowances.length" class="space-y-2">
          <div v-for="a in employeeAllowances" :key="a.id" class="flex items-center justify-between text-sm bg-stone-50 rounded-lg px-3 py-2">
            <span class="font-medium text-gray-800">{{ a.name }}</span>
            <span class="text-gray-600">{{ a.amount.toLocaleString('ar-EG') }} ج{{ a.is_taxable ? '' : ' (غير خاضع للضريبة)' }}</span>
          </div>
        </div>
        <EmptyState v-else icon="💵" title="لا يوجد بدلات مسجّلة" />

        <div class="border-t border-stone-100 pt-4 space-y-3">
          <div class="text-xs font-semibold text-gray-500 uppercase">إضافة بدل جديد</div>
          <AppInput v-model="allowanceForm.name" placeholder="اسم البدل (بدل سكن، انتقالات...)" />
          <AppInput v-model.number="allowanceForm.amount" type="number" placeholder="المبلغ (جنيه)" />
          <div class="flex items-center gap-4 text-sm text-gray-700">
            <label class="flex items-center gap-1.5"><input type="checkbox" v-model="allowanceForm.is_taxable" /> خاضع للضريبة</label>
            <label class="flex items-center gap-1.5"><input type="checkbox" v-model="allowanceForm.is_pensionable" /> خاضع للتأمينات</label>
          </div>
          <AppButton :disabled="savingAllowance" @click="submitAllowance" variant="primary" size="sm">
            {{ savingAllowance ? 'جاري الحفظ...' : 'إضافة البدل' }}
          </AppButton>
        </div>
      </div>
    </AppModal>

    <!-- Penalty Modal -->
    <AppModal :open="!!penaltyModalEmployee" :title="`تسجيل جزاء — ${penaltyModalEmployee?.full_name ?? ''}`"
      @close="penaltyModalEmployee = null">
      <div class="space-y-3">
        <select v-model="penaltyForm.penalty_type_id" @change="onPenaltyTypeChange"
          class="w-full bg-white border border-stone-200 text-gray-700 text-sm rounded-xl px-3 py-2 outline-none focus:border-primary-500">
          <option :value="null">نوع الجزاء (اختياري)</option>
          <option v-for="pt in penaltyTypes" :key="pt.id" :value="pt.id">{{ pt.name_ar || pt.name }} ({{ pt.penalty_days }} يوم)</option>
        </select>
        <AppInput v-model.number="penaltyForm.penalty_days" type="number" placeholder="عدد أيام الجزاء" />
        <AppInput v-model="penaltyForm.reason" placeholder="السبب" />
        <AppButton :disabled="savingPenalty" @click="submitPenalty" variant="danger" size="sm">
          {{ savingPenalty ? 'جاري الحفظ...' : 'تسجيل الجزاء' }}
        </AppButton>
      </div>
    </AppModal>

    <!-- #8: تصحيح سجل حضور -->
    <AppModal :open="!!editingAttendance"
      :title="`تصحيح حضور — ${editingAttendance ? (employeeNameById[editingAttendance.employee_id] ?? `موظف #${editingAttendance.employee_id}`) : ''}`"
      @close="editingAttendance = null">
      <div class="space-y-3">
        <label class="block text-xs font-semibold text-gray-500">وقت الحضور</label>
        <input v-model="editForm.check_in" type="datetime-local"
          class="w-full bg-white border border-stone-200 text-gray-700 text-sm rounded-xl px-3 py-2 outline-none focus:border-primary-500" />
        <label class="block text-xs font-semibold text-gray-500">وقت الانصراف</label>
        <input v-model="editForm.check_out" type="datetime-local"
          class="w-full bg-white border border-stone-200 text-gray-700 text-sm rounded-xl px-3 py-2 outline-none focus:border-primary-500" />
        <label class="block text-xs font-semibold text-gray-500">الحالة</label>
        <select v-model="editForm.status"
          class="w-full bg-white border border-stone-200 text-gray-700 text-sm rounded-xl px-3 py-2 outline-none focus:border-primary-500">
          <option value="present">حاضر</option>
          <option value="absent">غائب</option>
          <option value="late">متأخر</option>
          <option value="leave">إجازة</option>
          <option value="holiday">عطلة</option>
        </select>
        <AppInput v-model="editForm.notes" placeholder="سبب التصحيح (اختياري لكن مستحسن)" />
        <AppButton :disabled="savingAttendanceEdit" @click="saveAttendanceEdit" variant="primary" size="sm">
          {{ savingAttendanceEdit ? 'جاري الحفظ...' : 'حفظ التصحيح' }}
        </AppButton>
      </div>
    </AppModal>

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

      <!-- سياسة الحضور — سماحية التأخير/الانصراف المبكر ونسب الأوفرتايم/الخصم
           التلقائي المستخدمة في تشغيل الرواتب -->
      <AppCard title="سياسة الحضور والانصراف" padding="md">
        <div v-if="policyLoading" class="flex items-center gap-3 py-4">
          <AppSpinner size="sm" />
          <span class="text-sm text-gray-400">جاري التحميل...</span>
        </div>
        <div v-else class="space-y-4">
          <p v-if="!policyConfigured" class="text-xs text-amber-600 bg-amber-50 rounded-lg px-3 py-2">
            لا توجد سياسة محفوظة لهذا الفرع بعد — القيم دي افتراضية، احفظها عشان تُفعَّل فعليًا في حساب الرواتب.
          </p>
          <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
            <AppInput label="سماح تأخير (دقيقة)" type="number" v-model="attendancePolicy.late_grace_minutes" />
            <AppInput label="سماح انصراف مبكر (دقيقة)" type="number" v-model="attendancePolicy.early_leave_grace_minutes" />
            <AppInput label="بداية الوردية الافتراضية" type="time" v-model="attendancePolicy.standard_shift_start" />
            <AppInput label="نهاية الوردية الافتراضية" type="time" v-model="attendancePolicy.standard_shift_end" />
            <AppInput label="نسبة أجر الأوفرتايم (×)" type="number" v-model="attendancePolicy.overtime_rate_multiplier" />
            <AppInput label="نسبة خصم دقيقة التأخير (×)" type="number" v-model="attendancePolicy.late_penalty_rate_multiplier" />
          </div>
          <div class="flex justify-end">
            <AppButton size="sm" variant="primary" :disabled="policySaving" @click="saveAttendancePolicy">
              {{ policySaving ? 'جاري الحفظ...' : 'حفظ السياسة' }}
            </AppButton>
          </div>
        </div>
      </AppCard>

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
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase"></th>
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
                <td class="px-4 py-3 text-left">
                  <button @click="openEditAttendance(rec)" class="text-xs font-semibold text-primary-700 hover:underline">تعديل</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>
  </div>
</template>
