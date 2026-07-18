<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'
import LanguageSwitcher from '../../components/LanguageSwitcher.vue'

const auth = useAuthStore()
const { t, locale } = useI18n()

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const enrollmentToken = ref(auth.pendingEnrollmentToken)
const loading = ref(false)
const error = ref('')
const completed = ref(false)

const direction = computed(() => locale.value === 'ar' ? 'rtl' : 'ltr')
const requiresEnrollmentToken = computed(
  () => !!auth.user?.two_factor_bootstrap_required,
)

function apiMessage(exception: any): string {
  const detail = exception?.response?.data?.detail
  return typeof detail === 'object' ? detail?.message : detail
}

async function submit() {
  error.value = ''
  if (!currentPassword.value || !newPassword.value || !confirmPassword.value) {
    error.value = t('backoffice.securityOnboarding.password.allFieldsRequired')
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    error.value = t('backoffice.securityOnboarding.password.mismatch')
    return
  }
  if (requiresEnrollmentToken.value && enrollmentToken.value.trim().length < 20) {
    error.value = t('backoffice.login.enrollmentTokenHint')
    return
  }

  loading.value = true
  try {
    await api.post(ENDPOINTS.auth.changePassword, {
      current_password: currentPassword.value,
      new_password: newPassword.value,
      ...(requiresEnrollmentToken.value
        ? { enrollment_token: enrollmentToken.value.trim() }
        : {}),
    })
    completed.value = true
  } catch (exception: any) {
    error.value = apiMessage(exception) || t('backoffice.securityOnboarding.password.failed')
  } finally {
    loading.value = false
  }
}

function returnToLogin() {
  window.location.replace('/login')
}
</script>

<template>
  <main
    :dir="direction"
    class="min-h-screen bg-gradient-to-br from-blue-950 via-blue-900 to-cyan-800 flex items-center justify-center p-4"
  >
    <section class="w-full max-w-lg">
      <div class="flex justify-between items-center mb-5">
        <div class="text-white">
          <p class="text-xs font-semibold tracking-[0.18em] uppercase text-cyan-200">El Kheima Beach Resort OS</p>
          <h1 class="text-2xl font-bold mt-1">{{ t('backoffice.securityOnboarding.password.title') }}</h1>
        </div>
        <LanguageSwitcher variant="compact" />
      </div>

      <div class="bg-white dark:bg-surface rounded-2xl border border-white/20 dark:border-border shadow-2xl p-6 sm:p-8">
        <template v-if="completed">
          <div role="status" class="text-center py-3">
            <div class="mx-auto w-14 h-14 rounded-full bg-green-100 text-green-700 flex items-center justify-center text-2xl mb-4">✓</div>
            <h2 class="text-xl font-bold text-gray-900 dark:text-gray-100">
              {{ t('backoffice.securityOnboarding.password.successTitle') }}
            </h2>
            <p class="mt-2 text-sm leading-6 text-gray-600 dark:text-gray-300">
              {{ t('backoffice.securityOnboarding.password.successBody') }}
            </p>
            <button
              type="button"
              class="mt-6 w-full min-h-12 rounded-xl bg-blue-700 text-white font-semibold hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
              @click="returnToLogin"
            >
              {{ t('backoffice.securityOnboarding.password.backToLogin') }}
            </button>
          </div>
        </template>

        <form v-else class="space-y-4" @submit.prevent="submit">
          <div class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900">
            {{ t('backoffice.securityOnboarding.password.reason') }}
          </div>

          <div>
            <label for="temporary-password" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {{ t('backoffice.securityOnboarding.password.temporaryPassword') }}
            </label>
            <input
              id="temporary-password"
              v-model="currentPassword"
              type="password"
              autocomplete="current-password"
              required
              class="w-full min-h-12 px-4 rounded-xl border border-stone-300 dark:border-border dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
          </div>

          <div v-if="requiresEnrollmentToken">
            <label for="bootstrap-token" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {{ t('backoffice.login.enrollmentToken') }}
            </label>
            <input
              id="bootstrap-token"
              v-model="enrollmentToken"
              type="password"
              autocomplete="off"
              required
              class="w-full min-h-12 px-4 rounded-xl border border-stone-300 dark:border-border dark:bg-gray-800 dark:text-gray-100 font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
            <p class="mt-1 text-xs text-gray-500">{{ t('backoffice.login.enrollmentTokenHint') }}</p>
          </div>

          <div>
            <label for="new-password" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {{ t('backoffice.securityOnboarding.password.newPassword') }}
            </label>
            <input
              id="new-password"
              v-model="newPassword"
              type="password"
              autocomplete="new-password"
              required
              class="w-full min-h-12 px-4 rounded-xl border border-stone-300 dark:border-border dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
            <p class="mt-1 text-xs text-gray-500">{{ t('backoffice.securityOnboarding.password.requirements') }}</p>
          </div>

          <div>
            <label for="confirm-password" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {{ t('backoffice.securityOnboarding.password.confirmPassword') }}
            </label>
            <input
              id="confirm-password"
              v-model="confirmPassword"
              type="password"
              autocomplete="new-password"
              required
              class="w-full min-h-12 px-4 rounded-xl border border-stone-300 dark:border-border dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
          </div>

          <p v-if="error" role="alert" class="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {{ error }}
          </p>

          <button
            type="submit"
            :disabled="loading"
            class="w-full min-h-12 rounded-xl bg-blue-700 text-white font-semibold hover:bg-blue-800 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            {{ loading ? t('common.loading') : t('backoffice.securityOnboarding.password.submit') }}
          </button>
        </form>
      </div>
    </section>
  </main>
</template>
