<script lang="ts">
// Column definition lives in a plain (non-generic) <script> block so it can
// be imported as a type from outside without pulling in the generic
// component's own type parameter — `export type { DataTableColumn }` in
// packages/ui/src/index.ts re-exports this.
export interface DataTableColumn {
  key: string
  label: string
  sortable?: boolean
  align?: 'start' | 'center' | 'end'
  width?: string
}
</script>

<script setup lang="ts" generic="T extends Record<string, unknown>">
// The one sortable/paginated table shell every list screen should render
// instead of hand-building its own <table> (the exact duplication wagdy.md's
// Phase 9 "كل الجداول يجب أن تدعم..." calls out). This first version covers
// search-independent sorting, pagination (via Paginator.vue), loading/empty/
// error states, and per-column custom cell rendering via scoped slots — it
// deliberately does NOT yet do column picker/resize/grouping/export/virtual
// scroll/saved views (wagdy.md's own Phase 9 is a distinct later stage, and
// those features are substantial enough on their own that bolting them on
// here risked shipping all of them half-working instead of this solid).
// VirtualTable is intentionally a separate, not-yet-built component for
// the "tens of thousands of rows" case — real virtualization has enough
// edge cases (variable row height, sticky columns interacting with a
// windowed viewport) that it deserves its own dedicated pass rather than a
// bolted-on prop here.
//
// Zero domain knowledge: every cell either renders `item[column.key]`
// directly or defers entirely to the caller's `#cell-<key>` scoped slot —
// this file never interprets what the data means (CLAUDE.md §4: no business
// logic in components).
import { computed } from 'vue'
// DataTableColumn (declared in the plain <script> block above) is already
// in scope here — both <script> blocks in this SFC compile into one module.
import Paginator from './Paginator.vue'
import ErrorState from './ErrorState.vue'
import EmptyState from './EmptyState.vue'
import AppIcon from './Icon.vue'
import Skeleton from './Skeleton.vue'

const props = withDefaults(defineProps<{
  columns: DataTableColumn[]
  items: T[]
  rowKey: (item: T) => string | number
  loading?: boolean
  error?: boolean
  errorMessage?: string
  sortKey?: string
  sortDir?: 'asc' | 'desc'
  page?: number
  totalPages?: number
  totalItems?: number
  pageSize?: number
  emptyTitle?: string
  emptySubtitle?: string
  stickyHeader?: boolean
}>(), { emptyTitle: 'لا توجد بيانات', stickyHeader: true })

const emit = defineEmits<{
  sort: [key: string]
  'update:page': [page: number]
  'row-click': [item: T]
  retry: []
}>()

const alignClass = (a?: DataTableColumn['align']) => a === 'center' ? 'text-center' : a === 'end' ? 'text-end' : 'text-start'
const showPaginator = computed(() => !!props.totalPages && props.totalPages > 1 && props.page !== undefined)
</script>

<template>
  <div class="bg-white rounded-xl border border-stone-200 overflow-hidden">
    <div class="overflow-x-auto">
      <table class="w-full border-collapse">
        <thead :class="stickyHeader ? 'sticky top-0 z-10' : ''">
          <tr class="bg-stone-50 border-b border-stone-200">
            <th
              v-for="col in columns"
              :key="col.key"
              scope="col"
              :style="col.width ? { width: col.width } : undefined"
              :class="['px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider', alignClass(col.align)]"
            >
              <button
                v-if="col.sortable"
                type="button"
                class="inline-flex items-center gap-1 hover:text-gray-800 focus:outline-none focus-visible:shadow-focus-ring rounded"
                @click="emit('sort', col.key)"
              >
                {{ col.label }}
                <AppIcon
                  :name="sortKey === col.key ? (sortDir === 'asc' ? 'chevron-up' : 'chevron-down') : 'chevron-down'"
                  size="xs"
                  :class="sortKey === col.key ? 'text-gray-700' : 'text-stone-300'"
                />
              </button>
              <span v-else>{{ col.label }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-if="loading">
            <tr v-for="i in 5" :key="`skeleton-${i}`" class="border-b border-stone-100">
              <td v-for="col in columns" :key="col.key" class="px-4 py-3">
                <Skeleton />
              </td>
            </tr>
          </template>
          <tr v-else-if="error">
            <td :colspan="columns.length" class="p-0">
              <ErrorState :message="errorMessage" @retry="emit('retry')" />
            </td>
          </tr>
          <tr v-else-if="items.length === 0">
            <td :colspan="columns.length" class="p-0">
              <slot name="empty">
                <EmptyState :title="emptyTitle" :subtitle="emptySubtitle" />
              </slot>
            </td>
          </tr>
          <tr
            v-for="item in (loading || error ? [] : items)"
            :key="rowKey(item)"
            class="border-b border-stone-100 last:border-0 hover:bg-primary-50/30 transition-colors duration-fast cursor-pointer"
            @click="emit('row-click', item)"
          >
            <td v-for="col in columns" :key="col.key" :class="['px-4 py-3 text-sm text-gray-800', alignClass(col.align)]">
              <slot :name="`cell-${col.key}`" :item="item" :value="item[col.key]">
                {{ item[col.key] }}
              </slot>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="showPaginator" class="px-4 py-3 border-t border-stone-100">
      <Paginator :page="page!" :total-pages="totalPages!" :total-items="totalItems" :page-size="pageSize" @update:page="emit('update:page', $event)" />
    </div>
  </div>
</template>
