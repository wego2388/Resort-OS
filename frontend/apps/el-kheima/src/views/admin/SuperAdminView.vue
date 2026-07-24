<script setup lang="ts">
// SuperAdminView — لوحة تحكم الـ super_admin الموحّدة (Decision 0003).
// Users tab → UsersView logic (step-up + StaffUserProvisioned API).
// Permissions, Settings, Audit → inline.
import { ref, computed, onMounted } from 'vue'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'
import { AppCard, AppBadge, AppSpinner, AppInput, AppButton, AppModal, AppSelect, useToast } from '@resort-os/ui'
import { useI18n } from 'vue-i18n'
import StepUpConfirmModal from '../../components/StepUpConfirmModal.vue'

const { t, locale } = useI18n()
const toast = useToast()
const auth = useAuthStore()

// ── Tabs ──────────────────────────────────────────────────────────────
type Tab = 'users' | 'permissions' | 'settings' | 'audit'
const activeTab = ref<Tab>('users')
const tabsLoaded = ref<Set<Tab>>(new Set())

function activateTab(tab: Tab) {
  activeTab.value = tab
  if (!tabsLoaded.value.has(tab)) {
    tabsLoaded.value.add(tab)
    if (tab === 'users') { loadUsers(); loadEmployees() }
    else if (tab === 'permissions') { loadCatalog(); loadUsersForPerms() }
    else if (tab === 'settings') loadSettings()
    else if (tab === 'audit') loadAuditLogs()
  }
}

// ══════════════════════════════════════════════════════════════════════
// TAB 1 — USERS  (mirrors UsersView.vue, adapted for release API)
// ══════════════════════════════════════════════════════════════════════
interface UserRow {
  id: number; email: string; full_name: string; phone: string | null
  role: string; is_active: boolean; two_factor_enabled: boolean
  must_change_password: boolean; two_factor_bootstrap_required: boolean
  preferred_language: 'ar' | 'en'
}
interface BootstrapResult {
  user: UserRow; temporary_password: string
  enrollment_token: string; enrollment_expires_at: string
}
interface EmployeeOption { id: number; full_name: string; employee_code: string; user_id: number | null }
type PendingAction = { kind: 'create' } | { kind: 'status'; user: UserRow; nextActive: boolean }

const users = ref<UserRow[]>([])
const usersTotal = ref(0)
const employees = ref<EmployeeOption[]>([])
const usersLoading = ref(true)
const usersLoadError = ref('')
const usersSearch = ref('')
const form = ref({ full_name: '', email: '', phone: '', employee_id: '', role: 'employee', preferred_language: 'ar' })
const formError = ref('')
const pending = ref<PendingAction | null>(null)
const stepUpBusy = ref(false)
const stepUpError = ref('')
const bootstrap = ref<BootstrapResult | null>(null)

const roleValues = [
  'admin', 'accountant', 'hr_manager', 'manager', 'supervisor', 'receptionist',
  'cashier', 'waiter', 'chef', 'kitchen', 'employee',
]
const roleOptions = computed(() => roleValues.map(role => ({
  value: role, label: t(`backoffice.permissions.roles.${role}`, role),
})))
const languageOptions = computed(() => [
  { value: 'ar', label: t('backoffice.accounts.arabic') },
  { value: 'en', label: t('backoffice.accounts.english') },
])
const employeeOptions = computed(() => employees.value
  .filter(e => e.user_id === null)
  .map(e => ({ value: String(e.id), label: `${e.full_name} (${e.employee_code})` })))
const filteredUsers = computed(() => {
  const q = usersSearch.value.trim().toLowerCase()
  if (!q) return users.value
  return users.value.filter(u =>
    u.full_name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q) || u.role.toLowerCase().includes(q))
})

async function loadUsers() {
  usersLoading.value = true; usersLoadError.value = ''
  try {
    const res = await api.get(ENDPOINTS.users.list, { params: { page: 1, size: 100 } })
    users.value = res.data.items
    usersTotal.value = res.data.total ?? res.data.items.length
  } catch { usersLoadError.value = t('backoffice.accounts.loadFailed') }
  finally { usersLoading.value = false }
}

async function loadEmployees() {
  try {
    const res = await api.get(ENDPOINTS.hr.employees, { params: { branch_id: auth.branchId, page: 1, size: 100 } })
    employees.value = res.data.items ?? []
  } catch { employees.value = [] }
}

function requestCreate() {
  formError.value = ''
  if (form.value.full_name.trim().length < 3 || !form.value.email.includes('@')) {
    formError.value = t('backoffice.accounts.requiredFields'); return
  }
  pending.value = { kind: 'create' }
}
function requestStatus(user: UserRow) {
  pending.value = { kind: 'status', user, nextActive: !user.is_active }
  stepUpError.value = ''
}

const stepUpPurpose = computed(() =>
  pending.value?.kind === 'status' ? 'user_role_update' as const : 'user_provision' as const)
const stepUpIntent = computed<Record<string, unknown>>(() => {
  if (pending.value?.kind === 'status')
    return { user_id: pending.value.user.id, role: null, is_active: pending.value.nextActive }
  return {
    email: form.value.email.trim().toLowerCase(),
    full_name: form.value.full_name.trim(),
    phone: form.value.phone.trim() || null,
    employee_id: form.value.employee_id ? Number(form.value.employee_id) : null,
    role: form.value.role,
    preferred_language: form.value.preferred_language,
  }
})
const stepUpDescription = computed(() => {
  if (pending.value?.kind === 'status')
    return t(pending.value.nextActive ? 'backoffice.accounts.confirmActivate' : 'backoffice.accounts.confirmDeactivate',
      { name: pending.value.user.full_name })
  return t('backoffice.accounts.confirmCreate', { name: form.value.full_name.trim() })
})

async function onStepUpConfirmed({ stepUpToken, reason }: { stepUpToken: string; reason: string }) {
  const action = pending.value
  if (!action) return
  stepUpBusy.value = true; stepUpError.value = ''
  try {
    if (action.kind === 'create') {
      const res = await api.post(ENDPOINTS.users.list, {
        email: form.value.email.trim().toLowerCase(),
        full_name: form.value.full_name.trim(),
        phone: form.value.phone.trim() || null,
        employee_id: form.value.employee_id ? Number(form.value.employee_id) : null,
        role: form.value.role,
        preferred_language: form.value.preferred_language,
        reason,
      }, { headers: { 'X-Step-Up-Token': stepUpToken } })
      bootstrap.value = res.data
      users.value = [...users.value, res.data.user]
      form.value = { full_name: '', email: '', phone: '', employee_id: '', role: 'employee', preferred_language: 'ar' }
      toast.success(t('backoffice.accounts.created'))
    } else {
      const res = await api.patch(ENDPOINTS.users.role(action.user.id), {
        role: null, is_active: action.nextActive, reason,
      }, { headers: { 'X-Step-Up-Token': stepUpToken } })
      users.value = users.value.map(u => u.id === res.data.id ? res.data : u)
      toast.success(t(action.nextActive ? 'backoffice.accounts.activated' : 'backoffice.accounts.deactivated'))
    }
    pending.value = null
  } catch (e: any) {
    const code = e?.response?.data?.detail?.error_code
    if (code === 'STEP_UP_INVALID') { stepUpError.value = t('backoffice.stepUp.errorInvalidRestart') }
    else {
      const detail = e?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : detail?.message ?? t('backoffice.accounts.saveFailed'))
      pending.value = null
    }
  } finally { stepUpBusy.value = false }
}

async function copyBootstrap() {
  if (!bootstrap.value) return
  const msg = [
    `${t('backoffice.accounts.email')}: ${bootstrap.value.user.email}`,
    `${t('backoffice.accounts.temporaryPassword')}: ${bootstrap.value.temporary_password}`,
    `${t('backoffice.accounts.enrollmentToken')}: ${bootstrap.value.enrollment_token}`,
    `${t('backoffice.accounts.loginUrl')}: ${window.location.origin}/login`,
  ].join('\n')
  await navigator.clipboard.writeText(msg)
  toast.success(t('backoffice.accounts.copied'))
}

// ══════════════════════════════════════════════════════════════════════
// TAB 2 — PERMISSIONS
// ══════════════════════════════════════════════════════════════════════
interface CatalogEntry { resource: string; action: string; label_ar: string; label_en: string; module: string; min_role_level: number; endpoint: string }
interface ExplicitPerm { id: number; user_id: number; resource: string; action: string; allowed: boolean; branch_id: number | null }

const catalog = ref<CatalogEntry[]>([])
const permUsers = ref<UserRow[]>([])
const permSearch = ref('')
const selectedPermUserId = ref<number | null>(null)
const explicitPerms = ref<ExplicitPerm[]>([])
const loadingCatalog = ref(false)
const loadingPermUsers = ref(false)
const loadingUserPerms = ref(false)
const permError = ref('')

function catalogLabel(e: CatalogEntry) { return locale.value === 'ar' ? e.label_ar : e.label_en }
const targetablePermUsers = computed(() => permUsers.value.filter(u => u.role !== 'super_admin'))
const filteredPermUsers = computed(() => {
  const q = permSearch.value.trim().toLowerCase()
  return q ? targetablePermUsers.value.filter(u => u.full_name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q)) : targetablePermUsers.value
})
const catalogByModule = computed(() => {
  const g: Record<string, CatalogEntry[]> = {}
  for (const e of catalog.value) { (g[e.module] ??= []).push(e) }
  return g
})
const selectedPermUser = computed(() => permUsers.value.find(u => u.id === selectedPermUserId.value) ?? null)

interface PendingPermStepUp { kind: 'grant' | 'deny' | 'revert'; entry: CatalogEntry; existing?: ExplicitPerm }
const pendingPermStepUp = ref<PendingPermStepUp | null>(null)
const permStepUpError = ref('')
const permStepUpBusy = ref(false)
const savingPermKey = computed(() => pendingPermStepUp.value ? `${pendingPermStepUp.value.entry.resource}:${pendingPermStepUp.value.entry.action}` : null)

function stateFor(e: CatalogEntry): 'granted' | 'denied' | 'default' {
  const ex = explicitPerms.value.find(p => p.resource === e.resource && p.action === e.action && p.branch_id === null)
  if (!ex) return 'default'
  return ex.allowed ? 'granted' : 'denied'
}
function explicitRowFor(e: CatalogEntry) {
  return explicitPerms.value.find(p => p.resource === e.resource && p.action === e.action && p.branch_id === null)
}

async function loadCatalog() {
  loadingCatalog.value = true; permError.value = ''
  try { catalog.value = (await api.get(ENDPOINTS.permissions.catalog)).data }
  catch { permError.value = t('backoffice.permissions.loadErrorCatalog') }
  finally { loadingCatalog.value = false }
}
async function loadUsersForPerms() {
  loadingPermUsers.value = true
  try { permUsers.value = (await api.get(ENDPOINTS.users.list, { params: { page: 1, size: 200 } })).data.items }
  catch { permError.value = t('backoffice.permissions.loadErrorUsers') }
  finally { loadingPermUsers.value = false }
}
async function selectPermUser(id: number) {
  selectedPermUserId.value = id; loadingUserPerms.value = true
  try { explicitPerms.value = (await api.get(ENDPOINTS.permissions.list, { params: { user_id: id } })).data }
  catch { toast.error(t('backoffice.permissions.toastErrorLoadUserPerms')); explicitPerms.value = [] }
  finally { loadingUserPerms.value = false }
}
function requestPermState(entry: CatalogEntry, newState: 'granted' | 'denied' | 'default') {
  if (!selectedPermUserId.value) return
  permStepUpError.value = ''
  if (newState === 'default') {
    const ex = explicitRowFor(entry); if (!ex) return
    pendingPermStepUp.value = { kind: 'revert', entry, existing: ex }
  } else { pendingPermStepUp.value = { kind: newState === 'granted' ? 'grant' : 'deny', entry } }
}
async function onPermStepUpConfirmed({ stepUpToken, reason }: { stepUpToken: string; reason: string }) {
  const p = pendingPermStepUp.value; if (!p || !selectedPermUserId.value) return
  permStepUpBusy.value = true
  try {
    if (p.kind === 'revert') {
      await api.delete(ENDPOINTS.permissions.permission(p.existing!.id), { data: { reason }, headers: { 'X-Step-Up-Token': stepUpToken } })
      explicitPerms.value = explicitPerms.value.filter(x => x.id !== p.existing!.id)
      toast.success(t('backoffice.permissions.toastReverted', { label: catalogLabel(p.entry) }))
    } else {
      const res = await api.post(ENDPOINTS.permissions.list, { user_id: selectedPermUserId.value, resource: p.entry.resource, action: p.entry.action, allowed: p.kind === 'grant', branch_id: null, reason }, { headers: { 'X-Step-Up-Token': stepUpToken } })
      explicitPerms.value = [...explicitPerms.value.filter(x => !(x.resource === p.entry.resource && x.action === p.entry.action)), res.data]
      toast.success(p.kind === 'grant' ? t('backoffice.permissions.toastGranted', { label: catalogLabel(p.entry) }) : t('backoffice.permissions.toastDenied', { label: catalogLabel(p.entry) }))
    }
    pendingPermStepUp.value = null
  } catch (e: any) {
    const code = e?.response?.data?.detail?.error_code
    if (code === 'STEP_UP_INVALID') permStepUpError.value = t('backoffice.stepUp.errorInvalidRestart')
    else { toast.error(e?.response?.data?.detail?.message ?? t('backoffice.permissions.toastErrorSave')); pendingPermStepUp.value = null }
  } finally { permStepUpBusy.value = false }
}
const permStepUpPurpose = computed(() => pendingPermStepUp.value?.kind === 'revert' ? 'permission_override_revoke' as const : 'permission_override_upsert' as const)
const permStepUpIntent = computed(() => {
  const p = pendingPermStepUp.value; if (!p || !selectedPermUserId.value) return {}
  if (p.kind === 'revert') return { permission_id: p.existing!.id }
  return { user_id: selectedPermUserId.value, resource: p.entry.resource, action: p.entry.action, allowed: p.kind === 'grant', branch_id: null }
})
const permStepUpDescription = computed(() => {
  const p = pendingPermStepUp.value; if (!p || !selectedPermUser.value) return ''
  const label = catalogLabel(p.entry); const name = selectedPermUser.value.full_name
  if (p.kind === 'grant') return t('backoffice.permissions.reasonPromptGrant', { label, name })
  if (p.kind === 'deny') return t('backoffice.permissions.reasonPromptDeny', { label, name })
  return t('backoffice.permissions.reasonPromptRevert', { label, name })
})

// ══════════════════════════════════════════════════════════════════════
// TAB 3 — SETTINGS
// ══════════════════════════════════════════════════════════════════════
interface SettingRow { id: number; key: string; value: string; branch_id: number | null; updated_at: string }
const settings = ref<SettingRow[]>([])
const settingsLoading = ref(false)
const settingsError = ref('')
interface PendingSettingEdit { row: SettingRow; newValue: string }
const pendingSettingEdit = ref<PendingSettingEdit | null>(null)
const settingStepUpError = ref('')
const settingStepUpBusy = ref(false)

async function loadSettings() {
  settingsLoading.value = true; settingsError.value = ''
  try { settings.value = (await api.get(ENDPOINTS.settings.get, { params: {} })).data }
  catch { settingsError.value = t('backoffice.superAdmin.settings.loadError') }
  finally { settingsLoading.value = false }
}
function openSettingEdit(row: SettingRow) { pendingSettingEdit.value = { row, newValue: row.value }; settingStepUpError.value = '' }
async function onSettingStepUpConfirmed({ stepUpToken, reason }: { stepUpToken: string; reason: string }) {
  const p = pendingSettingEdit.value; if (!p) return
  settingStepUpBusy.value = true
  try {
    await api.put(ENDPOINTS.settings.set(p.row.key), { value: p.newValue, reason }, { headers: { 'X-Step-Up-Token': stepUpToken } })
    toast.success(t('backoffice.superAdmin.settings.updateSuccess', { key: p.row.key }))
    pendingSettingEdit.value = null; await loadSettings()
  } catch (e: any) {
    const code = e?.response?.data?.detail?.error_code
    if (code === 'STEP_UP_INVALID') settingStepUpError.value = t('backoffice.stepUp.errorInvalidRestart')
    else { toast.error(e?.response?.data?.detail?.message ?? t('backoffice.superAdmin.settings.updateError')); pendingSettingEdit.value = null }
  } finally { settingStepUpBusy.value = false }
}
const settingStepUpIntent = computed(() => {
  const p = pendingSettingEdit.value; if (!p) return {}
  return { key: p.row.key, branch_id: p.row.branch_id, value: p.newValue }
})

// ══════════════════════════════════════════════════════════════════════
// TAB 4 — AUDIT LOGS
// ══════════════════════════════════════════════════════════════════════
interface AuditRow { id: number; user_id: number | null; action: string; entity_type: string; entity_id: number | null; new_data: string | null; ip_address: string | null; created_at: string }
const auditLogs = ref<AuditRow[]>([])
const auditTotal = ref(0)
const auditPage = ref(1)
const auditLoading = ref(false)
const auditError = ref('')
const auditActionFilter = ref('')
const auditEntityFilter = ref('')

async function loadAuditLogs() {
  auditLoading.value = true; auditError.value = ''
  try {
    const params: Record<string, unknown> = { page: auditPage.value, size: 50 }
    if (auditActionFilter.value) params.action = auditActionFilter.value
    if (auditEntityFilter.value) params.entity_type = auditEntityFilter.value
    const res = await api.get('/api/v1/audit-logs', { params })
    auditLogs.value = res.data.items; auditTotal.value = res.data.total
  } catch { auditError.value = t('backoffice.superAdmin.audit.loadError') }
  finally { auditLoading.value = false }
}

// ══════════════════════════════════════════════════════════════════════
// PIN MANAGEMENT — ضبط PIN التشغيلي لأي موظف (super_admin فقط)
// Backend: POST /api/v1/pins/{user_id} (manager+ — super_admin يعدّيها)
// ══════════════════════════════════════════════════════════════════════
interface PinStatus {
  user_id: number
  has_pin: boolean
  failed_attempts: number
  is_locked: boolean
}

// كاش خفيف لحالات الـ PIN — بيتملأ عند فتح modal أو بعد حفظ ناجح
const pinStatuses = ref<Map<number, PinStatus>>(new Map())
const pinTarget = ref<UserRow | null>(null)
const pinValue = ref('')
const pinBusy = ref(false)
const pinError = ref('')
const pinFetchBusy = ref(false)

function openPinModal(row: UserRow) {
  pinTarget.value = row
  pinValue.value = ''
  pinError.value = ''
  // حمّل حالة الـ PIN الحالية للمستخدم ده لو مش موجودة في الكاش
  if (!pinStatuses.value.has(row.id)) fetchPinStatus(row.id)
}

function closePinModal() {
  pinTarget.value = null
  pinValue.value = ''
  pinError.value = ''
}

async function fetchPinStatus(userId: number) {
  pinFetchBusy.value = true
  try {
    const res = await api.get(ENDPOINTS.core.pinUser(userId))
    pinStatuses.value = new Map(pinStatuses.value).set(userId, res.data)
  } catch {
    // 404 يعني مفيش PIN مضبوط — ده حالة طبيعية (has_pin: false)
    pinStatuses.value = new Map(pinStatuses.value).set(userId, {
      user_id: userId, has_pin: false, failed_attempts: 0, is_locked: false,
    })
  } finally {
    pinFetchBusy.value = false
  }
}

async function submitSetPin() {
  if (!pinTarget.value) return
  pinError.value = ''
  if (!/^\d{4,6}$/.test(pinValue.value)) {
    pinError.value = t('backoffice.superAdmin.pin.validationError')
    return
  }
  pinBusy.value = true
  try {
    const res = await api.post(ENDPOINTS.core.pinUser(pinTarget.value.id), { pin: pinValue.value })
    pinStatuses.value = new Map(pinStatuses.value).set(pinTarget.value.id, res.data)
    toast.success(t('backoffice.superAdmin.pin.success'))
    closePinModal()
  } catch (e: any) {
    pinError.value = e?.response?.data?.detail ?? t('backoffice.superAdmin.pin.saveError')
  } finally {
    pinBusy.value = false
  }
}

// ── Init ──────────────────────────────────────────────────────────────
onMounted(() => { tabsLoaded.value.add('users'); loadUsers(); loadEmployees() })
</script>

<template>
  <div class="space-y-5">
    <!-- Header -->
    <div>
      <h1 class="text-2xl font-black text-gray-800 dark:text-gray-100">{{ t('backoffice.superAdmin.title') }}</h1>
      <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ t('backoffice.superAdmin.subtitle') }}</p>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 border-b border-stone-200 dark:border-border">
      <button v-for="tab in (['users','permissions','settings','audit'] as Tab[])" :key="tab"
        @click="activateTab(tab)"
        :class="['px-4 py-2.5 text-sm font-semibold rounded-t-lg transition-colors',
          activeTab === tab ? 'bg-white dark:bg-surface text-blue-600 border border-b-white border-stone-200 dark:border-border -mb-px' : 'text-gray-500 hover:text-gray-800 hover:bg-stone-50']">
        {{ t(`backoffice.superAdmin.tabs.${tab}`) }}
      </button>
    </div>

    <!-- ═══ TAB: USERS ═══ -->
    <div v-show="activeTab === 'users'" class="space-y-5">
      <!-- Create form -->
      <AppCard :title="t('backoffice.accounts.createTitle')">
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <AppInput v-model="form.full_name" :label="t('backoffice.accounts.fullName')" autocomplete="name" required />
          <AppInput v-model="form.email" type="email" inputmode="email" :label="t('backoffice.accounts.email')" autocomplete="off" required />
          <AppInput v-model="form.phone" inputmode="tel" :label="t('backoffice.accounts.phone')" autocomplete="off" />
          <AppSelect v-model="form.employee_id" :label="t('backoffice.accounts.employeeRecord')" :placeholder="t('backoffice.accounts.noEmployeeRecord')" :options="employeeOptions" />
          <AppSelect v-model="form.role" :label="t('backoffice.accounts.role')" :options="roleOptions" required />
          <AppSelect v-model="form.preferred_language" :label="t('backoffice.accounts.language')" :options="languageOptions" required />
          <div class="flex items-end">
            <button class="w-full rounded-lg bg-primary-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-primary-800" @click="requestCreate">
              {{ t('backoffice.accounts.createButton') }}
            </button>
          </div>
        </div>
        <p v-if="formError" class="mt-3 text-sm text-danger" role="alert">{{ formError }}</p>
        <p class="mt-3 text-xs text-gray-500 dark:text-gray-400">{{ t('backoffice.accounts.createHint') }}</p>
      </AppCard>

      <!-- Users list -->
      <AppCard :title="t('backoffice.accounts.listTitle')" padding="none">
        <div class="border-b border-stone-100 p-4 dark:border-border">
          <AppInput v-model="usersSearch" type="search" :placeholder="t('backoffice.accounts.search')" />
        </div>
        <div v-if="usersLoading" class="flex justify-center p-10"><AppSpinner /></div>
        <div v-else-if="usersLoadError" class="p-6 text-center text-danger">{{ usersLoadError }}</div>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-stone-50 text-gray-500 dark:bg-surface-2 dark:text-gray-400">
              <tr>
                <th class="px-4 py-3 text-start">{{ t('backoffice.accounts.nameAndEmail') }}</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.accounts.role') }}</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.accounts.security') }}</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.superAdmin.pin.columnHeader') }}</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.accounts.status') }}</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.accounts.actions') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-stone-100 dark:divide-border">
              <tr v-for="row in filteredUsers" :key="row.id">
                <td class="px-4 py-3">
                  <div class="font-semibold text-gray-800 dark:text-gray-100">{{ row.full_name }}</div>
                  <div class="text-xs text-gray-500">{{ row.email }}</div>
                </td>
                <td class="px-4 py-3">{{ t(`backoffice.permissions.roles.${row.role}`, row.role) }}</td>
                <td class="px-4 py-3">
                  <AppBadge v-if="row.must_change_password" variant="warning">{{ t('backoffice.accounts.awaitingPassword') }}</AppBadge>
                  <AppBadge v-else-if="row.two_factor_bootstrap_required" variant="warning">{{ t('backoffice.accounts.awaiting2FA') }}</AppBadge>
                  <AppBadge v-else-if="row.two_factor_enabled" variant="success">{{ t('backoffice.accounts.twoFactorOn') }}</AppBadge>
                  <AppBadge v-else variant="neutral">{{ t('backoffice.accounts.passwordReady') }}</AppBadge>
                </td>
                <!-- PIN status badge — lazy: يتحمّل من الكاش لما يتضبط أو يُفتح الـ modal -->
                <td class="px-4 py-3">
                  <template v-if="pinStatuses.has(row.id)">
                    <AppBadge v-if="pinStatuses.get(row.id)!.is_locked" variant="danger">{{ t('backoffice.superAdmin.pin.locked') }}</AppBadge>
                    <AppBadge v-else-if="pinStatuses.get(row.id)!.has_pin" variant="success">{{ t('backoffice.superAdmin.pin.ready') }}</AppBadge>
                    <AppBadge v-else variant="neutral">{{ t('backoffice.superAdmin.pin.notSet') }}</AppBadge>
                  </template>
                  <span v-else class="text-xs text-gray-400 dark:text-gray-300">—</span>
                </td>
                <td class="px-4 py-3">
                  <AppBadge :variant="row.is_active ? 'success' : 'danger'">
                    {{ t(row.is_active ? 'backoffice.accounts.active' : 'backoffice.accounts.inactive') }}
                  </AppBadge>
                </td>
                <td class="px-4 py-3">
                  <div class="flex flex-wrap items-center gap-2">
                    <button class="font-semibold text-primary-700 hover:underline disabled:opacity-50 dark:text-primary-400"
                      :disabled="stepUpBusy" @click="requestStatus(row)">
                      {{ t(row.is_active ? 'backoffice.accounts.deactivate' : 'backoffice.accounts.activate') }}
                    </button>
                    <!-- PIN button: مخفي لـ super_admin (لا يحتاج PIN تشغيلي) -->
                    <button v-if="row.role !== 'super_admin'"
                      class="font-semibold text-amber-600 hover:underline dark:text-amber-400"
                      @click="openPinModal(row)">
                      {{ pinStatuses.get(row.id)?.has_pin ? t('backoffice.superAdmin.pin.reset') : t('backoffice.superAdmin.pin.set') }}
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          <!-- Truncation warning: لو total > عدد العناصر المعروضة -->
          <p
            v-if="usersTotal > users.length"
            class="mt-2 px-4 py-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg"
          >
            ⚠️ {{ t('common.showingOf', { shown: users.length, total: usersTotal }) }} — {{ t('common.useSearchToFilter') }}
          </p>
        </div>
      </AppCard>

      <!-- Step-up for create/status -->
      <StepUpConfirmModal v-if="pending" :purpose="stepUpPurpose" :intent="stepUpIntent"
        :description="stepUpDescription" :loading="stepUpBusy" :error-message="stepUpError"
        @confirmed="onStepUpConfirmed" @cancel="pending = null" />


      <!-- ── PIN Setup Modal ──────────────────────────────────────────── -->
      <!-- super_admin يضبط/يجدّد PIN تشغيلي لأي موظف (manager+ endpoint) -->
      <AppModal
        v-if="pinTarget"
        :open="true"
        :title="`${t('backoffice.superAdmin.pin.modalTitle')} — ${t('backoffice.superAdmin.pin.modalFor', { name: pinTarget.full_name })}`"
        size="sm"
        @close="closePinModal"
      >
        <div class="space-y-4">
          <!-- حالة الـ PIN الحالية -->
          <div v-if="pinFetchBusy" class="flex justify-center py-2">
            <AppSpinner size="sm" />
          </div>
          <template v-else-if="pinStatuses.has(pinTarget.id)">
            <div class="rounded-lg border px-3 py-2 text-sm"
              :class="pinStatuses.get(pinTarget.id)!.is_locked
                ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300'
                : pinStatuses.get(pinTarget.id)!.has_pin
                  ? 'border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-950/40 dark:text-green-300'
                  : 'border-stone-200 bg-stone-50 text-gray-600 dark:border-border dark:bg-surface-2 dark:text-gray-400'">
              <template v-if="pinStatuses.get(pinTarget.id)!.is_locked">
                🔒 {{ t('backoffice.superAdmin.pin.locked') }}
                <span class="ms-1 text-xs opacity-75">({{ t('backoffice.superAdmin.pin.lockedFailedAttempts', { n: pinStatuses.get(pinTarget.id)!.failed_attempts }, `${pinStatuses.get(pinTarget.id)!.failed_attempts} محاولات`) }})</span>
              </template>
              <template v-else-if="pinStatuses.get(pinTarget.id)!.has_pin">
                ✅ {{ t('backoffice.superAdmin.pin.ready') }}
              </template>
              <template v-else>
                ⚪ {{ t('backoffice.superAdmin.pin.notSet') }}
              </template>
            </div>
          </template>

          <!-- PIN input -->
          <div>
            <label class="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-200" for="pin-admin-input">
              {{ t('backoffice.superAdmin.pin.pinLabel') }}
              <span class="ms-1 text-xs font-normal text-gray-400">{{ t('backoffice.superAdmin.pin.pinHint') }}</span>
            </label>
            <input
              id="pin-admin-input"
              v-model="pinValue"
              type="password"
              inputmode="numeric"
              maxlength="6"
              :placeholder="t('backoffice.superAdmin.pin.pinPlaceholder')"
              autocomplete="off"
              autofocus
              class="min-h-12 w-full rounded-xl border border-stone-300 bg-white p-2.5 text-center text-xl tracking-[0.5em] text-gray-900 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-400/30 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
              @keyup.enter="submitSetPin"
            />
          </div>

          <p v-if="pinError" role="alert" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-300">
            {{ pinError }}
          </p>
        </div>

        <template #footer>
          <div class="flex gap-2">
            <AppButton variant="outline" class="flex-1" :disabled="pinBusy" @click="closePinModal">
              {{ t('backoffice.superAdmin.pin.cancel') }}
            </AppButton>
            <AppButton variant="primary" class="flex-1" :loading="pinBusy" @click="submitSetPin">
              {{ pinBusy ? t('backoffice.superAdmin.pin.saving') : t('backoffice.superAdmin.pin.confirm') }}
            </AppButton>
          </div>
        </template>
      </AppModal>

      <!-- Bootstrap credentials modal -->
      <AppModal v-if="bootstrap" :open="true" :title="t('backoffice.accounts.credentialsTitle')" size="md" @close="bootstrap = null">
        <div class="space-y-4">
          <p class="rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-gray-700 dark:text-gray-200">
            {{ t('backoffice.accounts.credentialsWarning') }}
          </p>
          <dl class="space-y-3 text-sm">
            <div><dt class="text-gray-500">{{ t('backoffice.accounts.email') }}</dt><dd class="font-mono break-all">{{ bootstrap.user.email }}</dd></div>
            <div><dt class="text-gray-500">{{ t('backoffice.accounts.temporaryPassword') }}</dt><dd class="rounded bg-stone-100 p-2 font-mono break-all dark:bg-surface-2">{{ bootstrap.temporary_password }}</dd></div>
            <div><dt class="text-gray-500">{{ t('backoffice.accounts.enrollmentToken') }}</dt><dd class="rounded bg-stone-100 p-2 font-mono break-all dark:bg-surface-2">{{ bootstrap.enrollment_token }}</dd></div>
          </dl>
          <p class="text-xs text-gray-500">{{ t('backoffice.accounts.onboardingHint') }}</p>
        </div>
        <template #footer>
          <div class="flex gap-2">
            <button class="flex-1 rounded-lg border border-stone-200 px-4 py-2 font-semibold dark:border-border" @click="bootstrap = null">{{ t('backoffice.accounts.close') }}</button>
            <button class="flex-1 rounded-lg bg-primary-700 px-4 py-2 font-bold text-white" @click="copyBootstrap">{{ t('backoffice.accounts.copy') }}</button>
          </div>
        </template>
      </AppModal>
    </div>

    <!-- ═══ TAB: PERMISSIONS ═══ -->
    <div v-show="activeTab === 'permissions'" class="space-y-4">
      <div v-if="permError" class="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 rounded-xl px-4 py-3 text-sm">⚠️ {{ permError }}</div>
      <div class="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-5">
        <AppCard :title="t('backoffice.permissions.employees')" padding="none">
          <div class="p-3 border-b border-stone-100 dark:border-border/50">
            <AppInput v-model="permSearch" :placeholder="t('backoffice.permissions.searchPlaceholder')" />
          </div>
          <div v-if="loadingPermUsers" class="p-8 flex justify-center"><AppSpinner /></div>
          <div v-else-if="filteredPermUsers.length === 0" class="p-8 text-center text-gray-400 text-sm">
            <div class="text-3xl mb-2">🔍</div>{{ t('backoffice.permissions.noEmployees') }}
          </div>
          <ul v-else class="max-h-[60vh] overflow-y-auto divide-y divide-stone-100">
            <li v-for="u in filteredPermUsers" :key="u.id" @click="selectPermUser(u.id)"
              :class="['px-4 py-3 cursor-pointer transition-colors', selectedPermUserId === u.id ? 'bg-blue-50 dark:bg-blue-950/40' : 'hover:bg-stone-50 dark:hover:bg-gray-800/40']">
              <div class="font-medium text-gray-800 dark:text-gray-200 text-sm">{{ u.full_name }}</div>
              <div class="flex items-center gap-2 mt-1">
                <span class="text-xs text-gray-400">{{ u.email }}</span>
                <AppBadge size="sm" variant="info">{{ t(`backoffice.permissions.roles.${u.role}`, u.role) }}</AppBadge>
              </div>
            </li>
          </ul>
        </AppCard>
        <AppCard :title="selectedPermUser ? t('backoffice.permissions.permissionsFor', { name: selectedPermUser.full_name }) : t('backoffice.permissions.selectEmployeeTitle')" padding="sm">
          <div v-if="!selectedPermUserId" class="p-10 text-center text-gray-400">
            <div class="text-4xl mb-3">👈</div>{{ t('backoffice.permissions.selectEmployeePrompt') }}
          </div>
          <div v-else-if="loadingCatalog || loadingUserPerms" class="p-10 flex justify-center"><AppSpinner size="lg" /></div>
          <div v-else class="space-y-5">
            <div v-for="(entries, module) in catalogByModule" :key="module">
              <div class="text-xs font-bold text-gray-400 uppercase tracking-wide mb-2">{{ module }}</div>
              <div class="space-y-1.5">
                <div v-for="entry in entries" :key="`${entry.resource}:${entry.action}`"
                  class="flex items-center justify-between bg-stone-50 dark:bg-gray-800/60 rounded-xl px-4 py-3">
                  <div>
                    <div class="text-sm font-medium text-gray-800 dark:text-gray-200">{{ catalogLabel(entry) }}</div>
                    <div class="text-xs text-gray-400 font-mono mt-0.5">{{ entry.endpoint }}</div>
                  </div>
                  <div class="flex items-center gap-1.5 flex-shrink-0">
                    <AppSpinner v-if="savingPermKey === `${entry.resource}:${entry.action}`" size="sm" />
                    <template v-else>
                      <button @click="requestPermState(entry,'granted')" :class="['px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors', stateFor(entry)==='granted' ? 'bg-green-600 text-white' : 'bg-white dark:bg-surface text-green-700 border border-green-200 hover:bg-green-50']">{{ t('backoffice.permissions.grant') }}</button>
                      <button @click="requestPermState(entry,'default')" :class="['px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors', stateFor(entry)==='default' ? 'bg-gray-600 text-white' : 'bg-white dark:bg-surface text-gray-600 border border-gray-200 hover:bg-gray-50']">{{ t('backoffice.permissions.default') }}</button>
                      <button @click="requestPermState(entry,'denied')" :class="['px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors', stateFor(entry)==='denied' ? 'bg-red-600 text-white' : 'bg-white dark:bg-surface text-red-700 border border-red-200 hover:bg-red-50']">{{ t('backoffice.permissions.deny') }}</button>
                    </template>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </AppCard>
      </div>
      <StepUpConfirmModal v-if="pendingPermStepUp" :purpose="permStepUpPurpose" :intent="permStepUpIntent"
        :description="permStepUpDescription" :loading="permStepUpBusy" :error-message="permStepUpError"
        @confirmed="onPermStepUpConfirmed" @cancel="pendingPermStepUp=null; permStepUpError=''" />
    </div>

    <!-- ═══ TAB: SETTINGS ═══ -->
    <div v-show="activeTab === 'settings'" class="space-y-4">
      <p class="text-sm text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl px-4 py-3">
        ⚠️ {{ t('backoffice.superAdmin.settings.globalNote') }}
      </p>
      <div v-if="settingsLoading" class="p-10 flex justify-center"><AppSpinner /></div>
      <div v-else-if="settingsError" class="text-red-600 text-sm">⚠️ {{ settingsError }}
        <button @click="loadSettings" class="ms-2 underline font-semibold">{{ t('backoffice.superAdmin.retry') }}</button>
      </div>
      <AppCard v-else-if="settings.length > 0" padding="none">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr class="text-xs font-bold text-gray-500 uppercase tracking-wide">
                <th class="px-4 py-3 text-start">{{ t('backoffice.superAdmin.settings.colKey') }}</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.superAdmin.settings.colValue') }}</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.superAdmin.settings.colScope') }}</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.superAdmin.settings.colUpdated') }}</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.superAdmin.users.colActions') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-stone-100 dark:divide-border">
              <tr v-for="row in settings" :key="row.id" class="hover:bg-stone-50 dark:hover:bg-gray-800/40 transition-colors">
                <td class="px-4 py-3 font-mono text-xs text-gray-700 dark:text-gray-300">{{ row.key }}</td>
                <td class="px-4 py-3 text-gray-800 dark:text-gray-200">{{ row.value }}</td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="row.branch_id === null ? 'warning' : 'info'">
                    {{ row.branch_id === null ? t('backoffice.superAdmin.settings.global') : `Branch ${row.branch_id}` }}
                  </AppBadge>
                </td>
                <td class="px-4 py-3 text-xs text-gray-400">{{ new Date(row.updated_at).toLocaleString(locale) }}</td>
                <td class="px-4 py-3">
                  <button @click="openSettingEdit(row)" class="text-xs text-blue-600 hover:text-blue-800 font-semibold">
                    {{ t('backoffice.superAdmin.settings.editBtn') }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
      <div v-else class="p-10 text-center text-gray-400"><div class="text-3xl mb-2">⚙️</div>{{ t('backoffice.superAdmin.settings.empty') }}</div>

      <!-- Setting edit step-up -->
      <div v-if="pendingSettingEdit" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
        <AppCard :title="t('backoffice.superAdmin.settings.editTitle', { key: pendingSettingEdit.row.key })" padding="sm" class="w-full max-w-md">
          <AppInput v-model="pendingSettingEdit.newValue" :label="t('backoffice.superAdmin.settings.newValue')" class="mb-4" />
          <StepUpConfirmModal purpose="setting_upsert" :intent="settingStepUpIntent"
            :description="t('backoffice.superAdmin.settings.stepUpDesc', { key: pendingSettingEdit.row.key })"
            :loading="settingStepUpBusy" :error-message="settingStepUpError"
            @confirmed="onSettingStepUpConfirmed" @cancel="pendingSettingEdit = null; settingStepUpError = ''" />
        </AppCard>
      </div>
    </div>

    <!-- ═══ TAB: AUDIT ═══ -->
    <div v-show="activeTab === 'audit'" class="space-y-4">
      <div class="flex flex-wrap items-center gap-3">
        <AppInput v-model="auditActionFilter" :placeholder="t('backoffice.superAdmin.audit.filterAction')" class="w-52" @keyup.enter="auditPage=1; loadAuditLogs()" />
        <AppInput v-model="auditEntityFilter" :placeholder="t('backoffice.superAdmin.audit.filterEntity')" class="w-52" @keyup.enter="auditPage=1; loadAuditLogs()" />
        <AppButton @click="auditPage=1; loadAuditLogs()" size="sm" variant="secondary">{{ t('backoffice.superAdmin.audit.search') }}</AppButton>
      </div>
      <div v-if="auditLoading" class="p-10 flex justify-center"><AppSpinner /></div>
      <div v-else-if="auditError" class="text-red-600 text-sm">⚠️ {{ auditError }}</div>
      <AppCard v-else-if="auditLogs.length > 0" padding="none">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr class="text-xs font-bold text-gray-500 uppercase tracking-wide">
                <th class="px-4 py-3 text-start">#</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.superAdmin.audit.colAction') }}</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.superAdmin.audit.colEntity') }}</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.superAdmin.audit.colActor') }}</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.superAdmin.audit.colTime') }}</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.superAdmin.audit.colDetails') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-stone-100 dark:divide-border">
              <tr v-for="log in auditLogs" :key="log.id" class="hover:bg-stone-50 dark:hover:bg-gray-800/40 transition-colors">
                <td class="px-4 py-3 text-gray-400 text-xs">{{ log.id }}</td>
                <td class="px-4 py-3"><span class="font-mono text-xs bg-stone-100 dark:bg-gray-700 px-2 py-0.5 rounded">{{ log.action }}</span></td>
                <td class="px-4 py-3 text-xs text-gray-600 dark:text-gray-300">{{ log.entity_type }}<span v-if="log.entity_id" class="text-gray-400"> #{{ log.entity_id }}</span></td>
                <td class="px-4 py-3 text-xs text-gray-500">{{ log.user_id ?? '—' }}</td>
                <td class="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">{{ new Date(log.created_at).toLocaleString(locale) }}</td>
                <td class="px-4 py-3 text-xs text-gray-400 max-w-xs truncate" :title="log.new_data ?? ''">
                  {{ log.new_data ? (JSON.parse(log.new_data)?.reason ?? log.new_data.slice(0, 60)) : '—' }}
                </td>
              </tr>
            </tbody>
          </table>
          <div class="px-4 py-3 flex items-center justify-between text-xs text-gray-500 border-t border-stone-100">
            <span>{{ t('backoffice.superAdmin.users.total', { n: auditTotal }) }}</span>
            <div class="flex gap-2">
              <button :disabled="auditPage <= 1" @click="auditPage--; loadAuditLogs()" class="px-2 py-1 border rounded disabled:opacity-40">‹</button>
              <span>{{ auditPage }}</span>
              <button :disabled="auditPage * 50 >= auditTotal" @click="auditPage++; loadAuditLogs()" class="px-2 py-1 border rounded disabled:opacity-40">›</button>
            </div>
          </div>
        </div>
      </AppCard>
      <div v-else class="p-10 text-center text-gray-400"><div class="text-3xl mb-2">📋</div>{{ t('backoffice.superAdmin.audit.empty') }}</div>
    </div>
  </div>
</template>
