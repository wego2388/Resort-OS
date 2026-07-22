<script setup lang="ts">
/**
 * GuestAlertsBell — بيانات حية لتنبيهات الضيوف (نادِ الجرسون / هات الفاتورة)
 * في هيدر FieldLayout (يغطي /pos/* و/waiter/* — بالظبط الشاشات اللي النادل/
 * الكاشير شغالين عليها طول الوقت). قبل ده: الـ backend كان عنده قناة تنبيه
 * كاملة (POST /public/alerts + WebSocket) بس مفيش زر واحد في الفرونت إند
 * يستخدمها — نفس فئة باج "الموديل والـ API موجودين، الفرونت إند صفر".
 *
 * يستخدم:
 *   GET   /api/v1/alerts                (تحميل أولي — fallback لو الـ WS اتقطع)
 *   PATCH /api/v1/alerts/{id}/status    (تأكيد استلام / إغلاق)
 *   WS    /api/v1/ws/alerts/{branch_id} (بث لحظي — نفس نمط KDS)
 */
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore, useResortWebSocket, ENDPOINTS } from '@resort-os/core'
import { AppBadge, useToast } from '@resort-os/ui'

const auth = useAuthStore()
const toast = useToast()
const { t } = useI18n()
const branchId = computed(() => auth.branchId ?? 1)

interface GuestAlert {
  id: number
  context_type: string
  context_id: number
  alert_type: string
  message: string | null
  status: 'open' | 'acknowledged' | 'resolved'
  created_at: string
}

const alerts = ref<GuestAlert[]>([])
const panelOpen = ref(false)
const updatingId = ref<number | null>(null)

// dining_table (DINING_CUTOVER_PLAN.md Batch 6) هو context_type الوحيد
// المُصدَر دلوقتي من apps/public's OrderView.vue — restaurant_table/
// cafe_table باقيين هنا بس عشان أي تنبيه تاريخي قديم لسه في الداتابيز
// يفضل يترجم صح، مش لأنهم بيتصدروا تاني.
const CONTEXT_KEY: Record<string, string> = {
  dining_table: 'diningTable',
  restaurant_table: 'restaurantTable',
  cafe_table: 'cafeTable',
  beach_location: 'beachLocation',
  room: 'room',
  other: 'other',
}

const ALERT_UI: Record<string, { icon: string; key: string }> = {
  call_waiter: { icon: '🧑‍🍳', key: 'callWaiter' },
  request_bill: { icon: '🧾', key: 'requestBill' },
  other: { icon: '❗', key: 'other' },
}

function contextLabel(a: GuestAlert) {
  const key = CONTEXT_KEY[a.context_type]
  const label = key ? t(`backoffice.guestAlerts.context.${key}`) : a.context_type
  return `${label} #${a.context_id}`
}

function alertUi(a: GuestAlert) {
  const value = ALERT_UI[a.alert_type] ?? ALERT_UI.other
  return { icon: value.icon, label: t(`backoffice.guestAlerts.type.${value.key}`) }
}

function timeAgo(iso: string) {
  const mins = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000))
  if (mins < 1) return t('backoffice.guestAlerts.now')
  if (mins < 60) return t('backoffice.guestAlerts.minutesAgo', { count: mins })
  return t('backoffice.guestAlerts.hoursAgo', { count: Math.floor(mins / 60) })
}

async function fetchAlerts() {
  try {
    const { data } = await api.get(ENDPOINTS.core.alerts, { params: { branch_id: branchId.value, size: 50 } })
    alerts.value = data.items ?? []
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.guestAlerts.loadFailed'))
  }
}

async function setStatus(alert: GuestAlert, status: 'acknowledged' | 'resolved') {
  updatingId.value = alert.id
  try {
    const { data } = await api.patch(ENDPOINTS.core.alertStatus(alert.id), { status })
    if (status === 'resolved') {
      alerts.value = alerts.value.filter(a => a.id !== alert.id)
      toast.success(t('backoffice.guestAlerts.resolvedSuccess'))
    } else {
      const idx = alerts.value.findIndex(a => a.id === alert.id)
      if (idx >= 0) alerts.value[idx] = data
    }
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.guestAlerts.updateFailed'))
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
    toast.info(`${alertUi(data.alert).icon} ${alertUi(data.alert).label} — ${contextLabel(data.alert)}`)
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

onMounted(fetchAlerts)
</script>

<template>
  <div class="relative">
    <button
      type="button"
      :aria-label="t('backoffice.guestAlerts.buttonLabel', { count: alerts.length })"
      :aria-expanded="panelOpen"
      aria-haspopup="dialog"
      @click="panelOpen = !panelOpen"
      class="relative flex h-11 w-11 items-center justify-center rounded-xl text-gray-700 transition-colors hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-800"
      :title="t('backoffice.guestAlerts.buttonLabel', { count: alerts.length })"
    >
      <span class="text-lg" :class="alerts.length ? 'animate-pulse' : ''">🔔</span>
      <span
        v-if="alerts.length > 0"
        class="absolute -start-0.5 -top-0.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-black text-white"
      >{{ alerts.length }}</span>
    </button>

    <Teleport to="body">
      <div v-if="panelOpen" class="fixed inset-0 z-40" @click="panelOpen = false" />
      <div
        v-if="panelOpen"
        class="fixed inset-x-2 top-14 z-50 flex max-h-[70vh] w-auto flex-col rounded-2xl border border-stone-200 bg-white shadow-xl dark:border-gray-700 dark:bg-gray-900 sm:absolute sm:inset-x-auto sm:end-0 sm:top-auto sm:mt-2 sm:w-80"
        role="dialog"
        :aria-label="t('backoffice.guestAlerts.title')"
      >
        <div class="flex items-center justify-between border-b border-stone-100 px-4 py-3 font-bold text-gray-900 dark:border-gray-700 dark:text-gray-100">
          <span>{{ t('backoffice.guestAlerts.title') }}</span>
          <AppBadge v-if="alerts.length" variant="danger" size="sm">{{ alerts.length }}</AppBadge>
        </div>

        <div class="overflow-y-auto flex-1">
          <div v-if="alerts.length === 0" class="py-10 text-center text-sm text-gray-500 dark:text-gray-400">
            {{ t('backoffice.guestAlerts.empty') }} 👍
          </div>
          <div
            v-for="a in alerts" :key="a.id"
            class="flex items-start gap-2.5 border-b border-stone-100 px-4 py-3 dark:border-gray-800"
          >
            <span class="text-xl flex-shrink-0">{{ alertUi(a).icon }}</span>
            <div class="flex-1 min-w-0">
              <div class="text-sm font-semibold text-gray-900 dark:text-gray-100">{{ alertUi(a).label }}</div>
              <div class="text-xs text-gray-500 dark:text-gray-400">{{ contextLabel(a) }} · {{ timeAgo(a.created_at) }}</div>
              <div v-if="a.message" class="mt-0.5 text-xs italic text-gray-600 dark:text-gray-300">“{{ a.message }}”</div>
              <div class="flex gap-1.5 mt-1.5">
                <button
                  v-if="a.status === 'open'"
                  :disabled="updatingId === a.id"
                  @click="setStatus(a, 'acknowledged')"
                  class="min-h-11 rounded-xl bg-amber-50 px-3 py-2 text-xs font-bold text-amber-700 disabled:opacity-50 dark:bg-amber-950/40 dark:text-amber-300"
                >{{ t('backoffice.guestAlerts.acknowledge') }}</button>
                <button
                  :disabled="updatingId === a.id"
                  @click="setStatus(a, 'resolved')"
                  class="min-h-11 rounded-xl bg-green-50 px-3 py-2 text-xs font-bold text-green-700 disabled:opacity-50 dark:bg-green-950/40 dark:text-green-300"
                >{{ t('backoffice.guestAlerts.resolve') }} ✓</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
