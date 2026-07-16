<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, parseApiTimestamp, useAuthStore } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppSpinner, AppModal, AppInput, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const toast = useToast()
const { confirm } = useConfirm()
const auth = useAuthStore()
const branchId = auth.branchId
const tab = ref<'employees' | 'attendance' | 'payroll' | 'leaves' | 'leaderboard'>('employees')

interface Employee {
  id: number; full_name: string; position: string; department?: string
  hire_date: string; basic_salary: number; status: string; phone?: string
  insurance_base_salary?: number | null; holiday_bonus?: number
}
interface PayrollRun {
  id: number; period_year: number; period_month: number; status: string
  total_net: number; total_gross: number
}
interface PayrollLine {
  id: number; employee_id: number; net_salary: number; gross_salary: number
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
interface LeaderboardEntry {
  user_id: number; employee_name?: string | null; employee_code?: string | null
  total_sales: number; order_count: number
}

const employees = ref<Employee[]>([])
const payrollRuns = ref<PayrollRun[]>([])
// اعتماد الرواتب أصلاً على مستوى الدفعة الكاملة في الباك إند
// (POST /hr/payroll-runs/{id}/approve بيعتمد كل قسائم الموظفين في الدفعة
// دفعة واحدة، مفيش مفهوم اعتماد لكل قسيمة منفصل — راجع PayrollLine في
// backend/app/modules/hr/models.py، مفيهاش عمود status خالص). الفجوة كانت
// إن الشاشة دي ماكانش فيها زرار اعتماد خالص، فالمستخدم مكانش قادر يعتمد
// من هنا أصلاً (مش بس "واحد واحد").
const expandedRunId = ref<number | null>(null)
const payrollLinesByRun = ref<Record<number, PayrollLine[]>>({})
const payrollLinesLoading = ref(false)
const approvingRunId = ref<number | null>(null)
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
    toast.error('فشل تحميل بيانات الموظفين')
  } finally { loading.value = false }
}

async function fetchLeaveTypes() {
  try {
    const res = await api.get('/api/v1/hr/leave-types', { params: { branch_id: branchId } })
    leaveTypes.value = res.data ?? []
  } catch (e) {
    // غير حرج: أسماء أنواع الإجازات مجرد تسمية للعرض، بترجع لرقم النوع لو فشلت
  }
}

async function fetchPayroll() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/hr/payroll/runs', { params: { branch_id: branchId } })
    payrollRuns.value = res.data.runs ?? res.data.items ?? res.data
    if (!employees.value.length) await fetchEmployees()
  } catch (e) {
    toast.error('فشل تحميل بيانات الرواتب')
  } finally { loading.value = false }
}

// عرض قسائم كل الموظفين في الدفعة قبل الاعتماد — عشان المدير يشوف مين
// داخل في الدفعة والمبالغ قبل ما يعتمدها كلها بضغطة واحدة.
async function togglePayrollRunDetails(run: PayrollRun) {
  if (expandedRunId.value === run.id) {
    expandedRunId.value = null
    return
  }
  expandedRunId.value = run.id
  if (payrollLinesByRun.value[run.id]) return
  payrollLinesLoading.value = true
  try {
    const res = await api.get(`/api/v1/hr/payroll-runs/${run.id}/lines`)
    payrollLinesByRun.value = { ...payrollLinesByRun.value, [run.id]: res.data ?? [] }
  } catch (e) {
    toast.error('فشل تحميل قسائم الرواتب')
  } finally { payrollLinesLoading.value = false }
}

// اعتماد الدفعة كاملة — إجراء واحد يعتمد رواتب كل الموظفين في الدفعة دفعة
// واحدة (نفس الـ endpoint الموجود أصلاً في الباك إند)، بدل ما يكون المستخدم
// مضطر يفتح كل قسيمة لوحدها من غير ما يكون فيه زرار اعتماد أصلاً.
async function approvePayrollRun(run: PayrollRun) {
  const employeeCount = payrollLinesByRun.value[run.id]?.length
  const ok = await confirm({
    title: 'اعتماد صرف الرواتب',
    message: `هل تريد اعتماد رواتب ${monthLabel(run.period_year, run.period_month)}` +
      `${employeeCount ? ` لكل الموظفين (${employeeCount})` : ' لكل الموظفين'}؟ ` +
      'لا يمكن التراجع عن هذا الإجراء بعد الاعتماد.',
    confirmText: 'اعتماد الكل',
    danger: true,
  })
  if (!ok) return
  approvingRunId.value = run.id
  try {
    const res = await api.post(`/api/v1/hr/payroll-runs/${run.id}/approve`)
    const updated = res.data as PayrollRun
    payrollRuns.value = payrollRuns.value.map(r => (r.id === run.id ? { ...r, ...updated } : r))
    toast.success('تم اعتماد رواتب كل الموظفين في الدفعة')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'فشل اعتماد الرواتب')
  } finally { approvingRunId.value = null }
}

async function fetchLeaves() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/hr/leaves', { params: { branch_id: branchId, status: 'pending' } })
    leaveRequests.value = res.data.requests ?? res.data.items ?? res.data
    if (!employees.value.length) await fetchEmployees()
    if (!leaveTypes.value.length) await fetchLeaveTypes()
  } catch (e) {
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
    toast.error(e?.response?.data?.detail ?? 'فشل حفظ الجزاء')
  } finally { savingPenalty.value = false }
}

// ── wagdy.md H-04/H-05: وعاء تأمين منفصل + مكافأة عيد ثابتة — حقلان
// جديدان على Employee مش قابلين للتعديل من أي شاشة خالص لحد دلوقتي (حتى
// basic_salary نفسه مكانش قابل للتعديل من هنا) — مودال بسيط زي بدلات/جزاءات
// بدل شاشة تعديل موظف كاملة (out of scope لدفعة الشغل دي).
const compModalEmployee = ref<Employee | null>(null)
// insurance_base_salary فاضي = '' (مش null) — AppInput.modelValue بيقبل
// string | number بس، مش null.
const compForm = ref({ basic_salary: 0 as number | string, insurance_base_salary: '' as number | string, holiday_bonus: 0 as number | string })
const savingComp = ref(false)

function openCompModal(emp: Employee) {
  compModalEmployee.value = emp
  compForm.value = {
    basic_salary: emp.basic_salary ?? 0,
    insurance_base_salary: emp.insurance_base_salary ?? '',
    holiday_bonus: emp.holiday_bonus ?? 0,
  }
}

async function submitComp() {
  if (!compModalEmployee.value) return
  const basicSalary = Number(compForm.value.basic_salary)
  if (!(basicSalary > 0)) {
    toast.error('الراتب الأساسي لازم يكون أكبر من صفر')
    return
  }
  const insuranceBase = compForm.value.insurance_base_salary
  const insuranceBaseNum = insuranceBase === '' || insuranceBase === null || insuranceBase === undefined
    ? null : Number(insuranceBase)
  savingComp.value = true
  try {
    const empId = compModalEmployee.value.id
    const { data } = await api.patch(`/api/v1/hr/employees/${empId}`, {
      basic_salary: basicSalary,
      insurance_base_salary: insuranceBaseNum,
      holiday_bonus: Number(compForm.value.holiday_bonus) || 0,
    })
    employees.value = employees.value.map(e => (e.id === empId ? { ...e, ...data } : e))
    toast.success('تم تحديث بيانات الراتب')
    compModalEmployee.value = null
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'فشل حفظ بيانات الراتب')
  } finally { savingComp.value = false }
}

// ── wagdy.md H-01: سلفة راتب (قرض بأقساط شهرية ثابتة) ──────────────────
interface SalaryAdvance {
  id: number; employee_id: number; amount: number
  disbursed_date: string; monthly_deduction_amount: number
  remaining_balance: number; status: string; notes?: string | null
}
const advanceModalEmployee = ref<Employee | null>(null)
const employeeAdvances = ref<SalaryAdvance[]>([])
const advancesLoading = ref(false)
const advanceForm = ref({ amount: 0, disbursed_date: localDateStr(new Date()), monthly_deduction_amount: 0, notes: '' })
const savingAdvance = ref(false)

async function openAdvanceModal(emp: Employee) {
  advanceModalEmployee.value = emp
  advanceForm.value = { amount: 0, disbursed_date: localDateStr(new Date()), monthly_deduction_amount: 0, notes: '' }
  advancesLoading.value = true
  try {
    const res = await api.get('/api/v1/hr/salary-advances', { params: { employee_id: emp.id } })
    employeeAdvances.value = res.data ?? []
  } catch (e) {
    toast.error('فشل تحميل سلف الموظف')
  } finally { advancesLoading.value = false }
}

async function submitAdvance() {
  if (!advanceModalEmployee.value) return
  const amount = Number(advanceForm.value.amount)
  const monthlyDeduction = Number(advanceForm.value.monthly_deduction_amount)
  if (!(amount > 0) || !(monthlyDeduction > 0)) {
    toast.error('المبلغ والقسط الشهري (أكبر من صفر) مطلوبان')
    return
  }
  savingAdvance.value = true
  try {
    const empId = advanceModalEmployee.value.id
    const { data } = await api.post('/api/v1/hr/salary-advances', {
      employee_id: empId, branch_id: branchId,
      amount, disbursed_date: advanceForm.value.disbursed_date,
      monthly_deduction_amount: monthlyDeduction,
      notes: advanceForm.value.notes || undefined,
    })
    employeeAdvances.value = [data, ...employeeAdvances.value]
    advanceForm.value = { amount: 0, disbursed_date: localDateStr(new Date()), monthly_deduction_amount: 0, notes: '' }
    toast.success('تم تسجيل السلفة — سيبدأ خصمها من كشف الرواتب القادم')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'فشل حفظ السلفة')
  } finally { savingAdvance.value = false }
}

async function cancelAdvance(advance: SalaryAdvance) {
  const ok = await confirm({
    title: 'إلغاء السلفة',
    message: `هل تريد إلغاء السلفة (${advance.amount.toLocaleString('ar-EG')} ج)؟`,
    confirmText: 'إلغاء السلفة', danger: true,
  })
  if (!ok) return
  try {
    await api.patch(`/api/v1/hr/salary-advances/${advance.id}/cancel`, {})
    employeeAdvances.value = employeeAdvances.value.map(a => (a.id === advance.id ? { ...a, status: 'cancelled' } : a))
    toast.success('تم إلغاء السلفة')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'فشل إلغاء السلفة — ربما تم خصم قسط منها بالفعل')
  }
}

// ── wagdy.md H-02: دفعة يومية بسيطة تُخصم بالكامل في نفس الشهر ──────────
interface AdvancePayment {
  id: number; employee_id: number; amount: number; payment_date: string
  deducted: boolean; notes?: string | null
}
const paymentModalEmployee = ref<Employee | null>(null)
const employeePayments = ref<AdvancePayment[]>([])
const paymentsLoading = ref(false)
const paymentForm = ref({ amount: 0, payment_date: localDateStr(new Date()), notes: '' })
const savingPayment = ref(false)

async function openPaymentModal(emp: Employee) {
  paymentModalEmployee.value = emp
  paymentForm.value = { amount: 0, payment_date: localDateStr(new Date()), notes: '' }
  paymentsLoading.value = true
  try {
    const res = await api.get('/api/v1/hr/advance-payments', { params: { employee_id: emp.id } })
    employeePayments.value = res.data ?? []
  } catch (e) {
    toast.error('فشل تحميل دفعات الموظف')
  } finally { paymentsLoading.value = false }
}

async function submitPayment() {
  if (!paymentModalEmployee.value) return
  const amount = Number(paymentForm.value.amount)
  if (!(amount > 0)) {
    toast.error('المبلغ لازم يكون أكبر من صفر')
    return
  }
  savingPayment.value = true
  try {
    const empId = paymentModalEmployee.value.id
    const { data } = await api.post('/api/v1/hr/advance-payments', {
      employee_id: empId, branch_id: branchId,
      amount, payment_date: paymentForm.value.payment_date,
      notes: paymentForm.value.notes || undefined,
    })
    employeePayments.value = [data, ...employeePayments.value]
    paymentForm.value = { amount: 0, payment_date: localDateStr(new Date()), notes: '' }
    toast.success('تم تسجيل الدفعة — سيتم خصمها من صافي راتب نفس الشهر')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'فشل حفظ الدفعة')
  } finally { savingPayment.value = false }
}

// ── wagdy.md H-03: رصيد الإجازة الشهري المتحرّك (7.5 يوم/شهر) — للقراءة فقط،
// بيتحدّث تلقائيًا عبر Celery task شهري (hr_tasks.accrue_monthly_leave_ledger).
interface LeaveBalanceMonthly {
  id: number; period_year: number; period_month: number
  opening_balance: number; accrued: number; consumed: number; closing_balance: number
}
const balanceModalEmployee = ref<Employee | null>(null)
const employeeLeaveBalances = ref<LeaveBalanceMonthly[]>([])
const balancesLoading = ref(false)

async function openBalanceModal(emp: Employee) {
  balanceModalEmployee.value = emp
  balancesLoading.value = true
  try {
    const res = await api.get('/api/v1/hr/leave-balance-monthly', { params: { employee_id: emp.id } })
    employeeLeaveBalances.value = res.data ?? []
  } catch (e) {
    toast.error('فشل تحميل رصيد الإجازة')
  } finally { balancesLoading.value = false }
}

async function loadTab(t: typeof tab.value) {
  tab.value = t
  if (t === 'employees') await fetchEmployees()
  if (t === 'payroll') await fetchPayroll()
  if (t === 'leaves') await fetchLeaves()
  if (t === 'attendance') await fetchAttendance()
  if (t === 'leaderboard') await fetchLeaderboard()
}

// ── Leaderboard (wagdy.md P-11) ──────────────────────────────────────────
// GET /hr/leaderboard كان موجود بالكامل (مبيعات حقيقية من المطعم/الكافيه/
// الشاطئ مجمّعة بالموظف) من غير أي شاشة تعرضه.
function firstOfMonthStr(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}
function todayStr(): string {
  return new Date().toISOString().slice(0, 10)
}

const leaderboard = ref<LeaderboardEntry[]>([])
const leaderboardLoading = ref(false)
const leaderboardFrom = ref(firstOfMonthStr())
const leaderboardTo = ref(todayStr())

async function fetchLeaderboard() {
  leaderboardLoading.value = true
  try {
    const res = await api.get('/api/v1/hr/leaderboard', {
      params: { branch_id: branchId, date_from: leaderboardFrom.value, date_to: leaderboardTo.value },
    })
    leaderboard.value = res.data
  } catch (e) {
    toast.error('تعذّر تحميل لوحة الأداء')
  } finally { leaderboardLoading.value = false }
}

const leaderboardMedal = (rank: number) => rank === 0 ? '🥇' : rank === 1 ? '🥈' : rank === 2 ? '🥉' : `#${rank + 1}`

async function approveLeave(id: number) {
  try {
    await api.patch(`/api/v1/hr/leaves/${id}`, { status: 'approved' })
    leaveRequests.value = leaveRequests.value.filter(l => l.id !== id)
    toast.success('تم اعتماد الإجازة')
  } catch (e) {
    toast.error('فشل في اعتماد الإجازة')
  }
}

async function rejectLeave(id: number) {
  try {
    await api.patch(`/api/v1/hr/leaves/${id}`, { status: 'rejected' })
    leaveRequests.value = leaveRequests.value.filter(l => l.id !== id)
    toast.success('تم رفض الإجازة')
  } catch (e) {
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

// ── wagdy.md H-07: استيراد ملف حضور Excel (عمود موظف أول + عمود لكل يوم) ──
// نفس نمط استيراد عقود التايم شير (TimeshareView.vue) — رفع بضغطة واحدة،
// من غير معاينة مسبقة، ملخص النتيجة (استيراد/أخطاء/موظفين غير متعرّف
// عليهم) بيظهر بعد الرفع مباشرة.
interface AttendanceImportResult { imported: number; errors: string[]; unmatched_employees: string[] }
const showImportModal = ref(false)
const importFile = ref<File | null>(null)
const importPeriodYear = ref(today.getFullYear())
const importPeriodMonth = ref(today.getMonth() + 1)
const importUploading = ref(false)
const importResult = ref<AttendanceImportResult | { error: string } | null>(null)

function onImportFilePicked(e: Event) {
  const target = e.target as HTMLInputElement
  importFile.value = target.files?.[0] ?? null
  importResult.value = null
}

async function submitAttendanceImport() {
  if (!importFile.value || importUploading.value) return
  importUploading.value = true
  importResult.value = null
  try {
    const form = new FormData()
    form.append('file', importFile.value)
    const res = await api.post('/api/v1/hr/attendance/import-excel', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { branch_id: branchId, period_year: importPeriodYear.value, period_month: importPeriodMonth.value },
    })
    importResult.value = res.data
    toast.success(`تم استيراد ${res.data.imported} سجل حضور`)
    await fetchAttendance()
  } catch (e: any) {
    const msg = e?.response?.data?.detail ?? 'فشل الاستيراد'
    importResult.value = { error: msg }
    toast.error(msg)
  } finally {
    importUploading.value = false
  }
}

function openImportModal() {
  importFile.value = null
  importResult.value = null
  showImportModal.value = true
}

onMounted(fetchEmployees)
</script>

<template>
  <div dir="rtl">
    <h2 class="text-2xl font-black text-gray-900 dark:text-gray-100 mb-6">الموارد البشرية</h2>

    <!-- Tabs -->
    <div class="flex gap-1 bg-stone-100 dark:bg-gray-700 p-1 rounded-xl mb-6 w-fit">
      <button v-for="t in [
        { val: 'employees',   label: 'الموظفون' },
        { val: 'attendance',  label: 'الحضور' },
        { val: 'payroll',     label: 'الرواتب' },
        { val: 'leaves',      label: 'الإجازات' },
        { val: 'leaderboard', label: '🏆 لوحة الأداء' },
      ]" :key="t.val"
        @click="loadTab(t.val as any)"
        :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all', tab === t.val ? 'bg-white dark:bg-surface shadow-sm text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-500 hover:text-gray-700 dark:text-gray-300']"
      >{{ t.label }}</button>
    </div>

    <!-- Employees Tab -->
    <div v-if="tab === 'employees'">
      <div v-if="loading" class="flex flex-col items-center justify-center gap-3 py-12">
        <AppSpinner size="md" />
        <span class="text-sm text-gray-400 dark:text-gray-500">جاري التحميل...</span>
      </div>
      <AppCard v-else :title="`الموظفون (${employees.length})`" padding="none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الاسم</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الوظيفة</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">القسم</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الراتب</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الحالة</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">إجراءات</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="emp in employees" :key="emp.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3">
                  <div class="flex items-center gap-3">
                    <div class="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center text-blue-700 font-bold text-sm">
                      {{ emp.full_name.charAt(0) }}
                    </div>
                    <div>
                      <div class="font-semibold text-gray-900 dark:text-gray-100 text-sm">{{ emp.full_name }}</div>
                      <div v-if="emp.phone" class="text-xs text-gray-400 dark:text-gray-500">{{ emp.phone }}</div>
                    </div>
                  </div>
                </td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ emp.position }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ emp.department ?? '—' }}</td>
                <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">{{ (emp.basic_salary ?? 0).toLocaleString('ar-EG') }} ج</td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="statusVariant[emp.status] ?? 'neutral'">{{ statusLabel(emp.status) }}</AppBadge>
                </td>
                <td class="px-4 py-3">
                  <div class="flex items-center gap-2">
                    <button @click="openAllowanceModal(emp)" class="text-xs font-semibold text-blue-600 hover:text-blue-800">+ بدل</button>
                    <button @click="openPenaltyModal(emp)" class="text-xs font-semibold text-red-600 hover:text-red-800">+ جزاء</button>
                    <button v-if="auth.hasRole('admin')" @click="openAdvanceModal(emp)" class="text-xs font-semibold text-amber-600 hover:text-amber-800">💰 سلفة</button>
                    <button @click="openPaymentModal(emp)" class="text-xs font-semibold text-teal-600 hover:text-teal-800">📅 دفعة</button>
                    <button @click="openBalanceModal(emp)" class="text-xs font-semibold text-purple-600 hover:text-purple-800">📊 رصيد إجازة</button>
                    <button v-if="auth.hasRole('admin')" @click="openCompModal(emp)" class="text-xs font-semibold text-gray-600 dark:text-gray-500 hover:text-gray-900 dark:text-gray-100">✏️ الراتب</button>
                  </div>
                </td>
              </tr>
              <tr v-if="employees.length === 0">
                <td colspan="6" class="px-4 py-12 text-center text-gray-400 dark:text-gray-500">لا يوجد موظفون</td>
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
        <div v-if="allowancesLoading" class="text-center py-4 text-sm text-gray-400 dark:text-gray-500">جاري التحميل...</div>
        <div v-else-if="employeeAllowances.length" class="space-y-2">
          <div v-for="a in employeeAllowances" :key="a.id" class="flex items-center justify-between text-sm bg-stone-50 dark:bg-gray-800/60 rounded-lg px-3 py-2">
            <span class="font-medium text-gray-800 dark:text-gray-200">{{ a.name }}</span>
            <span class="text-gray-600 dark:text-gray-500">{{ a.amount.toLocaleString('ar-EG') }} ج{{ a.is_taxable ? '' : ' (غير خاضع للضريبة)' }}</span>
          </div>
        </div>
        <EmptyState v-else icon="💵" title="لا يوجد بدلات مسجّلة" />

        <div class="border-t border-stone-100 dark:border-border/50 pt-4 space-y-3">
          <div class="text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">إضافة بدل جديد</div>
          <AppInput v-model="allowanceForm.name" placeholder="اسم البدل (بدل سكن، انتقالات...)" />
          <AppInput v-model.number="allowanceForm.amount" type="number" placeholder="المبلغ (جنيه)" />
          <div class="flex items-center gap-4 text-sm text-gray-700 dark:text-gray-300">
            <label class="flex items-center gap-1.5"><input type="checkbox" v-model="allowanceForm.is_taxable" /> خاضع للضريبة</label>
            <label class="flex items-center gap-1.5"><input type="checkbox" v-model="allowanceForm.is_pensionable" /> خاضع للتأمينات</label>
          </div>
          <AppButton :disabled="savingAllowance" @click="submitAllowance" variant="primary" size="sm">
            {{ savingAllowance ? 'جاري الحفظ...' : 'إضافة البدل' }}
          </AppButton>
        </div>
      </div>
    </AppModal>

    <!-- wagdy.md H-04/H-05: تعديل الراتب الأساسي/وعاء التأمين/مكافأة العيد -->
    <AppModal :open="!!compModalEmployee" :title="`بيانات الراتب — ${compModalEmployee?.full_name ?? ''}`"
      @close="compModalEmployee = null">
      <div class="space-y-3">
        <AppInput label="الراتب الأساسي" v-model.number="compForm.basic_salary" type="number" />
        <div>
          <AppInput label="وعاء التأمينات الاجتماعية (اختياري)" v-model.number="compForm.insurance_base_salary" type="number"
            placeholder="اتركه فاضي لاستخدام الراتب الأساسي" />
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">لو مختلف عن الراتب الأساسي (بعض الموظفين وعاءهم التأميني المسجّل أقل) — لو فاضي، الراتب الأساسي هو المستخدَم.</p>
        </div>
        <div>
          <AppInput label="مكافأة الأعياد الرسمية" v-model.number="compForm.holiday_bonus" type="number" />
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">بند ثابت بيدخل الصافي تلقائيًا في كل كشف رواتب — صفّره بعد شهر العيد لو مش عايزه يتكرر.</p>
        </div>
        <AppButton :disabled="savingComp" @click="submitComp" variant="primary" size="sm">
          {{ savingComp ? 'جاري الحفظ...' : 'حفظ' }}
        </AppButton>
      </div>
    </AppModal>

    <!-- Penalty Modal -->
    <AppModal :open="!!penaltyModalEmployee" :title="`تسجيل جزاء — ${penaltyModalEmployee?.full_name ?? ''}`"
      @close="penaltyModalEmployee = null">
      <div class="space-y-3">
        <select v-model="penaltyForm.penalty_type_id" @change="onPenaltyTypeChange"
          class="w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2 outline-none focus:border-primary-500">
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

    <!-- wagdy.md H-01: سلفة راتب -->
    <AppModal :open="!!advanceModalEmployee" :title="`سلف — ${advanceModalEmployee?.full_name ?? ''}`"
      @close="advanceModalEmployee = null">
      <div class="space-y-4">
        <div v-if="advancesLoading" class="text-center py-4 text-sm text-gray-400 dark:text-gray-500">جاري التحميل...</div>
        <div v-else-if="employeeAdvances.length" class="space-y-2">
          <div v-for="a in employeeAdvances" :key="a.id" class="text-sm bg-stone-50 dark:bg-gray-800/60 rounded-lg px-3 py-2">
            <div class="flex items-center justify-between">
              <span class="font-medium text-gray-800 dark:text-gray-200">{{ a.amount.toLocaleString('ar-EG') }} ج — قسط {{ a.monthly_deduction_amount.toLocaleString('ar-EG') }} ج/شهر</span>
              <AppBadge size="sm" :variant="a.status === 'active' ? 'info' : a.status === 'settled' ? 'success' : 'neutral'">
                {{ a.status === 'active' ? 'نشطة' : a.status === 'settled' ? 'مسدّدة' : 'ملغاة' }}
              </AppBadge>
            </div>
            <div class="text-xs text-gray-500 dark:text-gray-500 mt-1">
              المتبقي: {{ a.remaining_balance.toLocaleString('ar-EG') }} ج — صرفت في {{ formatDate(a.disbursed_date) }}
            </div>
            <button v-if="a.status === 'active' && a.remaining_balance == a.amount"
              @click="cancelAdvance(a)" class="text-xs font-semibold text-red-600 hover:text-red-800 mt-1">إلغاء</button>
          </div>
        </div>
        <EmptyState v-else icon="💰" title="لا يوجد سلف مسجّلة" />

        <div class="border-t border-stone-100 dark:border-border/50 pt-4 space-y-3">
          <div class="text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">تسجيل سلفة جديدة</div>
          <AppInput v-model.number="advanceForm.amount" type="number" placeholder="المبلغ (جنيه)" />
          <label class="block text-xs font-semibold text-gray-500 dark:text-gray-500">تاريخ الصرف</label>
          <input v-model="advanceForm.disbursed_date" type="date"
            class="w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2 outline-none focus:border-primary-500" />
          <AppInput v-model.number="advanceForm.monthly_deduction_amount" type="number" placeholder="القسط الشهري (جنيه)" />
          <AppInput v-model="advanceForm.notes" placeholder="ملاحظات (اختياري)" />
          <AppButton :disabled="savingAdvance" @click="submitAdvance" variant="primary" size="sm">
            {{ savingAdvance ? 'جاري الحفظ...' : 'تسجيل السلفة' }}
          </AppButton>
        </div>
      </div>
    </AppModal>

    <!-- wagdy.md H-02: دفعة يومية -->
    <AppModal :open="!!paymentModalEmployee" :title="`دفعات — ${paymentModalEmployee?.full_name ?? ''}`"
      @close="paymentModalEmployee = null">
      <div class="space-y-4">
        <div v-if="paymentsLoading" class="text-center py-4 text-sm text-gray-400 dark:text-gray-500">جاري التحميل...</div>
        <div v-else-if="employeePayments.length" class="space-y-2">
          <div v-for="p in employeePayments" :key="p.id" class="flex items-center justify-between text-sm bg-stone-50 dark:bg-gray-800/60 rounded-lg px-3 py-2">
            <div>
              <span class="font-medium text-gray-800 dark:text-gray-200">{{ p.amount.toLocaleString('ar-EG') }} ج</span>
              <span class="text-xs text-gray-400 dark:text-gray-500 mr-2">{{ formatDate(p.payment_date) }}</span>
            </div>
            <AppBadge size="sm" :variant="p.deducted ? 'success' : 'warning'">{{ p.deducted ? 'اتخصمت' : 'لسه' }}</AppBadge>
          </div>
        </div>
        <EmptyState v-else icon="📅" title="لا يوجد دفعات مسجّلة" />

        <div class="border-t border-stone-100 dark:border-border/50 pt-4 space-y-3">
          <div class="text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">تسجيل دفعة جديدة</div>
          <AppInput v-model.number="paymentForm.amount" type="number" placeholder="المبلغ (جنيه)" />
          <label class="block text-xs font-semibold text-gray-500 dark:text-gray-500">تاريخ الدفعة</label>
          <input v-model="paymentForm.payment_date" type="date"
            class="w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2 outline-none focus:border-primary-500" />
          <AppInput v-model="paymentForm.notes" placeholder="ملاحظات (اختياري)" />
          <AppButton :disabled="savingPayment" @click="submitPayment" variant="primary" size="sm">
            {{ savingPayment ? 'جاري الحفظ...' : 'تسجيل الدفعة' }}
          </AppButton>
        </div>
      </div>
    </AppModal>

    <!-- wagdy.md H-07: استيراد حضور من Excel -->
    <AppModal :open="showImportModal" title="📥 استيراد حضور من Excel" @close="showImportModal = false">
      <div class="space-y-3">
        <p class="text-xs text-gray-400 dark:text-gray-500">
          العمود الأول = كود الموظف أو اسمه الكامل زي المسجّل في النظام بالظبط، وباقي الأعمدة = أيام
          الشهر (1، 2، 3...) أو تواريخ كاملة. قيمة الخلية: p = حاضر، u = غائب، v = إجازة.
        </p>
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label class="block text-xs font-semibold text-gray-500 dark:text-gray-500 mb-1">السنة</label>
            <AppInput v-model.number="importPeriodYear" type="number" />
          </div>
          <div>
            <label class="block text-xs font-semibold text-gray-500 dark:text-gray-500 mb-1">الشهر</label>
            <AppInput v-model.number="importPeriodMonth" type="number" />
          </div>
        </div>
        <input type="file" accept=".xlsx,.xls" @change="onImportFilePicked"
          class="w-full text-xs text-gray-600 dark:text-gray-500 file:ml-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:bg-primary-50 file:text-primary-700 file:font-bold" />

        <div v-if="importResult" class="p-3 rounded-xl text-xs"
          :class="'error' in importResult ? 'bg-red-50 text-red-600' : 'bg-green-50 text-green-700'">
          <div v-if="'error' in importResult">{{ importResult.error }}</div>
          <div v-else>
            ✅ تم استيراد {{ importResult.imported }} سجل حضور
            <div v-if="importResult.unmatched_employees.length" class="mt-2 text-amber-600">
              موظفون غير معروفين: {{ importResult.unmatched_employees.join('، ') }}
            </div>
            <div v-if="importResult.errors.length" class="mt-2 text-red-500">
              <div v-for="(err, i) in importResult.errors" :key="i">{{ err }}</div>
            </div>
          </div>
        </div>

        <AppButton :disabled="!importFile || importUploading" :loading="importUploading"
          @click="submitAttendanceImport" variant="primary" size="sm">
          {{ importUploading ? 'جاري الاستيراد...' : 'استيراد' }}
        </AppButton>
      </div>
    </AppModal>

    <!-- wagdy.md H-03: رصيد الإجازة الشهري -->
    <AppModal :open="!!balanceModalEmployee" :title="`رصيد الإجازة — ${balanceModalEmployee?.full_name ?? ''}`"
      @close="balanceModalEmployee = null">
      <div v-if="balancesLoading" class="text-center py-4 text-sm text-gray-400 dark:text-gray-500">جاري التحميل...</div>
      <EmptyState v-else-if="!employeeLeaveBalances.length" icon="📊" title="لا يوجد رصيد إجازة مسجّل بعد"
        subtitle="يُحسب تلقائيًا أول كل شهر (7.5 يوم يُستحق شهريًا)" />
      <div v-else class="space-y-2">
        <div v-for="b in employeeLeaveBalances" :key="b.id" class="flex items-center justify-between text-sm bg-stone-50 dark:bg-gray-800/60 rounded-lg px-3 py-2">
          <span class="text-gray-700 dark:text-gray-300">{{ monthLabel(b.period_year, b.period_month) }}</span>
          <div class="text-left">
            <div class="font-bold text-gray-900 dark:text-gray-100">{{ b.closing_balance }} يوم</div>
            <div class="text-xs text-gray-400 dark:text-gray-500">+{{ b.accrued }} − {{ b.consumed }}</div>
          </div>
        </div>
      </div>
    </AppModal>

    <!-- #8: تصحيح سجل حضور -->
    <AppModal :open="!!editingAttendance"
      :title="`تصحيح حضور — ${editingAttendance ? (employeeNameById[editingAttendance.employee_id] ?? `موظف #${editingAttendance.employee_id}`) : ''}`"
      @close="editingAttendance = null">
      <div class="space-y-3">
        <label class="block text-xs font-semibold text-gray-500 dark:text-gray-500">وقت الحضور</label>
        <input v-model="editForm.check_in" type="datetime-local"
          class="w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2 outline-none focus:border-primary-500" />
        <label class="block text-xs font-semibold text-gray-500 dark:text-gray-500">وقت الانصراف</label>
        <input v-model="editForm.check_out" type="datetime-local"
          class="w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2 outline-none focus:border-primary-500" />
        <label class="block text-xs font-semibold text-gray-500 dark:text-gray-500">الحالة</label>
        <select v-model="editForm.status"
          class="w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2 outline-none focus:border-primary-500">
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
        <span class="text-sm text-gray-400 dark:text-gray-500">جاري التحميل...</span>
      </div>
      <div v-else-if="!payrollRuns.length">
        <EmptyState icon="💰" title="لا توجد دفعات رواتب" />
      </div>
      <div v-else class="space-y-3">
        <AppCard v-for="run in payrollRuns" :key="run.id" padding="md">
          <div class="flex items-center justify-between">
            <div>
              <div class="font-bold text-gray-900 dark:text-gray-100">{{ monthLabel(run.period_year, run.period_month) }}</div>
              <div class="text-sm text-gray-500 dark:text-gray-500 mt-0.5">إجمالي قبل الاستقطاعات: {{ (run.total_gross ?? 0).toLocaleString('ar-EG') }} ج</div>
            </div>
            <div class="text-left">
              <div class="text-xl font-black text-gray-900 dark:text-gray-100">{{ (run.total_net ?? 0).toLocaleString('ar-EG') }} ج</div>
              <AppBadge size="sm" :variant="statusVariant[run.status] ?? 'neutral'">{{ statusLabel(run.status) }}</AppBadge>
            </div>
          </div>

          <div class="flex items-center justify-between mt-3 pt-3 border-t border-stone-100 dark:border-border/50">
            <AppButton size="sm" variant="secondary" @click="togglePayrollRunDetails(run)">
              {{ expandedRunId === run.id ? 'إخفاء القسائم' : 'عرض القسائم' }}
            </AppButton>
            <!-- الاعتماد على مستوى الدفعة كلها دفعة واحدة (نفس صلاحية الباك إند:
                 hr.approve_payroll_run، admin فأعلى فقط) — بضغطة واحدة بيعتمد
                 رواتب كل الموظفين في الدفعة، مش لازم فتح كل قسيمة لوحدها. -->
            <AppButton v-if="run.status === 'draft' && auth.hasRole('admin')" size="sm" variant="primary"
              :loading="approvingRunId === run.id" @click="approvePayrollRun(run)">
              {{ payrollLinesByRun[run.id]?.length ? `اعتماد الكل (${payrollLinesByRun[run.id].length})` : 'اعتماد الكل' }}
            </AppButton>
          </div>

          <div v-if="expandedRunId === run.id" class="mt-3 pt-3 border-t border-stone-100 dark:border-border/50">
            <div v-if="payrollLinesLoading" class="flex items-center gap-2 py-2">
              <AppSpinner size="sm" />
              <span class="text-xs text-gray-400 dark:text-gray-500">جاري تحميل القسائم...</span>
            </div>
            <div v-else-if="!payrollLinesByRun[run.id]?.length" class="text-xs text-gray-400 dark:text-gray-500 py-2">
              لا توجد قسائم في هذه الدفعة
            </div>
            <div v-else class="space-y-1.5">
              <div v-for="line in payrollLinesByRun[run.id]" :key="line.id"
                class="flex items-center justify-between text-sm">
                <span class="text-gray-700 dark:text-gray-300">{{ employeeNameById[line.employee_id] ?? `موظف #${line.employee_id}` }}</span>
                <span class="text-gray-900 dark:text-gray-100 font-semibold">{{ (line.net_salary ?? 0).toLocaleString('ar-EG') }} ج</span>
              </div>
            </div>
          </div>
        </AppCard>
      </div>
    </div>

    <!-- Leaves Tab -->
    <div v-if="tab === 'leaves'">
      <div v-if="loading" class="flex flex-col items-center justify-center gap-3 py-12">
        <AppSpinner size="md" />
        <span class="text-sm text-gray-400 dark:text-gray-500">جاري التحميل...</span>
      </div>
      <div v-else-if="!leaveRequests.length">
        <EmptyState icon="🌴" title="لا توجد طلبات إجازات معلقة" />
      </div>
      <div v-else class="space-y-3">
        <AppCard v-for="leave in leaveRequests" :key="leave.id" padding="md">
          <div class="flex items-start justify-between">
            <div>
              <div class="font-bold text-gray-900 dark:text-gray-100">{{ employeeNameById[leave.employee_id] ?? `موظف #${leave.employee_id}` }}</div>
              <div class="text-sm text-gray-500 dark:text-gray-500">{{ leaveTypeNameById[leave.leave_type_id] ?? 'إجازة' }} — {{ leave.days_requested }} أيام</div>
              <div class="text-xs text-gray-400 dark:text-gray-500 mt-1">
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
        <label class="text-xs font-semibold text-gray-500 dark:text-gray-500">من</label>
        <input v-model="attendanceDateFrom" @change="fetchAttendance" type="date"
          class="bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-xs rounded-xl px-3 py-2 outline-none focus:border-primary-500" />
        <label class="text-xs font-semibold text-gray-500 dark:text-gray-500">إلى</label>
        <input v-model="attendanceDateTo" @change="fetchAttendance" type="date"
          class="bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-xs rounded-xl px-3 py-2 outline-none focus:border-primary-500" />
        <AppButton v-if="auth.hasRole('manager')" size="sm" variant="secondary" @click="openImportModal">
          📥 استيراد من Excel
        </AppButton>
      </div>

      <!-- سياسة الحضور — سماحية التأخير/الانصراف المبكر ونسب الأوفرتايم/الخصم
           التلقائي المستخدمة في تشغيل الرواتب -->
      <AppCard title="سياسة الحضور والانصراف" padding="md">
        <div v-if="policyLoading" class="flex items-center gap-3 py-4">
          <AppSpinner size="sm" />
          <span class="text-sm text-gray-400 dark:text-gray-500">جاري التحميل...</span>
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
        <span class="text-sm text-gray-400 dark:text-gray-500">جاري التحميل...</span>
      </div>
      <EmptyState v-else-if="!attendanceRecords.length" icon="⏰" title="لا توجد سجلات حضور"
        subtitle="لم يتم تسجيل أي حضور خلال الفترة المحددة" />
      <AppCard v-else padding="none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الموظف</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">التاريخ</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الحضور</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الانصراف</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">ساعات العمل</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الحالة</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="rec in attendanceRecords" :key="rec.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
                  {{ employeeNameById[rec.employee_id] ?? `موظف #${rec.employee_id}` }}
                </td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ formatDate(rec.record_date) }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ formatTime(rec.check_in) }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ formatTime(rec.check_out) }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ rec.hours_worked != null ? rec.hours_worked.toFixed(2) : '—' }}</td>
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

    <!-- Leaderboard Tab -->
    <div v-if="tab === 'leaderboard'" class="space-y-4">
      <div class="flex flex-wrap items-end gap-3">
        <div>
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-500 mb-1">من تاريخ</label>
          <input v-model="leaderboardFrom" type="date"
            class="px-3 py-1.5 rounded-lg border border-stone-200 dark:border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-500 mb-1">إلى تاريخ</label>
          <input v-model="leaderboardTo" type="date"
            class="px-3 py-1.5 rounded-lg border border-stone-200 dark:border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
        </div>
        <AppButton size="sm" @click="fetchLeaderboard">تحديث</AppButton>
      </div>

      <AppSpinner v-if="leaderboardLoading" />
      <EmptyState v-else-if="!leaderboard.length" icon="🏆" title="لا توجد مبيعات مسجّلة"
        subtitle="لا يوجد مبيعات مرتبطة بموظفين خلال المدى المحدد" />
      <AppCard v-else padding="none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الترتيب</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الموظف</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">إجمالي المبيعات</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">عدد الطلبات</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(entry, i) in leaderboard" :key="entry.user_id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3 text-lg font-black">{{ leaderboardMedal(i) }}</td>
                <td class="px-4 py-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
                  {{ entry.employee_name ?? `موظف #${entry.user_id}` }}
                  <span v-if="entry.employee_code" class="text-gray-400 dark:text-gray-500 font-normal">({{ entry.employee_code }})</span>
                </td>
                <td class="px-4 py-3 text-sm font-bold text-green-700">{{ Number(entry.total_sales).toLocaleString('ar-EG') }} ج</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ entry.order_count }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>
  </div>
</template>
