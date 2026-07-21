<script setup lang="ts">
/**
 * TermsView — Gate 6 migration Batch 2 (2026-07-21). New route. Same
 * pending-content approach as PrivacyView.vue — see that file's note.
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
      <h1 class="font-heading text-3xl sm:text-4xl font-black text-brand-charcoal mb-8">{{ t('marketing.pages.terms.title') }}</h1>
      <div class="bg-brand-lightgray/50 border border-stone-200 rounded-2xl p-8">
        <p class="text-gray-600 font-body leading-relaxed">{{ t('marketing.pages.terms.pendingNotice') }}</p>
      </div>
    </div>

    <SiteFooter />
  </div>
</template>
