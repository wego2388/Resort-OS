<script setup lang="ts">
/**
 * GuestAlertsBell — طابور حي لطلبات الضيوف الأربعة في Gate 8
 * في هيدر FieldLayout (يغطي /pos/* و/waiter/* — بالظبط الشاشات اللي النادل/
 * الكاشير شغالين عليها طول الوقت). الـWebSocket هو المسار السريع، مع polling
 * دوري حتى لا يضيع تحديث لو انقطع الاتصال أو أُغلق طلب فاتورة أثناء الدفع.
 *
 * يستخدم:
 *   GET   /api/v1/alerts                (تحميل أولي + polling fallback)
 *   PATCH /api/v1/alerts/{id}/status    (استلام / وصول / إغلاق)
 *   WS    /api/v1/ws/alerts/{branch_id} (بث لحظي — نفس نمط KDS)
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore, useResortWebSocket, ENDPOINTS } from '@resort-os/core'
import { AppBadge, useToast } from '@resort-os/ui'

const auth = useAuthStore()
const toast = useToast()
const { locale, t } = useI18n()
const branchId = computed(() => auth.branchId ?? 0)

interface GuestAlert {
  id: number
  context_type: string
  context_id: number
  location_label: string | null
  outlet_name: string | null
  outlet_name_ar: string | null
  alert_type: string
  message: string | null
  status: 'open' | 'acknowledged' | 'arrived' | 'resolved'
  assigned_to: number | null
  created_at: string
}

const alerts = ref<GuestAlert[]>([])
const panelOpen = ref(false)
const updatingId = ref<number | null>(null)

// dining_table (DINING_CUTOVER_PLAN.md Batch 6) هو context_type الوحيد
// المُصدَر دلوقتي من apps/public's OrderView.vue — restaurant_table/
// cafe_table باقيين هنا بس عشان أي تنبيه تاريخي قديم لسه في الداتابيز
// يفضل يترجم صح، مش لأنهم بيتصدروا تاني.
const ALERT_UI: Record<string, { icon: string; key: string }> = {
  call_waiter:   { icon: '🧑‍🍳', key: 'callWaiter' },
  ready_to_order:{ icon: '🍽️', key: 'readyToOrder' },
  assistance:    { icon: '🙋', key: 'assistance' },
  request_bill:  { icon: '🧾', key: 'requestBill' },
  other:         { icon: '❗', key: 'other' },
}

function contextLabel(a: GuestAlert) {
  const outlet = locale.value === 'ar' ? (a.outlet_name_ar ?? a.outlet_name) : a.outlet_name
  return [a.location_label ?? a.context_type, outlet].filter(Boolean).join(' · ')
}

function alertUi(a: GuestAlert) {
  return ALERT_UI[a.alert_type] ?? ALERT_UI.other
}

function alertLabel(a: GuestAlert) {
  return t(`backoffice.guestAlerts.types.${alertUi(a).key}`)
}

function timeAgo(iso: string) {
  const mins = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000))
  if (mins < 1) return t('backoffice.guestAlerts.now')
  if (mins < 60) return t('backoffice.guestAlerts.minutesAgo', { count: mins })
  return t('backoffice.guestAlerts.hoursAgo', { count: Math.floor(mins / 60) })
}

async function fetchAlerts() {
  if (!branchId.value) return
  try {
    const { data } = await api.get(ENDPOINTS.core.alerts, { params: { branch_id: branchId.value, size: 50 } })
    alerts.value = data.items ?? []
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.guestAlerts.loadError'))
  }
}

async function setStatus(alert: GuestAlert, status: 'acknowledged' | 'arrived' | 'resolved') {
  updatingId.value = alert.id
  try {
    const { data } = await api.patch(ENDPOINTS.core.alertStatus(alert.id), { status })
    if (status === 'resolved') {
      alerts.value = alerts.value.filter(a => a.id !== alert.id)
      toast.success(t('backoffice.guestAlerts.closed'))
    } else {
      const idx = alerts.value.findIndex(a => a.id === alert.id)
      if (idx >= 0) alerts.value[idx] = data
    }
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.guestAlerts.updateError'))
  } finally {
    updatingId.value = null
  }
}

// اتصال لحظي — نفس نمط KDS (useResortWebSocket بيعيد الاتصال تلقائيًا لو
// النت اتقطع)، الـ GET أعلاه fallback للتحميل الأولي بس.
// الـ URL بيييجي من ENDPOINTS.core.alertsWs — نفس الـ /api prefix اللي
// الـ vite proxy (ws: true) بيعمله forward للباك إند تلقائياً.
const { onMessage } = useResortWebSocket(
  ENDPOINTS.core.alertsWs(branchId.value),
)
onMessage((data: any) => {
  if (data?.type === 'new_alert') {
    alerts.value.unshift(data.alert)
    toast.info(`${alertUi(data.alert).icon} ${alertLabel(data.alert)} — ${contextLabel(data.alert)}`)
  } else if (data?.type === 'alert_status_changed') {
    const a = data.alert as GuestAlert
    if (a.status === 'resolved') {
      alerts.value = alerts.value.filter(x => x.id !== a.id)
    } else {
      const idx = alerts.value.findIndex(x => x.id === a.id)
      if (idx >= 0) alerts.value[idx] = a
    }
  }
})

let fallbackTimer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  fetchAlerts()
  fallbackTimer = setInterval(fetchAlerts, 20_000)
})
onUnmounted(() => {
  if (fallbackTimer) clearInterval(fallbackTimer)
})
</script>

<template>
  <div class="relative">
    <button
      type="button"
      :aria-label="t('backoffice.guestAlerts.titleCount', { count: alerts.length })"
      :aria-expanded="panelOpen"
      aria-haspopup="dialog"
      @click="panelOpen = !panelOpen"
      class="relative flex h-11 w-11 items-center justify-center rounded-xl text-gray-700 transition-colors hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-800"
      :title="t('backoffice.guestAlerts.titleCount', { count: alerts.length })"
    >
      <span class="text-lg" :class="alerts.length ? 'animate-pulse' : ''">🔔</span>
      <span
        v-if="alerts.length > 0"
        class="absolute -top-0.5 -start-0.5 min-w-[18px] h-[18px] px-1 bg-red-500 rounded-full text-white text-[10px] font-black flex items-center justify-center"
      >{{ alerts.length }}</span>
    </button>

    <Teleport to="body">
      <div v-if="panelOpen" class="fixed inset-0 z-40" @click="panelOpen = false" />
      <div
        v-if="panelOpen"
        class="fixed sm:absolute inset-x-2 sm:inset-x-auto sm:end-0 top-14 sm:top-auto sm:mt-2 w-auto sm:w-80 bg-white rounded-2xl shadow-xl border border-stone-200 z-50 max-h-[70vh] flex flex-col dark:border-gray-700 dark:bg-gray-900"
        :dir="locale === 'ar' ? 'rtl' : 'ltr'"
        role="dialog"
        :aria-label="t('backoffice.guestAlerts.title')"
      >
        <div class="px-4 py-3 border-b border-stone-100 font-bold text-gray-900 flex items-center justify-between dark:border-gray-700 dark:text-gray-100">
          <span>{{ t('backoffice.guestAlerts.title') }}</span>
          <AppBadge v-if="alerts.length" variant="danger" size="sm">{{ alerts.length }}</AppBadge>
        </div>

        <div class="overflow-y-auto flex-1">
          <div v-if="alerts.length === 0" class="text-center text-gray-500 text-sm py-10 dark:text-gray-400">
            {{ t('backoffice.guestAlerts.empty') }} 👍
          </div>
          <div
            v-for="a in alerts" :key="a.id"
            class="px-4 py-3 border-b border-stone-100 flex items-start gap-2.5 dark:border-gray-800"
          >
            <span class="text-xl flex-shrink-0">{{ alertUi(a).icon }}</span>
            <div class="flex-1 min-w-0">
              <div class="font-semibold text-sm text-gray-900 dark:text-gray-100">{{ alertLabel(a) }}</div>
              <div class="text-xs text-gray-500 dark:text-gray-400">{{ contextLabel(a) }} · {{ timeAgo(a.created_at) }}</div>
              <div v-if="a.message" class="text-xs text-gray-600 mt-0.5 italic dark:text-gray-300">"{{ a.message }}"</div>
              <div class="flex gap-1.5 mt-1.5">
                <button
                  type="button"
                  v-if="a.status === 'open'"
                  :disabled="updatingId === a.id"
                  @click="setStatus(a, 'acknowledged')"
                  class="min-h-11 rounded-xl bg-amber-50 px-3 py-2 text-xs font-bold text-amber-700 disabled:opacity-50 dark:bg-amber-950/40 dark:text-amber-300"
                >{{ t('backoffice.guestAlerts.acknowledge') }}</button>
                <button
                  type="button"
                  v-if="a.status === 'acknowledged'"
                  :disabled="updatingId === a.id"
                  @click="setStatus(a, 'arrived')"
                  class="min-h-11 rounded-xl bg-blue-50 px-3 py-2 text-xs font-bold text-blue-700 disabled:opacity-50 dark:bg-blue-950/40 dark:text-blue-300"
                >{{ t('backoffice.guestAlerts.arrived') }}</button>
                <button
                  type="button"
                  :disabled="updatingId === a.id"
                  @click="setStatus(a, 'resolved')"
                  class="min-h-11 rounded-xl bg-green-50 px-3 py-2 text-xs font-bold text-green-700 disabled:opacity-50 dark:bg-green-950/40 dark:text-green-300"
                >{{ t('backoffice.guestAlerts.done') }} ✓</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
