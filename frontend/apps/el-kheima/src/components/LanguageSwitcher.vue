<script setup lang="ts">
/**
 * LanguageSwitcher — مبدّل اللغة المُستخدم في topbar وfield header.
 *
 * يستخدم switchLocale من @resort-os/core/i18n الذي يُحدّث:
 *   - i18n.global.locale (vue-i18n reactive)
 *   - document.documentElement.dir/lang
 *   - localStorage (3 keys للتوافق مع أي حاجة قديمة)
 *
 * variant="compact" → أيقونة 🌐 + كود اللغة فقط (للـ topbar/header)
 * variant="full"    → اسم كامل لكل لغة في dropdown (للإعدادات مستقبلاً)
 */
import { ref, computed } from 'vue'
import { switchLocale, getSavedLocale, SUPPORTED_LOCALES } from '@resort-os/core'
import { useI18n } from 'vue-i18n'

withDefaults(defineProps<{ variant?: 'compact' | 'full' }>(), { variant: 'compact' })

const { t } = useI18n()

const currentLocale = ref(getSavedLocale())
const isOpen = ref(false)

const LOCALE_LABELS: Record<string, string> = {
  ar: 'العربية',
  en: 'English',
  ru: 'Русский',
  it: 'Italiano',
}

const LOCALE_FLAGS: Record<string, string> = {
  ar: '🇸🇦',
  en: '🇬🇧',
  ru: '🇷🇺',
  it: '🇮🇹',
}

const otherLocales = computed(() =>
  SUPPORTED_LOCALES.filter((l) => l !== currentLocale.value),
)

async function select(locale: string) {
  isOpen.value = false
  if (locale === currentLocale.value) return
  await switchLocale(locale)
  currentLocale.value = locale as typeof currentLocale.value
}

function toggleOpen() {
  isOpen.value = !isOpen.value
}

// Close on outside click
function onBlur() {
  setTimeout(() => { isOpen.value = false }, 150)
}
</script>

<template>
  <div class="relative" @blur.capture="onBlur">
    <!-- Trigger button -->
    <button
      type="button"
      @click="toggleOpen"
      :title="t('backoffice.layout.selectLanguage')"
      class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-sm font-medium
             text-gray-600 hover:bg-gray-100 transition-colors select-none"
    >
      <span class="text-base leading-none">🌐</span>
      <span v-if="variant === 'compact'" class="uppercase text-xs tracking-wide font-semibold">
        {{ currentLocale }}
      </span>
      <span v-else>{{ LOCALE_LABELS[currentLocale] }}</span>
      <svg class="w-3 h-3 text-gray-400 transition-transform" :class="{ 'rotate-180': isOpen }"
           fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
      </svg>
    </button>

    <!-- Dropdown -->
    <Transition
      enter-active-class="transition duration-100 ease-out"
      enter-from-class="opacity-0 scale-95"
      enter-to-class="opacity-100 scale-100"
      leave-active-class="transition duration-75 ease-in"
      leave-from-class="opacity-100 scale-100"
      leave-to-class="opacity-0 scale-95"
    >
      <div
        v-if="isOpen"
        class="absolute z-50 mt-1 py-1 bg-white rounded-xl shadow-lg border border-gray-100
               min-w-[9rem]"
        :class="currentLocale === 'ar' ? 'left-0' : 'right-0'"
      >
        <!-- Current locale (highlighted, non-clickable) -->
        <div class="flex items-center gap-2.5 px-3 py-2 text-sm font-semibold text-blue-700 bg-blue-50 rounded-lg mx-1 mb-1">
          <span>{{ LOCALE_FLAGS[currentLocale] }}</span>
          <span>{{ LOCALE_LABELS[currentLocale] }}</span>
          <svg class="w-3.5 h-3.5 ml-auto text-blue-500" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
          </svg>
        </div>
        <!-- Other locales -->
        <button
          v-for="locale in otherLocales"
          :key="locale"
          type="button"
          @click="select(locale)"
          class="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-700
                 hover:bg-gray-50 transition-colors rounded-lg mx-1"
          style="width: calc(100% - 0.5rem)"
        >
          <span>{{ LOCALE_FLAGS[locale] }}</span>
          <span>{{ LOCALE_LABELS[locale] }}</span>
        </button>
      </div>
    </Transition>
  </div>
</template>
