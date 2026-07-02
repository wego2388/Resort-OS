<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const token = localStorage.getItem('access_token') ?? ''
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')
const h = { Authorization: `Bearer ${token}` }

interface Booking {
  id: number
  guest_name: string
  guest_phone?: string
  room_number?: string
  room_id?: number
  check_in: string
  check_out: string
  status: 'pending' | 'confirmed' | 'checked_in' | 'checked_out' | 'cancelled'
  total_price?: number
  notes?: string
}

interface RoomOption {
  id: number
  room_number: string
  room_type: string
  status: string
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
const form = ref({
  guest_name:  '',
  guest_phone: '',
  room_id:     null as number | null,
  check_in:    '',
  check_out:   '',
  notes:       '',
})

function openCreateModal() {
  form.value = { guest_name: '', guest_phone: '', room_id: null, check_in: '', check_out: '', notes: '' }
  createError.value = ''
  showCreateModal.value = true
}

// ─── API ──────────────────────────────────────────────────────────────────────
async function fetchBookings() {
  loading.value = true
  try {
    const res = await axios.get('/api/v1/pms/bookings', {
      headers: h,
      params: { branch_id: branchId, limit: 100 }
    })
    bookings.value = res.data.bookings ?? res.data.items ?? res.data
  } catch(e) { console.error(e) }
  finally { loading.value = false }
}

async function fetchRooms() {
  try {
    const res = await axios.get('/api/v1/pms/rooms', {
      headers: h,
      params: { branch_id: branchId, status: 'available' }
    })
    rooms.value = res.data.rooms ?? res.data.items ?? res.data
  } catch(e) { console.error(e) }
}

async function createBooking() {
  if (!form.value.guest_name.trim()) { createError.value = 'اسم الضيف مطلوب'; return }
  if (!form.value.room_id)            { createError.value = 'اختر الغرفة'; return }
  if (!form.value.check_in)           { createError.value = 'تاريخ الوصول مطلوب'; return }
  if (!form.value.check_out)          { createError.value = 'تاريخ المغادرة مطلوب'; return }

  submitting.value = true
  createError.value = ''
  try {
    await axios.post('/api/v1/pms/bookings', {
      ...form.value,
      branch_id: branchId,
    }, { headers: h })
    showCreateModal.value = false
    await fetchBookings()
  } catch(e: any) {
    createError.value = e?.response?.data?.detail ?? 'حدث خطأ، حاول مجدداً'
  } finally {
    submitting.value = false
  }
}

async function checkOut(booking: Booking) {
  if (!confirm(`تأكيد مغادرة ${booking.guest_name}؟`)) return
  try {
    await axios.patch(`/api/v1/pms/bookings/${booking.id}`, { status: 'checked_out' }, { headers: h })
    booking.status = 'checked_out'
  } catch(e) { console.error(e) }
}

async function checkIn(booking: Booking) {
  try {
    await axios.patch(`/api/v1/pms/bookings/${booking.id}`, { status: 'checked_in' }, { headers: h })
    booking.status = 'checked_in'
  } catch(e) { console.error(e) }
}

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('ar-EG', { day: 'numeric', month: 'short', year: 'numeric' })
}

onMounted(() => {
  fetchBookings()
  fetchRooms()
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
    <div v-if="loading" class="text-center py-16 text-gray-400">
      <div class="text-3xl mb-2">⏳</div>
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
            <td class="px-4 py-3 font-medium text-gray-700">{{ b.room_number ?? b.room_id ?? '—' }}</td>
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
          <div><span class="text-gray-400">غرفة: </span><strong>{{ b.room_number ?? b.room_id ?? '—' }}</strong></div>
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

      <div v-if="filteredBookings.length === 0" class="text-center py-16 text-gray-400">
        <div class="text-4xl mb-2">📋</div>
        <p>لا توجد حجوزات</p>
      </div>
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

            <!-- Room selection -->
            <div>
              <label class="block text-sm font-semibold text-gray-700 mb-1">الغرفة *</label>
              <select
                v-model="form.room_id"
                class="w-full border border-stone-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white"
              >
                <option :value="null" disabled>اختر غرفة...</option>
                <option
                  v-for="room in rooms"
                  :key="room.id"
                  :value="room.id"
                >{{ room.room_number }} — {{ room.room_type }}</option>
              </select>
            </div>

            <!-- Dates -->
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
