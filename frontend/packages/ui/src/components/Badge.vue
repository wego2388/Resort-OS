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
    variant === 'success' ? 'bg-success/10 text-success'   : '',
    variant === 'warning' ? 'bg-warning/10 text-warning'   : '',
    variant === 'danger'  ? 'bg-danger/10  text-danger'    : '',
    variant === 'info'    ? 'bg-info/10    text-info'      : '',
    (!variant || variant === 'neutral') ? 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300' : '',
  ]">
    <slot />
  </span>
</template>
