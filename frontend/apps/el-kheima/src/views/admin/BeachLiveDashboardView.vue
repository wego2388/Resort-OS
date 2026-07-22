<script setup lang="ts">
// لوحة الشاطئ الحيّة — سعة حالية (gauge)، حصص فنادق B2B، وتنبيه تلقائي
// لما فندق يوصل لـ 5 أشخاص أو أقل متبقين في حصته اليومية.
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, useToast, useConfirm } from '@resort-os/ui'

const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const toast = useToast()
const { confirm } = useConfirm()
const auth = useAuthStore()
const branchId = auth.branchId

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
    toast.success(t('backoffice.beachLive.creditLimitUpdated', { name: c.hotel_name }))
    editingCreditId.value = null
    await load()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.beachLive.creditLimitUpdateError'))
  } finally {
    savingCredit.value = false
  }
}

async function settleContract(c: B2BStatus) {
  const ok = await confirm({
    message: t('backoffice.beachLive.settleConfirm', { name: c.hotel_name, amount: formatNumber(c.outstanding_balance) }),
    confirmText: t('backoffice.beachLive.settleConfirmYes'), cancelText: t('backoffice.beachLive.settleConfirmCancel'),
  })
  if (!ok) return
  settlingId.value = c.contract_id
  try {
    await api.post(`/api/v1/beach/b2b-contracts/${c.contract_id}/settle`, {}, { params: { branch_id: branchId } })
    toast.success(t('backoffice.beachLive.settleSuccess', { name: c.hotel_name }))
    await load()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.beachLive.settleError'))
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
    toast.error(e?.response?.data?.detail ?? t('backoffice.beachLive.eodLoadError'))
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
    toast.error(e?.response?.data?.detail ?? t('backoffice.beachLive.pdfDownloadError'))
  } finally {
    downloadingPdf.value = false
  }
}

const gaugeColor = computed(() => {
  const pct = dash.value?.capacity_pct ?? 0
  if (pct >= 90) return 'text-red-500'
  if (pct >= 80) return 'text-amber-500'
  return 'text-green-600 dark:text-green-300'
})

async function load() {
  try {
    const r = await api.get('/api/v1/beach/live-dashboard', { params: { branch_id: branchId } })
    dash.value = r.data
    if (!isConnected.value) toast.success(t('backoffice.beachLive.reconnected'))
    isConnected.value = true
  } catch (e: any) {
    // نطلّع toast مرة واحدة بس عند لحظة الانقطاع، مش كل 15 ثانية طول ما
    // الاتصال مقطوع — النقطة الحمراء في الهيدر كفاية كمؤشر مستمر.
    if (isConnected.value) toast.error(t('backoffice.beachLive.refreshError'))
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
  <div class="p-6 max-w-6xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-xl font-black text-gray-900 dark:text-gray-100">🏖️ {{ t('backoffice.beachLive.title') }}</h1>
        <div class="flex items-center gap-3 mt-1">
          <p class="text-xs text-gray-400 dark:text-gray-400">{{ t('backoffice.beachLive.autoRefreshHint') }}</p>
          <div class="flex items-center gap-1.5">
            <div :class="['w-2 h-2 rounded-full', isConnected ? 'bg-green-400 animate-pulse' : 'bg-red-400']" />
            <span :class="['text-xs font-semibold', isConnected ? 'text-green-600 dark:text-green-300' : 'text-red-500 dark:text-red-300']">
              {{ isConnected ? t('backoffice.beachLive.connected') : t('backoffice.beachLive.disconnected') }}
            </span>
          </div>
        </div>
      </div>
      <button @click="load" class="px-4 py-2 rounded-xl bg-white dark:bg-surface border border-stone-200 dark:border-border text-sm font-bold text-gray-600 dark:text-gray-400 hover:bg-stone-50 dark:bg-gray-800/60">
        🔄 {{ t('backoffice.beachLive.refresh') }}
      </button>
    </div>

    <div v-if="loading" class="flex justify-center py-20">
      <div class="w-6 h-6 border-2 border-primary-700 border-t-transparent rounded-full animate-spin"/>
    </div>

    <template v-else-if="dash">
      <!-- Quota alerts banner -->
      <div v-if="dash.quota_alerts.length" class="mb-5 space-y-2">
        <div v-for="a in dash.quota_alerts" :key="a.contract_id"
             class="flex animate-pulse items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-3 dark:border-red-800 dark:bg-red-950/40">
          <span class="text-xl">🚨</span>
          <span class="text-sm font-bold text-red-700 dark:text-red-300">
            {{ t('backoffice.beachLive.quotaAlert', { name: a.hotel_name, remaining: a.remaining_quota, quota: a.daily_quota }) }}
          </span>
        </div>
      </div>

      <!-- Overdue B2B balance alerts banner — نفس نمط quota_alerts بالظبط،
           للرصيد المستحق المتأخر عن مهلة السداد بدل الحصة اليومية. -->
      <div v-if="dash.overdue_alerts.length" class="mb-5 space-y-2">
        <div v-for="a in dash.overdue_alerts" :key="a.contract_id"
             class="flex items-center gap-3 rounded-xl border border-amber-300 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950/40">
          <span class="text-xl">💸</span>
          <span class="text-sm font-bold text-amber-800 dark:text-amber-300">
            {{ t('backoffice.beachLive.overdueAlert', { name: a.hotel_name, amount: formatNumber(a.outstanding_balance), days: a.payment_terms_days }) }}
          </span>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-5">
        <!-- Capacity gauge -->
        <AppCard padding="md" class="flex flex-col items-center justify-center">
          <p class="text-xs text-gray-400 dark:text-gray-400 font-bold uppercase tracking-wide mb-3">{{ t('backoffice.beachLive.currentCapacity') }}</p>
          <div class="relative w-32 h-32">
            <svg class="w-32 h-32 -rotate-90" viewBox="0 0 100 100">
              <circle cx="50" cy="50" r="42" fill="none" stroke="#F1F0EC" stroke-width="10" />
              <circle cx="50" cy="50" r="42" fill="none" :class="gaugeColor" stroke="currentColor"
                      stroke-width="10" stroke-linecap="round"
                      :stroke-dasharray="`${(dash.capacity_pct / 100) * 264} 264`" />
            </svg>
            <div class="absolute inset-0 flex flex-col items-center justify-center">
              <span :class="['text-2xl font-black', gaugeColor]">{{ dash.capacity_pct }}%</span>
              <span class="text-[10px] text-gray-400 dark:text-gray-400">{{ dash.capacity_used }}/{{ dash.capacity_max }}</span>
            </div>
          </div>
          <AppBadge v-if="dash.surge_active" variant="warning" size="sm" class="mt-3">
            ⚡ {{ t('backoffice.beachLive.surgeActive', { pct: dash.surge_pct }) }}
          </AppBadge>
        </AppCard>

        <!-- Towels -->
        <AppCard padding="md">
          <p class="text-xs text-gray-400 dark:text-gray-400 font-bold uppercase tracking-wide mb-3">{{ t('backoffice.beachLive.towels') }}</p>
          <p class="text-3xl font-black text-gray-900 dark:text-gray-100">{{ dash.towels_available }}</p>
          <p class="text-xs text-gray-400 dark:text-gray-400 mt-1">{{ t('backoffice.beachLive.availableOf', { total: dash.towels_available + dash.towels_used }) }}</p>
          <div class="w-full h-2 rounded-full bg-stone-100 dark:bg-gray-700 overflow-hidden mt-3">
            <div class="h-full bg-sky-400"
                 :style="{ width: `${dash.towels_used + dash.towels_available > 0 ? (dash.towels_used / (dash.towels_used + dash.towels_available)) * 100 : 0}%` }" />
          </div>
        </AppCard>

        <!-- B2B partners overview -->
        <AppCard padding="md">
          <p class="text-xs text-gray-400 dark:text-gray-400 font-bold uppercase tracking-wide mb-3">{{ t('backoffice.beachLive.activeB2BHotels') }}</p>
          <p class="text-3xl font-black text-gray-900 dark:text-gray-100">{{ dash.b2b_contracts.length }}</p>
          <p class="text-xs text-gray-400 dark:text-gray-400 mt-1">{{ t('backoffice.beachLive.alertCount', { count: dash.quota_alerts.length }) }}</p>
        </AppCard>
      </div>

      <!-- B2B partners table -->
      <AppCard padding="md">
        <p class="font-black text-sm text-gray-900 dark:text-gray-100 mb-4">🏨 {{ t('backoffice.beachLive.b2bPartnersTitle') }}</p>
        <div v-if="!dash.b2b_contracts.length" class="text-center py-6 text-gray-300 text-xs">{{ t('backoffice.beachLive.noActiveB2B') }}</div>
        <div v-else class="space-y-2">
          <div v-for="c in dash.b2b_contracts" :key="c.contract_id"
               :class="['p-3 rounded-xl border',
                        !c.is_valid_today ? 'bg-gray-100 border-gray-200 opacity-70 dark:bg-gray-800 dark:border-gray-700' :
                        c.is_overdue ? 'bg-amber-50 border-amber-300 dark:bg-amber-950/40 dark:border-amber-800' :
                        c.quota_warning ? 'bg-red-50 border-red-200' : 'bg-stone-50 dark:bg-gray-800/60 border-stone-100 dark:border-border/50']">
            <div class="flex items-center justify-between gap-3">
              <div class="flex-1 min-w-0">
                <div class="font-bold text-sm text-gray-900 dark:text-gray-100 flex items-center gap-2 flex-wrap">
                  {{ c.hotel_name }}
                  <span v-if="!c.is_valid_today"
                        class="px-1.5 py-0.5 rounded-full bg-gray-400 text-white text-[9px] font-bold">
                    {{ t('backoffice.beachLive.expiredBadge') }}
                  </span>
                  <span v-if="c.is_overdue"
                        class="px-1.5 py-0.5 rounded-full bg-amber-500 text-white text-[9px] font-bold">
                    {{ t('backoffice.beachLive.overdueBadge') }}
                  </span>
                  <span v-if="c.credit_exceeded"
                        class="px-1.5 py-0.5 rounded-full bg-red-500 text-white text-[9px] font-bold">
                    {{ t('backoffice.beachLive.creditExceededBadge') }}
                  </span>
                </div>
                <div class="text-[11px] text-gray-400 dark:text-gray-400 mt-0.5">{{ c.checked_in_today }} / {{ c.daily_quota }} {{ t('backoffice.beachLive.checkedInToday') }}</div>
              </div>
              <div class="w-32 flex-shrink-0">
                <div class="h-2 w-full overflow-hidden rounded-full bg-stone-200 dark:bg-gray-700">
                  <div :class="['h-full', !c.is_valid_today ? 'bg-gray-400' : c.is_quota_exhausted ? 'bg-red-500' : c.quota_warning ? 'bg-amber-500' : 'bg-green-500']"
                       :style="{ width: `${Math.min(100, (c.checked_in_today / c.daily_quota) * 100)}%` }" />
                </div>
              </div>
              <div class="text-end flex-shrink-0 w-20">
                <div :class="['text-sm font-black', !c.is_valid_today ? 'text-gray-400 dark:text-gray-400' : c.is_quota_exhausted ? 'text-red-500' : c.quota_warning ? 'text-amber-500' : 'text-green-600']">
                  {{ c.remaining_quota }}
                </div>
                <div class="text-[10px] text-gray-400 dark:text-gray-400">{{ t('backoffice.beachLive.remaining') }}</div>
              </div>
            </div>

            <!-- الائتمان: الرصيد المستحق + حد الائتمان (قابل للتعديل — admin
                 فقط) + زر تسوية (manager فقط). -->
            <div class="flex items-center justify-between gap-3 mt-2 pt-2 border-t border-stone-200 dark:border-border/60 text-[11px]">
              <div class="text-gray-500 dark:text-gray-400">
                {{ t('backoffice.beachLive.outstandingBalance') }}:
                <span :class="['font-bold', c.credit_exceeded ? 'text-red-600' : 'text-gray-700 dark:text-gray-300']">
                  {{ formatNumber(c.outstanding_balance) }} {{ t('backoffice.beachLive.egp') }}
                </span>
                <template v-if="editingCreditId !== c.contract_id">
                  <span class="text-gray-400 dark:text-gray-400"> / {{ t('backoffice.beachLive.limit') }}: {{ c.credit_limit !== null ? formatNumber(c.credit_limit) + ' ' + t('backoffice.beachLive.egp') : t('backoffice.beachLive.noLimit') }}</span>
                  <button v-if="auth.hasRole('admin')" @click="openCreditEdit(c)"
                          class="ms-1 text-primary-700 hover:underline">✏️ {{ t('backoffice.beachLive.edit') }}</button>
                </template>
                <span v-else class="inline-flex items-center gap-1 ms-1">
                  <input v-model="creditLimitInput" type="number" min="0" step="1" :placeholder="t('backoffice.beachLive.noLimit')"
                         class="w-24 px-1.5 py-0.5 rounded border border-stone-300 text-[11px]" />
                  <button :disabled="savingCredit" @click="saveCreditLimit(c)"
                          class="font-bold text-green-700 hover:underline dark:text-green-300">{{ t('backoffice.beachLive.save') }}</button>
                  <button :disabled="savingCredit" @click="editingCreditId = null"
                          class="text-gray-400 dark:text-gray-400 hover:underline">{{ t('backoffice.beachLive.cancel') }}</button>
                </span>
              </div>
              <AppButton v-if="auth.hasRole('manager') && c.outstanding_balance > 0"
                         variant="secondary" size="sm" :loading="settlingId === c.contract_id"
                         @click="settleContract(c)">
                💳 {{ t('backoffice.beachLive.settleBalance') }}
              </AppButton>
            </div>
          </div>
        </div>
      </AppCard>

      <!-- Daily EOD Report -->
      <AppCard padding="md" class="mt-5">
        <div class="flex items-center justify-between mb-4">
          <p class="font-black text-sm text-gray-900 dark:text-gray-100">📋 {{ t('backoffice.beachLive.eodTitle') }}</p>
          <AppButton variant="primary" size="sm" :loading="downloadingPdf" :disabled="!eod" @click="downloadEodPdf">
            🖨️ {{ t('backoffice.beachLive.printPdf') }}
          </AppButton>
        </div>

        <div v-if="eodLoading" class="text-center py-6 text-gray-300 text-xs">{{ t('backoffice.beachLive.loading') }}</div>
        <template v-else-if="eod">
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
            <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
              <p class="text-[10px] text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.beachLive.totalEntries') }}</p>
              <p class="text-lg font-black text-gray-900 dark:text-gray-100">{{ eod.total_entries }}</p>
            </div>
            <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
              <p class="text-[10px] text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.beachLive.towelRevenue') }}</p>
              <p class="text-lg font-black text-sky-600 dark:text-sky-300">{{ eod.towel_revenue }} {{ t('backoffice.beachLive.egp') }}</p>
            </div>
            <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
              <p class="text-[10px] text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.beachLive.vsYesterday') }}</p>
              <p :class="['text-lg font-black', (eod.vs_yesterday_pct ?? 0) >= 0 ? 'text-green-600 dark:text-green-300' : 'text-red-500 dark:text-red-300']">
                {{ pctLabel(eod.vs_yesterday_pct) }}
              </p>
            </div>
            <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
              <p class="text-[10px] text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.beachLive.vsLastWeek') }}</p>
              <p :class="['text-lg font-black', (eod.vs_last_week_pct ?? 0) >= 0 ? 'text-green-600 dark:text-green-300' : 'text-red-500 dark:text-red-300']">
                {{ pctLabel(eod.vs_last_week_pct) }}
              </p>
            </div>
          </div>

          <table class="w-full text-xs">
            <thead>
              <tr class="text-gray-400 dark:text-gray-400 border-b border-stone-100 dark:border-border/50">
                <th class="text-start font-bold py-2">{{ t('backoffice.beachLive.transactionType') }}</th>
                <th class="text-center font-bold py-2">{{ t('backoffice.beachLive.quantity') }}</th>
                <th class="text-end font-bold py-2">{{ t('backoffice.beachLive.total') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in eod.by_type" :key="row.tx_type" class="border-b border-stone-50">
                <td class="py-2 text-gray-800 dark:text-gray-200">{{ row.label }}</td>
                <td class="py-2 text-center text-gray-600 dark:text-gray-400">{{ row.quantity }}</td>
                <td class="py-2 text-end font-bold text-gray-900 dark:text-gray-100">{{ row.total_amount }} {{ t('backoffice.beachLive.egp') }}</td>
              </tr>
              <tr v-if="!eod.by_type.length">
                <td colspan="3" class="text-center py-6 text-gray-300">{{ t('backoffice.beachLive.noTransactionsToday') }}</td>
              </tr>
            </tbody>
          </table>
        </template>
      </AppCard>
    </template>
  </div>
</template>
