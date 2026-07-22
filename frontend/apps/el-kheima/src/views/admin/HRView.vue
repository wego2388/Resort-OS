<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, parseApiTimestamp, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppSpinner, AppModal, AppInput, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatNumber, formatDate: fmtDateFn, formatTime: fmtTimeFn } = useStaffFormat()
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
      toast.error(t('backoffice.hr.msg.loadPolicyError'))
    }
  } finally { policyLoading.value = false }
}

async function saveAttendancePolicy() {
  policySaving.value = true
  try {
    const res = await api.put('/api/v1/hr/attendance-policy', attendancePolicy.value, { params: { branch_id: branchId } })
    attendancePolicy.value = res.data
    policyConfigured.value = true
    toast.success(t('backoffice.hr.msg.policySaved'))
  } catch (e) {
    toast.error(t('backoffice.hr.msg.policySaveError'))
  } finally { policySaving.value = false }
}

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

async function fetchEmployees() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/hr/employees', { params: { branch_id: branchId, size: 100 } })
    employees.value = res.data.employees ?? res.data.items ?? res.data
  } catch (e) {
    toast.error(t('backoffice.hr.msg.loadEmployeesError'))
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
    toast.error(t('backoffice.hr.msg.loadPayrollError'))
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
    toast.error(t('backoffice.hr.msg.loadPayrollLinesError'))
  } finally { payrollLinesLoading.value = false }
}

// اعتماد الدفعة كاملة — إجراء واحد يعتمد رواتب كل الموظفين في الدفعة دفعة
// واحدة (نفس الـ endpoint الموجود أصلاً في الباك إند)، بدل ما يكون المستخدم
// مضطر يفتح كل قسيمة لوحدها من غير ما يكون فيه زرار اعتماد أصلاً.
async function approvePayrollRun(run: PayrollRun) {
  const employeeCount = payrollLinesByRun.value[run.id]?.length
  const ok = await confirm({
    title: t('backoffice.hr.approvePayrollTitle'),
    message: employeeCount
      ? t('backoffice.hr.approvePayrollMessageCount', { period: monthLabel(run.period_year, run.period_month), count: employeeCount })
      : t('backoffice.hr.approvePayrollMessage', { period: monthLabel(run.period_year, run.period_month) }),
    confirmText: t('backoffice.hr.approveAll'),
    danger: true,
  })
  if (!ok) return
  approvingRunId.value = run.id
  try {
    const res = await api.post(`/api/v1/hr/payroll-runs/${run.id}/approve`)
    const updated = res.data as PayrollRun
    payrollRuns.value = payrollRuns.value.map(r => (r.id === run.id ? { ...r, ...updated } : r))
    toast.success(t('backoffice.hr.msg.payrollRunApproved'))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.hr.msg.payrollApproveError'))
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
    toast.error(t('backoffice.hr.msg.loadLeavesError'))
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
    toast.error(t('backoffice.hr.msg.loadAttendanceError'))
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
    toast.error(t('backoffice.hr.msg.loadAllowancesError'))
  } finally { allowancesLoading.value = false }
}

async function submitAllowance() {
  if (!allowanceModalEmployee.value) return
  // AppInput لا يطبّق مودفاير .number تلقائيًا (component مبني بـ defineProps
  // عادي مش defineModel) — القيمة اللي بترجع ممكن تكون string، فلازم تحويل
  // صريح هنا قبل أي مقارنة رقمية أو إرسال للباك إند.
  const amount = Number(allowanceForm.value.amount)
  if (!allowanceForm.value.name.trim() || !(amount > 0)) {
    toast.error(t('backoffice.hr.msg.allowanceFieldsRequired'))
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
    toast.success(t('backoffice.hr.msg.allowanceAdded'))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.hr.msg.allowanceSaveError'))
  } finally { savingAllowance.value = false }
}

async function openPenaltyModal(emp: Employee) {
  penaltyModalEmployee.value = emp
  penaltyForm.value = { penalty_type_id: null, penalty_days: 1, reason: '' }
  try {
    const res = await api.get('/api/v1/hr/penalty-types', { params: { branch_id: branchId } })
    penaltyTypes.value = res.data ?? []
  } catch (e) {
    toast.error(t('backoffice.hr.msg.loadPenaltyTypesError'))
  }
}

function onPenaltyTypeChange() {
  const pt = penaltyTypes.value.find(p => p.id === penaltyForm.value.penalty_type_id)
  if (pt) penaltyForm.value.penalty_days = pt.penalty_days
}

async function submitPenalty() {
  if (!penaltyModalEmployee.value) return
  const penaltyDays = Number(penaltyForm.value.penalty_days)
  if (!penaltyForm.value.reason.trim() || !(penaltyDays > 0)) {
    toast.error(t('backoffice.hr.msg.penaltyFieldsRequired'))
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
    toast.success(t('backoffice.hr.msg.penaltyLogged'))
    penaltyModalEmployee.value = null
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.hr.msg.penaltySaveError'))
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
    toast.error(t('backoffice.hr.msg.basicSalaryRequired'))
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
    toast.success(t('backoffice.hr.msg.compUpdated'))
    compModalEmployee.value = null
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.hr.msg.compSaveError'))
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
    toast.error(t('backoffice.hr.msg.loadAdvancesError'))
  } finally { advancesLoading.value = false }
}

async function submitAdvance() {
  if (!advanceModalEmployee.value) return
  const amount = Number(advanceForm.value.amount)
  const monthlyDeduction = Number(advanceForm.value.monthly_deduction_amount)
  if (!(amount > 0) || !(monthlyDeduction > 0)) {
    toast.error(t('backoffice.hr.msg.advanceFieldsRequired'))
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
    toast.success(t('backoffice.hr.msg.advanceLogged'))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.hr.msg.advanceSaveError'))
  } finally { savingAdvance.value = false }
}

async function cancelAdvance(advance: SalaryAdvance) {
  const ok = await confirm({
    title: t('backoffice.hr.cancelAdvanceTitle'),
    message: t('backoffice.hr.cancelAdvanceMessage', { amount: formatNumber(advance.amount) }),
    confirmText: t('backoffice.hr.cancelAdvanceConfirm'), danger: true,
  })
  if (!ok) return
  try {
    await api.patch(`/api/v1/hr/salary-advances/${advance.id}/cancel`, {})
    employeeAdvances.value = employeeAdvances.value.map(a => (a.id === advance.id ? { ...a, status: 'cancelled' } : a))
    toast.success(t('backoffice.hr.msg.advanceCancelled'))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.hr.msg.advanceCancelError'))
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
    toast.error(t('backoffice.hr.msg.loadPaymentsError'))
  } finally { paymentsLoading.value = false }
}

async function submitPayment() {
  if (!paymentModalEmployee.value) return
  const amount = Number(paymentForm.value.amount)
  if (!(amount > 0)) {
    toast.error(t('backoffice.hr.msg.amountRequired'))
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
    toast.success(t('backoffice.hr.msg.paymentLogged'))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.hr.msg.paymentSaveError'))
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
    toast.error(t('backoffice.hr.msg.loadBalanceError'))
  } finally { balancesLoading.value = false }
}

async function loadTab(tabId: typeof tab.value) {
  tab.value = tabId
  if (tabId === 'employees') await fetchEmployees()
  if (tabId === 'payroll') await fetchPayroll()
  if (tabId === 'leaves') await fetchLeaves()
  if (tabId === 'attendance') await fetchAttendance()
  if (tabId === 'leaderboard') await fetchLeaderboard()
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
    toast.error(t('backoffice.hr.msg.loadLeaderboardError'))
  } finally { leaderboardLoading.value = false }
}

const leaderboardMedal = (rank: number) => rank === 0 ? '🥇' : rank === 1 ? '🥈' : rank === 2 ? '🥉' : `#${rank + 1}`

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

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'
const statusVariant: Record<string, BadgeVariant> = {
  active: 'success', inactive: 'neutral', terminated: 'danger', on_leave: 'warning',
  pending: 'warning', approved: 'success', rejected: 'danger',
  processing: 'info', paid: 'success', draft: 'neutral',
  present: 'success', absent: 'danger', late: 'warning', leave: 'info', holiday: 'neutral',
}
const statusLabels = computed<Record<string, string>>(() => ({
  active: t('backoffice.hr.status.active'), inactive: t('backoffice.hr.status.inactive'),
  terminated: t('backoffice.hr.status.terminated'), on_leave: t('backoffice.hr.status.onLeave'),
  pending: t('backoffice.hr.status.pending'), approved: t('backoffice.hr.status.approved'),
  rejected: t('backoffice.hr.status.rejected'), processing: t('backoffice.hr.status.processing'),
  paid: t('backoffice.hr.status.paid'), draft: t('backoffice.hr.status.draft'),
  present: t('backoffice.hr.status.present'), absent: t('backoffice.hr.status.absent'),
  late: t('backoffice.hr.status.late'), leave: t('backoffice.hr.status.leave'),
  holiday: t('backoffice.hr.status.holiday'),
}))
function statusLabel(s: string) { return statusLabels.value[s] ?? s }

function formatDate(d?: string | null) {
  if (!d) return '—'
  return fmtDateFn(d)
}
function formatTime(d?: string | null) {
  if (!d) return '—'
  // check_in/check_out من الباك إند naive UTC (بدون "Z") — لازم parseApiTimestamp
  // مش new Date() الخام، وإلا وقت الحضور المعروض للمدير يبقى مزاح بفرق توقيت
  // القاهرة عن UTC (نفس فئة باج الـ KDS الموثّقة في @resort-os/core/utils/dates).
  return fmtTimeFn(parseApiTimestamp(d))
}
function monthLabel(year: number, month: number) {
  return fmtDateFn(new Date(year, month - 1, 1), { month: 'long', year: 'numeric' })
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
    toast.success(t('backoffice.hr.msg.attendanceEditSaved'))
    editingAttendance.value = null
    await fetchAttendance()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.hr.msg.attendanceEditSaveError'))
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
    toast.success(t('backoffice.hr.msg.attendanceImported', { count: res.data.imported }))
    await fetchAttendance()
  } catch (e: any) {
    const msg = e?.response?.data?.detail ?? t('backoffice.hr.msg.importError')
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

const tabsList = computed(() => [
  { val: 'employees', label: t('backoffice.hr.tabs.employees') },
  { val: 'attendance', label: t('backoffice.hr.tabs.attendance') },
  { val: 'payroll', label: t('backoffice.hr.tabs.payroll') },
  { val: 'leaves', label: t('backoffice.hr.tabs.leaves') },
  { val: 'leaderboard', label: `🏆 ${t('backoffice.hr.tabs.leaderboard')}` },
])

onMounted(fetchEmployees)
</script>

<template>
  <div>
    <h2 class="text-2xl font-black text-gray-900 dark:text-gray-100 mb-6">{{ t('backoffice.hr.title') }}</h2>

    <!-- Tabs -->
    <div class="flex gap-1 bg-stone-100 dark:bg-gray-700 p-1 rounded-xl mb-6 w-fit">
      <button v-for="tabDef in tabsList" :key="tabDef.val"
        @click="loadTab(tabDef.val as any)"
        :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all', tab === tabDef.val ? 'bg-white dark:bg-surface shadow-sm text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:text-gray-300']"
      >{{ tabDef.label }}</button>
    </div>

    <!-- Employees Tab -->
    <div v-if="tab === 'employees'">
      <div v-if="loading" class="flex flex-col items-center justify-center gap-3 py-12">
        <AppSpinner size="md" />
        <span class="text-sm text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.loading') }}</span>
      </div>
      <AppCard v-else :title="t('backoffice.hr.employeesCount', { count: employees.length })" padding="none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.name') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.position') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.department') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.salary') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.statusCol') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="emp in employees" :key="emp.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3">
                  <div class="flex items-center gap-3">
                    <div class="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-700 dark:bg-blue-950/50 dark:text-blue-300">
                      {{ emp.full_name.charAt(0) }}
                    </div>
                    <div>
                      <div class="font-semibold text-gray-900 dark:text-gray-100 text-sm">{{ emp.full_name }}</div>
                      <div v-if="emp.phone" class="text-xs text-gray-400 dark:text-gray-400">{{ emp.phone }}</div>
                    </div>
                  </div>
                </td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ emp.position }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ emp.department ?? '—' }}</td>
                <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">{{ formatNumber(emp.basic_salary ?? 0) }} {{ t('backoffice.hr.egp') }}</td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="statusVariant[emp.status] ?? 'neutral'">{{ statusLabel(emp.status) }}</AppBadge>
                </td>
                <td class="px-4 py-3">
                  <div class="flex items-center gap-2">
                    <button @click="openAllowanceModal(emp)" class="text-xs font-semibold text-blue-600 hover:text-blue-800 dark:text-blue-300 dark:hover:text-blue-200">{{ t('backoffice.hr.addAllowanceShort') }}</button>
                    <button @click="openPenaltyModal(emp)" class="text-xs font-semibold text-red-600 hover:text-red-800 dark:text-red-300 dark:hover:text-red-200">{{ t('backoffice.hr.addPenaltyShort') }}</button>
                    <button v-if="auth.hasRole('admin')" @click="openAdvanceModal(emp)" class="text-xs font-semibold text-amber-600 hover:text-amber-800 dark:text-amber-300 dark:hover:text-amber-200">💰 {{ t('backoffice.hr.advanceShort') }}</button>
                    <button @click="openPaymentModal(emp)" class="text-xs font-semibold text-teal-600 hover:text-teal-800">📅 {{ t('backoffice.hr.paymentShort') }}</button>
                    <button @click="openBalanceModal(emp)" class="text-xs font-semibold text-purple-600 hover:text-purple-800 dark:text-purple-300 dark:hover:text-purple-200">📊 {{ t('backoffice.hr.leaveBalanceShort') }}</button>
                    <button v-if="auth.hasRole('admin')" @click="openCompModal(emp)" class="text-xs font-semibold text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:text-gray-100">✏️ {{ t('backoffice.hr.salaryShort') }}</button>
                  </div>
                </td>
              </tr>
              <tr v-if="employees.length === 0">
                <td colspan="6" class="px-4 py-12 text-center text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.noEmployees') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- Allowance Modal -->
    <AppModal :open="!!allowanceModalEmployee" :title="t('backoffice.hr.allowancesTitle', { name: allowanceModalEmployee?.full_name ?? '' })"
      @close="allowanceModalEmployee = null">
      <div class="space-y-4">
        <div v-if="allowancesLoading" class="text-center py-4 text-sm text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.loading') }}</div>
        <div v-else-if="employeeAllowances.length" class="space-y-2">
          <div v-for="a in employeeAllowances" :key="a.id" class="flex items-center justify-between text-sm bg-stone-50 dark:bg-gray-800/60 rounded-lg px-3 py-2">
            <span class="font-medium text-gray-800 dark:text-gray-200">{{ a.name }}</span>
            <span class="text-gray-600 dark:text-gray-400">{{ formatNumber(a.amount) }} {{ t('backoffice.hr.egp') }}{{ a.is_taxable ? '' : ` (${t('backoffice.hr.notTaxable')})` }}</span>
          </div>
        </div>
        <EmptyState v-else icon="💵" :title="t('backoffice.hr.noAllowances')" />

        <div class="border-t border-stone-100 dark:border-border/50 pt-4 space-y-3">
          <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.addNewAllowance') }}</div>
          <AppInput v-model="allowanceForm.name" :placeholder="t('backoffice.hr.allowanceNamePlaceholder')" />
          <AppInput v-model.number="allowanceForm.amount" type="number" :placeholder="t('backoffice.hr.amountEgp')" />
          <div class="flex items-center gap-4 text-sm text-gray-700 dark:text-gray-300">
            <label class="flex items-center gap-1.5"><input type="checkbox" v-model="allowanceForm.is_taxable" /> {{ t('backoffice.hr.taxable') }}</label>
            <label class="flex items-center gap-1.5"><input type="checkbox" v-model="allowanceForm.is_pensionable" /> {{ t('backoffice.hr.pensionable') }}</label>
          </div>
          <AppButton :disabled="savingAllowance" @click="submitAllowance" variant="primary" size="sm">
            {{ savingAllowance ? t('backoffice.hr.saving') : t('backoffice.hr.addAllowance') }}
          </AppButton>
        </div>
      </div>
    </AppModal>

    <!-- wagdy.md H-04/H-05: تعديل الراتب الأساسي/وعاء التأمين/مكافأة العيد -->
    <AppModal :open="!!compModalEmployee" :title="t('backoffice.hr.compTitle', { name: compModalEmployee?.full_name ?? '' })"
      @close="compModalEmployee = null">
      <div class="space-y-3">
        <AppInput :label="t('backoffice.hr.basicSalary')" v-model.number="compForm.basic_salary" type="number" />
        <div>
          <AppInput :label="t('backoffice.hr.insuranceBaseOptional')" v-model.number="compForm.insurance_base_salary" type="number"
            :placeholder="t('backoffice.hr.insuranceBasePlaceholder')" />
          <p class="text-xs text-gray-400 dark:text-gray-400 mt-1">{{ t('backoffice.hr.insuranceBaseHint') }}</p>
        </div>
        <div>
          <AppInput :label="t('backoffice.hr.holidayBonus')" v-model.number="compForm.holiday_bonus" type="number" />
          <p class="text-xs text-gray-400 dark:text-gray-400 mt-1">{{ t('backoffice.hr.holidayBonusHint') }}</p>
        </div>
        <AppButton :disabled="savingComp" @click="submitComp" variant="primary" size="sm">
          {{ savingComp ? t('backoffice.hr.saving') : t('backoffice.hr.save') }}
        </AppButton>
      </div>
    </AppModal>

    <!-- Penalty Modal -->
    <AppModal :open="!!penaltyModalEmployee" :title="t('backoffice.hr.penaltyTitle', { name: penaltyModalEmployee?.full_name ?? '' })"
      @close="penaltyModalEmployee = null">
      <div class="space-y-3">
        <select v-model="penaltyForm.penalty_type_id" @change="onPenaltyTypeChange"
          class="w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2 outline-none focus:border-primary-500">
          <option :value="null">{{ t('backoffice.hr.penaltyTypeOptional') }}</option>
          <option v-for="pt in penaltyTypes" :key="pt.id" :value="pt.id">{{ pt.name_ar || pt.name }} ({{ t('backoffice.hr.dayCount', { count: pt.penalty_days }) }})</option>
        </select>
        <AppInput v-model.number="penaltyForm.penalty_days" type="number" :placeholder="t('backoffice.hr.penaltyDaysPlaceholder')" />
        <AppInput v-model="penaltyForm.reason" :placeholder="t('backoffice.hr.reason')" />
        <AppButton :disabled="savingPenalty" @click="submitPenalty" variant="danger" size="sm">
          {{ savingPenalty ? t('backoffice.hr.saving') : t('backoffice.hr.logPenalty') }}
        </AppButton>
      </div>
    </AppModal>

    <!-- wagdy.md H-01: سلفة راتب -->
    <AppModal :open="!!advanceModalEmployee" :title="t('backoffice.hr.advancesTitle', { name: advanceModalEmployee?.full_name ?? '' })"
      @close="advanceModalEmployee = null">
      <div class="space-y-4">
        <div v-if="advancesLoading" class="text-center py-4 text-sm text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.loading') }}</div>
        <div v-else-if="employeeAdvances.length" class="space-y-2">
          <div v-for="a in employeeAdvances" :key="a.id" class="text-sm bg-stone-50 dark:bg-gray-800/60 rounded-lg px-3 py-2">
            <div class="flex items-center justify-between">
              <span class="font-medium text-gray-800 dark:text-gray-200">{{ t('backoffice.hr.advanceLine', { amount: formatNumber(a.amount), installment: formatNumber(a.monthly_deduction_amount) }) }}</span>
              <AppBadge size="sm" :variant="a.status === 'active' ? 'info' : a.status === 'settled' ? 'success' : 'neutral'">
                {{ a.status === 'active' ? t('backoffice.hr.advanceActive') : a.status === 'settled' ? t('backoffice.hr.advanceSettled') : t('backoffice.hr.advanceCancelledBadge') }}
              </AppBadge>
            </div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
              {{ t('backoffice.hr.advanceRemaining', { amount: formatNumber(a.remaining_balance), date: formatDate(a.disbursed_date) }) }}
            </div>
            <button v-if="a.status === 'active' && a.remaining_balance == a.amount"
              @click="cancelAdvance(a)" class="mt-1 text-xs font-semibold text-red-600 hover:text-red-800 dark:text-red-300 dark:hover:text-red-200">{{ t('backoffice.hr.cancel') }}</button>
          </div>
        </div>
        <EmptyState v-else icon="💰" :title="t('backoffice.hr.noAdvances')" />

        <div class="border-t border-stone-100 dark:border-border/50 pt-4 space-y-3">
          <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.logNewAdvance') }}</div>
          <AppInput v-model.number="advanceForm.amount" type="number" :placeholder="t('backoffice.hr.amountEgp')" />
          <label class="block text-xs font-semibold text-gray-500 dark:text-gray-400">{{ t('backoffice.hr.disbursedDate') }}</label>
          <input v-model="advanceForm.disbursed_date" type="date"
            class="w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2 outline-none focus:border-primary-500" />
          <AppInput v-model.number="advanceForm.monthly_deduction_amount" type="number" :placeholder="t('backoffice.hr.monthlyInstallmentEgp')" />
          <AppInput v-model="advanceForm.notes" :placeholder="t('backoffice.hr.notesOptional')" />
          <AppButton :disabled="savingAdvance" @click="submitAdvance" variant="primary" size="sm">
            {{ savingAdvance ? t('backoffice.hr.saving') : t('backoffice.hr.logAdvance') }}
          </AppButton>
        </div>
      </div>
    </AppModal>

    <!-- wagdy.md H-02: دفعة يومية -->
    <AppModal :open="!!paymentModalEmployee" :title="t('backoffice.hr.paymentsTitle', { name: paymentModalEmployee?.full_name ?? '' })"
      @close="paymentModalEmployee = null">
      <div class="space-y-4">
        <div v-if="paymentsLoading" class="text-center py-4 text-sm text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.loading') }}</div>
        <div v-else-if="employeePayments.length" class="space-y-2">
          <div v-for="p in employeePayments" :key="p.id" class="flex items-center justify-between text-sm bg-stone-50 dark:bg-gray-800/60 rounded-lg px-3 py-2">
            <div>
              <span class="font-medium text-gray-800 dark:text-gray-200">{{ formatNumber(p.amount) }} {{ t('backoffice.hr.egp') }}</span>
              <span class="text-xs text-gray-400 dark:text-gray-400 ms-2">{{ formatDate(p.payment_date) }}</span>
            </div>
            <AppBadge size="sm" :variant="p.deducted ? 'success' : 'warning'">{{ p.deducted ? t('backoffice.hr.deducted') : t('backoffice.hr.notYet') }}</AppBadge>
          </div>
        </div>
        <EmptyState v-else icon="📅" :title="t('backoffice.hr.noPayments')" />

        <div class="border-t border-stone-100 dark:border-border/50 pt-4 space-y-3">
          <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.logNewPayment') }}</div>
          <AppInput v-model.number="paymentForm.amount" type="number" :placeholder="t('backoffice.hr.amountEgp')" />
          <label class="block text-xs font-semibold text-gray-500 dark:text-gray-400">{{ t('backoffice.hr.paymentDate') }}</label>
          <input v-model="paymentForm.payment_date" type="date"
            class="w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2 outline-none focus:border-primary-500" />
          <AppInput v-model="paymentForm.notes" :placeholder="t('backoffice.hr.notesOptional')" />
          <AppButton :disabled="savingPayment" @click="submitPayment" variant="primary" size="sm">
            {{ savingPayment ? t('backoffice.hr.saving') : t('backoffice.hr.logPayment') }}
          </AppButton>
        </div>
      </div>
    </AppModal>

    <!-- wagdy.md H-07: استيراد حضور من Excel -->
    <AppModal :open="showImportModal" :title="`📥 ${t('backoffice.hr.importAttendanceTitle')}`" @close="showImportModal = false">
      <div class="space-y-3">
        <p class="text-xs text-gray-400 dark:text-gray-400">
          {{ t('backoffice.hr.importHint') }}
        </p>
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label class="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.hr.year') }}</label>
            <AppInput v-model.number="importPeriodYear" type="number" />
          </div>
          <div>
            <label class="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.hr.month') }}</label>
            <AppInput v-model.number="importPeriodMonth" type="number" />
          </div>
        </div>
        <input type="file" accept=".xlsx,.xls" @change="onImportFilePicked"
          class="w-full text-xs text-gray-600 dark:text-gray-400 file:ms-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:bg-primary-50 file:text-primary-700 file:font-bold" />

        <div v-if="importResult" class="p-3 rounded-xl text-xs"
          :class="'error' in importResult
            ? 'bg-red-50 text-red-600 dark:bg-red-950/40 dark:text-red-300'
            : 'bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300'">
          <div v-if="'error' in importResult">{{ importResult.error }}</div>
          <div v-else>
            ✅ {{ t('backoffice.hr.importedCount', { count: importResult.imported }) }}
            <div v-if="importResult.unmatched_employees.length" class="mt-2 text-amber-600 dark:text-amber-300">
              {{ t('backoffice.hr.unmatchedEmployees', { names: importResult.unmatched_employees.join('، ') }) }}
            </div>
            <div v-if="importResult.errors.length" class="mt-2 text-red-500">
              <div v-for="(err, i) in importResult.errors" :key="i">{{ err }}</div>
            </div>
          </div>
        </div>

        <AppButton :disabled="!importFile || importUploading" :loading="importUploading"
          @click="submitAttendanceImport" variant="primary" size="sm">
          {{ importUploading ? t('backoffice.hr.importing') : t('backoffice.hr.import') }}
        </AppButton>
      </div>
    </AppModal>

    <!-- wagdy.md H-03: رصيد الإجازة الشهري -->
    <AppModal :open="!!balanceModalEmployee" :title="t('backoffice.hr.balanceTitle', { name: balanceModalEmployee?.full_name ?? '' })"
      @close="balanceModalEmployee = null">
      <div v-if="balancesLoading" class="text-center py-4 text-sm text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.loading') }}</div>
      <EmptyState v-else-if="!employeeLeaveBalances.length" icon="📊" :title="t('backoffice.hr.noBalanceYet')"
        :subtitle="t('backoffice.hr.noBalanceYetHint')" />
      <div v-else class="space-y-2">
        <div v-for="b in employeeLeaveBalances" :key="b.id" class="flex items-center justify-between text-sm bg-stone-50 dark:bg-gray-800/60 rounded-lg px-3 py-2">
          <span class="text-gray-700 dark:text-gray-300">{{ monthLabel(b.period_year, b.period_month) }}</span>
          <div class="text-end">
            <div class="font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.hr.dayCount', { count: b.closing_balance }) }}</div>
            <div class="text-xs text-gray-400 dark:text-gray-400">+{{ b.accrued }} − {{ b.consumed }}</div>
          </div>
        </div>
      </div>
    </AppModal>

    <!-- #8: تصحيح سجل حضور -->
    <AppModal :open="!!editingAttendance"
      :title="t('backoffice.hr.editAttendanceTitle', { name: editingAttendance ? (employeeNameById[editingAttendance.employee_id] ?? t('backoffice.hr.employeeHash', { id: editingAttendance.employee_id })) : '' })"
      @close="editingAttendance = null">
      <div class="space-y-3">
        <label class="block text-xs font-semibold text-gray-500 dark:text-gray-400">{{ t('backoffice.hr.checkInTime') }}</label>
        <input v-model="editForm.check_in" type="datetime-local"
          class="w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2 outline-none focus:border-primary-500" />
        <label class="block text-xs font-semibold text-gray-500 dark:text-gray-400">{{ t('backoffice.hr.checkOutTime') }}</label>
        <input v-model="editForm.check_out" type="datetime-local"
          class="w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2 outline-none focus:border-primary-500" />
        <label class="block text-xs font-semibold text-gray-500 dark:text-gray-400">{{ t('backoffice.hr.statusCol') }}</label>
        <select v-model="editForm.status"
          class="w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2 outline-none focus:border-primary-500">
          <option value="present">{{ t('backoffice.hr.status.present') }}</option>
          <option value="absent">{{ t('backoffice.hr.status.absent') }}</option>
          <option value="late">{{ t('backoffice.hr.status.late') }}</option>
          <option value="leave">{{ t('backoffice.hr.status.leave') }}</option>
          <option value="holiday">{{ t('backoffice.hr.status.holiday') }}</option>
        </select>
        <AppInput v-model="editForm.notes" :placeholder="t('backoffice.hr.editReasonPlaceholder')" />
        <AppButton :disabled="savingAttendanceEdit" @click="saveAttendanceEdit" variant="primary" size="sm">
          {{ savingAttendanceEdit ? t('backoffice.hr.saving') : t('backoffice.hr.saveCorrection') }}
        </AppButton>
      </div>
    </AppModal>

    <!-- Payroll Tab -->
    <div v-if="tab === 'payroll'">
      <div v-if="loading" class="flex flex-col items-center justify-center gap-3 py-12">
        <AppSpinner size="md" />
        <span class="text-sm text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.loading') }}</span>
      </div>
      <div v-else-if="!payrollRuns.length">
        <EmptyState icon="💰" :title="t('backoffice.hr.noPayrollRuns')" />
      </div>
      <div v-else class="space-y-3">
        <AppCard v-for="run in payrollRuns" :key="run.id" padding="md">
          <div class="flex items-center justify-between">
            <div>
              <div class="font-bold text-gray-900 dark:text-gray-100">{{ monthLabel(run.period_year, run.period_month) }}</div>
              <div class="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{{ t('backoffice.hr.grossTotal', { amount: formatNumber(run.total_gross ?? 0) }) }}</div>
            </div>
            <div class="text-end">
              <div class="text-xl font-black text-gray-900 dark:text-gray-100">{{ formatNumber(run.total_net ?? 0) }} {{ t('backoffice.hr.egp') }}</div>
              <AppBadge size="sm" :variant="statusVariant[run.status] ?? 'neutral'">{{ statusLabel(run.status) }}</AppBadge>
            </div>
          </div>

          <div class="flex items-center justify-between mt-3 pt-3 border-t border-stone-100 dark:border-border/50">
            <AppButton size="sm" variant="secondary" @click="togglePayrollRunDetails(run)">
              {{ expandedRunId === run.id ? t('backoffice.hr.hideLines') : t('backoffice.hr.showLines') }}
            </AppButton>
            <!-- الاعتماد على مستوى الدفعة كلها دفعة واحدة (نفس صلاحية الباك إند:
                 hr.approve_payroll_run، admin فأعلى فقط) — بضغطة واحدة بيعتمد
                 رواتب كل الموظفين في الدفعة، مش لازم فتح كل قسيمة لوحدها. -->
            <AppButton v-if="run.status === 'draft' && auth.hasRole('admin')" size="sm" variant="primary"
              :loading="approvingRunId === run.id" @click="approvePayrollRun(run)">
              {{ payrollLinesByRun[run.id]?.length ? t('backoffice.hr.approveAllCount', { count: payrollLinesByRun[run.id].length }) : t('backoffice.hr.approveAll') }}
            </AppButton>
          </div>

          <div v-if="expandedRunId === run.id" class="mt-3 pt-3 border-t border-stone-100 dark:border-border/50">
            <div v-if="payrollLinesLoading" class="flex items-center gap-2 py-2">
              <AppSpinner size="sm" />
              <span class="text-xs text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.loadingLines') }}</span>
            </div>
            <div v-else-if="!payrollLinesByRun[run.id]?.length" class="text-xs text-gray-400 dark:text-gray-400 py-2">
              {{ t('backoffice.hr.noLinesInRun') }}
            </div>
            <div v-else class="space-y-1.5">
              <div v-for="line in payrollLinesByRun[run.id]" :key="line.id"
                class="flex items-center justify-between text-sm">
                <span class="text-gray-700 dark:text-gray-300">{{ employeeNameById[line.employee_id] ?? t('backoffice.hr.employeeHash', { id: line.employee_id }) }}</span>
                <span class="text-gray-900 dark:text-gray-100 font-semibold">{{ formatNumber(line.net_salary ?? 0) }} {{ t('backoffice.hr.egp') }}</span>
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

    <!-- Attendance Tab -->
    <div v-if="tab === 'attendance'" class="space-y-4">
      <div class="flex flex-wrap items-center gap-3">
        <label class="text-xs font-semibold text-gray-500 dark:text-gray-400">{{ t('backoffice.hr.from') }}</label>
        <input v-model="attendanceDateFrom" @change="fetchAttendance" type="date"
          class="bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-xs rounded-xl px-3 py-2 outline-none focus:border-primary-500" />
        <label class="text-xs font-semibold text-gray-500 dark:text-gray-400">{{ t('backoffice.hr.to') }}</label>
        <input v-model="attendanceDateTo" @change="fetchAttendance" type="date"
          class="bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-xs rounded-xl px-3 py-2 outline-none focus:border-primary-500" />
        <AppButton v-if="auth.hasRole('manager')" size="sm" variant="secondary" @click="openImportModal">
          📥 {{ t('backoffice.hr.importFromExcel') }}
        </AppButton>
      </div>

      <!-- سياسة الحضور — سماحية التأخير/الانصراف المبكر ونسب الأوفرتايم/الخصم
           التلقائي المستخدمة في تشغيل الرواتب -->
      <AppCard :title="t('backoffice.hr.attendancePolicyTitle')" padding="md">
        <div v-if="policyLoading" class="flex items-center gap-3 py-4">
          <AppSpinner size="sm" />
          <span class="text-sm text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.loading') }}</span>
        </div>
        <div v-else class="space-y-4">
          <p v-if="!policyConfigured" class="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-600 dark:bg-amber-950/40 dark:text-amber-300">
            {{ t('backoffice.hr.noPolicyYet') }}
          </p>
          <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
            <AppInput :label="t('backoffice.hr.lateGrace')" type="number" v-model="attendancePolicy.late_grace_minutes" />
            <AppInput :label="t('backoffice.hr.earlyLeaveGrace')" type="number" v-model="attendancePolicy.early_leave_grace_minutes" />
            <AppInput :label="t('backoffice.hr.shiftStart')" type="time" v-model="attendancePolicy.standard_shift_start" />
            <AppInput :label="t('backoffice.hr.shiftEnd')" type="time" v-model="attendancePolicy.standard_shift_end" />
            <AppInput :label="t('backoffice.hr.overtimeMultiplier')" type="number" v-model="attendancePolicy.overtime_rate_multiplier" />
            <AppInput :label="t('backoffice.hr.latePenaltyMultiplier')" type="number" v-model="attendancePolicy.late_penalty_rate_multiplier" />
          </div>
          <div class="flex justify-end">
            <AppButton size="sm" variant="primary" :disabled="policySaving" @click="saveAttendancePolicy">
              {{ policySaving ? t('backoffice.hr.saving') : t('backoffice.hr.savePolicy') }}
            </AppButton>
          </div>
        </div>
      </AppCard>

      <div v-if="attendanceLoading" class="flex flex-col items-center justify-center gap-3 py-12">
        <AppSpinner size="md" />
        <span class="text-sm text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.loading') }}</span>
      </div>
      <EmptyState v-else-if="!attendanceRecords.length" icon="⏰" :title="t('backoffice.hr.noAttendanceRecords')"
        :subtitle="t('backoffice.hr.noAttendanceRecordsHint')" />
      <AppCard v-else padding="none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.employee') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.date') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.checkIn') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.checkOut') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.hoursWorked') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.statusCol') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="rec in attendanceRecords" :key="rec.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
                  {{ employeeNameById[rec.employee_id] ?? t('backoffice.hr.employeeHash', { id: rec.employee_id }) }}
                </td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ formatDate(rec.record_date) }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ formatTime(rec.check_in) }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ formatTime(rec.check_out) }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ rec.hours_worked != null ? rec.hours_worked.toFixed(2) : '—' }}</td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="statusVariant[rec.status] ?? 'neutral'">{{ statusLabel(rec.status) }}</AppBadge>
                </td>
                <td class="px-4 py-3 text-end">
                  <button @click="openEditAttendance(rec)" class="text-xs font-semibold text-primary-700 hover:underline">{{ t('backoffice.hr.edit') }}</button>
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
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.hr.fromDate') }}</label>
          <input v-model="leaderboardFrom" type="date"
            class="px-3 py-1.5 rounded-lg border border-stone-200 dark:border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.hr.toDate') }}</label>
          <input v-model="leaderboardTo" type="date"
            class="px-3 py-1.5 rounded-lg border border-stone-200 dark:border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
        </div>
        <AppButton size="sm" @click="fetchLeaderboard">{{ t('backoffice.hr.refresh') }}</AppButton>
      </div>

      <AppSpinner v-if="leaderboardLoading" />
      <EmptyState v-else-if="!leaderboard.length" icon="🏆" :title="t('backoffice.hr.noSalesRecorded')"
        :subtitle="t('backoffice.hr.noSalesRecordedHint')" />
      <AppCard v-else padding="none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.rank') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.employee') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.totalSales') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.orderCount') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(entry, i) in leaderboard" :key="entry.user_id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3 text-lg font-black">{{ leaderboardMedal(i) }}</td>
                <td class="px-4 py-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
                  {{ entry.employee_name ?? t('backoffice.hr.employeeHash', { id: entry.user_id }) }}
                  <span v-if="entry.employee_code" class="text-gray-400 dark:text-gray-400 font-normal">({{ entry.employee_code }})</span>
                </td>
                <td class="px-4 py-3 text-sm font-bold text-green-700 dark:text-green-300">{{ formatNumber(Number(entry.total_sales)) }} {{ t('backoffice.hr.egp') }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ entry.order_count }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>
  </div>
</template>
