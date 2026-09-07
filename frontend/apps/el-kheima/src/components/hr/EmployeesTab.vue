<script setup lang="ts">
// الموظفون: القائمة + الإنشاء + ملف الموظف الموحّد (بدلات/جزاءات/سلف/دفعات/
// رصيد إجازة/تعديل بيانات وراتب) — استُخرج من HRView.vue (تقسيم الملفات
// الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppSpinner, AppModal, AppInput, SearchInput, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface Employee {
  id: number; employee_code: string; full_name: string; position: string; department?: string
  hire_date: string; basic_salary: number; status: string; phone?: string
  email?: string; user_id?: number | null
  insurance_base_salary?: number | null; holiday_bonus?: number
}
interface Allowance {
  id: number; employee_id: number; name: string; amount: number
  is_taxable: boolean; is_pensionable: boolean; is_active: boolean
}
interface PenaltyType { id: number; name: string; name_ar?: string | null; penalty_days: number }
interface Penalty {
  id: number; employee_id: number; penalty_type_id: number | null
  penalty_date: string; penalty_days: number; reason: string; created_at: string
}
interface Payslip {
  id: number; payroll_run_id: number; period_year: number; period_month: number; status: string
  net_salary: number; gross_salary: number
}
interface AttendanceRecord {
  id: number; employee_id: number; record_date: string
  check_in: string | null; check_out: string | null; status: string
  hours_worked: number | null
}
interface LeaveRequest {
  id: number; employee_id: number; leave_type_id: number
  start_date: string; end_date: string; status: string; days_requested: number
}
interface SalaryAdvance {
  id: number; employee_id: number; amount: number
  disbursed_date: string; monthly_deduction_amount: number
  remaining_balance: number; status: string; notes?: string | null
}
interface AdvancePayment {
  id: number; employee_id: number; amount: number; payment_date: string
  deducted: boolean; notes?: string | null
}
interface LeaveBalanceMonthly {
  id: number; period_year: number; period_month: number
  opening_balance: number; accrued: number; consumed: number; closing_balance: number
}
type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatNumber, formatDate: fmtDateFn } = useStaffFormat()
const auth = useAuthStore()
const router = useRouter()
const branchId = computed(() => props.branchId)
const canManageEmployeeRecords = computed(() =>
  ['hr_manager', 'admin', 'super_admin'].includes(auth.role ?? ''),
)

// toISOString() بترجّع تاريخ UTC مش التاريخ المحلي (توقيت القاهرة) — بالقرب
// من منتصف الليل المحلي كانت بترجع يوم مختلف عن اليوم الحقيقي.
function localDateStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function formatDate(d?: string | null) {
  if (!d) return '—'
  return fmtDateFn(d)
}
function monthLabel(year: number, month: number) {
  return fmtDateFn(new Date(year, month - 1, 1), { month: 'long', year: 'numeric' })
}

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

const loading = ref(false)
const employees = ref<Employee[]>([])
const employeesTotal = ref(0)
const employeeSearchQuery = ref('')

async function fetchEmployees() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/hr/employees', {
      params: {
        branch_id: branchId.value, size: 100,
        search: employeeSearchQuery.value.trim() || undefined,
      },
    })
    employees.value = res.data.employees ?? res.data.items ?? res.data
    employeesTotal.value = res.data.total ?? employees.value.length
  } catch (e) {
    toast.error(t('backoffice.hr.msg.loadEmployeesError'))
  } finally { loading.value = false }
}

// ملف الموظف يسبق حساب الدخول عمدًا: HR يثبت البيانات الوظيفية والمالية،
// ثم السوبر أدمن يختار السجل نفسه ويمنحه الدور وعضوية الفرع من مركز التحكم.
const showEmployeeCreate = ref(false)
const savingEmployee = ref(false)
const employeeForm = ref({
  employee_code: '',
  full_name: '',
  national_id: '',
  position: '',
  department: '',
  basic_salary: '' as number | string,
  insurance_base_salary: '' as number | string,
  holiday_bonus: 0 as number | string,
  hire_date: localDateStr(new Date()),
  birth_date: '',
  phone: '',
  email: '',
})

function openEmployeeCreate() {
  employeeForm.value = {
    employee_code: '',
    full_name: '',
    national_id: '',
    position: '',
    department: '',
    basic_salary: '',
    insurance_base_salary: '',
    holiday_bonus: 0,
    hire_date: localDateStr(new Date()),
    birth_date: '',
    phone: '',
    email: '',
  }
  showEmployeeCreate.value = true
}

async function submitEmployee() {
  const form = employeeForm.value
  const salary = Number(form.basic_salary)
  if (
    !branchId.value || !form.employee_code.trim() || form.full_name.trim().length < 3
    || !form.position.trim() || !form.hire_date || !(salary > 0)
  ) {
    toast.error(t('backoffice.hr.msg.employeeRequiredFields'))
    return
  }
  savingEmployee.value = true
  try {
    const insuranceBase = form.insurance_base_salary === ''
      ? null
      : Number(form.insurance_base_salary)
    const { data } = await api.post('/api/v1/hr/employees', {
      branch_id: branchId.value,
      employee_code: form.employee_code.trim().toUpperCase(),
      full_name: form.full_name.trim(),
      national_id: form.national_id.trim() || null,
      position: form.position.trim(),
      department: form.department.trim() || null,
      basic_salary: salary,
      insurance_base_salary: insuranceBase,
      holiday_bonus: Number(form.holiday_bonus) || 0,
      hire_date: form.hire_date,
      birth_date: form.birth_date || null,
      phone: form.phone.trim() || null,
      email: form.email.trim().toLowerCase() || null,
      user_id: null,
    })
    employees.value = [data, ...employees.value]
    employeesTotal.value += 1
    showEmployeeCreate.value = false
    toast.success(t('backoffice.hr.msg.employeeCreated'))
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.hr.msg.employeeCreateError'))
  } finally {
    savingEmployee.value = false
  }
}

function openAccountProvisioning(emp: Employee) {
  router.push({
    path: '/admin/super-admin',
    query: { tab: 'users', employee: String(emp.id) },
  })
}

// ── Allowances / Penalties — نموذج بسيط لـ endpoints اليوم دي (كانت
// EmployeeAllowance/PenaltyType موجودين بالكامل في الباك إند من غير أي شاشة
// تستخدمهم). فورم صغير جوه مودال بدل شاشة منفصلة كاملة.
const allowanceModalEmployee = ref<Employee | null>(null)
const employeeAllowances = ref<Allowance[]>([])
const allowancesLoading = ref(false)
const allowanceForm = ref({ name: '', amount: 0, is_taxable: true, is_pensionable: false })
const savingAllowance = ref(false)

const penaltyModalEmployee = ref<Employee | null>(null)
const penaltyTypes = ref<PenaltyType[]>([])
const employeePenalties = ref<Penalty[]>([])
const penaltiesLoading = ref(false)
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
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.hr.msg.allowanceSaveError'))
  } finally { savingAllowance.value = false }
}

async function openPenaltyModal(emp: Employee) {
  penaltyModalEmployee.value = emp
  penaltyForm.value = { penalty_type_id: null, penalty_days: 1, reason: '' }
  try {
    const res = await api.get('/api/v1/hr/penalty-types', { params: { branch_id: branchId.value } })
    penaltyTypes.value = res.data ?? []
  } catch (e) {
    toast.error(t('backoffice.hr.msg.loadPenaltyTypesError'))
  }
  await loadEmployeePenalties(emp.id)
}

async function loadEmployeePenalties(employeeId: number) {
  penaltiesLoading.value = true
  try {
    const res = await api.get('/api/v1/hr/penalties', { params: { branch_id: branchId.value, employee_id: employeeId } })
    employeePenalties.value = res.data ?? []
  } catch (e) {
    toast.error(t('backoffice.hr.msg.loadPenaltiesError'))
  } finally { penaltiesLoading.value = false }
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
    const { data } = await api.post('/api/v1/hr/penalties', {
      employee_id: empId, branch_id: branchId.value,
      penalty_type_id: penaltyForm.value.penalty_type_id,
      penalty_date: localDateStr(new Date()),
      penalty_days: penaltyDays,
      reason: penaltyForm.value.reason,
      applied_by: auth.user?.id,
    })
    employeePenalties.value = [data, ...employeePenalties.value]
    penaltyForm.value = { penalty_type_id: null, penalty_days: 1, reason: '' }
    toast.success(t('backoffice.hr.msg.penaltyLogged'))
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.hr.msg.penaltySaveError'))
  } finally { savingPenalty.value = false }
}

// ── wagdy.md H-04/H-05: وعاء تأمين منفصل + مكافأة عيد ثابتة ─────────────
const compModalEmployee = ref<Employee | null>(null)
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
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.hr.msg.compSaveError'))
  } finally { savingComp.value = false }
}

// ── تعديل بيانات الموظف الأساسية + تغيير حالة الخدمة ────────────────────
const editModalEmployee = ref<Employee | null>(null)
const employeeEditForm = ref({ full_name: '', position: '', department: '', phone: '', email: '' })
const savingEdit = ref(false)

function openEditModal(emp: Employee) {
  editModalEmployee.value = emp
  employeeEditForm.value = {
    full_name: emp.full_name ?? '',
    position: emp.position ?? '',
    department: emp.department ?? '',
    phone: emp.phone ?? '',
    email: emp.email ?? '',
  }
}

async function submitEdit() {
  if (!editModalEmployee.value) return
  if (!employeeEditForm.value.full_name.trim() || !employeeEditForm.value.position.trim()) {
    toast.error(t('backoffice.hr.msg.editRequiredFields'))
    return
  }
  savingEdit.value = true
  try {
    const empId = editModalEmployee.value.id
    const { data } = await api.patch(`/api/v1/hr/employees/${empId}`, {
      full_name: employeeEditForm.value.full_name.trim(),
      position: employeeEditForm.value.position.trim(),
      department: employeeEditForm.value.department.trim() || null,
      phone: employeeEditForm.value.phone.trim() || null,
      email: employeeEditForm.value.email.trim() || null,
    })
    employees.value = employees.value.map(e => (e.id === empId ? { ...e, ...data } : e))
    toast.success(t('backoffice.hr.msg.editSaved'))
    editModalEmployee.value = null
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.hr.msg.editSaveError'))
  } finally { savingEdit.value = false }
}

const changingStatusEmployeeId = ref<number | null>(null)

async function changeEmployeeStatus(emp: Employee, newStatus: 'active' | 'on_leave' | 'terminated') {
  const messageKey = newStatus === 'terminated'
    ? (emp.user_id ? 'backoffice.hr.msg.confirmTerminateWithAccount' : 'backoffice.hr.msg.confirmTerminate')
    : newStatus === 'on_leave' ? 'backoffice.hr.msg.confirmOnLeave' : 'backoffice.hr.msg.confirmReactivate'
  const ok = await confirm({
    title: t('backoffice.hr.msg.confirmStatusTitle'),
    message: t(messageKey, { name: emp.full_name }),
    danger: newStatus === 'terminated',
  })
  if (!ok) return
  changingStatusEmployeeId.value = emp.id
  try {
    const { data } = await api.patch(`/api/v1/hr/employees/${emp.id}`, { status: newStatus })
    employees.value = employees.value.map(e => (e.id === emp.id ? { ...e, ...data } : e))
    toast.success(t('backoffice.hr.msg.statusUpdated'))
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.hr.msg.statusUpdateError'))
  } finally { changingStatusEmployeeId.value = null }
}

// ── ملف موظف موحّد (حضور/رواتب/إجازات/جزاءات في مكان واحد) ─────────────
const profileModalEmployee = ref<Employee | null>(null)
const profileLoading = ref(false)
const profileAttendance = ref<AttendanceRecord[]>([])
const profileLeaves = ref<LeaveRequest[]>([])
const profilePenalties = ref<Penalty[]>([])
const profilePayslips = ref<Payslip[]>([])

async function openProfileModal(emp: Employee) {
  profileModalEmployee.value = emp
  profileAttendance.value = []
  profileLeaves.value = []
  profilePenalties.value = []
  profilePayslips.value = []
  profileLoading.value = true
  const dateFrom = new Date()
  dateFrom.setDate(dateFrom.getDate() - 30)
  await Promise.all([
    api.get('/api/v1/hr/attendance', {
      params: { employee_id: emp.id, branch_id: branchId.value, date_from: localDateStr(dateFrom), size: 10 },
    }).then(res => { profileAttendance.value = res.data.items ?? [] }).catch(() => {}),
    api.get('/api/v1/hr/leaves', { params: { employee_id: emp.id, branch_id: branchId.value, size: 5 } })
      .then(res => { profileLeaves.value = res.data.items ?? [] }).catch(() => {}),
    api.get('/api/v1/hr/penalties', { params: { employee_id: emp.id, branch_id: branchId.value } })
      .then(res => { profilePenalties.value = (res.data ?? []).slice(0, 10) }).catch(() => {}),
    api.get(`/api/v1/hr/employees/${emp.id}/payslips`, { params: { size: 6 } })
      .then(res => { profilePayslips.value = res.data.items ?? [] }).catch(() => {}),
  ])
  profileLoading.value = false
}

// ── wagdy.md H-01: سلفة راتب (قرض بأقساط شهرية ثابتة) ──────────────────
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
      employee_id: empId, branch_id: branchId.value,
      amount, disbursed_date: advanceForm.value.disbursed_date,
      monthly_deduction_amount: monthlyDeduction,
      notes: advanceForm.value.notes || undefined,
    })
    employeeAdvances.value = [data, ...employeeAdvances.value]
    advanceForm.value = { amount: 0, disbursed_date: localDateStr(new Date()), monthly_deduction_amount: 0, notes: '' }
    toast.success(t('backoffice.hr.msg.advanceLogged'))
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.hr.msg.advanceSaveError'))
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
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.hr.msg.advanceCancelError'))
  }
}

// ── wagdy.md H-02: دفعة يومية بسيطة تُخصم بالكامل في نفس الشهر ──────────
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
      employee_id: empId, branch_id: branchId.value,
      amount, payment_date: paymentForm.value.payment_date,
      notes: paymentForm.value.notes || undefined,
    })
    employeePayments.value = [data, ...employeePayments.value]
    paymentForm.value = { amount: 0, payment_date: localDateStr(new Date()), notes: '' }
    toast.success(t('backoffice.hr.msg.paymentLogged'))
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.hr.msg.paymentSaveError'))
  } finally { savingPayment.value = false }
}

// ── wagdy.md H-03: رصيد الإجازة الشهري المتحرّك (7.5 يوم/شهر) ──────────
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

onMounted(fetchEmployees)
</script>

<template>
  <div class="space-y-4">
    <div class="flex justify-end mb-2">
      <AppButton v-if="canManageEmployeeRecords" variant="primary" @click="openEmployeeCreate">
        + {{ t('backoffice.hr.addEmployee') }}
      </AppButton>
    </div>

    <div class="grid gap-3 md:grid-cols-3">
      <div class="rounded-xl border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950/30">
        <div class="text-xs font-bold text-blue-700 dark:text-blue-300">{{ t('backoffice.hr.onboarding.step1Title') }}</div>
        <p class="mt-1 text-sm text-gray-700 dark:text-gray-300">{{ t('backoffice.hr.onboarding.step1Body') }}</p>
      </div>
      <div class="rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950/30">
        <div class="text-xs font-bold text-amber-700 dark:text-amber-300">{{ t('backoffice.hr.onboarding.step2Title') }}</div>
        <p class="mt-1 text-sm text-gray-700 dark:text-gray-300">{{ t('backoffice.hr.onboarding.step2Body') }}</p>
      </div>
      <div class="rounded-xl border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-900 dark:bg-emerald-950/30">
        <div class="text-xs font-bold text-emerald-700 dark:text-emerald-300">{{ t('backoffice.hr.onboarding.step3Title') }}</div>
        <p class="mt-1 text-sm text-gray-700 dark:text-gray-300">{{ t('backoffice.hr.onboarding.step3Body') }}</p>
      </div>
    </div>
    <SearchInput
      v-model="employeeSearchQuery"
      :placeholder="t('backoffice.hr.searchPlaceholder')"
      @search="fetchEmployees"
      class="max-w-sm"
    />
    <div v-if="loading" class="flex flex-col items-center justify-center gap-3 py-12">
      <AppSpinner size="md" />
      <span class="text-sm text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.loading') }}</span>
    </div>
    <AppCard v-else :title="t('backoffice.hr.employeesCount', { count: employees.length })" padding="none">
      <div class="overflow-x-auto">
        <table class="responsive-card-table w-full min-w-[900px]">
          <thead class="bg-stone-50 dark:bg-gray-800/60">
            <tr>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.name') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.position') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.department') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.salary') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.statusCol') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.accountStatus') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="emp in employees" :key="emp.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
              <td data-primary class="px-4 py-3">
                <div class="flex items-center gap-3">
                  <div class="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-700 dark:bg-blue-950/50 dark:text-blue-300">
                    {{ emp.full_name.charAt(0) }}
                  </div>
                  <div>
                    <div class="font-semibold text-gray-900 dark:text-gray-100 text-sm">{{ emp.full_name }}</div>
                    <div class="text-xs text-gray-400 dark:text-gray-400">{{ emp.employee_code }}<span v-if="emp.phone"> · {{ emp.phone }}</span></div>
                  </div>
                </div>
              </td>
              <td :data-label="t('backoffice.hr.position')" class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ emp.position }}</td>
              <td :data-label="t('backoffice.hr.department')" class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ emp.department ?? '—' }}</td>
              <td :data-label="t('backoffice.hr.salary')" class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">{{ formatNumber(emp.basic_salary ?? 0) }} {{ t('backoffice.hr.egp') }}</td>
              <td :data-label="t('backoffice.hr.statusCol')" class="px-4 py-3">
                <AppBadge size="sm" :variant="statusVariant[emp.status] ?? 'neutral'">{{ statusLabel(emp.status) }}</AppBadge>
              </td>
              <td :data-label="t('backoffice.hr.accountStatus')" class="px-4 py-3">
                <AppBadge v-if="emp.user_id" size="sm" variant="success">{{ t('backoffice.hr.accountLinked') }}</AppBadge>
                <button v-else-if="auth.role === 'super_admin'" class="text-xs font-bold text-primary-700 hover:underline dark:text-primary-300"
                  @click="openAccountProvisioning(emp)">
                  {{ t('backoffice.hr.createAccount') }}
                </button>
                <AppBadge v-else size="sm" variant="warning">{{ t('backoffice.hr.accountPending') }}</AppBadge>
              </td>
              <td data-actions class="px-4 py-3">
                <div class="flex flex-wrap items-center gap-x-3 gap-y-2 whitespace-nowrap">
                  <button @click="openProfileModal(emp)" class="text-xs font-semibold text-sky-700 hover:text-sky-900 dark:text-sky-300 dark:hover:text-sky-100">👤 {{ t('backoffice.hr.profileShort') }}</button>
                  <button v-if="canManageEmployeeRecords" @click="openEditModal(emp)" class="text-xs font-semibold text-indigo-600 hover:text-indigo-800 dark:text-indigo-300 dark:hover:text-indigo-200">✏️ {{ t('backoffice.hr.editShort') }}</button>
                  <button v-if="canManageEmployeeRecords" @click="openAllowanceModal(emp)" class="text-xs font-semibold text-blue-600 hover:text-blue-800 dark:text-blue-300 dark:hover:text-blue-200">{{ t('backoffice.hr.addAllowanceShort') }}</button>
                  <button @click="openPenaltyModal(emp)" class="text-xs font-semibold text-red-600 hover:text-red-800 dark:text-red-300 dark:hover:text-red-200">{{ t('backoffice.hr.addPenaltyShort') }}</button>
                  <button v-if="canManageEmployeeRecords" @click="openAdvanceModal(emp)" class="text-xs font-semibold text-amber-600 hover:text-amber-800 dark:text-amber-300 dark:hover:text-amber-200">💰 {{ t('backoffice.hr.advanceShort') }}</button>
                  <button @click="openPaymentModal(emp)" class="text-xs font-semibold text-teal-600 hover:text-teal-800">📅 {{ t('backoffice.hr.paymentShort') }}</button>
                  <button @click="openBalanceModal(emp)" class="text-xs font-semibold text-purple-600 hover:text-purple-800 dark:text-purple-300 dark:hover:text-purple-200">📊 {{ t('backoffice.hr.leaveBalanceShort') }}</button>
                  <button v-if="canManageEmployeeRecords" @click="openCompModal(emp)" class="text-xs font-semibold text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:text-gray-100">💵 {{ t('backoffice.hr.salaryShort') }}</button>
                  <template v-if="canManageEmployeeRecords">
                    <button v-if="emp.status !== 'on_leave'" :disabled="changingStatusEmployeeId === emp.id"
                      @click="changeEmployeeStatus(emp, 'on_leave')"
                      class="text-xs font-semibold text-amber-700 hover:text-amber-900 dark:text-amber-300 dark:hover:text-amber-100 disabled:opacity-50">
                      🌴 {{ t('backoffice.hr.setOnLeaveShort') }}
                    </button>
                    <button v-if="emp.status !== 'active'" :disabled="changingStatusEmployeeId === emp.id"
                      @click="changeEmployeeStatus(emp, 'active')"
                      class="text-xs font-semibold text-emerald-700 hover:text-emerald-900 dark:text-emerald-300 dark:hover:text-emerald-100 disabled:opacity-50">
                      ✅ {{ t('backoffice.hr.reactivateShort') }}
                    </button>
                    <button v-if="emp.status !== 'terminated'" :disabled="changingStatusEmployeeId === emp.id"
                      @click="changeEmployeeStatus(emp, 'terminated')"
                      class="text-xs font-semibold text-red-700 hover:text-red-900 dark:text-red-300 dark:hover:text-red-100 disabled:opacity-50">
                      🚫 {{ t('backoffice.hr.terminateShort') }}
                    </button>
                  </template>
                </div>
              </td>
            </tr>
            <tr v-if="employees.length === 0">
              <td data-empty colspan="7" class="px-4 py-12 text-center text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.noEmployees') }}</td>
            </tr>
          </tbody>
        </table>
        <!-- Truncation warning -->
        <p
          v-if="employeesTotal > employees.length"
          class="mt-2 px-4 py-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg"
        >
          ⚠️ {{ t('common.showingOf', { shown: employees.length, total: employeesTotal }) }} — {{ t('common.useSearchToFilter') }}
        </p>
      </div>
    </AppCard>

    <!-- HR employee master-data creation -->
    <AppModal :open="showEmployeeCreate" :title="t('backoffice.hr.createEmployeeTitle')" size="lg"
      @close="showEmployeeCreate = false">
      <div class="space-y-5">
        <div>
          <h3 class="mb-3 text-sm font-bold text-gray-800 dark:text-gray-100">{{ t('backoffice.hr.identityAndJob') }}</h3>
          <div class="grid gap-3 md:grid-cols-2">
            <AppInput v-model="employeeForm.employee_code" :label="t('backoffice.hr.employeeCode')" required />
            <AppInput v-model="employeeForm.full_name" :label="t('backoffice.hr.fullName')" required />
            <AppInput v-model="employeeForm.national_id" :label="t('backoffice.hr.nationalIdOptional')" inputmode="numeric" />
            <AppInput v-model="employeeForm.position" :label="t('backoffice.hr.position')" required />
            <AppInput v-model="employeeForm.department" :label="t('backoffice.hr.department')" />
            <AppInput v-model="employeeForm.hire_date" :label="t('backoffice.hr.hireDate')" type="date" required />
            <AppInput v-model="employeeForm.birth_date" :label="t('backoffice.hr.birthDateOptional')" type="date" />
          </div>
        </div>
        <div class="border-t border-stone-200 pt-4 dark:border-border">
          <h3 class="mb-3 text-sm font-bold text-gray-800 dark:text-gray-100">{{ t('backoffice.hr.compensationAndContact') }}</h3>
          <div class="grid gap-3 md:grid-cols-2">
            <AppInput v-model="employeeForm.basic_salary" :label="t('backoffice.hr.basicSalary')" type="number" required />
            <AppInput v-model="employeeForm.insurance_base_salary" :label="t('backoffice.hr.insuranceBaseOptional')" type="number" />
            <AppInput v-model="employeeForm.holiday_bonus" :label="t('backoffice.hr.holidayBonus')" type="number" />
            <AppInput v-model="employeeForm.phone" :label="t('backoffice.accounts.phone')" inputmode="tel" />
            <AppInput v-model="employeeForm.email" :label="t('backoffice.accounts.email')" type="email" />
          </div>
        </div>
        <p class="rounded-lg bg-blue-50 px-3 py-2 text-xs text-blue-700 dark:bg-blue-950/30 dark:text-blue-300">
          {{ t('backoffice.hr.createEmployeeHint') }}
        </p>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <AppButton variant="outline" :disabled="savingEmployee" @click="showEmployeeCreate = false">{{ t('backoffice.hr.cancel') }}</AppButton>
          <AppButton variant="primary" :loading="savingEmployee" @click="submitEmployee">{{ t('backoffice.hr.saveEmployee') }}</AppButton>
        </div>
      </template>
    </AppModal>

    <!-- ملف الموظف الموحّد -->
    <AppModal :open="!!profileModalEmployee" :title="t('backoffice.hr.profileTitle', { name: profileModalEmployee?.full_name ?? '' })"
      size="xl" @close="profileModalEmployee = null">
      <div v-if="profileLoading" class="flex justify-center py-10"><AppSpinner /></div>
      <div v-else class="space-y-5">
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div><div class="text-xs text-gray-400">{{ t('backoffice.hr.position') }}</div><div class="font-semibold text-gray-800 dark:text-gray-200">{{ profileModalEmployee?.position }}</div></div>
          <div><div class="text-xs text-gray-400">{{ t('backoffice.hr.department') }}</div><div class="font-semibold text-gray-800 dark:text-gray-200">{{ profileModalEmployee?.department ?? '—' }}</div></div>
          <div><div class="text-xs text-gray-400">{{ t('backoffice.hr.salary') }}</div><div class="font-semibold text-gray-800 dark:text-gray-200">{{ formatNumber(profileModalEmployee?.basic_salary ?? 0) }} {{ t('backoffice.hr.egp') }}</div></div>
          <div><div class="text-xs text-gray-400">{{ t('backoffice.hr.statusCol') }}</div><AppBadge size="sm" :variant="statusVariant[profileModalEmployee?.status ?? ''] ?? 'neutral'">{{ statusLabel(profileModalEmployee?.status ?? '') }}</AppBadge></div>
        </div>

        <div>
          <h4 class="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase mb-2">{{ t('backoffice.hr.profileAttendance') }}</h4>
          <div v-if="profileAttendance.length" class="space-y-1">
            <div v-for="rec in profileAttendance" :key="rec.id" class="flex items-center justify-between text-sm bg-stone-50 dark:bg-gray-800/60 rounded-lg px-3 py-1.5">
              <span class="text-gray-700 dark:text-gray-300">{{ formatDate(rec.record_date) }}</span>
              <AppBadge size="sm" :variant="statusVariant[rec.status] ?? 'neutral'">{{ statusLabel(rec.status) }}</AppBadge>
            </div>
          </div>
          <p v-else class="text-xs text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.profileNoAttendance') }}</p>
        </div>

        <div>
          <h4 class="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase mb-2">{{ t('backoffice.hr.profileLeaves') }}</h4>
          <div v-if="profileLeaves.length" class="space-y-1">
            <div v-for="lv in profileLeaves" :key="lv.id" class="flex items-center justify-between text-sm bg-stone-50 dark:bg-gray-800/60 rounded-lg px-3 py-1.5">
              <span class="text-gray-700 dark:text-gray-300">{{ formatDate(lv.start_date) }} — {{ formatDate(lv.end_date) }} ({{ t('backoffice.hr.dayCount', { count: lv.days_requested }) }})</span>
              <AppBadge size="sm" :variant="statusVariant[lv.status] ?? 'neutral'">{{ statusLabel(lv.status) }}</AppBadge>
            </div>
          </div>
          <p v-else class="text-xs text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.profileNoLeaves') }}</p>
        </div>

        <div>
          <h4 class="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase mb-2">{{ t('backoffice.hr.profilePenalties') }}</h4>
          <div v-if="profilePenalties.length" class="space-y-1">
            <div v-for="p in profilePenalties" :key="p.id" class="flex items-center justify-between text-sm bg-stone-50 dark:bg-gray-800/60 rounded-lg px-3 py-1.5">
              <div>
                <span class="text-gray-700 dark:text-gray-300">{{ p.reason }}</span>
                <span class="text-xs text-gray-400 ms-1">({{ formatDate(p.penalty_date) }})</span>
              </div>
              <span class="text-red-600 dark:text-red-300 font-semibold">{{ t('backoffice.hr.dayCount', { count: p.penalty_days }) }}</span>
            </div>
          </div>
          <p v-else class="text-xs text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.noPenalties') }}</p>
        </div>

        <div>
          <h4 class="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase mb-2">{{ t('backoffice.hr.profilePayslips') }}</h4>
          <div v-if="profilePayslips.length" class="space-y-1">
            <div v-for="slip in profilePayslips" :key="slip.id" class="flex items-center justify-between text-sm bg-stone-50 dark:bg-gray-800/60 rounded-lg px-3 py-1.5">
              <span class="text-gray-700 dark:text-gray-300">{{ monthLabel(slip.period_year, slip.period_month) }}</span>
              <span class="font-semibold text-gray-900 dark:text-gray-100">{{ formatNumber(slip.net_salary) }} {{ t('backoffice.hr.egp') }}</span>
            </div>
          </div>
          <p v-else class="text-xs text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.profileNoPayslips') }}</p>
        </div>
      </div>
    </AppModal>

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

    <!-- تعديل بيانات الموظف الأساسية -->
    <AppModal :open="!!editModalEmployee" :title="t('backoffice.hr.editTitle', { name: editModalEmployee?.full_name ?? '' })"
      @close="editModalEmployee = null">
      <div class="space-y-3">
        <AppInput v-model="employeeEditForm.full_name" :label="t('backoffice.hr.fullName')" required />
        <AppInput v-model="employeeEditForm.position" :label="t('backoffice.hr.position')" required />
        <AppInput v-model="employeeEditForm.department" :label="t('backoffice.hr.department')" />
        <AppInput v-model="employeeEditForm.phone" :label="t('backoffice.accounts.phone')" inputmode="tel" />
        <AppInput v-model="employeeEditForm.email" :label="t('backoffice.accounts.email')" type="email" />
        <AppButton :disabled="savingEdit" @click="submitEdit" variant="primary" size="sm">
          {{ savingEdit ? t('backoffice.hr.saving') : t('backoffice.hr.save') }}
        </AppButton>
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
      <div class="space-y-4">
        <div v-if="penaltiesLoading" class="text-center py-4 text-sm text-gray-400 dark:text-gray-400">{{ t('backoffice.hr.loading') }}</div>
        <div v-else-if="employeePenalties.length" class="space-y-2">
          <div v-for="p in employeePenalties" :key="p.id" class="flex items-center justify-between text-sm bg-stone-50 dark:bg-gray-800/60 rounded-lg px-3 py-2">
            <div>
              <div class="font-medium text-gray-800 dark:text-gray-200">{{ p.reason }}</div>
              <div class="text-xs text-gray-400 dark:text-gray-400">{{ formatDate(p.penalty_date) }}</div>
            </div>
            <span class="text-red-600 dark:text-red-300 font-semibold">{{ t('backoffice.hr.dayCount', { count: p.penalty_days }) }}</span>
          </div>
        </div>
        <EmptyState v-else icon="⚠️" :title="t('backoffice.hr.noPenalties')" />

        <div class="border-t border-stone-100 dark:border-border/50 pt-4 space-y-3">
        <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.logNewPenalty') }}</div>
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
  </div>
</template>
