<script setup lang="ts">
// Shared light/dark trigger. BackOfficeLayout and FieldLayout both mount it,
// while the @resort-os/core singleton keeps every shell synchronized with the
// preference that initTheme() applies before the app mounts.
import { computed } from 'vue'
import { useTheme } from '@resort-os/core'
import AppIcon from './Icon.vue'

const { isDark, toggleTheme } = useTheme()
const props = withDefaults(defineProps<{
  lightLabel?: string
  darkLabel?: string
}>(), {
  lightLabel: 'Switch to light mode / التبديل للوضع الفاتح',
  darkLabel: 'Switch to dark mode / التبديل للوضع الداكن',
})
const label = computed(() => isDark.value ? props.lightLabel : props.darkLabel)
</script>

<template>
  <button
    type="button"
    :aria-label="label"
    :title="label"
    @click="toggleTheme"
    class="flex h-11 w-11 items-center justify-center rounded-xl text-gray-600 transition-colors duration-base hover:bg-background focus:outline-none focus-visible:shadow-focus-ring dark:text-gray-300"
  >
    <AppIcon :name="isDark ? 'sun' : 'moon'" size="sm" />
  </button>
</template>
