<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import LanguageSelector from './LanguageSelector.vue'
import { RESORT } from '../constants/resort'

const { t, locale } = useI18n()
</script>

<template>
  <header class="sticky top-0 z-30 bg-brand-charcoal/95 backdrop-blur text-white shadow-md">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-3">
      <RouterLink to="/" class="flex items-center gap-2 shrink-0">
        <img src="../assets/el-kheima-logo.svg" alt="El Kheima Beach Resort" class="h-9 w-auto bg-white rounded-md p-0.5" />
        <span class="hidden sm:block font-heading font-black text-sm leading-tight">
          {{ locale === 'ar' ? t('marketing.brand.nameNative') : t('marketing.brand.name') }}
        </span>
      </RouterLink>

      <nav class="hidden md:flex items-center gap-6 font-semibold text-sm">
        <RouterLink to="/" class="hover:text-brand-sunset transition-colors">{{ t('marketing.nav.home') }}</RouterLink>
        <a href="#rooms" class="hover:text-brand-sunset transition-colors">{{ t('marketing.nav.rooms') }}</a>
        <RouterLink to="/dining" class="hover:text-brand-sunset transition-colors">{{ t('marketing.nav.dining') }}</RouterLink>
        <a href="#contact" class="hover:text-brand-sunset transition-colors">{{ t('marketing.nav.contact') }}</a>
      </nav>

      <div class="flex items-center gap-2 sm:gap-3">
        <a :href="`tel:${RESORT.phones[0]}`"
          class="hidden sm:inline-flex items-center gap-1.5 text-xs font-bold bg-white/10 hover:bg-white/20 px-3 py-2 rounded-full transition-colors" dir="ltr">
          📞 {{ RESORT.phones[0] }}
        </a>
        <LanguageSelector />
        <RouterLink to="/book"
          class="bg-brand-sunset text-white px-4 py-2 rounded-full font-black text-sm hover:brightness-110 transition-all">
          {{ t('marketing.nav.book') }}
        </RouterLink>
      </div>
    </div>
  </header>
</template>
