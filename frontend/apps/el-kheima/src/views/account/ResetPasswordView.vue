<script setup lang="ts">
// ResetPasswordView — الخطوة الثانية من نفس الفجوة اللي ForgotPasswordView.vue
// بتغطيها (راجع تعليقات الملف ده لتفاصيل الفجوة). التوكن بيوصل هنا كـ query
// param في رابط الإيميل اللي الباك إند بيبعته (app/core/kernel/email_service.py::
// send_password_reset_email → "{APP_URL}/reset-password?token=...").
//
// endpoint حقيقي من app/core/kernel/auth/router.py + service.py:
//   POST /api/v1/auth/password-reset/confirm  body: { token, new_password }
//   → 400 "Token expired or invalid"     لو التوكن غلط/منتهي (صلاحية ساعتين، مرة واحدة بس)
//   → 400 <رسالة قوة كلمة السر>           لو الباسورد الجديد ضعيف (validate_password_strength)
//   → 200 { message: "Password updated successfully." }
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, ENDPOINTS } from '@resort-os/core'
import { useI18n } from 'vue-i18n'
import LanguageSwitcher from '../../components/LanguageSwitcher.vue'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

// التوكن بيوصل مرة واحدة بس وقت التحميل — رابط بريد إلكتروني حقيقي، مش
// حاجة المفروض تتغيّر أثناء وجود المستخدم على الصفحة.
const token = ref('')
onMounted(() => {
  const raw = route.query.token
  token.value = typeof raw === 'string' ? raw : ''
})

const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const done = ref(false)
const error = ref('')
// التوكن نفسه غلط/منتهي (مش مشكلة في الباسورد الجديد) — يوجّه المستخدم
// لطلب رابط جديد بدل ما يفضل يحاول يعدّل الباسورد من غير فايدة.
const tokenInvalid = ref(false)

const missingToken = computed(() => !token.value)

async function handleSubmit() {
  error.value = ''
  if (newPassword.value.length < 8) {
    error.value = t('backoffice.resetPassword.errorMinLength')
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    error.value = t('backoffice.resetPassword.errorMismatch')
    return
  }
  loading.value = true
  try {
    await api.post(ENDPOINTS.auth.passwordResetConfirm, {
      token: token.value,
      new_password: newPassword.value,
    })
    done.value = true
    setTimeout(() => router.push('/login'), 3000)
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    if (typeof detail === 'string' && detail.toLowerCase().includes('token')) {
      tokenInvalid.value = true
      error.value = t('backoffice.resetPassword.noToken')
    } else {
      // رسائل قوة كلمة السر بترجع من الباك إند كنص واضح (مطلوب حرف كبير/رقم/
      // رمز خاص...) — إظهارها زي ما هي أفيد للمستخدم من رسالة عامة هنا.
      error.value = typeof detail === 'string' ? detail : t('errors.generic')
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div
    class="min-h-screen bg-gradient-to-br from-blue-900 via-blue-800 to-blue-700 flex items-center justify-center p-4"
    :dir="locale === 'ar' ? 'rtl' : 'ltr'"
  >
    <div class="w-full max-w-md">
      <div class="text-center mb-8">
        <div class="w-16 h-16 bg-white/10 rounded-2xl flex items-center justify-center mx-auto mb-3 backdrop-blur text-3xl">🔒</div>
        <h1 class="text-2xl font-bold text-white mb-1">{{ t('backoffice.resetPassword.title') }}</h1>
        <p class="text-blue-200 text-sm">{{ t('backoffice.resetPassword.subtitle') }}</p>
      </div>

      <div class="bg-white dark:bg-surface rounded-2xl p-8 shadow-2xl">
        <div class="flex justify-end mb-4">
          <LanguageSwitcher variant="compact" />
        </div>

        <!-- لا يوجد توكن في الرابط أصلاً -->
        <template v-if="missingToken && !done">
          <div class="text-center py-4">
            <p class="text-gray-600 text-sm mb-4">{{ t('backoffice.resetPassword.noToken') }}</p>
            <router-link
              to="/forgot-password"
              class="inline-block bg-blue-700 text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-blue-800 transition-colors"
            >
              {{ t('backoffice.resetPassword.requestNew') }}
            </router-link>
          </div>
        </template>

        <!-- نجاح -->
        <template v-else-if="done">
          <div class="flex items-center gap-3 bg-green-50 border border-green-200 text-green-700 rounded-xl px-4 py-3 mb-2">
            <span class="text-xl">✓</span>
            <span class="font-medium text-sm">{{ t('backoffice.resetPassword.successMessage') }}</span>
          </div>
        </template>

        <!-- الفورم -->
        <template v-else>
          <form @submit.prevent="handleSubmit" class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.resetPassword.newPassword') }}</label>
              <input
                v-model="newPassword"
                type="password"
                placeholder="••••••••"
                autocomplete="new-password"
                autofocus
                class="w-full px-4 py-3 rounded-xl border border-stone-200 dark:border-border focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900 dark:text-gray-100"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.resetPassword.confirmPassword') }}</label>
              <input
                v-model="confirmPassword"
                type="password"
                placeholder="••••••••"
                autocomplete="new-password"
                class="w-full px-4 py-3 rounded-xl border border-stone-200 dark:border-border focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900 dark:text-gray-100"
              />
            </div>
            <p v-if="error" class="text-red-600 text-sm">{{ error }}</p>
            <router-link
              v-if="tokenInvalid"
              to="/forgot-password"
              class="block text-center text-sm text-blue-700 font-medium hover:underline"
            >
              {{ t('backoffice.resetPassword.requestNew') }}
            </router-link>
            <button
              type="submit"
              :disabled="loading"
              class="w-full bg-blue-700 text-white py-3 rounded-xl font-semibold hover:bg-blue-800 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <svg v-if="loading" class="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
              </svg>
              {{ loading ? t('backoffice.resetPassword.submitting') : t('backoffice.resetPassword.submit') }}
            </button>
          </form>
        </template>

        <router-link to="/login" class="block text-center text-sm text-blue-700 font-medium hover:underline mt-6">
          {{ t('backoffice.resetPassword.backToLogin') }}
        </router-link>
        <p class="text-center text-xs text-gray-400 mt-6">{{ t('backoffice.login.footer') }}</p>
      </div>
    </div>
  </div>
</template>
