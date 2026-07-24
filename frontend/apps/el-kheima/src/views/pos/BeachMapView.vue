<script setup lang="ts">
/**
 * BeachMapView — خريطة الشاطئ الحية. قبل هذا التعديل، الشاطئ كان بيتتبّع
 * بس بعدّاد سعة مجمّع (BeachInventory.capacity_used/capacity_max) + سجل
 * عمليات بيع (BeachTransaction) — مفيش مفهوم "شمسية/برجولة فعلية" ولا شاشة
 * بصرية يقدر الموظف يبص عليها طول اليوم يشوف مين قاعد فين، نفس فئة الفجوة
 * اللي اتصلحت قبل كده للمطعم (TablesView.vue) بس الشاطئ ماكانش عنده حتى
 * نموذج بيانات لموقع فعلي واحد.
 *
 * تسجيل الدخول/الخروج هنا عملية بيع حقيقية عبر beach.services.checkin_location
 * (نفس sell_ticket الداخلي — تسعير/VAT/قيد محاسبي)، مش مجرد تلوين مربّع.
 * التحديثات الحية بتوصل لكل الكاشيرين/المشرفين الفاتحين الشاشة في نفس
 * الوقت عبر WebSocket (نفس نمط KDS/تنبيهات الضيوف — useResortWebSocket).
 */
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore, useResortWebSocket, ENDPOINTS, parseApiTimestamp } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppModal, EmptyState, useConfirm, useToast } from '@resort-os/ui'

const auth = useAuthStore()
const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatTime: fmtTimeFn } = useStaffFormat()
const branchId = computed(() => auth.branchId ?? 1)
const isManager = computed(() => auth.hasRole('manager'))

interface BeachLocation {
  id: number
  branch_id: number
  location_type: string
  number: string
  grid_row: number
  grid_col: number
  status: 'available' | 'occupied' | 'out_of_service'
  current_transaction_id: number | null
  guest_name: string | null
  guest_phone: string | null
  guests_count: number
  towels_given: number
  checked_in_at: string | null
  checked_in_by: number | null
}

const TYPE_LABELS = computed<Record<string, string>>(() => ({
  umbrella: t('backoffice.beachMap.type.umbrella'), pergola: t('backoffice.beachMap.type.pergola'),
  sunbed: t('backoffice.beachMap.type.sunbed'), cabana: t('backoffice.beachMap.type.cabana'),
}))
function typeLabel(locType: string) { return TYPE_LABELS.value[locType] ?? locType }

const TYPE_ICONS: Record<string, string> = {
  umbrella: '⛱️', pergola: '🏝️', sunbed: '🛏️', cabana: '🏖️',
}
function typeIcon(locType: string) { return TYPE_ICONS[locType] ?? '📍' }

const locations = ref<BeachLocation[]>([])
const loading = ref(false)

const sections = computed(() => {
  const map = new Map<string, BeachLocation[]>()
  for (const loc of locations.value) {
    if (!map.has(loc.location_type)) map.set(loc.location_type, [])
    map.get(loc.location_type)!.push(loc)
  }
  for (const list of map.values()) {
    list.sort((a, b) => a.grid_row - b.grid_row || a.grid_col - b.grid_col)
  }
  return Array.from(map.entries())
})

const stats = computed(() => ({
  total: locations.value.length,
  available: locations.value.filter(l => l.status === 'available').length,
  occupied: locations.value.filter(l => l.status === 'occupied').length,
  outOfService: locations.value.filter(l => l.status === 'out_of_service').length,
}))

async function fetchLocations() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.beach.locations, { params: { branch_id: branchId.value } })
    locations.value = data
  } catch (e) {
    toast.error(t('backoffice.beachMap.loadMapError'))
  } finally {
    loading.value = false
  }
}

function upsertLocation(loc: BeachLocation) {
  const idx = locations.value.findIndex(l => l.id === loc.id)
  if (idx >= 0) locations.value[idx] = loc
  else locations.value.push(loc)
}

// اتصال لحظي — نفس نمط KDS/تنبيهات الضيوف (useResortWebSocket بيعيد
// الاتصال تلقائيًا لو النت اتقطع).
const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
const { status: wsStatus, onMessage } = useResortWebSocket(
  `${wsProtocol}//${location.host}/api/v1/beach/ws/map/${branchId.value}`,
)
onMessage((data: any) => {
  if (data?.type === 'map_update' && data.location) {
    upsertLocation(data.location)
  } else if (data?.type === 'locations_changed') {
    fetchLocations()
  }
})

function statusColor(loc: BeachLocation): string {
  if (loc.status === 'occupied') return 'bg-red-100 border-red-400 text-red-800 active:bg-red-200 dark:bg-red-950/50 dark:border-red-800 dark:text-red-200 dark:active:bg-red-900/60'
  if (loc.status === 'out_of_service') return 'bg-gray-100 border-gray-300 text-gray-400 dark:bg-gray-800 dark:border-gray-700 dark:text-gray-400'
  return 'bg-green-100 border-green-400 text-green-800 active:bg-green-200 dark:bg-green-950/50 dark:border-green-800 dark:text-green-200 dark:active:bg-green-900/60'
}

function statusLabel(status: string): string {
  if (status === 'occupied') return t('backoffice.beachMap.occupied')
  if (status === 'out_of_service') return t('backoffice.beachMap.outOfService')
  return t('backoffice.beachMap.available')
}

// ── Check-in modal ──────────────────────────────────────────────────────
const checkinModalOpen = ref(false)
const checkinTarget = ref<BeachLocation | null>(null)
const checkinForm = ref({ guest_name: '', guest_phone: '', guests_count: 1, with_towel: false })
const checkinSubmitting = ref(false)

function openCheckin(loc: BeachLocation) {
  checkinTarget.value = loc
  checkinForm.value = { guest_name: '', guest_phone: '', guests_count: 1, with_towel: false }
  checkinModalOpen.value = true
}

async function submitCheckin() {
  if (!checkinTarget.value) return
  checkinSubmitting.value = true
  try {
    const { data } = await api.post(
      ENDPOINTS.beach.locationCheckin(checkinTarget.value.id),
      {
        guest_name: checkinForm.value.guest_name || null,
        guest_phone: checkinForm.value.guest_phone || null,
        guests_count: checkinForm.value.guests_count,
        with_towel: checkinForm.value.with_towel,
      },
      { params: { branch_id: branchId.value } },
    )
    upsertLocation(data)
    checkinModalOpen.value = false
    toast.success(t('backoffice.beachMap.checkedInToast', { type: typeLabel(checkinTarget.value.location_type), number: checkinTarget.value.number }))
  } catch (e: any) {
    if (e?.response?.status === 409) {
      toast.error(t('backoffice.beachMap.locationTakenError'))
      fetchLocations()
    } else {
      toast.error(e?.response?.data?.detail ?? t('backoffice.beachMap.checkInError'))
    }
  } finally {
    checkinSubmitting.value = false
  }
}

// ── Occupied detail / checkout ───────────────────────────────────────────
const detailModalOpen = ref(false)
const detailTarget = ref<BeachLocation | null>(null)
const checkoutSubmitting = ref(false)

function openDetail(loc: BeachLocation) {
  detailTarget.value = loc
  detailModalOpen.value = true
}

async function submitCheckout() {
  if (!detailTarget.value) return
  const ok = await confirm({
    title: t('backoffice.beachMap.confirmCheckOutTitle'),
    message: t('backoffice.beachMap.confirmCheckOutMessage', { guest: detailTarget.value.guest_name || t('backoffice.beachMap.theGuest'), type: typeLabel(detailTarget.value.location_type), number: detailTarget.value.number }),
    confirmText: t('backoffice.beachMap.checkOutAction'), danger: true,
  })
  if (!ok) return
  checkoutSubmitting.value = true
  try {
    const { data } = await api.post(
      ENDPOINTS.beach.locationCheckout(detailTarget.value.id),
      {}, { params: { branch_id: branchId.value } },
    )
    upsertLocation(data)
    detailModalOpen.value = false
    toast.success(t('backoffice.beachMap.checkedOutToast'))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.beachMap.checkOutError'))
  } finally {
    checkoutSubmitting.value = false
  }
}

function onTileClick(loc: BeachLocation) {
  if (loc.status === 'available') openCheckin(loc)
  else if (loc.status === 'occupied') openDetail(loc)
  else if (isManager.value) toggleOutOfService(loc) // out_of_service — manager can reactivate
}

// ── Manager: reactivate / disable a single spot ─────────────────────────
async function toggleOutOfService(loc: BeachLocation) {
  const makeAvailable = loc.status === 'out_of_service'
  try {
    const { data } = await api.patch(
      ENDPOINTS.beach.locationUpdate(loc.id),
      { status: makeAvailable ? 'available' : 'out_of_service' },
      { params: { branch_id: branchId.value } },
    )
    upsertLocation(data)
    toast.success(makeAvailable ? t('backoffice.beachMap.locationReactivated') : t('backoffice.beachMap.locationDisabled'))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.beachMap.updateLocationError'))
  }
}

// ── Manager: bulk add / reduce ───────────────────────────────────────────
const bulkAddModalOpen = ref(false)
const bulkAddForm = ref({ location_type: 'umbrella', count: 5 })
const bulkAddSubmitting = ref(false)

const bulkReduceModalOpen = ref(false)
const bulkReduceForm = ref({ location_type: '', count: 1 })
const bulkReduceSubmitting = ref(false)

const existingTypes = computed(() => Array.from(new Set(locations.value.map(l => l.location_type))))

async function submitBulkAdd() {
  bulkAddSubmitting.value = true
  try {
    await api.post(ENDPOINTS.beach.locationsBulk, {
      branch_id: branchId.value,
      location_type: bulkAddForm.value.location_type,
      count: bulkAddForm.value.count,
    })
    bulkAddModalOpen.value = false
    toast.success(t('backoffice.beachMap.locationsAdded', { count: bulkAddForm.value.count }))
    fetchLocations()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.beachMap.addLocationsError'))
  } finally {
    bulkAddSubmitting.value = false
  }
}

function openBulkReduce() {
  bulkReduceForm.value = { location_type: existingTypes.value[0] ?? '', count: 1 }
  bulkReduceModalOpen.value = true
}

async function submitBulkReduce() {
  bulkReduceSubmitting.value = true
  try {
    await api.post(ENDPOINTS.beach.locationsReduce, {
      branch_id: branchId.value,
      location_type: bulkReduceForm.value.location_type,
      count: bulkReduceForm.value.count,
    })
    bulkReduceModalOpen.value = false
    toast.success(t('backoffice.beachMap.locationsRemoved', { count: bulkReduceForm.value.count }))
    fetchLocations()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.beachMap.removeLocationsError'))
  } finally {
    bulkReduceSubmitting.value = false
  }
}

onMounted(fetchLocations)
</script>

<template>
  <div class="page-container">
    <div class="flex items-center justify-between mb-4 gap-2 flex-wrap">
      <div class="flex items-center gap-3">
        <h1 class="section-title mb-0">{{ t('backoffice.beachMap.title') }}</h1>
        <span
          class="w-2 h-2 rounded-full flex-shrink-0"
          :class="wsStatus === 'connected' ? 'bg-green-500' : 'bg-amber-500 animate-pulse'"
          :title="wsStatus === 'connected' ? t('backoffice.beachMap.liveConnected') : t('backoffice.beachMap.reconnecting')"
        />
      </div>
      <div v-if="isManager" class="flex items-center gap-2">
        <button
          @click="bulkAddModalOpen = true"
          class="px-4 py-2 bg-blue-700 text-white rounded-xl font-bold text-sm hover:bg-blue-800 active:scale-95 transition-all shadow-sm"
        >➕ {{ t('backoffice.beachMap.addLocations') }}</button>
        <button
          @click="openBulkReduce"
          :disabled="locations.length === 0"
          class="rounded-xl border-2 border-red-300 bg-white px-4 py-2 text-sm font-bold text-red-700 shadow-sm transition-all hover:bg-red-50 active:scale-95 disabled:opacity-40 dark:border-red-800 dark:bg-surface dark:text-red-300 dark:hover:bg-red-950/40"
        >➖ {{ t('backoffice.beachMap.removeLocations') }}</button>
      </div>
    </div>

    <!-- Summary stats -->
    <div v-if="locations.length > 0" class="grid grid-cols-3 gap-3 mb-5">
      <div class="rounded-xl border border-green-100 bg-green-50 p-3 text-center dark:border-green-900 dark:bg-green-950/40">
        <div class="text-2xl font-black text-green-700 dark:text-green-300">{{ stats.available }}</div>
        <div class="mt-0.5 text-xs text-green-600 dark:text-green-400">{{ t('backoffice.beachMap.available') }}</div>
      </div>
      <div class="rounded-xl border border-red-100 bg-red-50 p-3 text-center dark:border-red-900 dark:bg-red-950/40">
        <div class="text-2xl font-black text-red-700 dark:text-red-300">{{ stats.occupied }}</div>
        <div class="mt-0.5 text-xs text-red-600 dark:text-red-400">{{ t('backoffice.beachMap.occupied') }}</div>
      </div>
      <div class="rounded-xl border border-gray-200 bg-gray-50 p-3 text-center dark:border-gray-700 dark:bg-gray-800/60">
        <div class="text-2xl font-black text-gray-500">{{ stats.outOfService }}</div>
        <div class="text-xs text-gray-500 mt-0.5">{{ t('backoffice.beachMap.outOfService') }}</div>
      </div>
    </div>

    <div v-if="loading && locations.length === 0" class="flex items-center justify-center h-40">
      <div class="motion-safe:animate-spin w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full" />
    </div>

    <EmptyState
      v-else-if="locations.length === 0"
      icon="🏖️"
      :title="t('backoffice.beachMap.noLocations')"
      :description="isManager ? t('backoffice.beachMap.noLocationsManagerHint') : t('backoffice.beachMap.noLocationsStaffHint')"
    />

    <div v-else class="space-y-6">
      <div v-for="[type, typeLocations] in sections" :key="type">
        <h2 class="text-sm font-bold text-gray-500 uppercase tracking-wide mb-2">
          {{ typeIcon(type) }} {{ typeLabel(type) }} ({{ typeLocations.length }})
        </h2>
        <div class="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-3">
          <button
            v-for="loc in typeLocations"
            :key="loc.id"
            @click="onTileClick(loc)"
            :class="[
              'aspect-square rounded-2xl border-2 flex flex-col items-center justify-center gap-0.5 font-bold transition-all active:scale-95 shadow-sm relative',
              statusColor(loc),
            ]"
          >
            <span class="text-xl leading-none">{{ typeIcon(loc.location_type) }}</span>
            <span class="text-base leading-none">{{ loc.number }}</span>
            <span class="text-[10px] font-medium">{{ statusLabel(loc.status) }}</span>
            <span v-if="loc.status === 'occupied' && loc.guest_name" class="text-[9px] opacity-70 truncate max-w-full px-1">
              {{ loc.guest_name }}
            </span>
          </button>
        </div>
      </div>
    </div>

    <!-- ── Check-in modal ── -->
    <AppModal :open="checkinModalOpen" :title="t('backoffice.beachMap.checkInModalTitle')" size="sm" @close="checkinModalOpen = false">
      <div v-if="checkinTarget" class="space-y-3">
        <p class="text-sm text-gray-500">
          {{ typeIcon(checkinTarget.location_type) }} {{ typeLabel(checkinTarget.location_type) }} {{ checkinTarget.number }}
        </p>
        <div>
          <label class="mb-1 block text-xs font-bold text-gray-600 dark:text-gray-300">{{ t('backoffice.beachMap.guestNameOptional') }}</label>
          <input v-model="checkinForm.guest_name" type="text" class="w-full px-3 py-2 border border-stone-200 dark:border-border rounded-lg text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-bold text-gray-600 dark:text-gray-300">{{ t('backoffice.beachMap.phoneOptional') }}</label>
          <input v-model="checkinForm.guest_phone" type="text" class="w-full px-3 py-2 border border-stone-200 dark:border-border rounded-lg text-sm" dir="ltr" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-bold text-gray-600 dark:text-gray-300">{{ t('backoffice.beachMap.guestsCount') }}</label>
          <input v-model.number="checkinForm.guests_count" type="number" min="1" class="w-full px-3 py-2 border border-stone-200 dark:border-border rounded-lg text-sm" />
        </div>
        <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
          <input v-model="checkinForm.with_towel" type="checkbox" class="rounded border-stone-300 dark:border-gray-600" />
          {{ t('backoffice.beachMap.withTowel') }}
        </label>
      </div>
      <template #footer>
        <div class="flex gap-2">
          <button @click="checkinModalOpen = false" class="flex-1 rounded-xl border-2 border-stone-200 py-2.5 font-semibold text-gray-600 hover:bg-gray-50 dark:bg-surface-2 dark:border-border dark:text-gray-300 dark:hover:bg-gray-800">{{ t('backoffice.beachMap.cancel') }}</button>
          <button
            @click="submitCheckin" :disabled="checkinSubmitting"
            class="flex-1 py-2.5 rounded-xl bg-blue-700 text-white font-bold hover:bg-blue-800 disabled:opacity-50"
          >{{ checkinSubmitting ? t('backoffice.beachMap.processing') : t('backoffice.beachMap.checkInAction') }}</button>
        </div>
      </template>
    </AppModal>

    <!-- ── Occupied detail / checkout modal ── -->
    <AppModal :open="detailModalOpen" :title="t('backoffice.beachMap.locationDetailsTitle')" size="sm" @close="detailModalOpen = false">
      <div v-if="detailTarget" class="space-y-2 text-sm">
        <p class="font-bold text-gray-900 dark:text-gray-100">
          {{ typeIcon(detailTarget.location_type) }} {{ typeLabel(detailTarget.location_type) }} {{ detailTarget.number }}
        </p>
        <p v-if="detailTarget.guest_name"><span class="text-gray-500">{{ t('backoffice.beachMap.guestLabel') }}</span> {{ detailTarget.guest_name }}</p>
        <p v-if="detailTarget.guest_phone" dir="ltr" class="text-end"><span class="text-gray-500">{{ t('backoffice.beachMap.phoneLabel') }}</span> {{ detailTarget.guest_phone }}</p>
        <p><span class="text-gray-500">{{ t('backoffice.beachMap.guestsCountLabel') }}</span> {{ detailTarget.guests_count }}</p>
        <p><span class="text-gray-500">{{ t('backoffice.beachMap.towelsLabel') }}</span> {{ detailTarget.towels_given }}</p>
        <p v-if="detailTarget.checked_in_at"><span class="text-gray-500">{{ t('backoffice.beachMap.checkInTimeLabel') }}</span> {{ fmtTimeFn(parseApiTimestamp(detailTarget.checked_in_at)) }}</p>
      </div>
      <template #footer>
        <button
          @click="submitCheckout" :disabled="checkoutSubmitting"
          class="w-full py-2.5 rounded-xl bg-red-600 text-white font-bold hover:bg-red-700 disabled:opacity-50"
        >{{ checkoutSubmitting ? t('backoffice.beachMap.processing') : t('backoffice.beachMap.checkOutAction') }}</button>
      </template>
    </AppModal>

    <!-- ── Manager: bulk add modal ── -->
    <AppModal :open="bulkAddModalOpen" :title="t('backoffice.beachMap.addLocations')" size="sm" @close="bulkAddModalOpen = false">
      <div class="space-y-3">
        <div>
          <label class="mb-1 block text-xs font-bold text-gray-600 dark:text-gray-300">{{ t('backoffice.beachMap.locationType') }}</label>
          <input
            v-model="bulkAddForm.location_type" type="text" placeholder="umbrella / pergola / sunbed / cabana"
            class="w-full px-3 py-2 border border-stone-200 dark:border-border rounded-lg text-sm" dir="ltr"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-bold text-gray-600 dark:text-gray-300">{{ t('backoffice.beachMap.count') }}</label>
          <input v-model.number="bulkAddForm.count" type="number" min="1" max="200" class="w-full px-3 py-2 border border-stone-200 dark:border-border rounded-lg text-sm" />
        </div>
      </div>
      <template #footer>
        <div class="flex gap-2">
          <button @click="bulkAddModalOpen = false" class="flex-1 rounded-xl border-2 border-stone-200 py-2.5 font-semibold text-gray-600 hover:bg-gray-50 dark:bg-surface-2 dark:border-border dark:text-gray-300 dark:hover:bg-gray-800">{{ t('backoffice.beachMap.cancel') }}</button>
          <button
            @click="submitBulkAdd" :disabled="bulkAddSubmitting"
            class="flex-1 py-2.5 rounded-xl bg-blue-700 text-white font-bold hover:bg-blue-800 disabled:opacity-50"
          >{{ bulkAddSubmitting ? t('backoffice.beachMap.processing') : t('backoffice.beachMap.add') }}</button>
        </div>
      </template>
    </AppModal>

    <!-- ── Manager: bulk reduce modal ── -->
    <AppModal :open="bulkReduceModalOpen" :title="t('backoffice.beachMap.removeAvailableLocations')" size="sm" @close="bulkReduceModalOpen = false">
      <div class="space-y-3">
        <div>
          <label class="mb-1 block text-xs font-bold text-gray-600 dark:text-gray-300">{{ t('backoffice.beachMap.locationType') }}</label>
          <select v-model="bulkReduceForm.location_type" class="w-full px-3 py-2 border border-stone-200 dark:border-border rounded-lg text-sm">
            <option v-for="lt in existingTypes" :key="lt" :value="lt">{{ typeLabel(lt) }}</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs font-bold text-gray-600 dark:text-gray-300">{{ t('backoffice.beachMap.count') }}</label>
          <input v-model.number="bulkReduceForm.count" type="number" min="1" class="w-full px-3 py-2 border border-stone-200 dark:border-border rounded-lg text-sm" />
        </div>
        <p class="text-xs text-amber-600 dark:text-amber-300">⚠️ {{ t('backoffice.beachMap.reduceHint') }}</p>
      </div>
      <template #footer>
        <div class="flex gap-2">
          <button @click="bulkReduceModalOpen = false" class="flex-1 rounded-xl border-2 border-stone-200 py-2.5 font-semibold text-gray-600 hover:bg-gray-50 dark:bg-surface-2 dark:border-border dark:text-gray-300 dark:hover:bg-gray-800">{{ t('backoffice.beachMap.cancel') }}</button>
          <button
            @click="submitBulkReduce" :disabled="bulkReduceSubmitting"
            class="flex-1 py-2.5 rounded-xl bg-red-600 text-white font-bold hover:bg-red-700 disabled:opacity-50"
          >{{ bulkReduceSubmitting ? t('backoffice.beachMap.processing') : t('backoffice.beachMap.remove') }}</button>
        </div>
      </template>
    </AppModal>
  </div>
</template>
