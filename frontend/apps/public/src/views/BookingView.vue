<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const router = useRouter()
const loading = ref(false)
const error = ref('')
const form = ref({
  full_name: '', email: '', phone: '', nationality: '',
  check_in: '', check_out: '', adults: 2, children: 0,
  room_type: '', special_requests: ''
})

const roomTypes = [
  { value: 'standard', label: 'غرفة قياسية' },
  { value: 'sea_view', label: 'غرفة إطلالة بحر' },
  { value: 'suite', label: 'جناح فاخر' },
  { value: 'chalet', label: 'شاليه خاص' },
]

async function submitInquiry() {
  if (!form.value.full_name || !form.value.phone || !form.value.check_in) {
    error.value = 'الرجاء ملء الاسم ورقم الهاتف وتاريخ الوصول'; return
  }
  loading.value = true; error.value = ''
  try {
    await axios.post('/api/v1/hub/contact', {
      name: form.value.full_name, email: form.value.email,
      phone: form.value.phone, message: `حجز فندق: ${form.value.check_in} → ${form.value.check_out} | ${form.value.adults} بالغ + ${form.value.children} أطفال | ${roomTypes.find(r => r.value === form.value.room_type)?.label ?? ''} | ${form.value.special_requests}`,
      type: 'booking_inquiry',
    })
    router.push('/confirmation')
  } catch(e: any) {
    error.value = e?.response?.data?.detail ?? 'حدث خطأ، يرجى المحاولة مرة أخرى'
    loading.value = false
  }
}
</script>

<template>
  <div dir="rtl" class="min-h-screen bg-stone-50">
    <header class="bg-blue-900 text-white px-4 py-4 shadow-md">
      <RouterLink to="/" class="text-blue-200 text-sm mb-1 block">← الرئيسية</RouterLink>
      <h1 class="text-2xl font-black">استفسار حجز</h1>
    </header>

    <div class="max-w-lg mx-auto p-4 py-6">
      <div class="bg-white rounded-2xl border border-stone-200 p-6 shadow-sm">
        <div class="space-y-4">
          <div class="grid grid-cols-2 gap-3">
            <div class="col-span-2">
              <label class="block text-sm font-medium text-gray-700 mb-1">الاسم الكامل *</label>
              <input v-model="form.full_name" type="text" placeholder="محمد أحمد"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">رقم الهاتف *</label>
              <input v-model="form.phone" type="tel" placeholder="010xxxxxxxx" dir="ltr"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500 text-left"/>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">البريد الإلكتروني</label>
              <input v-model="form.email" type="email" placeholder="email@example.com" dir="ltr"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500 text-left"/>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">تاريخ الوصول *</label>
              <input v-model="form.check_in" type="date"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">تاريخ المغادرة</label>
              <input v-model="form.check_out" type="date"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">البالغون</label>
              <input v-model.number="form.adults" type="number" min="1" max="10"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">الأطفال</label>
              <input v-model.number="form.children" type="number" min="0" max="10"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
            </div>
            <div class="col-span-2">
              <label class="block text-sm font-medium text-gray-700 mb-1">نوع الغرفة</label>
              <select v-model="form.room_type"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="">اختر نوع الغرفة</option>
                <option v-for="r in roomTypes" :key="r.value" :value="r.value">{{ r.label }}</option>
              </select>
            </div>
            <div class="col-span-2">
              <label class="block text-sm font-medium text-gray-700 mb-1">طلبات خاصة</label>
              <textarea v-model="form.special_requests" rows="3" placeholder="أي طلبات أو ملاحظات..."
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none text-sm"/>
            </div>
          </div>

          <div v-if="error" class="bg-red-50 text-red-600 px-4 py-2.5 rounded-xl text-sm">{{ error }}</div>

          <button @click="submitInquiry" :disabled="loading"
            class="w-full py-4 bg-blue-700 text-white rounded-2xl font-black text-lg hover:bg-blue-800 disabled:opacity-50 transition-colors">
            {{ loading ? 'جاري الإرسال...' : 'إرسال الاستفسار' }}
          </button>
          <p class="text-center text-xs text-gray-400">سيتم التواصل معك خلال 24 ساعة</p>
        </div>
      </div>
    </div>
  </div>
</template>
