<script setup lang="ts">
/**
 * PrivacyView — Gate 6 migration Batch 2 (2026-07-21). New route. Real legal
 * text is Mohamed's to write, not something to fabricate (2026-07-21: "خليها
 * فاضية دلوقتي و في الآخر حبقى اعملهم") — real page shell + explicit
 * pending notice, ready for him to drop real policy text into later.
 */
import { useI18n } from 'vue-i18n'
import SiteHeader from '../components/SiteHeader.vue'
import SiteFooter from '../components/SiteFooter.vue'

const { t } = useI18n()
</script>

<template>
  <div class="min-h-screen bg-white">
    <SiteHeader />

    <div class="max-w-2xl mx-auto px-6 py-16 text-center">
      <h1 class="font-heading text-3xl sm:text-4xl font-black text-brand-charcoal mb-8">{{ t('marketing.pages.privacy.title') }}</h1>
      <div class="bg-brand-lightgray/50 border border-stone-200 rounded-2xl p-8">
        <p class="text-gray-600 font-body leading-relaxed">{{ t('marketing.pages.privacy.pendingNotice') }}</p>
      </div>
    </div>

    <SiteFooter />
  </div>
</template>
