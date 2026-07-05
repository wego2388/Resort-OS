<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, parseApiTimestamp } from '@resort-os/core'
import { AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()


interface AttRecord {
  id: number; record_date: string; check_in?: string; check_out?: string
  hours_worked?: number; status: string
}

const records = ref<AttRecord[]>([])
const todayRecord = ref<AttRecord | null>(null)
const loading = ref(false)
const punching = ref(false)
// ⚠️ توقيت حقيقي اتكشف حي (2026-07-05): `new Date().toISOString()` بترجّع
// التاريخ بتوقيت UTC، مش بتوقيت المتصفح المحلي (توقيت القاهرة للموظف على
// أرض الواقع). في نافذة منتصف الليل المحلي لحد ما UTC توصل لنفس اليوم
// (~2-3 ساعات، فرق القاهرة عن UTC)، `today` هنا كان بيرجع "امبارح" بينما
// السجل اللي الباك إند رجّعه فعلاً بتاريخ "النهاردة" الحقيقي — يعني كارت
// "تسجيل الحضور النهاردة" كان بيفضل فاضي رغم إن الموظف سجّل حضوره فعلاً.
// الحل: احسب تاريخ اليوم من مكوّنات التاريخ المحلية (getFullYear/Month/Date)
// مش من toISOString().
function localDateStr(d: Date): string {
  const y = d.getFullYear(), m = d.getMonth() + 1, day = d.getDate()
  return `${y}-${String(m).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}
const today = localDateStr(new Date())
const currentTime = ref(new Date().toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit', second: '2-digit' }))

let clockInterval: ReturnType<typeof setInterval>
onMounted(() => { clockInterval = setInterval(() => { currentTime.value = new Date().toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }, 1000) })
onUnmounted(() => clearInterval(clockInterval))

const isClockedIn = computed(() => !!(todayRecord.value?.check_in && !todayRecord.value?.check_out))
const isCompleted  = computed(() => !!(todayRecord.value?.check_in && todayRecord.value?.check_out))

const statusConfig: Record<string, { label: string; color: string }> = {
  present:  { label: 'حاضر',    color: 'text-green-600 bg-green-50' },
  absent:   { label: 'غائب',    color: 'text-red-600 bg-red-50' },
  late:     { label: 'متأخر',   color: 'text-amber-600 bg-amber-50' },
  half_day: { label: 'نصف يوم', color: 'text-blue-600 bg-blue-50' },
}

function fmtTime(iso?: string) {
  if (!iso) return '—'
  // check_in/check_out تيجي من الباك إند بدون "Z" (naive UTC) — نفس فئة باج
  // الـ KDS الموثّقة في parseApiTimestamp، لازم نفس المعالجة هنا وإلا وقت
  // الحضور المعروض يبقى مزاح بفرق توقيت القاهرة عن UTC (~2-3 ساعات).
  return parseApiTimestamp(iso).toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' })
}

async function fetchAttendance() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/hr/me/attendance', { params: { size: 30 } })
    records.value = res.data.items ?? []
    todayRecord.value = records.value.find(r => r.record_date === today) ?? null
  } catch(e) {
    console.error(e)
    toast.error('تعذّر تحميل سجل الحضور')
  } finally { loading.value = false }
}

async function punch() {
  if (isCompleted.value || punching.value) return
  punching.value = true
  try {
    if (!isClockedIn.value) {
      const { data } = await api.post('/api/v1/hr/me/attendance/punch-in', {})
      todayRecord.value = data
    } else {
      const { data } = await api.post('/api/v1/hr/me/attendance/punch-out', {})
      todayRecord.value = data
    }
    await fetchAttendance()
  } catch(e: any) {
    console.error(e)
    toast.error(e?.response?.data?.detail ?? 'تعذّر تسجيل الحضور، حاول مرة أخرى')
  } finally { punching.value = false }
}

onMounted(fetchAttendance)
</script>

<template>
  <div dir="rtl" class="space-y-4">
    <!-- Clock + Punch card -->
    <div class="bg-white rounded-2xl border border-stone-200 p-6 shadow-sm text-center">
      <div class="text-sm text-gray-500 mb-1">الوقت الحالي</div>
      <div class="text-4xl font-mono font-black text-gray-900 mb-5" dir="ltr">{{ currentTime }}</div>

      <div v-if="todayRecord" class="flex items-center justify-center gap-8 text-sm mb-5">
        <div class="text-center">
          <div class="text-gray-400 text-xs mb-1">تسجيل الدخول</div>
          <div class="font-bold text-gray-900 text-lg">{{ fmtTime(todayRecord.check_in) }}</div>
        </div>
        <div class="w-px h-10 bg-stone-200"/>
        <div class="text-center">
          <div class="text-gray-400 text-xs mb-1">تسجيل الخروج</div>
          <div class="font-bold text-gray-900 text-lg">{{ fmtTime(todayRecord.check_out) }}</div>
        </div>
        <div class="w-px h-10 bg-stone-200"/>
        <div class="text-center">
          <div class="text-gray-400 text-xs mb-1">الساعات</div>
          <div class="font-bold text-gray-900 text-lg">{{ todayRecord.hours_worked?.toFixed(1) ?? '—' }}h</div>
        </div>
      </div>

      <button @click="punch" :disabled="punching || isCompleted"
        :class="[
          'w-full max-w-xs py-4 rounded-2xl text-lg font-black transition-all shadow-lg active:scale-95',
          isCompleted ? 'bg-gray-200 text-gray-400 cursor-not-allowed' :
          isClockedIn ? 'bg-red-600 hover:bg-red-700 text-white' : 'bg-green-600 hover:bg-green-700 text-white',
        ]"
      >
        {{ punching ? 'جاري...' : isCompleted ? '✓ تم إنهاء الدوام' : isClockedIn ? '🔴 تسجيل الخروج' : '🟢 تسجيل الحضور' }}
      </button>
    </div>

    <!-- History -->
    <div class="bg-white rounded-2xl border border-stone-200 shadow-sm overflow-hidden">
      <div class="px-5 py-4 border-b border-stone-100 flex items-center justify-between">
        <span class="font-bold text-gray-900">سجل آخر 30 يوم</span>
        <button @click="fetchAttendance" :class="['text-xs text-gray-400 hover:text-blue-600', loading ? 'animate-spin' : '']">↻</button>
      </div>
      <div v-if="loading" class="p-8 flex flex-col items-center justify-center text-gray-400 text-sm gap-2">
        <AppSpinner size="md" />
        <span>جاري التحميل...</span>
      </div>
      <div v-else class="divide-y divide-stone-100">
        <div v-for="rec in records" :key="rec.id" class="flex items-center justify-between px-5 py-3">
          <div>
            <div class="text-sm font-medium text-gray-900">
              {{ new Date(rec.record_date).toLocaleDateString('ar-EG', { weekday: 'short', month: 'short', day: 'numeric' }) }}
            </div>
            <div class="text-xs text-gray-400 mt-0.5 dir-ltr" dir="ltr">
              {{ fmtTime(rec.check_in) }} → {{ fmtTime(rec.check_out) }}
            </div>
          </div>
          <div class="flex items-center gap-3">
            <span class="text-sm text-gray-600 font-medium">{{ rec.hours_worked?.toFixed(1) ?? '—' }}h</span>
            <span :class="['px-2.5 py-0.5 rounded-full text-xs font-medium', statusConfig[rec.status]?.color ?? 'text-gray-600 bg-gray-50']">
              {{ statusConfig[rec.status]?.label ?? rec.status }}
            </span>
          </div>
        </div>
        <EmptyState v-if="records.length === 0" icon="📅" title="لا توجد سجلات حضور" />
      </div>
    </div>
  </div>
</template>
