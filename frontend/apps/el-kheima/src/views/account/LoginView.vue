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
    } else if (e?.response?.status === 429) {
      // Rate-limit middleware (app/core/rate_limit.py) returns a flat
      // {code, message} body, not FastAPI's nested {detail: {code}} shape —
      // falls through to the generic branch below without this check, and
      // gets shown as "wrong email or password" even though the account and
      // password are both fine (real incident: multiple staff testing their
      // new accounts from the same office IP shared one 5-attempts/5-minute
      // bucket keyed by IP, not by account).
      toast.error(t('auth.loginRateLimited'))
    } else {
      toast.error(t('auth.loginError'))
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="relative min-h-screen overflow-hidden flex items-center justify-center p-4 bg-gradient-to-br from-blue-950 via-blue-900 to-blue-800 dark:from-gray-950 dark:via-gray-950 dark:to-gray-900">
    <!-- خلفية زخرفية (طلب Mohamed 2026-08-03: "حسّن مظهر الصفحة دي") — توهجات
    غروب دافئة (كهرماني/برتقالي، بألوان اللوجو نفسها) فوق الأزرق الغامق، بدل
    التدرّج المسطّح القديم اللي مالوش أي عمق بصري. blur-3xl عشان تفضل خلفية
    ناعمة مش تصميم مزدحم، prefers-reduced-motion بيوقف الحركة بس مش التوهج نفسه. -->
    <div class="pointer-events-none absolute inset-0" aria-hidden="true">
      <div class="absolute -top-24 -end-24 w-96 h-96 rounded-full opacity-20 blur-3xl motion-safe:animate-pulse" style="background:radial-gradient(circle, #f59e0b, transparent 70%)" />
      <div class="absolute -bottom-32 -start-32 w-[28rem] h-[28rem] rounded-full opacity-20 blur-3xl motion-safe:animate-pulse" style="background:radial-gradient(circle, #00d4ff, transparent 70%)" />
      <div class="absolute inset-0 opacity-[0.03]" style="background-image:radial-gradient(circle, #fff 1px, transparent 1px);background-size:28px 28px" />
    </div>

    <div class="relative w-full max-w-md">
      <!-- Logo -->
      <div class="text-center mb-8">
        <div class="w-28 h-28 bg-white rounded-3xl flex items-center justify-center mx-auto mb-4 shadow-2xl ring-1 ring-white/10 p-3">
          <img src="/el-kheima-logo.png" alt="El Kheima Beach Resort" class="w-full h-full object-contain" />
        </div>
        <p class="text-amber-300 text-xs font-black tracking-[0.3em] uppercase mb-1.5">Resort OS</p>
        <p class="text-blue-200/80 text-sm">{{ t('backoffice.login.subtitle') }}</p>
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
            <router-link to="/forgot-password" class="text-sm text-blue-700 hover:underline dark:text-blue-300">
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
            <p class="text-xs text-gray-400 dark:text-gray-400 mt-1">
              {{ t(useRecoveryCode ? 'backoffice.login.recoveryCodeHint' : 'backoffice.login.twoFaHint') }}
            </p>
            <button
              type="button"
              class="mt-2 text-sm text-blue-700 hover:underline dark:text-blue-300"
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
            <svg v-if="loading" class="motion-safe:animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
            </svg>
            {{ loading ? t('backoffice.login.signingIn') : t('backoffice.login.signIn') }}
          </button>
        </form>
        <p class="text-center text-xs text-gray-400 dark:text-gray-400 mt-6">{{ t('backoffice.login.footer') }}</p>
      </div>
    </div>
  </div>
</template>
