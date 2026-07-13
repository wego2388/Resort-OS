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
import { api, useAuthStore, useResortWebSocket, ENDPOINTS } from '@resort-os/core'
import { AppBadge, useToast } from '@resort-os/ui'

const auth = useAuthStore()
const toast = useToast()
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
const CONTEXT_LABEL: Record<string, string> = {
  dining_table:      'طاولة',
  restaurant_table:  'طاولة مطعم',
  cafe_table:        'طاولة كافيه',
  beach_location:    'موقع شاطئ',
  room:               'غرفة',
  other:              'أخرى',
}

const ALERT_UI: Record<string, { icon: string; label: string }> = {
  call_waiter:  { icon: '🧑‍🍳', label: 'نداء جرسون' },
  request_bill: { icon: '🧾', label: 'طلب فاتورة' },
  other:        { icon: '❗', label: 'طلب آخر' },
}

function contextLabel(a: GuestAlert) {
  return `${CONTEXT_LABEL[a.context_type] ?? a.context_type} #${a.context_id}`
}

function alertUi(a: GuestAlert) {
  return ALERT_UI[a.alert_type] ?? ALERT_UI.other
}

function timeAgo(iso: string) {
  const mins = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000))
  if (mins < 1) return 'الآن'
  if (mins < 60) return `منذ ${mins} د`
  return `منذ ${Math.floor(mins / 60)} س`
}

async function fetchAlerts() {
  try {
    const { data } = await api.get(ENDPOINTS.core.alerts, { params: { branch_id: branchId.value, size: 50 } })
    alerts.value = data.items ?? []
  } catch (e) {
    console.error('Failed to load guest alerts', e)
  }
}

async function setStatus(alert: GuestAlert, status: 'acknowledged' | 'resolved') {
  updatingId.value = alert.id
  try {
    const { data } = await api.patch(ENDPOINTS.core.alertStatus(alert.id), { status })
    if (status === 'resolved') {
      alerts.value = alerts.value.filter(a => a.id !== alert.id)
      toast.success('تم إغلاق التنبيه')
    } else {
      const idx = alerts.value.findIndex(a => a.id === alert.id)
      if (idx >= 0) alerts.value[idx] = data
    }
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تحديث التنبيه')
  } finally {
    updatingId.value = null
  }
}

// اتصال لحظي — نفس نمط KDS (useResortWebSocket بيعيد الاتصال تلقائيًا لو
// النت اتقطع)، الـ GET أعلاه fallback للتحميل الأولي بس.
// wsBase: نحترم X-Forwarded-Proto لو الـ reverse proxy بيمرّره (production)،
// وإلا نستنتج من location.protocol — بدل location.host المباشر اللي ممكن
// يكسر وراء nginx لو الـ WebSocket path مختلف عن HTTP path.
const wsProtocol = (
  window.location.protocol === 'https:' ||
  document.querySelector('meta[name="x-forwarded-proto"]')?.getAttribute('content') === 'https'
) ? 'wss:' : 'ws:'
const wsBase = import.meta.env.VITE_WS_BASE ?? `${wsProtocol}//${window.location.host}`
const { onMessage } = useResortWebSocket(
  `${wsBase}/api/v1/ws/alerts/${branchId.value}`,
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
      @click="panelOpen = !panelOpen"
      class="relative w-9 h-9 flex items-center justify-center rounded-full hover:bg-gray-100 transition-colors"
      :title="alerts.length ? `${alerts.length} تنبيه من الضيوف` : 'تنبيهات الضيوف'"
    >
      <span class="text-lg" :class="alerts.length ? 'animate-pulse' : ''">🔔</span>
      <span
        v-if="alerts.length > 0"
        class="absolute -top-0.5 -left-0.5 min-w-[18px] h-[18px] px-1 bg-red-500 rounded-full text-white text-[10px] font-black flex items-center justify-center"
      >{{ alerts.length }}</span>
    </button>

    <Teleport to="body">
      <div v-if="panelOpen" class="fixed inset-0 z-40" @click="panelOpen = false" />
      <div
        v-if="panelOpen"
        class="fixed sm:absolute left-2 right-2 sm:left-auto sm:right-0 top-14 sm:top-auto sm:mt-2 w-auto sm:w-80 bg-white rounded-2xl shadow-xl border border-stone-200 z-50 max-h-[70vh] flex flex-col"
        dir="rtl"
      >
        <div class="px-4 py-3 border-b border-stone-100 font-bold text-gray-900 flex items-center justify-between">
          <span>تنبيهات الضيوف</span>
          <AppBadge v-if="alerts.length" variant="danger" size="sm">{{ alerts.length }}</AppBadge>
        </div>

        <div class="overflow-y-auto flex-1">
          <div v-if="alerts.length === 0" class="text-center text-gray-400 text-sm py-10">
            لا توجد تنبيهات حالياً 👍
          </div>
          <div
            v-for="a in alerts" :key="a.id"
            class="px-4 py-3 border-b border-stone-50 flex items-start gap-2.5"
          >
            <span class="text-xl flex-shrink-0">{{ alertUi(a).icon }}</span>
            <div class="flex-1 min-w-0">
              <div class="font-semibold text-sm text-gray-900">{{ alertUi(a).label }}</div>
              <div class="text-xs text-gray-500">{{ contextLabel(a) }} · {{ timeAgo(a.created_at) }}</div>
              <div v-if="a.message" class="text-xs text-gray-600 mt-0.5 italic">"{{ a.message }}"</div>
              <div class="flex gap-1.5 mt-1.5">
                <button
                  v-if="a.status === 'open'"
                  :disabled="updatingId === a.id"
                  @click="setStatus(a, 'acknowledged')"
                  class="text-xs font-bold text-amber-700 bg-amber-50 px-2 py-1 rounded-lg disabled:opacity-50"
                >قيد المتابعة</button>
                <button
                  :disabled="updatingId === a.id"
                  @click="setStatus(a, 'resolved')"
                  class="text-xs font-bold text-green-700 bg-green-50 px-2 py-1 rounded-lg disabled:opacity-50"
                >تم ✓</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
