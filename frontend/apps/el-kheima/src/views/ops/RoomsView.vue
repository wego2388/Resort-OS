<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '@resort-os/core'
import { AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

interface Room {
  id: number
  room_number: string
  floor: number
  status: 'available' | 'occupied' | 'checkout_pending' | 'maintenance' | 'dirty'
  room_type: string
  current_booking?: { guest_name: string; check_out: string }
}

const rooms = ref<Room[]>([])
const loading = ref(false)
const selectedRoom = ref<Room | null>(null)
const filterStatus = ref<string | null>(null)

const statusConfig: Record<string, { label: string; color: string; bg: string; border: string }> = {
  available:        { label: 'فارغة',              color: 'text-green-700',  bg: 'bg-green-50',  border: 'border-green-400' },
  occupied:         { label: 'مشغولة',              color: 'text-blue-700',   bg: 'bg-blue-50',   border: 'border-blue-400' },
  checkout_pending: { label: 'في انتظار التنظيف',  color: 'text-amber-700',  bg: 'bg-amber-50',  border: 'border-amber-400' },
  maintenance:      { label: 'صيانة',               color: 'text-red-700',    bg: 'bg-red-50',    border: 'border-red-400' },
  dirty:            { label: 'تنظيف',               color: 'text-purple-700', bg: 'bg-purple-50', border: 'border-purple-400' },
}

const filteredRooms = computed(() =>
  filterStatus.value ? rooms.value.filter(r => r.status === filterStatus.value) : rooms.value
)

const counts = computed(() =>
  Object.fromEntries(
    Object.keys(statusConfig).map(s => [s, rooms.value.filter(r => r.status === s).length])
  )
)

async function fetchRooms() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/pms/rooms', { params: { branch_id: branchId } })
    rooms.value = res.data.rooms ?? res.data.items ?? res.data
  } catch(e) {
    console.error(e)
    toast.error('تعذّر تحميل خريطة الغرف')
  } finally { loading.value = false }
}

let refreshInterval: ReturnType<typeof setInterval>

onMounted(() => {
  fetchRooms()
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
        <div class="font-black text-lg text-gray-900">{{ room.room_number }}</div>
        <div class="text-xs text-gray-500 truncate">{{ room.room_type }}</div>
        <div :class="['text-xs font-semibold mt-1', statusConfig[room.status]?.color]">
          {{ statusConfig[room.status]?.label }}
        </div>
        <div v-if="room.current_booking" class="text-xs text-gray-500 mt-1 truncate">
          {{ room.current_booking.guest_name }}
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
            <h2 class="text-xl font-black text-gray-900">أوضة {{ selectedRoom.room_number }}</h2>
            <button
              @click="selectedRoom = null"
              class="text-gray-400 hover:text-gray-700 text-2xl leading-none"
            >×</button>
          </div>

          <div class="space-y-3 text-sm">
            <div class="flex justify-between border-b border-stone-100 pb-2">
              <span class="text-gray-500">النوع</span>
              <span class="font-medium text-gray-900">{{ selectedRoom.room_type }}</span>
            </div>
            <div class="flex justify-between border-b border-stone-100 pb-2">
              <span class="text-gray-500">الدور</span>
              <span class="font-medium text-gray-900">{{ selectedRoom.floor }}</span>
            </div>
            <div class="flex justify-between border-b border-stone-100 pb-2">
              <span class="text-gray-500">الحالة</span>
              <span :class="['font-bold', statusConfig[selectedRoom.status]?.color]">
                {{ statusConfig[selectedRoom.status]?.label }}
              </span>
            </div>
            <div v-if="selectedRoom.current_booking" class="pt-1">
              <p class="text-xs text-gray-400 font-semibold uppercase tracking-wide mb-2">الحجز الحالي</p>
              <div class="bg-blue-50 rounded-xl p-3 border border-blue-100">
                <div class="font-bold text-gray-900 mb-1">{{ selectedRoom.current_booking.guest_name }}</div>
                <div class="text-gray-500 text-xs">
                  مغادرة:
                  {{ new Date(selectedRoom.current_booking.check_out).toLocaleDateString('ar-EG') }}
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
