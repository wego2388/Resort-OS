<script setup lang="ts">
defineProps<{ icon?: string; title: string; subtitle?: string }>()
</script>
<template>
  <div class="text-center py-12 text-gray-400">
    <div class="text-4xl mb-3">{{ icon ?? '📭' }}</div>
    <p class="text-base font-medium text-gray-500">{{ title }}</p>
    <p v-if="subtitle" class="text-sm text-gray-400 mt-1">{{ subtitle }}</p>
  </div>
</template>
