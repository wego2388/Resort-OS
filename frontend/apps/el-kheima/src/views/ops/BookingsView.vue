<script setup lang="ts">
// Booking create/check-in/check-out flow — was fully broken end-to-end
// (found + fixed during a live QA pass, 2026-07-03):
//   1. createBooking() posted `room_id: number` — the real schema
//      (app/modules/pms/schemas.py::BookingCreate) requires `room_ids:
//      list[int]` (supports multi-room bookings); the mismatched field name
//      meant every single "حفظ الحجز" click 422'd with "room_ids: Field
//      required", never actually creating a booking.
//   2. checkIn()/checkOut() called `PATCH /pms/bookings/{id}` — that route
//      doesn't exist at all (real ones are `POST .../checkin` and
//      `POST .../checkout`, no body) — both buttons always 404'd, so a
//      booking could never actually be checked in or out from this screen.
//   3. The room dropdown/list used field names (`room_number`, `room_type`)
//      that don't exist on the real `RoomRead`/`BookingRoomRead` schemas
//      (real fields: `name`, `room_type_id`, and bookings only expose rooms
//      via a `rooms: BookingRoomRead[]` array keyed by `room_id`) — every
//      "room" column rendered as blank/"—" and the create dropdown was
//      permanently empty regardless of the (also fixed, see
//      app/modules/pms/crud.py::get_available_rooms) backend availability bug.
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS , useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatDate: fmtDateFn } = useStaffFormat()
const auth = useAuthStore()
const branchId = auth.branchId

interface Booking {
  id: number
  guest_name: string
  guest_phone?: string
  rooms?: { room_id: number }[]
  check_in: string
  check_out: string
  status: 'pending' | 'confirmed' | 'checked_in' | 'checked_out' | 'cancelled'
  total_rate?: number
  extra_charge?: number
  early_checkin_at?: string | null
  late_checkout_at?: string | null
  notes?: string
}

interface RoomOption {
  id: number
  name: string
  floor: number
  room_type_id: number
  status: string
}

interface RatePlanOption {
  id: number
  name: string
  room_type_id: number | null
  rate_multiplier: string
  base_rate_override: string | null
}

// ─── Data ────────────────────────────────────────────────────────────────────
const bookings  = ref<Booking[]>([])
const rooms     = ref<RoomOption[]>([])
const loading   = ref(false)
const submitting = ref(false)

// ─── Filters ─────────────────────────────────────────────────────────────────
const filterStatus = ref<string | null>(null)

const filteredBookings = computed(() =>
  filterStatus.value
    ? bookings.value.filter(b => b.status === filterStatus.value)
    : bookings.value
)

// ─── Status config ────────────────────────────────────────────────────────────
const statusConfig = computed<Record<string, { label: string; color: string; bg: string }>>(() => ({
  pending:     { label: t('backoffice.bookings.status.pending'), color: 'text-amber-700 dark:text-amber-300', bg: 'bg-amber-100 dark:bg-amber-950/50' },
  confirmed:   { label: t('backoffice.bookings.status.confirmed'), color: 'text-blue-700 dark:text-blue-300', bg: 'bg-blue-100 dark:bg-blue-950/50' },
  checked_in:  { label: t('backoffice.bookings.status.checkedIn'), color: 'text-green-700 dark:text-green-300', bg: 'bg-green-100 dark:bg-green-950/50' },
  checked_out: { label: t('backoffice.bookings.status.checkedOut'), color: 'text-gray-600 dark:text-gray-400', bg: 'bg-gray-100 dark:bg-gray-800' },
  cancelled:   { label: t('backoffice.bookings.status.cancelled'), color: 'text-red-700 dark:text-red-300', bg: 'bg-red-100 dark:bg-red-950/50' },
}))

const statusCounts = computed(() =>
  Object.fromEntries(
    Object.keys(statusConfig.value).map(s => [s, bookings.value.filter(b => b.status === s).length])
  )
)

// ─── Create modal ─────────────────────────────────────────────────────────────
const showCreateModal = ref(false)
const createError     = ref('')
const roomsLoading    = ref(false)
const ratePlans       = ref<RatePlanOption[]>([])
const form = ref({
  guest_name:   '',
  guest_phone:  '',
  room_ids:     [] as number[],
  check_in:     '',
  check_out:    '',
  notes:        '',
  rate_plan_id: null as number | null,
})

// خطط الأسعار الفعّالة اللي تنطبق فعليًا على أنواع الغرف المختارة (ممكن يبقى
// أكتر من غرفة/نوع في نفس الحجز — غرفة جناح + غرفة مجاورة مثلاً) — إما خطة
// عامة (room_type_id = null، لكل الفرع) أو خطة مخصصة لنوع من أنواع الغرف
// المختارة بالظبط. باقي الخطط (مخصصة لنوع مالوش أي غرفة مختارة) بتتخفي عشان
// الاستقبال ميختارش خطة هتتجاهل بصمت وقت الحساب (services._room_rate_for
// بتطبّقها بس على الغرف اللي نوعها مطابق، غير كده بترجع للسعر الأساسي الخام
// لباقي الغرف).
const applicableRatePlans = computed(() => {
  const selectedTypeIds = new Set(
    rooms.value.filter((r) => form.value.room_ids.includes(r.id)).map((r) => r.room_type_id)
  )
  if (selectedTypeIds.size === 0) return []
  return ratePlans.value.filter((p) => p.room_type_id === null || selectedTypeIds.has(p.room_type_id))
})

async function fetchRatePlans() {
  try {
    const res = await api.get(ENDPOINTS.pms_extra.ratePlans, {
      params: { branch_id: branchId, active_only: true },
    })
    ratePlans.value = res.data.items ?? res.data
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.bookings.loadRatePlansError'))
  }
}

function openCreateModal() {
  form.value = {
    guest_name: '', guest_phone: '', room_ids: [],
    check_in: '', check_out: '', notes: '', rate_plan_id: null,
  }
  createError.value = ''
  rooms.value = []
  showCreateModal.value = true
  fetchRatePlans()
}

// ─── API ──────────────────────────────────────────────────────────────────────
async function fetchBookings() {
  loading.value = true
  try {
    const res = await api.get(ENDPOINTS.pms.bookings, {
      params: { branch_id: branchId, page: 1, size: 100 }
    })
    bookings.value = res.data.items ?? res.data
  } catch(e) {
    toast.error(t('backoffice.bookings.loadBookingsError'))
  } finally { loading.value = false }
}

// كل الغرف (مهما كانت حالتها الحالية) — تُستخدم فقط لعرض اسم الغرفة في جدول
// الحجوزات (roomLabel أسفل)، مش لتحديد إتاحة الحجز الجديد.
const allRoomsById = ref<Record<number, RoomOption>>({})

async function fetchAllRooms() {
  try {
    const res = await api.get(ENDPOINTS.pms.rooms, { params: { branch_id: branchId } })
    const list: RoomOption[] = res.data.items ?? res.data
    allRoomsById.value = Object.fromEntries(list.map((r) => [r.id, r]))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.bookings.loadRoomsError'))
  }
}

function roomLabel(booking: Booking): string {
  const roomId = booking.rooms?.[0]?.room_id
  if (!roomId) return '—'
  const extra = (booking.rooms?.length ?? 0) > 1 ? ` (+${(booking.rooms!.length - 1)})` : ''
  return (allRoomsById.value[roomId]?.name ?? `#${roomId}`) + extra
}

// الغرف المتاحة فعليًا لفترة الحجز المطلوبة تحديدًا — لازم الاتنين تاريخ
// موجودين الأول (GET /pms/rooms/available بياخد check_in/check_out إجباري).
async function fetchAvailableRooms() {
  if (!form.value.check_in || !form.value.check_out) {
    rooms.value = []
    return
  }
  roomsLoading.value = true
  try {
    const res = await api.get(ENDPOINTS.pms.roomsAvailable, {
      params: { branch_id: branchId, check_in: form.value.check_in, check_out: form.value.check_out },
    })
    rooms.value = res.data
    // الغرف المختارة سابقًا ممكن يبقى بعضها مش متاح بعد تغيير التواريخ
    const stillAvailable = form.value.room_ids.filter((id) => rooms.value.some((r) => r.id === id))
    if (stillAvailable.length !== form.value.room_ids.length) {
      form.value.room_ids = stillAvailable
      form.value.rate_plan_id = null
    }
  } catch(e) {
    toast.error(t('backoffice.bookings.loadAvailableRoomsError'))
  } finally {
    roomsLoading.value = false
  }
}

watch(() => [form.value.check_in, form.value.check_out], fetchAvailableRooms)

// خطة الأسعار المختارة ممكن تبقى مش منطبقة بعد تغيير اختيار الغرف (نوع مختلف)
watch(() => form.value.room_ids, () => {
  if (form.value.rate_plan_id && !applicableRatePlans.value.some((p) => p.id === form.value.rate_plan_id)) {
    form.value.rate_plan_id = null
  }
}, { deep: true })

async function createBooking() {
  if (!form.value.guest_name.trim()) { createError.value = t('backoffice.bookings.guestNameRequired'); return }
  if (!form.value.check_in)           { createError.value = t('backoffice.bookings.checkInDateRequired'); return }
  if (!form.value.check_out)          { createError.value = t('backoffice.bookings.checkOutDateRequired'); return }
  if (form.value.room_ids.length === 0) { createError.value = t('backoffice.bookings.selectRoomRequired'); return }

  submitting.value = true
  createError.value = ''
  try {
    await api.post(ENDPOINTS.pms.bookings, {
      guest_name:   form.value.guest_name,
      guest_phone:  form.value.guest_phone || undefined,
      check_in:     form.value.check_in,
      check_out:    form.value.check_out,
      notes:        form.value.notes || undefined,
      room_ids:     form.value.room_ids,
      branch_id:    branchId,
      rate_plan_id: form.value.rate_plan_id || undefined,
    })
    showCreateModal.value = false
    await Promise.all([fetchBookings(), fetchAllRooms()])
  } catch(e: any) {
    createError.value = e?.response?.data?.detail
      ?? e?.response?.data?.message
      ?? t('backoffice.bookings.genericError')
  } finally {
    submitting.value = false
  }
}

async function checkOut(booking: Booking) {
  const ok = await confirm({ message: t('backoffice.bookings.confirmCheckOutMessage', { name: booking.guest_name }), danger: true })
  if (!ok) return
  try {
    const res = await api.post(ENDPOINTS.pms.bookingCheckout(booking.id))
    booking.status = res.data.status
    toast.success(t('backoffice.bookings.checkedOutToast'))
  } catch(e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.bookings.checkOutError'))
  }
}

async function checkIn(booking: Booking) {
  try {
    const res = await api.post(ENDPOINTS.pms.bookingCheckin(booking.id))
    booking.status = res.data.status
    toast.success(t('backoffice.bookings.checkedInToast'))
  } catch(e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.bookings.checkInError'))
  }
}

async function cancelBooking(booking: Booking) {
  const ok = await confirm({
    message: t('backoffice.bookings.confirmCancelMessage', { name: booking.guest_name }),
    danger: true,
    confirmText: t('backoffice.bookings.confirmCancelYes'),
    cancelText: t('backoffice.bookings.confirmCancelNo'),
  })
  if (!ok) return
  try {
    const res = await api.post(ENDPOINTS.pms.bookingCancel(booking.id))
    booking.status = res.data.status ?? 'cancelled'
    toast.success(t('backoffice.bookings.bookingCancelledToast'))
  } catch(e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.bookings.bookingCancelError'))
  }
}

// ─── Early / Late modal ───────────────────────────────────────────────────────
const showEarlyLateModal = ref(false)
const earlyLateBooking   = ref<Booking | null>(null)
const earlyCheckinAt     = ref('')
const lateCheckoutAt     = ref('')
const earlyLateCharge    = ref('0')
const earlyLateNotes     = ref('')
const earlyLateSubmitting = ref(false)

function openEarlyLate(booking: Booking) {
  earlyLateBooking.value  = booking
  earlyCheckinAt.value    = booking.early_checkin_at
    ? new Date(booking.early_checkin_at).toISOString().slice(0,16) : ''
  lateCheckoutAt.value    = booking.late_checkout_at
    ? new Date(booking.late_checkout_at).toISOString().slice(0,16) : ''
  earlyLateCharge.value   = String(booking.extra_charge ?? 0)
  earlyLateNotes.value    = ''
  showEarlyLateModal.value = true
}

async function submitEarlyLate() {
  if (!earlyLateBooking.value) return
  earlyLateSubmitting.value = true
  try {
    const payload: Record<string, unknown> = {
      charge: parseFloat(earlyLateCharge.value) || 0,
    }
    if (earlyCheckinAt.value)  payload.early_checkin_at  = new Date(earlyCheckinAt.value).toISOString()
    if (lateCheckoutAt.value)  payload.late_checkout_at  = new Date(lateCheckoutAt.value).toISOString()
    if (earlyLateNotes.value)  payload.notes             = earlyLateNotes.value
    const res = await api.post(ENDPOINTS.pms.bookingEarlyLate(earlyLateBooking.value.id), payload)
    const b = bookings.value.find(x => x.id === earlyLateBooking.value!.id)
    if (b) {
      b.early_checkin_at = res.data.early_checkin_at
      b.late_checkout_at = res.data.late_checkout_at
      b.extra_charge     = res.data.extra_charge
    }
    showEarlyLateModal.value = false
    toast.success(t('backoffice.bookings.earlyLateSaved'))
  } catch(e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.bookings.earlyLateSaveError'))
  } finally {
    earlyLateSubmitting.value = false
  }
}

function formatDate(d: string) {
  return fmtDateFn(d, { day: 'numeric', month: 'short', year: 'numeric' })
}

onMounted(() => {
  fetchBookings()
  fetchAllRooms()
})
</script>

<template>
  <div class="p-4">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.bookings.title') }}</h1>
      <div class="flex gap-2">
        <button
          @click="fetchBookings"
          class="rounded-lg bg-gray-100 px-3 py-1.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
        >🔄</button>
        <button
          @click="openCreateModal"
          class="px-4 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-bold hover:bg-blue-700 transition-colors"
        >{{ t('backoffice.bookings.newBooking') }}</button>
      </div>
    </div>

    <!-- Status filter tabs -->
    <div class="flex gap-2 mb-4 overflow-x-auto pb-1">
      <button
        @click="filterStatus = null"
        :class="[
          'flex-shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
          !filterStatus ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700'
        ]"
      >{{ t('backoffice.bookings.all') }} ({{ bookings.length }})</button>
      <button
        v-for="(cfg, status) in statusConfig"
        :key="status"
        @click="filterStatus = filterStatus === status ? null : status"
        :class="[
          'flex-shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
          filterStatus === status ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700'
        ]"
      >{{ cfg.label }} ({{ statusCounts[status] ?? 0 }})</button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex flex-col items-center justify-center py-16 text-gray-400 dark:text-gray-400 gap-3">
      <AppSpinner size="lg" />
      <p>{{ t('backoffice.bookings.loading') }}</p>
    </div>

    <!-- Desktop table -->
    <div v-else class="hidden md:block bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="border-b border-stone-200 bg-gray-50 dark:border-border dark:bg-gray-800/60">
          <tr>
            <th class="text-start px-4 py-3 font-semibold text-gray-600 dark:text-gray-400">#</th>
            <th class="text-start px-4 py-3 font-semibold text-gray-600 dark:text-gray-400">{{ t('backoffice.bookings.guest') }}</th>
            <th class="text-start px-4 py-3 font-semibold text-gray-600 dark:text-gray-400">{{ t('backoffice.bookings.room') }}</th>
            <th class="text-start px-4 py-3 font-semibold text-gray-600 dark:text-gray-400">{{ t('backoffice.bookings.arrival') }}</th>
            <th class="text-start px-4 py-3 font-semibold text-gray-600 dark:text-gray-400">{{ t('backoffice.bookings.departure') }}</th>
            <th class="text-start px-4 py-3 font-semibold text-gray-600 dark:text-gray-400">{{ t('backoffice.bookings.statusCol') }}</th>
            <th class="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="b in filteredBookings"
            :key="b.id"
            class="border-b border-stone-100 transition-colors hover:bg-gray-50 dark:bg-surface-2 dark:border-border/50 dark:hover:bg-gray-800/60"
          >
            <td class="px-4 py-3 text-gray-400 dark:text-gray-400 font-mono text-xs">{{ b.id }}</td>
            <td class="px-4 py-3">
              <div class="font-semibold text-gray-900 dark:text-gray-100">{{ b.guest_name }}</div>
              <div v-if="b.guest_phone" class="text-xs text-gray-400 dark:text-gray-400 dir-ltr">{{ b.guest_phone }}</div>
            </td>
            <td class="px-4 py-3 font-medium text-gray-700 dark:text-gray-300">{{ roomLabel(b) }}</td>
            <td class="px-4 py-3 text-gray-600 dark:text-gray-400">{{ formatDate(b.check_in) }}</td>
            <td class="px-4 py-3 text-gray-600 dark:text-gray-400">{{ formatDate(b.check_out) }}</td>
            <td class="px-4 py-3">
              <span :class="['px-2 py-0.5 rounded-full text-xs font-bold', statusConfig[b.status]?.bg, statusConfig[b.status]?.color]">
                {{ statusConfig[b.status]?.label ?? b.status }}
              </span>
            </td>
            <td class="px-4 py-3">
              <button
                v-if="b.status === 'confirmed'"
                @click="checkIn(b)"
                class="px-3 py-1 bg-green-600 text-white text-xs font-bold rounded-lg hover:bg-green-700 transition-colors"
              >{{ t('backoffice.bookings.checkIn') }}</button>
              <button
                v-else-if="b.status === 'checked_in'"
                @click="checkOut(b)"
                class="px-3 py-1 bg-amber-600 text-white text-xs font-bold rounded-lg hover:bg-amber-700 transition-colors"
              >{{ t('backoffice.bookings.checkOut') }}</button>
              <button
                v-if="b.status === 'confirmed' || b.status === 'checked_in'"
                @click="openEarlyLate(b)"
                class="ms-1 rounded-lg bg-purple-100 px-2 py-1 text-xs font-bold text-purple-700 transition-colors hover:bg-purple-200 dark:bg-purple-950/50 dark:text-purple-300 dark:hover:bg-purple-900/60"
                :title="t('backoffice.bookings.earlyLateTitle')"
              >🕐</button>
              <button
                v-if="b.status === 'pending' || b.status === 'confirmed'"
                @click="cancelBooking(b)"
                class="ms-1 rounded-lg bg-red-100 px-2 py-1 text-xs font-bold text-red-700 transition-colors hover:bg-red-200 dark:bg-red-950/50 dark:text-red-300 dark:hover:bg-red-900/60"
                :title="t('backoffice.bookings.cancelTitle')"
              >{{ t('backoffice.bookings.cancel') }}</button>
            </td>
          </tr>
          <tr v-if="filteredBookings.length === 0">
            <td colspan="7" class="px-4 py-16 text-center text-gray-400 dark:text-gray-400">
              {{ t('backoffice.bookings.noBookings') }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Mobile cards -->
    <div class="md:hidden space-y-3">
      <div
        v-for="b in filteredBookings"
        :key="b.id"
        class="bg-white dark:bg-surface rounded-xl border border-stone-200 dark:border-border p-4 shadow-sm"
      >
        <div class="flex items-start justify-between mb-2">
          <div>
            <div class="font-bold text-gray-900 dark:text-gray-100">{{ b.guest_name }}</div>
            <div v-if="b.guest_phone" class="text-xs text-gray-400 dark:text-gray-400">{{ b.guest_phone }}</div>
          </div>
          <span :class="['px-2 py-0.5 rounded-full text-xs font-bold', statusConfig[b.status]?.bg, statusConfig[b.status]?.color]">
            {{ statusConfig[b.status]?.label ?? b.status }}
          </span>
        </div>
        <div class="grid grid-cols-3 gap-2 text-xs text-gray-600 dark:text-gray-400 mb-3">
          <div><span class="text-gray-400 dark:text-gray-400">{{ t('backoffice.bookings.roomShort') }}</span><strong>{{ roomLabel(b) }}</strong></div>
          <div><span class="text-gray-400 dark:text-gray-400">{{ t('backoffice.bookings.arrivalShort') }}</span>{{ formatDate(b.check_in) }}</div>
          <div><span class="text-gray-400 dark:text-gray-400">{{ t('backoffice.bookings.departureShort') }}</span>{{ formatDate(b.check_out) }}</div>
        </div>
        <div class="flex gap-2">
          <button
            v-if="b.status === 'confirmed'"
            @click="checkIn(b)"
            class="flex-1 py-1.5 bg-green-600 text-white text-xs font-bold rounded-lg hover:bg-green-700 transition-colors"
          >{{ t('backoffice.bookings.checkIn') }}</button>
          <button
            v-else-if="b.status === 'checked_in'"
            @click="checkOut(b)"
            class="flex-1 py-1.5 bg-amber-600 text-white text-xs font-bold rounded-lg hover:bg-amber-700 transition-colors"
          >{{ t('backoffice.bookings.checkOut') }}</button>
          <button
            v-if="b.status === 'confirmed' || b.status === 'checked_in'"
            @click="openEarlyLate(b)"
            class="rounded-lg bg-purple-100 px-3 py-1.5 text-xs font-bold text-purple-700 dark:bg-purple-950/50 dark:text-purple-300"
          >🕐 {{ t('backoffice.bookings.earlyLateShort') }}</button>
          <button
            v-if="b.status === 'pending' || b.status === 'confirmed'"
            @click="cancelBooking(b)"
            class="rounded-lg bg-red-100 px-3 py-1.5 text-xs font-bold text-red-700 transition-colors hover:bg-red-200 dark:bg-red-950/50 dark:text-red-300 dark:hover:bg-red-900/60"
          >{{ t('backoffice.bookings.cancel') }}</button>
        </div>
      </div>

      <EmptyState v-if="filteredBookings.length === 0" icon="📋" :title="t('backoffice.bookings.noBookings')" />
    </div>

    <!-- Early / Late modal -->
    <Teleport to="body">
      <div
        v-if="showEarlyLateModal"
        class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
        @click.self="showEarlyLateModal = false"
      >
        <div class="bg-white dark:bg-surface rounded-2xl shadow-2xl w-full max-w-sm p-6 space-y-4">
          <h3 class="text-lg font-bold text-gray-900 dark:text-gray-100">🕐 {{ t('backoffice.bookings.earlyLateModalTitle') }}</h3>
          <p class="text-sm text-gray-500 dark:text-gray-400">{{ earlyLateBooking?.guest_name }}</p>
          <div class="space-y-3">
            <div>
              <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{{ t('backoffice.bookings.earlyCheckinTime') }}</label>
              <input type="datetime-local" v-model="earlyCheckinAt"
                class="w-full rounded-lg border border-stone-200 dark:border-border px-3 py-2 text-sm" />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{{ t('backoffice.bookings.lateCheckoutTime') }}</label>
              <input type="datetime-local" v-model="lateCheckoutAt"
                class="w-full rounded-lg border border-stone-200 dark:border-border px-3 py-2 text-sm" />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{{ t('backoffice.bookings.extraChargeEgp') }}</label>
              <input type="number" min="0" step="50" v-model="earlyLateCharge"
                class="w-full rounded-lg border border-stone-200 dark:border-border px-3 py-2 text-sm" />
              <p class="text-xs text-gray-400 dark:text-gray-400 mt-0.5">{{ t('backoffice.bookings.extraChargeHint') }}</p>
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{{ t('backoffice.bookings.notesOptional') }}</label>
              <input type="text" v-model="earlyLateNotes" placeholder="—"
                class="w-full rounded-lg border border-stone-200 dark:border-border px-3 py-2 text-sm" />
            </div>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <button @click="showEarlyLateModal = false"
              class="px-4 py-2 text-sm rounded-lg border border-stone-200 dark:border-border hover:bg-stone-50 dark:bg-gray-800/60">
              {{ t('backoffice.bookings.cancel') }}
            </button>
            <button @click="submitEarlyLate" :disabled="earlyLateSubmitting"
              class="px-4 py-2 text-sm font-bold rounded-lg bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50">
              {{ earlyLateSubmitting ? '...' : t('backoffice.bookings.save') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Create booking modal -->
    <Teleport to="body">
      <div
        v-if="showCreateModal"
        class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
        @click.self="showCreateModal = false"
      >
        <div class="bg-white dark:bg-surface rounded-2xl p-6 w-full max-w-md shadow-2xl">
          <div class="flex items-center justify-between mb-5">
            <h2 class="text-lg font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.bookings.newBookingModalTitle') }}</h2>
            <button
              @click="showCreateModal = false"
              class="text-gray-400 dark:text-gray-400 hover:text-gray-700 dark:text-gray-300 text-2xl leading-none"
            >×</button>
          </div>

          <div class="space-y-4">
            <!-- Guest name -->
            <div>
              <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.bookings.guestNameRequiredLabel') }}</label>
              <input
                v-model="form.guest_name"
                type="text"
                :placeholder="t('backoffice.bookings.fullName')"
                class="w-full border border-stone-300 dark:border-gray-600 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <!-- Phone -->
            <div>
              <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.bookings.phoneNumber') }}</label>
              <input
                v-model="form.guest_phone"
                type="tel"
                placeholder="01xxxxxxxxx"
                class="w-full border border-stone-300 dark:border-gray-600 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                dir="ltr"
              />
            </div>

            <!-- Dates (first — the room list below depends on this range) -->
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.bookings.checkInDateRequiredLabel') }}</label>
                <input
                  v-model="form.check_in"
                  type="date"
                  class="w-full border border-stone-300 dark:border-gray-600 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  dir="ltr"
                />
              </div>
              <div>
                <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.bookings.checkOutDateRequiredLabel') }}</label>
                <input
                  v-model="form.check_out"
                  type="date"
                  class="w-full border border-stone-300 dark:border-gray-600 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  dir="ltr"
                />
              </div>
            </div>

            <!-- Room selection — multi-select checklist so one booking can cover
                 several rooms at once (e.g. a suite + an adjacent room). Depends
                 on the dates above. -->
            <div>
              <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">
                {{ t('backoffice.bookings.roomsRequiredLabel') }}
                <span v-if="form.room_ids.length" class="font-normal text-blue-600 dark:text-blue-300">{{ t('backoffice.bookings.roomsSelectedCount', { count: form.room_ids.length }) }}</span>
              </label>
              <div
                v-if="form.check_in && form.check_out && !roomsLoading && rooms.length > 0"
                class="border border-stone-300 dark:border-gray-600 rounded-xl max-h-40 overflow-y-auto divide-y divide-stone-100"
              >
                <label
                  v-for="room in rooms"
                  :key="room.id"
                  class="flex items-center gap-2 px-3 py-2 text-sm cursor-pointer hover:bg-stone-50 dark:bg-gray-800/60"
                >
                  <input
                    type="checkbox"
                    :value="room.id"
                    v-model="form.room_ids"
                    class="rounded border-stone-300 text-blue-600 focus:ring-blue-500 dark:border-gray-600 dark:text-blue-400"
                  />
                  <span>{{ room.name }}</span>
                </label>
              </div>
              <p v-if="!form.check_in || !form.check_out" class="text-xs text-gray-400 dark:text-gray-400 mt-1">{{ t('backoffice.bookings.selectDatesFirst') }}</p>
              <p v-else-if="roomsLoading" class="text-xs text-gray-400 dark:text-gray-400 mt-1">{{ t('backoffice.bookings.loadingAvailableRooms') }}</p>
              <p v-else-if="rooms.length === 0" class="mt-1 text-xs text-amber-600 dark:text-amber-300">{{ t('backoffice.bookings.noAvailableRoomsPeriod') }}</p>
            </div>

            <!-- Rate plan — optional, only plans that actually apply to the
                 chosen rooms' types show up (see applicableRatePlans above) -->
            <div v-if="form.room_ids.length > 0">
              <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.bookings.ratePlanOptional') }}</label>
              <select
                v-model="form.rate_plan_id"
                class="w-full border border-stone-300 dark:border-gray-600 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-surface"
              >
                <option :value="null">{{ t('backoffice.bookings.baseRateNoPlan') }}</option>
                <option
                  v-for="plan in applicableRatePlans"
                  :key="plan.id"
                  :value="plan.id"
                >{{ plan.name }}</option>
              </select>
              <p v-if="applicableRatePlans.length === 0" class="text-xs text-gray-400 dark:text-gray-400 mt-1">{{ t('backoffice.bookings.noApplicableRatePlans') }}</p>
            </div>

            <!-- Notes -->
            <div>
              <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{{ t('backoffice.bookings.notes') }}</label>
              <textarea
                v-model="form.notes"
                rows="2"
                :placeholder="t('backoffice.bookings.specialInstructions')"
                class="w-full border border-stone-300 dark:border-gray-600 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
              />
            </div>

            <!-- Error -->
            <div v-if="createError" class="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
              ⚠️ {{ createError }}
            </div>
          </div>

          <!-- Actions -->
          <div class="flex gap-3 mt-6">
            <button
              @click="showCreateModal = false"
              class="flex-1 rounded-xl bg-gray-100 py-2.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
            >{{ t('backoffice.bookings.cancel') }}</button>
            <button
              @click="createBooking"
              :disabled="submitting"
              class="flex-1 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 rounded-xl text-sm font-bold text-white transition-colors"
            >{{ submitting ? t('backoffice.bookings.saving') : t('backoffice.bookings.saveBooking') }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
