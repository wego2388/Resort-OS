<script setup lang="ts">
// Page-number navigation for the list endpoints CLAUDE.md §16 requires
// pagination on ("Pagination على كل list endpoint — لا تُرجع آلاف الـ
// rows") — this is the frontend half every one of those screens needs, done
// once instead of per-screen prev/next buttons.
import { computed } from 'vue'
import AppIcon from './Icon.vue'

const props = defineProps<{ page: number; totalPages: number; totalItems?: number; pageSize?: number }>()
const emit = defineEmits<{ 'update:page': [v: number] }>()

// Compact page-number list: always show first/last, current ± 1, and "…"
// gaps — the standard pattern for avoiding 40 page buttons in a row.
const pages = computed<(number | '…')[]>(() => {
  const total = props.totalPages
  const current = props.page
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const set = new Set([1, total, current, current - 1, current + 1])
  const sorted = [...set].filter(p => p >= 1 && p <= total).sort((a, b) => a - b)
  const result: (number | '…')[] = []
  for (let i = 0; i < sorted.length; i++) {
    if (i > 0 && sorted[i]! - sorted[i - 1]! > 1) result.push('…')
    result.push(sorted[i]!)
  }
  return result
})

const rangeLabel = computed(() => {
  if (!props.totalItems || !props.pageSize) return null
  const from = (props.page - 1) * props.pageSize + 1
  const to = Math.min(props.page * props.pageSize, props.totalItems)
  return `${from}–${to} من ${props.totalItems}`
})
</script>

<template>
  <nav class="flex items-center justify-between gap-3 flex-wrap" aria-label="ترقيم الصفحات">
    <p v-if="rangeLabel" class="text-sm text-muted">{{ rangeLabel }}</p>
    <div class="flex items-center gap-1">
      <button
        type="button"
        class="w-8 h-8 flex items-center justify-center rounded-lg text-gray-600 dark:text-gray-400 hover:bg-background disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus-visible:shadow-focus-ring"
        :disabled="page <= 1"
        aria-label="الصفحة السابقة"
        @click="emit('update:page', page - 1)"
      >
        <AppIcon name="chevron-left" size="sm" class="rtl:-scale-x-100" />
      </button>
      <template v-for="(p, i) in pages" :key="`${p}-${i}`">
        <span v-if="p === '…'" class="w-8 h-8 flex items-center justify-center text-muted text-sm">…</span>
        <button
          v-else
          type="button"
          class="w-8 h-8 flex items-center justify-center rounded-lg text-sm font-medium transition-colors duration-base focus:outline-none focus-visible:shadow-focus-ring"
          :class="p === page ? 'bg-primary-700 text-white' : 'text-gray-700 dark:text-gray-300 hover:bg-background'"
          :aria-current="p === page ? 'page' : undefined"
          @click="emit('update:page', p)"
        >
          {{ p }}
        </button>
      </template>
      <button
        type="button"
        class="w-8 h-8 flex items-center justify-center rounded-lg text-gray-600 dark:text-gray-400 hover:bg-background disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus-visible:shadow-focus-ring"
        :disabled="page >= totalPages"
        aria-label="الصفحة التالية"
        @click="emit('update:page', page + 1)"
      >
        <AppIcon name="chevron-right" size="sm" class="rtl:-scale-x-100" />
      </button>
    </div>
  </nav>
</template>
