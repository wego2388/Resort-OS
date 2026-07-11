<script setup lang="ts">
// ⚠️ باج حقيقي كان هنا (لُقط أثناء اختبار حي للـ PMS): الشاشة كانت بتقرا
// أسماء حقول (`room_number`, `room_type` كنص، `current_booking`) مش موجودة
// خالص في RoomRead الحقيقي (app/modules/pms/schemas.py) — الحقول الحقيقية
// `name` و`room_type_id` (رقم، محتاج جدول أنواع الغرف عشان يتحول لاسم)، ومفيش
// `current_booking` في الـ response أصلاً. يعني "خريطة الغرف" (أهم شاشة
// للاستقبال) كانت بتعرض رقم غرفة فاضي ونوع غرفة فاضي لكل غرفة، ومفيش تفاصيل
// حجز حالي أبدًا حتى للغرف المشغولة — نفس فئة الباج اللي اتصلح قبل كده في
// BookingsView.vue (شوف تعليقه فوق). اتصلح بجلب أنواع الغرف + الحجوزات
// النشطة (checked_in) وتجميعها هنا للعرض فقط (مفيش منطق عمل، عرض بيانات بس).
//
// ⚠️ فجوة حقيقية تانية اتصلحت (wagdy.md #23): الشاشة كانت بتجيب حالة الغرف
// مرة واحدة عند الفتح + polling كل 60 ثانية بس — لو كاشير تاني سجّل دخول/
// خروج ضيف في نفس اللحظة، شاشة مدير تانية فاتحة الصفحة كانت تفضل قديمة لحد
// الـ polling التالي. اتضاف اتصال WebSocket لحظي حقيقي (نفس نمط
// BeachMapView.vue/useResortWebSocket — بث "rooms_changed" من
// pms/api/router.py عند أي تغيير حالة غرفة عبر HTTP). الـ polling كل 60
// ثانية والزرار اليدوي فضلوا زي ما هما عمدًا كطبقة أمان إضافية (WebSocket
// بيعيد الاتصال تلقائيًا لو النت اتقطع، لكن مفيش داعي نعتمد عليه 100%).
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, useResortWebSocket } from '@resort-os/core'
import { AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

interface Room {
  id: number
  name: string
  floor: number
  status: 'available' | 'occupied' | 'reserved' | 'checkout_pending' | 'maintenance'
  room_type_id: number
}

interface RoomTypeOption {
  id: number
  name: string
}

interface CurrentBookingInfo {
  guest_name: string
  check_out: string
}

const rooms = ref<Room[]>([])
const roomTypesById = ref<Record<number, RoomTypeOption>>({})
const currentBookingByRoomId = ref<Record<number, CurrentBookingInfo>>({})
const loading = ref(false)
const selectedRoom = ref<Room | null>(null)
const filterStatus = ref<string | null>(null)

function roomTypeName(room: Room): string {
  return roomTypesById.value[room.room_type_id]?.name ?? '—'
}

// القيم دي لازم تطابق Room.status الحقيقي بالظبط (app/modules/pms/models.py):
// available|occupied|reserved|maintenance|checkout_pending. كانت هنا "dirty"
// غلط بدل "reserved" — "dirty" أصلاً حالة HousekeepingTask مش Room، فكانت
// غرف الحجز المؤكد (لسه ما دخلش الضيف) بتتصنّف "غير معروفة" في العدّاد.
const statusConfig: Record<string, { label: string; color: string; bg: string; border: string }> = {
  available:        { label: 'فارغة',              color: 'text-green-700',  bg: 'bg-green-50',  border: 'border-green-400' },
  reserved:         { label: 'محجوزة',              color: 'text-purple-700', bg: 'bg-purple-50', border: 'border-purple-400' },
  occupied:         { label: 'مشغولة',              color: 'text-blue-700',   bg: 'bg-blue-50',   border: 'border-blue-400' },
  checkout_pending: { label: 'في انتظار التنظيف',  color: 'text-amber-700',  bg: 'bg-amber-50',  border: 'border-amber-400' },
  maintenance:      { label: 'صيانة',               color: 'text-red-700',    bg: 'bg-red-50',    border: 'border-red-400' },
}

const filteredRooms = computed(() =>
  filterStatus.value ? rooms.value.filter(r => r.status === filterStatus.value) : rooms.value
)

const counts = computed(() =>
  Object.fromEntries(
    Object.keys(statusConfig).map(s => [s, rooms.value.filter(r => r.status === s).length])
  )
)

async function fetchRoomTypes() {
  try {
    const res = await api.get('/api/v1/pms/room-types', { params: { branch_id: branchId } })
    const list: RoomTypeOption[] = res.data.items ?? res.data
    roomTypesById.value = Object.fromEntries(list.map((rt) => [rt.id, rt]))
  } catch (e) {
    console.error(e)
  }
}

// الحجوزات النشطة (checked_in) بس — عشان "الحجز الحالي" في تفاصيل الغرفة.
// عرض بيانات فقط (مفيش قرار عمل هنا)، مطابق لنفس الأسلوب المستخدم في
// BookingsView.vue (allRoomsById) لتجميع بيانات من endpoint تاني للعرض.
async function fetchCurrentBookings() {
  try {
    const res = await api.get('/api/v1/pms/bookings', {
      params: { branch_id: branchId, status: 'checked_in', page: 1, size: 100 },
    })
    const items: { rooms?: { room_id: number }[]; guest_name: string; check_out: string }[] =
      res.data.items ?? res.data
    const map: Record<number, CurrentBookingInfo> = {}
    for (const booking of items) {
      for (const br of booking.rooms ?? []) {
        map[br.room_id] = { guest_name: booking.guest_name, check_out: booking.check_out }
      }
    }
    currentBookingByRoomId.value = map
  } catch (e) {
    console.error(e)
  }
}

async function fetchRooms() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/pms/rooms', { params: { branch_id: branchId } })
    rooms.value = res.data.rooms ?? res.data.items ?? res.data
    await fetchCurrentBookings()
  } catch(e) {
    console.error(e)
    toast.error('تعذّر تحميل خريطة الغرف')
  } finally { loading.value = false }
}

// اتصال لحظي — نفس نمط BeachMapView.vue/useResortWebSocket (بيعيد الاتصال
// تلقائيًا لو النت اتقطع). الرسالة الوحيدة "rooms_changed" عامة عمدًا
// (راجع تعليق pms_rooms_websocket في الباك إند) — بترجّع نفس fetchRooms()
// اللي الشاشة أصلاً بتستخدمها، فمفيش منطق state-merge جديد يحتاج اختبار.
const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
const { onMessage } = useResortWebSocket(
  `${wsProtocol}//${location.host}/api/v1/pms/ws/rooms/${branchId}`,
)
onMessage((data: any) => {
  if (data?.type === 'rooms_changed') fetchRooms()
})

let refreshInterval: ReturnType<typeof setInterval>

onMounted(() => {
  fetchRoomTypes()
  fetchRooms()
  // طبقة أمان إضافية — الـ WebSocket فوق بيغطي التحديث اللحظي، لكن ده
  // بيضمن الشاشة تتصحّح لوحدها حتى لو رسالة WS اتفقدت (مثلاً reconnect
  // في نفس لحظة التغيير) من غير ما حد يحتاج يضغط "تحديث" يدوي.
  refreshInterval = setInterval(fetchRooms, 60_000)
})
onUnmounted(() => clearInterval(refreshInterval))
</script>

<template>
  <div class="p-4" dir="rtl">
    <!-- Page title + refresh -->
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold text-gray-900">خريطة الغرف</h1>
      <button
        @click="fetchRooms"
        class="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
      >🔄 تحديث</button>
    </div>

    <!-- Status stat cards / filter -->
    <div class="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-5">
      <div
        v-for="(cfg, status) in statusConfig"
        :key="status"
        :class="[
          'rounded-xl border-2 p-3 cursor-pointer transition-all select-none',
          cfg.border, cfg.bg,
          filterStatus === status ? 'ring-2 ring-blue-500 ring-offset-1' : 'hover:shadow-md'
        ]"
        @click="filterStatus = filterStatus === status ? null : status"
      >
        <div :class="['text-2xl font-black', cfg.color]">{{ counts[status] ?? 0 }}</div>
        <div class="text-xs font-medium text-gray-600 mt-0.5">{{ cfg.label }}</div>
      </div>
    </div>

    <!-- Active filter banner -->
    <div v-if="filterStatus" class="mb-3 flex items-center gap-2">
      <span class="text-sm text-gray-600">
        عرض: <strong>{{ statusConfig[filterStatus]?.label }}</strong> ({{ filteredRooms.length }} غرفة)
      </span>
      <button
        @click="filterStatus = null"
        class="text-xs text-blue-600 hover:text-blue-800 underline"
      >عرض الكل</button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex flex-col items-center justify-center py-16 text-gray-400 gap-3">
      <AppSpinner size="lg" />
      <p>جاري التحميل...</p>
    </div>

    <!-- Room grid -->
    <div v-else class="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 gap-3">
      <div
        v-for="room in filteredRooms"
        :key="room.id"
        :class="[
          'rounded-xl border-2 p-3 cursor-pointer transition-all hover:shadow-md select-none',
          statusConfig[room.status]?.border ?? 'border-gray-300',
          statusConfig[room.status]?.bg ?? 'bg-white'
        ]"
        @click="selectedRoom = room"
      >
        <div class="font-black text-lg text-gray-900">{{ room.name }}</div>
        <div class="text-xs text-gray-500 truncate">{{ roomTypeName(room) }}</div>
        <div :class="['text-xs font-semibold mt-1', statusConfig[room.status]?.color]">
          {{ statusConfig[room.status]?.label ?? room.status }}
        </div>
        <div v-if="currentBookingByRoomId[room.id]" class="text-xs text-gray-500 mt-1 truncate">
          {{ currentBookingByRoomId[room.id].guest_name }}
        </div>
      </div>

      <EmptyState v-if="filteredRooms.length === 0" class="col-span-full" icon="🛏️" title="لا توجد غرف" />
    </div>

    <!-- Room detail modal -->
    <Teleport to="body">
      <div
        v-if="selectedRoom"
        class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
        @click.self="selectedRoom = null"
      >
        <div class="bg-white rounded-2xl p-6 w-full max-w-sm shadow-2xl" dir="rtl">
          <div class="flex items-center justify-between mb-5">
            <h2 class="text-xl font-black text-gray-900">أوضة {{ selectedRoom.name }}</h2>
            <button
              @click="selectedRoom = null"
              class="text-gray-400 hover:text-gray-700 text-2xl leading-none"
            >×</button>
          </div>

          <div class="space-y-3 text-sm">
            <div class="flex justify-between border-b border-stone-100 pb-2">
              <span class="text-gray-500">النوع</span>
              <span class="font-medium text-gray-900">{{ roomTypeName(selectedRoom) }}</span>
            </div>
            <div class="flex justify-between border-b border-stone-100 pb-2">
              <span class="text-gray-500">الدور</span>
              <span class="font-medium text-gray-900">{{ selectedRoom.floor }}</span>
            </div>
            <div class="flex justify-between border-b border-stone-100 pb-2">
              <span class="text-gray-500">الحالة</span>
              <span :class="['font-bold', statusConfig[selectedRoom.status]?.color]">
                {{ statusConfig[selectedRoom.status]?.label ?? selectedRoom.status }}
              </span>
            </div>
            <div v-if="currentBookingByRoomId[selectedRoom.id]" class="pt-1">
              <p class="text-xs text-gray-400 font-semibold uppercase tracking-wide mb-2">الحجز الحالي</p>
              <div class="bg-blue-50 rounded-xl p-3 border border-blue-100">
                <div class="font-bold text-gray-900 mb-1">{{ currentBookingByRoomId[selectedRoom.id].guest_name }}</div>
                <div class="text-gray-500 text-xs">
                  مغادرة:
                  {{ new Date(currentBookingByRoomId[selectedRoom.id].check_out).toLocaleDateString('ar-EG') }}
                </div>
              </div>
            </div>
          </div>

          <button
            @click="selectedRoom = null"
            class="mt-5 w-full py-2.5 bg-gray-100 hover:bg-gray-200 rounded-xl text-sm font-medium text-gray-700 transition-colors"
          >إغلاق</button>
        </div>
      </div>
    </Teleport>
  </div>
</template>
