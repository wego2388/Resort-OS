<script setup lang="ts">
import { computed, ref } from 'vue'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'

const auth = useAuthStore()

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const enrollmentToken = ref(auth.pendingEnrollmentToken)
const loading = ref(false)
const error = ref('')
const completed = ref(false)
const showPasswords = ref(false)

const requiresEnrollmentToken = computed(
  () => !!auth.user?.two_factor_bootstrap_required,
)

function apiMessage(exception: unknown): string {
  const detail = (exception as {
    response?: { data?: { detail?: string | { message?: string } } }
  }).response?.data?.detail
  return typeof detail === 'object' ? detail?.message ?? '' : detail ?? ''
}

async function submit() {
  error.value = ''
  if (!currentPassword.value || !newPassword.value || !confirmPassword.value) {
    error.value = 'أكمل كل الحقول المطلوبة'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    error.value = 'كلمة المرور الجديدة وتأكيدها غير متطابقين'
    return
  }
  if (requiresEnrollmentToken.value && enrollmentToken.value.trim().length < 20) {
    error.value = 'أدخل رمز التهيئة الذي سلّمه لك المسؤول'
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
  } catch (exception: unknown) {
    error.value = apiMessage(exception) || 'تعذر تغيير كلمة المرور. راجع الشروط وحاول مرة أخرى.'
  } finally {
    loading.value = false
  }
}

function returnToLogin() {
  window.location.replace('/login')
}
</script>

<template>
  <main class="min-h-dvh bg-owner-bg flex items-center justify-center p-4" dir="rtl">
    <section class="w-full max-w-md rounded-2xl border border-owner-border bg-owner-card p-6 shadow-2xl sm:p-8">
      <template v-if="completed">
        <div class="py-3 text-center">
          <div class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-owner-green/10 text-2xl text-owner-green">✓</div>
          <h1 class="text-xl font-bold text-owner-text">تم تغيير كلمة المرور</h1>
          <p class="mt-2 text-sm leading-6 text-owner-muted">
            سجّل الدخول بكلمة المرور الجديدة، ثم أكمل ربط تطبيق المصادقة.
          </p>
          <button class="mt-6 min-h-12 w-full rounded-xl bg-owner-green font-bold text-black" @click="returnToLogin">
            العودة لتسجيل الدخول
          </button>
        </div>
      </template>

      <form v-else class="space-y-4" @submit.prevent="submit">
        <div>
          <p class="text-xs font-black uppercase tracking-[0.18em] text-owner-green">Owner Console</p>
          <h1 class="mt-1 text-xl font-bold text-owner-text">استبدال كلمة المرور المؤقتة</h1>
          <p class="mt-2 text-sm leading-6 text-owner-muted">دي خطوة إلزامية لأول دخول. اختَر كلمة مرور خاصة بك ولا تشاركها.</p>
        </div>

        <label class="block text-xs font-semibold text-owner-muted">
          كلمة المرور المؤقتة
          <input v-model="currentPassword" :type="showPasswords ? 'text' : 'password'" autocomplete="current-password" required
            class="mt-1 min-h-12 w-full rounded-xl border border-owner-border bg-owner-bg px-4 text-owner-text outline-none focus:border-owner-green" dir="ltr">
        </label>

        <label v-if="requiresEnrollmentToken" class="block text-xs font-semibold text-owner-muted">
          رمز التهيئة الآمن
          <input v-model="enrollmentToken" type="password" autocomplete="off" required
            class="mt-1 min-h-12 w-full rounded-xl border border-owner-border bg-owner-bg px-4 font-mono text-owner-text outline-none focus:border-owner-green" dir="ltr">
        </label>

        <label class="block text-xs font-semibold text-owner-muted">
          كلمة المرور الجديدة
          <input v-model="newPassword" :type="showPasswords ? 'text' : 'password'" autocomplete="new-password" required
            class="mt-1 min-h-12 w-full rounded-xl border border-owner-border bg-owner-bg px-4 text-owner-text outline-none focus:border-owner-green" dir="ltr">
          <span class="mt-1 block text-[11px] font-normal">12 حرفًا على الأقل، وتتضمن حرفًا كبيرًا وصغيرًا ورقمًا ورمزًا.</span>
        </label>

        <label class="block text-xs font-semibold text-owner-muted">
          تأكيد كلمة المرور الجديدة
          <input v-model="confirmPassword" :type="showPasswords ? 'text' : 'password'" autocomplete="new-password" required
            class="mt-1 min-h-12 w-full rounded-xl border border-owner-border bg-owner-bg px-4 text-owner-text outline-none focus:border-owner-green" dir="ltr">
        </label>

        <label class="flex cursor-pointer items-center gap-2 text-xs text-owner-muted">
          <input v-model="showPasswords" type="checkbox" class="accent-owner-green">
          إظهار كلمات المرور أثناء الكتابة
        </label>

        <p v-if="error" role="alert" class="rounded-xl border border-owner-red/30 bg-owner-red/10 px-4 py-3 text-xs text-owner-red">{{ error }}</p>

        <button type="submit" :disabled="loading" class="min-h-12 w-full rounded-xl bg-owner-green font-bold text-black disabled:opacity-50">
          {{ loading ? 'جارٍ الحفظ...' : 'حفظ كلمة المرور الجديدة' }}
        </button>
      </form>
    </section>
  </main>
</template>
