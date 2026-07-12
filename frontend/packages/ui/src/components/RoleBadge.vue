<script setup lang="ts">
// Renders a user's role as a labeled pill — the exact 14-role vocabulary
// mirrors ROLE_LEVELS in packages/core/src/stores/auth.ts (itself a
// deliberate duplicate of backend app/core/deps.py, per CLAUDE.md §13 rule
// ❺: any new role needs both updated together). Kept as its own small map
// here rather than importing ROLE_LEVELS from the auth store, since this
// only needs Arabic display labels + a visual tier, not the numeric levels.
import { computed } from 'vue'
import AppBadge from './Badge.vue'

type Variant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

const ROLE_LABELS: Record<string, { label: string; variant: Variant }> = {
  super_admin: { label: 'مدير عام', variant: 'danger' },
  admin: { label: 'إدارة', variant: 'danger' },
  accountant: { label: 'محاسب', variant: 'info' },
  hr_manager: { label: 'مدير موارد بشرية', variant: 'info' },
  manager: { label: 'مدير', variant: 'warning' },
  supervisor: { label: 'مشرف', variant: 'warning' },
  receptionist: { label: 'استقبال', variant: 'success' },
  cashier: { label: 'كاشير', variant: 'success' },
  waiter: { label: 'جرسون', variant: 'neutral' },
  chef: { label: 'شيف', variant: 'neutral' },
  kitchen: { label: 'مطبخ', variant: 'neutral' },
  employee: { label: 'موظف', variant: 'neutral' },
  customer: { label: 'عميل', variant: 'neutral' },
  guest: { label: 'ضيف', variant: 'neutral' },
}

const props = withDefaults(defineProps<{ role: string; size?: 'sm' | 'md' }>(), { size: 'sm' })
const resolved = computed(() => ROLE_LABELS[props.role] ?? { label: props.role, variant: 'neutral' as Variant })
</script>

<template>
  <AppBadge :variant="resolved.variant" :size="size">{{ resolved.label }}</AppBadge>
</template>
