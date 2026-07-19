<script setup lang="ts">
// Gate 3B — Account/Profile reference screen migrated to the shared i18n
// runtime + @resort-os/ui primitives. Direction is inherited from <html dir>
// (central staff locale controller); no forced dir, no hard-coded ar-EG.
import { ref, onMounted } from 'vue'
import { api } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppSpinner, AppInput, AppButton, useToast } from '@resort-os/ui'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const { formatDate } = useStaffFormat()
const toast = useToast()

interface Profile {
  id: number; employee_code: string; full_name: string; email?: string
  phone?: string; position: string; department?: string; hire_date: string
}

const profile = ref<Profile | null>(null)
const loading = ref(false)
const profileError = ref('')
const pwForm = ref({ current_password: '', new_password: '', confirm_password: '' })
const pwMsg = ref('')
const pwError = ref('')
const pwLoading = ref(false)

async function fetchProfile() {
  loading.value = true
  profileError.value = ''
  try {
    const { data } = await api.get('/api/v1/hr/me/profile')
    profile.value = data
  } catch (e: any) {
    profileError.value = e?.response?.data?.detail ?? t('backoffice.profile.loadFailed')
    toast.error(profileError.value)
  } finally { loading.value = false }
}

async function changePassword() {
  if (!pwForm.value.current_password || !pwForm.value.new_password) {
    pwError.value = t('backoffice.profile.fillAllFields'); return
  }
  if (pwForm.value.new_password !== pwForm.value.confirm_password) {
    pwError.value = t('backoffice.profile.passwordsMismatch'); return
  }
  if (pwForm.value.new_password.length < 8) {
    pwError.value = t('backoffice.profile.passwordTooShort'); return
  }
  pwLoading.value = true; pwError.value = ''
  try {
    await api.post('/api/v1/auth/change-password', {
      current_password: pwForm.value.current_password,
      new_password: pwForm.value.new_password,
    })
    pwMsg.value = t('backoffice.profile.passwordChanged')
    pwForm.value = { current_password: '', new_password: '', confirm_password: '' }
    // Credential changes intentionally revoke every access/refresh session.
    // Reloading clears the in-memory access token and starts a clean login
    // instead of leaving the user on a screen with a revoked credential.
    setTimeout(() => window.location.replace('/login'), 900)
  } catch (e: any) {
    pwError.value = e?.response?.data?.detail ?? t('backoffice.profile.currentPasswordWrong')
  } finally { pwLoading.value = false }
}

onMounted(fetchProfile)
</script>

<template>
  <div class="space-y-4">
    <h2 class="font-bold text-gray-900 dark:text-gray-100 text-lg">{{ t('backoffice.profile.title') }}</h2>

    <div v-if="loading" class="flex flex-col items-center justify-center py-12 text-gray-400 dark:text-gray-500 gap-3">
      <AppSpinner size="lg" />
      <p>{{ t('backoffice.profile.loading') }}</p>
    </div>

    <div v-else-if="profileError && !profile" class="text-center py-12 text-red-500 bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border">
      <div class="text-4xl mb-3" aria-hidden="true">⚠️</div>
      <p class="font-medium">{{ profileError }}</p>
    </div>

    <template v-else-if="profile">
      <!-- Profile card -->
      <div class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border p-6 shadow-sm">
        <div class="flex items-center gap-4 mb-5">
          <div class="w-16 h-16 bg-blue-100 rounded-2xl flex items-center justify-center text-2xl font-black text-blue-700 flex-shrink-0">
            {{ profile.full_name.charAt(0) }}
          </div>
          <div>
            <div class="font-bold text-xl text-gray-900 dark:text-gray-100">{{ profile.full_name }}</div>
            <div class="text-gray-500 dark:text-gray-500 text-sm">
              {{ profile.position }}
              <span v-if="profile.department"> — {{ profile.department }}</span>
            </div>
            <div class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{{ profile.employee_code }}</div>
          </div>
        </div>

        <div class="space-y-3 border-t border-stone-100 dark:border-border/50 pt-4">
          <div v-if="profile.email" class="flex items-center justify-between text-sm">
            <span class="text-gray-500 dark:text-gray-500 flex items-center gap-1.5">📧 {{ t('backoffice.profile.email') }}</span>
            <span class="font-medium text-gray-900 dark:text-gray-100">{{ profile.email }}</span>
          </div>
          <div v-if="profile.phone" class="flex items-center justify-between text-sm">
            <span class="text-gray-500 dark:text-gray-500 flex items-center gap-1.5">📞 {{ t('backoffice.profile.phone') }}</span>
            <span class="font-medium text-gray-900 dark:text-gray-100" dir="ltr">{{ profile.phone }}</span>
          </div>
          <div v-if="profile.hire_date" class="flex items-center justify-between text-sm">
            <span class="text-gray-500 dark:text-gray-500 flex items-center gap-1.5">📅 {{ t('backoffice.profile.hireDate') }}</span>
            <span class="font-medium text-gray-900 dark:text-gray-100">
              {{ formatDate(profile.hire_date, { year: 'numeric', month: 'long', day: 'numeric' }) }}
            </span>
          </div>
        </div>
      </div>

      <!-- Change password -->
      <div class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border p-6 shadow-sm">
        <h3 class="font-bold text-gray-900 dark:text-gray-100 mb-4">{{ t('backoffice.profile.changePassword') }}</h3>
        <form class="space-y-3" @submit.prevent="changePassword">
          <AppInput
            v-model="pwForm.current_password"
            type="password"
            :label="t('backoffice.profile.currentPassword')"
            placeholder="••••••••"
            autocomplete="current-password"
          />
          <AppInput
            v-model="pwForm.new_password"
            type="password"
            :label="t('backoffice.profile.newPassword')"
            :placeholder="t('backoffice.profile.newPasswordHint')"
            autocomplete="new-password"
          />
          <AppInput
            v-model="pwForm.confirm_password"
            type="password"
            :label="t('backoffice.profile.confirmPassword')"
            placeholder="••••••••"
            autocomplete="new-password"
          />
          <div v-if="pwMsg" role="status" class="bg-green-100 text-green-700 px-3 py-2 rounded-lg text-sm font-medium">{{ pwMsg }}</div>
          <div v-if="pwError" role="alert" class="bg-red-50 text-red-600 px-3 py-2 rounded-lg text-sm">{{ pwError }}</div>
          <AppButton type="submit" :loading="pwLoading" variant="primary" class="w-full">
            {{ pwLoading ? t('backoffice.profile.saving') : t('backoffice.profile.savePassword') }}
          </AppButton>
        </form>
      </div>
    </template>
  </div>
</template>
