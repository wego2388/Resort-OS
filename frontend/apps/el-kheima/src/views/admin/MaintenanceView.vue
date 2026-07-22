<script setup lang="ts">
// Maintenance — assets, work orders, preventive schedules.
// Backend: app/modules/maintenance (schemas.py / api/router.py). Real gates
// mirrored here exactly (not guessed): asset create/update + schedule
// create/update need `manager`; asset dispose needs `admin`; work orders can
// be created/updated by ANY authenticated user (get_current_active_user) —
// reporting a broken A/C is not a manager-only action — only `complete`
// needs `manager`. The /admin/maintenance route itself is gated at
// `supervisor` (see router/index.ts) so this whole screen — including the
// "report an issue" flow — only shows up for supervisor+ in the nav; a
// plain waiter/cashier reporting an issue is expected to go through their
// own floor screens, not this back-office management view.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatNumber, formatDate } = useStaffFormat()
const auth = useAuthStore()
// استخدام computed ref مش snapshot — عشان لو الـ store اتحمل بعد التعريف
// القيمة تتحدث تلقائياً ومش بنبعت branch_id=undefined فبنجيب 422
const branchId = computed(() => auth.branchId)

const tab = ref<'assets' | 'work-orders' | 'schedules'>('assets')
const loading = ref(false)

// ── Types (mirror backend schemas.py exactly) ───────────────────────────
interface Asset {
  id: number; branch_id: number; name: string; code: string; category: string
  location: string | null; serial_number: string | null
  purchase_date: string | null; warranty_until: string | null
  status: string; notes: string | null
  purchase_cost: number | null; salvage_value: number
  useful_life_years: number | null; depreciation_method: string
  depreciation_start_date: string | null; accumulated_depreciation: number
}
interface WorkOrderPart {
  id: number; work_order_id: number; part_name: string; part_number: string | null
  quantity: number; unit_cost: number; total_cost: number
}
interface WorkOrder {
  id: number; branch_id: number; asset_id: number | null; order_number: string
  title: string; description: string | null; order_type: string
  schedule_id: number | null; priority: string; status: string
  assigned_to: number | null; reported_by: number | null
  scheduled_date: string | null; completed_at: string | null
  labour_hours: number; labour_cost: number; parts_cost: number
  notes: string | null; parts: WorkOrderPart[]
}
interface Schedule {
  id: number; branch_id: number; asset_id: number; title: string
  frequency_days: number; last_done: string | null; next_due: string
  is_active: boolean; assigned_to: number | null; checklist: string | null
}

const assets = ref<Asset[]>([])
const workOrders = ref<WorkOrder[]>([])
const schedules = ref<Schedule[]>([])

const assetsById = computed<Record<number, Asset>>(() =>
  Object.fromEntries(assets.value.map((a) => [a.id, a])),
)

// ── Labels / badges ───────────────────────────────────────────────────
type Variant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

const categoryLabels = computed<Record<string, string>>(() => ({
  hvac: t('backoffice.maintenance.category.hvac'), electrical: t('backoffice.maintenance.category.electrical'),
  plumbing: t('backoffice.maintenance.category.plumbing'), furniture: t('backoffice.maintenance.category.furniture'),
  vehicle: t('backoffice.maintenance.category.vehicle'), other: t('backoffice.maintenance.category.other'),
}))
const assetStatusConfig = computed<Record<string, { label: string; variant: Variant }>>(() => ({
  operational:       { label: t('backoffice.maintenance.assetStatus.operational'),        variant: 'success' },
  under_maintenance:  { label: t('backoffice.maintenance.assetStatus.underMaintenance'), variant: 'warning' },
  out_of_service:     { label: t('backoffice.maintenance.assetStatus.outOfService'), variant: 'danger' },
  disposed:           { label: t('backoffice.maintenance.assetStatus.disposed'),      variant: 'neutral' },
}))
const priorityConfig = computed<Record<string, { label: string; variant: Variant }>>(() => ({
  low: { label: t('backoffice.maintenance.priority.low'), variant: 'neutral' },
  medium: { label: t('backoffice.maintenance.priority.medium'), variant: 'info' },
  high: { label: t('backoffice.maintenance.priority.high'), variant: 'warning' },
  critical: { label: t('backoffice.maintenance.priority.critical'), variant: 'danger' },
}))
const woStatusConfig = computed<Record<string, { label: string; variant: Variant }>>(() => ({
  open:           { label: t('backoffice.maintenance.woStatus.open'),       variant: 'neutral' },
  in_progress:    { label: t('backoffice.maintenance.woStatus.inProgress'), variant: 'info' },
  pending_parts:  { label: t('backoffice.maintenance.woStatus.pendingParts'), variant: 'warning' },
  completed:      { label: t('backoffice.maintenance.woStatus.completed'),       variant: 'success' },
  cancelled:      { label: t('backoffice.maintenance.woStatus.cancelled'),        variant: 'danger' },
}))
const orderTypeLabels = computed<Record<string, string>>(() => ({
  corrective: t('backoffice.maintenance.orderType.corrective'), preventive: t('backoffice.maintenance.orderType.preventive'),
  inspection: t('backoffice.maintenance.orderType.inspection'),
}))

function fmtMoney(v: number | null | undefined) {
  return `${formatNumber(Number(v ?? 0))} ${t('backoffice.maintenance.currency')}`
}
function fmtDate(d: string | null | undefined) {
  if (!d) return '—'
  try { return formatDate(d, { day: 'numeric', month: 'short', year: 'numeric' }) }
  catch { return d }
}

// ── Filters ──────────────────────────────────────────────────────────
const assetCategoryFilter = ref('')
const assetStatusFilter = ref('')
const woStatusFilter = ref('')
const woPriorityFilter = ref('')
const scheduleActiveOnly = ref(true)

// ── Loaders ──────────────────────────────────────────────────────────
async function loadAssets() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/maintenance/assets', {
      params: {
        branch_id: branchId.value, size: 100,
        category: assetCategoryFilter.value || undefined,
        status: assetStatusFilter.value || undefined,
      },
    })
    assets.value = res.data.items ?? []
  } catch { toast.error(t('backoffice.maintenance.msg.loadAssetsError')) }
  finally { loading.value = false }
}

async function loadWorkOrders() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/maintenance/work-orders', {
      params: {
        branch_id: branchId.value, size: 100,
        status: woStatusFilter.value || undefined,
        priority: woPriorityFilter.value || undefined,
      },
    })
    workOrders.value = res.data.items ?? []
  } catch { toast.error(t('backoffice.maintenance.msg.loadWorkOrdersError')) }
  finally { loading.value = false }
}

async function loadSchedules() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/maintenance/preventive-schedules', {
      params: { branch_id: branchId.value, size: 100, active_only: scheduleActiveOnly.value },
    })
    schedules.value = res.data.items ?? []
  } catch { toast.error(t('backoffice.maintenance.msg.loadSchedulesError')) }
  finally { loading.value = false }
}

// assets are needed as a lookup (asset names on work orders/schedules) and as
// a picker (create work order/schedule) regardless of which tab is active.
async function ensureAssetsLoaded() {
  if (assets.value.length === 0) await loadAssets()
}

async function loadTab(tabId: typeof tab.value) {
  tab.value = tabId
  if (tabId === 'assets') await loadAssets()
  if (tabId === 'work-orders') { await Promise.all([loadWorkOrders(), ensureAssetsLoaded()]) }
  if (tabId === 'schedules') { await Promise.all([loadSchedules(), ensureAssetsLoaded()]) }
}

function assetLabel(assetId: number | null) {
  if (!assetId) return '—'
  const a = assetsById.value[assetId]
  return a ? `${a.name} (${a.code})` : `#${assetId}`
}

// ── Asset create/edit modal ───────────────────────────────────────────
const assetModal = ref<{ open: boolean; saving: boolean; editingId: number | null }>({
  open: false, saving: false, editingId: null,
})
const assetForm = ref({
  name: '', code: '', category: 'hvac', location: '', serial_number: '',
  purchase_date: '', warranty_until: '', notes: '',
  purchase_cost: '', salvage_value: '0', useful_life_years: '', depreciation_start_date: '',
  status: 'operational',
})

function openCreateAsset() {
  assetModal.value = { open: true, saving: false, editingId: null }
  assetForm.value = {
    name: '', code: '', category: 'hvac', location: '', serial_number: '',
    purchase_date: '', warranty_until: '', notes: '',
    purchase_cost: '', salvage_value: '0', useful_life_years: '', depreciation_start_date: '',
    status: 'operational',
  }
}

function openEditAsset(a: Asset) {
  assetModal.value = { open: true, saving: false, editingId: a.id }
  assetForm.value = {
    name: a.name, code: a.code, category: a.category,
    location: a.location ?? '', serial_number: a.serial_number ?? '',
    purchase_date: a.purchase_date ?? '', warranty_until: a.warranty_until ?? '', notes: a.notes ?? '',
    purchase_cost: a.purchase_cost != null ? String(a.purchase_cost) : '',
    salvage_value: String(a.salvage_value ?? '0'),
    useful_life_years: a.useful_life_years != null ? String(a.useful_life_years) : '',
    depreciation_start_date: a.depreciation_start_date ?? '',
    status: a.status,
  }
}

async function submitAsset() {
  if (!assetForm.value.name.trim()) { toast.error(t('backoffice.maintenance.msg.assetNameRequired')); return }
  if (!assetModal.value.editingId && !assetForm.value.code.trim()) { toast.error(t('backoffice.maintenance.msg.assetCodeRequired')); return }

  assetModal.value.saving = true
  try {
    if (assetModal.value.editingId) {
      await api.patch(`/api/v1/maintenance/assets/${assetModal.value.editingId}`, {
        name: assetForm.value.name,
        category: assetForm.value.category,
        location: assetForm.value.location || undefined,
        serial_number: assetForm.value.serial_number || undefined,
        warranty_until: assetForm.value.warranty_until || undefined,
        status: assetForm.value.status,
        notes: assetForm.value.notes || undefined,
        purchase_cost: assetForm.value.purchase_cost || undefined,
        salvage_value: assetForm.value.salvage_value || undefined,
        useful_life_years: assetForm.value.useful_life_years ? Number(assetForm.value.useful_life_years) : undefined,
        depreciation_start_date: assetForm.value.depreciation_start_date || undefined,
      })
      toast.success(t('backoffice.maintenance.msg.assetUpdated'))
    } else {
      await api.post('/api/v1/maintenance/assets', {
        branch_id: branchId.value,
        name: assetForm.value.name,
        code: assetForm.value.code,
        category: assetForm.value.category,
        location: assetForm.value.location || undefined,
        serial_number: assetForm.value.serial_number || undefined,
        purchase_date: assetForm.value.purchase_date || undefined,
        warranty_until: assetForm.value.warranty_until || undefined,
        notes: assetForm.value.notes || undefined,
        purchase_cost: assetForm.value.purchase_cost || undefined,
        salvage_value: assetForm.value.salvage_value || '0',
        useful_life_years: assetForm.value.useful_life_years ? Number(assetForm.value.useful_life_years) : undefined,
        depreciation_start_date: assetForm.value.depreciation_start_date || undefined,
      })
      toast.success(t('backoffice.maintenance.msg.assetCreated'))
    }
    assetModal.value.open = false
    await loadAssets()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.maintenance.msg.saveAssetError'))
  } finally {
    assetModal.value.saving = false
  }
}

async function disposeAsset(a: Asset) {
  const ok = await confirm({
    message: t('backoffice.maintenance.confirmDisposeAsset', { name: a.name }),
    danger: true, confirmText: t('backoffice.maintenance.yesDispose'), cancelText: t('backoffice.maintenance.cancelAction'),
  })
  if (!ok) return
  try {
    await api.post(`/api/v1/maintenance/assets/${a.id}/dispose`)
    toast.success(t('backoffice.maintenance.msg.assetDisposed'))
    await loadAssets()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.maintenance.msg.disposeAssetError'))
  }
}

// ── Work order create/edit modal ──────────────────────────────────────
const woModal = ref<{ open: boolean; saving: boolean; editingId: number | null }>({
  open: false, saving: false, editingId: null,
})
const woForm = ref({
  asset_id: '' as string | number, title: '', description: '', order_type: 'corrective',
  priority: 'medium', assigned_to: '', scheduled_date: '', notes: '', status: 'open',
  labour_hours: '', labour_cost: '',
})

function openCreateWorkOrder() {
  woModal.value = { open: true, saving: false, editingId: null }
  woForm.value = {
    asset_id: '', title: '', description: '', order_type: 'corrective',
    priority: 'medium', assigned_to: '', scheduled_date: '', notes: '', status: 'open',
    labour_hours: '', labour_cost: '',
  }
}

function openEditWorkOrder(wo: WorkOrder) {
  woModal.value = { open: true, saving: false, editingId: wo.id }
  woForm.value = {
    asset_id: wo.asset_id ?? '', title: wo.title, description: wo.description ?? '',
    order_type: wo.order_type, priority: wo.priority,
    assigned_to: wo.assigned_to != null ? String(wo.assigned_to) : '',
    scheduled_date: wo.scheduled_date ?? '', notes: wo.notes ?? '', status: wo.status,
    labour_hours: String(wo.labour_hours ?? '0'), labour_cost: String(wo.labour_cost ?? '0'),
  }
}

async function submitWorkOrder() {
  if (!woForm.value.title.trim()) { toast.error(t('backoffice.maintenance.msg.woTitleRequired')); return }

  woModal.value.saving = true
  try {
    if (woModal.value.editingId) {
      await api.patch(`/api/v1/maintenance/work-orders/${woModal.value.editingId}`, {
        title: woForm.value.title,
        description: woForm.value.description || undefined,
        priority: woForm.value.priority,
        status: woForm.value.status,
        assigned_to: woForm.value.assigned_to ? Number(woForm.value.assigned_to) : undefined,
        scheduled_date: woForm.value.scheduled_date || undefined,
        labour_hours: woForm.value.labour_hours || undefined,
        labour_cost: woForm.value.labour_cost || undefined,
        notes: woForm.value.notes || undefined,
      })
      toast.success(t('backoffice.maintenance.msg.woUpdated'))
    } else {
      await api.post('/api/v1/maintenance/work-orders', {
        branch_id: branchId.value,
        asset_id: woForm.value.asset_id ? Number(woForm.value.asset_id) : undefined,
        title: woForm.value.title,
        description: woForm.value.description || undefined,
        order_type: woForm.value.order_type,
        priority: woForm.value.priority,
        assigned_to: woForm.value.assigned_to ? Number(woForm.value.assigned_to) : undefined,
        scheduled_date: woForm.value.scheduled_date || undefined,
        notes: woForm.value.notes || undefined,
      })
      toast.success(t('backoffice.maintenance.msg.woCreated'))
    }
    woModal.value.open = false
    await loadWorkOrders()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.maintenance.msg.saveWoError'))
  } finally {
    woModal.value.saving = false
  }
}

async function completeWorkOrder(wo: WorkOrder) {
  const ok = await confirm({ message: t('backoffice.maintenance.confirmCompleteWo', { title: wo.title }) })
  if (!ok) return
  try {
    await api.post(`/api/v1/maintenance/work-orders/${wo.id}/complete`)
    toast.success(t('backoffice.maintenance.msg.woClosed'))
    await loadWorkOrders()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.maintenance.msg.closeWoError'))
  }
}

// ── Add-part sub-flow ───────────────────────────────────────────────
const partModal = ref<{ open: boolean; saving: boolean; woId: number | null }>({
  open: false, saving: false, woId: null,
})
const partForm = ref({ part_name: '', part_number: '', quantity: '1', unit_cost: '0' })

function openAddPart(wo: WorkOrder) {
  partModal.value = { open: true, saving: false, woId: wo.id }
  partForm.value = { part_name: '', part_number: '', quantity: '1', unit_cost: '0' }
}

async function submitPart() {
  if (!partForm.value.part_name.trim() || !partModal.value.woId) { toast.error(t('backoffice.maintenance.msg.partNameRequired')); return }
  partModal.value.saving = true
  try {
    await api.post(`/api/v1/maintenance/work-orders/${partModal.value.woId}/parts`, {
      part_name: partForm.value.part_name,
      part_number: partForm.value.part_number || undefined,
      quantity: partForm.value.quantity || '1',
      unit_cost: partForm.value.unit_cost || '0',
    })
    toast.success(t('backoffice.maintenance.msg.partAdded'))
    partModal.value.open = false
    await loadWorkOrders()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.maintenance.msg.addPartError'))
  } finally {
    partModal.value.saving = false
  }
}

const expandedWorkOrder = ref<number | null>(null)

// ── Schedule create/edit modal ─────────────────────────────────────────
const scheduleModal = ref<{ open: boolean; saving: boolean; editingId: number | null }>({
  open: false, saving: false, editingId: null,
})
const scheduleForm = ref({
  asset_id: '' as string | number, title: '', frequency_days: '30', next_due: '',
  assigned_to: '', checklist: '', is_active: true,
})

function openCreateSchedule() {
  scheduleModal.value = { open: true, saving: false, editingId: null }
  scheduleForm.value = { asset_id: '', title: '', frequency_days: '30', next_due: '', assigned_to: '', checklist: '', is_active: true }
}

function openEditSchedule(s: Schedule) {
  scheduleModal.value = { open: true, saving: false, editingId: s.id }
  scheduleForm.value = {
    asset_id: s.asset_id, title: s.title, frequency_days: String(s.frequency_days),
    next_due: s.next_due, assigned_to: s.assigned_to != null ? String(s.assigned_to) : '',
    checklist: s.checklist ?? '', is_active: s.is_active,
  }
}

async function submitSchedule() {
  if (!scheduleForm.value.title.trim()) { toast.error(t('backoffice.maintenance.msg.scheduleTitleRequired')); return }
  if (!scheduleModal.value.editingId && !scheduleForm.value.asset_id) { toast.error(t('backoffice.maintenance.msg.selectAsset')); return }
  if (!scheduleModal.value.editingId && !scheduleForm.value.next_due) { toast.error(t('backoffice.maintenance.msg.nextDueRequired')); return }

  scheduleModal.value.saving = true
  try {
    if (scheduleModal.value.editingId) {
      await api.patch(`/api/v1/maintenance/preventive-schedules/${scheduleModal.value.editingId}`, {
        title: scheduleForm.value.title,
        frequency_days: Number(scheduleForm.value.frequency_days),
        next_due: scheduleForm.value.next_due || undefined,
        assigned_to: scheduleForm.value.assigned_to ? Number(scheduleForm.value.assigned_to) : undefined,
        checklist: scheduleForm.value.checklist || undefined,
        is_active: scheduleForm.value.is_active,
      })
      toast.success(t('backoffice.maintenance.msg.scheduleUpdated'))
    } else {
      await api.post('/api/v1/maintenance/preventive-schedules', {
        branch_id: branchId.value,
        asset_id: Number(scheduleForm.value.asset_id),
        title: scheduleForm.value.title,
        frequency_days: Number(scheduleForm.value.frequency_days),
        next_due: scheduleForm.value.next_due,
        assigned_to: scheduleForm.value.assigned_to ? Number(scheduleForm.value.assigned_to) : undefined,
        checklist: scheduleForm.value.checklist || undefined,
      })
      toast.success(t('backoffice.maintenance.msg.scheduleCreated'))
    }
    scheduleModal.value.open = false
    await loadSchedules()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.maintenance.msg.saveScheduleError'))
  } finally {
    scheduleModal.value.saving = false
  }
}

onMounted(() => loadTab('assets'))
</script>

<template>
  <div>
    <div class="flex items-center justify-between flex-wrap gap-3 mb-6">
      <h2 class="text-2xl font-black text-gray-900 dark:text-gray-100">🔧 {{ t('backoffice.maintenance.title') }}</h2>
    </div>

    <div class="flex gap-1 bg-stone-100 dark:bg-gray-700 p-1 rounded-xl mb-6 w-fit">
      <button
        v-for="tabDef in [{ val: 'assets', label: t('backoffice.maintenance.tabs.assets') }, { val: 'work-orders', label: t('backoffice.maintenance.tabs.workOrders') }, { val: 'schedules', label: t('backoffice.maintenance.tabs.schedules') }]"
        :key="tabDef.val" @click="loadTab(tabDef.val as any)"
        :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all', tab === tabDef.val ? 'bg-white dark:bg-surface shadow-sm text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:text-gray-300']"
      >{{ tabDef.label }}</button>
    </div>

    <!-- ══ ASSETS ══ -->
    <div v-if="tab === 'assets'">
      <div class="flex flex-wrap items-end gap-3 mb-4">
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.column.category') }}</label>
          <select v-model="assetCategoryFilter" @change="loadAssets" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm bg-white dark:bg-surface">
            <option value="">{{ t('backoffice.maintenance.all') }}</option>
            <option v-for="(label, val) in categoryLabels" :key="val" :value="val">{{ label }}</option>
          </select>
        </div>
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.column.status') }}</label>
          <select v-model="assetStatusFilter" @change="loadAssets" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm bg-white dark:bg-surface">
            <option value="">{{ t('backoffice.maintenance.all') }}</option>
            <option v-for="(cfg, val) in assetStatusConfig" :key="val" :value="val">{{ cfg.label }}</option>
          </select>
        </div>
        <AppButton v-if="auth.hasRole('manager')" size="sm" class="ms-auto" @click="openCreateAsset">+ {{ t('backoffice.maintenance.newAsset') }}</AppButton>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <AppCard v-for="a in assets" :key="a.id" padding="md">
          <div class="flex items-start justify-between mb-2">
            <div>
              <div class="font-bold text-gray-900 dark:text-gray-100">{{ a.name }}</div>
              <div class="text-xs text-gray-400 dark:text-gray-400 font-mono">{{ a.code }}</div>
            </div>
            <AppBadge size="sm" :variant="assetStatusConfig[a.status]?.variant ?? 'neutral'">
              {{ assetStatusConfig[a.status]?.label ?? a.status }}
            </AppBadge>
          </div>
          <div class="text-xs text-gray-500 dark:text-gray-400 space-y-1 mb-3">
            <div>{{ t('backoffice.maintenance.column.category') }}: <span class="font-medium text-gray-700 dark:text-gray-300">{{ categoryLabels[a.category] ?? a.category }}</span></div>
            <div v-if="a.location">{{ t('backoffice.maintenance.location') }}: <span class="font-medium text-gray-700 dark:text-gray-300">{{ a.location }}</span></div>
            <div v-if="a.purchase_cost != null">{{ t('backoffice.maintenance.purchaseCost') }}: <span class="font-medium text-gray-700 dark:text-gray-300">{{ fmtMoney(a.purchase_cost) }}</span></div>
            <div v-if="a.purchase_cost != null">{{ t('backoffice.maintenance.accumulatedDepreciation') }}: <span class="font-medium text-amber-600 dark:text-amber-300">{{ fmtMoney(a.accumulated_depreciation) }}</span></div>
            <div v-if="a.warranty_until">{{ t('backoffice.maintenance.warrantyUntil') }}: {{ fmtDate(a.warranty_until) }}</div>
          </div>
          <div class="flex gap-2" v-if="auth.hasRole('manager') && a.status !== 'disposed'">
            <AppButton size="sm" variant="secondary" @click="openEditAsset(a)">{{ t('backoffice.maintenance.edit') }}</AppButton>
            <AppButton v-if="auth.hasRole('admin')" size="sm" variant="danger" @click="disposeAsset(a)">{{ t('backoffice.maintenance.dispose') }}</AppButton>
          </div>
        </AppCard>
        <div v-if="assets.length === 0" class="md:col-span-2 xl:col-span-3">
          <EmptyState icon="🧰" :title="t('backoffice.maintenance.noAssets')" />
        </div>
      </div>
    </div>

    <!-- ══ WORK ORDERS ══ -->
    <div v-if="tab === 'work-orders'">
      <div class="flex flex-wrap items-end gap-3 mb-4">
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.column.status') }}</label>
          <select v-model="woStatusFilter" @change="loadWorkOrders" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm bg-white dark:bg-surface">
            <option value="">{{ t('backoffice.maintenance.all') }}</option>
            <option v-for="(cfg, val) in woStatusConfig" :key="val" :value="val">{{ cfg.label }}</option>
          </select>
        </div>
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.priorityLabel') }}</label>
          <select v-model="woPriorityFilter" @change="loadWorkOrders" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm bg-white dark:bg-surface">
            <option value="">{{ t('backoffice.maintenance.all') }}</option>
            <option v-for="(cfg, val) in priorityConfig" :key="val" :value="val">{{ cfg.label }}</option>
          </select>
        </div>
        <AppButton size="sm" class="ms-auto" @click="openCreateWorkOrder">+ {{ t('backoffice.maintenance.newWorkOrder') }}</AppButton>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <div v-else class="space-y-3">
        <div v-for="wo in workOrders" :key="wo.id" class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border shadow-sm overflow-hidden">
          <div class="p-4 cursor-pointer flex items-start justify-between gap-3" @click="expandedWorkOrder = expandedWorkOrder === wo.id ? null : wo.id">
            <div class="min-w-0">
              <div class="flex items-center gap-2 flex-wrap mb-1">
                <span class="font-bold text-gray-900 dark:text-gray-100">{{ wo.title }}</span>
                <span class="text-xs text-gray-400 dark:text-gray-400 font-mono">{{ wo.order_number }}</span>
              </div>
              <div class="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 flex-wrap">
                <span>{{ orderTypeLabels[wo.order_type] ?? wo.order_type }}</span>
                <span v-if="wo.asset_id">· {{ assetLabel(wo.asset_id) }}</span>
                <span v-if="wo.scheduled_date">· {{ t('backoffice.maintenance.scheduledFor', { date: fmtDate(wo.scheduled_date) }) }}</span>
              </div>
            </div>
            <div class="flex items-center gap-2 flex-shrink-0">
              <AppBadge size="sm" :variant="priorityConfig[wo.priority]?.variant ?? 'neutral'">{{ priorityConfig[wo.priority]?.label ?? wo.priority }}</AppBadge>
              <AppBadge size="sm" :variant="woStatusConfig[wo.status]?.variant ?? 'neutral'">{{ woStatusConfig[wo.status]?.label ?? wo.status }}</AppBadge>
            </div>
          </div>

          <div v-if="expandedWorkOrder === wo.id" class="border-t border-stone-100 dark:border-border/50 p-4 space-y-3">
            <p v-if="wo.description" class="text-sm text-gray-600 dark:text-gray-400">{{ wo.description }}</p>
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div><span class="text-gray-400 dark:text-gray-400 block">{{ t('backoffice.maintenance.labourHours') }}</span><span class="font-bold">{{ wo.labour_hours }}</span></div>
              <div><span class="text-gray-400 dark:text-gray-400 block">{{ t('backoffice.maintenance.labourCost') }}</span><span class="font-bold">{{ fmtMoney(wo.labour_cost) }}</span></div>
              <div><span class="text-gray-400 dark:text-gray-400 block">{{ t('backoffice.maintenance.partsCost') }}</span><span class="font-bold">{{ fmtMoney(wo.parts_cost) }}</span></div>
              <div><span class="text-gray-400 dark:text-gray-400 block">{{ t('backoffice.maintenance.completedAt') }}</span><span class="font-bold">{{ wo.completed_at ? fmtDate(wo.completed_at) : '—' }}</span></div>
            </div>

            <div v-if="wo.parts.length">
              <p class="text-xs font-bold text-gray-500 dark:text-gray-400 mb-2">{{ t('backoffice.maintenance.usedParts') }}</p>
              <table class="w-full text-xs">
                <thead class="text-gray-400 dark:text-gray-400"><tr><th class="text-start py-1">{{ t('backoffice.maintenance.column.part') }}</th><th class="text-start py-1">{{ t('backoffice.maintenance.column.quantity') }}</th><th class="text-start py-1">{{ t('backoffice.maintenance.column.cost') }}</th></tr></thead>
                <tbody class="divide-y divide-stone-100">
                  <tr v-for="p in wo.parts" :key="p.id">
                    <td class="py-1">{{ p.part_name }}</td>
                    <td class="py-1">{{ p.quantity }}</td>
                    <td class="py-1 font-bold">{{ fmtMoney(p.total_cost) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="flex flex-wrap gap-2 pt-2 border-t border-stone-100 dark:border-border/50">
              <AppButton size="sm" variant="secondary" @click="openEditWorkOrder(wo)">{{ t('backoffice.maintenance.edit') }}</AppButton>
              <AppButton size="sm" variant="outline" @click="openAddPart(wo)">+ {{ t('backoffice.maintenance.addPart') }}</AppButton>
              <AppButton v-if="auth.hasRole('manager') && !['completed', 'cancelled'].includes(wo.status)" size="sm" @click="completeWorkOrder(wo)">✅ {{ t('backoffice.maintenance.closeAsCompleted') }}</AppButton>
            </div>
          </div>
        </div>
        <EmptyState v-if="workOrders.length === 0" icon="🛠️" :title="t('backoffice.maintenance.noWorkOrders')" />
      </div>
    </div>

    <!-- ══ PREVENTIVE SCHEDULES ══ -->
    <div v-if="tab === 'schedules'">
      <div class="flex flex-wrap items-end gap-3 mb-4">
        <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
          <input type="checkbox" v-model="scheduleActiveOnly" @change="loadSchedules" />
          {{ t('backoffice.maintenance.activeOnly') }}
        </label>
        <AppButton v-if="auth.hasRole('manager')" size="sm" class="ms-auto" @click="openCreateSchedule">+ {{ t('backoffice.maintenance.newSchedule') }}</AppButton>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.maintenance.column.title') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.maintenance.column.asset') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.maintenance.column.everyDays') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.maintenance.column.lastDone') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.maintenance.column.nextDue') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.maintenance.column.status') }}</th>
                <th class="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in schedules" :key="s.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3 font-medium text-gray-900 dark:text-gray-100 text-sm">{{ s.title }}</td>
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ assetLabel(s.asset_id) }}</td>
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ s.frequency_days }}</td>
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ fmtDate(s.last_done) }}</td>
                <td class="px-4 py-3 text-sm font-bold" :class="new Date(s.next_due) < new Date() ? 'text-red-600' : 'text-gray-900 dark:text-gray-100'">{{ fmtDate(s.next_due) }}</td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="s.is_active ? 'success' : 'neutral'">{{ s.is_active ? t('backoffice.maintenance.active') : t('backoffice.maintenance.stopped') }}</AppBadge>
                </td>
                <td class="px-4 py-3">
                  <AppButton v-if="auth.hasRole('manager')" size="sm" variant="secondary" @click="openEditSchedule(s)">{{ t('backoffice.maintenance.edit') }}</AppButton>
                </td>
              </tr>
              <tr v-if="schedules.length === 0">
                <td colspan="7" class="px-4 py-8">
                  <EmptyState icon="🗓️" :title="t('backoffice.maintenance.noSchedules')" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- ══ ASSET MODAL ══ -->
    <AppModal :open="assetModal.open" :title="assetModal.editingId ? t('backoffice.maintenance.editAssetTitle') : t('backoffice.maintenance.newAssetTitle')" @close="assetModal.open = false">
      <div class="space-y-3">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.name') }} *</label>
            <input v-model="assetForm.name" type="text" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.code') }} *</label>
            <input v-model="assetForm.code" type="text" :disabled="!!assetModal.editingId"
              class="w-full rounded-xl border border-stone-200 px-3 py-2 text-sm disabled:bg-gray-50 disabled:text-gray-400 dark:border-border dark:text-gray-400 dark:disabled:bg-gray-800" />
          </div>
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.column.category') }}</label>
            <select v-model="assetForm.category" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm bg-white dark:bg-surface">
              <option v-for="(label, val) in categoryLabels" :key="val" :value="val">{{ label }}</option>
            </select>
          </div>
          <div v-if="assetModal.editingId">
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.column.status') }}</label>
            <select v-model="assetForm.status" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm bg-white dark:bg-surface">
              <option v-for="(cfg, val) in assetStatusConfig" :key="val" :value="val" :disabled="val === 'disposed'">{{ cfg.label }}</option>
            </select>
          </div>
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.location') }}</label>
            <input v-model="assetForm.location" type="text" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.serialNumber') }}</label>
            <input v-model="assetForm.serial_number" type="text" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
          <div v-if="!assetModal.editingId">
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.purchaseDate') }}</label>
            <input v-model="assetForm.purchase_date" type="date" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.warrantyUntil') }}</label>
            <input v-model="assetForm.warranty_until" type="date" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
        </div>

        <div class="border-t border-stone-100 dark:border-border/50 pt-3">
          <p class="text-xs font-bold text-gray-500 dark:text-gray-400 mb-2">{{ t('backoffice.maintenance.depreciationDataOptional') }}</p>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.purchaseCost') }}</label>
              <input v-model="assetForm.purchase_cost" type="number" min="0" step="0.01" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
            </div>
            <div>
              <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.salvageValue') }}</label>
              <input v-model="assetForm.salvage_value" type="number" min="0" step="0.01" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
            </div>
            <div>
              <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.usefulLifeYears') }}</label>
              <input v-model="assetForm.useful_life_years" type="number" min="1" max="100" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
            </div>
            <div>
              <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.depreciationStart') }}</label>
              <input v-model="assetForm.depreciation_start_date" type="date" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
            </div>
          </div>
        </div>

        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.notes') }}</label>
          <textarea v-model="assetForm.notes" rows="2" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm resize-none" />
        </div>
      </div>
      <template #footer>
        <div class="flex gap-3">
          <AppButton variant="primary" block :loading="assetModal.saving" @click="submitAsset">{{ t('backoffice.maintenance.save') }}</AppButton>
          <AppButton variant="ghost" @click="assetModal.open = false">{{ t('backoffice.maintenance.cancelAction') }}</AppButton>
        </div>
      </template>
    </AppModal>

    <!-- ══ WORK ORDER MODAL ══ -->
    <AppModal :open="woModal.open" :title="woModal.editingId ? t('backoffice.maintenance.editWoTitle') : t('backoffice.maintenance.newWoTitle')" @close="woModal.open = false">
      <div class="space-y-3">
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.titleLabel') }} *</label>
          <input v-model="woForm.title" type="text" :placeholder="t('backoffice.maintenance.woTitlePlaceholder')" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.description') }}</label>
          <textarea v-model="woForm.description" rows="2" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm resize-none" />
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div v-if="!woModal.editingId">
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.assetOptional') }}</label>
            <select v-model="woForm.asset_id" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm bg-white dark:bg-surface">
              <option value="">{{ t('backoffice.maintenance.noSpecificAsset') }}</option>
              <option v-for="a in assets" :key="a.id" :value="a.id">{{ a.name }} ({{ a.code }})</option>
            </select>
          </div>
          <div v-if="!woModal.editingId">
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.orderTypeLabel') }}</label>
            <select v-model="woForm.order_type" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm bg-white dark:bg-surface">
              <option v-for="(label, val) in orderTypeLabels" :key="val" :value="val">{{ label }}</option>
            </select>
          </div>
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.priorityLabel') }}</label>
            <select v-model="woForm.priority" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm bg-white dark:bg-surface">
              <option v-for="(cfg, val) in priorityConfig" :key="val" :value="val">{{ cfg.label }}</option>
            </select>
          </div>
          <div v-if="woModal.editingId">
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.column.status') }}</label>
            <select v-model="woForm.status" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm bg-white dark:bg-surface">
              <option v-for="(cfg, val) in woStatusConfig" :key="val" :value="val">{{ cfg.label }}</option>
            </select>
          </div>
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.assignedToOptional') }}</label>
            <input v-model="woForm.assigned_to" type="number" min="1" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.scheduledDate') }}</label>
            <input v-model="woForm.scheduled_date" type="date" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
          <div v-if="woModal.editingId">
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.labourHours') }}</label>
            <input v-model="woForm.labour_hours" type="number" min="0" step="0.5" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
          <div v-if="woModal.editingId">
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.labourCost') }}</label>
            <input v-model="woForm.labour_cost" type="number" min="0" step="0.01" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
        </div>
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.notes') }}</label>
          <textarea v-model="woForm.notes" rows="2" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm resize-none" />
        </div>
      </div>
      <template #footer>
        <div class="flex gap-3">
          <AppButton variant="primary" block :loading="woModal.saving" @click="submitWorkOrder">{{ t('backoffice.maintenance.save') }}</AppButton>
          <AppButton variant="ghost" @click="woModal.open = false">{{ t('backoffice.maintenance.cancelAction') }}</AppButton>
        </div>
      </template>
    </AppModal>

    <!-- ══ ADD PART MODAL ══ -->
    <AppModal :open="partModal.open" :title="t('backoffice.maintenance.addPartTitle')" size="sm" @close="partModal.open = false">
      <div class="space-y-3">
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.partName') }} *</label>
          <input v-model="partForm.part_name" type="text" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.partNumberOptional') }}</label>
          <input v-model="partForm.part_number" type="text" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.column.quantity') }}</label>
            <input v-model="partForm.quantity" type="number" min="0.01" step="0.01" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.unitCost') }}</label>
            <input v-model="partForm.unit_cost" type="number" min="0" step="0.01" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
        </div>
      </div>
      <template #footer>
        <div class="flex gap-3">
          <AppButton variant="primary" block :loading="partModal.saving" @click="submitPart">{{ t('backoffice.maintenance.add') }}</AppButton>
          <AppButton variant="ghost" @click="partModal.open = false">{{ t('backoffice.maintenance.cancelAction') }}</AppButton>
        </div>
      </template>
    </AppModal>

    <!-- ══ SCHEDULE MODAL ══ -->
    <AppModal :open="scheduleModal.open" :title="scheduleModal.editingId ? t('backoffice.maintenance.editScheduleTitle') : t('backoffice.maintenance.newScheduleTitle')" @close="scheduleModal.open = false">
      <div class="space-y-3">
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.titleLabel') }} *</label>
          <input v-model="scheduleForm.title" type="text" :placeholder="t('backoffice.maintenance.schedulePlaceholder')" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        </div>
        <div v-if="!scheduleModal.editingId">
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.column.asset') }} *</label>
          <select v-model="scheduleForm.asset_id" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm bg-white dark:bg-surface">
            <option value="">{{ t('backoffice.maintenance.selectAssetPlaceholder') }}</option>
            <option v-for="a in assets" :key="a.id" :value="a.id">{{ a.name }} ({{ a.code }})</option>
          </select>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.everyNDays') }} *</label>
            <input v-model="scheduleForm.frequency_days" type="number" min="1" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.column.nextDue') }} *</label>
            <input v-model="scheduleForm.next_due" type="date" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
        </div>
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.assignedToOptional') }}</label>
          <input v-model="scheduleForm.assigned_to" type="number" min="1" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.maintenance.checklistOptional') }}</label>
          <textarea v-model="scheduleForm.checklist" rows="2" class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm resize-none" />
        </div>
        <label v-if="scheduleModal.editingId" class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
          <input type="checkbox" v-model="scheduleForm.is_active" /> {{ t('backoffice.maintenance.active') }}
        </label>
      </div>
      <template #footer>
        <div class="flex gap-3">
          <AppButton variant="primary" block :loading="scheduleModal.saving" @click="submitSchedule">{{ t('backoffice.maintenance.save') }}</AppButton>
          <AppButton variant="ghost" @click="scheduleModal.open = false">{{ t('backoffice.maintenance.cancelAction') }}</AppButton>
        </div>
      </template>
    </AppModal>
  </div>
</template>
