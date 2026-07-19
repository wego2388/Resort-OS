<script setup lang="ts">
/**
 * LanguageSwitcher — staff language toggle (Gate 3A, ar/en only).
 *
 * Behavior:
 *   - Pre-login (login screen): apply + persist the namespaced staff-app
 *     preference locally via `staffLocale.setLocale`. No server call.
 *   - Signed in: persist the choice on the user's account first
 *     (`auth.updatePreferredLanguage`), then apply. On failure the UI reverts
 *     and surfaces an error — it never shows success while the server rejected.
 *
 * Direction/lang is applied centrally by the staff locale controller; this
 * component never sets `dir`/`lang` itself.
 */
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@resort-os/core'
import {
  normalizeStaffLocale,
  staffLocale,
  STAFF_LOCALES,
  type StaffLocale,
} from '@resort-os/core/i18n/staff'
import { useToast } from '@resort-os/ui'

withDefaults(defineProps<{ variant?: 'compact' | 'full' }>(), { variant: 'compact' })

const { t, locale: activeLocale } = useI18n()
const auth = useAuthStore()
const toast = useToast()

// Read from vue-i18n's reactive locale instead of keeping a second local copy.
// This keeps the label correct after login/refresh/PIN operator switch as well
// as after a choice made inside this component.
const currentLocale = computed<StaffLocale>(() =>
  normalizeStaffLocale(String(activeLocale.value)),
)
const isOpen = ref(false)
const isSaving = ref(false)

const LOCALE_LABELS: Record<string, string> = {
  ar: 'العربية',
  en: 'English',
}

const otherLocales = computed(() =>
  STAFF_LOCALES.filter((l) => l !== currentLocale.value),
)

async function select(locale: StaffLocale) {
  isOpen.value = false
  if (locale === currentLocale.value || isSaving.value) return

  isSaving.value = true
  try {
    if (auth.isAuthenticated) {
      // Server is the source of truth once signed in: persist first, then
      // apply the canonical value returned by the server. Relying only on the
      // auth watcher left this already-mounted switcher's label stale for a
      // render cycle (and after PIN switches).
      const persisted = await auth.updatePreferredLanguage(locale)
      await staffLocale.setLocale(persisted, { persist: false })
    } else {
      // Pre-login: local namespaced preference only.
      await staffLocale.setLocale(locale)
    }
  } catch {
    // Server-first means the active UI locale never changed on failure.
    toast.error(t('backoffice.layout.languageSaveFailed'))
  } finally {
    isSaving.value = false
  }
}

function toggleOpen() {
  isOpen.value = !isOpen.value
}

// Close on outside blur (keyboard + pointer both dismiss the menu).
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
      :disabled="isSaving"
      :aria-expanded="isOpen"
      aria-haspopup="listbox"
      :title="t('backoffice.layout.selectLanguage')"
      class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-sm font-medium
             text-gray-600 hover:bg-gray-100 transition-colors select-none
             disabled:opacity-60 disabled:cursor-wait
             focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
    >
      <span class="text-base leading-none" aria-hidden="true">🌐</span>
      <span v-if="variant === 'compact'" class="uppercase text-xs tracking-wide font-semibold">
        {{ currentLocale }}
      </span>
      <span v-else>{{ LOCALE_LABELS[currentLocale] }}</span>
      <svg class="w-3 h-3 text-gray-400 transition-transform" :class="{ 'rotate-180': isOpen }"
           fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
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
      <ul
        v-if="isOpen"
        role="listbox"
        :aria-label="t('backoffice.layout.selectLanguage')"
        class="absolute z-50 mt-1 py-1 bg-white rounded-xl shadow-lg border border-gray-100
               min-w-[9rem] end-0"
      >
        <!-- Current locale (selected) -->
        <li
          role="option"
          :aria-selected="true"
          class="flex items-center gap-2.5 px-3 py-2 text-sm font-semibold text-blue-700 bg-blue-50 rounded-lg mx-1 mb-1"
        >
          <span>{{ LOCALE_LABELS[currentLocale] }}</span>
          <svg class="w-3.5 h-3.5 ms-auto text-blue-500" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
            <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
          </svg>
        </li>
        <!-- Other locales -->
        <li v-for="locale in otherLocales" :key="locale" role="option" :aria-selected="false">
          <button
            type="button"
            @click="select(locale)"
            class="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-700
                   hover:bg-gray-50 transition-colors rounded-lg
                   focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <span>{{ LOCALE_LABELS[locale] }}</span>
          </button>
        </li>
      </ul>
    </Transition>
  </div>
</template>
