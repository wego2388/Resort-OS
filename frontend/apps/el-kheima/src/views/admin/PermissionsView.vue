<script setup lang="ts">
// PermissionsView — إدارة الصلاحيات التفصيلية (super_admin فقط).
//
// يعرض كتالوج الصلاحيات (GET /permissions/catalog) كمصفوفة × قائمة الموظفين
// (GET /users)، ولكل خلية (موظف × صلاحية) 3 حالات: منح صريح / افتراضي (حسب
// الدور)/ منع صريح. اختيار "منح" أو "منع" بيعمل POST /permissions، والرجوع
// لـ"افتراضي" بيعمل DELETE /permissions/{id} على أي استثناء موجود.
//
// Gate 2B3A: الثلاثة أفعال دي بقوا محتاجين step-up token صالح
// (X-Step-Up-Token) + reason إجباري — راجع StepUpConfirmModal.vue وdocs/
// audits/gate-2b3a-step-up-control-plane.md. حساب super_admin بقى مستبعد
// من قائمة الاستهداف هنا على مستوى الفرونت إند نفسه (مش بس اعتمادًا على
// رفض الباك إند SUPER_ADMIN_PERMISSION_OVERRIDE_FORBIDDEN) — Decision 0003
// invariant #2.
import { ref, computed, onMounted } from 'vue'
import { api, ENDPOINTS } from '@resort-os/core'
import { AppCard, AppBadge, AppSpinner, AppInput, useToast } from '@resort-os/ui'
import { useI18n } from 'vue-i18n'
import StepUpConfirmModal from '../../components/StepUpConfirmModal.vue'

const { t, locale } = useI18n()

interface CatalogEntry {
  resource: string
  action: string
  label_ar: string
  label_en: string
  module: string
  min_role_level: number
  endpoint: string
}

// مراجعة Codex المستقلة (2026-07-18): كانت الشاشة بتعرض label_ar حتى في
// الوضع الإنجليزي (الكتالوج معندوش label_en أصلاً وقتها) — بقى الباك إند
// يوفّر الاتنين، والشاشة تختار حسب اللغة الحالية.
function catalogLabel(entry: CatalogEntry): string {
  return locale.value === 'ar' ? entry.label_ar : entry.label_en
}
interface UserRow {
  id: number
  email: string
  full_name: string
  role: string
  is_active: boolean
}
interface ExplicitPermission {
  id: number
  user_id: number
  resource: string
  action: string
  allowed: boolean
  branch_id: number | null
}

const toast = useToast()

const catalog = ref<CatalogEntry[]>([])
const users = ref<UserRow[]>([])
const search = ref('')
const selectedUserId = ref<number | null>(null)
const explicitPerms = ref<ExplicitPermission[]>([])

const loadingCatalog = ref(true)
const loadingUsers = ref(true)
const loadingUserPerms = ref(false)
const loadError = ref('')
const needs2FA  = ref(false)

function roleLabel(role: string): string {
  return t(`backoffice.permissions.roles.${role}`, role)
}

// Decision 0003 invariant #2: مفيش override صريح جديد يقدر يستهدف
// super_admin (الباك إند بيرفضه دايمًا بـ409) — هنا بنستبعده من قائمة
// الاستهداف نفسها بدل ما نسيب المستخدم يحاول ويشوف رسالة رفض.
const targetableUsers = computed(() => users.value.filter((u) => u.role !== 'super_admin'))

const filteredUsers = computed(() => {
  const q = search.value.trim().toLowerCase()
  const pool = targetableUsers.value
  if (!q) return pool
  return pool.filter(
    (u) => u.full_name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q),
  )
})

const selectedUser = computed(() => users.value.find((u) => u.id === selectedUserId.value) ?? null)

const catalogByModule = computed(() => {
  const groups: Record<string, CatalogEntry[]> = {}
  for (const entry of catalog.value) {
    ;(groups[entry.module] ??= []).push(entry)
  }
  return groups
})

function moduleLabel(m: string): string {
  return t(`backoffice.permissions.modules.${m}`, m)
}

function stateFor(entry: CatalogEntry): 'granted' | 'denied' | 'default' {
  const explicit = explicitPerms.value.find(
    (p) => p.resource === entry.resource && p.action === entry.action && p.branch_id === null,
  )
  if (!explicit) return 'default'
  return explicit.allowed ? 'granted' : 'denied'
}

function explicitRowFor(entry: CatalogEntry): ExplicitPermission | undefined {
  return explicitPerms.value.find(
    (p) => p.resource === entry.resource && p.action === entry.action && p.branch_id === null,
  )
}

async function loadCatalog() {
  loadingCatalog.value = true
  loadError.value = ''
  needs2FA.value = false
  try {
    const res = await api.get(ENDPOINTS.permissions.catalog)
    catalog.value = res.data
  } catch (e: any) {
    const code = e?.response?.data?.detail?.code ?? e?.response?.data?.code
    if (code === '2FA_REQUIRED') {
      needs2FA.value = true
    } else {
      loadError.value = t('backoffice.permissions.loadErrorCatalog')
    }
  } finally {
    loadingCatalog.value = false
  }
}

async function loadUsers() {
  loadingUsers.value = true
  loadError.value = ''
  try {
    const res = await api.get(ENDPOINTS.permissions.users, { params: { page: 1, size: 100 } })
    users.value = res.data.items
  } catch (e: any) {
    const code = e?.response?.data?.detail?.code ?? e?.response?.data?.code
    if (code !== '2FA_REQUIRED') {
      loadError.value = t('backoffice.permissions.loadErrorUsers')
    }
  } finally {
    loadingUsers.value = false
  }
}

async function selectUser(userId: number) {
  selectedUserId.value = userId
  loadingUserPerms.value = true
  try {
    const res = await api.get(ENDPOINTS.permissions.list, { params: { user_id: userId } })
    explicitPerms.value = res.data
  } catch {
    toast.error(t('backoffice.permissions.toastErrorLoadUserPerms'))
    explicitPerms.value = []
  } finally {
    loadingUserPerms.value = false
  }
}

// Gate 2B3A — step-up state للفعل الجاري (منح/منع/رجوع لافتراضي) دلوقتي
interface PendingStepUp {
  kind: 'grant' | 'deny' | 'revert'
  entry: CatalogEntry
  existing?: ExplicitPermission
}
const pendingStepUp = ref<PendingStepUp | null>(null)
const stepUpError = ref('')
const stepUpBusy = ref(false)
const savingKey = computed(() => (
  pendingStepUp.value ? `${pendingStepUp.value.entry.resource}:${pendingStepUp.value.entry.action}` : null
))

function requestState(entry: CatalogEntry, newState: 'granted' | 'denied' | 'default') {
  if (!selectedUserId.value) return
  stepUpError.value = ''
  if (newState === 'default') {
    const existing = explicitRowFor(entry)
    if (!existing) return
    pendingStepUp.value = { kind: 'revert', entry, existing }
  } else {
    pendingStepUp.value = { kind: newState === 'granted' ? 'grant' : 'deny', entry }
  }
}

async function onStepUpConfirmed({ stepUpToken, reason }: { stepUpToken: string; reason: string }) {
  const pending = pendingStepUp.value
  if (!pending || !selectedUserId.value) return
  stepUpBusy.value = true
  try {
    if (pending.kind === 'revert') {
      await api.delete(ENDPOINTS.permissions.permission(pending.existing!.id), {
        data: { reason },
        headers: { 'X-Step-Up-Token': stepUpToken },
      })
      explicitPerms.value = explicitPerms.value.filter((p) => p.id !== pending.existing!.id)
      toast.success(t('backoffice.permissions.toastReverted', { label: catalogLabel(pending.entry) }))
    } else {
      const res = await api.post(ENDPOINTS.permissions.list, {
        user_id: selectedUserId.value,
        resource: pending.entry.resource,
        action: pending.entry.action,
        allowed: pending.kind === 'grant',
        branch_id: null,
        reason,
      }, {
        headers: { 'X-Step-Up-Token': stepUpToken },
      })
      explicitPerms.value = [
        ...explicitPerms.value.filter((p) => !(p.resource === pending.entry.resource && p.action === pending.entry.action)),
        res.data,
      ]
      toast.success(
        pending.kind === 'grant'
          ? t('backoffice.permissions.toastGranted', { label: catalogLabel(pending.entry) })
          : t('backoffice.permissions.toastDenied', { label: catalogLabel(pending.entry) }),
      )
    }
    pendingStepUp.value = null
  } catch (e: any) {
    const code = e?.response?.data?.detail?.error_code
    if (code === 'STEP_UP_INVALID') {
      // Gate 2B3A: الإثبات اتستخدم/انتهى — تبدأ دورة إثبات جديدة، مفيش
      // إعادة إرسال تلقائي للطلب الفعلي.
      stepUpError.value = t('backoffice.stepUp.errorInvalidRestart')
    } else {
      toast.error(e?.response?.data?.detail?.message ?? t('backoffice.permissions.toastErrorSave'))
      pendingStepUp.value = null
    }
  } finally {
    stepUpBusy.value = false
  }
}

function cancelStepUp() {
  pendingStepUp.value = null
  stepUpError.value = ''
}

const stepUpPurpose = computed(() => {
  const pending = pendingStepUp.value
  if (!pending) return 'permission_override_upsert' as const
  return pending.kind === 'revert' ? 'permission_override_revoke' as const : 'permission_override_upsert' as const
})
const stepUpIntent = computed(() => {
  const pending = pendingStepUp.value
  if (!pending || !selectedUserId.value) return {}
  if (pending.kind === 'revert') {
    return { permission_id: pending.existing!.id }
  }
  return {
    user_id: selectedUserId.value, resource: pending.entry.resource, action: pending.entry.action,
    allowed: pending.kind === 'grant', branch_id: null,
  }
})
const stepUpDescription = computed(() => {
  const pending = pendingStepUp.value
  if (!pending || !selectedUser.value) return ''
  const label = catalogLabel(pending.entry)
  const name = selectedUser.value.full_name
  if (pending.kind === 'grant') return t('backoffice.permissions.reasonPromptGrant', { label, name })
  if (pending.kind === 'deny') return t('backoffice.permissions.reasonPromptDeny', { label, name })
  return t('backoffice.permissions.reasonPromptRevert', { label, name })
})

onMounted(() => {
  loadCatalog()
  loadUsers()
})
</script>

<template>
  <div class="space-y-5">
    <div>
      <h1 class="text-2xl font-black text-gray-800 dark:text-gray-200">{{ t('backoffice.permissions.title') }}</h1>
      <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ t('backoffice.permissions.subtitle') }}</p>
    </div>

    <div v-if="loadError" class="flex items-center justify-between rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
      <span>⚠️ {{ loadError }}</span>
      <button @click="loadCatalog(); loadUsers()" class="font-semibold underline hover:no-underline">{{ t('backoffice.permissions.retry') }}</button>
    </div>

    <!-- 2FA required banner -->
    <div v-if="needs2FA" class="rounded-xl border border-amber-300 bg-amber-50 p-5 text-center dark:border-amber-800 dark:bg-amber-950/40">
      <div class="text-3xl mb-2">🔐</div>
      <h2 class="mb-1 text-lg font-black text-amber-800 dark:text-amber-300">{{ t('backoffice.permissions.needs2FATitle') }}</h2>
      <p class="mb-3 text-sm text-amber-700 dark:text-amber-300">{{ t('backoffice.permissions.needs2FABody') }}</p>
      <p class="text-xs text-amber-600 dark:text-amber-400">{{ t('backoffice.permissions.needs2FAHint') }}</p>
      <router-link
        to="/settings"
        class="inline-block mt-3 px-5 py-2 bg-amber-600 text-white rounded-lg font-bold text-sm hover:bg-amber-700 transition-colors"
      >{{ t('backoffice.permissions.needs2FAGoToSettings') }}</router-link>
    </div>

    <div v-if="!needs2FA" class="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-5">
      <!-- قائمة الموظفين -->
      <AppCard :title="t('backoffice.permissions.employees')" padding="none">
        <div class="p-3 border-b border-stone-100 dark:border-border/50">
          <AppInput v-model="search" :placeholder="t('backoffice.permissions.searchPlaceholder')" />
        </div>
        <div v-if="loadingUsers" class="p-8 flex justify-center">
          <AppSpinner />
        </div>
        <div v-else-if="filteredUsers.length === 0" class="p-8 text-center text-gray-400 dark:text-gray-400 text-sm">
          <div class="text-3xl mb-2">🔍</div>
          {{ t('backoffice.permissions.noEmployees') }}
        </div>
        <ul v-else class="max-h-[65vh] overflow-y-auto divide-y divide-stone-100">
          <li
            v-for="u in filteredUsers"
            :key="u.id"
            @click="selectUser(u.id)"
            :class="[
              'px-4 py-3 cursor-pointer transition-colors',
              selectedUserId === u.id ? 'bg-blue-50' : 'hover:bg-stone-50 dark:bg-gray-800/60',
            ]"
          >
            <div class="font-medium text-gray-800 dark:text-gray-200 text-sm">{{ u.full_name }}</div>
            <div class="flex items-center gap-2 mt-1">
              <span class="text-xs text-gray-400 dark:text-gray-400">{{ u.email }}</span>
              <AppBadge size="sm" :variant="u.is_active ? 'info' : 'neutral'">
                {{ roleLabel(u.role) }}
              </AppBadge>
            </div>
          </li>
        </ul>
      </AppCard>

      <!-- مصفوفة الصلاحيات -->
      <AppCard :title="selectedUser ? t('backoffice.permissions.permissionsFor', { name: selectedUser.full_name }) : t('backoffice.permissions.selectEmployeeTitle')" padding="sm">
        <div v-if="!selectedUserId" class="p-10 text-center text-gray-400 dark:text-gray-400">
          <div class="text-4xl mb-3">👈</div>
          {{ t('backoffice.permissions.selectEmployeePrompt') }}
        </div>

        <div v-else-if="loadingCatalog || loadingUserPerms" class="p-10 flex justify-center">
          <AppSpinner size="lg" />
        </div>

        <div v-else class="space-y-5">
          <div v-for="(entries, module) in catalogByModule" :key="module">
            <div class="text-xs font-bold text-gray-400 dark:text-gray-400 uppercase tracking-wide mb-2 px-1">
              {{ moduleLabel(module) }}
            </div>
            <div class="space-y-1.5">
              <div
                v-for="entry in entries"
                :key="`${entry.resource}:${entry.action}`"
                class="flex items-center justify-between bg-stone-50 dark:bg-gray-800/60 rounded-xl px-4 py-3"
              >
                <div>
                  <div class="text-sm font-medium text-gray-800 dark:text-gray-200">{{ catalogLabel(entry) }}</div>
                  <div class="text-xs text-gray-400 dark:text-gray-400 font-mono mt-0.5">{{ entry.endpoint }}</div>
                </div>

                <div class="flex items-center gap-1.5 flex-shrink-0">
                  <AppSpinner v-if="savingKey === `${entry.resource}:${entry.action}`" size="sm" />
                  <template v-else>
                    <button
                      @click="requestState(entry, 'granted')"
                      :class="[
                        'px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors',
                        stateFor(entry) === 'granted'
                          ? 'bg-green-600 text-white'
                          : 'border border-green-200 bg-white text-green-700 hover:bg-green-50 dark:border-green-800 dark:bg-surface dark:text-green-300 dark:hover:bg-green-950/40',
                      ]"
                    >{{ t('backoffice.permissions.grant') }}</button>
                    <button
                      @click="requestState(entry, 'default')"
                      :class="[
                        'px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors',
                        stateFor(entry) === 'default'
                          ? 'bg-gray-600 text-white'
                          : 'border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:bg-surface dark:text-gray-300 dark:hover:bg-gray-800',
                      ]"
                    >{{ t('backoffice.permissions.default') }}</button>
                    <button
                      @click="requestState(entry, 'denied')"
                      :class="[
                        'px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors',
                        stateFor(entry) === 'denied'
                          ? 'bg-red-600 text-white'
                          : 'border border-red-200 bg-white text-red-700 hover:bg-red-50 dark:border-red-800 dark:bg-surface dark:text-red-300 dark:hover:bg-red-950/40',
                      ]"
                    >{{ t('backoffice.permissions.deny') }}</button>
                  </template>
                </div>
              </div>
            </div>
          </div>
        </div>
      </AppCard>
    </div>

    <StepUpConfirmModal
      v-if="pendingStepUp"
      :purpose="stepUpPurpose"
      :intent="stepUpIntent"
      :description="stepUpDescription"
      :loading="stepUpBusy"
      :error-message="stepUpError"
      @confirmed="onStepUpConfirmed"
      @cancel="cancelStepUp"
    />
  </div>
</template>
