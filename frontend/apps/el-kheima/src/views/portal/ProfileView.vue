<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'

const h = { Authorization: `Bearer ${localStorage.getItem('access_token')}` }

interface Profile {
  id: number; employee_code: string; full_name: string; email?: string
  phone?: string; position: string; department?: string; hire_date: string
}

const profile = ref<Profile | null>(null)
const loading = ref(false)
const pwForm = ref({ current_password: '', new_password: '', confirm_password: '' })
const pwMsg = ref('')
const pwError = ref('')
const pwLoading = ref(false)

async function fetchProfile() {
  loading.value = true
  try {
    const { data } = await axios.get('/api/v1/hr/me/profile', { headers: h })
    profile.value = data
  } catch(e) { console.error(e) }
  finally { loading.value = false }
}

async function changePassword() {
  if (!pwForm.value.current_password || !pwForm.value.new_password) {
    pwError.value = 'الرجاء ملء جميع الحقول'; return
  }
  if (pwForm.value.new_password !== pwForm.value.confirm_password) {
    pwError.value = 'كلمتا المرور غير متطابقتان'; return
  }
  if (pwForm.value.new_password.length < 8) {
    pwError.value = 'كلمة المرور يجب أن تكون 8 أحرف على الأقل'; return
  }
  pwLoading.value = true; pwError.value = ''
  try {
    await axios.post('/api/v1/auth/change-password', {
      current_password: pwForm.value.current_password,
      new_password: pwForm.value.new_password,
    }, { headers: h })
    pwMsg.value = 'تم تغيير كلمة المرور بنجاح ✓'
    pwForm.value = { current_password: '', new_password: '', confirm_password: '' }
    setTimeout(() => pwMsg.value = '', 4000)
  } catch(e: any) {
    pwError.value = e?.response?.data?.detail ?? 'كلمة المرور الحالية غير صحيحة'
  } finally { pwLoading.value = false }
}

onMounted(fetchProfile)
</script>

<template>
  <div dir="rtl" class="space-y-4">
    <h2 class="font-bold text-gray-900 text-lg">ملفي الشخصي</h2>

    <div v-if="loading" class="text-center py-12 text-gray-400">جاري التحميل...</div>

    <template v-else-if="profile">
      <!-- Profile card -->
      <div class="bg-white rounded-2xl border border-stone-200 p-6 shadow-sm">
        <div class="flex items-center gap-4 mb-5">
          <div class="w-16 h-16 bg-blue-100 rounded-2xl flex items-center justify-center text-2xl font-black text-blue-700 flex-shrink-0">
            {{ profile.full_name.charAt(0) }}
          </div>
          <div>
            <div class="font-bold text-xl text-gray-900">{{ profile.full_name }}</div>
            <div class="text-gray-500 text-sm">
              {{ profile.position }}
              <span v-if="profile.department"> — {{ profile.department }}</span>
            </div>
            <div class="text-xs text-gray-400 mt-0.5">{{ profile.employee_code }}</div>
          </div>
        </div>

        <div class="space-y-3 border-t border-stone-100 pt-4">
          <div v-if="profile.email" class="flex items-center justify-between text-sm">
            <span class="text-gray-500 flex items-center gap-1.5">📧 البريد الإلكتروني</span>
            <span class="font-medium text-gray-900">{{ profile.email }}</span>
          </div>
          <div v-if="profile.phone" class="flex items-center justify-between text-sm">
            <span class="text-gray-500 flex items-center gap-1.5">📞 الهاتف</span>
            <span class="font-medium text-gray-900">{{ profile.phone }}</span>
          </div>
          <div v-if="profile.hire_date" class="flex items-center justify-between text-sm">
            <span class="text-gray-500 flex items-center gap-1.5">📅 تاريخ التعيين</span>
            <span class="font-medium text-gray-900">
              {{ new Date(profile.hire_date).toLocaleDateString('ar-EG', { year: 'numeric', month: 'long', day: 'numeric' }) }}
            </span>
          </div>
        </div>
      </div>

      <!-- Change password -->
      <div class="bg-white rounded-2xl border border-stone-200 p-6 shadow-sm">
        <h3 class="font-bold text-gray-900 mb-4">تغيير كلمة المرور</h3>
        <div class="space-y-3">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">كلمة المرور الحالية</label>
            <input v-model="pwForm.current_password" type="password" placeholder="••••••••"
              class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">كلمة المرور الجديدة</label>
            <input v-model="pwForm.new_password" type="password" placeholder="8 أحرف على الأقل"
              class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">تأكيد كلمة المرور</label>
            <input v-model="pwForm.confirm_password" type="password" placeholder="••••••••"
              class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
          </div>
          <div v-if="pwMsg" class="bg-green-100 text-green-700 px-3 py-2 rounded-lg text-sm font-medium">{{ pwMsg }}</div>
          <div v-if="pwError" class="bg-red-50 text-red-600 px-3 py-2 rounded-lg text-sm">{{ pwError }}</div>
          <button @click="changePassword" :disabled="pwLoading"
            class="w-full py-2.5 bg-blue-700 text-white rounded-xl font-bold hover:bg-blue-800 disabled:opacity-50 transition-colors">
            {{ pwLoading ? 'جاري الحفظ...' : 'حفظ كلمة المرور' }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
