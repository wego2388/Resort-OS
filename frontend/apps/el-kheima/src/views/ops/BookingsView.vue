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
import { api } from '@resort-os/core'
import { AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const toast = useToast()
const { confirm } = useConfirm()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

interface Booking {
  id: number
  guest_name: string
  guest_phone?: string
  rooms?: { room_id: number }[]
  check_in: string
  check_out: string
  status: 'pending' | 'confirmed' | 'checked_in' | 'checked_out' | 'cancelled'
  total_rate?: number
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
const statusConfig: Record<string, { label: string; color: string; bg: string }> = {
  pending:     { label: 'معلق',       color: 'text-amber-700',  bg: 'bg-amber-100' },
  confirmed:   { label: 'مؤكد',       color: 'text-blue-700',   bg: 'bg-blue-100' },
  checked_in:  { label: 'داخل',       color: 'text-green-700',  bg: 'bg-green-100' },
  checked_out: { label: 'خارج',       color: 'text-gray-600',   bg: 'bg-gray-100' },
  cancelled:   { label: 'ملغي',       color: 'text-red-700',    bg: 'bg-red-100' },
}

const statusCounts = computed(() =>
  Object.fromEntries(
    Object.keys(statusConfig).map(s => [s, bookings.value.filter(b => b.status === s).length])
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
  room_id:      null as number | null,
  check_in:     '',
  check_out:    '',
  notes:        '',
  rate_plan_id: null as number | null,
})

// خطط الأسعار الفعّالة اللي تنطبق فعليًا على نوع الغرفة المختارة — إما خطة
// عامة (room_type_id = null، لكل الفرع) أو خطة مخصصة لنفس نوع الغرفة دي
// بالظبط. باقي الخطط (مخصصة لنوع تاني) بتتخفي عشان الاستقبال ميختارش خطة
// هتتجاهل بصمت وقت الحساب (services._room_rate_for بتطبّقها بس لو نوع الغرفة
// مطابق، غير كده بترجع للسعر الأساسي الخام).
const applicableRatePlans = computed(() => {
  const room = rooms.value.find((r) => r.id === form.value.room_id)
  if (!room) return []
  return ratePlans.value.filter((p) => p.room_type_id === null || p.room_type_id === room.room_type_id)
})

async function fetchRatePlans() {
  try {
    const res = await api.get('/api/v1/pms/rate-plans', {
      params: { branch_id: branchId, active_only: true },
    })
    ratePlans.value = res.data.items ?? res.data
  } catch (e) {
    console.error(e)
  }
}

function openCreateModal() {
  form.value = {
    guest_name: '', guest_phone: '', room_id: null,
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
    const res = await api.get('/api/v1/pms/bookings', {
      params: { branch_id: branchId, page: 1, size: 100 }
    })
    bookings.value = res.data.items ?? res.data
  } catch(e) {
    console.error(e)
    toast.error('تعذّر تحميل الحجوزات')
  } finally { loading.value = false }
}

// كل الغرف (مهما كانت حالتها الحالية) — تُستخدم فقط لعرض اسم الغرفة في جدول
// الحجوزات (roomLabel أسفل)، مش لتحديد إتاحة الحجز الجديد.
const allRoomsById = ref<Record<number, RoomOption>>({})

async function fetchAllRooms() {
  try {
    const res = await api.get('/api/v1/pms/rooms', { params: { branch_id: branchId } })
    const list: RoomOption[] = res.data.items ?? res.data
    allRoomsById.value = Object.fromEntries(list.map((r) => [r.id, r]))
  } catch (e) {
    console.error(e)
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
    const res = await api.get('/api/v1/pms/rooms/available', {
      params: { branch_id: branchId, check_in: form.value.check_in, check_out: form.value.check_out },
    })
    rooms.value = res.data
    // الغرفة المختارة سابقًا ممكن تبقى مش متاحة بعد تغيير التواريخ
    if (form.value.room_id && !rooms.value.some((r) => r.id === form.value.room_id)) {
      form.value.room_id = null
      form.value.rate_plan_id = null
    }
  } catch(e) {
    console.error(e)
    toast.error('تعذّر تحميل قائمة الغرف المتاحة')
  } finally {
    roomsLoading.value = false
  }
}

watch(() => [form.value.check_in, form.value.check_out], fetchAvailableRooms)

// خطة الأسعار المختارة ممكن تبقى مش منطبقة بعد تغيير الغرفة (نوع مختلف)
watch(() => form.value.room_id, () => {
  if (form.value.rate_plan_id && !applicableRatePlans.value.some((p) => p.id === form.value.rate_plan_id)) {
    form.value.rate_plan_id = null
  }
})

async function createBooking() {
  if (!form.value.guest_name.trim()) { createError.value = 'اسم الضيف مطلوب'; return }
  if (!form.value.check_in)           { createError.value = 'تاريخ الوصول مطلوب'; return }
  if (!form.value.check_out)          { createError.value = 'تاريخ المغادرة مطلوب'; return }
  if (!form.value.room_id)            { createError.value = 'اختر الغرفة'; return }

  submitting.value = true
  createError.value = ''
  try {
    await api.post('/api/v1/pms/bookings', {
      guest_name:   form.value.guest_name,
      guest_phone:  form.value.guest_phone || undefined,
      check_in:     form.value.check_in,
      check_out:    form.value.check_out,
      notes:        form.value.notes || undefined,
      room_ids:     [form.value.room_id],
      branch_id:    branchId,
      rate_plan_id: form.value.rate_plan_id || undefined,
    })
    showCreateModal.value = false
    await Promise.all([fetchBookings(), fetchAllRooms()])
  } catch(e: any) {
    createError.value = e?.response?.data?.detail
      ?? e?.response?.data?.message
      ?? 'حدث خطأ، حاول مجدداً'
  } finally {
    submitting.value = false
  }
}

async function checkOut(booking: Booking) {
  const ok = await confirm({ message: `تأكيد مغادرة ${booking.guest_name}؟`, danger: true })
  if (!ok) return
  try {
    const res = await api.post(`/api/v1/pms/bookings/${booking.id}/checkout`)
    booking.status = res.data.status
    toast.success('تم تسجيل مغادرة الضيف')
  } catch(e: any) {
    console.error(e)
    toast.error(e?.response?.data?.detail ?? 'تعذّر تسجيل مغادرة الضيف')
  }
}

async function checkIn(booking: Booking) {
  try {
    const res = await api.post(`/api/v1/pms/bookings/${booking.id}/checkin`)
    booking.status = res.data.status
    toast.success('تم تسجيل دخول الضيف')
  } catch(e: any) {
    console.error(e)
    toast.error(e?.response?.data?.detail ?? 'تعذّر تسجيل دخول الضيف')
  }
}

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('ar-EG', { day: 'numeric', month: 'short', year: 'numeric' })
}

onMounted(() => {
  fetchBookings()
  fetchAllRooms()
})
</script>

<template>
  <div class="p-4" dir="rtl">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold text-gray-900">الحجوزات</h1>
      <div class="flex gap-2">
        <button
          @click="fetchBookings"
          class="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm font-medium text-gray-700 transition-colors"
        >🔄</button>
        <button
          @click="openCreateModal"
          class="px-4 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-bold hover:bg-blue-700 transition-colors"
        >+ حجز جديد</button>
      </div>
    </div>

    <!-- Status filter tabs -->
    <div class="flex gap-2 mb-4 overflow-x-auto pb-1">
      <button
        @click="filterStatus = null"
        :class="[
          'flex-shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
          !filterStatus ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
        ]"
      >الكل ({{ bookings.length }})</button>
      <button
        v-for="(cfg, status) in statusConfig"
        :key="status"
        @click="filterStatus = filterStatus === status ? null : status"
        :class="[
          'flex-shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
          filterStatus === status ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
        ]"
      >{{ cfg.label }} ({{ statusCounts[status] ?? 0 }})</button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex flex-col items-center justify-center py-16 text-gray-400 gap-3">
      <AppSpinner size="lg" />
      <p>جاري التحميل...</p>
    </div>

    <!-- Desktop table -->
    <div v-else class="hidden md:block bg-white rounded-2xl border border-stone-200 shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-gray-50 border-b border-stone-200">
          <tr>
            <th class="text-right px-4 py-3 font-semibold text-gray-600">#</th>
            <th class="text-right px-4 py-3 font-semibold text-gray-600">الضيف</th>
            <th class="text-right px-4 py-3 font-semibold text-gray-600">الغرفة</th>
            <th class="text-right px-4 py-3 font-semibold text-gray-600">الوصول</th>
            <th class="text-right px-4 py-3 font-semibold text-gray-600">المغادرة</th>
            <th class="text-right px-4 py-3 font-semibold text-gray-600">الحالة</th>
            <th class="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="b in filteredBookings"
            :key="b.id"
            class="border-b border-stone-100 hover:bg-gray-50 transition-colors"
          >
            <td class="px-4 py-3 text-gray-400 font-mono text-xs">{{ b.id }}</td>
            <td class="px-4 py-3">
              <div class="font-semibold text-gray-900">{{ b.guest_name }}</div>
              <div v-if="b.guest_phone" class="text-xs text-gray-400 dir-ltr">{{ b.guest_phone }}</div>
            </td>
            <td class="px-4 py-3 font-medium text-gray-700">{{ roomLabel(b) }}</td>
            <td class="px-4 py-3 text-gray-600">{{ formatDate(b.check_in) }}</td>
            <td class="px-4 py-3 text-gray-600">{{ formatDate(b.check_out) }}</td>
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
              >تسجيل دخول</button>
              <button
                v-else-if="b.status === 'checked_in'"
                @click="checkOut(b)"
                class="px-3 py-1 bg-amber-600 text-white text-xs font-bold rounded-lg hover:bg-amber-700 transition-colors"
              >تسجيل خروج</button>
            </td>
          </tr>
          <tr v-if="filteredBookings.length === 0">
            <td colspan="7" class="px-4 py-16 text-center text-gray-400">
              لا توجد حجوزات
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
        class="bg-white rounded-xl border border-stone-200 p-4 shadow-sm"
      >
        <div class="flex items-start justify-between mb-2">
          <div>
            <div class="font-bold text-gray-900">{{ b.guest_name }}</div>
            <div v-if="b.guest_phone" class="text-xs text-gray-400">{{ b.guest_phone }}</div>
          </div>
          <span :class="['px-2 py-0.5 rounded-full text-xs font-bold', statusConfig[b.status]?.bg, statusConfig[b.status]?.color]">
            {{ statusConfig[b.status]?.label ?? b.status }}
          </span>
        </div>
        <div class="grid grid-cols-3 gap-2 text-xs text-gray-600 mb-3">
          <div><span class="text-gray-400">غرفة: </span><strong>{{ roomLabel(b) }}</strong></div>
          <div><span class="text-gray-400">وصول: </span>{{ formatDate(b.check_in) }}</div>
          <div><span class="text-gray-400">خروج: </span>{{ formatDate(b.check_out) }}</div>
        </div>
        <div class="flex gap-2">
          <button
            v-if="b.status === 'confirmed'"
            @click="checkIn(b)"
            class="flex-1 py-1.5 bg-green-600 text-white text-xs font-bold rounded-lg hover:bg-green-700 transition-colors"
          >تسجيل دخول</button>
          <button
            v-else-if="b.status === 'checked_in'"
            @click="checkOut(b)"
            class="flex-1 py-1.5 bg-amber-600 text-white text-xs font-bold rounded-lg hover:bg-amber-700 transition-colors"
          >تسجيل خروج</button>
        </div>
      </div>

      <EmptyState v-if="filteredBookings.length === 0" icon="📋" title="لا توجد حجوزات" />
    </div>

    <!-- Create booking modal -->
    <Teleport to="body">
      <div
        v-if="showCreateModal"
        class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
        @click.self="showCreateModal = false"
      >
        <div class="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl" dir="rtl">
          <div class="flex items-center justify-between mb-5">
            <h2 class="text-lg font-black text-gray-900">حجز جديد</h2>
            <button
              @click="showCreateModal = false"
              class="text-gray-400 hover:text-gray-700 text-2xl leading-none"
            >×</button>
          </div>

          <div class="space-y-4">
            <!-- Guest name -->
            <div>
              <label class="block text-sm font-semibold text-gray-700 mb-1">اسم الضيف *</label>
              <input
                v-model="form.guest_name"
                type="text"
                placeholder="الاسم الكامل"
                class="w-full border border-stone-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <!-- Phone -->
            <div>
              <label class="block text-sm font-semibold text-gray-700 mb-1">رقم الهاتف</label>
              <input
                v-model="form.guest_phone"
                type="tel"
                placeholder="01xxxxxxxxx"
                class="w-full border border-stone-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                dir="ltr"
              />
            </div>

            <!-- Dates (first — the room list below depends on this range) -->
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-semibold text-gray-700 mb-1">تاريخ الوصول *</label>
                <input
                  v-model="form.check_in"
                  type="date"
                  class="w-full border border-stone-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  dir="ltr"
                />
              </div>
              <div>
                <label class="block text-sm font-semibold text-gray-700 mb-1">تاريخ المغادرة *</label>
                <input
                  v-model="form.check_out"
                  type="date"
                  class="w-full border border-stone-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  dir="ltr"
                />
              </div>
            </div>

            <!-- Room selection — depends on the dates above -->
            <div>
              <label class="block text-sm font-semibold text-gray-700 mb-1">الغرفة *</label>
              <select
                v-model="form.room_id"
                :disabled="!form.check_in || !form.check_out || roomsLoading"
                class="w-full border border-stone-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white disabled:bg-gray-50 disabled:text-gray-400"
              >
                <option :value="null" disabled>اختر غرفة...</option>
                <option
                  v-for="room in rooms"
                  :key="room.id"
                  :value="room.id"
                >{{ room.name }}</option>
              </select>
              <p v-if="!form.check_in || !form.check_out" class="text-xs text-gray-400 mt-1">اختر تاريخ الوصول والمغادرة أولاً لعرض الغرف المتاحة</p>
              <p v-else-if="roomsLoading" class="text-xs text-gray-400 mt-1">جاري تحميل الغرف المتاحة...</p>
              <p v-else-if="rooms.length === 0" class="text-xs text-amber-600 mt-1">لا توجد غرف متاحة في هذه الفترة</p>
            </div>

            <!-- Rate plan — optional, only plans that actually apply to the
                 chosen room's type show up (see applicableRatePlans above) -->
            <div v-if="form.room_id">
              <label class="block text-sm font-semibold text-gray-700 mb-1">خطة الأسعار (اختياري)</label>
              <select
                v-model="form.rate_plan_id"
                class="w-full border border-stone-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white"
              >
                <option :value="null">السعر الأساسي (بدون خطة)</option>
                <option
                  v-for="plan in applicableRatePlans"
                  :key="plan.id"
                  :value="plan.id"
                >{{ plan.name }}</option>
              </select>
              <p v-if="applicableRatePlans.length === 0" class="text-xs text-gray-400 mt-1">لا توجد خطط أسعار سارية لنوع هذه الغرفة</p>
            </div>

            <!-- Notes -->
            <div>
              <label class="block text-sm font-semibold text-gray-700 mb-1">ملاحظات</label>
              <textarea
                v-model="form.notes"
                rows="2"
                placeholder="أي تعليمات خاصة..."
                class="w-full border border-stone-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
              />
            </div>

            <!-- Error -->
            <div v-if="createError" class="text-red-600 text-sm bg-red-50 rounded-xl px-3 py-2 border border-red-200">
              ⚠️ {{ createError }}
            </div>
          </div>

          <!-- Actions -->
          <div class="flex gap-3 mt-6">
            <button
              @click="showCreateModal = false"
              class="flex-1 py-2.5 bg-gray-100 hover:bg-gray-200 rounded-xl text-sm font-medium text-gray-700 transition-colors"
            >إلغاء</button>
            <button
              @click="createBooking"
              :disabled="submitting"
              class="flex-1 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 rounded-xl text-sm font-bold text-white transition-colors"
            >{{ submitting ? 'جاري الحفظ...' : 'حفظ الحجز' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
