<script setup lang="ts">
defineProps<{
  title?: string
  padding?: 'none' | 'sm' | 'md' | 'lg'
  shadow?: boolean
}>()
</script>
<template>
  <div :class="['bg-white rounded-xl border border-stone-200', shadow !== false && 'shadow-sm']">
    <div v-if="title" class="px-5 py-4 border-b border-stone-100">
      <h3 class="font-semibold text-gray-800 text-base">{{ title }}</h3>
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
