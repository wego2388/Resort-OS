<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '@resort-os/core'
import { AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

interface HKTask {
  id: number
  room_id: number
  task_type: string
  status: string
  priority: string
  assigned_to?: string
  created_at: string
}

// HousekeepingTaskRead (app/modules/pms/schemas.py) مفيهوش room_number —
// كانت الشاشة بتعرض رقم الغرفة الداخلي (room_id) بدل اسمها الحقيقي (زي
// "101") لأي مهمة. اتصلح بجلب أسماء الغرف مرة واحدة وعرضها هنا (عرض بيانات
// بس، مفيش منطق عمل)، نفس الأسلوب المستخدم في RoomsView.vue/BookingsView.vue.
const roomNameById = ref<Record<number, string>>({})

function roomLabel(task: HKTask): string {
  return roomNameById.value[task.room_id] ?? `#${task.room_id}`
}

const tasks = ref<HKTask[]>([])
const loading = ref(false)
const filterStatus = ref<string | null>(null)

const filteredTasks = computed(() =>
  filterStatus.value ? tasks.value.filter(t => t.status === filterStatus.value) : tasks.value
)

const priorityBorder: Record<string, string> = {
  high:   'border-r-4 border-r-red-500',
  normal: 'border-r-4 border-r-blue-500',
  low:    'border-r-4 border-r-gray-300',
}

const statusFlow: Record<string, string> = {
  dirty:      'cleaning',
  cleaning:   'inspecting',
  inspecting: 'available',
}

const statusLabels: Record<string, string> = {
  dirty:      '🔴 متسخة',
  cleaning:   '🔵 جاري التنظيف',
  inspecting: '🟡 فحص',
  available:  '🟢 جاهزة',
}

const nextActionLabel: Record<string, string> = {
  dirty:      'ابدأ التنظيف',
  cleaning:   'انتهيت — للفحص',
  inspecting: 'اعتمدها جاهزة',
}

const nextActionColor: Record<string, string> = {
  dirty:      'bg-red-600 hover:bg-red-700',
  cleaning:   'bg-blue-600 hover:bg-blue-700',
  inspecting: 'bg-amber-600 hover:bg-amber-700',
}

const taskTypeLabel: Record<string, string> = {
  checkout_clean: 'تنظيف إفراغ',
  stay_clean:     'تنظيف إقامة',
  inspection:     'فحص روتيني',
  deep_clean:     'تنظيف عميق',
}

const statusCounts = computed(() =>
  Object.fromEntries(
    Object.keys(statusLabels).map(s => [s, tasks.value.filter(t => t.status === s).length])
  )
)

async function fetchRoomNames() {
  try {
    const res = await api.get('/api/v1/pms/rooms', { params: { branch_id: branchId } })
    const list: { id: number; name: string }[] = res.data.items ?? res.data
    roomNameById.value = Object.fromEntries(list.map((r) => [r.id, r.name]))
  } catch (e) {
    console.error(e)
  }
}

async function fetchTasks() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/pms/housekeeping/tasks', {
      params: { branch_id: branchId }
    })
    tasks.value = res.data.tasks ?? res.data.items ?? res.data
  } catch(e) {
    console.error(e)
    toast.error('تعذّر تحميل مهام التدبير المنزلي')
  } finally { loading.value = false }
}

async function advanceStatus(task: HKTask) {
  const next = statusFlow[task.status]
  if (!next) return
  try {
    await api.patch(`/api/v1/pms/housekeeping/tasks/${task.id}`, { status: next })
    task.status = next
    if (next === 'available') {
      setTimeout(() => {
        tasks.value = tasks.value.filter(t => t.id !== task.id)
      }, 1500)
    }
  } catch(e: any) {
    console.error(e)
    toast.error(e?.response?.data?.detail ?? 'تعذّر تحديث حالة الغرفة')
  }
}

onMounted(() => {
  fetchRoomNames()
  fetchTasks()
})
</script>

<template>
  <div class="p-4" dir="rtl">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold text-gray-900">مهام التدبير المنزلي</h1>
      <button
        @click="fetchTasks"
        class="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
      >🔄 تحديث</button>
    </div>

    <!-- Summary chips -->
    <div class="flex gap-2 mb-4 flex-wrap">
      <div
        v-for="(label, status) in statusLabels"
        :key="status"
        class="px-3 py-1.5 bg-white rounded-xl border border-stone-200 text-sm font-medium text-gray-700 shadow-sm"
      >
        {{ label }}: <strong>{{ statusCounts[status] ?? 0 }}</strong>
      </div>
    </div>

    <!-- Filter tabs -->
    <div class="flex gap-2 mb-4 flex-wrap">
      <button
        @click="filterStatus = null"
        :class="[
          'px-3 py-1 rounded-lg text-sm font-medium transition-colors',
          !filterStatus ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
        ]"
      >الكل ({{ tasks.length }})</button>
      <button
        v-for="(label, status) in statusLabels"
        :key="status"
        @click="filterStatus = filterStatus === status ? null : status"
        :class="[
          'px-3 py-1 rounded-lg text-sm font-medium transition-colors',
          filterStatus === status ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
        ]"
      >{{ label }} ({{ statusCounts[status] ?? 0 }})</button>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="flex flex-col items-center justify-center py-16 text-gray-400 gap-3">
      <AppSpinner size="lg" />
      <p>جاري التحميل...</p>
    </div>

    <!-- Task list -->
    <div v-else class="space-y-3">
      <div
        v-for="task in filteredTasks"
        :key="task.id"
        :class="[
          'bg-white rounded-xl border border-stone-200 p-4 flex items-center justify-between shadow-sm',
          priorityBorder[task.priority] ?? ''
        ]"
      >
        <div class="flex-1 min-w-0 ml-4">
          <div class="flex items-center gap-2 mb-1 flex-wrap">
            <span class="font-bold text-gray-900 text-base">
              أوضة {{ roomLabel(task) }}
            </span>
            <span class="text-xs px-2 py-0.5 bg-gray-100 rounded-full text-gray-600 font-medium">
              {{ taskTypeLabel[task.task_type] ?? task.task_type }}
            </span>
            <span
              v-if="task.priority === 'high'"
              class="text-xs px-2 py-0.5 bg-red-100 text-red-700 rounded-full font-bold"
            >عاجل</span>
          </div>
          <div class="text-sm text-gray-500 mb-0.5">{{ statusLabels[task.status] ?? task.status }}</div>
          <div v-if="task.assigned_to" class="text-xs text-gray-400">{{ task.assigned_to }}</div>
        </div>

        <div class="flex-shrink-0">
          <button
            v-if="statusFlow[task.status]"
            @click="advanceStatus(task)"
            :class="[
              'px-4 py-2 rounded-xl text-sm font-bold text-white transition-colors',
              nextActionColor[task.status] ?? 'bg-blue-600 hover:bg-blue-700'
            ]"
          >{{ nextActionLabel[task.status] }}</button>
          <span
            v-else
            class="px-4 py-2 rounded-xl text-sm font-bold bg-green-100 text-green-700"
          >✓ مكتملة</span>
        </div>
      </div>

      <EmptyState v-if="filteredTasks.length === 0" icon="✨" title="لا توجد مهام معلقة" />
    </div>
  </div>
</template>
