<script setup lang="ts">
// A generic lifecycle-status pill — every module has one (order status,
// booking status, payroll run status, maintenance ticket status, ...) and
// today each screen hand-picks its own AppBadge variant/color per status
// string, which is exactly the "duplicated logic that should be unified"
// wagdy.md's Design System calls out. This does NOT change any existing
// screen (none import it yet) — it's the target those call sites migrate
// onto in the later screens-migration stage.
//
// The default map covers the status vocabulary actually in use today (verified
// by grepping app/modules/**/models.py + services.py, not guessed): restaurant/
// cafe order status (pending/open/in_kitchen/served/paid/cancelled/rejected/
// refunded), PMS Booking.status (pending/confirmed/checked_in/checked_out/
// cancelled), HR (pending/approved/rejected/active/draft), maintenance
// WorkOrder.status (open/in_progress/completed/cancelled), plus closed/overdue/
// failed used across finance/leasing/timeshare/hub. `map` lets a screen
// override/extend it for a status vocabulary that doesn't fit the default
// without forking the component.
import { computed } from 'vue'
import AppBadge from './Badge.vue'

type Variant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

const DEFAULT_MAP: Record<string, { label: string; variant: Variant }> = {
  pending: { label: 'قيد الانتظار', variant: 'warning' },
  open: { label: 'مفتوح', variant: 'info' },
  in_progress: { label: 'قيد التنفيذ', variant: 'info' },
  in_kitchen: { label: 'قيد التحضير', variant: 'info' },
  served: { label: 'تم التقديم', variant: 'success' },
  completed: { label: 'مكتمل', variant: 'success' },
  confirmed: { label: 'مؤكد', variant: 'success' },
  approved: { label: 'معتمد', variant: 'success' },
  paid: { label: 'مدفوع', variant: 'success' },
  active: { label: 'نشط', variant: 'success' },
  checked_in: { label: 'تسجيل دخول', variant: 'success' },
  checked_out: { label: 'تسجيل خروج', variant: 'neutral' },
  cancelled: { label: 'ملغي', variant: 'danger' },
  refunded: { label: 'مسترجع', variant: 'danger' },
  rejected: { label: 'مرفوض', variant: 'danger' },
  failed: { label: 'فشل', variant: 'danger' },
  overdue: { label: 'متأخر', variant: 'danger' },
  draft: { label: 'مسودة', variant: 'neutral' },
  closed: { label: 'مغلق', variant: 'neutral' },
}

const props = withDefaults(defineProps<{
  status: string
  map?: Record<string, { label: string; variant: Variant }>
  size?: 'sm' | 'md'
}>(), { size: 'sm' })

const resolved = computed(() => {
  const table = { ...DEFAULT_MAP, ...props.map }
  return table[props.status] ?? { label: props.status, variant: 'neutral' as Variant }
})
</script>

<template>
  <AppBadge :variant="resolved.variant" :size="size">{{ resolved.label }}</AppBadge>
</template>
