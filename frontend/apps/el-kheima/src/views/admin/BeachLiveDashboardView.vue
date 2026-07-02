<script setup lang="ts">
// لوحة الشاطئ الحيّة — سعة حالية (gauge)، حصص فنادق B2B، وتنبيه تلقائي
// لما فندق يوصل لـ 5 أشخاص أو أقل متبقين في حصته اليومية.
import { ref, computed, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

const h = { Authorization: `Bearer ${localStorage.getItem('access_token')}` }
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

interface B2BStatus {
  contract_id: number; hotel_name: string; daily_quota: number
  checked_in_today: number; remaining_quota: number
  is_quota_exhausted: boolean; quota_warning: boolean
}
interface LiveDashboard {
  capacity_used: number; capacity_max: number; capacity_pct: number
  towels_available: number; towels_used: number
  surge_active: boolean; surge_pct: number
  b2b_contracts: B2BStatus[]
  quota_alerts: B2BStatus[]
}
interface EODByType { tx_type: string; label: string; quantity: number; count: number; total_amount: number }
interface EODReport {
  date: string; total_entries: number; total_revenue: number
  b2b_entries: number; b2b_revenue: number; towel_revenue: number; voided_count: number
  by_type: EODByType[]
  vs_yesterday_pct: number | null; vs_last_week_pct: number | null
}

const loading = ref(true)
const dash = ref<LiveDashboard | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

const eodLoading = ref(false)
const eod = ref<EODReport | null>(null)
const downloadingPdf = ref(false)

function pctLabel(pct: number | null): string {
  if (pct === null) return '—'
  return `${pct >= 0 ? '▲' : '▼'} ${Math.abs(pct)}%`
}

async function loadEod() {
  eodLoading.value = true
  try {
    const r = await axios.get('/api/v1/beach/eod-report', { headers: h, params: { branch_id: branchId } })
    eod.value = r.data
  } catch (e) {
    console.error(e)
  } finally {
    eodLoading.value = false
  }
}

async function downloadEodPdf() {
  downloadingPdf.value = true
  try {
    const res = await axios.get('/api/v1/beach/eod-report/pdf', {
      headers: h, params: { branch_id: branchId }, responseType: 'blob',
    })
    const url = URL.createObjectURL(res.data)
    const w = window.open(url, '_blank')
    if (!w) {
      const a = document.createElement('a')
      a.href = url
      a.download = `beach-eod-${eod.value?.date ?? 'today'}.pdf`
      a.click()
    }
  } catch (e) {
    console.error(e)
  } finally {
    downloadingPdf.value = false
  }
}

const gaugeColor = computed(() => {
  const pct = dash.value?.capacity_pct ?? 0
  if (pct >= 90) return 'text-red-500'
  if (pct >= 80) return 'text-amber-500'
  return 'text-green-600'
})

async function load() {
  try {
    const r = await axios.get('/api/v1/beach/live-dashboard', { headers: h, params: { branch_id: branchId } })
    dash.value = r.data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  loadEod()
  pollTimer = setInterval(load, 15000) // تحديث كل 15 ثانية
})
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<template>
  <div dir="rtl" class="p-6 max-w-6xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-xl font-black text-gray-900">🏖️ لوحة الشاطئ الحيّة</h1>
        <p class="text-xs text-gray-400 mt-1">تتحدّث تلقائياً كل 15 ثانية</p>
      </div>
      <button @click="load" class="px-4 py-2 rounded-xl bg-white border border-stone-200 text-sm font-bold text-gray-600 hover:bg-stone-50">
        🔄 تحديث
      </button>
    </div>

    <div v-if="loading" class="flex justify-center py-20">
      <div class="w-6 h-6 border-2 border-primary-700 border-t-transparent rounded-full animate-spin"/>
    </div>

    <template v-else-if="dash">
      <!-- Quota alerts banner -->
      <div v-if="dash.quota_alerts.length" class="mb-5 space-y-2">
        <div v-for="a in dash.quota_alerts" :key="a.contract_id"
             class="flex items-center gap-3 bg-red-50 border border-red-200 rounded-xl p-3 animate-pulse">
          <span class="text-xl">🚨</span>
          <span class="text-sm font-bold text-red-700">
            {{ a.hotel_name }} — باقي {{ a.remaining_quota }} أشخاص بس من حصة {{ a.daily_quota }}!
          </span>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-5">
        <!-- Capacity gauge -->
        <div class="bg-white rounded-2xl border border-stone-200 p-6 shadow-sm flex flex-col items-center justify-center">
          <p class="text-xs text-gray-400 font-bold uppercase tracking-wide mb-3">السعة الحالية</p>
          <div class="relative w-32 h-32">
            <svg class="w-32 h-32 -rotate-90" viewBox="0 0 100 100">
              <circle cx="50" cy="50" r="42" fill="none" stroke="#F1F0EC" stroke-width="10" />
              <circle cx="50" cy="50" r="42" fill="none" :class="gaugeColor" stroke="currentColor"
                      stroke-width="10" stroke-linecap="round"
                      :stroke-dasharray="`${(dash.capacity_pct / 100) * 264} 264`" />
            </svg>
            <div class="absolute inset-0 flex flex-col items-center justify-center">
              <span :class="['text-2xl font-black', gaugeColor]">{{ dash.capacity_pct }}%</span>
              <span class="text-[10px] text-gray-400">{{ dash.capacity_used }}/{{ dash.capacity_max }}</span>
            </div>
          </div>
          <p v-if="dash.surge_active" class="mt-3 text-[11px] font-bold text-amber-600 bg-amber-50 px-3 py-1 rounded-full">
            ⚡ Surge مُفعّل ({{ dash.surge_pct }}%)
          </p>
        </div>

        <!-- Towels -->
        <div class="bg-white rounded-2xl border border-stone-200 p-6 shadow-sm">
          <p class="text-xs text-gray-400 font-bold uppercase tracking-wide mb-3">الفوط</p>
          <p class="text-3xl font-black text-gray-900">{{ dash.towels_available }}</p>
          <p class="text-xs text-gray-400 mt-1">متاحة من إجمالي {{ dash.towels_available + dash.towels_used }}</p>
          <div class="w-full h-2 rounded-full bg-stone-100 overflow-hidden mt-3">
            <div class="h-full bg-sky-400"
                 :style="{ width: `${dash.towels_used + dash.towels_available > 0 ? (dash.towels_used / (dash.towels_used + dash.towels_available)) * 100 : 0}%` }" />
          </div>
        </div>

        <!-- B2B partners overview -->
        <div class="bg-white rounded-2xl border border-stone-200 p-6 shadow-sm">
          <p class="text-xs text-gray-400 font-bold uppercase tracking-wide mb-3">فنادق B2B نشطة</p>
          <p class="text-3xl font-black text-gray-900">{{ dash.b2b_contracts.length }}</p>
          <p class="text-xs text-gray-400 mt-1">{{ dash.quota_alerts.length }} في حالة تنبيه</p>
        </div>
      </div>

      <!-- B2B partners table -->
      <div class="bg-white rounded-2xl border border-stone-200 p-5 shadow-sm">
        <p class="font-black text-sm text-gray-900 mb-4">🏨 شركاء B2B — الحصة اليومية</p>
        <div v-if="!dash.b2b_contracts.length" class="text-center py-6 text-gray-300 text-xs">لا يوجد عقود B2B نشطة</div>
        <div v-else class="space-y-2">
          <div v-for="c in dash.b2b_contracts" :key="c.contract_id"
               :class="['flex items-center justify-between gap-3 p-3 rounded-xl border',
                        c.quota_warning ? 'bg-red-50 border-red-200' : 'bg-stone-50 border-stone-100']">
            <div class="flex-1 min-w-0">
              <div class="font-bold text-sm text-gray-900">{{ c.hotel_name }}</div>
              <div class="text-[11px] text-gray-400 mt-0.5">{{ c.checked_in_today }} / {{ c.daily_quota }} دخلوا اليوم</div>
            </div>
            <div class="w-32 flex-shrink-0">
              <div class="w-full h-2 rounded-full bg-stone-200 overflow-hidden">
                <div :class="['h-full', c.is_quota_exhausted ? 'bg-red-500' : c.quota_warning ? 'bg-amber-500' : 'bg-green-500']"
                     :style="{ width: `${Math.min(100, (c.checked_in_today / c.daily_quota) * 100)}%` }" />
              </div>
            </div>
            <div class="text-left flex-shrink-0 w-20">
              <div :class="['text-sm font-black', c.is_quota_exhausted ? 'text-red-500' : c.quota_warning ? 'text-amber-500' : 'text-green-600']">
                {{ c.remaining_quota }}
              </div>
              <div class="text-[10px] text-gray-400">متبقي</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Daily EOD Report -->
      <div class="bg-white rounded-2xl border border-stone-200 p-5 shadow-sm mt-5">
        <div class="flex items-center justify-between mb-4">
          <p class="font-black text-sm text-gray-900">📋 تقرير نهاية اليوم</p>
          <button @click="downloadEodPdf" :disabled="downloadingPdf || !eod"
                  class="px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-bold disabled:opacity-50">
            {{ downloadingPdf ? '...' : '🖨️ طباعة PDF' }}
          </button>
        </div>

        <div v-if="eodLoading" class="text-center py-6 text-gray-300 text-xs">جاري التحميل...</div>
        <template v-else-if="eod">
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
            <div class="bg-stone-50 rounded-xl p-3">
              <p class="text-[10px] text-gray-400 mb-1">إجمالي الدخول</p>
              <p class="text-lg font-black text-gray-900">{{ eod.total_entries }}</p>
            </div>
            <div class="bg-stone-50 rounded-xl p-3">
              <p class="text-[10px] text-gray-400 mb-1">إيرادات الفوط</p>
              <p class="text-lg font-black text-sky-600">{{ eod.towel_revenue }} ج</p>
            </div>
            <div class="bg-stone-50 rounded-xl p-3">
              <p class="text-[10px] text-gray-400 mb-1">مقارنة بالأمس</p>
              <p :class="['text-lg font-black', (eod.vs_yesterday_pct ?? 0) >= 0 ? 'text-green-600' : 'text-red-500']">
                {{ pctLabel(eod.vs_yesterday_pct) }}
              </p>
            </div>
            <div class="bg-stone-50 rounded-xl p-3">
              <p class="text-[10px] text-gray-400 mb-1">مقارنة بالأسبوع الماضي</p>
              <p :class="['text-lg font-black', (eod.vs_last_week_pct ?? 0) >= 0 ? 'text-green-600' : 'text-red-500']">
                {{ pctLabel(eod.vs_last_week_pct) }}
              </p>
            </div>
          </div>

          <table class="w-full text-xs">
            <thead>
              <tr class="text-gray-400 border-b border-stone-100">
                <th class="text-right font-bold py-2">نوع العملية</th>
                <th class="text-center font-bold py-2">الكمية</th>
                <th class="text-left font-bold py-2">الإجمالي</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in eod.by_type" :key="t.tx_type" class="border-b border-stone-50">
                <td class="py-2 text-gray-800">{{ t.label }}</td>
                <td class="py-2 text-center text-gray-600">{{ t.quantity }}</td>
                <td class="py-2 text-left font-bold text-gray-900">{{ t.total_amount }} ج</td>
              </tr>
              <tr v-if="!eod.by_type.length">
                <td colspan="3" class="text-center py-6 text-gray-300">لا توجد عمليات اليوم</td>
              </tr>
            </tbody>
          </table>
        </template>
      </div>
    </template>
  </div>
</template>
