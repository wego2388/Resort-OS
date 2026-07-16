<script setup lang="ts">
defineProps<{
  title?: string
  padding?: 'none' | 'sm' | 'md' | 'lg'
  shadow?: boolean
}>()
</script>
<template>
  <div :class="['bg-white dark:bg-surface rounded-xl border border-stone-200 dark:border-border', shadow !== false && 'shadow-sm']">
    <div v-if="title" class="px-5 py-4 border-b border-stone-100 dark:border-border">
      <h3 class="font-semibold text-gray-800 dark:text-gray-100 text-base">{{ title }}</h3>
    </div>
    <div :class="[
      padding === 'none' ? '' : '',
      padding === 'sm'   ? 'p-3' : '',
      padding === 'lg'   ? 'p-8' : '',
      (!padding || padding === 'md') ? 'p-5' : '',
    ]">
      <slot />
    </div>
  </div>
</template>
