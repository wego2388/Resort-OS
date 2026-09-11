<script setup lang="ts">
// جدول الورديات (Rota) — 2026-09-11: الباك إند كان كامل (templates/
// assignments/swap requests) من غير أي شاشة تستخدمه خالص (فجوة موثّقة في
// PROJECT_STATUS.md §8.2). نفس نمط تكرار الجلب المتبع في باقي تابات HR
// (employees/departments/shifts نسخ محلية للعرض بس).
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()
const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatDate: fmtDateFn } = useStaffFormat()
const branchId = computed(() => props.branchId)

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

interface Employee { id: number; full_name: string }
interface Department { id: number; name: string; name_ar?: string | null }
interface Shift { id: number; name: string; name_ar?: string | null; start_time: string; end_time: string }
interface RotaAssignment {
  id: number; employee_id: number; shift_id: number; assigned_date: string
  status: string; notes?: string | null
}
interface RotaTemplate {
  id: number; department_id: number; name: string; week_pattern: Record<string, unknown>; is_active: boolean
}
interface SwapRequest {
  id: number; requester_id: number; target_employee_id: number
  from_assignment_id: number; to_assignment_id: number; status: string; reason?: string | null
}

const subTab = ref<'week' | 'templates' | 'swaps'>('week')
const subTabs = computed(() => [
  { val: 'week' as const, label: t('backoffice.hr.rota.tabWeek') },
  { val: 'templates' as const, label: t('backoffice.hr.rota.tabTemplates') },
  { val: 'swaps' as const, label: t('backoffice.hr.rota.tabSwaps') },
])

const loadingRef = ref(false)
const employees = ref<Employee[]>([])
const departments = ref<Department[]>([])
const shifts = ref<Shift[]>([])

const employeeNameById = computed<Record<number, string>>(() => {
  const m: Record<number, string> = {}
  for (const e of employees.value) m[e.id] = e.full_name
  return m
})
const shiftLabelById = computed<Record<number, string>>(() => {
  const m: Record<number, string> = {}
  for (const s of shifts.value) m[s.id] = `${s.name_ar || s.name} (${s.start_time}-${s.end_time})`
  return m
})
const departmentNameById = computed<Record<number, string>>(() => {
  const m: Record<number, string> = {}
  for (const d of departments.value) m[d.id] = d.name_ar || d.name
  return m
})

async function loadReferenceData() {
  try {
    const [empRes, deptRes, shiftRes] = await Promise.all([
      api.get('/api/v1/hr/employees', { params: { branch_id: branchId.value, size: 100 } }),
      api.get('/api/v1/hr/departments', { params: { branch_id: branchId.value } }),
      api.get('/api/v1/hr/shifts', { params: { branch_id: branchId.value } }),
    ])
    employees.value = empRes.data.employees ?? empRes.data.items ?? empRes.data
    departments.value = deptRes.data ?? []
    shifts.value = shiftRes.data ?? []
  } catch {
    toast.error(t('backoffice.hr.rota.msg.loadReferenceError'))
  }
}

// ── Week view ───────────────────────────────────────────────────────────
function toIso(d: Date) { return d.toISOString().slice(0, 10) }
function addDays(iso: string, days: number) {
  const d = new Date(iso); d.setDate(d.getDate() + days); return toIso(d)
}
const weekStart = ref(toIso(new Date()))
const weekEnd = computed(() => addDays(weekStart.value, 6))
const assignments = ref<RotaAssignment[]>([])
const loadingWeek = ref(false)

async function loadWeek() {
  if (branchId.value == null) return
  loadingWeek.value = true
  try {
    const res = await api.get('/api/v1/hr/rota', {
      params: { branch_id: branchId.value, week_start: weekStart.value, week_end: weekEnd.value },
    })
    assignments.value = (res.data ?? []).sort((a: RotaAssignment, b: RotaAssignment) =>
      a.assigned_date.localeCompare(b.assigned_date))
  } catch {
    toast.error(t('backoffice.hr.rota.msg.loadWeekError'))
  } finally { loadingWeek.value = false }
}

const assignModal = ref(false)
const assignForm = ref({ employee_id: '' as number | '', shift_id: '' as number | '', assigned_date: weekStart.value, notes: '' })
const savingAssignment = ref(false)

function openAssignModal() {
  assignForm.value = { employee_id: '', shift_id: '', assigned_date: weekStart.value, notes: '' }
  assignModal.value = true
}

async function saveAssignment() {
  if (!assignForm.value.employee_id || !assignForm.value.shift_id || branchId.value == null) return
  savingAssignment.value = true
  try {
    await api.post('/api/v1/hr/rota/assignments', {
      branch_id: branchId.value,
      employee_id: assignForm.value.employee_id,
      shift_id: assignForm.value.shift_id,
      assigned_date: assignForm.value.assigned_date,
      notes: assignForm.value.notes || undefined,
    })
    toast.success(t('backoffice.hr.rota.msg.assignmentSaved'))
    assignModal.value = false
    await loadWeek()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.hr.rota.msg.assignmentSaveError'))
  } finally { savingAssignment.value = false }
}

const assignmentStatusVariant: Record<string, BadgeVariant> = {
  scheduled: 'info', confirmed: 'success', swapped: 'warning', absent: 'danger',
}

// ── Templates ───────────────────────────────────────────────────────────
const templates = ref<RotaTemplate[]>([])
const loadingTemplates = ref(false)

async function loadTemplates() {
  if (branchId.value == null) return
  loadingTemplates.value = true
  try {
    const res = await api.get('/api/v1/hr/rota/templates', { params: { branch_id: branchId.value } })
    templates.value = res.data ?? []
  } catch {
    toast.error(t('backoffice.hr.rota.msg.loadTemplatesError'))
  } finally { loadingTemplates.value = false }
}

const templateModal = ref(false)
const editingTemplate = ref<RotaTemplate | null>(null)
const templateForm = ref({ department_id: '' as number | '', name: '', week_pattern_json: '{}', is_active: true })
const savingTemplate = ref(false)

function openCreateTemplate() {
  editingTemplate.value = null
  templateForm.value = {
    department_id: '', name: '',
    week_pattern_json: JSON.stringify({ sat: { morning: 2 }, sun: { morning: 2 } }, null, 2),
    is_active: true,
  }
  templateModal.value = true
}
function openEditTemplate(tpl: RotaTemplate) {
  editingTemplate.value = tpl
  templateForm.value = {
    department_id: tpl.department_id, name: tpl.name,
    week_pattern_json: JSON.stringify(tpl.week_pattern, null, 2), is_active: tpl.is_active,
  }
  templateModal.value = true
}

async function saveTemplate() {
  let weekPattern: Record<string, unknown>
  try {
    weekPattern = JSON.parse(templateForm.value.week_pattern_json)
  } catch {
    toast.error(t('backoffice.hr.rota.msg.invalidWeekPatternJson'))
    return
  }
  savingTemplate.value = true
  try {
    if (editingTemplate.value) {
      await api.patch(`/api/v1/hr/rota/templates/${editingTemplate.value.id}`, {
        name: templateForm.value.name, week_pattern: weekPattern, is_active: templateForm.value.is_active,
      })
    } else {
      if (!templateForm.value.department_id || branchId.value == null) return
      await api.post('/api/v1/hr/rota/templates', {
        branch_id: branchId.value, department_id: templateForm.value.department_id,
        name: templateForm.value.name, week_pattern: weekPattern, is_active: templateForm.value.is_active,
      })
    }
    toast.success(t('backoffice.hr.rota.msg.templateSaved'))
    templateModal.value = false
    await loadTemplates()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.hr.rota.msg.templateSaveError'))
  } finally { savingTemplate.value = false }
}

// ── Swap requests ───────────────────────────────────────────────────────
const swapRequests = ref<SwapRequest[]>([])
const loadingSwaps = ref(false)

async function loadSwapRequests() {
  if (branchId.value == null) return
  loadingSwaps.value = true
  try {
    const res = await api.get('/api/v1/hr/rota/swap-requests', {
      params: { branch_id: branchId.value, status: 'pending' },
    })
    swapRequests.value = res.data ?? []
  } catch {
    toast.error(t('backoffice.hr.rota.msg.loadSwapsError'))
  } finally { loadingSwaps.value = false }
}

function assignmentLabel(id: number) {
  const a = assignments.value.find(x => x.id === id)
  if (!a) return `#${id}`
  return `${a.assigned_date} — ${employeeNameById.value[a.employee_id] ?? '#' + a.employee_id} — ${shiftLabelById.value[a.shift_id] ?? '#' + a.shift_id}`
}

async function approveSwap(id: number) {
  const ok = await confirm({
    title: t('backoffice.hr.rota.approveSwapTitle'),
    message: t('backoffice.hr.rota.approveSwapMessage'),
    confirmText: t('backoffice.hr.rota.approve'),
  })
  if (!ok) return
  try {
    await api.patch(`/api/v1/hr/rota/swap-requests/${id}/approve`)
    toast.success(t('backoffice.hr.rota.msg.swapApproved'))
    swapRequests.value = swapRequests.value.filter(s => s.id !== id)
    await loadWeek()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.hr.rota.msg.swapApproveError'))
  }
}

const swapModal = ref(false)
const swapForm = ref({
  requester_id: '' as number | '', target_employee_id: '' as number | '',
  from_assignment_id: '' as number | '', to_assignment_id: '' as number | '', reason: '',
})
const savingSwap = ref(false)

function openSwapModal() {
  swapForm.value = { requester_id: '', target_employee_id: '', from_assignment_id: '', to_assignment_id: '', reason: '' }
  swapModal.value = true
}

async function saveSwap() {
  const f = swapForm.value
  if (!f.requester_id || !f.target_employee_id || !f.from_assignment_id || !f.to_assignment_id || branchId.value == null) return
  savingSwap.value = true
  try {
    await api.post('/api/v1/hr/rota/swap-requests', {
      branch_id: branchId.value, requester_id: f.requester_id, target_employee_id: f.target_employee_id,
      from_assignment_id: f.from_assignment_id, to_assignment_id: f.to_assignment_id, reason: f.reason || undefined,
    })
    toast.success(t('backoffice.hr.rota.msg.swapRequested'))
    swapModal.value = false
    await loadSwapRequests()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.hr.rota.msg.swapRequestError'))
  } finally { savingSwap.value = false }
}

watch(subTab, (v) => {
  if (v === 'week' && !assignments.value.length) loadWeek()
  if (v === 'templates' && !templates.value.length) loadTemplates()
  if (v === 'swaps') loadSwapRequests()
})
watch(weekStart, loadWeek)

onMounted(async () => {
  loadingRef.value = true
  await loadReferenceData()
  await loadWeek()
  loadingRef.value = false
})
</script>

<template>
  <div>
    <div class="flex gap-1 bg-stone-50 dark:bg-gray-800/60 p-1 rounded-xl mb-4 w-fit">
      <button v-for="st in subTabs" :key="st.val" @click="subTab = st.val"
        :class="['px-3 py-1.5 rounded-lg text-sm font-semibold transition-all', subTab === st.val ? 'bg-white dark:bg-surface shadow-sm text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-400']"
      >{{ st.label }}</button>
    </div>

    <AppSpinner v-if="loadingRef" size="md" />

    <!-- Week view -->
    <div v-else-if="subTab === 'week'">
      <div class="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div class="flex items-center gap-2">
          <input v-model="weekStart" type="date" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <span class="text-sm text-gray-500 dark:text-gray-400">→ {{ fmtDateFn(weekEnd) }}</span>
        </div>
        <AppButton size="sm" @click="openAssignModal">+ {{ t('backoffice.hr.rota.newAssignment') }}</AppButton>
      </div>

      <AppSpinner v-if="loadingWeek" size="md" />
      <EmptyState v-else-if="!assignments.length" icon="🗓️" :title="t('backoffice.hr.rota.noAssignments')" />
      <AppCard v-else padding="none">
        <div class="overflow-x-auto">
          <table class="w-full min-w-[700px]">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.rota.column.date') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.rota.column.employee') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.rota.column.shift') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.rota.column.status') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.rota.column.notes') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="a in assignments" :key="a.id" class="border-t border-stone-100 dark:border-border/50">
                <td class="px-4 py-3 text-sm">{{ fmtDateFn(a.assigned_date) }}</td>
                <td class="px-4 py-3 text-sm font-medium">{{ employeeNameById[a.employee_id] ?? `#${a.employee_id}` }}</td>
                <td class="px-4 py-3 text-sm">{{ shiftLabelById[a.shift_id] ?? `#${a.shift_id}` }}</td>
                <td class="px-4 py-3"><AppBadge size="sm" :variant="assignmentStatusVariant[a.status] ?? 'neutral'">{{ t(`backoffice.hr.rota.assignmentStatus.${a.status}`) }}</AppBadge></td>
                <td class="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">{{ a.notes || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- Templates -->
    <div v-else-if="subTab === 'templates'">
      <div class="flex items-center justify-between mb-4">
        <p class="text-sm text-gray-500 dark:text-gray-400">{{ t('backoffice.hr.rota.templatesHint') }}</p>
        <AppButton size="sm" @click="openCreateTemplate">+ {{ t('backoffice.hr.rota.newTemplate') }}</AppButton>
      </div>
      <AppSpinner v-if="loadingTemplates" size="md" />
      <EmptyState v-else-if="!templates.length" icon="📋" :title="t('backoffice.hr.rota.noTemplates')" />
      <div v-else class="space-y-2">
        <AppCard v-for="tpl in templates" :key="tpl.id" padding="md">
          <div class="flex items-center justify-between">
            <div>
              <div class="font-bold text-gray-900 dark:text-gray-100">{{ tpl.name }}</div>
              <div class="text-xs text-gray-500 dark:text-gray-400">{{ departmentNameById[tpl.department_id] ?? `#${tpl.department_id}` }}</div>
            </div>
            <div class="flex items-center gap-2">
              <AppBadge size="sm" :variant="tpl.is_active ? 'success' : 'neutral'">{{ tpl.is_active ? t('backoffice.hr.rota.active') : t('backoffice.hr.rota.inactive') }}</AppBadge>
              <AppButton size="sm" variant="secondary" @click="openEditTemplate(tpl)">{{ t('backoffice.hr.rota.edit') }}</AppButton>
            </div>
          </div>
        </AppCard>
      </div>
    </div>

    <!-- Swap requests -->
    <div v-else-if="subTab === 'swaps'">
      <div class="flex items-center justify-between mb-4">
        <p class="text-sm text-gray-500 dark:text-gray-400">{{ t('backoffice.hr.rota.swapsHint') }}</p>
        <AppButton size="sm" @click="openSwapModal">+ {{ t('backoffice.hr.rota.newSwapRequest') }}</AppButton>
      </div>
      <AppSpinner v-if="loadingSwaps" size="md" />
      <EmptyState v-else-if="!swapRequests.length" icon="🔄" :title="t('backoffice.hr.rota.noPendingSwaps')" />
      <div v-else class="space-y-2">
        <AppCard v-for="sw in swapRequests" :key="sw.id" padding="md">
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="font-bold text-gray-900 dark:text-gray-100">
                {{ employeeNameById[sw.requester_id] ?? `#${sw.requester_id}` }}
                ⇄ {{ employeeNameById[sw.target_employee_id] ?? `#${sw.target_employee_id}` }}
              </div>
              <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">{{ assignmentLabel(sw.from_assignment_id) }}</div>
              <div class="text-xs text-gray-500 dark:text-gray-400">{{ assignmentLabel(sw.to_assignment_id) }}</div>
              <div v-if="sw.reason" class="text-xs text-gray-500 dark:text-gray-400 mt-1">📝 {{ sw.reason }}</div>
            </div>
            <AppButton size="sm" variant="primary" @click="approveSwap(sw.id)">{{ t('backoffice.hr.rota.approve') }}</AppButton>
          </div>
        </AppCard>
      </div>
    </div>

    <!-- Add assignment modal -->
    <AppModal :open="assignModal" :title="t('backoffice.hr.rota.newAssignment')" @close="assignModal = false">
      <div class="space-y-3">
        <select v-model="assignForm.employee_id" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
          <option value="">{{ t('backoffice.hr.rota.selectEmployee') }}</option>
          <option v-for="e in employees" :key="e.id" :value="e.id">{{ e.full_name }}</option>
        </select>
        <select v-model="assignForm.shift_id" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
          <option value="">{{ t('backoffice.hr.rota.selectShift') }}</option>
          <option v-for="s in shifts" :key="s.id" :value="s.id">{{ shiftLabelById[s.id] }}</option>
        </select>
        <input v-model="assignForm.assigned_date" type="date" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <input v-model="assignForm.notes" type="text" :placeholder="t('backoffice.hr.rota.notesPlaceholder')" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <AppButton class="w-full" :loading="savingAssignment" :disabled="!assignForm.employee_id || !assignForm.shift_id" @click="saveAssignment">{{ t('backoffice.hr.rota.save') }}</AppButton>
      </div>
    </AppModal>

    <!-- Template modal -->
    <AppModal :open="templateModal" :title="editingTemplate ? t('backoffice.hr.rota.editTemplate') : t('backoffice.hr.rota.newTemplate')" @close="templateModal = false">
      <div class="space-y-3">
        <select v-if="!editingTemplate" v-model="templateForm.department_id" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
          <option value="">{{ t('backoffice.hr.rota.selectDepartment') }}</option>
          <option v-for="d in departments" :key="d.id" :value="d.id">{{ departmentNameById[d.id] }}</option>
        </select>
        <input v-model="templateForm.name" type="text" :placeholder="t('backoffice.hr.rota.templateNamePlaceholder')" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <div>
          <label class="block text-xs text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.hr.rota.weekPatternLabel') }}</label>
          <textarea v-model="templateForm.week_pattern_json" rows="6" class="w-full font-mono text-xs border border-stone-200 dark:border-border rounded-xl px-3 py-2" />
          <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">{{ t('backoffice.hr.rota.weekPatternHint') }}</p>
        </div>
        <label class="flex items-center gap-2 text-sm">
          <input v-model="templateForm.is_active" type="checkbox" class="w-4 h-4" /> {{ t('backoffice.hr.rota.active') }}
        </label>
        <AppButton class="w-full" :loading="savingTemplate" :disabled="!templateForm.name || (!editingTemplate && !templateForm.department_id)" @click="saveTemplate">{{ t('backoffice.hr.rota.save') }}</AppButton>
      </div>
    </AppModal>

    <!-- Swap request modal -->
    <AppModal :open="swapModal" :title="t('backoffice.hr.rota.newSwapRequest')" @close="swapModal = false">
      <div class="space-y-3">
        <select v-model="swapForm.requester_id" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
          <option value="">{{ t('backoffice.hr.rota.selectRequester') }}</option>
          <option v-for="e in employees" :key="e.id" :value="e.id">{{ e.full_name }}</option>
        </select>
        <select v-model="swapForm.target_employee_id" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
          <option value="">{{ t('backoffice.hr.rota.selectTarget') }}</option>
          <option v-for="e in employees" :key="e.id" :value="e.id">{{ e.full_name }}</option>
        </select>
        <select v-model="swapForm.from_assignment_id" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
          <option value="">{{ t('backoffice.hr.rota.selectFromAssignment') }}</option>
          <option v-for="a in assignments" :key="a.id" :value="a.id">{{ assignmentLabel(a.id) }}</option>
        </select>
        <select v-model="swapForm.to_assignment_id" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
          <option value="">{{ t('backoffice.hr.rota.selectToAssignment') }}</option>
          <option v-for="a in assignments" :key="a.id" :value="a.id">{{ assignmentLabel(a.id) }}</option>
        </select>
        <textarea v-model="swapForm.reason" rows="2" :placeholder="t('backoffice.hr.rota.reasonPlaceholder')" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <p class="text-xs text-gray-500 dark:text-gray-400">{{ t('backoffice.hr.rota.swapAssignmentsHint') }}</p>
        <AppButton class="w-full" :loading="savingSwap"
          :disabled="!swapForm.requester_id || !swapForm.target_employee_id || !swapForm.from_assignment_id || !swapForm.to_assignment_id"
          @click="saveSwap"
        >{{ t('backoffice.hr.rota.save') }}</AppButton>
      </div>
    </AppModal>
  </div>
</template>
