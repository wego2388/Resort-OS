<script setup lang="ts">
/**
 * AboutView — Gate 6 migration Batch 2 (2026-07-21). New route, didn't exist
 * before this batch. Deliberately reuses marketing.about.title/body and
 * marketing.stats/valueProps — the same real, sourced content already shown
 * on the Home page — rather than inventing new "our story" copy that isn't
 * backed by real brand material (04_CONTENT_I18N_SEO_MAP.md's sourcing rule).
 */
import { useI18n } from 'vue-i18n'
import SiteHeader from '../components/SiteHeader.vue'
import SiteFooter from '../components/SiteFooter.vue'

const { t } = useI18n()

const FEATURE_KEYS = ['beach', 'dining', 'water', 'rooms', 'events', 'families'] as const
const FEATURE_ICONS: Record<typeof FEATURE_KEYS[number], string> = {
  beach: '🏖️', dining: '🍝', water: '🤿', rooms: '🌊', events: '💍', families: '👨‍👩‍👧‍👦',
}
</script>

<template>
  <div class="min-h-screen bg-white">
    <SiteHeader />

    <div class="max-w-3xl mx-auto px-6 py-16 text-center">
      <h1 class="font-heading text-4xl font-black text-brand-charcoal mb-2">{{ t('marketing.about.title') }}</h1>
      <p class="text-gray-500 font-body mb-8">{{ t('marketing.pages.about.subtitle') }}</p>
      <p class="text-gray-600 leading-relaxed font-body text-lg">{{ t('marketing.about.body') }}</p>
    </div>

    <div class="bg-brand-lightgray/50 py-12">
      <div class="max-w-5xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-6 px-6 text-center">
        <div>
          <p class="font-heading text-2xl sm:text-3xl font-black text-brand-ocean">{{ t('marketing.stats.beachArea') }}</p>
          <p class="text-xs sm:text-sm text-gray-500 mt-1 font-body">{{ t('marketing.stats.beachAreaLabel') }}</p>
        </div>
        <div>
          <p class="font-heading text-2xl sm:text-3xl font-black text-brand-ocean">{{ t('marketing.stats.beachLength') }}</p>
          <p class="text-xs sm:text-sm text-gray-500 mt-1 font-body">{{ t('marketing.stats.beachLengthLabel') }}</p>
        </div>
        <div>
          <p class="font-heading text-2xl sm:text-3xl font-black text-brand-ocean">{{ t('marketing.stats.totalArea') }}</p>
          <p class="text-xs sm:text-sm text-gray-500 mt-1 font-body">{{ t('marketing.stats.totalAreaLabel') }}</p>
        </div>
        <div>
          <p class="font-heading text-2xl sm:text-3xl font-black text-brand-ocean">{{ t('marketing.stats.ranking') }}</p>
          <p class="text-xs sm:text-sm text-gray-500 mt-1 font-body">{{ t('marketing.stats.rankingLabel') }}</p>
        </div>
      </div>
    </div>

    <div class="max-w-5xl mx-auto px-6 py-16">
      <h2 class="font-heading text-3xl font-black text-brand-charcoal text-center mb-10">{{ t('marketing.valueProps.title') }}</h2>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div v-for="key in FEATURE_KEYS" :key="key"
          class="text-center p-6 bg-white rounded-2xl border border-stone-200 shadow-sm hover:shadow-md transition-shadow">
          <div class="text-4xl mb-3">{{ FEATURE_ICONS[key] }}</div>
          <h3 class="font-heading font-bold text-brand-charcoal text-lg mb-2">{{ t(`marketing.valueProps.${key}.title`) }}</h3>
          <p class="text-gray-500 text-sm leading-relaxed font-body">{{ t(`marketing.valueProps.${key}.desc`) }}</p>
        </div>
      </div>
    </div>

    <SiteFooter />
  </div>
</template>
