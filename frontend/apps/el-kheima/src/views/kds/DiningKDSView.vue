<script setup lang="ts">
/**
 * DiningKDSView — first KDS screen against the unified `dining` API
 * (app/modules/dining/api/router.py::list_kitchen_tickets/update_ticket_status),
 * routed by DiningKitchenTicket.station exactly like restaurant/cafe's KDS
 * (CLAUDE.md §13 bullet ⓭: every module sharing a KDS screen must carry a
 * real station column — dining's DiningItem.station is non-nullable from
 * day one, so this never falls back to a hardcoded station).
 *
 * Deliberately unified across outlets by default (outlet_id filter is
 * optional, mirrors GET /dining/kitchen/tickets) — this is exactly the
 * "same KDS regardless of outlet" promise the dining merge exists for
 * (docstring on dining.models.DiningKDSScreen).
 *
 * Per-item bump (tap any item to confirm it individually, mirroring
 * restaurant/cafe's KitchenDisplayView — DINING_CUTOVER_PLAN.md Batch 1
 * parity gap, closed via PATCH /dining/orders/{order_id}/items/{item_id}/status)
 * alongside whole-ticket pending→in_progress→done confirmation.
 *
 * Same dark full-screen kiosk visual language as the existing kds/kitchen
 * and kds/bar screens (KitchenDisplayView.vue/BarDisplayView.vue) rather
 * than the light @resort-os/ui components — those components are styled for
 * the light back-office/POS surface; this screen intentionally matches its
 * existing sibling KDS screens' established dark aesthetic instead of
 * introducing a visual mismatch on a wall-mounted kitchen display.
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api, useResortWebSocket, parseApiTimestamp, ENDPOINTS , useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { useToast } from '@resort-os/ui'

const { t } = useI18n()
const auth = useAuthStore()
const branchId = auth.branchId
const toast = useToast()
const route = useRoute()

type TicketStatus = 'pending' | 'in_progress' | 'done'
type ItemStatus = 'pending' | 'in_kitchen' | 'ready' | 'served' | 'cancelled'
interface TicketItem { order_item_id: number; name: string; quantity: number; notes?: string | null; status?: ItemStatus }
interface Ticket {
  id: number; order_id: number; outlet_id: number; station: string
  items_snapshot: TicketItem[]; status: TicketStatus; created_at: string
  // حقول إضافية من list_kitchen_tickets المحدّث
  order_number:  string | null   // رقم الأوردر للعرض
  table_number:  string | null   // رقم الطاولة (dine_in)، null لو takeaway/delivery/room_service
  order_type:    string | null   // dine_in | takeaway | delivery | room_service
  order_notes:   string | null   // ملاحظة الأوردر الكلية
  outlet_name:   string | null   // اسم المنفذ — لو أكثر من منفذ في نفس المطبخ
}
const ITEM_DONE_STATUSES: ItemStatus[] = ['ready', 'served']

// راجع DINING_CUTOVER_PLAN.md Batch 4 — القديم كان عنده شاشتين فعليًا مركّبتين
// في أماكن مختلفة (KitchenDisplayView = hot+grill+cold+dessert مجمّعين،
// BarDisplayView = bar بس). موحّدين هنا في شاشة واحدة بمجموعات فلترة سريعة
// (بدل شاشتين منفصلتين)، زائد فلتر محطة مفردة لتحكّم أدق لو احتاجه حد.
// ?stations=hot,grill,cold,dessert في الـ URL بيحدد الفلتر الافتراضي وقت
// الفتح (راجع router/index.ts's /kds/kitchen و/kds/bar redirects) — عشان
// جهاز مثبّت فعليًا في المطبخ يفضل يفتح على تذاكر المطبخ بس زي الأول بالظبط.
// computed (مش constant) عشان يعيد الحساب لو اللغة اتغيّرت.
const stationGroups = computed<{ val: string[] | null; label: string }[]>(() => [
  { val: null, label: t('backoffice.kds.allStations') },
  { val: ['hot', 'grill', 'cold', 'dessert'], label: `🍳 ${t('backoffice.kds.kitchenGroup')}` },
  { val: ['bar'], label: `🍹 ${t('backoffice.kds.barGroup')}` },
])
const stations = computed(() => [
  { val: null, label: t('backoffice.kds.allStations') },
  { val: 'hot', label: `🔥 ${t('backoffice.kds.stations.hot')}` },
  { val: 'grill', label: `🥩 ${t('backoffice.kds.stations.grill')}` },
  { val: 'cold', label: `🥗 ${t('backoffice.kds.stations.cold')}` },
  { val: 'bar', label: `🍹 ${t('backoffice.kds.stations.bar')}` },
  { val: 'dessert', label: `🍰 ${t('backoffice.kds.stations.dessert')}` },
])

function initialStationFilter(): string[] | null {
  const q = route.query.stations
  const raw = Array.isArray(q) ? q[0] : q
  return raw ? raw.split(',').map(s => s.trim()).filter(Boolean) : null
}

const tickets = ref<Ticket[]>([])
const stationFilter = ref<string[] | null>(initialStationFilter())
const { formatTime } = useStaffFormat()
const now = ref(new Date())
const isConnected = ref(true)
let refreshInterval: ReturnType<typeof setInterval>
let clockInterval: ReturnType<typeof setInterval>

// ── صوت التنبيه للتذاكر الجديدة ─────────────────────────────────────
// نولّد صوت beep بسيط بـ Web Audio API (مش محتاج ملف صوت خارجي)
let audioCtx: AudioContext | null = null
function playNewTicketSound() {
  try {
    if (!audioCtx) audioCtx = new AudioContext()
    const osc = audioCtx.createOscillator()
    const gain = audioCtx.createGain()
    osc.connect(gain)
    gain.connect(audioCtx.destination)
    osc.type = 'sine'
    osc.frequency.setValueAtTime(880, audioCtx.currentTime)
    osc.frequency.setValueAtTime(660, audioCtx.currentTime + 0.1)
    gain.gain.setValueAtTime(0.3, audioCtx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.4)
    osc.start(audioCtx.currentTime)
    osc.stop(audioCtx.currentTime + 0.4)
  } catch { /* صامت لو المتصفح مش بيدعم AudioContext */ }
}
const soundEnabled = ref(true)
let knownTicketIds = new Set<number>()

// relative path — useResortWebSocket بيبني الـ full WS URL داخلياً
// (ws://host + path) عشان يشتغل صح مع vite proxy في dev ونginx في production
const { status: wsStatus, onMessage } = useResortWebSocket(ENDPOINTS.dining.kdsWs(branchId))
onMessage((data: any) => { if (data?.type === 'tickets_updated') fetchTickets() })

const filteredTickets = computed(() =>
  stationFilter.value ? tickets.value.filter(tk => stationFilter.value!.includes(tk.station)) : tickets.value)
function isActiveFilter(val: string[] | null) {
  if (val === null) return stationFilter.value === null
  return !!stationFilter.value && stationFilter.value.length === val.length && val.every(s => stationFilter.value!.includes(s))
}

function minutesElapsed(createdAt: string) {
  return Math.floor((now.value.getTime() - parseApiTimestamp(createdAt).getTime()) / 60000)
}
function ticketAge(createdAt: string) {
  const mins = minutesElapsed(createdAt)
  if (mins >= 15) return 'urgent'
  if (mins >= 8) return 'warning'
  return 'normal'
}
function ticketClasses(ticket: Ticket) {
  if (ticket.status === 'done') return 'border-green-500 bg-green-900/30'
  const age = ticketAge(ticket.created_at)
  if (age === 'urgent') return 'border-red-500 bg-red-900/30 animate-pulse'
  if (age === 'warning') return 'border-amber-500 bg-amber-900/30'
  return 'border-slate-600 bg-slate-800'
}
function statusLabel(status: TicketStatus) {
  if (status === 'pending') return { label: t('backoffice.kds.ticketStatus.pending'), color: 'bg-amber-500' }
  if (status === 'in_progress') return { label: t('backoffice.kds.ticketStatus.inProgress'), color: 'bg-blue-500' }
  return { label: t('backoffice.kds.ticketStatus.ready'), color: 'bg-green-500' }
}
const stationLabelFor = (station: string): string => {
  const map: Record<string, string> = {
    hot: t('backoffice.kds.stations.hot'), grill: t('backoffice.kds.stations.grill'),
    cold: t('backoffice.kds.stations.cold'), dessert: t('backoffice.kds.stations.dessert'),
    bar: t('backoffice.kds.stations.bar'),
  }
  return map[station] ?? station
}
function orderTypeLabelFor(orderType: string): string {
  const map: Record<string, string> = {
    takeaway: t('backoffice.pos.orderTypes.takeaway'),
    delivery: t('backoffice.pos.orderTypes.delivery'),
    room_service: t('backoffice.pos.orderTypes.roomService'),
  }
  return map[orderType] ?? orderType
}
function ticketTitleFor(ticket: Ticket): string {
  if (ticket.table_number) return t('backoffice.pos.tableLabel', { number: ticket.table_number })
  return ticket.order_number ?? `#${ticket.order_id}`
}

async function fetchTickets() {
  try {
    const res = await api.get(ENDPOINTS.dining.kitchenTickets, { params: { branch_id: branchId } })
    const newTickets: Ticket[] = res.data
    // تحقق من تذاكر جديدة (pending فقط) وشغّل الصوت
    if (soundEnabled.value && knownTicketIds.size > 0) {
      const hasNew = newTickets.some(tk => tk.status === 'pending' && !knownTicketIds.has(tk.id))
      if (hasNew) playNewTicketSound()
    }
    knownTicketIds = new Set(newTickets.map(tk => tk.id))
    tickets.value = newTickets
    isConnected.value = true
  } catch {
    isConnected.value = false
  }
}

// تأكيد صنف واحد جوه تذكرة — بدل الاضطرار لتأكيد التذكرة كلها حتى لو صنف
// واحد بس خلص فعليًا. تاب واحد = pending/in_kitchen→ready، تاب تاني على
// صنف جاهز بالفعل = رجوع لـ pending (تصحيح غلطة). السيرفر هو اللي بيقرر
// تلقائيًا لو التذكرة كلها بقت 'done' — راجع KitchenDisplayView.vue::bumpItem
// (نفس النمط بالظبط).
async function bumpItem(ticket: Ticket, item: TicketItem) {
  const next: ItemStatus = ITEM_DONE_STATUSES.includes(item.status ?? 'pending') ? 'pending' : 'ready'
  try {
    await api.patch(ENDPOINTS.dining.orderItemStatus(ticket.order_id, item.order_item_id), { status: next })
    await fetchTickets()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.kds.errors.updateItemStatus'))
  }
}

async function advanceStatus(ticket: Ticket) {
  const next: TicketStatus = ticket.status === 'pending' ? 'in_progress' : 'done'
  try {
    await api.patch(ENDPOINTS.dining.ticketStatus(ticket.id), { status: next })
    ticket.status = next
    if (next === 'done') {
      setTimeout(() => { tickets.value = tickets.value.filter(tk => tk.id !== ticket.id) }, 2000)
    }
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.kds.errors.updateTicketStatus'))
  }
}

const currentTime = computed(() => formatTime(now.value, { hour: '2-digit', minute: '2-digit', second: '2-digit' }))
const pendingCount = computed(() => tickets.value.filter(tk => tk.status === 'pending').length)
const inProgressCount = computed(() => tickets.value.filter(tk => tk.status === 'in_progress').length)

onMounted(() => {
  fetchTickets()
  refreshInterval = setInterval(fetchTickets, 15_000)
  clockInterval = setInterval(() => { now.value = new Date() }, 1000)
})
onUnmounted(() => { clearInterval(refreshInterval); clearInterval(clockInterval) })
</script>

<template>
  <!-- Direction inherited from <html dir> (central staff locale controller). -->
  <div class="min-h-screen bg-slate-900 text-white flex flex-col">
    <header class="bg-slate-800 border-b border-slate-700 px-6 py-3 flex items-center justify-between flex-shrink-0 flex-wrap gap-2">
      <div class="flex items-center gap-4 flex-wrap">
        <div class="flex items-center gap-2">
          <div :class="['w-2.5 h-2.5 rounded-full', isConnected ? 'bg-green-400 animate-pulse' : 'bg-red-400']" />
          <span class="text-sm text-slate-300">{{ isConnected ? t('backoffice.kds.connected') : t('backoffice.kds.disconnected') }}</span>
        </div>
        <div class="flex items-center gap-1.5" :title="wsStatus === 'connected' ? t('backoffice.kds.liveUpdatesOn') : t('backoffice.kds.reconnecting')">
          <div :class="['w-2 h-2 rounded-full', wsStatus === 'connected' ? 'bg-cyan-400' : 'bg-slate-500 animate-pulse']" />
          <span class="text-xs text-slate-400">{{ wsStatus === 'connected' ? t('backoffice.kds.live') : t('backoffice.kds.reconnectingShort') }}</span>
        </div>
        <h1 class="text-xl font-black tracking-wide">🍽️ {{ t('backoffice.kds.title') }}</h1>
        <div class="flex gap-3 text-sm">
          <span class="px-2 py-0.5 bg-amber-600 rounded-full font-bold">{{ t('backoffice.kds.ticketStatus.pending') }}: {{ pendingCount }}</span>
          <span class="px-2 py-0.5 bg-blue-600 rounded-full font-bold">{{ t('backoffice.kds.ticketStatus.inProgress') }}: {{ inProgressCount }}</span>
        </div>
      </div>
      <span class="text-2xl font-mono font-bold text-amber-300">{{ currentTime }}</span>
      <!-- زرار تشغيل/إيقاف الصوت -->
      <button @click="soundEnabled = !soundEnabled"
        :class="['px-3 py-1.5 rounded-lg text-sm font-semibold transition-colors', soundEnabled ? 'bg-slate-700 text-green-400 hover:bg-slate-600' : 'bg-slate-700 text-slate-400 hover:bg-slate-600']"
        :title="soundEnabled ? t('backoffice.kds.muteSound') : t('backoffice.kds.unmuteSound')">
        {{ soundEnabled ? '🔔' : '🔕' }}
      </button>
    </header>

    <div class="bg-slate-800 border-b border-slate-700 px-6 py-2 flex flex-wrap items-center gap-2">
      <button
        v-for="g in stationGroups"
        :key="'group-' + String(g.val)"
        type="button"
        @click="stationFilter = g.val"
        :class="[
          'px-3 py-1.5 rounded-lg text-sm font-bold transition-colors min-h-[36px]',
          isActiveFilter(g.val) ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600',
        ]"
      >{{ g.label }}</button>
      <span class="w-px h-5 bg-slate-600 mx-1" />
      <button
        v-for="s in stations.filter(s => s.val !== null)"
        :key="'single-' + s.val"
        type="button"
        @click="stationFilter = [s.val as string]"
        :class="[
          'px-2.5 py-1 rounded-lg text-xs font-medium transition-colors min-h-[32px]',
          isActiveFilter([s.val as string]) ? 'bg-blue-600/70 text-white' : 'bg-slate-700/60 text-slate-400 hover:bg-slate-600',
        ]"
      >{{ s.label }}</button>
    </div>

    <div class="flex-1 overflow-y-auto p-4">
      <div v-if="filteredTickets.length === 0" class="flex items-center justify-center h-64 text-slate-500">
        <div class="text-center">
          <div class="text-5xl mb-3">✅</div>
          <p class="text-lg">{{ t('backoffice.kds.noPendingOrders') }}</p>
        </div>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        <div v-for="ticket in filteredTickets" :key="ticket.id" :class="['rounded-2xl border-2 p-4 flex flex-col transition-all', ticketClasses(ticket)]">
          <div class="flex items-center justify-between mb-2">
            <div>
              <!-- رقم الطاولة أو نوع الأوردر — أهم معلومة للمطبخ -->
              <div class="text-2xl font-black leading-none">
                {{ ticketTitleFor(ticket) }}
              </div>
              <div class="text-xs text-slate-400 mt-0.5">
                {{ stationLabelFor(ticket.station) }}
                <span v-if="!ticket.table_number && ticket.order_type" class="ms-1 opacity-70">
                  · {{ orderTypeLabelFor(ticket.order_type) }}
                </span>
              </div>
            </div>
            <div class="text-end">
              <div class="text-xs text-slate-500 font-semibold mb-1 text-end" v-if="ticket.outlet_name">{{ ticket.outlet_name }}</div>
              <div :class="['text-xs px-2 py-0.5 rounded-full font-bold text-white mb-1', statusLabel(ticket.status).color]">{{ statusLabel(ticket.status).label }}</div>
              <div :class="[
                'text-lg font-black text-center',
                ticketAge(ticket.created_at) === 'urgent' ? 'text-red-400' : ticketAge(ticket.created_at) === 'warning' ? 'text-amber-400' : 'text-green-400',
              ]">{{ minutesElapsed(ticket.created_at) }}{{ t('backoffice.pos.elapsedUnits.minutes') }}</div>
            </div>
          </div>

          <!-- ملاحظة الأوردر الكلية — تظهر بلون واضح قبل قائمة الأصناف -->
          <div v-if="ticket.order_notes" class="mb-2 px-2 py-1.5 rounded-lg bg-amber-500/20 border border-amber-500/40 text-xs text-amber-200 font-medium">
            📋 {{ ticket.order_notes }}
          </div>

          <ul class="flex-1 space-y-1.5 mb-3">
            <li v-for="item in ticket.items_snapshot" :key="item.order_item_id" class="text-sm">
              <button
                type="button"
                @click="bumpItem(ticket, item)"
                :class="[
                  'w-full text-start rounded-lg px-1.5 py-1 flex items-start gap-2 transition-colors',
                  ITEM_DONE_STATUSES.includes(item.status ?? 'pending') ? 'bg-green-800/40' : 'hover:bg-white/10 active:bg-white/20',
                ]"
              >
                <span class="bg-white dark:bg-surface/20 text-white rounded px-1.5 py-0.5 text-xs font-bold flex-shrink-0">{{ item.quantity }}</span>
                <span :class="['leading-tight flex-1', ITEM_DONE_STATUSES.includes(item.status ?? 'pending') && 'line-through text-slate-400']">{{ item.name }}</span>
                <span v-if="ITEM_DONE_STATUSES.includes(item.status ?? 'pending')" class="text-green-400 text-xs flex-shrink-0">✓</span>
              </button>
              <p v-if="item.notes" class="text-xs text-amber-300 ms-6 mt-0.5">⚠️ {{ item.notes }}</p>
            </li>
          </ul>

          <div class="space-y-2">
            <div class="text-xs text-slate-400 text-center">
              {{ formatTime(parseApiTimestamp(ticket.created_at), { hour: '2-digit', minute: '2-digit' }) }}
            </div>
            <button
              v-if="ticket.status === 'pending'"
              type="button"
              @click="advanceStatus(ticket)"
              class="w-full py-2.5 bg-blue-600 hover:bg-blue-500 rounded-xl text-sm font-bold transition-colors active:scale-95 min-h-[48px]"
            >▶ {{ t('backoffice.kds.startPreparing') }}</button>
            <button
              v-else-if="ticket.status === 'in_progress'"
              type="button"
              @click="advanceStatus(ticket)"
              class="w-full py-2.5 bg-green-600 hover:bg-green-500 rounded-xl text-sm font-bold transition-colors active:scale-95 min-h-[48px]"
            >✓ {{ t('backoffice.kds.readyToServe') }}</button>
            <div v-else class="w-full py-2.5 bg-green-700 rounded-xl text-sm font-bold text-center text-green-200">✓ {{ t('backoffice.kds.delivered') }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
