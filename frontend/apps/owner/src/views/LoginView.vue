<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@resort-os/core'

const auth   = useAuthStore()
const router = useRouter()

// نفس مفتاح التخزين المستخدم في تطبيق الموظفين (el-kheima) عمدًا — لو نفس
// الشخص بيستخدم البريد على الاتنين على نفس الجهاز، بيتذكّره مرة واحدة بس.
const REMEMBERED_EMAIL_KEY = 'el-kheima:remembered-username'

const email    = ref(localStorage.getItem(REMEMBERED_EMAIL_KEY) ?? '')
const password = ref('')
const otp      = ref('')
const recoveryCode = ref('')
const enrollmentToken = ref('')
const error    = ref('')
const loading  = ref(false)
const needsOtp = ref(false)
const useRecoveryCode = ref(false)
const needsEnrollmentToken = ref(false)
const showPassword = ref(false)
const rememberMe = ref(false)
const capsLockOn = ref(false)
const shakeError = ref(false)
let shakeTimeout: ReturnType<typeof setTimeout> | null = null

const passwordInputRef = ref<HTMLInputElement | null>(null)
const otpInputRef = ref<HTMLInputElement | null>(null)

const otpSecondsRemaining = ref(30)
let otpCountdownInterval: ReturnType<typeof setInterval> | null = null

function _tickOtpCountdown() {
  otpSecondsRemaining.value = 30 - (Math.floor(Date.now() / 1000) % 30)
}
function _startOtpCountdown() {
  _tickOtpCountdown()
  if (otpCountdownInterval) clearInterval(otpCountdownInterval)
  otpCountdownInterval = setInterval(_tickOtpCountdown, 1000)
}
function _stopOtpCountdown() {
  if (otpCountdownInterval) {
    clearInterval(otpCountdownInterval)
    otpCountdownInterval = null
  }
}

watch(needsOtp, async (isNeeded) => {
  if (isNeeded) {
    _startOtpCountdown()
    await nextTick()
    otpInputRef.value?.focus()
  } else {
    _stopOtpCountdown()
  }
})

watch(useRecoveryCode, (enabled) => {
  if (enabled) _stopOtpCountdown()
  else if (needsOtp.value) _startOtpCountdown()
})

onBeforeUnmount(() => {
  _stopOtpCountdown()
  if (shakeTimeout) clearTimeout(shakeTimeout)
})

onMounted(() => {
  if (email.value) passwordInputRef.value?.focus()
})

function checkCapsLock(event: KeyboardEvent) {
  capsLockOn.value = event.getModifierState?.('CapsLock') ?? false
}

function triggerShake() {
  shakeError.value = false
  requestAnimationFrame(() => {
    shakeError.value = true
  })
  if (shakeTimeout) clearTimeout(shakeTimeout)
  shakeTimeout = setTimeout(() => {
    shakeError.value = false
  }, 500)
}

function handleOtpPaste(event: ClipboardEvent) {
  const pasted = event.clipboardData?.getData('text') ?? ''
  const digits = pasted.replace(/\D/g, '').slice(0, 6)
  if (digits.length === 6) {
    event.preventDefault()
    otp.value = digits
    nextTick(() => submit())
  }
}

const otpProgressPercent = computed(() => (otpSecondsRemaining.value / 30) * 100)

async function submit() {
  error.value = ''
  if (needsOtp.value) {
    if (useRecoveryCode.value && recoveryCode.value.replace(/[^a-z0-9]/gi, '').length !== 24) {
      error.value = 'أدخل كود الاسترداد الكامل'
      return
    }
    if (!useRecoveryCode.value && otp.value.trim().length !== 6) {
      error.value = 'أدخل رمز التحقق المكوّن من 6 أرقام'
      return
    }
  }
  if (needsEnrollmentToken.value && enrollmentToken.value.trim().length < 20) {
    error.value = 'أدخل رمز التهيئة الذي سلّمه لك المسؤول'
    return
  }
  loading.value = true
  try {
    await auth.login(
      email.value,
      password.value,
      !useRecoveryCode.value ? otp.value.trim() || undefined : undefined,
      useRecoveryCode.value ? recoveryCode.value.trim() || undefined : undefined,
      enrollmentToken.value.trim() || undefined,
      rememberMe.value,
    )
    localStorage.setItem(REMEMBERED_EMAIL_KEY, email.value.trim())
    await nextTick()
    if (auth.needsPasswordChange) router.replace('/change-temporary-password')
    else if (auth.needsTwoFactorSetup) router.replace('/2fa-setup')
    else router.replace('/')
  } catch (e: unknown) {
    triggerShake()
    const detail = (e as { response?: { data?: { detail?: { code?: string } | string } } })
      .response?.data?.detail
    const code = typeof detail === 'object' ? detail?.code : ''
    if (code === 'OTP_REQUIRED' || code === '2FA_REQUIRED' || code === '2FA_CODE_REQUIRED') {
      needsOtp.value = true
      error.value = 'أدخل رمز التحقق من تطبيق المصادقة'
    } else if (code === '2FA_CODE_INVALID') {
      needsOtp.value = true
      error.value = useRecoveryCode.value
        ? 'كود الاسترداد غير صحيح أو تم استخدامه من قبل'
        : 'رمز التحقق غير صحيح أو انتهت صلاحيته'
    } else if (
      code === '2FA_ENROLLMENT_TOKEN_REQUIRED'
      || code === '2FA_ENROLLMENT_TOKEN_INVALID'
      || code === '2FA_ENROLLMENT_TOKEN_EXPIRED'
      || code === '2FA_ENROLLMENT_NOT_PROVISIONED'
    ) {
      needsEnrollmentToken.value = true
      error.value = code === '2FA_ENROLLMENT_NOT_PROVISIONED'
        ? 'الحساب يحتاج رمز تهيئة جديد من السوبر أدمن'
        : 'رمز التهيئة مفقود أو غير صحيح أو انتهت صلاحيته'
    } else if (code === 'ACCOUNT_LOCKED' || (e as { response?: { status?: number } }).response?.status === 423) {
      error.value = 'الحساب مقفول مؤقتًا بعد محاولات فاشلة. انتظر المدة الموضحة أو اطلب من السوبر أدمن فك القفل.'
    } else if ((e as { response?: { status?: number } }).response?.status === 429) {
      error.value = 'محاولات دخول كثيرة من شبكة المنتجع. انتظر قليلًا ثم أعد المحاولة.'
    } else if (code === 'ACCOUNT_INACTIVE' || detail === 'Inactive account') {
      error.value = 'الحساب غير نشط. تواصل مع السوبر أدمن.'
    } else {
      error.value = typeof detail === 'string' ? detail : 'بيانات الدخول غير صحيحة'
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div
    class="relative min-h-screen overflow-hidden bg-owner-bg flex flex-col items-center justify-center px-6"
    style="padding-top: env(safe-area-inset-top); padding-bottom: env(safe-area-inset-bottom);"
  >
    <!-- خلفية زخرفية هادئة — بنفس روح تحسين صفحة دخول الموظفين، لكن بألوان
    لوحة المالك نفسها (أخضر/كهرماني على أسود تقريبًا) بدل نسخ التدرج الأزرق
    حرفيًا. توهج خفيف جدًا (opacity منخفضة) عشان يفضل شكل "لوحة تحكم" هادئ
    ورسمي، مش تصميم مزدحم زي شاشات التشغيل اليومي. -->
    <div class="pointer-events-none absolute inset-0" aria-hidden="true">
      <div class="absolute -top-24 -end-24 w-96 h-96 rounded-full opacity-[0.08] blur-3xl motion-safe:animate-pulse" style="background:radial-gradient(circle, #22C55E, transparent 70%)" />
      <div class="absolute -bottom-32 -start-32 w-[28rem] h-[28rem] rounded-full opacity-[0.08] blur-3xl motion-safe:animate-pulse" style="background:radial-gradient(circle, #F59E0B, transparent 70%)" />
      <div class="absolute inset-0 opacity-[0.025]" style="background-image:radial-gradient(circle, #fff 1px, transparent 1px);background-size:28px 28px" />
    </div>

    <!-- Logo area -->
    <div class="relative mb-8 text-center">
      <div class="w-24 h-24 bg-white rounded-3xl flex items-center justify-center mx-auto mb-4 shadow-2xl ring-1 ring-white/10 p-3">
        <img src="/icon-512.png" alt="El Kheima Beach Resort" class="w-full h-full object-contain" />
      </div>
      <p class="text-owner-green text-xs font-black tracking-[0.3em] uppercase mb-1.5">Owner Console</p>
      <p class="text-owner-muted text-sm">لوحة تحكم المنتجع</p>
    </div>

    <!-- Login form -->
    <form
      class="relative w-full max-w-sm space-y-4 bg-owner-card border border-owner-border rounded-2xl p-6 shadow-2xl transition-transform"
      :class="{ 'animate-shake': shakeError }"
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
          class="w-full bg-owner-bg border border-owner-border rounded-xl px-4 py-3 text-owner-text text-sm outline-none focus:border-owner-green transition-colors"
          :disabled="loading"
          required
        />
      </div>

      <div>
        <label class="block text-xs font-semibold text-owner-muted mb-1" for="password">
          كلمة المرور
        </label>
        <div class="relative">
          <input
            id="password"
            ref="passwordInputRef"
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="current-password"
            dir="ltr"
            class="w-full bg-owner-bg border border-owner-border rounded-xl px-4 py-3 pe-11 text-owner-text text-sm outline-none focus:border-owner-green transition-colors"
            :disabled="loading"
            required
            @keydown="checkCapsLock"
            @keyup="checkCapsLock"
          />
          <button
            type="button"
            class="absolute inset-y-0 end-0 flex items-center px-3 text-owner-muted hover:text-owner-text transition-colors"
            aria-label="إظهار/إخفاء كلمة المرور"
            tabindex="-1"
            @click="showPassword = !showPassword"
          >
            <svg v-if="showPassword" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.774 3.162 10.065 7.498a10.522 10.522 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
            </svg>
            <svg v-else class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
              <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
        </div>
        <p v-if="capsLockOn" class="mt-1.5 flex items-center gap-1 text-xs text-owner-amber">
          <svg class="w-3.5 h-3.5 shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd" /></svg>
          زر Caps Lock مفعّل
        </p>
      </div>

      <label v-if="!needsOtp" class="flex items-center gap-2 text-xs text-owner-muted cursor-pointer select-none">
        <input
          v-model="rememberMe"
          type="checkbox"
          class="rounded border-owner-border text-owner-green focus:ring-owner-green"
        />
        تذكرني على هذا الجهاز
      </label>

      <!-- OTP — يظهر فقط لو احتاج -->
      <div v-if="needsOtp">
        <div class="flex items-center justify-between mb-1">
          <label class="block text-xs font-semibold text-owner-muted" :for="useRecoveryCode ? 'recovery-code' : 'otp'">
            {{ useRecoveryCode ? 'كود الاسترداد' : 'رمز التحقق (2FA)' }}
          </label>
          <span v-if="!useRecoveryCode" class="text-xs text-owner-muted tabular-nums">يتجدد خلال {{ otpSecondsRemaining }} ث</span>
        </div>
        <input
          v-if="!useRecoveryCode"
          id="otp"
          ref="otpInputRef"
          v-model="otp"
          type="text"
          inputmode="numeric"
          autocomplete="one-time-code"
          maxlength="6"
          dir="ltr"
          class="w-full bg-owner-bg border border-owner-border rounded-xl px-4 py-3 text-owner-text text-sm text-center tracking-widest font-mono outline-none focus:border-owner-green transition-colors"
          :disabled="loading"
          @paste="handleOtpPaste"
        />
        <input
          v-else
          id="recovery-code"
          v-model="recoveryCode"
          type="text"
          autocomplete="one-time-code"
          dir="ltr"
          class="w-full bg-owner-bg border border-owner-border rounded-xl px-4 py-3 text-owner-text text-sm text-center tracking-wider font-mono outline-none focus:border-owner-green transition-colors"
          :disabled="loading"
        />
        <div v-if="!useRecoveryCode" class="mt-1.5 h-1 w-full rounded-full bg-owner-border overflow-hidden" aria-hidden="true">
          <div
            class="h-full rounded-full bg-owner-green transition-[width] duration-1000 ease-linear"
            :class="{ 'bg-owner-red': otpSecondsRemaining <= 5 }"
            :style="{ width: `${otpProgressPercent}%` }"
          />
        </div>
        <button type="button" class="mt-2 text-xs text-owner-green underline" @click="useRecoveryCode = !useRecoveryCode">
          {{ useRecoveryCode ? 'استخدام تطبيق المصادقة' : 'استخدام كود استرداد بدلًا منه' }}
        </button>
      </div>

      <div v-if="needsEnrollmentToken">
        <label class="block text-xs font-semibold text-owner-muted mb-1" for="enrollment-token">
          رمز التهيئة الآمن
        </label>
        <input
          id="enrollment-token"
          v-model="enrollmentToken"
          type="password"
          autocomplete="off"
          dir="ltr"
          class="w-full bg-owner-bg border border-owner-border rounded-xl px-4 py-3 text-owner-text text-sm font-mono outline-none focus:border-owner-green transition-colors"
          :disabled="loading"
        />
        <p class="mt-1 text-[11px] text-owner-muted">رمز منفصل يظهر للمسؤول مرة واحدة، وليس كلمة المرور.</p>
      </div>

      <!-- Error -->
      <div
        v-if="error"
        class="text-xs text-owner-red bg-owner-red/10 border border-owner-red/30 rounded-xl px-4 py-3"
        role="alert"
      >
        {{ error }}
      </div>

      <!-- Submit -->
      <button
        type="submit"
        class="w-full bg-owner-green text-black font-bold rounded-xl py-3.5 text-sm transition-opacity active:opacity-80 disabled:opacity-50 flex items-center justify-center gap-2"
        :disabled="loading || !email || !password"
      >
        <svg v-if="loading" class="motion-safe:animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
        </svg>
        <span v-if="loading">جارٍ الدخول...</span>
        <span v-else>دخول</span>
      </button>
    </form>

    <p class="relative text-center text-xs text-owner-muted mt-6">El Kheima Beach Resort · Owner Console</p>
  </div>
</template>

<style scoped>
@keyframes shake {
  10%, 90% { transform: translateX(-1px); }
  20%, 80% { transform: translateX(2px); }
  30%, 50%, 70% { transform: translateX(-4px); }
  40%, 60% { transform: translateX(4px); }
}
.animate-shake {
  animation: shake 0.5s cubic-bezier(.36,.07,.19,.97) both;
}
@media (prefers-reduced-motion: reduce) {
  .animate-shake {
    animation: none;
  }
}
</style>
