<script setup lang="ts">
/**
 * SiteHeader — Gate 6 migration Batch 1 polish (2026-07-21). Real gaps found
 * and fixed here, not a cosmetic-only pass:
 *  1. Nav links (`Home`/`Rooms`/`Dining`/`Contact`) were `hidden md:flex` with
 *     no mobile alternative at all — a guest on a phone (the overwhelming
 *     majority of marketing-site traffic) had literally no way to reach
 *     Rooms/Contact except the logo (home) and the Book button. Added a real
 *     mobile menu.
 *  2. No visible keyboard-focus states on any interactive element (logo,
 *     nav links, phone link, book button, language selector trigger) — a
 *     keyboard/screen-reader user couldn't tell what was focused against the
 *     dark charcoal header. Added `focus-visible:ring-2` throughout.
 *  3. Touch targets under ~40px (phone pill, book button) bumped to a real
 *     44px minimum (WCAG 2.5.5 / the ~44-48px convention already used
 *     elsewhere in this project's staff POS work).
 * Brand palette (ocean/sunset/sandy/charcoal — the official identity from
 * VISUAL_IDENTITY_GUIDE.md) is untouched deliberately; that's not "legacy",
 * it's the resort's actual brand.
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import LanguageSelector from './LanguageSelector.vue'
import { RESORT } from '../constants/resort'

const { t, locale } = useI18n()
// Each mobile menu link closes it via its own @click — no route watcher
// needed (anchor links like #rooms don't trigger a route change anyway).
const mobileMenuOpen = ref(false)
</script>

<template>
  <header class="sticky top-0 z-30 bg-brand-charcoal/95 backdrop-blur text-white shadow-md">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-3">
      <RouterLink
        to="/"
        class="flex items-center gap-2 shrink-0 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
      >
        <img src="../assets/el-kheima-logo.svg" alt="El Kheima Beach Resort" class="h-9 w-auto bg-white rounded-md p-0.5" />
        <span class="hidden sm:block font-heading font-black text-sm leading-tight">
          {{ locale === 'ar' ? t('marketing.brand.nameNative') : t('marketing.brand.name') }}
        </span>
      </RouterLink>

      <nav class="hidden lg:flex items-center gap-5 font-semibold text-sm">
        <RouterLink to="/" class="rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 hover:text-brand-sunset transition-colors">{{ t('marketing.nav.home') }}</RouterLink>
        <RouterLink to="/about" class="rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 hover:text-brand-sunset transition-colors">{{ t('marketing.nav.about') }}</RouterLink>
        <RouterLink to="/#rooms" class="rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 hover:text-brand-sunset transition-colors">{{ t('marketing.nav.rooms') }}</RouterLink>
        <RouterLink to="/dining" class="rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 hover:text-brand-sunset transition-colors">{{ t('marketing.nav.dining') }}</RouterLink>
        <RouterLink to="/faq" class="rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 hover:text-brand-sunset transition-colors">{{ t('marketing.nav.faq') }}</RouterLink>
        <RouterLink to="/contact" class="rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 hover:text-brand-sunset transition-colors">{{ t('marketing.nav.contact') }}</RouterLink>
      </nav>

      <div class="flex items-center gap-2 sm:gap-3">
        <a :href="`tel:${RESORT.phones[0]}`"
          class="hidden sm:inline-flex items-center gap-1.5 min-h-[44px] text-xs font-bold bg-white/10 hover:bg-white/20 px-3.5 rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70" dir="ltr">
          📞 {{ RESORT.phones[0] }}
        </a>
        <LanguageSelector />
        <RouterLink to="/book"
          class="inline-flex items-center min-h-[44px] bg-brand-sunset text-white px-4 rounded-full font-black text-sm hover:brightness-110 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70">
          {{ t('marketing.nav.book') }}
        </RouterLink>

        <!-- Mobile/tablet menu trigger — only real way to reach the full nav below the lg breakpoint -->
        <button
          type="button"
          class="lg:hidden inline-flex items-center justify-center w-11 h-11 rounded-full bg-white/10 hover:bg-white/20 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
          :aria-expanded="mobileMenuOpen"
          :aria-label="t('marketing.nav.menuToggle')"
          @click="mobileMenuOpen = !mobileMenuOpen"
        >
          <span class="text-xl leading-none">{{ mobileMenuOpen ? '✕' : '☰' }}</span>
        </button>
      </div>
    </div>

    <nav
      v-if="mobileMenuOpen"
      class="lg:hidden border-t border-white/10 px-4 py-3 flex flex-col gap-1 font-semibold text-sm bg-brand-charcoal"
    >
      <RouterLink to="/" class="rounded-lg px-3 py-2.5 min-h-[44px] flex items-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 hover:bg-white/10 transition-colors" @click="mobileMenuOpen = false">{{ t('marketing.nav.home') }}</RouterLink>
      <RouterLink to="/about" class="rounded-lg px-3 py-2.5 min-h-[44px] flex items-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 hover:bg-white/10 transition-colors" @click="mobileMenuOpen = false">{{ t('marketing.nav.about') }}</RouterLink>
      <a href="#rooms" class="rounded-lg px-3 py-2.5 min-h-[44px] flex items-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 hover:bg-white/10 transition-colors" @click="mobileMenuOpen = false">{{ t('marketing.nav.rooms') }}</a>
      <RouterLink to="/dining" class="rounded-lg px-3 py-2.5 min-h-[44px] flex items-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 hover:bg-white/10 transition-colors" @click="mobileMenuOpen = false">{{ t('marketing.nav.dining') }}</RouterLink>
      <RouterLink to="/faq" class="rounded-lg px-3 py-2.5 min-h-[44px] flex items-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 hover:bg-white/10 transition-colors" @click="mobileMenuOpen = false">{{ t('marketing.nav.faq') }}</RouterLink>
      <RouterLink to="/contact" class="rounded-lg px-3 py-2.5 min-h-[44px] flex items-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 hover:bg-white/10 transition-colors" @click="mobileMenuOpen = false">{{ t('marketing.nav.contact') }}</RouterLink>
      <a :href="`tel:${RESORT.phones[0]}`" class="rounded-lg px-3 py-2.5 min-h-[44px] flex items-center gap-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 hover:bg-white/10 transition-colors sm:hidden" dir="ltr">
        📞 {{ RESORT.phones[0] }}
      </a>
    </nav>
  </header>
</template>
