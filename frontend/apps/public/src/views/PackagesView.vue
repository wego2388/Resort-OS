<script setup lang="ts">
/**
 * PackagesView — Gate 6 migration Batch 3 (2026-07-21). New route. The 3
 * named packages (Morning Bliss / Sunset Signature / Couple's Chill) are
 * sourced from elkheima-beach-resort-marketing/05_content/
 * MASTER_FILE_COMPLETE.md — real, not invented. Same price-disclaimer
 * approach as BeachView.vue (static marketing document, not a live feed).
 */
import { useI18n } from 'vue-i18n'
import SiteHeader from '../components/SiteHeader.vue'
import SiteFooter from '../components/SiteFooter.vue'

const { t } = useI18n()

const PACKAGES = [
  { key: 'morning', icon: '☀️', titleKey: 'morningTitle', priceKey: 'morningPrice', descKey: 'morningDesc' },
  { key: 'sunset', icon: '🌅', titleKey: 'sunsetTitle', priceKey: 'sunsetPrice', descKey: 'sunsetDesc' },
  { key: 'couple', icon: '💑', titleKey: 'coupleTitle', priceKey: 'couplePrice', descKey: 'coupleDesc' },
] as const
</script>

<template>
  <div class="min-h-screen bg-white">
    <SiteHeader />

    <div class="bg-gradient-to-br from-brand-charcoal via-brand-ocean to-brand-teal text-white">
      <div class="max-w-3xl mx-auto text-center px-6 py-16">
        <h1 class="font-heading text-3xl md:text-5xl font-black mb-4">{{ t('marketing.pages.packages.title') }}</h1>
        <p class="text-white/90 text-lg font-body">{{ t('marketing.pages.packages.subtitle') }}</p>
      </div>
    </div>

    <div class="max-w-5xl mx-auto px-6 py-16">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div v-for="pkg in PACKAGES" :key="pkg.key"
          class="bg-white rounded-2xl border border-stone-200 shadow-sm hover:shadow-lg transition-shadow p-6 text-center flex flex-col">
          <div class="text-5xl mb-4">{{ pkg.icon }}</div>
          <h2 class="font-heading font-black text-brand-charcoal text-xl mb-2">{{ t(`marketing.pages.packages.${pkg.titleKey}`) }}</h2>
          <p class="font-heading text-3xl font-black text-brand-ocean mb-3">{{ t(`marketing.pages.packages.${pkg.priceKey}`) }}</p>
          <p class="text-gray-500 text-sm font-body leading-relaxed mt-auto">{{ t(`marketing.pages.packages.${pkg.descKey}`) }}</p>
        </div>
      </div>
      <p class="text-center text-xs text-gray-400 mt-10 font-body">{{ t('marketing.pages.packages.priceDisclaimer') }}</p>
    </div>

    <div class="bg-gradient-to-r from-brand-ocean to-brand-teal py-16 text-center px-6">
      <h2 class="font-heading text-3xl font-black text-white mb-4">{{ t('marketing.cta.title') }}</h2>
      <p class="text-white/90 mb-8 text-lg font-body">{{ t('marketing.cta.subtitle') }}</p>
      <RouterLink to="/book"
        class="inline-block bg-white text-brand-ocean px-10 py-4 rounded-2xl font-black text-lg hover:bg-brand-lightgray transition-colors">
        {{ t('marketing.cta.button') }}
      </RouterLink>
    </div>

    <SiteFooter />
  </div>
</template>
