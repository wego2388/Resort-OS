<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { api } from '@resort-os/core'
import { AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

interface Leave {
  id: number; leave_type_id: number; start_date: string; end_date: string
  days_requested: number; status: string; reason?: string
}
interface LeaveType { id: number; name: string; name_ar?: string }

const leaves = ref<Leave[]>([])
const leaveTypes = ref<LeaveType[]>([])
const loading = ref(false)
const showModal = ref(false)
const submitting = ref(false)
const successMsg = ref('')
const errorMsg = ref('')
const form = ref({ leave_type_id: null as number | null, start_date: '', end_date: '', reason: '' })

const leaveTypeLabel = computed(() => (id: number) => {
  const t = leaveTypes.value.find(lt => lt.id === id)
  return t ? (t.name_ar || t.name) : `نوع #${id}`
})

const statusColors: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-700',
  approved: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
}
const statusLabels: Record<string, string> = {
  pending: 'معلق', approved: 'معتمد', rejected: 'مرفوض'
}

function calcDays() {
  if (!form.value.start_date || !form.value.end_date) return 0
  const diff = new Date(form.value.end_date).getTime() - new Date(form.value.start_date).getTime()
  return Math.max(0, Math.round(diff / 86400000) + 1)
}

async function fetchLeaveTypes() {
  try {
    const res = await api.get('/api/v1/hr/leave-types', { params: { branch_id: branchId } })
    leaveTypes.value = res.data
    if (leaveTypes.value.length && form.value.leave_type_id === null) {
      form.value.leave_type_id = leaveTypes.value[0].id
    }
  } catch(e) {
    console.error(e)
    toast.error('تعذّر تحميل أنواع الإجازات')
  }
}

async function fetchLeaves() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/hr/me/leaves')
    leaves.value = res.data.items ?? []
  } catch(e) {
    console.error(e)
    toast.error('تعذّر تحميل طلبات الإجازات')
  } finally { loading.value = false }
}

async function requestLeave() {
  if (!form.value.start_date || !form.value.end_date || !form.value.leave_type_id) {
    errorMsg.value = 'الرجاء تحديد نوع الإجازة وتاريخ البداية والنهاية'; return
  }
  submitting.value = true; errorMsg.value = ''
  try {
    await api.post('/api/v1/hr/me/leaves/request', {
      leave_type_id: form.value.leave_type_id,
      start_date: form.value.start_date,
      end_date: form.value.end_date,
      reason: form.value.reason || null,
    })
    showModal.value = false
    form.value = { leave_type_id: leaveTypes.value[0]?.id ?? null, start_date: '', end_date: '', reason: '' }
    successMsg.value = 'تم تقديم طلب الإجازة بنجاح ✓'
    setTimeout(() => successMsg.value = '', 4000)
    await fetchLeaves()
  } catch(e: any) {
    errorMsg.value = e?.response?.data?.detail ?? 'حدث خطأ في تقديم الطلب'
  } finally { submitting.value = false }
}

onMounted(() => { fetchLeaveTypes(); fetchLeaves() })
</script>

<template>
  <div dir="rtl" class="space-y-4">
    <div class="flex items-center justify-between">
      <h2 class="font-bold text-gray-900 text-lg">طلبات الإجازات</h2>
      <button @click="showModal = true"
        class="px-4 py-2 bg-blue-700 text-white rounded-xl text-sm font-bold hover:bg-blue-800 transition-colors">
        + طلب إجازة
      </button>
    </div>

    <div v-if="successMsg" class="bg-green-100 text-green-700 px-4 py-3 rounded-xl text-sm font-medium">{{ successMsg }}</div>

    <div v-if="loading" class="flex flex-col items-center justify-center py-12 text-gray-400 gap-3">
      <AppSpinner size="lg" />
      <p>جاري التحميل...</p>
    </div>
    <div v-else class="space-y-3">
      <div v-for="leave in leaves" :key="leave.id"
        class="bg-white rounded-2xl border border-stone-200 p-4 shadow-sm">
        <div class="flex items-start justify-between">
          <div>
            <div class="font-semibold text-gray-900">{{ leaveTypeLabel(leave.leave_type_id) }}</div>
            <div class="text-sm text-gray-500 mt-0.5">
              {{ new Date(leave.start_date).toLocaleDateString('ar-EG') }}
              ←
              {{ new Date(leave.end_date).toLocaleDateString('ar-EG') }}
            </div>
            <div class="text-xs text-gray-400 mt-0.5">{{ leave.days_requested }} {{ leave.days_requested === 1 ? 'يوم' : 'أيام' }}</div>
            <div v-if="leave.reason" class="text-xs text-gray-500 mt-1.5 italic border-r-2 border-stone-200 pr-2">{{ leave.reason }}</div>
          </div>
          <span :class="['px-2.5 py-1 rounded-full text-xs font-medium flex-shrink-0', statusColors[leave.status] ?? 'bg-gray-100 text-gray-600']">
            {{ statusLabels[leave.status] ?? leave.status }}
          </span>
        </div>
      </div>

      <div v-if="leaves.length === 0" class="bg-white rounded-2xl border border-stone-200">
        <EmptyState icon="🌴" title="لا توجد طلبات إجازات" subtitle='اضغط "طلب إجازة" لتقديم طلب جديد' />
      </div>
    </div>

    <!-- Request modal -->
    <Teleport to="body">
      <div v-if="showModal" class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" @click.self="showModal = false">
        <div class="bg-white rounded-2xl p-6 w-full max-w-sm shadow-2xl" dir="rtl">
          <div class="flex items-center justify-between mb-5">
            <h3 class="font-bold text-gray-900 text-lg">طلب إجازة جديدة</h3>
            <button @click="showModal = false" class="text-gray-400 hover:text-gray-600 text-2xl leading-none">×</button>
          </div>
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">نوع الإجازة</label>
              <select v-model="form.leave_type_id"
                class="w-full border border-stone-200 rounded-xl px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option v-for="lt in leaveTypes" :key="lt.id" :value="lt.id">{{ lt.name_ar || lt.name }}</option>
              </select>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">من</label>
                <input v-model="form.start_date" type="date"
                  class="w-full border border-stone-200 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">إلى</label>
                <input v-model="form.end_date" type="date"
                  class="w-full border border-stone-200 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
              </div>
            </div>
            <div v-if="calcDays() > 0" class="text-center text-sm font-medium text-blue-700 bg-blue-50 py-2 rounded-lg">
              {{ calcDays() }} {{ calcDays() === 1 ? 'يوم' : 'أيام' }}
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">السبب (اختياري)</label>
              <textarea v-model="form.reason" rows="2" placeholder="وصف سبب الإجازة..."
                class="w-full border border-stone-200 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none text-sm"/>
            </div>
            <div v-if="errorMsg" class="bg-red-50 text-red-600 px-3 py-2 rounded-lg text-sm">{{ errorMsg }}</div>
          </div>
          <div class="flex gap-2 mt-5">
            <button @click="showModal = false" class="flex-1 py-2.5 border-2 border-stone-200 rounded-xl text-sm font-semibold text-gray-600 hover:bg-gray-50">إلغاء</button>
            <button @click="requestLeave" :disabled="submitting"
              class="flex-1 py-2.5 bg-blue-700 text-white rounded-xl text-sm font-bold hover:bg-blue-800 disabled:opacity-50">
              {{ submitting ? 'جاري الإرسال...' : 'تقديم الطلب' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
