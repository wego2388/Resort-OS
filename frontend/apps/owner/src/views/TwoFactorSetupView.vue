<script setup lang="ts">
/**
 * TwoFactorSetupView — 2FA setup flow حقيقي (Decision 0004 §7b).
 * يستخدم endpoints الموجودة: POST /auth/2fa/setup → POST /auth/2fa/enable
 * خطوات:
 *  1. طلب QR code من /2fa/setup
 *  2. عرض QR + secret key
 *  3. المستخدم يدخل كود التحقق من التطبيق
 *  4. تأكيد التفعيل عبر /2fa/enable
 */
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api, useAuthStore } from '@resort-os/core'

const router = useRouter()
const auth   = useAuthStore()

type Step = 'loading' | 'show_qr' | 'verify' | 'done' | 'error'

const step       = ref<Step>('loading')
const qrCodeUrl  = ref('')
const secretKey  = ref('')
const otpCode    = ref('')
const errorMsg   = ref('')
const verifying  = ref(false)
const showSecret = ref(false)

interface SetupResponse {
  qr_code_url: string
  secret: string
}

async function loadQR() {
  step.value = 'loading'
  errorMsg.value = ''
  try {
    const res = await api.post<SetupResponse>('/api/v1/auth/2fa/setup')
    qrCodeUrl.value = res.data.qr_code_url
    secretKey.value = res.data.secret
    step.value = 'show_qr'
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } })
      .response?.data?.detail ?? 'فشل تحميل رمز QR'
    errorMsg.value = msg
    step.value = 'error'
  }
}

async function confirmSetup() {
  if (!otpCode.value || otpCode.value.length < 6) {
    errorMsg.value = 'أدخل الرمز المكوّن من 6 أرقام'
    return
  }
  verifying.value = true
  errorMsg.value = ''
  try {
    await api.post('/api/v1/auth/2fa/enable', { code: otpCode.value })
    step.value = 'done'
    // حدّث auth store
    await auth.fetchUser?.()
    setTimeout(() => router.replace('/'), 1500)
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } })
      .response?.data?.detail ?? 'رمز التحقق غير صحيح'
    errorMsg.value = msg
  } finally {
    verifying.value = false
  }
}

onMounted(loadQR)
</script>

<template>
  <div
    class="min-h-screen bg-owner-bg flex flex-col items-center justify-center px-6"
    style="padding-top: env(safe-area-inset-top); padding-bottom: env(safe-area-inset-bottom);"
  >

    <!-- Loading -->
    <template v-if="step === 'loading'">
      <div class="text-owner-muted text-sm animate-pulse">جارٍ التحضير...</div>
    </template>

    <!-- Error -->
    <template v-else-if="step === 'error'">
      <div class="text-4xl mb-4">⚠️</div>
      <p class="text-owner-red text-sm mb-6 text-center">{{ errorMsg }}</p>
      <button
        class="bg-owner-green text-black font-bold rounded-xl px-8 py-3 text-sm"
        @click="loadQR"
      >إعادة المحاولة</button>
    </template>

    <!-- Done -->
    <template v-else-if="step === 'done'">
      <div class="text-4xl mb-4">✅</div>
      <h2 class="text-owner-text font-bold mb-2 text-center">تم تفعيل التحقق بخطوتين</h2>
      <p class="text-owner-muted text-sm text-center">سيتم توجيهك الآن...</p>
    </template>

    <!-- Show QR -->
    <template v-else-if="step === 'show_qr'">
      <div class="text-4xl mb-6">🔐</div>
      <h2 class="text-owner-text font-bold mb-2 text-center">إعداد التحقق بخطوتين</h2>
      <p class="text-owner-muted text-xs mb-6 text-center max-w-xs">
        افتح تطبيق المصادقة (Google Authenticator أو Authy) وامسح رمز QR.
      </p>

      <!-- QR Code image -->
      <div class="bg-white p-4 rounded-2xl mb-4 shadow-lg">
        <img
          v-if="qrCodeUrl"
          :src="qrCodeUrl"
          alt="رمز QR للتحقق بخطوتين"
          class="w-48 h-48 block"
        />
      </div>

      <!-- Secret key toggle -->
      <button
        class="text-xs text-owner-muted underline mb-6"
        @click="showSecret = !showSecret"
      >
        {{ showSecret ? 'إخفاء' : 'عرض' }} المفتاح اليدوي
      </button>
      <div
        v-if="showSecret"
        class="bg-owner-card border border-owner-border rounded-xl px-4 py-2 text-xs font-mono text-owner-text text-center tracking-widest mb-6 select-all"
        dir="ltr"
      >
        {{ secretKey }}
      </div>

      <button
        class="bg-owner-green text-black font-bold rounded-xl px-8 py-3 text-sm w-full max-w-xs"
        @click="step = 'verify'"
      >
        تم — أدخل رمز التحقق
      </button>
    </template>

    <!-- Verify OTP -->
    <template v-else-if="step === 'verify'">
      <div class="text-4xl mb-6">🔑</div>
      <h2 class="text-owner-text font-bold mb-2 text-center">أدخل رمز التحقق</h2>
      <p class="text-owner-muted text-xs mb-6 text-center max-w-xs">
        أدخل الرمز المكوّن من 6 أرقام من تطبيق المصادقة.
      </p>

      <input
        v-model="otpCode"
        type="text"
        inputmode="numeric"
        autocomplete="one-time-code"
        maxlength="6"
        placeholder="000000"
        dir="ltr"
        class="w-full max-w-xs bg-owner-card border border-owner-border rounded-xl px-4 py-3 text-owner-text text-center text-2xl tracking-[0.5em] outline-none focus:border-owner-green mb-4"
        :disabled="verifying"
        @keyup.enter="confirmSetup"
      />

      <div
        v-if="errorMsg"
        class="text-xs text-owner-red bg-red-950/40 border border-red-900/50 rounded-xl px-4 py-3 mb-4 w-full max-w-xs text-center"
        role="alert"
      >
        {{ errorMsg }}
      </div>

      <button
        class="bg-owner-green text-black font-bold rounded-xl px-8 py-3 text-sm w-full max-w-xs disabled:opacity-50"
        :disabled="verifying || otpCode.length < 6"
        @click="confirmSetup"
      >
        <span v-if="verifying">جارٍ التحقق...</span>
        <span v-else>تأكيد التفعيل</span>
      </button>

      <button
        class="text-xs text-owner-muted mt-4"
        @click="step = 'show_qr'"
      >
        العودة للرمز
      </button>
    </template>

  </div>
</template>
