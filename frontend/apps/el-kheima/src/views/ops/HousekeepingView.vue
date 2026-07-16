<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, ENDPOINTS , useAuthStore } from '@resort-os/core'
import { AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const auth = useAuthStore()
const branchId = auth.branchId

interface HKTask {
  id: number
  room_id: number
  task_type: string
  status: string
  priority: string
  assigned_to?: number | null
  created_at: string
}
interface EmployeeOption { id: number; full_name: string }

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
    const res = await api.get(ENDPOINTS.pms.rooms, { params: { branch_id: branchId } })
    const list: { id: number; name: string }[] = res.data.items ?? res.data
    roomNameById.value = Object.fromEntries(list.map((r) => [r.id, r.name]))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تحميل أسماء الغرف')
  }
}

// wagdy.md P-12: assigned_to كان عمود حقيقي بيتعرض كـ رقم موظف خام بدون
// اسم، ومن غير أي طريقة يتحدّد بيها من الشاشة أصلاً.
const employees = ref<EmployeeOption[]>([])
const employeeNameById = ref<Record<number, string>>({})
const assigningTaskId = ref<number | null>(null)

async function fetchEmployees() {
  try {
    const res = await api.get(ENDPOINTS.hr.employees, {
      params: { branch_id: branchId, status: 'active', size: 100 },
    })
    employees.value = res.data.items ?? []
    employeeNameById.value = Object.fromEntries(employees.value.map((e) => [e.id, e.full_name]))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تحميل قائمة الموظفين')
  }
}

async function assignTask(task: HKTask, employeeId: number | null) {
  const previous = task.assigned_to
  task.assigned_to = employeeId
  try {
    await api.patch(ENDPOINTS.pms_extra.housekeepingTask(task.id), {
      status: task.status, assigned_to: employeeId,
    })
    toast.success(employeeId ? 'تم تعيين الموظف' : 'تم إلغاء التعيين')
  } catch (e: any) {
    task.assigned_to = previous
    toast.error(e?.response?.data?.detail ?? 'تعذّر تعيين الموظف')
  } finally {
    assigningTaskId.value = null
  }
}

async function fetchTasks() {
  loading.value = true
  try {
    const res = await api.get(ENDPOINTS.pms.housekeeping, {
      params: { branch_id: branchId }
    })
    tasks.value = res.data.tasks ?? res.data.items ?? res.data
  } catch(e) {
    toast.error('تعذّر تحميل مهام التدبير المنزلي')
  } finally { loading.value = false }
}

async function advanceStatus(task: HKTask) {
  const next = statusFlow[task.status]
  if (!next) return
  try {
    await api.patch(ENDPOINTS.pms_extra.housekeepingTask(task.id), { status: next })
    task.status = next
    if (next === 'available') {
      setTimeout(() => {
        tasks.value = tasks.value.filter(t => t.id !== task.id)
      }, 1500)
    }
  } catch(e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تحديث حالة الغرفة')
  }
}

onMounted(() => {
  fetchRoomNames()
  fetchEmployees()
  fetchTasks()
})
</script>

<template>
  <div class="p-4" dir="rtl">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold text-gray-900 dark:text-gray-100">مهام التدبير المنزلي</h1>
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
        class="px-3 py-1.5 bg-white dark:bg-surface rounded-xl border border-stone-200 dark:border-border text-sm font-medium text-gray-700 dark:text-gray-300 shadow-sm"
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
          !filterStatus ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 dark:text-gray-500 hover:bg-gray-200'
        ]"
      >الكل ({{ tasks.length }})</button>
      <button
        v-for="(label, status) in statusLabels"
        :key="status"
        @click="filterStatus = filterStatus === status ? null : status"
        :class="[
          'px-3 py-1 rounded-lg text-sm font-medium transition-colors',
          filterStatus === status ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 dark:text-gray-500 hover:bg-gray-200'
        ]"
      >{{ label }} ({{ statusCounts[status] ?? 0 }})</button>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="flex flex-col items-center justify-center py-16 text-gray-400 dark:text-gray-500 gap-3">
      <AppSpinner size="lg" />
      <p>جاري التحميل...</p>
    </div>

    <!-- Task list -->
    <div v-else class="space-y-3">
      <div
        v-for="task in filteredTasks"
        :key="task.id"
        :class="[
          'bg-white dark:bg-surface rounded-xl border border-stone-200 dark:border-border p-4 flex items-center justify-between shadow-sm',
          priorityBorder[task.priority] ?? ''
        ]"
      >
        <div class="flex-1 min-w-0 ml-4">
          <div class="flex items-center gap-2 mb-1 flex-wrap">
            <span class="font-bold text-gray-900 dark:text-gray-100 text-base">
              أوضة {{ roomLabel(task) }}
            </span>
            <span class="text-xs px-2 py-0.5 bg-gray-100 rounded-full text-gray-600 dark:text-gray-500 font-medium">
              {{ taskTypeLabel[task.task_type] ?? task.task_type }}
            </span>
            <span
              v-if="task.priority === 'high'"
              class="text-xs px-2 py-0.5 bg-red-100 text-red-700 rounded-full font-bold"
            >عاجل</span>
          </div>
          <div class="text-sm text-gray-500 dark:text-gray-500 mb-0.5">{{ statusLabels[task.status] ?? task.status }}</div>

          <!-- تعيين موظف — عرض عادي بيتحول لـ select عند الضغط -->
          <div v-if="assigningTaskId !== task.id" class="text-xs mt-0.5">
            <button
              @click="assigningTaskId = task.id"
              class="text-gray-400 dark:text-gray-500 hover:text-blue-600 underline decoration-dotted"
            >
              👤 {{ task.assigned_to ? (employeeNameById[task.assigned_to] ?? `موظف #${task.assigned_to}`) : 'تعيين موظف...' }}
            </button>
          </div>
          <select
            v-else
            :value="task.assigned_to ?? ''"
            @change="assignTask(task, ($event.target as HTMLSelectElement).value ? Number(($event.target as HTMLSelectElement).value) : null)"
            @blur="assigningTaskId = null"
            class="text-xs border border-stone-200 dark:border-border rounded-lg px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            <option value="">بدون تعيين</option>
            <option v-for="emp in employees" :key="emp.id" :value="emp.id">{{ emp.full_name }}</option>
          </select>
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
