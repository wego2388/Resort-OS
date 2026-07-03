<script setup lang="ts">
// TwoFactorSetupView — يغطي فجوة كانت موجودة: الباك إند (app/core/deps.py)
// يفرض 2FA إجباري على super_admin/accountant (403 "2FA_REQUIRED" على أي
// endpoint غير /auth/*) لكن الفرونت إند ما كانش فيه أي شاشة تعمل setup/enable
// أصلاً — يعني أي حساب من الدورين دول من غير 2FA مفعّل كان بيشوف كل شاشة
// فاضية/بصفر من غير أي تفسير (كل الطلبات بترجع 403 بصمت).
//
// endpoints حقيقية من app/core/kernel/auth/router.py:
//   POST /api/v1/auth/2fa/setup   → { secret, provisioning_uri, qr_url }
//   POST /api/v1/auth/2fa/enable  → { code } → 2FA enabled
//   POST /api/v1/auth/2fa/disable → { code } → 2FA disabled
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api, useAuthStore, ENDPOINTS } from '@resort-os/core'
import { AppButton, AppSpinner, useToast } from '@resort-os/ui'
import { homeRouteFor } from '../../router'

const auth = useAuthStore()
const router = useRouter()
const toast = useToast()

const isMandatory = computed(() => auth.needsTwoFactorSetup)
const isEnabled = computed(() => !!auth.user?.two_factor_enabled)

// ── Setup (not yet enabled) ──────────────────────────────────────────────
const loadingSetup = ref(false)
const setupError = ref('')
const secret = ref('')
const qrUrl = ref('')
const qrFailed = ref(false)
const code = ref('')
const enabling = ref(false)
const enableError = ref('')

async function loadSetup() {
  loadingSetup.value = true
  setupError.value = ''
  try {
    const { data } = await api.post(ENDPOINTS.auth.setup2fa)
    secret.value = data.secret
    qrUrl.value = data.qr_url
  } catch (e: any) {
    setupError.value = e?.response?.data?.detail?.message ?? e?.response?.data?.detail ?? 'تعذّر بدء إعداد التحقق بخطوتين — حاول تاني'
  } finally {
    loadingSetup.value = false
  }
}

async function submitEnable() {
  if (code.value.trim().length !== 6) {
    enableError.value = 'أدخل الكود المكوّن من 6 أرقام من تطبيق المصادقة'
    return
  }
  enabling.value = true
  enableError.value = ''
  try {
    await api.post(ENDPOINTS.auth.enable2fa, { code: code.value.trim() })
    await auth.fetchUser()
    toast.success('تم تفعيل التحقق بخطوتين بنجاح')
    router.push(homeRouteFor(auth.role))
  } catch (e: any) {
    enableError.value = e?.response?.data?.detail?.message ?? e?.response?.data?.detail ?? 'الكود غير صحيح — تأكد من تطبيق المصادقة وحاول تاني'
  } finally {
    enabling.value = false
  }
}

// ── Disable (already enabled, voluntary only) ────────────────────────────
const showDisableForm = ref(false)
const disableCode = ref('')
const disabling = ref(false)
const disableError = ref('')

async function submitDisable() {
  if (disableCode.value.trim().length !== 6) {
    disableError.value = 'أدخل الكود المكوّن من 6 أرقام من تطبيق المصادقة'
    return
  }
  disabling.value = true
  disableError.value = ''
  try {
    await api.post(ENDPOINTS.auth.disable2fa, { code: disableCode.value.trim() })
    await auth.fetchUser()
    toast.success('تم تعطيل التحقق بخطوتين')
    showDisableForm.value = false
    disableCode.value = ''
  } catch (e: any) {
    disableError.value = e?.response?.data?.detail?.message ?? e?.response?.data?.detail ?? 'الكود غير صحيح'
  } finally {
    disabling.value = false
  }
}

onMounted(() => {
  if (!isEnabled.value) loadSetup()
})
</script>

<template>
  <div dir="rtl" class="min-h-screen bg-gradient-to-br from-blue-900 via-blue-800 to-blue-700 flex items-center justify-center p-4">
    <div class="w-full max-w-md">
      <div class="text-center mb-6">
        <div class="w-16 h-16 bg-white/10 rounded-2xl flex items-center justify-center mx-auto mb-3 backdrop-blur text-3xl">🔐</div>
        <h1 class="text-2xl font-bold text-white mb-1">التحقق بخطوتين (2FA)</h1>
        <p class="text-blue-200 text-sm" v-if="isMandatory && !isEnabled">
          إجباري لهذا الدور — لازم تفعّله عشان تقدر تستخدم النظام
        </p>
      </div>

      <div class="bg-white rounded-2xl p-8 shadow-2xl">
        <!-- Already enabled -->
        <template v-if="isEnabled">
          <div class="flex items-center gap-3 bg-green-50 border border-green-200 text-green-700 rounded-xl px-4 py-3 mb-5">
            <span class="text-xl">✓</span>
            <span class="font-semibold">التحقق بخطوتين مفعّل على حسابك</span>
          </div>

          <template v-if="!isMandatory">
            <button
              v-if="!showDisableForm"
              @click="showDisableForm = true"
              class="text-sm text-red-600 font-medium hover:underline"
            >
              تعطيل التحقق بخطوتين
            </button>

            <div v-else class="space-y-3 border-t border-stone-100 pt-4 mt-1">
              <label class="block text-sm font-medium text-gray-700">أدخل كود المصادقة الحالي لتأكيد التعطيل</label>
              <input
                v-model="disableCode"
                type="text"
                inputmode="numeric"
                maxlength="6"
                placeholder="000000"
                class="w-full px-4 py-3 rounded-xl border border-stone-200 focus:outline-none focus:ring-2 focus:ring-red-500 text-center tracking-widest text-lg font-mono"
              />
              <p v-if="disableError" class="text-red-600 text-sm">{{ disableError }}</p>
              <div class="flex gap-2">
                <AppButton variant="danger" class="flex-1" :loading="disabling" @click="submitDisable">تأكيد التعطيل</AppButton>
                <AppButton variant="secondary" @click="showDisableForm = false; disableCode = ''; disableError = ''">إلغاء</AppButton>
              </div>
            </div>
          </template>
          <p v-else class="text-xs text-gray-400">
            هذا الدور يتطلب التحقق بخطوتين إجباريًا ولا يمكن تعطيله من هنا.
          </p>

          <router-link :to="homeRouteFor(auth.role)" class="block text-center text-sm text-blue-700 font-medium hover:underline mt-6">
            الرجوع للوحة التحكم
          </router-link>
        </template>

        <!-- Not enabled yet: setup flow -->
        <template v-else>
          <div v-if="loadingSetup" class="flex flex-col items-center gap-3 py-8">
            <AppSpinner size="lg" />
            <p class="text-gray-500 text-sm">جاري إعداد كود التحقق...</p>
          </div>

          <div v-else-if="setupError" class="text-center py-4">
            <p class="text-red-600 text-sm mb-4">{{ setupError }}</p>
            <AppButton variant="primary" @click="loadSetup">إعادة المحاولة</AppButton>
          </div>

          <template v-else>
            <ol class="text-sm text-gray-600 space-y-2 mb-5 list-decimal list-inside">
              <li>افتح تطبيق مصادقة على موبايلك (Google Authenticator أو Authy)</li>
              <li>اعمل مسح للكود (QR) تحت، أو أدخل المفتاح يدويًا</li>
              <li>هيظهر لك كود من 6 أرقام في التطبيق — اكتبه تحت وأكّد</li>
            </ol>

            <div class="flex justify-center mb-4" v-if="!qrFailed">
              <img
                :src="qrUrl"
                alt="امسح هذا الكود بتطبيق المصادقة"
                class="w-40 h-40 rounded-xl border border-stone-200"
                @error="qrFailed = true"
              />
            </div>
            <p v-if="qrFailed" class="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-4">
              تعذّر تحميل صورة الكود (يحتاج اتصال بالإنترنت) — أدخل المفتاح يدويًا في تطبيق المصادقة بدل المسح.
            </p>

            <div class="bg-stone-50 border border-stone-200 rounded-xl px-4 py-3 mb-5 text-center">
              <div class="text-xs text-gray-500 mb-1">المفتاح اليدوي</div>
              <div class="font-mono text-sm tracking-widest text-gray-800 select-all">{{ secret }}</div>
            </div>

            <label class="block text-sm font-medium text-gray-700 mb-1">كود التحقق</label>
            <input
              v-model="code"
              type="text"
              inputmode="numeric"
              maxlength="6"
              placeholder="000000"
              autocomplete="one-time-code"
              class="w-full px-4 py-3 rounded-xl border border-stone-200 focus:outline-none focus:ring-2 focus:ring-blue-500 text-center tracking-widest text-lg font-mono mb-2"
              @keyup.enter="submitEnable"
            />
            <p v-if="enableError" class="text-red-600 text-sm mb-3">{{ enableError }}</p>

            <button
              @click="submitEnable"
              :disabled="enabling"
              class="w-full bg-blue-700 text-white py-3 rounded-xl font-semibold hover:bg-blue-800 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {{ enabling ? 'جاري التفعيل...' : 'تفعيل التحقق بخطوتين' }}
            </button>
          </template>
        </template>

        <p class="text-center text-xs text-gray-400 mt-6">Blue Bay El Kheima — Resort OS v1.0</p>
      </div>
    </div>
  </div>
</template>
