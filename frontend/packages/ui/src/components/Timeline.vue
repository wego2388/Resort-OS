<script setup lang="ts">
// A vertical event timeline — audit logs, order history, maintenance ticket
// history, HR document trails; anywhere a screen currently renders its own
// "list of dated events" markup gets this instead once migrated. Each item
// owns its own icon/variant so a caller can distinguish e.g. a void from a
// normal status change without the component needing to know the domain.
import { computed } from 'vue'
import AppIcon from './Icon.vue'
import type { IconName } from '../icons/registry'

export interface TimelineItem {
  id: string | number
  title: string
  description?: string
  timestamp: string
  icon?: IconName
  variant?: 'primary' | 'success' | 'warning' | 'danger' | 'neutral'
}

const props = defineProps<{ items: TimelineItem[] }>()

const dotClass = (variant: TimelineItem['variant'] = 'neutral') => ({
  primary: 'bg-primary-700 text-white',
  success: 'bg-success text-white',
  warning: 'bg-warning text-white',
  danger: 'bg-danger text-white',
  neutral: 'bg-background text-muted border border-border',
}[variant])
</script>

<template>
  <ol class="relative">
    <li v-for="(item, i) in items" :key="item.id" class="relative flex gap-3 pb-6 last:pb-0">
      <div
        v-if="i < items.length - 1"
        class="absolute top-8 bottom-0 w-px bg-border"
        style="inset-inline-start: 0.9375rem"
        aria-hidden="true"
      />
      <div :class="['w-8 h-8 rounded-full flex items-center justify-center shrink-0 z-10', dotClass(item.variant)]">
        <AppIcon v-if="item.icon" :name="item.icon" size="sm" />
        <span v-else class="w-2 h-2 rounded-full bg-current" />
      </div>
      <div class="flex-1 min-w-0 pt-1">
        <div class="flex items-baseline justify-between gap-2">
          <p class="text-sm font-medium text-gray-900">{{ item.title }}</p>
          <time class="text-xs text-muted whitespace-nowrap">{{ item.timestamp }}</time>
        </div>
        <p v-if="item.description" class="text-sm text-muted mt-0.5">{{ item.description }}</p>
      </div>
    </li>
  </ol>
</template>
