<script setup lang="ts">
/**
 * GalleryView — Gate 6 migration Batch 3 (2026-07-21). New route. No
 * verified real resort photography exists in this repo (only menu-item
 * photos, keyed by UUID, unrelated to beach/rooms/facilities) — real page
 * shell + pending notice rather than filling a "gallery" with unrelated or
 * stock images passed off as the resort, same approach as FaqView.vue.
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
      <h1 class="font-heading text-4xl font-black text-brand-charcoal mb-2">{{ t('marketing.pages.gallery.title') }}</h1>
      <p class="text-gray-500 font-body mb-8">{{ t('marketing.pages.gallery.subtitle') }}</p>

      <div class="bg-brand-lightgray/50 border border-stone-200 rounded-2xl p-8">
        <p class="text-gray-600 font-body leading-relaxed mb-4">{{ t('marketing.pages.gallery.pendingNotice') }}</p>
        <div class="flex items-center justify-center gap-3">
          <a :href="RESORT.social.facebook" target="_blank" rel="noopener"
            class="w-11 h-11 flex items-center justify-center rounded-full bg-white border border-stone-200 hover:bg-brand-sunset hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-ocean" aria-label="Facebook">📘</a>
          <a :href="RESORT.social.instagram" target="_blank" rel="noopener"
            class="w-11 h-11 flex items-center justify-center rounded-full bg-white border border-stone-200 hover:bg-brand-sunset hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-ocean" aria-label="Instagram">📷</a>
        </div>
      </div>
    </div>

    <SiteFooter />
  </div>
</template>
