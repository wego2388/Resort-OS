<script setup lang="ts">
/**
 * POSBeachMapWorkspace.vue — خريطة الشمسيات والبرجولات في كاشير الدايننج.
 *
 * الفرق عن BeachPOSView.vue / BeachMapView.vue:
 * - هنا: الضغط على موقع = فتح طلب أكل (DiningOrder)، مش تذكرة شاطئ.
 * - موقع "occupied" (دخل كاشير الشاطئ ضيف) يظهر مشغول باسم الضيف
 *   والكاشير يقدر يفتح عليه طلب دايننج مباشرة.
 * - موقع "available" يقدر الكاشير يفتح عليه طلب بدون رسوم شاطئ.
 * - موقع له طلب دايننج نشط: يظهر "🍽️ طلب جاري" بجانب اسم الضيف.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS, useResortWebSocket } from '@resort-os/core'
import { AppBadge, AppButton, EmptyState, LoadingState } from '@resort-os/ui'
import type { BeachLocation, ActiveOrder } from './types'

const props = defineProps<{
  branchId: number | null
  activeOrders: ActiveOrder[]  // الطلبات النشطة من الدايننج — لتحديد الشمسيات المشغولة بطلب أكل
}>()

const emit = defineEmits<{
  /** كاشير اختار موقع (سواء فاضي أو مشغول) لفتح طلب دايننج عليه */
  startOrder: [location: BeachLocation]
  /** كاشير ضغط على موقع عنده طلب دايننج نشط — فتح تفاصيل الطلب */
  openOrder: [orderId: number]
}>()

const { t } = useI18n()

const locations = ref<BeachLocation[]>([])
const loading = ref(false)
const error = ref('')

// خريطة: beach_location_id → order نشط (open/in_kitchen/served)
const activeOrderByLocation = computed(() => {
  const map = new Map<number, ActiveOrder>()
  for (const order of props.activeOrders) {
    if (order.beach_location_id != null) {
      map.set(order.beach_location_id, order)
    }
  }
  return map
})

// الـ grid: نحسب حجم الشبكة من أقصى row/col
const gridMaxRow = computed(() => Math.max(...locations.value.map(l => l.grid_row), 1))
const gridMaxCol = computed(() => Math.max(...locations.value.map(l => l.grid_col), 1))

// index الـ locations على الـ grid (row,col) → location
const locationGrid = computed(() => {
  const grid = new Map<string, BeachLocation>()
  for (const loc of locations.value) {
    grid.set(`${loc.grid_row}:${loc.grid_col}`, loc)
  }
  return grid
})

function locationLabel(loc: BeachLocation): string {
  const icons: Record<string, string> = {
    umbrella: '⛱️',
    pergola: '🏕️',
    sunbed: '🛋️',
    cabana: '🏖️',
  }
  return `${icons[loc.location_type] ?? '📍'} ${loc.number}`
}

function locationStatusClass(loc: BeachLocation): string {
  const diningActive = activeOrderByLocation.value.has(loc.id)
  if (loc.status === 'out_of_service') return 'bg-gray-100 dark:bg-gray-800 border-gray-300 text-gray-400 cursor-not-allowed'
  if (diningActive) return 'bg-amber-100 dark:bg-amber-900/40 border-amber-500 text-amber-900 dark:text-amber-200 hover:border-amber-600'
  if (loc.status === 'occupied') return 'bg-blue-100 dark:bg-blue-900/40 border-blue-500 text-blue-900 dark:text-blue-200 hover:border-blue-600'
  return 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-400 text-emerald-900 dark:text-emerald-200 hover:border-emerald-600 hover:bg-emerald-100'
}

function onLocationClick(loc: BeachLocation) {
  if (loc.status === 'out_of_service') return
  const diningOrder = activeOrderByLocation.value.get(loc.id)
  if (diningOrder) {
    emit('openOrder', diningOrder.id)
    return
  }
  emit('startOrder', loc)
}

async function loadLocations() {
  if (!props.branchId) return
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get(ENDPOINTS.beach.locations, {
      params: { branch_id: props.branchId },
    })
    locations.value = data
  } catch {
    error.value = t('backoffice.pos.beachMap.loadError')
  } finally {
    loading.value = false
  }
}

// WS للتحديثات الحية من كاشير الشاطئ (تشيك-إن/تشيك-أوت)
// لا نفتح WS إطلاقاً لو branchId null — useResortWebSocket على URL فاضي
// يعمل connection وهمي على /api/v1/beach/ws/map/0.
const { onMessage: onWsMessage } = useResortWebSocket(
  props.branchId ? ENDPOINTS.beach.mapWs(props.branchId) : '',
)
onWsMessage((message: any) => {
  if (message?.type === 'map_update' && message.location) {
    const updated = message.location as BeachLocation
    const idx = locations.value.findIndex(l => l.id === updated.id)
    if (idx >= 0) locations.value[idx] = updated
    else locations.value.push(updated)
  }
})

onMounted(loadLocations)
</script>

<template>
  <div class="h-full min-h-0 flex flex-col">
    <!-- Header -->
    <div class="bg-white dark:bg-surface border-b border-stone-200 dark:border-border px-4 py-3 flex items-center justify-between gap-3 flex-shrink-0">
      <div>
        <h2 class="font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.pos.beachMap.title') }}</h2>
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ t('backoffice.pos.beachMap.hint') }}</p>
      </div>
      <AppButton variant="ghost" size="sm" :loading="loading" @click="loadLocations">
        {{ t('backoffice.pos.beachMap.refresh') }}
      </AppButton>
    </div>

    <!-- Legend -->
    <div class="bg-stone-50 dark:bg-background border-b border-stone-200 dark:border-border px-4 py-2 flex flex-wrap gap-3 flex-shrink-0">
      <span class="flex items-center gap-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-400">
        <span class="w-3 h-3 rounded-sm bg-emerald-400 inline-block" />
        {{ t('backoffice.pos.beachMap.available') }}
      </span>
      <span class="flex items-center gap-1.5 text-xs font-semibold text-blue-700 dark:text-blue-400">
        <span class="w-3 h-3 rounded-sm bg-blue-400 inline-block" />
        {{ t('backoffice.pos.beachMap.occupiedByBeach') }}
      </span>
      <span class="flex items-center gap-1.5 text-xs font-semibold text-amber-700 dark:text-amber-400">
        <span class="w-3 h-3 rounded-sm bg-amber-400 inline-block" />
        {{ t('backoffice.pos.beachMap.hasDiningOrder') }}
      </span>
      <span class="flex items-center gap-1.5 text-xs font-semibold text-gray-400">
        <span class="w-3 h-3 rounded-sm bg-gray-300 dark:bg-gray-700 inline-block" />
        {{ t('backoffice.pos.beachMap.outOfService') }}
      </span>
    </div>

    <!-- Map content -->
    <div class="flex-1 min-h-0 overflow-auto p-4">
      <LoadingState v-if="loading" :label="t('backoffice.pos.beachMap.loading')" />

      <p v-else-if="error" role="alert" class="text-danger text-sm text-center py-8">{{ error }}</p>

      <EmptyState
        v-else-if="locations.length === 0"
        icon="⛱️"
        :title="t('backoffice.pos.beachMap.empty')"
        :subtitle="t('backoffice.pos.beachMap.emptyHint')"
      />

      <!-- Grid layout — بيحاكي BeachMapView بس مبسّط للـ POS -->
      <div
        v-else
        class="inline-grid gap-2"
        :style="{
          gridTemplateColumns: `repeat(${gridMaxCol}, minmax(90px, 1fr))`,
          gridTemplateRows: `repeat(${gridMaxRow}, auto)`,
        }"
      >
        <template v-for="row in gridMaxRow" :key="row">
          <template v-for="col in gridMaxCol" :key="`${row}:${col}`">
            <div
              v-if="locationGrid.get(`${row}:${col}`)"
              :key="`loc-${locationGrid.get(`${row}:${col}`)!.id}`"
            >
              <button
                type="button"
                :disabled="locationGrid.get(`${row}:${col}`)!.status === 'out_of_service'"
                :class="[
                  'w-full min-h-[80px] rounded-xl border-2 p-2 flex flex-col justify-between gap-1 transition-all text-start',
                  'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
                  locationStatusClass(locationGrid.get(`${row}:${col}`)!),
                ]"
                @click="onLocationClick(locationGrid.get(`${row}:${col}`)!)"
              >
                <div class="font-black text-sm leading-snug">
                  {{ locationLabel(locationGrid.get(`${row}:${col}`)!) }}
                </div>

                <!-- ضيف شاطئ مشغول -->
                <div
                  v-if="locationGrid.get(`${row}:${col}`)!.status === 'occupied' && locationGrid.get(`${row}:${col}`)!.guest_name"
                  class="text-xs leading-snug truncate font-semibold"
                >
                  {{ locationGrid.get(`${row}:${col}`)!.guest_name }}
                </div>

                <!-- طلب دايننج نشط -->
                <AppBadge
                  v-if="activeOrderByLocation.has(locationGrid.get(`${row}:${col}`)!.id)"
                  variant="warning"
                  size="sm"
                  class="self-start"
                >
                  🍽️ {{ activeOrderByLocation.get(locationGrid.get(`${row}:${col}`)!.id)!.order_number }}
                </AppBadge>

                <div
                  v-else-if="locationGrid.get(`${row}:${col}`)!.status === 'available'"
                  class="text-xs text-emerald-600 dark:text-emerald-400 font-semibold"
                >
                  {{ t('backoffice.pos.beachMap.tap') }}
                </div>

                <div
                  v-else-if="locationGrid.get(`${row}:${col}`)!.status === 'out_of_service'"
                  class="text-xs"
                >
                  {{ t('backoffice.pos.beachMap.oos') }}
                </div>
              </button>
            </div>
            <!-- خلية فاضية في الـ grid -->
            <div v-else class="min-h-[80px] rounded-xl border-2 border-dashed border-stone-200 dark:border-stone-700 opacity-30" />
          </template>
        </template>
      </div>
    </div>
  </div>
</template>
