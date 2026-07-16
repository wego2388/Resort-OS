<script setup lang="ts">
// The dark-mode trigger — built and ready, but not mounted in any layout
// yet (BackOfficeLayout/KioskLayout/FieldLayout are all existing shell
// files, and wiring nav chrome into them is Phase 3's job, not this pass's
// "pure additive infrastructure" scope). Uses @resort-os/core's useTheme()
// singleton, so it reflects/drives the same state initTheme() bootstraps in
// main.ts — mounting this anywhere just works without extra plumbing.
import { computed } from 'vue'
import { useTheme } from '@resort-os/core'
import AppIcon from './Icon.vue'

const { isDark, toggleTheme } = useTheme()
const label = computed(() => isDark.value ? 'التبديل للوضع الفاتح' : 'التبديل للوضع الداكن')
</script>

<template>
  <button
    type="button"
    :aria-label="label"
    :title="label"
    @click="toggleTheme"
    class="w-9 h-9 rounded-lg flex items-center justify-center text-gray-600 dark:text-gray-400 hover:bg-background transition-colors duration-base focus:outline-none focus-visible:shadow-focus-ring"
  >
    <AppIcon :name="isDark ? 'sun' : 'moon'" size="sm" />
  </button>
</template>
