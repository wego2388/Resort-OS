<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppBadge, AppButton, AppSelect, EmptyState, LoadingState, SearchInput } from '@resort-os/ui'
import type { SelectOption } from '@resort-os/ui'
import type { ActiveOrder, DiningOutlet, VenueTable } from './types'

const props = defineProps<{
  orders: ActiveOrder[]
  outlets: DiningOutlet[]
  tables: VenueTable[]
  loading: boolean
  initialOutletId?: number | null
}>()
const emit = defineEmits<{
  open: [orderId: number]
  refresh: []
}>()

const { t, locale } = useI18n()
const { formatMoney, formatTime } = useStaffFormat()
const query = ref('')
const statusFilter = ref('all')
const outletFilter = ref('all')
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  outletFilter.value = props.initialOutletId ? String(props.initialOutletId) : 'all'
  timer = setInterval(() => { now.value = Date.now() }, 30_000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const outletOptions = computed<SelectOption[]>(() => [
  { value: 'all', label: t('backoffice.pos.activeOrders.allOutlets') },
  ...props.outlets.map(outlet => ({
    value: String(outlet.id),
    label: locale.value === 'ar' ? (outlet.name_ar || outlet.name) : outlet.name,
  })),
])

const statusFilters = computed(() => [
  { value: 'all', label: t('backoffice.pos.activeOrders.all'), count: props.orders.length },
  { value: 'open', label: t('backoffice.pos.orderStatus.open'), count: countStatus('open') },
  { value: 'in_kitchen', label: t('backoffice.pos.orderStatus.inKitchen'), count: countStatus('in_kitchen') },
  { value: 'served', label: t('backoffice.pos.orderStatus.served'), count: countStatus('served') },
])

function countStatus(status: string): number {
  return props.orders.filter(order => order.status === status).length
}

const filteredOrders = computed(() => {
  const normalized = query.value.trim().toLowerCase()
  return props.orders.filter(order => {
    if (statusFilter.value !== 'all' && order.status !== statusFilter.value) return false
    if (outletFilter.value !== 'all' && order.outlet_id !== Number(outletFilter.value)) return false
    if (!normalized) return true
    return order.order_number.toLowerCase().includes(normalized) ||
      tableLabel(order).toLowerCase().includes(normalized) ||
      outletName(order.outlet_id).toLowerCase().includes(normalized)
  }).sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
})

function outletName(outletId: number): string {
  const outlet = props.outlets.find(item => item.id === outletId)
  if (!outlet) return t('backoffice.pos.activeOrders.unknownOutlet')
  return locale.value === 'ar' ? (outlet.name_ar || outlet.name) : outlet.name
}

function tableLabel(order: ActiveOrder): string {
  if (!order.table_id) return t(`backoffice.pos.orderTypes.${orderTypeKey(order.order_type)}`)
  const table = props.tables.find(item => item.id === order.table_id)
  return table
    ? t('backoffice.pos.tableLabel', { number: table.table_number })
    : t('backoffice.pos.tableLabel', { number: order.table_id })
}

function orderTypeKey(type: ActiveOrder['order_type']): string {
  return {
    dine_in: 'dineIn',
    takeaway: 'takeaway',
    delivery: 'delivery',
    room_service: 'roomService',
  }[type]
}

function statusLabel(status: string): string {
  const key: Record<string, string> = {
    open: 'open',
    in_kitchen: 'inKitchen',
    served: 'served',
    held: 'held',
  }
  return key[status] ? t(`backoffice.pos.orderStatus.${key[status]}`) : status
}

function statusVariant(status: string): 'info' | 'warning' | 'success' | 'neutral' {
  if (status === 'served') return 'warning'
  if (status === 'in_kitchen') return 'info'
  if (status === 'open') return 'success'
  return 'neutral'
}

function elapsed(createdAt: string): string {
  const normalized = createdAt.endsWith('Z') ? createdAt : `${createdAt}Z`
  const created = new Date(normalized).getTime()
  if (!Number.isFinite(created)) return ''
  const minutes = Math.max(0, Math.floor((now.value - created) / 60_000))
  if (minutes < 60) return t('backoffice.pos.elapsedMinutes', { count: minutes })
  return t('backoffice.pos.elapsedHoursMinutes', {
    hours: Math.floor(minutes / 60),
    minutes: minutes % 60,
  })
}

/** دقائق منذ إنشاء الطلب — لتحديد الأولوية البصرية */
function elapsedMinutes(createdAt: string): number {
  const normalized = createdAt.endsWith('Z') ? createdAt : `${createdAt}Z`
  const created = new Date(normalized).getTime()
  if (!Number.isFinite(created)) return 0
  return Math.max(0, Math.floor((now.value - created) / 60_000))
}

/** border + ring urgency class على كارت الطلب */
function orderUrgencyClass(order: { status: string; created_at: string }): string {
  if (order.status === 'served') return 'border-amber-400 dark:border-amber-500'
  const mins = elapsedMinutes(order.created_at)
  if (mins >= 45) return 'border-red-500 dark:border-red-400 shadow-red-100 dark:shadow-red-900/20'
  if (mins >= 20) return 'border-amber-400 dark:border-amber-500'
  return 'border-stone-200 dark:border-border'
}
</script>

<template>
  <section class="h-full min-h-0 overflow-y-auto bg-stone-50/80 dark:bg-background p-4 lg:p-5">
    <div class="max-w-[1500px] mx-auto space-y-4">
      <div class="flex flex-col xl:flex-row xl:items-end justify-between gap-4">
        <div>
          <h1 class="text-xl font-black text-gray-950 dark:text-gray-100">{{ t('backoffice.pos.activeOrdersTitle') }}</h1>
          <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ t('backoffice.pos.activeOrders.hint') }}</p>
        </div>
        <div class="flex flex-col sm:flex-row gap-2 w-full xl:w-auto">
          <div class="sm:w-64">
            <SearchInput
              v-model="query"
              :placeholder="t('backoffice.pos.activeOrders.search')"
              :clear-label="t('backoffice.pos.activeOrders.clearSearch')"
            />
          </div>
          <div class="sm:w-52">
            <AppSelect
              v-model="outletFilter"
              :options="outletOptions"
              :placeholder="t('backoffice.pos.activeOrders.allOutlets')"
            />
          </div>
          <AppButton variant="outline" :loading="loading" @click="emit('refresh')">
            {{ t('backoffice.pos.activeOrders.refresh') }}
          </AppButton>
        </div>
      </div>

      <div class="flex gap-2 overflow-x-auto pb-1" role="tablist" :aria-label="t('backoffice.pos.activeOrders.statusFilter')">
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

      <LoadingState v-if="loading && orders.length === 0" :label="t('backoffice.pos.activeOrders.loading')" />
      <EmptyState
        v-else-if="filteredOrders.length === 0"
        icon="🧾"
        :title="t('backoffice.pos.noActiveOrders')"
        :subtitle="t('backoffice.pos.activeOrders.noResultsHint')"
      />
      <div v-else class="grid md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
        <button
          v-for="order in filteredOrders"
          :key="order.id"
          type="button"
          :class="['min-h-[156px] rounded-2xl border-2 bg-white dark:bg-surface p-4 text-start shadow-sm hover:shadow-md transition-all flex flex-col justify-between gap-4 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2', orderUrgencyClass(order)]"
          @click="emit('open', order.id)"
        >
          <div class="w-full">
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="text-lg font-black text-gray-950 dark:text-gray-100">{{ order.order_number }}</div>
                <div class="text-sm font-semibold text-gray-600 dark:text-gray-300 mt-1">{{ tableLabel(order) }}</div>
              </div>
              <AppBadge :variant="statusVariant(order.status)">{{ statusLabel(order.status) }}</AppBadge>
            </div>
            <div class="flex flex-wrap gap-x-3 gap-y-1 text-sm text-gray-500 dark:text-gray-400 mt-3">
              <span>{{ outletName(order.outlet_id) }}</span>
              <span>{{ t('backoffice.pos.activeOrders.guestsCount', { count: order.guests_count }) }}</span>
            </div>
          </div>
          <div class="w-full flex items-end justify-between gap-3 pt-3 border-t border-stone-100 dark:border-border">
            <div class="text-xs text-gray-500 dark:text-gray-400">
              <div>{{ formatTime(order.created_at) }}</div>
              <div
                :class="['font-black mt-1',
                  elapsedMinutes(order.created_at) >= 45 ? 'text-red-600 dark:text-red-400' :
                  elapsedMinutes(order.created_at) >= 20 ? 'text-amber-600 dark:text-amber-400' :
                  'text-gray-600 dark:text-gray-300']"
              >{{ elapsed(order.created_at) }}</div>
            </div>
            <div class="text-xl font-black text-primary-800 dark:text-primary-300 tabular-nums">
              {{ formatMoney(order.total, 'EGP') }}
            </div>
          </div>
        </button>
      </div>
    </div>
  </section>
</template>
