<script setup lang="ts">
// لوحة مبيعات التايم شير — لفريق المبيعات (مختلفة عن لوحة الإدارة في TimeshareView).
// الهدف: مين نشط/متأخر/منتهي، مين يستاهل مكالمة النهاردة (بالتليفون)، والـ pipeline العام.
import { ref, onMounted } from 'vue'
import axios from 'axios'

const h = { Authorization: `Bearer ${localStorage.getItem('access_token')}` }
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

interface OverdueClient {
  id: number; customer_name: string; customer_phone: string | null
  room_type: string; overdue_amount: number; pending_count: number; next_due: string | null
}
interface UpcomingVisit {
  id: number; contract_number: string; customer_name: string; customer_phone: string | null
  room_type: string; week_number: number; visit_start: string; days_until: number
}
interface Dashboard {
  pipeline: Record<string, number>
  active_contracts: number
  overdue_contracts_count: number
  expired_contracts_count: number
  this_month_due: number
  collection_rate_pct: number
  total_value: number
  total_collected: number
  total_overdue: number
  overdue_clients: OverdueClient[]
  upcoming_visits: UpcomingVisit[]
}

const loading = ref(true)
const dash = ref<Dashboard | null>(null)

const PIPELINE_STAGES = [
  { key: 'draft', label: 'مسودة', color: 'bg-stone-300' },
  { key: 'active', label: 'نشط', color: 'bg-green-500' },
  { key: 'suspended', label: 'موقوف', color: 'bg-amber-400' },
  { key: 'expired', label: 'منتهي', color: 'bg-gray-400' },
  { key: 'cancelled', label: 'ملغى', color: 'bg-red-400' },
]

const fmt = (v: any) => `${(parseFloat(v) || 0).toLocaleString('ar-EG', { maximumFractionDigits: 0 })} ج`
const formatDateAr = (d?: string | null) => {
  if (!d) return '—'
  try { return new Date(d).toLocaleDateString('ar-EG', { day: 'numeric', month: 'short', year: 'numeric' }) }
  catch { return d }
}

async function load() {
  loading.value = true
  try {
    const r = await axios.get('/api/v1/timeshare/sales-dashboard', { headers: h, params: { branch_id: branchId } })
    dash.value = r.data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function pipelineTotal(): number {
  if (!dash.value) return 0
  return Object.values(dash.value.pipeline).reduce((a, b) => a + b, 0)
}

onMounted(load)
</script>

<template>
  <div dir="rtl" class="p-6 max-w-6xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-xl font-black text-gray-900">📞 لوحة مبيعات التايم شير</h1>
        <p class="text-xs text-gray-400 mt-1">مين يستاهل مكالمة النهاردة، وحالة العقود بشكل عام</p>
      </div>
      <button @click="load" class="px-4 py-2 rounded-xl bg-white border border-stone-200 text-sm font-bold text-gray-600 hover:bg-stone-50">
        🔄 تحديث
      </button>
    </div>

    <div v-if="loading" class="flex justify-center py-20">
      <div class="w-6 h-6 border-2 border-primary-700 border-t-transparent rounded-full animate-spin"/>
    </div>

    <template v-else-if="dash">
      <!-- Stat cards -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        <div class="bg-white rounded-2xl border border-green-200 p-4 shadow-sm">
          <p class="text-[10px] text-gray-400 font-bold uppercase tracking-wide mb-2">عقود نشطة</p>
          <p class="text-2xl font-black text-green-600">{{ dash.active_contracts }}</p>
        </div>
        <div class="bg-white rounded-2xl border border-red-200 p-4 shadow-sm">
          <p class="text-[10px] text-gray-400 font-bold uppercase tracking-wide mb-2">عقود متأخرة السداد</p>
          <p class="text-2xl font-black text-red-500">{{ dash.overdue_contracts_count }}</p>
        </div>
        <div class="bg-white rounded-2xl border border-gray-200 p-4 shadow-sm">
          <p class="text-[10px] text-gray-400 font-bold uppercase tracking-wide mb-2">عقود منتهية</p>
          <p class="text-2xl font-black text-gray-500">{{ dash.expired_contracts_count }}</p>
        </div>
        <div class="bg-white rounded-2xl border border-amber-200 p-4 shadow-sm">
          <p class="text-[10px] text-gray-400 font-bold uppercase tracking-wide mb-2">مستحق هذا الشهر</p>
          <p class="text-2xl font-black text-amber-500">{{ fmt(dash.this_month_due) }}</p>
        </div>
      </div>

      <!-- Pipeline -->
      <div class="bg-white rounded-2xl border border-stone-200 p-5 shadow-sm mb-5">
        <p class="font-black text-sm text-gray-900 mb-4">🔀 Pipeline العقود (مسودة ← نشط ← ...)</p>
        <div class="flex h-3 rounded-full overflow-hidden bg-stone-100 mb-4" v-if="pipelineTotal() > 0">
          <div v-for="stage in PIPELINE_STAGES" :key="stage.key"
               :class="stage.color"
               :style="{ width: `${((dash.pipeline[stage.key] || 0) / pipelineTotal()) * 100}%` }" />
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <div v-for="stage in PIPELINE_STAGES" :key="stage.key" class="flex items-center gap-2">
            <span :class="['w-2.5 h-2.5 rounded-full flex-shrink-0', stage.color]" />
            <span class="text-xs text-gray-500">{{ stage.label }}</span>
            <span class="text-sm font-black text-gray-900 mr-auto">{{ dash.pipeline[stage.key] || 0 }}</span>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <!-- Overdue clients — the main "call list" -->
        <div class="bg-white rounded-2xl border border-red-100 p-5 shadow-sm">
          <div class="flex items-center justify-between mb-4">
            <p class="font-black text-sm text-gray-900">📞 اتصل بهم النهاردة — متأخرون بالسداد</p>
            <span class="text-[10px] px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-bold">{{ dash.overdue_clients.length }}</span>
          </div>
          <div v-if="!dash.overdue_clients.length" class="text-center py-6 text-gray-300 text-xs">🎉 لا توجد متأخرات</div>
          <div v-else class="space-y-2 max-h-96 overflow-y-auto">
            <div v-for="c in dash.overdue_clients" :key="c.id"
                 class="flex items-center justify-between gap-3 p-3 rounded-xl bg-red-50 border border-red-100">
              <div class="flex-1 min-w-0">
                <div class="font-bold text-xs text-gray-900">{{ c.customer_name }}</div>
                <div class="text-[10px] text-gray-400 mt-0.5">
                  {{ c.room_type }} · {{ c.pending_count }} قسط معلق
                  <span v-if="c.next_due"> · استحق {{ formatDateAr(c.next_due) }}</span>
                </div>
              </div>
              <div class="text-left flex-shrink-0">
                <div class="text-sm font-black text-red-500">{{ fmt(c.overdue_amount) }}</div>
                <a v-if="c.customer_phone" :href="`tel:${c.customer_phone}`"
                   class="inline-flex items-center gap-1 text-[11px] font-bold text-white bg-green-600 hover:bg-green-700 rounded-lg px-2 py-1 mt-1">
                  📞 {{ c.customer_phone }}
                </a>
              </div>
            </div>
          </div>
        </div>

        <!-- Upcoming visits -->
        <div class="bg-white rounded-2xl border border-stone-200 p-5 shadow-sm">
          <div class="flex items-center justify-between mb-4">
            <p class="font-black text-sm text-gray-900">📅 زيارات قادمة — خلال 30 يوم</p>
            <span class="text-[10px] px-2 py-0.5 rounded-full bg-sky-100 text-sky-700 font-bold">{{ dash.upcoming_visits.length }}</span>
          </div>
          <div v-if="!dash.upcoming_visits.length" class="text-center py-6 text-gray-300 text-xs">لا توجد زيارات قادمة</div>
          <div v-else class="space-y-2 max-h-96 overflow-y-auto">
            <div v-for="v in dash.upcoming_visits" :key="v.id"
                 class="flex items-center justify-between gap-3 p-3 rounded-xl bg-stone-50 border border-stone-100">
              <div class="flex-1 min-w-0">
                <div class="font-bold text-xs text-gray-900">{{ v.customer_name }}</div>
                <div class="text-[10px] text-gray-400 mt-0.5">{{ v.room_type }} · أسبوع {{ v.week_number }} · {{ formatDateAr(v.visit_start) }}</div>
              </div>
              <div :class="['text-sm font-black flex-shrink-0', v.days_until <= 7 ? 'text-amber-500' : 'text-green-600']">
                {{ v.days_until === 0 ? 'اليوم!' : v.days_until === 1 ? 'غداً' : `${v.days_until} يوم` }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Collection summary -->
      <div class="bg-white rounded-2xl border border-stone-200 p-5 shadow-sm mt-5">
        <p class="font-black text-sm text-gray-900 mb-3">💰 التحصيل الإجمالي</p>
        <div class="flex items-center justify-between text-xs text-gray-500 mb-2">
          <span>{{ fmt(dash.total_collected) }} محصّل من {{ fmt(dash.total_value) }}</span>
          <span class="font-black text-gray-900">{{ dash.collection_rate_pct }}%</span>
        </div>
        <div class="w-full h-2.5 rounded-full bg-stone-100 overflow-hidden">
          <div class="h-full bg-green-500" :style="{ width: `${dash.collection_rate_pct}%` }" />
        </div>
      </div>
    </template>
  </div>
</template>
