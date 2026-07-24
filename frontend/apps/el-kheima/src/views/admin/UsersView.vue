<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'
import {
  AppBadge, AppCard, AppInput, AppModal, AppSelect, AppSpinner, useToast,
} from '@resort-os/ui'
import StepUpConfirmModal from '../../components/StepUpConfirmModal.vue'

interface UserRow {
  id: number
  email: string
  full_name: string
  phone: string | null
  role: string
  is_active: boolean
  two_factor_enabled: boolean
  must_change_password: boolean
  two_factor_bootstrap_required: boolean
  preferred_language: 'ar' | 'en'
}

interface BootstrapResult {
  user: UserRow
  temporary_password: string
  enrollment_token: string
  enrollment_expires_at: string
}

interface EmployeeOption {
  id: number
  full_name: string
  employee_code: string
  user_id: number | null
}

type PendingAction =
  | { kind: 'create' }
  | { kind: 'status'; user: UserRow; nextActive: boolean }

const { t } = useI18n()
const toast = useToast()
const auth = useAuthStore()
const users = ref<UserRow[]>([])
const employees = ref<EmployeeOption[]>([])
const loading = ref(true)
const loadError = ref('')
const search = ref('')
const form = ref({
  full_name: '', email: '', phone: '', employee_id: '', role: 'employee', preferred_language: 'ar',
})
const formError = ref('')
const pending = ref<PendingAction | null>(null)
const stepUpBusy = ref(false)
const stepUpError = ref('')
const bootstrap = ref<BootstrapResult | null>(null)

const roleValues = [
  'admin', 'accountant', 'hr_manager', 'manager', 'supervisor', 'receptionist',
  'cashier', 'waiter', 'chef', 'kitchen', 'employee',
]
const roleOptions = computed(() => roleValues.map((role) => ({
  value: role,
  label: t(`backoffice.permissions.roles.${role}`, role),
})))
const languageOptions = computed(() => [
  { value: 'ar', label: t('backoffice.accounts.arabic') },
  { value: 'en', label: t('backoffice.accounts.english') },
])
const employeeOptions = computed(() => employees.value
  .filter((employee) => employee.user_id === null)
  .map((employee) => ({
    value: String(employee.id),
    label: `${employee.full_name} (${employee.employee_code})`,
  })))
const filteredUsers = computed(() => {
  const query = search.value.trim().toLowerCase()
  if (!query) return users.value
  return users.value.filter((user) => (
    user.full_name.toLowerCase().includes(query)
    || user.email.toLowerCase().includes(query)
    || user.role.toLowerCase().includes(query)
  ))
})

async function loadUsers() {
  loading.value = true
  loadError.value = ''
  try {
    const response = await api.get(ENDPOINTS.users.list, { params: { page: 1, size: 100 } })
    users.value = response.data.items
  } catch {
    loadError.value = t('backoffice.accounts.loadFailed')
  } finally {
    loading.value = false
  }
}

async function loadEmployees() {
  try {
    const response = await api.get(ENDPOINTS.hr.employees, { params: { branch_id: auth.branchId, page: 1, size: 100 } })
    employees.value = response.data.items ?? []
  } catch {
    // Linking is optional; account provisioning remains available even when
    // there are no HR records or the branch has not been configured yet.
    employees.value = []
  }
}

function requestCreate() {
  formError.value = ''
  if (form.value.full_name.trim().length < 3 || !form.value.email.includes('@')) {
    formError.value = t('backoffice.accounts.requiredFields')
    return
  }
  pending.value = { kind: 'create' }
}

function requestStatus(user: UserRow) {
  pending.value = { kind: 'status', user, nextActive: !user.is_active }
  stepUpError.value = ''
}

const stepUpPurpose = computed(() => (
  pending.value?.kind === 'status' ? 'user_role_update' as const : 'user_provision' as const
))
const stepUpIntent = computed<Record<string, unknown>>(() => {
  if (pending.value?.kind === 'status') {
    return { user_id: pending.value.user.id, role: null, is_active: pending.value.nextActive }
  }
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
  if (pending.value?.kind === 'status') {
    return t(
      pending.value.nextActive
        ? 'backoffice.accounts.confirmActivate'
        : 'backoffice.accounts.confirmDeactivate',
      { name: pending.value.user.full_name },
    )
  }
  return t('backoffice.accounts.confirmCreate', { name: form.value.full_name.trim() })
})

async function onStepUpConfirmed({ stepUpToken, reason }: { stepUpToken: string; reason: string }) {
  const action = pending.value
  if (!action) return
  stepUpBusy.value = true
  stepUpError.value = ''
  try {
    if (action.kind === 'create') {
      const response = await api.post(ENDPOINTS.users.list, {
        email: form.value.email.trim().toLowerCase(),
        full_name: form.value.full_name.trim(),
        phone: form.value.phone.trim() || null,
        employee_id: form.value.employee_id ? Number(form.value.employee_id) : null,
        role: form.value.role,
        preferred_language: form.value.preferred_language,
        reason,
      }, { headers: { 'X-Step-Up-Token': stepUpToken } })
      bootstrap.value = response.data
      users.value = [...users.value, response.data.user]
      form.value = { full_name: '', email: '', phone: '', employee_id: '', role: 'employee', preferred_language: 'ar' }
      toast.success(t('backoffice.accounts.created'))
    } else {
      const response = await api.patch(ENDPOINTS.users.role(action.user.id), {
        role: null,
        is_active: action.nextActive,
        reason,
      }, { headers: { 'X-Step-Up-Token': stepUpToken } })
      users.value = users.value.map((row) => row.id === response.data.id ? response.data : row)
      toast.success(t(action.nextActive ? 'backoffice.accounts.activated' : 'backoffice.accounts.deactivated'))
    }
    pending.value = null
  } catch (error: any) {
    const code = error?.response?.data?.detail?.error_code
    if (code === 'STEP_UP_INVALID') {
      stepUpError.value = t('backoffice.stepUp.errorInvalidRestart')
    } else {
      const detail = error?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : detail?.message ?? t('backoffice.accounts.saveFailed'))
      pending.value = null
    }
  } finally {
    stepUpBusy.value = false
  }
}

async function copyBootstrap() {
  if (!bootstrap.value) return
  const message = [
    `${t('backoffice.accounts.email')}: ${bootstrap.value.user.email}`,
    `${t('backoffice.accounts.temporaryPassword')}: ${bootstrap.value.temporary_password}`,
    `${t('backoffice.accounts.enrollmentToken')}: ${bootstrap.value.enrollment_token}`,
    `${t('backoffice.accounts.loginUrl')}: ${window.location.origin}/login`,
  ].join('\n')
  await navigator.clipboard.writeText(message)
  toast.success(t('backoffice.accounts.copied'))
}

function closeBootstrap() {
  bootstrap.value = null
}

onMounted(() => {
  loadUsers()
  loadEmployees()
})
</script>

<template>
  <div class="space-y-5">
    <div>
      <h1 class="text-2xl font-black text-gray-800 dark:text-gray-100">{{ t('backoffice.accounts.title') }}</h1>
      <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ t('backoffice.accounts.subtitle') }}</p>
    </div>

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

    <AppCard :title="t('backoffice.accounts.listTitle')" padding="none">
      <div class="border-b border-stone-100 p-4 dark:border-border">
        <AppInput v-model="search" type="search" :placeholder="t('backoffice.accounts.search')" />
      </div>
      <div v-if="loading" class="flex justify-center p-10"><AppSpinner /></div>
      <div v-else-if="loadError" class="p-6 text-center text-danger">{{ loadError }}</div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-stone-50 text-gray-500 dark:bg-surface-2 dark:text-gray-400">
            <tr>
              <th class="px-4 py-3 text-start">{{ t('backoffice.accounts.nameAndEmail') }}</th>
              <th class="px-4 py-3 text-start">{{ t('backoffice.accounts.role') }}</th>
              <th class="px-4 py-3 text-start">{{ t('backoffice.accounts.security') }}</th>
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
              <td class="px-4 py-3">
                <AppBadge :variant="row.is_active ? 'success' : 'danger'">
                  {{ t(row.is_active ? 'backoffice.accounts.active' : 'backoffice.accounts.inactive') }}
                </AppBadge>
              </td>
              <td class="px-4 py-3">
                <button class="font-semibold text-primary-700 hover:underline disabled:opacity-50 dark:text-primary-400" :disabled="stepUpBusy" @click="requestStatus(row)">
                  {{ t(row.is_active ? 'backoffice.accounts.deactivate' : 'backoffice.accounts.activate') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>

    <StepUpConfirmModal
      v-if="pending"
      :purpose="stepUpPurpose"
      :intent="stepUpIntent"
      :description="stepUpDescription"
      :loading="stepUpBusy"
      :error-message="stepUpError"
      @confirmed="onStepUpConfirmed"
      @cancel="pending = null"
    />

    <AppModal v-if="bootstrap" :open="true" :title="t('backoffice.accounts.credentialsTitle')" size="md" @close="closeBootstrap">
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
          <button class="flex-1 rounded-lg border border-stone-200 px-4 py-2 font-semibold dark:border-border" @click="closeBootstrap">{{ t('backoffice.accounts.close') }}</button>
          <button class="flex-1 rounded-lg bg-primary-700 px-4 py-2 font-bold text-white" @click="copyBootstrap">{{ t('backoffice.accounts.copy') }}</button>
        </div>
      </template>
    </AppModal>
  </div>
</template>
