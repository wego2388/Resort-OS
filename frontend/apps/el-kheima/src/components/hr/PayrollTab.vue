<script setup lang="ts">
// دفعات الرواتب — استُخرج من HRView.vue (تقسيم الملفات الكبيرة،
// 2026-09-07). employees هنا نسخة محلية مستقلة (لعرض اسم الموظف بدل الرقم
// فقط) — نفس نمط تكرار الجلب المتبع في تقسيم FinanceView.vue/CRMView.vue.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface Employee { id: number; full_name: string }
interface PayrollRun {
  id: number; period_year: number; period_month: number; status: string
  total_net: number; total_gross: number
}
interface PayrollLine {
  id: number; employee_id: number; net_salary: number; gross_salary: number
}
type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatNumber, formatDate: fmtDateFn } = useStaffFormat()
const auth = useAuthStore()
const branchId = computed(() => props.branchId)

function monthLabel(year: number, month: number) {
  return fmtDateFn(new Date(year, month - 1, 1), { month: 'long', year: 'numeric' })
}
const statusVariant: Record<string, BadgeVariant> = {
  processing: 'info', paid: 'success', draft: 'neutral', approved: 'success', rejected: 'danger',
}
const statusLabels = computed<Record<string, string>>(() => ({
  processing: t('backoffice.hr.status.processing'), paid: t('backoffice.hr.status.paid'), draft: t('backoffice.hr.status.draft'),
  approved: t('backoffice.hr.status.approved'), rejected: t('backoffice.hr.status.rejected'),
}))
function statusLabel(s: string) { return statusLabels.value[s] ?? s }

const loading = ref(false)
const employees = ref<Employee[]>([])
const employeeNameById = computed(() => {
  const m: Record<number, string> = {}
  for (const e of employees.value) m[e.id] = e.full_name
  return m
})

const payrollRuns = ref<PayrollRun[]>([])
// اعتماد الرواتب أصلاً على مستوى الدفعة الكاملة في الباك إند
// (POST /hr/payroll-runs/{id}/approve بيعتمد كل قسائم الموظفين في الدفعة
// دفعة واحدة، مفيش مفهوم اعتماد لكل قسيمة منفصل).
const expandedRunId = ref<number | null>(null)
const payrollLinesByRun = ref<Record<number, PayrollLine[]>>({})
const payrollLinesLoading = ref(false)
const approvingRunId = ref<number | null>(null)

async function loadEmployeesForNames() {
  if (employees.value.length) return
  try {
    const res = await api.get('/api/v1/hr/employees', { params: { branch_id: branchId.value, size: 100 } })
    employees.value = res.data.employees ?? res.data.items ?? res.data
  } catch { /* غير حرج — الأسماء هتفضل بس بالرقم لو فشل */ }
}

async function fetchPayroll() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/hr/payroll/runs', { params: { branch_id: branchId.value } })
    payrollRuns.value = res.data.runs ?? res.data.items ?? res.data
    await loadEmployeesForNames()
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
// واحدة (نفس الـendpoint الموجود أصلاً في الباك إند)، بدل ما يكون المستخدم
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
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.hr.msg.payrollApproveError'))
  } finally { approvingRunId.value = null }
}

// تحميل PDF/Excel كشف الرواتب (blob response، object URL، تنزيل تلقائي،
// revoke بعد 5 ثواني — نفس نمط TimeshareView.vue's downloadContractPdf).
function downloadBlobFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}

const downloadingRunFileId = ref<number | null>(null)

async function downloadPayrollExcel(run: PayrollRun) {
  downloadingRunFileId.value = run.id
  try {
    const res = await api.get(`/api/v1/hr/payroll/${run.id}/excel`, { responseType: 'blob' })
    downloadBlobFile(res.data, `payroll-${run.period_year}-${run.period_month}.xlsx`)
  } catch {
    toast.error(t('backoffice.hr.msg.payrollDownloadError'))
  } finally { downloadingRunFileId.value = null }
}

async function downloadPayrollPdf(run: PayrollRun) {
  downloadingRunFileId.value = run.id
  try {
    const res = await api.get(`/api/v1/hr/payroll/${run.id}/pdf`, { responseType: 'blob' })
    downloadBlobFile(res.data, `payroll-${run.period_year}-${run.period_month}.pdf`)
  } catch {
    toast.error(t('backoffice.hr.msg.payrollDownloadError'))
  } finally { downloadingRunFileId.value = null }
}

const downloadingPayslipLineId = ref<number | null>(null)

async function downloadPayslip(run: PayrollRun, line: PayrollLine) {
  downloadingPayslipLineId.value = line.id
  try {
    const res = await api.get(`/api/v1/hr/payroll/${run.id}/payslip/${line.employee_id}`, { responseType: 'blob' })
    downloadBlobFile(res.data, `payslip-${run.period_year}-${run.period_month}-${line.employee_id}.pdf`)
  } catch {
    toast.error(t('backoffice.hr.msg.payrollDownloadError'))
  } finally { downloadingPayslipLineId.value = null }
}

onMounted(fetchPayroll)
</script>

<template>
  <div>
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

        <div class="flex flex-wrap items-center justify-between gap-2 mt-3 pt-3 border-t border-stone-100 dark:border-border/50">
          <div class="flex flex-wrap items-center gap-2">
            <AppButton size="sm" variant="secondary" @click="togglePayrollRunDetails(run)">
              {{ expandedRunId === run.id ? t('backoffice.hr.hideLines') : t('backoffice.hr.showLines') }}
            </AppButton>
            <AppButton size="sm" variant="secondary" :loading="downloadingRunFileId === run.id" @click="downloadPayrollExcel(run)">
              📊 {{ t('backoffice.hr.downloadExcel') }}
            </AppButton>
            <AppButton size="sm" variant="secondary" :loading="downloadingRunFileId === run.id" @click="downloadPayrollPdf(run)">
              📄 {{ t('backoffice.hr.downloadPdf') }}
            </AppButton>
          </div>
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
              <div class="flex items-center gap-2">
                <span class="text-gray-900 dark:text-gray-100 font-semibold">{{ formatNumber(line.net_salary ?? 0) }} {{ t('backoffice.hr.egp') }}</span>
                <button :disabled="downloadingPayslipLineId === line.id" @click="downloadPayslip(run, line)"
                  class="text-xs font-semibold text-teal-600 hover:text-teal-800 dark:text-teal-300 dark:hover:text-teal-200 disabled:opacity-50">
                  📄 {{ t('backoffice.hr.payslipShort') }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </AppCard>
    </div>
  </div>
</template>
