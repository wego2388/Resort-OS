<script setup lang="ts">
/**
 * FaqView — Gate 6 migration Batch 2 (2026-07-21). New route. No sourced
 * FAQ content exists yet (04_CONTENT_I18N_SEO_MAP.md's rule: no invented
 * legal/marketing claims) — real page shell with an explicit pending
 * notice, ready for Mohamed to fill in later, rather than fabricated Q&A.
 */
import { useI18n } from 'vue-i18n'
import SiteHeader from '../components/SiteHeader.vue'
import SiteFooter from '../components/SiteFooter.vue'
import { RESORT } from '../constants/resort'

const { t } = useI18n()
</script>

<template>
  <div class="min-h-screen bg-white">
    <SiteHeader />

    <div class="max-w-2xl mx-auto px-6 py-16 text-center">
      <h1 class="font-heading text-4xl font-black text-brand-charcoal mb-2">{{ t('marketing.pages.faq.title') }}</h1>
      <p class="text-gray-500 font-body mb-8">{{ t('marketing.pages.faq.subtitle') }}</p>

      <div class="bg-brand-lightgray/50 border border-stone-200 rounded-2xl p-8">
        <p class="text-gray-600 font-body leading-relaxed mb-4">{{ t('marketing.pages.faq.pendingNotice') }}</p>
        <a :href="`tel:${RESORT.phones[0]}`"
          class="inline-flex items-center gap-2 min-h-[44px] px-5 bg-brand-sunset text-white rounded-full font-black text-sm hover:brightness-110 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-ocean" dir="ltr">
          📞 {{ RESORT.phones[0] }}
        </a>
      </div>
    </div>

    <SiteFooter />
  </div>
</template>
