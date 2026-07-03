<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import SiteHeader from '../components/SiteHeader.vue'
import SiteFooter from '../components/SiteFooter.vue'

const { t } = useI18n()
const router = useRouter()
const loading = ref(false)
const error = ref('')
const form = ref({
  full_name: '', email: '', phone: '', nationality: '',
  check_in: '', check_out: '', adults: 2, children: 0,
  room_type: '', special_requests: ''
})

// Values kept exactly as before (standard/sea_view/suite/chalet) — only the
// display label is localized, so this stays purely a UI-copy change.
const roomTypes = computed(() => [
  { value: 'standard', label: t('marketing.booking.roomTypeStandard') },
  { value: 'sea_view', label: t('marketing.booking.roomTypeSeaView') },
  { value: 'suite', label: t('marketing.booking.roomTypeSuite') },
  { value: 'chalet', label: t('marketing.booking.roomTypeChalet') },
])

async function submitInquiry() {
  if (!form.value.full_name || !form.value.phone || !form.value.check_in) {
    error.value = t('marketing.booking.validationError'); return
  }
  loading.value = true; error.value = ''
  try {
    // ⚠️ Field names below (full_name/email/phone/subject/message/source_page)
    // must stay exactly as-is — this is the live-verified contract with
    // POST /api/v1/hub/contact. Don't change field names here.
    await axios.post('/api/v1/hub/contact', {
      full_name: form.value.full_name, email: form.value.email,
      phone: form.value.phone, subject: t('marketing.booking.subjectLine'),
      message: `${t('marketing.booking.checkIn')}: ${form.value.check_in} → ${form.value.check_out} | ${form.value.adults} ${t('marketing.booking.adults')} + ${form.value.children} ${t('marketing.booking.children')} | ${roomTypes.value.find(r => r.value === form.value.room_type)?.label ?? ''} | ${form.value.special_requests}`,
      source_page: 'booking_inquiry',
    })
    router.push('/confirmation')
  } catch(e: any) {
    error.value = e?.response?.data?.detail ?? t('marketing.booking.genericError')
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-stone-50">
    <SiteHeader />

    <div class="max-w-lg mx-auto p-4 py-8">
      <div class="mb-5 text-center">
        <h1 class="font-heading text-2xl font-black text-brand-charcoal">{{ t('marketing.booking.title') }}</h1>
        <p class="text-gray-500 text-sm mt-1 font-body">{{ t('marketing.booking.subtitle') }}</p>
      </div>

      <div class="bg-white rounded-2xl border border-stone-200 p-6 shadow-sm">
        <div class="space-y-4">
          <div class="grid grid-cols-2 gap-3">
            <div class="col-span-2">
              <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('marketing.booking.fullName') }} *</label>
              <input v-model="form.full_name" type="text" :placeholder="t('marketing.booking.fullNamePlaceholder')"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-ocean"/>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('marketing.booking.phone') }} *</label>
              <input v-model="form.phone" type="tel" placeholder="010xxxxxxxx" dir="ltr"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-ocean text-start"/>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('marketing.booking.email') }}</label>
              <input v-model="form.email" type="email" placeholder="email@example.com" dir="ltr"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-ocean text-start"/>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('marketing.booking.checkIn') }} *</label>
              <input v-model="form.check_in" type="date"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-ocean"/>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('marketing.booking.checkOut') }}</label>
              <input v-model="form.check_out" type="date"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-ocean"/>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('marketing.booking.adults') }}</label>
              <input v-model.number="form.adults" type="number" min="1" max="10"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-ocean"/>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('marketing.booking.children') }}</label>
              <input v-model.number="form.children" type="number" min="0" max="10"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-ocean"/>
            </div>
            <div class="col-span-2">
              <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('marketing.booking.roomType') }}</label>
              <select v-model="form.room_type"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-ocean">
                <option value="">{{ t('marketing.booking.roomTypePlaceholder') }}</option>
                <option v-for="r in roomTypes" :key="r.value" :value="r.value">{{ r.label }}</option>
              </select>
            </div>
            <div class="col-span-2">
              <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('marketing.booking.specialRequests') }}</label>
              <textarea v-model="form.special_requests" rows="3" :placeholder="t('marketing.booking.specialRequestsPlaceholder')"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-ocean resize-none text-sm"/>
            </div>
          </div>

          <div v-if="error" class="bg-red-50 text-red-600 px-4 py-2.5 rounded-xl text-sm">{{ error }}</div>

          <button @click="submitInquiry" :disabled="loading"
            class="w-full py-4 bg-brand-ocean text-white rounded-2xl font-black text-lg hover:bg-brand-teal disabled:opacity-50 transition-colors">
            {{ loading ? t('marketing.booking.submitting') : t('marketing.booking.submit') }}
          </button>
          <p class="text-center text-xs text-gray-400">{{ t('marketing.booking.responseTime') }}</p>
        </div>
      </div>
    </div>

    <SiteFooter />
  </div>
</template>
