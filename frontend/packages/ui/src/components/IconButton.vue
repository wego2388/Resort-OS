<script setup lang="ts">
// A dedicated icon-only button — distinct from AppButton because icon-only
// controls have different sizing (square, not padded-for-text) and an
// accessibility requirement AppButton doesn't have: `label` is required so
// screen-reader users get a real name instead of nothing (icon-only
// <button>s with no accessible name are a common, easy-to-miss WCAG failure).
import { computed } from 'vue'
import AppIcon from './Icon.vue'
import type { IconName } from '../icons/registry'

const props = withDefaults(defineProps<{
  icon: IconName
  label: string
  variant?: 'primary' | 'ghost' | 'danger' | 'outline'
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  loading?: boolean
}>(), { variant: 'ghost', size: 'md' })

defineEmits<{ click: [MouseEvent] }>()

// 'lg' hits the 48px touch target wagdy.md's Touch UX phase calls for; 'sm'/
// 'md' are for dense desktop/back-office toolbars where every screen already
// packs many actions per row.
const sizeClass = computed(() => ({ sm: 'w-8 h-8', md: 'w-10 h-10', lg: 'w-12 h-12' }[props.size]))
const iconSize = computed(() => ({ sm: 'sm', md: 'md', lg: 'lg' }[props.size] as 'sm' | 'md' | 'lg'))

const variantClass = computed(() => ({
  primary: 'bg-primary text-white hover:bg-primary-800',
  danger: 'bg-danger text-white hover:opacity-90',
  outline: 'border border-border text-gray-700 hover:bg-background',
  ghost: 'text-gray-600 hover:bg-background hover:text-gray-900',
}[props.variant]))
</script>

<template>
  <button
    type="button"
    :disabled="disabled || loading"
    :aria-label="label"
    :aria-busy="loading || undefined"
    :title="label"
    @click="$emit('click', $event)"
    :class="[
      sizeClass, variantClass,
      'inline-flex items-center justify-center rounded-lg transition-colors duration-base focus:shadow-focus-ring focus:outline-none',
      (disabled || loading) ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
    ]"
  >
    <AppIcon v-if="!loading" :name="icon" :size="iconSize" />
    <svg v-else class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  </button>
</template>
