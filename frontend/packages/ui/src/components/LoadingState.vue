<script setup lang="ts">
// A full-region loading placeholder (spinner + optional label) for the
// "first load, nothing to skeleton yet" case — Skeleton.vue is the sibling
// for "we know the shape of what's coming" (a table row, a card grid).
import AppSpinner from './Spinner.vue'

withDefaults(defineProps<{ label?: string; size?: 'sm' | 'md' | 'lg' }>(), { size: 'md' })
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-3 py-12 text-muted" role="status" :aria-label="label ?? 'جارٍ التحميل'">
    <AppSpinner :size="size" color="text-primary" />
    <p v-if="label" class="text-sm">{{ label }}</p>
  </div>
</template>
