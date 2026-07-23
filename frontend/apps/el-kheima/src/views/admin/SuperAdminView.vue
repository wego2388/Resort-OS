<script setup lang="ts">
// SuperAdminView — لوحة التحكم الموحّدة للـ super_admin (Decision 0003).
// تجمع: إدارة المستخدمين + الصلاحيات + الإعدادات + سجل التدقيق في مكان واحد.
// كل tab يحمّل بياناته بشكل مستقل عند أول تنشيط — lazy loading.
import { ref, computed, onMounted } from 'vue'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'
import { AppCard, AppBadge, AppSpinner, AppInput, AppButton, useToast } from '@resort-os/ui'
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
    if (tab === 'users') loadUsers()
    else if (tab === 'permissions') { loadCatalog(); loadUsersForPerms() }
    else if (tab === 'settings') loadSettings()
    else if (tab === 'audit') loadAuditLogs()
  }
}

// ══════════════════════════════════════════════════════════════════════
// TAB 1 — USERS
// ══════════════════════════════════════════════════════════════════════
interface UserRow {
  id: number; email: string; full_name: string; role: string
  is_active: boolean; two_factor_enabled: boolean; must_change_password: boolean
  created_at: string
}
const users = ref<UserRow[]>([])
const usersTotal = ref(0)
const usersPage = ref(1)
const usersSearch = ref('')
const usersRoleFilter = ref('')
const usersActiveFilter = ref<'' | 'true' | 'false'>('')
const usersLoading = ref(false)
const usersError = ref('')

// إنشاء مستخدم
const showCreateUser = ref(false)
const newUser = ref({ email: '', full_name: '', phone: '', role: 'cashier', password: '' })
const creatingUser = ref(false)
const createUserError = ref('')

// تغيير role/حالة مستخدم
interface PendingRoleUpdate { userId: number; full_name: string; role: string; is_active: boolean }
const pendingRoleUpdate = ref<PendingRoleUpdate | null>(null)
const roleUpdateForm = ref({ role: '', is_active: true, reason: '' })
const roleUpdateBusy = ref(false)
const roleUpdateStepUpError = ref('')

const STAFF_ROLES = [
  'admin','manager','supervisor','accountant','hr_manager',
  'receptionist','cashier','waiter','chef','kitchen',
  'timeshare_agent','employee',
]

function roleLabel(role: string) {
  return t(`backoffice.superAdmin.roles.${role}`, role)
}

async function loadUsers() {
  usersLoading.value = true
  usersError.value = ''
  try {
    const params: Record<string, unknown> = { page: usersPage.value, size: 20 }
    if (usersSearch.value.trim()) params.search = usersSearch.value.trim()
    if (usersRoleFilter.value) params.role = usersRoleFilter.value
    if (usersActiveFilter.value !== '') params.is_active = usersActiveFilter.value
    const res = await api.get(ENDPOINTS.permissions.users, { params })
    users.value = res.data.items
    usersTotal.value = res.data.total
  } catch {
    usersError.value = t('backoffice.superAdmin.users.loadError')
  } finally {
    usersLoading.value = false
  }
}

async function createUser() {
  createUserError.value = ''
  if (!newUser.value.email || !newUser.value.full_name || !newUser.value.password) {
    createUserError.value = t('backoffice.superAdmin.users.createValidation')
    return
  }
  creatingUser.value = true
  try {
    await api.post(ENDPOINTS.permissions.createUser, newUser.value)
    toast.success(t('backoffice.superAdmin.users.createSuccess', { name: newUser.value.full_name }))
    showCreateUser.value = false
    newUser.value = { email: '', full_name: '', phone: '', role: 'cashier', password: '' }
    await loadUsers()
  } catch (e: any) {
    createUserError.value = e?.response?.data?.detail ?? t('backoffice.superAdmin.users.createError')
  } finally {
    creatingUser.value = false
  }
}

function openRoleUpdate(user: UserRow) {
  pendingRoleUpdate.value = { userId: user.id, full_name: user.full_name, role: user.role, is_active: user.is_active }
  roleUpdateForm.value = { role: user.role, is_active: user.is_active, reason: '' }
  roleUpdateStepUpError.value = ''
}

async function onRoleUpdateStepUpConfirmed({ stepUpToken, reason }: { stepUpToken: string; reason: string }) {
  if (!pendingRoleUpdate.value) return
  roleUpdateBusy.value = true
  try {
    await api.patch(
      `${ENDPOINTS.permissions.users}/${pendingRoleUpdate.value.userId}/role`,
      { role: roleUpdateForm.value.role, is_active: roleUpdateForm.value.is_active, reason },
      { headers: { 'X-Step-Up-Token': stepUpToken } },
    )
    toast.success(t('backoffice.superAdmin.users.roleUpdateSuccess', { name: pendingRoleUpdate.value.full_name }))
    pendingRoleUpdate.value = null
    await loadUsers()
  } catch (e: any) {
    const code = e?.response?.data?.detail?.error_code
    if (code === 'STEP_UP_INVALID') {
      roleUpdateStepUpError.value = t('backoffice.stepUp.errorInvalidRestart')
    } else {
      toast.error(e?.response?.data?.detail?.message ?? t('backoffice.superAdmin.users.roleUpdateError'))
      pendingRoleUpdate.value = null
    }
  } finally {
    roleUpdateBusy.value = false
  }
}

// ══════════════════════════════════════════════════════════════════════
// TAB 2 — PERMISSIONS (نفس منطق PermissionsView المفصولة)
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
  loadingCatalog.value = true
  permError.value = ''
  try { catalog.value = (await api.get(ENDPOINTS.permissions.catalog)).data }
  catch { permError.value = t('backoffice.permissions.loadErrorCatalog') }
  finally { loadingCatalog.value = false }
}
async function loadUsersForPerms() {
  loadingPermUsers.value = true
  try { permUsers.value = (await api.get(ENDPOINTS.permissions.users, { params: { page: 1, size: 200 } })).data.items }
  catch { permError.value = t('backoffice.permissions.loadErrorUsers') }
  finally { loadingPermUsers.value = false }
}
async function selectPermUser(id: number) {
  selectedPermUserId.value = id
  loadingUserPerms.value = true
  try { explicitPerms.value = (await api.get(ENDPOINTS.permissions.list, { params: { user_id: id } })).data }
  catch { toast.error(t('backoffice.permissions.toastErrorLoadUserPerms')); explicitPerms.value = [] }
  finally { loadingUserPerms.value = false }
}
function requestPermState(entry: CatalogEntry, newState: 'granted' | 'denied' | 'default') {
  if (!selectedPermUserId.value) return
  permStepUpError.value = ''
  if (newState === 'default') {
    const ex = explicitRowFor(entry)
    if (!ex) return
    pendingPermStepUp.value = { kind: 'revert', entry, existing: ex }
  } else {
    pendingPermStepUp.value = { kind: newState === 'granted' ? 'grant' : 'deny', entry }
  }
}
async function onPermStepUpConfirmed({ stepUpToken, reason }: { stepUpToken: string; reason: string }) {
  const p = pendingPermStepUp.value
  if (!p || !selectedPermUserId.value) return
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
  const p = pendingPermStepUp.value
  if (!p || !selectedPermUserId.value) return {}
  if (p.kind === 'revert') return { permission_id: p.existing!.id }
  return { user_id: selectedPermUserId.value, resource: p.entry.resource, action: p.entry.action, allowed: p.kind === 'grant', branch_id: null }
})
const permStepUpDescription = computed(() => {
  const p = pendingPermStepUp.value
  if (!p || !selectedPermUser.value) return ''
  const label = catalogLabel(p.entry)
  const name = selectedPermUser.value.full_name
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
  settingsLoading.value = true
  settingsError.value = ''
  try {
    // global settings (branch_id=null) — super_admin فقط
    const res = await api.get(ENDPOINTS.settings.get, { params: {} })
    settings.value = res.data
  } catch {
    settingsError.value = t('backoffice.superAdmin.settings.loadError')
  } finally {
    settingsLoading.value = false
  }
}

function openSettingEdit(row: SettingRow) {
  pendingSettingEdit.value = { row, newValue: row.value }
  settingStepUpError.value = ''
}

async function onSettingStepUpConfirmed({ stepUpToken, reason }: { stepUpToken: string; reason: string }) {
  const p = pendingSettingEdit.value
  if (!p) return
  settingStepUpBusy.value = true
  try {
    await api.put(
      ENDPOINTS.settings.set(p.row.key),
      { value: p.newValue, reason },
      { headers: { 'X-Step-Up-Token': stepUpToken } },
    )
    toast.success(t('backoffice.superAdmin.settings.updateSuccess', { key: p.row.key }))
    pendingSettingEdit.value = null
    await loadSettings()
  } catch (e: any) {
    const code = e?.response?.data?.detail?.error_code
    if (code === 'STEP_UP_INVALID') settingStepUpError.value = t('backoffice.stepUp.errorInvalidRestart')
    else { toast.error(e?.response?.data?.detail?.message ?? t('backoffice.superAdmin.settings.updateError')); pendingSettingEdit.value = null }
  } finally {
    settingStepUpBusy.value = false
  }
}

const settingStepUpIntent = computed(() => {
  const p = pendingSettingEdit.value
  if (!p) return {}
  return { key: p.row.key, branch_id: p.row.branch_id, value: p.newValue }
})

// ══════════════════════════════════════════════════════════════════════
// TAB 4 — AUDIT LOGS
// ══════════════════════════════════════════════════════════════════════
interface AuditRow { id: number; user_id: number | null; action: string; entity_type: string; entity_id: number | null; new_data: string | null; old_data: string | null; ip_address: string | null; created_at: string }
const auditLogs = ref<AuditRow[]>([])
const auditTotal = ref(0)
const auditPage = ref(1)
const auditLoading = ref(false)
const auditError = ref('')
const auditActionFilter = ref('')
const auditEntityFilter = ref('')

async function loadAuditLogs() {
  auditLoading.value = true
  auditError.value = ''
  try {
    const params: Record<string, unknown> = { page: auditPage.value, size: 50 }
    if (auditActionFilter.value) params.action = auditActionFilter.value
    if (auditEntityFilter.value) params.entity_type = auditEntityFilter.value
    const res = await api.get('/api/v1/audit-logs', { params })
    auditLogs.value = res.data.items
    auditTotal.value = res.data.total
  } catch {
    auditError.value = t('backoffice.superAdmin.audit.loadError')
  } finally {
    auditLoading.value = false
  }
}

// ── Init ──────────────────────────────────────────────────────────────
onMounted(() => {
  tabsLoaded.value.add('users')
  loadUsers()
})
</script>

<template>
  <div class="space-y-5">
    <!-- Header -->
    <div class="flex items-start justify-between">
      <div>
        <h1 class="text-2xl font-black text-gray-800 dark:text-gray-200">
          {{ t('backoffice.superAdmin.title') }}
        </h1>
        <p class="text-sm text-gray-500 mt-1">{{ t('backoffice.superAdmin.subtitle') }}</p>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 border-b border-stone-200 dark:border-border">
      <button
        v-for="tab in (['users','permissions','settings','audit'] as Tab[])"
        :key="tab"
        @click="activateTab(tab)"
        :class="[
          'px-4 py-2.5 text-sm font-semibold rounded-t-lg transition-colors',
          activeTab === tab
            ? 'bg-white dark:bg-surface text-blue-600 border border-b-white border-stone-200 dark:border-border -mb-px'
            : 'text-gray-500 hover:text-gray-800 hover:bg-stone-50',
        ]"
      >{{ t(`backoffice.superAdmin.tabs.${tab}`) }}</button>
    </div>

    <!-- ═══ TAB: USERS ═══ -->
    <div v-show="activeTab === 'users'" class="space-y-4">
      <!-- Toolbar -->
      <div class="flex flex-wrap items-center gap-3">
        <AppInput v-model="usersSearch" :placeholder="t('backoffice.superAdmin.users.searchPlaceholder')" class="w-60" @keyup.enter="usersPage=1; loadUsers()" />
        <select v-model="usersRoleFilter" @change="usersPage=1; loadUsers()" class="border border-stone-200 rounded-lg px-3 py-2 text-sm dark:bg-surface dark:border-border">
          <option value="">{{ t('backoffice.superAdmin.users.allRoles') }}</option>
          <option v-for="r in STAFF_ROLES" :key="r" :value="r">{{ roleLabel(r) }}</option>
        </select>
        <select v-model="usersActiveFilter" @change="usersPage=1; loadUsers()" class="border border-stone-200 rounded-lg px-3 py-2 text-sm dark:bg-surface dark:border-border">
          <option value="">{{ t('backoffice.superAdmin.users.allStatus') }}</option>
          <option value="true">{{ t('backoffice.superAdmin.users.active') }}</option>
          <option value="false">{{ t('backoffice.superAdmin.users.inactive') }}</option>
        </select>
        <AppButton @click="showCreateUser = true" variant="primary" size="sm">
          + {{ t('backoffice.superAdmin.users.createBtn') }}
        </AppButton>
      </div>

      <!-- Create User Form -->
      <AppCard v-if="showCreateUser" :title="t('backoffice.superAdmin.users.createTitle')" padding="sm">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <AppInput v-model="newUser.email" :label="t('backoffice.superAdmin.users.email')" type="email" />
          <AppInput v-model="newUser.full_name" :label="t('backoffice.superAdmin.users.fullName')" />
          <AppInput v-model="newUser.phone" :label="t('backoffice.superAdmin.users.phone')" />
          <div>
            <label class="block text-xs font-semibold text-gray-500 mb-1">{{ t('backoffice.superAdmin.users.role') }}</label>
            <select v-model="newUser.role" class="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm dark:bg-surface dark:border-border">
              <option v-for="r in STAFF_ROLES" :key="r" :value="r">{{ roleLabel(r) }}</option>
            </select>
          </div>
          <AppInput v-model="newUser.password" :label="t('backoffice.superAdmin.users.tempPassword')" type="password" />
        </div>
        <p v-if="createUserError" class="text-red-600 text-sm mt-2">⚠️ {{ createUserError }}</p>
        <p class="text-xs text-amber-600 mt-2">⚠️ {{ t('backoffice.superAdmin.users.mustChangeNote') }}</p>
        <div class="flex gap-2 mt-3">
          <AppButton @click="createUser" :loading="creatingUser" variant="primary" size="sm">{{ t('backoffice.superAdmin.users.createSubmit') }}</AppButton>
          <AppButton @click="showCreateUser=false; createUserError=''" variant="ghost" size="sm">{{ t('backoffice.superAdmin.cancel') }}</AppButton>
        </div>
      </AppCard>

      <!-- Users Table -->
      <AppCard padding="none">
        <div v-if="usersLoading" class="p-10 flex justify-center"><AppSpinner /></div>
        <div v-else-if="usersError" class="p-6 text-red-600 text-sm">⚠️ {{ usersError }}
          <button @click="loadUsers" class="ms-2 underline font-semibold">{{ t('backoffice.superAdmin.retry') }}</button>
        </div>
        <div v-else-if="users.length === 0" class="p-10 text-center text-gray-400">
          <div class="text-3xl mb-2">👤</div>{{ t('backoffice.superAdmin.users.empty') }}
        </div>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr class="text-xs font-bold text-gray-500 uppercase tracking-wide">
                <th class="px-4 py-3 text-start">#</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.superAdmin.users.colName') }}</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.superAdmin.users.colEmail') }}</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.superAdmin.users.colRole') }}</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.superAdmin.users.colStatus') }}</th>
                <th class="px-4 py-3 text-start">2FA</th>
                <th class="px-4 py-3 text-start">{{ t('backoffice.superAdmin.users.colActions') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-stone-100 dark:divide-border">
              <tr v-for="u in users" :key="u.id" class="hover:bg-stone-50 dark:hover:bg-gray-800/40 transition-colors">
                <td class="px-4 py-3 text-gray-400 text-xs">{{ u.id }}</td>
                <td class="px-4 py-3 font-medium text-gray-800 dark:text-gray-200">{{ u.full_name }}</td>
                <td class="px-4 py-3 text-gray-500 font-mono text-xs">{{ u.email }}</td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="u.role === 'super_admin' ? 'warning' : 'info'">{{ roleLabel(u.role) }}</AppBadge>
                </td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="u.is_active ? 'success' : 'neutral'">
                    {{ u.is_active ? t('backoffice.superAdmin.users.active') : t('backoffice.superAdmin.users.inactive') }}
                  </AppBadge>
                </td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="u.two_factor_enabled ? 'success' : 'neutral'">
                    {{ u.two_factor_enabled ? '✓' : '✗' }}
                  </AppBadge>
                </td>
                <td class="px-4 py-3">
                  <button
                    v-if="u.role !== 'super_admin'"
                    @click="openRoleUpdate(u)"
                    class="text-xs text-blue-600 hover:text-blue-800 font-semibold"
                  >{{ t('backoffice.superAdmin.users.editBtn') }}</button>
                </td>
              </tr>
            </tbody>
          </table>
          <!-- Pagination -->
          <div class="px-4 py-3 flex items-center justify-between text-xs text-gray-500 border-t border-stone-100">
            <span>{{ t('backoffice.superAdmin.users.total', { n: usersTotal }) }}</span>
            <div class="flex gap-2">
              <button :disabled="usersPage <= 1" @click="usersPage--; loadUsers()" class="px-2 py-1 border rounded disabled:opacity-40">‹</button>
              <span>{{ usersPage }}</span>
              <button :disabled="usersPage * 20 >= usersTotal" @click="usersPage++; loadUsers()" class="px-2 py-1 border rounded disabled:opacity-40">›</button>
            </div>
          </div>
        </div>
      </AppCard>

      <!-- Role Update Step-Up -->
      <StepUpConfirmModal
        v-if="pendingRoleUpdate"
        purpose="user_role_update"
        :intent="{ user_id: pendingRoleUpdate.userId, role: roleUpdateForm.role, is_active: roleUpdateForm.is_active }"
        :description="t('backoffice.superAdmin.users.roleUpdateDesc', { name: pendingRoleUpdate.full_name })"
        :loading="roleUpdateBusy"
        :error-message="roleUpdateStepUpError"
        @confirmed="onRoleUpdateStepUpConfirmed"
        @cancel="pendingRoleUpdate = null; roleUpdateStepUpError = ''"
      >
        <template #extra>
          <div class="space-y-2 mb-3">
            <div>
              <label class="block text-xs font-semibold text-gray-500 mb-1">{{ t('backoffice.superAdmin.users.role') }}</label>
              <select v-model="roleUpdateForm.role" class="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm">
                <option v-for="r in STAFF_ROLES" :key="r" :value="r">{{ roleLabel(r) }}</option>
              </select>
            </div>
            <label class="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" v-model="roleUpdateForm.is_active" class="rounded" />
              {{ t('backoffice.superAdmin.users.isActive') }}
            </label>
          </div>
        </template>
      </StepUpConfirmModal>
    </div>

    <!-- ═══ TAB: PERMISSIONS ═══ -->
    <div v-show="activeTab === 'permissions'" class="space-y-4">
      <div v-if="permError" class="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">⚠️ {{ permError }}</div>
      <div class="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-5">
        <!-- Employee List -->
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
              :class="['px-4 py-3 cursor-pointer transition-colors', selectedPermUserId === u.id ? 'bg-blue-50' : 'hover:bg-stone-50 dark:hover:bg-gray-800/40']">
              <div class="font-medium text-gray-800 dark:text-gray-200 text-sm">{{ u.full_name }}</div>
              <div class="flex items-center gap-2 mt-1">
                <span class="text-xs text-gray-400">{{ u.email }}</span>
                <AppBadge size="sm" variant="info">{{ roleLabel(u.role) }}</AppBadge>
              </div>
            </li>
          </ul>
        </AppCard>

        <!-- Permission Matrix -->
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
                      <button @click="requestPermState(entry,'granted')" :class="['px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors', stateFor(entry)==='granted' ? 'bg-green-600 text-white' : 'bg-white text-green-700 border border-green-200 hover:bg-green-50']">{{ t('backoffice.permissions.grant') }}</button>
                      <button @click="requestPermState(entry,'default')" :class="['px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors', stateFor(entry)==='default' ? 'bg-gray-600 text-white' : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50']">{{ t('backoffice.permissions.default') }}</button>
                      <button @click="requestPermState(entry,'denied')" :class="['px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors', stateFor(entry)==='denied' ? 'bg-red-600 text-white' : 'bg-white text-red-700 border border-red-200 hover:bg-red-50']">{{ t('backoffice.permissions.deny') }}</button>
                    </template>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </AppCard>
      </div>
      <StepUpConfirmModal v-if="pendingPermStepUp" :purpose="permStepUpPurpose" :intent="permStepUpIntent" :description="permStepUpDescription" :loading="permStepUpBusy" :error-message="permStepUpError" @confirmed="onPermStepUpConfirmed" @cancel="pendingPermStepUp=null; permStepUpError=''" />
    </div>

    <!-- ═══ TAB: SETTINGS ═══ -->
    <div v-show="activeTab === 'settings'" class="space-y-4">
      <p class="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
        ⚠️ {{ t('backoffice.superAdmin.settings.globalNote') }}
      </p>
      <div v-if="settingsLoading" class="p-10 flex justify-center"><AppSpinner /></div>
      <div v-else-if="settingsError" class="text-red-600 text-sm">⚠️ {{ settingsError }}
        <button @click="loadSettings" class="ms-2 underline font-semibold">{{ t('backoffice.superAdmin.retry') }}</button>
      </div>
      <div v-else-if="settings.length === 0" class="p-10 text-center text-gray-400">
        <div class="text-3xl mb-2">⚙️</div>{{ t('backoffice.superAdmin.settings.empty') }}
      </div>
      <AppCard v-else padding="none">
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

      <!-- Setting Edit Step-Up -->
      <div v-if="pendingSettingEdit" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
        <AppCard :title="t('backoffice.superAdmin.settings.editTitle', { key: pendingSettingEdit.row.key })" padding="sm" class="w-full max-w-md">
          <AppInput v-model="pendingSettingEdit.newValue" :label="t('backoffice.superAdmin.settings.newValue')" class="mb-4" />
          <StepUpConfirmModal
            purpose="setting_upsert"
            :intent="settingStepUpIntent"
            :description="t('backoffice.superAdmin.settings.stepUpDesc', { key: pendingSettingEdit.row.key })"
            :loading="settingStepUpBusy"
            :error-message="settingStepUpError"
            @confirmed="onSettingStepUpConfirmed"
            @cancel="pendingSettingEdit = null; settingStepUpError = ''"
          />
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
      <div v-else-if="auditLogs.length === 0" class="p-10 text-center text-gray-400">
        <div class="text-3xl mb-2">📋</div>{{ t('backoffice.superAdmin.audit.empty') }}
      </div>
      <AppCard v-else padding="none">
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
                <td class="px-4 py-3">
                  <span class="font-mono text-xs bg-stone-100 dark:bg-gray-700 px-2 py-0.5 rounded">{{ log.action }}</span>
                </td>
                <td class="px-4 py-3 text-xs text-gray-600 dark:text-gray-300">
                  {{ log.entity_type }}<span v-if="log.entity_id" class="text-gray-400"> #{{ log.entity_id }}</span>
                </td>
                <td class="px-4 py-3 text-xs text-gray-500">{{ log.user_id ?? '—' }}</td>
                <td class="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">{{ new Date(log.created_at).toLocaleString(locale) }}</td>
                <td class="px-4 py-3 text-xs text-gray-400 max-w-xs truncate" :title="log.new_data ?? ''">
                  {{ log.new_data ? JSON.parse(log.new_data)?.reason ?? log.new_data.slice(0, 60) : '—' }}
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
    </div>

  </div>
</template>
