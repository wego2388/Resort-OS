<script setup lang="ts">
// الحضور والانصراف + سياسة الحضور + تصحيح السجلات + استيراد Excel —
// استُخرج من HRView.vue (تقسيم الملفات الكبيرة، 2026-09-07). employees
// هنا نسخة محلية مستقلة (لعرض اسم الموظف بدل الرقم فقط) — نفس نمط تكرار
// الجلب المتبع في تقسيم FinanceView.vue/CRMView.vue.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, parseApiTimestamp, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppSpinner, AppModal, AppInput, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface Employee { id: number; full_name: string }
interface AttendanceRecord {
  id: number; employee_id: number; record_date: string
  check_in: string | null; check_out: string | null; status: string
  hours_worked: number | null
}
interface AttendancePolicy {
  late_grace_minutes: number | string; early_leave_grace_minutes: number | string
  standard_shift_start: string; standard_shift_end: string
  overtime_rate_multiplier: number | string; late_penalty_rate_multiplier: number | string
  is_active: boolean
}
interface AttendanceImportResult { imported: number; errors: string[]; unmatched_employees: string[] }
type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

const toast = useToast()
const { t } = useI18n()
const { formatDate: fmtDateFn, formatTime: fmtTimeFn } = useStaffFormat()
const auth = useAuthStore()
const branchId = computed(() => props.branchId)

// toISOString() بترجّع تاريخ UTC مش التاريخ المحلي (توقيت القاهرة) — بالقرب
// من منتصف الليل المحلي كانت بترجع يوم مختلف عن اليوم الحقيقي.
function localDateStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
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

const statusVariant: Record<string, BadgeVariant> = {
  present: 'success', absent: 'danger', late: 'warning', leave: 'info', holiday: 'neutral',
}
const statusLabels = computed<Record<string, string>>(() => ({
  present: t('backoffice.hr.status.present'), absent: t('backoffice.hr.status.absent'),
  late: t('backoffice.hr.status.late'), leave: t('backoffice.hr.status.leave'),
  holiday: t('backoffice.hr.status.holiday'),
}))
function statusLabel(s: string) { return statusLabels.value[s] ?? s }

const today = new Date()
const attendanceDateFrom = ref(localDateStr(new Date(today.getFullYear(), today.getMonth(), 1)))
const attendanceDateTo = ref(localDateStr(today))
const attendanceRecords = ref<AttendanceRecord[]>([])
const attendanceLoading = ref(false)
const employees = ref<Employee[]>([])

const employeeNameById = computed(() => {
  const m: Record<number, string> = {}
  for (const e of employees.value) m[e.id] = e.full_name
  return m
})

async function loadEmployeesForNames() {
  if (employees.value.length) return
  try {
    const res = await api.get('/api/v1/hr/employees', { params: { branch_id: branchId.value, size: 100 } })
    employees.value = res.data.employees ?? res.data.items ?? res.data
  } catch { /* غير حرج — الأسماء هتفضل بس بالرقم لو فشل */ }
}

async function fetchAttendance() {
  attendanceLoading.value = true
  try {
    const res = await api.get('/api/v1/hr/attendance', {
      params: {
        branch_id: branchId.value,
        date_from: attendanceDateFrom.value,
        date_to: attendanceDateTo.value,
        size: 200,
      },
    })
    attendanceRecords.value = res.data.items ?? res.data
    await loadEmployeesForNames()
  } catch (e) {
    toast.error(t('backoffice.hr.msg.loadAttendanceError'))
  } finally { attendanceLoading.value = false }
  await fetchAttendancePolicy()
}

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
    const res = await api.get('/api/v1/hr/attendance-policy', { params: { branch_id: branchId.value } })
    attendancePolicy.value = res.data
    policyConfigured.value = true
  } catch (e: unknown) {
    if ((e as ApiErr)?.response?.status === 404) {
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
    const res = await api.put('/api/v1/hr/attendance-policy', attendancePolicy.value, { params: { branch_id: branchId.value } })
    attendancePolicy.value = res.data
    policyConfigured.value = true
    toast.success(t('backoffice.hr.msg.policySaved'))
  } catch (e) {
    toast.error(t('backoffice.hr.msg.policySaveError'))
  } finally { policySaving.value = false }
}

// ── #8: تصحيح سجل حضور يدويًا (موظف نسي يبصم انصراف، وقت خطأ...) ──────
// <input type="datetime-local"> بيشتغل بتوقيت المتصفح المحلي بدون أي معلومة
// timezone — لازم تحويل صريح للـ UTC الخام (naive) اللي الباك إند مخزّنه.
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
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.hr.msg.attendanceEditSaveError'))
  } finally {
    savingAttendanceEdit.value = false
  }
}

// ── wagdy.md H-07: استيراد ملف حضور Excel (عمود موظف أول + عمود لكل يوم) ──
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
      params: { branch_id: branchId.value, period_year: importPeriodYear.value, period_month: importPeriodMonth.value },
    })
    importResult.value = res.data
    toast.success(t('backoffice.hr.msg.attendanceImported', { count: res.data.imported }))
    await fetchAttendance()
  } catch (e: unknown) {
    const msg = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.hr.msg.importError')
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

onMounted(fetchAttendance)
</script>

<template>
  <div class="space-y-4">
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
        <table class="w-full min-w-[860px]">
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
  </div>
</template>
