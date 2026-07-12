<script setup lang="ts">
// A shape-matched loading placeholder — used inside a Card/table row/list
// item while its real content is being fetched, so the layout doesn't jump
// once data arrives (unlike LoadingState.vue's full-region spinner, which
// replaces the whole area). `count` renders multiple stacked lines in one
// call for the common "3 skeleton rows" case.
withDefaults(defineProps<{
  variant?: 'text' | 'circle' | 'rect'
  width?: string
  height?: string
  count?: number
}>(), { variant: 'text', count: 1 })
</script>

<template>
  <div class="flex flex-col gap-2">
    <div
      v-for="i in count"
      :key="i"
      class="animate-pulse bg-background"
      :class="[
        variant === 'circle' ? 'rounded-full' : variant === 'rect' ? 'rounded-lg' : 'rounded h-4',
      ]"
      :style="{
        width: width ?? (variant === 'text' && i === count && count > 1 ? '70%' : '100%'),
        height: height ?? (variant === 'circle' ? '2.5rem' : variant === 'rect' ? '6rem' : undefined),
      }"
    />
  </div>
</template>
