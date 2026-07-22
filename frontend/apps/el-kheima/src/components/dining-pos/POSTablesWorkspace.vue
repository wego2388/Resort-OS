<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppBadge, EmptyState, SearchInput } from '@resort-os/ui'
import type { DiningOutlet, VenueTable } from './types'

const props = defineProps<{
  tables: VenueTable[]
  outlets: DiningOutlet[]
  selectedOutletId: number | null
}>()
const emit = defineEmits<{
  start: [table: VenueTable]
  open: [orderId: number]
}>()

const { t, locale } = useI18n()
const { formatMoney } = useStaffFormat()
const query = ref('')
const statusFilter = ref('all')
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  timer = setInterval(() => { now.value = Date.now() }, 30_000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const statusFilters = computed(() => [
  { value: 'all', label: t('backoffice.pos.tableSummary.all'), count: props.tables.length },
  { value: 'available', label: t('backoffice.pos.tableSummary.available'), count: countStatus('available') },
  { value: 'occupied', label: t('backoffice.pos.tableSummary.occupied'), count: countStatus('occupied') },
  { value: 'served', label: t('backoffice.pos.tableSummary.waitingPayment'), count: countStatus('served') },
  { value: 'reserved', label: t('backoffice.pos.tableSummary.reserved'), count: countStatus('reserved') },
])

function countStatus(status: string): number {
  return props.tables.filter(table => tableState(table) === status).length
}

function tableState(table: VenueTable): string {
  return table.order_status === 'served' ? 'served' : table.status
}

const filteredTables = computed(() => {
  const normalized = query.value.trim().toLowerCase()
  return props.tables.filter(table => {
    if (statusFilter.value !== 'all' && tableState(table) !== statusFilter.value) return false
    if (!normalized) return true
    return table.table_number.toLowerCase().includes(normalized) ||
      (table.section ?? '').toLowerCase().includes(normalized) ||
      (table.active_order_number ?? '').toLowerCase().includes(normalized)
  })
})

const groupedTables = computed(() => {
  const groups = new Map<string, VenueTable[]>()
  for (const table of filteredTables.value) {
    const section = table.section || t('backoffice.pos.noSection')
    if (!groups.has(section)) groups.set(section, [])
    groups.get(section)!.push(table)
  }
  return [...groups.entries()].map(([section, tables]) => ({ section, tables }))
})

function outletName(id: number | null): string {
  if (id === null) return ''
  const outlet = props.outlets.find(item => item.id === id)
  if (!outlet) return ''
  return locale.value === 'ar' ? (outlet.name_ar || outlet.name) : outlet.name
}

function elapsed(occupiedAt: string | null): string {
  if (!occupiedAt) return ''
  const started = new Date(occupiedAt.endsWith('Z') ? occupiedAt : `${occupiedAt}Z`).getTime()
  if (!Number.isFinite(started)) return ''
  const minutes = Math.max(0, Math.floor((now.value - started) / 60_000))
  if (minutes < 60) return t('backoffice.pos.elapsedMinutes', { count: minutes })
  return t('backoffice.pos.elapsedHoursMinutes', {
    hours: Math.floor(minutes / 60),
    minutes: minutes % 60,
  })
}

function statusLabel(status: string): string {
  const key: Record<string, string> = {
    available: 'available',
    occupied: 'occupied',
    served: 'served',
    reserved: 'reserved',
    out_of_service: 'outOfService',
  }
  return key[status]
    ? t(`backoffice.pos.tableStatus.${key[status]}`)
    : status
}

function activate(table: VenueTable) {
  if (tableState(table) === 'out_of_service') return
  if (table.active_order_id) emit('open', table.active_order_id)
  else emit('start', table)
}
</script>

<template>
  <section class="h-full min-h-0 overflow-y-auto bg-stone-50/80 dark:bg-background p-4 lg:p-5">
    <div class="max-w-[1600px] mx-auto space-y-4">
      <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        <div>
          <h1 class="text-xl font-black text-gray-950 dark:text-gray-100">{{ t('backoffice.pos.tablesWorkspace.title') }}</h1>
          <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ t('backoffice.pos.tablesWorkspace.hint') }}</p>
        </div>
        <div class="w-full lg:w-80">
          <SearchInput
            v-model="query"
            :placeholder="t('backoffice.pos.tablesWorkspace.search')"
            :clear-label="t('backoffice.pos.tablesWorkspace.clearSearch')"
          />
        </div>
      </div>

      <div class="flex gap-2 overflow-x-auto pb-1" role="tablist" :aria-label="t('backoffice.pos.tablesWorkspace.filterLabel')">
        <button
          v-for="filter in statusFilters"
          :key="filter.value"
          type="button"
          role="tab"
          :aria-selected="statusFilter === filter.value"
          :class="[
            'min-h-[44px] whitespace-nowrap px-4 rounded-xl border-2 font-bold text-sm transition-colors',
            statusFilter === filter.value
              ? 'border-primary-700 bg-primary-700 text-white'
              : 'border-stone-200 dark:border-border bg-white dark:bg-surface text-gray-700 dark:text-gray-300',
          ]"
          @click="statusFilter = filter.value"
        >
          {{ filter.label }} · {{ filter.count }}
        </button>
      </div>

      <EmptyState
        v-if="groupedTables.length === 0"
        icon="🍽️"
        :title="tables.length === 0 ? t('backoffice.pos.noTables') : t('backoffice.pos.tablesWorkspace.noResults')"
      />

      <section v-for="group in groupedTables" :key="group.section" class="space-y-2">
        <div class="flex items-center gap-2">
          <h2 class="font-black text-gray-900 dark:text-gray-100">{{ group.section }}</h2>
          <AppBadge variant="neutral" size="sm">{{ group.tables.length }}</AppBadge>
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-3">
          <button
            v-for="table in group.tables"
            :key="table.id"
            type="button"
            :disabled="tableState(table) === 'out_of_service'"
            :class="[
              'relative min-h-[124px] rounded-2xl border-2 p-4 text-start transition-all flex flex-col justify-between gap-3 shadow-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
              tableState(table) === 'available' ? 'bg-white dark:bg-surface border-emerald-300 hover:border-emerald-500' : '',
              tableState(table) === 'occupied' ? 'bg-red-50 dark:bg-red-950/20 border-red-300 hover:border-red-500' : '',
              tableState(table) === 'served' ? 'bg-amber-50 dark:bg-amber-950/20 border-amber-300 hover:border-amber-500' : '',
              tableState(table) === 'reserved' ? 'bg-blue-50 dark:bg-blue-950/20 border-blue-300 hover:border-blue-500' : '',
              tableState(table) === 'out_of_service' ? 'bg-gray-100 dark:bg-gray-800 border-gray-200 opacity-60 cursor-not-allowed' : '',
            ]"
            @click="activate(table)"
          >
            <div class="flex items-start justify-between gap-3 w-full">
              <div>
                <div class="text-2xl font-black text-gray-950 dark:text-gray-100">{{ table.table_number }}</div>
                <div class="text-sm font-bold mt-1 text-gray-600 dark:text-gray-300">{{ statusLabel(tableState(table)) }}</div>
              </div>
              <span
                :class="[
                  'w-3 h-3 rounded-full mt-1',
                  tableState(table) === 'available' ? 'bg-emerald-500' : '',
                  tableState(table) === 'occupied' ? 'bg-red-500' : '',
                  tableState(table) === 'served' ? 'bg-amber-500' : '',
                  tableState(table) === 'reserved' ? 'bg-blue-500' : '',
                  tableState(table) === 'out_of_service' ? 'bg-gray-400' : '',
                ]"
                aria-hidden="true"
              />
            </div>

            <div v-if="table.active_order_id" class="space-y-1 text-sm w-full">
              <div class="flex items-center justify-between gap-2">
                <span class="font-semibold text-gray-700 dark:text-gray-300 truncate">{{ table.active_order_number }}</span>
                <span v-if="table.occupied_at" class="text-gray-500 dark:text-gray-400 tabular-nums">{{ elapsed(table.occupied_at) }}</span>
              </div>
              <div class="flex items-center justify-between gap-2">
                <span class="text-gray-500 dark:text-gray-400">{{ outletName(table.active_order_outlet_id) }}</span>
                <span class="font-black text-gray-900 dark:text-gray-100 tabular-nums">{{ formatMoney(table.active_order_total, 'EGP') }}</span>
              </div>
              <div v-if="table.active_covers" class="text-xs text-gray-500 dark:text-gray-400">
                {{ t('backoffice.pos.tablesWorkspace.coversCount', { count: table.active_covers }) }}
              </div>
            </div>
            <div v-else class="text-sm font-semibold text-emerald-700 dark:text-emerald-300">
              {{ t('backoffice.pos.tablesWorkspace.startOrder') }}
            </div>
          </button>
        </div>
      </section>
    </div>
  </section>
</template>
