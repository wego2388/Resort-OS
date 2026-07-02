<script setup lang="ts">
defineProps<{ size?: 'sm' | 'md' | 'lg'; color?: string }>()
</script>
<template>
  <svg :class="[
    'animate-spin',
    size === 'sm' ? 'w-4 h-4' : size === 'lg' ? 'w-10 h-10' : 'w-6 h-6',
    color ?? 'text-blue-600'
  ]" fill="none" viewBox="0 0 24 24">
    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
  </svg>
</template>
