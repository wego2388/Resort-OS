<script setup lang="ts">
// Visual output for every existing variant/size is unchanged by this pass
// (still bg-blue-700/amber-500/red-600 etc — deliberately NOT re-pointed at
// the newer primary/secondary/danger DS tokens here, since AppButton is
// already wired into ~30 shipped screens; re-skinning a shared component
// out from under that much in-production UI without an explicit visual
// review is out of scope for "additive infrastructure". Tracked as known
// follow-up for the screens-migration stage instead.
// Changes in this pass are non-visual: the old computed had a fully dead
// fourth `primary` branch (identical condition already covered by the first
// branch, so it could never add anything the first branch hadn't already
// added) removed, and two purely-additive props (`type`, `ariaLabel`) that
// don't change default rendering.
import { computed } from 'vue'

const props = defineProps<{
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'outline'
  size?: 'sm' | 'md' | 'lg' | 'xl'
  loading?: boolean
  disabled?: boolean
  block?: boolean
  /** Native button type — left unset by default so a button inside a <form> keeps the browser's implicit type="submit" behavior existing call sites may rely on. */
  type?: 'button' | 'submit' | 'reset'
  ariaLabel?: string
}>()

const SIZE_CLASSES: Record<string, string> = {
  sm: 'px-3 py-1.5 text-sm',
  lg: 'px-6 py-3 text-lg',
  xl: 'px-8 py-4 text-xl',
}
const VARIANT_CLASSES: Record<string, string> = {
  secondary: 'bg-amber-500 text-white hover:bg-amber-600 focus:ring-amber-400',
  danger: 'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500',
  ghost: 'bg-transparent text-gray-700 hover:bg-gray-100',
  outline: 'border-2 border-blue-700 text-blue-700 hover:bg-blue-50',
}

const sizeClass = computed(() => SIZE_CLASSES[props.size ?? 'md'] ?? 'px-4 py-2 text-base')
const variantClass = computed(() => VARIANT_CLASSES[props.variant ?? 'primary'] ?? 'bg-blue-700 text-white hover:bg-blue-800 focus:ring-blue-500')
</script>

<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
    :aria-label="ariaLabel"
    :class="[
      'inline-flex items-center justify-center gap-2 font-semibold rounded-lg transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-offset-2',
      block && 'w-full',
      sizeClass,
      variantClass,
      (disabled || loading) ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
    ]"
  >
    <svg v-if="loading" class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
    </svg>
    <slot />
  </button>
</template>
