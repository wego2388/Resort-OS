<script setup lang="ts">
/**
 * استبيان رضا الضيف بعد الإقامة — يوصل الضيف من رابط/QR فيه survey token
 * حقيقي (JWT صادر من GET /analytics/reviews/survey-token/{booking_id} أو
 * .../survey-token/timeshare/{visit_id})، بدون أي تسجيل دخول. نفس نمط
 * BeachCheckinView.vue (شاشة مستقلة token-driven بدون auth).
 *
 * الرابط بيتبعت للضيف بعد زيارة حقيقية فقط (staff بيولّده يدويًا من شاشة
 * تايم شير/PMS) — عمداً مش لينك عام مفتوح على الموقع، عشان يمنع تقييمات
 * وهمية تأثر على المتوسط المنشور وعلى إنشاء CRM complaint التلقائي عند
 * تقييم ≤ 2 (راجع services.submit_review).
 *
 * محتوى النسخة الخاصة بالتايم شير (نظافة الوحدة/الاستقبال/نظافة الشاطئ/
 * توافر المرافق + سؤالين مفتوحين) مأخوذ ومُحسَّن من نموذج الاستطلاع الورقي
 * الحالي (2026-07-06) — الفئات الست العامة (service/cleanliness/value/beach/
 * food/location) فضلت زي ما هي لحجوزات الفندق العادية، الاتنين بيستخدموا
 * نفس الـ endpoint ونفس الموديل (ReviewCategory.category نص حر بدون قيد،
 * فمفيش أي تعديل باك إند مطلوب).
 *
 * ref_type (booking | timeshare_visit) بيتقرا من الـ JWT payload نفسه على
 * الفرونت إند بدون أي تحقق من التوقيع — ده آمن لأنه مُستخدَم للعرض بس
 * (اختيار نص/فئات الفورم)، مش لأي قرار أمني؛ التحقق الحقيقي بيحصل سيرفر-
 * سايد وقت الإرسال الفعلي (verify_survey_token).
 */
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'

const route = useRoute()
const token = computed(() => String(route.params.token ?? ''))

function decodeTokenPayload(t: string): Record<string, unknown> | null {
  try {
    const base64 = t.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(decodeURIComponent(escape(atob(base64))))
  } catch {
    return null
  }
}

const isTimeshare = computed(() => decodeTokenPayload(token.value)?.ref_type === 'timeshare_visit')

// نفس القيم الحقيقية الموجودة في ReviewCategory.category على الباك إند —
// مفيش أي قيمة هنا مخترعة من الفرونت (الحقل String(30) حر، مفيش migration مطلوب).
const HOTEL_CATEGORIES = [
  { key: 'service',     label: 'الخدمة' },
  { key: 'cleanliness', label: 'النظافة' },
  { key: 'value',       label: 'القيمة مقابل السعر' },
  { key: 'beach',       label: 'الشاطئ' },
  { key: 'food',        label: 'الطعام' },
  { key: 'location',    label: 'الموقع' },
] as const

const TIMESHARE_CATEGORIES = [
  { key: 'unit_cleanliness',   label: 'نظافة وحدتك' },
  { key: 'reception',          label: 'الاستقبال والضيافة' },
  { key: 'beach_cleanliness',  label: 'نظافة الشاطئ' },
  { key: 'facilities',         label: 'توافر المرافق (المظلات والمقاعد)' },
] as const

const CATEGORIES = computed(() => (isTimeshare.value ? TIMESHARE_CATEGORIES : HOTEL_CATEGORIES))

const copy = computed(() =>
  isTimeshare.value
    ? {
        title: 'رأيك يهمنا يا مالك الخيمة',
        subtitle: 'زيارتك كمالك تهمنا فعلاً — يستغرق أقل من دقيقة',
        highlightLabel: 'ما الذي أسعدك أكثر في هذه الزيارة؟',
        suggestionLabel: 'عندك اقتراح يساعدنا نطوّر خدماتنا لك؟',
        submitLabel: 'إرسال رأيي',
        thankYouTitle: 'شكرًا لثقتك بنا يا مالك الخيمة!',
        thankYouSubtitle: 'نتطلع لاستضافتك في زيارتك القادمة 🌊',
      }
    : {
        title: 'قيّم إقامتك معنا',
        subtitle: 'رأيك يهمنا — يستغرق أقل من دقيقة',
        highlightLabel: 'اسمك (اختياري)',
        suggestionLabel: 'تعليقك (اختياري)',
        submitLabel: 'إرسال التقييم',
        thankYouTitle: 'شكرًا لتقييمك!',
        thankYouSubtitle: 'رأيك بيساعدنا نطوّر تجربة إقامتك القادمة',
      },
)

const guestName = ref('')
const overallRating = ref(0)
const categoryRatings = ref<Record<string, number>>({})
const highlightText = ref('')   // تايم شير: "ما أسعدك أكثر؟" — فندقي: مش مستخدم (الاسم بدلاً منه)
const comment = ref('')         // تايم شير: الاقتراحات — فندقي: التعليق العام

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
    const categories = CATEGORIES.value
      .filter((c) => (categoryRatings.value[c.key] ?? 0) > 0)
      .map((c) => ({ category: c.key, rating: categoryRatings.value[c.key] }))

    // فورم التايم شير فيه سؤالين مفتوحين منفصلين (زي النموذج الورقي الأصلي)
    // — الباك إند عنده حقل comment واحد بس، فبندمجهم بعنوان واضح لكل جزء.
    const finalComment = isTimeshare.value
      ? [
          highlightText.value ? `أكثر شيء أعجبه: ${highlightText.value}` : null,
          comment.value ? `اقتراحات: ${comment.value}` : null,
        ].filter(Boolean).join('\n')
      : comment.value

    await axios.post('/api/v1/analytics/reviews/submit', {
      guest_name: isTimeshare.value ? (guestName.value || 'مالك') : (highlightText.value || 'ضيف'),
      overall_rating: overallRating.value,
      comment: finalComment || undefined,
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
        <p class="font-black text-lg text-gray-900">{{ copy.thankYouTitle }}</p>
        <p class="text-sm text-gray-400 mt-1">{{ copy.thankYouSubtitle }}</p>
      </div>

      <!-- Invalid token -->
      <div v-else-if="!token" class="text-center py-8">
        <div class="text-4xl mb-3">❌</div>
        <p class="font-bold text-gray-800">رابط الاستبيان غير صالح</p>
      </div>

      <!-- Survey form -->
      <template v-else>
        <div class="text-center mb-5">
          <div class="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center mx-auto mb-3 text-3xl">
            {{ isTimeshare ? '🏝️' : '⭐' }}
          </div>
          <h1 class="text-lg font-black text-gray-900">{{ copy.title }}</h1>
          <p class="text-xs text-gray-400">{{ copy.subtitle }}</p>
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
                  :class="(categoryRatings[c.key] ?? 0) >= n ? 'text-gold' : 'text-stone-300'"
                  :aria-label="`${c.label}: ${n} نجوم`"
                >★</button>
              </div>
            </div>
          </div>

          <template v-if="isTimeshare">
            <!-- Owner name (optional) -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">اسمك (اختياري)</label>
              <input v-model="guestName" type="text" placeholder="اسمك"
                class="w-full border border-resort-border rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
            </div>

            <!-- What did you like most -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">{{ copy.highlightLabel }}</label>
              <textarea v-model="highlightText" rows="2" placeholder="مثال: نظافة الشاطئ وسرعة الاستقبال..."
                class="w-full border border-resort-border rounded-xl px-4 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/30" />
            </div>

            <!-- Suggestions -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">{{ copy.suggestionLabel }}</label>
              <textarea v-model="comment" rows="2" placeholder="شاركنا اقتراحك..."
                class="w-full border border-resort-border rounded-xl px-4 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/30" />
            </div>
          </template>

          <template v-else>
            <!-- Name (optional) -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">{{ copy.highlightLabel }}</label>
              <input v-model="highlightText" type="text" placeholder="اسمك"
                class="w-full border border-resort-border rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
            </div>

            <!-- Comment -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">{{ copy.suggestionLabel }}</label>
              <textarea v-model="comment" rows="3" placeholder="شاركنا رأيك..."
                class="w-full border border-resort-border rounded-xl px-4 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/30" />
            </div>
          </template>

          <p v-if="errorMsg" class="text-red-600 text-xs text-center">{{ errorMsg }}</p>

          <button @click="submit" :disabled="submitting"
            class="w-full bg-primary text-white font-black py-3 rounded-xl text-base disabled:opacity-50">
            {{ submitting ? '...جاري الإرسال' : copy.submitLabel }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
