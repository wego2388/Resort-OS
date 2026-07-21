<script setup lang="ts">
/**
 * SiteFooter — Gate 6 migration Batch 1 polish (2026-07-21). Real a11y gaps
 * fixed: the three social links were emoji-only anchors with no accessible
 * name at all (a screen reader announces "link" with nothing else) — added
 * aria-label to each. Also added focus-visible states throughout (none
 * existed before). Brand palette untouched (see SiteHeader.vue's note).
 */
import { useI18n } from 'vue-i18n'
import { RESORT } from '../constants/resort'

const { t, locale } = useI18n()
const year = new Date().getFullYear()
</script>

<template>
  <footer id="contact" class="bg-brand-charcoal text-white/80">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 py-12 grid grid-cols-1 md:grid-cols-3 gap-10">
      <div>
        <div class="flex items-center gap-2 mb-3">
          <img src="../assets/el-kheima-logo.svg" alt="El Kheima Beach Resort" class="h-10 w-auto bg-white rounded-md p-0.5" />
        </div>
        <p class="text-sm leading-relaxed max-w-xs">
          {{ locale === 'ar' ? t('marketing.brand.nameNative') : t('marketing.brand.name') }} —
          {{ t('marketing.brand.tagline') }}
        </p>
        <div class="flex gap-3 mt-4">
          <a :href="RESORT.social.facebook" target="_blank" rel="noopener" aria-label="Facebook"
            class="w-11 h-11 flex items-center justify-center rounded-full bg-white/10 hover:bg-brand-sunset transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70">📘</a>
          <a :href="RESORT.social.instagram" target="_blank" rel="noopener" aria-label="Instagram"
            class="w-11 h-11 flex items-center justify-center rounded-full bg-white/10 hover:bg-brand-sunset transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70">📷</a>
          <a :href="`https://wa.me/2${RESORT.whatsapp}`" target="_blank" rel="noopener" aria-label="WhatsApp"
            class="w-11 h-11 flex items-center justify-center rounded-full bg-white/10 hover:bg-brand-sunset transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70">💬</a>
        </div>
      </div>

      <div>
        <h4 class="font-heading font-bold text-white mb-3">{{ t('marketing.contact.title') }}</h4>
        <p class="text-sm mb-1">{{ t('marketing.contact.phone') }}:</p>
        <p class="text-sm mb-3" dir="ltr">
          <a v-for="(p, i) in RESORT.phones" :key="p" :href="`tel:${p}`" class="rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 hover:text-white">
            {{ p }}<span v-if="i < RESORT.phones.length - 1"> | </span>
          </a>
        </p>
        <p class="text-sm mb-1">{{ t('marketing.contact.hours') }}:</p>
        <p class="text-sm mb-3">{{ t('marketing.contact.hoursValue') }}</p>
        <RouterLink to="/contact" class="text-sm font-bold text-brand-sunset rounded hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70">✉️ {{ t('marketing.pages.contact.formTitle') }}</RouterLink>
      </div>

      <div>
        <h4 class="font-heading font-bold text-white mb-3">{{ t('marketing.nav.contact') }}</h4>
        <p class="text-sm leading-relaxed mb-3">{{ t('marketing.contact.address') }}</p>
        <a :href="RESORT.mapUrl" target="_blank" rel="noopener"
          class="rounded text-sm font-bold text-brand-sunset hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70">🗺️ Google Maps</a>
      </div>
    </div>

    <div class="border-t border-white/10 py-5 px-4 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-center text-xs text-white/50">
      <span>© {{ year }} {{ t('marketing.brand.name') }} — {{ t('marketing.footer.rights') }}</span>
      <span class="flex items-center gap-4">
        <RouterLink to="/privacy" class="rounded hover:text-white/80 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70">{{ t('marketing.footer.privacyLink') }}</RouterLink>
        <RouterLink to="/terms" class="rounded hover:text-white/80 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70">{{ t('marketing.footer.termsLink') }}</RouterLink>
      </span>
    </div>
  </footer>
</template>
