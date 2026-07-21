<script setup lang="ts">
/**
 * ContactView — Gate 6 migration Batch 2 (2026-07-21). New route, didn't
 * exist before this batch (the header's "Contact" nav link only ever
 * scrolled to the footer's static info). Real, working general-inquiry
 * form wired to the already-current, already-rate-limited POST /hub/contact
 * contract — same field names as BookingView.vue's inquiry form; don't
 * change them without checking that contract.
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import SiteHeader from '../components/SiteHeader.vue'
import SiteFooter from '../components/SiteFooter.vue'
import { RESORT } from '../constants/resort'

const { t } = useI18n()
const loading = ref(false)
const error = ref('')
const sent = ref(false)
const form = ref({ full_name: '', email: '', phone: '', subject: '', message: '' })

async function submit() {
  if (!form.value.full_name || !form.value.email || !form.value.message) {
    error.value = t('marketing.pages.contact.validationError'); return
  }
  loading.value = true; error.value = ''
  try {
    await axios.post('/api/v1/hub/contact', {
      full_name: form.value.full_name, email: form.value.email, phone: form.value.phone,
      subject: form.value.subject || t('marketing.pages.contact.subjectPlaceholder'),
      message: form.value.message, source_page: 'contact_page',
    })
    sent.value = true
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? t('marketing.pages.contact.genericError')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-stone-50">
    <SiteHeader />

    <div class="max-w-4xl mx-auto p-4 py-12">
      <div class="mb-8 text-center">
        <h1 class="font-heading text-3xl sm:text-4xl font-black text-brand-charcoal">{{ t('marketing.pages.contact.title') }}</h1>
        <p class="text-gray-500 mt-2 font-body">{{ t('marketing.pages.contact.subtitle') }}</p>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-5 gap-6">
        <!-- Form -->
        <div class="md:col-span-3 bg-white rounded-2xl border border-stone-200 p-6 shadow-sm">
          <div v-if="sent" class="text-center py-10">
            <div class="text-5xl mb-4">✅</div>
            <h2 class="font-heading text-xl font-black text-brand-charcoal mb-2">{{ t('marketing.pages.contact.successTitle') }}</h2>
            <p class="text-gray-500 font-body">{{ t('marketing.pages.contact.successBody') }}</p>
          </div>
          <div v-else class="space-y-4">
            <h2 class="font-heading font-bold text-brand-charcoal text-lg">{{ t('marketing.pages.contact.formTitle') }}</h2>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('marketing.pages.contact.fullName') }} *</label>
              <input v-model="form.full_name" type="text" :placeholder="t('marketing.pages.contact.fullNamePlaceholder')"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-ocean" />
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('marketing.pages.contact.email') }} *</label>
                <input v-model="form.email" type="email" dir="ltr"
                  class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-ocean text-start" />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('marketing.pages.contact.phone') }}</label>
                <input v-model="form.phone" type="tel" placeholder="010xxxxxxxx" dir="ltr"
                  class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-ocean text-start" />
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('marketing.pages.contact.subject') }}</label>
              <input v-model="form.subject" type="text" :placeholder="t('marketing.pages.contact.subjectPlaceholder')"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-ocean" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('marketing.pages.contact.message') }} *</label>
              <textarea v-model="form.message" rows="4" :placeholder="t('marketing.pages.contact.messagePlaceholder')"
                class="w-full border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-ocean resize-none" />
            </div>

            <p v-if="error" class="text-sm text-red-600 font-body">{{ error }}</p>

            <button type="button" :disabled="loading" @click="submit"
              class="w-full min-h-[48px] bg-brand-sunset text-white rounded-xl font-black text-base hover:brightness-110 transition-all disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-ocean">
              {{ loading ? t('marketing.pages.contact.submitting') : t('marketing.pages.contact.submit') }}
            </button>
          </div>
        </div>

        <!-- Info -->
        <div class="md:col-span-2 bg-white rounded-2xl border border-stone-200 p-6 shadow-sm h-fit">
          <h2 class="font-heading font-bold text-brand-charcoal text-lg mb-4">{{ t('marketing.pages.contact.infoTitle') }}</h2>
          <div class="space-y-4 text-sm">
            <div>
              <p class="text-gray-400 mb-1">{{ t('marketing.contact.phone') }}</p>
              <p dir="ltr" class="font-semibold text-brand-charcoal">
                <a v-for="(p, i) in RESORT.phones" :key="p" :href="`tel:${p}`" class="rounded hover:text-brand-ocean focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-ocean">
                  {{ p }}<span v-if="i < RESORT.phones.length - 1"> · </span>
                </a>
              </p>
            </div>
            <div>
              <p class="text-gray-400 mb-1">{{ t('marketing.pages.contact.email') }}</p>
              <a :href="`mailto:${RESORT.email}`" dir="ltr" class="font-semibold text-brand-charcoal rounded hover:text-brand-ocean focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-ocean">{{ RESORT.email }}</a>
            </div>
            <div>
              <p class="text-gray-400 mb-1">{{ t('marketing.contact.hours') }}</p>
              <p class="font-semibold text-brand-charcoal">{{ t('marketing.contact.hoursValue') }}</p>
            </div>
            <div>
              <p class="text-gray-400 mb-1">{{ t('marketing.nav.contact') }}</p>
              <p class="font-semibold text-brand-charcoal leading-relaxed">{{ t('marketing.contact.address') }}</p>
              <a :href="RESORT.mapUrl" target="_blank" rel="noopener"
                class="inline-block mt-2 text-sm font-bold text-brand-sunset rounded hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-ocean">🗺️ Google Maps</a>
            </div>
          </div>
        </div>
      </div>
    </div>

    <SiteFooter />
  </div>
</template>
