<script setup lang="ts">
/**
 * ShiftMonitorView — /pos/shift-monitor
 * مراقبة لحظية للورديات المفتوحة — مدير+ فقط (level ≥ 60).
 *
 * المصدر: GET /finance/shifts/active (snapshot) +
 *         WS /finance/ws/shifts/{branchId} (إشارة تحديث فوري).
 * عند وصول حدث WS (shift_opened / shift_closed / shift_sale)
 * يُعيد تحميل الـ snapshot تلقائياً.
 * Fallback: polling كل 30 ثانية لو WS اتقطع.
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore, ENDPOINTS } from '@resort-os/core'
import { AppButton, AppCard, AppBadge, EmptyState, LoadingState, useToast } from '@resort-os/ui'
import { useStaffFormat } from '@resort-os/core/i18n/staff'

const auth  = useAuthStore()
const toast = useToast()
const { t }  = useI18n()
const { formatMoney, formatTime, formatDateTime } = useStaffFormat()

const branchId = computed(() => auth.branchId ?? 1)

// ── Data ──────────────────────────────────────────────────────────────
interface ShiftSummary {
  shift_id:      number
  cashier_id:    number
  cashier_name:  string
  opened_at:     string
  opening_float: number | string
  total_sales:   number | string
  total_cash:    number | string
  total_card:    number | string
  expected_cash: number | string
  invoice_count: number
}

interface ActiveShiftsResponse {
  branch_id:   number
  shift_count: number
  shifts:      ShiftSummary[]
  as_of:       string
}

const data      = ref<ActiveShiftsResponse | null>(null)
const loading   = ref(false)
const lastError = ref<string | null>(null)

async function fetchActiveShifts() {
  loading.value = true
  lastError.value = null
  try {
    const res = await api.get(ENDPOINTS.finance.shiftsActive, {
      params: { branch_id: branchId.value },
    })
    data.value = res.data
  } catch (e: any) {
    const msg = e?.response?.data?.detail ?? t('shiftMonitor.loadError')
    lastError.value = msg
    toast.error(msg)
  } finally {
    loading.value = false
  }
}

// ── مدّة الوردية ──────────────────────────────────────────────────────
function shiftDuration(openedAt: string): string {
  const diffMs = Date.now() - new Date(openedAt).getTime()
  const h = Math.floor(diffMs / 3_600_000)
  const m = Math.floor((diffMs % 3_600_000) / 60_000)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

function num(v: number | string): number {
  return Number(v) || 0
}

// ── WebSocket ─────────────────────────────────────────────────────────
let ws: WebSocket | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
const wsConnected = ref(false)

function connectWs() {
  if (ws) { ws.onclose = null; ws.close() }
  const token = auth.token
  if (!token) return

  const proto  = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const wsUrl  = `${proto}://${window.location.host}${ENDPOINTS.finance.shiftsWs(branchId.value)}?token=${token}`
  ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    wsConnected.value = true
    // نوقف الـ polling لما WS يشتغل
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      // shift_opened أو shift_closed أو shift_sale → نعيد تحميل الـ snapshot
      if (msg.type && msg.type !== 'pong') {
        fetchActiveShifts()
      }
    } catch { /* ignore malformed */ }
  }

  ws.onclose = () => {
    wsConnected.value = false
    // نرجع للـ polling كـ fallback + نحاول إعادة الاتصال بعد 10 ث
    startPolling()
    reconnectTimer = setTimeout(connectWs, 10_000)
  }

  ws.onerror = () => {
    ws?.close()
  }
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(fetchActiveShifts, 30_000)
}

onMounted(async () => {
  await fetchActiveShifts()
  connectWs()
})

onUnmounted(() => {
  if (ws) { ws.onclose = null; ws.close(); ws = null }
  if (pollTimer) clearInterval(pollTimer)
  if (reconnectTimer) clearTimeout(reconnectTimer)
})
</script>

<template>
  <div class="page-container">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4 gap-2 flex-wrap">
      <div class="flex items-center gap-2">
        <h1 class="section-title mb-0">{{ t('shiftMonitor.title') }}</h1>
        <!-- مؤشر اتصال WS -->
        <span
          :class="wsConnected
            ? 'bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-300'
            : 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'"
          class="text-xs font-bold px-2 py-0.5 rounded-full"
        >
          {{ wsConnected ? '🟢 ' + t('shiftMonitor.live') : '🟡 ' + t('shiftMonitor.polling') }}
        </span>
      </div>
      <div class="flex items-center gap-2">
        <span v-if="data" class="text-xs text-gray-400">
          {{ t('shiftMonitor.asOf') }}: {{ formatDateTime(data.as_of) }}
        </span>
        <AppButton variant="outline" size="sm" :loading="loading" @click="fetchActiveShifts">
          🔄 {{ t('shiftMonitor.refresh') }}
        </AppButton>
      </div>
    </div>

    <!-- Loading -->
    <LoadingState v-if="loading && !data" :label="t('shiftMonitor.loading')" />

    <!-- Empty -->
    <EmptyState
      v-else-if="!loading && data && data.shift_count === 0"
      icon="🔒"
      :title="t('shiftMonitor.noShifts')"
      :subtitle="t('shiftMonitor.noShiftsHint')"
    />

    <!-- Error -->
    <div
      v-else-if="lastError && !data"
      class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300"
    >
      ⚠️ {{ lastError }}
    </div>

    <!-- الورديات -->
    <template v-else-if="data">
      <!-- ملخص سريع -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <AppCard padding="sm" class="text-center">
          <p class="text-2xl font-black text-gray-800 dark:text-gray-100">{{ data.shift_count }}</p>
          <p class="text-xs text-gray-500 mt-0.5">{{ t('shiftMonitor.openShifts') }}</p>
        </AppCard>
        <AppCard padding="sm" class="text-center">
          <p class="text-2xl font-black text-emerald-600 dark:text-emerald-300">
            {{ formatMoney(data.shifts.reduce((s, r) => s + num(r.total_sales), 0), 'EGP') }}
          </p>
          <p class="text-xs text-gray-500 mt-0.5">{{ t('shiftMonitor.totalSales') }}</p>
        </AppCard>
        <AppCard padding="sm" class="text-center">
          <p class="text-2xl font-black text-blue-600 dark:text-blue-300">
            {{ formatMoney(data.shifts.reduce((s, r) => s + num(r.total_cash), 0), 'EGP') }}
          </p>
          <p class="text-xs text-gray-500 mt-0.5">{{ t('shiftMonitor.totalCash') }}</p>
        </AppCard>
        <AppCard padding="sm" class="text-center">
          <p class="text-2xl font-black text-purple-600 dark:text-purple-300">
            {{ data.shifts.reduce((s, r) => s + r.invoice_count, 0) }}
          </p>
          <p class="text-xs text-gray-500 mt-0.5">{{ t('shiftMonitor.totalInvoices') }}</p>
        </AppCard>
      </div>

      <!-- جدول الورديات — desktop -->
      <AppCard class="hidden sm:block overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-xs text-gray-400 border-b border-stone-100 dark:border-stone-800">
              <th class="text-right py-2 px-3 font-medium">{{ t('shiftMonitor.col.cashier') }}</th>
              <th class="text-right py-2 px-3 font-medium">{{ t('shiftMonitor.col.openedAt') }}</th>
              <th class="text-right py-2 px-3 font-medium">{{ t('shiftMonitor.col.duration') }}</th>
              <th class="text-right py-2 px-3 font-medium">{{ t('shiftMonitor.col.sales') }}</th>
              <th class="text-right py-2 px-3 font-medium">{{ t('shiftMonitor.col.cash') }}</th>
              <th class="text-right py-2 px-3 font-medium">{{ t('shiftMonitor.col.card') }}</th>
              <th class="text-right py-2 px-3 font-medium">{{ t('shiftMonitor.col.expectedCash') }}</th>
              <th class="text-right py-2 px-3 font-medium">{{ t('shiftMonitor.col.invoices') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="s in data.shifts"
              :key="s.shift_id"
              class="border-t border-stone-100 dark:border-stone-800 hover:bg-gray-50 dark:hover:bg-gray-800/40 transition-colors"
            >
              <td class="py-2.5 px-3">
                <div class="font-semibold text-gray-800 dark:text-gray-200">{{ s.cashier_name }}</div>
                <div class="text-xs text-gray-400">#{{ s.shift_id }}</div>
              </td>
              <td class="py-2.5 px-3 text-gray-600 dark:text-gray-300">{{ formatTime(s.opened_at) }}</td>
              <td class="py-2.5 px-3">
                <span class="font-mono text-xs bg-gray-100 dark:bg-gray-800 rounded px-1.5 py-0.5">
                  {{ shiftDuration(s.opened_at) }}
                </span>
              </td>
              <td class="py-2.5 px-3 font-semibold text-emerald-700 dark:text-emerald-300">
                {{ formatMoney(num(s.total_sales), 'EGP') }}
              </td>
              <td class="py-2.5 px-3 text-blue-700 dark:text-blue-300">
                {{ formatMoney(num(s.total_cash), 'EGP') }}
              </td>
              <td class="py-2.5 px-3 text-purple-700 dark:text-purple-300">
                {{ formatMoney(num(s.total_card), 'EGP') }}
              </td>
              <td class="py-2.5 px-3 text-gray-700 dark:text-gray-300">
                {{ formatMoney(num(s.expected_cash), 'EGP') }}
              </td>
              <td class="py-2.5 px-3">
                <AppBadge variant="info">{{ s.invoice_count }}</AppBadge>
              </td>
            </tr>
          </tbody>
        </table>
      </AppCard>

      <!-- بطاقات — mobile -->
      <div class="sm:hidden space-y-3">
        <AppCard
          v-for="s in data.shifts"
          :key="s.shift_id"
          padding="sm"
        >
          <div class="flex items-start justify-between mb-2">
            <div>
              <p class="font-bold text-gray-800 dark:text-gray-200">{{ s.cashier_name }}</p>
              <p class="text-xs text-gray-400">{{ t('shiftMonitor.shiftHash', { id: s.shift_id }) }} · {{ formatTime(s.opened_at) }}</p>
            </div>
            <span class="font-mono text-xs bg-gray-100 dark:bg-gray-800 rounded px-2 py-0.5">
              ⏱ {{ shiftDuration(s.opened_at) }}
            </span>
          </div>
          <div class="grid grid-cols-2 gap-2 text-sm">
            <div class="rounded bg-emerald-50 dark:bg-emerald-950/30 px-2 py-1.5">
              <p class="text-xs text-gray-500">{{ t('shiftMonitor.col.sales') }}</p>
              <p class="font-bold text-emerald-700 dark:text-emerald-300">{{ formatMoney(num(s.total_sales), 'EGP') }}</p>
            </div>
            <div class="rounded bg-blue-50 dark:bg-blue-950/30 px-2 py-1.5">
              <p class="text-xs text-gray-500">{{ t('shiftMonitor.col.cash') }}</p>
              <p class="font-bold text-blue-700 dark:text-blue-300">{{ formatMoney(num(s.total_cash), 'EGP') }}</p>
            </div>
            <div class="rounded bg-purple-50 dark:bg-purple-950/30 px-2 py-1.5">
              <p class="text-xs text-gray-500">{{ t('shiftMonitor.col.card') }}</p>
              <p class="font-bold text-purple-700 dark:text-purple-300">{{ formatMoney(num(s.total_card), 'EGP') }}</p>
            </div>
            <div class="rounded bg-gray-50 dark:bg-gray-800/50 px-2 py-1.5">
              <p class="text-xs text-gray-500">{{ t('shiftMonitor.col.invoices') }}</p>
              <p class="font-bold text-gray-700 dark:text-gray-300">{{ s.invoice_count }}</p>
            </div>
          </div>
        </AppCard>
      </div>
    </template>
  </div>
</template>
