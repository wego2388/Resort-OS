<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAuthStore } from '@resort-os/core'
import { useToast } from '@resort-os/ui'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import LanguageSwitcher from '../../components/LanguageSwitcher.vue'

const auth = useAuthStore()
const toast = useToast()
const router = useRouter()
const { t } = useI18n()

// تذكّر آخر username على نفس الجهاز — تحسين راحة بس (مفيش أي بيانات حساسة)،
// مخزّن محليًا ومنفصل تمامًا عن "تذكرني على هذا الجهاز" (rememberMe تحت،
// اللي بتتحكم في عمر جلسة الدخول نفسها على الباك إند).
const REMEMBERED_USERNAME_KEY = 'el-kheima:remembered-username'

const username = ref(localStorage.getItem(REMEMBERED_USERNAME_KEY) ?? '')
const password = ref('')
const loading = ref(false)
const showPassword = ref(false)
const rememberMe = ref(false)
const capsLockOn = ref(false)
const shakeError = ref(false)
let shakeTimeout: ReturnType<typeof setTimeout> | null = null

const passwordInputRef = ref<HTMLInputElement | null>(null)
const otpInputRef = ref<HTMLInputElement | null>(null)

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

// عدّاد ثواني حتى انتهاء صلاحية كود TOTP الحالي — إعلامي بس (السيرفر هو
// اللي بيتحقق فعليًا)، بيساعد المستخدم يعرف لو الوقت قرّب يخلص قبل ما
// يبعت كود هيترفض. TOTP بيتجدد كل 30 ثانية على حدود الـUNIX epoch الثابتة.
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

watch(useRecoveryCode, async () => {
  // التبديل بين كود المصادقة وكود الاسترداد — العدّاد معناه بس لكود TOTP.
  if (useRecoveryCode.value) _stopOtpCountdown()
  else if (needsOtp.value) _startOtpCountdown()
})

onBeforeUnmount(() => {
  _stopOtpCountdown()
  if (shakeTimeout) clearTimeout(shakeTimeout)
})

function checkCapsLock(event: KeyboardEvent) {
  capsLockOn.value = event.getModifierState?.('CapsLock') ?? false
}

function triggerShake() {
  shakeError.value = false
  // إعادة تشغيل الأنيميشن لازم يبدأ من false عشان لو المستخدم غلط
  // مرتين متتاليتين الحركة تتكرر (Vue مش بيعمل re-render لو نفس القيمة).
  requestAnimationFrame(() => {
    shakeError.value = true
  })
  if (shakeTimeout) clearTimeout(shakeTimeout)
  shakeTimeout = setTimeout(() => {
    shakeError.value = false
  }, 500)
}

// لصق كود TOTP كامل (6 أرقام) — من مدير كلمات مرور أو تطبيق مصادقة على
// نفس الجهاز — بيملأ الحقل ويبعت الفورم تلقائيًا بدل ما المستخدم يضغط
// Enter بنفسه.
function handleOtpPaste(event: ClipboardEvent) {
  const pasted = event.clipboardData?.getData('text') ?? ''
  const digits = pasted.replace(/\D/g, '').slice(0, 6)
  if (digits.length === 6) {
    event.preventDefault()
    otpCode.value = digits
    nextTick(() => handleLogin())
  }
}

const otpProgressPercent = computed(() => (otpSecondsRemaining.value / 30) * 100)

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
      rememberMe.value,
    )
    // بعد نجاح فعلي بس — تذكّر الـusername للمرة الجاية على نفس الجهاز.
    localStorage.setItem(REMEMBERED_USERNAME_KEY, username.value.trim())
    // nextTick: نضمن إن Vue flush الـ reactive state (activeBranchId،
    // needsPasswordChange، needsTwoFactorSetup) اللي اتحدثوا في
    // _applyBootstrap() قبل ما الـ router guard يقرأهم. بدون ده، الـ guard
    // كان ممكن يقرأ القيم القديمة (branchId=null) ويوجّه الكاشير لـ
    // /select-branch بدل homeRoute الصحيح — freeze ظاهري للمستخدم.
    await nextTick()
    if (auth.needsPasswordChange) {
      router.push('/change-temporary-password')
    } else if (auth.needsTwoFactorSetup) {
      router.push('/2fa-setup')
    } else {
      router.push('/')
    }
  } catch (e: any) {
    triggerShake()
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

onMounted(() => {
  // لو الـusername اتملى تلقائيًا من الجلسة السابقة، الفوكس الأول يبقى
  // على كلمة المرور مباشرة بدل الاسم اللي المستخدم مش هيلمسه أصلاً.
  if (username.value) passwordInputRef.value?.focus()
})
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
      <div
        class="bg-white dark:bg-surface dark:border dark:border-border rounded-2xl p-8 shadow-2xl"
        :class="{ 'motion-safe:animate-shake': shakeError }"
      >
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
            <div class="relative">
              <input
                id="login-password"
                ref="passwordInputRef"
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                placeholder="••••••••"
                autocomplete="current-password"
                class="w-full px-4 py-3 pe-11 rounded-xl border border-stone-200 dark:border-border dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900 dark:placeholder-gray-500"
                @keydown="checkCapsLock"
                @keyup="checkCapsLock"
              />
              <button
                type="button"
                class="absolute inset-y-0 end-0 flex items-center px-3 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                :aria-label="t(showPassword ? 'backoffice.login.hidePassword' : 'backoffice.login.showPassword')"
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
            <p v-if="capsLockOn" class="mt-1.5 flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
              <svg class="w-3.5 h-3.5 shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd" /></svg>
              {{ t('backoffice.login.capsLockWarning') }}
            </p>
          </div>
          <div class="flex items-center justify-between -mt-2">
            <label v-if="!needsOtp && !needsEnrollmentToken" class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 cursor-pointer select-none">
              <input
                v-model="rememberMe"
                type="checkbox"
                class="rounded border-stone-300 dark:border-border text-blue-600 focus:ring-blue-500"
              />
              {{ t('backoffice.login.rememberMe') }}
            </label>
            <router-link
              v-if="!needsOtp && !needsEnrollmentToken"
              to="/forgot-password"
              class="text-sm text-blue-700 hover:underline dark:text-blue-300"
            >
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
            <p class="text-xs text-gray-500 dark:text-gray-300 mt-1">{{ t('backoffice.login.enrollmentTokenHint') }}</p>
          </div>
          <div v-if="needsOtp">
            <div class="flex items-center justify-between mb-1">
              <label :for="useRecoveryCode ? 'login-recovery-code' : 'login-totp-code'" class="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {{ t(useRecoveryCode ? 'backoffice.login.recoveryCode' : 'backoffice.login.twoFaCode') }}
              </label>
              <span v-if="!useRecoveryCode" class="text-xs text-gray-400 dark:text-gray-300 tabular-nums">
                {{ t('backoffice.login.twoFaExpiresIn', { seconds: otpSecondsRemaining }) }}
              </span>
            </div>
            <input
              v-if="!useRecoveryCode"
              id="login-totp-code"
              ref="otpInputRef"
              v-model="otpCode"
              type="text"
              inputmode="numeric"
              maxlength="6"
              :placeholder="t('backoffice.login.twoFaPlaceholder')"
              autocomplete="one-time-code"
              class="w-full px-4 py-3 rounded-xl border border-stone-200 dark:border-border dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 text-center tracking-widest text-lg font-mono text-gray-900"
              @paste="handleOtpPaste"
            />
            <!-- شريط تقدّم بسيط يعكس وقت انتهاء صلاحية كود TOTP الحالي (30 ثانية) —
            إعلامي بس، السيرفر هو مصدر الحقيقة الوحيد للتحقق. -->
            <div v-if="!useRecoveryCode" class="mt-1.5 h-1 w-full rounded-full bg-stone-100 dark:bg-gray-700 overflow-hidden" aria-hidden="true">
              <div
                class="h-full rounded-full bg-blue-500 transition-[width] duration-1000 ease-linear"
                :class="{ 'bg-amber-500': otpSecondsRemaining <= 5 }"
                :style="{ width: `${otpProgressPercent}%` }"
              />
            </div>
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

<style scoped>
/* اهتزاز بسيط عند فشل تسجيل الدخول — feedback بصري فوري بجانب الـtoast،
مش بديل عنه. prefers-reduced-motion (motion-safe:) بيلغي الحركة بالكامل. */
@keyframes shake {
  10%, 90% { transform: translateX(-1px); }
  20%, 80% { transform: translateX(2px); }
  30%, 50%, 70% { transform: translateX(-4px); }
  40%, 60% { transform: translateX(4px); }
}
.motion-safe\:animate-shake {
  animation: shake 0.5s cubic-bezier(.36,.07,.19,.97) both;
}
@media (prefers-reduced-motion: reduce) {
  .motion-safe\:animate-shake {
    animation: none;
  }
}
</style>
