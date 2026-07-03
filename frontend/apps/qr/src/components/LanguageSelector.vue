<script setup lang="ts">
/**
 * LanguageSelector — مبدّل لغة صغير للضيوف (عربي/إنجليزي/إيطالي/روسي)
 *
 * زر عائم صغير (🌐) بيفتح قائمة قصيرة، بينده switchLocale() من @resort-os/core/i18n
 * مباشرة (بدون أي app-store abstraction) — الاختيار بيتخزّن أوتوماتيك في localStorage
 * جوه switchLocale نفسها، وبيقلب RTL/LTR على مستوى الصفحة كلها.
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { switchLocale } from '@resort-os/core/i18n'

const { locale } = useI18n()
const open = ref(false)

const LANGUAGES = [
  { code: 'ar', flag: '🇸🇦', label: 'العربية' },
  { code: 'en', flag: '🇬🇧', label: 'English' },
  { code: 'it', flag: '🇮🇹', label: 'Italiano' },
  { code: 'ru', flag: '🇷🇺', label: 'Русский' },
] as const

async function select(code: string) {
  open.value = false
  if (code === locale.value) return
  await switchLocale(code)
}

function currentFlag() {
  return LANGUAGES.find(l => l.code === locale.value)?.flag ?? '🌐'
}
</script>

<template>
  <div class="relative inline-block">
    <button
      type="button"
      @click="open = !open"
      class="w-9 h-9 flex items-center justify-center bg-white border border-stone-200 rounded-full text-lg shadow-sm active:scale-95 transition-transform"
      :aria-label="'Change language'"
    >
      {{ currentFlag() }}
    </button>

    <!-- Backdrop to dismiss on outside click -->
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
          lang.code === locale ? 'bg-blue-50 text-blue-700' : 'text-gray-700 hover:bg-stone-50']"
      >
        <span class="text-lg">{{ lang.flag }}</span>
        <span>{{ lang.label }}</span>
      </button>
    </div>
  </div>
</template>
