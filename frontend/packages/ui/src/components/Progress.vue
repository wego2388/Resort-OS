<script setup lang="ts">
// A linear progress bar — payroll run progress, upload/import progress
// (timeshare Excel import), shift/task completion. `indeterminate` covers
// the "we don't know how long this takes" case (matches native <progress>
// semantics without a value attribute).
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  value?: number
  max?: number
  variant?: 'primary' | 'success' | 'warning' | 'danger'
  indeterminate?: boolean
  label?: string
  showValue?: boolean
}>(), { max: 100, variant: 'primary' })

const percent = computed(() => Math.min(100, Math.max(0, ((props.value ?? 0) / props.max) * 100)))

const barClass = computed(() => ({
  primary: 'bg-primary-700',
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
}[props.variant]))
</script>

<template>
  <div class="w-full">
    <div v-if="label || showValue" class="flex items-center justify-between text-xs text-muted mb-1">
      <span v-if="label">{{ label }}</span>
      <span v-if="showValue" class="tabular-nums">{{ Math.round(percent) }}%</span>
    </div>
    <div
      class="h-2 w-full rounded-full bg-background overflow-hidden"
      role="progressbar"
      :aria-valuenow="indeterminate ? undefined : value"
      aria-valuemin="0"
      :aria-valuemax="max"
    >
      <div
        v-if="indeterminate"
        :class="[barClass, 'h-full w-1/3 rounded-full animate-ds-indeterminate']"
      />
      <div
        v-else
        :class="[barClass, 'h-full rounded-full transition-all duration-slow ease-ds-standard']"
        :style="{ width: `${percent}%` }"
      />
    </div>
  </div>
</template>
