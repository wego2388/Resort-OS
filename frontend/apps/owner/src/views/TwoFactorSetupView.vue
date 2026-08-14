<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'

type Step = 'proof' | 'loading' | 'show_qr' | 'verify' | 'recovery' | 'error'

const auth = useAuthStore()
const step = ref<Step>('proof')
const enrollmentToken = ref(auth.pendingEnrollmentToken)
const qrUrl = ref('')
const secret = ref('')
const otpCode = ref('')
const recoveryCodes = ref<string[]>([])
const codesAcknowledged = ref(false)
const copied = ref(false)
const showSecret = ref(false)
const error = ref('')
const busy = ref(false)

function apiMessage(exception: unknown, fallback: string): string {
  const detail = (exception as {
    response?: { data?: { detail?: string | { message?: string; code?: string } } }
  }).response?.data?.detail
  return (typeof detail === 'object' ? detail?.message : detail) || fallback
}

async function loadQR() {
  if (enrollmentToken.value.trim().length < 20) {
    error.value = 'أدخل رمز التهيئة الذي سلّمه لك المسؤول'
    step.value = 'proof'
    return
  }
  error.value = ''
  step.value = 'loading'
  try {
    const { data } = await api.post(ENDPOINTS.auth.setup2fa, {
      enrollment_token: enrollmentToken.value.trim(),
    })
    qrUrl.value = data.qr_url
    secret.value = data.secret
    step.value = 'show_qr'
  } catch (exception: unknown) {
    error.value = apiMessage(exception, 'تعذر تجهيز تطبيق المصادقة')
    step.value = 'error'
  }
}

async function confirmSetup() {
  if (!/^\d{6}$/.test(otpCode.value.trim())) {
    error.value = 'أدخل الرمز المكوّن من 6 أرقام'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const { data } = await api.post(ENDPOINTS.auth.enable2fa, {
      code: otpCode.value.trim(),
      enrollment_token: enrollmentToken.value.trim(),
    })
    recoveryCodes.value = data.recovery_codes ?? []
    step.value = 'recovery'
  } catch (exception: unknown) {
    error.value = apiMessage(exception, 'رمز التحقق غير صحيح أو انتهت صلاحيته')
  } finally {
    busy.value = false
  }
}

async function copyCodes() {
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

onMounted(() => {
  if (auth.user?.two_factor_enabled) {
    window.location.replace('/')
  } else if (enrollmentToken.value.trim().length >= 20) {
    loadQR()
  }
})
</script>

<template>
  <main class="min-h-dvh bg-owner-bg flex items-center justify-center p-4" dir="rtl">
    <section class="w-full max-w-lg rounded-2xl border border-owner-border bg-owner-card p-6 shadow-2xl sm:p-8">
      <div class="mb-6 text-center">
        <div class="mb-3 text-4xl">🔐</div>
        <p class="text-xs font-black uppercase tracking-[0.18em] text-owner-green">Owner Console</p>
        <h1 class="mt-1 text-xl font-bold text-owner-text">تفعيل التحقق بخطوتين</h1>
        <p class="mt-2 text-sm leading-6 text-owner-muted">احمِ حساب المالك بتطبيق مصادقة واحفظ أكواد الاسترداد في مكان آمن.</p>
      </div>

      <div v-if="step === 'loading'" class="py-10 text-center text-sm text-owner-muted animate-pulse">جارٍ التحضير...</div>

      <form v-else-if="step === 'proof'" class="space-y-4" @submit.prevent="loadQR">
        <label class="block text-xs font-semibold text-owner-muted">
          رمز التهيئة الآمن
          <input v-model="enrollmentToken" type="password" autocomplete="off" required dir="ltr"
            class="mt-1 min-h-12 w-full rounded-xl border border-owner-border bg-owner-bg px-4 font-mono text-owner-text outline-none focus:border-owner-green">
        </label>
        <p class="text-xs leading-5 text-owner-muted">استخدم الرمز المنفصل الذي ظهر مرة واحدة عند إنشاء الحساب أو استعادة 2FA.</p>
        <p v-if="error" role="alert" class="rounded-xl border border-red-900/50 bg-red-950/40 px-4 py-3 text-xs text-owner-red">{{ error }}</p>
        <button class="min-h-12 w-full rounded-xl bg-owner-green font-bold text-black">متابعة</button>
      </form>

      <div v-else-if="step === 'error'" class="text-center">
        <p role="alert" class="rounded-xl border border-red-900/50 bg-red-950/40 px-4 py-3 text-sm text-owner-red">{{ error }}</p>
        <button class="mt-4 min-h-12 w-full rounded-xl bg-owner-green font-bold text-black" @click="step = 'proof'">مراجعة رمز التهيئة</button>
      </div>

      <div v-else-if="step === 'show_qr'" class="text-center">
        <p class="mb-4 text-sm leading-6 text-owner-muted">افتح Google Authenticator أو Authy وامسح الرمز.</p>
        <div class="mx-auto mb-4 w-fit rounded-2xl bg-white p-4 shadow-lg">
          <img :src="qrUrl" alt="رمز QR للتحقق بخطوتين" class="block h-48 w-48">
        </div>
        <button class="text-xs text-owner-green underline" @click="showSecret = !showSecret">{{ showSecret ? 'إخفاء' : 'عرض' }} المفتاح اليدوي</button>
        <code v-if="showSecret" class="my-4 block select-all break-all rounded-xl border border-owner-border bg-owner-bg p-3 text-xs text-owner-text" dir="ltr">{{ secret }}</code>
        <button class="mt-5 min-h-12 w-full rounded-xl bg-owner-green font-bold text-black" @click="step = 'verify'">مسحت الرمز — متابعة</button>
      </div>

      <form v-else-if="step === 'verify'" class="space-y-4" @submit.prevent="confirmSetup">
        <label class="block text-center text-sm font-semibold text-owner-text">
          أدخل رمز التحقق من التطبيق
          <input v-model="otpCode" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="6" autofocus dir="ltr"
            class="mt-3 min-h-14 w-full rounded-xl border border-owner-border bg-owner-bg px-4 text-center font-mono text-2xl tracking-[0.5em] text-owner-text outline-none focus:border-owner-green">
        </label>
        <p v-if="error" role="alert" class="rounded-xl border border-red-900/50 bg-red-950/40 px-4 py-3 text-xs text-owner-red">{{ error }}</p>
        <button :disabled="busy" class="min-h-12 w-full rounded-xl bg-owner-green font-bold text-black disabled:opacity-50">{{ busy ? 'جارٍ التحقق...' : 'تأكيد التفعيل' }}</button>
        <button type="button" class="w-full text-xs text-owner-muted" @click="step = 'show_qr'">العودة لرمز QR</button>
      </form>

      <div v-else-if="step === 'recovery'">
        <div class="rounded-xl border border-amber-900/50 bg-amber-950/30 p-4">
          <h2 class="font-bold text-owner-amber">احفظ أكواد الاسترداد الآن</h2>
          <p class="mt-1 text-xs leading-5 text-owner-muted">كل كود يُستخدم مرة واحدة لو فقدت هاتفك. لن تظهر الأكواد مرة ثانية.</p>
        </div>
        <div class="my-5 grid grid-cols-1 gap-2 sm:grid-cols-2" dir="ltr">
          <code v-for="recoveryCode in recoveryCodes" :key="recoveryCode" class="select-all rounded-lg border border-owner-border bg-owner-bg px-3 py-2 text-center font-mono text-sm text-owner-text">{{ recoveryCode }}</code>
        </div>
        <button class="text-xs font-semibold text-owner-green underline" @click="copyCodes">{{ copied ? 'تم النسخ' : 'نسخ كل الأكواد' }}</button>
        <label class="mt-5 flex cursor-pointer items-start gap-3 rounded-xl border border-owner-border p-3 text-sm text-owner-muted">
          <input v-model="codesAcknowledged" type="checkbox" class="mt-1 accent-green-500">
          حفظت الأكواد في مكان آمن.
        </label>
        <button :disabled="!codesAcknowledged" class="mt-4 min-h-12 w-full rounded-xl bg-owner-green font-bold text-black disabled:opacity-40" @click="returnToLogin">الدخول من جديد</button>
      </div>
    </section>
  </main>
</template>
