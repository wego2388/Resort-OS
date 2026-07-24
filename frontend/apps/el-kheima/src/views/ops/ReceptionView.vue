<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS, useAuthStore, parseApiTimestamp } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import {
  AppCard, AppBadge, AppButton, AppModal, AppInput, AppSelect, AppSpinner,
  EmptyState, StatCard, StatusBadge, SearchInput, useToast, useConfirm,
  type SelectOption,
} from '@resort-os/ui'

const toast  = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatNumber, formatDate: fmtDateFn, formatTime: fmtTimeFn } = useStaffFormat()
const auth   = useAuthStore()
const branchId = auth.branchId

// ─────────────────────────────────────────────────────────────────────────────
// Interfaces
// ─────────────────────────────────────────────────────────────────────────────
interface Room {
  id: number
  name: string
  floor: number
  status: 'available' | 'occupied' | 'reserved' | 'checkout_pending' | 'maintenance'
  room_type_id: number
}
interface RoomTypeOption { id: number; name: string }
interface CurrentBookingInfo { booking_id: number; guest_name: string; check_out: string }

interface Booking {
  id: number
  guest_name: string
  guest_phone?: string
  guest_id_number?: string
  rooms?: { room_id: number }[]
  check_in: string
  check_out: string
  status: 'pending' | 'confirmed' | 'checked_in' | 'checked_out' | 'cancelled'
  total_rate?: number
  notes?: string
}

interface RatePlanOption {
  id: number
  name: string
  room_type_id: number | null
  base_rate_override: string | null
}

interface HKTask {
  id: number
  room_id: number
  status: 'pending' | 'in_progress' | 'done' | 'skipped'
  priority: 'normal' | 'high' | 'urgent'
  assigned_to_name?: string
}

// ─────────────────────────────────────────────────────────────────────────────
// Live clock
// ─────────────────────────────────────────────────────────────────────────────
const now = ref(new Date())
let clockInterval: ReturnType<typeof setInterval>
const currentTime = computed(() =>
  fmtTimeFn(now.value, { hour: '2-digit', minute: '2-digit', second: '2-digit' }))
const todayLabel = computed(() =>
  fmtDateFn(now.value, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }))

// ─────────────────────────────────────────────────────────────────────────────
// Data
// ─────────────────────────────────────────────────────────────────────────────
const rooms          = ref<Room[]>([])
const roomTypesById  = ref<Record<number, RoomTypeOption>>({})
const bookingByRoomId = ref<Record<number, CurrentBookingInfo>>({})
const todayBookings  = ref<Booking[]>([])
const hkTasks        = ref<HKTask[]>([])
const allRooms       = ref<{ id: number; name: string }[]>([])
const ratePlans      = ref<RatePlanOption[]>([])
const loading        = ref(false)
const searchQuery    = ref('')
// ── Room map filters ─────────────────────────────────────────────────────────
const roomSearchQuery  = ref('')
const roomStatusFilter = ref<string | null>(null)

// ─────────────────────────────────────────────────────────────────────────────
// Computed stats
// ─────────────────────────────────────────────────────────────────────────────
const checkedInToday  = computed(() => todayBookings.value.filter(b => b.status === 'checked_in').length)

const filteredRooms = computed(() => {
  let list = rooms.value
  if (roomStatusFilter.value) list = list.filter(r => r.status === roomStatusFilter.value)
  const q = roomSearchQuery.value.trim().toLowerCase()
  if (q) list = list.filter(r =>
    r.name.toLowerCase().includes(q) ||
    (roomTypesById.value[r.room_type_id]?.name ?? '').toLowerCase().includes(q) ||
    (bookingByRoomId.value[r.id]?.guest_name ?? '').toLowerCase().includes(q)
  )
  return list
})
const checkedOutToday = computed(() => todayBookings.value.filter(b => b.status === 'checked_out').length)
const arrivalsToday   = computed(() =>
  todayBookings.value.filter(b => ['pending', 'confirmed'].includes(b.status)).length)

const availableRooms  = computed(() => rooms.value.filter(r => r.status === 'available').length)
const occupiedRooms   = computed(() => rooms.value.filter(r => r.status === 'occupied').length)
const reservedRooms   = computed(() => rooms.value.filter(r => r.status === 'reserved').length)
const cleaningRooms   = computed(() => rooms.value.filter(r => r.status === 'checkout_pending').length)

const pendingHK       = computed(() => hkTasks.value.filter(t => t.status === 'pending').length)
const urgentHK        = computed(() => hkTasks.value.filter(t => t.priority === 'urgent' && t.status !== 'done').length)

// ─────────────────────────────────────────────────────────────────────────────
// Arrivals list (filtered by search)
// ─────────────────────────────────────────────────────────────────────────────
const arrivals = computed(() => {
  const list = todayBookings.value.filter(b => ['pending', 'confirmed'].includes(b.status))
  if (!searchQuery.value.trim()) return list
  const q = searchQuery.value.toLowerCase()
  return list.filter(b =>
    b.guest_name.toLowerCase().includes(q) ||
    String(b.id).includes(q) ||
    (b.guest_phone ?? '').includes(q))
})

// ─────────────────────────────────────────────────────────────────────────────
// Room name helper
// ─────────────────────────────────────────────────────────────────────────────
function roomName(booking: Booking): string {
  if (!booking.rooms?.length) return '—'
  return booking.rooms.map(r => {
    const rm = allRooms.value.find(x => x.id === r.room_id)
    return rm?.name ?? `#${r.room_id}`
  }).join(t('backoffice.reception.listSeparator'))
}
function roomTypeName(room: Room): string {
  return roomTypesById.value[room.room_type_id]?.name ?? '—'
}

// ─────────────────────────────────────────────────────────────────────────────
// Fetch functions
// ─────────────────────────────────────────────────────────────────────────────
async function fetchAll() {
  loading.value = true
  try {
    await Promise.all([fetchRooms(), fetchTodayBookings(), fetchHKTasks()])
  } finally {
    loading.value = false
  }
}

async function fetchRooms() {
  try {
    const [rRes, rtRes] = await Promise.all([
      api.get(ENDPOINTS.pms.rooms, { params: { branch_id: branchId } }),
      api.get(ENDPOINTS.pms_extra.roomTypes,   { params: { branch_id: branchId } }),
    ])
    rooms.value = rRes.data ?? []
    allRooms.value = rooms.value
    const rtMap: Record<number, RoomTypeOption> = {}
    for (const rt of (rtRes.data ?? [])) rtMap[rt.id] = rt
    roomTypesById.value = rtMap

    // جلب الحجوزات الحالية (checked_in) لمعرفة من في أي غرفة
    const biRes = await api.get(ENDPOINTS.pms.bookings, {
      params: { branch_id: branchId, status: 'checked_in', limit: 200 },
    })
    const biMap: Record<number, CurrentBookingInfo> = {}
    for (const b of (biRes.data?.items ?? biRes.data ?? [])) {
      for (const r of (b.rooms ?? [])) {
        biMap[r.room_id] = {
          booking_id: b.id,
          guest_name: b.guest_name,
          check_out:  b.check_out,
        }
      }
    }
    bookingByRoomId.value = biMap
  } catch { /* silent */ }
}

async function fetchTodayBookings() {
  try {
    const today = new Date().toISOString().slice(0, 10)
    const res = await api.get(ENDPOINTS.pms.bookings, {
      params: { branch_id: branchId, check_in_date: today, limit: 100 },
    })
    todayBookings.value = res.data?.items ?? res.data ?? []
  } catch { /* silent */ }
}

async function fetchHKTasks() {
  try {
    const res = await api.get(ENDPOINTS.pms.housekeeping, {
      params: { branch_id: branchId, limit: 200 },
    })
    hkTasks.value = res.data?.items ?? res.data ?? []
  } catch { /* silent */ }
}

async function fetchRatePlans() {
  if (ratePlans.value.length) return
  try {
    const res = await api.get(ENDPOINTS.pms_extra.ratePlans, { params: { branch_id: branchId } })
    ratePlans.value = res.data ?? []
  } catch { /* silent */ }
}

// ─────────────────────────────────────────────────────────────────────────────
// Check-in modal
// ─────────────────────────────────────────────────────────────────────────────
const ciOpen      = ref(false)
const ciBooking   = ref<Booking | null>(null)
const ciIdNumber  = ref('')
const ciPayMethod = ref<'cash' | 'card' | 'bank_transfer'>('cash')
const ciLoading   = ref(false)

const payOptions = computed<SelectOption[]>(() => [
  { value: 'cash',          label: t('backoffice.reception.payCash') },
  { value: 'card',          label: t('backoffice.reception.payCard') },
  { value: 'bank_transfer', label: t('backoffice.reception.payBankTransfer') },
])

function openCheckIn(booking: Booking) {
  ciBooking.value  = booking
  ciIdNumber.value = booking.guest_id_number ?? ''
  ciPayMethod.value = 'cash'
  ciOpen.value     = true
}

async function confirmCheckIn() {
  if (!ciBooking.value) return
  ciLoading.value = true
  try {
    await api.post(ENDPOINTS.pms.bookingCheckin(ciBooking.value.id))
    toast.success(t('backoffice.reception.checkedInToast', { name: ciBooking.value.guest_name }))
    ciOpen.value = false
    await fetchAll()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.reception.checkInError'))
  } finally {
    ciLoading.value = false
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Check-out modal
// ─────────────────────────────────────────────────────────────────────────────
const coOpen    = ref(false)
const coBooking = ref<Booking | null>(null)
const coLoading = ref(false)
// folio summary لعرضه في الـ check-out modal قبل التأكيد
interface FolioCharge { id: number; charge_type: string; description: string; amount: string }
interface FolioSummary { id: number; total: string; charges: FolioCharge[] }
const coFolio   = ref<FolioSummary | null>(null)
const coFolioLoading = ref(false)

function openCheckOut(booking: Booking) {
  coBooking.value = booking
  coFolio.value   = null
  coOpen.value    = true
  // جلب الفوليو لو موجود لعرض الإجمالي قبل تأكيد الخروج
  if ((booking as any).folio_id) {
    coFolioLoading.value = true
    api.get(`/api/v1/finance/folios/${(booking as any).folio_id}`)
      .then(r => { coFolio.value = r.data })
      .catch(() => {})
      .finally(() => { coFolioLoading.value = false })
  }
}

function openCheckOutFromRoom(roomId: number) {
  const info = bookingByRoomId.value[roomId]
  if (!info) return
  // ابحث في todayBookings أو اعمل booking مبسوط من المعلومات المتاحة
  const found = todayBookings.value.find(b => b.id === info.booking_id)
  if (found) {
    openCheckOut(found)
  } else {
    // أنشئ كائن مبسوط مؤقت للعرض
    coBooking.value = {
      id: info.booking_id,
      guest_name: info.guest_name,
      check_in: '',
      check_out: info.check_out,
      status: 'checked_in',
    }
    coOpen.value = true
  }
}

async function confirmCheckOut() {
  if (!coBooking.value) return
  coLoading.value = true
  try {
    const res = await api.post(ENDPOINTS.pms.bookingCheckout(coBooking.value.id))
    toast.success(t('backoffice.reception.checkedOutToast', { name: coBooking.value.guest_name }))
    if (res.data?.folio_total != null) {
      toast.success(t('backoffice.reception.folioTotalToast', { amount: formatNumber(res.data.folio_total) }))
    }
    coOpen.value = false
    await fetchAll()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.reception.checkOutError'))
  } finally {
    coLoading.value = false
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// New Booking modal
// ─────────────────────────────────────────────────────────────────────────────
const nbOpen    = ref(false)
const nbLoading = ref(false)
const nbForm    = ref({
  guest_name: '', guest_phone: '', check_in: '', check_out: '',
  room_ids: [] as number[], rate_plan_id: undefined as number | undefined, notes: '',
})

const availableRoomOptions = computed<SelectOption[]>(() =>
  rooms.value
    .filter(r => r.status === 'available')
    .map(r => ({ value: r.id, label: `${r.name} — ${roomTypeName(r)}` })))

const applicableRatePlans = computed<SelectOption[]>(() =>
  ratePlans.value.map(p => ({ value: p.id, label: p.name })))

function openNewBooking() {
  const today = new Date().toISOString().slice(0, 10)
  const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10)
  nbForm.value = {
    guest_name: '', guest_phone: '', check_in: today, check_out: tomorrow,
    room_ids: [], rate_plan_id: undefined, notes: '',
  }
  fetchRatePlans()
  nbOpen.value = true
}

async function saveNewBooking() {
  if (!nbForm.value.guest_name.trim()) { toast.error(t('backoffice.reception.guestNameRequired')); return }
  if (!nbForm.value.room_ids.length)   { toast.error(t('backoffice.reception.selectRoomRequired')); return }
  if (!nbForm.value.check_in)          { toast.error(t('backoffice.reception.checkInDateRequired')); return }
  if (!nbForm.value.check_out)         { toast.error(t('backoffice.reception.checkOutDateRequired')); return }
  nbLoading.value = true
  try {
    await api.post(ENDPOINTS.pms.bookings, {
      branch_id:    branchId,
      guest_name:   nbForm.value.guest_name,
      guest_phone:  nbForm.value.guest_phone || undefined,
      check_in:     nbForm.value.check_in,
      check_out:    nbForm.value.check_out,
      room_ids:     nbForm.value.room_ids,
      rate_plan_id: nbForm.value.rate_plan_id || undefined,
      notes:        nbForm.value.notes || undefined,
    })
    toast.success(t('backoffice.reception.bookingCreated'))
    nbOpen.value = false
    await fetchAll()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.reception.bookingSaveError'))
  } finally {
    nbLoading.value = false
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Night Audit (manager+ فقط)
// ─────────────────────────────────────────────────────────────────────────────
const naOpen    = ref(false)
const naDate    = ref(new Date(Date.now() - 86400000).toISOString().slice(0, 10))
const naLoading = ref(false)
const naResult  = ref<{ rooms_updated: number; revenue: number } | null>(null)
const naError   = ref('')

async function runNightAudit() {
  naLoading.value = true
  naError.value   = ''
  naResult.value  = null
  try {
    const res = await api.post(ENDPOINTS.pms.nightAudit, null, {
      params: { branch_id: branchId, date: naDate.value },
    })
    naResult.value = res.data
    toast.success(t('backoffice.reception.nightAuditSuccess'))
  } catch (e: any) {
    naError.value = e?.response?.data?.detail ?? t('backoffice.reception.nightAuditError')
  } finally {
    naLoading.value = false
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Room status colors
// ─────────────────────────────────────────────────────────────────────────────
const roomStatusConfig = computed<Record<string, { label: string; bg: string; text: string; dot: string }>>(() => ({
  available:        { label: t('backoffice.reception.roomStatus.available'), bg: 'bg-green-50 dark:bg-green-950/40', text: 'text-green-700 dark:text-green-300', dot: 'bg-green-500' },
  occupied:         { label: t('backoffice.reception.roomStatus.occupied'), bg: 'bg-blue-50 dark:bg-blue-950/40', text: 'text-blue-700 dark:text-blue-300', dot: 'bg-blue-500' },
  reserved:         { label: t('backoffice.reception.roomStatus.reserved'), bg: 'bg-amber-50 dark:bg-amber-950/40', text: 'text-amber-700 dark:text-amber-300', dot: 'bg-amber-500' },
  checkout_pending: { label: t('backoffice.reception.roomStatus.checkoutPending'), bg: 'bg-slate-50 dark:bg-slate-800/60', text: 'text-slate-600 dark:text-slate-300', dot: 'bg-slate-400' },
  maintenance:      { label: t('backoffice.reception.roomStatus.maintenance'), bg: 'bg-red-50 dark:bg-red-950/40', text: 'text-red-700 dark:text-red-300', dot: 'bg-red-500' },
}))

// ─────────────────────────────────────────────────────────────────────────────
// Lifecycle
// ─────────────────────────────────────────────────────────────────────────────
let refreshInterval: ReturnType<typeof setInterval>

onMounted(() => {
  fetchAll()
  refreshInterval = setInterval(fetchAll, 60_000)
  clockInterval   = setInterval(() => { now.value = new Date() }, 1000)
})
onUnmounted(() => {
  clearInterval(refreshInterval)
  clearInterval(clockInterval)
})
</script>

<template>
  <div class="space-y-6 p-6">

    <!-- ══ HEADER ══ -->
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100">🛎️ {{ t('backoffice.reception.title') }}</h1>
        <p class="text-sm text-muted mt-0.5">{{ todayLabel }} — {{ currentTime }}</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <AppButton variant="secondary" size="sm" @click="fetchAll" :loading="loading">
          {{ t('backoffice.reception.refresh') }}
        </AppButton>
        <AppButton size="sm" @click="openNewBooking">
          {{ t('backoffice.reception.newBooking') }}
        </AppButton>
        <AppButton
          v-if="auth.hasRole('admin')"
          variant="outline"
          size="sm"
          @click="naOpen = true"
        >
          ⚡ {{ t('backoffice.reception.nightAudit') }}
        </AppButton>
      </div>
    </div>

    <!-- ══ KPI STATS ══ -->
    <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
      <StatCard :label="t('backoffice.reception.checkedInToday')"  :value="checkedInToday"  icon="login"   variant="success" />
      <StatCard :label="t('backoffice.reception.checkedOutToday')" :value="checkedOutToday" icon="logout"  variant="info" />
      <StatCard :label="t('backoffice.reception.upcomingArrivals')" :value="arrivalsToday"   icon="calendar" variant="warning" />
      <StatCard :label="t('backoffice.reception.availableRoomsKpi')" :value="availableRooms"  icon="building" variant="success" />
      <StatCard :label="t('backoffice.reception.occupiedRoomsKpi')" :value="occupiedRooms"   icon="users"   variant="info" />
      <StatCard :label="t('backoffice.reception.pendingCleaning')" :value="pendingHK"       icon="refresh"
        :variant="urgentHK > 0 ? 'danger' : 'neutral'" />
    </div>

    <!-- ══ MAIN GRID ══ -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">

      <!-- ── العمود الأيمن: الوصولات + بحث ── -->
      <div class="lg:col-span-1 space-y-4">
        <AppCard>
          <template v-slot:default>
            <div class="flex items-center justify-between mb-4">
              <h2 class="text-base font-semibold text-gray-800 dark:text-gray-200">📋 {{ t('backoffice.reception.todaysArrivals') }}</h2>
              <AppBadge :label="String(arrivals.length)" variant="warning" />
            </div>

            <SearchInput
              v-model="searchQuery"
              :placeholder="t('backoffice.reception.searchPlaceholder')"
              class="mb-3"
            />

            <div v-if="loading" class="flex justify-center py-8">
              <AppSpinner />
            </div>

            <EmptyState
              v-else-if="!arrivals.length"
              :title="t('backoffice.reception.noArrivalsToday')"
              :subtitle="t('backoffice.reception.noArrivalsTodayHint')"
            />

            <div v-else class="space-y-2 max-h-[420px] overflow-y-auto">
              <div
                v-for="b in arrivals"
                :key="b.id"
                class="rounded-xl border border-border bg-background p-3 flex flex-col gap-2 hover:border-primary-300 transition-colors"
              >
                <div class="flex items-start justify-between gap-2">
                  <div class="min-w-0">
                    <p class="font-semibold text-gray-900 dark:text-gray-100 truncate">{{ b.guest_name }}</p>
                    <p class="text-xs text-muted">#{{ b.id }} — {{ roomName(b) }}</p>
                  </div>
                  <StatusBadge
                    :status="b.status"
                    :map="{
                      pending:    { label: t('backoffice.reception.bookingStatus.pending'),  variant: 'warning' },
                      confirmed:  { label: t('backoffice.reception.bookingStatus.confirmed'),  variant: 'info' },
                    }"
                    size="sm"
                  />
                </div>
                <div class="flex items-center justify-between text-xs text-muted">
                  <span>{{ b.check_in }} → {{ b.check_out }}</span>
                </div>
                <AppButton size="sm" class="w-full" @click="openCheckIn(b)">
                  {{ t('backoffice.reception.checkInAction') }}
                </AppButton>
              </div>
            </div>
                  </template>
        </AppCard>
      </div>

      <!-- ── العمود الأوسط+اليسار: خريطة الغرف ── -->
      <div class="lg:col-span-2 space-y-4">
        <AppCard>
          <template v-slot:default>
            <div class="flex flex-wrap items-center justify-between gap-3 mb-3">
              <h2 class="text-base font-semibold text-gray-800 dark:text-gray-200">🏨 {{ t('backoffice.reception.roomStatusTitle') }}</h2>
              <!-- legend -->
              <div class="flex flex-wrap gap-3">
                <span v-for="(cfg, key) in roomStatusConfig" :key="key"
                  class="flex items-center gap-1.5 text-xs text-muted">
                  <span :class="['w-2.5 h-2.5 rounded-full flex-shrink-0', cfg.dot]" />
                  {{ cfg.label }}
                </span>
              </div>
            </div>
            <!-- فلتر + بحث خريطة الغرف -->
            <div class="flex flex-wrap gap-2 mb-3">
              <input
                v-model="roomSearchQuery"
                type="search"
                :placeholder="t('backoffice.reception.roomSearchPlaceholder')"
                class="flex-1 min-w-[140px] px-3 py-1.5 rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
              <button
                @click="roomStatusFilter = null"
                :class="['px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors', !roomStatusFilter ? 'bg-primary-700 text-white' : 'bg-stone-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-stone-200']"
              >{{ t('common.allStatuses') }}</button>
              <button
                v-for="(cfg, key) in roomStatusConfig" :key="key"
                @click="roomStatusFilter = roomStatusFilter === key ? null : key"
                :class="['px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors flex items-center gap-1',
                  roomStatusFilter === key ? 'bg-primary-700 text-white' : 'bg-stone-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-stone-200']"
              >
                <span :class="['w-2 h-2 rounded-full', cfg.dot]" />{{ cfg.label }}
              </button>
            </div>

            <div v-if="loading" class="flex justify-center py-12"><AppSpinner /></div>

            <EmptyState v-else-if="!rooms.length" :title="t('backoffice.reception.noRooms')" />
            <p v-else-if="filteredRooms.length === 0" class="text-sm text-center text-muted py-6">{{ t('backoffice.reception.noRoomsFiltered') }}</p>

            <div v-else class="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-2">
              <div
                v-for="room in filteredRooms"
                :key="room.id"
                :class="[
                  'rounded-xl border p-2.5 flex flex-col gap-1 cursor-pointer transition-all hover:shadow-sm select-none',
                  roomStatusConfig[room.status]?.bg ?? 'bg-surface',
                  'border-border',
                ]"
                :title="roomStatusConfig[room.status]?.label ?? room.status"
              >
                <div class="flex items-center justify-between">
                  <span class="font-bold text-gray-900 dark:text-gray-100 text-sm">{{ room.name }}</span>
                  <span :class="['w-2 h-2 rounded-full flex-shrink-0', roomStatusConfig[room.status]?.dot ?? 'bg-gray-300']" />
                </div>
                <span class="text-xs text-muted truncate">{{ roomTypeName(room) }}</span>

                <!-- ضيف الغرفة إن كانت مشغولة -->
                <template v-if="room.status === 'occupied' && bookingByRoomId[room.id]">
                  <span class="text-xs text-gray-700 dark:text-gray-300 truncate font-medium">
                    {{ bookingByRoomId[room.id].guest_name }}
                  </span>
                  <span class="text-xs text-muted">
                    {{ t('backoffice.reception.checkOutLabel', { date: bookingByRoomId[room.id].check_out }) }}
                  </span>
                  <AppButton
                    size="sm"
                    variant="danger"
                    class="mt-1 text-xs py-0.5"
                    @click.stop="openCheckOutFromRoom(room.id)"
                  >
                    {{ t('backoffice.reception.checkOutAction') }}
                  </AppButton>
                </template>
              </div>
            </div>
          </template>
        </AppCard>

        <!-- ── Housekeeping summary ── -->
        <AppCard v-if="hkTasks.length">
          <template v-slot:default>
            <div class="flex items-center justify-between mb-3">
              <h2 class="text-base font-semibold text-gray-800 dark:text-gray-200">🧹 {{ t('backoffice.reception.pendingCleaningTitle') }}</h2>
              <AppBadge
                :label="String(pendingHK)"
                :variant="urgentHK > 0 ? 'danger' : 'warning'"
              />
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-48 overflow-y-auto">
              <div
                v-for="task in hkTasks.filter(hk => hk.status !== 'done')"
                :key="task.id"
                :class="[
                  'flex items-center gap-2 rounded-lg px-3 py-2 text-sm',
                  task.priority === 'urgent'   ? 'border border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/40' :
                  task.priority === 'high'     ? 'border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40' :
                                                 'bg-background border border-border',
                ]"
              >
                <span :class="[
                  'w-2 h-2 rounded-full flex-shrink-0',
                  task.priority === 'urgent' ? 'bg-red-500' :
                  task.priority === 'high'   ? 'bg-amber-500' : 'bg-slate-400',
                ]" />
                <span class="font-medium text-gray-800 dark:text-gray-200">
                  {{ rooms.find(r => r.id === task.room_id)?.name ?? t('backoffice.reception.roomHash', { id: task.room_id }) }}
                </span>
                <span v-if="task.assigned_to_name" class="text-xs text-muted ms-auto">
                  {{ task.assigned_to_name }}
                </span>
              </div>
            </div>
          </template>
        </AppCard>
      </div>
    </div>

    <!-- ════════════════════════════════════════════════
         Modal: تسجيل دخول
    ═════════════════════════════════════════════════ -->
    <AppModal
      :open="ciOpen"
      :title="t('backoffice.reception.checkInModalTitle')"
      size="sm"
      @close="ciOpen = false"
    >
      <template v-slot:default>
        <div v-if="ciBooking" class="space-y-4">
          <div class="bg-primary-50 border border-primary-200 rounded-xl p-4 space-y-1">
            <p class="font-bold text-primary-900 text-lg">{{ ciBooking.guest_name }}</p>
            <p class="text-sm text-primary-700">
              {{ t('backoffice.reception.bookingHash', { id: ciBooking.id }) }} — {{ roomName(ciBooking) }}
            </p>
            <p class="text-sm text-primary-700">
              {{ ciBooking.check_in }} → {{ ciBooking.check_out }}
            </p>
            <p v-if="ciBooking.total_rate" class="text-sm font-semibold text-primary-800">
              {{ t('backoffice.reception.totalValue', { amount: formatNumber(ciBooking.total_rate) }) }}
            </p>
          </div>

          <AppInput
            v-model="ciIdNumber"
            :label="t('backoffice.reception.idNumberLabel')"
            :placeholder="t('backoffice.reception.optional')"
          />

          <AppSelect
            v-model="ciPayMethod"
            :label="t('backoffice.reception.expectedPaymentMethod')"
            :options="payOptions"
          />
        </div>
      </template>
      <template v-slot:footer>
        <AppButton variant="ghost" @click="ciOpen = false">{{ t('backoffice.reception.cancel') }}</AppButton>
        <AppButton @click="confirmCheckIn" :loading="ciLoading">
          {{ t('backoffice.reception.confirmCheckIn') }}
        </AppButton>
      </template>
    </AppModal>

    <!-- ════════════════════════════════════════════════
         Modal: تسجيل خروج
    ═════════════════════════════════════════════════ -->
    <AppModal
      :open="coOpen"
      :title="t('backoffice.reception.checkOutModalTitle')"
      size="sm"
      @close="coOpen = false"
    >
      <template v-slot:default>
        <div v-if="coBooking" class="space-y-3">
          <div class="space-y-1 rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/40">
            <p class="text-lg font-bold text-amber-900 dark:text-amber-200">{{ coBooking.guest_name }}</p>
            <p class="text-sm text-amber-700 dark:text-amber-300">{{ t('backoffice.reception.bookingHash', { id: coBooking.id }) }}</p>
            <p class="text-sm text-amber-700 dark:text-amber-300">{{ t('backoffice.reception.departureDate', { date: coBooking.check_out }) }}</p>
          </div>
          <!-- Folio summary -->
          <div v-if="coFolioLoading" class="flex justify-center py-3"><AppSpinner size="sm" /></div>
          <div v-else-if="coFolio" class="rounded-xl border border-stone-200 dark:border-border p-3 space-y-2">
            <p class="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.reception.folioSummaryTitle') }}</p>
            <div v-if="coFolio.charges.length" class="space-y-1 max-h-40 overflow-y-auto">
              <div v-for="ch in coFolio.charges" :key="ch.id" class="flex justify-between text-xs">
                <span class="text-gray-600 dark:text-gray-300 truncate">{{ ch.description }}</span>
                <span class="font-semibold tabular-nums ms-2">{{ formatNumber(Number(ch.amount)) }}</span>
              </div>
            </div>
            <div class="flex justify-between items-center border-t border-stone-200 dark:border-border pt-2">
              <span class="text-sm font-bold text-gray-700 dark:text-gray-200">{{ t('backoffice.reception.folioTotal') }}</span>
              <span class="text-base font-black text-primary-700 dark:text-primary-300 tabular-nums">{{ formatNumber(Number(coFolio.total)) }}</span>
            </div>
          </div>
          <p class="text-sm text-muted">
            {{ t('backoffice.reception.checkOutHint') }}
          </p>
        </div>
      </template>
      <template v-slot:footer>
        <AppButton variant="ghost" @click="coOpen = false">{{ t('backoffice.reception.cancel') }}</AppButton>
        <AppButton variant="danger" @click="confirmCheckOut" :loading="coLoading">
          {{ t('backoffice.reception.confirmCheckOut') }}
        </AppButton>
      </template>
    </AppModal>

    <!-- ════════════════════════════════════════════════
         Modal: حجز جديد
    ═════════════════════════════════════════════════ -->
    <AppModal
      :open="nbOpen"
      :title="t('backoffice.reception.newBookingModalTitle')"
      size="md"
      @close="nbOpen = false"
    >
      <template v-slot:default>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <AppInput
            v-model="nbForm.guest_name"
            :label="t('backoffice.reception.guestNameRequiredLabel')"
            :placeholder="t('backoffice.reception.fullName')"
          />
          <AppInput
            v-model="nbForm.guest_phone"
            :label="t('backoffice.reception.phoneNumber')"
            :placeholder="t('backoffice.reception.optional')"
          />
          <AppInput
            v-model="nbForm.check_in"
            :label="t('backoffice.reception.checkInDateRequiredLabel')"
            type="date"
          />
          <AppInput
            v-model="nbForm.check_out"
            :label="t('backoffice.reception.checkOutDateRequiredLabel')"
            type="date"
          />
          <div class="sm:col-span-2">
            <label class="text-sm font-medium text-gray-700 dark:text-gray-300 block mb-1">{{ t('backoffice.reception.roomsRequiredLabel') }}</label>
            <div class="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-36 overflow-y-auto p-1">
              <label
                v-for="opt in availableRoomOptions"
                :key="opt.value"
                :class="[
                  'flex items-center gap-2 rounded-lg border px-3 py-2 cursor-pointer text-sm transition-colors',
                  nbForm.room_ids.includes(opt.value as number)
                    ? 'border-primary-500 bg-primary-50 text-primary-800 dark:bg-primary-950/40 dark:text-primary-200'
                    : 'border-border bg-background hover:border-primary-300',
                ]"
              >
                <input
                  type="checkbox"
                  class="rounded"
                  :value="opt.value"
                  v-model="nbForm.room_ids"
                />
                {{ opt.label }}
              </label>
              <p v-if="!availableRoomOptions.length" class="text-sm text-muted col-span-3 py-2 text-center">
                {{ t('backoffice.reception.noAvailableRooms') }}
              </p>
            </div>
          </div>
          <AppSelect
            v-model="nbForm.rate_plan_id"
            :label="t('backoffice.reception.ratePlan')"
            :options="([{ value: undefined, label: t('backoffice.reception.defaultRate') }, ...applicableRatePlans] as SelectOption[])"
          />
          <AppInput
            v-model="nbForm.notes"
            :label="t('backoffice.reception.notes')"
            :placeholder="t('backoffice.reception.optional')"
          />
        </div>
      </template>
      <template v-slot:footer>
        <AppButton variant="ghost" @click="nbOpen = false">{{ t('backoffice.reception.cancel') }}</AppButton>
        <AppButton @click="saveNewBooking" :loading="nbLoading">
          {{ t('backoffice.reception.saveBooking') }}
        </AppButton>
      </template>
    </AppModal>

    <!-- ════════════════════════════════════════════════
         Modal: Night Audit (manager+ فقط)
    ═════════════════════════════════════════════════ -->
    <AppModal
      :open="naOpen"
      :title="`⚡ ${t('backoffice.reception.nightAudit')}`"
      size="sm"
      @close="naOpen = false"
    >
      <template v-slot:default>
        <div class="space-y-4">
          <p class="text-sm text-muted">
            {{ t('backoffice.reception.nightAuditHint') }}
          </p>
          <AppInput
            v-model="naDate"
            :label="t('backoffice.reception.auditDate')"
            type="date"
          />
          <div v-if="naResult" class="space-y-1 rounded-xl border border-green-200 bg-green-50 p-4 text-sm dark:border-green-800 dark:bg-green-950/40">
            <p class="font-bold text-green-800 dark:text-green-300">✅ {{ t('backoffice.reception.auditSuccess') }}</p>
            <p class="text-green-700 dark:text-green-300">{{ t('backoffice.reception.roomsUpdated', { count: naResult.rooms_updated }) }}</p>
            <p class="text-green-700 dark:text-green-300">
              {{ t('backoffice.reception.calculatedRevenue', { amount: naResult.revenue != null ? formatNumber(naResult.revenue) : '—' }) }}
            </p>
          </div>
          <div v-if="naError" class="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
            {{ naError }}
          </div>
        </div>
      </template>
      <template v-slot:footer>
        <AppButton variant="ghost" @click="naOpen = false">{{ t('backoffice.reception.close') }}</AppButton>
        <AppButton
          v-if="!naResult"
          variant="danger"
          @click="runNightAudit"
          :loading="naLoading"
        >
          {{ t('backoffice.reception.runNightAudit') }}
        </AppButton>
      </template>
    </AppModal>

  </div>
</template>
