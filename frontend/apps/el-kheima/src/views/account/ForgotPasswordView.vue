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

const email = ref('')
const loading = ref(false)
const submitted = ref(false)
const error = ref('')

async function handleSubmit() {
  if (!email.value.trim()) {
    error.value = 'أدخل البريد الإلكتروني المرتبط بحسابك'
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
  <div dir="rtl" class="min-h-screen bg-gradient-to-br from-blue-900 via-blue-800 to-blue-700 flex items-center justify-center p-4">
    <div class="w-full max-w-md">
      <div class="text-center mb-8">
        <div class="w-16 h-16 bg-white/10 rounded-2xl flex items-center justify-center mx-auto mb-3 backdrop-blur text-3xl">🔑</div>
        <h1 class="text-2xl font-bold text-white mb-1">نسيت كلمة السر؟</h1>
        <p class="text-blue-200 text-sm">هنبعتلك رابط إعادة تعيين على بريدك الإلكتروني</p>
      </div>

      <div class="bg-white rounded-2xl p-8 shadow-2xl">
        <template v-if="!submitted">
          <form @submit.prevent="handleSubmit" class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">البريد الإلكتروني</label>
              <input
                v-model="email"
                type="email"
                placeholder="you@example.com"
                autocomplete="email"
                autofocus
                class="w-full px-4 py-3 rounded-xl border border-stone-200 focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900"
              />
            </div>
            <p v-if="error" class="text-red-600 text-sm">{{ error }}</p>
            <button
              type="submit"
              :disabled="loading"
              class="w-full bg-blue-700 text-white py-3 rounded-xl font-semibold hover:bg-blue-800 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <svg v-if="loading" class="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
              </svg>
              {{ loading ? 'جاري الإرسال...' : 'إرسال رابط إعادة التعيين' }}
            </button>
          </form>
        </template>

        <!-- رسالة عامة موحّدة — تظهر سواء الإيميل مسجّل أو لأ (لا تسريب معلومات) -->
        <template v-else>
          <div class="flex items-center gap-3 bg-green-50 border border-green-200 text-green-700 rounded-xl px-4 py-3 mb-2">
            <span class="text-xl">✓</span>
            <span class="font-medium text-sm">لو البريد الإلكتروني ده مسجّل عندنا، هيوصلك رابط لإعادة تعيين كلمة السر خلال دقائق. الرابط صالح لمدة ساعتين.</span>
          </div>
        </template>

        <router-link to="/login" class="block text-center text-sm text-blue-700 font-medium hover:underline mt-6">
          الرجوع لتسجيل الدخول
        </router-link>
        <p class="text-center text-xs text-gray-400 mt-6">El Kheima Beach — Resort OS v1.0</p>
      </div>
    </div>
  </div>
</template>
