<script setup lang="ts">
// The one KPI tile every dashboard (Analytics/Finance/Sales/Beach/HR
// leaderboard) should render instead of hand-rolling its own number-tile
// layout per screen — this is exactly the "Stat Card" wagdy.md's Phase 2
// asks for, generalized rather than tied to any one module's data shape.
import { computed } from 'vue'
import AppIcon from './Icon.vue'
import type { IconName } from '../icons/registry'

const props = withDefaults(defineProps<{
  label: string
  value: string | number
  icon?: IconName
  /** Positive = up/green, negative = down/red, 0/undefined = no trend shown. */
  trend?: number
  trendLabel?: string
  variant?: 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'neutral'
  loading?: boolean
}>(), { variant: 'neutral' })

const iconWrapClass = computed(() => ({
  primary: 'bg-primary-50 text-primary-700',
  success: 'bg-success/10 text-success',
  warning: 'bg-warning/10 text-warning',
  danger: 'bg-danger/10 text-danger',
  info: 'bg-info/10 text-info',
  neutral: 'bg-background text-muted',
}[props.variant]))

const trendClass = computed(() => (props.trend ?? 0) > 0 ? 'text-success' : (props.trend ?? 0) < 0 ? 'text-danger' : 'text-muted')
const trendIcon = computed<IconName>(() => (props.trend ?? 0) > 0 ? 'chevron-up' : (props.trend ?? 0) < 0 ? 'chevron-down' : 'refresh')
</script>

<template>
  <div class="bg-white dark:bg-surface rounded-xl border border-stone-200 dark:border-border shadow-elevation-1 p-5 flex items-start justify-between gap-3">
    <div class="min-w-0 flex-1">
      <p class="text-sm text-muted font-medium truncate">{{ label }}</p>
      <div v-if="loading" class="h-8 w-24 mt-2 rounded bg-background animate-pulse" />
      <p v-else class="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-1 tabular-nums">{{ value }}</p>
      <p v-if="trend !== undefined && !loading" :class="['flex items-center gap-1 text-xs font-medium mt-2', trendClass]">
        <AppIcon :name="trendIcon" size="xs" />
        <span>{{ Math.abs(trend) }}%</span>
        <span v-if="trendLabel" class="text-muted font-normal">{{ trendLabel }}</span>
      </p>
    </div>
    <div v-if="icon" :class="['w-11 h-11 rounded-lg flex items-center justify-center shrink-0', iconWrapClass]">
      <AppIcon :name="icon" size="lg" />
    </div>
  </div>
</template>
