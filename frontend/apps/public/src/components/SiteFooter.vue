<script setup lang="ts">
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
          <a :href="RESORT.social.facebook" target="_blank" rel="noopener"
            class="w-9 h-9 flex items-center justify-center rounded-full bg-white/10 hover:bg-brand-sunset transition-colors">📘</a>
          <a :href="RESORT.social.instagram" target="_blank" rel="noopener"
            class="w-9 h-9 flex items-center justify-center rounded-full bg-white/10 hover:bg-brand-sunset transition-colors">📷</a>
          <a :href="`https://wa.me/2${RESORT.whatsapp}`" target="_blank" rel="noopener"
            class="w-9 h-9 flex items-center justify-center rounded-full bg-white/10 hover:bg-brand-sunset transition-colors">💬</a>
        </div>
      </div>

      <div>
        <h4 class="font-heading font-bold text-white mb-3">{{ t('marketing.contact.title') }}</h4>
        <p class="text-sm mb-1">{{ t('marketing.contact.phone') }}:</p>
        <p class="text-sm mb-3" dir="ltr">
          <a v-for="(p, i) in RESORT.phones" :key="p" :href="`tel:${p}`" class="hover:text-white">
            {{ p }}<span v-if="i < RESORT.phones.length - 1"> | </span>
          </a>
        </p>
        <p class="text-sm mb-1">{{ t('marketing.contact.hours') }}:</p>
        <p class="text-sm">{{ t('marketing.contact.hoursValue') }}</p>
      </div>

      <div>
        <h4 class="font-heading font-bold text-white mb-3">{{ t('marketing.nav.contact') }}</h4>
        <p class="text-sm leading-relaxed mb-3">{{ t('marketing.contact.address') }}</p>
        <a :href="RESORT.mapUrl" target="_blank" rel="noopener"
          class="text-sm font-bold text-brand-sunset hover:underline">🗺️ Google Maps</a>
      </div>
    </div>

    <div class="border-t border-white/10 py-5 text-center text-xs text-white/50">
      © {{ year }} {{ t('marketing.brand.name') }} — {{ t('marketing.footer.rights') }}
    </div>
  </footer>
</template>
