<script lang="ts">
// Column definition في plain <script> عشان تُستورد كـ type من خارج الـ component
// بدون ما تشيل الـ generic type parameter.
export interface VirtualTableColumn {
  key: string
  label: string
  sortable?: boolean
  align?: 'start' | 'center' | 'end'
  width?: string
}
</script>

<script setup lang="ts" generic="T extends Record<string, unknown>">
/**
 * VirtualTable — جدول مع windowed rendering للـ rows الكتير (500+).
 * بيرندر بس اللي في الـ viewport بدل كل الـ rows — مهم لـ Inventory products وJournal entries.
 *
 * لا يحتاج مكتبة خارجية — بيستخدم IntersectionObserver + scroll events.
 * rowHeight ثابت (prop) لأن variable-height virtualization أعقد بكثير وليست مطلوبة هنا.
 *
 * للـ server-side pagination العادي → استخدم DataTable بدلاً منه.
 * VirtualTable مخصوص للـ client-side data (كل الـ rows في الذاكرة).
 */
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import ErrorState from './ErrorState.vue'
import EmptyState from './EmptyState.vue'
import AppIcon from './Icon.vue'
import Skeleton from './Skeleton.vue'

const props = withDefaults(defineProps<{
  columns: VirtualTableColumn[]
  items: T[]
  rowKey: (item: T) => string | number
  rowHeight?: number
  loading?: boolean
  error?: boolean
  errorMessage?: string
  sortKey?: string
  sortDir?: 'asc' | 'desc'
  emptyTitle?: string
  emptySubtitle?: string
  /** عدد rows إضافية فوق وتحت الـ viewport (buffer) */
  overscan?: number
}>(), {
  rowHeight: 48,
  emptyTitle: 'لا توجد بيانات',
  overscan: 5,
})

const emit = defineEmits<{
  sort: [key: string]
  'row-click': [item: T]
  retry: []
}>()

const containerRef = ref<HTMLDivElement>()
const scrollTop    = ref(0)
const containerH   = ref(400)

// الـ rows المرئية حسب scroll position
const visibleRange = computed(() => {
  const startRaw = Math.floor(scrollTop.value / props.rowHeight) - props.overscan
  const start    = Math.max(0, startRaw)
  const visCount = Math.ceil(containerH.value / props.rowHeight) + props.overscan * 2
  const end      = Math.min(props.items.length - 1, start + visCount)
  return { start, end }
})

const visibleItems = computed(() =>
  props.items.slice(visibleRange.value.start, visibleRange.value.end + 1),
)

// الـ spacer فوق الـ rows المرئية (عشان الـ scroll bar يشتغل صح)
const topSpacer    = computed(() => visibleRange.value.start * props.rowHeight)
const bottomSpacer = computed(() =>
  (props.items.length - visibleRange.value.end - 1) * props.rowHeight,
)

const totalHeight = computed(() => props.items.length * props.rowHeight)

function onScroll(e: Event) {
  scrollTop.value = (e.target as HTMLDivElement).scrollTop
}

// ResizeObserver لتتبع ارتفاع الـ container
let resizeObs: ResizeObserver | null = null

onMounted(() => {
  if (!containerRef.value) return
  containerH.value = containerRef.value.clientHeight
  resizeObs = new ResizeObserver(entries => {
    containerH.value = entries[0]?.contentRect.height ?? containerH.value
  })
  resizeObs.observe(containerRef.value)
})

onBeforeUnmount(() => resizeObs?.disconnect())

// reset scroll لما تتغير الـ items
watch(() => props.items.length, () => {
  scrollTop.value = 0
  if (containerRef.value) containerRef.value.scrollTop = 0
})

const alignClass = (a?: VirtualTableColumn['align']) =>
  a === 'center' ? 'text-center' : a === 'end' ? 'text-end' : 'text-start'
</script>

<template>
  <div class="bg-white dark:bg-surface rounded-xl border border-stone-200 dark:border-border overflow-hidden flex flex-col">
    <!-- Header -->
    <div class="overflow-x-auto shrink-0">
      <table class="w-full border-collapse">
        <thead>
          <tr class="bg-stone-50 dark:bg-gray-800/60 border-b border-stone-200 dark:border-border">
            <th
              v-for="col in columns"
              :key="col.key"
              scope="col"
              :style="col.width ? { width: col.width } : undefined"
              :class="['px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider', alignClass(col.align)]"
            >
              <button
                v-if="col.sortable"
                type="button"
                class="inline-flex items-center gap-1 hover:text-gray-800 dark:hover:text-gray-200 focus:outline-none focus-visible:shadow-focus-ring rounded"
                @click="emit('sort', col.key)"
              >
                {{ col.label }}
                <AppIcon
                  :name="sortKey === col.key ? (sortDir === 'asc' ? 'chevron-up' : 'chevron-down') : 'chevron-down'"
                  size="xs"
                  :class="sortKey === col.key ? 'text-gray-700 dark:text-gray-300' : 'text-stone-300 dark:text-gray-600'"
                />
              </button>
              <span v-else>{{ col.label }}</span>
            </th>
          </tr>
        </thead>
      </table>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="p-4 space-y-2">
      <div v-for="i in 8" :key="i" class="flex gap-4">
        <Skeleton v-for="col in columns" :key="col.key" class="h-10 flex-1" />
      </div>
    </div>

    <!-- Error -->
    <ErrorState v-else-if="error" :message="errorMessage" @retry="emit('retry')" />

    <!-- Empty -->
    <EmptyState v-else-if="!items.length" :title="emptyTitle" :subtitle="emptySubtitle" />

    <!-- Virtual scroll container -->
    <div
      v-else
      ref="containerRef"
      class="flex-1 overflow-y-auto overflow-x-auto"
      style="min-height: 200px; max-height: 600px;"
      @scroll="onScroll"
    >
      <table class="w-full border-collapse" :style="{ height: totalHeight + 'px', display: 'block', position: 'relative' }">
        <tbody style="display: block; position: relative; width: 100%;">
          <!-- Top spacer -->
          <tr v-if="topSpacer > 0" :style="{ height: `${topSpacer}px`, display: 'block' }" aria-hidden="true" />

          <!-- Visible rows -->
          <tr
            v-for="item in visibleItems"
            :key="rowKey(item)"
            :style="{ height: `${rowHeight}px`, display: 'flex', alignItems: 'center' }"
            class="border-b border-stone-100 dark:border-border/50 last:border-0 hover:bg-primary-50/30 dark:hover:bg-primary-900/20 transition-colors cursor-pointer w-full"
            @click="emit('row-click', item)"
          >
            <td
              v-for="col in columns"
              :key="col.key"
              :style="col.width ? { width: col.width, flexShrink: 0 } : { flex: 1, minWidth: 0 }"
              :class="['px-4 py-2 text-sm text-gray-800 dark:text-gray-200 overflow-hidden text-ellipsis whitespace-nowrap', alignClass(col.align)]"
            >
              <slot :name="`cell-${col.key}`" :item="item" :value="item[col.key]">
                {{ item[col.key] }}
              </slot>
            </td>
          </tr>

          <!-- Bottom spacer -->
          <tr v-if="bottomSpacer > 0" :style="{ height: `${bottomSpacer}px`, display: 'block' }" aria-hidden="true" />
        </tbody>
      </table>
    </div>

    <!-- Footer: row count -->
    <div v-if="!loading && !error && items.length > 0" class="px-4 py-2 border-t border-stone-100 dark:border-border/50 text-xs text-muted text-end">
      {{ items.length.toLocaleString('ar-EG') }} صف
    </div>
  </div>
</template>
