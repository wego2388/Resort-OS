<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@resort-os/core'

const auth   = useAuthStore()
const router = useRouter()

const email    = ref('')
const password = ref('')
const otp      = ref('')
const error    = ref('')
const loading  = ref(false)
const needsOtp = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(email.value, password.value, otp.value || undefined)
    router.replace('/')
  } catch (e: unknown) {
    const detail = (e as { response?: { data?: { detail?: { code?: string } | string } } })
      .response?.data?.detail
    const code = typeof detail === 'object' ? detail?.code : ''
    if (code === 'OTP_REQUIRED' || code === '2FA_REQUIRED') {
      needsOtp.value = true
      error.value = 'أدخل رمز التحقق من تطبيق المصادقة'
    } else {
      error.value = typeof detail === 'string' ? detail : 'بيانات الدخول غير صحيحة'
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-owner-bg flex flex-col items-center justify-center px-6"
       style="padding-top: env(safe-area-inset-top); padding-bottom: env(safe-area-inset-bottom);">
    <!-- Logo area -->
    <div class="mb-10 text-center">
      <div class="text-4xl mb-3" aria-hidden="true">🏖️</div>
      <h1 class="text-xl font-bold text-owner-text">المالك</h1>
      <p class="text-xs text-owner-muted mt-1">لوحة تحكم المنتجع</p>
    </div>

    <!-- Login form -->
    <form
      class="w-full max-w-sm space-y-4"
      @submit.prevent="submit"
      novalidate
    >
      <div>
        <label class="block text-xs font-semibold text-owner-muted mb-1" for="email">
          البريد الإلكتروني
        </label>
        <input
          id="email"
          v-model="email"
          type="email"
          autocomplete="username"
          dir="ltr"
          class="w-full bg-owner-card border border-owner-border rounded-xl px-4 py-3 text-owner-text text-sm outline-none focus:border-owner-green transition-colors"
          :disabled="loading"
          required
        />
      </div>

      <div>
        <label class="block text-xs font-semibold text-owner-muted mb-1" for="password">
          كلمة المرور
        </label>
        <input
          id="password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          dir="ltr"
          class="w-full bg-owner-card border border-owner-border rounded-xl px-4 py-3 text-owner-text text-sm outline-none focus:border-owner-green transition-colors"
          :disabled="loading"
          required
        />
      </div>

      <!-- OTP — يظهر فقط لو احتاج -->
      <div v-if="needsOtp">
        <label class="block text-xs font-semibold text-owner-muted mb-1" for="otp">
          رمز التحقق (2FA)
        </label>
        <input
          id="otp"
          v-model="otp"
          type="text"
          inputmode="numeric"
          autocomplete="one-time-code"
          maxlength="6"
          dir="ltr"
          class="w-full bg-owner-card border border-owner-border rounded-xl px-4 py-3 text-owner-text text-sm text-center tracking-widest outline-none focus:border-owner-green transition-colors"
          :disabled="loading"
        />
      </div>

      <!-- Error -->
      <div
        v-if="error"
        class="text-xs text-owner-red bg-red-950/40 border border-red-900/50 rounded-xl px-4 py-3"
        role="alert"
      >
        {{ error }}
      </div>

      <!-- Submit -->
      <button
        type="submit"
        class="w-full bg-owner-green text-black font-bold rounded-xl py-3.5 text-sm transition-opacity active:opacity-80 disabled:opacity-50"
        :disabled="loading || !email || !password"
      >
        <span v-if="loading">جارٍ الدخول...</span>
        <span v-else>دخول</span>
      </button>
    </form>
  </div>
</template>
