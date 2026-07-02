<script setup lang="ts">
defineProps<{
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'outline'
  size?: 'sm' | 'md' | 'lg' | 'xl'
  loading?: boolean
  disabled?: boolean
  block?: boolean
}>()
</script>

<template>
  <button
    :disabled="disabled || loading"
    :class="[
      'inline-flex items-center justify-center gap-2 font-semibold rounded-lg transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-offset-2',
      block && 'w-full',
      size === 'sm'  ? 'px-3 py-1.5 text-sm'  : '',
      size === 'lg'  ? 'px-6 py-3 text-lg'    : '',
      size === 'xl'  ? 'px-8 py-4 text-xl'    : '',
      (!size || size === 'md') ? 'px-4 py-2 text-base' : '',
      variant === 'primary'   ? 'bg-blue-700 text-white hover:bg-blue-800 focus:ring-blue-500' : '',
      variant === 'secondary' ? 'bg-amber-500 text-white hover:bg-amber-600 focus:ring-amber-400' : '',
      variant === 'danger'    ? 'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500'   : '',
      variant === 'ghost'     ? 'bg-transparent text-gray-700 hover:bg-gray-100'              : '',
      variant === 'outline'   ? 'border-2 border-blue-700 text-blue-700 hover:bg-blue-50'     : '',
      (!variant || variant === 'primary') && !['secondary','danger','ghost','outline'].includes(variant ?? '') ? 'bg-blue-700 text-white hover:bg-blue-800 focus:ring-blue-500' : '',
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
