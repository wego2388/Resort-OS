<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, ENDPOINTS, useAuthStore, parseApiTimestamp } from '@resort-os/core'
import {
  AppCard, AppBadge, AppButton, AppModal, AppInput, AppSelect, AppSpinner,
  EmptyState, StatCard, StatusBadge, SearchInput, useToast, useConfirm,
  type SelectOption,
} from '@resort-os/ui'

const toast  = useToast()
const { confirm } = useConfirm()
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
  now.value.toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit', second: '2-digit' }))
const todayLabel = computed(() =>
  now.value.toLocaleDateString('ar-EG', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }))

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

// ─────────────────────────────────────────────────────────────────────────────
// Computed stats
// ─────────────────────────────────────────────────────────────────────────────
const checkedInToday  = computed(() => todayBookings.value.filter(b => b.status === 'checked_in').length)
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
  }).join('، ')
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

const payOptions: SelectOption[] = [
  { value: 'cash',          label: 'كاش' },
  { value: 'card',          label: 'بطاقة بنكية' },
  { value: 'bank_transfer', label: 'تحويل بنكي' },
]

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
    toast.success(`تم تسجيل دخول ${ciBooking.value.guest_name} ✅`)
    ciOpen.value = false
    await fetchAll()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تسجيل الدخول')
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

function openCheckOut(booking: Booking) {
  coBooking.value = booking
  coOpen.value    = true
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
    toast.success(`تم تسجيل خروج ${coBooking.value.guest_name} ✅`)
    if (res.data?.folio_total != null) {
      toast.success(`الإجمالي: ${res.data.folio_total.toLocaleString('ar-EG')} ج`)
    }
    coOpen.value = false
    await fetchAll()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تسجيل الخروج')
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
  if (!nbForm.value.guest_name.trim()) { toast.error('اسم الضيف مطلوب'); return }
  if (!nbForm.value.room_ids.length)   { toast.error('اختر غرفة واحدة على الأقل'); return }
  if (!nbForm.value.check_in)          { toast.error('تاريخ الوصول مطلوب'); return }
  if (!nbForm.value.check_out)         { toast.error('تاريخ المغادرة مطلوب'); return }
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
    toast.success('تم إنشاء الحجز بنجاح ✅')
    nbOpen.value = false
    await fetchAll()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر حفظ الحجز')
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
    toast.success('تم تشغيل Night Audit بنجاح ✅')
  } catch (e: any) {
    naError.value = e?.response?.data?.detail ?? 'تعذّر تشغيل Night Audit'
  } finally {
    naLoading.value = false
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Room status colors
// ─────────────────────────────────────────────────────────────────────────────
const roomStatusConfig: Record<string, { label: string; bg: string; text: string; dot: string }> = {
  available:        { label: 'شاغرة',      bg: 'bg-green-50',  text: 'text-green-700',  dot: 'bg-green-500' },
  occupied:         { label: 'مشغولة',     bg: 'bg-blue-50',   text: 'text-blue-700',   dot: 'bg-blue-500' },
  reserved:         { label: 'محجوزة',     bg: 'bg-amber-50',  text: 'text-amber-700',  dot: 'bg-amber-500' },
  checkout_pending: { label: 'قيد التنظيف', bg: 'bg-slate-50',  text: 'text-slate-600',  dot: 'bg-slate-400' },
  maintenance:      { label: 'صيانة',      bg: 'bg-red-50',    text: 'text-red-700',    dot: 'bg-red-500' },
}

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
  <div class="space-y-6 p-6" dir="rtl">

    <!-- ══ HEADER ══ -->
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100">🛎️ شاشة الاستقبال</h1>
        <p class="text-sm text-muted mt-0.5">{{ todayLabel }} — {{ currentTime }}</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <AppButton variant="secondary" size="sm" @click="fetchAll" :loading="loading">
          تحديث
        </AppButton>
        <AppButton size="sm" @click="openNewBooking">
          + حجز جديد
        </AppButton>
        <AppButton
          v-if="auth.hasRole('admin')"
          variant="outline"
          size="sm"
          @click="naOpen = true"
        >
          ⚡ Night Audit
        </AppButton>
      </div>
    </div>

    <!-- ══ KPI STATS ══ -->
    <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
      <StatCard label="دخل اليوم"    :value="checkedInToday"  icon="login"   variant="success" />
      <StatCard label="خرج اليوم"    :value="checkedOutToday" icon="logout"  variant="info" />
      <StatCard label="وصول قادم"    :value="arrivalsToday"   icon="calendar" variant="warning" />
      <StatCard label="غرف شاغرة"    :value="availableRooms"  icon="building" variant="success" />
      <StatCard label="غرف مشغولة"   :value="occupiedRooms"   icon="users"   variant="info" />
      <StatCard label="تنظيف معلق"   :value="pendingHK"       icon="refresh"
        :variant="urgentHK > 0 ? 'danger' : 'neutral'" />
    </div>

    <!-- ══ MAIN GRID ══ -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">

      <!-- ── العمود الأيمن: الوصولات + بحث ── -->
      <div class="lg:col-span-1 space-y-4">
        <AppCard>
          <template v-slot:default>
            <div class="flex items-center justify-between mb-4">
              <h2 class="text-base font-semibold text-gray-800 dark:text-gray-200">📋 وصول اليوم</h2>
              <AppBadge :label="String(arrivals.length)" variant="warning" />
            </div>

            <SearchInput
              v-model="searchQuery"
              placeholder="بحث بالاسم أو رقم الحجز..."
              class="mb-3"
            />

            <div v-if="loading" class="flex justify-center py-8">
              <AppSpinner />
            </div>

            <EmptyState
              v-else-if="!arrivals.length"
              title="لا توجد وصولات اليوم"
              subtitle="يمكنك إنشاء حجز جديد"
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
                      pending:    { label: 'معلق',  variant: 'warning' },
                      confirmed:  { label: 'مؤكد',  variant: 'info' },
                    }"
                    size="sm"
                  />
                </div>
                <div class="flex items-center justify-between text-xs text-muted">
                  <span>{{ b.check_in }} → {{ b.check_out }}</span>
                </div>
                <AppButton size="sm" class="w-full" @click="openCheckIn(b)">
                  تسجيل دخول ✅
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
            <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
              <h2 class="text-base font-semibold text-gray-800 dark:text-gray-200">🏨 حالة الغرف</h2>
              <!-- legend -->
              <div class="flex flex-wrap gap-3">
                <span v-for="(cfg, key) in roomStatusConfig" :key="key"
                  class="flex items-center gap-1.5 text-xs text-muted">
                  <span :class="['w-2.5 h-2.5 rounded-full flex-shrink-0', cfg.dot]" />
                  {{ cfg.label }}
                </span>
              </div>
            </div>

            <div v-if="loading" class="flex justify-center py-12"><AppSpinner /></div>

            <EmptyState v-else-if="!rooms.length" title="لا توجد غرف" />

            <div v-else class="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-2">
              <div
                v-for="room in rooms"
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
                    خروج: {{ bookingByRoomId[room.id].check_out }}
                  </span>
                  <AppButton
                    size="sm"
                    variant="danger"
                    class="mt-1 text-xs py-0.5"
                    @click.stop="openCheckOutFromRoom(room.id)"
                  >
                    تسجيل خروج
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
              <h2 class="text-base font-semibold text-gray-800 dark:text-gray-200">🧹 التنظيف المعلق</h2>
              <AppBadge
                :label="String(pendingHK)"
                :variant="urgentHK > 0 ? 'danger' : 'warning'"
              />
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-48 overflow-y-auto">
              <div
                v-for="task in hkTasks.filter(t => t.status !== 'done')"
                :key="task.id"
                :class="[
                  'flex items-center gap-2 rounded-lg px-3 py-2 text-sm',
                  task.priority === 'urgent'   ? 'bg-red-50 border border-red-200' :
                  task.priority === 'high'     ? 'bg-amber-50 border border-amber-200' :
                                                 'bg-background border border-border',
                ]"
              >
                <span :class="[
                  'w-2 h-2 rounded-full flex-shrink-0',
                  task.priority === 'urgent' ? 'bg-red-500' :
                  task.priority === 'high'   ? 'bg-amber-500' : 'bg-slate-400',
                ]" />
                <span class="font-medium text-gray-800 dark:text-gray-200">
                  {{ rooms.find(r => r.id === task.room_id)?.name ?? `غرفة #${task.room_id}` }}
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
      title="تسجيل دخول ضيف"
      size="sm"
      @close="ciOpen = false"
    >
      <template v-slot:default>
        <div v-if="ciBooking" class="space-y-4">
          <div class="bg-primary-50 border border-primary-200 rounded-xl p-4 space-y-1">
            <p class="font-bold text-primary-900 text-lg">{{ ciBooking.guest_name }}</p>
            <p class="text-sm text-primary-700">
              حجز #{{ ciBooking.id }} — {{ roomName(ciBooking) }}
            </p>
            <p class="text-sm text-primary-700">
              {{ ciBooking.check_in }} → {{ ciBooking.check_out }}
            </p>
            <p v-if="ciBooking.total_rate" class="text-sm font-semibold text-primary-800">
              القيمة الإجمالية: {{ ciBooking.total_rate.toLocaleString('ar-EG') }} ج
            </p>
          </div>

          <AppInput
            v-model="ciIdNumber"
            label="رقم الهوية / جواز السفر"
            placeholder="اختياري"
          />

          <AppSelect
            v-model="ciPayMethod"
            label="طريقة الدفع المتوقعة"
            :options="payOptions"
          />
        </div>
      </template>
      <template v-slot:footer>
        <AppButton variant="ghost" @click="ciOpen = false">إلغاء</AppButton>
        <AppButton @click="confirmCheckIn" :loading="ciLoading">
          تأكيد الدخول ✅
        </AppButton>
      </template>
    </AppModal>

    <!-- ════════════════════════════════════════════════
         Modal: تسجيل خروج
    ═════════════════════════════════════════════════ -->
    <AppModal
      :open="coOpen"
      title="تسجيل خروج ضيف"
      size="sm"
      @close="coOpen = false"
    >
      <template v-slot:default>
        <div v-if="coBooking" class="space-y-3">
          <div class="bg-amber-50 border border-amber-200 rounded-xl p-4 space-y-1">
            <p class="font-bold text-amber-900 text-lg">{{ coBooking.guest_name }}</p>
            <p class="text-sm text-amber-700">حجز #{{ coBooking.id }}</p>
            <p class="text-sm text-amber-700">موعد المغادرة: {{ coBooking.check_out }}</p>
          </div>
          <p class="text-sm text-muted">
            سيتم تسجيل الخروج وتسوية الفاتورة تلقائياً من النظام.
          </p>
        </div>
      </template>
      <template v-slot:footer>
        <AppButton variant="ghost" @click="coOpen = false">إلغاء</AppButton>
        <AppButton variant="danger" @click="confirmCheckOut" :loading="coLoading">
          تأكيد الخروج 🚪
        </AppButton>
      </template>
    </AppModal>

    <!-- ════════════════════════════════════════════════
         Modal: حجز جديد
    ═════════════════════════════════════════════════ -->
    <AppModal
      :open="nbOpen"
      title="حجز جديد"
      size="md"
      @close="nbOpen = false"
    >
      <template v-slot:default>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <AppInput
            v-model="nbForm.guest_name"
            label="اسم الضيف *"
            placeholder="الاسم الكامل"
          />
          <AppInput
            v-model="nbForm.guest_phone"
            label="رقم الهاتف"
            placeholder="اختياري"
          />
          <AppInput
            v-model="nbForm.check_in"
            label="تاريخ الوصول *"
            type="date"
          />
          <AppInput
            v-model="nbForm.check_out"
            label="تاريخ المغادرة *"
            type="date"
          />
          <div class="sm:col-span-2">
            <label class="text-sm font-medium text-gray-700 dark:text-gray-300 block mb-1">الغرف *</label>
            <div class="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-36 overflow-y-auto p-1">
              <label
                v-for="opt in availableRoomOptions"
                :key="opt.value"
                :class="[
                  'flex items-center gap-2 rounded-lg border px-3 py-2 cursor-pointer text-sm transition-colors',
                  nbForm.room_ids.includes(opt.value as number)
                    ? 'border-primary-500 bg-primary-50 text-primary-800'
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
                لا توجد غرف شاغرة
              </p>
            </div>
          </div>
          <AppSelect
            v-model="nbForm.rate_plan_id"
            label="خطة الأسعار"
            :options="([{ value: undefined, label: 'السعر الافتراضي' }, ...applicableRatePlans] as SelectOption[])"
          />
          <AppInput
            v-model="nbForm.notes"
            label="ملاحظات"
            placeholder="اختياري"
          />
        </div>
      </template>
      <template v-slot:footer>
        <AppButton variant="ghost" @click="nbOpen = false">إلغاء</AppButton>
        <AppButton @click="saveNewBooking" :loading="nbLoading">
          حفظ الحجز
        </AppButton>
      </template>
    </AppModal>

    <!-- ════════════════════════════════════════════════
         Modal: Night Audit (manager+ فقط)
    ═════════════════════════════════════════════════ -->
    <AppModal
      :open="naOpen"
      title="⚡ Night Audit"
      size="sm"
      @close="naOpen = false"
    >
      <template v-slot:default>
        <div class="space-y-4">
          <p class="text-sm text-muted">
            يُشغّل Night Audit لحساب إيرادات الغرف وتحديث حالة الحجوزات لتاريخ محدد.
            العملية لا يمكن التراجع عنها.
          </p>
          <AppInput
            v-model="naDate"
            label="تاريخ الـ Audit"
            type="date"
          />
          <div v-if="naResult" class="bg-green-50 border border-green-200 rounded-xl p-4 space-y-1 text-sm">
            <p class="font-bold text-green-800">✅ تم بنجاح</p>
            <p class="text-green-700">غرف محدّثة: {{ naResult.rooms_updated }}</p>
            <p class="text-green-700">
              الإيراد المحتسب: {{ naResult.revenue?.toLocaleString('ar-EG') ?? '—' }} ج
            </p>
          </div>
          <div v-if="naError" class="bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700">
            {{ naError }}
          </div>
        </div>
      </template>
      <template v-slot:footer>
        <AppButton variant="ghost" @click="naOpen = false">إغلاق</AppButton>
        <AppButton
          v-if="!naResult"
          variant="danger"
          @click="runNightAudit"
          :loading="naLoading"
        >
          تشغيل Night Audit
        </AppButton>
      </template>
    </AppModal>

  </div>
</template>
