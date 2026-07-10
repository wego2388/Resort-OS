<script setup lang="ts">
// لوحة الشاطئ الحيّة — سعة حالية (gauge)، حصص فنادق B2B، وتنبيه تلقائي
// لما فندق يوصل لـ 5 أشخاص أو أقل متبقين في حصته اليومية.
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, useAuthStore } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, useToast, useConfirm } from '@resort-os/ui'

const toast = useToast()
const { confirm } = useConfirm()
const auth = useAuthStore()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

interface B2BStatus {
  contract_id: number; hotel_name: string; daily_quota: number
  checked_in_today: number; remaining_quota: number
  is_quota_exhausted: boolean; quota_warning: boolean
  // باج حقيقي كان هنا (اتصلح 2026-07-06): عقد فندق منتهي فعليًا
  // (valid_until فات) بس لسه is_active=True كان يظهر هنا زي أي شريك سليم
  // بالظبط — "8 متبقي" باللون الأخضر — رغم إن أي محاولة تسجيل دخول فعلية
  // كانت (بعد الإصلاح) هترفض فورًا. is_valid_today موجودة في الرد من
  // الباك إند من زمان الإصلاح، بس محدش كان بيعرضها هنا. دلوقتي أي عقد
  // منتهي بيظهر بشارة "منتهي" واضحة بدل ما يتوه وسط الشركاء السليمين.
  is_valid_today: boolean
  // ائتمان/تحصيل — نفس فئة الفجوة اللي is_valid_today صلّحتها بالظبط، بس
  // للرصيد المستحق مش لتاريخ الصلاحية: عقد فندق متجاوز حد ائتمانه أو
  // متأخر في السداد كان (قبل هذه الإضافة) هيفضل يقبل تسجيل دخول جديد بلا
  // حد خالص — مفيش أي مفهوم "رصيد مستحق" أو "تأخر سداد" في النظام أصلاً.
  credit_limit: number | null
  outstanding_balance: number
  credit_exceeded: boolean
  is_overdue: boolean
  payment_terms_days: number
}
interface LiveDashboard {
  capacity_used: number; capacity_max: number; capacity_pct: number
  towels_available: number; towels_used: number
  surge_active: boolean; surge_pct: number
  b2b_contracts: B2BStatus[]
  quota_alerts: B2BStatus[]
  overdue_alerts: B2BStatus[]
}

// تعديل حد الائتمان — admin فقط (نفس مستوى إنشاء عقد B2B نفسه)، والتسوية
// (تسجيل تحصيل الفاتورة الدورية) — manager فقط.
const editingCreditId = ref<number | null>(null)
const creditLimitInput = ref<string>('')
const savingCredit = ref(false)
const settlingId = ref<number | null>(null)

function openCreditEdit(c: B2BStatus) {
  editingCreditId.value = c.contract_id
  creditLimitInput.value = c.credit_limit !== null ? String(c.credit_limit) : ''
}

async function saveCreditLimit(c: B2BStatus) {
  savingCredit.value = true
  try {
    const value = creditLimitInput.value.trim()
    const payload = { credit_limit: value === '' ? null : Number(value) }
    await api.patch(`/api/v1/beach/b2b-contracts/${c.contract_id}`, payload, { params: { branch_id: branchId } })
    toast.success(`تم تحديث حد الائتمان لـ ${c.hotel_name}`)
    editingCreditId.value = null
    await load()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'فشل تحديث حد الائتمان')
  } finally {
    savingCredit.value = false
  }
}

async function settleContract(c: B2BStatus) {
  const ok = await confirm({
    message: `تسجيل تسوية (تحصيل) رصيد ${c.hotel_name} المستحق (${c.outstanding_balance.toLocaleString()} ج.م) بالكامل حتى اليوم؟`,
    confirmText: 'نعم، اتسوّى', cancelText: 'تراجع',
  })
  if (!ok) return
  settlingId.value = c.contract_id
  try {
    await api.post(`/api/v1/beach/b2b-contracts/${c.contract_id}/settle`, {}, { params: { branch_id: branchId } })
    toast.success(`تم تسجيل تسوية رصيد ${c.hotel_name}`)
    await load()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'فشل تسجيل التسوية')
  } finally {
    settlingId.value = null
  }
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
// #24: polling interval كـ named constant — سهّل التعديل لاحقًا بدون
// البحث عن الـ magic number 15000 في كل مكان
const POLL_INTERVAL_MS = 15_000 // 15 ثانية — Beach dashboard حي

let pollTimer: ReturnType<typeof setInterval> | null = null

// حالة الاتصال بالـ poll — نتّبع نفس نمط KitchenDisplayView/BarDisplayView
// (نقطة ملوّنة + "متصل"/"منقطع") عشان المدير يعرف إن اللوحة فعلاً لايف مش
// معلّقة على بيانات قديمة بصمت.
const isConnected = ref(true)

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
    const r = await api.get('/api/v1/beach/eod-report', { params: { branch_id: branchId } })
    eod.value = r.data
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'فشل تحميل تقرير نهاية اليوم')
  } finally {
    eodLoading.value = false
  }
}

async function downloadEodPdf() {
  downloadingPdf.value = true
  try {
    const res = await api.get('/api/v1/beach/eod-report/pdf', {
      params: { branch_id: branchId }, responseType: 'blob',
    })
    const url = URL.createObjectURL(res.data)
    const w = window.open(url, '_blank')
    if (!w) {
      const a = document.createElement('a')
      a.href = url
      a.download = `beach-eod-${eod.value?.date ?? 'today'}.pdf`
      a.click()
    }
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'فشل تحميل ملف PDF')
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
    const r = await api.get('/api/v1/beach/live-dashboard', { params: { branch_id: branchId } })
    dash.value = r.data
    if (!isConnected.value) toast.success('تم استعادة الاتصال باللوحة الحية')
    isConnected.value = true
  } catch (e: any) {
    // نطلّع toast مرة واحدة بس عند لحظة الانقطاع، مش كل 15 ثانية طول ما
    // الاتصال مقطوع — النقطة الحمراء في الهيدر كفاية كمؤشر مستمر.
    if (isConnected.value) toast.error('فشل تحديث اللوحة الحية — البيانات المعروضة قد تكون قديمة')
    isConnected.value = false
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  loadEod()
  pollTimer = setInterval(load, POLL_INTERVAL_MS)
})
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<template>
  <div dir="rtl" class="p-6 max-w-6xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-xl font-black text-gray-900">🏖️ لوحة الشاطئ الحيّة</h1>
        <div class="flex items-center gap-3 mt-1">
          <p class="text-xs text-gray-400">تتحدّث تلقائياً كل 15 ثانية</p>
          <div class="flex items-center gap-1.5">
            <div :class="['w-2 h-2 rounded-full', isConnected ? 'bg-green-400 animate-pulse' : 'bg-red-400']" />
            <span :class="['text-xs font-semibold', isConnected ? 'text-green-600' : 'text-red-500']">
              {{ isConnected ? 'متصل' : 'منقطع' }}
            </span>
          </div>
        </div>
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

      <!-- Overdue B2B balance alerts banner — نفس نمط quota_alerts بالظبط،
           للرصيد المستحق المتأخر عن مهلة السداد بدل الحصة اليومية. -->
      <div v-if="dash.overdue_alerts.length" class="mb-5 space-y-2">
        <div v-for="a in dash.overdue_alerts" :key="a.contract_id"
             class="flex items-center gap-3 bg-amber-50 border border-amber-300 rounded-xl p-3">
          <span class="text-xl">💸</span>
          <span class="text-sm font-bold text-amber-800">
            {{ a.hotel_name }} — رصيد متأخر السداد {{ a.outstanding_balance.toLocaleString() }} ج.م
            (تخطّى مهلة {{ a.payment_terms_days }} يوم)
          </span>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-5">
        <!-- Capacity gauge -->
        <AppCard padding="md" class="flex flex-col items-center justify-center">
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
          <AppBadge v-if="dash.surge_active" variant="warning" size="sm" class="mt-3">
            ⚡ Surge مُفعّل ({{ dash.surge_pct }}%)
          </AppBadge>
        </AppCard>

        <!-- Towels -->
        <AppCard padding="md">
          <p class="text-xs text-gray-400 font-bold uppercase tracking-wide mb-3">الفوط</p>
          <p class="text-3xl font-black text-gray-900">{{ dash.towels_available }}</p>
          <p class="text-xs text-gray-400 mt-1">متاحة من إجمالي {{ dash.towels_available + dash.towels_used }}</p>
          <div class="w-full h-2 rounded-full bg-stone-100 overflow-hidden mt-3">
            <div class="h-full bg-sky-400"
                 :style="{ width: `${dash.towels_used + dash.towels_available > 0 ? (dash.towels_used / (dash.towels_used + dash.towels_available)) * 100 : 0}%` }" />
          </div>
        </AppCard>

        <!-- B2B partners overview -->
        <AppCard padding="md">
          <p class="text-xs text-gray-400 font-bold uppercase tracking-wide mb-3">فنادق B2B نشطة</p>
          <p class="text-3xl font-black text-gray-900">{{ dash.b2b_contracts.length }}</p>
          <p class="text-xs text-gray-400 mt-1">{{ dash.quota_alerts.length }} في حالة تنبيه</p>
        </AppCard>
      </div>

      <!-- B2B partners table -->
      <AppCard padding="md">
        <p class="font-black text-sm text-gray-900 mb-4">🏨 شركاء B2B — الحصة اليومية</p>
        <div v-if="!dash.b2b_contracts.length" class="text-center py-6 text-gray-300 text-xs">لا يوجد عقود B2B نشطة</div>
        <div v-else class="space-y-2">
          <div v-for="c in dash.b2b_contracts" :key="c.contract_id"
               :class="['p-3 rounded-xl border',
                        !c.is_valid_today ? 'bg-gray-100 border-gray-200 opacity-70' :
                        c.is_overdue ? 'bg-amber-50 border-amber-300' :
                        c.quota_warning ? 'bg-red-50 border-red-200' : 'bg-stone-50 border-stone-100']">
            <div class="flex items-center justify-between gap-3">
              <div class="flex-1 min-w-0">
                <div class="font-bold text-sm text-gray-900 flex items-center gap-2 flex-wrap">
                  {{ c.hotel_name }}
                  <span v-if="!c.is_valid_today"
                        class="px-1.5 py-0.5 rounded-full bg-gray-400 text-white text-[9px] font-bold">
                    منتهي — خارج نافذة الصلاحية
                  </span>
                  <span v-if="c.is_overdue"
                        class="px-1.5 py-0.5 rounded-full bg-amber-500 text-white text-[9px] font-bold">
                    متأخر السداد
                  </span>
                  <span v-if="c.credit_exceeded"
                        class="px-1.5 py-0.5 rounded-full bg-red-500 text-white text-[9px] font-bold">
                    تخطّى حد الائتمان
                  </span>
                </div>
                <div class="text-[11px] text-gray-400 mt-0.5">{{ c.checked_in_today }} / {{ c.daily_quota }} دخلوا اليوم</div>
              </div>
              <div class="w-32 flex-shrink-0">
                <div class="w-full h-2 rounded-full bg-stone-200 overflow-hidden">
                  <div :class="['h-full', !c.is_valid_today ? 'bg-gray-400' : c.is_quota_exhausted ? 'bg-red-500' : c.quota_warning ? 'bg-amber-500' : 'bg-green-500']"
                       :style="{ width: `${Math.min(100, (c.checked_in_today / c.daily_quota) * 100)}%` }" />
                </div>
              </div>
              <div class="text-left flex-shrink-0 w-20">
                <div :class="['text-sm font-black', !c.is_valid_today ? 'text-gray-400' : c.is_quota_exhausted ? 'text-red-500' : c.quota_warning ? 'text-amber-500' : 'text-green-600']">
                  {{ c.remaining_quota }}
                </div>
                <div class="text-[10px] text-gray-400">متبقي</div>
              </div>
            </div>

            <!-- الائتمان: الرصيد المستحق + حد الائتمان (قابل للتعديل — admin
                 فقط) + زر تسوية (manager فقط). -->
            <div class="flex items-center justify-between gap-3 mt-2 pt-2 border-t border-stone-200/60 text-[11px]">
              <div class="text-gray-500">
                رصيد مستحق:
                <span :class="['font-bold', c.credit_exceeded ? 'text-red-600' : 'text-gray-700']">
                  {{ c.outstanding_balance.toLocaleString() }} ج.م
                </span>
                <template v-if="editingCreditId !== c.contract_id">
                  <span class="text-gray-400"> / حد: {{ c.credit_limit !== null ? c.credit_limit.toLocaleString() + ' ج.م' : 'بلا حد' }}</span>
                  <button v-if="auth.hasRole('admin')" @click="openCreditEdit(c)"
                          class="mr-1 text-primary-700 hover:underline">✏️ تعديل</button>
                </template>
                <span v-else class="inline-flex items-center gap-1 mr-1">
                  <input v-model="creditLimitInput" type="number" min="0" step="1" placeholder="بلا حد"
                         class="w-24 px-1.5 py-0.5 rounded border border-stone-300 text-[11px]" />
                  <button :disabled="savingCredit" @click="saveCreditLimit(c)"
                          class="text-green-700 font-bold hover:underline">حفظ</button>
                  <button :disabled="savingCredit" @click="editingCreditId = null"
                          class="text-gray-400 hover:underline">إلغاء</button>
                </span>
              </div>
              <AppButton v-if="auth.hasRole('manager') && c.outstanding_balance > 0"
                         variant="secondary" size="sm" :loading="settlingId === c.contract_id"
                         @click="settleContract(c)">
                💳 تسوية الرصيد
              </AppButton>
            </div>
          </div>
        </div>
      </AppCard>

      <!-- Daily EOD Report -->
      <AppCard padding="md" class="mt-5">
        <div class="flex items-center justify-between mb-4">
          <p class="font-black text-sm text-gray-900">📋 تقرير نهاية اليوم</p>
          <AppButton variant="primary" size="sm" :loading="downloadingPdf" :disabled="!eod" @click="downloadEodPdf">
            🖨️ طباعة PDF
          </AppButton>
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
      </AppCard>
    </template>
  </div>
</template>
