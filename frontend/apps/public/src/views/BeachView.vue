<script setup lang="ts">
/**
 * BeachView — Gate 6 migration Batch 3 (2026-07-21). New route. Content
 * (amenities list, water sports, the 4 beach-access tiers) sourced from
 * elkheima-beach-resort-marketing/05_content/MASTER_FILE_COMPLETE.md — real
 * resort material, not invented. Prices are from that static document (no
 * live pricing feed for beach access exists on the public API), so the page
 * carries an explicit "approximate, subject to change" disclaimer rather
 * than presenting them as a live, authoritative price list.
 */
import { useI18n } from 'vue-i18n'
import SiteHeader from '../components/SiteHeader.vue'
import SiteFooter from '../components/SiteFooter.vue'

const { t } = useI18n()

const AMENITY_KEYS = ['amenity1', 'amenity2', 'amenity3', 'amenity4', 'amenity5', 'amenity6'] as const
const ACTIVITY_KEYS = ['activity1', 'activity2', 'activity3', 'activity4'] as const
const TIERS = [
  { key: 'tierRegular', priceKey: 'tierRegularPrice', descKey: 'tierRegularDesc' },
  { key: 'tierVip', priceKey: 'tierVipPrice', descKey: 'tierVipDesc' },
  { key: 'tierPrivate', priceKey: 'tierPrivatePrice', descKey: 'tierPrivateDesc' },
  { key: 'tierGroup', priceKey: 'tierGroupPrice', descKey: 'tierGroupDesc' },
] as const
</script>

<template>
  <div class="min-h-screen bg-white">
    <SiteHeader />

    <div class="bg-gradient-to-br from-brand-charcoal via-brand-ocean to-brand-teal text-white">
      <div class="max-w-3xl mx-auto text-center px-6 py-16">
        <h1 class="font-heading text-3xl md:text-5xl font-black mb-4">{{ t('marketing.pages.beach.title') }}</h1>
        <p class="text-white/90 text-lg font-body">{{ t('marketing.pages.beach.subtitle') }}</p>
      </div>
    </div>

    <div class="max-w-5xl mx-auto px-6 py-16">
      <h2 class="font-heading text-2xl font-black text-brand-charcoal text-center mb-8">{{ t('marketing.pages.beach.amenitiesTitle') }}</h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
        <div v-for="key in AMENITY_KEYS" :key="key"
          class="bg-brand-lightgray/50 rounded-xl px-4 py-3 text-center font-body text-sm font-semibold text-brand-charcoal">
          {{ t(`marketing.pages.beach.${key}`) }}
        </div>
      </div>
    </div>

    <div class="bg-brand-lightgray/50 py-16">
      <div class="max-w-5xl mx-auto px-6">
        <h2 class="font-heading text-2xl font-black text-brand-charcoal text-center mb-8">{{ t('marketing.pages.beach.activitiesTitle') }}</h2>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div v-for="key in ACTIVITY_KEYS" :key="key"
            class="bg-white rounded-2xl border border-stone-200 shadow-sm px-4 py-6 text-center font-body font-bold text-brand-charcoal">
            {{ t(`marketing.pages.beach.${key}`) }}
          </div>
        </div>
      </div>
    </div>

    <div class="max-w-5xl mx-auto px-6 py-16">
      <h2 class="font-heading text-2xl font-black text-brand-charcoal text-center mb-2">{{ t('marketing.pages.beach.accessTitle') }}</h2>
      <p class="text-gray-500 text-center mb-10 font-body">{{ t('marketing.pages.beach.accessSubtitle') }}</p>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div v-for="tier in TIERS" :key="tier.key"
          class="bg-white rounded-2xl border border-stone-200 shadow-sm p-5 flex flex-col text-center hover:shadow-md transition-shadow">
          <h3 class="font-heading font-bold text-brand-charcoal mb-1">{{ t(`marketing.pages.beach.${tier.key}`) }}</h3>
          <p class="font-heading text-2xl font-black text-brand-ocean mb-2">{{ t(`marketing.pages.beach.${tier.priceKey}`) }}</p>
          <p class="text-gray-500 text-xs font-body leading-relaxed mt-auto">{{ t(`marketing.pages.beach.${tier.descKey}`) }}</p>
        </div>
      </div>
      <p class="text-center text-xs text-gray-400 mt-8 font-body">{{ t('marketing.pages.beach.priceDisclaimer') }}</p>
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
