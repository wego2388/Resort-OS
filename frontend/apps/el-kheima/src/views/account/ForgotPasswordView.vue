<script setup lang="ts">
// ForgotPasswordView — يغطي فجوة كانت موجودة: الباك إند (app/core/kernel/auth/router.py)
// عنده POST /auth/password-reset/request جاهز وشغال من زمان، لكن مفيش أي شاشة
// فرونت إند بتستخدمه — يعني موظف نسي كلمة السر كان مضطر يكلم super_admin يدويًا
// عشان يغيّرها له من شاشة إدارة المستخدمين.
//
// endpoint حقيقي من app/core/kernel/auth/router.py + service.py:
//   POST /api/v1/auth/password-reset/request  body: { email }
//   → دايمًا بيرجّع { message: "If that email exists, a reset link has been sent." }
//     (200) بغض النظر عن وجود الإيميل من عدمه — الباك إند نفسه مصمم عشان
//     يمنع user-enumeration، فالشاشة هنا لازم تعرض نفس الرسالة العامة دايمًا
//     ومتحاولش تخمّن أو تفرّق بين "الإيميل موجود" و"الإيميل مش موجود".
//   الباك إند بيبعت إيميل حقيقي (لو SendGrid مُعدّ) فيه رابط
//   {APP_URL}/reset-password?token=... — التوكن صالح لمدة ساعتين.
import { ref } from 'vue'
import { api, ENDPOINTS } from '@resort-os/core'
import { useI18n } from 'vue-i18n'
import LanguageSwitcher from '../../components/LanguageSwitcher.vue'

const { t, locale } = useI18n()

const email = ref('')
const loading = ref(false)
const submitted = ref(false)
const error = ref('')

async function handleSubmit() {
  if (!email.value.trim()) {
    error.value = t('backoffice.forgotPassword.error')
    return
  }
  loading.value = true
  error.value = ''
  try {
    await api.post(ENDPOINTS.auth.passwordResetRequest, { email: email.value.trim() })
  } catch {
    // ⚠️ متعمّد: حتى لو الطلب فشل (شبكة، 5xx...) بنعرض نفس رسالة النجاح
    // العامة — عشان محدش يقدر يفرّق بين "الإيميل مش موجود" و"حصل خطأ" أو
    // يستنتج أي حاجة عن حالة الحساب من رد الشاشة. الباك إند نفسه أصلاً
    // بيرجّع 200 دايمًا للمسار العادي (سطر service.py: try/except صامت
    // حوالين إرسال الإيميل الفعلي).
  } finally {
    loading.value = false
    submitted.value = true
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
        <div class="w-16 h-16 bg-white/10 rounded-2xl flex items-center justify-center mx-auto mb-3 backdrop-blur text-3xl">🔑</div>
        <h1 class="text-2xl font-bold text-white mb-1">{{ t('backoffice.forgotPassword.title') }}</h1>
        <p class="text-blue-200 text-sm">{{ t('backoffice.forgotPassword.subtitle') }}</p>
      </div>

      <div class="bg-white dark:bg-surface rounded-2xl p-8 shadow-2xl">
        <div class="flex justify-end mb-4">
          <LanguageSwitcher variant="compact" />
        </div>

        <template v-if="!submitted">
          <form @submit.prevent="handleSubmit" class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.forgotPassword.email') }}</label>
              <input
                v-model="email"
                type="email"
                :placeholder="t('backoffice.forgotPassword.emailPlaceholder')"
                autocomplete="email"
                autofocus
                class="w-full px-4 py-3 rounded-xl border border-stone-200 dark:border-border focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900 dark:text-gray-100"
              />
            </div>
            <p v-if="error" class="text-sm text-red-600 dark:text-red-300">{{ error }}</p>
            <button
              type="submit"
              :disabled="loading"
              class="w-full bg-blue-700 text-white py-3 rounded-xl font-semibold hover:bg-blue-800 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <svg v-if="loading" class="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
              </svg>
              {{ loading ? t('backoffice.forgotPassword.submitting') : t('backoffice.forgotPassword.submit') }}
            </button>
          </form>
        </template>

        <!-- رسالة عامة موحّدة — تظهر سواء الإيميل مسجّل أو لأ (لا تسريب معلومات) -->
        <template v-else>
          <div class="mb-2 flex items-center gap-3 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-green-700 dark:border-green-800 dark:bg-green-950/40 dark:text-green-300">
            <span class="text-xl">✓</span>
            <span class="font-medium text-sm">{{ t('backoffice.forgotPassword.successMessage') }}</span>
          </div>
        </template>

        <router-link to="/login" class="mt-6 block text-center text-sm font-medium text-blue-700 hover:underline dark:text-blue-300">
          {{ t('backoffice.forgotPassword.backToLogin') }}
        </router-link>
        <p class="text-center text-xs text-gray-400 mt-6">{{ t('backoffice.login.footer') }}</p>
      </div>
    </div>
  </div>
</template>
