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
 * Deliberately deferred for this pass: per-item bump (dining's router has
 * no PATCH .../items/{id}/status endpoint yet, unlike restaurant/cafe's
 * KitchenDisplayView — only whole-ticket pending→in_progress→done is
 * available today). Adding item-level status is a real, scoped backend gap
 * for a later pass, not something silently faked here.
 *
 * Same dark full-screen kiosk visual language as the existing kds/kitchen
 * and kds/bar screens (KitchenDisplayView.vue/BarDisplayView.vue) rather
 * than the light @resort-os/ui components — those components are styled for
 * the light back-office/POS surface; this screen intentionally matches its
 * existing sibling KDS screens' established dark aesthetic instead of
 * introducing a visual mismatch on a wall-mounted kitchen display.
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, useResortWebSocket, parseApiTimestamp, ENDPOINTS } from '@resort-os/core'
import { useToast } from '@resort-os/ui'

const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')
const toast = useToast()

type TicketStatus = 'pending' | 'in_progress' | 'done'
interface TicketItem { order_item_id: number; name: string; quantity: number; notes?: string | null }
interface Ticket {
  id: number; order_id: number; outlet_id: number; station: string
  items_snapshot: TicketItem[]; status: TicketStatus; created_at: string
}

const STATIONS = [
  { val: null, label: 'كل المحطات' },
  { val: 'hot', label: '🔥 ساخن' },
  { val: 'grill', label: '🥩 شواية' },
  { val: 'cold', label: '🥗 بارد' },
  { val: 'bar', label: '🍹 بار' },
  { val: 'dessert', label: '🍰 حلويات' },
]

const tickets = ref<Ticket[]>([])
const stationFilter = ref<string | null>(null)
const now = ref(new Date())
const isConnected = ref(true)
let refreshInterval: ReturnType<typeof setInterval>
let clockInterval: ReturnType<typeof setInterval>

const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
const { status: wsStatus, onMessage } = useResortWebSocket(`${wsProtocol}//${location.host}${ENDPOINTS.dining.kdsWs(branchId)}`)
onMessage((data: any) => { if (data?.type === 'tickets_updated') fetchTickets() })

const filteredTickets = computed(() =>
  stationFilter.value ? tickets.value.filter(t => t.station === stationFilter.value) : tickets.value)

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
  if (status === 'pending') return { label: 'معلق', color: 'bg-amber-500' }
  if (status === 'in_progress') return { label: 'قيد التحضير', color: 'bg-blue-500' }
  return { label: 'جاهز', color: 'bg-green-500' }
}
const stationLabel: Record<string, string> = { hot: 'ساخن', grill: 'شواية', cold: 'بارد', dessert: 'حلويات', bar: 'بار' }

async function fetchTickets() {
  try {
    const res = await api.get(ENDPOINTS.dining.kitchenTickets, { params: { branch_id: branchId } })
    tickets.value = res.data
    isConnected.value = true
  } catch {
    isConnected.value = false
  }
}

async function advanceStatus(ticket: Ticket) {
  const next: TicketStatus = ticket.status === 'pending' ? 'in_progress' : 'done'
  try {
    await api.patch(ENDPOINTS.dining.ticketStatus(ticket.id), { status: next })
    ticket.status = next
    if (next === 'done') {
      setTimeout(() => { tickets.value = tickets.value.filter(t => t.id !== ticket.id) }, 2000)
    }
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تحديث حالة التذكرة — حاول تاني')
  }
}

const currentTime = computed(() => now.value.toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit', second: '2-digit' }))
const pendingCount = computed(() => tickets.value.filter(t => t.status === 'pending').length)
const inProgressCount = computed(() => tickets.value.filter(t => t.status === 'in_progress').length)

onMounted(() => {
  fetchTickets()
  refreshInterval = setInterval(fetchTickets, 15_000)
  clockInterval = setInterval(() => { now.value = new Date() }, 1000)
})
onUnmounted(() => { clearInterval(refreshInterval); clearInterval(clockInterval) })
</script>

<template>
  <div class="min-h-screen bg-slate-900 text-white flex flex-col" dir="rtl">
    <header class="bg-slate-800 border-b border-slate-700 px-6 py-3 flex items-center justify-between flex-shrink-0 flex-wrap gap-2">
      <div class="flex items-center gap-4 flex-wrap">
        <div class="flex items-center gap-2">
          <div :class="['w-2.5 h-2.5 rounded-full', isConnected ? 'bg-green-400 animate-pulse' : 'bg-red-400']" />
          <span class="text-sm text-slate-300">{{ isConnected ? 'متصل' : 'منقطع' }}</span>
        </div>
        <div class="flex items-center gap-1.5" :title="wsStatus === 'connected' ? 'تحديث لحظي شغال' : 'بيحاول يعيد الاتصال...'">
          <div :class="['w-2 h-2 rounded-full', wsStatus === 'connected' ? 'bg-cyan-400' : 'bg-slate-500 animate-pulse']" />
          <span class="text-xs text-slate-400">{{ wsStatus === 'connected' ? 'لحظي' : '...جاري إعادة الاتصال' }}</span>
        </div>
        <h1 class="text-xl font-black tracking-wide">🍽️ شاشة المطبخ الموحّدة — Dining KDS</h1>
        <div class="flex gap-3 text-sm">
          <span class="px-2 py-0.5 bg-amber-600 rounded-full font-bold">معلق: {{ pendingCount }}</span>
          <span class="px-2 py-0.5 bg-blue-600 rounded-full font-bold">تحضير: {{ inProgressCount }}</span>
        </div>
      </div>
      <span class="text-2xl font-mono font-bold text-amber-300">{{ currentTime }}</span>
    </header>

    <div class="bg-slate-800 border-b border-slate-700 px-6 py-2 flex gap-2 flex-wrap">
      <button
        v-for="s in STATIONS"
        :key="String(s.val)"
        type="button"
        @click="stationFilter = s.val"
        :class="[
          'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors min-h-[36px]',
          stationFilter === s.val ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600',
        ]"
      >{{ s.label }}</button>
    </div>

    <div class="flex-1 overflow-y-auto p-4">
      <div v-if="filteredTickets.length === 0" class="flex items-center justify-center h-64 text-slate-500">
        <div class="text-center">
          <div class="text-5xl mb-3">✅</div>
          <p class="text-lg">لا توجد طلبات معلقة</p>
        </div>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        <div v-for="ticket in filteredTickets" :key="ticket.id" :class="['rounded-2xl border-2 p-4 flex flex-col transition-all', ticketClasses(ticket)]">
          <div class="flex items-center justify-between mb-3">
            <div>
              <div class="text-2xl font-black">#{{ ticket.order_id }}</div>
              <div class="text-xs text-slate-400">{{ stationLabel[ticket.station] ?? ticket.station }}</div>
            </div>
            <div class="text-left">
              <div :class="['text-xs px-2 py-0.5 rounded-full font-bold text-white mb-1', statusLabel(ticket.status).color]">{{ statusLabel(ticket.status).label }}</div>
              <div :class="[
                'text-lg font-black text-center',
                ticketAge(ticket.created_at) === 'urgent' ? 'text-red-400' : ticketAge(ticket.created_at) === 'warning' ? 'text-amber-400' : 'text-green-400',
              ]">{{ minutesElapsed(ticket.created_at) }}د</div>
            </div>
          </div>

          <ul class="flex-1 space-y-1.5 mb-3">
            <li v-for="item in ticket.items_snapshot" :key="item.order_item_id" class="text-sm">
              <div class="flex items-start gap-2 px-1.5 py-1">
                <span class="bg-white/20 text-white rounded px-1.5 py-0.5 text-xs font-bold flex-shrink-0">{{ item.quantity }}</span>
                <span class="leading-tight flex-1">{{ item.name }}</span>
              </div>
              <p v-if="item.notes" class="text-xs text-amber-300 mr-6 mt-0.5">⚠️ {{ item.notes }}</p>
            </li>
          </ul>

          <div class="space-y-2">
            <div class="text-xs text-slate-400 text-center">
              {{ parseApiTimestamp(ticket.created_at).toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' }) }}
            </div>
            <button
              v-if="ticket.status === 'pending'"
              type="button"
              @click="advanceStatus(ticket)"
              class="w-full py-2.5 bg-blue-600 hover:bg-blue-500 rounded-xl text-sm font-bold transition-colors active:scale-95 min-h-[48px]"
            >▶ بدء التحضير</button>
            <button
              v-else-if="ticket.status === 'in_progress'"
              type="button"
              @click="advanceStatus(ticket)"
              class="w-full py-2.5 bg-green-600 hover:bg-green-500 rounded-xl text-sm font-bold transition-colors active:scale-95 min-h-[48px]"
            >✓ جاهز للتسليم</button>
            <div v-else class="w-full py-2.5 bg-green-700 rounded-xl text-sm font-bold text-center text-green-200">✓ تم التسليم</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
