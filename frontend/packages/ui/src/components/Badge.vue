<script setup lang="ts">
defineProps<{
  variant?: 'success' | 'warning' | 'danger' | 'info' | 'neutral'
  size?: 'sm' | 'md'
}>()
</script>
<template>
  <span :class="[
    'inline-flex items-center font-medium rounded-full',
    size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm',
    variant === 'success' ? 'bg-green-100 text-green-800'   : '',
    variant === 'warning' ? 'bg-amber-100 text-amber-800'   : '',
    variant === 'danger'  ? 'bg-red-100 text-red-700'       : '',
    variant === 'info'    ? 'bg-blue-100 text-blue-800'     : '',
    (!variant || variant === 'neutral') ? 'bg-gray-100 text-gray-700' : '',
  ]">
    <slot />
  </span>
</template>
