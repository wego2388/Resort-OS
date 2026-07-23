<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'
import { AppButton, AppSpinner } from '@resort-os/ui'
import LanguageSwitcher from '../../components/LanguageSwitcher.vue'

const auth = useAuthStore()
const { t, locale } = useI18n()

const direction = computed(() => locale.value === 'ar' ? 'rtl' : 'ltr')
const isMandatory = computed(() => auth.needsTwoFactorSetup)
const isEnabled = computed(() => !!auth.user?.two_factor_enabled)
const requiresEnrollmentToken = computed(
  () => !!auth.user?.two_factor_bootstrap_required,
)

const currentPassword = ref('')
const enrollmentToken = ref(auth.pendingEnrollmentToken)
const loadingSetup = ref(false)
const setupError = ref('')
const secret = ref('')
const qrUrl = ref('')
const qrFailed = ref(false)
const code = ref('')
const enabling = ref(false)
const enableError = ref('')

const recoveryCodes = ref<string[]>([])
const codesAcknowledged = ref(false)
const copied = ref(false)

const showDisableForm = ref(false)
const disableCode = ref('')
const disablePassword = ref('')
const disabling = ref(false)
const disableError = ref('')

const showRegenerateForm = ref(false)
const regenerateCode = ref('')
const regeneratePassword = ref('')
const regenerating = ref(false)
const regenerateError = ref('')

function apiMessage(exception: any, fallbackKey: string): string {
  const detail = exception?.response?.data?.detail
  return (typeof detail === 'object' ? detail?.message : detail) || t(fallbackKey)
}

async function loadSetup() {
  setupError.value = ''
  if (requiresEnrollmentToken.value && enrollmentToken.value.trim().length < 20) {
    setupError.value = t('backoffice.login.enrollmentTokenHint')
    return
  }
  if (!requiresEnrollmentToken.value && !currentPassword.value) {
    setupError.value = t('backoffice.securityOnboarding.twoFactor.currentPasswordRequired')
    return
  }

  loadingSetup.value = true
  try {
    const { data } = await api.post(ENDPOINTS.auth.setup2fa, {
      ...(requiresEnrollmentToken.value
        ? { enrollment_token: enrollmentToken.value.trim() }
        : { current_password: currentPassword.value }),
    })
    secret.value = data.secret
    qrUrl.value = data.qr_url
  } catch (exception: any) {
    setupError.value = apiMessage(exception, 'backoffice.securityOnboarding.twoFactor.setupFailed')
  } finally {
    loadingSetup.value = false
  }
}

async function submitEnable() {
  if (code.value.trim().length !== 6) {
    enableError.value = t('backoffice.securityOnboarding.twoFactor.codeRequired')
    return
  }
  enabling.value = true
  enableError.value = ''
  try {
    const { data } = await api.post(ENDPOINTS.auth.enable2fa, {
      code: code.value.trim(),
      ...(requiresEnrollmentToken.value
        ? { enrollment_token: enrollmentToken.value.trim() }
        : {}),
    })
    recoveryCodes.value = data.recovery_codes ?? []
  } catch (exception: any) {
    enableError.value = apiMessage(exception, 'backoffice.securityOnboarding.twoFactor.invalidCode')
  } finally {
    enabling.value = false
  }
}

async function copyRecoveryCodes() {
  try {
    await navigator.clipboard.writeText(recoveryCodes.value.join('\n'))
    copied.value = true
  } catch {
    copied.value = false
  }
}

function returnToLogin() {
  window.location.replace('/login')
}

async function submitDisable() {
  disabling.value = true
  disableError.value = ''
  try {
    await api.post(ENDPOINTS.auth.disable2fa, {
      code: disableCode.value.trim(),
      current_password: disablePassword.value,
    })
    returnToLogin()
  } catch (exception: any) {
    disableError.value = apiMessage(exception, 'backoffice.securityOnboarding.twoFactor.disableFailed')
  } finally {
    disabling.value = false
  }
}

async function submitRegenerate() {
  regenerating.value = true
  regenerateError.value = ''
  try {
    const { data } = await api.post(ENDPOINTS.auth.regenerateRecoveryCodes, {
      code: regenerateCode.value.trim(),
      current_password: regeneratePassword.value,
    })
    recoveryCodes.value = data.recovery_codes ?? []
    codesAcknowledged.value = false
  } catch (exception: any) {
    regenerateError.value = apiMessage(exception, 'backoffice.securityOnboarding.twoFactor.regenerateFailed')
  } finally {
    regenerating.value = false
  }
}

onMounted(() => {
  if (!isEnabled.value && requiresEnrollmentToken.value && enrollmentToken.value) {
    loadSetup()
  }
})
</script>

<template>
  <main
    :dir="direction"
    class="min-h-screen bg-gradient-to-br from-blue-950 via-blue-900 to-cyan-800 flex items-center justify-center p-4"
  >
    <section class="w-full max-w-2xl">
      <div class="flex justify-between items-start gap-4 mb-5">
        <div class="text-white">
          <p class="text-xs font-semibold tracking-[0.18em] uppercase text-cyan-200">El Kheima Beach Resort OS</p>
          <h1 class="text-2xl font-bold mt-1">{{ t('backoffice.securityOnboarding.twoFactor.title') }}</h1>
          <p v-if="isMandatory && !isEnabled" class="text-sm text-blue-100 mt-1">
            {{ t('backoffice.securityOnboarding.twoFactor.mandatory') }}
          </p>
        </div>
        <LanguageSwitcher variant="compact" />
      </div>

      <div class="bg-white dark:bg-surface rounded-2xl border border-white/20 dark:border-border shadow-2xl p-6 sm:p-8">
        <template v-if="recoveryCodes.length">
          <div role="status" class="rounded-xl border border-amber-300 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/40 sm:p-5">
            <h2 class="text-lg font-bold text-amber-950 dark:text-amber-200">
              {{ t('backoffice.securityOnboarding.twoFactor.recoveryTitle') }}
            </h2>
            <p class="mt-1 text-sm leading-6 text-amber-900 dark:text-amber-200">
              {{ t('backoffice.securityOnboarding.twoFactor.recoveryBody') }}
            </p>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 my-5" dir="ltr">
            <code
              v-for="recoveryCode in recoveryCodes"
              :key="recoveryCode"
              class="select-all rounded-lg border border-stone-200 bg-stone-50 px-3 py-2 text-center font-mono font-semibold tracking-wide text-gray-900 dark:border-border dark:bg-gray-800 dark:text-gray-100"
            >{{ recoveryCode }}</code>
          </div>

          <button type="button" class="text-sm font-semibold text-blue-700 hover:underline dark:text-blue-300" @click="copyRecoveryCodes">
            {{ copied
              ? t('backoffice.securityOnboarding.twoFactor.copied')
              : t('backoffice.securityOnboarding.twoFactor.copyCodes') }}
          </button>

          <label class="mt-5 flex items-start gap-3 rounded-xl border border-stone-200 p-3 cursor-pointer">
            <input v-model="codesAcknowledged" type="checkbox" class="mt-1 w-4 h-4 accent-blue-700">
            <span class="text-sm leading-6 text-gray-700 dark:text-gray-300">
              {{ t('backoffice.securityOnboarding.twoFactor.savedConfirmation') }}
            </span>
          </label>

          <button
            type="button"
            :disabled="!codesAcknowledged"
            class="mt-4 w-full min-h-12 rounded-xl bg-blue-700 text-white font-semibold hover:bg-blue-800 disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            @click="returnToLogin"
          >
            {{ t('backoffice.securityOnboarding.twoFactor.signInAgain') }}
          </button>
        </template>

        <template v-else-if="isEnabled">
          <div class="flex items-center gap-3 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-green-800 dark:border-green-800 dark:bg-green-950/40 dark:text-green-300">
            <span aria-hidden="true" class="text-xl">✓</span>
            <span class="font-semibold">{{ t('backoffice.securityOnboarding.twoFactor.enabled') }}</span>
          </div>

          <div class="mt-6 rounded-xl border border-stone-200 p-4">
            <h2 class="font-semibold text-gray-900 dark:text-gray-100">
              {{ t('backoffice.securityOnboarding.twoFactor.recoveryManagement') }}
            </h2>
            <p class="text-sm text-gray-600 dark:text-gray-300 mt-1">
              {{ t('backoffice.securityOnboarding.twoFactor.regenerateWarning') }}
            </p>
            <AppButton v-if="!showRegenerateForm" variant="secondary" class="mt-3" @click="showRegenerateForm = true">
              {{ t('backoffice.securityOnboarding.twoFactor.regenerate') }}
            </AppButton>
            <form v-else class="space-y-3 mt-4" @submit.prevent="submitRegenerate">
              <label for="regenerate-password" class="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {{ t('backoffice.securityOnboarding.twoFactor.currentPassword') }}
              </label>
              <input
                id="regenerate-password"
                v-model="regeneratePassword"
                type="password"
                autocomplete="current-password"
                :placeholder="t('backoffice.securityOnboarding.twoFactor.currentPassword')"
                required
                class="w-full min-h-11 px-4 rounded-xl border border-stone-300 dark:border-border dark:bg-gray-800 dark:text-gray-100"
              >
              <label for="regenerate-code" class="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {{ t('backoffice.login.twoFaCode') }}
              </label>
              <input
                id="regenerate-code"
                v-model="regenerateCode"
                type="text"
                inputmode="numeric"
                maxlength="6"
                autocomplete="one-time-code"
                :placeholder="t('backoffice.login.twoFaPlaceholder')"
                required
                class="w-full min-h-11 px-4 rounded-xl border border-stone-300 dark:border-border dark:bg-gray-800 dark:text-gray-100 text-center font-mono tracking-widest"
              >
              <p v-if="regenerateError" role="alert" class="text-sm text-red-700 dark:text-red-300">{{ regenerateError }}</p>
              <div class="flex gap-2">
                <AppButton type="submit" variant="primary" :loading="regenerating">
                  {{ t('backoffice.securityOnboarding.twoFactor.regenerate') }}
                </AppButton>
                <AppButton type="button" variant="secondary" @click="showRegenerateForm = false">
                  {{ t('common.cancel') }}
                </AppButton>
              </div>
            </form>
          </div>

          <div v-if="!isMandatory" class="mt-6 border-t border-stone-200 pt-5">
            <button
              v-if="!showDisableForm"
              type="button"
              class="text-sm font-semibold text-red-700 hover:underline dark:text-red-300"
              @click="showDisableForm = true"
            >
              {{ t('backoffice.securityOnboarding.twoFactor.disable') }}
            </button>
            <form v-else class="space-y-3" @submit.prevent="submitDisable">
              <p class="text-sm text-red-700 dark:text-red-300">{{ t('backoffice.securityOnboarding.twoFactor.disableWarning') }}</p>
              <label for="disable-password" class="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {{ t('backoffice.securityOnboarding.twoFactor.currentPassword') }}
              </label>
              <input
                id="disable-password"
                v-model="disablePassword"
                type="password"
                autocomplete="current-password"
                :placeholder="t('backoffice.securityOnboarding.twoFactor.currentPassword')"
                required
                class="w-full min-h-11 px-4 rounded-xl border border-stone-300 dark:border-border dark:bg-gray-800 dark:text-gray-100"
              >
              <label for="disable-code" class="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {{ t('backoffice.login.twoFaCode') }}
              </label>
              <input
                id="disable-code"
                v-model="disableCode"
                type="text"
                inputmode="numeric"
                maxlength="6"
                autocomplete="one-time-code"
                :placeholder="t('backoffice.login.twoFaPlaceholder')"
                required
                class="w-full min-h-11 px-4 rounded-xl border border-stone-300 dark:border-border dark:bg-gray-800 dark:text-gray-100 text-center font-mono tracking-widest"
              >
              <p v-if="disableError" role="alert" class="text-sm text-red-700 dark:text-red-300">{{ disableError }}</p>
              <div class="flex gap-2">
                <AppButton type="submit" variant="danger" :loading="disabling">
                  {{ t('backoffice.securityOnboarding.twoFactor.confirmDisable') }}
                </AppButton>
                <AppButton type="button" variant="secondary" @click="showDisableForm = false">
                  {{ t('common.cancel') }}
                </AppButton>
              </div>
            </form>
          </div>
          <p v-else class="mt-5 text-sm text-gray-500">
            {{ t('backoffice.securityOnboarding.twoFactor.cannotDisableMandatory') }}
          </p>
        </template>

        <template v-else>
          <div v-if="!secret && !loadingSetup" class="space-y-4">
            <div class="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm leading-6 text-blue-900 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300">
              {{ t('backoffice.securityOnboarding.twoFactor.bindingExplanation') }}
            </div>
            <div v-if="requiresEnrollmentToken">
              <label for="enrollment-token" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {{ t('backoffice.login.enrollmentToken') }}
              </label>
              <input
                id="enrollment-token"
                v-model="enrollmentToken"
                type="password"
                autocomplete="off"
                class="w-full min-h-12 px-4 rounded-xl border border-stone-300 dark:border-border dark:bg-gray-800 dark:text-gray-100 font-mono"
              >
              <p class="mt-1 text-xs text-gray-500">{{ t('backoffice.login.enrollmentTokenHint') }}</p>
            </div>
            <div v-else>
              <label for="setup-password" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {{ t('backoffice.securityOnboarding.twoFactor.currentPassword') }}
              </label>
              <input
                id="setup-password"
                v-model="currentPassword"
                type="password"
                autocomplete="current-password"
                class="w-full min-h-12 px-4 rounded-xl border border-stone-300 dark:border-border dark:bg-gray-800 dark:text-gray-100"
              >
            </div>
            <p v-if="setupError" role="alert" class="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
              {{ setupError }}
            </p>
            <AppButton variant="primary" class="w-full" @click="loadSetup">
              {{ t('backoffice.securityOnboarding.twoFactor.beginSetup') }}
            </AppButton>
          </div>

          <div v-else-if="loadingSetup" class="flex flex-col items-center gap-3 py-10">
            <AppSpinner size="lg" />
            <p class="text-sm text-gray-500">{{ t('backoffice.securityOnboarding.twoFactor.preparing') }}</p>
          </div>

          <div v-else class="space-y-4">
            <ol class="list-decimal list-inside space-y-2 text-sm leading-6 text-gray-700 dark:text-gray-300">
              <li>{{ t('backoffice.securityOnboarding.twoFactor.stepOne') }}</li>
              <li>{{ t('backoffice.securityOnboarding.twoFactor.stepTwo') }}</li>
              <li>{{ t('backoffice.securityOnboarding.twoFactor.stepThree') }}</li>
            </ol>

            <div v-if="!qrFailed" class="flex justify-center">
              <img
                :src="qrUrl"
                :alt="t('backoffice.securityOnboarding.twoFactor.qrAlt')"
                class="w-48 h-48 rounded-xl border border-stone-200 bg-white dark:bg-surface p-2"
                @error="qrFailed = true"
              >
            </div>
            <p v-if="qrFailed" class="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
              {{ t('backoffice.securityOnboarding.twoFactor.qrFailed') }}
            </p>

            <div class="rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-center dark:border-border dark:bg-gray-800" dir="ltr">
              <p class="mb-1 text-xs text-gray-500 dark:text-gray-400">{{ t('backoffice.securityOnboarding.twoFactor.manualKey') }}</p>
              <code class="select-all break-all font-mono text-sm tracking-widest text-gray-900 dark:text-gray-100">{{ secret }}</code>
            </div>

            <label for="totp-code" class="block text-sm font-medium text-gray-700 dark:text-gray-300">
              {{ t('backoffice.login.twoFaCode') }}
            </label>
            <input
              id="totp-code"
              v-model="code"
              type="text"
              inputmode="numeric"
              maxlength="6"
              autocomplete="one-time-code"
              class="w-full min-h-12 px-4 rounded-xl border border-stone-300 dark:border-border dark:bg-gray-800 dark:text-gray-100 text-center tracking-widest text-lg font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
              @keyup.enter="submitEnable"
            >
            <p v-if="enableError" role="alert" class="text-sm text-red-700 dark:text-red-300">{{ enableError }}</p>
            <AppButton variant="primary" class="w-full" :loading="enabling" @click="submitEnable">
              {{ t('backoffice.securityOnboarding.twoFactor.enable') }}
            </AppButton>
          </div>
        </template>
      </div>
    </section>
  </main>
</template>
