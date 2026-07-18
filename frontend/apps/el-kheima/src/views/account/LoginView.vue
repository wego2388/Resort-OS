<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '@resort-os/core'
import { useToast } from '@resort-os/ui'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import LanguageSwitcher from '../../components/LanguageSwitcher.vue'

const auth = useAuthStore()
const toast = useToast()
const router = useRouter()
const { t } = useI18n()

const username = ref('')
const password = ref('')
const loading = ref(false)

// LOGIN_2FA_ENFORCED (backend, off by default): once on, a 2FA-enabled
// account's POST /login returns 401 `2FA_CODE_REQUIRED` until the current
// TOTP code is submitted alongside the password — same code the account
// already set up in TwoFactorSetupView.vue. `needsOtp` switches the form to
// collect it; every other account/config never sees this branch at all.
const needsOtp = ref(false)
const otpCode = ref('')
const useRecoveryCode = ref(false)
const recoveryCode = ref('')
const needsEnrollmentToken = ref(false)
const enrollmentToken = ref('')

async function handleLogin() {
  if (!username.value || !password.value) return
  if (needsOtp.value) {
    if (useRecoveryCode.value && recoveryCode.value.replace(/[^a-z0-9]/gi, '').length !== 24) {
      toast.error(t('backoffice.login.recoveryCodeHint'))
      return
    }
    if (!useRecoveryCode.value && otpCode.value.trim().length !== 6) {
      toast.error(t('backoffice.login.twoFaHint'))
      return
    }
  }
  if (needsEnrollmentToken.value && enrollmentToken.value.trim().length < 20) {
    toast.error(t('backoffice.login.enrollmentTokenHint'))
    return
  }
  loading.value = true
  try {
    await auth.login(
      username.value,
      password.value,
      !useRecoveryCode.value ? otpCode.value.trim() || undefined : undefined,
      useRecoveryCode.value ? recoveryCode.value.trim() || undefined : undefined,
      enrollmentToken.value.trim() || undefined,
    )
    if (auth.needsPasswordChange) {
      router.push('/change-temporary-password')
    } else if (auth.needsTwoFactorSetup) {
      router.push('/2fa-setup')
    } else {
      router.push('/')
    }
  } catch (e: any) {
    const code = e?.response?.data?.detail?.code
    if (code === '2FA_CODE_REQUIRED') {
      needsOtp.value = true
      if (!otpCode.value) toast.error(t('backoffice.login.twoFaHint'))
    } else if (code === '2FA_CODE_INVALID') {
      needsOtp.value = true
      toast.error(t(useRecoveryCode.value ? 'backoffice.login.recoveryCodeInvalid' : 'backoffice.login.twoFaInvalid'))
    } else if (
      code === '2FA_ENROLLMENT_TOKEN_REQUIRED'
      || code === '2FA_ENROLLMENT_TOKEN_INVALID'
      || code === '2FA_ENROLLMENT_TOKEN_EXPIRED'
      || code === '2FA_ENROLLMENT_NOT_PROVISIONED'
    ) {
      needsEnrollmentToken.value = true
      toast.error(
        code === '2FA_ENROLLMENT_NOT_PROVISIONED'
          ? t('backoffice.login.enrollmentNotProvisioned')
          : t('backoffice.login.enrollmentTokenInvalid'),
      )
    } else {
      toast.error(t('auth.loginError'))
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-gradient-to-br from-blue-900 via-blue-800 to-blue-700 dark:from-gray-950 dark:via-gray-900 dark:to-gray-900 flex items-center justify-center p-4">
    <div class="w-full max-w-md">
      <!-- Logo -->
      <div class="text-center mb-8">
        <div class="w-20 h-20 bg-white/10 rounded-2xl flex items-center justify-center mx-auto mb-4 backdrop-blur">
          <svg class="w-10 h-10 text-amber-300" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
          </svg>
        </div>
        <h1 class="text-3xl font-bold text-white mb-1">Resort OS</h1>
        <p class="text-blue-200 text-sm">{{ t('backoffice.login.subtitle') }}</p>
      </div>

      <!-- Form card -->
      <div class="bg-white dark:bg-surface dark:border dark:border-border rounded-2xl p-8 shadow-2xl">
        <!-- Language switcher — top of card so user can pick language before entering credentials -->
        <div class="flex justify-end mb-4">
          <LanguageSwitcher variant="compact" />
        </div>

        <h2 class="text-xl font-bold text-gray-900 dark:text-gray-100 mb-6 text-center">{{ t('backoffice.login.title') }}</h2>
        <form @submit.prevent="handleLogin" class="space-y-4">
          <div>
            <label for="login-username" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.login.username') }}</label>
            <input
              id="login-username"
              v-model="username"
              type="text"
              placeholder="username"
              autocomplete="username"
              class="w-full px-4 py-3 rounded-xl border border-stone-200 dark:border-border dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900"
            />
          </div>
          <div>
            <label for="login-password" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.login.password') }}</label>
            <input
              id="login-password"
              v-model="password"
              type="password"
              placeholder="••••••••"
              autocomplete="current-password"
              class="w-full px-4 py-3 rounded-xl border border-stone-200 dark:border-border dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900 dark:placeholder-gray-500"
            />
          </div>
          <div v-if="!needsOtp && !needsEnrollmentToken" class="text-center -mt-2">
            <router-link to="/forgot-password" class="text-sm text-blue-700 hover:underline">
              {{ t('backoffice.login.forgotPassword') }}
            </router-link>
          </div>
          <div v-if="needsEnrollmentToken">
            <label for="login-enrollment-token" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {{ t('backoffice.login.enrollmentToken') }}
            </label>
            <input
              id="login-enrollment-token"
              v-model="enrollmentToken"
              type="password"
              :placeholder="t('backoffice.login.enrollmentTokenPlaceholder')"
              autocomplete="off"
              class="w-full px-4 py-3 rounded-xl border border-stone-200 dark:border-border dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-gray-900"
            />
            <p class="text-xs text-gray-500 mt-1">{{ t('backoffice.login.enrollmentTokenHint') }}</p>
          </div>
          <div v-if="needsOtp">
            <label :for="useRecoveryCode ? 'login-recovery-code' : 'login-totp-code'" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {{ t(useRecoveryCode ? 'backoffice.login.recoveryCode' : 'backoffice.login.twoFaCode') }}
            </label>
            <input
              v-if="!useRecoveryCode"
              id="login-totp-code"
              v-model="otpCode"
              type="text"
              inputmode="numeric"
              maxlength="6"
              :placeholder="t('backoffice.login.twoFaPlaceholder')"
              autocomplete="one-time-code"
              autofocus
              class="w-full px-4 py-3 rounded-xl border border-stone-200 dark:border-border dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 text-center tracking-widest text-lg font-mono text-gray-900"
            />
            <input
              v-else
              id="login-recovery-code"
              v-model="recoveryCode"
              type="text"
              maxlength="29"
              :placeholder="t('backoffice.login.recoveryCodePlaceholder')"
              autocomplete="one-time-code"
              autofocus
              class="w-full px-4 py-3 rounded-xl border border-stone-200 dark:border-border dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 text-center tracking-wider font-mono text-gray-900 uppercase"
            />
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
              {{ t(useRecoveryCode ? 'backoffice.login.recoveryCodeHint' : 'backoffice.login.twoFaHint') }}
            </p>
            <button
              type="button"
              class="mt-2 text-sm text-blue-700 hover:underline"
              @click="useRecoveryCode = !useRecoveryCode"
            >
              {{ t(useRecoveryCode ? 'backoffice.login.useAuthenticator' : 'backoffice.login.useRecoveryCode') }}
            </button>
          </div>
          <button
            type="submit"
            :disabled="loading"
            class="w-full bg-blue-700 text-white py-3 rounded-xl font-semibold hover:bg-blue-800 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            <svg v-if="loading" class="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
            </svg>
            {{ loading ? t('backoffice.login.signingIn') : t('backoffice.login.signIn') }}
          </button>
        </form>
        <p class="text-center text-xs text-gray-400 dark:text-gray-500 mt-6">{{ t('backoffice.login.footer') }}</p>
      </div>
    </div>
  </div>
</template>
