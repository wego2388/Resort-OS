<script setup lang="ts">
// استبيان رضا الضيف بعد الإقامة — يوصل الضيف من رابط/QR فيه survey token
// حقيقي (JWT صادر من GET /analytics/reviews/survey-token/{booking_id} أو
// .../survey-token/timeshare/{visit_id})، بدون أي تسجيل دخول. نفس نمط
// BeachCheckinView.vue (شاشة مستقلة token-driven بدون auth) — الباك إند
// (POST /api/v1/analytics/reviews/submit) كان موجود وشغال بالكامل من غير
// أي واجهة تستخدمه في المشروع كله قبل الشاشة دي.
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'

const route = useRoute()
const token = computed(() => String(route.params.token ?? ''))

// نفس القيم الحقيقية الموجودة في ReviewCategory.category على الباك إند —
// مفيش أي قيمة هنا مخترعة من الفرونت.
const CATEGORIES = [
  { key: 'service',     label: 'الخدمة' },
  { key: 'cleanliness', label: 'النظافة' },
  { key: 'value',       label: 'القيمة مقابل السعر' },
  { key: 'beach',       label: 'الشاطئ' },
  { key: 'food',        label: 'الطعام' },
  { key: 'location',    label: 'الموقع' },
] as const

const guestName = ref('')
const overallRating = ref(0)
const categoryRatings = ref<Record<string, number>>(
  Object.fromEntries(CATEGORIES.map((c) => [c.key, 0])),
)
const comment = ref('')

const submitting = ref(false)
const submitted = ref(false)
const errorMsg = ref('')

function setOverall(n: number) {
  overallRating.value = n
}
function setCategory(key: string, n: number) {
  categoryRatings.value[key] = n
}

async function submit() {
  errorMsg.value = ''
  if (!token.value) {
    errorMsg.value = 'رابط الاستبيان غير صالح'
    return
  }
  if (overallRating.value < 1) {
    errorMsg.value = 'من فضلك اختر تقييمك العام أولاً'
    return
  }

  submitting.value = true
  try {
    const categories = CATEGORIES
      .filter((c) => categoryRatings.value[c.key] > 0)
      .map((c) => ({ category: c.key, rating: categoryRatings.value[c.key] }))

    await axios.post('/api/v1/analytics/reviews/submit', {
      guest_name: guestName.value || 'ضيف',
      overall_rating: overallRating.value,
      comment: comment.value || undefined,
      categories,
    }, { params: { token: token.value } })

    submitted.value = true
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail ?? 'تعذّر إرسال التقييم — حاول مرة أخرى'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div dir="rtl" class="min-h-screen bg-resort-bg flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl p-6 shadow-sm border border-resort-border max-w-md w-full">

      <!-- Thank-you state -->
      <div v-if="submitted" class="text-center py-10">
        <div class="text-5xl mb-3">🙏</div>
        <p class="font-black text-lg text-gray-900">شكرًا لتقييمك!</p>
        <p class="text-sm text-gray-400 mt-1">رأيك بيساعدنا نطوّر تجربة إقامتك القادمة</p>
      </div>

      <!-- Invalid token -->
      <div v-else-if="!token" class="text-center py-8">
        <div class="text-4xl mb-3">❌</div>
        <p class="font-bold text-gray-800">رابط الاستبيان غير صالح</p>
      </div>

      <!-- Survey form -->
      <template v-else>
        <div class="text-center mb-5">
          <div class="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center mx-auto mb-3 text-3xl">⭐</div>
          <h1 class="text-lg font-black text-gray-900">قيّم إقامتك معنا</h1>
          <p class="text-xs text-gray-400">رأيك يهمنا — يستغرق أقل من دقيقة</p>
        </div>

        <div class="space-y-5">
          <!-- Overall rating -->
          <div>
            <p class="text-sm font-bold text-gray-700 mb-2 text-center">التقييم العام *</p>
            <div class="flex justify-center gap-1">
              <button
                v-for="n in 5" :key="n" type="button"
                @click="setOverall(n)"
                class="text-3xl leading-none transition-transform hover:scale-110"
                :class="n <= overallRating ? 'text-gold' : 'text-stone-200'"
                :aria-label="`${n} نجوم`"
              >★</button>
            </div>
          </div>

          <!-- Per-category ratings -->
          <div class="space-y-2.5 bg-resort-bg rounded-xl p-4">
            <div v-for="c in CATEGORIES" :key="c.key" class="flex items-center justify-between gap-2">
              <span class="text-sm text-gray-600">{{ c.label }}</span>
              <div class="flex gap-0.5">
                <button
                  v-for="n in 5" :key="n" type="button"
                  @click="setCategory(c.key, n)"
                  class="text-lg leading-none"
                  :class="n <= categoryRatings[c.key] ? 'text-gold' : 'text-stone-300'"
                  :aria-label="`${c.label}: ${n} نجوم`"
                >★</button>
              </div>
            </div>
          </div>

          <!-- Name (optional) -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">اسمك (اختياري)</label>
            <input v-model="guestName" type="text" placeholder="اسمك"
              class="w-full border border-resort-border rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
          </div>

          <!-- Comment -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">تعليقك (اختياري)</label>
            <textarea v-model="comment" rows="3" placeholder="شاركنا رأيك..."
              class="w-full border border-resort-border rounded-xl px-4 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/30" />
          </div>

          <p v-if="errorMsg" class="text-red-600 text-xs text-center">{{ errorMsg }}</p>

          <button @click="submit" :disabled="submitting"
            class="w-full bg-primary text-white font-black py-3 rounded-xl text-base disabled:opacity-50">
            {{ submitting ? '...جاري الإرسال' : 'إرسال التقييم' }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
