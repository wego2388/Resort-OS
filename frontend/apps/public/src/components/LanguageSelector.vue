<script setup lang="ts">
/**
 * LanguageSelector — small guest-facing language switcher (ar/en/ru/it).
 *
 * Same pattern as apps/qr/src/components/LanguageSelector.vue: calls
 * switchLocale() from @resort-os/core/i18n directly (no store indirection).
 * switchLocale() persists the choice under the public app's namespaced key
 * and flips document.documentElement `dir` for the whole page (rtl for ar,
 * ltr otherwise) — that's what makes ar <-> en/ru/it re-layout the site.
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { switchLocale } from '@resort-os/core/i18n'

const { locale } = useI18n()
const open = ref(false)

const LANGUAGES = [
  { code: 'ar', flag: '🇪🇬', label: 'العربية' },
  { code: 'en', flag: '🇬🇧', label: 'English' },
  { code: 'it', flag: '🇮🇹', label: 'Italiano' },
  { code: 'ru', flag: '🇷🇺', label: 'Русский' },
] as const

async function select(code: string) {
  open.value = false
  if (code === locale.value) return
  await switchLocale(code)
}

function currentLabel() {
  return LANGUAGES.find(l => l.code === locale.value)?.flag ?? '🌐'
}
</script>

<template>
  <div class="relative inline-block">
    <button
      type="button"
      @click="open = !open"
      class="w-10 h-10 flex items-center justify-center bg-white/10 hover:bg-white/20 border border-white/20 rounded-full text-lg transition-colors"
      aria-label="Change language"
    >
      {{ currentLabel() }}
    </button>

    <div v-if="open" class="fixed inset-0 z-40" @click="open = false" />

    <div
      v-if="open"
      class="absolute z-50 mt-2 end-0 bg-white rounded-2xl border border-stone-200 shadow-lg overflow-hidden min-w-[9.5rem]"
    >
      <button
        v-for="lang in LANGUAGES"
        :key="lang.code"
        type="button"
        @click="select(lang.code)"
        :class="['w-full flex items-center gap-2.5 px-4 py-2.5 text-sm font-semibold transition-colors text-start',
          lang.code === locale ? 'bg-brand-ocean/10 text-brand-ocean' : 'text-gray-700 hover:bg-stone-50']"
      >
        <span class="text-lg">{{ lang.flag }}</span>
        <span>{{ lang.label }}</span>
      </button>
    </div>
  </div>
</template>
