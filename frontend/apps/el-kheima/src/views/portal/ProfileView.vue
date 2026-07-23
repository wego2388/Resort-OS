<script setup lang="ts">
// Gate 3B — Account/Profile reference screen migrated to the shared i18n
// runtime + @resort-os/ui primitives. Direction is inherited from <html dir>
// (central staff locale controller); no forced dir, no hard-coded ar-EG.
import { ref, onMounted } from 'vue'
import { api, ENDPOINTS } from '@resort-os/core'
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

interface PinStatus {
  user_id: number; has_pin: boolean; failed_attempts: number; is_locked: boolean
}

const profile = ref<Profile | null>(null)
const loading = ref(false)
const profileError = ref('')
const pwForm = ref({ current_password: '', new_password: '', confirm_password: '' })
const pwMsg = ref('')
const pwError = ref('')
const pwLoading = ref(false)

// ── PIN state ──────────────────────────────────────────────────────────
const pinStatus = ref<PinStatus | null>(null)
const pinLoading = ref(false)
const pinValue = ref('')
const pinMsg = ref('')
const pinError = ref('')
const pinSaving = ref(false)

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

async function fetchPinStatus() {
  pinLoading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.core.pinMe)
    pinStatus.value = data
  } catch {
    // 404 = لا PIN مضبوط بعد — حالة طبيعية
    pinStatus.value = { user_id: 0, has_pin: false, failed_attempts: 0, is_locked: false }
  } finally { pinLoading.value = false }
}

async function savePin() {
  pinMsg.value = ''
  pinError.value = ''
  if (!/^\d{4,6}$/.test(pinValue.value)) {
    pinError.value = t('backoffice.profile.pin.validationError')
    return
  }
  pinSaving.value = true
  try {
    const { data } = await api.post(ENDPOINTS.core.pinMe, { pin: pinValue.value })
    pinStatus.value = data
    pinMsg.value = t('backoffice.profile.pin.success')
    pinValue.value = ''
  } catch (e: any) {
    pinError.value = e?.response?.data?.detail ?? t('backoffice.profile.pin.saveError')
  } finally { pinSaving.value = false }
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

onMounted(() => { fetchProfile(); fetchPinStatus() })
</script>

<template>
  <div class="space-y-4">
    <h2 class="font-bold text-gray-900 dark:text-gray-100 text-lg">{{ t('backoffice.profile.title') }}</h2>

    <div v-if="loading" class="flex flex-col items-center justify-center py-12 text-gray-400 dark:text-gray-400 gap-3">
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
          <div class="flex h-16 w-16 flex-shrink-0 items-center justify-center rounded-2xl bg-blue-100 text-2xl font-black text-blue-700 dark:bg-blue-950/50 dark:text-blue-300">
            {{ profile.full_name.charAt(0) }}
          </div>
          <div>
            <div class="font-bold text-xl text-gray-900 dark:text-gray-100">{{ profile.full_name }}</div>
            <div class="text-gray-500 dark:text-gray-400 text-sm">
              {{ profile.position }}
              <span v-if="profile.department"> — {{ profile.department }}</span>
            </div>
            <div class="text-xs text-gray-400 dark:text-gray-400 mt-0.5">{{ profile.employee_code }}</div>
          </div>
        </div>

        <div class="space-y-3 border-t border-stone-100 dark:border-border/50 pt-4">
          <div v-if="profile.email" class="flex items-center justify-between text-sm">
            <span class="text-gray-500 dark:text-gray-400 flex items-center gap-1.5">📧 {{ t('backoffice.profile.email') }}</span>
            <span class="font-medium text-gray-900 dark:text-gray-100">{{ profile.email }}</span>
          </div>
          <div v-if="profile.phone" class="flex items-center justify-between text-sm">
            <span class="text-gray-500 dark:text-gray-400 flex items-center gap-1.5">📞 {{ t('backoffice.profile.phone') }}</span>
            <span class="font-medium text-gray-900 dark:text-gray-100" dir="ltr">{{ profile.phone }}</span>
          </div>
          <div v-if="profile.hire_date" class="flex items-center justify-between text-sm">
            <span class="text-gray-500 dark:text-gray-400 flex items-center gap-1.5">📅 {{ t('backoffice.profile.hireDate') }}</span>
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
          <div v-if="pwMsg" role="status" class="rounded-lg bg-green-100 px-3 py-2 text-sm font-medium text-green-700 dark:bg-green-950/50 dark:text-green-300">{{ pwMsg }}</div>
          <div v-if="pwError" role="alert" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-300">{{ pwError }}</div>
          <AppButton type="submit" :loading="pwLoading" variant="primary" class="w-full">
            {{ pwLoading ? t('backoffice.profile.saving') : t('backoffice.profile.savePassword') }}
          </AppButton>
        </form>
      </div>

      <!-- Operational PIN -->
      <div class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border p-6 shadow-sm">
        <h3 class="font-bold text-gray-900 dark:text-gray-100 mb-1">{{ t('backoffice.profile.pin.title') }}</h3>
        <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">{{ t('backoffice.profile.pin.subtitle') }}</p>

        <!-- حالة الـ PIN الحالية -->
        <div v-if="pinLoading" class="flex items-center gap-2 py-2 text-sm text-gray-400">
          <AppSpinner size="sm" />
        </div>
        <div v-else-if="pinStatus" class="mb-4">
          <div v-if="pinStatus.is_locked"
            class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
            🔒 {{ t('backoffice.profile.pin.locked') }}
            <p class="mt-0.5 text-xs opacity-80">{{ t('backoffice.profile.pin.lockedHint') }}</p>
          </div>
          <div v-else-if="pinStatus.has_pin"
            class="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700 dark:border-green-800 dark:bg-green-950/40 dark:text-green-300">
            ✅ {{ t('backoffice.profile.pin.ready') }}
          </div>
          <div v-else
            class="rounded-lg border border-stone-200 bg-stone-50 px-3 py-2 text-sm text-gray-500 dark:border-border dark:bg-surface-2 dark:text-gray-400">
            ⚪ {{ t('backoffice.profile.pin.notSet') }}
          </div>
        </div>

        <!-- Set / Change PIN form -->
        <form class="space-y-3" @submit.prevent="savePin">
          <div>
            <label class="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-200" for="profile-pin-input">
              {{ pinStatus?.has_pin ? t('backoffice.profile.pin.changeTitle') : t('backoffice.profile.pin.setTitle') }}
              <span class="ms-1 text-xs font-normal text-gray-400">{{ t('backoffice.profile.pin.pinHint') }}</span>
            </label>
            <input
              id="profile-pin-input"
              v-model="pinValue"
              type="password"
              inputmode="numeric"
              maxlength="6"
              :placeholder="t('backoffice.profile.pin.pinPlaceholder')"
              autocomplete="off"
              class="min-h-12 w-full rounded-xl border border-stone-300 bg-white p-2.5 text-center text-xl tracking-[0.5em] text-gray-900 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-400/30 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
            />
          </div>
          <div v-if="pinMsg" role="status" class="rounded-lg bg-green-100 px-3 py-2 text-sm font-medium text-green-700 dark:bg-green-950/50 dark:text-green-300">{{ pinMsg }}</div>
          <div v-if="pinError" role="alert" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-300">{{ pinError }}</div>
          <AppButton type="submit" :loading="pinSaving" variant="primary" class="w-full">
            {{ pinSaving ? t('backoffice.profile.pin.saving') : t('backoffice.profile.pin.confirm') }}
          </AppButton>
        </form>
      </div>
    </template>
  </div>
</template>
